"""Tests for oozie_converter module."""
import json
from pathlib import Path

import pytest
from lb_migration_platform_ui.modules.oozie_converter import (
    OozieAction,
    OozieDecision,
    OozieKill,
    WorkflowGraph,
    parse_workflow,
    workflow_to_dict,
    workflow_to_json,
)

_REPO_ROOT = Path(__file__).parent.parent
WORKFLOW_XML = (_REPO_ROOT / "files" / "sample_oozie" / "workflow.xml").read_text(
    encoding="utf-8"
)


# ── Helper XML builders ───────────────────────────────────────────────────────

def _fork_join_xml(job_name: str = "fork-test") -> str:
    return f"""<?xml version="1.0"?>
<workflow-app name="{job_name}" xmlns="uri:oozie:workflow:0.5">
  <start to="a1"/>
  <action name="a1"><hive xmlns="uri:oozie:hive-action:0.2">
    <script>a1.hql</script></hive>
    <ok to="fork1"/><error to="fail"/>
  </action>
  <fork name="fork1">
    <path start="b1"/><path start="b2"/>
  </fork>
  <action name="b1"><hive xmlns="uri:oozie:hive-action:0.2">
    <script>b1.hql</script></hive>
    <ok to="join1"/><error to="fail"/>
  </action>
  <action name="b2"><hive xmlns="uri:oozie:hive-action:0.2">
    <script>b2.hql</script></hive>
    <ok to="join1"/><error to="fail"/>
  </action>
  <join name="join1" to="a2"/>
  <action name="a2"><hive xmlns="uri:oozie:hive-action:0.2">
    <script>a2.hql</script></hive>
    <ok to="end"/><error to="fail"/>
  </action>
  <kill name="fail"><message>failed</message></kill>
  <end name="end"/>
</workflow-app>"""


def _decision_xml() -> str:
    return """<?xml version="1.0"?>
<workflow-app name="decision-test" xmlns="uri:oozie:workflow:0.5">
  <start to="a1"/>
  <action name="a1"><hive xmlns="uri:oozie:hive-action:0.2">
    <script>a1.hql</script></hive>
    <ok to="decide1"/><error to="fail"/>
  </action>
  <decision name="decide1">
    <switch>
      <case to="b1">${cond1}</case>
      <case to="b2">${cond2}</case>
      <default to="b3"/>
    </switch>
  </decision>
  <action name="b1"><hive xmlns="uri:oozie:hive-action:0.2">
    <script>b1.hql</script></hive>
    <ok to="end"/><error to="fail"/>
  </action>
  <action name="b2"><hive xmlns="uri:oozie:hive-action:0.2">
    <script>b2.hql</script></hive>
    <ok to="end"/><error to="fail"/>
  </action>
  <action name="b3"><hive xmlns="uri:oozie:hive-action:0.2">
    <script>b3.hql</script></hive>
    <ok to="end"/><error to="fail"/>
  </action>
  <kill name="fail"><message>failed</message></kill>
  <end name="end"/>
</workflow-app>"""


def _retry_xml() -> str:
    return """<?xml version="1.0"?>
<workflow-app name="retry-test" xmlns="uri:oozie:workflow:0.5">
  <start to="a1"/>
  <action name="a1" retry-max="3" retry-interval="5">
    <hive xmlns="uri:oozie:hive-action:0.2">
      <script>a1.hql</script>
    </hive>
    <ok to="end"/><error to="fail"/>
  </action>
  <kill name="fail"><message>failed</message></kill>
  <end name="end"/>
</workflow-app>"""


def _global_config_xml() -> str:
    return """<?xml version="1.0"?>
<workflow-app name="global-test" xmlns="uri:oozie:workflow:0.5">
  <global>
    <configuration>
      <property><name>queue.name</name><value>default</value></property>
    </configuration>
  </global>
  <start to="a1"/>
  <action name="a1">
    <hive xmlns="uri:oozie:hive-action:0.2">
      <script>a1.hql</script>
    </hive>
    <ok to="end"/><error to="fail"/>
  </action>
  <kill name="fail"><message>failed</message></kill>
  <end name="end"/>
</workflow-app>"""


