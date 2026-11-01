#!/usr/bin/env python3
"""Re-check the links of open leads in Job_Search_Log.xlsx.

Open leads are rows not applied to whose Status isn't already final
(Closed, Screened out, Rejected, Offer, Interview, Submitted). When a
posting is gone, its Status becomes "Closed" and the Notes get
"Posting gone as of <date> (<reason>)". Rows you've applied to are never changed.

Usage:
    python check_links.py --dry-run   # show what would change
    python check_links.py             # update the spreadsheet
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from linkcheck import check_many
from spreadsheet import read_rows, write_changes

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = {"Closed", "Screened out", "Rejected", "Offer", "Interview",
         "Submitted – awaiting response"}


def main(argv=None):
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # Python 3.8-3.10
        import tomli as tomllib
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--log", help="path to Job_Search_Log.xlsx (default: log_path in config.toml)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    with open(os.path.join(HERE, "config.toml"), "rb") as f:
        log_path = os.path.expanduser(args.log or tomllib.load(f)["log_path"])
    if not os.path.exists(log_path):
        sys.exit(f"Job log not found: {log_path}")

    rows = [r for r in read_rows(log_path)
            if r["Applied?"] != "Yes" and r["Status"] not in FINAL and r["Application Link"]]
    print(f"Checking {len(rows)} open lead(s)...")
    results = check_many(r["Application Link"] for r in rows)

    today = date.today().isoformat()
    updates, unknown = [], []
    for r in rows:
        status, reason = results[r["Application Link"]]
        if status == "gone":
            note = f"Posting gone as of {today} ({reason})"
            notes = f"{r['Notes']} · {note}" if r["Notes"] else note
            updates.append((r["_row"], {"Status": "Closed", "Notes": notes}))
            print(f"  ✗ {r['Employer']} – {r['Role']}: {reason}")
        elif status == "unknown":
            unknown.append(f"{r['Employer']} – {r['Role']} ({reason})")

    print(f"\n{len(updates)} closed, {len(rows) - len(updates) - len(unknown)} still up, "
          f"{len(unknown)} couldn't be checked.")
    for u in unknown:
        print(f"  ? {u}")
    if updates and not args.dry_run:
        write_changes(log_path, updates)
        print(f"\nMarked {len(updates)} row(s) Closed. Previous version saved as {log_path}.bak")


if __name__ == "__main__":
    main()
