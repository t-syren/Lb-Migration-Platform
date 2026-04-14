"""Dummy dataset generation for SQL transpilation testing."""
import logging
import random
from datetime import date, timedelta
from decimal import Decimal as PyDecimal
from typing import Any, Dict, List

from faker import Faker
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    BooleanType,
    BinaryType,
    DateType,
    DoubleType,
    FloatType,
    IntegerType,
    LongType,
    ShortType,
    StringType,
    StructField,
    StructType,
    TimestampType,
    DecimalType,
    ByteType,
)

logger = logging.getLogger(__name__)

_faker = Faker()
Faker.seed(42)
random.seed(42)

_TYPE_GENERATORS = {
    "INT": lambda: random.randint(1, 100_000),
    "BIGINT": lambda: random.randint(1, 10_000_000),
    "SMALLINT": lambda: random.randint(1, 1_000),
    "TINYINT": lambda: random.randint(0, 127),
    "FLOAT": lambda: round(random.uniform(0.0, 10_000.0), 4),
    "DOUBLE": lambda: round(random.uniform(0.0, 100_000.0), 6),
    "DECIMAL": lambda: PyDecimal(str(round(random.uniform(0.0, 99_999.99), 2))),
    "STRING": lambda: _faker.word(),
    "VARCHAR": lambda: _faker.word(),
    "CHAR": lambda: _faker.lexify("?"),
    "BOOLEAN": lambda: random.choice([True, False]),
    "DATE": lambda: (date(2020, 1, 1) + timedelta(days=random.randint(0, 1460))).isoformat(),
    "TIMESTAMP": lambda: _faker.date_time_between(start_date="-3y", end_date="now").isoformat(sep=" "),
    "BINARY": lambda: b"\x00",
}
_DEFAULT_GEN = lambda: _faker.word()  # noqa: E731

# Mapping from Hive base type to PySpark SQL type for explicit schema inference
_HIVE_TO_SPARK_TYPE = {
    "INT": IntegerType(),
    "BIGINT": LongType(),
    "SMALLINT": ShortType(),
    "TINYINT": ByteType(),
    "FLOAT": FloatType(),
    "DOUBLE": DoubleType(),
    "DECIMAL": DecimalType(18, 2),
    "STRING": StringType(),
    "VARCHAR": StringType(),
    "CHAR": StringType(),
    "BOOLEAN": BooleanType(),
    "DATE": StringType(),       # dates are stored as ISO strings
    "TIMESTAMP": StringType(),  # timestamps stored as ISO strings
    "BINARY": BinaryType(),
}


def _gen_value(hive_type: str) -> Any:
    base_type = hive_type.split("(")[0].upper()  # strip DECIMAL(10,2) -> DECIMAL
    gen = _TYPE_GENERATORS.get(base_type)
    if gen is None:
        logger.warning("Unknown Hive type '%s', falling back to STRING", hive_type)
        return _DEFAULT_GEN()
    return gen()


def _build_spark_schema(schema: Dict[str, str]) -> StructType:
    """Build an explicit PySpark StructType from a Hive-type schema dict."""
    fields = []
    for col_name, hive_type in schema.items():
        base_type = hive_type.split("(")[0].upper()
        spark_type = _HIVE_TO_SPARK_TYPE.get(base_type, StringType())
        fields.append(StructField(col_name, spark_type, nullable=True))
    return StructType(fields)


def generate_rows(schema: Dict[str, str], n: int = 100) -> List[Dict[str, Any]]:
    """Generate n synthetic rows for the given {col_name: hive_type} schema."""
    return [
        {col: _gen_value(hive_type) for col, hive_type in schema.items()}
        for _ in range(n)
    ]


def register_temp_tables(
    spark: SparkSession,
    tables: Dict[str, Dict[str, str]],
    n: int = 100,
) -> None:
    """Generate dummy data and register each table as a Spark temporary view.

    Args:
        spark: Active SparkSession (local mode).
        tables: {table_name: {col_name: hive_type}}.
        n: Number of rows per table.
    """
    for table_name, schema in tables.items():
        if not schema:
            continue
        rows = generate_rows(schema, n=n)
        spark_schema = _build_spark_schema(schema)
        df = spark.createDataFrame(rows, schema=spark_schema)
        df.createOrReplaceTempView(table_name)
