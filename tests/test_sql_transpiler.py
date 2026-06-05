"""Tests for sql_transpiler module.

conftest.py puts lb_migration_platform_ui/ on sys.path so that
`from modules.xxx import` resolves the same way it does at app runtime.
"""
import os
import pytest
from unittest.mock import MagicMock, patch
from modules.sql_transpiler import (
    transpile_hive_sql,
    infer_schema,
    split_sql_statements,
    handle_hive_variables,
    create_table_handler,
    run_hive_transpiler,
)


# ══════════════════════════════════════════════════════════════════════════════
# transpile_hive_sql — clause stripping and basic conversion
# ══════════════════════════════════════════════════════════════════════════════

class TestTranspileHiveSQL:
    def test_stored_as_textfile_removed(self):
        result = transpile_hive_sql("CREATE TABLE t (id INT) STORED AS TEXTFILE")
        assert "STORED AS TEXTFILE" not in result
        assert "CREATE TABLE" in result

    def test_row_format_delimited_removed(self):
        result = transpile_hive_sql(
            "CREATE TABLE t (id INT) ROW FORMAT DELIMITED FIELDS TERMINATED BY ','"
        )
        assert "ROW FORMAT" not in result

    def test_partitioned_by_preserved(self):
        result = transpile_hive_sql(
            "CREATE TABLE txns (id INT, amt DOUBLE) PARTITIONED BY (dt STRING)"
        )
        assert "PARTITIONED BY" in result

    def test_insert_not_stripped(self):
        result = transpile_hive_sql("INSERT OVERWRITE TABLE t SELECT id FROM src")
        assert "INSERT" in result

    def test_multiple_statements(self):
        result = transpile_hive_sql("USE db;\nCREATE TABLE t (id INT);")
        assert len(result.strip()) > 0

    def test_returns_string(self):
        assert isinstance(transpile_hive_sql("SELECT 1"), str)

    def test_simple_select_passes_through(self):
        result = transpile_hive_sql("SELECT id, name FROM customers WHERE age > 30")
        assert "SELECT" in result and "FROM" in result

    def test_stored_as_orc_removed(self):
        result = transpile_hive_sql("CREATE TABLE t (id INT) STORED AS ORC")
        assert "STORED AS ORC" not in result

    def test_tblproperties_removed(self):
        result = transpile_hive_sql(
            "CREATE TABLE t (id INT) TBLPROPERTIES ('transactional'='true')"
        )
        assert "TBLPROPERTIES" not in result

    def test_hdfs_location_preserved_for_manual_rewrite(self):
        # The transpiler intentionally keeps LOCATION (including hdfs:// paths)
        # so engineers can manually rewrite to dbfs:/ or abfss://.
        # USING DELTA is added; the LOCATION clause itself is kept.
        result = transpile_hive_sql(
            "CREATE TABLE t (id INT) LOCATION 'hdfs://namenode:8020/warehouse/t'"
        )
        assert "USING DELTA" in result.upper()
        assert "LOCATION" in result.upper()

    def test_row_format_serde_removed(self):
        result = transpile_hive_sql(
            "CREATE TABLE t (id INT) ROW FORMAT SERDE "
            "'org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe'"
        )
        assert "ROW FORMAT" not in result

    def test_using_delta_added(self):
        result = transpile_hive_sql("CREATE TABLE t (id INT, name STRING)")
        assert "USING DELTA" in result.upper()

    def test_nvl_rewritten(self):
        result = transpile_hive_sql("SELECT NVL(col, 0) FROM t")
        assert "NVL" not in result.upper()
        assert "COALESCE" in result.upper()

    def test_ctas_with_complex_nested_types(self):
        """Balanced-paren scanner must not corrupt CTAS with MAP<STRING,ARRAY<INT>>."""
        sql = (
            "CREATE TABLE t (id INT, meta MAP<STRING,ARRAY<INT>>) "
            "AS SELECT id, map() AS meta FROM src"
        )
        result = transpile_hive_sql(sql)
        assert "SELECT" in result.upper()
        assert "USING DELTA" in result.upper()


