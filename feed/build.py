"""
One run: read every journal, find what is new, fill in what older papers were still
missing, and write the site's data.

    python -m feed.build              # the daily run
    python -m feed.build --no-network-figures   # skip figure routes (quick local test)
    python -m feed.build --backfill 30          # also fill the last 30 days

State lives in `state/papers.json` (every paper of the last 26 weeks and its bookkeeping).
Abstracts are the publishers' text, and the repository is public, so they are never
saved: each run fetches them from PubMed for the papers that still need a summary. The site reads `site/data/feed.json` (the last six weeks) and
`site/data/weeks/<monday>.json` (older weeks). Both are committed by the Action.

Papers are grouped by the week they were first seen, so a week's edition never changes
after the fact except to gain figures. A paper keeps being re-checked for six weeks:
PubMed abstracts arrive within days, PMC's open-access figures within two to five weeks.
When figures arrive for a paper from an earlier week, it is marked `figures_added` and
the site shows it again under "New figures".
"""

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import abstracts, figures, net, sources, summary

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "papers.json"
SITE_DATA = ROOT / "site" / "data"

ACTIVE_DAYS = 42        # keep looking for abstracts and figures this long
KEEP_WEEKS = 26         # drop papers first seen longer ago than this
FEED_WEEKS = 6          # weeks in feed.json; older weeks go to weeks/<monday>.json
OTHER_MEMORY_DAYS = 60  # remember non-research DOIs this long, so pages are read once
SUMMARY_LIMIT = int(os.environ.get("SUMMARY_LIMIT", "200"))

log = logging.getLogger("feed")


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def load_config() -> dict:
    return yaml.safe_load((ROOT / "journals.yaml").read_text())


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"papers": {}, "not_research": {}}


def save_json(path: Path, data, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    if compact:
        tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    else:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True))
    tmp.replace(path)


# ── Steps ────────────────────────────────────────────────────────────────────

def _new_paper(it: sources.Item, first_seen: date, page: str | None) -> dict:
    return {
        "doi": it.doi, "journal": it.journal, "title": it.title, "link": it.link,
        "published": it.published.isoformat() if it.published else None,
        "first_seen": first_seen.isoformat(), "article_type": it.article_type,
        "abstract": None, "pmid": None, "summary": None, "summary_source": None,
        "licence": None, "licence_checked": None, "pmcid": None,
        "figures": [], "figure_source": None, "figures_added": None,
        "preview": figures.og_image(page, it.link) if page else None,
        "preview_tried": page is not None,
    }


def _take(fetch, it: sources.Item, jcfg: dict, state: dict, today: date,
          first_seen: date) -> bool:
    """Add one listed item if it is a new research paper. Non-research DOIs are
    remembered, so a Nature page is read once."""
    papers, other = state["papers"], state["not_research"]
    if it.doi in papers or it.doi in other:
        return False
    if it.kind in (sources.COMMENTARY, sources.OTHER):
        other[it.doi] = today.isoformat()
        return False
    page = None
    if it.kind is None:                           # Nature family: the page says
        page = net.text(fetch, it.link)
        if page is None:
            return False                          # try again next run
        it.article_type, it.kind = sources.kind_from_page(page, jcfg)
        if it.kind != sources.RESEARCH:
            other[it.doi] = today.isoformat()
            return False
    papers[it.doi] = _new_paper(it, first_seen, page)
    return True


def poll(fetch, config: dict, state: dict, today: date) -> int:
    """Add every new research paper the sources list. Returns how many were added."""
    added = 0
    for jcfg in config["journals"]:
        items = sources.items_for(fetch, jcfg, config, today)
        log.info("%-32s %3d items", jcfg["name"], len(items))
        added += sum(_take(fetch, it, jcfg, state, today, today) for it in items)
    return added


def _dated(it_published: date | None, today: date, since: date) -> date:
    """When the daily run would have first seen a paper: the day it went online."""
    if it_published is None:
        return today
    return min(max(it_published, since), today)


