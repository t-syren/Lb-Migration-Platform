"""Tests for oozie_converter module."""
import json
from pathlib import Path

import pytest
from lb_migration_platform_ui.modules.oozie_converter import (
    parse_workflow,
    to_databricks_job,
    workflow_to_json,
    OozieAction,
)

_REPO_ROOT = Path(__file__).parent.parent  # Lb-Migration-Platform/
WORKFLOW_XML = (_REPO_ROOT / "files" / "sample_oozie" / "workflow.xml").read_text(encoding="utf-8")


class TestParseWorkflow:
    def test_returns_list(self):
        actions = parse_workflow(WORKFLOW_XML)
        assert isinstance(actions, list)

    def test_action_count(self):
        actions = parse_workflow(WORKFLOW_XML)
        assert len(actions) == 4  # ingest-customers, ingest-transactions, transform-spark, export-report

    def test_hive_action_names(self):
        actions = parse_workflow(WORKFLOW_XML)
        names = {a.name for a in actions}
        assert "ingest-customers" in names
        assert "ingest-transactions" in names

    def test_spark_action_present(self):
        actions = parse_workflow(WORKFLOW_XML)
        spark_actions = [a for a in actions if a.action_type == "spark"]
        assert len(spark_actions) == 1
        assert spark_actions[0].name == "transform-spark"

    def test_shell_action_present(self):
        actions = parse_workflow(WORKFLOW_XML)
        shell_actions = [a for a in actions if a.action_type == "shell"]
        assert len(shell_actions) == 1
        assert shell_actions[0].name == "export-report"

    def test_hive_action_count(self):
        actions = parse_workflow(WORKFLOW_XML)
        hive_actions = [a for a in actions if a.action_type == "hive"]
        assert len(hive_actions) == 2

    def test_ok_to_edge(self):
        actions = parse_workflow(WORKFLOW_XML)
        action_map = {a.name: a for a in actions}
        assert action_map["ingest-customers"].ok_to == "ingest-transactions"

    def test_error_to_edge(self):
        actions = parse_workflow(WORKFLOW_XML)
        action_map = {a.name: a for a in actions}
        assert action_map["ingest-customers"].error_to == "fail"

    def test_kill_and_end_not_in_actions(self):
        actions = parse_workflow(WORKFLOW_XML)
        names = {a.name for a in actions}
        assert "fail" not in names
        assert "end" not in names

    def test_oozie_action_dataclass(self):
        actions = parse_workflow(WORKFLOW_XML)
        assert all(isinstance(a, OozieAction) for a in actions)


class TestToDatabricksJob:
    def setup_method(self):
        self.actions = parse_workflow(WORKFLOW_XML)

    def test_returns_dict(self):
        job = to_databricks_job(self.actions, job_name="retail-etl")
        assert isinstance(job, dict)

    def test_job_name(self):
        job = to_databricks_job(self.actions, job_name="retail-etl")
        assert job["name"] == "retail-etl"

    def test_tasks_list_length(self):
        job = to_databricks_job(self.actions, job_name="retail-etl")
        assert len(job["tasks"]) == 4

    def test_task_keys_present(self):
        job = to_databricks_job(self.actions, job_name="retail-etl")
        for task in job["tasks"]:
            assert "task_key" in task

    def test_dependency_captured(self):
        job = to_databricks_job(self.actions, job_name="retail-etl")
        task_map = {t["task_key"]: t for t in job["tasks"]}
        deps = [d["task_key"] for d in task_map["ingest-transactions"].get("depends_on", [])]
        assert "ingest-customers" in deps


class TestWorkflowToJson:
    def test_returns_valid_json(self):
        result = workflow_to_json(WORKFLOW_XML, job_name="retail-etl")
        parsed = json.loads(result)
        assert "tasks" in parsed
        assert len(parsed["tasks"]) == 4
