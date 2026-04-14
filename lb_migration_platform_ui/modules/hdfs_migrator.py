"""Generate HDFS → DBFS / Unity Catalog migration scripts."""
import re
import logging
from dataclasses import dataclass
from typing import List, Literal

logger = logging.getLogger(__name__)

_LS_LINE = re.compile(
    r"^([-d])[rwx-]{9}\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(.+)$"
)


@dataclass
class HDFSEntry:
    entry_type: str   # "file" or "dir"
    path: str


def parse_hdfs_listing(text: str) -> List[HDFSEntry]:
    """Parse `hdfs dfs -ls -R /` output into HDFSEntry list."""
    entries: List[HDFSEntry] = []
    for line in text.splitlines():
        line = line.strip()
        m = _LS_LINE.match(line)
        if not m:
            continue
        type_char, path = m.group(1), m.group(2).strip()
        entries.append(HDFSEntry(
            entry_type="dir" if type_char == "d" else "file",
            path=path,
        ))
    return entries


def _to_dbfs_path(hdfs_path: str, hdfs_host: str) -> str:
    """Convert an absolute HDFS path to dbfs:/ equivalent."""
    path = hdfs_path
    if hdfs_host and path.startswith(hdfs_host):
        path = path[len(hdfs_host):]
    if not path.startswith("dbfs:"):
        path = "dbfs:" + path
    return path


def generate_fs_cp_script(
    entries: List[HDFSEntry],
    hdfs_host: str = "hdfs://namenode:8020",
) -> str:
    """Generate shell script using `databricks fs cp` for each file."""
    lines = ["#!/bin/bash", "# Auto-generated HDFS → DBFS migration script", "set -e", ""]
    for entry in entries:
        if entry.entry_type != "file":
            continue
        src = f"{hdfs_host}{entry.path}"
        dst = _to_dbfs_path(entry.path, "")
        lines.append(f'databricks fs cp "{src}" "{dst}"')
    return "\n".join(lines)


def generate_dbutils_script(
    entries: List[HDFSEntry],
    hdfs_host: str = "hdfs://namenode:8020",
) -> str:
    """Generate Python notebook cells using dbutils.fs.cp."""
    lines = [
        "# Auto-generated HDFS → DBFS migration — run in a Databricks notebook",
        "",
    ]
    for entry in entries:
        if entry.entry_type != "file":
            continue
        src = f"{hdfs_host}{entry.path}"
        dst = _to_dbfs_path(entry.path, "")
        lines.append(f'dbutils.fs.cp("{src}", "{dst}")')
    return "\n".join(lines)


def generate_unity_catalog_script(
    entries: List[HDFSEntry],
    catalog: str = "main",
    schema: str = "migrations",
    container: str = "data",
    storage_account: str = "mystorageaccount",
) -> str:
    """Generate Unity Catalog CREATE VOLUME + abfss:// path statements."""
    abfss_base = f"abfss://{container}@{storage_account}.dfs.core.windows.net"
    lines = [
        f"-- Auto-generated Unity Catalog migration script",
        f"-- Target: {abfss_base}",
        "",
        f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema};",
        "",
    ]
    dirs_seen: set = set()
    for entry in entries:
        parent = "/".join(entry.path.rsplit("/", 1)[:1])
        if parent and parent not in dirs_seen:
            volume_name = parent.strip("/").replace("/", "_")
            lines.append(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume_name}")
            lines.append(f"  LOCATION '{abfss_base}{parent}';")
            lines.append("")
            dirs_seen.add(parent)
    return "\n".join(lines)


def rewrite_sql_locations(
    sql: str,
    target: Literal["dbfs", "abfss"] = "dbfs",
    container: str = "data",
    storage_account: str = "mystorageaccount",
) -> str:
    """Rewrite LOCATION 'hdfs://...' clauses in SQL DDL statements."""
    def _replace(m: re.Match) -> str:
        hdfs_path = re.sub(r"hdfs://[^/]*", "", m.group(1))
        if target == "abfss":
            new_path = (
                f"abfss://{container}@{storage_account}.dfs.core.windows.net{hdfs_path}"
            )
        else:
            new_path = f"dbfs:{hdfs_path}"
        return f"LOCATION '{new_path}'"

    return re.sub(r"LOCATION\s+'(hdfs://[^']+)'", _replace, sql, flags=re.IGNORECASE)
