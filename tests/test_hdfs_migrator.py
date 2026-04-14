"""Tests for hdfs_migrator module."""
from pathlib import Path
import pytest
from lb_migration_platform_ui.modules.hdfs_migrator import (
    parse_hdfs_listing,
    generate_fs_cp_script,
    generate_dbutils_script,
    generate_unity_catalog_script,
    rewrite_sql_locations,
    HDFSEntry,
)

_REPO_ROOT = Path(__file__).parent.parent
_LISTING_PATH = _REPO_ROOT / "files" / "sample_hdfs" / "hdfs_listing.txt"


@pytest.fixture(scope="module")
def listing_text():
    if not _LISTING_PATH.exists():
        pytest.skip(f"Sample file not found: {_LISTING_PATH}")
    return _LISTING_PATH.read_text()


class TestParseHDFSListing:
    def test_returns_list(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        assert isinstance(entries, list)

    def test_total_entries(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        assert len(entries) == 12  # 12 items total (dirs + files)

    def test_file_count(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        files = [e for e in entries if e.entry_type == "file"]
        assert len(files) == 5

    def test_dir_count(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        dirs = [e for e in entries if e.entry_type == "dir"]
        assert len(dirs) == 7

    def test_entry_paths_start_with_slash(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        for e in entries:
            assert e.path.startswith("/")

    def test_entry_is_hdfs_entry(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        assert all(isinstance(e, HDFSEntry) for e in entries)

    def test_file_path_contains_parquet(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        files = [e for e in entries if e.entry_type == "file"]
        parquet_files = [e for e in files if ".parquet" in e.path]
        assert len(parquet_files) == 3


class TestGenerateFSCPScript:
    def test_contains_databricks_fs_cp(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        script = generate_fs_cp_script(entries, hdfs_host="hdfs://namenode:8020")
        assert "databricks fs cp" in script

    def test_source_contains_hdfs_host(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        script = generate_fs_cp_script(entries, hdfs_host="hdfs://namenode:8020")
        assert "hdfs://namenode:8020" in script

    def test_destination_has_dbfs_prefix(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        script = generate_fs_cp_script(entries, hdfs_host="hdfs://namenode:8020")
        assert "dbfs:/" in script

    def test_files_only_not_dirs(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        script = generate_fs_cp_script(entries, hdfs_host="hdfs://namenode:8020")
        lines = [l for l in script.splitlines() if "databricks fs cp" in l]
        assert len(lines) == 5  # 5 files only


class TestGenerateDbutilsScript:
    def test_dbutils_fs_cp_present(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        script = generate_dbutils_script(entries, hdfs_host="hdfs://namenode:8020")
        assert "dbutils.fs.cp" in script

    def test_file_count_in_script(self, listing_text):
        entries = parse_hdfs_listing(listing_text)
        script = generate_dbutils_script(entries, hdfs_host="hdfs://namenode:8020")
        lines = [l for l in script.splitlines() if "dbutils.fs.cp" in l]
        assert len(lines) == 5


class TestRewriteSQLLocations:
    def test_hdfs_location_to_dbfs(self):
        sql = "CREATE TABLE t LOCATION 'hdfs://namenode:8020/warehouse/retail_db'"
        result = rewrite_sql_locations(sql, target="dbfs")
        assert "hdfs://" not in result
        assert "dbfs:/" in result

    def test_hdfs_location_to_abfss(self):
        sql = "CREATE TABLE t LOCATION 'hdfs:///warehouse/t'"
        result = rewrite_sql_locations(sql, target="abfss", container="data", storage_account="mystorage")
        assert "abfss://" in result
        assert "mystorage" in result

    def test_non_hdfs_location_unchanged(self):
        sql = "CREATE TABLE t LOCATION 's3://bucket/path'"
        result = rewrite_sql_locations(sql, target="dbfs")
        assert "s3://" in result  # unchanged

    def test_case_insensitive(self):
        sql = "CREATE TABLE t location 'hdfs://host/path'"
        result = rewrite_sql_locations(sql, target="dbfs")
        assert "hdfs://" not in result
