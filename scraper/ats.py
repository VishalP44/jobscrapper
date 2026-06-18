import re
import hashlib
import requests
import pandas as pd
import yaml
from rich.console import Console

console = Console()

REQUIRED_COLUMNS = ["id", "title", "company", "location", "description",
                    "salary_min", "salary_max", "currency", "date_posted",
                    "job_url", "source", "is_remote"]


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def _make_id(job_url: str) -> str:
    return hashlib.md5(job_url.encode()).hexdigest()


def fetch_greenhouse(company: str, token: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    resp = requests.get(url, params={"content": "true"}, timeout=20)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])

    records = []
    for j in jobs:
        location = (j.get("location") or {}).get("name") or ""
        job_url = j.get("absolute_url") or ""
        records.append({
            "id": _make_id(job_url) if job_url else str(j.get("id")),
            "title": j.get("title", "").strip(),
            "company": company,
            "location": location,
            "description": _strip_html(j.get("content", "")),
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "date_posted": j.get("first_published") or j.get("updated_at"),
            "job_url": job_url,
            "source": "greenhouse",
            "is_remote": 1 if "remote" in location.lower() else 0,
        })
    return records


def fetch_lever(company: str, token: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{token}"
    resp = requests.get(url, params={"mode": "json"}, timeout=20)
    resp.raise_for_status()
    jobs = resp.json()
    if not isinstance(jobs, list):
        return []

    records = []
    for j in jobs:
        categories = j.get("categories") or {}
        location = categories.get("location") or ""
        job_url = j.get("hostedUrl") or j.get("applyUrl") or ""
        created_at = j.get("createdAt")
        date_posted = pd.to_datetime(created_at, unit="ms", utc=True).isoformat() if created_at else None
        records.append({
            "id": _make_id(job_url) if job_url else str(j.get("id")),
            "title": (j.get("text") or "").strip(),
            "company": company,
            "location": location,
            "description": _strip_html(j.get("descriptionPlain") or j.get("description") or ""),
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "date_posted": date_posted,
            "job_url": job_url,
            "source": "lever",
            "is_remote": 1 if "remote" in location.lower() else 0,
        })
    return records


def fetch_ashby(company: str, token: str) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])

    records = []
    for j in jobs:
        if not j.get("isListed", True):
            continue
        location = j.get("location") or ""
        job_url = j.get("jobUrl") or j.get("applyUrl") or ""
        records.append({
            "id": _make_id(job_url) if job_url else str(j.get("id")),
            "title": (j.get("title") or "").strip(),
            "company": company,
            "location": location,
            "description": _strip_html(j.get("descriptionHtml", "")),
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "date_posted": j.get("publishedAt"),
            "job_url": job_url,
            "source": "ashby",
            "is_remote": 1 if j.get("isRemote") else 0,
        })
    return records


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def fetch_ats_jobs() -> pd.DataFrame:
    config = load_config()
    boards = config.get("ats_boards", [])

    all_records = []
    for board in boards:
        company  = board["company"]
        platform = board["platform"]
        token    = board["token"]
        fetcher  = FETCHERS.get(platform)
        if not fetcher:
            console.log(f"[yellow]Unknown ATS platform: {platform}[/yellow]")
            continue
        try:
            records = fetcher(company, token)
            console.log(f"  [green]{platform}/{company}: {len(records)} results[/green]")
            all_records.extend(records)
        except Exception as e:
            console.log(f"  [yellow]{platform}/{company} failed:[/yellow] {e}")

    if not all_records:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.DataFrame(all_records)
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df.drop_duplicates(subset=["id"]).reset_index(drop=True)