# ══════════════════════════════════════════════════════════════════════════════
# infer_schema
# ══════════════════════════════════════════════════════════════════════════════

class TestInferSchema:
    def test_int_column(self):
        schema = infer_schema("CREATE TABLE customers (cust_id INT, name STRING)")
        assert schema.get("cust_id") == "INT"

    def test_string_columns(self):
        schema = infer_schema("CREATE TABLE t (name STRING, city STRING)")
        assert schema["name"] == "STRING"
        assert schema["city"] == "STRING"

    def test_double_column(self):
        assert infer_schema("CREATE TABLE t (amount DOUBLE)").get("amount") == "DOUBLE"

    def test_partitioned_columns_excluded(self):
        schema = infer_schema(
            "CREATE TABLE t (id INT, amt DOUBLE) PARTITIONED BY (dt STRING)"
        )
        assert "dt" not in schema
        assert "id" in schema

    def test_non_create_returns_empty(self):
        assert infer_schema("SELECT 1") == {}

    def test_if_not_exists(self):
        schema = infer_schema(
            "CREATE TABLE IF NOT EXISTS customers (cust_id INT, name STRING)"
        )
        assert "cust_id" in schema

    def test_multiple_columns(self):
        schema = infer_schema("CREATE TABLE t (a INT, b STRING, c DOUBLE, d BIGINT)")
        assert len(schema) == 4

    def test_external_table(self):
        schema = infer_schema(
            "CREATE EXTERNAL TABLE t (id INT) LOCATION 'hdfs://h/t'"
        )
        assert "id" in schema


# ══════════════════════════════════════════════════════════════════════════════
# split_sql_statements
# ══════════════════════════════════════════════════════════════════════════════

class TestSplitSqlStatements:
    def test_single_statement(self):
        assert len(split_sql_statements("SELECT 1")) == 1

    def test_semicolon_delimited(self):
        assert len(split_sql_statements("SELECT 1; SELECT 2; SELECT 3")) == 3

    def test_comment_not_split(self):
        assert len(split_sql_statements("-- comment\nSELECT 1")) == 1

    def test_string_semicolon_not_split(self):
        assert len(split_sql_statements("SELECT 'a;b' FROM t")) == 1

    def test_empty_input(self):
        assert split_sql_statements("") == []


# ══════════════════════════════════════════════════════════════════════════════
# handle_hive_variables
# ══════════════════════════════════════════════════════════════════════════════

class TestHandleHiveVariables:
    def test_user_var_extracted(self):
        _, decls = handle_hive_variables("SET myvar=hello;\nSELECT ${myvar} FROM t")
        assert any("myvar" in d for d in decls)

    def test_engine_config_not_in_declarations(self):
        _, decls = handle_hive_variables(
            "SET spark.sql.shuffle.partitions=200;\nSELECT 1"
        )
        assert not any("spark.sql" in d for d in decls)

    def test_returns_tuple_of_two(self):
        result = handle_hive_variables("SELECT 1")
        assert isinstance(result, tuple) and len(result) == 2


# ══════════════════════════════════════════════════════════════════════════════
# create_table_handler
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTableHandler:
    def test_external_becomes_table(self):
        result = create_table_handler(
            "CREATE EXTERNAL TABLE t (id INT) LOCATION 'hdfs://h/t'",
            location="hdfs://h/t",
        )
        assert "EXTERNAL" not in result

    def test_using_delta_added(self):
        result = create_table_handler("CREATE TABLE t (id INT, name STRING)")
        assert "USING DELTA" in result.upper()

    def test_non_create_unchanged(self):
        stmt = "SELECT 1 FROM t"
        assert create_table_handler(stmt) == stmt

    def test_ctas_removes_schema_block(self):
        result = create_table_handler("CREATE TABLE t (id INT) AS SELECT id FROM src")
        assert "USING DELTA" in result.upper()
        assert "(id INT)" not in result

    def test_ctas_nested_types_not_corrupted(self):
        stmt = (
            "CREATE TABLE t (id INT, tags MAP<STRING, ARRAY<STRING>>) "
            "AS SELECT id, map() AS tags FROM src"
        )
        result = create_table_handler(stmt)
        assert "SELECT" in result.upper()
        assert "USING DELTA" in result.upper()


