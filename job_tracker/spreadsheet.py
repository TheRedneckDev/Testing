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


def _style_like(ws, src_row, dst_row, cols):
    for c in cols.values():
        above, cell = ws.cell(src_row, c), ws.cell(dst_row, c)
        cell.font, cell.border = copy(above.font), copy(above.border)
        cell.alignment, cell.number_format = copy(above.alignment), above.number_format
        cell.fill = copy(above.fill)


def _set_link(ws, r, cols, url):
    cell = ws.cell(r, cols["Application Link"], url or None)
    cell.hyperlink = url or None
    if url:
        cell.font = Font(color="0563C1", underline="single")


def _cell_text(v):
    if v is None:
        return ""
    if hasattr(v, "date") and callable(v.date):  # datetime from Excel
        return v.date().isoformat()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v).strip()


def read_rows(path):
    """All rows as {header: text} dicts, plus "_row" (the sheet row number)."""
    ws = load_workbook(path)[SHEET]
    cols = _col(ws)
    rows = []
    for r in range(2, _last_row(ws, cols) + 1):
        row = {h: _cell_text(ws.cell(r, c).value) for h, c in cols.items()}
        if row["Employer"] or row["Role"]:
            row["_row"] = r
            rows.append(row)
    return rows


def save(wb, path, backup=True):
    if backup and os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    tmp = path + ".tmp.xlsx"
    wb.save(tmp)
    os.replace(tmp, path)


def write_changes(path, updates=(), new_rows=(), extra_statuses=(), backup=True):
    """Apply cell updates and append rows, keeping table/dropdowns/formulas.

    updates: iterable of (sheet_row, {header: value}).
    new_rows: iterable of {header: value} dicts.
    extra_statuses: Status values to add to the Status dropdown if missing.
    """
    updates, new_rows = list(updates), list(new_rows)
    if not (updates or new_rows or extra_statuses):
        return
    wb = load_workbook(path)
    ws = wb[SHEET]
    cols = _col(ws)

    for r, fields in updates:
        for h, v in fields.items():
            if h == "Application Link":
                _set_link(ws, r, cols, v)
            else:
                ws.cell(r, cols[h], v if v != "" else None)

    last = _last_row(ws, cols)
    for row in new_rows:
        r = last + 1
        if last >= 2:
            _style_like(ws, last, r, cols)
        for h, c in cols.items():
            if h != "Application Link":
                v = row.get(h)
                ws.cell(r, c, v if v != "" else None)
        _set_link(ws, r, cols, row.get("Application Link"))
        last = r

    # Grow the Excel table (and its autofilter) to cover new rows.
    for table in ws.tables.values():
        start, end = table.ref.split(":")
        end_col = re.match(r"[A-Z]+", end).group()
        end_row = max(int(re.search(r"\d+", end).group()), last)
        table.ref = f"{start}:{end_col}{end_row}"
        if table.autoFilter is not None:
            table.autoFilter.ref = table.ref

    # Make sure every Status value used is offered by the dropdown.
    status_letter = ws.cell(1, cols["Status"]).column_letter
    for dv in ws.data_validations.dataValidation:
        if dv.formula1 and status_letter in str(dv.sqref):
            options = dv.formula1.strip('"').split(",")
            missing = [s for s in extra_statuses if s and s not in options]
            if missing:
                dv.formula1 = '"' + ",".join(options + missing) + '"'

    save(wb, path, backup)


def append_jobs(path, jobs, today=None, backup=True):
    """Append search results not already in the log. Returns the rows added."""
    today = (today or date.today()).isoformat()
    keys, links = existing_keys(path)
    added = []
    for job in jobs:
        k, link = job_key(job["company"], job["title"]), _norm_url(job["url"])
        if k in keys or (link and link in links):
            continue
        keys.add(k)
        if link:
            links.add(link)
        added.append(to_row(job, today))
    write_changes(path, new_rows=added, backup=backup)
    return added