def backfill(fetch, config: dict, state: dict, today: date, days: int) -> set[str]:
    """Fill the last `days` days as if the daily run had been going all along: every
    research paper the journals put online in that time, filed under the week it went
    online. Papers already held are re-filed the same way. Returns the DOIs filed, so
    figures found for them now are not shown again as "New figures".

    The feeds only hold the latest items, so the backfill lists works from Crossref by
    ISSN. Crossref carries no section, so `type_from: field` journals are typed by
    PubMed's publication types (`abstracts.is_research`); papers PubMed has not indexed
    yet are left for the daily run to meet in the feed."""
    since = today - timedelta(days=days)
    papers, other = state["papers"], state["not_research"]
    filed: set[str] = set()
    for p in papers.values():
        pub = date.fromisoformat(p["published"]) if p["published"] else None
        if pub and pub >= since and p["first_seen"] >= since.isoformat():
            p["first_seen"] = _dated(pub, today, since).isoformat()
            filed.add(p["doi"])

    for jcfg in config["journals"]:
        if not jcfg.get("issn"):
            continue
        items = sources.crossref_items(fetch, jcfg, config, today, days=days, backfill=True)
        ask = [it for it in items if it.kind == sources.PUBMED
               and it.doi not in papers and it.doi not in other]
        records = abstracts.lookup_many(fetch, [it.doi for it in ask]) if ask else {}
        added = unknown = 0
        for it in items:
            if it.kind == sources.PUBMED:
                if it.doi in papers or it.doi in other:
                    continue
                rec = records.get(it.doi)
                if rec is None:
                    unknown += 1
                    continue
                it.kind = sources.RESEARCH if abstracts.is_research(rec) else sources.OTHER
            if _take(fetch, it, jcfg, state, today, _dated(it.published, today, since)):
                filed.add(it.doi)
                added += 1
        log.info("%-32s %3d works, %3d added%s", jcfg["name"], len(items), added,
                 f", {unknown} not in PubMed yet" if unknown else "")
    return filed


def active(state: dict, today: date) -> list[dict]:
    cutoff = (today - timedelta(days=ACTIVE_DAYS)).isoformat()
    return [p for p in state["papers"].values() if p["first_seen"] >= cutoff]


def fill_abstracts(fetch, papers: list[dict], upgrade: bool = False) -> int:
    """Abstracts, held for this run only, for the papers that still need a summary (and,
    with `upgrade`, those whose summary Claude has not written yet)."""
    need = [p for p in papers if not p["abstract"]
            and (not p["summary"] or (upgrade and p["summary_source"] != "claude"))]
    found = abstracts.lookup_many(fetch, [p["doi"] for p in need]) if need else {}
    n = 0
    for p in need:
        rec = found.get(p["doi"])
        if rec:
            p["pmid"] = rec["pmid"]
            if rec["abstract"]:
                p["abstract"] = rec["abstract"]
                n += 1
    return n


def fill_licences(fetch, papers: list[dict], today: date) -> None:
    for p in papers:
        if p["licence_checked"]:
            continue
        answered, url = figures.crossref_licence(fetch, p["doi"])
        if answered:
            p["licence"], p["licence_checked"] = url, today.isoformat()


def fill_previews(fetch, papers: list[dict]) -> None:
    """One try per paper at the publisher's link-preview image. Most publishers other
    than Springer Nature refuse scripted requests; those papers stay text cards."""
    for p in papers:
        if p["preview_tried"]:
            continue
        p["preview_tried"] = True
        page = net.text(fetch, p["link"])
        if page:
            p["preview"] = figures.og_image(page, p["link"])


def fill_figures(fetch, papers: list[dict], today: date, filed: set[str] = frozenset()) -> int:
    """Full figures where the licence allows. Returns how many papers gained them.
    A paper from an earlier week is marked `figures_added`, unless the backfill filed it
    in this run: it was never shown without them."""
    this_week = monday(today).isoformat()
    gained = 0

    def got(p, figs, source, licence=None):
        nonlocal gained
        p["figures"], p["figure_source"] = figs, source
        if licence:
            p["licence"] = licence
        if p["first_seen"] < this_week and p["doi"] not in filed:
            p["figures_added"] = today.isoformat()
        gained += 1

    pending = [p for p in papers if p["figure_source"] not in ("springer", "pmc")]
    for p in pending:
        if p["licence"] and figures.springer_figure_url(p["doi"], 1):
            figs = figures.springer(fetch, p["doi"])
            if figs:
                got(p, figs, "springer")

    pending = [p for p in pending if p["figure_source"] not in ("springer", "pmc")]
    found = figures.pmcids(fetch, [p["doi"] for p in pending if not p["pmcid"]])
    for p in pending:
        p["pmcid"] = p["pmcid"] or found.get(p["doi"])
    for p in pending:
        if not p["pmcid"]:
            continue
        code, figs = figures.pmc(fetch, p["pmcid"])
        if figs:
            lic = p["licence"] or code_to_url(code)
            got(p, figs, "pmc", lic)
    return gained


def code_to_url(code: str | None) -> str | None:
    """PMC's 'CC BY-NC-ND' as a licence URL, for papers Crossref had no CC licence for."""
    if not code or not code.upper().startswith("CC"):
        return None
    if code.upper() == "CC0":
        return "https://creativecommons.org/publicdomain/zero/1.0/"
    parts = code.split(" ", 1)
    kind = parts[1].lower() if len(parts) > 1 else "by"
    return f"https://creativecommons.org/licenses/{kind}/4.0/"


