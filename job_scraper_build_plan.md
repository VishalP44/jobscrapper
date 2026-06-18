# Job Scraper Pipeline — Claude Code Build Plan

A fully automated job aggregation pipeline that pulls listings from multiple boards, filters and scores them against a target profile, stores results in SQLite, and surfaces them via a Streamlit dashboard.

---

## Project Structure

```
job-scraper/
├── scraper/
│   ├── __init__.py
│   ├── fetch.py          # jobspy wrapper + RSS fallback
│   └── dedupe.py         # deduplication logic
├── pipeline/
│   ├── __init__.py
│   ├── run.py            # main entry point
│   ├── filter.py         # keyword / location / salary filters
│   └── score.py          # relevance scorer against profile
├── storage/
│   ├── __init__.py
│   └── db.py             # SQLite read/write helpers
├── dashboard/
│   └── app.py            # Streamlit dashboard
├── data/
│   └── jobs.db           # SQLite database (auto-created)
├── config.yaml           # all settings live here
├── requirements.txt
└── README.md
```

---

## Step 1 — Requirements

**File: `requirements.txt`**

```
python-jobspy==1.1.4
pandas
pyyaml
streamlit
schedule
sqlite-utils
rich
```

---

## Step 2 — Configuration

**File: `config.yaml`**

```yaml
search:
  queries:
    - "Data Analyst"
    - "Analytics Engineer"
    - "BI Analyst"
    - "Product Analyst"
  locations:
    - "Mumbai, India"
    - "Remote"
    - "London, UK"
  results_per_query: 30
  days_old_max: 14      # skip listings older than this

sources:
  jobspy:
    sites: [indeed, glassdoor, linkedin]  # linkedin is best-effort
    country: IN                           # change to GB for UK run

filters:
  exclude_keywords:
    - "5+ years"
    - "10 years"
    - "Director"
    - "VP"
    - "BPO"
    - "Data Entry"
  require_any_keyword:
    - "SQL"
    - "Power BI"
    - "Tableau"
    - "Snowflake"
    - "dbt"
    - "Python"
    - "BigQuery"
  min_salary_inr: 1600000   # 16 LPA in INR
  min_salary_gbp: 45000

scoring:
  profile_keywords:
    - "SQL"
    - "Power BI"
    - "Tableau"
    - "Snowflake"
    - "dbt"
    - "Python"
    - "BigQuery"
    - "Databricks"
    - "Azure"
    - "GCP"
    - "analytics"
    - "dashboard"
    - "ELT"
  boost_titles:
    - "Analytics Engineer"
    - "Senior Data Analyst"
    - "BI Engineer"
  penalise_titles:
    - "Data Entry"
    - "BPO"
    - "Fresher"

schedule:
  run_every_hours: 12
```

---

## Step 3 — Scraper Layer

### `scraper/fetch.py`

Use jobspy to pull jobs from multiple boards. Returns a normalised pandas DataFrame with columns:
`id, title, company, location, description, salary_min, salary_max, currency, date_posted, job_url, source, is_remote`

**Implementation steps:**
1. Load `config.yaml`
2. Loop over each `(query, location)` combination from config
3. Call `jobspy.scrape_jobs()` with:
   - `site_name` = `config.sources.jobspy.sites`
   - `search_term` = query
   - `location` = location
   - `results_wanted` = `config.search.results_per_query`
   - `country_indeed` = `config.sources.jobspy.country`
4. Concatenate all results into one DataFrame
5. Drop rows where `date_posted` is older than `config.search.days_old_max`
6. Return the combined DataFrame

**Error handling:**
- If jobspy raises for a specific site, log the error with `rich` and continue (do not crash the whole run)
- If all sites fail for a query, log a warning and skip that query

---

### `scraper/dedupe.py`

Deduplicate new jobs against what is already stored in the DB.

**Implementation steps:**
1. Accept: `new_df` (DataFrame), db connection
2. Load all existing `job_url` values from the jobs table
3. Filter `new_df` to only rows whose `job_url` is NOT in the existing set
4. Also deduplicate within `new_df` itself on `job_url` (same listing can appear from multiple sites in one run)
5. Return the deduplicated DataFrame (new jobs only)

---

## Step 4 — Filter and Score

### `pipeline/filter.py`

Filter jobs based on config rules. Returns filtered DataFrame.

**Implementation steps:**
1. Load `config.yaml`
2. Exclude rows where description or title contains any `config.filters.exclude_keywords` (case-insensitive)
3. Keep rows where description or title contains at least one `config.filters.require_any_keyword` (case-insensitive)
4. Salary filter (apply only if salary data is available):
   - For INR salaries: keep if `salary_max >= config.filters.min_salary_inr` OR if no salary data (do not discard listings with no salary)
   - For GBP salaries: keep if `salary_max >= config.filters.min_salary_gbp` OR if no salary data
5. Log how many rows were dropped at each stage using `rich`
6. Return the filtered DataFrame

---

### `pipeline/score.py`

Score each job 0–100 for relevance against the target profile. Adds a `relevance_score` column to the DataFrame.

**Scoring logic:**

