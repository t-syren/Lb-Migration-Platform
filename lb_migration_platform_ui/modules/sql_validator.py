"""Validate Hive→Spark SQL transpilation by executing both in local PySpark."""
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    passed: bool = False
    row_count_match: bool = False
    schema_match: bool = False
    original_count: int = 0
    transpiled_count: int = 0
    original_columns: List[str] = field(default_factory=list)
    transpiled_columns: List[str] = field(default_factory=list)
    diff_report: str = ""
    error: Optional[str] = None


def validate_transpilation(
    spark: SparkSession,
    original_sql: str,
    transpiled_sql: str,
) -> ValidationResult:
    """Execute both SQL strings in local Spark and compare results.

    The caller is responsible for registering required temp tables before
    calling this function (use dummy_data.register_temp_tables).
    """
    result = ValidationResult()

    # Execute original SQL
    try:
        orig_df = spark.sql(original_sql)
        result.original_count = orig_df.count()
        result.original_columns = orig_df.columns
    except Exception as exc:
        result.error = f"Original SQL execution failed: {exc}"
        logger.error(result.error)
        return result

    # Execute transpiled SQL
    try:
        trans_df = spark.sql(transpiled_sql)
        result.transpiled_count = trans_df.count()
        result.transpiled_columns = trans_df.columns
    except Exception as exc:
        result.error = f"Transpiled SQL execution failed: {exc}"
        logger.error(result.error)
        return result

    # Compare schema (column names, order-insensitive)
    result.schema_match = sorted(result.original_columns) == sorted(result.transpiled_columns)

    # Compare row counts
    result.row_count_match = result.original_count == result.transpiled_count

    # Build diff report
    lines = [
        f"Row count — original: {result.original_count}, transpiled: {result.transpiled_count}",
        f"Schema match: {result.schema_match}",
    ]
    if not result.schema_match:
        only_orig = set(result.original_columns) - set(result.transpiled_columns)
        only_trans = set(result.transpiled_columns) - set(result.original_columns)
        if only_orig:
            lines.append(f"  Columns only in original: {sorted(only_orig)}")
        if only_trans:
            lines.append(f"  Columns only in transpiled: {sorted(only_trans)}")

    # Sample data diff (first 5 rows, only when schema matches)
    data_match = True
    if result.schema_match and result.row_count_match:
        orig_rows = [str(r.asDict()) for r in orig_df.limit(5).collect()]
        trans_rows = [str(r.asDict()) for r in trans_df.limit(5).collect()]
        if orig_rows != trans_rows:
            data_match = False
            lines.append("Sample data differs:")
            for i, (o, t) in enumerate(zip(orig_rows, trans_rows)):
                if o != t:
                    lines.append(f"  Row {i}: original={o}")
                    lines.append(f"          transpiled={t}")

    result.diff_report = "\n".join(lines)
    result.passed = result.schema_match and result.row_count_match and data_match and result.error is None
    return result
