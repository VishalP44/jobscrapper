import sqlite_utils
import pandas as pd
from datetime import datetime, timezone

SCHEMA = {
    "id": str,
    "title": str,
    "company": str,
    "location": str,
    "description": str,
    "salary_min": float,
    "salary_max": float,
    "currency": str,
    "date_posted": str,
    "job_url": str,
    "source": str,
    "is_remote": int,
    "relevance_score": float,
    "tier": str,
    "ai_score": float,
    "ai_reason": str,
    "region": str,
    "target_category": str,
    "applied": int,
    "notes": str,
    "scraped_at": str,
    "is_new": int,
}

def init_db(db_path: str) -> sqlite_utils.Database:
    db = sqlite_utils.Database(db_path)
    if "jobs" not in db.table_names():
        db["jobs"].create(SCHEMA, pk="id", not_null=set(), defaults={"applied": 0, "notes": ""})
        db["jobs"].create_index(["job_url"], unique=True, if_not_exists=True)
    else:
        # Migrate: add new columns if they don't exist yet
        existing = {col.name for col in db["jobs"].columns}
        if "ai_score" not in existing:
            db["jobs"].add_column("ai_score", float)
        if "ai_reason" not in existing:
            db["jobs"].add_column("ai_reason", str)
        if "region" not in existing:
            db["jobs"].add_column("region", str)
        if "target_category" not in existing:
            db["jobs"].add_column("target_category", str)
        if "is_new" not in existing:
            db["jobs"].add_column("is_new", int, not_null_default=0)
    return db

def insert_jobs(db: sqlite_utils.Database, df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    scraped_at = datetime.now(timezone.utc).isoformat()
    records = []
    for _, row in df.iterrows():
        record = {}
        for col in SCHEMA:
            val = row.get(col)
            if pd.isna(val) if not isinstance(val, str) else False:
                val = None
            # Coerce datetime to string
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            record[col] = val
        record["scraped_at"] = scraped_at
        if not record.get("applied"):
            record["applied"] = 0
        if not record.get("notes"):
            record["notes"] = ""
        record["is_new"] = 1
        # Generate id from job_url if missing
        if not record.get("id") and record.get("job_url"):
            import hashlib
            record["id"] = hashlib.md5(record["job_url"].encode()).hexdigest()
        records.append(record)

    # Clear the "new" flag from the previous run's batch before inserting this one,
    # so only the most recent run's jobs are ever flagged as new.
    db.execute("UPDATE jobs SET is_new = 0 WHERE is_new = 1")

    before = db["jobs"].count
    db["jobs"].insert_all(records, ignore=True)
    after = db["jobs"].count
    return after - before

def get_jobs(db: sqlite_utils.Database, tier: str = None, applied: int = None) -> pd.DataFrame:
    where_clauses = []
    params = []
    if tier is not None:
        where_clauses.append("tier = ?")
        params.append(tier)
    if applied is not None:
        where_clauses.append("applied = ?")
        params.append(applied)

    where = " AND ".join(where_clauses) if where_clauses else None
    rows = list(db["jobs"].rows_where(where, params, order_by="date_posted desc, relevance_score desc"))
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=list(SCHEMA.keys()))

def update_applied(db: sqlite_utils.Database, job_url: str, applied_flag: int):
    db["jobs"].update_where("job_url = ?", [job_url], {"applied": applied_flag})

def update_notes(db: sqlite_utils.Database, job_url: str, notes_text: str):
    db["jobs"].update_where("job_url = ?", [job_url], {"notes": notes_text})

