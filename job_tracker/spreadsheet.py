"""Append newly found jobs to the existing Job_Search_Log.xlsx, in place.

The workbook's structure is preserved: the "Job Log" sheet and its Excel table
(JobLog), the Applied?/Status dropdowns, and the Summary sheet's formulas.
Existing rows are never modified. A job is skipped when the log already has a
row with the same employer + role, or the same application link.
"""

from __future__ import annotations

import os
import re
import shutil
from copy import copy
from datetime import date

from openpyxl import load_workbook
from openpyxl.styles import Font

SHEET = "Job Log"
HEADERS = [
    "Date Found", "Employer", "Role", "Pay", "Schedule", "Texas Eligible?",
    "Found Via (website)", "Application Link", "Applied?", "Date Applied",
    "Status", "Notes",
]
NEW_STATUS = "Unverified – check employer site"


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _norm_url(url):
    url = str(url or "").strip().lower()
    url = re.sub(r"^https?://(www\.)?", "", url)
    return url.split("?")[0].split("#")[0].rstrip("/")


def job_key(employer, role):
    return (_norm(employer), _norm(role))


def _col(ws):
    header = [c.value for c in ws[1]]
    missing = [h for h in HEADERS if h not in header]
    if missing:
        raise SystemExit(f"'{SHEET}' sheet is missing columns: {missing}")
    return {h: header.index(h) + 1 for h in HEADERS}


def _last_row(ws, cols):
    last = 1
    for r in range(2, ws.max_row + 1):
        if any(ws.cell(r, c).value not in (None, "") for c in cols.values()):
            last = r
    return last


def existing_keys(path):
    """Return (employer+role keys, normalized links) already in the log."""
    ws = load_workbook(path)[SHEET]
    cols = _col(ws)
    keys, links = set(), set()
    for r in range(2, _last_row(ws, cols) + 1):
        keys.add(job_key(ws.cell(r, cols["Employer"]).value, ws.cell(r, cols["Role"]).value))
        link = ws.cell(r, cols["Application Link"]).value
        if link:
            links.add(_norm_url(link))
    return keys, links


def to_row(job, today):
    return {
        "Date Found": today,
        "Employer": job["company"],
        "Role": job["title"],
        "Pay": job["salary"] or "Not listed",
        "Schedule": job["schedule"] or "Not stated",
        "Texas Eligible?": job["texas"],
        "Found Via (website)": f"Job tracker → {job['source']}",
        "Application Link": job["url"],
        "Applied?": "No",
        "Date Applied": None,
        "Status": NEW_STATUS,
        "Notes": job["notes"],
    }


def append_jobs(path, jobs, today=None, backup=True):
    """Append jobs not already in the log. Returns the rows actually added."""
    today = (today or date.today()).isoformat()
    wb = load_workbook(path)
    ws = wb[SHEET]
    cols = _col(ws)
    last = _last_row(ws, cols)

    keys, links = existing_keys(path)
    added = []
    for job in jobs:
        k, link = job_key(job["company"], job["title"]), _norm_url(job["url"])
        if k in keys or (link and link in links):
            continue
        keys.add(k)
        if link:
            links.add(link)
        row = to_row(job, today)
        r = last + 1
        for h, c in cols.items():
            cell = ws.cell(r, c, row[h])
            if last >= 2:  # copy the look of the row above
                above = ws.cell(last, c)
                cell.font, cell.border = copy(above.font), copy(above.border)
                cell.alignment, cell.number_format = copy(above.alignment), above.number_format
                cell.fill = copy(above.fill)
        if row["Application Link"]:
            link_cell = ws.cell(r, cols["Application Link"])
            link_cell.hyperlink = row["Application Link"]
            link_cell.font = Font(color="0563C1", underline="single")
        last = r
        added.append(row)

    if not added:
        return added

    # Grow the Excel table (and its autofilter) to cover the new rows.
    for table in ws.tables.values():
        start, end = table.ref.split(":")
        end_col = re.match(r"[A-Z]+", end).group()
        table.ref = f"{start}:{end_col}{last}"
        if table.autoFilter is not None:
            table.autoFilter.ref = table.ref

    if backup:
        shutil.copy2(path, path + ".bak")
    tmp = path + ".tmp.xlsx"
    wb.save(tmp)
    os.replace(tmp, path)
    return added
