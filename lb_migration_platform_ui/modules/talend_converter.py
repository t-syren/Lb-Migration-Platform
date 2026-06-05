"""
Talend → Databricks PySpark converter.

Parses Talend .item XML job files and generates PySpark notebook (.py) files.
Each .item file becomes one output .py file ready to run on Databricks.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class TalendColumn:
    name: str
    col_type: str
    nullable: bool = True


@dataclass
class TalendComponent:
    unique_name: str
    component_name: str
    params: Dict[str, str] = field(default_factory=dict)
    columns: List[TalendColumn] = field(default_factory=list)


@dataclass
class TalendConnection:
    source: str
    target: str
    label: str
    conn_type: str = "FLOW"


# ── XML parsing ────────────────────────────────────────────────────────────────

def _param_val(node_el: ET.Element, param_name: str, default: str = "") -> str:
    for ep in node_el.findall("elementParameter"):
        if ep.get("name") == param_name:
            return ep.get("value", default)
    return default


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _parse_columns(node_el: ET.Element) -> List[TalendColumn]:
    for meta in node_el.findall("metadata"):
        connector = meta.get("connector", "")
        if connector in ("FLOW", "OUT", "ITERATE", "MAIN", ""):
            cols = []
            for col in meta.findall("column"):
                name = col.get("name", "col")
                col_type = col.get("type", "id_String")
                nullable = col.get("nullable", "true").lower() == "true"
                cols.append(TalendColumn(name=name, col_type=col_type, nullable=nullable))
            if cols:
                return cols
    return []


def parse_talend_job(
    xml_str: str,
    filename: str = "job",
) -> Tuple[Dict[str, TalendComponent], List[TalendConnection], List[str]]:
    """Parse a Talend .item XML and return (components, connections, warnings)."""
    warnings: List[str] = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as exc:
        return {}, [], [f"XML parse error in {filename}: {exc}"]

    components: Dict[str, TalendComponent] = {}
    connections: List[TalendConnection] = []

    def _tag(el: ET.Element) -> str:
        t = el.tag
        return t.split("}")[-1] if "}" in t else t

    for child in root:
        tag = _tag(child)
        if tag == "node":
            comp_name = child.get("componentName", "")
            unique_name = _param_val(child, "UNIQUE_NAME") or comp_name + "_1"
            params: Dict[str, str] = {}
            for ep in child.findall("elementParameter"):
                n = ep.get("name", "")
                v = ep.get("value", "")
                if n:
                    params[n] = v
            columns = _parse_columns(child)
            components[unique_name] = TalendComponent(
                unique_name=unique_name,
                component_name=comp_name,
                params=params,
                columns=columns,
            )
        elif tag == "connection":
            source = child.get("source", "")
            target = child.get("target", "")
            label = child.get("label", "")
            conn_type = child.get("connectorName", "FLOW")
            if source and target:
                connections.append(TalendConnection(
                    source=source, target=target, label=label, conn_type=conn_type
                ))

    if not components:
        warnings.append(f"{filename}: no Talend nodes found — is this a .item file?")

    return components, connections, warnings


# ── Topological sort ───────────────────────────────────────────────────────────

def _topo_sort(
    components: Dict[str, TalendComponent],
    connections: List[TalendConnection],
) -> List[str]:
    in_degree: Dict[str, int] = {k: 0 for k in components}
    successors: Dict[str, List[str]] = defaultdict(list)
    for conn in connections:
        if conn.conn_type in ("FLOW", "ITERATE", "REJECT", "MAIN"):
            if conn.source in in_degree and conn.target in in_degree:
                in_degree[conn.target] += 1
                successors[conn.source].append(conn.target)

    queue = sorted(k for k, v in in_degree.items() if v == 0)
    result: List[str] = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for suc in sorted(successors[node]):
            in_degree[suc] -= 1
            if in_degree[suc] == 0:
                queue.append(suc)
    for k in components:
        if k not in result:
            result.append(k)
    return result


# ── Helpers ────────────────────────────────────────────────────────────────────

def _var(unique_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", unique_name).lower()


def _df(unique_name: str) -> str:
    return f"df_{_var(unique_name)}"


def _db_type_from_component(comp: TalendComponent) -> str:
    """Infer DB type from component name first, then fall back to explicit param."""
    cname = comp.component_name.lower()
    if "mysql" in cname:
        return "mysql"
    if "oracle" in cname:
        return "oracle"
    if "snowflake" in cname:
        return "snowflake"
    if "mssql" in cname or "sqlserver" in cname:
        return "mssql"
    if "postgres" in cname:
        return "postgresql"
    if "redshift" in cname:
        return "redshift"
    if "synapse" in cname:
        return "synapse"
    if "teradata" in cname:
        return "teradata"
    if "db2" in cname:
        return "db2"
    if "netezza" in cname:
        return "netezza"
    # fall back to explicit param
    p = comp.params
    return _strip_quotes(p.get("DB_TYPE", p.get("DBTYPE", "jdbc")))


def _jdbc_url(db_type: str, host: str, port: str, db: str) -> str:
    db_type = db_type.lower()
    host = host or "host"
    port = port or "port"
    db = db or "database"
    if "mysql" in db_type:
        return f"jdbc:mysql://{host}:{port}/{db}"
    if "postgres" in db_type or "redshift" in db_type:
        return f"jdbc:postgresql://{host}:{port}/{db}"
    if "oracle" in db_type:
        return f"jdbc:oracle:thin:@{host}:{port}:{db}"
    if "mssql" in db_type or "sqlserver" in db_type:
        return f"jdbc:sqlserver://{host}:{port};databaseName={db}"
    if "db2" in db_type:
        return f"jdbc:db2://{host}:{port}/{db}"
    if "hive" in db_type:
        return f"jdbc:hive2://{host}:{port}/{db}"
    if "snowflake" in db_type:
        return f"jdbc:snowflake://{host}/?db={db}"
    return f"jdbc:{db_type}://{host}:{port}/{db}"


def _write_mode(action: str) -> str:
    action = action.lower()
    if action in ("truncate", "drop_create", "clear_data_and_bulk_load", "drop_and_create"):
        return "overwrite"
    return "append"


# ── Per-component code generators ─────────────────────────────────────────────

def _gen_db_input(comp: TalendComponent, _inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    db_type = _db_type_from_component(comp)
    host = _strip_quotes(p.get("HOST", "host"))
    port = _strip_quotes(p.get("PORT", "3306"))
    db = _strip_quotes(p.get("DBNAME", p.get("DATABASE", "database")))
    user = _strip_quotes(p.get("USERNAME", p.get("USER", "user")))
    password = _strip_quotes(p.get("PASSWORD", "password"))
    query = _strip_quotes(p.get("QUERY", f"SELECT * FROM {_strip_quotes(p.get('TABLE', 'table'))}"))
    url = _jdbc_url(db_type, host, port, db)
    out = _df(comp.unique_name)
    code = (
        f"# {comp.unique_name}: Read from {db_type}\n"
        f'{out} = (\n'
        f'    spark.read.format("jdbc")\n'
        f'    .option("url", "{url}")\n'
        f'    .option("query", {repr(query)})\n'
        f'    .option("user", "{user}")\n'
        f'    .option("password", "{password}")  # TODO: use a secret\n'
        f'    .load()\n'
        f')\n'
    )
    return code, []


def _gen_file_input_delimited(comp: TalendComponent, _inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    path = _strip_quotes(p.get("FILENAME", "/path/to/input.csv"))
    sep = _strip_quotes(p.get("FIELDSEPARATOR", p.get("FIELD_SEPARATOR", ","))) or ","
    header = _strip_quotes(p.get("HEADER", "1"))
    has_header = header not in ("0", "false", "False")
    out = _df(comp.unique_name)
    code = (
        f"# {comp.unique_name}: Read CSV / delimited file\n"
        f'{out} = (\n'
        f'    spark.read.format("csv")\n'
        f'    .option("sep", {repr(sep)})\n'
        f'    .option("header", "{str(has_header).lower()}")\n'
        f'    .option("inferSchema", "true")\n'
        f'    .load({repr(path)})\n'
        f')\n'
    )
    return code, []


def _gen_file_input_excel(comp: TalendComponent, _inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    path = _strip_quotes(p.get("FILENAME", "/path/to/input.xlsx"))
    out = _df(comp.unique_name)
    warnings = [f"{comp.unique_name}: Excel files require the 'com.crealytics:spark-excel' library — add it to your cluster."]
    code = (
        f"# {comp.unique_name}: Read Excel file\n"
        f"# Requires: com.crealytics:spark-excel library on the cluster\n"
        f'{out} = (\n'
        f'    spark.read.format("com.crealytics.spark.excel")\n'
        f'    .option("header", "true")\n'
        f'    .option("inferSchema", "true")\n'
        f'    .load({repr(path)})\n'
        f')\n'
    )
    return code, warnings


def _gen_file_input_json(comp: TalendComponent, _inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    path = _strip_quotes(p.get("FILENAME", "/path/to/input.json"))
    out = _df(comp.unique_name)
    return f"# {comp.unique_name}: Read JSON\n{out} = spark.read.json({repr(path)})\n", []


def _gen_file_input_parquet(comp: TalendComponent, _inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    path = _strip_quotes(p.get("FILENAME", "/path/to/input.parquet"))
    out = _df(comp.unique_name)
    return f"# {comp.unique_name}: Read Parquet\n{out} = spark.read.parquet({repr(path)})\n", []


def _gen_hive_input(comp: TalendComponent, _inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    table = _strip_quotes(p.get("TABLE_NAME", p.get("TABLE", "schema.table")))
    out = _df(comp.unique_name)
    return f"# {comp.unique_name}: Read from Delta / Hive table\n{out} = spark.table({repr(table)})\n", []


def _gen_s3_input(comp: TalendComponent, _inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    bucket = _strip_quotes(p.get("BUCKET", "my-bucket"))
    key = _strip_quotes(p.get("KEY", p.get("PREFIX", "path/to/files")))
    fmt = _strip_quotes(p.get("FORMAT", "csv")).lower()
    path = f"s3a://{bucket}/{key}"
    out = _df(comp.unique_name)
    code = (
        f"# {comp.unique_name}: Read from S3\n"
        f'# TODO: Configure S3 credentials via Databricks secrets or instance profile\n'
        f'{out} = spark.read.format("{fmt}").option("header", "true").load({repr(path)})\n'
    )
    return code, []


def _gen_db_output(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    db_type = _db_type_from_component(comp)
    host = _strip_quotes(p.get("HOST", "host"))
    port = _strip_quotes(p.get("PORT", "3306"))
    db = _strip_quotes(p.get("DBNAME", p.get("DATABASE", "database")))
    user = _strip_quotes(p.get("USERNAME", p.get("USER", "user")))
    password = _strip_quotes(p.get("PASSWORD", "password"))
    table = _strip_quotes(p.get("TABLE", "output_table"))
    action = _strip_quotes(p.get("ACTION", "INSERT"))
    url = _jdbc_url(db_type, host, port, db)
    mode = _write_mode(action)
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    code = (
        f"# {comp.unique_name}: Write to {db_type}\n"
        f'{src}.write.format("jdbc") \\\n'
        f'    .option("url", "{url}") \\\n'
        f'    .option("dbtable", "{table}") \\\n'
        f'    .option("user", "{user}") \\\n'
        f'    .option("password", "{password}")  # TODO: use a secret\\\n'
        f'    .mode("{mode}") \\\n'
        f'    .save()\n'
        f'{out} = {src}\n'
    )
    return code, []


def _gen_hive_output(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    table = _strip_quotes(p.get("TABLE_NAME", p.get("TABLE", "output_table")))
    action = _strip_quotes(p.get("ACTION", "INSERT"))
    mode = _write_mode(action)
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    code = (
        f"# {comp.unique_name}: Write to Delta / Hive table\n"
        f'{src}.write.format("delta").mode("{mode}").saveAsTable({repr(table)})\n'
        f'{out} = {src}\n'
    )
    return code, []


def _gen_delta_output(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    path = _strip_quotes(p.get("PATH", p.get("FILENAME", "/delta/output")))
    action = _strip_quotes(p.get("ACTION", "INSERT"))
    mode = _write_mode(action)
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    code = (
        f"# {comp.unique_name}: Write to Delta Lake path\n"
        f'{src}.write.format("delta").mode("{mode}").save({repr(path)})\n'
        f'{out} = {src}\n'
    )
    return code, []


def _gen_file_output_delimited(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    path = _strip_quotes(p.get("FILENAME", "/path/to/output.csv"))
    sep = _strip_quotes(p.get("FIELDSEPARATOR", p.get("FIELD_SEPARATOR", ","))) or ","
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    code = (
        f"# {comp.unique_name}: Write CSV / delimited file\n"
        f'{src}.write.format("csv") \\\n'
        f'    .option("sep", {repr(sep)}) \\\n'
        f'    .option("header", "true") \\\n'
        f'    .mode("overwrite") \\\n'
        f'    .save({repr(path)})\n'
        f'{out} = {src}\n'
    )
    return code, []


def _gen_file_output_parquet(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    path = _strip_quotes(p.get("FILENAME", "/path/to/output.parquet"))
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    return (
        f"# {comp.unique_name}: Write Parquet\n"
        f'{src}.write.parquet({repr(path)}, mode="overwrite")\n'
        f'{out} = {src}\n',
        [],
    )


def _gen_file_output_json(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    p = comp.params
    path = _strip_quotes(p.get("FILENAME", "/path/to/output.json"))
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    return (
        f"# {comp.unique_name}: Write JSON\n"
        f'{src}.write.json({repr(path)}, mode="overwrite")\n'
        f'{out} = {src}\n',
        [],
    )


_TMAP_SKIP_PARAMS = frozenset({
    "UNIQUE_NAME", "STARTABLE", "ACTIVATED", "MAPPING_TYPE",
    "POSITION_X", "POSITION_Y", "LABEL",
})


def _gen_map(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    warnings = [
        f"{comp.unique_name}: tMap expressions require manual review — column passthrough generated. "
        "Add F.expr() or withColumn() calls for each transformation."
    ]

    # Dump all non-trivial elementParameters as reference comments so engineers
    # can see the original Talend expressions without opening the .item file.
    expr_lines: List[str] = []
    for name, val in comp.params.items():
        if name in _TMAP_SKIP_PARAMS:
            continue
        clean = _strip_quotes(val).replace("\n", " ").strip()
        if clean:
            expr_lines.append(f"#   {name}: {clean[:160]}")

    expr_block = ""
    if expr_lines:
        expr_block = (
            "# Original tMap parameters (implement each as F.expr() / withColumn()):\n"
            + "\n".join(expr_lines)
            + "\n"
        )

    if comp.columns:
        col_list = ", ".join(f'"{c.name}"' for c in comp.columns[:30])
        select_expr = f".select({col_list})"
    else:
        select_expr = ""

    code = (
        f"# {comp.unique_name}: Column mapping / transformation (tMap)\n"
        f"# TODO: Replace passthrough with actual transformation expressions\n"
        + expr_block
        + f"{out} = {src}{select_expr}\n"
    )
    return code, warnings


def _gen_filter_row(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    conds_raw = comp.params.get("CONDITIONS", "")
    warnings = []
    if conds_raw and conds_raw not in ("[]", ""):
        warnings.append(f"{comp.unique_name}: tFilterRow conditions require manual review: {conds_raw[:200]}")
    code = (
        f"# {comp.unique_name}: Filter rows (tFilterRow)\n"
        f"# TODO: Replace with actual filter condition\n"
        f'{out} = {src}.filter("1=1")  # placeholder\n'
    )
    return code, warnings


def _gen_sort_row(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    sort_raw = comp.params.get("SORT_CRITERIA", "")
    comment = f"  # criteria: {sort_raw[:100]}" if sort_raw and sort_raw != "[]" else "  # TODO: add sort columns"
    return (
        f"# {comp.unique_name}: Sort rows (tSortRow)\n"
        f"{out} = {src}.orderBy(){comment}\n",
        [],
    )


def _gen_aggregate_row(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    warnings = [f"{comp.unique_name}: tAggregateRow groupBy/agg expressions require manual review"]
    code = (
        f"# {comp.unique_name}: Aggregate rows (tAggregateRow)\n"
        f"# TODO: Replace with actual groupBy columns and agg expressions\n"
        f"{out} = {src}.groupBy().agg(F.count('*').alias('count'))\n"
    )
    return code, warnings


def _gen_join(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    out = _df(comp.unique_name)
    warnings = [f"{comp.unique_name}: tJoin join key and type require manual review"]
    if len(inputs) >= 2:
        code = (
            f"# {comp.unique_name}: Join DataFrames (tJoin)\n"
            f"# TODO: Replace join key and join type\n"
            f'{out} = {inputs[0]}.join({inputs[1]}, on="id", how="inner")\n'
        )
    else:
        src = inputs[0] if inputs else "df_input"
        code = (
            f"# {comp.unique_name}: tJoin (missing second input — review manually)\n"
            f"{out} = {src}\n"
        )
    return code, warnings


def _gen_unite(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    out = _df(comp.unique_name)
    if len(inputs) >= 2:
        chain = inputs[0] + "".join(f".union({i})" for i in inputs[1:])
        code = f"# {comp.unique_name}: Union DataFrames (tUnite)\n{out} = {chain}\n"
    else:
        src = inputs[0] if inputs else "df_input"
        code = f"# {comp.unique_name}: tUnite (single input)\n{out} = {src}\n"
    return code, []


def _gen_log_row(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    return (
        f"# {comp.unique_name}: Print rows (tLogRow)\n"
        f"{src}.show(20, truncate=False)\n"
        f"{out} = {src}\n",
        [],
    )


def _gen_replace_list(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    warnings = [f"{comp.unique_name}: tReplaceList replacement mappings require manual review"]
    return (
        f"# {comp.unique_name}: Replace values (tReplaceList)\n"
        f"# TODO: Add F.when() expressions for each replacement rule\n"
        f"{out} = {src}\n",
        warnings,
    )


def _gen_normalize(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    src = inputs[0] if inputs else "df_input"
    out = _df(comp.unique_name)
    warnings = [f"{comp.unique_name}: tNormalize requires manual review — use F.explode() or F.split()"]
    return (
        f"# {comp.unique_name}: Normalize / explode rows (tNormalize)\n"
        f"# TODO: Use F.explode() or F.split() on the relevant column\n"
        f"{out} = {src}\n",
        warnings,
    )


def _gen_generic(comp: TalendComponent, inputs: List[str]) -> Tuple[str, List[str]]:
    src = inputs[0] if inputs else None
    out = _df(comp.unique_name)
    warnings = [f"{comp.unique_name}: {comp.component_name} is not fully supported — passthrough generated; review manually"]
    src_expr = src if src else "spark.createDataFrame([], schema=StructType([]))"
    return (
        f"# {comp.unique_name}: {comp.component_name} (not fully supported — review manually)\n"
        f"{out} = {src_expr}\n",
        warnings,
    )


# ── Component dispatch table ───────────────────────────────────────────────────

_GENERATORS = {
    # ── Inputs ────────────────────────────────────────────────────────────────
    "tDBInput":              _gen_db_input,
    "tMysqlInput":           _gen_db_input,
    "tOracleInput":          _gen_db_input,
    "tMSSqlInput":           _gen_db_input,
    "tPostgresqlInput":      _gen_db_input,
    "tSnowflakeInput":       _gen_db_input,
    "tNetsuiteInput":        _gen_db_input,
    "tRedshiftInput":        _gen_db_input,
    "tSynapseInput":         _gen_db_input,
    "tTeradataInput":        _gen_db_input,
    "tFileInputDelimited":   _gen_file_input_delimited,
    "tFileInputExcel":       _gen_file_input_excel,
    "tFileInputJSON":        _gen_file_input_json,
    "tFileInputParquet":     _gen_file_input_parquet,
    "tHiveInput":            _gen_hive_input,
    "tDeltaLakeInput":       _gen_hive_input,
    "tS3Input":              _gen_s3_input,
    # ── Outputs ───────────────────────────────────────────────────────────────
    "tDBOutput":             _gen_db_output,
    "tMysqlOutput":          _gen_db_output,
    "tOracleOutput":         _gen_db_output,
    "tMSSqlOutput":          _gen_db_output,
    "tPostgresqlOutput":     _gen_db_output,
    "tSnowflakeOutput":      _gen_db_output,
    "tRedshiftOutput":       _gen_db_output,
    "tSynapseOutput":        _gen_db_output,
    "tTeradataOutput":       _gen_db_output,
    "tHiveOutput":           _gen_hive_output,
    "tDeltaLakeOutput":      _gen_delta_output,
    "tFileOutputDelimited":  _gen_file_output_delimited,
    "tFileOutputParquet":    _gen_file_output_parquet,
    "tFileOutputJSON":       _gen_file_output_json,
    # ── Transformations ───────────────────────────────────────────────────────
    "tMap":                  _gen_map,
    "tFilterRow":            _gen_filter_row,
    "tSortRow":              _gen_sort_row,
    "tAggregateRow":         _gen_aggregate_row,
    "tJoin":                 _gen_join,
    "tUnite":                _gen_unite,
    "tLogRow":               _gen_log_row,
    "tWarn":                 _gen_log_row,
    "tReplaceList":          _gen_replace_list,
    "tNormalize":            _gen_normalize,
}

# Components that need ALL predecessor DataFrames (not just the first)
_MULTI_INPUT = {"tJoin", "tUnite"}


# ── Code generator ─────────────────────────────────────────────────────────────

def generate_pyspark(
    job_name: str,
    components: Dict[str, TalendComponent],
    connections: List[TalendConnection],
) -> Tuple[str, List[str]]:
    """Generate a PySpark notebook string from a parsed Talend job."""
    all_warnings: List[str] = []
    order = _topo_sort(components, connections)

    predecessors: Dict[str, List[str]] = defaultdict(list)
    for conn in connections:
        if conn.conn_type in ("FLOW", "ITERATE", "MAIN"):
            predecessors[conn.target].append(conn.source)

    lines: List[str] = [
        f"# Databricks PySpark — converted from Talend job: {job_name}",
        "# Generated by SyrenBridge Talend Converter",
        "# Review all TODO comments before running in production",
        "",
        "from pyspark.sql import SparkSession",
        "from pyspark.sql import functions as F",
        "from pyspark.sql.types import *",
        "",
        "spark = SparkSession.builder.getOrCreate()",
        "",
    ]

    for unique_name in order:
        comp = components.get(unique_name)
        if comp is None:
            continue

        preds = [p for p in predecessors.get(unique_name, []) if p in components]
        input_dfs = [_df(p) for p in preds]

        gen_fn = _GENERATORS.get(comp.component_name)
        if gen_fn is None:
            code, warnings = _gen_generic(comp, input_dfs)
        elif comp.component_name in _MULTI_INPUT:
            code, warnings = gen_fn(comp, input_dfs)
        else:
            code, warnings = gen_fn(comp, input_dfs)

        lines.append(code)
        all_warnings.extend(warnings)

    return "\n".join(lines), all_warnings


# ── Public API ─────────────────────────────────────────────────────────────────

def convert_talend_file_set(files: Dict[str, str]) -> Dict:
    """
    Convert a set of Talend .item files to PySpark notebooks.

    Args:
        files: mapping of relative filename → XML content.

    Returns:
        {
            "notebooks": {job_name: pyspark_code_str},
            "warnings":  [str],
        }
    """
    notebooks: Dict[str, str] = {}
    all_warnings: List[str] = []

    for filename, xml_str in files.items():
        job_name = Path(filename).stem
        components, connections, parse_warnings = parse_talend_job(xml_str, filename)
        all_warnings.extend(parse_warnings)

        if not components:
            continue

        code, gen_warnings = generate_pyspark(job_name, components, connections)
        notebooks[job_name] = code
        all_warnings.extend(gen_warnings)

    return {"notebooks": notebooks, "warnings": all_warnings}