def _subworkflow_xml() -> str:
    return """<?xml version="1.0"?>
<workflow-app name="sub-test" xmlns="uri:oozie:workflow:0.5">
  <start to="sub1"/>
  <action name="sub1">
    <sub-workflow>
      <app-path>/user/oozie/subflows/etl</app-path>
    </sub-workflow>
    <ok to="end"/><error to="fail"/>
  </action>
  <kill name="fail"><message>failed</message></kill>
  <end name="end"/>
</workflow-app>"""


# ══════════════════════════════════════════════════════════════════════════════
# parse_workflow — sample workflow
# ══════════════════════════════════════════════════════════════════════════════

class TestParseWorkflow:
    def test_returns_workflow_graph(self):
        graph = parse_workflow(WORKFLOW_XML)
        assert isinstance(graph, WorkflowGraph)

    def test_action_count(self):
        graph = parse_workflow(WORKFLOW_XML)
        assert len(graph.actions) == 4

    def test_action_names(self):
        graph = parse_workflow(WORKFLOW_XML)
        names = {a.name for a in graph.actions}
        assert {"ingest-customers", "ingest-transactions", "transform-spark", "export-report"} == names

    def test_start_node(self):
        graph = parse_workflow(WORKFLOW_XML)
        assert graph.start_node == "ingest-customers"

    def test_hive_actions(self):
        graph = parse_workflow(WORKFLOW_XML)
        hive = [a for a in graph.actions if a.action_type == "hive"]
        assert len(hive) == 2

    def test_spark_action(self):
        graph = parse_workflow(WORKFLOW_XML)
        spark = [a for a in graph.actions if a.action_type == "spark"]
        assert len(spark) == 1
        assert spark[0].name == "transform-spark"

    def test_shell_action(self):
        graph = parse_workflow(WORKFLOW_XML)
        shell = [a for a in graph.actions if a.action_type == "shell"]
        assert len(shell) == 1
        assert shell[0].name == "export-report"

    def test_ok_to_edge(self):
        graph = parse_workflow(WORKFLOW_XML)
        action_map = {a.name: a for a in graph.actions}
        assert action_map["ingest-customers"].ok_to == "ingest-transactions"

    def test_error_to_edge(self):
        graph = parse_workflow(WORKFLOW_XML)
        action_map = {a.name: a for a in graph.actions}
        assert action_map["ingest-customers"].error_to == "fail"

    def test_kill_node_parsed(self):
        graph = parse_workflow(WORKFLOW_XML)
        assert "fail" in graph.kills
        assert isinstance(graph.kills["fail"], OozieKill)

    def test_kill_not_in_actions(self):
        graph = parse_workflow(WORKFLOW_XML)
        names = {a.name for a in graph.actions}
        assert "fail" not in names
        assert "end" not in names

    def test_all_actions_are_oozie_action(self):
        graph = parse_workflow(WORKFLOW_XML)
        assert all(isinstance(a, OozieAction) for a in graph.actions)


# ══════════════════════════════════════════════════════════════════════════════
# workflow_to_dict — sample workflow
# ══════════════════════════════════════════════════════════════════════════════

