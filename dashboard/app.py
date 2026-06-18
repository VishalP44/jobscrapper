import sys
import os
import subprocess
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.db import init_db, get_jobs, update_applied, update_notes

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "jobs.db")

st.set_page_config(page_title="Job Scraper", layout="wide", page_icon="🎯")

st.markdown("""
<style>
.stApp { background-color: #f4f6fb; }
[data-testid="stMetric"] {
    background: #ffffff;
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    border: 1px solid #ececf5;
}
[data-testid="stMetricValue"] { font-size: 1.6rem; }
h1 { font-weight: 800; letter-spacing: -0.5px; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [data-baseweb="tab"] {
    background: #ffffff;
    border-radius: 8px 8px 0 0;
    padding: 8px 16px;
    border: 1px solid #ececf5;
}
.stTabs [aria-selected="true"] {
    background: #1e293b !important;
    color: white !important;
}
.job-card {
    background: #ffffff;
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    border: 1px solid #ececf5;
    margin-bottom: 14px;
    height: 100%;
}
.job-card-title { font-weight: 700; font-size: 1.02rem; margin-bottom: 2px; }
.job-card-company { color: #555; font-size: 0.9rem; margin-bottom: 8px; }
.pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    color: white;
    font-size: 0.72rem;
    font-weight: 700;
    margin-right: 6px;
}
</style>
""", unsafe_allow_html=True)

st.title("🎯 Job Scraper Dashboard")
st.caption("Your personal job radar — scraped, scored, and sorted so you don't have to dig.")

db = init_db(DB_PATH)
df = get_jobs(db)

TIER_COLORS = {
    "Tier 1 — Apply today":     "#1e7d32",
    "Tier 2 — Apply this week": "#b8860b",
    "Tier 3 — Monitor":         "#1565c0",
    "Skip":                     "#616161",
}
TARGET_COLORS = {
    "finance":  "#6a1b9a",
    "tech":     "#0277bd",
    "retail":   "#ef6c00",
    "startups": "#c2185b",
    "fintech":  "#00897b",
}
REGION_FLAGS = {
    "India": "🇮🇳", "UK": "🇬🇧", "US": "🇺🇸", "Europe": "🇪🇺", "Remote": "🌐", "Other": "🗺️",
}

def style_table(view: pd.DataFrame):
    def tier_style(val):
        color = TIER_COLORS.get(val)
        return f"background-color: {color}; color: white;" if color else ""

    def target_style(val):
        color = TARGET_COLORS.get(val)
        return f"background-color: {color}; color: white; font-weight: bold;" if color else ""

    styler = view.style
    if "tier" in view.columns:
        styler = styler.applymap(tier_style, subset=["tier"])
    if "target_category" in view.columns:
        styler = styler.applymap(target_style, subset=["target_category"])
    return styler

# --- Sidebar ---
st.sidebar.header("Filters")

all_tiers = ["Tier 1 — Apply today", "Tier 2 — Apply this week", "Tier 3 — Monitor", "Skip"]
selected_tiers = st.sidebar.multiselect("Tier", options=all_tiers, default=["Tier 1 — Apply today", "Tier 2 — Apply this week"])

all_sources = sorted(df["source"].dropna().unique().tolist()) if not df.empty else []
selected_sources = st.sidebar.multiselect("Source", options=all_sources, default=all_sources)

all_countries = sorted(df["region"].dropna().unique().tolist()) if not df.empty else []
selected_countries = st.sidebar.multiselect("Country / Region", options=all_countries, default=all_countries)

ROLE_OPTIONS = ["Data Analyst", "Analytics Engineer", "Business Intelligence",
                 "Business Analyst", "Product Analyst", "BI Engineer", "Reporting Analyst"]
selected_roles = st.sidebar.multiselect("Role", options=ROLE_OPTIONS, default=[])

applied_filter = st.sidebar.radio("Applied status", ["All", "Not applied", "Applied"], index=1)

search_query = st.sidebar.text_input("🔎 Search title or company", value="")

