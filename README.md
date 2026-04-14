# SyrenBridge — Migration Platform

A Streamlit-based migration accelerator that wraps **Databricks Labs Lakebridge** and extends it with custom-built engines for Hive SQL transpilation and Oozie workflow conversion.

---

## Table of Contents

- [Overview](#overview)
- [What Lakebridge Provides Natively](#what-lakebridge-provides-natively)
- [What SyrenBridge Adds](#what-syrenbridge-adds)
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

Lakebridge's HiveQL support is limited. SyrenBridge replaces the CLI call with a fully custom pipeline:

- **sqlglot** (`read="hive"`, `write="databricks"`) for structural SQL conversion
- **Regex-based clause stripping** for Hive-specific constructs that have no Databricks equivalent:
  - `STORED AS {TEXTFILE|ORC|PARQUET|…}`
  - `ROW FORMAT DELIMITED FIELDS TERMINATED BY …`
  - `SERDE '…' WITH SERDEPROPERTIES (…)`
  - `TBLPROPERTIES (…)`
  - `LOCATION 'hdfs://…'`
- Output targets **Databricks SQL dialect** (not generic Spark SQL), so transpiled code runs directly on Databricks SQL Warehouses and clusters.

The custom engine lives in `modules/sql_transpiler.py`. It is also backed by a local-mode PySpark validation layer (`modules/sql_validator.py`) that executes both the original and transpiled SQL against dummy data to confirm row count and schema equivalence.

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

## Application Tabs

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
├── sql_transpiler.py      # transpile_hive_sql(), infer_schema()
├── dummy_data.py          # generate_rows(), register_temp_tables()
├── sql_validator.py       # validate_transpilation() → ValidationResult
├── oozie_converter.py     # parse_workflow(), to_databricks_job(), workflow_to_json()
├── pyspark_migrator.py    # migrate_pyspark_script(), migrate_notebook()
└── hdfs_migrator.py       # parse_hdfs_listing(), generate_fs_cp_script(), ...
```

### `sql_transpiler.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `transpile_hive_sql` | `(sql: str) -> str` | Transpile Hive SQL to Databricks SQL using sqlglot + regex stripping |
| `infer_schema` | `(sql: str) -> Dict[str, str]` | Extract `{col_name: hive_type}` from the first `CREATE TABLE` in a SQL string; excludes partition columns |

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
| `test_sql_transpiler.py` | 11 | `transpile_hive_sql`, `infer_schema` — clause stripping, schema inference, partition column exclusion |
| `test_dummy_data.py` | 8 | `generate_rows`, `register_temp_tables` — type mapping, row counts, Spark temp view registration |
| `test_sql_validator.py` | 5 | `validate_transpilation` — pass/fail detection, schema mismatch, row count diff, invalid SQL handling |
| `test_oozie_converter.py` | 10 | `parse_workflow`, `to_databricks_job` — action types, dependency graph, output structure |
| `test_pyspark_migrator.py` | 9 | `migrate_pyspark_script` — HDFS path rewriting, deprecated API warnings |
| `test_hdfs_migrator.py` | 9 | `parse_hdfs_listing`, all script generators, `rewrite_sql_locations` |

> SQL Validator tests start a local PySpark session (JVM startup ~20-30s on first run). Subsequent test runs reuse the session-scoped fixture and are faster.

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
│       ├── sql_transpiler.py        # HiveSQL → Databricks SQL
│       ├── dummy_data.py            # Synthetic test data generation
│       ├── sql_validator.py         # PySpark-based SQL validation
│       ├── oozie_converter.py       # Oozie XML → Databricks Jobs JSON
│       ├── pyspark_migrator.py      # PySpark script modernization
│       └── hdfs_migrator.py         # HDFS path migration scripts
├── tests/
│   ├── conftest.py                  # Session-scoped SparkSession fixture
│   ├── test_sql_transpiler.py
│   ├── test_dummy_data.py
│   ├── test_sql_validator.py
│   ├── test_oozie_converter.py
│   ├── test_pyspark_migrator.py
│   └── test_hdfs_migrator.py
├── files/
│   ├── source_hive/                 # Sample HiveQL files
│   ├── source_spark/                # Sample PySpark scripts
│   ├── sample_oozie/                # Sample Oozie workflow XML
│   └── sample_hdfs/                 # Sample HDFS listing
├── pytest.ini
└── README.md
```

---

## PySpark & Serverless Migration

PySpark and Spark Classic → Serverless migrations are handled by a separate accelerator.

**Syren Server to Serverless Migration Platform** — [https://syren-s2s-platform-204242957656703.3.azure.databricksapps.com/#home](https://syren-s2s-platform-204242957656703.3.azure.databricksapps.com/#home)
