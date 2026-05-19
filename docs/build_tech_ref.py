"""
Generate SyrenBridge Technical Reference PDF.
Run: python docs/build_tech_ref.py
Output: docs/SyrenBridge_Technical_Reference.pdf
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import NextPageTemplate
import os

# ── Colours ──────────────────────────────────────────────────────────────────
C_ORANGE  = colors.HexColor("#FF3621")
C_BG      = colors.HexColor("#09090e")
C_DARK    = colors.HexColor("#0f172a")
C_MID     = colors.HexColor("#1e293b")
C_BORDER  = colors.HexColor("#334155")
C_TEXT    = colors.HexColor("#1e293b")
C_MUTED   = colors.HexColor("#64748b")
C_WHITE   = colors.white
C_INDIGO  = colors.HexColor("#6366f1")
C_CYAN    = colors.HexColor("#0891b2")
C_GREEN   = colors.HexColor("#059669")
C_AMBER   = colors.HexColor("#d97706")

OUT_PATH = os.path.join(os.path.dirname(__file__), "SyrenBridge_Technical_Reference.pdf")
LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "lb_migration_platform_ui", "logo.png")

W, H = A4

# ── Styles ────────────────────────────────────────────────────────────────────
def make_styles():
    s = getSampleStyleSheet()

    def add(name, **kw):
        s.add(ParagraphStyle(name=name, **kw))

    add("CoverTitle",   fontName="Helvetica-Bold",   fontSize=32, textColor=C_WHITE,   leading=40,  spaceAfter=12, alignment=TA_CENTER)
    add("CoverSub",     fontName="Helvetica",         fontSize=14, textColor=colors.HexColor("#94a3b8"), leading=20, spaceAfter=6,  alignment=TA_CENTER)
    add("CoverMeta",    fontName="Helvetica",         fontSize=10, textColor=colors.HexColor("#64748b"), leading=14, alignment=TA_CENTER)
    add("H1",           fontName="Helvetica-Bold",   fontSize=20, textColor=C_ORANGE,  leading=26,  spaceBefore=18, spaceAfter=8)
    add("H2",           fontName="Helvetica-Bold",   fontSize=14, textColor=C_DARK,    leading=20,  spaceBefore=14, spaceAfter=6)
    add("H3",           fontName="Helvetica-Bold",   fontSize=11, textColor=C_INDIGO,  leading=16,  spaceBefore=10, spaceAfter=4)
    add("SBBody",         fontName="Helvetica",         fontSize=10, textColor=C_TEXT,    leading=15,  spaceAfter=6, alignment=TA_JUSTIFY)
    add("SBBullet",     fontName="Helvetica",         fontSize=10, textColor=C_TEXT,    leading=14,  spaceAfter=4, leftIndent=16, firstLineIndent=-10)
    add("SBCode",         fontName="Courier",           fontSize=8.5, textColor=colors.HexColor("#1e40af"), leading=13, spaceAfter=2, leftIndent=12)
    add("SBCaption",      fontName="Helvetica-Oblique", fontSize=8.5, textColor=C_MUTED,  leading=12,  spaceAfter=6, alignment=TA_CENTER)
    add("SBBadge",        fontName="Helvetica-Bold",   fontSize=8,   textColor=C_WHITE,  leading=11,  alignment=TA_CENTER)
    add("SBTOCEntry1",    fontName="Helvetica-Bold",   fontSize=11,  textColor=C_DARK,   leading=18,  leftIndent=0)
    add("SBTOCEntry2",    fontName="Helvetica",         fontSize=9.5, textColor=C_MUTED,  leading=15,  leftIndent=18)
    add("SBSectionLabel", fontName="Helvetica-Bold",   fontSize=8,   textColor=C_WHITE,  leading=11,  alignment=TA_CENTER)
    add("SBDialectName",  fontName="Helvetica-Bold",   fontSize=16,  textColor=C_DARK,   leading=22,  spaceBefore=6, spaceAfter=4)
    add("SBDialectSub",   fontName="Helvetica",         fontSize=10,  textColor=C_MUTED,  leading=14,  spaceAfter=8)
    add("SBTableHeader",  fontName="Helvetica-Bold",   fontSize=9,   textColor=C_WHITE,  leading=13,  alignment=TA_CENTER)
    add("SBTableCell",    fontName="Helvetica",         fontSize=9,   textColor=C_TEXT,   leading=13)
    add("SBTableCellMono",fontName="Courier",           fontSize=8.5, textColor=colors.HexColor("#1e40af"), leading=13)
    add("SBFooterText",   fontName="Helvetica",         fontSize=8,   textColor=C_MUTED,  leading=11,  alignment=TA_CENTER)

    return s

# ── Page templates ─────────────────────────────────────────────────────────
def header_footer(canvas, doc):
    canvas.saveState()
    if doc.page > 1:
        # Header bar
        canvas.setFillColor(C_BG)
        canvas.rect(0, H - 1.1*cm, W, 1.1*cm, fill=1, stroke=0)
        canvas.setFillColor(C_ORANGE)
        canvas.rect(0, H - 1.1*cm, 4*cm, 1.1*cm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(C_WHITE)
        canvas.drawCentredString(2*cm, H - 0.7*cm, "SYRENBRIDGE")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(4.5*cm, H - 0.72*cm, "Technical Reference — All Dialects")

        # Footer
        canvas.setFillColor(colors.HexColor("#f1f5f9"))
        canvas.rect(0, 0, W, 0.9*cm, fill=1, stroke=0)
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.4)
        canvas.line(0, 0.9*cm, W, 0.9*cm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(1.5*cm, 0.32*cm, "SyrenBridge — Powered by Databricks Labs Lakebridge")
        canvas.drawRightString(W - 1.5*cm, 0.32*cm, f"Page {doc.page}")
    canvas.restoreState()


def cover_page(canvas, doc):
    canvas.saveState()
    # Full dark background
    canvas.setFillColor(C_BG)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    # Orange top bar
    canvas.setFillColor(C_ORANGE)
    canvas.rect(0, H - 3*cm, W, 3*cm, fill=1, stroke=0)
    # Bottom bar
    canvas.setFillColor(C_MID)
    canvas.rect(0, 0, W, 2.2*cm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawCentredString(W/2, 0.8*cm, "CONFIDENTIAL — Internal & Customer Reference  |  SyrenBridge by Syren Cloud  |  2026")
    canvas.restoreState()


# ── Data ──────────────────────────────────────────────────────────────────────

ANALYZER_TECHS = [
    (0,  "ABInitio",                       "ETL",  ["mp","mf","ab","xml","sh","ksh"],
     "Metadata-driven ETL workloads built on Ab Initio GDE/Co>Op. Assessment covers graph layouts, component types, and partitioning strategies."),
    (1,  "ADF",                            "ETL",  ["json","xml"],
     "Azure Data Factory pipelines in ARM/JSON format. Assessment covers activity types, linked services, triggers, and parameter passing."),
    (2,  "Alteryx",                        "ETL",  ["yxmd","yxwz","yxmc","yxapp"],
     "Alteryx Designer workflows (.yxmd/.yxwz). Assessment maps tool types (Join, Formula, Summarize) to Spark/Python equivalents."),
    (3,  "Athena",                         "SQL",  ["sql","ddl","dml"],
     "AWS Athena SQL (Presto-based). Assessment flags ANSI gaps, partition projections, and S3 references that need remapping to Delta Lake."),
    (4,  "BigQuery",                       "SQL",  ["sql","ddl","dml","json"],
     "Google BigQuery SQL. Assessment flags ARRAY/STRUCT types, UNNEST patterns, and BigQuery-specific functions needing Spark equivalents."),
    (5,  "BODS",                           "ETL",  ["atl","xml","bods"],
     "SAP BusinessObjects Data Services. Assessment covers dataflows, transforms, and lookup objects in ATL/XML format."),
    (6,  "Cloudera (Impala)",              "SQL",  ["sql","ddl","dml"],
     "Impala SQL on Cloudera CDH/CDP. Assessment identifies Kudu-specific syntax, COMPUTE STATS calls, and HDFS-rooted data paths."),
    (7,  "Datastage",                      "ETL",  ["dsx","xml","pjb"],
     "IBM DataStage jobs exported as .dsx or .pjb. Assessment covers stage types (Transformer, Join, Aggregator) and runtime parameters."),
    (8,  "Greenplum",                      "SQL",  ["sql","ddl","dml"],
     "Greenplum PostgreSQL-based SQL. Assessment flags distribution keys, append-optimised tables, and external table definitions."),
    (9,  "Hive",                           "SQL",  ["hql","hive","sql","ddl","dml"],
     "HiveQL from Cloudera/Hortonworks. Assessment identifies STORED AS clauses, SerDe configurations, partitioned inserts, and dynamic partition settings."),
    (10, "IBM DB2",                        "SQL",  ["sql","ddl","dml"],
     "IBM DB2 LUW / z/OS SQL. Assessment covers REXX-style syntax, DB2-specific date arithmetic, and catalog object references."),
    (11, "Informatica - Big Data Edition", "ETL",  ["xml","session","wf","m","mplt","lkp"],
     "Informatica BDE (native Hadoop) mappings. Assessment covers pushdown optimisation settings, HDFS sources, and Spark-native equivalents."),
    (12, "Informatica - PC",               "ETL",  ["xml","session","wf","m","mplt","lkp","pc"],
     "Informatica PowerCenter mappings, sessions, and workflows. Assessment maps source/target definitions, transformations, and session parameters."),
    (13, "Informatica Cloud",              "ETL",  ["xml","json","session"],
     "Informatica IICS/CDI taskflows. Assessment covers connection references, mapping tasks, schedule triggers, and cloud connector types."),
    (14, "Jupyter Notebook",              "Code", ["ipynb"],
     "Jupyter notebooks (.ipynb). Assessment identifies Spark/pandas API patterns, magic commands, and cells with side-effects needing review."),
    (15, "MS SQL Server",                  "SQL",  ["sql","ddl","dml","proc","view"],
     "T-SQL: stored procedures, views, functions, DDL. Assessment flags T-SQL-specific constructs: MERGE, TOP N, NOLOCK hints, CONVERT, GETDATE, cursors."),
    (16, "Netezza",                        "SQL",  ["sql","ddl","dml","nzb"],
     "IBM Netezza SQL including SPU-specific syntax. Assessment covers GROOM TABLE, distribution keys, zone maps, and Netezza UDFs."),
    (17, "Oozie",                          "ETL",  ["xml","properties","sh","ksh"],
     "Apache Oozie workflow.xml and coordinator.xml files. Assessment maps actions (Hive, Pig, Shell, Java, Spark) and coordinator scheduling."),
    (18, "Oracle",                         "SQL",  ["sql","ddl","dml","pls","pks","pkb","prc","fnc","vw","trg"],
     "Oracle SQL and PL/SQL: packages, procedures, functions, triggers. Assessment flags Oracle-specific syntax: CONNECT BY, ROWNUM, NVL, dbms_* packages."),
    (19, "Oracle Data Integrator",         "ETL",  ["xml","odixml","sql"],
     "ODI interfaces and knowledge modules in XML export format. Assessment covers IKM/LKM types, staging areas, and CDC configurations."),
    (20, "PentahoDI",                      "ETL",  ["ktr","kjb","xml"],
     "Pentaho Kettle (.ktr transformations, .kjb jobs). Assessment covers step types, hop conditions, and job entry parameters."),
    (21, "PIG",                            "Code", ["pig","txt"],
     "Apache Pig Latin scripts (.pig). Assessment maps LOAD/STORE paths, relation aliases, UDFs, and GROUP/JOIN operations to Spark."),
    (22, "Presto",                         "SQL",  ["sql","ddl","dml"],
     "Presto/Trino SQL. Assessment flags connector-specific syntax, Lambda functions, and WITH ORDINALITY clauses."),
    (23, "PySpark",                        "Code", ["py","ipynb","scala","java"],
     "Spark Classic (PySpark, Scala Spark, Java Spark). Assessment identifies APIs deprecated in Spark 3.x/4.x and patterns incompatible with Serverless."),
    (24, "Redshift",                       "SQL",  ["sql","ddl","dml"],
     "Amazon Redshift SQL. Assessment flags DISTKEY/SORTKEY DDL, UNLOAD/COPY commands, and Redshift-specific window functions."),
    (25, "SAPHANA - CalcViews",            "SQL",  ["xml","hdbcalcview","hdbprocedure","hdbview","analyticview","attributeview"],
     "SAP HANA Calculation Views and procedures in .hdbcalcview/.xml format. Assessment covers join types, filter nodes, and aggregation behaviour."),
    (26, "SAS",                            "Code", ["sas","sas7bdat"],
     "SAS Base and SAS Macro language. Assessment flags DATA step patterns, PROC SQL usage, macro variables, and SAS library references."),
    (27, "Snowflake",                      "SQL",  ["sql","ddl","dml"],
     "Snowflake SQL. Assessment flags VARIANT/ARRAY/OBJECT types, FLATTEN, Snowflake JavaScript UDFs, and warehouse-size references."),
    (28, "SPSS",                           "Code", ["sps","spv"],
     "IBM SPSS Modeler streams (.sps syntax files). Assessment covers statistical procedure calls and data file references."),
    (29, "SQOOP",                          "ETL",  ["xml","sh","ksh","properties"],
     "Apache Sqoop import/export jobs in shell scripts or XML configs. Assessment maps JDBC connection params and split-by column patterns."),
    (30, "SSIS",                           "ETL",  ["dtsx","xml"],
     "SQL Server Integration Services packages (.dtsx). Assessment covers Data Flow Tasks, Execute SQL Tasks, and Control Flow complexity."),
    (31, "SSRS",                           "ETL",  ["rdl","rdlc","rsd"],
     "SQL Server Reporting Services reports (.rdl). Assessment classifies datasets (Text vs StoredProcedure), flags VB.NET code blocks, and rates auto-convertibility."),
    (32, "Synapse",                        "SQL",  ["sql","ddl","dml","json"],
     "Azure Synapse Analytics SQL pools. Assessment flags Synapse-specific DDL (DISTRIBUTION, PARTITION), PolyBase EXTERNAL TABLE definitions, and linked service references."),
    (33, "Talend",                         "ETL",  ["item","properties","xml","java"],
     "Talend Open Studio jobs in .item/.properties format. Assessment covers component types (tMap, tJDBCInput, tFileInput) and Java subjobs."),
    (34, "Teradata",                       "SQL",  ["sql","bteq","tdl","tpt","ddl","dml"],
     "Teradata SQL and BTEQ scripts. Assessment flags Teradata-specific syntax: QUALIFY, NORMALIZE, COMPRESS, SET vs MULTISET tables, and volatile tables."),
    (35, "Vertica",                        "SQL",  ["sql","ddl","dml"],
     "Vertica SQL including PROJECTIONS, SEGMENTED BY, and Vertica-specific UDFs. Assessment covers projection DDL and Vertica analytic functions."),
]

TRANSPILER_DIALECTS = [
    {
        "name": "DataStage",
        "engine": "Lakebridge CLI (BladeBridge)",
        "engine_color": C_CYAN,
        "exts": ["dsx","xml","pjb"],
        "targets": ["PySpark","SparkSQL"],
        "category": "ETL",
        "description": "Converts IBM DataStage parallel jobs and server jobs exported in DSX or PJB format to Databricks-compatible PySpark notebooks or SparkSQL.",
        "what_converts": [
            "Transformer stage → withColumn() / select() expressions",
            "Join stage → df.join() with configurable join type",
            "Aggregator stage → df.groupBy().agg()",
            "Sequential File / DB2 source → spark.read.jdbc() / spark.read.csv()",
            "DB2 / Oracle destination → df.write.saveAsTable() / jdbc()",
            "Shared containers → extracted as reusable PySpark functions",
            "Job sequences and sequencer stages → Databricks Workflow tasks",
        ],
        "what_is_manual": [
            "Custom C/C++ transforms — rewrite as PySpark UDFs",
            "Before/After SQL subroutines — migrate as separate notebook cells",
            "DataStage parameters → map to Databricks job parameters or widgets",
        ],
        "output_note": "Output is a PySpark or SparkSQL notebook per DataStage job, plus a migration summary report.",
    },
    {
        "name": "HiveSQL (Cloudera)",
        "engine": "Built-in engine (sqlglot)",
        "engine_color": C_AMBER,
        "exts": ["hql","hive","sql","ddl","dml"],
        "targets": ["PySpark","SparkSQL"],
        "category": "SQL",
        "description": "Custom in-process transpiler using sqlglot (read='hive', write='databricks'). Post-processes output to strip Hive-only DDL clauses and optionally refines complex statements via an LLM endpoint.",
        "what_converts": [
            "SELECT / INSERT / CREATE TABLE / CTAS statements",
            "Hive UDFs referenced by name — preserved with migration comment",
            "Partition predicates and dynamic partition inserts",
            "LATERAL VIEW EXPLODE → Spark LATERAL VIEW equivalent",
            "Subqueries and CTEs",
            "Hive date functions → Spark SQL equivalents via sqlglot",
        ],
        "what_is_manual": [
            "STORED AS / ROW FORMAT / SERDE / TBLPROPERTIES / LOCATION hdfs:// — stripped with comment",
            "Custom Hive UDFs — must be registered as Spark UDFs manually",
            "Hive authorization (GRANT/REVOKE on table level) — migrate to Unity Catalog grants",
        ],
        "output_note": "Output is Databricks SQL dialect (runs on SQL Warehouses). LLM-assisted fix applied per statement when LLM endpoint is configured.",
    },
    {
        "name": "Informatica",
        "engine": "Lakebridge CLI (BladeBridge)",
        "engine_color": C_CYAN,
        "exts": ["xml","session","wf","m","mplt","lkp"],
        "targets": ["PySpark","SparkSQL"],
        "category": "ETL",
        "description": "Converts Informatica PowerCenter mappings, sessions, and workflows (XML export) to PySpark notebooks. Covers source/target definitions, transformations, and session-level parameters.",
        "what_converts": [
            "Source Qualifier → spark.read.jdbc() with pushdown SQL",
            "Expression / Filter / Router transformations → PySpark column ops",
            "Aggregator → groupBy().agg()",
            "Joiner → df.join()",
            "Lookup → broadcast join or lookup DataFrame",
            "Sorter → df.orderBy()",
            "Normalizer → explode() on repeated fields",
            "Update Strategy → merge/insert logic on Delta table",
        ],
        "what_is_manual": [
            "Custom Java Transformations — rewrite as PySpark UDFs",
            "Mapping parameters/variables — map to Databricks job parameters",
            "Workflow scheduling — migrate to Databricks Jobs scheduler",
        ],
        "output_note": "One PySpark notebook per mapping. Workflow-level orchestration mapped to a Databricks Workflow JSON.",
    },
    {
        "name": "Informatica Cloud",
        "engine": "Lakebridge CLI (BladeBridge)",
        "engine_color": C_CYAN,
        "exts": ["xml","json","session"],
        "targets": ["PySpark","SparkSQL"],
        "category": "ETL",
        "description": "Converts Informatica IICS (Intelligent Cloud Services) / CDI (Cloud Data Integration) taskflow exports to PySpark.",
        "what_converts": [
            "Mapping tasks → PySpark notebooks",
            "Connection references (Salesforce, S3, JDBC) → Databricks connection configs",
            "Parameterised schedules → Databricks Jobs triggers",
        ],
        "what_is_manual": [
            "IICS-specific connectors without Databricks equivalent — manual integration",
            "Data Quality rules embedded in tasks — review for Databricks DQ equivalent",
        ],
        "output_note": "PySpark notebooks with connection parameter stubs for engineer completion.",
    },
    {
        "name": "MS SQL Server",
        "engine": "Lakebridge CLI (BladeBridge)",
        "engine_color": C_CYAN,
        "exts": ["sql","ddl","dml","proc","view"],
        "targets": ["PySpark","SparkSQL"],
        "category": "SQL",
        "description": "Converts T-SQL objects — stored procedures, views, DDL scripts, DML — to Spark SQL or PySpark. Handles the most common T-SQL constructs including MERGE, TOP N, NOLOCK, and date functions.",
        "what_converts": [
            "SELECT / INSERT / UPDATE / DELETE → Spark SQL / Delta merge",
            "CREATE TABLE / CREATE VIEW → Databricks DDL",
            "MERGE → Delta Lake MERGE INTO",
            "TOP N → LIMIT N",
            "GETDATE() / GETUTCDATE() → current_timestamp()",
            "ISNULL(a,b) → ifnull(a,b)",
            "CONVERT(type, val) → CAST(val AS type)",
            "Stored procedures → PySpark functions or SQL notebooks",
            "Common Table Expressions (WITH ...) → preserved",
            "Window functions (ROW_NUMBER, RANK, LEAD/LAG) → preserved",
        ],
        "what_is_manual": [
            "Cursors — rewrite as set-based Spark operations",
            "Dynamic SQL (EXEC sp_executesql) — requires manual analysis",
            "NOLOCK hints → removed (Delta Lake handles MVCC)",
            "Linked server references — must be remapped to Databricks external connections",
            "CLR stored procedures — rewrite as Python UDFs",
        ],
        "output_note": "One SQL notebook or PySpark file per source script. Warnings generated for each pattern requiring manual review.",
    },
    {
        "name": "Netezza",
        "engine": "Lakebridge CLI (BladeBridge)",
        "engine_color": C_CYAN,
        "exts": ["sql","ddl","dml","nzb"],
        "targets": ["PySpark","SparkSQL"],
        "category": "SQL",
        "description": "Converts IBM Netezza (now IBM Db2 Warehouse) SQL to Spark SQL. Handles Netezza's MPP-specific DDL including distribution and zone map syntax.",
        "what_converts": [
            "SELECT / INSERT / CREATE TABLE → standard Spark SQL",
            "DISTRIBUTE ON → stripped (Delta Lake manages layout)",
            "ORGANIZE ON → converted to ZORDER BY hint comment",
            "Netezza string / date functions → Spark equivalents",
            "NZPLSQL procedures → PySpark functions",
            "External tables (NZB format references) → flagged with migration notes",
        ],
        "what_is_manual": [
            "NZB backup files — extract SQL DDL via Netezza tooling first",
            "GROOM TABLE — no direct equivalent; use OPTIMIZE on Delta tables",
            "Netezza UDFs (C-based) — rewrite as Python UDFs",
        ],
        "output_note": "SparkSQL notebooks with distribution clauses removed and ZORDER hints added as comments.",
    },
    {
        "name": "Oracle",
        "engine": "Lakebridge CLI (BladeBridge)",
        "engine_color": C_CYAN,
        "exts": ["sql","ddl","dml","pls","pks","pkb","prc","fnc","vw","trg"],
        "targets": ["PySpark","SparkSQL"],
        "category": "SQL",
        "description": "Converts Oracle SQL and PL/SQL — packages, procedures, functions, triggers — to Spark SQL or PySpark. One of the most comprehensive conversion paths in Lakebridge.",
        "what_converts": [
            "SELECT / INSERT / MERGE / CREATE TABLE / CREATE VIEW",
            "CONNECT BY hierarchical queries → WITH RECURSIVE CTE",
            "ROWNUM → ROW_NUMBER() OVER () or LIMIT",
            "NVL(a,b) → ifnull(a,b), NVL2 → CASE WHEN",
            "DECODE → CASE WHEN",
            "SYSDATE → current_date(), SYSTIMESTAMP → current_timestamp()",
            "TO_DATE / TO_CHAR → date_format() / to_date()",
            "Sequences (NEXTVAL/CURRVAL) → Databricks IDENTITY columns",
            "ROWID references → flagged for removal",
            "PL/SQL anonymous blocks → PySpark cells",
            "Package specs/bodies → Python modules",
        ],
        "what_is_manual": [
            "DBMS_* packages — replace with Python/Databricks API equivalents",
            "UTL_FILE, UTL_HTTP — rewrite using Python file/HTTP libs",
            "Triggers — no direct Delta equivalent; consider CDC or DLT",
            "Global Temporary Tables → Spark temp views or session caches",
            "Oracle spatial (SDO_*) — map to Databricks Mosaic or PostGIS",
        ],
        "output_note": "High-confidence auto-conversion for standard SQL. PL/SQL bodies emitted as PySpark with manual flags for complex constructs.",
    },
    {
        "name": "Snowflake",
        "engine": "Lakebridge CLI (BladeBridge)",
        "engine_color": C_CYAN,
        "exts": ["sql","ddl","dml"],
        "targets": ["PySpark","SparkSQL"],
        "category": "SQL",
        "description": "Converts Snowflake SQL to Spark SQL. Modern SQL dialects are close; key differences are Snowflake semi-structured types and JavaScript UDFs.",
        "what_converts": [
            "Standard SELECT / DDL / DML → Spark SQL",
            "FLATTEN / LATERAL FLATTEN → LATERAL VIEW EXPLODE",
            "PARSE_JSON / TO_VARIANT → from_json() / to_json()",
            "ARRAY_AGG → collect_list()",
            "OBJECT_CONSTRUCT → named_struct() or map()",
            "Snowflake date/time functions → Spark equivalents",
            "QUALIFY clause → wrapped in outer SELECT with WHERE on window alias",
            "Streams and Tasks references → flagged for Databricks DLT / Jobs",
        ],
        "what_is_manual": [
            "JavaScript UDFs — rewrite as Python UDFs",
            "Snowflake Streams / Tasks — migrate to DLT pipelines or Databricks Jobs",
            "External stages (S3/Azure/GCS references) — remap to Unity Catalog volumes",
            "Snowpark Python code — review for PySpark compatibility",
        ],
        "output_note": "SparkSQL output with semi-structured type conversions annotated for engineer review.",
    },
    {
        "name": "SSIS",
        "engine": "Lakebridge CLI — BladeBridge (SparkSQL only)",
        "engine_color": C_CYAN,
        "exts": ["dtsx","xml"],
        "targets": ["SparkSQL"],
        "category": "ETL",
        "description": "Converts SQL Server Integration Services packages (.dtsx) to SparkSQL via Databricks Labs BladeBridge. Output format is fixed to SparkSQL.",
        "what_converts": [
            "OLE DB Source (SQL query) → spark.sql() read cell",
            "OLE DB Destination → df.write.saveAsTable()",
            "Derived Column → df.withColumn() with column expressions",
            "Conditional Split → df.filter() into separate DataFrames",
            "Execute SQL Task (MERGE) → Delta Lake MERGE INTO",
            "Lookup → broadcast join",
            "Aggregate transform → groupBy().agg()",
            "Sort → df.orderBy()",
            "Precedence constraints → Databricks Workflow task dependencies",
        ],
        "what_is_manual": [
            "Script Tasks / Script Components (C# or VB.NET) — rewrite as PySpark UDFs",
            "Custom third-party SSIS components — no automatic mapping",
            "Complex @[User::Variable] expressions — may need manual adjustment",
            "FTP / SMTP / WMI tasks — no Spark equivalent; use Python libraries",
            "Event handlers — not converted; implement as Databricks Jobs notifications",
        ],
        "output_note": "SparkSQL notebook(s) per DTSX package. BladeBridge limitation: only SparkSQL target is supported for SSIS; PySpark output is not available.",
    },
    {
        "name": "SSRS (Reports)",
        "engine": "Built-in engine (ssrs_converter) — no CLI required",
        "engine_color": C_AMBER,
        "exts": ["rdl","rdlc","rsd"],
        "targets": ["SQL Notebooks + Assessment JSON"],
        "category": "Reporting",
        "description": "Custom SSRS-to-Databricks converter built into SyrenBridge. Parses RDL XML with lxml, classifies each report's convertibility, generates a SQL notebook per auto-convertible report, and produces a structured assessment JSON for every report.",
        "what_converts": [
            "Text-query datasets → one SQL cell per dataset in a .sql notebook",
            "Parameters → -- DECLARE comments (replace with dbutils.widgets)",
            "TableDirect datasets → SELECT * FROM <table>",
            "T-SQL function flags: GETDATE→current_timestamp, ISNULL→ifnull, TOP N→LIMIT N, DATEADD, DATEDIFF, CONVERT, NOLOCK",
            "Assessment JSON: data sources, datasets, report items (Tablix/Chart/Matrix), parameters, VB.NET code",
        ],
        "what_is_manual": [
            "StoredProcedure datasets — migrate the proc logic, then add SELECT query",
            "VB.NET code blocks — rewrite as Python UDFs or SQL CASE expressions",
            "Report layout, formatting, charts — use Databricks Dashboards (Lakeview) or a BI tool",
            "Parameters → replace -- DECLARE stubs with dbutils.widgets.get() calls",
            "Cross-report drillthrough links — no automated equivalent",
        ],
        "output_note": "One .sql notebook + one _assessment.json per RDL file. Non-auto-convertible reports produce assessment JSON only (no notebook).",
    },
    {
        "name": "Synapse",
        "engine": "Lakebridge CLI (BladeBridge)",
        "engine_color": C_CYAN,
        "exts": ["sql","ddl","dml","json"],
        "targets": ["PySpark","SparkSQL"],
        "category": "SQL",
        "description": "Converts Azure Synapse Analytics dedicated SQL pool scripts to Spark SQL. Handles Synapse MPP DDL and PolyBase external table patterns.",
        "what_converts": [
            "CREATE TABLE with DISTRIBUTION and PARTITION → Databricks DDL with USING DELTA",
            "DISTRIBUTION = HASH(col) → noted in COMMENT (Delta handles layout)",
            "PolyBase EXTERNAL TABLE / CREATE EXTERNAL DATA SOURCE → Unity Catalog external table stub",
            "Standard SELECT / INSERT / MERGE → Spark SQL",
            "Synapse-specific functions → Spark equivalents",
            "Synapse Pipelines JSON (ARM) → Databricks Workflow tasks",
        ],
        "what_is_manual": [
            "Serverless SQL pool queries over Azure Data Lake → remap to Unity Catalog volumes",
            "PolyBase credential objects — replace with Databricks secret scopes",
            "STATISTICS / RESULT_SET_CACHING — no direct equivalent",
            "Workload management (WORKLOAD GROUP) — use Databricks cluster policies",
        ],
        "output_note": "DDL clauses specific to Synapse MPP (DISTRIBUTION, STATISTICS) are stripped with comments; output runs directly on Databricks SQL Warehouse.",
    },
    {
        "name": "Teradata",
        "engine": "Lakebridge CLI (BladeBridge)",
        "engine_color": C_CYAN,
        "exts": ["sql","bteq","tdl","tpt","ddl","dml"],
        "targets": ["PySpark","SparkSQL"],
        "category": "SQL",
        "description": "Converts Teradata SQL, BTEQ scripts, and TPT (Teradata Parallel Transporter) files. One of the most common enterprise DW-to-Databricks migrations.",
        "what_converts": [
            "SELECT / INSERT / CREATE TABLE (SET/MULTISET) → Spark SQL",
            "QUALIFY → ROW_NUMBER() OVER () in outer SELECT",
            "NORMALIZE → Spark window function equivalent",
            "COMPRESS (column compression) → stripped (Delta handles encoding)",
            "VOLATILE TABLE → Spark temp view or CREATE TEMP TABLE",
            "PRIMARY INDEX → noted in COMMENT (Delta auto-manages layout)",
            "BTEQ control flow (.IF / .GOTO / .QUIT) → Python conditional notebook cells",
            "TPT APPLY ... OPERATOR patterns → PySpark bulk load equivalent",
            "Teradata date arithmetic (DATE + 1) → date_add()",
            "OREPLACE → regexp_replace()",
            "ZEROIFNULL / NULLIFZERO → ifnull(col,0) / nullif(col,0)",
        ],
        "what_is_manual": [
            "Teradata stored procedures (SPL) — rewrite as PySpark functions",
            "Macro objects → PySpark functions with parameter injection",
            "COLLECT STATISTICS — no equivalent; use ANALYZE TABLE on Delta",
            "Multi-statement requests (MSR) — split into individual cells",
            "FastLoad / MultiLoad scripts → Databricks batch ingest patterns",
        ],
        "output_note": "BTEQ scripts are split into SQL cells; control flow converted to Python. High conversion coverage for standard DW SQL patterns.",
    },
    {
        "name": "Oozie (Workflow)",
        "engine": "Built-in engine (oozie_converter) — no CLI required",
        "engine_color": C_AMBER,
        "exts": ["xml"],
        "targets": ["Databricks Workflow JSON"],
        "category": "ETL",
        "description": "Custom Oozie-to-Databricks converter built into SyrenBridge. Parses workflow.xml and coordinator.xml files with lxml and outputs Databricks Jobs API 2.1 JSON, ready for direct deployment via /api/2.1/jobs.",
        "what_converts": [
            "workflow.xml → Databricks Workflow (tasks with dependencies)",
            "coordinator.xml → Databricks scheduled Job (Quartz cron → Databricks cron)",
            "Hive action → notebook_task pointing to migrated HiveSQL notebook",
            "Spark action → spark_python_task or notebook_task",
            "Shell action → notebook_task with shell commands as %sh magic",
            "Java action → spark_jar_task stub",
            "Pig action → notebook_task (Pig Latin converted separately)",
            "Fork/Join → parallel tasks with dependency tracking (fan-in DAG)",
            "Coordinator→workflow linking → run_job_task with sentinel {{job_id:<name>}}",
            "Decision nodes (switch/case) → Databricks conditional task dependencies",
        ],
        "what_is_manual": [
            "EL expressions (${...}) — preserved verbatim, engineer resolves to Databricks job params",
            "Datasets and SLA blocks — not converted; document in migration notes",
            "Coordinator end-time — captured in coordinator_info JSON field only",
            "Sub-workflow actions → inline tasks or separate workflow job",
            "Custom action types not in the standard set",
        ],
        "output_note": "Output is deployable Databricks Workflow JSON. Coordinator→workflow links use a sentinel that the UI auto-replaces with the real job_id after the workflow job is created.",
    },
]

# ── Doc class with TOC ───────────────────────────────────────────────────────

class TocDocTemplate(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        self.toc = TableOfContents()
        self.toc.levelStyles = [
            ParagraphStyle("SBtoc1", fontName="Helvetica-Bold", fontSize=11, textColor=C_DARK,
                           leading=18, leftIndent=0, spaceAfter=2),
            ParagraphStyle("SBtoc2", fontName="Helvetica", fontSize=9.5, textColor=C_MUTED,
                           leading=14, leftIndent=18, spaceAfter=1),
        ]

    def afterFlowable(self, flowable):
        if hasattr(flowable, "toc_entry"):
            level, text, key = flowable.toc_entry
            self.notify("TOCEntry", (level, text, self.page, key))


class TocEntry(Paragraph):
    def __init__(self, text, style, level=0, key=None):
        k = key or text
        anchor = f'<a name="{k}"/>' if k else ''
        super().__init__(anchor + text, style)
        self.toc_entry = (level, text.replace("<b>","").replace("</b>",""), k)


# ── Helpers ───────────────────────────────────────────────────────────────────

def colour_cell(text, bg, fg=None, style_name="SBBadge"):
    s = make_styles()
    p = Paragraph(f"<font color='{'white' if fg is None else fg.hexval()}'>{text}</font>", s[style_name])
    return p


def ext_table(exts):
    s = make_styles()
    cells = []
    for e in exts:
        cells.append(Paragraph(f"<font color='white'>.{e}</font>", s["SBBadge"]))
    col_w = 1.6*cm
    n = len(cells)
    rows = [cells[i:i+6] for i in range(0, n, 6)]
    if rows[-1] and len(rows[-1]) < 6:
        rows[-1] += [""] * (6 - len(rows[-1]))
    t = Table(rows, colWidths=[col_w]*6)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_INDIGO),
        ("ROWBACKGROUNDS", (0,0),(-1,-1),[C_INDIGO, colors.HexColor("#4f46e5")]),
        ("ROUNDEDCORNERS", [4]),
        ("FONTSIZE", (0,0),(-1,-1), 8),
        ("ALIGN", (0,0),(-1,-1), "CENTER"),
        ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING", (0,0),(-1,-1), 4),
        ("RIGHTPADDING", (0,0),(-1,-1), 4),
        ("GRID", (0,0),(-1,-1), 0.3, C_BORDER),
    ]))
    return t


def info_row(label, value, s, label_style="H3", value_style="Body"):
    return Table(
        [[Paragraph(label, s[label_style]), Paragraph(value, s[value_style])]],
        colWidths=[4*cm, 13.2*cm],
        style=TableStyle([
            ("VALIGN", (0,0),(-1,-1), "TOP"),
            ("LEFTPADDING", (0,0),(-1,-1), 0),
            ("RIGHTPADDING", (0,0),(-1,-1), 0),
            ("TOPPADDING", (0,0),(-1,-1), 2),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
        ])
    )


def bullet_table(items, s, icon="▸"):
    rows = [[Paragraph(f"{icon}", s["SBBody"]), Paragraph(item, s["SBBody"])] for item in items]
    t = Table(rows, colWidths=[0.5*cm, 16.7*cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING", (0,0),(-1,-1), 2),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING", (0,0),(-1,-1), 1),
        ("BOTTOMPADDING", (0,0),(-1,-1), 2),
    ]))
    return t


# ── Build ─────────────────────────────────────────────────────────────────────

def build():
    s = make_styles()

    doc = TocDocTemplate(
        OUT_PATH,
        pagesize=A4,
        leftMargin=1.6*cm, rightMargin=1.6*cm,
        topMargin=1.8*cm, bottomMargin=1.8*cm,
        title="SyrenBridge Technical Reference",
        author="Syren Cloud",
        subject="All Dialects — Analyzer & Transpiler",
    )

    content_frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        W - doc.leftMargin - doc.rightMargin,
        H - doc.topMargin - doc.bottomMargin,
        id="content"
    )
    cover_frame = Frame(
        1.8*cm, 3*cm,
        W - 3.6*cm,
        H - 6*cm,
        id="cover"
    )

    doc.addPageTemplates([
        PageTemplate(id="Cover",  frames=[cover_frame], onPage=cover_page),
        PageTemplate(id="Normal", frames=[content_frame], onPage=header_footer),
    ])

    story = []

    # ── Cover ─────────────────────────────────────────────────────────────────
    story.append(NextPageTemplate("Cover"))
    story.append(Spacer(1, 1.5*cm))

    if os.path.exists(LOGO_PATH):
        from reportlab.platypus import Image as RLImage
        logo = RLImage(LOGO_PATH, width=2.8*cm, height=2.8*cm)
        story.append(logo)
        story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("SyrenBridge", s["CoverTitle"]))
    story.append(Paragraph("Technical Reference — All Dialects", s["CoverSub"]))
    story.append(Spacer(1, 0.6*cm))
    story.append(HRFlowable(width="60%", thickness=1.5, color=C_ORANGE, spaceAfter=16, spaceBefore=8))
    story.append(Paragraph(
        "Analyzer · Transpiler · Architecture · Conversion Coverage",
        s["CoverSub"]
    ))
    story.append(Spacer(1, 1.2*cm))

    cover_stats = Table(
        [[
            Paragraph("<b>36</b><br/>Analyzer Sources", s["CoverSub"]),
            Paragraph("<b>13</b><br/>Transpiler Dialects", s["CoverSub"]),
            Paragraph("<b>100%</b><br/>No-install Deployment", s["CoverSub"]),
        ]],
        colWidths=[5.5*cm, 5.5*cm, 5.5*cm],
        style=TableStyle([
            ("ALIGN", (0,0),(-1,-1), "CENTER"),
            ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
            ("FONTNAME", (0,0),(-1,-1), "Helvetica"),
            ("TEXTCOLOR", (0,0),(-1,-1), colors.HexColor("#94a3b8")),
            ("LINEAFTER", (0,0),(1,-1), 0.5, colors.HexColor("#334155")),
            ("TOPPADDING", (0,0),(-1,-1), 8),
            ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ])
    )
    story.append(cover_stats)
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("Syren Cloud  ·  Powered by Databricks Labs Lakebridge  ·  2026", s["CoverMeta"]))

    # ── Switch to Normal template ─────────────────────────────────────────────
    story.append(NextPageTemplate("Normal"))
    story.append(PageBreak())

    # ── TOC ───────────────────────────────────────────────────────────────────
    story.append(Paragraph("<b>Table of Contents</b>", s["H1"]))
    story.append(Spacer(1, 0.3*cm))
    story.append(doc.toc)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PART 1 — PLATFORM OVERVIEW
    # ══════════════════════════════════════════════════════════════════════════
    story.append(TocEntry("<b>1. Platform Overview</b>", s["H1"], level=0, key="overview"))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ORANGE, spaceAfter=10))

    story.append(Paragraph(
        "SyrenBridge is a Streamlit application deployed on Databricks Apps. It wraps "
        "Databricks Labs Lakebridge and extends it with three custom-built migration engines "
        "for HiveSQL, Oozie workflows, and SSRS reports. The platform provides a unified UI "
        "for analyzing legacy data platform complexity and transpiling source artifacts to "
        "Databricks-native formats.",
        s["SBBody"]
    ))
    story.append(Spacer(1, 0.3*cm))

    overview_table = Table(
        [
            [Paragraph("<b>Component</b>", s["SBTableHeader"]),
             Paragraph("<b>Role</b>", s["SBTableHeader"]),
             Paragraph("<b>Coverage</b>", s["SBTableHeader"])],
            [Paragraph("Analyzer Tab", s["SBTableCell"]),
             Paragraph("Complexity assessment, effort estimation, migration readiness scoring", s["SBTableCell"]),
             Paragraph("36 source technologies", s["SBTableCell"])],
            [Paragraph("Transpiler Tab", s["SBTableCell"]),
             Paragraph("Automated code conversion to PySpark, SparkSQL, or Databricks Workflow JSON", s["SBTableCell"]),
             Paragraph("13 dialects", s["SBTableCell"])],
            [Paragraph("Lakebridge CLI", s["SBTableCell"]),
             Paragraph("Backs 10 transpiler dialects via BladeBridge", s["SBTableCell"]),
             Paragraph("DataStage, Informatica, MSSQL, Netezza, Oracle, Snowflake, SSIS, Synapse, Teradata, Informatica Cloud", s["SBTableCell"])],
            [Paragraph("HiveSQL Engine", s["SBTableCell"]),
             Paragraph("In-process sqlglot conversion (Hive→Databricks SQL), LLM-assisted fix", s["SBTableCell"]),
             Paragraph(".hql, .hive, .sql, .ddl, .dml", s["SBTableCell"])],
            [Paragraph("Oozie Engine", s["SBTableCell"]),
             Paragraph("lxml-based workflow/coordinator parser → Databricks Jobs API 2.1 JSON", s["SBTableCell"]),
             Paragraph("workflow.xml, coordinator.xml", s["SBTableCell"])],
            [Paragraph("SSRS Engine", s["SBTableCell"]),
             Paragraph("lxml RDL parser → SQL notebooks + assessment JSON, auto-convertibility scoring", s["SBTableCell"]),
             Paragraph(".rdl, .rdlc, .rsd", s["SBTableCell"])],
        ],
        colWidths=[4*cm, 9*cm, 4.2*cm],
        style=TableStyle([
            ("BACKGROUND", (0,0),(-1,0), C_BG),
            ("TEXTCOLOR", (0,0),(-1,0), C_WHITE),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [colors.HexColor("#f8fafc"), C_WHITE]),
            ("GRID", (0,0),(-1,-1), 0.4, C_BORDER),
            ("FONTNAME", (0,0),(-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0),(-1,-1), 9),
            ("ALIGN", (0,0),(-1,0), "CENTER"),
            ("VALIGN", (0,0),(-1,-1), "TOP"),
            ("TOPPADDING", (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("LEFTPADDING", (0,0),(-1,-1), 8),
            ("RIGHTPADDING", (0,0),(-1,-1), 8),
        ])
    )
    story.append(overview_table)
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("<b>Execution path decision:</b>", s["H3"]))
    story.append(bullet_table([
        "dialect_info.get('oozie') → run_oozie_converter() (lxml engine, no CLI)",
        "dialect_info.get('ssrs')  → run_ssrs_converter() (ssrs_converter engine, no CLI)",
        "dialect_info.get('custom') → run_hive_transpiler() (sqlglot engine, no CLI)",
        "All other dialects          → run_transpiler() → lakebridge transpile CLI (BladeBridge)",
    ], s))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PART 2 — ANALYZER
    # ══════════════════════════════════════════════════════════════════════════
    story.append(TocEntry("<b>2. Analyzer — All 36 Source Technologies</b>", s["H1"], level=0, key="analyzer"))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ORANGE, spaceAfter=10))
    story.append(Paragraph(
        "The Analyzer tab invokes <i>lakebridge analyze</i> against uploaded or workspace-browsed files. "
        "It produces a complexity report per source: object counts, migration effort score, warnings, "
        "and a downloadable assessment ZIP. Files can be uploaded directly or browsed from a Databricks workspace.",
        s["SBBody"]
    ))
    story.append(Spacer(1, 0.3*cm))

    # Summary table of all 36
    cat_colors = {"SQL": C_CYAN, "ETL": C_AMBER, "Code": C_GREEN}
    rows = [[
        Paragraph("<b>#</b>", s["SBTableHeader"]),
        Paragraph("<b>Technology</b>", s["SBTableHeader"]),
        Paragraph("<b>Category</b>", s["SBTableHeader"]),
        Paragraph("<b>File Extensions</b>", s["SBTableHeader"]),
    ]]
    for idx, name, cat, exts, _ in ANALYZER_TECHS:
        ext_str = "  ".join(f".{e}" for e in exts)
        rows.append([
            Paragraph(str(idx+1), s["SBTableCell"]),
            Paragraph(f"<b>{name}</b>", s["SBTableCell"]),
            Paragraph(cat, s["SBTableCell"]),
            Paragraph(f"<font name='Courier' size='8'>{ext_str}</font>", s["SBTableCell"]),
        ])

    at = Table(rows, colWidths=[0.8*cm, 5.5*cm, 2*cm, 8.9*cm])
    at.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), C_BG),
        ("TEXTCOLOR", (0,0),(-1,0), C_WHITE),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [colors.HexColor("#f8fafc"), C_WHITE]),
        ("GRID", (0,0),(-1,-1), 0.3, C_BORDER),
        ("FONTSIZE", (0,0),(-1,-1), 8.5),
        ("ALIGN", (0,0),(0,-1), "CENTER"),
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("TOPPADDING", (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING", (0,0),(-1,-1), 6),
        ("RIGHTPADDING", (0,0),(-1,-1), 6),
    ]))
    story.append(at)
    story.append(PageBreak())

    # Detail per tech
    story.append(TocEntry("<b>2.1 Analyzer — Per-Technology Detail</b>", s["H2"], level=1, key="analyzer_detail"))
    story.append(Spacer(1, 0.2*cm))

    for idx, name, cat, exts, desc in ANALYZER_TECHS:
        anchor_key = f"az_{idx}"
        bg = cat_colors.get(cat, C_MUTED)

        block = []
        block.append(TocEntry(f"{idx+1}. {name}", s["H2"], level=1, key=anchor_key))

        badge_cat = Table(
            [[Paragraph(f"<font color='white'><b>{cat}</b></font>", s["SBBadge"])]],
            colWidths=[1.6*cm],
            style=TableStyle([
                ("BACKGROUND", (0,0),(-1,-1), bg),
                ("ROUNDEDCORNERS", [4]),
                ("TOPPADDING", (0,0),(-1,-1), 3),
                ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ])
        )
        ext_str = "  ".join(f".{e}" for e in exts)
        info_t = Table(
            [[badge_cat, Paragraph(f"<font name='Courier' size='9'>{ext_str}</font>", s["SBBody"])]],
            colWidths=[2*cm, 15.2*cm],
            style=TableStyle([
                ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
                ("LEFTPADDING", (0,0),(-1,-1), 0),
                ("RIGHTPADDING", (0,0),(-1,-1), 0),
            ])
        )
        block.append(info_t)
        block.append(Spacer(1, 0.15*cm))
        block.append(Paragraph(desc, s["SBBody"]))
        block.append(HRFlowable(width="100%", thickness=0.3, color=C_BORDER, spaceAfter=8, spaceBefore=6))

        story.append(KeepTogether(block))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PART 3 — TRANSPILER
    # ══════════════════════════════════════════════════════════════════════════
    story.append(TocEntry("<b>3. Transpiler — All 13 Dialects</b>", s["H1"], level=0, key="transpiler"))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ORANGE, spaceAfter=10))
    story.append(Paragraph(
        "The Transpiler tab converts source artifacts to Databricks-native code. "
        "Each dialect has a dedicated engine (Lakebridge CLI or built-in), fixed or selectable output format, "
        "and a clearly defined conversion scope. The sections below provide per-dialect detail.",
        s["SBBody"]
    ))
    story.append(Spacer(1, 0.3*cm))

    # Summary table
    rows = [[
        Paragraph("<b>Dialect</b>", s["SBTableHeader"]),
        Paragraph("<b>Engine</b>", s["SBTableHeader"]),
        Paragraph("<b>Output</b>", s["SBTableHeader"]),
        Paragraph("<b>Extensions</b>", s["SBTableHeader"]),
    ]]
    for d in TRANSPILER_DIALECTS:
        rows.append([
            Paragraph(f"<b>{d['name']}</b>", s["SBTableCell"]),
            Paragraph(d["engine"], s["SBTableCell"]),
            Paragraph(" / ".join(d["targets"]), s["SBTableCell"]),
            Paragraph(f"<font name='Courier' size='8'>" + "  ".join(f".{e}" for e in d["exts"]) + "</font>", s["SBTableCell"]),
        ])
    tt = Table(rows, colWidths=[4.2*cm, 5.8*cm, 3.5*cm, 3.7*cm])
    tt.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), C_BG),
        ("TEXTCOLOR", (0,0),(-1,0), C_WHITE),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [colors.HexColor("#f8fafc"), C_WHITE]),
        ("GRID", (0,0),(-1,-1), 0.3, C_BORDER),
        ("FONTSIZE", (0,0),(-1,-1), 8.5),
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("TOPPADDING", (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING", (0,0),(-1,-1), 6),
        ("RIGHTPADDING", (0,0),(-1,-1), 6),
    ]))
    story.append(tt)
    story.append(PageBreak())

    # Detail per dialect
    for i, d in enumerate(TRANSPILER_DIALECTS):
        anchor_key = f"tp_{d['name'].replace(' ','_')}"

        story.append(TocEntry(f"3.{i+1}  {d['name']}", s["H2"], level=1, key=anchor_key))

        # Engine + category badges
        engine_bg = d["engine_color"]
        cat_bg = {"SQL": C_CYAN, "ETL": C_AMBER, "Code": C_GREEN, "Reporting": C_INDIGO}.get(d["category"], C_MUTED)
        badge_row = Table(
            [[
                Paragraph(f"<font color='white'><b>{d['category']}</b></font>", s["SBBadge"]),
                Paragraph(f"<font color='white'>{d['engine']}</font>", s["SBBadge"]),
                Paragraph(f"<font color='white'>Output: {' / '.join(d['targets'])}</font>", s["SBBadge"]),
            ]],
            colWidths=[2*cm, 9.5*cm, 5.7*cm],
            style=TableStyle([
                ("BACKGROUND", (0,0),(0,0), cat_bg),
                ("BACKGROUND", (1,0),(1,0), engine_bg),
                ("BACKGROUND", (2,0),(2,0), C_DARK),
                ("TOPPADDING", (0,0),(-1,-1), 4),
                ("BOTTOMPADDING", (0,0),(-1,-1), 4),
                ("LEFTPADDING", (0,0),(-1,-1), 6),
                ("RIGHTPADDING", (0,0),(-1,-1), 6),
                ("GRID", (0,0),(-1,-1), 0.3, C_BORDER),
            ])
        )
        story.append(badge_row)
        story.append(Spacer(1, 0.25*cm))
        story.append(Paragraph(d["description"], s["SBBody"]))
        story.append(Spacer(1, 0.15*cm))

        # File extensions
        story.append(Paragraph("<b>Accepted file types:</b>", s["H3"]))
        story.append(Paragraph(
            f"<font name='Courier' size='9'>" + "   ".join(f".{e}" for e in d["exts"]) + "</font>",
            s["SBBody"]
        ))
        story.append(Spacer(1, 0.1*cm))

        # What converts
        story.append(Paragraph("<b>What is automatically converted:</b>", s["H3"]))
        story.append(bullet_table(d["what_converts"], s, icon="✓"))
        story.append(Spacer(1, 0.1*cm))

        # What is manual
        story.append(Paragraph("<b>What requires manual migration:</b>", s["H3"]))
        story.append(bullet_table(d["what_is_manual"], s, icon="△"))
        story.append(Spacer(1, 0.1*cm))

        # Output note
        story.append(Paragraph("<b>Output:</b>", s["H3"]))
        story.append(Paragraph(d["output_note"], s["SBBody"]))

        story.append(HRFlowable(width="100%", thickness=0.4, color=C_BORDER, spaceAfter=10, spaceBefore=10))
        if i < len(TRANSPILER_DIALECTS) - 1 and i % 2 == 1:
            story.append(PageBreak())

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PART 4 — ARCHITECTURE
    # ══════════════════════════════════════════════════════════════════════════
    story.append(TocEntry("<b>4. Architecture & Data Flow</b>", s["H1"], level=0, key="arch"))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ORANGE, spaceAfter=10))

    story.append(Paragraph("<b>4.1 Deployment</b>", s["H2"]))
    story.append(bullet_table([
        "SyrenBridge is a single Streamlit app deployed as a Databricks App (no additional infrastructure).",
        "Lakebridge CLI is installed in the app's Python environment — no separate server.",
        "Custom engines (HiveSQL, Oozie, SSRS) are pure Python modules — no external services.",
        "Credentials (Databricks host/token) are passed via environment variables or the Settings tab; used for workspace browsing and file upload.",
    ], s))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("<b>4.2 Module Boundaries</b>", s["H2"]))
    story.append(bullet_table([
        "modules/ — pure Python, no Streamlit imports. Independently testable with pytest.",
        "app.py — all Streamlit rendering; imports from modules/ only.",
        "PySpark (sql_validator.py, dummy_data.py) — only used in test/validation path, never in the Streamlit render path.",
    ], s))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("<b>4.3 File Flow</b>", s["H2"]))
    arch_rows = [
        ["Step", "Action", "Location"],
        ["1", "User uploads files or browses Databricks workspace", "app.py — Upload Files / Databricks Workspace tabs"],
        ["2", "Files written to a temp directory on the app server", "tempfile.mkdtemp()"],
        ["3", "Engine invoked with src_dir and out_dir", "run_transpiler / run_hive_transpiler / run_oozie_converter / run_ssrs_converter"],
        ["4", "Engine writes output files to out_dir", "Lakebridge CLI writes notebooks; custom engines write .sql/.json/.workflow_json"],
        ["5", "UI reads out_dir and presents file tree, metrics, download ZIP", "app.py — results section"],
        ["6", "(Optional) Upload ZIP to Databricks workspace", "DatabricksClient.upload_directory_to_workspace()"],
    ]
    arch_t = Table(
        [[Paragraph(f"<b>{c}</b>", s["SBTableHeader"]) if r == arch_rows[0] else Paragraph(c, s["SBTableCell"]) for c in r]
         for r in arch_rows],
        colWidths=[0.8*cm, 7*cm, 9.4*cm],
        style=TableStyle([
            ("BACKGROUND", (0,0),(-1,0), C_BG),
            ("TEXTCOLOR", (0,0),(-1,0), C_WHITE),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [colors.HexColor("#f8fafc"), C_WHITE]),
            ("GRID", (0,0),(-1,-1), 0.3, C_BORDER),
            ("FONTSIZE", (0,0),(-1,-1), 8.5),
            ("VALIGN", (0,0),(-1,-1), "TOP"),
            ("TOPPADDING", (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING", (0,0),(-1,-1), 6),
            ("RIGHTPADDING", (0,0),(-1,-1), 6),
        ])
    )
    story.append(arch_t)
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("<b>4.4 HiveSQL Pipeline Detail</b>", s["H2"]))
    story.append(bullet_table([
        "Pre-processing: clean whitespace, detect encoding issues",
        "Split into statements (line-aware splitter)",
        "sqlglot.transpile(sql, read='hive', write='databricks') per statement",
        "Post-processing rules: strip STORED AS, ROW FORMAT, SERDE, TBLPROPERTIES, LOCATION hdfs://",
        "Issue tagging: flag statements with warnings",
        "Optional LLM fix: per-statement HTTP call to configured LLM endpoint for complex patterns",
        "Final output: concatenated Databricks SQL file",
    ], s))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("<b>4.5 Oozie Converter Detail</b>", s["H2"]))
    story.append(bullet_table([
        "Parse workflow.xml and coordinator.xml with lxml.etree",
        "Workflow → Databricks Job with tasks (one per Oozie action)",
        "Fan-in DAG: predecessors tracked as Dict[str, List[str]] (supports multiple upstream edges)",
        "Cluster rule: job_clusters (shared) only for 2+ task jobs; single-task → new_cluster inline",
        "Coordinator → run_job_task with sentinel {{job_id:<wf_name>}} after workflow linking",
        "Coordinator→workflow matching: basename exact, then normalised (-↔_, lowercase)",
        "_strip_annotation_keys() removes _-prefixed migration metadata from workflow jobs",
    ], s))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("<b>4.6 SSRS Converter Detail</b>", s["H2"]))
    story.append(bullet_table([
        "Parse .rdl XML with lxml.etree; auto-detect RDL namespace",
        "Extract: DataSources, ReportParameters, Code (VB.NET), DataSets (CommandType + SQL), ReportItems",
        "Classify: Text → convertible; StoredProcedure → manual; TableDirect → SELECT * FROM <table>",
        "Flag T-SQL patterns: GETDATE, ISNULL, TOP N, DATEADD, DATEDIFF, CONVERT, NOLOCK",
        "auto_convertible = True if at least one Text dataset exists",
        "Generate .sql notebook (one cell per dataset) + _assessment.json (full structural inventory)",
    ], s))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PART 5 — QUICK REFERENCE
    # ══════════════════════════════════════════════════════════════════════════
    story.append(TocEntry("<b>5. Quick Reference</b>", s["H1"], level=0, key="quickref"))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ORANGE, spaceAfter=10))

    story.append(Paragraph("<b>Transpiler Engine Decision Table</b>", s["H2"]))
    dec_rows = [
        ["Dialect flag in TRANSPILER_DIALECTS", "Engine called", "Output format"],
        ["oozie: True", "run_oozie_converter()", "Databricks Workflow JSON"],
        ["ssrs: True", "run_ssrs_converter()", "SQL notebooks + assessment JSON"],
        ["custom: True (HiveSQL)", "run_hive_transpiler()", "Databricks SQL (SparkSQL or PySpark)"],
        ["sparksql_only: True (SSIS)", "run_transpiler() → lakebridge CLI", "SparkSQL only"],
        ["(none of the above)", "run_transpiler() → lakebridge CLI", "PySpark or SparkSQL (user selects)"],
    ]
    dec_t = Table(
        [[Paragraph(f"<b>{c}</b>", s["SBTableHeader"]) if r == dec_rows[0]
          else Paragraph(f"<font name='Courier' size='8.5'>{c}</font>" if j == 0 else c, s["SBTableCell"])
          for j, c in enumerate(r)] for r in dec_rows],
        colWidths=[6*cm, 5.5*cm, 5.7*cm],
        style=TableStyle([
            ("BACKGROUND", (0,0),(-1,0), C_BG),
            ("TEXTCOLOR", (0,0),(-1,0), C_WHITE),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [colors.HexColor("#f8fafc"), C_WHITE]),
            ("GRID", (0,0),(-1,-1), 0.3, C_BORDER),
            ("FONTSIZE", (0,0),(-1,-1), 9),
            ("VALIGN", (0,0),(-1,-1), "TOP"),
            ("TOPPADDING", (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING", (0,0),(-1,-1), 6),
            ("RIGHTPADDING", (0,0),(-1,-1), 6),
        ])
    )
    story.append(dec_t)
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("<b>T-SQL → Spark SQL Quick Mapping</b>", s["H2"]))
    tsql_rows = [
        ["T-SQL", "Spark SQL"],
        ["GETDATE() / GETUTCDATE()", "current_timestamp()"],
        ["ISNULL(a, b) / NVL(a, b)", "ifnull(a, b)"],
        ["TOP N", "LIMIT N"],
        ["DATEADD(day, n, col)", "date_add(col, n)"],
        ["DATEDIFF(day, a, b)", "datediff(b, a)"],
        ["CONVERT(VARCHAR, col)", "CAST(col AS STRING)"],
        ["WITH (NOLOCK)", "— removed (Delta MVCC)"],
        ["MERGE ... WHEN MATCHED", "Delta Lake MERGE INTO"],
        ["SELECT INTO #temp", "CREATE TEMP VIEW / CACHE TABLE"],
        ["ROWNUM", "ROW_NUMBER() OVER (ORDER BY ...)"],
    ]
    tsql_t = Table(
        [[Paragraph(f"<b>{c}</b>", s["SBTableHeader"]) if r == tsql_rows[0]
          else Paragraph(f"<font name='Courier' size='8.5'>{c}</font>", s["SBTableCell"])
          for c in r] for r in tsql_rows],
        colWidths=[8.5*cm, 8.7*cm],
        style=TableStyle([
            ("BACKGROUND", (0,0),(-1,0), C_BG),
            ("TEXTCOLOR", (0,0),(-1,0), C_WHITE),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [colors.HexColor("#f8fafc"), C_WHITE]),
            ("GRID", (0,0),(-1,-1), 0.3, C_BORDER),
            ("FONTSIZE", (0,0),(-1,-1), 9),
            ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING", (0,0),(-1,-1), 8),
            ("RIGHTPADDING", (0,0),(-1,-1), 8),
        ])
    )
    story.append(tsql_t)

    doc.multiBuild(story)
    print(f"PDF written → {OUT_PATH}")


if __name__ == "__main__":
    build()
