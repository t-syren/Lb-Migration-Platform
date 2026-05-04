"""Convert Oozie workflow.xml to Databricks Jobs API 2.1 JSON.

Supports:
  - Linear workflows  → action → action chains
  - Fork / Join       → Databricks parallel tasks via depends_on fan-out/fan-in
  - Decision          → All branches kept; annotated for manual conditional review
  - Kill / Error      → Failure endpoints preserved as migration annotations
  - Sub-workflow      → Placeholder notebook tasks with referenced app-path
  - Start node        → Entry point explicitly tracked; start task sorted first
  - Coordinator       → Databricks job schedule (cron)
  - Bundle            → Multiple job payloads, one per coordinator
  - Retry settings    → Databricks max_retries / min_retry_interval_millis
  - Global config     → <global><configuration> injected into all task base_parameters
  - Action config     → <configuration> inside each action injected into base_parameters
  - File / Archive    → Preserved as migration annotations

Not converted (no Databricks equivalent or requires manual substitution):
  - Dataset-based scheduling  — Oozie datasets have no Jobs API equivalent
  - SLA configurations        — no Jobs API equivalent; silently skipped
  - EL expressions ${...}     — preserved verbatim; require manual replacement
  - Coordinator end-time      — informational only
"""

import json
import logging
import os
import posixpath
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree

logger = logging.getLogger(__name__)

_OOZIE_ACTION_TYPES = {
    "hive", "spark", "java", "pig", "sqoop", "shell", "fs", "email", "sub-workflow"
}
_BASE_PARAMETER_LIST_DELIMITER = ","


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class OozieAction:
    name: str
    action_type: str
    ok_to: str = ""
    error_to: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    retry_max: int = 1
    retry_interval_ms: int = 60000  # milliseconds


@dataclass
class OozieFork:
    """<fork> node — branches out to multiple parallel paths."""
    name: str
    paths: List[str] = field(default_factory=list)


@dataclass
class OozieJoin:
    """<join> node — merges parallel branches back together."""
    name: str
    to: str = ""


@dataclass
class OozieDecision:
    """<decision> node — conditional switch with case/default branches."""
    name: str
    cases: List[Tuple[str, str]] = field(default_factory=list)  # (condition_expr, to_node)
    default: str = ""


@dataclass
class OozieKill:
    """<kill> node — workflow failure endpoint."""
    name: str
    message: str = ""


@dataclass
class WorkflowGraph:
    """Parsed representation of an entire Oozie workflow."""
    name: str = ""
    actions: List[OozieAction] = field(default_factory=list)
    forks: Dict[str, OozieFork] = field(default_factory=dict)
    joins: Dict[str, OozieJoin] = field(default_factory=dict)
    decisions: Dict[str, OozieDecision] = field(default_factory=dict)
    kills: Dict[str, OozieKill] = field(default_factory=dict)
    start_node: str = ""
    global_config: Dict[str, str] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _strip_ns(tag: str) -> str:
    """Remove namespace URI from an lxml tag string."""
    if callable(tag):  # lxml Comment/PI nodes have a callable tag, not a string
        return ""
    return tag.split("}")[-1] if "}" in tag else tag


def _as_list(value: Any) -> List[Any]:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _base_parameter_value(value: Any) -> str:
    """Databricks notebook base_parameters must contain string values only."""
    if isinstance(value, list):
        return _BASE_PARAMETER_LIST_DELIMITER.join(str(item) for item in value)
    return "" if value is None else str(value)


def _notebook_base_parameters(parameters: Dict[str, Any]) -> Dict[str, str]:
    return {str(k): _base_parameter_value(v) for k, v in parameters.items()}


def _parse_configuration(elem: Any) -> Dict[str, str]:
    """Parse an Oozie <configuration> element into a name → value dict."""
    result: Dict[str, str] = {}
    for prop in elem:
        if _strip_ns(prop.tag) != "property":
            continue
        name = value = ""
        for child in prop:
            t = _strip_ns(child.tag)
            if t == "name":
                name = (child.text or "").strip()
            elif t == "value":
                value = (child.text or "").strip()
        if name:
            result[name] = value
    return result


