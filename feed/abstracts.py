"""
Abstracts from PubMed, by DOI, many at a time.

The feeds give a title and nothing else worth reading. PubMed has abstracts for nearly
all research papers in these journals, a few days after publication, so a paper without
one is simply asked again on the next run.

Two E-utilities calls per batch: `esearch` for the PMIDs of up to 40 DOIs, then
`efetch` for the records, matched back to DOIs through each record's ArticleIdList.
"""

import json
import logging
from urllib.parse import quote
from xml.etree import ElementTree as ET

from . import net

log = logging.getLogger(__name__)

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
BATCH = 40


# PubMed publication types that mark an item as something other than a research paper.
NOT_RESEARCH = {"news", "letter", "comment", "editorial", "review", "systematic review",
                "published erratum", "retraction notice", "retraction of publication",
                "case reports", "interview", "biography", "portrait", "introductory journal article",
                "practice guideline", "guideline", "expression of concern", "lecture", "congress"}


MIN_WORDS = 90   # research abstracts in these journals run 96 words and up


def is_research(rec: dict) -> bool:
    """For a backfill: a research paper has a full abstract and no non-research
    publication type. PubMed types previews, Perspectives and Policy Forums as plain
    journal articles, but their abstracts are a teaser of 10 to 85 words. Checked
    against the feeds' own labels: every research paper passes, no opinion piece does."""
    types = {t.lower() for t in rec.get("types", [])}
    words = len((rec.get("abstract") or "").split())
    return words >= MIN_WORDS and not (types & NOT_RESEARCH)


def parse_efetch(xml) -> dict[str, dict]:
    """{doi: {"pmid", "abstract", "types"}} for every PubmedArticle that has a DOI.

    Labelled sections (BACKGROUND, METHODS, ...) are joined as "LABEL: text", in order.
    """
    root = ET.fromstring(xml)
    out = {}
    for art in root.iter("PubmedArticle"):
        doi = None
        for aid in art.iter("ArticleId"):
            if aid.get("IdType") == "doi" and aid.text:
                doi = aid.text.strip().lower()
                break
        if doi is None:
            for loc in art.iter("ELocationID"):
                if loc.get("EIdType") == "doi" and loc.text:
                    doi = loc.text.strip().lower()
                    break
        if doi is None:
            continue
        parts = []
        for node in art.iter("AbstractText"):
            text = " ".join("".join(node.itertext()).split())
            if not text:
                continue
            label = node.get("Label")
            parts.append(f"{label}: {text}" if label else text)
        pmid = art.findtext("MedlineCitation/PMID")
        types = [t.text.strip() for t in art.iter("PublicationType") if t.text]
        out[doi] = {"pmid": pmid, "abstract": "\n\n".join(parts) or None, "types": types}
    return out


def lookup_many(fetch, dois: list[str]) -> dict[str, dict]:
    """PubMed records for as many of `dois` as PubMed has. A failed batch is logged and
    skipped: those papers are asked again next run."""
    found: dict[str, dict] = {}
    for i in range(0, len(dois), BATCH):
        chunk = dois[i:i + BATCH]
        term = " OR ".join(f'"{d}"[doi]' for d in chunk)
        try:
            body = net.text(fetch, f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&retmax=200"
                                   f"&term={quote(term)}&{net.ncbi_params()}")
            ids = json.loads(body or "{}").get("esearchresult", {}).get("idlist", [])
            if not ids:
                continue
            xml = net.text(fetch, f"{EUTILS}/efetch.fcgi?db=pubmed&retmode=xml"
                                  f"&id={','.join(ids)}&{net.ncbi_params()}")
            if xml:
                wanted = set(chunk)
                found.update({d: r for d, r in parse_efetch(xml).items() if d in wanted})
        except (ValueError, ET.ParseError) as exc:
            log.warning("PubMed batch failed: %s", exc)
    return found
