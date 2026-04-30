# CLAUDE.md — SyrenBridge Migration Platform

Project context for AI assistants working in this repository.

---

## What This Project Is

SyrenBridge is a Streamlit app (deployed on Databricks Apps) that wraps **Databricks Labs Lakebridge** and extends it with two custom-built migration engines. The UI has two tabs: **Analyzer** and **Transpiler**.

- The Analyzer tab calls `lakebridge analyze` (36 supported source technologies).
- The Transpiler tab calls `lakebridge transpile` for 10 CLI-backed dialects, plus two custom engines (HiveSQL and Oozie) that bypass the CLI entirely.

Transpiler execution paths:
1. CLI-backed dialects → `run_transpiler()` (Databricks Lakebridge)
2. HiveSQL → `run_hive_transpiler()` (sqlglot-based, in-process)
3. Oozie → `run_oozie_converter()` (lxml-based workflow conversion)
---

## Two Custom Engines (Built Here, Not in Lakebridge)

### 1. HiveSQL (Cloudera)
- Lives in `modules/sql_transpiler.py`
- Uses **sqlglot** with `read="hive", write="databricks"` — not `write="spark"`
- Strips Hive-only clauses (STORED AS, ROW FORMAT, SERDE, TBLPROPERTIES, LOCATION hdfs://) via regex after sqlglot conversion
- Outputs **Databricks SQL dialect** so the result runs directly on Databricks SQL Warehouses
- Backed by `modules/sql_validator.py` (PySpark local mode) and `modules/dummy_data.py` (Faker-based row generation)

### 2. Oozie (Workflow) — 11th Dialect
- Lives in `modules/oozie_converter.py`; parsed with **lxml**; outputs Databricks Jobs API 2.1 JSON
- Detected in `app.py` via `dialect_info.get("oozie")`; skips the CLI entirely
- Entry point for multi-file conversion: `convert_oozie_file_set(files: Dict[str,str]) -> Dict`
  - Returns `{"jobs", "workflow_job_map", "links", "warnings"}`
  - Workflows converted first → independent jobs; coordinators converted second → scheduled jobs
  - `_strip_annotation_keys()` applied to workflow jobs before writing (removes `_`-prefixed migration annotations)
- **Coordinator→workflow linking** via `_match_coordinator_to_workflow(app_path, workflow_files)`:
  - Matches `<app-path>` basename against workflow `name` attribute or filename stem
  - Priority: exact match first, then normalised (`-`↔`_`, lowercase)
  - Match → coordinator gets `run_job_task` with sentinel `"{{job_id:<wf_name>}}"`
  - No match → coordinator gets a placeholder `notebook_task` pointing to the app-path + `migration_warnings` field
  - After workflow job created in UI, sentinel is auto-replaced with the real integer `job_id`
- **Fan-in DAG**: predecessors tracked as `Dict[str, List[str]]` — plain `Dict[str, str]` silently drops edges
- **Cluster rule**: `job_clusters` (shared) only for 2+ task jobs; 1-task jobs get `new_cluster` inline (Databricks rejects shared clusters on single-task jobs)
- **`coordinator_info`** field (visible, no `_` prefix) carries `frequency`, `start`, `end`, `timezone`, `workflow_app_path`, `quartz_cron_expression`
- **`coord_job.pop("job_clusters", None)`** always called on coordinator jobs — they trigger other jobs and never run cluster tasks directly
- `coordinator_to_dict()` always appends "No workflow XML supplied" warning when called without `workflow_xml_str`; `convert_oozie_file_set` filters this out when a workflow was matched (would be misleading)
- Not converted: EL expressions `${...}` (preserved verbatim), datasets, SLA, coordinator end-time (in `coordinator_info` only)

---

## Tab Structure

The app has 4 tabs: `tab_start`, `tab_analyze`, `tab_transpile`, `tab_settings`.

- `tab_start` — Get Started documentation (no state dependencies)
- `tab_analyze` — Analyzer (calls Lakebridge CLI)
- `tab_transpile` — Transpiler (Lakebridge CLI / custom engines)
- `tab_settings` — Credentials form; writes to `st.session_state` keys `sb_db_host`, `sb_db_token`

Both Analyzer and Transpiler now support Databricks workspace browsing as an alternative source input path. Each uses a `📂 Upload Files` / `☁️ Databricks Workspace` tabbed UI:

- `Upload Files` lets users choose individual source files or a ZIP archive.
- `Databricks Workspace` lets users navigate folders, select workspace files, and fetch them locally for analysis/transpilation.
- Transpiler also supports uploading converted output files back into a target Databricks workspace folder.

Credentials flow:
- Credentials are stored in `st.session_state` (`sb_db_host`, `sb_db_token`)
- Fallback to environment variables (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`)
- Unified resolution via `get_databricks_credentials()`
- Used by:
  - `DatabricksClient.from_app_context()` for API calls
  - CLI calls via `os.environ` injection

## Key Architecture Rules

- `modules/` files are pure Python — **no Streamlit imports**. They are tested independently with pytest.
- `app.py` imports from `modules/` and handles all Streamlit rendering.
- PySpark is only used in `modules/dummy_data.py`, `modules/sql_validator.py`, and tests — never in the Streamlit render path (it's too slow to start on page load).
- sqlglot dialect must be `write="databricks"` for HiveSQL output, NOT `write="spark"`.
Input SQL
 → Pre-processing (clean + detect issues)
 → Split into statements (line-aware)
 → SQLGlot conversion (Hive → Databricks)
 → Post-processing (rules + normalization)
 → Issue tagging
 → (Optional) LLM fix for problematic statements ,not for whole file content ,if LLM Not configured -> Output = SQLGlot + rule-based conversion only else ->Output = SQLGlot + rule-based + LLM Fixes
 → Final SQL output

---

## Databricks Workspace Integration

The app now includes first-class Databricks workspace support in both Analyzer and Transpiler:

- Workspace browsing uses `DatabricksClient.from_app_context()` and `DatabricksClient.list_workspace_items()`.
- Users can navigate folders, open directories, and select notebook/file objects from the Databricks workspace.
- Selected workspace files are fetched locally using `fetch_workspace_files_to_local()` before analysis/transpilation.
- Transpiler can upload converted output files back to Databricks using `upload_directory_to_workspace()`.
- The upload helper creates missing workspace folders and writes each output file with the correct Databricks file language metadata.

These features make it possible to source files directly from Databricks and publish converted results back into the workspace without leaving the app.


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
- Oozie coordinator jobs **must not** contain `job_clusters` — they only trigger other jobs via `run_job_task` and never run cluster tasks; `coord_job.pop("job_clusters", None)` is mandatory
- Oozie `job_clusters` (shared cluster) is only valid for multi-task jobs — single-task workflows must inline `new_cluster` per task; omitting this causes a `INVALID_PARAMETER_VALUE` API error
- `_match_coordinator_to_workflow` intentionally excludes same-directory and substring heuristics — they caused false positives when unrelated XMLs are uploaded together; only basename matching (exact + normalised) is safe
- Coordinator→workflow linking uses `run_job_task` with a sentinel `"{{job_id:<name>}}"`, not a notebook task — do not merge the workflow DAG into the coordinator job
- `_strip_annotation_keys()` is applied to workflow jobs but not coordinator jobs — coordinator jobs set their tasks explicitly and don't go through the same annotation pipeline

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
