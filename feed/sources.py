"""
Where papers come from: a journal's RSS feed, or Crossref by ISSN.

The journals publish RSS 1.0 (Nature, Science, Cell, NEJM, the Lancet), and each says
what kind of article an item is in its own way (see `journals.yaml` for the four rules).
What comes out is the same for all of them: a DOI (lowercased), a title, a link, a
publication date, and a kind: `research`, `commentary` or `other`.

Nature and its sister journals carry no type in the feed, so their items come back with
`kind=None`; the build reads the article page once, when the item is first seen, and
`kind_from_page` decides from its `citation_article_type` meta tag.
"""

import html
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote
from xml.etree import ElementTree as ET

from . import net

RESEARCH, COMMENTARY, OTHER = "research", "commentary", "other"
PUBMED = "pubmed"     # a backfilled item whose type PubMed decides

_DC = "http://purl.org/dc/elements/1.1/"
_TAG = re.compile(r"<[^>]+>")
_SECTION_PREFIX = re.compile(r"^\[[^\]]{1,40}\]\s*")     # the Lancet's "[Comment] "
_DOI = re.compile(r"(10\.\d{4,9}/[^\s?#&\"<>]+)")
_PAGE_TYPE = re.compile(r'<meta\s+name="citation_article_type"\s+content="([^"]*)"', re.I)


@dataclass
class Item:
    journal: str
    doi: str
    title: str
    link: str
    published: Optional[date]
    article_type: Optional[str]   # the feed's (or page's) own label, as written
    kind: Optional[str]           # None: read the article page to decide


