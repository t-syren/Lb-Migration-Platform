# CLAUDE.md — SyrenBridge Migration Platform

Project context for AI assistants working in this repository.

---

## What This Project Is

SyrenBridge is a Streamlit app (deployed on Databricks Apps) that wraps **Databricks Labs Lakebridge** and extends it with two custom-built migration engines. The UI has two tabs: **Analyzer** and **Transpiler**.

- The Analyzer tab calls `lakebridge analyze` (36 supported source technologies).
- The Transpiler tab calls `lakebridge transpile` for 10 CLI-backed dialects, plus two custom engines (HiveSQL and Oozie) that bypass the CLI entirely.

---

## Two Custom Engines (Built Here, Not in Lakebridge)

### 1. HiveSQL (Cloudera)
- Lives in `modules/sql_transpiler.py`
- Uses **sqlglot** with `read="hive", write="databricks"` — not `write="spark"`
- Strips Hive-only clauses (STORED AS, ROW FORMAT, SERDE, TBLPROPERTIES, LOCATION hdfs://) via regex after sqlglot conversion
- Outputs **Databricks SQL dialect** so the result runs directly on Databricks SQL Warehouses
- Backed by `modules/sql_validator.py` (PySpark local mode) and `modules/dummy_data.py` (Faker-based row generation)

### 2. Oozie (Workflow) — 11th Dialect
- Lives in `modules/oozie_converter.py`
- Parses `workflow.xml` with **lxml**
- Outputs Databricks Jobs API 2.1 JSON
- Detected in `app.py` via `dialect_info.get("oozie")` flag; skips the CLI entirely
- Fan-in DAG: predecessors tracked as `Dict[str, List[str]]` (not a single string)

---

## Tab Structure

The app has 4 tabs: `tab_start`, `tab_analyze`, `tab_transpile`, `tab_settings`.

- `tab_start` — Get Started documentation (no state dependencies)
- `tab_analyze` — Analyzer (calls Lakebridge CLI)
- `tab_transpile` — Transpiler (Lakebridge CLI / custom engines)
- `tab_settings` — Credentials form; writes to `st.session_state` keys `sb_db_host`, `sb_db_token`, `sb_db_profile`

Both Analyzer and Transpiler now support Databricks workspace browsing as an alternative source input path. Each uses a `📂 Upload Files` / `☁️ Databricks Workspace` tabbed UI:

- `Upload Files` lets users choose individual source files or a ZIP archive.
- `Databricks Workspace` lets users navigate folders, select workspace files, and fetch them locally for analysis/transpilation.
- Transpiler also supports uploading converted output files back into a target Databricks workspace folder.

Credentials flow: Settings tab → `st.session_state` → `get_env()` → `subprocess.run(env=get_env())`.
The `get_env()` function (defined before the helper section) overlays session credentials on top of `os.environ`.

## Key Architecture Rules

- `modules/` files are pure Python — **no Streamlit imports**. They are tested independently with pytest.
- `app.py` imports from `modules/` and handles all Streamlit rendering.
- PySpark is only used in `modules/dummy_data.py`, `modules/sql_validator.py`, and tests — never in the Streamlit render path (it's too slow to start on page load).
- sqlglot dialect must be `write="databricks"` for HiveSQL output, NOT `write="spark"`.

---

## Databricks Workspace Integration

The app now includes first-class Databricks workspace support in both Analyzer and Transpiler:

- Workspace browsing uses `DatabricksClient.from_app_context()` and `DatabricksClient.list_workspace_items()`.
- Users can navigate folders, open directories, and select notebook/file objects from the Databricks workspace.
- Selected workspace files are fetched locally using `fetch_workspace_files_to_local()` before analysis/transpilation.
- Transpiler can upload converted output files back to Databricks using `upload_directory_to_workspace()`.
- The upload helper creates missing workspace folders and writes each output file with the correct Databricks file language metadata.

These features make it possible to source files directly from Databricks and publish converted results back into the workspace without leaving the app.

---

## Running Locally

```bash
source lb/bin/activate
cd lb_migration_platform_ui
streamlit run app.py
```

## Running Tests

```bash
cd Lb-Migration-Platform
pytest tests/ -v
```

Tests require Java (for PySpark). On macOS with Homebrew: `brew install openjdk@11`. The `conftest.py` auto-sets `JAVA_HOME` if Homebrew OpenJDK is found at `/opt/homebrew/opt/openjdk`.

---

## Dialect List (app.py `TRANSPILER_DIALECTS`)

| Key in dict | Engine | `"oozie": True`? | `"custom": True`? |
|-------------|--------|-----------------|------------------|
| DataStage | Lakebridge CLI | — | — |
| HiveSQL (Cloudera) | Custom (sqlglot) | — | ✓ |
| Informatica | Lakebridge CLI | — | — |
| Informatica Cloud | Lakebridge CLI | — | — |
| MS SQL Server | Lakebridge CLI | — | — |
| Netezza | Lakebridge CLI | — | — |
| Oracle | Lakebridge CLI | — | — |
| Snowflake | Lakebridge CLI | — | — |
| Synapse | Lakebridge CLI | — | — |
| Teradata | Lakebridge CLI | — | — |
| Oozie (Workflow) | Custom (lxml) | ✓ | — |

The hero badge reads **"⚡ Transpiler — 11 Dialects"**. If a new dialect is added, update both `TRANSPILER_DIALECTS` and the badge count in the HTML block around line 770 of `app.py`.

---

## Important Decisions (Do Not Revert)

- `write="databricks"` in sqlglot — using `write="spark"` produces non-Databricks SQL
- Fan-in DAG in `oozie_converter.py` uses `Dict[str, List[str]]` for predecessors — a plain `Dict[str, str]` silently drops upstream edges when two actions share the same `ok_to` target
- No `.cache()` calls in `sql_validator.py` — they were removed because uncached DataFrames are re-evaluated but don't leak memory; `.cache()` without `.unpersist()` caused memory growth in tests
- `data_match` field in `ValidationResult` influences `passed` — without it, a schema+count match with different data incorrectly returns `passed=True`
- The PySpark/HDFS UI tabs were deliberately removed — they are not part of the current scope. The only UI is Analyzer + Transpiler.

---

## PySpark Migration (Out of Scope Here)

PySpark and Spark Classic → Serverless migrations are handled by the **Syren Server to Serverless Migration Platform**:
https://syren-s2s-platform-204242957656703.3.azure.databricksapps.com/#home

This link appears in the blue info banner at the top of the Transpiler tab.

---

## Sample Files

- `files/source_hive/*.hql` — use these to test the HiveSQL transpiler
- `files/sample_oozie/workflow.xml` — 4-action retail ETL pipeline for Oozie testing
- `files/sample_hdfs/hdfs_listing.txt` — sample `hdfs -ls -R` output

---

## Dependencies

Runtime: `requirements.txt` (streamlit, pandas, sqlglot, pyspark, lxml, libcst, databricks-sdk)
Dev/test: `requirements-dev.txt` (adds faker, pytest, pytest-mock)
