import argparse
import sys
import os
import yaml
import schedule
import time

from rich.console import Console
from rich.table import Table

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.fetch import fetch_jobs
from scraper.dedupe import dedupe
from pipeline.filter import filter_jobs
from pipeline.score import score_jobs
from storage.db import init_db, insert_jobs

console = Console()
DB_PATH = "data/jobs.db"

def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)

def run_pipeline():
    console.rule("[bold blue]Job Scraper Pipeline[/bold blue]")

    db = init_db(DB_PATH)

    console.log("Fetching jobs...")
    raw_df = fetch_jobs()
    total_scraped = len(raw_df)
    console.log(f"Total scraped: {total_scraped}")

    console.log("Deduplicating...")
    new_df = dedupe(raw_df, db)
    console.log(f"New jobs (not in DB): {len(new_df)}")

    if new_df.empty:
        console.log("[yellow]No new jobs found. Exiting.[/yellow]")
        return

    console.log("Filtering...")
    filtered_df = filter_jobs(new_df)
    filtered_out = len(new_df) - len(filtered_df)

    console.log("Scoring...")
    scored_df = score_jobs(filtered_df)

    console.log("Inserting into DB...")
    inserted = insert_jobs(db, scored_df)

    summary = Table(title="Pipeline Summary", show_header=True)
    summary.add_column("Metric", style="cyan")
    summary.add_column("Count", style="magenta")
    summary.add_row("Total scraped", str(total_scraped))
    summary.add_row("New (not in DB)", str(len(new_df)))
    summary.add_row("Filtered out", str(filtered_out))
    summary.add_row("Inserted", str(inserted))
    console.print(summary)

    if not scored_df.empty:
        top5 = scored_df.nlargest(5, "relevance_score")[["title", "company", "tier", "relevance_score"]]
        top_table = Table(title="Top 5 Jobs", show_header=True)
        top_table.add_column("Title")
        top_table.add_column("Company")
        top_table.add_column("Tier")
        top_table.add_column("Score", justify="right")
        for _, row in top5.iterrows():
            top_table.add_row(
                str(row.get("title", "")),
                str(row.get("company", "")),
                str(row.get("tier", "")),
                f"{row.get('relevance_score', 0):.1f}",
            )
        console.print(top_table)

def main():
    parser = argparse.ArgumentParser(description="Job Scraper Pipeline")
    parser.add_argument("--watch", action="store_true", help="Run on schedule")
    args = parser.parse_args()

    if args.watch:
        config = load_config()
        hours = config["schedule"]["run_every_hours"]
        console.log(f"[bold]Watch mode:[/bold] running every {hours} hours")
        run_pipeline()
        schedule.every(hours).hours.do(run_pipeline)
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        run_pipeline()

if __name__ == "__main__":
    main()
