"""
The line under the title: what the paper found, in a sentence.

By default it is lifted from the abstract, so the words are the authors' own: the
conclusions section where the abstract has one, else the "Here we show" sentence, else
the abstract's last sentence. Free, and never wrong about the paper.

When the repository has an ANTHROPIC_API_KEY secret, Claude writes a plain-language
sentence from the title and abstract instead. That is a paid API, so it runs only when
the key is set, and at most SUMMARY_LIMIT papers per run.
"""

import logging
import os
import re

log = logging.getLogger(__name__)

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


# ── Optional: Claude ─────────────────────────────────────────────────────────

SYSTEM = (
    "You write the one-line summary under a research paper's title in a public feed "
    "for curious readers who are not specialists in the field. Given the title and "
    "abstract, write one sentence of at most 35 words that says what the authors found "
    "or built, in plain words. Keep the key result concrete (what, in whom or what "
    "system, how much) and do not add anything the abstract does not say. No hype, no "
    "'this study' or 'the authors', no jargon a general science reader would not know. "
    "Reply with the sentence only."
)


def claude_client():
    """A client when the API key is set, else None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("ANTHROPIC_API_KEY is set but the anthropic package is not installed")
        return None
    return anthropic.Anthropic()


def claude(client, title: str, abstract: str) -> str | None:
    """One plain-language sentence, or None if the call fails or is declined."""
    import anthropic
    try:
        response = client.beta.messages.create(
            model=os.environ.get("SUMMARY_MODEL") or "claude-opus-5-5",
            max_tokens=2000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            messages=[{"role": "user", "content": f"Title: {title}\n\nAbstract:\n{abstract}"}],
        )
    except anthropic.APIStatusError as e:
        log.warning("summary failed (%s): %s", e.status_code, e.message)
        return None
    except anthropic.APIConnectionError as e:
        log.warning("summary failed: %s", e)
        return None
    if response.stop_reason == "refusal":
        return None
    text = " ".join(b.text for b in response.content if b.type == "text").strip()
    return _trim(text) if text else None
