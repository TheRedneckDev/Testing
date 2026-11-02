# Job tracker: command cheat sheet

Searches job sites and adds new matches to a job-log spreadsheet. It has two profiles: one for Julian and one for Elizabeth.

| | Julian | Elizabeth |
|---|---|---|
| Searches | **Support** (remote tech support / customer service) and **Software Engineering** (Java/full-stack, QA, Sales Engineer) | **Customer Support** (non-technical, no sales) and **Receptionist** / front desk |
| Settings file | `job_tracker/config.toml` | `job_tracker/config-elizabeth.toml` |
| Spreadsheet | `~/JobTracker/JobStuff/Job_Search_Log.xlsx` | `~/JobTracker/ElizabethJobs/Job_Search_Log.xlsx` |
| Job Tracker page | [Synced](https://claude.ai/artifact/SXzbUitgGK2Q5jWACxrAct) | None (spreadsheet only) |

This page lists the commands. For how the filters, sources and sync work, see [`job_tracker/README.md`](job_tracker/README.md).

> Run every command from the `job_tracker` folder, and **close the spreadsheet in Excel first**.

```bash
cd ~/JobTracker/Testing/job_tracker
```

---

## Switching between Julian and Elizabeth

Every command runs **Julian's** profile by default. To run **Elizabeth's** instead, add `--config config-elizabeth.toml` to the same command:

| To… | Julian | Elizabeth |
|---|---|---|
| Preview new jobs | `python3 track.py --dry-run` | `python3 track.py --config config-elizabeth.toml --dry-run` |
| Add new jobs | `python3 track.py` | `python3 track.py --config config-elizabeth.toml` |
| Close postings that are gone | `python3 check_links.py` | `python3 check_links.py --config config-elizabeth.toml` |
| Delete jobs that no longer fit | `python3 prune.py --delete` | `python3 prune.py --config config-elizabeth.toml --delete` |
| Open the spreadsheet | `open ~/JobTracker/JobStuff/Job_Search_Log.xlsx` | `open ~/JobTracker/ElizabethJobs/Job_Search_Log.xlsx` |
| Sync with the Job Tracker page | Say "sync my job tracker" in Claude Code | Not set up; her list is only a spreadsheet |

The two profiles don't share anything except your API keys. Each has its own settings, spreadsheet and backups, so running one never touches the other's list.

**How to tell which one ran:** the first line of the output shows the spreadsheet being updated (`…/JobStuff/…` for Julian, `…/ElizabethJobs/…` for Elizabeth). The search names in the summary (Support / Software Engineering, or Customer Support / Receptionist) also show which profile it was.

### Optional: one-word shortcuts

To skip typing the folder and `--config` each time, add shortcuts to `~/.zshrc` once:

```bash
cat >> ~/.zshrc <<'ALIASES'
alias jobs-julian='cd ~/JobTracker/Testing/job_tracker && python3 track.py'
alias jobs-liz='cd ~/JobTracker/Testing/job_tracker && python3 track.py --config config-elizabeth.toml'
alias links-julian='cd ~/JobTracker/Testing/job_tracker && python3 check_links.py'
alias links-liz='cd ~/JobTracker/Testing/job_tracker && python3 check_links.py --config config-elizabeth.toml'
ALIASES
source ~/.zshrc
```

Then run them from any folder, adding options as usual:

```bash
jobs-liz --dry-run        # preview Elizabeth's new jobs
jobs-liz                  # add them to her spreadsheet
jobs-julian --dry-run     # preview Julian's
links-liz                 # close her postings that are gone
```

---

## First-time setup

```bash
git clone -b claude/intelligent-bohr-fcqs24 https://github.com/theredneckdev/testing.git
cd testing/job_tracker
pip3 install -r requirements.txt
```

Get the latest version later:

```bash
git pull origin claude/intelligent-bohr-fcqs24
pip3 install -r requirements.txt
```

---

## Everyday use

**Simplest:** open Claude Code in the repo and ask it to do everything:

```bash
cd ~/JobTracker/Testing && claude
```

Then type one of these:

| Say this | What happens |
|---|---|
| `find new jobs and sync my job tracker` | Searches, checks links, then syncs the spreadsheet and the page |
| `sync my job tracker` | Only syncs the spreadsheet and the page |
| `check which jobs are still open and sync my job tracker` | Re-checks open leads, then syncs |
| `prune my job list and sync my job tracker` | Screens out old rows that no longer fit your filters, then syncs |
| `delete jobs that don't fit and sync my job tracker` | Deletes those rows instead, from both the spreadsheet and the page |

**By hand, without Claude:**

```bash
python3 track.py --dry-run        # 1. preview what's new (changes nothing)
python3 track.py                  # 2. add the new jobs to the spreadsheet
python3 check_links.py            # 3. mark open leads whose postings closed
python3 prune.py                  # 4. (after changing filters) screen out old rows that no longer fit
open ~/JobTracker/JobStuff/Job_Search_Log.xlsx   # 5. look at the results
```

---

## Elizabeth's job search

Elizabeth's settings are in `job_tracker/config-elizabeth.toml`:

- **Searches:** Customer Support (non-technical) and Receptionist / front desk, including salon and spa front desk and virtual receptionist roles.
- **Location:** remote anywhere in the U.S., or on-site within about 20 miles of Pflugerville.
- **Pay:** $10/hr or more.
- **No sales:** sales titles and jobs whose description mentions cold calling, sales quotas or commission-only pay are skipped.

Her spreadsheet is `~/JobTracker/ElizabethJobs/Job_Search_Log.xlsx`. It's created automatically the first time `track.py` runs without `--dry-run`, in the same layout as Julian's.

For the commands, see [Switching between Julian and Elizabeth](#switching-between-julian-and-elizabeth).

Her searches use the same API keys (Adzuna, Jooble, USAJobs). Adzuna and Jooble are the main sources for local Pflugerville and Austin jobs, so make sure those keys are set. Her list isn't synced to a Job Tracker page; it's only a spreadsheet.

---

## Searching: `track.py`

```bash
# Preview without changing anything
python3 track.py --dry-run

# Search everything and add new jobs to the spreadsheet
python3 track.py

# Only one search
python3 track.py --category Support
python3 track.py --category "Software Engineering"

# Only certain sites (comma-separated, no spaces)
python3 track.py --dry-run --sources usajobs
python3 track.py --dry-run --sources adzuna,jooble
python3 track.py --sources companies              # only employers' own job boards
python3 track.py --sources hackernews             # only HN "Who is hiring?"

# Mix and match
python3 track.py --dry-run --category Support --sources remotive,jobicy

# Faster run that skips the "is the posting still open?" check
python3 track.py --dry-run --no-check-links

# Use a different spreadsheet
python3 track.py --log ~/Desktop/Test_Log.xlsx --dry-run
```

**Source names for `--sources`:** `remotive`, `remoteok`, `themuse`, `jobicy`, `himalayas`, `weworkremotely`, `workingnomads`, `hackernews`, `companies`, `adzuna`, `jooble`, `usajobs`, `arbeitnow`.

---

## Checking postings are still open: `check_links.py`

```bash
python3 check_links.py --dry-run   # list open leads whose postings are gone
python3 check_links.py             # mark them Closed, with a dated note
python3 check_links.py --dry-run --verbose   # also list every job that couldn't be checked
```

Some sites, Jooble especially, block automated checks. Those are grouped under "Couldn't check", so open them by hand if one interests you.

It only checks rows not yet applied to. Rows you've applied to are never changed.

---

## Cleaning up after changing filters: `prune.py`

New filters only apply to jobs found from then on. To re-apply them to jobs the tracker already added:

```bash
python3 prune.py --dry-run   # list the jobs that no longer fit, grouped by reason
python3 prune.py             # mark them "Screened out", with the reason in Notes
```

To **delete** them instead:

```bash
python3 prune.py --delete --dry-run   # list what would be deleted
python3 prune.py --delete             # delete them (also deletes rows an earlier prune marked)
```

It only touches rows the tracker added that you haven't changed yet (Applied? = No and Status = "Unverified – check employer site"). Jobs you logged yourself, or applied to, are never deleted. The previous file is saved as `Job_Search_Log.xlsx.bak`.

Run a sync afterwards ("sync my job tracker"). Deleted rows are then deleted from the page too, unless the job was edited on the page since the last sync. In that case it's kept, and Claude tells you.

---

## Syncing with the Job Tracker page: `sync.py`

Normally Claude runs this for you when you say "sync my job tracker". It's two steps because only Claude can read and write the page:

```bash
python3 sync.py plan --page-dir .page_snapshot   # after Claude saves the page snapshot
python3 sync.py commit                           # after Claude applies page_writes.json
python3 sync.py plan --page-dir .page_snapshot --dry-run   # just show the differences
```

---

## API keys (free)

Keys go in `~/.zshrc`. Keep the quotes and replace only the text inside them:

```bash
echo 'export USAJOBS_API_KEY="your-key"' >> ~/.zshrc
echo 'export USAJOBS_EMAIL="you@example.com"' >> ~/.zshrc
echo 'export ADZUNA_APP_ID="your-id"' >> ~/.zshrc
echo 'export ADZUNA_APP_KEY="your-key"' >> ~/.zshrc
echo 'export JOOBLE_API_KEY="your-key"' >> ~/.zshrc
source ~/.zshrc
```

Check which keys are loaded (this prints `set` or nothing, never the key):

```bash
echo "USAJobs: ${USAJOBS_API_KEY:+set}  Adzuna: ${ADZUNA_APP_KEY:+set}  Jooble: ${JOOBLE_API_KEY:+set}"
```

Get keys at: [USAJobs](https://developer.usajobs.gov) · [Adzuna](https://developer.adzuna.com) · [Jooble](https://jooble.org/api/about)

---

## Changing what it looks for

Everything is in `job_tracker/config.toml`:

```bash
open -e config.toml
```

| To change… | Edit |
|---|---|
| Search words | `search_keywords` |
| Which titles count | `title_include` / `title_exclude` |
| Your skills / stacks to avoid | `my_skills` / `avoid_skills` |
| Pay ceiling ($160k) | `salary_max`, `salary_cutoff` |
| How old a posting can be | `max_days_old` |
| Which sites run | `sources` |
| Employers to watch directly | `[settings.companies]` |
| Nearby towns counted as local | `local_terms` |

After editing, preview with `python3 track.py --dry-run`, then run `python3 prune.py --dry-run` to see which existing rows the change would screen out.

---

## Troubleshooting

| You see | Fix |
|---|---|
| `skipped (set ..._API_KEY ...)` | Run `source ~/.zshrc`, or open a new Terminal window |
| `unknown source 'xyz'` | Your copy is out of date: `git pull origin claude/intelligent-bohr-fcqs24` |
| `ModuleNotFoundError: tomllib` or `tomli` | `pip3 install -r requirements.txt` |
| `Job log not found` | Fix `log_path` in `config.toml`, or pass `--log path/to/file.xlsx` |
| `divergent branches` on `git pull` | `git switch claude/intelligent-bohr-fcqs24`, then pull again |
| Spreadsheet changes missing | Excel had the file open. Close it and re-run. The previous version is in `Job_Search_Log.xlsx.bak` |
| `couldn't read these boards` | That employer renamed or removed its job board. Fix or delete the name under `[settings.companies]` |
