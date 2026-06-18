import yaml
import hashlib
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone, timedelta
from rich.console import Console

console = Console()

def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)

def fetch_jobs() -> pd.DataFrame:
    from jobspy import scrape_jobs

    config = load_config()
    queries   = config["search"]["queries"]
    locations = config["search"]["locations"]
    sites     = config["sources"]["jobspy"]["sites"]
    results_n = config["search"]["results_per_query"]
    days_old  = config["search"]["days_old_max"]

    all_frames = []

    for query in queries:
        for loc_entry in locations:
            location = loc_entry["location"]
            country  = loc_entry["country"]
            console.log(f"Scraping: [cyan]{query}[/cyan] in [cyan]{location}[/cyan] ({country}) via {sites}")
            for site in sites:
                try:
                    df = scrape_jobs(
                        site_name=[site],
                        search_term=query,
                        location=location,
                        results_wanted=results_n,
                        country_indeed=country,
                        hours_old=days_old * 24,
                        linkedin_fetch_description=True,
                        verbose=0,
                    )
                    console.log(f"  [green]{site}: {len(df)} results[/green]")
                    all_frames.append(df)
                except Exception as e:
                    console.log(f"  [yellow]{site} failed:[/yellow] {e}")

    if not all_frames:
        console.log("[yellow]No jobs fetched.[/yellow]")
        return pd.DataFrame()

    combined = pd.concat(all_frames, ignore_index=True)

    # Normalise columns to match the rest of the pipeline
    rename = {
        "site":        "source",
        "min_amount":  "salary_min",
        "max_amount":  "salary_max",
    }
    combined = combined.rename(columns={k: v for k, v in rename.items() if k in combined.columns})

    # Ensure required columns exist
    for col in ["id", "title", "company", "location", "description",
                "salary_min", "salary_max", "currency", "date_posted",
                "job_url", "source", "is_remote"]:
        if col not in combined.columns:
            combined[col] = None

    # Generate stable id from job_url
    def make_id(row):
        if row.get("id") and pd.notna(row["id"]):
            return str(row["id"])
        url = str(row.get("job_url") or "")
        return hashlib.md5(url.encode()).hexdigest() if url else hashlib.md5(
            (str(row.get("title", "")) + str(row.get("company", ""))).encode()
        ).hexdigest()

    combined["id"] = combined.apply(make_id, axis=1)
    combined["is_remote"] = combined["is_remote"].apply(
        lambda v: 1 if str(v).lower() in ("true", "1", "yes", "remote") else 0
    )

    # Drop listings older than days_old_max
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
    if "date_posted" in combined.columns:
        def within_cutoff(val):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return True  # keep if no date
            try:
                if hasattr(val, "tzinfo"):
                    dt = val if val.tzinfo else val.replace(tzinfo=timezone.utc)
                else:
                    dt = pd.to_datetime(val, utc=True)
                return dt >= cutoff
            except Exception:
                return True
        mask = combined["date_posted"].apply(within_cutoff)
        combined = combined[mask]

    combined = combined.drop_duplicates(subset=["id"]).reset_index(drop=True)
    console.log(f"[bold green]Total fetched: {len(combined)}[/bold green]")
    return combined
