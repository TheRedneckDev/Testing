"""Decide which fetched jobs belong in a search category, and annotate them."""

from __future__ import annotations

import re
from datetime import date, timedelta


def _any(patterns, text):
    text = text.lower()
    return any(re.search(rf"\b{re.escape(p.lower())}\b", text) for p in patterns)


def annual_pay(salary):
    """Dollar figures in a pay string, converted to yearly amounts.

    Handles "$120k - $150k", "$122,000", "$56 - $60 per hour" (x 2080) and
    "$5,425 - $7,100 per month" (x 12). Returns [] when no amount is found.
    """
    text = salary.lower()
    if re.search(r"hour|/\s*hr\b|hourly", text):
        factor = 2080
    elif re.search(r"month|/\s*mo\b|monthly", text):
        factor = 12
    elif re.search(r"week|/\s*wk\b|weekly", text):
        factor = 52
    else:
        factor = 1
    nums = []
    for m in re.finditer(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?", text):
        n = float(m.group(1).replace(",", ""))
        if m.group(2):
            n *= 1000
        nums.append(n * factor)
    return nums


def location_status(job, category):
    """Return (accepted, texas_eligible_text)."""
    loc = job["location"].lower()
    remote = job["remote"] is True or "remote" in loc or "remote" in job["title"].lower()

    if _any(category.get("local_terms", []), loc):
        if remote:
            return True, "Listed (Texas location) – verify"
        # On-site/hybrid near Austin is fine only for searches that allow it.
        return (not category.get("remote_only")), "Yes – local (on-site/hybrid; verify)"

    if not remote:
        return False, ""
    if _any(category.get("texas_terms", []), loc):
        return True, "Listed (Texas location) – verify"
    if not loc.strip():
        return True, "Unknown – verify"
    if _any(category.get("us_terms", []), loc):
        return True, "Likely (U.S. remote) – verify"
    return False, ""


def match(job, category, settings, today=None):
    """Return an annotated copy of job if it fits the category, else None."""
    title = job["title"]
    if not title or not job["company"]:
        return None
    if not _any(category["title_include"], title):
        return None
    if _any(category.get("title_exclude", []), title):
        return None

    ok, texas = location_status(job, category)
    if not ok:
        return None

    # Pay cutoff: drop jobs whose pay range goes above salary_max.
    salary_max = category.get("salary_max")
    if salary_max and job["salary"]:
        pay = annual_pay(job["salary"])
        if pay:
            top_or_bottom = max(pay) if category.get("salary_cutoff", "top") == "top" else min(pay)
            if top_or_bottom > salary_max:
                return None

    max_age = settings.get("max_days_old")
    if max_age and job["posted"]:
        try:
            posted = date.fromisoformat(job["posted"])
            if posted < (today or date.today()) - timedelta(days=max_age):
                return None
        except ValueError:
            pass

    notes = [f"{category['name']} search", f"Location: {job['location'] or 'not stated'}"]
    notes.append("Auto-found; verify on employer site before applying")

    out = dict(job)
    out.update(category=category["name"], texas=texas, notes=" · ".join(notes))
    return out
