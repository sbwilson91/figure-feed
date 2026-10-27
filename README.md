# IN A WORLD OF OVERFLOWING INFORMATION - PRESENTING: FIGURE FEED

# Figure Feed

**Live site:** [sbwilson91.github.io/figure-feed](https://sbwilson91.github.io/figure-feed/)

The idea is to build a scrollable-app style format to browse the latest publications from major journals. The focus is to show the figures and title, with a link to the paper if you want to read it further based on the snapshot presented on the app. It is implemented as a GitHub Action and rebuilds daily.

Conceptualisation and fine tuning performed by me (Sean Wilson), majority of code base written by Claude.

## Install on your phone

Figure Feed installs from its website, so it isn't in an app store. Open the site's
address https://sbwilson91.github.io/figure-feed on the phone, then:

**iPhone (Safari)**
1. Tap the **Share** button (the square with an arrow).
2. Tap **Add to Home Screen**, then **Add**.

**Android (Chrome)**
1. Tap the **⋮** menu.
2. Tap **Install app**. On some phones it is called **Add to Home screen**. Chrome often
   offers this itself, as a banner at the bottom of the page.

Figure Feed then has its own icon and opens full screen with no browser bar. It loads
the latest papers each time it opens. Without a connection the app still opens, but
figures and new papers need the internet. Saved papers stay on your phone only: there
is no account and nothing syncs between devices.

## Journals

Nature, Science, Cell, Cell Stem Cell, Stem Cell Reports, Nature Biotechnology,
Nature Methods, Nature Materials, Bioinformatics, NEJM and The Lancet. Only research
articles are included; news, comment, reviews and corrections are left out. The list,
and the rule that decides what each journal's feed calls research, is in
[`journals.yaml`](journals.yaml). Customisable for anyone who wants to clone the respository to make their own version, this one is set with my personal interests in mind.

## Where figures come from

Full figures are shown only when the paper's licence allows it (Creative Commons). The
site links to each image where the publisher or PubMed Central hosts it; it does not
store copies. As such, papers locked behind a paywall remain so, and isn't that a greedy shame.

| Route | Which papers | When |
|---|---|---|
| Springer Nature | CC-licensed Nature-family papers | the day they're published |
| PubMed Central | any paper in PMC's open-access subset with a CC licence | usually 2–5 weeks after publication |
| Link preview | any other paper whose publisher offers a preview image | first sighting |
| Text card | everything else (most Science, NEJM and Cell papers) | — |

## New figures

For six weeks, each run checks again for abstracts and PMC figures. When figures turn up
for a paper from an earlier week, the paper appears in the **New figures** tab.

## Summaries

The sentence under each title comes from the PubMed abstract: the conclusions section if
the abstract has one, otherwise the "Here we show…" sentence.

