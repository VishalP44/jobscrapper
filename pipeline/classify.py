import pandas as pd

REGION_KEYWORDS = {
    "India": ["india", "mumbai", "bangalore", "bengaluru", "hyderabad", "delhi",
              "pune", "chennai", "gurgaon", "gurugram", "noida", "kolkata"],
    "UK": ["united kingdom", "uk", "england", "london", "manchester",
           "edinburgh", "birmingham", "scotland", "wales", "glasgow", "leeds"],
    "US": ["united states", "usa", "u.s.", "new york", "san francisco",
           "california", "texas", "chicago", "seattle", "boston", "austin",
           "remote - us", "nyc"],
}


def classify_region(location: str, is_remote=False) -> str:
    loc = str(location or "").lower()
    for region, keywords in REGION_KEYWORDS.items():
        if any(kw in loc for kw in keywords):
            return region
    if "remote" in loc or is_remote:
        return "Remote"
    return "Other"


def build_target_company_lookup(config: dict) -> dict:
    lookup = {}
    for category, companies in config.get("target_companies", {}).items():
        for company in companies:
            lookup[company.lower()] = category
    return lookup


def classify_target_company(company: str, lookup: dict) -> str:
    name = str(company or "").lower()
    if not name:
        return ""
    for keyword, category in lookup.items():
        if keyword in name:
            return category
    return ""


def add_classifications(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    if df.empty:
        return df
    lookup = build_target_company_lookup(config)
    df = df.copy()
    df["region"] = df.apply(
        lambda r: classify_region(r.get("location"), r.get("is_remote")), axis=1
    )
    df["target_category"] = df["company"].apply(lambda c: classify_target_company(c, lookup))
    return df
