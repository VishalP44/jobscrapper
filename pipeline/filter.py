import re
import yaml
import pandas as pd
from rich.console import Console

console = Console()

def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)

def _extract_min_experience(text: str):
    """Return the minimum years of experience required from a text blob, or None."""
    t = text.lower()
    patterns = [
        r'(\d+)\s*\+\s*years?',
        r'(\d+)\s*plus\s+years?',
        r'minimum\s+(\d+)\s+years?',
        r'at\s+least\s+(\d+)\s+years?',
        r'(\d+)\s*[-–]\s*\d+\s*years?',
        r'(\d+)\s+to\s+\d+\s+years?',
        r'(\d+)\s+years?\s+(?:of\s+)?(?:relevant\s+)?(?:experience|exp\b)',
        r'experience\s*(?:of\s*)?(\d+)\s+years?',
        r'(\d+)\s+years?\b(?!\s+ago)',
    ]
    found = []
    for pattern in patterns:
        for m in re.findall(pattern, t):
            n = int(m)
            if 1 <= n <= 25:
                found.append(n)
    return min(found) if found else None

def filter_jobs(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    config = load_config()
    exclude_kw = [k.lower() for k in config["filters"]["exclude_keywords"]]
    require_kw  = [k.lower() for k in config["filters"]["require_any_keyword"]]
    min_inr     = config["filters"]["min_salary_inr"]
    min_gbp     = config["filters"]["min_salary_gbp"]
    my_exp      = config["filters"].get("my_experience_years")

    loc_cfg          = config.get("location_filter", {})
    allowed_regions  = [r.lower() for r in loc_cfg.get("allowed_regions", [])]
    keep_remote      = loc_cfg.get("keep_remote", True)
    uk_spon_required = loc_cfg.get("uk_sponsorship_required", False)

    initial = len(df)

    def full_text(row):
        return " ".join(filter(None, [
            str(row.get("title", "") or ""),
            str(row.get("description", "") or ""),
        ])).lower()

    # 1. Location filter (direct-from-source ATS jobs are curated target companies — exempt from this filter)
    ats_sources = {"greenhouse", "lever", "ashby"}
    if allowed_regions:
        def location_ok(row):
            if str(row.get("source") or "").lower() in ats_sources:
                return True
            loc = str(row.get("location") or "").lower()
            is_remote = row.get("is_remote") == 1 or "remote" in loc
            if is_remote and keep_remote:
                return True
            return any(region in loc for region in allowed_regions)

        mask_loc = df.apply(location_ok, axis=1)
        console.log(f"Dropped {(~mask_loc).sum()} rows outside India/UK (kept remote)")
        df = df[mask_loc]

    # 2. UK sponsorship filter
    if uk_spon_required and not df.empty:
        uk_kw    = ["uk", "united kingdom", "england", "london", "manchester", "edinburgh", "birmingham"]
        spon_kw  = ["sponsorship", "sponsor", "visa", "skilled worker"]

        def sponsorship_ok(row):
            loc  = str(row.get("location") or "").lower()
            desc = str(row.get("description") or "").lower()
            if not any(k in loc for k in uk_kw):
                return True
            return any(s in desc or s in loc for s in spon_kw)

        mask_spon = df.apply(sponsorship_ok, axis=1)
        console.log(f"Dropped {(~mask_spon).sum()} UK jobs with no sponsorship mention")
        df = df[mask_spon]

    # 3. Exclude blacklisted keywords
    mask_excl = df.apply(lambda r: any(kw in full_text(r) for kw in exclude_kw), axis=1)
    console.log(f"Excluded {mask_excl.sum()} rows by exclude_keywords")
    df = df[~mask_excl]

    # 4. Experience filter
    if my_exp is not None and not df.empty:
        max_allowed = my_exp + 1  # 1-year buffer

        def exp_ok(row):
            req = _extract_min_experience(full_text(row))
            if req is None:
                return True
            return req <= max_allowed

        mask_exp = df.apply(exp_ok, axis=1)
        console.log(f"Dropped {(~mask_exp).sum()} rows requiring more than {max_allowed} years experience")
        df = df[mask_exp]

    # 5. Salary filter — only discard if salary data present AND below threshold
    def salary_ok(row):
        sal_max  = row.get("salary_max")
        currency = str(row.get("currency") or "").upper()
        try:
            if pd.isna(sal_max) or sal_max is None:
                return True
        except TypeError:
            pass
        if "GBP" in currency or "£" in currency:
            return sal_max >= min_gbp
        if "INR" in currency or "₹" in currency:
            return sal_max >= min_inr
        return True

    mask_sal = df.apply(salary_ok, axis=1)
    console.log(f"Dropped {(~mask_sal).sum()} rows below salary threshold")
    df = df[mask_sal]

    console.log(f"[bold]Filter:[/bold] {initial} → {len(df)} jobs remaining")
    return df.reset_index(drop=True)
