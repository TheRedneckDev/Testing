"""Check whether job postings are still open by visiting their links.

A posting counts as gone when its page:
  - returns 404 or 410,
  - redirects to an error page (e.g. Greenhouse's "?error=true"), or
  - says so ("no longer accepting applications", "position has been filled", ...).
Anything else, including sites that block the check or time out, is
"unknown" and is never treated as gone.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import requests

TIMEOUT = 15
# Many job sites refuse requests that don't look like a browser.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
GONE_PHRASES = [
    "no longer accepting applications",
    "job is no longer available", "job you are looking for is no longer",
    "job you're looking for is no longer", "posting is no longer available",
    "position is no longer available", "position has been filled",
    "this position is no longer", "this job has expired", "job has expired",
    "posting has expired", "job posting has expired", "this job has been closed",
    "this job is closed", "job is closed", "posting is closed", "no longer open",
    "job not found", "job no longer exists",
    "this requisition is no longer", "job listing has expired", "this listing has expired",
]
GONE_URL = re.compile(r"[?&]error=true|/404\b|/not[-_]found|/job-not-found|/expired", re.I)


def check_url(url, session=None):
    """Return ("active" | "gone" | "unknown", reason)."""
    if not url:
        return "unknown", "no link"
    s = session or requests
    try:
        resp = s.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True, stream=True)
        try:
            if resp.status_code in (404, 410):
                return "gone", f"page returns {resp.status_code}"
            if GONE_URL.search(resp.url) and not GONE_URL.search(url):
                return "gone", "redirects to an error page"
            if resp.status_code >= 400:
                return "unknown", f"site answered {resp.status_code}"
            body = b""
            for chunk in resp.iter_content(65536):
                body += chunk
                if len(body) > 400_000:
                    break
            text = re.sub(r"\s+", " ", body.decode(resp.encoding or "utf-8", "replace")).lower()
            for phrase in GONE_PHRASES:
                if phrase in text:
                    return "gone", f'page says "{phrase}"'
            return "active", "page is up"
        finally:
            resp.close()
    except requests.RequestException as e:
        return "unknown", f"couldn't reach ({type(e).__name__})"


def check_many(urls, workers=8):
    """Check links in parallel. Returns {url: (status, reason)}."""
    urls = list(dict.fromkeys(u for u in urls if u))
    with requests.Session() as session, ThreadPoolExecutor(workers) as pool:
        results = pool.map(lambda u: check_url(u, session), urls)
        return dict(zip(urls, results))
