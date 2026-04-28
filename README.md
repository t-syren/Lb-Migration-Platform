# SyrenBridge — Migration Platform

A Streamlit-based migration accelerator that wraps **Databricks Labs Lakebridge** and extends it with custom-built engines for Hive SQL transpilation and Oozie workflow conversion.

---

## Table of Contents

- [Overview](#overview)
- [What Lakebridge Provides Natively](#what-lakebridge-provides-natively)
- [What SyrenBridge Adds](#what-syrenbridge-adds)
- [HiveSQL Transpiler Enhancements](#hivesql-transpiler-enhancements)
- [Application Tabs](#application-tabs)
  - [Get Started](#get-started-tab)
  - [Analyzer](#analyzer-tab)
  - [Transpiler](#transpiler-tab)
  - [Settings](#settings-tab)
- [Supported Technologies — All 11 Dialects](#supported-technologies--all-11-dialects)
- [Module Architecture](#module-architecture)
- [Sample Files](#sample-files)
- [Running the App](#running-the-app)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)
- [PySpark & Serverless Migration](#pyspark--serverless-migration)

---

## Overview

SyrenBridge is a browser-based migration toolkit deployed on Databricks Apps. It gives data engineers a single interface to:

1. **Analyze** legacy data platform assets — discover schemas, stored procedures, and dependencies across 36 source technologies.
2. **Transpile** source SQL and workflow code to Databricks-compatible output — across 11 source dialects.

The tool is built on top of [Databricks Labs Lakebridge](https://github.com/databrickslabs/lakebridge), a CLI that handles the bulk of the heavy lifting. SyrenBridge adds a polished UI and two custom-built engines for technologies Lakebridge does not cover out of the box.

---

## What Lakebridge Provides Natively

Lakebridge is the open-source CLI layer that does the actual analysis and transpilation work. SyrenBridge calls it as a subprocess.

### Analyzer — 36 Technologies

The Analyzer tab calls `lakebridge analyze` and supports the following source systems natively:

| Category | Technologies |
|----------|-------------|
| Data Warehouses | Teradata, Netezza, Oracle, MS SQL Server, Snowflake, Synapse, Redshift, Vertica, IBM DB2, SAP HANA |
| ETL/ELT Tools | Informatica PowerCenter, Informatica Cloud (IICS), DataStage, SSIS, Talend, Ab Initio, Pentaho, ODI, OWB |
| Hadoop/Hive | HiveQL, Spark SQL, Impala, HBase |
| BI/Reporting | Tableau, Power BI, MicroStrategy, Business Objects, Cognos, OBIEE, Qlik |
| Other | Cassandra, MongoDB, Mainframe COBOL, JCL, Shell Scripts, PL/SQL |

> The complete list of 36 technologies is determined by the installed version of Lakebridge. Run `lakebridge analyze --help` to see the current list.

### Transpiler — 10 CLI-Based Dialects

Lakebridge handles transpilation for these 10 dialects via `lakebridge transpile`:

| Dialect | CLI Key | Source Extensions |
|---------|---------|-------------------|
| DataStage | `datastage` | `.dsx`, `.xml`, `.pjb` |
| Informatica | `informatica` | `.xml`, `.session`, `.wf`, `.m`, `.mplt`, `.lkp` |
| Informatica Cloud | `informatica_cloud` | `.xml`, `.json`, `.session` |
| MS SQL Server | `mssql` | `.sql`, `.ddl`, `.dml`, `.proc`, `.view` |
| Netezza | `netezza` | `.sql`, `.ddl`, `.dml`, `.nzb` |
| Oracle | `oracle` | `.sql`, `.ddl`, `.dml`, `.pls`, `.pks`, `.pkb`, `.prc`, `.fnc`, `.vw`, `.trg` |
| Snowflake | `snowflake` | `.sql`, `.ddl`, `.dml` |
| Synapse | `synapse` | `.sql`, `.ddl`, `.dml`, `.json` |
| Teradata | `teradata` | `.sql`, `.bteq`, `.tdl`, `.tpt`, `.ddl`, `.dml` |

---

## What SyrenBridge Adds

SyrenBridge contributes two custom engines on top of Lakebridge:

### 1. HiveSQL (Cloudera) — Custom Transpiler Engine

Lakebridge's HiveQL support is limited. SyrenBridge replaces the CLI call with a fully custom, production-grade transpilation pipeline:

#### Enhanced Transpilation Pipeline

The transpiler (`modules/sql_transpiler.py`) processes Hive SQL in three stages:

**Stage 1: Pre-Processing (Whole-File Analysis)**
- Extract and normalize Hive variables: `${var}`, `${hivevar:var}`, `SET var=value`
  - Converts to Databricks `DECLARE OR REPLACE VARIABLE` syntax
  - Filters out engine configs (`spark.*`, `hive.*`, `mapreduce.*`)
- Detect unsupported constructs:
  - `ADD JAR` (custom UDF JARs) — **BLOCKER**
  - `CREATE TEMPORARY FUNCTION` — **BLOCKER**
  - `EXPLAIN` statements (removed silently)
  - Multi-insert statements — **BLOCKER**
- Line-aware SQL statement splitting with full comment handling:
  - Single-line (`--`) and block (`/* */`) comment preservation
  - Quoted string and identifier handling (single/double/backtick)
  - Each statement tracked with original line number

**Stage 2: Statement-Level Conversion**
- **sqlglot transpilation** (`read="hive"`, `write="databricks"`) for each statement
- Hive-specific transformations (via regex):
  - `NVL()` → `COALESCE()`
  - `FROM_UNIXTIME(ts, fmt)` → `DATE_FORMAT(TIMESTAMP_SECONDS(ts), fmt)`
  - `FROM_UNIXTIME(ts)` → `TIMESTAMP_SECONDS(ts)`
  - `UNIX_TIMESTAMP()` → `CURRENT_TIMESTAMP()`
  - `DISTRIBUTE BY` / `SORT BY` → removed
  - `MAPJOIN` hints → `BROADCAST` hints
- **CREATE TABLE handling**:
  - Normalizes `CREATE EXTERNAL TABLE` → `CREATE TABLE`
  - Adds `USING DELTA` clause
  - Handles CTAS (`CREATE TABLE AS SELECT`)
  - Preserves `LOCATION` directives (rewrite HDFS paths to dbfs:/)
  - Removes Hive-only clauses: `ROW FORMAT`, `SERDE`, `STORED AS`, `TBLPROPERTIES`, `CLUSTERED BY`, `SORTED BY`, `SKEWED BY`, `INPUTFORMAT`, `OUTPUTFORMAT`
- **Special DDL fixes**:
  - `MSCK REPAIR TABLE tbl` → `REFRESH TABLE tbl`
  - `ANALYZE TABLE tbl COMPUTE STATISTICS FOR COLUMNS` → `ANALYZE TABLE tbl COMPUTE STATISTICS FOR ALL COLUMNS`
  - Flags external tables and CTAS for manual review (INFO-level issues)

**Stage 3: LLM Enhancement (Optional)**
- If LLM endpoint configured (`llm_endpoint`, `llm_api_key`):
  - Load prompt from `modules/prompts/hivesql.yml`
  - Collect only problematic statements (ERROR or BLOCKER severity)
  - Send to Databricks Claude Sonnet API with context
  - Parse statement markers (`-- STATEMENT_ID: idx`) in output
  - Replace problematic statements while preserving unrelated ones
  - Safety checks: preserve INSERT/PARTITION logic, minimum length validation
  - Falls back to rule-based output on LLM failure or timeout

#### Output Formats

- **Databricks SQL (`.sql`)**: Direct SQL suitable for Databricks SQL Warehouses
  - Includes variable declarations
  - Optional catalog/schema prefixes
  - Issues annotated as SQL comments
- **PySpark (`.py`)**: Notebook-ready Python code
  - SparkSession initialization
  - `spark.sql("""statement""")` wrapping
  - Issues annotated as Python comments


### 2. Oozie (Workflow) — 11th Dialect

Apache Oozie is not supported by Lakebridge. SyrenBridge adds it as the 11th transpiler dialect:

- **Input**: Oozie `workflow.xml` files
- **Parser**: lxml-based XML parser (`modules/oozie_converter.py`) that extracts actions, action types, dependencies, and parameters
- **Output**: Databricks Jobs API 2.1 JSON (`/api/2.1/jobs` format), ready to import via the Databricks CLI or SDK
- **Action type mapping**:

| Oozie Action | Databricks Task Type |
|-------------|---------------------|
| `hive` | `sql_task` (SQL Warehouse query) |
| `spark` | `spark_jar_task` |
| `shell` | `notebook_task` (shell wrapper notebook) |
| `java` | `spark_jar_task` |
| other (pig, sqoop, etc.) | `notebook_task` (migration stub) |

- **DAG support**: handles fan-in dependencies (multiple upstream actions pointing to the same downstream action)

---

## HiveSQL Transpiler Enhancements

The HiveSQL transpiler has been significantly enhanced with a **3-stage production-grade pipeline**, advanced issue detection, and optional LLM-assisted fixing.

### Transpilation Pipeline Overview

```
┌──────────────────────────────────────────────────────────────┐
│ Stage 1: Pre-Processing (Whole-File Analysis)              │
├──────────────────────────────────────────────────────────────┤
│ • Extract & normalize Hive variables (${var}, SET statements)
│ • Detect blockers: ADD JAR, CREATE TEMPORARY FUNCTION       │
│ • Line-aware SQL statement splitting with full comment      │
│   handling (single-line, block, quoted strings, identifiers)│
│ • Generate DECLARE OR REPLACE VARIABLE statements           │
│ • Remove: UDF definitions, EXPLAIN plans, CLUSTERED/SORTED  │
│   BY clauses                                                 │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ Stage 2: Statement-Level Conversion & Cleaning              │
├──────────────────────────────────────────────────────────────┤
│ • sqlglot transpilation (read="hive", write="databricks")   │
│ • Hive → Databricks function rewrites (NVL, FROM_UNIXTIME,  │
│   UNIX_TIMESTAMP, MAPJOIN hints, etc.)                      │
│ • CREATE TABLE normalization (EXTERNAL → TABLE,             │
│   USING DELTA, CTAS handling)                               │
│ • DDL fixes (MSCK REPAIR → REFRESH, ANALYZE normalization)  │
│ • Issue tagging (unsupported constructs, parse errors)      │
│ • Hive clause stripping (ROW FORMAT, SERDE, STORED AS, etc.)│
└──────────────────────────────────────────────────────────────┘
                           ↓
        ┌──────────────────┴──────────────────┐
        ↓ (if LLM configured)                 ↓ (no LLM)
┌──────────────────────────────────────────┐
│ Stage 3: LLM Enhancement (Optional)      │
├──────────────────────────────────────────┤
│ • Collect ERROR/BLOCKER statements       │
│ • Send to Databricks Claude with context │
│ • Parse STATEMENT_ID markers             │
│ • Replace problematic statements         │
│ • Fallback to rule-based output on error │
└──────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ Output: Databricks SQL (.sql) or PySpark (.py)             │
│         + Issues log (SQL/Python comments)                   │
│         + Error file (any read/write errors)                 │
└──────────────────────────────────────────────────────────────┘
```


### Issue Detection & Categorization

All issues are categorized by severity:

| Severity | Meaning | Action |
|----------|---------|--------|
| **BLOCKER** | Fatal — transpilation cannot proceed | Manual rewrite required |
| **ERROR** | Parse/conversion error | Candidate for LLM fixing or manual review |
| **WARNING** | Unsupported feature detected | Manual review recommended |
| **INFO** | FYI — clause converted, verify behavior | Normal, no action required |

**Common blockers:**
- `ADD JAR` (custom UDF JARs) — requires PySpark UDF registration
- `CREATE TEMPORARY FUNCTION` — custom Hive UDFs not portable
- Multi-insert statements — not supported in Databricks
- `LOAD DATA` (HDFS bulk load) — use `COPY INTO` or Databricks I/O instead

**Common warnings:**
- Dynamic variables (`${...}`) — may need manual substitution
- External tables — converted to Delta, verify LOCATION and format

**Common info:**
- `MSCK REPAIR TABLE` → `REFRESH TABLE` — internal catalog maintained automatically
- `ANALYZE TABLE ... FOR COLUMNS` → normalized syntax

### LLM-Assisted Fixing (Optional)

When LLM credentials are provided, the transpiler automatically attempts to fix problematic statements:

**Configuration:**
- `llm_endpoint`: Databricks API endpoint (e.g., `https://<workspace>.cloud.databricks.com/api/2.0/serving-endpoints/chat/completions`)
- `llm_api_key`: Databricks Personal Access Token
- Model: Defaults to `databricks-claude-sonnet-4-6`

**Flow:**
1. Collect statements with ERROR or BLOCKER severity
2. Load prompt from `modules/prompts/hivesql.yml`
3. Send batch with `-- STATEMENT_ID: idx` markers
4. Parse LLM output using markers
5. Replace only problematic statements (safety checks):
   - Minimum output length (≥10 chars)
   - Preserve INSERT/PARTITION keywords
   - Exact statement ID matching
6. Fall back to rule-based output if LLM fails/times out

**Safety guarantees:**
- LLM only touches ERROR/BLOCKER statements
- INFO/WARNING statements unmodified
- Unrelated statements fully preserved
- Automatic fallback on any LLM error
- Output validity checks prevent broken SQL

### Supported Transformations

**Function Rewrites:**
| Hive Function | Databricks Equivalent |
|---------------|----------------------|
| `NVL(x, y)` | `COALESCE(x, y)` |
| `FROM_UNIXTIME(ts)` | `TIMESTAMP_SECONDS(ts)` |
| `FROM_UNIXTIME(ts, fmt)` | `DATE_FORMAT(TIMESTAMP_SECONDS(ts), fmt)` |
| `UNIX_TIMESTAMP()` | `CURRENT_TIMESTAMP()` |
| `/\*+ MAPJOIN(tbl) \*/` | `/\*+ BROADCAST(tbl) \*/` |

**Clause Handling:**
| Hive Clause | Action | Databricks Behavior |
|-------------|--------|-------------------|
| `ROW FORMAT DELIMITED` | Removed | Inferred from data format |
| `ROW FORMAT SERDE` | Removed | Use `STORED AS PARQUET` / `ORC` instead |
| `STORED AS {TEXTFILE,ORC,PARQUET,…}` | Removed | Use table format parameter |
| `TBLPROPERTIES (...)` | Removed | Unsupported, migrate manually |
| `LOCATION 'hdfs://...'` | Preserved | Rewrite to `dbfs:/` or `abfss://` path |
| `CLUSTERED BY` | Removed | Use Z-order or clustering hints |
| `SORTED BY` | Removed | Use ORDER BY in queries |
| `SKEWED BY` | Removed | Not needed in Databricks |
| `INPUTFORMAT` / `OUTPUTFORMAT` | Removed | Auto-detected from `STORED AS` |

**CREATE TABLE Normalization:**
- `CREATE EXTERNAL TABLE` → `CREATE TABLE` (Delta-managed by default)
- Adds `USING DELTA` clause
- Handles CTAS (Create Table As Select) — schema inferred from SELECT
- External table LOCATION preserved (verify hdfs:// → dbfs:/ rewrite)
- Unsupported clauses stripped, issues flagged for review

---

### Get Started Tab

Landing page and documentation for new users.

- 2-step guide (Analyze → Transpile)
- Side-by-side comparison: what Lakebridge provides vs. what SyrenBridge adds
- Full 11-dialect transpiler table with engine type and output format
- 36 Analyzer technologies grouped by SQL / ETL / Code
- Link to the Syren S2S platform for PySpark/Serverless migrations

### Analyzer Tab

Calls `lakebridge analyze` on uploaded source files or a local directory.

- Upload source files (any format) or point to a directory
- Select the source technology from the 36-technology dropdown
- View the analysis report in-browser
- Download the full report as a ZIP

### Transpiler Tab

Converts source code to Databricks-compatible output.

- Select source dialect from 11 options
- Upload individual files or a ZIP archive
- For HiveSQL: choose output format (Databricks SQL `.sql` or PySpark `.py`); green badge clarifies Databricks dialect is used
- For Oozie: output is always Databricks Workflow JSON; limitations warning (fork/join, EL expressions, Coordinator) shown with results
- For all other dialects: choose PySpark or SparkSQL
- View transpiled output with syntax highlighting per file type
- Download all output as a ZIP

**PySpark note**: A blue info banner in the Transpiler tab links to the Syren Server to Serverless Migration Platform for PySpark and Spark Classic → Serverless migrations.

### Settings Tab

Configure Databricks credentials for local use. On Databricks Apps, auth is automatic.

- Input Databricks Workspace URL and Personal Access Token
- Or specify a named profile from `~/.databrickscfg`
- Credentials are held in session state only — never written to disk
- Live connection test via `databricks auth status`
- Auto-detects if `DATABRICKS_HOST` is already set in the environment

---

## Supported Technologies — All 11 Dialects

| # | Dialect | Engine | Output Format |
|---|---------|--------|---------------|
| 1 | DataStage | Lakebridge CLI | PySpark / SparkSQL |
| 2 | HiveSQL (Cloudera) | **Custom (sqlglot)** | Databricks SQL |
| 3 | Informatica | Lakebridge CLI | PySpark / SparkSQL |
| 4 | Informatica Cloud | Lakebridge CLI | PySpark / SparkSQL |
| 5 | MS SQL Server | Lakebridge CLI | PySpark / SparkSQL |
| 6 | Netezza | Lakebridge CLI | PySpark / SparkSQL |
| 7 | Oracle | Lakebridge CLI | PySpark / SparkSQL |
| 8 | Snowflake | Lakebridge CLI | PySpark / SparkSQL |
| 9 | Synapse | Lakebridge CLI | PySpark / SparkSQL |
| 10 | Teradata | Lakebridge CLI | PySpark / SparkSQL |
| 11 | Oozie (Workflow) | **Custom (lxml)** | Databricks Jobs API 2.1 JSON |

---

## Module Architecture

All custom logic lives in `lb_migration_platform_ui/modules/`. These are pure-Python modules with no Streamlit imports — they can be imported and tested independently.

```
modules/
├── __init__.py
├── sql_transpiler.py       # transpile_hive_sql(), run_hive_transpiler(), handle_hive_variables()
├── llm_converter.py        # LLMConverter class for LLM-assisted SQL fixing
├── sql_validator.py        # validate_transpilation() → ValidationResult
├── dummy_data.py           # generate_rows(), register_temp_tables()
├── oozie_converter.py      # parse_workflow(), to_databricks_job(), workflow_to_json()
├── pyspark_migrator.py     # migrate_pyspark_script(), migrate_notebook()
├── hdfs_migrator.py        # parse_hdfs_listing(), generate_fs_cp_script(), ...
└── prompts/
    ├── __init__.py
    └── hivesql.yml         # LLM prompt template for HiveSQL fixes
```

### `sql_transpiler.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `split_sql_statements` | `(sql: str) -> List[Tuple[str, int]]` | Parse SQL into statements with line-aware comment handling; returns `[(stmt, line_number), ...]` |
| `handle_hive_variables` | `(content: str) -> Tuple[str, List[str]]` | Extract Hive variables, generate `DECLARE OR REPLACE VARIABLE` statements, return cleaned SQL and declarations |
| `create_table_handler` | `(stmt: str, location: str\|None) -> str` | Normalize CREATE TABLE statements: add `USING DELTA`, handle CTAS, preserve/add LOCATION |
| `add_global_issue` | `(issues, category, message, pattern, content, severity)` | Add multi-line issue for patterns found in entire file |
| `add_statement_issue` | `(issues, category, message, stmt, line_no, stmt_index, severity)` | Add issue for specific statement |
| `run_hive_transpiler` | `(src_dir, out_dir, err_file, target, catalog, schema, llm_endpoint, llm_api_key) -> Tuple[bool, str, str]` | **Main entry point**: transpile all `.hql` files in directory, apply transformations, optionally fix with LLM, output `.sql` or `.py` |

**Key parameters for `run_hive_transpiler`**:
- `target`: `"SPARKSQL"` (output `.sql`) or `"PYSPARK"` (output `.py`)
- `catalog`, `schema`: Optional Databricks three-level namespace
- `llm_endpoint`, `llm_api_key`: Optional LLM service endpoint (Databricks API) and token for statement enhancement
- `err_file`: Error log file path

### `llm_converter.py`

LLM-assisted SQL transpilation engine. Integrates with Databricks API or other OpenAI-compatible endpoints.

| Class/Function | Signature | Description |
|---|---|---|
| `load_prompt` | `(prompt_obj) -> Dict` | Load YAML prompt file or return dict as-is |
| `format_issues` | `(issues) -> str` | Format issue list as `[SEVERITY] CATEGORY → message` strings |
| `LLMConverter.__init__` | `(api_key, endpoint, model, max_retries, timeout, max_tokens)` | Initialize LLM client with Databricks defaults: `databricks-claude-sonnet-4-6`, max_tokens=12000 |
| `LLMConverter.build_prompt` | `(prompt_config, code, issues)` | Combine system prompt, user template, and issues into final prompt |
| `LLMConverter.call_llm` | `(system_prompt, user_prompt) -> str` | Call LLM API with retry logic (exponential backoff, request tracking) |
| `LLMConverter.code_convert_llm` | `(code, prompt, issues, fallback) -> str` | **Main entry point**: load prompt, call LLM, return fixed code or original on failure |

**Key features**:
- Retries with exponential backoff (default 3 attempts)
- Request ID tracking for debugging
- Fallback to original code on error (if `fallback=True`)
- Strict safety checks: minimum output length, preserves INSERT/PARTITION logic

### `prompts/hivesql.yml`

YAML prompt template for LLM-based HiveSQL fixing. Controls LLM behavior during Stage 3 enhancement.

```yaml
system: |
  Convert Hive SQL to Databricks SQL using LLM.
  Focus on fixing syntax and compatibility issues while preserving original logic.
  Only return valid Databricks SQL without explanations or markdown.

rules: |
  - ONLY return valid Databricks SQL
  - DO NOT add explanations or comments
  - DO NOT add markdown (no ```sql)
  - DO NOT change business logic
  - ONLY fix statements related to issues
  - Keep output minimal and executable
  - If unsure, return the original SQL without changes
  - DO NOT remove partition logic
  - DO NOT change table behavior
  - ONLY modify statements that contain issues
  - DO NOT modify unrelated statements
  - PRESERVE structure of other statements exactly
  - FIX only syntax incompatibilities
  - DO NOT skip required transformations

template: |
  Input SQL:
  {code}

  Issues detected:
  {issues}

  You MUST fix the issues if possible.

  Output only SQL.
```

When multiple statements are passed, they are marked with `-- STATEMENT_ID: idx` for precise parsing of LLM output.

### `dummy_data.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `generate_rows` | `(schema: Dict[str, str], n: int) -> List[Dict]` | Generate `n` synthetic rows for a `{col: hive_type}` schema using Faker |
| `register_temp_tables` | `(spark, tables: Dict[str, Dict], n: int)` | Register each table as a PySpark temp view with `n` dummy rows |

Supported Hive types: `INT`, `BIGINT`, `SMALLINT`, `TINYINT`, `FLOAT`, `DOUBLE`, `DECIMAL`, `STRING`, `VARCHAR`, `CHAR`, `BOOLEAN`, `DATE`, `TIMESTAMP`, `BINARY`.

### `sql_validator.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `validate_transpilation` | `(spark, original_sql, transpiled_sql) -> ValidationResult` | Execute both SQL strings in local PySpark, compare row counts, schema, and sample data |

`ValidationResult` fields: `passed`, `row_count_match`, `schema_match`, `data_match`, `original_count`, `transpiled_count`, `original_columns`, `transpiled_columns`, `diff_report`, `error`.

### `oozie_converter.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `parse_workflow` | `(xml_str: str) -> List[OozieAction]` | Parse Oozie workflow XML into a list of `OozieAction` dataclasses |
| `to_databricks_job` | `(actions, job_name) -> Dict` | Convert actions to a Databricks Jobs API 2.1 payload with dependency graph |
| `workflow_to_json` | `(xml_str, job_name) -> str` | End-to-end: parse XML and return formatted JSON string |

`OozieAction` fields: `name`, `action_type`, `ok_to`, `error_to`, `config`.

### `pyspark_migrator.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `migrate_pyspark_script` | `(code: str) -> MigrationResult` | Rewrite HDFS paths to DBFS paths and flag deprecated API usage |
| `migrate_notebook` | `(ipynb_json: str) -> MigrationResult` | Migrate all code cells in a Jupyter notebook JSON |

Detected patterns: `hdfs://` paths, `sc.textFile()`, `SparkContext()`, `SparkConf()`, `.foreachPartition()`, `.collect()` on large DataFrames, excessive `.repartition()`.

### `hdfs_migrator.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `parse_hdfs_listing` | `(text: str) -> List[HDFSEntry]` | Parse `hdfs dfs -ls -R` output |
| `generate_fs_cp_script` | `(entries, hdfs_host) -> str` | Generate `databricks fs cp` shell script |
| `generate_dbutils_script` | `(entries, hdfs_host) -> str` | Generate `dbutils.fs.cp()` Python notebook cells |
| `generate_unity_catalog_script` | `(entries, catalog, schema, ...) -> str` | Generate `CREATE VOLUME` statements for Unity Catalog |
| `rewrite_sql_locations` | `(sql, target, ...) -> str` | Rewrite `LOCATION 'hdfs://...'` to `dbfs:/` or `abfss://` |

---

## Sample Files

```
files/
├── source_hive/
│   ├── 01_setup_database.hql       # CREATE DATABASE / CREATE TABLE DDL
│   ├── 02_insert_data.hql          # INSERT statements with Hive syntax
│   ├── 03_transform_data.hql       # SELECT / INSERT OVERWRITE transforms
│   └── 04_maintenance.hql          # ANALYZE TABLE, MSCK REPAIR, etc.
├── source_spark/
│   ├── pyspark-arraytype.py        # ArrayType column operations
│   ├── pyspark-cast-column.py      # Column casting patterns
│   └── pyspark-collect.py          # .collect() anti-pattern example
├── sample_oozie/
│   └── workflow.xml                # 4-action retail ETL pipeline
│                                   # (hive → hive → spark → shell)
└── sample_hdfs/
    └── hdfs_listing.txt            # Sample hdfs -ls -R output (12 entries)
```

---

## Running the App

### Prerequisites

- Python 3.11+
- Java 11+ (required by PySpark — `JAVA_HOME` must be set)
- Databricks Labs Lakebridge installed and on `PATH`

### Local Development

```bash
# 1. Create and activate virtual environment
python -m venv lb
source lb/bin/activate          # macOS/Linux
# lb\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r lb_migration_platform_ui/requirements.txt

# 3. Run the app
cd lb_migration_platform_ui
streamlit run app.py
```

The app will open at `http://localhost:8501`.

### Databricks Apps Deployment

Upload the `lb_migration_platform_ui/` directory as a Databricks App. The `requirements.txt` is used for dependency installation. Lakebridge must be available in the app's execution environment.

### Configuring LLM Enhancement (Optional)

HiveSQL transpilation can optionally use an LLM to fix problematic statements. This requires a Databricks workspace with a serving endpoint or an external API-compatible LLM service.

**Step 1: Get Databricks Credentials**
- Workspace URL: `https://<workspace>.cloud.databricks.com`
- Personal Access Token: Generate from Databricks Account Console
- Serving Endpoint (if using Databricks):
  - Ensure Claude model is deployed in your workspace
  - Endpoint path: `/api/2.0/serving-endpoints/chat/completions`

**Step 2: Configure in Streamlit App**
In the **Settings** tab, you'll see optional LLM fields:
- **LLM Endpoint**: Full URL to Claude endpoint (Databricks supported)
- **LLM API Key**: Personal Access Token

When both are filled, HiveSQL Transpiler automatically uses LLM for Stage 3 enhancement.

**Step 3: Test LLM Connection**
Run a test transpilation with a problematic HiveSQL file:
- Upload file with ERROR/BLOCKER issues
- Check the LLM logs in the app output
- Verify fixed SQL in the result

**Example with Databricks Claude:**
```
Endpoint: https://my-workspace.cloud.databricks.com/api/2.0/serving-endpoints/chat/completions
API Key: <personal-access-token>
Model: databricks-claude-sonnet-4-6 (default)
```

**LLM Request Limits:**
- Timeout: 300 seconds (5 minutes per batch)
- Max retries: 3 (exponential backoff)
- Max tokens: 12,000 per response
- Max statement batch size: All ERROR/BLOCKER statements in one file

**Fallback Behavior:**
If LLM is unavailable or fails:
1. Transpiler continues with Stage 2 (rule-based) output
2. Issues remain flagged for manual review
3. Original code fallback if LLM timeout
4. No data loss — errors logged, not thrown

---

## Running Tests

```bash
# From the Lb-Migration-Platform/ directory

# Install dev dependencies (includes Faker, pytest)
pip install -r lb_migration_platform_ui/requirements-dev.txt

# Run all tests
pytest tests/ -v

# Run a specific module
pytest tests/test_sql_transpiler.py -v
pytest tests/test_oozie_converter.py -v
```

### Test Coverage by Module

| Test File | Tests | What It Covers |
|-----------|-------|----------------|
| `test_sql_transpiler.py` | 11+ | `split_sql_statements`, `handle_hive_variables`, `create_table_handler`, `run_hive_transpiler` — statement parsing, variable extraction, CREATE TABLE normalization, full transpilation pipeline, clause stripping, transformations |
| `test_dummy_data.py` | 8 | `generate_rows`, `register_temp_tables` — type mapping, row counts, Spark temp view registration |
| `test_sql_validator.py` | 5 | `validate_transpilation` — pass/fail detection, schema mismatch, row count diff, invalid SQL handling |
| `test_oozie_converter.py` | 10 | `parse_workflow`, `to_databricks_job` — action types, dependency graph, output structure |
| `test_pyspark_migrator.py` | 9 | `migrate_pyspark_script` — HDFS path rewriting, deprecated API warnings |
| `test_hdfs_migrator.py` | 9 | `parse_hdfs_listing`, all script generators, `rewrite_sql_locations` |

> SQL Validator tests start a local PySpark session (JVM startup ~20-30s on first run). Subsequent test runs reuse the session-scoped fixture and are faster.

**Enhanced sql_transpiler.py Tests:**
The transpiler module now tests:
- Line-aware SQL statement splitting with comment preservation
- Multi-line comment handling (`/* */` and `--`)
- Quoted string and identifier protection
- Hive variable extraction and normalization
- SET statement filtering (configs vs. user variables)
- CREATE TABLE normalization (EXTERNAL, CTAS, USING DELTA, LOCATION)
- Issue categorization (BLOCKER, ERROR, WARNING, INFO)
- Function rewrites (NVL, FROM_UNIXTIME, UNIX_TIMESTAMP, MAPJOIN)
- Clause stripping (ROW FORMAT, SERDE, STORED AS, TBLPROPERTIES, etc.)
- Statement-level transpilation with error handling
- Full pipeline execution (all three stages)

---

## Project Structure

```
Lb-Migration-Platform/
├── lb_migration_platform_ui/
│   ├── app.py                       # Main Streamlit app (~1500 lines)
│   ├── requirements.txt             # Runtime dependencies
│   ├── requirements-dev.txt         # Dev/test dependencies
│   └── modules/
│       ├── __init__.py
│       ├── sql_transpiler.py        # HiveSQL → Databricks SQL (3-stage pipeline)
│       ├── llm_converter.py         # LLM-assisted SQL fixing (Databricks API)
│       ├── sql_validator.py         # PySpark-based SQL validation
│       ├── dummy_data.py            # Synthetic test data generation
│       ├── oozie_converter.py       # Oozie XML → Databricks Jobs JSON
│       ├── pyspark_migrator.py      # PySpark script modernization
│       ├── hdfs_migrator.py         # HDFS path migration scripts
│       └── prompts/
│           ├── __init__.py
│           └── hivesql.yml          # LLM prompt template for HiveSQL fixing
├── tests/
│   ├── conftest.py                  # Session-scoped SparkSession fixture
│   ├── test_sql_transpiler.py       # Enhanced with split_sql_statements, handle_hive_variables, etc.
│   ├── test_dummy_data.py
│   ├── test_sql_validator.py
│   ├── test_oozie_converter.py
│   ├── test_pyspark_migrator.py
│   └── test_hdfs_migrator.py
├── files/
│   ├── source_hive/                 # Sample HiveQL files
│   │   ├── 01_setup_database.hql
│   │   ├── 02_insert_data.hql
│   │   ├── 03_transform_data.hql
│   │   └── 04_maintenance.hql
│   ├── source_spark/                # Sample PySpark scripts
│   ├── sample_oozie/                # Sample Oozie workflow XML
│   └── sample_hdfs/                 # Sample HDFS listing
├── pytest.ini
├── CLAUDE.md                        # Project context for AI assistants
└── README.md
```

---

## PySpark & Serverless Migration

PySpark and Spark Classic → Serverless migrations are handled by a separate accelerator.

**Syren Server to Serverless Migration Platform** — [https://syren-s2s-platform-204242957656703.3.azure.databricksapps.com/#home](https://syren-s2s-platform-204242957656703.3.azure.databricksapps.com/#home)
