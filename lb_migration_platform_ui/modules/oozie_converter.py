"""Convert Oozie workflow.xml to Databricks Jobs API 2.1 JSON."""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lxml import etree

logger = logging.getLogger(__name__)

_OOZIE_ACTION_TYPES = {"hive", "spark", "java", "pig", "sqoop", "shell", "fs", "email"}


@dataclass
class OozieAction:
    name: str
    action_type: str
    ok_to: str = ""
    error_to: str = ""
    config: Dict[str, Any] = field(default_factory=dict)


def _strip_ns(tag: str) -> str:
    """Remove namespace URI from an lxml tag string."""
    return tag.split("}")[-1] if "}" in tag else tag


def parse_workflow(xml_str: str) -> List[OozieAction]:
    """Parse an Oozie workflow XML string and return a list of OozieActions.

    Kill nodes and start/end pseudo-nodes are excluded.
    """
    root = etree.fromstring(xml_str.encode("utf-8"))
    actions: List[OozieAction] = []

    for elem in root:
        tag = _strip_ns(elem.tag)
        if tag != "action":
            continue

        action_name = elem.get("name", "")
        action_type: Optional[str] = None
        ok_to = ""
        error_to = ""
        config: Dict[str, Any] = {}

        for child in elem:
            child_tag = _strip_ns(child.tag)
            if child_tag == "ok":
                ok_to = child.get("to", "")
            elif child_tag == "error":
                error_to = child.get("to", "")
            elif child_tag in _OOZIE_ACTION_TYPES:
                action_type = child_tag
                for sub in child:
                    sub_tag = _strip_ns(sub.tag)
                    config[sub_tag] = sub.text or sub.get("value", "")

        if action_type is None:
            logger.debug("Action %s has unknown type, skipping", action_name)
            continue

        actions.append(
            OozieAction(
                name=action_name,
                action_type=action_type,
                ok_to=ok_to,
                error_to=error_to,
                config=config,
            )
        )

    return actions


def _action_to_task(action: OozieAction, predecessor: Optional[str]) -> Dict[str, Any]:
    """Convert one OozieAction to a Databricks task dict."""
    task: Dict[str, Any] = {
        "task_key": action.name,
        "depends_on": [{"task_key": predecessor}] if predecessor else [],
        "max_retries": 1,
        "min_retry_interval_millis": 60_000,
    }

    if action.action_type == "hive":
        task["sql_task"] = {
            "query": {"query_id": f"<replace: {action.config.get('script', 'hive_script.hql')}>"},
            "warehouse_id": "<replace: sql_warehouse_id>",
        }
    elif action.action_type == "spark":
        task["spark_jar_task"] = {
            "main_class_name": action.config.get("class", ""),
            "parameters": [],
        }
        task["libraries"] = [{"jar": action.config.get("jar", "")}]
    elif action.action_type == "shell":
        task["notebook_task"] = {
            "notebook_path": f"/Migrations/shell/{action.name}",
            "source": "WORKSPACE",
            "base_parameters": {"script": action.config.get("exec", "")},
        }
    elif action.action_type == "java":
        task["spark_jar_task"] = {
            "main_class_name": action.config.get("main-class", ""),
            "parameters": [],
        }
    else:
        task["notebook_task"] = {
            "notebook_path": f"/Migrations/{action.action_type}/{action.name}",
            "source": "WORKSPACE",
        }

    return task


def to_databricks_job(actions: List[OozieAction], job_name: str = "migrated-workflow") -> Dict[str, Any]:
    """Convert a list of OozieActions to a Databricks Jobs API 2.1 payload."""
    # Build predecessor map from ok_to edges
    successor_to_predecessor: Dict[str, str] = {}
    for action in actions:
        if action.ok_to:
            successor_to_predecessor[action.ok_to] = action.name

    tasks = []
    for action in actions:
        predecessor = successor_to_predecessor.get(action.name)
        tasks.append(_action_to_task(action, predecessor))

    return {
        "name": job_name,
        "tasks": tasks,
        "format": "MULTI_TASK",
        "max_concurrent_runs": 1,
    }


def workflow_to_json(xml_str: str, job_name: str = "migrated-workflow") -> str:
    """End-to-end: parse XML and return formatted Databricks job JSON."""
    actions = parse_workflow(xml_str)
    job = to_databricks_job(actions, job_name=job_name)
    return json.dumps(job, indent=2)
