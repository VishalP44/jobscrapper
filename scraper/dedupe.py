import pandas as pd

def dedupe(new_df: pd.DataFrame, db) -> pd.DataFrame:
    if new_df.empty:
        return new_df

    try:
        existing_urls = {row["job_url"] for row in db["jobs"].rows_where(select="job_url")}
    except Exception:
        existing_urls = set()

    new_df = new_df[new_df["job_url"].notna()]
    new_df = new_df[~new_df["job_url"].isin(existing_urls)]
    new_df = new_df.drop_duplicates(subset=["job_url"])

    return new_df.reset_index(drop=True)
