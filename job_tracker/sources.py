"""Job search sources.

Each source is a function ``fetch(category, settings) -> list[dict]`` returning
jobs in a common shape (see ``make_job``). Free sources need no keys; keyed
sources read credentials from environment variables and are skipped when the
keys are missing.
"""

from __future__ import annotations

import html
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

USER_AGENT = "job-tracker/1.0 (+https://github.com/theredneckdev/testing)"
TIMEOUT = 20


class SkipSource(Exception):
    """Raised when a source can't run (e.g. missing API keys)."""


def make_job(*, source, source_id, title, company, location="", url="",
             posted="", salary="", remote=None, description="", schedule=""):
    return {
        "source": source,
        "source_id": str(source_id or ""),
        "title": _clean(title),
        "company": _clean(company),
        "location": _clean(location),
        "url": (url or "").strip(),
        "posted": _norm_date(posted),
        "salary": (salary or "").strip() if isinstance(salary, str) else _fmt_salary(*salary) if salary else "",
        "remote": remote,
        "schedule": (schedule or "").replace("_", "-").strip(),
        "description": _strip_html(description or "")[:2000],
    }


def _clean(text):
    """Decode HTML entities like &amp; and tidy whitespace."""
    return re.sub(r"\s+", " ", html.unescape(str(text or ""))).strip()


_CACHE = {}


def _get(url, *, params=None, headers=None, as_text=False):
    """GET a URL (JSON by default). Responses are cached for the run, so a
    feed used by both searches is only downloaded once."""
    key = (url, repr(params), as_text)
    if key in _CACHE:
        return _CACHE[key]
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    h.update(headers or {})
    resp = requests.get(url, params=params, headers=h, timeout=TIMEOUT)
    resp.raise_for_status()
    _CACHE[key] = resp.text if as_text else resp.json()
    return _CACHE[key]


