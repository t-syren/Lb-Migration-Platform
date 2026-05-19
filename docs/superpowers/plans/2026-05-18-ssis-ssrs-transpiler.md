# SSIS + SSRS Transpiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SSIS and SSRS as fully-supported dialects in the Transpiler tab, verify the Analyzer already works for both, and build a custom SSRS converter engine that produces an assessment JSON + SQL notebook from `.rdl` files.

**Architecture:** SSIS reuses the existing Lakebridge CLI path via BladeBridge (SparkSQL-only target); SSRS gets a new custom engine in `modules/ssrs_converter.py` that parses RDL XML with lxml, mirroring the existing Oozie engine pattern. Both are wired into `app.py` by adding entries to `TRANSPILER_DIALECTS` and handling their flags in the run + UI logic.

**Tech Stack:** Python 3.10, lxml, Streamlit, existing `run_transpiler()` / `run_oozie_converter()` patterns, pytest

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `lb_migration_platform_ui/app.py` | Add SSIS + SSRS to TRANSPILER_DIALECTS, handle `sparksql_only` + `ssrs` flags in UI and run logic, update badge count + Get Started table, import ssrs_converter |
| Create | `lb_migration_platform_ui/modules/ssrs_converter.py` | Custom SSRS→SQL+JSON converter engine |
| Create | `tests/test_ssrs_converter.py` | Unit tests for ssrs_converter |

---

### Task 1: SSIS in Transpiler (TRANSPILER_DIALECTS + target UI)

**Files:**
- Modify: `lb_migration_platform_ui/app.py:122-134` (TRANSPILER_DIALECTS)
- Modify: `lb_migration_platform_ui/app.py:2109-2173` (target selection UI)
- Modify: `lb_migration_platform_ui/app.py:2415-2457` (run logic)

- [ ] **Step 1: Add SSIS to TRANSPILER_DIALECTS**

In `app.py`, add SSIS after `"Snowflake"` in TRANSPILER_DIALECTS:

```python
TRANSPILER_DIALECTS: dict[str, dict] = {
    "DataStage":           {"cli": "datastage",         "exts": ["dsx", "xml", "pjb"]},
    "HiveSQL (Cloudera)":  {"cli": "hive",              "exts": ["hql", "hive", "sql", "ddl", "dml"], "custom": True},
    "Informatica":         {"cli": "informatica",        "exts": ["xml", "session", "wf", "m", "mplt", "lkp"]},
    "Informatica Cloud":   {"cli": "informatica_cloud",  "exts": ["xml", "json", "session"]},
    "MS SQL Server":       {"cli": "mssql",              "exts": ["sql", "ddl", "dml", "proc", "view"]},
    "Netezza":             {"cli": "netezza",            "exts": ["sql", "ddl", "dml", "nzb"]},
    "Oracle":              {"cli": "oracle",             "exts": ["sql", "ddl", "dml", "pls", "pks", "pkb", "prc", "fnc", "vw", "trg"]},
    "Snowflake":           {"cli": "snowflake",          "exts": ["sql", "ddl", "dml"]},
    "SSIS":                {"cli": "ssis",               "exts": ["dtsx", "xml"],             "sparksql_only": True},
    "Synapse":             {"cli": "synapse",            "exts": ["sql", "ddl", "dml", "json"]},
    "Teradata":            {"cli": "teradata",           "exts": ["sql", "bteq", "tdl", "tpt", "ddl", "dml"]},
    "Oozie (Workflow)":    {"cli": "oozie",              "exts": ["xml"],                               "oozie": True},
}
```

- [ ] **Step 2: Add `sparksql_only` engine badge**

In app.py around line 2114 where `_engine_badge` is set, add a branch for `sparksql_only` **before** the `else` branch:

```python
        if dialect_info.get("oozie"):
            _engine_badge = (
                '<span style="font-size:0.72rem;background:#fef3c7;color:#92400e;'
                'border:1px solid #fcd34d;border-radius:6px;padding:2px 7px;font-weight:600;">'
                '🔁 Built-in engine (oozie_converter) — outputs Databricks Workflow JSON</span>'
            )
        elif dialect_info.get("ssrs"):
            _engine_badge = (
                '<span style="font-size:0.72rem;background:#fef3c7;color:#92400e;'
                'border:1px solid #fcd34d;border-radius:6px;padding:2px 7px;font-weight:600;">'
                '📊 Built-in engine (ssrs_converter) — outputs SQL notebooks + assessment JSON</span>'
            )
        elif dialect_info.get("custom"):
            _engine_badge = (
                '<span style="font-size:0.72rem;background:#fef3c7;color:#92400e;'
                'border:1px solid #fcd34d;border-radius:6px;padding:2px 7px;font-weight:600;">'
                '⚙️ Built-in engine (sqlglot) — no Databricks CLI needed</span>'
            )
        elif dialect_info.get("sparksql_only"):
            _engine_badge = (
                '<span style="font-size:0.72rem;background:#e0f2fe;color:#0369a1;'
                'border:1px solid #7dd3fc;border-radius:6px;padding:2px 7px;font-weight:600;">'
                '⚡ BladeBridge — SparkSQL output only</span>'
            )
        else:
            _engine_badge = ""
```

