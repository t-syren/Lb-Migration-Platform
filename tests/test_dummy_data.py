"""Tests for dummy_data module."""
import re
import pytest
from lb_migration_platform_ui.modules.dummy_data import generate_rows, register_temp_tables


class TestGenerateRows:
    def test_row_count(self):
        schema = {"id": "INT", "name": "STRING"}
        rows = generate_rows(schema, n=10)
        assert len(rows) == 10

    def test_int_column_is_int(self):
        schema = {"id": "INT"}
        rows = generate_rows(schema, n=5)
        assert all(isinstance(r["id"], int) for r in rows)

    def test_string_column_is_str(self):
        schema = {"name": "STRING"}
        rows = generate_rows(schema, n=5)
        assert all(isinstance(r["name"], str) for r in rows)

    def test_double_column_is_float(self):
        schema = {"amount": "DOUBLE"}
        rows = generate_rows(schema, n=5)
        assert all(isinstance(r["amount"], float) for r in rows)

    def test_date_column_is_iso_string(self):
        schema = {"txn_date": "DATE"}
        rows = generate_rows(schema, n=5)
        assert all(isinstance(r["txn_date"], str) for r in rows)
        for r in rows:
            assert re.match(r"\d{4}-\d{2}-\d{2}", r["txn_date"])

    def test_empty_schema_returns_empty_dicts(self):
        rows = generate_rows({}, n=5)
        assert rows == [{} for _ in range(5)]

    def test_boolean_column_is_bool(self):
        schema = {"active": "BOOLEAN"}
        rows = generate_rows(schema, n=5)
        assert all(isinstance(r["active"], bool) for r in rows)

    def test_bigint_column_is_int(self):
        schema = {"large_id": "BIGINT"}
        rows = generate_rows(schema, n=5)
        assert all(isinstance(r["large_id"], int) for r in rows)

    def test_returns_list_of_dicts(self):
        schema = {"id": "INT"}
        rows = generate_rows(schema, n=3)
        assert isinstance(rows, list)
        assert all(isinstance(r, dict) for r in rows)

    def test_float_column_is_float(self):
        schema = {"score": "FLOAT"}
        rows = generate_rows(schema, n=5)
        assert all(isinstance(r["score"], float) for r in rows)

    def test_varchar_column_is_str(self):
        schema = {"code": "VARCHAR"}
        rows = generate_rows(schema, n=5)
        assert all(isinstance(r["code"], str) for r in rows)


class TestRegisterTempTables:
    def test_table_registered(self, spark):
        schema = {"id": "INT", "name": "STRING"}
        register_temp_tables(spark, {"reg_customers": schema}, n=10)
        result = spark.sql("SELECT COUNT(*) as cnt FROM reg_customers").collect()
        assert result[0]["cnt"] == 10

    def test_multiple_tables(self, spark):
        tables = {
            "reg_orders": {"order_id": "INT", "amount": "DOUBLE"},
            "reg_products": {"product_id": "INT", "name": "STRING"},
        }
        register_temp_tables(spark, tables, n=5)
        for table_name in tables:
            count = spark.sql(f"SELECT COUNT(*) as cnt FROM {table_name}").collect()[0]["cnt"]
            assert count == 5

    def test_empty_schema_table_skipped(self, spark):
        # Should not raise — empty schema tables are skipped gracefully
        register_temp_tables(spark, {"empty_tbl": {}}, n=5)