| Component | Points |
|---|---|
| `keyword_hits`: count `profile_keywords` in title + description, normalised | 0–50 |
| `title_boost`: title matches any `boost_titles` | +20 |
| `title_penalty`: title matches any `penalise_titles` | −20 |
| `recency_bonus`: posted within 3 days | +15 |
| `recency_bonus`: posted within 7 days | +10 |
| `remote_bonus`: `is_remote` is True | +5 |

Clamp final score to 0–100.

**Tier assignment:**

| Score | Tier |
|---|---|
| ≥ 70 | Tier 1 — Apply today |
| ≥ 50 | Tier 2 — Apply this week |
| ≥ 30 | Tier 3 — Monitor |
| < 30 | Skip |

Return DataFrame with `relevance_score` and `tier` columns added.

---

## Step 5 — Storage

### `storage/db.py`

SQLite helpers using the `sqlite-utils` library.

**Functions to implement:**

**`init_db(db_path)`**
- Create/open SQLite DB at `db_path`
- Ensure table `jobs` exists with columns:

```sql
id TEXT PRIMARY KEY,
title TEXT,
company TEXT,
location TEXT,
description TEXT,
salary_min REAL,
salary_max REAL,
currency TEXT,
date_posted TEXT,
job_url TEXT UNIQUE,
source TEXT,
is_remote INTEGER,
relevance_score REAL,
tier TEXT,
applied INTEGER DEFAULT 0,   -- 0/1 flag
notes TEXT DEFAULT '',       -- free text from dashboard
scraped_at TEXT              -- ISO timestamp of when we found it
```

- Return db object

**`insert_jobs(db, df)`**
- Insert rows from df into `jobs` table
- Use `insert()` with `ignore=True` to skip duplicate `job_url`s
- Set `scraped_at` to current UTC timestamp
- Return count of rows inserted

**`get_jobs(db, tier=None, applied=None)`**
- Query jobs table
- Optional: filter by tier string
- Optional: filter by applied flag (0 or 1)
- Return as pandas DataFrame sorted by `relevance_score` DESC

**`update_applied(db, job_url, applied_flag)`**
- Set `applied = applied_flag` for the given `job_url`

**`update_notes(db, job_url, notes_text)`**
- Update `notes` field for the given `job_url`

---

## Step 6 — Pipeline Entry Point

### `pipeline/run.py`

Main pipeline runner.

**Steps:**
1. `init_db` from `storage/db.py`
2. Call `scraper/fetch.py` → `raw_df`
3. Call `scraper/dedupe.py` → `new_df` (only new listings)
4. If `new_df` is empty, log "No new jobs found" and exit
5. Call `pipeline/filter.py` → `filtered_df`
6. Call `pipeline/score.py` → `scored_df`
7. Call `storage/db.insert_jobs` → log count inserted
8. Print summary table using `rich`:
   - Total scraped, new, filtered out, inserted
   - Top 5 jobs by `relevance_score` with title, company, tier

**CLI interface (use argparse):**

```bash
python -m pipeline.run           # single run
python -m pipeline.run --watch   # run on schedule every N hours from config
```

`--watch` mode: use the `schedule` library to call the pipeline every `config.schedule.run_every_hours` hours, running in a loop.

---

## Step 7 — Dashboard

### `dashboard/app.py`

Streamlit dashboard. Run with: `streamlit run dashboard/app.py`

**Sidebar:**
- Filter by tier (multiselect)
- Filter by source (multiselect)
- Toggle: show applied / hide applied / show all
- Button: Run pipeline now (calls `pipeline/run.py` programmatically)

**Main area:**
- Summary metrics row: total jobs, Tier 1 count, Tier 2 count, applied count
- Jobs table (`st.dataframe`) with columns: `tier, relevance_score, title, company, location, salary_min, salary_max, date_posted, source, applied`
- Job detail expander — when user selects a row:
  - Show full description
  - Button to mark as Applied / Undo Applied
  - Text area to save notes
  - Link to `job_url` (`st.link_button`)

Refresh data from DB on every rerun (no caching). Use `st.session_state` to track selected row between interactions.

---

## Step 8 — README

Document the following in `README.md`:

### Setup
```bash
pip install -r requirements.txt
```

### Configuration
Edit `config.yaml` to change search queries, locations, filter keywords, and scoring weights.

### Run the pipeline once
```bash
python -m pipeline.run
```

### Run on a schedule
```bash
python -m pipeline.run --watch
```

Default interval is every 12 hours (set in `config.yaml`).

### Open the dashboard
```bash
streamlit run dashboard/app.py
```

### Notes on LinkedIn
`python-jobspy` attempts LinkedIn scraping but it rate-limits aggressively. Indeed and Glassdoor are more reliable. For India roles, Indeed IN is the most consistent source. For UK runs, change `country: GB` in `config.yaml`.

---

## Claude Code Prompt to Use

Paste this at the start of your Claude Code session:

> Read the build plan in `job_scraper_build_plan.md` and create the full project from scratch. Build each file in the order shown: `requirements.txt` → `config.yaml` → `scraper/` → `pipeline/` → `storage/` → `dashboard/app.py` → `README.md`. After creating all files, run `pip install -r requirements.txt` and then `python -m pipeline.run` to verify the pipeline works end to end. Fix any errors before finishing.
