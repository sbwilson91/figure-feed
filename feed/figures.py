"""
A paper's figures, by the route its licence allows. Nothing is downloaded or stored:
the page links each image where it already lives.

  springer  A CC-licensed Springer Nature paper serves its figures at a URL built from
            the DOI. Full figures, available the day the paper is.
  pmc       A paper in PubMed Central's open-access subset (licence CC) has its figures
            and their captions in PMC's public bucket on AWS, typically two to four
            weeks after publication. Full figures with captions.
  preview   Otherwise, the `og:image` the publisher offers for link previews, where it
            is a real picture rather than the journal's logo. One image, shown as a
            preview with a link back, the way a link preview shows it.

Only CC-licensed papers get full figures. Everything else is a preview or a text card.
`fetch(url) -> (status, content_type, body)` is passed in, so tests run with no network.
"""

import html
import json
import re
from urllib.parse import quote, urljoin
from xml.etree import ElementTree as ET

from . import net

MAX_FIGURES = 8
MAX_CAPTION = 220
PMC_BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"

_SPRINGER_DOI = re.compile(r"10\.1038/(s(\d{5})-(\d{3})-(\d+)-[0-9xX])$")
_LOGO = re.compile(r"logo|favicon|placeholder|default[-_]?(image|share)|brand|banner"
                   r"|main[-_ ]?visual|website", re.I)
_OG_IMAGE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image(?::url)?["\'][^>]*content=["\']([^"\']+)'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']og:image(?::url)?["\']',
    re.I)
_XLINK = "{http://www.w3.org/1999/xlink}href"
_S3_KEY = re.compile(r"<Key>([^<]+)</Key>")


def _caption(text: str | None) -> str | None:
    text = " ".join((text or "").split()).strip()
    if not text:
        return None
    return text if len(text) <= MAX_CAPTION else text[:MAX_CAPTION].rsplit(" ", 1)[0] + "…"


# ── Licence ──────────────────────────────────────────────────────────────────

def cc_licence(crossref_message: dict) -> str | None:
    """The Creative Commons licence URL that covers the published version, or None.
    Elsevier and others also list text-mining (`tdm`) licences, which do not count."""
    for lic in crossref_message.get("license") or []:
        url = lic.get("URL") or ""
        if "creativecommons.org" in url and lic.get("content-version") in ("vor", "unspecified"):
            return url
    return None


def licence_name(url: str | None) -> str | None:
    """'CC BY 4.0' from https://creativecommons.org/licenses/by/4.0/."""
    if not url:
        return None
    m = re.search(r"creativecommons\.org/(?:licenses|publicdomain)/([a-z-]+)/?([\d.]+)?", url)
    if not m:
        return None
    kind, ver = m.groups()
    name = "CC0" if kind == "zero" else "CC " + kind.upper()
    return f"{name} {ver}" if ver else name


def crossref_licence(fetch, doi: str) -> tuple[bool, str | None]:
    """(answered, cc_url). `answered` is False when Crossref could not be asked."""
    tail = net.crossref_params()
    try:
        status, _, body = fetch(f"https://api.crossref.org/works/{quote(doi, safe='/')}"
                                + (f"?{tail}" if tail else ""))
    except OSError:
        return False, None
    if status == 404:
        return True, None
    if status != 200:
        return False, None
    return True, cc_licence(json.loads(body).get("message", {}))


# ── Springer Nature ──────────────────────────────────────────────────────────

def springer_figure_url(doi: str, k: int) -> str | None:
    """Figure `k` of a Springer Nature article, from its DOI alone:
    10.1038/s41536-026-00514-6 → …/41536_2026_514_Fig{k}_HTML.png."""
    m = _SPRINGER_DOI.match(doi)
    if not m:
        return None
    suffix, journal, year, number = m.groups()
    return ("https://media.springernature.com/full/springer-static/image/"
            f"art%3A10.1038%2F{suffix}/MediaObjects/"
            f"{journal}_2{year}_{int(number)}_Fig{k}_HTML.png")


