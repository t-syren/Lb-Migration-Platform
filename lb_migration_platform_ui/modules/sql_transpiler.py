"""Hive SQL → Databricks SQL transpiler utilities."""
import logging
import re
from typing import Dict

import sqlglot
import sqlglot.errors

logger = logging.getLogger(__name__)

# Hive-specific clauses that have no Spark SQL equivalent
_STRIP_PATTERNS = [
    r"ROW\s+FORMAT\s+DELIMITED(?:\s+FIELDS\s+TERMINATED\s+BY\s+'[^']*')?(?:\s+LINES\s+TERMINATED\s+BY\s+'[^']*')?",
    r"STORED\s+AS\s+(?:TEXTFILE|ORC|PARQUET|AVRO|SEQUENCEFILE|RCFILE)",
    r"TBLPROPERTIES\s*\([^)]*\)",
    r"LOCATION\s+'hdfs://[^']*'",
]


def transpile_hive_sql(sql: str) -> str:
    """Transpile Hive SQL to Databricks-compatible Spark SQL.

    Uses sqlglot for structural conversion then applies Hive-specific
    clause stripping for constructs sqlglot does not fully handle.
    """
    try:
        statements = sqlglot.transpile(sql, read="hive", write="spark", pretty=True)
        result = ";\n\n".join(statements)
    except sqlglot.errors.SqlglotError as exc:
        logger.warning("sqlglot transpile failed, falling back to raw SQL: %s", exc)
        result = sql

    # Strip unsupported Hive clauses
    for pattern in _STRIP_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    # Collapse extra blank lines introduced by stripping
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result


def infer_schema(sql: str) -> Dict[str, str]:
    """Return {column_name: hive_type} for the first CREATE TABLE in sql.

    Partition columns (PARTITIONED BY clause) are excluded — they are
    not stored in the data files and don't need dummy data rows.
    """
    schema: Dict[str, str] = {}

    # Find first CREATE TABLE ... ( columns ) block
    create_match = re.search(
        r"CREATE\s+(?:EXTERNAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:\w+\.)?\w+\s*\(([^)]+)\)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not create_match:
        return schema

    columns_block = create_match.group(1)

    # Find PARTITIONED BY columns to exclude
    partition_cols: set = set()
    part_match = re.search(
        r"PARTITIONED\s+BY\s*\(([^)]+)\)", sql, re.IGNORECASE | re.DOTALL
    )
    if part_match:
        for line in part_match.group(1).split(","):
            parts = line.strip().split()
            if parts:
                partition_cols.add(parts[0].lower())

    # Parse column definitions: name TYPE [COMMENT '...']
    for line in columns_block.split(","):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        col_name = parts[0].strip("`")
        col_type = parts[1].upper()
        if col_name.lower() not in partition_cols:
            schema[col_name] = col_type

    return schema
