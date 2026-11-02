#!/usr/bin/env python3
"""Re-apply the current filters to jobs the tracker already added.

Use this after changing filters (config.toml), so older rows that no longer fit
are labelled. Only rows the tracker added ("Job tracker → ..." in Found Via)
that are still untouched (Applied? = No and Status "Unverified – check employer
site") are checked. A row that no longer fits becomes "Screened out", with
"Screened out by filter: <reason>" added to Notes. Nothing is deleted.

Old rows only keep the title, employer, pay and location, so the checks that need
the full description can't be repeated here: titles, pay and location are.

Usage:
    python prune.py --dry-run   # show what would be screened out
    python prune.py             # update the spreadsheet
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from filters import check
from spreadsheet import NEW_STATUS, read_rows, write_changes
from track import load_config

HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH = re.compile(r"^\s*(Support|Software Engineering|Engineering) search\b")
LOCATION = re.compile(r"Location: ([^·]*)")


def row_to_job(row):
    loc = LOCATION.search(row["Notes"] or "")
    location = loc.group(1).strip() if loc else ""
    return {
        "title": row["Role"], "company": row["Employer"],
        "salary": "" if row["Pay"] in ("", "Not listed") else row["Pay"],
        "location": "" if location == "not stated" else location,
        "remote": None, "description": "", "posted": "",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=os.path.join(HERE, "config.toml"))
    p.add_argument("--log", help="path to Job_Search_Log.xlsx (default: log_path in config.toml)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    log_path = os.path.expanduser(args.log or cfg["log_path"])
    if not os.path.exists(log_path):
        sys.exit(f"Job log not found: {log_path}")
    categories = {c["name"]: c for c in cfg["categories"]}
    categories["Engineering"] = categories.get("Software Engineering")

    rows = [r for r in read_rows(log_path)
            if str(r["Found Via (website)"]).startswith("Job tracker")
            and r["Applied?"] != "Yes" and r["Status"] in (NEW_STATUS, "")]
    updates, by_reason = [], {}
    for r in rows:
        m = SEARCH.match(r["Notes"] or "")
        category = categories.get(m.group(1)) if m else None
        if not category:
            continue
        reason, _, _ = check(row_to_job(r), category, cfg["settings"], check_location=False)
        if reason:
            note = f"Screened out by filter: {reason}"
            updates.append((r["_row"], {"Status": "Screened out", "Notes": f"{r['Notes']} · {note}"}))
            by_reason.setdefault(reason, []).append(f"{r['Employer']} – {r['Role']}")

    print(f"Checked {len(rows)} untouched job(s) added by the tracker.")
    print(f"{len(updates)} {'would be ' if args.dry_run else ''}screened out, "
          f"{len(rows) - len(updates)} still fit.\n")
    for reason, jobs in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        print(f"  {reason} ({len(jobs)}):")
        for j in jobs:
            print(f"    ✗ {j}")
    if updates and not args.dry_run:
        write_changes(log_path, updates)
        print(f"\nMarked {len(updates)} row(s) Screened out. Previous version saved as {log_path}.bak")


if __name__ == "__main__":
    main()
