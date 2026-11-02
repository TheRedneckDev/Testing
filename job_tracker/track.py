#!/usr/bin/env python3
"""Search job sources and add new matches to Job_Search_Log.xlsx.

Usage:
    python track.py                    # search everything, update the log
    python track.py --dry-run          # show what would be added, change nothing
    python track.py --category Support # only one search
    python track.py --log path/to/Job_Search_Log.xlsx
"""

from __future__ import annotations

import argparse
import os
import sys
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.8-3.10
    import tomli as tomllib

import requests

from filters import match
from linkcheck import check_many
from sources import SOURCES, SkipSource
from spreadsheet import NEW_STATUS, _norm_url, append_jobs, create_blank, existing_keys, job_key

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config(path):
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    for cat in cfg["categories"]:
        for k, v in cfg.get("locations", {}).items():
            cat.setdefault(k, v)
    return cfg


def search(cfg, only_category=None, only_sources=None, log=print):
    settings = cfg["settings"]
    source_names = only_sources or settings["sources"]
    found, seen = [], set()
    for cat in cfg["categories"]:
        if only_category and cat["name"].lower() != only_category.lower():
            continue
        matched = 0
        for name in source_names:
            fetch = SOURCES.get(name)
            if fetch is None:
                log(f"  ! unknown source '{name}' (choices: {', '.join(SOURCES)})")
                continue
            try:
                jobs = fetch(cat, settings)
            except SkipSource as e:
                log(f"  - {name}: skipped ({e})")
                continue
            except Exception as e:  # one broken source shouldn't stop the run
                log(f"  ! {name}: failed ({type(e).__name__}: {e})")
                continue
            hits = 0
            for job in jobs:
                m = match(job, cat, settings)
                if not m:
                    continue
                k = (job_key(m["company"], m["title"]), _norm_url(m["url"]))
                if k[0] in seen or (k[1] and k[1] in seen):
                    continue
                seen.update(x for x in k if x)
                found.append(m)
                hits += 1
            log(f"  {cat['name']:<12} {name:<10} {len(jobs):>4} fetched, {hits:>3} matched")
            matched += hits
        log(f"  {cat['name']}: {matched} matching jobs")
    return found


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=os.path.join(HERE, "config.toml"))
    p.add_argument("--log", help="path to Job_Search_Log.xlsx (overrides config)")
    p.add_argument("--category", help='run only this search, e.g. Support or "Software Engineering"')
    p.add_argument("--sources", help="comma-separated sources to use (default: all in config)")
    p.add_argument("--dry-run", action="store_true", help="show new jobs without editing the log")
    p.add_argument("--no-backup", action="store_true", help="don't write Job_Search_Log.xlsx.bak")
    p.add_argument("--no-check-links", action="store_true",
                   help="don't visit new jobs' links to confirm they're still active")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    log_path = os.path.expanduser(args.log or cfg["log_path"])
    if not os.path.exists(log_path):
        if args.dry_run:
            sys.exit(f"Job log not found: {log_path}\n"
                     f"Run once without --dry-run to create it, or fix log_path in {args.config}")
        create_blank(log_path)
        print(f"Created a new, empty job log: {log_path}")

    print(f"Searching ({'dry run' if args.dry_run else 'will update ' + log_path})...")
    sources = args.sources.split(",") if args.sources else None
    found = search(cfg, args.category, sources)

    # Only jobs not already in the log need their links checked.
    keys, links = existing_keys(log_path)
    candidates = [j for j in found
                  if job_key(j["company"], j["title"]) not in keys and _norm_url(j["url"]) not in links]
    already = len(found) - len(candidates)
    gone = []
    if candidates and not args.no_check_links:
        print(f"\nChecking {len(candidates)} new job link(s) are still active...")
        results = check_many(j["url"] for j in candidates)
        kept = []
        for j in candidates:
            status, reason = results.get(j["url"], ("unknown", "no link"))
            if status == "gone":
                gone.append((j, reason))
                continue
            if status == "unknown":
                j = dict(j, notes=f"{j['notes']} · Link not checked: {reason}")
            kept.append(j)
        candidates = kept

    if args.dry_run:
        new = candidates
    else:
        added = append_jobs(log_path, candidates, backup=not args.no_backup)
        new = [{"category": r["Notes"].split(" search")[0], "company": r["Employer"],
                "title": r["Role"], "salary": r["Pay"], "url": r["Application Link"]}
               for r in added]

    print(f"\n{len(new)} new job(s) {'would be ' if args.dry_run else ''}added "
          f"({already} already in the log, {len(gone)} no longer active).")
    for j in new:
        pay = f" — {j['salary']}" if j["salary"] and j["salary"] != "Not listed" else ""
        print(f"  [{j['category']}] {j['company']}: {j['title']}{pay}\n      {j['url']}")
    if gone:
        print("\nSkipped because the posting is gone:")
        for j, reason in gone:
            print(f"  ✗ {j['company']}: {j['title']} — {reason}")
    if new and not args.dry_run:
        print(f"\nNew rows have Status '{NEW_STATUS}' and Applied? = No.")
        if not args.no_backup:
            print(f"Previous version saved as {log_path}.bak")


if __name__ == "__main__":
    main()
