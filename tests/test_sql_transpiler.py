"""Tests for sql_transpiler module."""
import pytest
from lb_migration_platform_ui.modules.sql_transpiler import transpile_hive_sql, infer_schema


class TestTranspileHiveSQL:
    def test_stored_as_textfile_removed(self):
        sql = "CREATE TABLE t (id INT) STORED AS TEXTFILE"
        result = transpile_hive_sql(sql)
        assert "STORED AS TEXTFILE" not in result
        assert "CREATE TABLE" in result

    def test_row_format_delimited_removed(self):
        sql = "CREATE TABLE t (id INT) ROW FORMAT DELIMITED FIELDS TERMINATED BY ','"
        result = transpile_hive_sql(sql)
        assert "ROW FORMAT" not in result

    def test_partitioned_by_preserved(self):
        sql = "CREATE TABLE txns (id INT, amt DOUBLE) PARTITIONED BY (dt STRING)"
        result = transpile_hive_sql(sql)
        assert "PARTITIONED BY" in result

    def test_insert_statement_not_stripped(self):
        sql = "INSERT OVERWRITE TABLE t SELECT id FROM src"
        result = transpile_hive_sql(sql)
        assert "INSERT" in result

    def test_multiple_statements(self):
        sql = "USE db;\nCREATE TABLE t (id INT);"
        result = transpile_hive_sql(sql)
        assert len(result.strip()) > 0

    def test_returns_string(self):
        result = transpile_hive_sql("SELECT 1")
        assert isinstance(result, str)

    def test_simple_select_passes_through(self):
        result = transpile_hive_sql("SELECT id, name FROM customers WHERE age > 30")
        assert "SELECT" in result
        assert "FROM" in result

    def test_stored_as_orc_removed(self):
        sql = "CREATE TABLE t (id INT) STORED AS ORC"
        result = transpile_hive_sql(sql)
        assert "STORED AS ORC" not in result

    def test_tblproperties_removed(self):
        sql = "CREATE TABLE t (id INT) TBLPROPERTIES ('transactional'='true')"
        result = transpile_hive_sql(sql)
        assert "TBLPROPERTIES" not in result

    def test_hdfs_location_removed(self):
        sql = "CREATE TABLE t (id INT) LOCATION 'hdfs://namenode:8020/warehouse/t'"
        result = transpile_hive_sql(sql)
        assert "hdfs://" not in result

    def test_row_format_serde_removed(self):
        sql = "CREATE TABLE t (id INT) ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe'"
        result = transpile_hive_sql(sql)
        assert "ROW FORMAT" not in result


class TestInferSchema:
    def test_infer_int_column(self):
        sql = "CREATE TABLE customers (cust_id INT, name STRING)"
        schema = infer_schema(sql)
        assert "cust_id" in schema
        assert schema["cust_id"] == "INT"

    def test_infer_string_column(self):
        sql = "CREATE TABLE t (name STRING, city STRING)"
        schema = infer_schema(sql)
        assert schema["name"] == "STRING"
        assert schema["city"] == "STRING"

    def test_infer_double_column(self):
        sql = "CREATE TABLE t (amount DOUBLE)"
        schema = infer_schema(sql)
        assert schema["amount"] == "DOUBLE"

    def test_partitioned_columns_excluded(self):
        sql = "CREATE TABLE t (id INT, amt DOUBLE) PARTITIONED BY (dt STRING)"
        schema = infer_schema(sql)
        assert "dt" not in schema

    def test_no_table_returns_empty(self):
        schema = infer_schema("SELECT 1")
        assert schema == {}

    def test_if_not_exists_handled(self):
        sql = "CREATE TABLE IF NOT EXISTS customers (cust_id INT, name STRING)"
        schema = infer_schema(sql)
        assert "cust_id" in schema

    def test_multiple_columns(self):
        sql = "CREATE TABLE t (a INT, b STRING, c DOUBLE, d BIGINT)"
        schema = infer_schema(sql)
        assert len(schema) == 4