def _strip_html(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def _norm_date(value):
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        if value > 1e11:  # milliseconds
            value /= 1000
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    s = str(value).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    try:  # RSS style: "Mon, 03 Nov 2026 14:00:00 +0000"
        return parsedate_to_datetime(s).date().isoformat()
    except (TypeError, ValueError):
        return s[:10]


def _fmt_salary(lo=None, hi=None, unit=""):
    def f(v):
        try:
            return f"${float(v):,.0f}"
        except (TypeError, ValueError):
            return ""
    lo, hi = f(lo), f(hi)
    if not lo and not hi:
        return ""
    text = f"{lo} - {hi}" if lo and hi and lo != hi else (lo or hi)
    return f"{text} {unit}".strip()


# --------------------------------------------------------------------------
# Free sources (no API key)
# --------------------------------------------------------------------------

def remotive(category, settings):
    jobs = []
    for kw in category["search_keywords"]:
        data = _get("https://remotive.com/api/remote-jobs",
                    params={"search": kw, "limit": settings["max_results_per_source"]})
        for j in data.get("jobs", []):
            jobs.append(make_job(
                source="Remotive", source_id=j.get("id"), title=j.get("title"),
                company=j.get("company_name"), location=j.get("candidate_required_location"),
                url=j.get("url"), posted=j.get("publication_date"), salary=j.get("salary") or "",
                remote=True, description=j.get("description"), schedule=j.get("job_type")))
    return jobs


def arbeitnow(category, settings):
    jobs = []
    for page in range(1, settings["max_pages"] + 1):
        data = _get("https://www.arbeitnow.com/api/job-board-api", params={"page": page})
        items = data.get("data", [])
        for j in items:
            jobs.append(make_job(
                source="Arbeitnow", source_id=j.get("slug"), title=j.get("title"),
                company=j.get("company_name"), location=j.get("location"), url=j.get("url"),
                posted=j.get("created_at"), remote=bool(j.get("remote")),
                description=j.get("description"), schedule=", ".join(j.get("job_types") or [])))
        if not items or not (data.get("links") or {}).get("next"):
            break
    return jobs


def remoteok(category, settings):
    data = _get("https://remoteok.com/api")
    jobs = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue  # first element is a legal notice
        jobs.append(make_job(
            source="RemoteOK", source_id=j.get("id"), title=j.get("position"),
            company=j.get("company"), location=j.get("location") or "Remote",
            url=j.get("url") or j.get("apply_url"), posted=j.get("epoch") or j.get("date"),
            salary=(j.get("salary_min") or None, j.get("salary_max") or None, "/yr"),
            remote=True, description=j.get("description")))
    return jobs


def themuse(category, settings):
    # The Muse filters by its own category names (e.g. "Software Engineering",
    # "Customer Service") and location names (e.g. "Flexible / Remote").
    params = [("page", 0)]
    params += [("category", c) for c in category.get("muse_categories", [])]
    params += [("location", l) for l in category.get("muse_locations", [])]
    jobs = []
    for page in range(settings["max_pages"]):
        params[0] = ("page", page)
        data = _get("https://www.themuse.com/api/public/jobs", params=params)
        for j in data.get("results", []):
            locs = ", ".join(l.get("name", "") for l in j.get("locations", []))
            jobs.append(make_job(
                source="The Muse", source_id=j.get("id"), title=j.get("name"),
                company=(j.get("company") or {}).get("name"), location=locs,
                url=(j.get("refs") or {}).get("landing_page"), posted=j.get("publication_date"),
                remote=("remote" in locs.lower()) or None, description=j.get("contents"),
                schedule=", ".join(l.get("name", "") for l in j.get("levels", []))))
        if page + 1 >= data.get("page_count", 0):
            break
    return jobs


def jobicy(category, settings):
    jobs = []
    for kw in category["search_keywords"]:
        data = _get("https://jobicy.com/api/v2/remote-jobs",
                    params={"count": min(settings["max_results_per_source"], 50),
                            "geo": "usa", "tag": kw})
        for j in data.get("jobs", []):
            jobs.append(make_job(
                source="Jobicy", source_id=j.get("id"), title=j.get("jobTitle"),
                company=j.get("companyName"), location=j.get("jobGeo"), url=j.get("url"),
                posted=j.get("pubDate"),
                salary=(j.get("annualSalaryMin"), j.get("annualSalaryMax"), "/yr"),
                remote=True, schedule=", ".join(j.get("jobType") or []),
                description=j.get("jobExcerpt")))
    return jobs


def himalayas(category, settings):
    jobs = []
    for kw in category["search_keywords"]:
        data = _get("https://himalayas.app/jobs/api/search",
                    params={"q": kw, "country": "US", "sort": "recent"})
        for j in data.get("jobs", []):
            jobs.append(make_job(
                source="Himalayas", source_id=j.get("guid"), title=j.get("title"),
                company=j.get("companyName"),
                location=", ".join(j.get("locationRestrictions") or []) or "Anywhere",
                url=j.get("applicationLink") or j.get("guid"), posted=j.get("pubDate"),
                salary=(j.get("minSalary"), j.get("maxSalary"), "/yr"), remote=True,
                schedule=j.get("employmentType"), description=j.get("excerpt")))
    return jobs


def weworkremotely(category, settings):
    jobs = []
    for feed in category.get("wwr_categories", []):
        xml = _get(f"https://weworkremotely.com/categories/{feed}.rss", as_text=True)
        for item in ET.fromstring(xml).iter("item"):
            text = lambda tag: (item.findtext(tag) or "").strip()
            company, _, title = text("title").partition(": ")
            if not title:
                company, title = "", company
            jobs.append(make_job(
                source="We Work Remotely", source_id=text("guid") or text("link"),
                title=title, company=company,
                location=text("region") or text("country") or "Anywhere",
                url=text("link"), posted=text("pubDate"), remote=True,
                schedule=text("type"), description=text("description")))
    return jobs


def workingnomads(category, settings):
    data = _get("https://www.workingnomads.com/api/exposed_jobs/")
    jobs = []
    for j in data if isinstance(data, list) else []:
        jobs.append(make_job(
            source="Working Nomads", source_id=j.get("url"), title=j.get("title"),
            company=j.get("company_name"), location=j.get("location") or "Anywhere",
            url=j.get("url"), posted=j.get("pub_date"), remote=True,
            description=j.get("description")))
    return jobs


def company_boards(category, settings):
    """Openings posted directly on employers' own Greenhouse/Lever/Ashby boards.

    The companies are listed under [companies] in config.toml. One company
    failing (renamed or removed board) doesn't stop the others.
    """
    if "company_boards" in _CACHE:  # boards are the same for both searches
        return _CACHE["company_boards"]
    companies = settings.get("companies", {})
    names = companies.get("names", {})
    _company_name = lambda slug: names.get(slug) or _tidy_slug(slug)
    jobs, failed = [], []

    def each(kind, fetch):
        for name in companies.get(kind, []):
            try:
                jobs.extend(fetch(name))
            except (requests.RequestException, ValueError):
                failed.append(f"{kind}:{name}")

    def greenhouse(token):
        data = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                    params={"content": "true"})
        return [make_job(
            source="Employer board (Greenhouse)", source_id=j.get("id"), title=j.get("title"),
            company=_company_name(j.get("company_name") or token),
            location=(j.get("location") or {}).get("name"), url=j.get("absolute_url"),
            posted=j.get("first_published") or j.get("updated_at"),
            description=html.unescape(j.get("content") or ""))
            for j in data.get("jobs", [])]

    def lever(company):
        data = _get(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"})
        out = []
        for j in data if isinstance(data, list) else []:
            cats = j.get("categories") or {}
            pay = j.get("salaryRange") or {}
            unit = {"per-year-salary": "/yr", "per-hour-wage": "/hr"}.get(pay.get("interval"), "")
            out.append(make_job(
                source="Employer board (Lever)", source_id=j.get("id"), title=j.get("text"),
                company=_company_name(company), location=cats.get("location"),
                url=j.get("hostedUrl"), posted=j.get("createdAt"),
                salary=(pay.get("min"), pay.get("max"), unit) if pay else "",
                remote=(j.get("workplaceType") == "remote") or None,
                schedule=cats.get("commitment"), description=j.get("descriptionPlain")))
        return out

    def ashby(board):
        data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{board}",
                    params={"includeCompensation": "true"})
        return [make_job(
            source="Employer board (Ashby)", source_id=j.get("id") or j.get("jobUrl"),
            title=j.get("title"), company=_company_name(board), location=j.get("location"),
            url=j.get("jobUrl") or j.get("applyUrl"), posted=j.get("publishedAt"),
            salary=(j.get("compensation") or {}).get("compensationTierSummary") or "",
            remote=bool(j.get("isRemote")) or None, schedule=j.get("employmentType"),
            description=j.get("descriptionPlain") or j.get("descriptionHtml") or "")
            for j in data.get("jobs", [])]

    each("greenhouse", greenhouse)
    each("lever", lever)
    each("ashby", ashby)
    if failed and not jobs:
        raise requests.RequestException(f"no boards reachable ({', '.join(failed)})")
    if failed:
        print(f"    (couldn't read these boards; check the names in config.toml: {', '.join(failed)})")
    _CACHE["company_boards"] = jobs
    return jobs


