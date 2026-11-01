# Job tracker

Searches job sites for your two searches and adds new matches to your existing
**Job_Search_Log.xlsx** (tab **Job Log**). You run it yourself whenever you want to refresh.

| Search | What it looks for |
|---|---|
| **Support** | Remote (work-from-home) tech support, customer service and help desk roles. Any schedule, temp or contract OK. |
| **Engineering** | Software Developer/Engineer, Senior SWE, QA/test, and Sales/Solutions Engineer. Remote nationwide, or on-site/hybrid within ~30 miles of 78660. |

Both searches skip Lead, Manager, Director and Supervisor titles. Engineering also skips Principal, Staff, Architect and Intern.
Engineering jobs paying $160k or more get a "check seniority/scope" note. They are not skipped.

## Setup (once)

Needs Python 3.11 or newer.

```bash
cd job_tracker
pip install -r requirements.txt
```

By default the tracker uses `~/Downloads/JobStuff/Job_Search_Log.xlsx`. Change `log_path` in
`config.toml`, or pass `--log`.

## Run

```bash
python track.py --dry-run      # preview new jobs; the spreadsheet is not touched
python track.py                # add new jobs to the log
python track.py --category Support
python track.py --sources remotive,themuse
```

**Close the spreadsheet in Excel before running.**

## What gets written

The tracker adds one row per new job, in the log's existing columns:

- **Found Via** says `Job tracker → <site>`.
- **Applied?** is `No`.
- **Status** is `Unverified – check employer site`.
- **Notes** names the search (Support/Engineering) and the listed location.

**Texas Eligible?** is only a guess from the listing's location text, so it always says "verify".

A job is skipped if the log already has a row with the same **employer + role** or the same
**application link**. Existing rows are never changed. Your edits, the JobLog table,
the Applied?/Status dropdowns and the Summary formulas are kept. The table grows to
cover the new rows. Before each change, the previous file is saved as
`Job_Search_Log.xlsx.bak`.

## Sources

| Source | Key needed? | Notes |
|---|---|---|
| Remotive | No | Remote jobs, searched by keyword |
| RemoteOK | No | Recent remote jobs |
| Arbeitnow | No | Mostly Europe; most listings get filtered out |
| The Muse | No | Searched by Muse category and location |
| Adzuna | Free key | Broad US coverage, including local Austin jobs. Register at https://developer.adzuna.com |
| USAJobs | Free key | Federal jobs. Request a key at https://developer.usajobs.gov |

Keyed sources are skipped until their environment variables are set:

```bash
export ADZUNA_APP_ID=...  ADZUNA_APP_KEY=...
export USAJOBS_API_KEY=... USAJOBS_EMAIL=you@example.com
```

## Tuning

Edit `config.toml` to change keywords, title include/exclude lists, local towns, the
age cutoff (`max_days_old`) or which sources run.
