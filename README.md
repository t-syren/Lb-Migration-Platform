# SyrenBridge — Migration Platform

A Streamlit-based migration accelerator that wraps **Databricks Labs Lakebridge** and extends it with four custom-built engines for HiveSQL transpilation, Oozie workflow conversion, SSRS report migration, and Talend job conversion.

---

## Table of Contents

- [Overview](#overview)
- [What Lakebridge Provides Natively](#what-lakebridge-provides-natively)
- [What SyrenBridge Adds](#what-syrenbridge-adds)
  - [HiveSQL (Cloudera)](#1-hivesql-cloudera--custom-transpiler-engine)
  - [Oozie (Workflow)](#2-oozie-workflow--12th-dialect)
  - [SSRS (Reports)](#3-ssrs-reports--13th-dialect)
  - [Talend](#4-talend--14th-dialect)
- [HiveSQL Transpiler Pipeline](#hivesql-transpiler-pipeline)
- [Application Tabs](#application-tabs)
- [Supported Technologies — All 14 Dialects](#supported-technologies--all-14-dialects)
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
2. **Transpile** source SQL and workflow code to Databricks-compatible output — across 14 source dialects.

The tool is built on top of [Databricks Labs Lakebridge](https://github.com/databrickslabs/lakebridge), a CLI that handles the bulk of the heavy lifting. SyrenBridge adds a polished UI and four custom-built engines for technologies Lakebridge does not cover out of the box.

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
| SSIS | `ssis` | `.dtsx`, `.xml` |
| Synapse | `synapse` | `.sql`, `.ddl`, `.dml`, `.json` |
| Teradata | `teradata` | `.sql`, `.bteq`, `.tdl`, `.tpt`, `.ddl`, `.dml` |

---

## What SyrenBridge Adds

SyrenBridge contributes four custom engines on top of Lakebridge, covering technologies that the CLI does not handle or where the CLI output is insufficient for production use.

### 1. HiveSQL (Cloudera) — Custom Transpiler Engine

Lakebridge's HiveQL support is limited. SyrenBridge replaces the CLI call with a fully custom, production-grade transpilation pipeline:

- **sqlglot** conversion (`read="hive"`, `write="databricks"`)
- Hive-specific function rewrites: `NVL→COALESCE`, `FROM_UNIXTIME→TIMESTAMP_SECONDS`, `MAPJOIN→BROADCAST`, etc.
- Clause stripping: `ROW FORMAT`, `SERDE`, `STORED AS`, `TBLPROPERTIES`, `CLUSTERED BY`, `SKEWED BY`, etc.
- Variable extraction: `${var}` / `SET var=value` → `DECLARE OR REPLACE VARIABLE`
- Optional Stage 3 LLM fixing for ERROR/BLOCKER statements (Databricks Claude API)
- Outputs `.sql` (Databricks SQL) or `.py` (PySpark notebook)

### 2. Oozie (Workflow) — 12th Dialect

Apache Oozie is not supported by Lakebridge. SyrenBridge converts Oozie XML to **Databricks Jobs API 2.1 JSON** using a custom `lxml`-based parser (`modules/oozie_converter.py`).

**Accepted inputs:** `workflow.xml`, `coordinator.xml`, or both together.

**Output:** One `.json` per job, deployable via the **Create Databricks Workflow** button in the UI.

Key capabilities:
- All Oozie action types → Databricks task types (`notebook_task`, `spark_jar_task`, etc.)
- Fork/join fan-out DAG resolution → `depends_on` wiring
- Coordinator frequency → Quartz cron expression
- Coordinator→workflow auto-linking via `run_job_task` with `{{job_id:<name>}}` sentinel

### 3. SSRS (Reports) — 13th Dialect

SSRS (`.rdl`/`.rdlc`/`.rsd`) reports are converted by a custom `lxml`-based parser (`modules/ssrs_converter.py`). Lakebridge has no SSRS transpiler.

**Output per report:**
- **`.sql` notebook** — one SQL cell per dataset, runnable on a Databricks SQL Warehouse (auto-convertible reports only)
- **`_assessment.json`** — full structural inventory: data sources, datasets, parameters, report items, VB.NET code blocks

Reports using stored procedures or VB.NET code are flagged as manual migration; they still receive an assessment JSON.

T-SQL patterns are automatically flagged with Spark SQL equivalents: `GETDATE()→current_timestamp()`, `ISNULL→ifnull()`, `TOP N→LIMIT N`, etc.

### 4. Talend — 14th Dialect

Talend is supported in the Lakebridge **Analyzer** but not in its Transpiler CLI. SyrenBridge adds a custom XML-based converter (`modules/talend_converter.py`) that parses Talend `.item` job files and generates **Databricks PySpark notebooks** (`.py` files).

**How it works:**
1. Parses `.item` XML — extracts components, parameters, and column schemas
2. Topological sort of the component DAG (connections define execution order)
3. Generates PySpark code per component, threading DataFrames through the chain
4. DB type inferred from component name (`tOracleInput` → `jdbc:oracle:thin:@...`)
5. Complex components (`tMap`, `tFilterRow`, `tJoin`, `tAggregateRow`) get passthrough stubs with `# TODO` comments and warnings
6. Context variables (`${context.var}`) preserved verbatim for replacement with Databricks widgets

**Supported component types (30+):**

| Category | Components |
|----------|-----------|
| DB Inputs | `tDBInput`, `tMysqlInput`, `tOracleInput`, `tMSSqlInput`, `tPostgresqlInput`, `tSnowflakeInput`, `tRedshiftInput`, `tTeradataInput`, `tSynapseInput` |
| File Inputs | `tFileInputDelimited`, `tFileInputJSON`, `tFileInputParquet`, `tFileInputExcel`, `tS3Input` |
| Hive / Delta | `tHiveInput`, `tDeltaLakeInput` |
| DB Outputs | `tDBOutput`, `tMysqlOutput`, `tOracleOutput`, `tMSSqlOutput`, `tPostgresqlOutput`, `tSnowflakeOutput`, `tRedshiftOutput`, `tTeradataOutput` |
| File Outputs | `tFileOutputDelimited`, `tFileOutputParquet`, `tFileOutputJSON` |
| Hive / Delta | `tHiveOutput`, `tDeltaLakeOutput` |
| Transforms | `tMap`, `tFilterRow`, `tSortRow`, `tAggregateRow`, `tJoin`, `tUnite`, `tLogRow`, `tReplaceList`, `tNormalize` |

---

## HiveSQL Transpiler Pipeline

```
Input SQL
 → Stage 1: Pre-processing
   – Extract Hive variables (${var}, SET statements) → DECLARE OR REPLACE VARIABLE
   – Detect blockers: ADD JAR, CREATE TEMPORARY FUNCTION, multi-insert
   – Line-aware statement splitting (handles comments, quoted strings, identifiers)
 → Stage 2: Statement-level conversion
   – sqlglot (read="hive", write="databricks")
   – Function rewrites (NVL, FROM_UNIXTIME, UNIX_TIMESTAMP, MAPJOIN hints)
   – CREATE TABLE normalisation (EXTERNAL→TABLE, USING DELTA, CTAS)
   – Clause stripping (ROW FORMAT, SERDE, STORED AS, TBLPROPERTIES, CLUSTERED BY, etc.)
   – Issue tagging (BLOCKER / ERROR / WARNING / INFO)
 → Stage 3: LLM enhancement (optional — only if endpoint configured)
   – Collects ERROR/BLOCKER statements only
   – Sends to Databricks Claude Sonnet API with prompt
   – Replaces problematic statements; falls back to rule-based on failure
 → Output: Databricks SQL (.sql) or PySpark (.py) + issues log
```

### Issue Severity Levels

| Severity | Meaning | Action |
|----------|---------|--------|
| **BLOCKER** | Cannot auto-convert | Manual rewrite required |
| **ERROR** | Parse/conversion failure | LLM fix candidate or manual review |
| **WARNING** | Unsupported feature detected | Manual review recommended |
| **INFO** | Clause converted — verify behavior | No action usually needed |

---

## Application Tabs

### Get Started Tab
Landing page with 2-step guide (Analyze → Transpile), full 14-dialect transpiler table, 36-technology analyzer list, and link to the Syren S2S platform for PySpark/Serverless migrations.

### Analyzer Tab
Calls `lakebridge analyze` on uploaded files or a Databricks workspace path.
- Select from 36 source technologies
- Upload files / ZIP or browse Databricks workspace
- View analysis report in-browser, download as ZIP

### Transpiler Tab
Converts source code to Databricks-compatible output across all 14 dialects.
- Upload files / ZIP or browse Databricks workspace
- **HiveSQL**: Databricks SQL or PySpark output; optional LLM enhancement
- **Oozie**: Databricks Workflow JSON; one-click **Create Databricks Workflow** button
- **SSRS**: SQL Notebooks + Assessment JSON
- **Talend**: PySpark notebooks (one `.py` per `.item` job file)
- **SSIS**: SparkSQL only (BladeBridge limitation)
- **All others**: choose PySpark or SparkSQL
- Download all output as ZIP or upload directly to Databricks workspace

### Settings Tab
Configure Databricks and LLM credentials.
- Databricks Workspace URL + Personal Access Token
- Optional LLM endpoint + API key for HiveSQL Stage 3 enhancement
- Credentials held in session state only — never written to disk

---

## Supported Technologies — All 14 Dialects

| # | Dialect | Engine | Output Format | Source Extensions |
|---|---------|--------|---------------|-------------------|
| 1 | DataStage | Lakebridge CLI | PySpark / SparkSQL | `.dsx .xml .pjb` |
| 2 | HiveSQL (Cloudera) | **Custom (sqlglot)** | Databricks SQL / PySpark | `.hql .hive .sql .ddl .dml` |
| 3 | Informatica | Lakebridge CLI | PySpark / SparkSQL | `.xml .session .wf .m .mplt .lkp` |
| 4 | Informatica Cloud | Lakebridge CLI | PySpark / SparkSQL | `.xml .json .session` |
| 5 | MS SQL Server | Lakebridge CLI | PySpark / SparkSQL | `.sql .ddl .dml .proc .view` |
| 6 | Netezza | Lakebridge CLI | PySpark / SparkSQL | `.sql .ddl .dml .nzb` |
| 7 | Oracle | Lakebridge CLI | PySpark / SparkSQL | `.sql .ddl .dml .pls .prc .vw` |
| 8 | Snowflake | Lakebridge CLI | PySpark / SparkSQL | `.sql .ddl .dml` |
| 9 | SSIS | BladeBridge (Lakebridge) | SparkSQL only | `.dtsx .xml` |
| 10 | Synapse | Lakebridge CLI | PySpark / SparkSQL | `.sql .ddl .dml .json` |
| 11 | Teradata | Lakebridge CLI | PySpark / SparkSQL | `.sql .bteq .tdl .tpt .ddl .dml` |
| 12 | Oozie (Workflow) | **Custom (lxml)** | Databricks Jobs JSON | `.xml` |
| 13 | SSRS (Reports) | **Custom (ssrs_converter)** | SQL Notebooks + JSON | `.rdl .rdlc .rsd` |
| 14 | Talend | **Custom (talend_converter)** | PySpark Notebooks | `.item .xml` |

---

## Module Architecture

All custom logic lives in `lb_migration_platform_ui/modules/`. These are pure-Python modules with no Streamlit imports — they can be imported and tested independently.

```
modules/
├── __init__.py
├── sql_transpiler.py       # HiveSQL → Databricks SQL/PySpark (3-stage pipeline)
├── llm_converter.py        # LLM-assisted SQL fixing (Databricks Claude API)
├── sql_validator.py        # validate_transpilation() → ValidationResult
├── dummy_data.py           # Faker-based synthetic test data generation
├── oozie_converter.py      # Oozie XML → Databricks Jobs API 2.1 JSON
├── ssrs_converter.py       # SSRS .rdl → SQL notebooks + assessment JSON
├── talend_converter.py     # Talend .item XML → Databricks PySpark notebooks
├── databricks_service.py   # DatabricksClient — workspace browse / upload / download
├── pyspark_migrator.py     # PySpark script HDFS-path and deprecated-API modernisation
├── hdfs_migrator.py        # HDFS listing → dbutils.fs / Unity Catalog scripts
└── prompts/
    ├── __init__.py
    └── hivesql.yml         # LLM prompt for HiveSQL Stage 3 enhancement
```

### Key Entry Points

| Module | Entry Point | Returns |
|--------|------------|---------|
| `sql_transpiler.py` | `run_hive_transpiler(src_dir, out_dir, err_file, target, ...)` | `(ok, stdout, stderr)` |
| `oozie_converter.py` | `convert_oozie_file_set(files: Dict[str,str])` | `{jobs, workflow_job_map, links, warnings}` |
| `ssrs_converter.py` | `convert_ssrs_file_set(files: Dict[str,str])` | `{notebooks, assessments, warnings}` |
| `talend_converter.py` | `convert_talend_file_set(files: Dict[str,str])` | `{notebooks, warnings}` |
| `databricks_service.py` | `DatabricksClient.from_app_context()` | `DatabricksClient` instance |

---

## Sample Files

```
files/
├── source_hive/
│   ├── 01_setup_database.hql        # CREATE DATABASE / CREATE TABLE DDL
│   ├── 02_insert_data.hql           # INSERT with Hive syntax
│   ├── 03_transform_data.hql        # SELECT / INSERT OVERWRITE transforms
│   └── 04_maintenance.hql           # ANALYZE TABLE, MSCK REPAIR, etc.
├── source_spark/
│   ├── pyspark-arraytype.py
│   ├── pyspark-cast-column.py
│   └── pyspark-collect.py
├── sample_oozie/
│   └── workflow.xml                 # 4-action retail ETL pipeline
├── sample_ssis/
│   └── RetailETL.dtsx               # OLE DB Source → Derived Column → Split → Destination
├── sample_ssrs/
│   ├── SalesOrderReport.rdl         # 2 Text datasets — auto-convertible
│   └── InventoryStoredProc.rdl      # StoredProcedure + VB.NET — assessment JSON only
├── sample_talend/
│   ├── CustomerETL.item             # MySQL → tMap → tFilterRow → DeltaLake + tLogRow (reject)
│   ├── SalesAggregation.item        # Oracle × 2 → tJoin → tSortRow → tAggregateRow → CSV
│   ├── HiveToSnowflakeMigration.item # HiveInput → tMap → tReplaceList → Snowflake + Parquet/S3
│   └── FileIngestionPipeline.item   # CSV + JSON + Parquet → tUnite → tMap → HiveOutput
└── sample_hdfs/
    └── hdfs_listing.txt             # Sample hdfs -ls -R output
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

The app opens at `http://localhost:8501`.

### Databricks Apps Deployment

Upload `lb_migration_platform_ui/` as a Databricks App. `requirements.txt` is used for dependency installation. Lakebridge must be available in the app's execution environment.

### Configuring LLM Enhancement (Optional)

HiveSQL Stage 3 can use an LLM to auto-fix ERROR/BLOCKER statements. Configure in the **Settings** tab:

- **LLM Endpoint**: `https://<workspace>.cloud.databricks.com/api/2.0/serving-endpoints/chat/completions`
- **LLM API Key**: Databricks Personal Access Token
- **Model**: `databricks-claude-sonnet-4-6` (default)

Falls back silently to rule-based output on any LLM failure.

---

## Running Tests

```bash
# From Lb-Migration-Platform/
pip install -r lb_migration_platform_ui/requirements-dev.txt
pytest tests/ -v

# Individual modules
pytest tests/test_sql_transpiler.py -v
pytest tests/test_oozie_converter.py -v
pytest tests/test_ssrs_converter.py -v
```

### Test Coverage

| Test File | Tests | What It Covers |
|-----------|-------|----------------|
| `test_sql_transpiler.py` | 11+ | Statement splitting, variable extraction, CREATE TABLE normalisation, full 3-stage pipeline |
| `test_dummy_data.py` | 8 | `generate_rows`, `register_temp_tables` — Hive type mapping, PySpark temp views |
| `test_sql_validator.py` | 5 | Pass/fail detection, schema mismatch, row count diff, invalid SQL |
| `test_oozie_converter.py` | 10 | Action types, dependency graph, coordinator linking, cluster rules |
| `test_ssrs_converter.py` | 28 | RDL parsing, dataset classification, T-SQL flagging, assessment JSON structure |
| `test_pyspark_migrator.py` | 9 | HDFS path rewriting, deprecated API detection |
| `test_hdfs_migrator.py` | 9 | `parse_hdfs_listing`, all script generators, `rewrite_sql_locations` |

> PySpark tests start a local JVM (~20-30 s first run). Subsequent runs reuse the session-scoped fixture.

---

## Project Structure

```
Lb-Migration-Platform/
├── lb_migration_platform_ui/
│   ├── app.py                          # Main Streamlit app
│   ├── requirements.txt                # Runtime dependencies
│   ├── requirements-dev.txt            # Dev/test dependencies
│   └── modules/
│       ├── sql_transpiler.py           # HiveSQL → Databricks SQL (3-stage pipeline)
│       ├── llm_converter.py            # LLM-assisted SQL fixing
│       ├── sql_validator.py            # PySpark-based SQL validation
│       ├── dummy_data.py               # Synthetic test data generation
│       ├── oozie_converter.py          # Oozie XML → Databricks Jobs JSON
│       ├── ssrs_converter.py           # SSRS .rdl → SQL notebooks + assessment JSON
│       ├── talend_converter.py         # Talend .item → PySpark notebooks
│       ├── databricks_service.py       # Workspace browse / file I/O
│       ├── pyspark_migrator.py         # PySpark modernisation
│       ├── hdfs_migrator.py            # HDFS migration scripts
│       └── prompts/
│           └── hivesql.yml             # LLM prompt template
├── tests/
│   ├── conftest.py
│   ├── test_sql_transpiler.py
│   ├── test_dummy_data.py
│   ├── test_sql_validator.py
│   ├── test_oozie_converter.py
│   ├── test_ssrs_converter.py
│   ├── test_pyspark_migrator.py
│   └── test_hdfs_migrator.py
├── files/
│   ├── source_hive/
│   ├── source_spark/
│   ├── sample_oozie/
│   ├── sample_ssis/
│   ├── sample_ssrs/
│   ├── sample_talend/
│   └── sample_hdfs/
├── docs/                               # Architecture diagrams, pitch deck, tech reference
├── pytest.ini
├── CLAUDE.md                           # Project context for AI assistants
├── README.md
└── SSIS_SSRS_MIGRATION.md              # SSIS & SSRS technical reference
```

---

## PySpark & Serverless Migration

PySpark and Spark Classic → Serverless migrations are handled by a separate accelerator.

**Syren Server to Serverless Migration Platform** — [https://syren-s2s-platform-204242957656703.3.azure.databricksapps.com/#home](https://syren-s2s-platform-204242957656703.3.azure.databricksapps.com/#home)
