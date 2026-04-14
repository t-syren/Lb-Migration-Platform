"""Tests for pyspark_migrator module."""
import json
import pytest
from lb_migration_platform_ui.modules.pyspark_migrator import migrate_pyspark_script, migrate_notebook, MigrationResult


class TestHDFSPathReplacement:
    def test_hdfs_with_host_to_dbfs(self):
        code = 'path = "hdfs://namenode:8020/data/customers.csv"'
        result = migrate_pyspark_script(code)
        assert "hdfs://" not in result.transformed_code
        assert "dbfs:/" in result.transformed_code

    def test_hdfs_triple_slash_to_dbfs(self):
        code = 'df = spark.read.parquet("hdfs:///user/data/txns")'
        result = migrate_pyspark_script(code)
        assert "hdfs://" not in result.transformed_code
        assert "dbfs:/" in result.transformed_code

    def test_non_hdfs_path_unchanged(self):
        code = 'df = spark.read.parquet("/local/path/data")'
        result = migrate_pyspark_script(code)
        assert result.transformed_code == code


class TestDeprecatedAPIWarnings:
    def test_sc_textfile_warning(self):
        code = 'rdd = sc.textFile("/data/file.txt")'
        result = migrate_pyspark_script(code)
        assert any("sc.textFile" in w or "RDD" in w for w in result.warnings)

    def test_sparkcontext_warning(self):
        code = "sc = SparkContext(appName='test')"
        result = migrate_pyspark_script(code)
        assert any("SparkContext" in w for w in result.warnings)

    def test_foreachpartition_suggestion(self):
        code = "df.foreachPartition(process_batch)"
        result = migrate_pyspark_script(code)
        assert any("foreachPartition" in w or "applyInPandas" in w for w in result.warnings)

    def test_collect_warning(self):
        code = "all_rows = large_df.collect()"
        result = migrate_pyspark_script(code)
        assert any("collect" in w.lower() for w in result.warnings)

    def test_sparkconf_warning(self):
        code = "conf = SparkConf().setAppName('test')"
        result = migrate_pyspark_script(code)
        assert any("SparkConf" in w for w in result.warnings)


class TestMigrationResult:
    def test_result_type(self):
        result = migrate_pyspark_script("x = 1")
        assert isinstance(result, MigrationResult)

    def test_transformed_code_is_str(self):
        result = migrate_pyspark_script("x = 1")
        assert isinstance(result.transformed_code, str)

    def test_warnings_is_list(self):
        result = migrate_pyspark_script("x = 1")
        assert isinstance(result.warnings, list)

    def test_no_warnings_for_clean_code(self):
        code = "df = spark.read.parquet('/dbfs/data')\ndf.show()"
        result = migrate_pyspark_script(code)
        assert result.warnings == []


class TestMigrateNotebook:
    def test_notebook_code_cells_transformed(self):
        nb = {
            "cells": [
                {"cell_type": "code", "source": ['path = "hdfs:///data/file"']},
                {"cell_type": "markdown", "source": ["# Title"]},
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        result = migrate_notebook(json.dumps(nb))
        parsed = json.loads(result.transformed_code)
        code_cell = parsed["cells"][0]["source"]
        assert "hdfs://" not in code_cell

    def test_notebook_markdown_unchanged(self):
        nb = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title with hdfs://host/path"]},
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        result = migrate_notebook(json.dumps(nb))
        parsed = json.loads(result.transformed_code)
        assert "hdfs://" in parsed["cells"][0]["source"]
