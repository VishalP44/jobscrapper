import sys
import os
import subprocess
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.db import init_db, get_jobs, update_applied, update_notes

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "jobs.db")

st.set_page_config(page_title="Job Scraper", layout="wide")
st.title("Job Scraper Dashboard")

db = init_db(DB_PATH)
df = get_jobs(db)

# --- Sidebar ---
st.sidebar.header("Filters")

all_tiers = ["Tier 1 — Apply today", "Tier 2 — Apply this week", "Tier 3 — Monitor", "Skip"]
selected_tiers = st.sidebar.multiselect("Tier", options=all_tiers, default=["Tier 1 — Apply today", "Tier 2 — Apply this week"])

all_sources = sorted(df["source"].dropna().unique().tolist()) if not df.empty else []
selected_sources = st.sidebar.multiselect("Source", options=all_sources, default=all_sources)

applied_filter = st.sidebar.radio("Applied status", ["All", "Not applied", "Applied"], index=1)

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

# --- Filter dataframe ---
view = df.copy()

if selected_tiers and not view.empty:
    view = view[view["tier"].isin(selected_tiers)]

if selected_sources and not view.empty:
    view = view[view["source"].isin(selected_sources)]

if not view.empty:
    if applied_filter == "Not applied":
        view = view[view["applied"] == 0]
    elif applied_filter == "Applied":
        view = view[view["applied"] == 1]

view = view.reset_index(drop=True)

# --- Metrics ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total jobs (DB)", len(df))
col2.metric("Tier 1", len(df[df["tier"] == "Tier 1 — Apply today"]) if not df.empty else 0)
col3.metric("Tier 2", len(df[df["tier"] == "Tier 2 — Apply this week"]) if not df.empty else 0)
col4.metric("Applied", int(df["applied"].sum()) if not df.empty else 0)

# --- Jobs table ---
st.subheader(f"Jobs ({len(view)} shown)")
st.caption("Click a row to see full details below.")

display_cols = ["tier", "relevance_score", "title", "company", "location",
                "date_posted", "source", "applied"]
display_cols = [c for c in display_cols if c in view.columns]

if view.empty:
    st.info("No jobs match the current filters.")
    st.stop()

event = st.dataframe(
    view[display_cols],
    use_container_width=True,
    on_select="rerun",
    selection_mode="single-row",
)

selected_rows = event.selection.rows

# --- Job detail panel ---
if not selected_rows:
    st.info("Click a row above to view the full job details.")
    st.stop()

sel_idx = selected_rows[0]
sel_row = view.iloc[sel_idx]
job_url = sel_row.get("job_url", "")

st.divider()
st.subheader(f"{sel_row.get('title', 'Job Detail')} — {sel_row.get('company', '')}")

c1, c2, c3 = st.columns(3)
c1.markdown(f"**Location:** {sel_row.get('location', '—')}")
c2.markdown(f"**Score:** {sel_row.get('relevance_score', 0):.1f} | **{sel_row.get('tier', '')}**")
c3.markdown(f"**Posted:** {sel_row.get('date_posted', '—')}")

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