def _tidy_slug(slug):
    """Board tokens look like 'easypost-2' or 'lightspeedsystems'; tidy them."""
    name = re.sub(r"[-_]\d+$", "", str(slug))
    return name if " " in name or any(c.isupper() for c in name) else name.replace("-", " ").title()


def hackernews(category, settings):
    """Hacker News "Ask HN: Who is hiring?" — the monthly startup hiring thread.

    Posts usually start with a line like
    "Company | Role(s) | Location | REMOTE | $120k-$160k", which is parsed here.
    """
    stories = _get("https://hn.algolia.com/api/v1/search_by_date",
                   params={"tags": "story,author_whoishiring", "hitsPerPage": 10})
    thread = next((h for h in stories.get("hits", [])
                   if (h.get("title") or "").lower().startswith("ask hn: who is hiring")), None)
    if not thread:
        return []
    data = _get("https://hn.algolia.com/api/v1/search",
                params={"tags": f"comment,story_{thread['objectID']}", "hitsPerPage": 1000})
    jobs = []
    for c in data.get("hits", []):
        if str(c.get("parent_id")) != str(thread["objectID"]):
            continue  # replies, not job posts
        first = re.split(r"<p>|\n", c.get("comment_text") or "", maxsplit=1)[0]
        parts = [p.strip() for p in _strip_html(first).split("|") if p.strip()]
        if len(parts) < 2:
            continue
        details = " | ".join(parts[1:])
        pay = re.search(r"\$\s?\d[\d,.]*\s?k?(\s?[-–]\s?\$?\s?\d[\d,.]*\s?k?)?", details, re.I)
        jobs.append(make_job(
            source="Hacker News (Who is hiring)", source_id=c.get("objectID"),
            title=details[:200], company=parts[0][:80], location=details,
            url=f"https://news.ycombinator.com/item?id={c.get('objectID')}",
            posted=c.get("created_at"), salary=pay.group(0) if pay else "",
            remote=("remote" in details.lower()) or None,
            description=c.get("comment_text")))
    return jobs


