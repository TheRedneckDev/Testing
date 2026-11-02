#!/usr/bin/env python3
"""Two-way sync between Job_Search_Log.xlsx and the Job Tracker page.

The page's data can only be read and written through Claude (its ArtifactData
tool), so a sync is a three-step loop, normally run by Claude for you (see the
`sync-job-tracker` skill in .claude/skills):

  1. Claude saves the page's `jobs` collection as JSON files into a folder.
  2. python sync.py plan --page-dir <folder>
       - copies page-only jobs and page-side edits into the spreadsheet
       - writes page_writes.json: the creates/updates the page needs
  3. Claude applies page_writes.json to the page, then runs
       python sync.py commit
     which records this sync as the new baseline.

How conflicts are settled: for each job (matched by employer + role, or by
application link) and each field, whichever side changed since the last sync
wins. If both changed it, the page wins and the conflict is reported. Jobs
deleted on one side after they were synced are not re-created there.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

from spreadsheet import _norm_url, job_key, read_rows, write_changes

HERE = os.path.dirname(os.path.abspath(__file__))
SWE = "Software Engineering"

# Page field <-> spreadsheet column.
FIELDS = {
    "dateFound": "Date Found", "employer": "Employer", "role": "Role", "pay": "Pay",
    "schedule": "Schedule", "txEligible": "Texas Eligible?", "foundVia": "Found Via (website)",
    "link": "Application Link", "applied": "Applied?", "dateApplied": "Date Applied",
    "status": "Status", "notes": "Notes",
}
SYNCED = list(FIELDS) + ["track"]
# Status wording differs slightly between the two.
PAGE_TO_XLSX_STATUS = {"In progress – not submitted": "In progress"}
XLSX_TO_PAGE_STATUS = {v: k for k, v in PAGE_TO_XLSX_STATUS.items()}
SEARCH_PREFIX = re.compile(r"^\s*(Support|Software Engineering|Engineering) search\s*(·\s*)?")


def _key(rec):
    return "|".join(job_key(rec["employer"], rec["role"]))


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80].strip("-")


# ---------------------------------------------------------------------------
# Convert both sides to one canonical record shape (the page's field names).
# ---------------------------------------------------------------------------

def from_xlsx(row):
    rec = {f: row.get(col, "") for f, col in FIELDS.items()}
    rec["applied"] = rec["applied"] or "No"
    rec["status"] = XLSX_TO_PAGE_STATUS.get(rec["status"], rec["status"])
    m = SEARCH_PREFIX.match(rec["notes"])
    rec["track"] = SWE if m and m.group(1) != "Support" else "Support"
    rec["notes"] = SEARCH_PREFIX.sub("", rec["notes"]).strip()
    return rec


def to_xlsx(rec):
    row = {col: rec.get(f, "") for f, col in FIELDS.items()}
    row["Status"] = PAGE_TO_XLSX_STATUS.get(rec["status"], rec["status"])
    if rec["track"] == SWE:
        row["Notes"] = f"{SWE} search" + (f" · {rec['notes']}" if rec["notes"] else "")
    return row


def from_page(doc):
    rec = {f: str(doc.get(f) or "").strip() for f in FIELDS}
    rec["applied"] = rec["applied"] or "No"
    rec["track"] = SWE if doc.get("track") == SWE else "Support"
    return rec


def to_page(rec):
    doc = {f: rec.get(f, "") for f in FIELDS}
    doc["track"] = rec["track"]
    doc["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return doc


# ---------------------------------------------------------------------------

def load_page(page_dir):
    docs = {}
    for path in glob.glob(os.path.join(page_dir, "**", "*.json"), recursive=True):
        with open(path) as f:
            doc = json.load(f)
        if isinstance(doc, dict) and (doc.get("employer") or doc.get("role")):
            docs[os.path.splitext(os.path.basename(path))[0]] = doc
    return docs


def state_paths(log_path):
    return log_path + ".sync.json", log_path + ".sync.pending.json"


def plan(log_path, page_dir, writes_path, dry_run=False):
    base_path, pending_path = state_paths(log_path)
    base = json.load(open(base_path)) if os.path.exists(base_path) else {}

    xrows = read_rows(log_path)
    xlsx = {}
    for row in xrows:
        rec = from_xlsx(row)
        xlsx[_key(rec)] = (rec, row["_row"])
    page = {}
    for doc_id, doc in load_page(page_dir).items():
        rec = from_page(doc)
        page[_key(rec)] = (rec, doc_id)

    # Pair page jobs with spreadsheet jobs by link when employer/role wording differs.
    x_by_link = {_norm_url(r["link"]): k for k, (r, _) in xlsx.items() if r["link"]}
    for k in list(page):
        if k not in xlsx:
            alt = x_by_link.get(_norm_url(page[k][0]["link"]))
            if alt and alt not in page:
                page[alt] = page.pop(k)

    xlsx_updates, xlsx_new, page_writes, conflicts, merged = [], [], [], [], {}
    xlsx_deletes = []
    used_ids = {doc_id for _, doc_id in page.values()}
    unchanged = lambda rec, b: all(rec.get(f, "") == b.get(f, "") for f in SYNCED)

    for k in sorted(set(xlsx) | set(page)):
        x, p, b = xlsx.get(k), page.get(k), base.get(k)
        if x and not p and b:
            # Synced before, now deleted on the page.
            if unchanged(x[0], b):
                xlsx_deletes.append((x[1], x[0]))
                continue
            conflicts.append(f"{x[0]['employer']} – {x[0]['role']}: deleted on the page but "
                             f"edited in the spreadsheet; kept and put back on the page")
        if p and not x and b:
            # Synced before, now deleted from the spreadsheet.
            if unchanged(p[0], b):
                page_writes.append({"op": "delete", "collection": "jobs", "doc_id": p[1],
                                    "if_version": "FILL_IN_FROM_LISTING",
                                    "_label": f"{p[0]['employer']} – {p[0]['role']}"})
                continue
            conflicts.append(f"{p[0]['employer']} – {p[0]['role']}: deleted from the spreadsheet "
                             f"but edited on the page; kept and put back in the spreadsheet")
        if x and not p:
            rec = x[0]
            doc_id = _slug(("swe " if rec["track"] == SWE else "") + f"{rec['employer']} {rec['role']}")
            while doc_id in used_ids:
                doc_id += "-2"
            used_ids.add(doc_id)
            page_writes.append({"op": "set", "collection": "jobs", "doc_id": doc_id, "data": to_page(rec)})
            merged[k] = rec
            continue
        if p and not x:
            xlsx_new.append(to_xlsx(p[0]))
            merged[k] = p[0]
            continue

        (xr, row_num), (pr, doc_id) = x, p
        result = {}
        for f in SYNCED:
            xv, pv, bv = xr.get(f, ""), pr.get(f, ""), (b or {}).get(f)
            if xv == pv:
                result[f] = xv
            elif bv is None:  # never synced: page wins unless it's blank
                result[f] = pv or xv
            elif xv == bv:
                result[f] = pv
            elif pv == bv:
                result[f] = xv
            else:
                result[f] = pv
                conflicts.append(f"{xr['employer']} – {xr['role']}: {f} "
                                 f"(spreadsheet '{xv}' vs page '{pv}'; kept page)")
        merged[k] = result
        if any(result[f] != xr.get(f, "") for f in SYNCED):
            want, have = to_xlsx(result), to_xlsx(xr)
            xlsx_updates.append((row_num, {c: v for c, v in want.items() if v != have[c]}))
        changed = {f: result[f] for f in SYNCED if result[f] != pr.get(f, "")}
        if changed:
            changed["updatedAt"] = to_page(result)["updatedAt"]
            page_writes.append({"op": "update", "collection": "jobs", "doc_id": doc_id,
                                "data": changed, "if_version": "FILL_IN_FROM_LISTING"})

    # Report
    print(f"Spreadsheet: {len(xlsx)} jobs · Page: {len(page)} jobs")
    print(f"  spreadsheet: {len(xlsx_new)} to add, {len(xlsx_updates)} to update, "
          f"{len(xlsx_deletes)} to delete")
    print(f"  page:        {sum(w['op'] == 'set' for w in page_writes)} to add, "
          f"{sum(w['op'] == 'update' for w in page_writes)} to update, "
          f"{sum(w['op'] == 'delete' for w in page_writes)} to delete")
    for _, rec in xlsx_deletes:
        print(f"    - spreadsheet: {rec['employer']} – {rec['role']}")
    for row in xlsx_new:
        print(f"    + spreadsheet: {row['Employer']} – {row['Role']}")
    for r, fields in xlsx_updates:
        print(f"    ~ spreadsheet row {r}: " + ", ".join(f"{c} → {v!r}" for c, v in fields.items()))
    for w in page_writes:
        sign = {"set": "+", "update": "~", "delete": "-"}[w["op"]]
        what = (f"{w['data']['employer']} – {w['data']['role']}" if w["op"] == "set"
                else w["_label"] if w["op"] == "delete"
                else ", ".join(f"{f} → {v!r}" for f, v in w["data"].items() if f != "updatedAt"))
        print(f"    {sign} page {w['doc_id']}: {what}")
    for c in conflicts:
        print(f"  ! conflict: {c}")

    if dry_run:
        return page_writes
    statuses = {to_xlsx(r)["Status"] for r in merged.values()}
    write_changes(log_path, xlsx_updates, xlsx_new, extra_statuses=sorted(statuses),
                  delete_rows=[r for r, _ in xlsx_deletes])
    with open(writes_path, "w") as f:
        json.dump([{k: v for k, v in w.items() if not k.startswith("_")} for w in page_writes],
                  f, indent=2, ensure_ascii=False)
    with open(pending_path, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"\nSpreadsheet updated. Page writes saved to {writes_path} "
          f"({len(page_writes)}). After applying them, run: python sync.py commit")
    return page_writes


def commit(log_path):
    base_path, pending_path = state_paths(log_path)
    if not os.path.exists(pending_path):
        sys.exit("Nothing to commit: run `python sync.py plan` first.")
    os.replace(pending_path, base_path)
    print(f"Sync baseline saved ({base_path}).")


def main(argv=None):
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # Python 3.8-3.10
        import tomli as tomllib
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["plan", "commit"])
    p.add_argument("--log", help="path to Job_Search_Log.xlsx (default: log_path in config.toml)")
    p.add_argument("--page-dir", help="folder holding the page's jobs as JSON files (plan)")
    p.add_argument("--writes", default=os.path.join(HERE, "page_writes.json"))
    p.add_argument("--dry-run", action="store_true", help="show the plan; change nothing")
    args = p.parse_args(argv)

    with open(os.path.join(HERE, "config.toml"), "rb") as f:
        log_path = os.path.expanduser(args.log or tomllib.load(f)["log_path"])
    if not os.path.exists(log_path):
        sys.exit(f"Job log not found: {log_path}")
    if args.command == "commit":
        return commit(log_path)
    if not args.page_dir:
        sys.exit("plan needs --page-dir")
    plan(log_path, args.page_dir, args.writes, args.dry_run)


if __name__ == "__main__":
    main()