def fill_summaries(papers: list[dict], client=None) -> int:
    n = 0
    for p in papers:
        if not p["abstract"]:
            continue
        if client and p["summary_source"] != "claude" and n < SUMMARY_LIMIT:
            text = summary.claude(client, p["title"], p["abstract"])
            n += 1
            if text:
                p["summary"], p["summary_source"] = text, "claude"
                continue
        if not p["summary"]:
            p["summary"], p["summary_source"] = summary.extractive(p["abstract"]), "abstract"
    return n


def forget_abstracts(state: dict) -> None:
    """Abstracts never reach the committed state; the summary is what is kept."""
    for p in state["papers"].values():
        p["abstract"] = None


def prune(state: dict, today: date) -> None:
    cutoff = (monday(today) - timedelta(weeks=KEEP_WEEKS)).isoformat()
    state["papers"] = {d: p for d, p in state["papers"].items() if p["first_seen"] >= cutoff}
    other_cut = (today - timedelta(days=OTHER_MEMORY_DAYS)).isoformat()
    state["not_research"] = {d: s for d, s in state["not_research"].items() if s >= other_cut}


# ── The site's data ──────────────────────────────────────────────────────────

def public(p: dict) -> dict:
    """What the page needs of one paper. Abstracts stay out: the summary and a link do.
    Links and images are checked again here, so state saved before the check still
    publishes only https."""
    full = [f for f in p["figures"] if net.https_url(f["url"]) == f["url"]]
    preview = net.https_url(p.get("preview"))
    if full:
        figs, kind = full, "full"
    elif preview:
        figs, kind = [{"url": preview, "label": "Preview", "caption": None}], "preview"
    else:
        figs, kind = [], "none"
    return {
        "doi": p["doi"], "journal": p["journal"], "title": p["title"],
        "link": net.https_url(p["link"]) or sources.doi_url(p["doi"]),
        "published": p["published"], "week": monday(date.fromisoformat(p["first_seen"])).isoformat(),
        "summary": p["summary"], "figures": figs, "figure_kind": kind,
        "licence": figures.licence_name(p["licence"]) if kind == "full" else None,
        "figures_added": p["figures_added"],
    }


def _order(p: dict) -> tuple:
    rank = {"full": 0, "preview": 1, "none": 2}[p["figure_kind"]]
    return (p["week"], -rank, p["published"] or "", p["doi"])


def write_site(config: dict, state: dict, today: date) -> dict:
    rows = sorted((public(p) for p in state["papers"].values()), key=_order, reverse=True)
    weeks = sorted({r["week"] for r in rows}, reverse=True)
    recent, older = weeks[:FEED_WEEKS], weeks[FEED_WEEKS:]
    weeks_dir = SITE_DATA / "weeks"
    weeks_dir.mkdir(parents=True, exist_ok=True)
    for f in weeks_dir.glob("*.json"):
        if f.stem not in older:
            f.unlink()
    for w in older:
        save_json(weeks_dir / f"{w}.json", [r for r in rows if r["week"] == w], compact=True)
    feed = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "today": today.isoformat(),
        "journals": [{"name": j["name"], "short": j.get("short", j["name"]),
                      "colour": j.get("colour", "#334155")} for j in config["journals"]],
        "weeks": weeks,
        "archived": older,
        "papers": [r for r in rows if r["week"] in recent],
    }
    save_json(SITE_DATA / "feed.json", feed, compact=True)
    return feed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--today", help="pretend it is this date (YYYY-MM-DD)")
    ap.add_argument("--no-network-figures", action="store_true",
                    help="skip licence, preview and figure lookups")
    ap.add_argument("--backfill", type=int, metavar="DAYS",
                    help="also list the last DAYS days from Crossref and file each paper "
                         "under the week it went online")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    config, state = load_config(), load_state()
    fetch = net.fetch
    n_before = len(state["papers"])

    poll(fetch, config, state, today)
    filed = backfill(fetch, config, state, today, args.backfill) if args.backfill else set()
    added = len(state["papers"]) - n_before
    papers = active(state, today)
    client = summary.claude_client()
    n_abs = fill_abstracts(fetch, papers, upgrade=client is not None)
    gained = 0
    if not args.no_network_figures:
        fill_licences(fetch, papers, today)
        fill_previews(fetch, papers)
        gained = fill_figures(fetch, papers, today, filed)
    n_claude = fill_summaries(papers, client)
    prune(state, today)
    forget_abstracts(state)
    save_json(STATE, state)
    feed = write_site(config, state, today)

    shown = feed["papers"]
    log.info("new papers %d · abstracts found %d · gained figures %d · Claude summaries %d",
             added, n_abs, gained, n_claude)
    log.info("feed: %d papers in %d weeks — full figures %d, preview %d, text %d",
             len(shown), len(feed["weeks"]) - len(feed["archived"]),
             sum(p["figure_kind"] == "full" for p in shown),
             sum(p["figure_kind"] == "preview" for p in shown),
             sum(p["figure_kind"] == "none" for p in shown))
    return 0


if __name__ == "__main__":
    sys.exit(main())