- [ ] **Step 3: Add `sparksql_only` target selection branch**

In app.py, find the target selection block (around line 2139). It currently has `if dialect_info.get("oozie"):` / `elif dialect_info.get("custom"):` / `else:`. Add a new `elif` for `sparksql_only` before the final `else`:

```python
        if dialect_info.get("oozie"):
            target_cli = "OOZIE_WORKFLOW"
            selected_target_label = "Databricks Workflow JSON"
            st.markdown(
                '<div style="background:#ecfdf5;border:1px solid #6ee7b7;border-radius:8px;'
                'padding:0.6rem 1rem;font-size:0.82rem;color:#065f46;font-weight:500;">'
                '📋 Output: <strong>Databricks Workflow JSON</strong> — deployable via '
                '<code>/api/2.1/jobs ,please use button below - Create Databricks Workflow</code></div>',
                unsafe_allow_html=True,
            )
        elif dialect_info.get("ssrs"):
            target_cli = "SSRS_NOTEBOOKS"
            selected_target_label = "SQL Notebooks + Assessment JSON"
            st.markdown(
                '<div style="background:#ecfdf5;border:1px solid #6ee7b7;border-radius:8px;'
                'padding:0.6rem 1rem;font-size:0.82rem;color:#065f46;font-weight:500;">'
                '📊 Output: <strong>SQL Notebooks + Assessment JSON</strong> — '
                'one .sql notebook and one assessment.json per report</div>',
                unsafe_allow_html=True,
            )
        elif dialect_info.get("sparksql_only"):
            target_cli = "SPARKSQL"
            selected_target_label = "SparkSQL  (SQL-compatible Spark)"
            st.markdown(
                '<div style="background:#ecfdf5;border:1px solid #6ee7b7;border-radius:8px;'
                'padding:0.6rem 1rem;font-size:0.82rem;color:#065f46;font-weight:500;">'
                '⚡ Output: <strong>SparkSQL</strong> — SSIS packages convert to SparkSQL only '
                '(BladeBridge limitation)</div>',
                unsafe_allow_html=True,
            )
        elif dialect_info.get("custom"):
            ...
```

- [ ] **Step 4: Exclude `sparksql_only` and `ssrs` from the Advanced options expander**

Find the line `if not dialect_info.get("oozie"):` (around line 2176) that gates the Advanced options expander. Extend the condition:

```python
        if not dialect_info.get("oozie") and not dialect_info.get("sparksql_only") and not dialect_info.get("ssrs"):
```

- [ ] **Step 5: Confirm the run logic falls through to `run_transpiler()` for SSIS**

SSIS has no custom flag beyond `sparksql_only`. In the run block (around line 2415), the existing `if dialect_info.get("oozie"):` / `elif dialect_info.get("custom"):` / `else:` chain already calls `run_transpiler()` in the `else` branch — SSIS will fall into that branch correctly since it has neither `oozie` nor `custom` nor `ssrs` flags. No code change needed here for SSIS itself.

Verify the `else` branch passes `dialect_cli` (which is `"ssis"`) and `target_cli` (which is `"SPARKSQL"`):

```python
                else:
                    tp_ok, tp_stdout, tp_stderr = run_transpiler(
                        src_dir=tp_src_dir,
                        out_dir=tp_out_dir,
                        err_file=tp_err_file,
                        dialect=dialect_cli,   # "ssis"
                        target=target_cli,      # "SPARKSQL"
                        catalog=st.session_state.get("tp_catalog", ""),
                        schema=st.session_state.get("tp_schema", ""),
                        skip_validation=st.session_state.get("tp_skip_val", True),
                    )
```

This is already correct — no change needed.

