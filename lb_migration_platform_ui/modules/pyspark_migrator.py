"""PySpark script migration: path rewrites, deprecated API warnings, best-practice hints."""
import copy
import json
import re
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    transformed_code: str = ""
    warnings: List[str] = field(default_factory=list)


# Regex substitution rules: (pattern, replacement)
_TRANSFORMATIONS = [
    # hdfs:///path → dbfs:/path  (triple-slash must come BEFORE generic host pattern)
    (r'hdfs:///([^"\']+)', r"dbfs:/\1"),
    # hdfs://host:port/path → dbfs:/path
    (r'hdfs://[^/\s"\'\)]*(/[^"\']+)', r"dbfs:\1"),
]

# Warning-only patterns: (pattern, message)
_WARNINGS = [
    (
        r"\bsc\.textFile\s*\(",
        "RDD API detected: sc.textFile() → consider spark.read.text() or spark.read.csv()",
    ),
    (
        r"\bSparkContext\s*\(",
        "SparkContext() is managed by Databricks — remove explicit SparkContext initialization",
    ),
    (
        r"\bforeachPartition\s*\(",
        "foreachPartition() detected — consider applyInPandas() for vectorized partition processing",
    ),
    (
        r"\b\.collect\s*\(\s*\)",
        "collect() detected — avoid on large DataFrames; use .limit(n).collect() or write to Delta",
    ),
    (
        r"\bSparkConf\s*\(",
        "SparkConf() — cluster config belongs in cluster settings; use spark.conf.set() instead",
    ),
    (
        r"\.repartition\s*\(\s*\d{3,}",
        "High repartition count detected — validate against cluster size",
    ),
]


def migrate_pyspark_script(code: str) -> MigrationResult:
    """Apply migration transformations to a PySpark script string."""
    warnings: List[str] = []
    transformed = code

    for pattern, replacement in _TRANSFORMATIONS:
        transformed = re.sub(pattern, replacement, transformed)

    for pattern, message in _WARNINGS:
        if re.search(pattern, transformed):
            warnings.append(message)

    return MigrationResult(transformed_code=transformed, warnings=warnings)


def migrate_notebook(ipynb_json: str) -> MigrationResult:
    """Migrate all code cells in a Jupyter notebook JSON string."""
    try:
        nb = copy.deepcopy(json.loads(ipynb_json))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid notebook JSON: {exc}") from exc
    all_warnings: List[str] = []

    for cell in nb.get("cells", []):
        source = cell["source"]
        # Normalise source: list of strings → single string
        if isinstance(source, list):
            source_str = "".join(source)
        else:
            source_str = source

        if cell.get("cell_type") == "code":
            result = migrate_pyspark_script(source_str)
            cell["source"] = result.transformed_code
            all_warnings.extend(result.warnings)
        else:
            # Non-code cells are left semantically unchanged but normalised to string
            cell["source"] = source_str

    return MigrationResult(
        transformed_code=json.dumps(nb, indent=2),
        warnings=list(dict.fromkeys(all_warnings)),  # deduplicate, preserve order
    )
