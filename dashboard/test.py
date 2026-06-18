
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

print(df)