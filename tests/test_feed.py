"""Offline tests: every network call goes through a fake `fetch`."""

import json
import unittest
from datetime import date

from feed import abstracts, build, figures, sources, summary

CONFIG = {"never_titles": ["Correction:", "Author Correction"]}

SCIENCE_RSS = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:prism="http://prismstandard.org/namespaces/basic/2.0/">
 <item rdf:about="https://www.science.org/doi/10.1126/science.adx1">
  <title>A &lt;i&gt;new&lt;/i&gt; kidney</title>
  <link>https://www.science.org/doi/10.1126/science.adx1</link>
  <dc:identifier>doi:10.1126/science.ADX1</dc:identifier>
  <dc:date>2026-10-23T00:00:00Z</dc:date>
  <dc:type>Research Article</dc:type>
 </item>
 <item rdf:about="x">
  <title>Why kidneys matter</title>
  <link>https://www.science.org/doi/10.1126/science.adx2</link>
  <dc:identifier>doi:10.1126/science.adx2</dc:identifier>
  <dc:type>Perspective</dc:type>
 </item>
 <item rdf:about="y">
  <title>Correction: an earlier paper</title>
  <link>https://www.science.org/doi/10.1126/science.adx3</link>
  <dc:type>Research Article</dc:type>
 </item>
</rdf:RDF>"""

SCIENCE = {"name": "Science", "type_from": "field", "field": "type",
           "research": ["Research Article"], "commentary": ["Perspective"]}
NEJM = {"name": "NEJM", "type_from": "doi", "research": ["/NEJMoa"]}

EFETCH = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article>
<Abstract><AbstractText Label="BACKGROUND">Kidneys fail.</AbstractText>
<AbstractText Label="CONCLUSIONS">Drug X halved the decline in kidney function. More text.</AbstractText>
</Abstract></Article></MedlineCitation>
<PubmedData><ArticleIdList><ArticleId IdType="doi">10.1056/NEJMoa1</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>"""

PMC_XML = """<article xmlns:xlink="http://www.w3.org/1999/xlink"><body>
<fig id="f1"><label>Fig. 1</label><caption><title>Organoids grow.</title><p>Long text.</p></caption>
 <graphic xlink:href="41586_2026_1_Fig1_HTML"/></fig>
<fig id="f2"><label>Figure 2</label><caption><p>Nephrons form in vitro. Then more.</p></caption>
 <graphic xlink:href="gr2.webp"/></fig>
<fig id="f3"><label>Fig. 3</label><graphic xlink:href="missing.webp"/></fig>
</body></article>"""


def fake(routes):
    """A fetch that answers from {url-substring: (status, ctype, body)}."""
    calls = []

    def fetch(url, timeout=30, method="GET"):
        calls.append(url)
        for key, resp in routes.items():
            if key in url:
                status, ctype, body = resp
                return status, ctype, body.encode() if isinstance(body, str) else body
        return 404, "", b""
    fetch.calls = calls
    return fetch


