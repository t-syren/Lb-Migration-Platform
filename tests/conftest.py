"""Shared pytest fixtures for SyrenBridge test suite (session-scoped SparkSession)."""
import os
import pytest
from pyspark.sql import SparkSession

# Ensure JAVA_HOME is set for macOS Homebrew openjdk (keg-only, not in PATH by default)
if not os.environ.get("JAVA_HOME"):
    _homebrew_jdk = "/opt/homebrew/opt/openjdk"
    if os.path.isdir(_homebrew_jdk):
        os.environ["JAVA_HOME"] = _homebrew_jdk

@pytest.fixture(scope="session")
def spark():
    session = (
        SparkSession.builder
        .master("local[1]")
        .appName("SyrenBridge-Tests")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()
