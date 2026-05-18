"""
SyrenBridge Platform  —  v4
Full Streamlit app wrapping both:
  • `databricks labs lakebridge analyze`   (Analyzer tab)
  • `databricks labs lakebridge transpile` (Transpiler tab)
Designed to be hosted on Databricks Apps.
"""

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from urllib import response
import zipfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.oozie_converter import workflow_to_json, parse_workflow, coordinator_to_dict, parse_coordinator,convert_xml, convert_oozie_file_set, _strip_annotation_keys
from modules.ssrs_converter import convert_ssrs_file_set as _convert_ssrs_file_set

from modules.databricks_service import DatabricksClient, get_databricks_credentials
from modules.sql_transpiler import run_hive_transpiler
from modules.llm_converter import LLMConverter, load_prompt

# ══════════════════════════════════════════════════════════════════════════════
# DATA — ANALYZER
# ══════════════════════════════════════════════════════════════════════════════

TECHNOLOGIES = [
    (0,  "ABInitio",                    "ETL"),
    (1,  "ADF",                         "ETL"),
    (2,  "Alteryx",                     "ETL"),
    (3,  "Athena",                      "SQL"),
    (4,  "BigQuery",                    "SQL"),
    (5,  "BODS",                        "ETL"),
    (6,  "Cloudera (Impala)",           "SQL"),
    (7,  "Datastage",                   "ETL"),
    (8,  "Greenplum",                   "SQL"),
    (9,  "Hive",                        "SQL"),
    (10, "IBM DB2",                     "SQL"),
    (11, "Informatica - Big Data Edition", "ETL"),
    (12, "Informatica - PC",            "ETL"),
    (13, "Informatica Cloud",           "ETL"),
    (14, "Jupyter Notebook",            "Code"),
    (15, "MS SQL Server",               "SQL"),
    (16, "Netezza",                     "SQL"),
    (17, "Oozie",                       "ETL"),
    (18, "Oracle",                      "SQL"),
    (19, "Oracle Data Integrator",      "ETL"),
    (20, "PentahoDI",                   "ETL"),
    (21, "PIG",                         "Code"),
    (22, "Presto",                      "SQL"),
    (23, "PySpark",                     "Code"),
    (24, "Redshift",                    "SQL"),
    (25, "SAPHANA - CalcViews",         "SQL"),
    (26, "SAS",                         "Code"),
    (27, "Snowflake",                   "SQL"),
    (28, "SPSS",                        "Code"),
    (29, "SQOOP",                       "ETL"),
    (30, "SSIS",                        "ETL"),
    (31, "SSRS",                        "ETL"),
    (32, "Synapse",                     "SQL"),
    (33, "Talend",                      "ETL"),
    (34, "Teradata",                    "SQL"),
    (35, "Vertica",                     "SQL"),
]

TECH_EXTENSIONS: dict[int, list[str]] = {
    0:  ["mp", "mf", "ab", "xml", "sh", "ksh"],
    1:  ["json", "xml"],
    2:  ["yxmd", "yxwz", "yxmc", "yxapp"],
    3:  ["sql", "ddl", "dml"],
    4:  ["sql", "ddl", "dml", "json"],
    5:  ["atl", "xml", "bods"],
    6:  ["sql", "ddl", "dml"],
    7:  ["dsx", "xml", "pjb"],
    8:  ["sql", "ddl", "dml"],
    9:  ["hql", "hive", "sql", "ddl", "dml"],
    10: ["sql", "ddl", "dml"],
    11: ["xml", "session", "wf", "m", "mplt", "lkp"],
    12: ["xml", "session", "wf", "m", "mplt", "lkp", "pc"],
    13: ["xml", "json", "session"],
    14: ["ipynb"],
    15: ["sql", "ddl", "dml", "proc", "view"],
    16: ["sql", "ddl", "dml", "nzb"],
    17: ["xml", "properties", "sh", "ksh"],
    18: ["sql", "ddl", "dml", "pls", "pks", "pkb", "prc", "fnc", "vw", "trg"],
    19: ["xml", "odixml", "sql"],
    20: ["ktr", "kjb", "xml"],
    21: ["pig", "txt"],
    22: ["sql", "ddl", "dml"],
    23: ["py", "ipynb", "scala", "java"],
    24: ["sql", "ddl", "dml"],
    25: ["xml", "hdbcalcview", "hdbprocedure", "hdbview", "analyticview", "attributeview"],
    26: ["sas", "sas7bdat"],
    27: ["sql", "ddl", "dml"],
    28: ["sps", "spv"],
    29: ["xml", "sh", "ksh", "properties"],
    30: ["dtsx", "xml"],
    31: ["rdl", "rdlc", "rsd"],
    32: ["sql", "ddl", "dml", "json"],
    33: ["item", "properties", "xml", "java"],
    34: ["sql", "bteq", "tdl", "tpt", "ddl", "dml"],
    35: ["sql", "ddl", "dml"],
}

CATEGORY_ICON = {"SQL": "SQL", "ETL": "ETL", "Code": "Code"}

# ══════════════════════════════════════════════════════════════════════════════
# DATA — TRANSPILER
# ══════════════════════════════════════════════════════════════════════════════

TRANSPILER_DIALECTS: dict[str, dict] = {
    "DataStage":           {"cli": "datastage",         "exts": ["dsx", "xml", "pjb"]},
    "HiveSQL (Cloudera)":  {"cli": "hive",              "exts": ["hql", "hive", "sql", "ddl", "dml"], "custom": True},
    "Informatica":         {"cli": "informatica",        "exts": ["xml", "session", "wf", "m", "mplt", "lkp"]},
    "Informatica Cloud":   {"cli": "informatica_cloud",  "exts": ["xml", "json", "session"]},
    "MS SQL Server":       {"cli": "mssql",              "exts": ["sql", "ddl", "dml", "proc", "view"]},
    "Netezza":             {"cli": "netezza",            "exts": ["sql", "ddl", "dml", "nzb"]},
    "Oracle":              {"cli": "oracle",             "exts": ["sql", "ddl", "dml", "pls", "pks", "pkb", "prc", "fnc", "vw", "trg"]},
    "Snowflake":           {"cli": "snowflake",          "exts": ["sql", "ddl", "dml"]},
    "SSIS":                {"cli": "ssis",               "exts": ["dtsx", "xml"],              "sparksql_only": True},
    "SSRS (Reports)":      {"cli": "ssrs",               "exts": ["rdl", "rdlc", "rsd"],       "ssrs": True},
    "Synapse":             {"cli": "synapse",            "exts": ["sql", "ddl", "dml", "json"]},
    "Teradata":            {"cli": "teradata",           "exts": ["sql", "bteq", "tdl", "tpt", "ddl", "dml"]},
    "Oozie (Workflow)":    {"cli": "oozie",              "exts": ["xml"],                               "oozie": True},
}

TRANSPILER_TARGETS = {
    "PySpark  (Python notebooks / scripts)": "PYSPARK",
    "SparkSQL  (SQL-compatible Spark)":       "SPARKSQL",
}

# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG  (must be first Streamlit call)
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="SyrenBridge — Migration Platform",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════

import base64 as _b64
_LOGO_B64 = ""
_logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
if os.path.exists(_logo_path):
    with open(_logo_path, "rb") as _lf:
        _LOGO_B64 = _b64.b64encode(_lf.read()).decode()