def springer(fetch, doi: str) -> list[dict]:
    """Probes Fig1, Fig2, … until one is missing. A paywalled article answers 404."""
    figures = []
    for k in range(1, MAX_FIGURES + 1):
        url = springer_figure_url(doi, k)
        if url is None:
            break
        try:
            status, ctype, _ = fetch(url, method="HEAD")
        except OSError:
            break
        if status != 200 or not ctype.startswith("image/"):
            break
        figures.append({"url": url, "label": f"Figure {k}", "caption": None})
    return figures


# ── PubMed Central ───────────────────────────────────────────────────────────

def pmcids(fetch, dois: list[str]) -> dict[str, str]:
    """{doi: PMCID} for those of `dois` that PMC holds."""
    out = {}
    for i in range(0, len(dois), 150):
        body = net.text(fetch, f"{IDCONV}?format=json&{net.ncbi_params()}"
                               f"&ids={','.join(quote(d, safe='/') for d in dois[i:i + 150])}")
        if not body:
            continue
        try:
            records = json.loads(body).get("records", [])
        except ValueError:
            continue
        for rec in records:
            if rec.get("pmcid") and rec.get("doi"):
                out[rec["doi"].lower()] = rec["pmcid"]
    return out


def parse_pmc_figures(xml, files: set[str]) -> list[dict]:
    """Figures from a PMC article's XML, in reading order, each with its caption title
    (or first caption sentence). Only figures whose image is in the bucket count."""
    root = ET.fromstring(xml)
    figures = []
    for fig in root.iter("fig"):
        graphic = fig.find(".//graphic")
        href = graphic.get(_XLINK) if graphic is not None else None
        if not href:
            continue
        name = href if "." in href.rsplit("/", 1)[-1] else href + ".webp"
        if name not in files:
            stem = name.rsplit(".", 1)[0]
            name = next((f for f in files if f.rsplit(".", 1)[0] == stem), None)
            if name is None:
                continue
        label = " ".join("".join(fig.findtext("label") or "").split()).rstrip(".:") or "Figure"
        cap = fig.find("caption")
        caption = None
        if cap is not None:
            title = cap.find("title")
            caption = "".join(title.itertext()) if title is not None else None
            if not (caption and caption.strip()):
                p = cap.find("p")
                if p is not None:
                    caption = re.split(r"(?<=[.!?])\s", " ".join("".join(p.itertext()).split()), maxsplit=1)[0]
        figures.append({"name": name, "label": label, "caption": _caption(caption)})
    return figures


def pmc(fetch, pmcid: str) -> tuple[str | None, list[dict]]:
    """(licence code, figures) from PMC's open-access bucket; (None, []) when the paper
    is not open access there (an author manuscript, say) or not there yet."""
    listing = net.text(fetch, f"{PMC_BUCKET}/?list-type=2&prefix={pmcid}.")
    if not listing:
        return None, []
    keys = _S3_KEY.findall(listing)
    if not keys:
        return None, []
    version = max({k.split("/", 1)[0] for k in keys}, key=lambda v: int(v.rsplit(".", 1)[1]))
    files = {k.split("/", 1)[1] for k in keys if k.startswith(version + "/")}
    meta = net.text(fetch, f"{PMC_BUCKET}/{version}/{version}.json")
    if not meta:
        return None, []
    meta = json.loads(meta)
    code = meta.get("license_code") or ""
    if not (meta.get("is_pmc_openaccess") and code.upper().startswith("CC")):
        return None, []
    xml = net.text(fetch, f"{PMC_BUCKET}/{version}/{version}.xml")
    if not xml:
        return code, []
    try:
        figs = parse_pmc_figures(xml, files)
    except ET.ParseError:
        return code, []
    return code, [{"url": f"{PMC_BUCKET}/{version}/{quote(f['name'])}", "label": f["label"],
                   "caption": f["caption"]} for f in figs[:MAX_FIGURES]]


# ── Link preview ─────────────────────────────────────────────────────────────

def og_image(page_html: str, base_url: str) -> str | None:
    m = _OG_IMAGE.search(page_html or "")
    if not m:
        return None
    url = net.https_url(quote(urljoin(base_url, html.unescape(m.group(1) or m.group(2)).strip()),
                              safe=":/?&=%#~+,;@!$'()*"))
    return None if not url or _LOGO.search(url) else url