# ══════════════════════════════════════════════════════════════════════════════
# LLM Stage 3 — mocked tests  (fix #5)
# ══════════════════════════════════════════════════════════════════════════════

def _write_hql(tmp_path, sql: str):
    src_dir = tmp_path / "src"
    out_dir = tmp_path / "out"
    src_dir.mkdir()
    out_dir.mkdir()
    (src_dir / "input.hql").write_text(sql, encoding="utf-8")
    err_file = str(tmp_path / "errors.log")
    return str(src_dir), str(out_dir), err_file


class TestLLMStage:
    @patch("modules.sql_transpiler.LLMConverter")
    def test_llm_not_called_when_no_issues(self, MockLLM, tmp_path):
        """Clean SQL → LLM instance created but code_convert_llm never invoked."""
        src_dir, out_dir, err_file = _write_hql(tmp_path, "SELECT id FROM t")
        run_hive_transpiler(
            src_dir, out_dir, err_file, "SPARKSQL",
            llm_endpoint="http://fake", llm_api_key="tok",
        )
        MockLLM.return_value.code_convert_llm.assert_not_called()

    @patch("modules.sql_transpiler.LLMConverter")
    def test_llm_called_for_blocker(self, MockLLM, tmp_path):
        """Per-statement BLOCKER (LOAD DATA) triggers LLM call.

        Note: ADD JAR is a *global* issue (GLOBAL statement, idx=None) and is
        intentionally excluded from per-statement LLM processing.  LOAD DATA
        is a per-statement BLOCKER and does flow through the LLM path.
        """
        mock_instance = MagicMock()
        mock_instance.code_convert_llm.return_value = (
            "-- STATEMENT_ID: 0\nINSERT INTO t SELECT * FROM src  -- llm fixed"
        )
        MockLLM.return_value = mock_instance

        # LOAD DATA creates a per-statement BLOCKER → problem_indexes is non-empty
        sql = "LOAD DATA INPATH '/hdfs/data' INTO TABLE t;\nSELECT id FROM t"
        src_dir, out_dir, err_file = _write_hql(tmp_path, sql)
        run_hive_transpiler(
            src_dir, out_dir, err_file, "SPARKSQL",
            llm_endpoint="http://fake", llm_api_key="tok",
        )
        MockLLM.assert_called_once_with(api_key="tok", endpoint="http://fake")
        mock_instance.code_convert_llm.assert_called()

    @patch("modules.sql_transpiler.LLMConverter")
    def test_llm_exception_falls_back_to_rule_based(self, MockLLM, tmp_path):
        """LLM raising an exception must not crash transpilation."""
        MockLLM.return_value.code_convert_llm.side_effect = Exception("API down")

        src_dir, out_dir, err_file = _write_hql(
            tmp_path, "ADD JAR /path.jar;\nSELECT id FROM t"
        )
        ok, stdout, stderr = run_hive_transpiler(
            src_dir, out_dir, err_file, "SPARKSQL",
            llm_endpoint="http://fake", llm_api_key="tok",
        )
        output_files = [f for f in os.listdir(out_dir) if not f.endswith(".log")]
        assert len(output_files) >= 1, "output file should still be written on LLM failure"

    @patch("modules.sql_transpiler.LLMConverter")
    def test_insert_safety_guard_rejects_llm_output(self, MockLLM, tmp_path):
        """LLM output that drops INSERT is rejected; original INSERT preserved."""
        MockLLM.return_value.code_convert_llm.return_value = (
            "SELECT id FROM t  -- llm accidentally dropped INSERT"
        )
        src_dir, out_dir, err_file = _write_hql(
            tmp_path, "INSERT OVERWRITE TABLE dst SELECT id FROM src"
        )
        run_hive_transpiler(
            src_dir, out_dir, err_file, "SPARKSQL",
            llm_endpoint="http://fake", llm_api_key="tok",
        )
        for fname in os.listdir(out_dir):
            fpath = os.path.join(out_dir, fname)
            if os.path.isfile(fpath) and not fname.endswith(".log"):
                assert "INSERT" in open(fpath).read().upper()