st.markdown("""
<style>
/* ── Google Fonts ─────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── CSS variables ────────────────────────────────────────────────────────── */
:root {
    --bg:          #09090e;
    --orange:      #FF3621;
    --orange-dim:  rgba(255,54,33,0.15);
    --indigo:      #6366f1;
    --cyan:        #06b6d4;
    --glass-bg:    rgba(255,255,255,0.03);
    --glass-bdr:   rgba(255,255,255,0.08);
    --text-pri:    #f1f5f9;
    --text-muted:  #94a3b8;
    --nav-h:       52px;
}

/* ── Base ─────────────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    color: var(--text-pri);
}

/* ── App background ───────────────────────────────────────────────────────── */
.stApp {
    background-color: var(--bg) !important;
}

/* Radial gradient orbs */
.stApp::before {
    content: '';
    position: fixed; inset: 0; pointer-events: none; z-index: 0;
    background:
        radial-gradient(ellipse 700px 500px at 15% 10%,  rgba(255,54,33,0.10)  0%, transparent 70%),
        radial-gradient(ellipse 600px 500px at 85% 20%,  rgba(99,102,241,0.08) 0%, transparent 70%),
        radial-gradient(ellipse 500px 400px at 50% 85%,  rgba(6,182,212,0.06)  0%, transparent 70%);
}

/* ── Hide Streamlit chrome ────────────────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding-top: calc(var(--nav-h) + 1.75rem) !important;
    padding-bottom: 3rem;
    max-width: 1100px;
    position: relative; z-index: 1;
}

/* ── Hide sidebar entirely ────────────────────────────────────────────────── */
section[data-testid="stSidebar"],
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"] {
    display: none !important;
    visibility: hidden !important;
}

/* ── Top nav ──────────────────────────────────────────────────────────────── */
#sb-nav {
    position: fixed; top: 0; left: 0; right: 0;
    height: var(--nav-h);
    background: rgba(9,9,14,0.88);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--glass-bdr);
    z-index: 9999;
    display: flex; align-items: center;
    padding: 0 24px; gap: 8px;
    font-family: 'Inter', sans-serif;
}
#sb-nav .sb-logo {
    display: flex; align-items: center; gap: 10px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 999px;
    padding: 4px 14px 4px 6px;
    margin-right: 16px;
    text-decoration: none; cursor: pointer;
}
#sb-nav .sb-logo img { height: 28px; width: auto; border-radius: 4px; }
#sb-nav .sb-logo span {
    font-size: 13px; font-weight: 700;
    color: #fff; letter-spacing: 0.02em;
}
#sb-nav .sb-divider {
    width: 1px; height: 20px;
    background: var(--glass-bdr); margin: 0 8px;
}
#sb-nav .sb-links { display: flex; align-items: center; gap: 2px; }
#sb-nav .sb-link {
    padding: 6px 14px; border-radius: 8px;
    font-size: 13px; font-weight: 500;
    color: var(--text-muted);
    text-decoration: none; cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.15s;
}
#sb-nav .sb-link:hover {
    color: var(--text-pri);
    background: rgba(255,255,255,0.05);
}
#sb-nav .sb-link.active {
    color: var(--orange);
    background: rgba(255,54,33,0.08);
    border-color: rgba(255,54,33,0.2);
}
#sb-nav .sb-spacer { flex: 1; }
#sb-nav .sb-badge {
    font-size: 11px; font-weight: 600;
    color: var(--text-muted);
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--glass-bdr);
    border-radius: 6px; padding: 3px 9px;
    letter-spacing: 0.03em;
}

/* ── fadeUp animation ─────────────────────────────────────────────────────── */
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* ── Page header ──────────────────────────────────────────────────────────── */
.page-hdr {
    display: flex; align-items: flex-start; gap: 0.9rem;
    border-bottom: 1px solid var(--glass-bdr);
    padding-bottom: 1.25rem; margin-bottom: 2rem;
    animation: fadeUp 0.4s ease both;
}
.page-hdr-icon {
    width: 44px; height: 44px; border-radius: 10px;
    background: var(--glass-bg);
    border: 1px solid var(--glass-bdr);
    display: flex; align-items: center;
    justify-content: center; font-size: 1.2rem; flex-shrink: 0;
}
.page-hdr h1 {
    font-size: 1.45rem; font-weight: 800; color: #fff;
    margin: 0 0 0.1rem; letter-spacing: -0.025em; line-height: 1.2;
}
.page-hdr p { color: var(--text-muted); font-size: 0.82rem; margin: 0; }

/* ── Cards ────────────────────────────────────────────────────────────────── */
.card {
    background: var(--glass-bg);
    border: 1px solid var(--glass-bdr);
    border-radius: 14px; padding: 1.4rem 1.6rem;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    animation: fadeUp 0.45s ease both;
}
.card-title {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--text-muted); margin-bottom: 1rem;
    display: flex; align-items: center; gap: 0.4rem;
}

/* ── Step indicator ───────────────────────────────────────────────────────── */
.step-num {
    width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.78rem; font-weight: 700;
    background: var(--orange); color: white; margin-right: 0.45rem;
}
.step-num.teal { background: #0f766e; }

/* ── Extension tags ───────────────────────────────────────────────────────── */
.ext-wrap { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 0.5rem; }
.ext-tag {
    background: rgba(255,255,255,0.04); color: var(--text-muted);
    border: 1px solid var(--glass-bdr); border-radius: 4px;
    padding: 2px 7px; font-size: 0.72rem; font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
}
.ext-tag.teal { background: rgba(6,182,212,0.08); color: #67e8f9; border-color: rgba(6,182,212,0.2); }

/* ── Buttons ──────────────────────────────────────────────────────────────── */
div[data-testid="stButton"] button {
    background: var(--orange) !important; color: #fff !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 0.92rem !important;
    padding: 0.6rem 2rem !important;
    box-shadow: 0 0 20px rgba(255,54,33,0.25) !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stButton"] button:hover {
    background: #e8301d !important;
    box-shadow: 0 0 32px rgba(255,54,33,0.4) !important;
    transform: translateY(-1px) !important;
}
div[data-testid="stButton"] button:disabled {
    background: rgba(255,255,255,0.06) !important;
    color: var(--text-muted) !important;
    box-shadow: none !important; transform: none !important;
}

/* ── Metric cards ─────────────────────────────────────────────────────────── */
.metric-card {
    background: var(--glass-bg);
    border: 1px solid var(--glass-bdr); border-radius: 14px;
    padding: 1.25rem 1rem; text-align: center;
    backdrop-filter: blur(12px);
    animation: fadeUp 0.5s ease both;
}
.metric-icon { font-size: 1.4rem; margin-bottom: 0.4rem; }
.metric-val { font-size: 2rem; font-weight: 800; line-height: 1; color: #fff; font-family: 'JetBrains Mono', monospace; }
.metric-lbl {
    font-size: 0.68rem; font-weight: 700; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 0.07em; margin-top: 0.35rem;
}

/* ── Results header ───────────────────────────────────────────────────────── */
.results-header { display: flex; align-items: center; margin-bottom: 1.25rem; }
.results-title {
    font-size: 1.1rem; font-weight: 700; color: #fff;
    display: flex; align-items: center; gap: 0.5rem;
}
.success-pill {
    background: rgba(34,197,94,0.12); color: #4ade80;
    border: 1px solid rgba(34,197,94,0.2);
    border-radius: 20px; padding: 2px 10px;
    font-size: 0.73rem; font-weight: 600;
}

/* ── Section divider ──────────────────────────────────────────────────────── */
.section-sep { border: none; border-top: 1px solid var(--glass-bdr); margin: 1.75rem 0; }

/* ── File tree / output block ─────────────────────────────────────────────── */
.file-tree {
    background: rgba(0,0,0,0.5); color: #e2e8f0; border-radius: 10px;
    padding: 1rem 1.25rem; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
    line-height: 1.7; max-height: 360px; overflow-y: auto;
    width: 100%; overflow-x: auto; white-space: nowrap; word-break: break-word;
    border: 1px solid var(--glass-bdr);
}
.file-tree .dir  { color: var(--orange); font-weight: 600; }
.file-tree .file { color: #86efac; }
.file-tree .meta { color: #475569; }

.output-block {
    background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.06); border-radius: 0.85rem;
    padding: 0.85rem; max-height: 42vh; overflow-y: auto;
    white-space: pre-wrap; word-break: break-word;
    color: var(--text-pri); font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
}

/* ── Info box ─────────────────────────────────────────────────────────────── */
.info-box {
    background: var(--glass-bg); border: 1px solid var(--glass-bdr); border-radius: 10px;
    padding: 0.85rem 1.1rem; margin-top: 0.5rem;
}
.info-box strong { color: #fff; }
.info-box p { color: var(--text-muted); font-size: 0.85rem; margin: 0.2rem 0 0; }

/* ── Dark Streamlit widgets ───────────────────────────────────────────────── */
.stSelectbox > div > div,
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
    background: rgba(255,255,255,0.04) !important;
    border-color: var(--glass-bdr) !important;
    color: #f1f5f9 !important;
    border-radius: 8px !important;
}
.stSelectbox > div > div:focus-within,
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: rgba(255,54,33,0.4) !important;
    box-shadow: 0 0 0 1px rgba(255,54,33,0.25) !important;
}
.stSelectbox div[data-baseweb="select"] span { color: #f1f5f9 !important; }
.stSelectbox svg { fill: var(--text-muted) !important; }
.stRadio label { color: var(--text-pri) !important; }
div[data-testid="stFileUploader"] {
    background: var(--glass-bg) !important;
    border-color: var(--glass-bdr) !important;
    border-radius: 10px !important;
}
div[data-testid="stFileUploader"] span { color: var(--text-muted) !important; }
.streamlit-expanderHeader {
    background: var(--glass-bg) !important;
    color: var(--text-pri) !important;
    border-color: var(--glass-bdr) !important;
    border-radius: 8px !important;
}
.streamlit-expanderContent {
    background: rgba(0,0,0,0.2) !important;
    border-color: var(--glass-bdr) !important;
}
.stCheckbox label { color: var(--text-pri) !important; }
.stCaption { color: var(--text-muted) !important; }
div[data-testid="stTabs"] button {
    color: var(--text-muted) !important;
    background: transparent !important;
    border-color: transparent !important;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
    color: var(--text-pri) !important;
    border-bottom-color: var(--orange) !important;
}
.stDataFrame { filter: invert(0.85) hue-rotate(180deg); }
div[data-testid="stAlert"] { border-radius: 10px !important; }
input::placeholder, textarea::placeholder { color: #475569 !important; }
p, li, span, label { color: var(--text-pri); }
h1, h2, h3, h4, h5, h6 { color: #fff; }
strong { color: #fff; }
hr { border-color: var(--glass-bdr) !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — SHARED
# ══════════════════════════════════════════════════════════════════════════════

def save_uploaded_files(files: list, is_zip: bool) -> str:
    src = tempfile.mkdtemp(prefix="lb_src_")
    for uf in files:
        dest = os.path.join(src, uf.name)
        with open(dest, "wb") as fh:
            fh.write(uf.getbuffer())
        if is_zip and uf.name.lower().endswith(".zip"):
            with zipfile.ZipFile(dest, "r") as zf:
                zf.extractall(os.path.join(src, Path(uf.name).stem))
            os.remove(dest)
    return src


def count_files(directory: str) -> tuple[int, int]:
    files = [p for p in Path(directory).rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def zip_directory(directory: str) -> bytes:
    """Zip a directory and return bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(Path(directory).rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(directory))
    return buf.getvalue()


def _workspace_language_for_path(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".py":
        return "PYTHON"
    if ext == ".sql":
        return "SQL"
    if ext == ".scala":
        return "SCALA"
    if ext == ".java":
        return "JAVA"
    if ext in {".json", ".yaml", ".yml", ".txt", ".md", ".csv"}:
        return "PYTHON"
    return "PYTHON"

def set_databricks_env(host: str, token: str):
    host = (host or "").strip()
    token = (token or "").strip()

    if not host or not token:
        raise ValueError("Both Databricks Host and PAT are required")

    os.environ["DATABRICKS_HOST"] = host
    os.environ["DATABRICKS_TOKEN"] = token


def set_llm_env(endpoint: str, api_key: str):
    """Set LLM credentials in environment variables."""
    endpoint = (endpoint or "").strip()
    api_key = (api_key or "").strip()

    if not endpoint or not api_key:
        raise ValueError("Both LLM Endpoint and API Key are required")

    os.environ["LLM_ENDPOINT"] = endpoint
    os.environ["LLM_API_KEY"] = api_key


def test_llm_connection(endpoint: str, api_key: str) -> tuple[bool, str]:
    endpoint = endpoint.strip()
    api_key = api_key.strip()

    if not (endpoint and api_key):
        return False, "Both LLM Endpoint and API Key are required"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # minimal valid payload
    payload = {
        "messages": [
            {"role": "user", "content": "Hello"}
        ],
        "max_tokens": 5,
        "temperature": 0
    }

    try:
        import requests

        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()

            # basic validation
            if "choices" in data:
                return True, "LLM connection successful"
            else:
                return False, "LLM responded but invalid format"

        elif response.status_code == 401:
            return False, "Invalid API key"

        elif response.status_code == 404:
            return False, "Invalid endpoint URL"

        else:
            return False, f"LLM error: {response.status_code} - {response.text}"

    except Exception as e:
        return False, f"Connection failed: {str(e)}"


def clear_databricks_credentials():
    """Clear Databricks credentials from environment and session state."""
    # Remove from environment
    os.environ.pop("DATABRICKS_HOST", None)
    os.environ.pop("DATABRICKS_TOKEN", None)
    
    # Remove from session state
    st.session_state.pop("sb_db_host", None)
    st.session_state.pop("sb_db_token", None)


def clear_llm_credentials():
    """Clear LLM credentials from environment and session state."""
    # Remove from environment
    os.environ.pop("LLM_ENDPOINT", None)
    os.environ.pop("LLM_API_KEY", None)
    
    # Remove from session state
    st.session_state.pop("sb_llm_endpoint", None)
    st.session_state.pop("sb_llm_api_key", None)

def _ensure_workspace_folder(client: DatabricksClient, folder_path: str) -> None:
    folder_path = folder_path.strip()
    if not folder_path:
        return
    if not folder_path.startswith("/"):
        folder_path = "/" + folder_path

    parts = [p for p in folder_path.split("/") if p]
    current = ""
    for part in parts:
        current += "/" + part
        client.create_folder(current)


def upload_directory_to_workspace(out_dir: str, workspace_path: str) -> tuple[bool, list[str]]:
    client = DatabricksClient.from_app_context()
    workspace_path = workspace_path.strip()
    if not workspace_path:
        return False, ["Workspace destination path is required."]
    if not workspace_path.startswith("/"):
        workspace_path = "/" + workspace_path

    errors: list[str] = []
    for file_path in sorted(Path(out_dir).rglob("*")):
        if not file_path.is_file():
            continue

        relative_path = file_path.relative_to(out_dir).as_posix()
        target_path = f"{workspace_path.rstrip('/')}/{relative_path}"
        parent = os.path.dirname(target_path)
        if parent:
            _ensure_workspace_folder(client, parent)

        content = file_path.read_text(encoding="utf-8", errors="replace")
        response = client.write_file(
            path=target_path,
            content=content,
            language=_workspace_language_for_path(file_path.name),
        )
        if isinstance(response, dict) and response.get("error"):
            errors.append(f"{target_path}: {response['error']}")

    if errors:
        return False, errors
    return True, []


def clear_transpile_output_state() -> None:
    existing = st.session_state.pop("tp_out_dir", None)
    st.session_state.pop("tp_output_info", None)
    if existing and os.path.exists(existing):
        shutil.rmtree(existing, ignore_errors=True)


def clear_databricks_workspace_selection_state() -> None:
    for key in [
        "ws_selected_files",
        "ws_items",
        "ws_path",
        "last_loaded_path",
        "source_mode",
        "tp_ws_selected_files",
        "tp_ws_items",
        "tp_ws_path",
        "tp_last_loaded_path",
        "tp_source_mode",
    ]:
        st.session_state.pop(key, None)


def store_transpile_output_state(out_dir: str, info: dict) -> None:
    st.session_state["tp_out_dir"] = out_dir
    st.session_state["tp_output_info"] = info


def extract_llm_enhancement_counts(stdout: str) -> tuple[int, int, int] | None:
    match = re.search(
        r"LLM enhancement:\s*(\d+)\s+file\(s\)\s+sent,\s+(\d+)\s+statement\(s\)\s+replaced(?:,\s+(\d+)\s+failure\(s\))?",
        stdout or "",
    )
    if not match:
        return None

    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def extract_llm_enhancement_summary(stdout: str) -> str | None:
    counts = extract_llm_enhancement_counts(stdout)
    if not counts:
        return None

    files_sent, statements_replaced, failures = counts

    if files_sent == 0:
        return "LLM enhancement skipped - no problematic statements required LLM review"

    file_label = "file" if files_sent == 1 else "files"
    summary = f"LLM enhancement completed for {files_sent} {file_label} with {statements_replaced} statement(s)"
    if failures:
        summary += f" with {failures} failure(s)"
    return summary


def render_transpile_metric_cards(
    n_src: int,
    n_out: int,
    elapsed: float,
    llm_files_sent: int = 0,
    llm_statements_replaced: int = 0,
) -> None:
    metric_columns = st.columns(4 if llm_files_sent else 3)
    with metric_columns[0]:
        st.markdown(f"""
        <div class="metric-card">

            <div class="metric-val">{n_src}</div>
            <div class="metric-lbl">Files Processed</div>
        </div>""", unsafe_allow_html=True)
    with metric_columns[1]:
        st.markdown(f"""
        <div class="metric-card">

            <div class="metric-val">{n_out}</div>
            <div class="metric-lbl">Files Generated</div>
        </div>""", unsafe_allow_html=True)
    if llm_files_sent:
        with metric_columns[2]:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon">LLM</div>
                <div class="metric-val">{llm_files_sent}</div>
                <div class="metric-lbl">LLM Enhanced ({llm_statements_replaced} statement{'s' if llm_statements_replaced != 1 else ''})</div>
            </div>""", unsafe_allow_html=True)
    with metric_columns[-1]:
        st.markdown(f"""
        <div class="metric-card">

            <div class="metric-val">{elapsed:.1f}s</div>
            <div class="metric-lbl">Time Taken</div>
        </div>""", unsafe_allow_html=True)


def render_oozie_workflow_create_section(tp_out_dir: str, key_suffix: str) -> None:
    json_files = sorted(
        [p for p in Path(tp_out_dir).rglob("*.json")],
        key=lambda p: str(p),
    )
    if not json_files:
        st.warning("No Databricks Workflow JSON was found to create.")
        return

    selected_file = json_files[0]
    if len(json_files) > 1:
        file_labels = [str(p.relative_to(tp_out_dir)) for p in json_files]
        selected_label = st.selectbox(
            "Workflow JSON",
            options=file_labels,
            key=f"create_oozie_workflow_file_{key_suffix}",
        )
        selected_file = json_files[file_labels.index(selected_label)]

    col1, col2 = st.columns([1, 2])
    with col1:
        create_clicked = st.button(
            "Create Databricks Workflow",
            key=f"create_oozie_workflow_{key_suffix}",
            width='stretch',
        )

    if not create_clicked:
        with col2:
            st.caption(f"Ready to create from `{selected_file.name}`.")
        return

    with col2:
        with st.spinner("Creating workflow..."):
            try:
                host, token = get_databricks_credentials()
                if not host or not token:
                    st.error(
                        "Databricks credentials not found. Go to Settings and provide "
                        "the workspace URL and personal access token."
                    )
                    return

                job_payload = json.loads(selected_file.read_text(encoding="utf-8"))
                # ==============================
                # SHOW PAYLOAD
                # ==============================
                st.subheader("Job Payload Sent to Databricks")
                # st.json(job_payload)
                dbx = DatabricksClient.from_app_context()
                response = dbx.create_job(job_payload)
                st.subheader("Databricks API Response")
                # st.json(response)

                if "job_id" in response:
                    job_id = response["job_id"]
                    st.success(f"Workflow created. Job ID: {job_id}")
                    st.markdown(f"[Open Job]({dbx.workspace_url}/#job/{job_id})")

                    # Replace sentinel "{{job_id:<name>}}" in coordinator JSONs
                    wf_name = job_payload.get("name", "")
                    sentinel = f'"{{{{job_id:{wf_name}}}}}"'
                    patched = []
                    for other_file in json_files:
                        if other_file == selected_file:
                            continue
                        raw = other_file.read_text(encoding="utf-8")
                        if sentinel in raw:
                            other_file.write_text(
                                raw.replace(sentinel, str(job_id)), encoding="utf-8"
                            )
                            patched.append(other_file.name)
                    if patched:
                        st.info(
                            f"Updated coordinator job(s) with real job_id {job_id}: "
                            + ", ".join(patched)
                        )
                    return

                st.error(f"Failed to create workflow: {response.get('error', 'Unknown error')}")
            except json.JSONDecodeError as exc:
                st.error(f"Workflow JSON is invalid: {exc}")
            except Exception as exc:
                st.error(f"Deployment error: {exc}")


def render_transpile_output_section() -> None:
    tp_out_dir = st.session_state.get("tp_out_dir")
    info = st.session_state.get("tp_output_info", {})
    if not tp_out_dir or not os.path.exists(tp_out_dir):
        return

    n_out = info.get("n_out", 0)
    if n_out == 0:
        return

    selected_dialect_name = info.get("selected_dialect_name", "Transpiler")
    selected_target_label = info.get("selected_target_label", "Target")
    dialect_cli = info.get("dialect_cli", "output")
    target_cli = info.get("target_cli", "output")
    n_src = info.get("n_src", 0)
    b_out = info.get("b_out", 0)
    elapsed = info.get("elapsed", 0.0)

    st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)

    if info.get("is_oozie"):
        oozie_links = info.get("oozie_links", [])
        if oozie_links:
            st.markdown("**Coordinator → Workflow Links**")
            for lk in oozie_links:
                if lk["workflow"]:
                    st.success(f"{lk['coordinator']} → linked to **{lk['workflow']}** via `run_job_task`")
                else:
                    st.warning(f"{lk['coordinator']} → no workflow matched — add `run_job_task` manually")
        st.markdown("**Oozie Conversion Notes**")
        with st.expander("ℹ️ View details"):
            st.markdown("""
        - **Workflow jobs** are created as independent Databricks jobs with a full task graph.
        - **Coordinator jobs** trigger workflow jobs via `run_job_task`. If a matching workflow XML was uploaded, the `job_id` sentinel (`{{job_id:<name>}}`) is **automatically replaced** with the real Databricks job ID once you create the workflow job — create workflow jobs first, then coordinator jobs.
        - **Schedule** is set to `PAUSED` by default — activate after verifying the job in the Databricks Workflow editor.
        - **EL expressions** (`${variable}`) are preserved as-is — replace them with Databricks job parameters or widgets.
        - **Bundle workflows** are not supported — convert each coordinator individually.
        - **Parallel execution (fork/join)** may require manual validation to ensure correct task dependencies.
        - **Error handling** logic is simplified — validate failure paths and retry behavior.
        - **Cluster config** is not automatically optimized — review node type, Spark version, and worker count.
        """)
        render_oozie_workflow_create_section(tp_out_dir, "main")

    st.markdown("""
    <div class="results-header">
        <div class="results-title">
            Transpiled Output <span class="success-pill">Ready</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    render_transpile_metrics(
        n_src=n_src,
        n_out=n_out,
        elapsed=elapsed,
        llm_counts=(
            info.get("llm_files_sent", 0),
            info.get("llm_statements_replaced", 0)
        )
    )
    
    zip_bytes = zip_directory(tp_out_dir)
    zip_name = f"transpiled_{dialect_cli}_{target_cli.lower()}.zip"
    dl_col, info_col = st.columns([1, 2])
    with dl_col:
        st.download_button(
            label="Download All Output Files",
            data=zip_bytes,
            file_name=zip_name,
            mime="application/zip",
            key="tp_download_all_output_helper",
            width='stretch',
        )
    with info_col:
        st.markdown(f"""
        <div class="info-box">
            <strong>{zip_name}</strong>
            <p>{n_out} converted file(s) · {b_out/1024:.1f} KB total</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

    st.session_state["tp_upload_dest"] = st.session_state.get("tp_upload_dest", "/Shared/transpiler_output")
    upload_dest = st.text_input(
        "Upload output to Databricks workspace folder",
        value=st.session_state["tp_upload_dest"],
        key="tp_upload_dest",
        help="Enter the target Databricks workspace folder where transpiled files will be uploaded.",
    )
    if upload_dest and not upload_dest.startswith("/"):
        upload_dest = "/" + upload_dest
        st.session_state["tp_upload_dest"] = upload_dest

    if st.button("Upload All Output Files to Databricks", key="tp_upload_output", width='stretch'):
        try:
            ok, upload_errors = upload_directory_to_workspace(tp_out_dir, upload_dest)
            if ok:
                st.success(f"✅ Uploaded {n_out} files to {upload_dest}")
            else:
                st.error("Upload failed. See details below.")
                for msg in upload_errors:
                    st.write(f"- {msg}")
        except Exception as e:
            st.error(f"Upload error: {e}")

    st.markdown("**Output File Tree**")
    tree_html, _, _ = build_file_tree_html(tp_out_dir)
    st.markdown(f'<div class="file-tree">{tree_html}</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

    output_files = sorted(
        [p for p in Path(tp_out_dir).rglob("*") if p.is_file() and p.name != "transpile_errors.log"],
        key=lambda p: str(p)
    )
    if output_files:
        st.markdown("**File Preview**")
        preview_tabs = st.tabs([p.name for p in output_files[:20]])
        for tab, fp in zip(preview_tabs, output_files[:20]):
            with tab:
                try:
                    content = fp.read_text(encoding="utf-8", errors="replace")
                    _lang_map = {".py": "python", ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".xml": "xml"}
                    lang = _lang_map.get(fp.suffix.lower(), "sql")
                    st.code(content, language=lang)
                except Exception as e:
                    st.warning(f"Could not read file: {e}")
        if len(output_files) > 20:
            st.caption(f"Showing first 20 of {len(output_files)} files. Download the ZIP to view all.")

    tp_err_file = os.path.join(tp_out_dir, "transpile_errors.log")
    if os.path.exists(tp_err_file):
        err_content = Path(tp_err_file).read_text(encoding="utf-8", errors="replace").strip()
        if err_content:
            with st.expander("Transpilation error log", expanded=False):
                st.code(err_content, language="text")
        else:
            st.success("✅ No transpilation errors logged.")


def is_valid_excel(path):
    try:
        import pandas as pd
        pd.ExcelFile(path)
        return True
    except Exception:
        return False


def make_widget_key(prefix: str, path: str) -> str:
    normalized = path.strip("/").replace("/", "_").replace(" ", "_")
    return f"{prefix}_{normalized}"


def fetch_workspace_files_to_local(paths):
    dbx = DatabricksClient.from_app_context()
    temp_dir = tempfile.mkdtemp(prefix="ws_src_")

    for p in paths:
        content = dbx.get_file_content(p)

        if isinstance(content, dict):  # error
            continue

        filename = os.path.basename(p)
        with open(os.path.join(temp_dir, filename), "w", encoding="utf-8") as f:
            f.write(content)

    return temp_dir

# ══════════════════════════════════════════════════════════════════════════════
# DATABRICKS CREDENTIALS HELPER
# ══════════════════════════════════════════════════════════════════════════════



def test_databricks_workspace_connection(host: str, token: str) -> tuple[bool, str]:
    """Validate the provided Databricks host and PAT by listing workspace files."""
    host = host.strip()
    token = token.strip()

    if not (host and token):
        return False, "Host and PAT are required for workspace validation."

    try:
        client = DatabricksClient(host, token)
        items = client.list_workspace_items("/")
        if isinstance(items, dict) and items.get("error"):
            return False, items["error"]
        count = len(items) if isinstance(items, list) else 0
        return True, f"Workspace validated successfully. Listed {count} item(s) at the root path."
    except Exception as e:
        return False, str(e)


def test_databricks_cli_connection() -> tuple[bool, str]:
    env = os.environ.copy()
    if not env.get("DATABRICKS_HOST") or not env.get("DATABRICKS_TOKEN"):
        return False, "Host and PAT are required to test the Databricks CLI connection."

    try:
        result = subprocess.run(
            ["databricks", "auth", "status"],
            capture_output=True, text=True, timeout=30, env=env,
        )
        if result.returncode == 0:
            return True, result.stdout.strip() or "Databricks CLI is authenticated."
        return False, result.stderr.strip() or result.stdout.strip() or "Unknown CLI error."
    except FileNotFoundError:
        return False, (
            "`databricks` CLI not found in PATH. Install it:\n"
            "curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh\n"
            "databricks labs install lakebridge"
        )
    except subprocess.TimeoutExpired:
        return False, "Databricks CLI connection test timed out after 30 seconds."


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — ANALYZER
# ══════════════════════════════════════════════════════════════════════════════

def run_lakebridge(src: str, out: str, tech: int) -> tuple[bool, str, str]:
    payload = f"{src}\n{out}\n{tech}\n"
    env = os.environ.copy()
    if not env.get("DATABRICKS_HOST") or not env.get("DATABRICKS_TOKEN"):
        return False, "", "Host and PAT are required to run Lakebridge. Set them in Settings or via environment variables."

    # Force PAT auth so the SDK doesn't fall back to a stale databricks-cli OAuth session
    env["DATABRICKS_AUTH_TYPE"] = "pat"

    try:
        proc = subprocess.run(
            ["databricks", "labs", "lakebridge", "analyze"],
            input=payload, capture_output=True, text=True,
            timeout=600, env=env,
        )
        return proc.returncode == 0 or os.path.exists(out), proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Analysis timed out after 10 minutes."
    except FileNotFoundError:
        return False, "", (
            "`databricks` CLI not found in PATH.\n"
            "Install it:\n"
            "  curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh\n"
            "  databricks labs install lakebridge"
        )
    except Exception as e:
        return False, "", str(e)


def read_excel_sheets(path: str) -> dict[str, pd.DataFrame]:
    sheets: dict[str, pd.DataFrame] = {}
    try:
        xl = pd.ExcelFile(path)
        for name in xl.sheet_names:
            try:
                sheets[name] = xl.parse(name)
            except Exception as e:
                sheets[name] = pd.DataFrame({"Parse error": [str(e)]})
    except Exception as e:
        sheets["Error"] = pd.DataFrame({"Error": [str(e)]})
    return sheets


def extract_metrics(sheets: dict[str, pd.DataFrame]) -> dict:
    metrics: dict[str, int] = {}
    for sheet_name, df in sheets.items():
        if df.empty:
            continue
        lower_cols = {str(c).strip().lower(): c for c in df.columns}

        if "summary" in sheet_name.lower():
            for key in ("total_files", "file_count", "files", "total files"):
                if key in lower_cols:
                    try:
                        metrics["Files Analyzed"] = int(df[lower_cols[key]].dropna().sum())
                    except Exception:
                        pass

        if "function" in sheet_name.lower() and "xref" not in sheet_name.lower() and "by script" not in sheet_name.lower():
            try:
                metrics["Unique Functions"] = len(df)
            except Exception:
                pass

        if "sql program" in sheet_name.lower():
            try:
                metrics["SQL Programs"] = len(df)
            except Exception:
                pass

        if "referenced object" in sheet_name.lower():
            try:
                metrics["Referenced Objects"] = len(df)
            except Exception:
                pass

        for key in ("transformation_count", "transformations"):
            if key in lower_cols:
                try:
                    metrics["Transformations"] = int(df[lower_cols[key]].dropna().sum())
                except Exception:
                    pass

    return metrics


def build_function_chart(sheets: dict[str, pd.DataFrame]):
    target_sheet = next(
        (name for name in sheets if "function" in name.lower()
         and "xref" not in name.lower() and "by script" not in name.lower()),
        None,
    )
    if not target_sheet:
        return None
    df = sheets[target_sheet]
    if df.empty or len(df.columns) < 1:
        return None
    name_col = next(
        (c for c in df.columns if any(k in c.lower() for k in ("function", "name", "object"))),
        df.columns[0],
    )
    count_col = next(
        (c for c in df.columns if any(k in c.lower() for k in ("count", "usage", "calls", "occurrences", "frequency"))),
        None,
    )
    if count_col:
        plot_df = df[[name_col, count_col]].dropna().rename(columns={name_col: "Function", count_col: "Count"})
        try:
            plot_df["Count"] = pd.to_numeric(plot_df["Count"], errors="coerce")
            plot_df = plot_df.dropna().sort_values("Count", ascending=False).head(15)
        except Exception:
            return None
    else:
        counts = df[name_col].dropna().value_counts().head(15).reset_index()
        counts.columns = ["Function", "Count"]
        plot_df = counts
    if plot_df.empty:
        return None
    return (
        alt.Chart(plot_df)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("Count:Q", axis=alt.Axis(title="Usage Count", grid=False)),
            y=alt.Y("Function:N", sort="-x", axis=alt.Axis(title=None, labelLimit=220)),
            color=alt.value("#FF3621"),
            tooltip=["Function", "Count"],
        )
        .properties(height=max(260, len(plot_df) * 28))
        .configure_axis(labelFontSize=12, titleFontSize=12)
        .configure_view(strokeWidth=0)
    )


def build_category_chart(sheets: dict[str, pd.DataFrame]):
    target = next((n for n in sheets if "categor" in n.lower()), None)
    if not target:
        return None
    df = sheets[target]
    if df.empty:
        return None
    cat_col = next((c for c in df.columns if "categor" in c.lower() or "type" in c.lower()), df.columns[0] if len(df.columns) else None)
    cnt_col = next((c for c in df.columns if "count" in c.lower() or "total" in c.lower()), None)
    if not cat_col:
        return None
    if cnt_col:
        plot_df = df[[cat_col, cnt_col]].dropna().rename(columns={cat_col: "Category", cnt_col: "Count"})
        try:
            plot_df["Count"] = pd.to_numeric(plot_df["Count"], errors="coerce").dropna()
        except Exception:
            return None
    else:
        plot_df = df[cat_col].dropna().value_counts().reset_index()
        plot_df.columns = ["Category", "Count"]
    if plot_df.empty:
        return None
    return (
        alt.Chart(plot_df.head(12))
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("Count:Q", axis=alt.Axis(title="Count", grid=False)),
            y=alt.Y("Category:N", sort="-x", axis=alt.Axis(title=None, labelLimit=240)),
            color=alt.value("#6366f1"),
            tooltip=["Category", "Count"],
        )
        .properties(height=max(180, len(plot_df.head(12)) * 28))
        .configure_axis(labelFontSize=12, titleFontSize=12)
        .configure_view(strokeWidth=0)
    )


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — TRANSPILER
# ══════════════════════════════════════════════════════════════════════════════

def run_transpiler(
    src_dir: str,
    out_dir: str,
    err_file: str,
    dialect: str,
    target: str,
    catalog: str = "",
    schema: str = "",
    skip_validation: bool = True,
) -> tuple[bool, str, str]:
    cmd = [
        "databricks", "labs", "lakebridge", "transpile",
        "--source-dialect", dialect,
        "--input-source", src_dir,
        "--output-folder", out_dir,
        "--skip-validation", "true" if skip_validation else "false",
        "--error-file-path", err_file,
        "--target-technology", target,
    ]
    if catalog.strip():
        cmd += ["--catalog-name", catalog.strip()]
    if schema.strip():
        cmd += ["--schema-name", schema.strip()]
    env = os.environ.copy()
    # Force PAT auth so the SDK doesn't fall back to a stale databricks-cli OAuth session
    env["DATABRICKS_AUTH_TYPE"] = "pat"

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=600, env=env,
        )
        ok = proc.returncode == 0 or any(Path(out_dir).rglob("*"))
        return ok, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Transpilation timed out after 10 minutes."
    except FileNotFoundError:
        return False, "", (
            "`databricks` CLI not found in PATH.\n"
            "Install it:\n"
            "  curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh\n"
            "  databricks labs install lakebridge"
        )
    except Exception as e:
        return False, "", str(e)



def run_oozie_converter(
    src_dir: str,
    out_dir: str,
    err_file: str,
) -> tuple[bool, str, str, list]:
    """
    Convert Oozie XML files to Databricks Jobs API 2.1 JSON.

    Workflows become independent job JSONs.
    Coordinators become scheduled jobs that trigger workflow jobs via run_job_task.
    Files are linked automatically when a coordinator and workflow share the same
    directory or when the coordinator app-path matches a workflow file.

    Returns (ok, stdout, stderr, links) where links is a list of
    {"coordinator": str, "workflow": str | None} dicts.
    """
    src_root = Path(src_dir)
    out_root = Path(out_dir)

    # Read all XML files into a dict keyed by relative path
    all_xmls: dict[str, str] = {}
    for src_file in sorted(src_root.rglob("*.xml")):
        if src_file.is_file():
            rel = str(src_file.relative_to(src_root))
            all_xmls[rel] = src_file.read_text(encoding="utf-8", errors="replace")

    if not all_xmls:
        return False, "Oozie converter: no XML files found.", "", []

    results = convert_oozie_file_set(all_xmls)

    errors: list[str] = list(results["warnings"])
    generated = 0

    for job_name, job_dict in results["jobs"].items():
        out_file = out_root / f"{job_name}.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            out_file.write_text(
                json.dumps(job_dict, indent=2), encoding="utf-8"
            )
            generated += 1
        except Exception as exc:
            errors.append(f"{job_name}: could not write output — {exc}")

    if errors:
        Path(err_file).write_text("\n".join(errors), encoding="utf-8")

    wf_count   = len(results["workflow_job_map"])
    co_count   = len(results["links"])
    linked     = sum(1 for lk in results["links"] if lk["workflow"])
    warn_count = len(errors)

    lines = [
        f"Oozie converter: {len(all_xmls)} file(s) read → "
        f"{wf_count} workflow job(s), {co_count} coordinator job(s), "
        f"{generated} JSON file(s) written.",
    ]
    if co_count:
        lines.append(
            f"  {linked}/{co_count} coordinator(s) auto-linked to a workflow via run_job_task."
        )
    if co_count - linked:
        lines.append(
            f"  {co_count - linked} coordinator(s) have no workflow match — "
            "add run_job_task manually after creating the workflow job."
        )
    if warn_count:
        lines.append(f"  {warn_count} warning(s) — see log below.")

    stdout = "\n".join(lines)
    stderr = "\n".join(errors) if (errors and generated == 0) else ""
    return generated > 0, stdout, stderr, results["links"]


def run_ssrs_converter(
    src_dir: str,
    out_dir: str,
    err_file: str,
) -> tuple[bool, str, str, dict]:
    """
    Convert SSRS .rdl/.rdlc/.rsd files to SQL notebooks and assessment JSON.

    Returns (ok, stdout, stderr, ssrs_results) where ssrs_results is the
    dict returned by _convert_ssrs_file_set.
    """
    src_root = Path(src_dir)
    out_root = Path(out_dir)

    all_rdls: dict[str, str] = {}
    for ext in ("*.rdl", "*.rdlc", "*.rsd"):
        for src_file in sorted(src_root.rglob(ext)):
            if src_file.is_file():
                rel = str(src_file.relative_to(src_root))
                all_rdls[rel] = src_file.read_text(encoding="utf-8", errors="replace")

    if not all_rdls:
        return False, "SSRS converter: no .rdl/.rdlc/.rsd files found.", "", {}

    results = _convert_ssrs_file_set(all_rdls)

    errors: list[str] = list(results["warnings"])
    generated = 0

    for fname, content in results["notebooks"].items():
        out_file = out_root / fname
        out_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            out_file.write_text(content, encoding="utf-8")
            generated += 1
        except Exception as exc:
            errors.append(f"{fname}: could not write — {exc}")

    for fname, adict in results["assessments"].items():
        out_file = out_root / fname
        out_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            out_file.write_text(json.dumps(adict, indent=2), encoding="utf-8")
            generated += 1
        except Exception as exc:
            errors.append(f"{fname}: could not write — {exc}")

    if errors:
        Path(err_file).write_text("\n".join(errors), encoding="utf-8")

    n_rdl = len(all_rdls)
    n_nb = len(results["notebooks"])
    n_as = len(results["assessments"])
    stdout = (
        f"SSRS converter: {n_rdl} file(s) read → "
        f"{n_nb} SQL notebook(s), {n_as} assessment JSON(s), "
        f"{generated} total file(s) written."
    )

    return generated > 0, stdout, "\n".join(errors) if errors else "", results


def build_file_tree_html(directory: str) -> tuple[str, int, int]:
    """Return an HTML file-tree string plus (n_files, n_bytes)."""
    root = Path(directory)
    lines = []
    total_files = 0
    total_bytes = 0
    for p in sorted(root.rglob("*")):
        depth = len(p.relative_to(root).parts) - 1
        indent = "│  " * depth + ("├─ " if depth > 0 else "")
        if p.is_dir():
            lines.append(f'<span class="dir">{indent}{p.name}/</span>')
        else:
            size = p.stat().st_size
            total_files += 1
            total_bytes += size
            lines.append(
                f'<span class="file">{indent}{p.name}</span>'
                f'<span class="meta">  ({size:,} bytes)</span>'
            )
    return "<br>".join(lines) if lines else '<span class="meta">No files found.</span>', total_files, total_bytes

def classify_error(stderr: str):
    if "Invalid value for '--source-dialect'" in stderr:
        return "UNSUPPORTED_DIALECT"
    if "No such file or directory" in stderr:
        return "INPUT_PATH_ERROR"
    if "authentication" in stderr.lower():
        return "AUTH_ERROR"
    return "UNKNOWN"

def render_transpile_metrics(n_src, n_out, elapsed, llm_counts=(0, 0)):
    """
    llm_counts = (llm_files_sent, llm_statements_replaced)
    Only llm_files_sent is used for display.
    """

    llm_files_sent = llm_counts[0]

    # decide columns
    num_cols = 4 if llm_files_sent else 3
    cols = st.columns(num_cols)

    idx = 0

    # Files processed
    with cols[idx]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val">{n_src}</div>
            <div class="metric-lbl">Files Processed</div>
        </div>""", unsafe_allow_html=True)
    idx += 1

    # Files generated
    with cols[idx]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val">{n_out}</div>
            <div class="metric-lbl">Files Generated</div>
        </div>""", unsafe_allow_html=True)
    idx += 1

    # LLM card (only if present)
    if llm_files_sent:
        with cols[idx]:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-icon">AI</div>
                <div class="metric-val">{llm_files_sent}</div>
                <div class="metric-lbl">files enhanced</div>
            </div>""", unsafe_allow_html=True)
        idx += 1

    # Time taken
    with cols[idx]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val">{elapsed:.1f}s</div>
            <div class="metric-lbl">Time Taken</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TOP NAV + ROUTING
# ══════════════════════════════════════════════════════════════════════════════

_PAGES = ["Home", "Docs", "Analyzer", "Transpiler", "Settings"]
selected_page = st.query_params.get("page", "Home")
if selected_page not in _PAGES:
    selected_page = "Home"

_logo_src = f"data:image/png;base64,{_LOGO_B64}" if _LOGO_B64 else ""
_logo_img = f'<img src="{_logo_src}" alt="Syren">' if _logo_src else ""

def _nav_link(label: str, page: str, active: str) -> str:
    from urllib.parse import quote_plus
    cls = "sb-link active" if page == active else "sb-link"
    return f'<a class="{cls}" href="?page={quote_plus(page)}" target="_self">{label}</a>'

_nav_html = f"""
<div id="sb-nav">
    <a class="sb-logo" href="?page=Home" target="_self">
        {_logo_img}
        <span>SyrenBridge</span>
    </a>
    <div class="sb-divider"></div>
    <div class="sb-links">
        {_nav_link("Home", "Home", selected_page)}
        {_nav_link("Docs", "Docs", selected_page)}
        {_nav_link("Analyser", "Analyzer", selected_page)}
        {_nav_link("Transpiler", "Transpiler", selected_page)}
        {_nav_link("Settings", "Settings", selected_page)}
    </div>
    <div class="sb-spacer"></div>
    <span class="sb-badge">13 Dialects</span>
</div>
"""
st.markdown(_nav_html, unsafe_allow_html=True)


# ── Page header renderer ──────────────────────────────────────────────────────
_PAGE_META = {
    "Home":       ("", "SyrenBridge", "Enterprise migration platform by Syren Cloud"),
    "Docs":       ("", "Documentation", "Overview, capabilities, and how to use SyrenBridge"),
    "Analyzer":   ("", "Code Analyzer", "Analyze legacy source code for migration readiness"),
    "Transpiler": ("", "Code Transpiler", "Convert source code to Databricks-compatible output"),
    "Settings":   ("", "Settings", "Configure Databricks workspace credentials"),
}
_icon, _title, _subtitle = _PAGE_META[selected_page]
if selected_page != "Home":
    st.markdown(f"""
<div class="page-hdr">
    <div class="page-hdr-icon">{_icon}</div>
    <div>
        <h1>{_title}</h1>
        <p>{_subtitle} &nbsp;·&nbsp; SyrenBridge by Syren Cloud</p>
    </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE — HOME
# ══════════════════════════════════════════════════════════════════════════════

if selected_page == "Home":

    st.markdown("""
    <div style="padding:3rem 0 2rem;">

        <!-- Hero -->
        <div style="text-align:center;max-width:760px;margin:0 auto 3.5rem;">
            <div style="display:inline-block;background:rgba(255,54,33,0.1);border:1px solid rgba(255,54,33,0.25);
                        border-radius:999px;padding:5px 16px;font-size:12px;font-weight:600;
                        color:#FF3621;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:1.5rem;">
                Enterprise Migration Platform
            </div>
            <h1 style="font-size:3rem;font-weight:800;color:#fff;letter-spacing:-0.04em;
                       line-height:1.1;margin:0 0 1.25rem;">
                Move legacy data platforms<br>to <span style="color:#FF3621;">Databricks</span>
            </h1>
            <p style="font-size:1.1rem;color:#94a3b8;line-height:1.7;margin:0 0 2.5rem;">
                SyrenBridge automates the migration of SQL dialects, ETL pipelines, and workflow
                orchestration to Databricks — from analysis through production-ready converted code.
            </p>
            <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
                <a href="?page=Analyzer" target="_self"
                   style="display:inline-block;background:#FF3621;color:#fff;font-weight:600;
                          font-size:14px;padding:12px 28px;border-radius:9px;text-decoration:none;
                          box-shadow:0 0 24px rgba(255,54,33,0.3);">
                    Start Analysis
                </a>
                <a href="?page=Transpiler" target="_self"
                   style="display:inline-block;background:rgba(255,255,255,0.05);color:#f1f5f9;
                          font-weight:600;font-size:14px;padding:12px 28px;border-radius:9px;
                          text-decoration:none;border:1px solid rgba(255,255,255,0.1);">
                    Browse Transpiler
                </a>
            </div>
        </div>

        <!-- Stats row -->
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:3rem;">
            <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);
                        border-radius:14px;padding:1.75rem;text-align:center;backdrop-filter:blur(12px);">
                <div style="font-size:2.75rem;font-weight:800;color:#FF3621;
                            font-family:'JetBrains Mono',monospace;line-height:1;">36</div>
                <div style="font-size:13px;font-weight:600;color:#94a3b8;margin-top:8px;
                            text-transform:uppercase;letter-spacing:0.07em;">Source Technologies</div>
                <div style="font-size:12px;color:#475569;margin-top:4px;">SQL · ETL · Workflow · Code</div>
            </div>
            <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);
                        border-radius:14px;padding:1.75rem;text-align:center;backdrop-filter:blur(12px);">
                <div style="font-size:2.75rem;font-weight:800;color:#6366f1;
                            font-family:'JetBrains Mono',monospace;line-height:1;">13</div>
                <div style="font-size:13px;font-weight:600;color:#94a3b8;margin-top:8px;
                            text-transform:uppercase;letter-spacing:0.07em;">Transpiler Dialects</div>
                <div style="font-size:12px;color:#475569;margin-top:4px;">CLI · Custom engines · SSRS · Oozie</div>
            </div>
            <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);
                        border-radius:14px;padding:1.75rem;text-align:center;backdrop-filter:blur(12px);">
                <div style="font-size:2.75rem;font-weight:800;color:#06b6d4;
                            font-family:'JetBrains Mono',monospace;line-height:1;">100%</div>
                <div style="font-size:13px;font-weight:600;color:#94a3b8;margin-top:8px;
                            text-transform:uppercase;letter-spacing:0.07em;">Databricks Native</div>
                <div style="font-size:12px;color:#475569;margin-top:4px;">Runs on Databricks Apps</div>
            </div>
        </div>

        <!-- Feature cards -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:3rem;">

            <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);
                        border-radius:16px;padding:2rem;backdrop-filter:blur(12px);">
                <div style="width:40px;height:40px;background:rgba(255,54,33,0.1);
                            border:1px solid rgba(255,54,33,0.2);border-radius:10px;
                            display:flex;align-items:center;justify-content:center;margin-bottom:1.25rem;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FF3621" stroke-width="2">
                        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                    </svg>
                </div>
                <div style="font-size:17px;font-weight:700;color:#fff;margin-bottom:0.6rem;">Code Analyzer</div>
                <div style="font-size:14px;color:#94a3b8;line-height:1.65;margin-bottom:1.25rem;">
                    Upload source files and receive a full migration-readiness report —
                    object inventory, function usage, SQL category breakdown, and complexity scoring
                    across 36 technologies.
                </div>
                <a href="?page=Analyzer" target="_self"
                   style="font-size:13px;font-weight:600;color:#FF3621;text-decoration:none;">
                    Open Analyzer &rarr;
                </a>
            </div>

            <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);
                        border-radius:16px;padding:2rem;backdrop-filter:blur(12px);">
                <div style="width:40px;height:40px;background:rgba(99,102,241,0.1);
                            border:1px solid rgba(99,102,241,0.2);border-radius:10px;
                            display:flex;align-items:center;justify-content:center;margin-bottom:1.25rem;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                    </svg>
                </div>
                <div style="font-size:17px;font-weight:700;color:#fff;margin-bottom:0.6rem;">Code Transpiler</div>
                <div style="font-size:14px;color:#94a3b8;line-height:1.65;margin-bottom:1.25rem;">
                    Convert HiveSQL, SSIS, SSRS, Oozie workflows, and 9 other dialects to
                    Databricks SQL, PySpark notebooks, or Jobs API JSON — with optional
                    LLM-assisted refinement for complex statements.
                </div>
                <a href="?page=Transpiler" target="_self"
                   style="font-size:13px;font-weight:600;color:#6366f1;text-decoration:none;">
                    Open Transpiler &rarr;
                </a>
            </div>

            <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);
                        border-radius:16px;padding:2rem;backdrop-filter:blur(12px);">
                <div style="width:40px;height:40px;background:rgba(6,182,212,0.1);
                            border:1px solid rgba(6,182,212,0.2);border-radius:10px;
                            display:flex;align-items:center;justify-content:center;margin-bottom:1.25rem;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#06b6d4" stroke-width="2">
                        <rect x="3" y="3" width="18" height="18" rx="2"/>
                        <path d="M3 9h18M9 21V9"/>
                    </svg>
                </div>
                <div style="font-size:17px;font-weight:700;color:#fff;margin-bottom:0.6rem;">Workspace Integration</div>
                <div style="font-size:14px;color:#94a3b8;line-height:1.65;margin-bottom:1.25rem;">
                    Browse and fetch files directly from your Databricks workspace.
                    Push converted output back into workspace folders without leaving the app.
                </div>
                <a href="?page=Settings" target="_self"
                   style="font-size:13px;font-weight:600;color:#06b6d4;text-decoration:none;">
                    Configure &rarr;
                </a>
            </div>

            <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);
                        border-radius:16px;padding:2rem;backdrop-filter:blur(12px);">
                <div style="width:40px;height:40px;background:rgba(251,191,36,0.1);
                            border:1px solid rgba(251,191,36,0.2);border-radius:10px;
                            display:flex;align-items:center;justify-content:center;margin-bottom:1.25rem;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2">
                        <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                        <path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
                    </svg>
                </div>
                <div style="font-size:17px;font-weight:700;color:#fff;margin-bottom:0.6rem;">LLM-Assisted Migration</div>
                <div style="font-size:14px;color:#94a3b8;line-height:1.65;margin-bottom:1.25rem;">
                    Connect any OpenAI-compatible endpoint — including Databricks model serving —
                    to automatically refine complex SQL statements that rule-based transpilation
                    cannot fully resolve.
                </div>
                <a href="?page=Settings" target="_self"
                   style="font-size:13px;font-weight:600;color:#fbbf24;text-decoration:none;">
                    Configure LLM &rarr;
                </a>
            </div>

        </div>

        <!-- Footer note -->
        <div style="text-align:center;padding:1.5rem 0;border-top:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:12px;color:#334155;">
                Built by Syren Cloud &nbsp;&middot;&nbsp; Powered by Databricks Labs Lakebridge
                &nbsp;&middot;&nbsp;
                <a href="?page=Docs" target="_self" style="color:#475569;text-decoration:none;">Documentation</a>
            </div>
        </div>

    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE — DOCS
