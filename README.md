# IN A WORLD OF OVERFLOWING INFORMATION - PRESENTING: FIGURE FEED

# Figure Feed

**Live site:** [sbwilson91.github.io/figure-feed](https://sbwilson91.github.io/figure-feed/)

The idea is to build a scrollable-app style format to browse the latest publications from major journals. The focus is to show the figures and title, with a link to the paper if you want to read it further based on the snapshot presented on the app. It is implemented as a GitHub Action and rebuilds daily.

Conceptualisation and fine tuning performed by me (Sean Wilson), majority of code base written by Claude.

## Features

- Menu in the top right corner: three colour modes, and the search box
- Papers without loadable figures appear as text at end
- Can ignore a paper to remove from feed, store a paper to come back to later, open the paper at its source
- Memory for where you last scrolled to
- Back up and restore stored papers as a file (Saved tab)
- Swipe on figures to show all available in paper
- Filter by journal
- Search by keyword (Menu → Search): titles and summaries matching every word (or "quoted phrase") stay, with the words highlighted
- Previous 6 weeks stored in Earlier tab
- Search for topics of interest (eg. "kidney", "CRISPR screen")

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

Figure Feed then has its own icon and opens full screen with no browser bar. It updates
itself: each time it opens, and when it comes back to the front after half an hour or
more, it loads the latest papers and the latest version of the app. There is nothing to
reinstall. Without a connection the app still opens, but figures and new papers need the
internet. Saved papers stay on your phone only: there is no account and nothing syncs
between devices. Removing the app removes them too, so the Saved tab has **Back up**,
which saves them to a file (Files, Drive, email), and **Restore**, which reads that file
back in.

### Looks

The menu (☰, top right) has three colour looks from the Plexus palette under **Colour**:
**Technical** (the default), **Dark** and **Light**. The choice is remembered on that
phone.

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

## Filling past weeks

The journals' feeds only hold their latest items. To fill earlier weeks, for a new copy
of the app say, run `python -m feed.build --backfill 30`: it lists the last 30 days of
each journal from Crossref and files each paper under the week it went online. Crossref
has no article sections, so for Science, Cell, Cell Stem Cell, Stem Cell Reports and the
Lancet the backfill goes by PubMed's publication types and a full-length abstract; the
odd opinion piece can slip through.

## Summaries

The sentence under each title comes from the PubMed abstract: the conclusions section if
the abstract has one, otherwise the "Here we show…" sentence. Abstracts are the
publishers' text, so they are fetched for each run and never saved in this repository.
