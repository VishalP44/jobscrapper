import yaml
import pandas as pd
from datetime import datetime, timezone

def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)

def score_jobs(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    config = load_config()
    profile_kw      = [k.lower() for k in config["scoring"]["profile_keywords"]]
    boost_titles    = [t.lower() for t in config["scoring"]["boost_titles"]]
    penalise_titles = [t.lower() for t in config["scoring"]["penalise_titles"]]
    now = datetime.now(timezone.utc)

    def compute_score(row):
        title    = str(row.get("title", "") or "").lower()
        desc     = str(row.get("description", "") or "").lower()
        combined = title + " " + desc

        hits          = sum(1 for kw in profile_kw if kw in combined)
        keyword_score = min(hits / max(len(profile_kw), 1), 1.0) * 50
        score         = keyword_score

        if any(bt in title for bt in boost_titles):
            score += 20
        if any(pt in title for pt in penalise_titles):
            score -= 20

        date_posted = row.get("date_posted")
        if date_posted is not None and not pd.isna(date_posted):
            try:
                if hasattr(date_posted, "tzinfo") and date_posted.tzinfo is None:
                    date_posted = date_posted.replace(tzinfo=timezone.utc)
                days_old = (now - date_posted).days
                if days_old <= 3:
                    score += 15
                elif days_old <= 7:
                    score += 10
            except Exception:
                pass

        if row.get("is_remote"):
            score += 5

        return max(0, min(100, score))

    def assign_tier(score):
        if score >= 50:
            return "Tier 1 — Apply today"
        elif score >= 30:
            return "Tier 2 — Apply this week"
        elif score >= 15:
            return "Tier 3 — Monitor"
        return "Skip"

    df = df.copy()
    df["relevance_score"] = df.apply(compute_score, axis=1)
    df["tier"]            = df["relevance_score"].apply(assign_tier)
    return df
