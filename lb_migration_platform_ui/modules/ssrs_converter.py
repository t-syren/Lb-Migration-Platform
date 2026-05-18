"""
SSRS (.rdl/.rdlc/.rsd) to Databricks SQL Notebook + Assessment JSON converter.

Entry point: convert_ssrs_file_set(files: Dict[str, str]) -> Dict
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from lxml import etree


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
    """Return the RDL namespace from the root element, or empty string."""
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

    name_el = root.find(_t(ns, "Name"))
    report_name = _text(name_el) or filename

    # ── Data Sources ──────────────────────────────────────────────────────────
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

    # ── Parameters ────────────────────────────────────────────────────────────
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

    # ── Datasets ──────────────────────────────────────────────────────────────
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
            for hit in _flag_tsql_hints(sql):
                warnings.append(f"Dataset '{dset_name}': T-SQL pattern detected — {hit}")

        datasets.append(SsrsDataset(name=dset_name, query_language=lang, query=sql, parameters=dset_params))

    # ── Report Items ──────────────────────────────────────────────────────────
    report_items: list[SsrsReportItem] = []
    for item_type in ("Tablix", "Chart", "Matrix", "Textbox", "Image", "Subreport"):
        for el in root.iter(_t(ns, item_type)):
            ri_name = el.get("Name", "")
            ds_ref_el = None
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
            lines.append("-- STORED PROCEDURE — manual migration required")
            lines.append(f"-- {ds.query}")
        elif ds.query_language == "TableDirect":
            lines.append("-- TABLE DIRECT — manual review")
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
            "notebooks":   {stem + ".sql": sql_content},
            "assessments": {stem + "_assessment.json": dict},
            "warnings":    [str, ...]
        }
    """
    import json
    from pathlib import Path as _Path

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
