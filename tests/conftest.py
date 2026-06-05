"""Shared pytest fixtures for SyrenBridge test suite (session-scoped SparkSession)."""
import os
import sys
from pathlib import Path
import pytest
from pyspark.sql import SparkSession

# Put lb_migration_platform_ui/ on sys.path so that `from modules.xxx import`
# resolves the same way it does at runtime (app.py does sys.path.insert too).
_UI_ROOT = str(Path(__file__).parent.parent / "lb_migration_platform_ui")
if _UI_ROOT not in sys.path:
    sys.path.insert(0, _UI_ROOT)

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
