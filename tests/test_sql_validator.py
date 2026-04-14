"""Tests for sql_validator module."""
import pytest
from lb_migration_platform_ui.modules.sql_validator import validate_transpilation, ValidationResult


class TestValidateTranspilation:
    def test_identical_sql_passes(self, spark):
        spark.createDataFrame([(1, "a"), (2, "b")], ["id", "name"]).createOrReplaceTempView("val_tbl1")
        result = validate_transpilation(spark, "SELECT * FROM val_tbl1", "SELECT * FROM val_tbl1")
        assert result.passed is True
        assert result.row_count_match is True
        assert result.schema_match is True

    def test_different_row_count_fails(self, spark):
        spark.createDataFrame([(1,), (2,), (3,)], ["id"]).createOrReplaceTempView("val_tbl2")
        result = validate_transpilation(
            spark,
            "SELECT * FROM val_tbl2",
            "SELECT * FROM val_tbl2 WHERE id < 3",
        )
        assert result.row_count_match is False
        assert result.passed is False

    def test_schema_mismatch_detected(self, spark):
        spark.createDataFrame([(1, "a")], ["id", "name"]).createOrReplaceTempView("val_tbl3")
        result = validate_transpilation(
            spark,
            "SELECT id, name FROM val_tbl3",
            "SELECT id FROM val_tbl3",  # missing column
        )
        assert result.schema_match is False
        assert result.passed is False

    def test_invalid_transpiled_sql_returns_error(self, spark):
        result = validate_transpilation(spark, "SELECT 1", "THIS IS NOT SQL !!!")
        assert result.passed is False
        assert result.error is not None

    def test_result_has_diff_report(self, spark):
        spark.createDataFrame([(1,)], ["id"]).createOrReplaceTempView("val_tbl4")
        result = validate_transpilation(spark, "SELECT * FROM val_tbl4", "SELECT * FROM val_tbl4")
        assert result.diff_report is not None
        assert isinstance(result.diff_report, str)

    def test_original_and_transpiled_counts_in_result(self, spark):
        spark.createDataFrame([(1,), (2,)], ["id"]).createOrReplaceTempView("val_tbl5")
        result = validate_transpilation(spark, "SELECT * FROM val_tbl5", "SELECT * FROM val_tbl5")
        assert result.original_count == 2
        assert result.transpiled_count == 2

    def test_column_names_in_result(self, spark):
        spark.createDataFrame([(1, "a")], ["id", "name"]).createOrReplaceTempView("val_tbl6")
        result = validate_transpilation(spark, "SELECT * FROM val_tbl6", "SELECT * FROM val_tbl6")
        assert "id" in result.original_columns
        assert "name" in result.original_columns
