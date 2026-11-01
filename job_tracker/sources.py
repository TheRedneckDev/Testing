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
from datetime import datetime, timezone

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
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "location": (location or "").strip(),
        "url": (url or "").strip(),
        "posted": _norm_date(posted),
        "salary": (salary or "").strip() if isinstance(salary, str) else _fmt_salary(*salary) if salary else "",
        "remote": remote,
        "schedule": (schedule or "").replace("_", "-").strip(),
        "description": _strip_html(description or "")[:2000],
    }


def _get(url, *, params=None, headers=None):
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    h.update(headers or {})
    resp = requests.get(url, params=params, headers=h, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _strip_html(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def _norm_date(value):
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    s = str(value).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
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
    "adzuna": adzuna,
    "usajobs": usajobs,
}