class TestWorkflowToDict:
    def setup_method(self):
        self.job = workflow_to_dict(WORKFLOW_XML, job_name="retail-etl")

    def test_returns_dict(self):
        assert isinstance(self.job, dict)

    def test_job_name(self):
        assert self.job["name"] == "retail-etl"

    def test_task_count(self):
        assert len(self.job["tasks"]) == 4

    def test_task_keys_present(self):
        for task in self.job["tasks"]:
            assert "task_key" in task

    def test_start_task_has_no_depends_on(self):
        task_map = {t["task_key"]: t for t in self.job["tasks"]}
        assert task_map["ingest-customers"]["depends_on"] == []

    def test_linear_dependency(self):
        task_map = {t["task_key"]: t for t in self.job["tasks"]}
        deps = [d["task_key"] for d in task_map["ingest-transactions"]["depends_on"]]
        assert "ingest-customers" in deps

    def test_notebook_base_parameters_are_strings(self):
        for task in self.job["tasks"]:
            bp = task.get("notebook_task", {}).get("base_parameters", {})
            assert all(isinstance(v, str) for v in bp.values())

    def test_shell_args_joined(self):
        task_map = {t["task_key"]: t for t in self.job["tasks"]}
        bp = task_map["export-report"]["notebook_task"]["base_parameters"]
        assert bp["args"] == "${txnDate},${reportPath}"

    def test_spark_task_has_jar_library(self):
        task_map = {t["task_key"]: t for t in self.job["tasks"]}
        t = task_map["transform-spark"]
        assert "spark_jar_task" in t
        assert any("lib/retail-transform.jar" in lib.get("jar", "") for lib in t.get("libraries", []))

    def test_spark_args_captured(self):
        task_map = {t["task_key"]: t for t in self.job["tasks"]}
        params = task_map["transform-spark"]["spark_jar_task"]["parameters"]
        assert "--date" in params

    def test_migration_notes_present(self):
        # kill node "fail" should trigger a migration note
        assert "_migration_notes" in self.job

    def test_start_task_sorted_first(self):
        assert self.job["tasks"][0]["task_key"] == "ingest-customers"


# ══════════════════════════════════════════════════════════════════════════════
# workflow_to_json
# ══════════════════════════════════════════════════════════════════════════════

class TestWorkflowToJson:
    def test_returns_valid_json(self):
        result = workflow_to_json(WORKFLOW_XML, job_name="retail-etl")
        parsed = json.loads(result)
        assert "tasks" in parsed
        assert len(parsed["tasks"]) == 4

    def test_annotation_keys_stripped(self):
        result = workflow_to_json(WORKFLOW_XML, job_name="retail-etl")
        parsed = json.loads(result)
        # Top-level annotation keys must be absent
        assert "_migration_notes" not in parsed
        # Task-level annotation keys must also be absent
        for task in parsed["tasks"]:
            for key in task:
                assert not key.startswith("_"), f"Annotation key '{key}' leaked into JSON output"


# ══════════════════════════════════════════════════════════════════════════════
# Fork / Join
# ══════════════════════════════════════════════════════════════════════════════

class TestForkJoin:
    def setup_method(self):
        self.graph = parse_workflow(_fork_join_xml())
        self.job = workflow_to_dict(_fork_join_xml(), job_name="fork-test")
        self.task_map = {t["task_key"]: t for t in self.job["tasks"]}

    def test_fork_parsed(self):
        assert "fork1" in self.graph.forks
        assert set(self.graph.forks["fork1"].paths) == {"b1", "b2"}

    def test_join_parsed(self):
        assert "join1" in self.graph.joins
        assert self.graph.joins["join1"].to == "a2"

    def test_branch_tasks_depend_on_a1(self):
        b1_deps = [d["task_key"] for d in self.task_map["b1"]["depends_on"]]
        b2_deps = [d["task_key"] for d in self.task_map["b2"]["depends_on"]]
        assert b1_deps == ["a1"]
        assert b2_deps == ["a1"]

    def test_post_join_depends_on_both_branches(self):
        a2_deps = {d["task_key"] for d in self.task_map["a2"]["depends_on"]}
        assert a2_deps == {"b1", "b2"}

    def test_entry_task_has_no_deps(self):
        assert self.task_map["a1"]["depends_on"] == []


# ══════════════════════════════════════════════════════════════════════════════
# Decision nodes
# ══════════════════════════════════════════════════════════════════════════════

