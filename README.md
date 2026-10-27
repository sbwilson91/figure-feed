# Figure Feed

New research from the major journals, one card per paper: the figures first, then the
title and a single sentence about the finding. Swipe right to keep a paper, left to pass.
It installs as an app on a phone (Add to Home Screen). It has no accounts or server, and
what a reader keeps stays in their own browser.

It's a static site on GitHub Pages. A GitHub Action rebuilds it once a day.

## Install on your phone

Figure Feed installs from its website, so it isn't in an app store. Open the site's
address (for example `https://<account>.github.io/figure-feed/`) on the phone, then:

**iPhone (Safari)**
1. Tap the **Share** button (the square with an arrow).
2. Tap **Add to Home Screen**, then **Add**.

**Android (Chrome)**
1. Tap the **⋮** menu.
2. Tap **Install app**. On some phones it is called **Add to Home screen**. Chrome often
   offers this itself, as a banner at the bottom of the page.

Figure Feed then has its own icon and opens full screen with no browser bar. It loads
the latest papers each time it opens. Without a connection the app still opens, but
figures and new papers need the internet. Saved papers stay on that phone only: there
is no account and nothing syncs between devices.

### App stores (optional, later)

- **Google Play:** the same website can be wrapped and listed with free tools such as
  [PWABuilder](https://www.pwabuilder.com/). You'd need a one-off $25 Google Play
  developer account.
- **Apple App Store:** this needs a native wrapper (e.g. Capacitor) and a $99/year Apple
  developer account. Apple sometimes rejects apps that are mainly a website.

Installing from the home screen covers everyday use without either store.

## Journals

Nature, Science, Cell, Cell Stem Cell, Stem Cell Reports, Nature Biotechnology,
Nature Methods, Nature Materials, Bioinformatics, NEJM and The Lancet. Only research
articles are included; news, comment, reviews and corrections are left out. The list,
and the rule that decides what each journal's feed calls research, is in
[`journals.yaml`](journals.yaml).

## Where figures come from

Full figures are shown only when the paper's licence allows it (Creative Commons). The
site links to each image where the publisher or PubMed Central hosts it; it does not
store copies.

| Route | Which papers | When |
|---|---|---|
| Springer Nature | CC-licensed Nature-family papers | the day they're published |
| PubMed Central | any paper in PMC's open-access subset with a CC licence | usually 2–5 weeks after publication |
| Link preview | any other paper whose publisher offers a preview image | first sighting |
| Text card | everything else (most Science, NEJM and Cell papers) | — |

For six weeks, each run checks again for abstracts and PMC figures. When figures turn up
for a paper from an earlier week, the paper appears in the **New figures** tab.

## Summaries

The sentence under each title comes from the PubMed abstract: the conclusions section if
the abstract has one, otherwise the "Here we show…" sentence.

You can have Claude write a plain-language sentence instead. This is optional and paid:
add an `ANTHROPIC_API_KEY` repository secret. Without the secret, nothing is sent to an
API. Each run summarises at most `SUMMARY_LIMIT` papers (default 200), roughly a week's
worth. The model defaults to `claude-opus-5-5`, with low effort and server-side fallbacks
enabled. Set the `SUMMARY_MODEL` repository variable to use a different model, such as
`claude-haiku-5-5`, which costs much less.

## Running costs

None by default. The daily build uses only free public services: the journals' RSS
feeds, Crossref, NCBI PubMed and ID converter, the PubMed Central open-access bucket,
and Springer Nature's figure server. GitHub Actions and GitHub Pages are free for
public repositories, and the daily run takes well within the free minutes.

The only paid option is Claude summaries (see Summaries above). They run only if you
add an `ANTHROPIC_API_KEY` secret.

## Setup

1. Create a GitHub repository and push this folder to it.
2. **Settings → Pages → Source: GitHub Actions.**
3. **Settings → Secrets and variables → Actions**:
   - Variable `CONTACT_EMAIL` (recommended): sent to Crossref and NCBI as a courtesy
     contact. Both services ask for one.
   - Secret `NCBI_API_KEY` (optional): faster PubMed lookups.
   - Secret `ANTHROPIC_API_KEY` and variable `SUMMARY_MODEL` (optional, see above).
4. **Actions → Update feed → Run workflow** to run the first build. After that it runs
   daily at 05:17 UTC.

The feed builds up from the journals' current feeds. The first run collects what each
feed lists today, typically one to two weeks of papers.

## Local run

```bash
pip install -r requirements.txt
python -m feed.build                 # fetch, update state/ and site/data/
python -m unittest                   # offline tests
python -m http.server -d site 8000   # then open http://localhost:8000
```

## Layout

```
journals.yaml        the journals and how to tell research from the rest
feed/                the build: sources, abstracts, figures, summaries
state/papers.json    every paper of the last 26 weeks with its bookkeeping (committed)
site/                the app; site/data/ is written by the build (committed)
.github/workflows/   the daily update and Pages deploy
```

Titles, abstracts-derived summaries and figures belong to their authors and publishers.
Figures shown in full are under the Creative Commons licence named on each card.