- [ ] **Step 6: Commit**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
git add lb_migration_platform_ui/app.py
git commit -m "feat: add SSIS dialect to transpiler (BladeBridge SparkSQL-only)"
```

---

### Task 2: SSRS Converter Module

**Files:**
- Create: `lb_migration_platform_ui/modules/ssrs_converter.py`

The SSRS RDL format is XML. Namespaces vary by version but the content schema is consistent. We parse with lxml. The entry point mirrors Oozie: `convert_ssrs_file_set(files: Dict[str, str]) -> Dict`.

- [ ] **Step 1: Write the failing tests first** (see Task 3 — write tests, then come back here)

- [ ] **Step 2: Create `lb_migration_platform_ui/modules/ssrs_converter.py`**

```python
"""
SSRS (.rdl) to Databricks SQL Notebook + Assessment JSON converter.

Entry point: convert_ssrs_file_set(files: Dict[str, str]) -> Dict
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import Any

from lxml import etree


# RDL files may or may not declare a namespace. Common ones:
_RDL_NAMESPACES = [
    "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition",
    "http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition",
    "http://schemas.microsoft.com/sqlserver/reporting/2008/01/reportdefinition",
    "http://schemas.microsoft.com/sqlserver/reporting/2005/01/reportdefinition",
]

_TSQL_PATTERNS = [
    (r"\bGETDATE\s*\(\)", "current_timestamp()"),
    (r"\bGETUTCDATE\s*\(\)", "current_timestamp()"),
    (r"\bISNULL\s*\(", "ifnull("),
    (r"\bNVL\s*\(", "ifnull("),
    (r"\bNOLOCK\b", "-- [NOLOCK hint removed]"),
    (r"\bTOP\s+(\d+)\b", r"LIMIT \1"),
    (r"\bDATEADD\s*\(", "-- [DATEADD → date_add()] "),
    (r"\bDATEDIFF\s*\(", "-- [DATEDIFF → datediff()] "),
    (r"\bCONVERT\s*\(", "-- [CONVERT → CAST()] "),
]


@dataclass
class SsrsDataSource:
    name: str
    connection_string: str = ""
    data_source_type: str = ""


@dataclass
class SsrsDataset:
    name: str
    query_language: str = "Text"   # "Text" | "StoredProcedure" | "TableDirect"
    query: str = ""
    parameters: list[str] = field(default_factory=list)


@dataclass
class SsrsReportItem:
    item_type: str   # "Tablix" | "Chart" | "Matrix" | "Textbox" | "Image" | "Subreport"
    name: str
    dataset_name: str = ""


@dataclass
class SsrsAssessment:
    report_name: str
    auto_convertible: bool
    warnings: list[str] = field(default_factory=list)
    data_sources: list[SsrsDataSource] = field(default_factory=list)
    datasets: list[SsrsDataset] = field(default_factory=list)
    report_items: list[SsrsReportItem] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    vb_code_blocks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_name": self.report_name,
            "auto_convertible": self.auto_convertible,
            "warnings": self.warnings,
            "data_sources": [
                {"name": ds.name, "connection_string": ds.connection_string, "type": ds.data_source_type}
                for ds in self.data_sources
            ],
            "datasets": [
                {
                    "name": d.name,
                    "query_language": d.query_language,
                    "query": d.query,
                    "parameters": d.parameters,
                }
                for d in self.datasets
            ],
            "report_items": [
                {"type": ri.item_type, "name": ri.name, "dataset": ri.dataset_name}
                for ri in self.report_items
            ],
            "parameters": self.parameters,
            "vb_code_blocks": self.vb_code_blocks,
        }


def _find_ns(root: etree._Element) -> str:
    """Return the RDL namespace found in the root element, or empty string."""
    tag = root.tag
    if tag.startswith("{"):
        return tag[1: tag.index("}")]
    return ""


def _t(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}" if ns else local


def _text(el: etree._Element | None) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


def _flag_tsql_hints(sql: str) -> list[str]:
    """Return a list of T-SQL patterns detected in the query."""
    found = []
    for pattern, _ in _TSQL_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            found.append(pattern)
    return found


def parse_rdl(xml_str: str, filename: str = "report") -> SsrsAssessment:
    """Parse a single RDL XML string into an SsrsAssessment."""
    warnings: list[str] = []
    try:
        root = etree.fromstring(xml_str.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        return SsrsAssessment(
            report_name=filename,
            auto_convertible=False,
            warnings=[f"XML parse error: {exc}"],
        )

    ns = _find_ns(root)

    # Report name: prefer Name element, fall back to filename stem
    name_el = root.find(_t(ns, "Name"))
    report_name = _text(name_el) or filename

    # ── Data Sources ─────────────────────────────────────────────────────────
    data_sources: list[SsrsDataSource] = []
    for ds_el in root.iter(_t(ns, "DataSource")):
        ds_name = ds_el.get("Name", "")
        conn_el = ds_el.find(_t(ns, "ConnectionProperties"))
        cs = ""
        ds_type = ""
        if conn_el is not None:
            cs = _text(conn_el.find(_t(ns, "ConnectString")))
            ds_type = _text(conn_el.find(_t(ns, "DataProvider")))
        data_sources.append(SsrsDataSource(name=ds_name, connection_string=cs, data_source_type=ds_type))

    # ── Parameters ───────────────────────────────────────────────────────────
    param_names: list[str] = []
    for p_el in root.iter(_t(ns, "ReportParameter")):
        pname = p_el.get("Name", "")
        if pname:
            param_names.append(pname)

    # ── VB Code Blocks ────────────────────────────────────────────────────────
    vb_blocks: list[str] = []
    code_el = root.find(_t(ns, "Code"))
    if code_el is not None and code_el.text and code_el.text.strip():
        vb_blocks.append(code_el.text.strip())
        warnings.append("Custom VB.NET code block detected — manual migration required")

    # ── Datasets ─────────────────────────────────────────────────────────────
    datasets: list[SsrsDataset] = []
    for dset_el in root.iter(_t(ns, "DataSet")):
        dset_name = dset_el.get("Name", "")
        query_el = dset_el.find(_t(ns, "Query"))
        lang = "Text"
        sql = ""
        dset_params: list[str] = []
        if query_el is not None:
            lang_el = query_el.find(_t(ns, "CommandType"))
            lang = _text(lang_el) if lang_el is not None else "Text"
            cmd_el = query_el.find(_t(ns, "CommandText"))
            sql = _text(cmd_el)
            for qp in query_el.iter(_t(ns, "QueryParameter")):
                pn = qp.get("Name", "")
                if pn:
                    dset_params.append(pn)

        if lang == "StoredProcedure":
            warnings.append(
                f"Dataset '{dset_name}' uses a stored procedure ({sql!r}) — manual migration required"
            )
        elif lang == "TableDirect":
            warnings.append(
                f"Dataset '{dset_name}' uses TableDirect — convert to SELECT * FROM {sql!r}"
            )
        else:
            tsql_hits = _flag_tsql_hints(sql)
            for hit in tsql_hits:
                warnings.append(f"Dataset '{dset_name}': T-SQL pattern detected — {hit}")

        datasets.append(SsrsDataset(name=dset_name, query_language=lang, query=sql, parameters=dset_params))

    # ── Report Items ─────────────────────────────────────────────────────────
    report_items: list[SsrsReportItem] = []
    for item_type in ("Tablix", "Chart", "Matrix", "Textbox", "Image", "Subreport"):
        for el in root.iter(_t(ns, item_type)):
            ri_name = el.get("Name", "")
            ds_ref_el = el.find(_t(ns, "DataSetName"))
            if ds_ref_el is None:
                # Tablix stores the ref deeper
                for child in el.iter(_t(ns, "DataSetName")):
                    ds_ref_el = child
                    break
            ds_ref = _text(ds_ref_el)
            report_items.append(SsrsReportItem(item_type=item_type, name=ri_name, dataset_name=ds_ref))

    # ── Auto-convertible? ─────────────────────────────────────────────────────
    text_datasets = [d for d in datasets if d.query_language == "Text"]
    auto_convertible = len(text_datasets) > 0

    if not datasets:
        warnings.append("No datasets found — nothing to convert")
        auto_convertible = False

    return SsrsAssessment(
        report_name=report_name,
        auto_convertible=auto_convertible,
        warnings=warnings,
        data_sources=data_sources,
        datasets=datasets,
        report_items=report_items,
        parameters=param_names,
        vb_code_blocks=vb_blocks,
    )


def assessment_to_sql_notebook(assessment: SsrsAssessment) -> str:
    """Convert an SsrsAssessment to a Databricks SQL notebook string."""
    lines: list[str] = [
        f"-- SSRS Report: {assessment.report_name}",
        "-- Migrated by SyrenBridge",
        "-- Review T-SQL patterns flagged in the assessment JSON before running.",
        "",
    ]

    if assessment.parameters:
        lines.append("-- Parameters (replace with Databricks widgets or job parameters):")
        for p in assessment.parameters:
            lines.append(f"-- DECLARE @{p} = :_{p};")
        lines.append("")

    for ds in assessment.datasets:
        lines.append(f"-- ═══ Dataset: {ds.name} ═══")
        if ds.query_language == "StoredProcedure":
            lines.append(f"-- STORED PROCEDURE — manual migration required")
            lines.append(f"-- {ds.query}")
        elif ds.query_language == "TableDirect":
            lines.append(f"-- TABLE DIRECT — manual review")
            lines.append(f"SELECT * FROM {ds.query};")
        else:
            lines.append(ds.query.strip() if ds.query.strip() else "-- (empty query)")
        lines.append("")

    if assessment.vb_code_blocks:
        lines.append("-- ═══ VB.NET Custom Code — MANUAL MIGRATION REQUIRED ═══")
        for block in assessment.vb_code_blocks:
            for vb_line in block.splitlines():
                lines.append(f"-- {vb_line}")
        lines.append("")

    return "\n".join(lines)


def convert_ssrs_file_set(files: dict[str, str]) -> dict:
    """
    Convert a set of SSRS RDL files to SQL notebooks and assessment JSON.

    Args:
        files: Dict mapping relative filename → file content string.

    Returns:
        {
            "notebooks":    {filename_stem + ".sql": sql_content},
            "assessments":  {filename_stem + "_assessment.json": dict},
            "warnings":     [str, ...]
        }
    """
    import json

    notebooks: dict[str, str] = {}
    assessments: dict[str, dict] = {}
    all_warnings: list[str] = []

    rdl_files = {k: v for k, v in files.items() if k.lower().endswith((".rdl", ".rdlc", ".rsd"))}

    if not rdl_files:
        return {
            "notebooks": {},
            "assessments": {},
            "warnings": ["No .rdl / .rdlc / .rsd files found in the uploaded set"],
        }

    for rel_path, content in sorted(rdl_files.items()):
        from pathlib import Path as _Path
        stem = _Path(rel_path).stem
        assessment = parse_rdl(content, filename=stem)

        assessments[f"{stem}_assessment.json"] = assessment.to_dict()

        if assessment.auto_convertible:
            notebooks[f"{stem}.sql"] = assessment_to_sql_notebook(assessment)
        else:
            all_warnings.append(
                f"{stem}: not auto-convertible — {'; '.join(assessment.warnings) or 'no convertible datasets'}"
            )

        for w in assessment.warnings:
            all_warnings.append(f"{stem}: {w}")

    return {
        "notebooks": notebooks,
        "assessments": assessments,
        "warnings": all_warnings,
    }
```

- [ ] **Step 3: Verify module imports without error**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
source lb/bin/activate
python -c "from lb_migration_platform_ui.modules.ssrs_converter import convert_ssrs_file_set; print('OK')"
```

Expected output: `OK`

---

### Task 3: SSRS Converter Tests

**Files:**
- Create: `tests/test_ssrs_converter.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for ssrs_converter module."""
import json
import pytest
from lb_migration_platform_ui.modules.ssrs_converter import (
    parse_rdl,
    assessment_to_sql_notebook,
    convert_ssrs_file_set,
    SsrsAssessment,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_SIMPLE_RDL = """\
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition">
  <Name>SalesReport</Name>
  <DataSources>
    <DataSource Name="DS1">
      <ConnectionProperties>
        <DataProvider>SQL</DataProvider>
        <ConnectString>Data Source=myserver;Initial Catalog=SalesDB</ConnectString>
      </ConnectionProperties>
    </DataSource>
  </DataSources>
  <DataSets>
    <DataSet Name="Orders">
      <Query>
        <DataSourceName>DS1</DataSourceName>
        <CommandType>Text</CommandType>
        <CommandText>SELECT order_id, customer_id FROM orders WHERE order_date &gt; @start</CommandText>
        <QueryParameters>
          <QueryParameter Name="@start"/>
        </QueryParameters>
      </Query>
    </DataSet>
  </DataSets>
  <ReportParameters>
    <ReportParameter Name="start">
      <DataType>DateTime</DataType>
    </ReportParameter>
  </ReportParameters>
  <Body>
    <ReportItems>
      <Tablix Name="Table1">
        <DataSetName>Orders</DataSetName>
      </Tablix>
    </ReportItems>
  </Body>
</Report>"""

_SPROC_RDL = """\
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition">
  <Name>ProcReport</Name>
  <DataSets>
    <DataSet Name="Summary">
      <Query>
        <CommandType>StoredProcedure</CommandType>
        <CommandText>sp_get_summary</CommandText>
      </Query>
    </DataSet>
  </DataSets>
</Report>"""

_EMPTY_RDL = """\
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition">
  <Name>EmptyReport</Name>
</Report>"""

_VB_RDL = """\
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition">
  <Name>VbReport</Name>
  <Code>Function FormatCurrency(val As Decimal) As String
    Return Format(val, "C")
  End Function</Code>
  <DataSets>
    <DataSet Name="Sales">
      <Query>
        <CommandType>Text</CommandType>
        <CommandText>SELECT id, amount FROM sales</CommandText>
      </Query>
    </DataSet>
  </DataSets>
</Report>"""


# ── parse_rdl tests ───────────────────────────────────────────────────────────

def test_parse_rdl_report_name():
    result = parse_rdl(_SIMPLE_RDL, filename="SalesReport")
    assert result.report_name == "SalesReport"


def test_parse_rdl_data_sources():
    result = parse_rdl(_SIMPLE_RDL)
    assert len(result.data_sources) == 1
    assert result.data_sources[0].name == "DS1"
    assert result.data_sources[0].data_source_type == "SQL"


def test_parse_rdl_datasets_text():
    result = parse_rdl(_SIMPLE_RDL)
    assert len(result.datasets) == 1
    ds = result.datasets[0]
    assert ds.name == "Orders"
    assert ds.query_language == "Text"
    assert "order_id" in ds.query


def test_parse_rdl_parameters():
    result = parse_rdl(_SIMPLE_RDL)
    assert "start" in result.parameters


def test_parse_rdl_report_items():
    result = parse_rdl(_SIMPLE_RDL)
    assert len(result.report_items) == 1
    assert result.report_items[0].item_type == "Tablix"
    assert result.report_items[0].dataset_name == "Orders"


def test_parse_rdl_auto_convertible_text():
    result = parse_rdl(_SIMPLE_RDL)
    assert result.auto_convertible is True


def test_parse_rdl_stored_procedure_not_auto_convertible():
    result = parse_rdl(_SPROC_RDL)
    assert result.auto_convertible is False


def test_parse_rdl_stored_procedure_warning():
    result = parse_rdl(_SPROC_RDL)
    assert any("stored procedure" in w.lower() for w in result.warnings)


def test_parse_rdl_empty_report_not_auto_convertible():
    result = parse_rdl(_EMPTY_RDL)
    assert result.auto_convertible is False
    assert any("no datasets" in w.lower() for w in result.warnings)


def test_parse_rdl_vb_code_detected():
    result = parse_rdl(_VB_RDL)
    assert len(result.vb_code_blocks) == 1
    assert "FormatCurrency" in result.vb_code_blocks[0]
    assert any("vb" in w.lower() or "code" in w.lower() for w in result.warnings)


def test_parse_rdl_vb_still_auto_convertible_if_text_datasets():
    result = parse_rdl(_VB_RDL)
    assert result.auto_convertible is True


def test_parse_rdl_invalid_xml():
    result = parse_rdl("not xml at all", filename="bad")
    assert result.auto_convertible is False
    assert any("parse error" in w.lower() for w in result.warnings)


# ── assessment_to_sql_notebook tests ─────────────────────────────────────────

def test_notebook_contains_report_name():
    assessment = parse_rdl(_SIMPLE_RDL, filename="SalesReport")
    sql = assessment_to_sql_notebook(assessment)
    assert "SalesReport" in sql


def test_notebook_contains_sql_query():
    assessment = parse_rdl(_SIMPLE_RDL)
    sql = assessment_to_sql_notebook(assessment)
    assert "order_id" in sql


def test_notebook_contains_dataset_label():
    assessment = parse_rdl(_SIMPLE_RDL)
    sql = assessment_to_sql_notebook(assessment)
    assert "Dataset: Orders" in sql


def test_notebook_sproc_commented_out():
    assessment = parse_rdl(_SPROC_RDL)
    sql = assessment_to_sql_notebook(assessment)
    assert "STORED PROCEDURE" in sql
    assert "sp_get_summary" in sql


def test_notebook_parameter_header():
    assessment = parse_rdl(_SIMPLE_RDL)
    sql = assessment_to_sql_notebook(assessment)
    assert "@start" in sql or "_start" in sql


# ── convert_ssrs_file_set tests ───────────────────────────────────────────────

def test_convert_file_set_no_rdl_files():
    result = convert_ssrs_file_set({"report.txt": "not rdl"})
    assert result["notebooks"] == {}
    assert result["assessments"] == {}
    assert len(result["warnings"]) > 0


def test_convert_file_set_single_rdl():
    result = convert_ssrs_file_set({"SalesReport.rdl": _SIMPLE_RDL})
    assert "SalesReport.sql" in result["notebooks"]
    assert "SalesReport_assessment.json" in result["assessments"]


def test_convert_file_set_assessment_json_structure():
    result = convert_ssrs_file_set({"SalesReport.rdl": _SIMPLE_RDL})
    assessment = result["assessments"]["SalesReport_assessment.json"]
    assert assessment["report_name"] == "SalesReport"
    assert assessment["auto_convertible"] is True
    assert len(assessment["datasets"]) == 1


def test_convert_file_set_sproc_no_notebook():
    result = convert_ssrs_file_set({"ProcReport.rdl": _SPROC_RDL})
    assert "ProcReport.sql" not in result["notebooks"]
    assert "ProcReport_assessment.json" in result["assessments"]
    assert len(result["warnings"]) > 0


def test_convert_file_set_multiple_files():
    result = convert_ssrs_file_set({
        "SalesReport.rdl": _SIMPLE_RDL,
        "ProcReport.rdl": _SPROC_RDL,
    })
    assert "SalesReport.sql" in result["notebooks"]
    assert "ProcReport_assessment.json" in result["assessments"]


def test_convert_file_set_rdlc_extension():
    result = convert_ssrs_file_set({"MyReport.rdlc": _SIMPLE_RDL})
    assert "MyReport.sql" in result["notebooks"]
```

- [ ] **Step 2: Run tests to verify they fail (module not yet written)**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
source lb/bin/activate
pytest tests/test_ssrs_converter.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError` or `ImportError` for `ssrs_converter`.

- [ ] **Step 3: Run tests after implementing Task 2 Step 2**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
source lb/bin/activate
pytest tests/test_ssrs_converter.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
git add lb_migration_platform_ui/modules/ssrs_converter.py tests/test_ssrs_converter.py
git commit -m "feat: add SSRS converter module with tests"
```

---

### Task 4: Wire SSRS into app.py (Transpiler)

**Files:**
- Modify: `lb_migration_platform_ui/app.py`

- [ ] **Step 1: Add SSRS to TRANSPILER_DIALECTS**

Add after the SSIS entry (which was added in Task 1):

```python
    "SSRS (Reports)":      {"cli": "ssrs",               "exts": ["rdl", "rdlc", "rsd"],      "ssrs": True},
```

So the full dict including SSIS and SSRS looks like:

```python
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
```

- [ ] **Step 2: Import ssrs_converter in app.py**

At the top of app.py near the other module imports (around line 28-31):

```python
from modules.oozie_converter import workflow_to_json, parse_workflow, coordinator_to_dict, parse_coordinator,convert_xml, convert_oozie_file_set, _strip_annotation_keys
from modules.ssrs_converter import convert_ssrs_file_set as _convert_ssrs_file_set

from modules.databricks_service import DatabricksClient, get_databricks_credentials
from modules.sql_transpiler import run_hive_transpiler
from modules.llm_converter import LLMConverter, load_prompt
```

- [ ] **Step 3: Add `run_ssrs_converter()` helper in app.py**

Place this immediately after `run_oozie_converter()` (around line 1230):

```python
def run_ssrs_converter(
    src_dir: str,
    out_dir: str,
    err_file: str,
) -> tuple[bool, str, str, dict]:
    """
    Convert SSRS .rdl/.rdlc/.rsd files to SQL notebooks and assessment JSON.

    Returns (ok, stdout, stderr, ssrs_results) where ssrs_results is the
    dict returned by convert_ssrs_file_set.
    """
    import json as _json
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
            out_file.write_text(_json.dumps(adict, indent=2), encoding="utf-8")
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

    ok = generated > 0
    return ok, stdout, "\n".join(errors) if errors else "", results
```

- [ ] **Step 4: Add SSRS run branch in the transpiler execution block**

In the `if run_transpile_clicked` block around line 2415, add the `ssrs` branch **before** the `elif dialect_info.get("custom"):` branch:

```python
                if dialect_info.get("oozie"):
                    tp_ok, tp_stdout, tp_stderr, _oozie_links = run_oozie_converter(
                        src_dir=tp_src_dir,
                        out_dir=tp_out_dir,
                        err_file=tp_err_file,
                    )
                    st.session_state["tp_oozie_links"] = _oozie_links
                    for lk in _oozie_links:
                        if lk["workflow"]:
                            st.write(f"✅ **{lk['coordinator']}** → linked to **{lk['workflow']}** via `run_job_task`")
                        else:
                            st.write(f"⚠️ **{lk['coordinator']}** → no workflow matched — add `run_job_task` manually")
                elif dialect_info.get("ssrs"):
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
                    st.write(f"📊 **{n_as}** report(s) assessed · **{auto_conv}/{n_as}** auto-convertible · **{n_nb}** SQL notebook(s) generated")
                elif dialect_info.get("custom"):
                    ...
```

- [ ] **Step 5: Add SSRS session state to `store_transpile_output_state` call**

In the `store_transpile_output_state(...)` call (around line 2473), add the `is_ssrs` key:

```python
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
```

- [ ] **Step 6: Add SSRS results section in the output display block**

In the results section (around line 2509, after the `if dialect_info.get("oozie"):` block), add an `elif` for SSRS:

```python
                if dialect_info.get("oozie"):
                    # ... existing oozie block unchanged ...

                elif dialect_info.get("ssrs"):
                    ssrs_results = st.session_state.get("tp_ssrs_results", {})
                    assessments = ssrs_results.get("assessments", {})
                    notebooks = ssrs_results.get("notebooks", {})

                    if assessments:
                        n_auto = sum(1 for a in assessments.values() if a.get("auto_convertible"))
                        st.markdown(
                            f'<div style="background:#ecfdf5;border:1px solid #6ee7b7;border-radius:8px;'
                            f'padding:0.75rem 1rem;margin-bottom:0.75rem;font-size:0.88rem;color:#065f46;">'
                            f'📊 <strong>{len(assessments)}</strong> report(s) assessed · '
                            f'<strong>{n_auto}/{len(assessments)}</strong> auto-convertible · '
                            f'<strong>{len(notebooks)}</strong> SQL notebook(s) generated</div>',
                            unsafe_allow_html=True,
                        )
                    st.markdown("⚠️ **SSRS Conversion Notes**")
                    with st.expander("ℹ️ View details"):
                        st.markdown("""
                    - **SQL Notebooks** contain one SQL cell per dataset with the original query.
                    - **Assessment JSON** files list data sources, datasets, report items, parameters, and VB code blocks.
                    - **Stored procedures** are commented out — migrate the proc logic manually.
                    - **T-SQL functions** (GETDATE, ISNULL, TOP N, etc.) are flagged in warnings — update to Spark SQL equivalents.
                    - **VB.NET code blocks** are preserved as comments — rewrite as Python UDFs or SQL expressions.
                    - **Parameters** appear as `-- DECLARE` comments — replace with Databricks widgets (`dbutils.widgets`) or job parameters.
                    - **Report layout** (visual formatting) is not converted — use Databricks Dashboards or LSQL for visual output.
                    """)
```

- [ ] **Step 7: Update dialect count badge and Get Started table**

In app.py, find the two places that reference "11 Supported Dialects" and update to **13**:

1. Around line 1454 in the Get Started tab:
```python
    <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                text-transform:uppercase;margin-bottom:0.75rem;">Transpiler — 13 Supported Dialects</div>
```

2. Find the `⚡ Transpiler — 11 Supported Dialects` badge HTML (around line 770 per CLAUDE.md) and update to 13:
```html
Transpiler — 13 Supported Dialects
```

Also add SSIS and SSRS rows to `dialect_rows` list (around line 1457):

```python
    dialect_rows = [
        ("DataStage",          "Databricks Labs Lakebridge",  "PySpark / SparkSQL",          ".dsx .xml .pjb"),
        ("HiveSQL (Cloudera)", "sqlglot (Databricks dialect)", "Databricks SQL / PySpark",   ".hql .hive .sql .ddl .dml"),
        ("Informatica",        "Databricks Labs Lakebridge",  "PySpark / SparkSQL",          ".xml .session .wf .m .mplt .lkp"),
        ("Informatica Cloud",  "Databricks Labs Lakebridge",  "PySpark / SparkSQL",          ".xml .json .session"),
        ("MS SQL Server",      "Databricks Labs Lakebridge",  "PySpark / SparkSQL",          ".sql .ddl .dml .proc .view"),
        ("Netezza",            "Databricks Labs Lakebridge",  "PySpark / SparkSQL",          ".sql .ddl .dml .nzb"),
        ("Oracle",             "Databricks Labs Lakebridge",  "PySpark / SparkSQL",          ".sql .ddl .dml .pls .prc .vw"),
        ("Snowflake",          "Databricks Labs Lakebridge",  "PySpark / SparkSQL",          ".sql .ddl .dml"),
        ("SSIS",               "BladeBridge (Lakebridge)",    "SparkSQL",                    ".dtsx .xml"),
        ("SSRS (Reports)",     "Built-in ssrs_converter",     "SQL Notebooks + JSON",        ".rdl .rdlc .rsd"),
        ("Synapse",            "Databricks Labs Lakebridge",  "PySpark / SparkSQL",          ".sql .ddl .dml .json"),
        ("Teradata",           "Databricks Labs Lakebridge",  "PySpark / SparkSQL",          ".sql .bteq .tdl .tpt .ddl .dml"),
        ("Oozie (Workflow)",   "lxml (built-in parser)",      "Databricks Jobs JSON",        ".xml"),
    ]
```

- [ ] **Step 8: Commit**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
git add lb_migration_platform_ui/app.py
git commit -m "feat: wire SSRS into transpiler tab with assessment + SQL notebook output"
```

---

### Task 5: Run Full Test Suite

- [ ] **Step 1: Run all tests**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
source lb/bin/activate
pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: All tests PASS, including the new `test_ssrs_converter.py` suite.

- [ ] **Step 2: Final commit if anything needed fixing**

```bash
git add -p
git commit -m "fix: address test failures from SSIS/SSRS integration"
```

---

## Spec Coverage Check

| Requirement | Covered by |
|-------------|-----------|
| SSIS in Analyzer (verify working) | Already works — no changes needed (verified in exploration) |
| SSRS in Analyzer (verify working) | Already works — no changes needed (verified in exploration) |
| SSIS in Transpiler via BladeBridge | Task 1 |
| SSIS SparkSQL-only target | Task 1, Step 3 |
| SSRS custom converter module | Task 2 |
| SSRS assessment JSON output | Task 2, Task 4 |
| SSRS SQL notebook output | Task 2, Task 4 |
| SSRS save to Databricks button | Handled by existing upload_directory_to_workspace flow (already in results section) |
| Tests for SSRS converter | Task 3 |
| Dialect count badge 11 → 13 | Task 4, Step 7 |
| Get Started table updated | Task 4, Step 7 |