class TestDecision:
    def setup_method(self):
        self.graph = parse_workflow(_decision_xml())
        self.job = workflow_to_dict(_decision_xml(), job_name="decision-test")
        self.task_map = {t["task_key"]: t for t in self.job["tasks"]}

    def test_decision_parsed(self):
        assert "decide1" in self.graph.decisions
        dec = self.graph.decisions["decide1"]
        assert isinstance(dec, OozieDecision)
        assert dec.default == "b3"
        assert len(dec.cases) == 2

    def test_decision_task_created(self):
        assert "decide1" in self.task_map

    def test_decision_task_depends_on_a1(self):
        deps = [d["task_key"] for d in self.task_map["decide1"]["depends_on"]]
        assert deps == ["a1"]

    def test_branch_tasks_depend_on_decision(self):
        for branch in ("b1", "b2", "b3"):
            deps = [d["task_key"] for d in self.task_map[branch]["depends_on"]]
            assert "decide1" in deps, f"{branch} should depend on decide1"

    def test_decision_note_annotation(self):
        assert "_decision_note" in self.task_map["decide1"]

    def test_decision_json_strips_annotation(self):
        result = json.loads(workflow_to_json(_decision_xml()))
        for task in result["tasks"]:
            assert "_decision_note" not in task

    def test_total_task_count(self):
        # 1 decision + 1 a1 + 3 branch actions = 5
        assert len(self.job["tasks"]) == 5


# ══════════════════════════════════════════════════════════════════════════════
# Retry settings
# ══════════════════════════════════════════════════════════════════════════════

class TestRetrySettings:
    def test_retry_max_mapped(self):
        job = workflow_to_dict(_retry_xml())
        task_map = {t["task_key"]: t for t in job["tasks"]}
        assert task_map["a1"]["max_retries"] == 3

    def test_retry_interval_mapped(self):
        job = workflow_to_dict(_retry_xml())
        task_map = {t["task_key"]: t for t in job["tasks"]}
        # 5 minutes × 60000 ms/min = 300000 ms
        assert task_map["a1"]["min_retry_interval_millis"] == 300_000


# ══════════════════════════════════════════════════════════════════════════════
# Global configuration injection
# ══════════════════════════════════════════════════════════════════════════════

class TestGlobalConfig:
    def test_global_config_parsed(self):
        graph = parse_workflow(_global_config_xml())
        assert graph.global_config.get("queue.name") == "default"

    def test_global_config_in_base_parameters(self):
        job = workflow_to_dict(_global_config_xml())
        task_map = {t["task_key"]: t for t in job["tasks"]}
        bp = task_map["a1"]["notebook_task"]["base_parameters"]
        assert bp.get("queue.name") == "default"


# ══════════════════════════════════════════════════════════════════════════════
# Sub-workflow
# ══════════════════════════════════════════════════════════════════════════════

class TestSubWorkflow:
    def test_subworkflow_action_parsed(self):
        graph = parse_workflow(_subworkflow_xml())
        assert len(graph.actions) == 1
        assert graph.actions[0].action_type == "sub-workflow"

    def test_subworkflow_notebook_task(self):
        job = workflow_to_dict(_subworkflow_xml())
        task_map = {t["task_key"]: t for t in job["tasks"]}
        assert "notebook_task" in task_map["sub1"]
        bp = task_map["sub1"]["notebook_task"]["base_parameters"]
        assert bp.get("sub_workflow_app_path") == "/user/oozie/subflows/etl"

    def test_subworkflow_annotation_stripped_in_json(self):
        result = json.loads(workflow_to_json(_subworkflow_xml()))
        for task in result["tasks"]:
            assert "_sub_workflow_note" not in task


# ══════════════════════════════════════════════════════════════════════════════
# Kill nodes
# ══════════════════════════════════════════════════════════════════════════════

class TestKillNodes:
    def test_kill_stored_in_graph(self):
        graph = parse_workflow(WORKFLOW_XML)
        assert "fail" in graph.kills

    def test_kill_message_captured(self):
        graph = parse_workflow(WORKFLOW_XML)
        assert "error message" in graph.kills["fail"].message.lower() or \
               "wf:errorMessage" in graph.kills["fail"].message

    def test_kill_not_a_task(self):
        job = workflow_to_dict(WORKFLOW_XML)
        task_keys = {t["task_key"] for t in job["tasks"]}
        assert "fail" not in task_keys
