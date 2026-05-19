# SSIS & SSRS Migration — SyrenBridge Technical Reference

> Audience: Databricks Solution Architects and customer technical teams evaluating or implementing SyrenBridge.

---

## Overview

SyrenBridge handles SSIS and SSRS through two distinct engines, each following a different migration strategy driven by the nature of the source artifact:

| Source | Engine | Output | Auto-convert? |
|--------|--------|--------|---------------|
| SSIS (`.dtsx`, `.xml`) | Databricks Labs Lakebridge — BladeBridge | SparkSQL notebooks | Yes, for standard data flows |
| SSRS (`.rdl`, `.rdlc`, `.rsd`) | Built-in `ssrs_converter` (custom) | SQL notebooks + Assessment JSON | Yes, for Text-query datasets |

Both engines are surfaced in the same two tabs — **Analyzer** and **Transpiler** — and share the same file-upload / Databricks-workspace-browse input flow.

---

## SSIS

### What SSIS packages contain

SSIS (`.dtsx`) packages define ETL pipelines: one or more **Data Flow Tasks** (extract, transform, load) and **Control Flow Tasks** (Execute SQL, FTP, Script, etc.), connected by precedence constraints. The package embeds connection managers pointing to source and destination systems.

### How SyrenBridge processes SSIS

**Analyzer tab**  
SSIS is registered as source technology #30 in the Lakebridge analyzer catalog. When a `.dtsx` or `.xml` file is submitted, the Analyzer tab calls:

```
lakebridge analyze --source-tech SSIS --input-dir <src> --output-dir <out>
```

Lakebridge inspects the package XML and produces a migration complexity report: how many tasks, which transformations are used, estimated migration effort. The report lands in the output directory and is available for download as a ZIP.

**Transpiler tab**  
SSIS is registered in `TRANSPILER_DIALECTS` with `sparksql_only: True`:

```python
"SSIS": {"cli": "ssis", "exts": ["dtsx", "xml"], "sparksql_only": True}
```

The `sparksql_only` flag has two effects in the UI:
1. The target format selector is hidden — there is no choice. Output is always SparkSQL.
2. A fixed info banner reads: *"Output: SparkSQL — SSIS packages convert to SparkSQL only (BladeBridge limitation)"*

When the user clicks **Run Transpiler**, the standard `run_transpiler()` function is called:

```python
run_transpiler(
    src_dir=tp_src_dir,
    out_dir=tp_out_dir,
    dialect="ssis",
    target="SPARKSQL",
    ...
)
```

This shells out to:

```
lakebridge transpile --source-dialect ssis --target SPARKSQL \
    --input-dir <src> --output-dir <out>
```

Lakebridge / BladeBridge parses the DTSX XML, maps each pipeline component to a Spark equivalent, and writes `.sql` or `.py` notebooks to the output directory.

### What gets converted

| SSIS component | Spark equivalent |
|----------------|-----------------|
| OLE DB Source (SQL query) | `spark.sql(...)` read |
| OLE DB Destination | `df.write.saveAsTable(...)` |
| Derived Column | `df.withColumn(...)` with column expression |
| Conditional Split | `df.filter(...)` into separate DataFrames |
| Execute SQL Task | `spark.sql(...)` cell |
| Lookup | `df.join(...)` |
| Aggregate | `df.groupBy(...).agg(...)` |

### What is not auto-converted

