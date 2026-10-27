"""
The line under the title: what the paper found, in a sentence.

It is lifted from the abstract, so the words are the authors' own: the conclusions
section where the abstract has one, else the "Here we show" sentence, else the
abstract's last sentence. Free, and never wrong about the paper.
"""

import re

MAX_CHARS = 300
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")
_ABBREV = re.compile(r"\b(e\.g|i\.e|et al|vs|approx|Fig|Figs|ca)\.$", re.I)
_CUE = re.compile(r"^(here,? we|we (show|find|found|report|demonstrate|identify|reveal|describe|present|establish|propose|uncover|develop)"
                  r"|our (findings|results|data|study)|these (findings|results|data)|together|collectively|taken together|in summary|overall)",
                  re.I)
_CONCLUDE = re.compile(r"^(CONCLUSIONS?|INTERPRETATION|CONCLUSIONS AND RELEVANCE|SIGNIFICANCE)$", re.I)
_SKIP = re.compile(r"^(BACKGROUND|METHODS|FUNDING|TRIAL REGISTRATION|AVAILABILITY|"
                   r"AVAILABILITY AND IMPLEMENTATION|SUPPLEMENTARY INFORMATION|CONTACT)$", re.I)


def sentences(text: str) -> list[str]:
    raw = _SENT.split(" ".join(text.split()))
    out: list[str] = []
    for s in raw:
        if out and _ABBREV.search(out[-1]):
            out[-1] += " " + s
        else:
            out.append(s)
    return [s for s in out if s]


def _trim(s: str) -> str:
    s = s.strip()
    if len(s) <= MAX_CHARS:
        return s
    return s[:MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def extractive(abstract: str | None) -> str | None:
    if not abstract:
        return None
    sections = []
    for block in abstract.split("\n\n"):
        label, sep, body = block.partition(": ")
        if sep and label.isupper() and len(label) < 40:
            sections.append((label, body))
        else:
            sections.append((None, block))
    for label, body in sections:
        if label and _CONCLUDE.match(label):
            first = sentences(body)
            if first:
                return _trim(first[0])
    pool = [s for label, body in sections if not (label and _SKIP.match(label))
            for s in sentences(body)]
    if not pool:
        return None
    for s in pool:
        if _CUE.match(s):
            return _trim(s)
    return _trim(pool[-1]) if len(pool) > 1 else _trim(pool[0])

