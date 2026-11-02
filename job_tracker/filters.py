"""Decide which fetched jobs belong in a search category, and annotate them."""

from __future__ import annotations

import re
from datetime import date, timedelta


def _any(patterns, text):
    text = text.lower()
    return any(re.search(rf"\b{re.escape(p.lower())}\b", text) for p in patterns)


def _has(term, text):
    """Whole-term match that also works for terms like "c++", "c#" and ".net"."""
    return re.search(rf"(?<![\w+#.]){re.escape(term.lower())}(?![\w+#])", text) is not None


def _found(terms, text):
    text = text.lower()
    return [t for t in terms if _has(t, text)]


def skills_check(job, category):
    """Return (keep, matched_skills) based on the résumé skill lists in config.

    Drops a job when:
      1. its title names a stack from avoid_skills and none of your skills, or
      2. its description mentions avoid_skills and none of your skills, or
      3. its description is long enough to judge but mentions none of your
         skills (titles in skills_exempt_titles, e.g. QA and Sales Engineer,
         skip this rule since those postings often don't list languages).
    """
    mine = category.get("my_skills")
    if not mine:
        return True, []
    avoid = category.get("avoid_skills", [])
    title, desc = job["title"], job.get("description", "")
    title_mine, title_avoid = _found(mine, title), _found(avoid, title)
    if title_avoid and not title_mine:
        return False, []
    desc_mine = _found(mine, desc)
    matched = list(dict.fromkeys(title_mine + desc_mine))
    if matched:
        return True, matched
    if _found(avoid, desc):
        return False, []
    exempt = _any(category.get("skills_exempt_titles", []), title)
    if len(desc) >= category.get("skills_min_description", 600) and not exempt:
        return False, []
    return True, []


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


def check(job, category, settings, today=None, check_location=True):
    """Apply the category's filters. Returns (reason, texas, skills).

    reason is None when the job passes, otherwise a short explanation of why
    it doesn't fit (used by prune.py to label old rows).
    """
    title = job["title"]
    if not title or not job["company"]:
        return "missing title or company", "", []
    if not _any(category["title_include"], title):
        return "title doesn't match this search", "", []
    excluded = _found(category.get("title_exclude", []), title)
    if excluded:
        return f'title has "{excluded[0]}"', "", []

    texas = ""
    if check_location:
        ok, texas = location_status(job, category)
        if not ok:
            return "not remote and not near Austin", "", []

    keep, skills = skills_check(job, category)
    if not keep:
        stacks = _found(category.get("avoid_skills", []), title + " " + job.get("description", ""))
        return (f"needs {', '.join(stacks[:3])}, not on your résumé" if stacks
                else "doesn't mention any of your skills"), "", []

    # Pay cutoff: drop jobs whose pay range goes above salary_max.
    salary_max = category.get("salary_max")
    if salary_max and job["salary"]:
        pay = annual_pay(job["salary"])
        if pay:
            top_or_bottom = max(pay) if category.get("salary_cutoff", "top") == "top" else min(pay)
            if top_or_bottom > salary_max:
                return f"pay above ${salary_max / 1000:,.0f}k", "", []

    max_age = settings.get("max_days_old")
    if max_age and job.get("posted"):
        try:
            posted = date.fromisoformat(job["posted"])
            if posted < (today or date.today()) - timedelta(days=max_age):
                return f"posted more than {max_age} days ago", "", []
        except ValueError:
            pass
    return None, texas, skills


def match(job, category, settings, today=None):
    """Return an annotated copy of job if it fits the category, else None."""
    reason, texas, skills = check(job, category, settings, today)
    if reason:
        return None

    notes = [f"{category['name']} search", f"Location: {job['location'] or 'not stated'}"]
    if skills:
        notes.append("Your skills mentioned: " + ", ".join(skills[:6]))
    notes.append("Auto-found; verify on employer site before applying")

    out = dict(job)
    out.update(category=category["name"], texas=texas, notes=" · ".join(notes))
    return out