- **Script Tasks / Script Components** (C# or VB.NET code) — flagged for manual rewrite as PySpark UDFs
- **Custom third-party components** — flagged, require manual mapping
- **SSIS variables and expressions** — complex `@[User::Var]` expressions may need manual adjustment
- **FTP / SMTP / WMI tasks** — no Spark equivalent; flagged as manual

### Output files

```
output/
  <package_name>.sql        # SparkSQL notebook(s)
  <package_name>_report.md  # Lakebridge conversion summary
```

---

## SSRS

### What SSRS reports contain

SSRS (`.rdl`) reports are XML files that define:
- **Data Sources** — connection strings to SQL Server databases
- **Datasets** — SQL queries (or stored procedure calls) that populate report data
- **Parameters** — values passed in at render time (dates, region filters, etc.)
- **Report Items** — Tablix tables, Charts, Matrix, Textboxes, Subreports
- **Custom Code** — VB.NET helper functions embedded in the `<Code>` element

### How SyrenBridge processes SSRS

**Analyzer tab**  
SSRS is registered as a source technology in the Lakebridge analyzer catalog. The Analyzer tab calls Lakebridge CLI for complexity assessment, same flow as all other source types.

**Transpiler tab**  
SSRS uses a **custom built-in engine** — `modules/ssrs_converter.py` — not the Lakebridge CLI. This is because Lakebridge does not include an SSRS transpiler; the conversion logic is implemented entirely within SyrenBridge.

SSRS is registered in `TRANSPILER_DIALECTS` with `ssrs: True`:

```python
"SSRS (Reports)": {"cli": "ssrs", "exts": ["rdl", "rdlc", "rsd"], "ssrs": True}
```

The `ssrs` flag causes the Transpiler tab to:
1. Skip the target format selector — output is always `SQL Notebooks + Assessment JSON`
2. Show a fixed info banner: *"Output: SQL Notebooks + Assessment JSON — one .sql notebook and one assessment.json per report"*
3. Call `run_ssrs_converter()` instead of `run_transpiler()`

### The ssrs_converter engine — step by step

Entry point: `convert_ssrs_file_set(files: Dict[str, str]) -> Dict`

**Step 1 — Parse RDL XML**  
Each `.rdl` file is parsed with `lxml.etree`. The parser handles any RDL namespace automatically (the namespace URI varies between SSRS versions). It extracts:
- Report name from `<Name>`
- Data sources from `<DataSource>` → `<ConnectionProperties>`
- Parameters from `<ReportParameter>`
- Custom VB.NET code from `<Code>`
- Datasets from `<DataSet>` → `<Query>` (command type, SQL text, query parameters)
- Report items by iterating for `<Tablix>`, `<Chart>`, `<Matrix>`, `<Textbox>`, `<Image>`, `<Subreport>`

**Step 2 — Classify datasets**  
Each dataset is classified by its `<CommandType>`:
- `Text` — a plain SQL query, convertible
- `StoredProcedure` — calls `dbo.usp_...`, flagged as manual migration required
- `TableDirect` — direct table access, converted to `SELECT * FROM <table>`

**Step 3 — Flag T-SQL patterns**  
For Text datasets, the SQL is scanned for T-SQL functions that have Spark SQL equivalents:

| T-SQL | Spark SQL |
|-------|-----------|
| `GETDATE()` / `GETUTCDATE()` | `current_timestamp()` |
| `ISNULL(a, b)` / `NVL(a, b)` | `ifnull(a, b)` |
| `TOP N` | `LIMIT N` |
| `DATEADD(...)` | `date_add(...)` |
| `DATEDIFF(...)` | `datediff(...)` |
| `CONVERT(...)` | `CAST(...)` |
| `WITH (NOLOCK)` | removed (hint not applicable) |

Matches are added as warnings in the assessment output. The SQL text in the generated notebook preserves the original query — the engineer applies these substitutions as part of review.

**Step 4 — Determine auto-convertibility**  
A report is `auto_convertible = True` if it has at least one `Text`-type dataset.  
A report is **not** auto-convertible if:
- All datasets use stored procedures
- No datasets exist at all
- The `<Code>` block contains VB.NET functions

Non-convertible reports still receive a full Assessment JSON but no SQL notebook.

**Step 5 — Generate SQL notebook**  
For auto-convertible reports, one `.sql` file is produced:

```sql
-- SSRS Report: SalesOrderReport
-- Migrated by SyrenBridge

-- Parameters (replace with Databricks widgets or job parameters):
-- DECLARE @ReportDate = :_ReportDate;
-- DECLARE @Region = :_Region;

-- ═══ Dataset: OrderSummary ═══
SELECT
  CAST(o.order_date AS DATE) AS order_day,
  ...
FROM dbo.fact_orders o
...

-- ═══ Dataset: TopOrders ═══
SELECT TOP 10
  ...
```

The file is structured so each dataset becomes a runnable SQL cell. Parameters appear as `-- DECLARE` comments — the engineer replaces them with `dbutils.widgets.get(...)` calls or Databricks job parameters.

**Step 6 — Generate Assessment JSON**  
Every report (convertible or not) receives an `_assessment.json`:

```json
{
  "report_name": "SalesOrderReport",
  "auto_convertible": true,
  "warnings": [
    "SalesOrderReport: T-SQL pattern detected — \\bTOP\\s+(\\d+)\\b"
  ],
  "data_sources": [
    {"name": "RetailDW", "connection_string": "Data Source=sql-dw-prod;...", "type": "SQL"}
  ],
  "datasets": [
    {"name": "OrderSummary", "query_language": "Text", "query": "SELECT ...", "parameters": ["@ReportDate","@Region"]},
    {"name": "TopOrders",    "query_language": "Text", "query": "SELECT TOP 10 ...", "parameters": ["@ReportDate"]}
  ],
  "report_items": [
    {"type": "Tablix", "name": "RegionSummaryTable", "dataset": "OrderSummary"},
    {"type": "Chart",  "name": "RevenueByRegionChart", "dataset": "OrderSummary"},
    {"type": "Tablix", "name": "TopOrdersTable", "dataset": "TopOrders"}
  ],
  "parameters": ["ReportDate", "Region"],
  "vb_code_blocks": []
}
```

This JSON is the primary artefact for reports that are not auto-convertible — a migration engineer uses it to understand the report's structure and plan manual migration.

### Output files per report

| Report | auto_convertible | Output files |
|--------|-----------------|-------------|
| `SalesOrderReport.rdl` | true | `SalesOrderReport.sql` + `SalesOrderReport_assessment.json` |
| `InventoryStoredProc.rdl` | false | `InventoryStoredProc_assessment.json` only |

### Post-conversion steps for engineers

1. **Run the SQL notebook** on a Databricks SQL Warehouse. Resolve any T-SQL functions flagged in warnings.
2. **Replace parameters** — change `-- DECLARE @Param = :_Param;` to `dbutils.widgets.text("Param", "")` and reference with `dbutils.widgets.get("Param")`.
3. **Stored procedure datasets** — migrate the procedure logic to a Databricks SQL view or a Python function, then reference in the notebook.
4. **VB.NET custom code** — rewrite as Python UDFs (`@udf`) registered in the Spark session, or as SQL expressions if the logic is simple enough.
5. **Report layout** — SSRS visual formatting (fonts, page layout, charts) is not migrated. Use **Databricks Dashboards (Lakeview)** or a BI tool connected to the Databricks SQL Warehouse for the visual layer.

---

## Shared UI Flow (Both SSIS and SSRS)

### Input: two modes

**Upload Files** — the user drops one or more source files (or a ZIP) via the browser.  
**Databricks Workspace** — the user browses their Databricks workspace, selects files, and SyrenBridge fetches them via the Databricks REST API before conversion. After transpilation, results can be pushed back to a workspace folder using the *Upload All Output Files to Databricks* button.

### Execution flow

```
User selects dialect (SSIS or SSRS)
        │
        ▼
UI shows accepted extensions, engine badge, fixed output format
        │
        ▼
User uploads files / browses workspace
        │
        ▼
User clicks "Run Transpiler"
        │
        ├─ SSIS ──► run_transpiler(dialect="ssis", target="SPARKSQL")
        │                │
        │                └──► lakebridge transpile CLI (BladeBridge)
        │                          │
        │                          └──► SparkSQL notebooks written to output dir
        │
        └─ SSRS ──► run_ssrs_converter(src_dir, out_dir)
                         │
                         └──► convert_ssrs_file_set()
                                   │
                                   ├── parse_rdl() per file (lxml)
                                   ├── classify datasets (Text / SP / TableDirect)
                                   ├── flag T-SQL patterns
                                   ├── determine auto_convertible
                                   ├── assessment_to_sql_notebook() if convertible
                                   └── write .sql + _assessment.json to output dir
        │
        ▼
UI shows: N reports assessed · X/N auto-convertible · Y SQL notebooks generated
        │
        ▼
Download ZIP  —or—  Upload to Databricks workspace folder
```

### What the UI displays after conversion

**SSIS** — standard output log from Lakebridge, file tree of generated notebooks, download ZIP.

**SSRS** — summary banner (reports assessed / auto-convertible / notebooks generated), expandable *SSRS Conversion Notes* panel explaining what each output file contains, download ZIP, option to upload directly to a Databricks workspace folder.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SyrenBridge (Streamlit)                      │
│                                                                     │
│  ┌──────────────┐          ┌──────────────────────────────────────┐ │
│  │  Analyzer    │          │  Transpiler Tab                      │ │
│  │  Tab         │          │                                      │ │
│  │              │          │  dialect = SSIS                      │ │
│  │  lakebridge  │          │  ┌─────────────────────────────────┐ │ │
│  │  analyze     │          │  │ run_transpiler()                │ │ │
│  │  --source    │          │  │   lakebridge transpile          │ │ │
│  │  SSIS/SSRS   │          │  │   --source-dialect ssis         │ │ │
│  └──────────────┘          │  │   --target SPARKSQL             │ │ │
│                            │  │   (BladeBridge engine)          │ │ │
│  Lakebridge CLI            │  └────────────┬────────────────────┘ │ │
│  ─ complexity report       │               │ SparkSQL notebooks    │ │
│  ─ effort estimate         │               ▼                      │ │
│                            │  ┌─────────────────────────────────┐ │ │
│                            │  │  Output dir                     │ │ │
│                            │  │  .sql / .py notebooks           │ │ │
│                            │  └─────────────────────────────────┘ │ │
│                            │                                      │ │
│                            │  dialect = SSRS (Reports)            │ │
│                            │  ┌─────────────────────────────────┐ │ │
│                            │  │ run_ssrs_converter()            │ │ │
│                            │  │   modules/ssrs_converter.py     │ │ │
│                            │  │   ─ lxml XML parse              │ │ │
│                            │  │   ─ classify datasets           │ │ │
│                            │  │   ─ flag T-SQL patterns         │ │ │
│                            │  │   ─ generate .sql notebook      │ │ │
│                            │  │   ─ generate _assessment.json   │ │ │
│                            │  └────────────┬────────────────────┘ │ │
│                            │               │                      │ │
│                            │               ▼                      │ │
│                            │  ┌─────────────────────────────────┐ │ │
│                            │  │  Output dir                     │ │ │
│                            │  │  <report>.sql                   │ │ │
│                            │  │  <report>_assessment.json       │ │ │
│                            │  └─────────────────────────────────┘ │ │
│                            └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   Download ZIP                Upload to Databricks
                                Workspace via REST API
```

---

## Key Design Decisions

**Why BladeBridge for SSIS and not a custom engine?**  
SSIS packages contain complex DAG control flow, dozens of component types, and C#/VB.NET scripting. Lakebridge BladeBridge already covers the common component set well. SyrenBridge wraps it with a `sparksql_only` constraint because BladeBridge's SSIS support targets SparkSQL specifically.

**Why a custom engine for SSRS and not BladeBridge?**  
Lakebridge does not include an SSRS transpiler. The SSRS format is well-structured XML with a predictable schema; the primary migration value is extracting the SQL queries that feed report data. A purpose-built parser (`lxml` + dataclasses) gives full control over classification, T-SQL flagging, and the assessment output format — without adding a CLI dependency that doesn't exist.

**Why produce an Assessment JSON for every report?**  
Even non-auto-convertible reports (stored procs, VB code) need a migration plan. The assessment JSON gives the engineer a complete structural inventory — data sources, datasets, parameters, report items, custom code — without having to read the raw XML. It also feeds into broader migration tracking spreadsheets or project management tools.

**Why is output format locked for both SSIS and SSRS?**  
SSIS → SparkSQL is a BladeBridge limitation (the CLI does not expose other targets for SSIS).  
SSRS → SQL Notebooks + JSON is the only meaningful output: SSRS reports are about queries and layout, not a target dialect. Offering a "target language" selector would be misleading.

---

## Sample Files

Two sample files are included in the repository under `files/` for testing:

| File | Type | Notes |
|------|------|-------|
| `files/sample_ssis/RetailETL.dtsx` | SSIS package | OLE DB Source → Derived Column → Conditional Split → OLE DB Destination, plus Execute SQL MERGE task. Standard auto-convertible package. |
| `files/sample_ssrs/SalesOrderReport.rdl` | SSRS report | 2 Text-query datasets, 2 parameters, 1 Tablix, 1 Chart. Auto-convertible. |
| `files/sample_ssrs/InventoryStoredProc.rdl` | SSRS report | 1 StoredProcedure dataset + VB.NET custom code. Not auto-convertible — assessment JSON produced, no SQL notebook. |

---

## Testing

SSRS converter unit tests live in `tests/test_ssrs_converter.py` (28 tests). Run with:

```bash
cd Lb-Migration-Platform
pytest tests/test_ssrs_converter.py -v
```

SSIS conversion is tested end-to-end via the Lakebridge CLI — unit tests for that path rely on the CLI being installed in the environment.
