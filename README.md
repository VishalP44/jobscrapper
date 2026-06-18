# Job Scraper Pipeline

Automated job aggregation pipeline — scrapes multiple boards, filters and scores listings against your profile, stores in SQLite, and surfaces results via a Streamlit dashboard.

## Setup

```bash
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` to change search queries, locations, filter keywords, and scoring weights.

## Run the pipeline once

```bash
python -m pipeline.run
```

## Run on a schedule

```bash
python -m pipeline.run --watch
```

Default interval is every 12 hours (set in `config.yaml`).

## Open the dashboard

```bash
streamlit run dashboard/app.py
```

Each pipeline run flags newly inserted jobs (`is_new`), surfaced in the dashboard via a "🆕 New since last run" filter, metric tile, and card/table indicators — so you can see at a glance what showed up since the last scrape.

## Notes on LinkedIn

`python-jobspy` attempts LinkedIn scraping but it rate-limits aggressively. Indeed and Glassdoor are more reliable. For India roles, Indeed IN is the most consistent source. For UK runs, change `country: GB` in `config.yaml`.
