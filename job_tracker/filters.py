"""Decide which fetched jobs belong in a search category, and annotate them."""

from __future__ import annotations

import re
from datetime import date, timedelta


def _any(patterns, text):
    text = text.lower()
    return any(re.search(rf"\b{re.escape(p.lower())}\b", text) for p in patterns)


def _salary_numbers(salary):
    """Annual-ish dollar figures in a salary string ("$120k", "$120,000")."""
    nums = []
    for m in re.finditer(r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?", salary.lower()):
        n = float(m.group(1).replace(",", ""))
        if m.group(2):
            n *= 1000
        nums.append(n)
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

    max_age = settings.get("max_days_old")
    if max_age and job["posted"]:
        try:
            posted = date.fromisoformat(job["posted"])
            if posted < (today or date.today()) - timedelta(days=max_age):
                return None
        except ValueError:
            pass

    notes = [f"{category['name']} search", f"Location: {job['location'] or 'not stated'}"]
    caution = category.get("salary_caution_at")
    if caution and job["salary"]:
        nums = _salary_numbers(job["salary"])
        if nums and max(nums) >= caution:
            notes.append(f"Pay ≥ ${caution:,.0f} — check seniority/scope")
    notes.append("Auto-found; verify on employer site before applying")

    out = dict(job)
    out.update(category=category["name"], texas=texas, notes=" · ".join(notes))
    return out