class Sources(unittest.TestCase):
    def test_field_rule(self):
        items = sources.parse_feed(SCIENCE_RSS, SCIENCE, CONFIG)
        by = {i.doi: i for i in items}
        self.assertEqual(by["10.1126/science.adx1"].kind, sources.RESEARCH)
        self.assertEqual(by["10.1126/science.adx1"].title, "A new kidney")
        self.assertEqual(by["10.1126/science.adx1"].published, date(2026, 10, 23))
        self.assertEqual(by["10.1126/science.adx2"].kind, sources.COMMENTARY)
        self.assertEqual(by["10.1126/science.adx3"].kind, sources.OTHER)

    def test_doi_rule(self):
        rss = SCIENCE_RSS.replace("10.1126/science.ADX1", "10.1056/NEJMoa2601")
        items = sources.parse_feed(rss, NEJM, CONFIG)
        self.assertEqual(items[0].kind, sources.RESEARCH)
        self.assertEqual(items[1].kind, sources.OTHER)

    def test_page_type(self):
        cfg = {"research": ["Article"], "commentary": ["News & Views"]}
        page = '<meta name="citation_article_type" content="News &amp; Views">'
        self.assertEqual(sources.kind_from_page(page, cfg), ("News & Views", sources.COMMENTARY))
        self.assertEqual(sources.kind_from_page("", cfg), (None, sources.OTHER))

    def test_crossref(self):
        payload = {"message": {"items": [
            {"DOI": "10.1093/Bioinformatics/btag1", "title": ["Fast <i>aligner</i>"],
             "published-online": {"date-parts": [[2026, 10, 20]]}, "type": "journal-article"},
            {"DOI": "10.1093/x", "title": ["Correction: y"]}]}}
        items = sources.parse_crossref(payload, {"name": "Bioinformatics"}, CONFIG)
        self.assertEqual([i.kind for i in items], [sources.RESEARCH, sources.OTHER])
        self.assertEqual(items[0].doi, "10.1093/bioinformatics/btag1")
        self.assertEqual(items[0].title, "Fast aligner")

    def test_crossref_backfill_kinds(self):
        def work(doi, title, **dates):
            return {"DOI": doi, "title": [title], "type": "journal-article", **dates}
        payload = {"message": {"items": [
            work("10.1056/NEJMoa9", "Trial", **{"published": {"date-parts": [[2026, 10]]},
                                               "created": {"date-parts": [[2026, 10, 8]]}}),
            work("10.1056/NEJMp9", "View", created={"date-parts": [[2026, 10, 8]]}),
            work("10.1056/NEJMc9", "Correction: Trial"),
        ]}}
        by = {i.doi: i for i in sources.parse_crossref(payload, NEJM, CONFIG, backfill=True)}
        self.assertEqual(by["10.1056/nejmoa9"].kind, sources.RESEARCH)
        self.assertEqual(by["10.1056/nejmoa9"].published, date(2026, 10, 8))   # month-only: registration day
        self.assertEqual(by["10.1056/nejmp9"].kind, sources.OTHER)
        self.assertEqual(by["10.1056/nejmc9"].kind, sources.OTHER)
        field = sources.parse_crossref(payload, SCIENCE, CONFIG, backfill=True)
        self.assertEqual([i.kind for i in field], [sources.PUBMED, sources.PUBMED, sources.OTHER])
        page = sources.parse_crossref(payload, {"name": "Nature", "type_from": "page"}, CONFIG, backfill=True)
        self.assertIsNone(page[0].kind)

    def test_crossref_pages(self):
        first = {"message": {"next-cursor": "c2", "items": [
            {"DOI": f"10.1/{n}", "title": ["t"]} for n in range(200)]}}
        second = {"message": {"next-cursor": "c3", "items": [{"DOI": "10.1/last", "title": ["t"]}]}}
        fetch = fake({"cursor=c2": (200, "json", json.dumps(second)),
                      "cursor=%2A": (200, "json", json.dumps(first))})
        cfg = {"name": "Bioinformatics", "issn": "1367-4811", "type_from": "all"}
        items = sources.crossref_items(fetch, cfg, CONFIG, date(2026, 10, 27), days=30, backfill=True)
        self.assertEqual(len(items), 201)
        self.assertEqual(len(fetch.calls), 2)                    # a short page ends it
        self.assertIn("from-created-date:2026-09-27", fetch.calls[0])