def jooble(category, settings):
    key = os.environ.get("JOOBLE_API_KEY")
    if not key:
        raise SkipSource("set JOOBLE_API_KEY to enable")
    jobs, failed = [], []
    for kw in category["search_keywords"]:
        body = {"keywords": f"{kw} remote" if category.get("remote_only") else kw, "page": 1}
        if category.get("search_location"):
            body["location"] = category["search_location"]
        cache_key = ("jooble", repr(body))
        if cache_key not in _CACHE:
            try:
                resp = requests.post(f"https://jooble.org/api/{key}", json=body,
                                     headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
                resp.raise_for_status()
                _CACHE[cache_key] = resp.json()
            except (requests.RequestException, ValueError) as e:
                failed.append(f"'{kw}' ({getattr(e.response, 'status_code', None) or type(e).__name__})"
                              if isinstance(e, requests.RequestException) else f"'{kw}'")
                continue
        for j in _CACHE[cache_key].get("jobs", []):
            # Only trust "remote" in the title/location; descriptions often say
            # things like "not remote".
            text = f"{j.get('location', '')} {j.get('title', '')}".lower()
            jobs.append(make_job(
                source=f"Jooble ({j['source']})" if j.get("source") else "Jooble",
                source_id=j.get("id"), title=j.get("title"), company=j.get("company"),
                location=j.get("location"), url=j.get("link"), posted=j.get("updated"),
                salary=j.get("salary") or "", remote=("remote" in text) or None,
                schedule=j.get("type"), description=j.get("snippet")))
    if failed and not jobs:
        raise requests.RequestException("every search failed: " + ", ".join(failed))
    if failed:
        print(f"    (jooble searches that failed: {', '.join(failed)})")
    return jobs


# --------------------------------------------------------------------------
# Keyed sources (enabled when environment variables are set)
# --------------------------------------------------------------------------

def adzuna(category, settings):
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        raise SkipSource("set ADZUNA_APP_ID and ADZUNA_APP_KEY to enable")
    country = category.get("adzuna_country", settings.get("adzuna_country", "us"))
    jobs = []
    for kw in category["search_keywords"]:
        what = f"{kw} remote" if category.get("remote_only") else kw
        params = {"app_id": app_id, "app_key": app_key, "what": what,
                  "results_per_page": min(settings["max_results_per_source"], 50),
                  "max_days_old": settings["max_days_old"]}
        if category.get("search_location"):
            params["where"] = category["search_location"]
        data = _get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", params=params)
        for j in data.get("results", []):
            jobs.append(make_job(
                source="Adzuna", source_id=j.get("id"), title=j.get("title"),
                company=(j.get("company") or {}).get("display_name"),
                location=(j.get("location") or {}).get("display_name"),
                url=j.get("redirect_url"), posted=j.get("created"),
                salary=(j.get("salary_min"), j.get("salary_max"), "/yr"),
                description=j.get("description"),
                schedule=" ".join(filter(None, [j.get("contract_time"), j.get("contract_type")]))))
    return jobs


def usajobs(category, settings):
    key, email = os.environ.get("USAJOBS_API_KEY"), os.environ.get("USAJOBS_EMAIL")
    if not (key and email):
        raise SkipSource("set USAJOBS_API_KEY and USAJOBS_EMAIL to enable")
    headers = {"Host": "data.usajobs.gov", "User-Agent": email, "Authorization-Key": key}
    jobs = []
    for kw in category["search_keywords"]:
        params = {"Keyword": kw, "ResultsPerPage": settings["max_results_per_source"],
                  "DatePosted": settings["max_days_old"]}
        if category.get("search_location"):
            params["LocationName"] = category["search_location"]
        if category.get("remote_only"):
            params["RemoteIndicator"] = "True"
        data = _get("https://data.usajobs.gov/api/search", params=params, headers=headers)
        for item in (data.get("SearchResult") or {}).get("SearchResultItems", []):
            d = item.get("MatchedObjectDescriptor", {})
            pay = (d.get("PositionRemuneration") or [{}])[0]
            jobs.append(make_job(
                source="USAJobs", source_id=item.get("MatchedObjectId") or d.get("PositionID"),
                title=d.get("PositionTitle"), company=d.get("OrganizationName"),
                location=d.get("PositionLocationDisplay"), url=d.get("PositionURI"),
                posted=d.get("PublicationStartDate"),
                salary=(pay.get("MinimumRange"), pay.get("MaximumRange"),
                        "/" + pay.get("RateIntervalCode", "") if pay.get("RateIntervalCode") else ""),
                description=(d.get("UserArea") or {}).get("Details", {}).get("JobSummary", ""),
                schedule=", ".join(x.get("Name", "") for x in d.get("PositionSchedule") or [])))
    return jobs


SOURCES = {
    "remotive": remotive,
    "arbeitnow": arbeitnow,
    "remoteok": remoteok,
    "themuse": themuse,
    "jobicy": jobicy,
    "himalayas": himalayas,
    "weworkremotely": weworkremotely,
    "workingnomads": workingnomads,
    "companies": company_boards,
    "hackernews": hackernews,
    "jooble": jooble,
    "adzuna": adzuna,
    "usajobs": usajobs,
}