def _local(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        ns, _, local = tag[1:].partition("}")
        return ns, local
    return "", tag


def clean(text: Optional[str]) -> str:
    text = html.unescape(_TAG.sub("", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _date(text: Optional[str]) -> Optional[date]:
    if not text:
        return None
    text = text.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).date()     # RSS 2.0 pubDate, RFC 822
    except (TypeError, ValueError):
        return None


def _doi(fields: dict) -> Optional[str]:
    for key in ("doi", "identifier", "guid", "link"):
        m = _DOI.search(fields.get(key) or "")
        if m:
            return m.group(1).rstrip(".").lower()
    return None


def is_never(title: str, config: dict) -> bool:
    return any(title.lower().startswith(p.lower()) for p in config.get("never_titles", []))


def _match(label: Optional[str], labels) -> bool:
    return label is not None and label.strip().lower() in {x.lower() for x in labels or ()}


def classify(label: Optional[str], journal_cfg: dict) -> str:
    """A type label, by the journal's lists. Unrecognised is `other`, never research."""
    if _match(label, journal_cfg.get("research")):
        return RESEARCH
    if _match(label, journal_cfg.get("commentary")):
        return COMMENTARY
    return OTHER


def parse_feed(xml, journal_cfg: dict, config: dict) -> list[Item]:
    """Every item in the feed that has a DOI and a title, typed by the journal's rule."""
    root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    rule = journal_cfg["type_from"]
    out = []
    for node in root.iter():
        if _local(node.tag)[1] != "item":
            continue
        fields: dict[str, str] = {}
        for child in node:
            ns, local = _local(child.tag)
            key = "dc_title" if (local == "title" and ns == _DC) else local
            fields.setdefault(key, child.text or "")
        title = _SECTION_PREFIX.sub("", clean(fields.get("dc_title") or fields.get("title")))
        doi = _doi(fields)
        if not title or not doi:
            continue
        pub = _date(fields.get("publicationDate") or fields.get("date") or fields.get("pubDate"))
        link = (fields.get("link") or fields.get("url") or f"https://doi.org/{doi}").strip()

        label, kind = None, None
        if is_never(title, config):
            kind = OTHER
        elif rule == "field":
            label = clean(fields.get(journal_cfg["field"])) or None
            kind = classify(label, journal_cfg)
        elif rule == "doi":
            original = (fields.get("doi") or fields.get("identifier") or doi)
            if any(p.lower() in original.lower() for p in journal_cfg.get("research", [])):
                kind = RESEARCH
            elif any(p.lower() in original.lower() for p in journal_cfg.get("commentary", [])):
                kind = COMMENTARY
            else:
                kind = OTHER
        elif rule == "all":
            kind = RESEARCH
        elif rule == "page":
            kind = None
        else:
            raise ValueError(f"{journal_cfg['name']}: unknown type_from {rule!r}")
        out.append(Item(journal=journal_cfg["name"], doi=doi, title=title, link=link,
                        published=pub, article_type=label, kind=kind))
    return out


def page_type(page_html: str) -> Optional[str]:
    """The article page's own statement of what it is, or None if it makes none."""
    m = _PAGE_TYPE.search(page_html or "")
    return html.unescape(m.group(1)).strip() if m else None


def kind_from_page(page_html: str, journal_cfg: dict) -> tuple[Optional[str], str]:
    """(label, kind) for a `type_from: page` journal, from its article page."""
    label = page_type(page_html)
    return label, classify(label, journal_cfg)


# ── Crossref, for journals whose RSS is too short ────────────────────────────

def _crossref_date(w: dict) -> Optional[date]:
    """The online date if Crossref has a full one, else the day the DOI was registered.
    Elsevier records only the issue month, and registration is the day it went online."""
    for key in ("published-online", "published", "created"):
        parts = (w.get(key) or {}).get("date-parts") or [[]]
        if len(parts[0]) == 3:
            try:
                return date(*parts[0])
            except (TypeError, ValueError):
                pass
    return None


def parse_crossref(payload: dict, journal_cfg: dict, config: dict, backfill: bool = False) -> list[Item]:
    """Crossref works as items. The daily source (`type_from: all`) takes every work as
    research; a backfill applies the journal's own rule where Crossref can carry it."""
    rule = journal_cfg["type_from"] if backfill else "all"
    out = []
    for w in payload.get("message", {}).get("items", []):
        doi = (w.get("DOI") or "").lower()
        title = clean((w.get("title") or [""])[0])
        if not doi or not title:
            continue
        if is_never(title, config):
            kind = OTHER
        elif rule == "all":
            kind = RESEARCH
        elif rule == "doi":
            hit = lambda key: any(x.lower() in doi for x in journal_cfg.get(key, []))
            kind = RESEARCH if hit("research") else COMMENTARY if hit("commentary") else OTHER
        elif rule == "page":
            kind = None
        else:
            kind = PUBMED
        out.append(Item(journal=journal_cfg["name"], doi=doi, title=title,
                        link=w.get("URL") or f"https://doi.org/{doi}", published=_crossref_date(w),
                        article_type=None if backfill else w.get("type"), kind=kind))
    return out


def crossref_items(fetch, journal_cfg: dict, config: dict, today: date,
                   days: int = 14, backfill: bool = False) -> list[Item]:
    """The journal's works of the last `days` days, every page of them. The daily source
    filters by online date; a backfill by registration date, which every publisher sets
    (Elsevier, Science and the Lancet give no online date)."""
    since = (today - timedelta(days=days)).isoformat()
    field = "created-date" if backfill else "online-pub-date"
    base = (f"https://api.crossref.org/journals/{journal_cfg['issn']}/works?rows=200"
            f"&filter=from-{field}:{since},until-{field}:{today.isoformat()},type:journal-article"
            f"&select=DOI,title,URL,published-online,published,created,type")
    if net.crossref_params():                      # empty without CONTACT_EMAIL; "&&" is a 400
        base += "&" + net.crossref_params()
    out, cursor = [], "*"
    for _ in range(20):                                   # 4,000 works: far beyond a month
        body = net.text(fetch, f"{base}&cursor={quote(cursor)}")
        if not body:
            break
        payload = json.loads(body)
        items = parse_crossref(payload, journal_cfg, config, backfill)
        out.extend(items)
        cursor = payload.get("message", {}).get("next-cursor")
        if not cursor or len(payload.get("message", {}).get("items", [])) < 200:
            break
    return out


def items_for(fetch, journal_cfg: dict, config: dict, today: date) -> list[Item]:
    """The journal's current items, or [] when its source cannot be read today."""
    if journal_cfg.get("source") == "crossref":
        return crossref_items(fetch, journal_cfg, config, today)
    body = net.text(fetch, journal_cfg["rss"])
    if not body:
        return []
    try:
        return parse_feed(body, journal_cfg, config)
    except ET.ParseError:
        return []


def doi_url(doi: str) -> str:
    return f"https://doi.org/{quote(doi, safe='/')}"