if st.sidebar.button("Run pipeline now"):
    with st.spinner("Running pipeline..."):
        result = subprocess.run(
            [sys.executable, "-m", "pipeline.run"],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        st.sidebar.success("Pipeline finished!")
        if result.stdout:
            st.sidebar.text(result.stdout[-2000:])
        if result.returncode != 0 and result.stderr:
            st.sidebar.error(result.stderr[-1000:])
    st.rerun()

# --- Apply shared filters ---
base = df.copy()
if selected_tiers and not base.empty:
    base = base[base["tier"].isin(selected_tiers)]
if selected_sources and not base.empty:
    base = base[base["source"].isin(selected_sources)]
if selected_countries and not base.empty:
    base = base[base["region"].isin(selected_countries)]
if selected_roles and not base.empty:
    roles_lower = [r.lower() for r in selected_roles]
    base = base[base["title"].str.lower().apply(lambda t: any(r in t for r in roles_lower))]
if not base.empty:
    if applied_filter == "Not applied":
        base = base[base["applied"] == 0]
    elif applied_filter == "Applied":
        base = base[base["applied"] == 1]
if search_query and not base.empty:
    q = search_query.lower()
    base = base[
        base["title"].str.lower().str.contains(q, na=False)
        | base["company"].str.lower().str.contains(q, na=False)
    ]
base = base.reset_index(drop=True)

# --- Top metrics ---
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total jobs (DB)", len(df))
col2.metric("Tier 1", len(df[df["tier"] == "Tier 1 — Apply today"]) if not df.empty else 0)
col3.metric("Tier 2", len(df[df["tier"] == "Tier 2 — Apply this week"]) if not df.empty else 0)
col4.metric("Target companies", len(df[df["target_category"] != ""]) if not df.empty else 0)
col5.metric("Applied", int(df["applied"].sum()) if not df.empty else 0)

# --- Charts ---
if not df.empty:
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.caption("Jobs by tier")
        st.bar_chart(df["tier"].value_counts())
    with chart_col2:
        st.caption("Jobs by region")
        st.bar_chart(df["region"].value_counts())

st.divider()

# --- Top Matches: card view of the best current matches ---
if not base.empty:
    st.subheader("🔥 Top Matches")
    top_n = base.sort_values("relevance_score", ascending=False).head(6).reset_index(drop=True)
    card_cols = st.columns(3)
    for i, row in top_n.iterrows():
        with card_cols[i % 3]:
            tier_color = TIER_COLORS.get(row.get("tier"), "#616161")
            cat = row.get("target_category") or ""
            cat_color = TARGET_COLORS.get(cat, "#9e9e9e")
            region = row.get("region") or ""
            flag = REGION_FLAGS.get(region, "")
            pills = f'<span class="pill" style="background:{tier_color}">{row.get("tier","")}</span>'
            if cat:
                pills += f'<span class="pill" style="background:{cat_color}">{cat.title()}</span>'
            st.markdown(f"""
            <div class="job-card">
                <div class="job-card-title">{row.get('title','')}</div>
                <div class="job-card-company">{row.get('company','')} &nbsp;·&nbsp; {flag} {row.get('location','')}</div>
                {pills}
                <div style="margin-top:8px; font-size:0.85rem; color:#444;">Score: <b>{row.get('relevance_score',0):.0f}</b> &nbsp;|&nbsp; Posted: {str(row.get('date_posted',''))[:10]}</div>
            </div>
            """, unsafe_allow_html=True)
            job_url = row.get("job_url") or ""
            if job_url:
                st.link_button("Open ↗", job_url, key=f"open_top_{i}", use_container_width=True)
    st.divider()

display_cols = ["tier", "relevance_score", "title", "company", "target_category",
                 "location", "region", "date_posted", "source", "applied"]

def render_job_table(view: pd.DataFrame, key_prefix: str):
    view = view.reset_index(drop=True)
    cols = [c for c in display_cols if c in view.columns]
    if view.empty:
        st.info("No jobs match the current filters.")
        return None
    event = st.dataframe(
        style_table(view[cols]),
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"table_{key_prefix}",
    )
    return view, event.selection.rows

# --- Tabs: All / regions / target companies ---
regions_present = [r for r in ["India", "UK", "US", "Europe", "Remote", "Other"] if not base.empty and r in base["region"].unique()]
tab_labels = ["All"] + [f"{REGION_FLAGS.get(r, '')} {r}" for r in regions_present] + ["⭐ Target Companies"]
tabs = st.tabs(tab_labels)

selection = None

with tabs[0]:
    st.subheader(f"All jobs ({len(base)} shown)")
    result = render_job_table(base, "all")
    if result and result[1]:
        selection = result

for i, region in enumerate(regions_present, start=1):
    with tabs[i]:
        region_df = base[base["region"] == region]
        st.subheader(f"{region} jobs ({len(region_df)} shown)")
        result = render_job_table(region_df, f"region_{region}")
        if result and result[1]:
            selection = result

with tabs[-1]:
    target_df = base[base["target_category"] != ""] if not base.empty else base
    st.subheader(f"Target companies ({len(target_df)} shown)")
    st.caption("Finance, tech, retail, startup, and European fintech companies you're prioritizing — edit the list in config.yaml under `target_companies`.")
    if not target_df.empty:
        cat_col1, cat_col2, cat_col3, cat_col4, cat_col5 = st.columns(5)
        cat_col1.metric("Finance", len(target_df[target_df["target_category"] == "finance"]))
        cat_col2.metric("Tech", len(target_df[target_df["target_category"] == "tech"]))
        cat_col3.metric("Retail", len(target_df[target_df["target_category"] == "retail"]))
        cat_col4.metric("Startups", len(target_df[target_df["target_category"] == "startups"]))
        cat_col5.metric("Fintech (EU)", len(target_df[target_df["target_category"] == "fintech"]))
    result = render_job_table(target_df, "targets")
    if result and result[1]:
        selection = result

# --- Job detail panel ---
st.divider()
if selection is None or not selection[1]:
    st.info("Click a row in any tab above to view full job details.")
    st.stop()

sel_view, sel_rows = selection
sel_idx = sel_rows[0]
sel_row = sel_view.iloc[sel_idx]
job_url = sel_row.get("job_url", "")

st.subheader(f"{sel_row.get('title', 'Job Detail')} — {sel_row.get('company', '')}")

c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"**Location:** {sel_row.get('location', '—')}")
c2.markdown(f"**Score:** {sel_row.get('relevance_score', 0):.1f} | **{sel_row.get('tier', '')}**")
c3.markdown(f"**Posted:** {sel_row.get('date_posted', '—')}")
target_cat = sel_row.get("target_category") or ""
c4.markdown(f"**Target list:** {target_cat.title() if target_cat else '—'}")

sal_min = sel_row.get("salary_min")
sal_max = sel_row.get("salary_max")
currency = sel_row.get("currency") or ""
if sal_min or sal_max:
    st.markdown(f"**Salary:** {currency} {sal_min or '?'} – {sal_max or '?'}")

if job_url:
    st.link_button("Open job posting ↗", job_url)

with st.expander("Full Description", expanded=True):
    desc = sel_row.get("description") or "No description available."
    st.text(desc)

# Applied toggle + notes
applied_val = int(sel_row.get("applied", 0))
col_a, col_b = st.columns([1, 3])
with col_a:
    if applied_val:
        if st.button("Undo Applied"):
            update_applied(db, job_url, 0)
            st.rerun()
    else:
        if st.button("Mark as Applied ✓"):
            update_applied(db, job_url, 1)
            st.rerun()

notes_key = f"notes_{sel_row.get('id', sel_idx)}"
if notes_key not in st.session_state:
    st.session_state[notes_key] = sel_row.get("notes", "") or ""

notes = st.text_area("Notes", value=st.session_state[notes_key], key=notes_key)
if st.button("Save Notes"):
    update_notes(db, job_url, notes)
    st.success("Saved!")