class Abstracts(unittest.TestCase):
    def test_parse(self):
        rec = abstracts.parse_efetch(EFETCH)["10.1056/nejmoa1"]
        self.assertEqual(rec["pmid"], "123")
        self.assertTrue(rec["abstract"].startswith("BACKGROUND: Kidneys fail."))
        self.assertEqual(rec["types"], [])

    def test_is_research(self):
        full = " ".join(["word"] * 120)
        self.assertTrue(abstracts.is_research({"abstract": full, "types": ["Journal Article"]}))
        self.assertTrue(abstracts.is_research(
            {"abstract": full, "types": ["Journal Article", "Randomized Controlled Trial"]}))
        self.assertFalse(abstracts.is_research({"abstract": full, "types": ["Journal Article", "Review"]}))
        self.assertFalse(abstracts.is_research({"abstract": full, "types": ["News"]}))
        self.assertFalse(abstracts.is_research(            # a Perspective's teaser
            {"abstract": "Does the postmenopausal ovary still matter? Yes.", "types": ["Journal Article"]}))
        self.assertFalse(abstracts.is_research({"abstract": None, "types": ["Journal Article"]}))

    def test_lookup_many(self):
        fetch = fake({"esearch": (200, "json", json.dumps({"esearchresult": {"idlist": ["123"]}})),
                      "efetch": (200, "xml", EFETCH)})
        found = abstracts.lookup_many(fetch, ["10.1056/nejmoa1", "10.1/other"])
        self.assertEqual(list(found), ["10.1056/nejmoa1"])


class Summary(unittest.TestCase):
    def test_conclusions_first(self):
        abstract = abstracts.parse_efetch(EFETCH)["10.1056/nejmoa1"]["abstract"]
        self.assertEqual(summary.extractive(abstract), "Drug X halved the decline in kidney function.")

    def test_cue_sentence(self):
        text = ("Kidneys are complex. Here we show that organoids form nephrons, e.g. in mice. "
                "This matters.")
        self.assertEqual(summary.extractive(text),
                         "Here we show that organoids form nephrons, e.g. in mice.")

    def test_trim(self):
        out = summary.extractive("Word " * 200 + ".")
        self.assertLessEqual(len(out), summary.MAX_CHARS + 1)
        self.assertTrue(out.endswith("…"))

    def test_none(self):
        self.assertIsNone(summary.extractive(None))


class Figures(unittest.TestCase):
    def test_springer_url(self):
        self.assertTrue(figures.springer_figure_url("10.1038/s41586-026-11053-2", 3).endswith(
            "/41586_2026_11053_Fig3_HTML.png"))
        self.assertIsNone(figures.springer_figure_url("10.1126/science.adx1", 1))

    def test_springer_probe_stops(self):
        fetch = fake({"Fig1_": (200, "image/png", ""), "Fig2_": (200, "image/png", "")})
        self.assertEqual(len(figures.springer(fetch, "10.1038/s41586-026-11053-2")), 2)

    def test_licences(self):
        msg = {"license": [{"URL": "https://www.elsevier.com/tdm", "content-version": "tdm"},
                           {"URL": "http://creativecommons.org/licenses/by-nc-nd/4.0/", "content-version": "vor"}]}
        url = figures.cc_licence(msg)
        self.assertEqual(figures.licence_name(url), "CC BY-NC-ND 4.0")
        self.assertIsNone(figures.cc_licence({"license": [{"URL": "https://creativecommons.org/licenses/by/4.0/",
                                                           "content-version": "am"}]}))

    def test_pmc_xml(self):
        figs = figures.parse_pmc_figures(PMC_XML, {"41586_2026_1_Fig1_HTML.webp", "gr2.webp"})
        self.assertEqual([f["name"] for f in figs], ["41586_2026_1_Fig1_HTML.webp", "gr2.webp"])
        self.assertEqual(figs[0]["label"], "Fig. 1")
        self.assertEqual(figs[0]["caption"], "Organoids grow.")
        self.assertEqual(figs[1]["caption"], "Nephrons form in vitro.")

    def listing(self, *names):
        return "<ListBucketResult>" + "".join(f"<Key>PMC9.1/{n}</Key>" for n in names) + "</ListBucketResult>"

    def test_pmc_open_access(self):
        fetch = fake({"prefix=PMC9.": (200, "xml", self.listing("PMC9.1.json", "PMC9.1.xml", "gr2.webp")),
                      "PMC9.1.json": (200, "json", json.dumps({"license_code": "CC BY", "is_pmc_openaccess": True})),
                      "PMC9.1.xml": (200, "xml", PMC_XML)})
        code, figs = figures.pmc(fetch, "PMC9")
        self.assertEqual(code, "CC BY")
        self.assertEqual(figs[0]["url"], "https://pmc-oa-opendata.s3.amazonaws.com/PMC9.1/gr2.webp")

    def test_pmc_author_manuscript_refused(self):
        fetch = fake({"prefix=PMC9.": (200, "xml", self.listing("PMC9.1.json", "PMC9.1.xml")),
                      "PMC9.1.json": (200, "json", json.dumps({"license_code": "TDM", "is_pmc_openaccess": False}))})
        self.assertEqual(figures.pmc(fetch, "PMC9"), (None, []))

    def test_og_image(self):
        page = '<meta content="/img/fig1.png" property="og:image">'
        self.assertEqual(figures.og_image(page, "https://www.nature.com/articles/x"),
                         "https://www.nature.com/img/fig1.png")
        self.assertIsNone(figures.og_image('<meta property="og:image" content="https://x.org/logo.png">', "https://x.org"))


