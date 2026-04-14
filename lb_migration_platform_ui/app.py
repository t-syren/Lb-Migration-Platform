"""
SyrenBridge Platform  —  v4
Full Streamlit app wrapping both:
  • `databricks labs lakebridge analyze`   (Analyzer tab)
  • `databricks labs lakebridge transpile` (Transpiler tab)
Designed to be hosted on Databricks Apps.
"""

import io
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.oozie_converter import workflow_to_json, parse_workflow

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

CATEGORY_ICON = {"SQL": "🗄️", "ETL": "🔄", "Code": "💻"}

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
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
/* ── Fonts & base ─────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ── Hide Streamlit chrome ───────────────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.75rem; padding-bottom: 3rem; max-width: 1100px; }

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #0f172a !important;
    border-right: 1px solid #1e293b !important;
    min-width: 210px !important;
    max-width: 230px !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div { color: #94a3b8; }
[data-testid="stSidebar"] hr { border-color: #1e293b !important; }
[data-testid="stSidebar"] .stRadio > label { display: none; }
[data-testid="stSidebar"] .stRadio > div {
    display: flex; flex-direction: column; gap: 2px;
}
[data-testid="stSidebar"] .stRadio label {
    display: flex !important; align-items: center;
    padding: 0.55rem 0.85rem !important; border-radius: 7px !important;
    font-size: 0.88rem !important; font-weight: 500 !important;
    color: #94a3b8 !important; cursor: pointer;
    transition: background 0.12s, color 0.12s;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: #1e293b !important; color: #e2e8f0 !important;
}
[data-testid="stSidebar"] .stRadio label[data-checked="true"],
[data-testid="stSidebar"] .stRadio input:checked + label {
    background: #1e3a5f !important; color: #93c5fd !important; font-weight: 600 !important;
}

/* ── Page header ─────────────────────────────────────────────────────────── */
.page-hdr {
    display: flex; align-items: flex-start; gap: 0.9rem;
    border-bottom: 1px solid #e2e8f0; padding-bottom: 1.25rem; margin-bottom: 2rem;
}
.page-hdr-icon {
    width: 44px; height: 44px; border-radius: 10px;
    background: #0f172a; display: flex; align-items: center;
    justify-content: center; font-size: 1.2rem; flex-shrink: 0;
}
.page-hdr h1 {
    font-size: 1.45rem; font-weight: 800; color: #0f172a;
    margin: 0 0 0.1rem; letter-spacing: -0.025em; line-height: 1.2;
}
.page-hdr p { color: #64748b; font-size: 0.82rem; margin: 0; }

/* ── Cards ───────────────────────────────────────────────────────────────── */
.card {
    background: #fff; border: 1px solid #e2e8f0;
    border-radius: 12px; padding: 1.4rem 1.6rem;
    box-shadow: 0 1px 3px rgba(15,23,42,0.04);
}
.card-title {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #94a3b8; margin-bottom: 1rem;
    display: flex; align-items: center; gap: 0.4rem;
}

/* ── Step indicator ──────────────────────────────────────────────────────── */
.step-num {
    width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.78rem; font-weight: 700;
    background: #0f172a; color: white; margin-right: 0.45rem;
}
.step-num.teal { background: #0f766e; }

/* ── Extension tags ──────────────────────────────────────────────────────── */
.ext-wrap { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 0.5rem; }
.ext-tag {
    background: #f8fafc; color: #475569;
    border: 1px solid #e2e8f0; border-radius: 4px;
    padding: 2px 7px; font-size: 0.72rem; font-family: 'Courier New', monospace;
    font-weight: 600;
}
.ext-tag.teal { background: #f0fdfa; color: #0f766e; border: 1px solid #99f6e4; }

/* ── Buttons ─────────────────────────────────────────────────────────────── */
div[data-testid="stButton"] button {
    background: #0f172a !important; color: #f1f5f9 !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 0.92rem !important;
    padding: 0.6rem 2rem !important;
    box-shadow: 0 1px 3px rgba(15,23,42,0.18) !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stButton"] button:hover {
    background: #1e293b !important;
    box-shadow: 0 4px 12px rgba(15,23,42,0.22) !important;
    transform: translateY(-1px) !important;
}
div[data-testid="stButton"] button:disabled {
    background: #e2e8f0 !important; color: #94a3b8 !important;
    box-shadow: none !important; transform: none !important;
}

/* ── Sidebar collapse / expand toggle ───────────────────────────────────── */
/* The expand arrow shown when sidebar is collapsed must always be visible */
[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    background: #0f172a !important;
    border-radius: 0 8px 8px 0 !important;
    box-shadow: 2px 0 8px rgba(15,23,42,0.25) !important;
}
[data-testid="collapsedControl"] button,
[data-testid="collapsedControl"] span {
    background: transparent !important;
    box-shadow: none !important;
    transform: none !important;
    color: #94a3b8 !important;
    padding: 0 !important;
}
[data-testid="collapsedControl"] svg {
    fill: #94a3b8 !important;
    stroke: #94a3b8 !important;
}

/* ── Metric cards ────────────────────────────────────────────────────────── */
.metric-card {
    background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 1.25rem 1rem; text-align: center;
    box-shadow: 0 1px 3px rgba(15,23,42,0.04);
}
.metric-icon { font-size: 1.4rem; margin-bottom: 0.4rem; }
.metric-val { font-size: 2rem; font-weight: 800; line-height: 1; color: #0f172a; }
.metric-lbl {
    font-size: 0.68rem; font-weight: 700; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 0.07em; margin-top: 0.35rem;
}

/* ── Results header ──────────────────────────────────────────────────────── */
.results-header { display: flex; align-items: center; margin-bottom: 1.25rem; }
.results-title {
    font-size: 1.1rem; font-weight: 700; color: #0f172a;
    display: flex; align-items: center; gap: 0.5rem;
}
.success-pill {
    background: #dcfce7; color: #166534; border-radius: 20px;
    padding: 2px 10px; font-size: 0.73rem; font-weight: 600;
}

/* ── Section divider ─────────────────────────────────────────────────────── */
.section-sep { border: none; border-top: 1px solid #e2e8f0; margin: 1.75rem 0; }

/* ── File tree ───────────────────────────────────────────────────────────── */
.file-tree {
    background: #0f172a; color: #e2e8f0; border-radius: 10px;
    padding: 1rem 1.25rem; font-family: 'Courier New', monospace; font-size: 0.82rem;
    line-height: 1.7; max-height: 360px; overflow-y: auto;
}
.file-tree .dir  { color: #60a5fa; font-weight: 600; }
.file-tree .file { color: #86efac; }
.file-tree .meta { color: #475569; }

/* ── Info box ────────────────────────────────────────────────────────────── */
.info-box {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 0.85rem 1.1rem; margin-top: 0.5rem;
}
.info-box strong { color: #0f172a; }
.info-box p { color: #475569; font-size: 0.85rem; margin: 0.2rem 0 0; }
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


# ══════════════════════════════════════════════════════════════════════════════
# CREDENTIALS HELPER
# ══════════════════════════════════════════════════════════════════════════════

def get_env() -> dict:
    """Return os.environ with any user-supplied Databricks credentials injected.

    Values come from st.session_state keys set by the Settings tab:
      - sb_db_host   → DATABRICKS_HOST
      - sb_db_token  → DATABRICKS_TOKEN
      - sb_db_profile → DATABRICKS_CONFIG_PROFILE
    If the keys are empty or absent the existing environment values are used.
    """
    env = os.environ.copy()
    host = st.session_state.get("sb_db_host", "").strip()
    token = st.session_state.get("sb_db_token", "").strip()
    profile = st.session_state.get("sb_db_profile", "").strip()
    if host:
        env["DATABRICKS_HOST"] = host
    if token:
        env["DATABRICKS_TOKEN"] = token
    if profile:
        env["DATABRICKS_CONFIG_PROFILE"] = profile
    return env


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — ANALYZER
# ══════════════════════════════════════════════════════════════════════════════

def run_lakebridge(src: str, out: str, tech: int) -> tuple[bool, str, str]:
    payload = f"{src}\n{out}\n{tech}\n"
    try:
        proc = subprocess.run(
            ["databricks", "labs", "lakebridge", "analyze"],
            input=payload, capture_output=True, text=True,
            timeout=600, env=get_env(),
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
        lower_cols = {c.lower(): c for c in df.columns}

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
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=600, env=get_env(),
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


def run_hive_transpiler(
    src_dir: str,
    out_dir: str,
    err_file: str,
    target: str,
    catalog: str = "",
    schema: str = "",
) -> tuple[bool, str, str]:
    """
    Custom HiveSQL → SparkSQL / PySpark transpiler powered by sqlglot.
    Bypasses the lakebridge CLI (which has no Hive dialect) and processes
    .hql / .hive / .sql / .ddl / .dml files directly in Python.
    """
    try:
        import sqlglot
    except ImportError:
        return False, "", (
            "`sqlglot` is not installed.\n"
            "Run:  pip install 'sqlglot>=23.0.0'"
        )

    src_root = Path(src_dir)
    out_root = Path(out_dir)
    hive_exts = {".hql", ".hive", ".sql", ".ddl", ".dml"}

    errors: list[str] = []
    processed = 0
    generated = 0

    for src_file in sorted(src_root.rglob("*")):
        if not src_file.is_file() or src_file.suffix.lower() not in hive_exts:
            continue

        processed += 1
        rel_path = src_file.relative_to(src_root)

        try:
            content = src_file.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            errors.append(f"{rel_path}: could not read — {exc}")
            continue

        # ── Transpile with sqlglot ───────────────────────────────────────────
        try:
            converted_stmts = sqlglot.transpile(
                content,
                read="hive",
                write="databricks",
                pretty=True,
                error_level=sqlglot.ErrorLevel.WARN,
            )
        except Exception as exc:
            errors.append(f"{rel_path}: parse/transpile error — {exc}")
            continue

        if not converted_stmts:
            errors.append(f"{rel_path}: no SQL statements found")
            continue

        # ── Build output content ─────────────────────────────────────────────
        if target == "SPARKSQL":
            out_ext = ".sql"
            lines: list[str] = [
                f"-- Transpiled from HiveSQL  |  source: {src_file.name}",
                f"-- Engine: sqlglot (hive → spark)  |  target: SparkSQL / Databricks",
                "",
            ]
            if catalog.strip():
                lines += [f"USE CATALOG {catalog.strip()};", ""]
            if schema.strip():
                lines += [f"USE {schema.strip()};", ""]
            for stmt in converted_stmts:
                if stmt.strip():
                    lines.append(stmt.rstrip(";") + ";")
                    lines.append("")
            out_content = "\n".join(lines)

        else:  # PYSPARK
            out_ext = ".py"
            lines = [
                "# -*- coding: utf-8 -*-",
                '"""',
                f"Transpiled from HiveSQL  |  source: {src_file.name}",
                "Engine: sqlglot (hive → spark)  |  target: PySpark / Databricks",
                '"""',
                "",
                "from pyspark.sql import SparkSession",
                "",
                "spark = SparkSession.builder.getOrCreate()",
                "",
            ]
            if catalog.strip():
                lines += [f'spark.sql("USE CATALOG {catalog.strip()}")', ""]
            if schema.strip():
                lines += [f'spark.sql("USE {schema.strip()}")', ""]
            for i, stmt in enumerate(converted_stmts, start=1):
                if not stmt.strip():
                    continue
                safe_stmt = stmt.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
                lines += [
                    f"# ── Statement {i} ──",
                    f'spark.sql("""',
                    safe_stmt,
                    '""")',
                    "",
                ]
            out_content = "\n".join(lines)

        # ── Write output file ────────────────────────────────────────────────
        out_file = out_root / rel_path.with_suffix(out_ext)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            out_file.write_text(out_content, encoding="utf-8")
            generated += 1
        except Exception as exc:
            errors.append(f"{rel_path}: could not write output — {exc}")

    # ── Error log ────────────────────────────────────────────────────────────
    if errors:
        Path(err_file).write_text("\n".join(errors), encoding="utf-8")

    stdout = (
        f"HiveSQL transpiler (sqlglot → Databricks SQL): {processed} file(s) processed, "
        f"{generated} file(s) generated."
        + (f"  {len(errors)} error(s) — see log." if errors else "")
    )
    stderr = "\n".join(errors) if (errors and generated == 0) else ""
    return generated > 0, stdout, stderr


def run_oozie_converter(
    src_dir: str,
    out_dir: str,
    err_file: str,
) -> tuple[bool, str, str]:
    """
    Convert Oozie workflow.xml files to Databricks Jobs API 2.1 JSON.
    Each .xml file in src_dir is parsed and written as a matching .json in out_dir.
    """
    src_root = Path(src_dir)
    out_root = Path(out_dir)

    errors: list[str] = []
    processed = 0
    generated = 0

    for src_file in sorted(src_root.rglob("*.xml")):
        if not src_file.is_file():
            continue
        processed += 1
        rel_path = src_file.relative_to(src_root)
        try:
            xml_str = src_file.read_text(encoding="utf-8", errors="replace")
            job_name = src_file.stem  # filename without extension as job name
            job_json = workflow_to_json(xml_str, job_name=job_name)
        except Exception as exc:
            errors.append(f"{rel_path}: conversion error — {exc}")
            continue

        out_file = out_root / rel_path.with_suffix(".json")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            out_file.write_text(job_json, encoding="utf-8")
            generated += 1
        except Exception as exc:
            errors.append(f"{rel_path}: could not write output — {exc}")

    if errors:
        Path(err_file).write_text("\n".join(errors), encoding="utf-8")

    stdout = (
        f"Oozie converter: {processed} workflow(s) processed, "
        f"{generated} Databricks Workflow JSON file(s) generated."
        + (f"  {len(errors)} error(s) — see log." if errors else "")
    )
    stderr = "\n".join(errors) if (errors and generated == 0) else ""
    return generated > 0, stdout, stderr


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
            lines.append(f'<span class="dir">{indent}📁 {p.name}/</span>')
        else:
            size = p.stat().st_size
            total_files += 1
            total_bytes += size
            lines.append(
                f'<span class="file">{indent}📄 {p.name}</span>'
                f'<span class="meta">  ({size:,} bytes)</span>'
            )
    return "<br>".join(lines) if lines else '<span class="meta">No files found.</span>', total_files, total_bytes


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="padding:1.75rem 0.5rem 1.25rem;">
        <div style="font-size:1.3rem;font-weight:800;color:#f1f5f9;
                    letter-spacing:-0.03em;line-height:1;">
            Syren<span style="color:#ef4444;">Bridge</span>
        </div>
        <div style="font-size:0.67rem;color:#475569;margin-top:4px;font-weight:600;
                    letter-spacing:0.1em;text-transform:uppercase;">
            Migration Suite
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#1e293b;margin:0 0 0.75rem;'>", unsafe_allow_html=True)

    selected_page = st.radio(
        "Navigation",
        ["Get Started", "Analyzer", "Transpiler", "Settings"],
        label_visibility="collapsed",
        key="main_nav",
    )

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

    st.markdown("""
    <div style="border-top:1px solid #1e293b;padding-top:1.25rem;padding-left:0.5rem;">
        <div style="font-size:0.64rem;font-weight:700;color:#334155;letter-spacing:0.1em;
                    text-transform:uppercase;margin-bottom:0.65rem;">Suite Capabilities</div>
        <div style="font-size:0.78rem;color:#475569;line-height:1.9;">
            🔍 &nbsp;36 analysis technologies<br>
            ⚡ &nbsp;11 transpiler dialects<br>
            🗄️ &nbsp;Databricks SQL output<br>
            🔁 &nbsp;Oozie workflow conversion<br>
            ☁️ &nbsp;Runs on Databricks Apps
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="position:absolute;bottom:1.5rem;left:1rem;right:1rem;">
        <div style="font-size:0.68rem;color:#334155;text-align:center;">
            © 2024 Syren Cloud
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Page header renderer ──────────────────────────────────────────────────────
_PAGE_META = {
    "Get Started": ("📚", "Get Started", "Overview, capabilities, and how to use SyrenBridge"),
    "Analyzer":    ("🔍", "Code Analyzer", "Analyze legacy source code for migration readiness"),
    "Transpiler":  ("⚡", "Code Transpiler", "Convert source code to Databricks-compatible output"),
    "Settings":    ("⚙️", "Settings", "Configure Databricks workspace credentials"),
}
_icon, _title, _subtitle = _PAGE_META[selected_page]
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
# PAGE — GET STARTED
# ══════════════════════════════════════════════════════════════════════════════

if selected_page == "Get Started":

    # ── Intro ─────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="max-width:720px;margin-bottom:2rem;">
        <p style="color:#475569;font-size:0.95rem;line-height:1.7;margin:0;">
            SyrenBridge is Syren Cloud's enterprise migration suite for moving legacy data platforms
            to <strong>Databricks</strong>. It covers the full migration journey — from automated
            analysis of your existing codebase to production-ready converted code — supporting
            <strong>36 source technologies</strong> across SQL, ETL, and workflow orchestration.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Quick-start steps ─────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;
                padding:1.5rem 1.75rem;margin-bottom:2rem;">
        <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                    text-transform:uppercase;margin-bottom:1.1rem;">Quick Start</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.25rem;">
            <div>
                <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.08em;
                            text-transform:uppercase;margin-bottom:0.3rem;">Step 1</div>
                <div style="font-weight:700;color:#0f172a;margin-bottom:0.3rem;font-size:0.95rem;">
                    🔍 Analyze
                </div>
                <div style="font-size:0.85rem;color:#64748b;line-height:1.6;">
                    Select your source technology, upload source files, and get a
                    migration-readiness report — object inventory, function usage, SQL category breakdown.
                </div>
            </div>
            <div style="border-left:1px solid #e2e8f0;padding-left:1.25rem;">
                <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.08em;
                            text-transform:uppercase;margin-bottom:0.3rem;">Step 2</div>
                <div style="font-weight:700;color:#0f172a;margin-bottom:0.3rem;font-size:0.95rem;">
                    ⚡ Transpile
                </div>
                <div style="font-size:0.85rem;color:#64748b;line-height:1.6;">
                    Select your source dialect, upload files, and download Databricks-compatible
                    output — SQL, PySpark notebooks, or Workflow JSON.
                </div>
            </div>
            <div style="border-left:1px solid #e2e8f0;padding-left:1.25rem;">
                <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.08em;
                            text-transform:uppercase;margin-bottom:0.3rem;">First time?</div>
                <div style="font-weight:700;color:#0f172a;margin-bottom:0.3rem;font-size:0.95rem;">
                    ⚙️ Configure
                </div>
                <div style="font-size:0.85rem;color:#64748b;line-height:1.6;">
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
                text-transform:uppercase;margin-bottom:0.75rem;">Transpiler — 11 Supported Dialects</div>
    """, unsafe_allow_html=True)

    dialect_rows = [
        ("DataStage",          "Databricks Labs Lakebridge",  "PySpark / SparkSQL",       ".dsx .xml .pjb"),
        ("HiveSQL (Cloudera)", "sqlglot (Databricks dialect)", "Databricks SQL / PySpark", ".hql .hive .sql .ddl .dml"),
        ("Informatica",        "Databricks Labs Lakebridge",  "PySpark / SparkSQL",       ".xml .session .wf .m .mplt .lkp"),
        ("Informatica Cloud",  "Databricks Labs Lakebridge",  "PySpark / SparkSQL",       ".xml .json .session"),
        ("MS SQL Server",      "Databricks Labs Lakebridge",  "PySpark / SparkSQL",       ".sql .ddl .dml .proc .view"),
        ("Netezza",            "Databricks Labs Lakebridge",  "PySpark / SparkSQL",       ".sql .ddl .dml .nzb"),
        ("Oracle",             "Databricks Labs Lakebridge",  "PySpark / SparkSQL",       ".sql .ddl .dml .pls .prc .vw"),
        ("Snowflake",          "Databricks Labs Lakebridge",  "PySpark / SparkSQL",       ".sql .ddl .dml"),
        ("Synapse",            "Databricks Labs Lakebridge",  "PySpark / SparkSQL",       ".sql .ddl .dml .json"),
        ("Teradata",           "Databricks Labs Lakebridge",  "PySpark / SparkSQL",       ".sql .bteq .tdl .tpt .ddl .dml"),
        ("Oozie (Workflow)",   "lxml (built-in parser)",      "Databricks Jobs JSON",     ".xml"),
    ]

    gs_table_rows = ""
    for i, (dialect, engine, output, exts) in enumerate(dialect_rows):
        bg = "#ffffff" if i % 2 == 0 else "#f8fafc"
        gs_table_rows += f"""
        <tr style="background:{bg};">
            <td style="padding:0.55rem 0.85rem;font-weight:600;color:#0f172a;font-size:0.87rem;">{dialect}</td>
            <td style="padding:0.55rem 0.85rem;color:#475569;font-size:0.84rem;">{engine}</td>
            <td style="padding:0.55rem 0.85rem;color:#475569;font-size:0.84rem;">{output}</td>
            <td style="padding:0.55rem 0.85rem;color:#94a3b8;font-size:0.78rem;font-family:monospace;">{exts}</td>
        </tr>"""

    st.markdown(f"""
    <div style="border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:2rem;">
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:#f1f5f9;border-bottom:1px solid #e2e8f0;">
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">Dialect</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">Engine</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">Output</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">File Types</th>
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
            f'<li style="padding:0.1rem 0;color:#475569;font-size:0.85rem;">{t}</li>'
            for t in techs
        )

    with gs_a1:
        st.markdown(f"""
        <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:1rem 1.25rem;">
            <div style="font-size:0.68rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                        text-transform:uppercase;margin-bottom:0.6rem;">🗄️ SQL ({len(sql_techs)})</div>
            <ul style="list-style:none;padding:0;margin:0;line-height:1.7;">{_tech_list(sql_techs)}</ul>
        </div>""", unsafe_allow_html=True)

    with gs_a2:
        st.markdown(f"""
        <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:1rem 1.25rem;">
            <div style="font-size:0.68rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                        text-transform:uppercase;margin-bottom:0.6rem;">🔄 ETL ({len(etl_techs)})</div>
            <ul style="list-style:none;padding:0;margin:0;line-height:1.7;">{_tech_list(etl_techs)}</ul>
        </div>""", unsafe_allow_html=True)

    with gs_a3:
        st.markdown(f"""
        <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:1rem 1.25rem;">
            <div style="font-size:0.68rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                        text-transform:uppercase;margin-bottom:0.6rem;">💻 Code ({len(code_techs)})</div>
            <ul style="list-style:none;padding:0;margin:0;line-height:1.7;">{_tech_list(code_techs)}</ul>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

    # ── PySpark / Serverless note ─────────────────────────────────────────────
    st.markdown(
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
        'padding:0.8rem 1.1rem;font-size:0.86rem;color:#475569;">'
        '💡 <strong style="color:#0f172a;">PySpark &amp; Spark Classic → Serverless</strong> '
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
    <div style="color:#475569;font-size:0.92rem;max-width:680px;margin-bottom:1.5rem;">
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
            f"{CATEGORY_ICON.get(cat, '📦')}  {name}"
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
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:1rem 1.25rem;margin-top:0.75rem;">
            <div style="font-weight:700;color:#111827;font-size:1rem;margin-bottom:0.2rem;">
                {CATEGORY_ICON.get(tech_cat,'📦')} {tech_name}
            </div>
            <div style="font-size:0.78rem;color:#9ca3af;margin-bottom:0.6rem;">
                Category: {tech_cat} &nbsp;·&nbsp; Option #{tech_num}
            </div>
            <div style="font-size:0.78rem;color:#6b7280;margin-bottom:0.4rem;font-weight:600;">
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

        upload_mode = st.radio(
            "Mode",
            ["Individual files", "ZIP archive"],
            horizontal=True,
            label_visibility="collapsed",
        )
        is_zip = upload_mode == "ZIP archive"

        if is_zip:
            raw = st.file_uploader(
                "Drop your ZIP here",
                type=["zip"],
                label_visibility="collapsed",
                help="All files inside the ZIP will be extracted and analyzed.",
            )
            uploaded_files = [raw] if raw else []
        else:
            uploaded_files = st.file_uploader(
                "Drop files here",
                type=tech_exts,
                accept_multiple_files=True,
                label_visibility="collapsed",
                help=f"Accepted: {', '.join('.' + e for e in tech_exts)}  —  Use ZIP mode for mixed types.",
            )

        if uploaded_files:
            total_kb = sum(f.size for f in uploaded_files) / 1024
            st.markdown(f"""
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;
                        padding:0.85rem 1.1rem;margin-top:0.5rem;">
                <div style="font-weight:700;color:#065f46;font-size:0.95rem;">
                    ✅ {len(uploaded_files)} file(s) ready &nbsp;·&nbsp; {total_kb:.1f} KB
                </div>
            </div>
            """, unsafe_allow_html=True)
            with st.expander("View uploaded files", expanded=False):
                for f in uploaded_files:
                    st.markdown(f"📄 `{f.name}` &nbsp; <span style='color:#9ca3af;font-size:0.8rem'>{f.size:,} bytes</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:#fafafa;border:2px dashed #e5e7eb;border-radius:12px;
                        padding:2rem 1.5rem;text-align:center;margin-top:0.5rem;color:#9ca3af;">
                <div style="font-size:2rem;margin-bottom:0.5rem;">📂</div>
                <div style="font-weight:600;color:#6b7280;margin-bottom:0.25rem;">No files selected yet</div>
                <div style="font-size:0.82rem;">Use the uploader above to add your source files</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div style="font-size:0.78rem;color:#9ca3af;margin-top:0.75rem;line-height:1.5;">
            💡 <strong>Tip:</strong> Use <em>ZIP archive</em> mode to upload entire folders
            or mixed file types at once.
        </div>
        """, unsafe_allow_html=True)

    # ── STEP 3: RUN ───────────────────────────────────────────────────────────
    st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)

    _, btn_col, _ = st.columns([2, 1, 2])
    with btn_col:
        run_clicked = st.button(
            "🚀  Run Analysis",
            use_container_width=True,
            disabled=not bool(uploaded_files),
            key="run_analyze",
        )

    if not uploaded_files:
        st.markdown(
            "<div style='text-align:center;color:#9ca3af;font-size:0.85rem;margin-top:0.25rem'>"
            "Upload at least one file to run the analysis."
            "</div>",
            unsafe_allow_html=True,
        )

    # ── ANALYSIS EXECUTION ────────────────────────────────────────────────────
    if run_clicked and uploaded_files:
        src_dir = out_dir = None
        try:
            with st.status("Running analysis…", expanded=True) as status:
                st.write(f"📂 Preparing **{len(uploaded_files)}** file(s)…")
                src_dir = save_uploaded_files(uploaded_files, is_zip)
                n_files, n_bytes = count_files(src_dir)
                st.write(f"&nbsp;&nbsp;→ {n_files} file(s) staged ({n_bytes/1024:.1f} KB)")

                out_dir = tempfile.mkdtemp(prefix="lb_out_")
                out_file = os.path.join(out_dir, output_filename)

                st.write(f"⚙️ Analyzing as **{tech_name}** (#{tech_num})…")
                t0 = time.time()
                ok, stdout, stderr = run_lakebridge(src_dir, out_file, tech_num)
                elapsed = time.time() - t0
                st.write(f"&nbsp;&nbsp;→ Completed in **{elapsed:.1f}s**")

                report_ok = os.path.exists(out_file)
                sql_reports = sorted(Path(out_dir).glob("*_SQL.xlsx"))

                if report_ok:
                    status.update(label="✅ Analysis complete!", state="complete", expanded=False)
                else:
                    status.update(label="⚠️ Finished with issues — see log below", state="error", expanded=True)

            if stdout:
                with st.expander("📋 Full analysis log"):
                    st.code(stdout, language="text")
            if stderr and not ok:
                with st.expander("❗ Errors / warnings"):
                    st.code(stderr, language="text")

            if report_ok:
                main_sheets = read_excel_sheets(out_file)

                st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)
                st.markdown("""
                <div class="results-header">
                    <div class="results-title">📊 Analysis Results <span class="success-pill">Ready</span></div>
                </div>
                """, unsafe_allow_html=True)

                metrics = extract_metrics(main_sheets)
                if metrics:
                    icons = {
                        "Files Analyzed": "📁",
                        "SQL Programs": "📜",
                        "Unique Functions": "⚡",
                        "Referenced Objects": "🔗",
                        "Transformations": "🔄",
                    }
                    items = list(metrics.items())
                    cols = st.columns(min(len(items), 4))
                    for col, (label, val) in zip(cols, items):
                        with col:
                            st.markdown(f"""
                            <div class="metric-card">
                                <div class="metric-icon">{icons.get(label, '📊')}</div>
                                <div class="metric-val">{val:,}</div>
                                <div class="metric-lbl">{label}</div>
                            </div>
                            """, unsafe_allow_html=True)

                st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

                fn_chart = build_function_chart(main_sheets)
                cat_chart = build_category_chart(main_sheets)

                if fn_chart or cat_chart:
                    ch1, ch2 = st.columns(2) if (fn_chart and cat_chart) else (st.columns(1)[0], None)
                    if fn_chart:
                        with (ch1 if cat_chart else st):
                            st.markdown("**⚡ Top Functions by Usage**")
                            st.altair_chart(fn_chart, use_container_width=True)
                    if cat_chart and ch2:
                        with ch2:
                            st.markdown("**🗂️ SQL Script Categories**")
                            st.altair_chart(cat_chart, use_container_width=True)

                st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
                dl_cols = st.columns(2) if sql_reports else st.columns([1, 2])

                with dl_cols[0]:
                    with open(out_file, "rb") as fh:
                        st.download_button(
                            label="📥  Download Main Report",
                            data=fh.read(),
                            file_name=output_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )

                if sql_reports:
                    with dl_cols[1]:
                        with open(str(sql_reports[0]), "rb") as fh:
                            st.download_button(
                                label="📥  Download SQL Sub-Report",
                                data=fh.read(),
                                file_name=sql_reports[0].name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                            )

                st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)
                st.markdown("**📋 Sheet Explorer**")
                sheet_names = list(main_sheets.keys())
                if sheet_names:
                    tabs = st.tabs(sheet_names)
                    for tab, name in zip(tabs, sheet_names):
                        with tab:
                            df = main_sheets[name]
                            if df.empty:
                                st.markdown(
                                    "<div class='empty-state'><div class='icon'>🗃️</div>"
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
                                st.dataframe(display_df, use_container_width=True, hide_index=True)

                if sql_reports:
                    st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)
                    st.markdown("**📋 Embedded SQL Report — Sheet Explorer**")
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
                                    st.dataframe(df, use_container_width=True, hide_index=True)
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
    <div style="color:#475569;font-size:0.92rem;max-width:720px;margin-bottom:1.5rem;">
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
        '<div style="background:#eff6ff;border:1px solid #93c5fd;border-radius:8px;'
        'padding:0.65rem 1rem;margin-bottom:1rem;font-size:0.83rem;color:#1e40af;">'
        '💡 <strong>PySpark & Spark Classic → Serverless migration</strong> is available through '
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
                '<span style="font-size:0.72rem;background:#fef3c7;color:#92400e;'
                'border:1px solid #fcd34d;border-radius:6px;padding:2px 7px;font-weight:600;">'
                '🔁 Built-in engine (oozie_converter) — outputs Databricks Workflow JSON</span>'
            )
        elif dialect_info.get("custom"):
            _engine_badge = (
                '<span style="font-size:0.72rem;background:#fef3c7;color:#92400e;'
                'border:1px solid #fcd34d;border-radius:6px;padding:2px 7px;font-weight:600;">'
                '⚙️ Built-in engine (sqlglot) — no Databricks CLI needed</span>'
            )
        else:
            _engine_badge = ""
        st.markdown(f"""
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;
                    padding:0.85rem 1.25rem;margin-top:0.5rem;margin-bottom:1rem;">
            <div style="font-size:0.78rem;color:#6b7280;font-weight:600;margin-bottom:0.4rem;">
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
                '<div style="background:#ecfdf5;border:1px solid #6ee7b7;border-radius:8px;'
                'padding:0.6rem 1rem;font-size:0.82rem;color:#065f46;font-weight:500;">'
                '📋 Output: <strong>Databricks Workflow JSON</strong> — deployable via '
                '<code>/api/2.1/jobs</code></div>',
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
                '<div style="background:#ecfdf5;border:1px solid #6ee7b7;border-radius:8px;'
                'padding:0.6rem 1rem;font-size:0.82rem;color:#065f46;font-weight:500;">'
                '🗄️ SQL output uses <strong>Databricks SQL dialect</strong> — '
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

        # Optional settings (not applicable for Oozie)
        if not dialect_info.get("oozie"):
            with st.expander("⚙️ Advanced options", expanded=False):
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
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;
                        padding:0.85rem 1.1rem;margin-top:0.5rem;">
                <div style="font-weight:700;color:#065f46;font-size:0.95rem;">
                    ✅ {len(tp_files)} file(s) ready &nbsp;·&nbsp; {tp_total_kb:.1f} KB
                </div>
            </div>
            """, unsafe_allow_html=True)
            with st.expander("View uploaded files", expanded=False):
                for f in tp_files:
                    st.markdown(f"📄 `{f.name}` &nbsp; <span style='color:#9ca3af;font-size:0.8rem'>{f.size:,} bytes</span>", unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="background:#fafafa;border:2px dashed #e5e7eb;border-radius:12px;
                        padding:2rem 1.5rem;text-align:center;margin-top:0.5rem;color:#9ca3af;">
                <div style="font-size:2rem;margin-bottom:0.5rem;">📂</div>
                <div style="font-weight:600;color:#6b7280;margin-bottom:0.25rem;">No files selected yet</div>
                <div style="font-size:0.82rem;">Upload source files to begin transpilation</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div style="font-size:0.78rem;color:#9ca3af;margin-top:0.75rem;line-height:1.5;">
            💡 <strong>Tip:</strong> Use <em>ZIP archive</em> mode to upload an entire
            source project folder at once.
        </div>
        """, unsafe_allow_html=True)

    # ── RUN BUTTON ────────────────────────────────────────────────────────────
    st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)

    _, tp_btn_col, _ = st.columns([2, 1, 2])
    with tp_btn_col:
        tp_run = st.button(
            "⚡  Transpile Code",
            use_container_width=True,
            disabled=not bool(tp_files),
            key="run_transpile",
        )

    if not tp_files:
        st.markdown(
            "<div style='text-align:center;color:#9ca3af;font-size:0.85rem;margin-top:0.25rem'>"
            "Upload at least one source file to run transpilation."
            "</div>",
            unsafe_allow_html=True,
        )

    # ── TRANSPILATION EXECUTION ───────────────────────────────────────────────
    if tp_run and tp_files:
        tp_src_dir = tp_out_dir = None
        try:
            with st.status("Transpiling…", expanded=True) as tp_status:
                st.write(f"📂 Preparing **{len(tp_files)}** file(s)…")
                tp_src_dir = save_uploaded_files(tp_files, tp_is_zip)
                n_src, b_src = count_files(tp_src_dir)
                st.write(f"&nbsp;&nbsp;→ {n_src} file(s) staged ({b_src/1024:.1f} KB)")

                tp_out_dir = tempfile.mkdtemp(prefix="lb_tp_out_")
                tp_err_file = os.path.join(tp_out_dir, "transpile_errors.log")

                st.write(f"⚡ Transpiling **{selected_dialect_name}** → **{selected_target_label.split('(')[0].strip()}**…")
                t0 = time.time()
                if dialect_info.get("oozie"):
                    # Built-in Oozie → Databricks Workflow JSON converter
                    tp_ok, tp_stdout, tp_stderr = run_oozie_converter(
                        src_dir=tp_src_dir,
                        out_dir=tp_out_dir,
                        err_file=tp_err_file,
                    )
                elif dialect_info.get("custom"):
                    # Custom in-process transpiler (HiveSQL via sqlglot → Databricks SQL)
                    tp_ok, tp_stdout, tp_stderr = run_hive_transpiler(
                        src_dir=tp_src_dir,
                        out_dir=tp_out_dir,
                        err_file=tp_err_file,
                        target=target_cli,
                        catalog=st.session_state.get("tp_catalog", ""),
                        schema=st.session_state.get("tp_schema", ""),
                    )
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
                    tp_status.update(label="⚠️ No output files generated — check log below", state="error", expanded=True)
                else:
                    tp_status.update(label="⚠️ Completed with warnings — see log below", state="complete", expanded=False)

            # ── Logs ─────────────────────────────────────────────────────────
            if tp_stdout:
                with st.expander("📋 Transpiler output log"):
                    st.code(tp_stdout, language="text")
            if tp_stderr and not tp_ok:
                with st.expander("❗ Errors / warnings"):
                    st.code(tp_stderr, language="text")

            # ── Results ──────────────────────────────────────────────────────
            if n_out > 0:
                st.markdown("<hr class='section-sep'>", unsafe_allow_html=True)

                # Oozie-specific notes shown with results
                if dialect_info.get("oozie"):
                    st.markdown(
                        '<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;'
                        'padding:0.75rem 1rem;margin-bottom:1rem;font-size:0.87rem;color:#92400e;">'
                        '⚠️ <strong>Oozie Limitations to review in the generated JSON:</strong>'
                        '<ul style="margin:0.4rem 0 0 1rem;padding:0;line-height:1.8;">'
                        '<li><strong>Fork/Join not supported</strong> — parallel branches (<code>&lt;fork&gt;</code>/<code>&lt;join&gt;</code>) '
                        'are silently skipped. Review your workflow XML for these nodes and add the parallel tasks manually in the Databricks Workflow editor.</li>'
                        '<li><strong>EL expressions</strong> (<code>${variable}</code>) are preserved as-is — replace them with Databricks job parameters or widget values.</li>'
                        '<li><strong>Coordinator &amp; Bundle</strong> schedules are not converted — recreate them as Databricks Job schedules (cron or trigger-based).</li>'
                        '<li>Placeholder values marked <code>&lt;replace: …&gt;</code> must be filled in before deploying the job.</li>'
                        '</ul>'
                        '</div>',
                        unsafe_allow_html=True,
                    )

                st.markdown("""
                <div class="results-header">
                    <div class="results-title">
                        ⚡ Transpiled Output <span class="success-pill">Ready</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Metric cards
                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-icon">📁</div>
                        <div class="metric-val">{n_src}</div>
                        <div class="metric-lbl">Files Processed</div>
                    </div>""", unsafe_allow_html=True)
                with mc2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-icon">✅</div>
                        <div class="metric-val">{n_out}</div>
                        <div class="metric-lbl">Files Generated</div>
                    </div>""", unsafe_allow_html=True)
                with mc3:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-icon">⚡</div>
                        <div class="metric-val">{elapsed:.1f}s</div>
                        <div class="metric-lbl">Time Taken</div>
                    </div>""", unsafe_allow_html=True)

                st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

                # ZIP download
                zip_bytes = zip_directory(tp_out_dir)
                zip_name = f"transpiled_{dialect_cli}_{target_cli.lower()}.zip"
                dl_col, info_col = st.columns([1, 2])
                with dl_col:
                    st.download_button(
                        label="📥  Download All Output Files",
                        data=zip_bytes,
                        file_name=zip_name,
                        mime="application/zip",
                        use_container_width=True,
                    )
                with info_col:
                    st.markdown(f"""
                    <div class="info-box">
                        <strong>📦 {zip_name}</strong>
                        <p>{n_out} converted file(s) · {b_out/1024:.1f} KB total</p>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

                # File tree
                st.markdown("**📂 Output File Tree**")
                tree_html, _, _ = build_file_tree_html(tp_out_dir)
                st.markdown(f'<div class="file-tree">{tree_html}</div>', unsafe_allow_html=True)

                st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

                # Inline preview of each output file
                output_files = sorted(
                    [p for p in Path(tp_out_dir).rglob("*") if p.is_file() and p.name != "transpile_errors.log"],
                    key=lambda p: str(p)
                )
                if output_files:
                    st.markdown("**👁️ File Preview**")
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
                        with st.expander("⚠️ Transpilation error log", expanded=False):
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
            for d in (tp_src_dir,):
                if d and os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
            # Note: tp_out_dir is kept in memory via zip_bytes; cleaned after download
            # In production, a cleanup hook or time-based cleanup is recommended.


# ══════════════════════════════════════════════════════════════════════════════
# PAGE — SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

elif selected_page == "Settings":

    st.markdown("""
    <div style="max-width:680px;margin-bottom:1.5rem;">
        <p style="color:#475569;font-size:0.92rem;line-height:1.65;margin:0;">
            SyrenBridge calls the Databricks CLI to run analysis and transpilation.
            Credentials are held in session memory only — never written to disk or shared between users.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Auto-detect context ───────────────────────────────────────────────────
    db_host_env   = os.environ.get("DATABRICKS_HOST", "")
    db_token_env  = os.environ.get("DATABRICKS_TOKEN", "")
    db_cfg_exists = Path.home().joinpath(".databrickscfg").exists()

    if db_host_env and db_token_env:
        st.markdown(
            f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;'
            f'padding:0.85rem 1.1rem;margin-bottom:1.5rem;font-size:0.87rem;color:#166534;">'
            f'✅ <strong>Ready</strong> — workspace <code>{db_host_env}</code> and token are '
            f'already present in the environment (Databricks Apps or pre-configured CLI). '
            f'You do not need to fill anything in below. '
            f'Use the fields only if you want to override for this session.'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif db_host_env:
        st.markdown(
            f'<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;'
            f'padding:0.85rem 1.1rem;margin-bottom:1.5rem;font-size:0.87rem;color:#92400e;">'
            f'⚠️ <strong>Workspace URL detected</strong> (<code>{db_host_env}</code>) but no token '
            f'found in environment. If you have a configured CLI profile (<code>~/.databrickscfg</code>) '
            f'it will be used automatically. Otherwise enter a token below.'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif db_cfg_exists:
        st.markdown(
            '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;'
            'padding:0.85rem 1.1rem;margin-bottom:1.5rem;font-size:0.87rem;color:#166534;">'
            '✅ <strong>Databricks CLI profile found</strong> (<code>~/.databrickscfg</code>). '
            'The CLI will use it automatically — no input needed unless you want a different workspace.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;'
            'padding:0.85rem 1.1rem;margin-bottom:1.5rem;font-size:0.87rem;color:#991b1b;">'
            '⚠️ <strong>No credentials detected.</strong> Enter your Databricks workspace URL and '
            'Personal Access Token below. The Analyzer and Transpiler require a connected workspace.<br><br>'
            '<strong>On Databricks Apps:</strong> this is handled automatically — no input needed.'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Credential form ───────────────────────────────────────────────────────
    cfg_col1, cfg_col2 = st.columns([3, 2], gap="large")

    with cfg_col1:
        st.markdown("##### Option A — Host + Token (recommended for local use)")

        st.text_input(
            "Databricks Workspace URL",
            key="sb_db_host",
            placeholder="https://adb-XXXXXXXXXXXX.XX.azuredatabricks.net",
            help="The full URL of your Databricks workspace, e.g. https://adb-1234567890.1.azuredatabricks.net",
        )

        st.text_input(
            "Personal Access Token (PAT)",
            key="sb_db_token",
            type="password",
            placeholder="dapi…",
            help="Generate a token in Databricks → User Settings → Developer → Access Tokens.",
        )

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        st.markdown("##### Option B — Named Profile")
        st.text_input(
            "Databricks Config Profile",
            key="sb_db_profile",
            placeholder="DEFAULT",
            help=(
                "Name of the profile in your ~/.databrickscfg file. "
                "Leave blank to use the DEFAULT profile. "
                "Create profiles with: databricks configure --profile <name>"
            ),
        )

    with cfg_col2:
        st.markdown("##### How to get a Personal Access Token")
        st.markdown("""
1. Open your Databricks workspace in a browser.
2. Click your username (top right) → **Settings**.
3. Go to **Developer** → **Access Tokens** → **Generate new token**.
4. Give it a name and copy the token value — you won't see it again.
5. Paste it in the **PAT** field on the left.

##### How to configure a CLI profile
```bash
databricks configure --profile myprofile
# Enter workspace URL and token when prompted
```
Then set **Profile** = `myprofile` on the left.

##### Azure / GCP / AWS
SyrenBridge works with any Databricks workspace. The workspace URL format varies:
- **Azure:** `https://adb-XXXX.XX.azuredatabricks.net`
- **AWS:** `https://XXXX.cloud.databricks.com`
- **GCP:** `https://XXXX.gcp.databricks.com`
        """)

    # ── Live status check ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("##### Connection Status")

    if st.button("🔍 Test Databricks CLI connection", key="test_db_connection"):
        test_env = get_env()
        with st.spinner("Checking `databricks auth status`…"):
            try:
                result = subprocess.run(
                    ["databricks", "auth", "status"],
                    capture_output=True, text=True, timeout=30, env=test_env,
                )
                if result.returncode == 0:
                    st.success("✅ Connection successful")
                    st.code(result.stdout or "(no output)", language="text")
                else:
                    st.error("❌ Connection failed")
                    st.code(result.stderr or result.stdout or "(no output)", language="text")
            except FileNotFoundError:
                st.error(
                    "❌ `databricks` CLI not found in PATH.\n\n"
                    "Install it:\n"
                    "```bash\n"
                    "curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh\n"
                    "databricks labs install lakebridge\n"
                    "```"
                )
            except subprocess.TimeoutExpired:
                st.error("❌ Connection test timed out after 30 seconds.")

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    st.caption(
        "Credentials are held in session state only. "
        "They are injected into the subprocess environment for Analyzer and Transpiler calls "
        "and are not stored to disk or shared between users."
    )

