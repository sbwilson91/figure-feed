"""
The one HTTP client. Every request goes through `fetch`, which identifies the app,
paces requests per host (NCBI allows three a second without a key), and retries
once on a 429 or 5xx.

`fetch(url) -> (status, content_type, body)`; it raises OSError when the request does
not complete. The rest of the package takes `fetch` as an argument, so the tests run
with no network.
"""

import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

CONTACT = os.environ.get("CONTACT_EMAIL", "").strip()
USER_AGENT = "figure-feed/1.0 (static research digest" + (f"; mailto:{CONTACT}" if CONTACT else "") + ")"
NCBI_KEY = os.environ.get("NCBI_API_KEY", "").strip()

_GAP = {"eutils.ncbi.nlm.nih.gov": 0.12 if NCBI_KEY else 0.36,
        "www.ncbi.nlm.nih.gov": 0.36, "pmc.ncbi.nlm.nih.gov": 0.36,
        "api.crossref.org": 0.1}
_last: dict[str, float] = {}


def ncbi_params() -> str:
    """The query-string tail NCBI asks every caller to send."""
    tail = "tool=figure-feed"
    if CONTACT:
        tail += f"&email={CONTACT}"
    if NCBI_KEY:
        tail += f"&api_key={NCBI_KEY}"
    return tail


def crossref_params() -> str:
    return f"mailto={CONTACT}" if CONTACT else ""


def _pace(host: str) -> None:
    gap = _GAP.get(host, 0.25)
    wait = _last.get(host, 0) + gap - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.monotonic()


def fetch(url: str, timeout: float = 30, method: str = "GET") -> tuple[int, str, bytes]:
    host = urlsplit(url).hostname or ""
    for attempt in (0, 1):
        _pace(host)
        req = urllib.request.Request(url, method=method, headers={
            "User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            if attempt == 0 and (e.code == 429 or e.code >= 500):
                time.sleep(3)
                continue
            return e.code, e.headers.get("Content-Type", "") if e.headers else "", b""
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == 0:
                time.sleep(2)
                continue
            raise OSError(str(e)) from e
    raise OSError(f"{url}: no response")


def text(fetch_fn, url: str) -> str | None:
    """The body of a 200 response as text, or None."""
    try:
        status, _, body = fetch_fn(url)
    except OSError:
        return None
    return body.decode("utf-8", "replace") if status == 200 else None
