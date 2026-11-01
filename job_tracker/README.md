# Job tracker

Searches job sites for your two searches and adds new matches to your existing
**Job_Search_Log.xlsx** (tab **Job Log**). You run it yourself whenever you want to refresh.

| Search | What it looks for |
|---|---|
| **Support** | Remote (work-from-home) tech support, customer service and help desk roles. Any schedule, temp or contract OK. |
| **Software Engineering** | Software Developer/Engineer, Senior SWE, QA/test, and Sales/Solutions Engineer. Remote nationwide, or on-site/hybrid within ~30 miles of 78660. |

Both searches skip Lead, Manager, Director and Supervisor titles. Software Engineering also skips Principal, Staff, Architect and Intern. It also matches government titles like Programmer, Programmer Analyst and IT Specialist (APPSW).
Software Engineering jobs paying $160k or more get a "check seniority/scope" note. They are not skipped.

## Setup (once)

Needs Python 3.8 or newer.

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
- **Notes** names the search (Support or Software Engineering) and the listed location.

**Texas Eligible?** is only a guess from the listing's location text, so it always says "verify".

A job is skipped if the log already has a row with the same **employer + role** or the same
**application link**. Existing rows are never changed. Your edits, the JobLog table,
the Applied?/Status dropdowns and the Summary formulas are kept. The table grows to
cover the new rows. Before each change, the previous file is saved as
`Job_Search_Log.xlsx.bak`.

## Sources

| Source | Key needed? | What it covers |
|---|---|---|
| Remotive, RemoteOK, Jobicy, Himalayas, We Work Remotely, Working Nomads, The Muse | No | Remote job boards |
| Hacker News "Who is hiring?" | No | The monthly startup hiring thread. Each post's first line ("Company \| Role \| Location \| Pay") becomes the role, so check the link for details |
| Employer boards (`companies`) | No | Openings on employers' own Greenhouse, Lever and Ashby pages. Starts with the employers in your log; add more under `[settings.companies]` in config.toml |
| USAJobs | Free key | Federal government jobs. Request one at https://developer.usajobs.gov |
| Adzuna | Free key | Big US aggregator, including local Austin jobs. Sign up at https://developer.adzuna.com |
| Jooble | Free key | Big aggregator that pulls from many job sites. Get a key at https://jooble.org/api/about |
| Arbeitnow | No | Mostly European jobs, so it's off by default. Add "arbeitnow" to `sources` to use it |

Sites that aren't included:
- **Built In, Wellfound (AngelList) and YC's Work at a Startup** have no public feed, and their terms forbid scraping. Many of their listings link to the employer's Greenhouse, Lever or Ashby page, so you can add those employers under `[settings.companies]` instead.
- **Texas state jobs (CAPPS) and City of Austin / Travis County jobs** have no public feed. For government work, USAJobs (federal) is the one with an API.
- **LinkedIn and Indeed** have no public job-search API.

Keyed sources are skipped until their environment variables are set. Add these lines to `~/.zshrc` to keep them:

```bash
export USAJOBS_API_KEY=... USAJOBS_EMAIL=you@example.com
export ADZUNA_APP_ID=...  ADZUNA_APP_KEY=...
export JOOBLE_API_KEY=...
```

If an employer board can't be read (for example, the company renamed it), the run says so and keeps going.

## Tuning

Edit `config.toml` to change keywords, title include/exclude lists, local towns, the
age cutoff (`max_days_old`) or which sources run.

## Keeping the spreadsheet and the Job Tracker page in sync

The [Job Tracker page](https://claude.ai/artifact/SXzbUitgGK2Q5jWACxrAct) keeps its own copy
of the log. Only Claude can read and write it, so syncing goes through Claude Code. Open
Claude Code in this repo on your Mac and say:

> sync my job tracker

or, to search for new jobs first:

> find new jobs and sync my job tracker

Claude follows the `sync-job-tracker` skill in `.claude/skills/`:

1. It runs `track.py` (only if you asked for a search).
2. It saves a snapshot of the page.
3. It runs `sync.py plan`, which updates the spreadsheet.
4. It applies the resulting changes to the page.
5. It runs `sync.py commit` to save the new sync baseline.

How the sync decides:

- **Missing jobs:** a job on only one side is copied to the other. Jobs are matched by employer + role, or by link.
- **Edits:** for each field (Status, Applied?, Date Applied, Notes and so on), whichever side changed since the last sync wins.
- **Conflicts:** if both sides changed the same field, the page wins and Claude tells you.
- **Deletions:** a job deleted on one side after a sync is not re-created there.
- **Wording:** Software Engineering jobs are marked "Software Engineering search · …" in the spreadsheet's Notes. The page's "In progress – not submitted" status is "In progress" in the spreadsheet.

The sync baseline is saved next to the spreadsheet as `Job_Search_Log.xlsx.sync.json`.