def _strip_annotation_keys(obj: Any) -> Any:
    """Recursively remove dict keys starting with '_' (migration annotations)."""
    if isinstance(obj, dict):
        return {k: _strip_annotation_keys(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_annotation_keys(item) for item in obj]
    return obj

def convert_xml(xml_str: str):
    if "<coordinator-app" in xml_str:
        job, warnings = coordinator_to_dict(xml_str)
        if warnings:
            print("⚠️ Coordinator warnings:", warnings)
        return json.dumps(job, indent=2)
        # return json.dumps(coordinator_to_dict(xml_str), indent=2)
    elif "<workflow-app" in xml_str:
        return workflow_to_json(xml_str)
    else:
        raise ValueError("Unknown XML type")
# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW PARSER  (actions, fork/join, decision, kill, start, global)
# ══════════════════════════════════════════════════════════════════════════════

def parse_workflow(xml_str: str) -> WorkflowGraph:
    """Parse a workflow XML into a WorkflowGraph capturing the full topology."""
    root = etree.fromstring(xml_str.encode("utf-8"))
    graph = WorkflowGraph(name=root.get("name", ""))

    # First pass: collect <global><configuration> (applies to all actions)
    for elem in root:
        if _strip_ns(elem.tag) == "global":
            for child in elem:
                if _strip_ns(child.tag) == "configuration":
                    graph.global_config.update(_parse_configuration(child))
            break

    for elem in root:
        tag = _strip_ns(elem.tag)

        # ── Start ─────────────────────────────────────────────────────────────
        if tag == "start":
            graph.start_node = elem.get("to", "")

        # ── Kill ──────────────────────────────────────────────────────────────
        elif tag == "kill":
            kill_name = elem.get("name", "")
            message = ""
            for child in elem:
                if _strip_ns(child.tag) == "message":
                    message = (child.text or "").strip()
            graph.kills[kill_name] = OozieKill(name=kill_name, message=message)

        # ── Fork ──────────────────────────────────────────────────────────────
        elif tag == "fork":
            fork_name = elem.get("name", "")
            paths = [
                child.get("start", "")
                for child in elem
                if _strip_ns(child.tag) == "path"
            ]
            graph.forks[fork_name] = OozieFork(name=fork_name, paths=paths)

        # ── Join ──────────────────────────────────────────────────────────────
        elif tag == "join":
            join_name = elem.get("name", "")
            to = elem.get("to", "")
            graph.joins[join_name] = OozieJoin(name=join_name, to=to)

        # ── Decision ──────────────────────────────────────────────────────────
        elif tag == "decision":
            dec_name = elem.get("name", "")
            cases: List[Tuple[str, str]] = []
            default = ""
            for child in elem:
                if _strip_ns(child.tag) == "switch":
                    for case_elem in child:
                        case_tag = _strip_ns(case_elem.tag)
                        if case_tag == "case":
                            cases.append(
                                ((case_elem.text or "").strip(), case_elem.get("to", ""))
                            )
                        elif case_tag == "default":
                            default = case_elem.get("to", "")
            graph.decisions[dec_name] = OozieDecision(
                name=dec_name, cases=cases, default=default
            )

        # ── Action ────────────────────────────────────────────────────────────
        elif tag == "action":
            action_name = elem.get("name", "")
            # Attributes take precedence; child elements (<retry-max>, <retry-interval>)
            # are also accepted for compatibility with workflow variants that use them.
            retry_max = int(elem.get("retry-max", "1") or "1")
            retry_interval_ms = int(elem.get("retry-interval", "1") or "1") * 60000

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
                elif child_tag == "retry-max":
                    retry_max = int((child.text or "1").strip())
                elif child_tag == "retry-interval":
                    retry_interval_ms = int((child.text or "1").strip()) * 60000
                elif child_tag in _OOZIE_ACTION_TYPES:
                    action_type = child_tag
                    files: List[str] = []
                    archives: List[str] = []
                    for sub in child:
                        sub_tag = _strip_ns(sub.tag)
                        if sub_tag == "configuration":
                            config.setdefault("properties", {}).update(
                                _parse_configuration(sub)
                            )
                        elif sub_tag == "file":
                            files.append((sub.text or "").strip())
                        elif sub_tag == "archive":
                            archives.append((sub.text or "").strip())
                        else:
                            val = (sub.text or "").strip()
                            if not val:
                                continue
                            if sub_tag in config:
                                existing = config[sub_tag]
                                if isinstance(existing, list):
                                    existing.append(val)
                                else:
                                    config[sub_tag] = [existing, val]
                            else:
                                config[sub_tag] = val
                    if files:
                        config["files"] = files
                    if archives:
                        config["archives"] = archives

            if action_type is None:
                continue

            graph.actions.append(OozieAction(
                name=action_name,
                action_type=action_type,
                ok_to=ok_to,
                error_to=error_to,
                config=config,
                retry_max=retry_max,
                retry_interval_ms=retry_interval_ms,
            ))

    return graph


# ══════════════════════════════════════════════════════════════════════════════
# PREDECESSOR RESOLVER  (fork/join/decision/error → depends_on + run_if)
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_predecessors(
    graph: WorkflowGraph,
) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    """
    Compute predecessors and run_if for every action and decision node.

    Returns
    -------
    predecessors : node → ordered list of predecessor task/decision names
    run_if_map   : node → Databricks run_if string

    Edge semantics
    ──────────────
    ok_to    → success path  → run_if = ALL_SUCCESS
    error_to → failure path  → run_if = AT_LEAST_ONE_FAILED
    mixed    → both types    → run_if = ALL_DONE

    Fork / Join / Decision are pseudo-nodes: transparent in traversal.
    error_to pointing to a kill node or "end" is ignored (not a task).
    """
    action_names: set = {a.name for a in graph.actions}
    decision_names: set = set(graph.decisions.keys())
    real_nodes: set = action_names | decision_names
    pseudo_nodes: set = set(graph.forks) | set(graph.joins)
    terminal_names: set = set(graph.kills.keys()) | {"end"}

    # ── ok-path incoming edges ─────────────────────────────────────────────────
    ok_in: Dict[str, List[str]] = {}

    for action in graph.actions:
        if action.ok_to:
            ok_in.setdefault(action.ok_to, []).append(action.name)

    for fork_name, fork in graph.forks.items():
        for path in fork.paths:
            ok_in.setdefault(path, []).append(fork_name)

    for join_name, join in graph.joins.items():
        if join.to:
            ok_in.setdefault(join.to, []).append(join_name)

    for dec_name, decision in graph.decisions.items():
        for _, to_node in decision.cases:
            if to_node:
                ok_in.setdefault(to_node, []).append(dec_name)
        if decision.default:
            ok_in.setdefault(decision.default, []).append(dec_name)

    # ── error-path incoming edges ──────────────────────────────────────────────
    err_in: Dict[str, List[str]] = {}

    for action in graph.actions:
        if action.error_to and action.error_to not in terminal_names:
            err_in.setdefault(action.error_to, []).append(action.name)

    # ── traversal: walk through pseudo-nodes to reach real predecessors ────────
    def resolve(node_name: str, incoming: Dict[str, List[str]]) -> List[str]:
        result_preds: List[str] = []
        for pred in incoming.get(node_name, []):
            if pred in real_nodes:
                result_preds.append(pred)
            elif pred in pseudo_nodes:
                result_preds.extend(resolve(pred, ok_in))
        return result_preds

    # ── assemble per-node results ──────────────────────────────────────────────
    predecessors: Dict[str, List[str]] = {}
    run_if_map: Dict[str, str] = {}

    for node_name in list(action_names) + list(decision_names):
        ok_preds = resolve(node_name, ok_in)
        err_preds = resolve(node_name, err_in)

        # Merge, preserving order and deduplicating
        seen: set = set()
        merged: List[str] = []
        for p in ok_preds + err_preds:
            if p not in seen:
                seen.add(p)
                merged.append(p)

        predecessors[node_name] = merged

        if ok_preds and err_preds:
            run_if_map[node_name] = "ALL_DONE"
        elif err_preds:
            run_if_map[node_name] = "AT_LEAST_ONE_FAILED"
        else:
            run_if_map[node_name] = "ALL_SUCCESS"

    return predecessors, run_if_map


# ══════════════════════════════════════════════════════════════════════════════
# ACTION → DATABRICKS TASK
# ══════════════════════════════════════════════════════════════════════════════

def _action_to_task(
    action: OozieAction,
    predecessors: List[str],
    global_config: Optional[Dict[str, str]] = None,
    run_if: str = "ALL_SUCCESS",
) -> Dict[str, Any]:
    task: Dict[str, Any] = {
        "task_key":                   action.name,
        "depends_on":                 [{"task_key": p} for p in predecessors],
        "job_cluster_key":            "default_cluster",
        "run_if":                     run_if,
        "max_retries":                 getattr(action, "retry_max", 1),
        "min_retry_interval_millis":  getattr(action, "retry_interval_ms", 60000),
        "retry_on_timeout":           True,
        "timeout_seconds":            3600,
        "email_notifications":        {},
    }

    # Merge global + action-level <configuration> into base_parameters
    combined_params: Dict[str, str] = dict(global_config or {})
    if isinstance(action.config.get("properties"), dict):
        combined_params.update(action.config["properties"])

    # File/archive distributions → annotation only (no Databricks equivalent)
    if action.config.get("files") or action.config.get("archives"):
        task["_distributed_files"] = {
            "files":    action.config.get("files", []),
            "archives": action.config.get("archives", []),
        }

    # ── Hive ──────────────────────────────────────────────────────────────────
    if action.action_type == "hive":
        params = _as_list(action.config.get("param"))
        param_dict: Dict[str, str] = {}
        for p in params:
            if "=" in p:
                k, v = p.split("=", 1)
                param_dict[k.strip()] = v.strip()
        task["notebook_task"] = {
            "notebook_path": f"/Migrations/hive/{action.name}",
            "source": "WORKSPACE",
            "base_parameters": _notebook_base_parameters({
                "script_path": action.config.get("script", ""),
                **combined_params,
                **param_dict,
            }),
        }

    # ── Spark ─────────────────────────────────────────────────────────────────
    elif action.action_type == "spark":
        args = [str(a) for a in _as_list(action.config.get("arg"))]
        task["spark_jar_task"] = {
            "main_class_name": action.config.get("class", ""),
            "parameters":      args,
        }
        jar_path = action.config.get("jar", "")
        if jar_path:
            task["libraries"] = [{"jar": jar_path}]

    # ── Shell ─────────────────────────────────────────────────────────────────
    elif action.action_type == "shell":
        args = _as_list(action.config.get("argument"))
        task["notebook_task"] = {
            "notebook_path": f"/Migrations/shell/{action.name}",
            "source": "WORKSPACE",
            "base_parameters": _notebook_base_parameters({
                "script_path": action.config.get("exec", ""),
                "args":        args,
                **combined_params,
            }),
        }

    # ── Java ──────────────────────────────────────────────────────────────────
    elif action.action_type == "java":
        args = [str(a) for a in _as_list(action.config.get("arg"))]
        task["spark_jar_task"] = {
            "main_class_name": action.config.get("main-class", ""),
            "parameters":      args,
        }
        jar_path = action.config.get("jar", "")
        if jar_path:
            task["libraries"] = [{"jar": jar_path}]

    # ── Sub-workflow ──────────────────────────────────────────────────────────
    elif action.action_type == "sub-workflow":
        app_path = action.config.get("app-path", "")
        task["notebook_task"] = {
            "notebook_path": f"/Migrations/sub-workflow/{action.name}",
            "source": "WORKSPACE",
            "base_parameters": _notebook_base_parameters({
                "sub_workflow_app_path": app_path,
                **combined_params,
            }),
        }
        task["_sub_workflow_note"] = (
            f"Sub-workflow reference: '{app_path}'. "
            "Migrate the referenced workflow separately and update notebook_path."
        )

    # ── Fallback (pig, sqoop, fs, email, …) ──────────────────────────────────
    else:
        task["notebook_task"] = {
            "notebook_path": f"/Migrations/{action.action_type}/{action.name}",
            "source":        "WORKSPACE",
            "base_parameters": _notebook_base_parameters(combined_params) if combined_params else {},
        }

    return task


# ══════════════════════════════════════════════════════════════════════════════
# DECISION → DATABRICKS PLACEHOLDER TASK
# ══════════════════════════════════════════════════════════════════════════════

def _decision_to_task(decision: OozieDecision, predecessors: List[str]) -> Dict[str, Any]:
    """
    Convert an Oozie <decision> node to a Databricks placeholder notebook task.

    All conditional branches are retained so the full DAG is preserved.
    The Databricks Jobs API does not support data-driven conditional routing,
    so conditions are stored as base_parameters for manual review.
    """
    case_params: Dict[str, str] = {}
    for i, (cond, to_node) in enumerate(decision.cases):
        case_params[f"case_{i}_condition"] = cond
        case_params[f"case_{i}_to"] = to_node
    if decision.default:
        case_params["default_to"] = decision.default

    branches = [to for _, to in decision.cases] + ([decision.default] if decision.default else [])

    return {
        "task_key":                   decision.name,
        "depends_on":                 [{"task_key": p} for p in predecessors],
        "job_cluster_key":            "default_cluster",
        "run_if":                     "ALL_SUCCESS",
        "max_retries":                0,
        "min_retry_interval_millis":  0,
        "retry_on_timeout":           False,
        "timeout_seconds":            3600,
        "email_notifications":        {},
        "notebook_task": {
            "notebook_path": f"/Migrations/decision/{decision.name}",
            "source":        "WORKSPACE",
            "base_parameters": case_params,
        },
        "_decision_note": (
            f"Decision node '{decision.name}': {len(branches)} branch(es) "
            f"({', '.join(branches)}). "
            "All branches are retained — remove unreachable ones in the Databricks Workflow editor. "
            "EL conditions (${...}) must be replaced with custom routing logic."
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# COORDINATOR PARSER  → Databricks schedule
# ══════════════════════════════════════════════════════════════════════════════

_COORD_FREQ_RE = re.compile(
    r"\$\{coord:(minutes|hours|days|months)\((\d+)\)\}",
    re.IGNORECASE,
)


def _oozie_frequency_to_quartz_cron(frequency: str, start_time: str) -> Optional[str]:
    """
    Convert an Oozie coordinator frequency string to a Quartz cron expression
    suitable for the Databricks Jobs API schedule.quartz_cron_expression field.

    Returns None if the frequency cannot be mapped automatically.

    Examples
    --------
    "${coord:hours(1)}"  → "0 0 * * * ?"      (every hour)
    "${coord:days(1)}"   → "0 0 0 * * ?"      (daily at midnight)
    "${coord:months(1)}" → "0 0 0 1 * ?"      (monthly on the 1st)
    "60"                 → "0 0 * * * ?"      (every 60 minutes → hourly)
    "1440"               → "0 0 0 * * ?"      (1440 minutes → daily)
    """
    frequency = (frequency or "").strip()

    m = _COORD_FREQ_RE.match(frequency)
    if m:
        unit, n = m.group(1).lower(), int(m.group(2))
        if unit == "minutes":
            if n == 60:
                return "0 0 * * * ?"
            if n < 60:
                return f"0 0/{n} * * * ?"
        elif unit == "hours":
            if n == 1:
                return "0 0 * * * ?"
            return f"0 0 0/{n} * * ?"
        elif unit == "days":
            if n == 1:
                return "0 0 0 * * ?"
            return f"0 0 0 1/{n} * ?"
        elif unit == "months":
            if n == 1:
                return "0 0 0 1 * ?"
            return f"0 0 0 1 1/{n} ?"
        return None

    if frequency.isdigit():
        minutes = int(frequency)
        if minutes == 60:
            return "0 0 * * * ?"
        if minutes == 1440:
            return "0 0 0 * * ?"
        if minutes == 10080:
            return "0 0 0 ? * MON"
        if minutes < 60:
            return f"0 0/{minutes} * * * ?"
        hours = minutes // 60
        if hours < 24:
            return f"0 0 0/{hours} * * ?"

    return None


def _parse_coordinator_timezone(timezone_str: str) -> str:
    return timezone_str if timezone_str else "UTC"


@dataclass
class CoordinatorSchedule:
    """Parsed Oozie coordinator schedule metadata."""
    name: str
    frequency: str
    start: str
    end: str
    timezone: str
    workflow_app_path: str
    quartz_cron: Optional[str] = None
    cron_warning: Optional[str] = None


def parse_coordinator(xml_str: str) -> CoordinatorSchedule:
    """
    Parse an Oozie coordinator.xml and return a CoordinatorSchedule.

    Raises ValueError if the root element is not a coordinator-app.
    """
    root = etree.fromstring(xml_str.encode("utf-8"))
    root_tag = _strip_ns(root.tag)
    if root_tag != "coordinator-app":
        raise ValueError(f"Expected <coordinator-app>, got <{root_tag}>")

    name      = root.get("name", "migrated-coordinator")
    frequency = root.get("frequency", "")
    start     = root.get("start", "")
    end       = root.get("end", "")
    timezone  = root.get("timezone", "UTC")

    workflow_app_path = ""
    for elem in root.iter():
        if _strip_ns(elem.tag) == "app-path":
            workflow_app_path = (elem.text or "").strip()
            break

    quartz_cron = _oozie_frequency_to_quartz_cron(frequency, start)
    cron_warning = None
    if quartz_cron is None:
        cron_warning = (
            f"Could not auto-convert frequency '{frequency}' to a Quartz cron expression. "
            "Set schedule.quartz_cron_expression manually in the generated JSON."
        )

    return CoordinatorSchedule(
        name=name,
        frequency=frequency,
        start=start,
        end=end,
        timezone=timezone,
        workflow_app_path=workflow_app_path,
        quartz_cron=quartz_cron,
        cron_warning=cron_warning,
    )


def coordinator_schedule_to_databricks(schedule: CoordinatorSchedule) -> Dict[str, Any]:
    """
    Convert a CoordinatorSchedule to the Databricks Jobs API 2.1 schedule block.

    Returns a dict with keys:
      schedule   → the Jobs API schedule object
      _warnings  → list of human-readable warnings (not sent to API)
      _metadata  → original Oozie coordinator metadata
    """
    warnings: List[str] = []
    if schedule.cron_warning:
        warnings.append(schedule.cron_warning)

    cron = schedule.quartz_cron or "0 0 0 * * ?"

    return {
        "schedule": {
            "quartz_cron_expression": cron,
            "timezone_id":            _parse_coordinator_timezone(schedule.timezone),
            "pause_status":           "PAUSED",
        },
            # ✅ ADD THIS BLOCK
       
        "_warnings": warnings,
        "_metadata": {
            "oozie_frequency":         schedule.frequency,
            "oozie_start":             schedule.start,
            "oozie_end":               schedule.end,
            "oozie_workflow_app_path": schedule.workflow_app_path,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# BUNDLE PARSER  → multiple coordinator schedules
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BundleEntry:
    """One coordinator reference inside a bundle.xml."""
    name: str
    coordinator_app_path: str
    kickoff_time: str = ""


def parse_bundle(xml_str: str) -> List[BundleEntry]:
    """
    Parse a bundle.xml and return a list of BundleEntry items.

    Raises ValueError if the root element is not a bundle-app.
    """
    root = etree.fromstring(xml_str.encode("utf-8"))
    root_tag = _strip_ns(root.tag)
    if root_tag != "bundle-app":
        raise ValueError(f"Expected <bundle-app>, got <{root_tag}>")

    entries: List[BundleEntry] = []
    for elem in root:
        if _strip_ns(elem.tag) != "coordinator":
            continue

        name = elem.get("name", "")
        app_path = ""
        kickoff_time = ""

        for child in elem:
            child_tag = _strip_ns(child.tag)
            if child_tag == "app-path":
                app_path = (child.text or "").strip()
            elif child_tag == "configuration":
                for prop in child:
                    prop_name = prop_value = ""
                    for p_child in prop:
                        p_tag = _strip_ns(p_child.tag)
                        if p_tag == "name":
                            prop_name  = (p_child.text or "").strip()
                        elif p_tag == "value":
                            prop_value = (p_child.text or "").strip()
                    if prop_name == "oozie.coord.application.path":
                        app_path = prop_value
                    elif prop_name == "kickOffTime":
                        kickoff_time = prop_value

        entries.append(BundleEntry(
            name=name,
            coordinator_app_path=app_path,
            kickoff_time=kickoff_time,
        ))

    return entries


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW → DATABRICKS JOB PAYLOAD
# ══════════════════════════════════════════════════════════════════════════════

def workflow_to_dict(xml_str: str, job_name: str = "migrated-workflow") -> Dict[str, Any]:
    """
    Parse workflow XML and return a Databricks Jobs API 2.1 payload dict.

    Fork/Join nodes are resolved to parallel tasks via depends_on.
    Decision nodes become placeholder tasks with all branches retained.
    Keys prefixed with '_' are migration annotations (stripped before API submission).
    """
    graph = parse_workflow(xml_str)
    pred_map, run_if_map = _resolve_predecessors(graph)

    tasks: List[Dict[str, Any]] = []

    # Decision placeholder tasks first (actions may depend on them)
    for dec_name, decision in graph.decisions.items():
        tasks.append(_decision_to_task(decision, pred_map.get(dec_name, [])))

    # Action tasks
    for action in graph.actions:
        tasks.append(
            _action_to_task(
                action,
                pred_map.get(action.name, []),
                graph.global_config,
                run_if_map.get(action.name, "ALL_SUCCESS"),
            )
        )


    # Sort so the start node appears first (cosmetic — Databricks ignores order)
    if graph.start_node:
        tasks.sort(
            key=lambda t: (0 if t["task_key"] == graph.start_node else 1, t["task_key"])
        )

    _default_cluster = {
        "spark_version": "14.3.x-scala2.12",
        "node_type_id":  "Standard_DS3_v2",
        "num_workers":   2,
    }

    payload: Dict[str, Any] = {
        "name":                  job_name,
        "email_notifications":   {},
        "webhook_notifications": {},
        "timeout_seconds":       86400,
        "max_concurrent_runs":   1,
        "tasks":                 tasks,
    }

    if len(tasks) >= 2:
        # Shared job cluster — only valid for multi-task jobs
        payload["job_clusters"] = [
            {"job_cluster_key": "default_cluster", "new_cluster": _default_cluster}
        ]
    else:
        # Single-task or empty job: inline cluster per task; shared clusters are rejected
        for t in tasks:
            t.pop("job_cluster_key", None)
            t["new_cluster"] = _default_cluster

    # Migration annotations (stripped before serialisation / API submission)
    notes: List[str] = []
    if graph.forks:
        notes.append(
            f"Fork/Join detected: {', '.join(graph.forks.keys())}. "
            "Converted to parallel Databricks tasks via depends_on fan-out/fan-in. "
            "Verify the task graph in the Databricks Workflow editor."
        )
    if graph.decisions:
        notes.append(
            f"Decision nodes detected: {', '.join(graph.decisions.keys())}. "
            "All conditional branches are retained — remove unreachable ones manually. "
            "Replace EL conditions (${...}) with custom routing logic."
        )
    if graph.kills:
        kill_msgs = {k: v.message for k, v in graph.kills.items()}
        notes.append(
            f"Kill nodes: {kill_msgs}. "
            "No automatic Databricks mapping — add failure notifications manually."
        )
    if graph.global_config:
        notes.append(
            f"Global configuration ({len(graph.global_config)} properties) "
            "injected into all task base_parameters."
        )
    if notes:
        payload["_migration_notes"] = notes

    return payload


def workflow_to_json(xml_str: str, job_name: str = "migrated-workflow") -> str:
    """End-to-end: parse workflow XML and return formatted Databricks job JSON string."""
    job = workflow_to_dict(xml_str, job_name=job_name)
    return json.dumps(_strip_annotation_keys(job), indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# COORDINATOR / BUNDLE → DATABRICKS JOB PAYLOAD
# ══════════════════════════════════════════════════════════════════════════════
from datetime import datetime

def _to_epoch_millis(ts):
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
    except:
        return None
    
def coordinator_to_dict(
    coord_xml_str: str,
    workflow_xml_str: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Convert a coordinator XML (and optionally its referenced workflow XML)
    to a Databricks Jobs API 2.1 payload dict.

    Returns (payload_dict, warnings_list).
    """
    schedule = parse_coordinator(coord_xml_str)
    schedule_block = coordinator_schedule_to_databricks(schedule)
    warnings: List[str] = list(schedule_block.get("_warnings", []))

    if workflow_xml_str:
        payload = workflow_to_dict(workflow_xml_str, job_name=schedule.name)
    else:
        placeholder_path = (
            schedule_block.get("_metadata", {}).get(
                "oozie_workflow_app_path",
                f"/Migrations/{schedule.name}/placeholder",
            )
        )
        payload = {
            "name":                  schedule.name,
            "email_notifications":   {},
            "webhook_notifications": {},
            "timeout_seconds":       86400,
            "max_concurrent_runs":   1,
            "tasks": [
                {
                    "task_key":   "placeholder_task",
                    "depends_on": [],
                    "new_cluster": {
                        "spark_version": "14.3.x-scala2.12",
                        "node_type_id":  "Standard_DS3_v2",
                        "num_workers":   2,
                    },
                    "notebook_task": {
                        "notebook_path": placeholder_path,
                        "source": "WORKSPACE",
                    },
                }
            ],
        }
        warnings.append(
            f"No workflow XML supplied for coordinator '{schedule.name}'. "
            f"A placeholder task pointing to '{schedule.workflow_app_path}' was inserted. "
            "Replace it with the actual migrated notebook path."
        )

    payload["schedule"] = schedule_block["schedule"]
    payload["coordinator_info"] = {
        "frequency":            schedule.frequency,
        "start":                schedule.start,
        "end":                  schedule.end,
        "timezone":             schedule.timezone,
        "workflow_app_path":    schedule.workflow_app_path,
        "quartz_cron_expression": schedule.quartz_cron or "0 0 0 * * ?",
    }

    return payload, warnings


def bundle_to_dicts(
    bundle_xml_str: str,
    coordinator_xmls: Optional[Dict[str, str]] = None,
) -> List[Tuple[str, Dict[str, Any], List[str]]]:
    """
    Convert a bundle XML to a list of (coordinator_name, payload_dict, warnings).

    coordinator_xmls: optional mapping of coordinator_app_path → coordinator XML string.
    """
    entries = parse_bundle(bundle_xml_str)
    results: List[Tuple[str, Dict[str, Any], List[str]]] = []

    for entry in entries:
        coord_xml = (coordinator_xmls or {}).get(entry.coordinator_app_path)
        if coord_xml:
            payload, warnings = coordinator_to_dict(coord_xml)
        else:
            payload = {
                "name":                  entry.name,
                "email_notifications":   {},
                "webhook_notifications": {},
                "timeout_seconds":       86400,
                "max_concurrent_runs":   1,
                "tasks":                 [],
                "job_clusters":          [],
            }
            warnings = [
                f"Bundle entry '{entry.name}': coordinator XML for path "
                f"'{entry.coordinator_app_path}' was not supplied. "
                "Add the coordinator XML to generate a complete job payload."
            ]

        if entry.kickoff_time and "schedule" not in payload:
            payload["schedule"] = {
                "quartz_cron_expression": "0 0 0 * * ?",
                "timezone_id":            "UTC",
                "pause_status":           "PAUSED",
            }
            warnings.append(
                f"Bundle kickoff_time '{entry.kickoff_time}' noted but could not be "
                "converted to a cron expression. Set schedule.quartz_cron_expression manually."
            )

        results.append((entry.name, payload, warnings))

    return results


# ══════════════════════════════════════════════════════════════════════════════
# MULTI-FILE CONVERSION  (coordinator ↔ workflow linking)
# ══════════════════════════════════════════════════════════════════════════════

def _app_path_basename(workflow_app_path: str) -> str:
    """Extract the bare name from an Oozie <app-path> value.

    Strips HDFS scheme (hdfs://host/...) and leading EL variables (${nameNode}/...)
    then returns the last path segment without a trailing slash.
    """
    norm = re.sub(r"^\$\{[^}]+\}", "", workflow_app_path or "")
    norm = re.sub(r"^hdfs://[^/]*", "", norm)
    return posixpath.basename(norm.rstrip("/"))


def _normalise_name(s: str) -> str:
    """Lowercase and collapse hyphens/underscores to '_' for fuzzy name matching.

    Oozie paths commonly use hyphens (wf-sales) while workflow name attributes
    use underscores (wf_sales).  Normalising both sides lets them match.
    """
    return re.sub(r"[-_]+", "_", s.lower())


def _match_coordinator_to_workflow(
    workflow_app_path: str,
    workflow_files: Dict[str, Tuple[str, str]],
) -> Optional[str]:
    """Return the workflow name whose name or filename matches the coordinator's
    <app-path> basename.  Returns None if no uploaded workflow matches.

    Matching rules (in order, first match wins):
    1. Exact: workflow name attribute == app-path basename
    2. Exact: workflow filename stem == app-path basename
    3. Normalised: hyphens and underscores treated as equivalent for rules 1 & 2

    Loose heuristics (same directory, path-segment, substring) are excluded to
    avoid false positives when unrelated workflow XMLs are uploaded together.
    """
    if not workflow_app_path or not workflow_files:
        return None

    app_base = _app_path_basename(workflow_app_path)
    if not app_base:
        return None

    # ── Exact passes ─────────────────────────────────────────────────────────
    # Priority 1: workflow name attribute == app-path basename (exact)
    for wf_name in workflow_files:
        if wf_name == app_base:
            return wf_name

    # Priority 2: workflow filename stem == app-path basename (exact)
    for wf_name, (wf_path, _) in workflow_files.items():
        stem = posixpath.basename(wf_path.replace("\\", "/"))
        stem = stem.rsplit(".", 1)[0] if "." in stem else stem
        if stem == app_base:
            return wf_name

    # ── Normalised passes (hyphen ↔ underscore) ───────────────────────────────
    norm_base = _normalise_name(app_base)

    # Priority 3a: normalised workflow name == normalised app-path basename
    for wf_name in workflow_files:
        if _normalise_name(wf_name) == norm_base:
            return wf_name

    # Priority 3b: normalised filename stem == normalised app-path basename
    for wf_name, (wf_path, _) in workflow_files.items():
        stem = posixpath.basename(wf_path.replace("\\", "/"))
        stem = stem.rsplit(".", 1)[0] if "." in stem else stem
        if _normalise_name(stem) == norm_base:
            return wf_name

    return None


def convert_oozie_file_set(
    files: Dict[str, str],
) -> Dict[str, Any]:
    """
    Convert a set of Oozie XML files to Databricks Jobs API 2.1 payloads.

    Workflow XMLs become independent Databricks jobs.
    Coordinator XMLs become scheduled jobs that trigger workflow jobs via
    ``run_job_task``.  The ``job_id`` field in each ``run_job_task`` is set to
    the string sentinel ``"{{job_id:<workflow_name>}}"`` — callers must replace
    it with the real Databricks job ID after creating the workflow jobs.

    Parameters
    ----------
    files : {relative_path: xml_content}

    Returns
    -------
    {
        "jobs":             {job_name: job_dict},
        "workflow_job_map": {wf_name: None},   # placeholder for real job IDs
        "links":            [{"coordinator": str, "workflow": str | None}],
        "warnings":         [str],
    }
    """
    # ── Step A: categorise ────────────────────────────────────────────────────
    # wf_name  → (file_path, xml_str)
    workflow_files: Dict[str, Tuple[str, str]] = {}
    # coord_name → (file_path, xml_str, CoordinatorSchedule)
    coordinator_files: Dict[str, Tuple[str, str, "CoordinatorSchedule"]] = {}
    warnings: List[str] = []

    for file_path, xml in files.items():
        if "<workflow-app" in xml:
            try:
                wf = parse_workflow(xml)
                wf_name = wf.name or os.path.splitext(os.path.basename(file_path))[0]
                workflow_files[wf_name] = (file_path, xml)
            except Exception as exc:
                warnings.append(f"Could not parse workflow '{file_path}': {exc}")
        elif "<coordinator-app" in xml:
            try:
                coord = parse_coordinator(xml)
                coord_name = coord.name or os.path.splitext(os.path.basename(file_path))[0]
                coordinator_files[coord_name] = (file_path, xml, coord)
            except Exception as exc:
                warnings.append(f"Could not parse coordinator '{file_path}': {exc}")

    # ── Step B: convert workflows (strip annotation keys for clean output) ────
    workflow_jobs: Dict[str, Dict[str, Any]] = {}
    for wf_name, (_, wf_xml) in workflow_files.items():
        job = workflow_to_dict(wf_xml, job_name=wf_name)
        workflow_jobs[wf_name] = _strip_annotation_keys(job)

    # ── Step C: workflow_job_map — name → None (filled by caller after deploy) ─
    workflow_job_map: Dict[str, Optional[int]] = {n: None for n in workflow_jobs}

    # ── Steps D–H: convert coordinators ──────────────────────────────────────
    coordinator_jobs: Dict[str, Dict[str, Any]] = {}
    links: List[Dict[str, Optional[str]]] = []

    for coord_name, (coord_path, coord_xml, coord) in coordinator_files.items():
        # Step D: match coordinator → workflow via app-path basename
        matched_wf = _match_coordinator_to_workflow(
            coord.workflow_app_path, workflow_files
        )

        # Step E: get coordinator shell (schedule + metadata, no workflow tasks)
        coord_job, coord_warns = coordinator_to_dict(coord_xml)
        # coordinator_to_dict always appends "No workflow XML supplied" when called
        # without workflow XML.  Suppress it here when a match was found — the
        # matched branch uses run_job_task and the warning would be misleading.
        if matched_wf:
            warnings.extend(w for w in coord_warns if "No workflow XML supplied" not in w)
        else:
            warnings.extend(coord_warns)

        # Step F: replace tasks with run_job_task (matched) or placeholder (unmatched)
        if matched_wf:
            task_key = f"run_{re.sub(r'[^a-zA-Z0-9_]', '_', matched_wf)}"
            coord_job["tasks"] = [
                {
                    "task_key": task_key,
                    "run_if": "ALL_SUCCESS",
                    "depends_on": [],
                    "run_job_task": {
                        # Sentinel replaced by caller once workflow job is created
                        "job_id": f"{{{{job_id:{matched_wf}}}}}",
                    },
                }
            ]
        else:
            # No matching workflow XML uploaded — insert a notebook placeholder so
            # the coordinator job is deployable; user replaces the notebook path.
            app_path = coord.workflow_app_path or f"/Migrations/{coord_name}"
            placeholder_key = f"run_{re.sub(r'[^a-zA-Z0-9_]', '_', _app_path_basename(app_path) or coord_name)}"
            coord_job["tasks"] = [
                {
                    "task_key": placeholder_key,
                    "run_if": "ALL_SUCCESS",
                    "depends_on": [],
                    "notebook_task": {
                        "notebook_path": app_path,
                        "source": "WORKSPACE",
                    },
                    "new_cluster": {
                        "spark_version": "14.3.x-scala2.12",
                        "node_type_id":  "Standard_DS3_v2",
                        "num_workers":   2,
                    },
                }
            ]
            warn_msg = (
                f"No workflow XML supplied for coordinator '{coord_name}'. "
                f"A placeholder task pointing to '{app_path}' was inserted. "
                "Replace it with the actual migrated notebook path."
            )
            coord_job["migration_warnings"] = [warn_msg]
            # warn_msg is already in coord_warns (from coordinator_to_dict) — don't duplicate

        # Step G: coordinators trigger jobs, they do not run cluster tasks
        coord_job.pop("job_clusters", None)

        # Step H: track link
        links.append({"coordinator": coord_name, "workflow": matched_wf})
        coordinator_jobs[coord_name] = coord_job

    # ── Step I: combine ───────────────────────────────────────────────────────
    jobs: Dict[str, Dict[str, Any]] = {}
    jobs.update(workflow_jobs)
    jobs.update(coordinator_jobs)

    return {
        "jobs": jobs,
        "workflow_job_map": workflow_job_map,
        "links": links,
        "warnings": warnings,
    }