# ══════════════════════════════════════════════════════════════════════════════

elif selected_page == "Docs":

    # ── Intro ─────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="max-width:720px;margin-bottom:2rem;">
        <p style="color:#94a3b8;font-size:0.95rem;line-height:1.7;margin:0;">
            SyrenBridge is Syren Cloud's enterprise migration suite for moving legacy data platforms
            to <strong>Databricks</strong>. It covers the full migration journey — from automated
            analysis of your existing codebase to production-ready converted code — supporting
            <strong>36 source technologies</strong> across SQL, ETL, and workflow orchestration.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Quick-start steps ─────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:12px;
                backdrop-filter:blur(12px);padding:1.5rem 1.75rem;margin-bottom:2rem;">
        <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                    text-transform:uppercase;margin-bottom:1.1rem;">Quick Start</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.25rem;">
            <div>
                <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.08em;
                            text-transform:uppercase;margin-bottom:0.3rem;">Step 1</div>
                <div style="font-weight:700;color:#f1f5f9;margin-bottom:0.3rem;font-size:0.95rem;">
                    Analyze
                </div>
                <div style="font-size:0.85rem;color:#94a3b8;line-height:1.6;">
                    Select your source technology, upload source files or use Databricks workspace folder files, and get a
                    migration-readiness report — object inventory, function usage, SQL category breakdown.
                </div>
            </div>
            <div style="border-left:1px solid rgba(255,255,255,0.08);padding-left:1.25rem;">
                <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.08em;
                            text-transform:uppercase;margin-bottom:0.3rem;">Step 2</div>
                <div style="font-weight:700;color:#f1f5f9;margin-bottom:0.3rem;font-size:0.95rem;">
                    Transpile
                </div>
                <div style="font-size:0.85rem;color:#94a3b8;line-height:1.6;">
                    Select your source dialect, upload files either locally or from your Databricks workspace, and download Databricks-compatible
                    output — SQL, PySpark notebooks, or Workflow JSON or you can write directly to your workspace folders.
                </div>
            </div>
            <div style="border-left:1px solid rgba(255,255,255,0.08);padding-left:1.25rem;">
                <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.08em;
                            text-transform:uppercase;margin-bottom:0.3rem;">First time?</div>
                <div style="font-weight:700;color:#f1f5f9;margin-bottom:0.3rem;font-size:0.95rem;">
                    Configure
                </div>
                <div style="font-size:0.85rem;color:#94a3b8;line-height:1.6;">
                    If running locally, go to <strong>Settings</strong> and enter your Databricks
                    workspace URL and token. On Databricks Apps this is automatic.
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Transpiler dialects table ─────────────────────────────────────────────
    st.markdown("""
    <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                text-transform:uppercase;margin-bottom:0.75rem;">Transpiler — 13 Supported Dialects</div>
    """, unsafe_allow_html=True)

    dialect_rows = [
        ("DataStage",          "Databricks Labs Lakebridge",   "PySpark / SparkSQL",          ".dsx .xml .pjb"),
        ("HiveSQL (Cloudera)", "sqlglot (Databricks dialect)", "Databricks SQL / PySpark",    ".hql .hive .sql .ddl .dml"),
        ("Informatica",        "Databricks Labs Lakebridge",   "PySpark / SparkSQL",          ".xml .session .wf .m .mplt .lkp"),
        ("Informatica Cloud",  "Databricks Labs Lakebridge",   "PySpark / SparkSQL",          ".xml .json .session"),
        ("MS SQL Server",      "Databricks Labs Lakebridge",   "PySpark / SparkSQL",          ".sql .ddl .dml .proc .view"),
        ("Netezza",            "Databricks Labs Lakebridge",   "PySpark / SparkSQL",          ".sql .ddl .dml .nzb"),
        ("Oracle",             "Databricks Labs Lakebridge",   "PySpark / SparkSQL",          ".sql .ddl .dml .pls .prc .vw"),
        ("Snowflake",          "Databricks Labs Lakebridge",   "PySpark / SparkSQL",          ".sql .ddl .dml"),
        ("SSIS",               "BladeBridge (Lakebridge)",     "SparkSQL",                    ".dtsx .xml"),
        ("SSRS (Reports)",     "Built-in ssrs_converter",      "SQL Notebooks + JSON",        ".rdl .rdlc .rsd"),
        ("Synapse",            "Databricks Labs Lakebridge",   "PySpark / SparkSQL",          ".sql .ddl .dml .json"),
        ("Teradata",           "Databricks Labs Lakebridge",   "PySpark / SparkSQL",          ".sql .bteq .tdl .tpt .ddl .dml"),
        ("Oozie (Workflow)",   "lxml (built-in parser)",       "Databricks Jobs JSON",        ".xml"),
    ]

    gs_table_rows = ""
    for i, (dialect, engine, output, exts) in enumerate(dialect_rows):
        bg = "rgba(255,255,255,0.03)" if i % 2 == 0 else "rgba(255,255,255,0.015)"
        gs_table_rows += f"""
        <tr style="background:{bg};">
            <td style="padding:0.55rem 0.85rem;font-weight:600;color:#f1f5f9;font-size:0.87rem;">{dialect}</td>
            <td style="padding:0.55rem 0.85rem;color:#94a3b8;font-size:0.84rem;">{engine}</td>
            <td style="padding:0.55rem 0.85rem;color:#94a3b8;font-size:0.84rem;">{output}</td>
            <td style="padding:0.55rem 0.85rem;color:#94a3b8;font-size:0.78rem;font-family:monospace;">{exts}</td>
        </tr>"""

    st.markdown(f"""
    <div style="border:1px solid rgba(255,255,255,0.08);border-radius:10px;overflow:hidden;margin-bottom:2rem;backdrop-filter:blur(12px);">
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:rgba(255,255,255,0.05);border-bottom:1px solid rgba(255,255,255,0.08);">
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#f1f5f9;text-transform:uppercase;">Dialect</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#f1f5f9;text-transform:uppercase;">Engine</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#f1f5f9;text-transform:uppercase;">Output</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#f1f5f9;text-transform:uppercase;">File Types</th>
                </tr>
            </thead>
            <tbody>{gs_table_rows}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)

    # ── Analyzer technologies ─────────────────────────────────────────────────
    st.markdown("""
    <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                text-transform:uppercase;margin-bottom:0.75rem;">Analyzer — 36 Supported Technologies</div>
    """, unsafe_allow_html=True)

    sql_techs  = [n for _, n, c in TECHNOLOGIES if c == "SQL"]
    etl_techs  = [n for _, n, c in TECHNOLOGIES if c == "ETL"]
    code_techs = [n for _, n, c in TECHNOLOGIES if c == "Code"]

    gs_a1, gs_a2, gs_a3 = st.columns(3, gap="medium")
    def _tech_list(techs):
        return "".join(
            f'<li style="padding:0.1rem 0;color:#94a3b8;font-size:0.85rem;">{t}</li>'
            for t in techs
        )

    with gs_a1:
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:1rem 1.25rem;">
            <div style="font-size:0.68rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                        text-transform:uppercase;margin-bottom:0.6rem;">SQL ({len(sql_techs)})</div>
            <ul style="list-style:none;padding:0;margin:0;line-height:1.7;">{_tech_list(sql_techs)}</ul>
        </div>""", unsafe_allow_html=True)

    with gs_a2:
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:1rem 1.25rem;">
            <div style="font-size:0.68rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                        text-transform:uppercase;margin-bottom:0.6rem;">ETL ({len(etl_techs)})</div>
            <ul style="list-style:none;padding:0;margin:0;line-height:1.7;">{_tech_list(etl_techs)}</ul>
        </div>""", unsafe_allow_html=True)

    with gs_a3:
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:1rem 1.25rem;">
            <div style="font-size:0.68rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                        text-transform:uppercase;margin-bottom:0.6rem;">Code ({len(code_techs)})</div>
            <ul style="list-style:none;padding:0;margin:0;line-height:1.7;">{_tech_list(code_techs)}</ul>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

    # ── PySpark / Serverless note ─────────────────────────────────────────────
    st.markdown(
        '<div style="background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.2);border-radius:8px;'
        'padding:0.8rem 1.1rem;font-size:0.86rem;color:#67e8f9;">'
        '<strong style="color:#f1f5f9;">PySpark &amp; Spark Classic → Serverless</strong> '
        'migrations are handled by the Syren Server to Serverless Migration Platform — '
        '<a href="https://syren-s2s-platform-204242957656703.3.azure.databricksapps.com/#home" '
        'target="_blank" style="color:#2563eb;font-weight:600;">Open platform →</a>'
        '</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE — ANALYZER
# ══════════════════════════════════════════════════════════════════════════════

elif selected_page == "Analyzer":

    st.markdown("""
    <div style="color:#94a3b8;font-size:0.92rem;max-width:680px;margin-bottom:1.5rem;">
        Upload your source code, select the technology, and receive a
        <strong>migration-readiness report</strong> — covering object inventory, function usage,
        SQL category breakdown, and complexity scoring.
    </div>
    """, unsafe_allow_html=True)

    # ── STEP 1 + STEP 2 ──────────────────────────────────────────────────────
    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.markdown("""
        <div class="card-title">
            <span class="step-num">1</span> Select Source Technology
        </div>
        """, unsafe_allow_html=True)

        tech_options_display = [
            f"{CATEGORY_ICON.get(cat, cat)}  {name}"
            for _, name, cat in TECHNOLOGIES
        ]

        selected_idx = st.selectbox(
            "Technology",
            options=range(len(TECHNOLOGIES)),
            format_func=lambda i: tech_options_display[i],
            index=23,
            key="tech_select",
            label_visibility="collapsed",
        )

        tech_num, tech_name, tech_cat = TECHNOLOGIES[selected_idx]
        tech_exts = TECH_EXTENSIONS.get(tech_num, ["sql", "txt"])

        tags_html = "".join(f'<span class="ext-tag">.{e}</span>' for e in tech_exts)
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:1rem 1.25rem;margin-top:0.75rem;">
            <div style="font-weight:700;color:#f1f5f9;font-size:1rem;margin-bottom:0.2rem;">
                {tech_name}
            </div>
            <div style="font-size:0.78rem;color:#9ca3af;margin-bottom:0.6rem;">
                Category: {tech_cat} &nbsp;·&nbsp; Option #{tech_num}
            </div>
            <div style="font-size:0.78rem;color:#94a3b8;margin-bottom:0.4rem;font-weight:600;">
                ACCEPTED FILE TYPES
            </div>
            <div class="ext-wrap">{tags_html}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

        output_filename = st.text_input(
            "Output report filename",
            value="lakebridge_analysis.xlsx",
            help="Name for the generated Excel report.",
        )
        if not output_filename.lower().endswith(".xlsx"):
            output_filename += ".xlsx"

    with col_right:
        st.markdown("""
        <div class="card-title">
            <span class="step-num">2</span> Upload Source Files
        </div>
        """, unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["Upload Files", "Databricks Workspace"])

        uploaded_files = []
        is_zip = False

        # ==========================================================
        # TAB 1 — FILE UPLOAD
        # ==========================================================
        with tab1:
            upload_mode = st.radio(
                "Mode",
                ["Individual files", "ZIP archive"],
                horizontal=True,
                label_visibility="collapsed",
            )

            is_zip = upload_mode == "ZIP archive"

            if is_zip:
                raw = st.file_uploader("Drop ZIP", type=["zip"], label_visibility="collapsed")
                uploaded_files = [raw] if raw else []
            else:
                uploaded_files = st.file_uploader(
                    "Drop files",
                    type=tech_exts,
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                )

            if uploaded_files:
                total_kb = sum(f.size for f in uploaded_files) / 1024
                st.success(f"✅ {len(uploaded_files)} file(s) ready · {total_kb:.1f} KB")

                with st.expander("View uploaded files"):
                    for f in uploaded_files:
                        st.markdown(f"`{f.name}`")

                st.session_state["source_mode"] = "upload"
            else:
                st.info("No files uploaded")

        # ==========================================================
        # TAB 2 — WORKSPACE
        # ==========================================================
        with tab2:
            from modules.databricks_service import DatabricksClient

            st.markdown("#### Browse Workspace")

            try:
                dbx = DatabricksClient.from_app_context()

                # ─────────────────────────────────────────
                # INIT STATE
                # ─────────────────────────────────────────
                if "ws_path" not in st.session_state:
                    st.session_state["ws_path"] = "/"
                if "ws_selected_files" not in st.session_state:
                    st.session_state["ws_selected_files"] = []
                if "ws_items" not in st.session_state:
                    st.session_state["ws_items"] = []
                if "last_loaded_path" not in st.session_state:
                    st.session_state["last_loaded_path"] = None

                current_path = st.session_state["ws_path"]

                # ─────────────────────────────────────────
                # SHOW CURRENT PATH
                # ─────────────────────────────────────────
                st.text_input("Current Path", value=current_path, disabled=True, key="ws_current_path")

                # ─────────────────────────────────────────
                # AUTO LOAD (NO BUTTON NEEDED)
                # ─────────────────────────────────────────
                if (
                    st.session_state.get("last_loaded_path") != current_path
                ):
                    items = dbx.list_workspace_items(current_path)

                    if isinstance(items, dict) and "error" in items:
                        st.error(items["error"])
                        st.session_state["ws_items"] = []
                    else:
                        st.session_state["ws_items"] = items

                    st.session_state["last_loaded_path"] = current_path

                items = st.session_state.get("ws_items", [])

                # Show navigation buttons if not at root
                if current_path != "/":
                    parent = "/".join(current_path.rstrip("/").split("/")[:-1]) or "/"
                    back_col, home_col = st.columns([1, 1], gap="small")
                    with back_col:
                        if st.button("Back", key="ws_back"):
                            st.session_state["ws_path"] = parent
                            st.session_state.pop("ws_items", None)
                            st.session_state.pop("last_loaded_path", None)
                            st.rerun()
                    with home_col:
                        if st.button("Home", key="ws_home"):
                            st.session_state["ws_path"] = "/"
                            st.session_state.pop("ws_items", None)
                            st.session_state.pop("last_loaded_path", None)
                            st.rerun()

                if items:
                    dirs = [o for o in items if o.get("object_type") == "DIRECTORY"]
                    files = [o for o in items if o.get("object_type") in ["NOTEBOOK", "FILE"]]

                    # 🔥 REAL SCROLL CONTAINER
                    container = st.container(height=350)

                    with container:
                        # ─────────────────────────────────────────
                        # FOLDERS
                        # ─────────────────────────────────────────
                        if dirs:
                            st.markdown("##### Folders")

                            for obj in dirs:
                                path = obj.get("path")
                                name = path.rstrip("/").split("/")[-1]
                                button_key = make_widget_key("dir", path)

                                if st.button(f"{name}", key=button_key):
                                    st.session_state["ws_path"] = path
                                    st.session_state.pop("ws_items", None)
                                    st.session_state.pop("last_loaded_path", None)
                                    st.rerun()

                    # ─────────────────── files ──────────────────────
                        if files:
                            st.markdown("##### Select files")

                            selected_paths = set(st.session_state.get("ws_selected_files", []))
                            for obj in files:
                                path = obj.get("path")

                                if any(path.lower().endswith(f".{ext}") for ext in tech_exts):
                                    checkbox_key = make_widget_key("ws", path)
                                    checked = st.checkbox(path, value=(path in selected_paths), key=checkbox_key)
                                    if checked:
                                        selected_paths.add(path)
                                    else:
                                        selected_paths.discard(path)

                            st.session_state["ws_selected_files"] = sorted(selected_paths)

                            if selected_paths:
                                st.success(f"✅ {len(selected_paths)} file(s) selected")
                                st.session_state["source_mode"] = "workspace"
                            else:
                                st.info("No files selected")

                        else:
                            st.info("No valid files in this folder")

                else:
                    st.info("No items found in this path")

            except Exception as e:
                st.error(f"Workspace error: {str(e)}")

        # ==========================================================
        # EMPTY STATE
        # ==========================================================
        if not uploaded_files and not st.session_state.get("ws_selected_files"):
            st.markdown("""
            <div style="background:rgba(255,255,255,0.03);border:2px dashed rgba(255,255,255,0.08);border-radius:12px;
                        padding:2rem;text-align:center;color:#9ca3af;">
                <div style="font-size:2rem;">&#128193;</div>
                <div>No files selected yet</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div style="font-size:0.78rem;color:#9ca3af;margin-top:0.75rem;">
            Upload files or browse Databricks workspace
        </div>
        """, unsafe_allow_html=True)

    # ── STEP 3: RUN ───────────────────────────────────────────────────────────
    st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)

    _, btn_col, _ = st.columns([2, 1, 2])
    with btn_col:
        run_clicked = st.button(
            "Analyse",
            width='stretch',
            disabled=not bool(uploaded_files or st.session_state.get("ws_selected_files")),
            key="run_analyze",
        )

    if not uploaded_files and not st.session_state.get("ws_selected_files"):
        st.markdown(
            "<div style='text-align:center;color:#9ca3af;font-size:0.85rem;margin-top:0.25rem'>"
            "Upload at least one file to run the analysis."
            "</div>",
            unsafe_allow_html=True,
        )

    # ── ANALYSIS EXECUTION ────────────────────────────────────────────────────
    if run_clicked and (uploaded_files or st.session_state.get("ws_selected_files")):
        src_dir = out_dir = None
        try:
            with st.status("Running analysis…", expanded=True) as status:
                source_mode = st.session_state.get("source_mode")

                if source_mode == "workspace":
                    ws_files = st.session_state.get("ws_selected_files", [])

                    if not ws_files:
                        st.error("No workspace files selected")
                        st.stop()

                    st.write(f"Preparing **{len(ws_files)}** workspace file(s)…")
                    src_dir = fetch_workspace_files_to_local(ws_files)

                elif source_mode == "upload":
                    if not uploaded_files:
                        st.error("No uploaded files found")
                        st.stop()

                    st.write(f"Preparing **{len(uploaded_files)}** file(s)…")
                    src_dir = save_uploaded_files(uploaded_files, is_zip)

                else:
                    st.error("No input source selected")
                    st.stop()

                # ─────────────────────────────────────────
                # COMMON PROCESSING
                # ─────────────────────────────────────────
                n_files, n_bytes = count_files(src_dir)

                if n_files == 0:
                    st.error("No valid files found to analyze")
                    st.stop()

                st.write(f"&nbsp;&nbsp;→ {n_files} file(s) staged ({n_bytes/1024:.1f} KB)")

                out_dir = tempfile.mkdtemp(prefix="lb_out_")
                out_file = os.path.join(out_dir, output_filename)

                st.write(f"Analyzing as **{tech_name}** (#{tech_num})…")
                t0 = time.time()
                ok, stdout, stderr = run_lakebridge(src_dir, out_file, tech_num)
                elapsed = time.time() - t0
                st.write(f"&nbsp;&nbsp;→ Completed in **{elapsed:.1f}s**")

                report_ok = os.path.exists(out_file) and is_valid_excel(out_file)
                sql_reports = sorted(Path(out_dir).glob("*_SQL.xlsx"))

                if report_ok:
                    status.update(label="✅ Analysis complete!", state="complete", expanded=False)
                else:
                    status.update(label="Finished with issues — see log below", state="error", expanded=True)

            if stdout:
                with st.expander("Full analysis log"):
                    log_container = st.container(height=400)
                    with log_container:
                        st.markdown("<div class='output-block'>", unsafe_allow_html=True)
                        st.code(stdout, language="text")
                        st.markdown("</div>", unsafe_allow_html=True)
            if stderr and not ok:
                with st.expander("Errors / warnings"):
                    error_container = st.container(height=400)
                    with error_container:
                        st.markdown("<div class='output-block'>", unsafe_allow_html=True)
                        st.code(stderr, language="text")
                        st.markdown("</div>", unsafe_allow_html=True)

            if not report_ok:
                st.error("Lakebridge did not generate a valid Excel report.")
                st.stop()
                
            if report_ok:
                main_sheets = read_excel_sheets(out_file)

                st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)
                st.markdown("""
                <div class="results-header">
                    <div class="results-title">Analysis Results <span class="success-pill">Ready</span></div>
                </div>
                """, unsafe_allow_html=True)

                metrics = extract_metrics(main_sheets)
                if metrics:
                    icons = {
                        "Files Analyzed": "",
                        "SQL Programs": "",
                        "Unique Functions": "",
                        "Referenced Objects": "",
                        "Transformations": "",
                    }
                    items = list(metrics.items())
                    cols = st.columns(min(len(items), 4))
                    for col, (label, val) in zip(cols, items):
                        with col:
                            st.markdown(f"""
                            <div class="metric-card">
                                <div class="metric-icon">{icons.get(label, '')}</div>
                                <div class="metric-val">{val:,}</div>
                                <div class="metric-lbl">{label}</div>
                            </div>
                            """, unsafe_allow_html=True)

                st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

                fn_chart = build_function_chart(main_sheets)
                cat_chart = build_category_chart(main_sheets)

                if fn_chart and cat_chart:
                    ch1, ch2 = st.columns(2) 
                    with ch1 :
                        st.markdown("**Top Functions by Usage**")
                        st.altair_chart(fn_chart, width='stretch')
                    with ch2:
                        st.markdown("**SQL Script Categories**")
                        st.altair_chart(cat_chart, width='stretch')
                # Case 2: only function chart
                elif fn_chart:
                    st.markdown("**Top Functions by Usage**")
                    st.altair_chart(fn_chart, width='stretch')

                # Case 3: only category chart
                elif cat_chart:
                    st.markdown("**SQL Script Categories**")
                    st.altair_chart(cat_chart, width='stretch')
                st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
                dl_cols = st.columns(2) if sql_reports else st.columns([1, 2])

                with dl_cols[0]:
                    with open(out_file, "rb") as fh:
                        st.download_button(
                            label="Download Main Report",
                            data=fh.read(),
                            file_name=output_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="analysis_download_main",
                            width='stretch',
                        )

                if sql_reports:
                    with dl_cols[1]:
                        with open(str(sql_reports[0]), "rb") as fh:
                            st.download_button(
                                label="Download SQL Sub-Report",
                                data=fh.read(),
                                file_name=sql_reports[0].name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="analysis_download_sql_sub",
                                width='stretch',
                            )

                st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)
                st.markdown("**Sheet Explorer**")
                sheet_names = list(main_sheets.keys())
                if sheet_names:
                    tabs = st.tabs(sheet_names)
                    for tab, name in zip(tabs, sheet_names):
                        with tab:
                            df = main_sheets[name]
                            if df.empty:
                                st.markdown(
                                    "<div class='empty-state'><p>No data rows.</p>"
                                    "<p>This sheet has no data rows.</p></div>",
                                    unsafe_allow_html=True,
                                )
                            else:
                                info_col, search_col = st.columns([2, 1])
                                with info_col:
                                    st.caption(f"{len(df):,} rows · {len(df.columns)} columns")
                                with search_col:
                                    search = st.text_input(
                                        "Filter rows",
                                        key=f"az_search_{name}",
                                        placeholder="Type to filter…",
                                        label_visibility="collapsed",
                                    )
                                if search:
                                    mask = df.apply(
                                        lambda col: col.astype(str).str.contains(search, case=False, na=False)
                                    ).any(axis=1)
                                    display_df = df[mask]
                                    st.caption(f"Showing {len(display_df):,} matching rows")
                                else:
                                    display_df = df
                                st.dataframe(display_df, width='stretch', hide_index=True)

                if sql_reports:
                    st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)
                    st.markdown("**Embedded SQL Report — Sheet Explorer**")
                    sql_sheets = read_excel_sheets(str(sql_reports[0]))
                    sql_names = list(sql_sheets.keys())
                    if sql_names:
                        sql_tabs = st.tabs(sql_names)
                        for tab, name in zip(sql_tabs, sql_names):
                            with tab:
                                df = sql_sheets[name]
                                if df.empty:
                                    st.caption("No data rows.")
                                else:
                                    st.caption(f"{len(df):,} rows · {len(df.columns)} columns")
                                    st.dataframe(df, width='stretch', hide_index=True)
            else:
                st.error(
                    "No output report was generated. "
                    "Common causes: the `databricks` CLI is not installed, "
                    "or authentication is not configured in this environment."
                )
                if stderr:
                    st.code(stderr, language="text")

        finally:
            for d in (src_dir, out_dir):
                if d and os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE — TRANSPILER
# ══════════════════════════════════════════════════════════════════════════════

elif selected_page == "Transpiler":

    st.markdown("""
    <div style="color:#94a3b8;font-size:0.92rem;max-width:720px;margin-bottom:1.5rem;">
        Convert legacy SQL, ETL, and workflow code into <strong>Databricks-compatible output</strong>.
        Select your source dialect, upload files, and download the converted result.
    </div>
    """, unsafe_allow_html=True)

    # ── Supported dialects info ───────────────────────────────────────────────
    dial_names = list(TRANSPILER_DIALECTS.keys())
    dial_tags = "".join(f'<span class="ext-tag teal">{d}</span>' for d in dial_names)
    st.markdown(f"""
    <div style="background:#f0fdfa;border:1px solid #99f6e4;border-radius:10px;
                padding:0.85rem 1.25rem;margin-bottom:1.5rem;">
        <div style="font-size:0.8rem;font-weight:700;color:#0D9488;margin-bottom:0.5rem;letter-spacing:0.05em;">
            SUPPORTED SOURCE DIALECTS
        </div>
        <div class="ext-wrap">{dial_tags}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── PySpark / Serverless note ─────────────────────────────────────────────
    st.markdown(
        '<div style="background:rgba(99,102,241,0.08);border:1px solid #93c5fd;border-radius:8px;'
        'padding:0.65rem 1rem;margin-bottom:1rem;font-size:0.83rem;color:#93c5fd;">'
        '<strong>PySpark & Spark Classic → Serverless migration</strong> is available through '
        'the <strong>Syren Server to Serverless Migration Platform</strong>. '
        '<a href="https://syren-s2s-platform-204242957656703.3.azure.databricksapps.com/#home" '
        'target="_blank" style="color:#1d4ed8;font-weight:600;">Learn more →</a>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── CONFIG COLUMNS ────────────────────────────────────────────────────────
    tp_left, tp_right = st.columns([1, 1], gap="large")

    with tp_left:
        # Step 1 — Dialect
        st.markdown("""
        <div class="card-title">
            <span class="step-num teal">1</span> Source Dialect &amp; Target
        </div>
        """, unsafe_allow_html=True)

        selected_dialect_name = st.selectbox(
            "Source dialect",
            options=list(TRANSPILER_DIALECTS.keys()),
            key="tp_dialect",
            label_visibility="collapsed",
        )
        dialect_info = TRANSPILER_DIALECTS[selected_dialect_name]
        dialect_cli   = dialect_info["cli"]
        dialect_exts  = dialect_info["exts"]

        dial_tags_sel = "".join(f'<span class="ext-tag teal">.{e}</span>' for e in dialect_exts)
        if dialect_info.get("oozie"):
            _engine_badge = (
                '<span style="font-size:0.72rem;background:rgba(251,191,36,0.06);color:#fbbf24;'
                'border:1px solid rgba(251,191,36,0.2);border-radius:6px;padding:2px 7px;font-weight:600;">'
                'Built-in engine (oozie_converter) — outputs Databricks Workflow JSON</span>'
            )
        elif dialect_info.get("ssrs"):
            _engine_badge = (
                '<span style="font-size:0.72rem;background:rgba(251,191,36,0.06);color:#fbbf24;'
                'border:1px solid rgba(251,191,36,0.2);border-radius:6px;padding:2px 7px;font-weight:600;">'
                'Built-in engine (ssrs_converter) — outputs SQL notebooks + assessment JSON</span>'
            )
        elif dialect_info.get("custom"):
            _engine_badge = (
                '<span style="font-size:0.72rem;background:rgba(251,191,36,0.06);color:#fbbf24;'
                'border:1px solid rgba(251,191,36,0.2);border-radius:6px;padding:2px 7px;font-weight:600;">'
                'Built-in engine (sqlglot) — no Databricks CLI needed</span>'
            )
        elif dialect_info.get("sparksql_only"):
            _engine_badge = (
                '<span style="font-size:0.72rem;background:#e0f2fe;color:#0369a1;'
                'border:1px solid #7dd3fc;border-radius:6px;padding:2px 7px;font-weight:600;">'
                'BladeBridge — SparkSQL output only</span>'
            )
        else:
            _engine_badge = ""
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:10px;
                    padding:0.85rem 1.25rem;margin-top:0.5rem;margin-bottom:1rem;">
            <div style="font-size:0.78rem;color:#94a3b8;font-weight:600;margin-bottom:0.4rem;">
                ACCEPTED FILE TYPES
            </div>
            <div class="ext-wrap">{dial_tags_sel}</div>
            {"<div style='margin-top:0.5rem;'>" + _engine_badge + "</div>" if _engine_badge else ""}
        </div>
        """, unsafe_allow_html=True)

        if dialect_info.get("oozie"):
            # Oozie always outputs Databricks Workflow JSON — no target selector needed
            target_cli = "OOZIE_WORKFLOW"
            selected_target_label = "Databricks Workflow JSON"
            st.markdown(
                '<div style="background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.2);border-radius:8px;'
                'padding:0.6rem 1rem;font-size:0.82rem;color:#67e8f9;font-weight:500;">'
                'Output: <strong>Databricks Workflow JSON</strong> — deployable via '
                '<code>/api/2.1/jobs ,please use button below - Create Databricks Workflow</code></div>',
                unsafe_allow_html=True,
            )
        elif dialect_info.get("ssrs"):
            # SSRS custom engine outputs SQL notebooks + assessment JSON
            target_cli = "SSRS_NOTEBOOKS"
            selected_target_label = "SQL Notebooks + Assessment JSON"
            st.markdown(
                '<div style="background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.2);border-radius:8px;'
                'padding:0.6rem 1rem;font-size:0.82rem;color:#67e8f9;font-weight:500;">'
                'Output: <strong>SQL Notebooks + Assessment JSON</strong> — '
                'one .sql notebook and one assessment.json per report</div>',
                unsafe_allow_html=True,
            )
        elif dialect_info.get("sparksql_only"):
            # BladeBridge SSIS only supports SparkSQL — no target picker needed
            target_cli = "SPARKSQL"
            selected_target_label = "SparkSQL  (SQL-compatible Spark)"
            st.markdown(
                '<div style="background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.2);border-radius:8px;'
                'padding:0.6rem 1rem;font-size:0.82rem;color:#67e8f9;font-weight:500;">'
                'Output: <strong>SparkSQL</strong> — SSIS packages convert to SparkSQL only '
                '(BladeBridge limitation)</div>',
                unsafe_allow_html=True,
            )
        elif dialect_info.get("custom"):
            # HiveSQL custom engine supports both SparkSQL and PySpark output formats
            selected_target_label = st.selectbox(
                "Output format",
                options=list(TRANSPILER_TARGETS.keys()),
                key="tp_target",
                label_visibility="collapsed",
            )
            target_cli = TRANSPILER_TARGETS[selected_target_label]
            st.markdown(
                '<div style="background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.2);border-radius:8px;'
                'padding:0.6rem 1rem;font-size:0.82rem;color:#67e8f9;font-weight:500;">'
                'SQL output uses <strong>Databricks SQL dialect</strong> — '
                'runs directly on Databricks SQL Warehouses &amp; clusters</div>',
                unsafe_allow_html=True,
            )
        else:
            selected_target_label = st.selectbox(
                "Target technology",
                options=list(TRANSPILER_TARGETS.keys()),
                key="tp_target",
                label_visibility="collapsed",
            )
            target_cli = TRANSPILER_TARGETS[selected_target_label]

        # Optional settings (not applicable for Oozie, SSRS, or sparksql_only)
        if not dialect_info.get("oozie") and not dialect_info.get("sparksql_only") and not dialect_info.get("ssrs"):
            with st.expander("Advanced options", expanded=False):
                catalog_name = st.text_input(
                    "Catalog name (optional)",
                    value="",
                    key="tp_catalog",
                    placeholder="e.g. main",
                    help="Unity Catalog catalog name to use in generated code.",
                )
                schema_name = st.text_input(
                    "Schema / database name (optional)",
                    value="",
                    key="tp_schema",
                    placeholder="e.g. default",
                    help="Target schema name to prefix output objects.",
                )
                skip_val = st.toggle(
                    "Skip validation",
                    value=True,
                    key="tp_skip_val",
                    help="Pass --skip-validation true to bypass pre-flight checks (recommended for large migrations).",
                )

    with tp_right:
        # Step 2 — Files
        st.markdown("""
        <div class="card-title">
            <span class="step-num teal">2</span> Upload Source Files
        </div>
        """, unsafe_allow_html=True)

        tp_is_zip = False

        if "tp_ws_path" not in st.session_state:
            st.session_state["tp_ws_path"] = "/"
        if "tp_ws_selected_files" not in st.session_state:
            st.session_state["tp_ws_selected_files"] = []
        if "tp_ws_items" not in st.session_state:
            st.session_state["tp_ws_items"] = []
        if "tp_last_loaded_path" not in st.session_state:
            st.session_state["tp_last_loaded_path"] = None

        tab1, tab2 = st.tabs(["Upload Files", "Databricks Workspace"])

        tp_files = []

        with tab1:
            tp_mode = st.radio(
                "Upload mode",
                ["Individual files", "ZIP archive"],
                horizontal=True,
                key="tp_upload_mode",
                label_visibility="collapsed",
            )
            tp_is_zip = tp_mode == "ZIP archive"

            if tp_is_zip:
                tp_raw = st.file_uploader(
                    "Drop your ZIP here",
                    type=["zip"],
                    key="tp_zip_uploader",
                    label_visibility="collapsed",
                    help="ZIP will be extracted before transpiling.",
                )
                tp_files = [tp_raw] if tp_raw else []
            else:
                tp_files = st.file_uploader(
                    "Drop source files here",
                    type=dialect_exts,
                    accept_multiple_files=True,
                    key="tp_file_uploader",
                    label_visibility="collapsed",
                    help=f"Accepted: {', '.join('.' + e for e in dialect_exts)}",
                )

            if tp_files:
                tp_total_kb = sum(f.size for f in tp_files) / 1024
                st.markdown(f"""
                <div style="background:rgba(34,197,94,0.06);border:1px solid rgba(34,197,94,0.2);border-radius:10px;
                            padding:0.85rem 1.1rem;margin-top:0.5rem;">
                    <div style="font-weight:700;color:#4ade80;font-size:0.95rem;">
                        {len(tp_files)} file(s) ready · {tp_total_kb:.1f} KB
                    </div>
                </div>
                """, unsafe_allow_html=True)
                with st.expander("View uploaded files", expanded=False):
                    for f in tp_files:
                        st.markdown(f"`{f.name}` &nbsp; <span style='color:#9ca3af;font-size:0.8rem'>{f.size:,} bytes</span>", unsafe_allow_html=True)
                st.session_state["tp_source_mode"] = "upload"
            else:
                st.markdown("""
                <div style="background:rgba(255,255,255,0.03);border:2px dashed rgba(255,255,255,0.08);border-radius:12px;
                            padding:2rem 1.5rem;text-align:center;margin-top:0.5rem;color:#9ca3af;">
                    <div style="font-size:2rem;margin-bottom:0.5rem;">&#128193;</div>
                    <div style="font-weight:600;color:#94a3b8;margin-bottom:0.25rem;">No files selected yet</div>
                    <div style="font-size:0.82rem;">Upload source files to begin transpilation</div>
                </div>
                """, unsafe_allow_html=True)

        with tab2:
            from modules.databricks_service import DatabricksClient

            st.markdown("#### Browse Workspace")

            try:
                dbx = DatabricksClient.from_app_context()
                current_path = st.session_state["tp_ws_path"]
                st.text_input("Current Path", value=current_path, disabled=True)

                if (
                    "tp_ws_items" not in st.session_state
                    or st.session_state.get("tp_last_loaded_path") != current_path
                ):
                    items = dbx.list_workspace_items(current_path)
                    if isinstance(items, dict) and "error" in items:
                        st.error(items["error"])
                        st.session_state["tp_ws_items"] = []
                    else:
                        st.session_state["tp_ws_items"] = items
                    st.session_state["tp_last_loaded_path"] = current_path

                items = st.session_state.get("tp_ws_items", [])

                # Show navigation buttons if not at root
                if current_path != "/":
                    parent = "/".join(current_path.rstrip("/").split("/")[:-1]) or "/"
                    back_col, home_col = st.columns([1, 1], gap="small")
                    with back_col:
                        if st.button("Back", key="tp_back"):
                            st.session_state["tp_ws_path"] = parent
                            st.session_state.pop("tp_ws_items", None)
                            st.session_state.pop("tp_last_loaded_path", None)
                            st.rerun()
                    with home_col:
                        if st.button("Home", key="tp_home"):
                            st.session_state["tp_ws_path"] = "/"
                            st.session_state.pop("tp_ws_items", None)
                            st.session_state.pop("tp_last_loaded_path", None)
                            st.rerun()

                if items:
                    dirs = [o for o in items if o.get("object_type") == "DIRECTORY"]
                    files = [o for o in items if o.get("object_type") in ["NOTEBOOK", "FILE"]]

                    # 🔥 REAL SCROLL CONTAINER
                    container = st.container(height=350)

                    with container:
                        if dirs:
                            st.markdown("##### Folders")
                            for obj in dirs:
                                path = obj.get("path")
                                name = path.rstrip("/").split("/")[-1]
                                button_key = make_widget_key("tp_dir", path)
                                if st.button(f"{name}", key=button_key):
                                    st.session_state["tp_ws_path"] = path
                                    st.session_state.pop("tp_ws_items", None)
                                    st.session_state.pop("tp_last_loaded_path", None)
                                    st.rerun()

                        if files:
                            st.markdown("##### Select files")
                            selected_paths = set(st.session_state.get("tp_ws_selected_files", []))
                            for obj in files:
                                path = obj.get("path")
                                if any(path.lower().endswith(f".{ext}") for ext in dialect_exts):
                                    checkbox_key = make_widget_key("tp_ws", path)
                                    checked = st.checkbox(path, value=(path in selected_paths), key=checkbox_key)
                                    if checked:
                                        selected_paths.add(path)
                                    else:
                                        selected_paths.discard(path)

                            st.session_state["tp_ws_selected_files"] = sorted(selected_paths)
                            if selected_paths:
                                st.success(f"✅ {len(selected_paths)} file(s) selected")
                                st.session_state["tp_source_mode"] = "workspace"
                            else:
                                st.info("No files selected")
                        else:
                            st.info("No valid files in this folder")

                else:
                    st.info("No items found in this path")
            except Exception as e:
                st.error(f"Workspace error: {str(e)}")

        st.markdown("""
        <div style="font-size:0.78rem;color:#9ca3af;margin-top:0.75rem;line-height:1.5;">
            <strong>Tip:</strong> Use <em>ZIP archive</em> mode to upload an entire
            source project folder at once.
        </div>
        """, unsafe_allow_html=True)

    # ── RUN BUTTON ────────────────────────────────────────────────────────────
    st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)

    tp_ws_selected_files = st.session_state.get("tp_ws_selected_files", [])
    tp_has_source = bool(tp_files or tp_ws_selected_files)

    _, tp_btn_col, _ = st.columns([2, 1, 2])
    with tp_btn_col:
        tp_run = st.button(
            "Transpile Code",
            width="content",
            disabled=not tp_has_source,
            key="run_transpile",
        )

    if not tp_has_source:
        st.markdown(
            "<div style='text-align:center;color:#9ca3af;font-size:0.85rem;margin-top:0.25rem'>"
            "Upload at least one source file or select Databricks workspace files to run transpilation."
            "</div>",
            unsafe_allow_html=True,
        )

    # ── TRANSPILATION EXECUTION ───────────────────────────────────────────────
    if tp_run and tp_has_source:
        tp_src_dir = tp_out_dir = None
        clear_transpile_output_state()
        try:
            with st.status("Transpiling…", expanded=True) as tp_status:
                if tp_files:
                    st.write(f"Preparing **{len(tp_files)}** file(s)…")
                    tp_src_dir = save_uploaded_files(tp_files, tp_is_zip)
                else:
                    tp_ws_selected_files = st.session_state.get("tp_ws_selected_files", [])
                    st.write(f"Preparing **{len(tp_ws_selected_files)}** workspace file(s)…")
                    tp_src_dir = fetch_workspace_files_to_local(tp_ws_selected_files)

                n_src, b_src = count_files(tp_src_dir)
                st.write(f"&nbsp;&nbsp;→ {n_src} file(s) staged ({b_src/1024:.1f} KB)")

                tp_out_dir = tempfile.mkdtemp(prefix="lb_tp_out_")
                tp_err_file = os.path.join(tp_out_dir, "transpile_errors.log")

                st.write(f"Transpiling **{selected_dialect_name}** → **{selected_target_label.split('(')[0].strip()}**…")
                t0 = time.time()
                if dialect_info.get("oozie"):
                    # Built-in Oozie → Databricks Workflow JSON converter
                    tp_ok, tp_stdout, tp_stderr, _oozie_links = run_oozie_converter(
                        src_dir=tp_src_dir,
                        out_dir=tp_out_dir,
                        err_file=tp_err_file,
                    )
                    st.session_state["tp_oozie_links"] = _oozie_links
                    for lk in _oozie_links:
                        if lk["workflow"]:
                            st.write(f"**{lk['coordinator']}** → linked to **{lk['workflow']}** via `run_job_task`")
                        else:
                            st.write(f"**{lk['coordinator']}** → no workflow matched — add `run_job_task` manually")
                elif dialect_info.get("ssrs"):
                    # Built-in SSRS → SQL Notebooks + Assessment JSON converter
                    tp_ok, tp_stdout, tp_stderr, _ssrs_results = run_ssrs_converter(
                        src_dir=tp_src_dir,
                        out_dir=tp_out_dir,
                        err_file=tp_err_file,
                    )
                    st.session_state["tp_ssrs_results"] = _ssrs_results
                    n_nb = len(_ssrs_results.get("notebooks", {}))
                    n_as = len(_ssrs_results.get("assessments", {}))
                    auto_conv = sum(
                        1 for a in _ssrs_results.get("assessments", {}).values()
                        if a.get("auto_convertible")
                    )
                    st.write(
                        f"**{n_as}** report(s) assessed · "
                        f"**{auto_conv}/{n_as}** auto-convertible · "
                        f"**{n_nb}** SQL notebook(s) generated"
                    )
                elif dialect_info.get("custom"):
                    # Custom in-process transpiler (HiveSQL via sqlglot → Databricks SQL)
                    # Get LLM credentials from environment or session state
                    llm_endpoint = os.environ.get("LLM_ENDPOINT", "") or st.session_state.get("sb_llm_endpoint", "")
                    llm_api_key = os.environ.get("LLM_API_KEY", "") or st.session_state.get("sb_llm_api_key", "")
                    
                    tp_ok, tp_stdout, tp_stderr = run_hive_transpiler(
                        src_dir=tp_src_dir,
                        out_dir=tp_out_dir,
                        err_file=tp_err_file,
                        target=target_cli,
                        catalog=st.session_state.get("tp_catalog", ""),
                        schema=st.session_state.get("tp_schema", ""),
                        llm_endpoint=llm_endpoint,
                        llm_api_key=llm_api_key,
                    )
                    llm_summary = extract_llm_enhancement_summary(tp_stdout)
                    if llm_summary:
                        st.write(f"&nbsp;&nbsp;-> {llm_summary}")
                else:
                    tp_ok, tp_stdout, tp_stderr = run_transpiler(
                        src_dir=tp_src_dir,
                        out_dir=tp_out_dir,
                        err_file=tp_err_file,
                        dialect=dialect_cli,
                        target=target_cli,
                        catalog=st.session_state.get("tp_catalog", ""),
                        schema=st.session_state.get("tp_schema", ""),
                        skip_validation=st.session_state.get("tp_skip_val", True),
                    )
                elapsed = time.time() - t0
                st.write(f"&nbsp;&nbsp;→ Completed in **{elapsed:.1f}s**")

                n_out, b_out = count_files(tp_out_dir)

                if tp_ok and n_out > 0:
                    tp_status.update(label=f"✅ Transpilation complete! {n_out} output file(s)", state="complete", expanded=False)
                elif n_out == 0:
                    tp_status.update(label="No output files generated — check log below", state="error", expanded=True)
                else:
                    tp_status.update(label="Completed with warnings — see log below", state="complete", expanded=False)

            st.session_state["tp_stdout"] = tp_stdout
            st.session_state["tp_stderr"] = tp_stderr
            llm_counts = extract_llm_enhancement_counts(tp_stdout) or (0, 0, 0)
            store_transpile_output_state(tp_out_dir, {
                "n_src": n_src,
                "b_out": b_out,
                "n_out": n_out,
                "elapsed": elapsed,
                "dialect_cli": dialect_cli,
                "target_cli": target_cli,
                "selected_dialect_name": selected_dialect_name,
                "selected_target_label": selected_target_label,
                "is_oozie": bool(dialect_info.get("oozie")),
                "oozie_links": st.session_state.get("tp_oozie_links", []),
                "is_ssrs": bool(dialect_info.get("ssrs")),
                "ssrs_results": st.session_state.get("tp_ssrs_results", {}),
                "llm_files_sent": llm_counts[0],
                "llm_statements_replaced": llm_counts[1],
                "llm_failures": llm_counts[2],
            })

            # ── Logs ─────────────────────────────────────────────────────────
            if tp_stdout:
                with st.expander("Transpiler output log"):
                    tp_log_container = st.container(height=400)
                    with tp_log_container:
                        st.markdown("<div class='output-block'>", unsafe_allow_html=True)
                        st.code(tp_stdout, language="text")
                        st.markdown("</div>", unsafe_allow_html=True)
            if tp_stderr and not tp_ok:
                with st.expander("Errors / warnings"):
                    tp_error_container = st.container(height=400)
                    with tp_error_container:
                        st.markdown("<div class='output-block'>", unsafe_allow_html=True)
                        st.code(tp_stderr, language="text")
                        st.markdown("</div>", unsafe_allow_html=True)

            # ── Results ──────────────────────────────────────────────────────
            if n_out > 0:
                st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)

                # Dialect-specific notes shown with results
                if dialect_info.get("oozie"):
                    oozie_links = st.session_state.get("tp_oozie_links", [])
                    if oozie_links:
                        st.markdown("**Coordinator → Workflow Links**")
                        for lk in oozie_links:
                            if lk["workflow"]:
                                st.success(f"{lk['coordinator']} → linked to **{lk['workflow']}** via `run_job_task`")
                            else:
                                st.warning(f"{lk['coordinator']} → no workflow matched — add `run_job_task` manually")
                    st.markdown("**Oozie Conversion Notes**")
                    with st.expander("ℹ️ View details"):
                        st.markdown("""
                    - **Workflow jobs** are created as independent Databricks jobs with a full task graph.
                    - **Coordinator jobs** trigger workflow jobs via `run_job_task`. If a matching workflow XML was uploaded, the `job_id` sentinel (`{{job_id:<name>}}`) is **automatically replaced** with the real Databricks job ID once you create the workflow job — create workflow jobs first, then coordinator jobs.
                    - **Schedule** is set to `PAUSED` by default — activate after verifying the job in the Databricks Workflow editor.
                    - **EL expressions** (`${variable}`) are preserved as-is — replace them with Databricks job parameters or widgets.
                    - **Bundle workflows** are not supported — convert each coordinator individually.
                    - **Parallel execution (fork/join)** may require manual validation to ensure correct task dependencies.
                    - **Error handling** logic is simplified — validate failure paths and retry behavior.
                    - **Cluster config** is not automatically optimized — review node type, Spark version, and worker count.
                    """)
                    render_oozie_workflow_create_section(tp_out_dir, "main")

                elif dialect_info.get("ssrs"):
                    ssrs_results = st.session_state.get("tp_ssrs_results", {})
                    assessments = ssrs_results.get("assessments", {})
                    notebooks = ssrs_results.get("notebooks", {})
                    if assessments:
                        n_auto = sum(1 for a in assessments.values() if a.get("auto_convertible"))
                        st.markdown(
                            f'<div style="background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.2);border-radius:8px;'
                            f'padding:0.75rem 1rem;margin-bottom:0.75rem;font-size:0.88rem;color:#67e8f9;">'
                            f'<strong>{len(assessments)}</strong> report(s) assessed · '
                            f'<strong>{n_auto}/{len(assessments)}</strong> auto-convertible · '
                            f'<strong>{len(notebooks)}</strong> SQL notebook(s) generated</div>',
                            unsafe_allow_html=True,
                        )
                    st.markdown("**SSRS Conversion Notes**")
                    with st.expander("ℹ️ View details"):
                        st.markdown("""
                    - **SQL Notebooks** (`.sql`) contain one SQL cell per dataset — run them directly on a Databricks SQL Warehouse.
                    - **Assessment JSON** files list data sources, datasets, report items, parameters, and any VB.NET code blocks.
                    - **Stored procedures** are commented out in the notebook — migrate the proc logic manually.
                    - **T-SQL functions** (GETDATE, ISNULL, TOP N, etc.) are flagged in warnings — update to Spark SQL equivalents (`current_timestamp()`, `ifnull()`, `LIMIT n`).
                    - **VB.NET code blocks** are preserved as comments — rewrite as Python UDFs or SQL expressions.
                    - **Parameters** appear as `-- DECLARE` comments — replace with Databricks widgets (`dbutils.widgets`) or job parameters.
                    - **Report layout** (visual formatting, charts) is not converted — use Databricks Dashboards or Lakeview SQL for visual output.
                    - Use the **Download All Output Files** button below to get the ZIP, or upload directly to Databricks workspace.
                    """)

                st.markdown("""
                <div class="results-header">
                    <div class="results-title">
                        Transpiled Output <span class="success-pill">Ready</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                #METRICS TAB  
                # Decide number of columns
                render_transpile_metrics(n_src=n_src,n_out=n_out,elapsed=elapsed,llm_counts=llm_counts)
                
                # ZIP download
                zip_bytes = zip_directory(tp_out_dir)
                zip_name = f"transpiled_{dialect_cli}_{target_cli.lower()}.zip"
                dl_col, info_col = st.columns([1, 2])
                with dl_col:
                    st.download_button(
                        label="Download All Output Files",
                        data=zip_bytes,
                        file_name=zip_name,
                        mime="application/zip",
                        key="tp_download_all_output_inline",
                        width='stretch',
                    )
                with info_col:
                    st.markdown(f"""
                    <div class="info-box">
                        <strong>{zip_name}</strong>
                        <p>{n_out} converted file(s) · {b_out/1024:.1f} KB total</p>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

                st.session_state["tp_upload_dest"] = st.session_state.get("tp_upload_dest", "/Shared/transpiler_output")
                upload_dest = st.text_input(
                    "Upload output to Databricks workspace folder",
                    value=st.session_state["tp_upload_dest"],
                    key="tp_upload_dest",
                    help="Enter the target Databricks workspace folder where transpiled files will be uploaded.",
                )
                if upload_dest and not upload_dest.startswith("/"):
                    upload_dest = "/" + upload_dest
                    st.session_state["tp_upload_dest"] = upload_dest

                if st.button("Upload All Output Files to Databricks", key="tp_upload_output", width='stretch'):
                    try:
                        ok, upload_errors = upload_directory_to_workspace(tp_out_dir, upload_dest)
                        if ok:
                            st.success(f"✅ Uploaded {n_out} files to {upload_dest}")
                        else:
                            st.error("Upload failed. See details below.")
                            for msg in upload_errors:
                                st.write(f"- {msg}")
                    except Exception as e:
                        st.error(f"Upload error: {e}")

                # File tree
                st.markdown("**Output File Tree**")
                tree_html, _, _ = build_file_tree_html(tp_out_dir)
                st.markdown(f'<div class="file-tree">{tree_html}</div>', unsafe_allow_html=True)

                st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

                # Inline preview of each output file
                output_files = sorted(
                    [p for p in Path(tp_out_dir).rglob("*") if p.is_file() and p.name != "transpile_errors.log"],
                    key=lambda p: str(p)
                )
                if output_files:
                    st.markdown("**File Preview**")
                    preview_tabs = st.tabs([p.name for p in output_files[:20]])
                    for tab, fp in zip(preview_tabs, output_files[:20]):
                        with tab:
                            try:
                                content = fp.read_text(encoding="utf-8", errors="replace")
                                _lang_map = {".py": "python", ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".xml": "xml"}
                                lang = _lang_map.get(fp.suffix.lower(), "sql")
                                st.code(content, language=lang)
                            except Exception as e:
                                st.warning(f"Could not read file: {e}")
                    if len(output_files) > 20:
                        st.caption(f"Showing first 20 of {len(output_files)} files. Download the ZIP to view all.")

                # Error log
                if os.path.exists(tp_err_file):
                    err_content = Path(tp_err_file).read_text(encoding="utf-8", errors="replace").strip()
                    if err_content:
                        with st.expander("Transpilation error log", expanded=False):
                            st.code(err_content, language="text")
                    else:
                        st.success("✅ No transpilation errors logged.")

            else:
                st.error(
                    "Transpilation produced no output files. "
                    "Common causes: the `databricks` CLI is not installed, "
                    "lakebridge is not set up, or authentication is not configured. "
                    "Check the logs above for details."
                )

        finally:
            if tp_src_dir and os.path.exists(tp_src_dir):
                shutil.rmtree(tp_src_dir, ignore_errors=True)

    if (
        selected_page == "Transpiler"
        and not tp_run
        and st.session_state.get("tp_out_dir")
        and os.path.exists(st.session_state["tp_out_dir"])
    ):
        render_transpile_output_section()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE — SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

elif selected_page == "Settings":

    st.markdown("""
    <div style="max-width:680px;margin-bottom:1.5rem;">
        <p style="color:#94a3b8;font-size:0.92rem;line-height:1.65;margin:0;">
            SyrenBridge calls the Databricks CLI to run analysis and transpilation.
            Credentials are held in session memory only — never written to disk or shared between users.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Auto-detect context ───────────────────────────────────────────────────
    db_host_env = os.environ.get("DATABRICKS_HOST", "")
    db_token_env = os.environ.get("DATABRICKS_TOKEN", "")

    if db_host_env and db_token_env:
        st.markdown(
            f'<div style="background:rgba(34,197,94,0.06);border:1px solid rgba(34,197,94,0.2);border-radius:8px;'
            f'padding:0.85rem 1.1rem;margin-bottom:1.5rem;font-size:0.87rem;color:#4ade80;">'
            f'<strong>Ready</strong> — workspace <code>{db_host_env}</code> and token are '
            f'already present in the environment. '
            f'You do not need to fill anything in below. '
            f'Use the fields only if you want to override for this session.'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif db_host_env:
        st.markdown(
            f'<div style="background:rgba(251,191,36,0.06);border:1px solid rgba(251,191,36,0.2);border-radius:8px;'
            f'padding:0.85rem 1.1rem;margin-bottom:1.5rem;font-size:0.87rem;color:#fbbf24;">'
            f'<strong>Workspace URL detected</strong> (<code>{db_host_env}</code>) but no token '
            f'found in environment. Enter a token below to continue.'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);border-radius:8px;'
            'padding:0.85rem 1.1rem;margin-bottom:1.5rem;font-size:0.87rem;color:#f87171;">'
            '<strong>No credentials detected.</strong> Enter your Databricks workspace URL and '
            'Personal Access Token below. The Analyzer and Transpiler require a connected workspace.<br><br>'
            '<strong>On Databricks Apps:</strong> this is handled automatically — no input needed.'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Credential form ───────────────────────────────────────────────────────
    # cfg_col1, cfg_col2 = st.columns([3, 2], gap="large")

    # with cfg_col1:
    st.markdown("##### Connection Details — Host + Token ")

    st.text_input(
        "Databricks Workspace URL",
        key="sb_db_host",
        placeholder="https://adb-XXXXXXXXXXXX.XX.azuredatabricks.net",
        help="The full URL of your Databricks workspace, e.g. https://adb-xxxxxxxxxx.xx.azuredatabricks.net",
    )

    st.text_input(
        "Personal Access Token (PAT)",
        key="sb_db_token",
        type="password",
        placeholder="dapiXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        help="Generate a token in Databricks → User Settings → Developer → Access Tokens.",
    )
    status_col1, status_col2, status_col3 = st.columns([1, 1, 1], gap="large")
    save_clicked = status_col1.button("Save connection", key="save_db_connection")
    test_workspace_clicked = status_col2.button("Test workspace connection", key="test_workspace_connection")
    clear_clicked = status_col3.button("Clear workspace credentials", key="clear_db_connection")
    
    if clear_clicked:
        clear_databricks_credentials()
        st.success("✅ Databricks credentials cleared")
        st.rerun()
    
    if save_clicked:
        try:
            set_databricks_env(st.session_state.get("sb_db_host"),
            st.session_state.get("sb_db_token"))
            clear_databricks_workspace_selection_state()
            st.success("✅ Connection configured successfully")
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
            st.caption(
            "Credentials are held in session state only. "
            "They are injected into the subprocess environment for Analyzer and Transpiler calls "
            "and are not stored to disk or shared between users."
        )
        except ValueError as e:
            st.error(str(e))
        # sync_databricks_env_from_session_state()
        

    if test_workspace_clicked:
        # sync_databricks_env_from_session_state()
        host = st.session_state.get("sb_db_host", "").strip()
        token = st.session_state.get("sb_db_token", "").strip()
        ok, message = test_databricks_workspace_connection(host, token)
        if ok:
            st.success(f"✅ {message}")
        else:
            st.error(f"❌ {message}")

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        ##### Azure / GCP / AWS
        SyrenBridge works with any Databricks workspace. The workspace URL format varies:
        - **Azure:** `https://adb-XXXX.XX.azuredatabricks.net`
        - **AWS:** `https://XXXX.cloud.databricks.com`
        - **GCP:** `https://XXXX.gcp.databricks.com`
        """
    )

    st.markdown("---")

    # ── LLM Credentials ───────────────────────────────────────────────────────
    st.markdown("##### LLM Credentials — Endpoint + API Key")

    # Auto-detect LLM context from environment
    llm_endpoint_env = os.environ.get("LLM_ENDPOINT", "")
    llm_api_key_env = os.environ.get("LLM_API_KEY", "")

    if llm_endpoint_env and llm_api_key_env:
        st.markdown(
            f'<div style="background:rgba(34,197,94,0.06);border:1px solid rgba(34,197,94,0.2);border-radius:8px;'
            f'padding:0.85rem 1.1rem;margin-bottom:1.5rem;font-size:0.87rem;color:#4ade80;">'
            f'<strong>Ready</strong> — LLM endpoint <code>{llm_endpoint_env}</code> and API key are '
            f'already present in the environment. '
            f'You do not need to fill anything in below. '
            f'Use the fields only if you want to override for this session.'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif llm_endpoint_env:
        st.markdown(
            f'<div style="background:rgba(251,191,36,0.06);border:1px solid rgba(251,191,36,0.2);border-radius:8px;'
            f'padding:0.85rem 1.1rem;margin-bottom:1.5rem;font-size:0.87rem;color:#fbbf24;">'
            f'<strong>LLM Endpoint detected</strong> (<code>{llm_endpoint_env}</code>) but no API key '
            f'found in environment. Enter an API key below to continue.'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:8px;'
            'padding:0.85rem 1.1rem;margin-bottom:1.5rem;font-size:0.87rem;color:#94a3b8;">'
            '<strong>LLM credentials are optional.</strong> They are used for the LLM-powered '
            'transpiler (when enabled). If not provided, the standard transpiler will be used.<br><br>'
            '<strong>Supported providers:</strong> OpenAI, Azure OpenAI, Anthropic, Cohere, and other '
            'compatible LLM endpoints.'
            '</div>',
            unsafe_allow_html=True,
        )

    st.text_input(
        "LLM Endpoint URL",
        key="sb_llm_endpoint",
        placeholder="https://adb-<workspace-id>.azuredatabricks.net/serving-endpoints/databricks-<model-name>/invocations",
        help="The full URL of your LLM API endpoint. For OpenAI, use https://api.openai.com/v1",
    )

    st.text_input(
        "LLM API Key",
        key="sb_llm_api_key",
        type="password",
        placeholder="dap-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        help="Your LLM API key. For OpenAI, get it from https://platform.openai.com/api-keys",
    )

    llm_col1, llm_col2, llm_col3 = st.columns([1, 1, 1], gap="large")
    llm_save_clicked = llm_col1.button("Save LLM connection", key="save_llm_connection")
    llm_test_clicked = llm_col2.button("Test LLM connection", key="test_llm_connection")
    llm_clear_clicked = llm_col3.button("Clear LLM credentials", key="clear_llm_connection")

    if llm_clear_clicked:
        clear_llm_credentials()
        st.success("✅ LLM credentials cleared")
        st.rerun()

    if llm_save_clicked:
        try:
            set_llm_env(
                st.session_state.get("sb_llm_endpoint"),
                st.session_state.get("sb_llm_api_key")
            )
            st.success("✅ LLM connection configured successfully")
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
            st.caption(
                "LLM credentials are held in session state only. "
                "They are injected into the subprocess environment for LLM transpiler calls "
                "and are not stored to disk or shared between users."
            )
        except ValueError as e:
            st.error(str(e))

    if llm_test_clicked:
        endpoint = st.session_state.get("sb_llm_endpoint", "").strip()
        api_key = st.session_state.get("sb_llm_api_key", "").strip()
        ok, message = test_llm_connection(endpoint, api_key)
        if ok:
            st.success(f"✅ {message}")
        else:
            st.error(f"❌ {message}")

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        ##### Supported LLM Providers
         **Databricks serving models:** `https://adb-<workspace-id>.azuredatabricks.net/serving-endpoints/databricks-<model-name>/invocations` (Use claude sonnet )
       
        """
    )