def paper(doi, first_seen, **kw):
    p = {"doi": doi, "journal": "Nature", "title": "T", "link": "https://doi.org/" + doi,
         "published": first_seen, "first_seen": first_seen, "article_type": None,
         "abstract": None, "pmid": None, "summary": None, "summary_source": None,
         "licence": None, "licence_checked": None, "pmcid": None, "figures": [],
         "figure_source": None, "figures_added": None, "preview": None, "preview_tried": True}
    p.update(kw)
    return p


class Build(unittest.TestCase):
    def test_backfill_marks_figures_added(self):
        today = date(2026, 10, 28)                       # a Wednesday
        old = paper("10.1/old", "2026-10-07")
        new = paper("10.1/new", "2026-10-27")
        fetch = fake({
            "idconv": (200, "json", json.dumps({"records": [
                {"doi": "10.1/old", "pmcid": "PMC9"}, {"doi": "10.1/new", "pmcid": "PMC9"}]})),
            "prefix=PMC9.": (200, "xml", Figures.listing(None, "PMC9.1.json", "PMC9.1.xml", "gr2.webp")),
            "PMC9.1.json": (200, "json", json.dumps({"license_code": "CC BY", "is_pmc_openaccess": True})),
            "PMC9.1.xml": (200, "xml", PMC_XML)})
        self.assertEqual(build.fill_figures(fetch, [old, new], today), 2)
        self.assertEqual(old["figures_added"], "2026-10-28")
        self.assertIsNone(new["figures_added"])          # same week: just has figures
        self.assertEqual(old["licence"], "https://creativecommons.org/licenses/by/4.0/")

    def test_backfill_figures_not_new(self):
        today = date(2026, 10, 28)
        old = paper("10.1/old", "2026-10-07")
        fetch = fake({
            "idconv": (200, "json", json.dumps({"records": [{"doi": "10.1/old", "pmcid": "PMC9"}]})),
            "prefix=PMC9.": (200, "xml", Figures.listing(None, "PMC9.1.json", "PMC9.1.xml", "gr2.webp")),
            "PMC9.1.json": (200, "json", json.dumps({"license_code": "CC BY", "is_pmc_openaccess": True})),
            "PMC9.1.xml": (200, "xml", PMC_XML)})
        self.assertEqual(build.fill_figures(fetch, [old], today, {"10.1/old"}), 1)
        self.assertTrue(old["figures"])
        self.assertIsNone(old["figures_added"])          # filed this run: never shown bare

    def test_backfill(self):
        today = date(2026, 10, 28)
        science = dict(SCIENCE, issn="1095-9203")
        bioinf = {"name": "Bioinformatics", "issn": "1367-4811", "type_from": "all"}
        config = dict(CONFIG, journals=[science, bioinf, {"name": "No ISSN", "type_from": "field"}])

        def work(doi, created):
            return {"DOI": doi, "title": ["T " + doi], "created": {"date-parts": [created]}}
        sci = {"message": {"items": [work("10.1126/r", [2026, 10, 2]), work("10.1126/rev", [2026, 10, 2]),
                                     work("10.1126/new", [2026, 10, 27]), work("10.1126/held", [2026, 10, 5])]}}
        bio = {"message": {"items": [work("10.1093/b", [2026, 9, 1])]}}
        efetch = "<PubmedArticleSet>" + "".join(
            f"<PubmedArticle><MedlineCitation><PMID>{i}</PMID><Article>"
            f"<Abstract><AbstractText>{' '.join(['Text.'] * 100)}</AbstractText></Abstract>"
            f"<PublicationTypeList><PublicationType>Journal Article</PublicationType>{extra}</PublicationTypeList>"
            f"</Article></MedlineCitation><PubmedData><ArticleIdList>"
            f'<ArticleId IdType="doi">{doi}</ArticleId></ArticleIdList></PubmedData></PubmedArticle>'
            for i, (doi, extra) in enumerate([("10.1126/r", ""), ("10.1126/rev", "<PublicationType>Review</PublicationType>")])
        ) + "</PubmedArticleSet>"
        fetch = fake({"journals/1095-9203": (200, "json", json.dumps(sci)),
                      "journals/1367-4811": (200, "json", json.dumps(bio)),
                      "esearch": (200, "json", json.dumps({"esearchresult": {"idlist": ["0", "1"]}})),
                      "efetch": (200, "xml", efetch)})
        state = {"papers": {"10.1126/held": paper("10.1126/held", "2026-10-28", published="2026-10-05")},
                 "not_research": {}}
        filed = build.backfill(fetch, config, state, today, 30)
        papers = state["papers"]
        self.assertEqual(papers["10.1126/r"]["first_seen"], "2026-10-02")
        self.assertEqual(papers["10.1126/held"]["first_seen"], "2026-10-05")   # re-filed
        self.assertEqual(papers["10.1093/b"]["first_seen"], "2026-09-28")      # clamped to the window
        self.assertIn("10.1126/rev", state["not_research"])
        self.assertNotIn("10.1126/new", papers)                                # not in PubMed yet:
        self.assertNotIn("10.1126/new", state["not_research"])                 # left for the feed
        self.assertEqual(filed, {"10.1126/r", "10.1126/held", "10.1093/b"})
        self.assertFalse(any("No ISSN" in u for u in fetch.calls))

    def test_public_and_prune(self):
        today = date(2026, 10, 28)
        state = {"papers": {"a": paper("a", "2026-10-27", preview="https://x/p.png"),
                            "b": paper("b", "2026-01-05")},
                 "not_research": {"c": "2026-06-01", "d": "2026-10-20"}}
        build.prune(state, today)
        self.assertEqual(list(state["papers"]), ["a"])
        self.assertEqual(list(state["not_research"]), ["d"])
        row = build.public(state["papers"]["a"])
        self.assertEqual((row["week"], row["figure_kind"], row["licence"]), ("2026-10-26", "preview", None))
        self.assertNotIn("abstract", row)

    def test_abstracts_only_for_summaries(self):
        done = paper("10.1/done", "2026-10-27", summary="Said.", summary_source="abstract")
        todo = paper("10.1056/nejmoa1", "2026-10-27")
        fetch = fake({"esearch": (200, "json", json.dumps({"esearchresult": {"idlist": ["123"]}})),
                      "efetch": (200, "xml", EFETCH)})
        self.assertEqual(build.fill_abstracts(fetch, [done, todo]), 1)
        self.assertNotIn("done", fetch.calls[0])                        # has a summary: not asked
        build.fill_summaries([done, todo])
        self.assertTrue(todo["summary"].startswith("Drug X halved"))
        state = {"papers": {p["doi"]: p for p in (done, todo)}, "not_research": {}}
        build.forget_abstracts(state)
        self.assertIsNone(todo["abstract"])
        self.assertEqual(todo["summary_source"], "abstract")

    def test_code_to_url(self):
        self.assertEqual(build.code_to_url("CC BY-NC-ND"), "https://creativecommons.org/licenses/by-nc-nd/4.0/")
        self.assertIsNone(build.code_to_url("TDM"))


if __name__ == "__main__":
    unittest.main()
