"""Convert Oozie workflow.xml to Databricks Jobs API 2.1 JSON."""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from lxml import etree

logger = logging.getLogger(__name__)

_OOZIE_ACTION_TYPES = {"hive", "spark", "java", "pig", "sqoop", "shell", "fs", "email"}
_BASE_PARAMETER_LIST_DELIMITER = ","


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


def _as_list(value: Any) -> List[Any]:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _base_parameter_value(value: Any) -> str:
    """Databricks notebook base_parameters must contain string values only."""
    if isinstance(value, list):
        return _BASE_PARAMETER_LIST_DELIMITER.join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _notebook_base_parameters(parameters: Dict[str, Any]) -> Dict[str, str]:
    return {str(key): _base_parameter_value(value) for key, value in parameters.items()}


def parse_workflow(xml_str: str) -> List[OozieAction]:
    root = etree.fromstring(xml_str.encode("utf-8"))
    actions: List[OozieAction] = []

    for elem in root.findall(".//*"):
        if _strip_ns(elem.tag) != "action":
            continue

        action_name = elem.get("name", "")
        action_type = None
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

                # 🔥 FIX: handle repeated tags like <arg>
                for sub in child:
                    sub_tag = _strip_ns(sub.tag)

                    val = (sub.text or "").strip()

                    if not val:
                        continue

                    # handle repeated keys (arg, param, etc.)
                    if sub_tag in config:
                        if isinstance(config[sub_tag], list):
                            config[sub_tag].append(val)
                        else:
                            config[sub_tag] = [config[sub_tag], val]
                    else:
                        config[sub_tag] = val

        if action_type is None:
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


def _action_to_task(action: OozieAction, predecessors: List[str]) -> Dict[str, Any]:
    """Convert one OozieAction to a Databricks task dict."""
    task: Dict[str, Any] = {
        "task_key": action.name,
        "depends_on": [{"task_key": p} for p in predecessors],
        "max_retries": 1,
        "min_retry_interval_millis": 60_000,
    }
    
    task["job_cluster_key"] = "default_cluster"
    task.update({
        "run_if": "ALL_SUCCESS",
        "retry_on_timeout": True,
        "timeout_seconds": 3600,
        "email_notifications": {}
    })

    if action.action_type == "hive":
        script_path = action.config.get("script", "")

        # extract params like INPUT_PATH=xxx
        params = _as_list(action.config.get("param"))

        param_dict = {}
        for p in params:
            if "=" in p:
                k, v = p.split("=", 1)
                param_dict[k.strip()] = v.strip()

        task["notebook_task"] = {
            "notebook_path": f"/Migrations/hive/{action.name}",
            "source": "WORKSPACE",
            "base_parameters": _notebook_base_parameters({
                "script_path": script_path,
                **param_dict
            })
        }
    elif action.action_type == "spark":
        # 🔥 handle <arg> properly
        params = [str(param) for param in _as_list(action.config.get("arg"))]

        task["spark_jar_task"] = {
            "main_class_name": action.config.get("class", ""),
            "parameters": params,
        }

        jar_path = action.config.get("jar", "")
        if jar_path:
            task["libraries"] = [{"jar": jar_path}]
    elif action.action_type == "shell":
        args = _as_list(action.config.get("argument"))

        task["notebook_task"] = {
            "notebook_path": f"/Migrations/shell/{action.name}",
            "source": "WORKSPACE",
            "base_parameters": _notebook_base_parameters({
                "script_path": action.config.get("exec", ""),
                "args": args
            })
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
    # Build predecessor map from ok_to edges (supports fan-in: multiple predecessors)
    successor_to_predecessors: Dict[str, List[str]] = {}
    for action in actions:
        if action.ok_to:
            successor_to_predecessors.setdefault(action.ok_to, []).append(action.name)
    # 🔥 sanity check
    action_names = {a.name for a in actions}
    # allowed terminal nodes
    TERMINAL_NODES = {"end", "fail"}

    for succ in successor_to_predecessors:
        if succ not in action_names and succ not in TERMINAL_NODES:
            raise ValueError(f"Broken DAG: '{succ}' not found in actions")

    tasks = []
    for action in actions:
        predecessors = successor_to_predecessors.get(action.name, [])
        tasks.append(_action_to_task(action, predecessors))

    return {
        "name": job_name,
        "email_notifications": {},
        "webhook_notifications": {},
        "timeout_seconds": 86400,
        "max_concurrent_runs": 1,
        "tasks": tasks,
        "job_clusters": [
            {
                "job_cluster_key": "default_cluster",
                "new_cluster": {
                    "spark_version": "14.3.x-scala2.12",
                    "node_type_id": "Standard_DS3_v2",
                    "num_workers": 2
                }
            }
        ]
    }


def workflow_to_json(xml_str: str, job_name: str = "migrated-workflow") -> str:
    """End-to-end: parse XML and return formatted Databricks job JSON."""
    actions = parse_workflow(xml_str)
    job = to_databricks_job(actions, job_name=job_name)
    return json.dumps(job, indent=2)
