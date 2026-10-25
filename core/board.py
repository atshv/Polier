"""Reading board.json, validating it and choosing the tasks whose scope applies.

Board schema versions:

- 0.9: no ``schema_version`` field. Only the classic fields are allowed.
- 1.0: ``"schema_version": "1.0"``. Adds stages, packages, runtime resources,
  budgets, worktree mode, contracts and the matching task fields.

``board_errors`` is the single schema check used by tools/check.py; the
semantic project checks (cycles, briefs, evidence, budgets, ...) stay in the
tools that need them.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .errors import PolierError

BOARD = "board.json"

SCHEMA_09 = "0.9"
SCHEMA_10 = "1.0"
SCHEMAS = (SCHEMA_09, SCHEMA_10)

ID_09 = re.compile(r"^M[0-9]{2,3}$")
ID_10 = re.compile(r"^(M[0-9]{2,3}|[A-Z][A-Z0-9]{0,5}-[0-9]{2,3})$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

STATUSES = {
    "pending", "claimed", "in_progress", "verifying", "review",
    "rework", "done", "blocked", "failed",
}
PROFILES = {"S", "M", "L"}
WORKTREE_MODES = {"required", "recommended", "off"}
OWNER_DECISIONS = {"pending", "continue", "stop"}
PACKAGE_KINDS = {"package", "service", "app", "tool", "infra"}
BUDGET_KEYS = {"architecture", "agents", "status", "brief", "package_architecture", "package_agents"}

TASK_REQUIRED = (
    "id", "title", "goal", "status", "depends_on", "complexity",
    "stage", "scope_write", "acceptance", "gates",
)
TASK_FIELDS_09 = frozenset(TASK_REQUIRED + (
    "why", "satisfies", "parallel_group", "scope_read", "owner", "branch",
    "worktree", "round", "evidence", "scope_write_forbidden", "handoff",
))
TASK_FIELDS_10 = frozenset(TASK_FIELDS_09 | {
    "package", "exclusive", "resources", "claim", "contract_followups",
})

BOARD_REQUIRED = ("project", "profile", "base_branch", "tasks")
BOARD_FIELDS_09 = frozenset(BOARD_REQUIRED + (
    "generator_version", "stage", "decisions", "open_questions",
))
BOARD_FIELDS_10 = frozenset(BOARD_FIELDS_09 | {
    "schema_version", "stages", "packages", "resources", "budgets",
    "worktrees", "contracts",
})

STAGE_FIELDS = frozenset({
    "id", "title", "goal", "exit_criteria", "exit_gates", "owner_decision", "depends_on",
})
PACKAGE_FIELDS = frozenset({"path", "kind", "may_import"})
RESOURCE_FIELDS = frozenset({"slots", "port_base", "port_stride", "services", "infra_patterns"})
CLAIM_FIELDS = frozenset({"task", "harness", "session", "worktree", "slot", "started", "heartbeat"})
CONTRACT_FIELDS = frozenset({
    "name", "path", "version", "schema_files", "fixtures_dir", "dependants",
})


def find_root(start) -> Optional[Path]:
    """The nearest folder at or above `start` that holds a board.json, or None."""
    if not start:
        return None
    folder = Path(os.path.abspath(str(start)))
    for candidate in (folder, *folder.parents):
        if (candidate / BOARD).exists():
            return candidate
    return None


def load_board(root, strict: bool = True) -> Optional[dict]:
    """Parsed board.json of `root`.

    strict=True raises PolierError for a missing or invalid board (the CLI tools);
    strict=False returns None instead, so a guard stays out of the way.
    """
    path = Path(root) / BOARD
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if not strict:
            return None
        raise PolierError(f"board.json not found in {root}") from exc
    except (ValueError, OSError) as exc:
        if not strict:
            return None
        raise PolierError(f"board.json is invalid: {exc}") from exc
    if not isinstance(board, dict) or not isinstance(board.get("tasks"), list):
        if not strict:
            return None
        raise PolierError("board.json has no task list")
    return board


def tasks_of(board: Optional[dict]) -> List[dict]:
    tasks = (board or {}).get("tasks") or []
    return [t for t in tasks if isinstance(t, dict)]


def pick_task(board: dict, task_id: Optional[str] = None) -> dict:
    """The task `task_id`, or the one task in_progress; PolierError otherwise."""
    tasks = tasks_of(board)
    if task_id:
        for task in tasks:
            if task.get("id") == task_id:
                return task
        raise PolierError(f"task {task_id} is not on the board")
    running = [t for t in tasks if t.get("status") == "in_progress"]
    if len(running) == 1:
        return running[0]
    if not running:
        raise PolierError("no task is in_progress; pass --task <ID>")
    ids = ", ".join(str(t.get("id")) for t in running)
    raise PolierError(f"several tasks are in_progress ({ids}); pass --task <ID>")


def active_tasks(board: Optional[dict], root=None, cwd=None, pinned: Optional[str] = None) -> Tuple[List[dict], str]:
    """The tasks whose scope applies to a session, and how they were chosen.

    Order: the pinned task, the in_progress task whose `worktree` contains `cwd`,
    every in_progress task. `how` is pinned, worktree, single, several or none.
    """
    tasks = tasks_of(board)
    if pinned:
        for task in tasks:
            if task.get("id") == pinned:
                return [task], "pinned"
    running = [t for t in tasks if t.get("status") == "in_progress"]
    if not running:
        return [], "none"
    if cwd and root:
        here = os.path.abspath(str(cwd))
        by_tree = []
        for task in running:
            tree = task.get("worktree")
            if not isinstance(tree, str) or not tree:
                continue
            tree = os.path.abspath(os.path.join(str(root), tree))
            if here == tree or here.startswith(tree + os.sep):
                by_tree.append(task)
        if len(by_tree) == 1:
            return by_tree, "worktree"
    return running, "single" if len(running) == 1 else "several"


def ready_tasks(board: Optional[dict]) -> List[dict]:
    """Pending tasks whose dependencies are all done, with their dependencies' handoff notes."""
    tasks = tasks_of(board)
    done = {t.get("id") for t in tasks if t.get("status") == "done"}
    by_id = {t.get("id"): t for t in tasks}
    out = []
    for task in tasks:
        deps = task.get("depends_on") or []
        if task.get("status") != "pending" or not all(d in done for d in deps):
            continue
        out.append({
            "id": task.get("id"),
            "title": task.get("title"),
            "brief": f"tasks/{task.get('id')}.md",
            "handoff": [f"{d}: {h}" for d in deps for h in (by_id.get(d, {}).get("handoff") or [])],
        })
    return out


# ---------------------------------------------------------------------------
# schema 1.0 helpers
# ---------------------------------------------------------------------------

def schema_version(board: Optional[dict]) -> str:
    """`"1.0"` when the board opts in, `"0.9"` when the field is absent."""
    value = (board or {}).get("schema_version")
    return value if value in SCHEMAS else SCHEMA_09


def is_legacy(board: Optional[dict]) -> bool:
    return schema_version(board) == SCHEMA_09


def task_id_pattern(board: Optional[dict]):
    return ID_10 if schema_version(board) == SCHEMA_10 else ID_09


def stage_ids(board: Optional[dict]) -> List[str]:
    """Ids of the declared stages, in board order."""
    out = []
    for stage in (board or {}).get("stages") or []:
        if isinstance(stage, dict) and isinstance(stage.get("id"), str):
            out.append(stage["id"])
    return out


def stage_of_task(board: Optional[dict], task: dict):
    """The stage a task belongs to: an int (classic) or a stages[].id (1.0)."""
    return (task or {}).get("stage")


def stage_key(stage) -> str:
    """Comparison key for a stage reference (`1` and `"1"` are different kinds)."""
    return f"stage:{stage}" if isinstance(stage, int) else f"id:{stage}"


def package_paths(board: Optional[dict]) -> List[str]:
    out = []
    for package in (board or {}).get("packages") or []:
        if isinstance(package, dict) and isinstance(package.get("path"), str):
            out.append(package["path"])
    return out


def task_package(board: Optional[dict], task: dict) -> Optional[str]:
    """The package path a task belongs to, or None."""
    value = (task or {}).get("package")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def resources(board: Optional[dict]) -> dict:
    """Runtime resources of the board with the defaults of PL-02."""
    raw = (board or {}).get("resources")
    raw = raw if isinstance(raw, dict) else {}
    services = raw.get("services")
    services = services if isinstance(services, dict) else {}
    return {
        "slots": raw.get("slots", 3),
        "port_base": raw.get("port_base", 4000),
        "port_stride": raw.get("port_stride", 100),
        "services": {str(k): v for k, v in services.items() if isinstance(v, int)},
        "infra_patterns": [p for p in raw.get("infra_patterns") or [] if isinstance(p, str)],
    }


# ---------------------------------------------------------------------------
# schema validation
# ---------------------------------------------------------------------------

def _is_str(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _needs_100(label: str, field: str) -> str:
    return f"{label}: field {field!r} needs schema version 1.0 — set schema_version to 1.0"


def _check_task(task, version: str, known_ids: set, errors: List[str], stage_id_set: set,
                package_set: set) -> None:
    if not isinstance(task, dict):
        errors.append(f"board.json: task entry is not an object: {task!r}")
        return
    tid = task.get("id", "?")
    label = f"board.json: task {tid}"
    allowed = TASK_FIELDS_10 if version == SCHEMA_10 else TASK_FIELDS_09
    for field in sorted(set(task) - allowed):
        if version == SCHEMA_09 and field in TASK_FIELDS_10:
            errors.append(_needs_100(label, field))
        else:
            errors.append(f"{label}: unknown field {field!r}")
    for field in TASK_REQUIRED:
        if field not in task:
            errors.append(f"{label}: mandatory field missing: {field}")

    pattern = ID_10 if version == SCHEMA_10 else ID_09
    if "id" not in task or not _is_str(task.get("id")) or not pattern.match(task["id"]):
        hint = "e.g. M03, P3-02, ENG-14" if version == SCHEMA_10 else "e.g. M03"
        errors.append(f"{label}: id must match {pattern.pattern} ({hint}), is {task.get('id')!r}")

    title = task.get("title")
    if title is not None and (not isinstance(title, str) or not 3 <= len(title) <= 120):
        errors.append(f"{label}: title must be a string of 3–120 characters")
    goal = task.get("goal")
    if goal is not None and (not isinstance(goal, str) or len(goal) < 3):
        errors.append(f"{label}: goal must be a string of at least 3 characters")

    if "status" in task and task.get("status") not in STATUSES:
        errors.append(f"{label}: unknown status {task.get('status')!r}")

    if "depends_on" in task:
        if not _is_str_list(task.get("depends_on")):
            errors.append(f"{label}: depends_on must be a list of strings")
        else:
            for dep in task["depends_on"]:
                if dep not in known_ids:
                    errors.append(f"{label}: unknown dependency {dep}")

    complexity = task.get("complexity")
    if complexity is not None and not _is_int(complexity):
        errors.append(f"{label}: complexity must be an integer")
    elif isinstance(complexity, int) and not 1 <= complexity <= 10:
        errors.append(f"{label}: complexity must be 1–10")

    if "stage" in task:
        stage = task["stage"]
        if _is_int(stage):
            if stage < 1:
                errors.append(f"{label}: stage must be >= 1")
        elif isinstance(stage, str) and stage:
            if version == SCHEMA_09:
                errors.append(_needs_100(label, "stage") + " (a named stage needs schema 1.0)")
            elif stage not in stage_id_set:
                errors.append(f"{label}: unknown stage {stage!r} (not in stages[].id)")
        else:
            errors.append(f"{label}: stage must be an integer or a stages[].id")

    for field in ("scope_write", "acceptance", "gates"):
        value = task.get(field)
        if field == "scope_write" and isinstance(value, list) and not value:
            errors.append(f"{label}: {field} is empty")
        elif value is not None and not _is_str_list(value):
            errors.append(f"{label}: {field} must be a list of strings")
    for field in ("scope_read", "scope_write_forbidden", "satisfies", "evidence", "exclusive",
                  "resources", "contract_followups"):
        if field in task and not _is_str_list(task[field]):
            errors.append(f"{label}: {field} must be a list of strings")
    if "satisfies" in task and isinstance(task["satisfies"], list):
        for ref in task["satisfies"]:
            if isinstance(ref, str) and not re.match(r"^D[0-9]+$", ref):
                errors.append(f"{label}: satisfies entry {ref!r} is not a definition-of-done ID (D1, D2 …)")
    for field in ("owner", "branch", "worktree"):
        if field in task and task[field] is not None and not isinstance(task[field], str):
            errors.append(f"{label}: {field} must be a string or null")
    if "round" in task and not _is_int(task.get("round")):
        errors.append(f"{label}: round must be an integer")
    if "parallel_group" in task and task["parallel_group"] is not None \
            and not isinstance(task["parallel_group"], str):
        errors.append(f"{label}: parallel_group must be a string or null")
    handoff = task.get("handoff")
    if handoff is not None:
        if not _is_str_list(handoff):
            errors.append(f"{label}: handoff must be a list of strings")
        elif len(handoff) > 3:
            errors.append(f"{label}: handoff has {len(handoff)} lines (max. 3)")
        elif any(len(line) > 200 for line in handoff):
            errors.append(f"{label}: handoff line longer than 200 characters")

    if "package" in task:
        package = task.get("package")
        if not _is_str(package):
            errors.append(f"{label}: package must be a non-empty string")
        elif package_set and package.rstrip("/") not in package_set:
            errors.append(f"{label}: unknown package {package!r} (not in packages[].path)")

    if "claim" in task:
        claim = task.get("claim")
        if not isinstance(claim, dict):
            errors.append(f"{label}: claim must be an object")
        else:
            for field in sorted(set(claim) - CLAIM_FIELDS):
                errors.append(f"{label}: claim has unknown field {field!r}")


def _check_stage(stage, index: int, ids: List[str], errors: List[str]) -> None:
    label = f"board.json: stage {index + 1}"
    if not isinstance(stage, dict):
        errors.append(f"{label} is not an object")
        return
    if _is_str(stage.get("id")):
        label = f"board.json: stage {stage['id']}"
        if ids.count(stage["id"]) > 1:
            errors.append(f"{label}: duplicate stage id")
    else:
        errors.append(f"{label}: id must be a non-empty string")
    for field in sorted(set(stage) - STAGE_FIELDS):
        errors.append(f"{label}: unknown field {field!r}")
    if not _is_str(stage.get("title")):
        errors.append(f"{label}: title must be a non-empty string")
    for field in ("exit_criteria", "exit_gates", "depends_on"):
        if field in stage and not _is_str_list(stage[field]):
            errors.append(f"{label}: {field} must be a list of strings")
    if "goal" in stage and not isinstance(stage["goal"], str):
        errors.append(f"{label}: goal must be a string")
    if "owner_decision" in stage and stage["owner_decision"] not in OWNER_DECISIONS:
        errors.append(f"{label}: owner_decision must be one of {sorted(OWNER_DECISIONS)}")


def _check_package(package, index: int, errors: List[str], paths: List[str]) -> None:
    label = f"board.json: package {index + 1}"
    if not isinstance(package, dict):
        errors.append(f"{label} is not an object")
        return
    path = package.get("path")
    if _is_str(path):
        label = f"board.json: package {path}"
        if paths.count(path) > 1:
            errors.append(f"{label}: duplicate package path")
    else:
        errors.append(f"{label}: path must be a non-empty string")
    for field in sorted(set(package) - PACKAGE_FIELDS):
        errors.append(f"{label}: unknown field {field!r}")
    if package.get("kind") not in PACKAGE_KINDS:
        errors.append(f"{label}: kind must be one of {sorted(PACKAGE_KINDS)}")
    if "may_import" in package and not _is_str_list(package["may_import"]):
        errors.append(f"{label}: may_import must be a list of package paths")


def _check_resources(raw, errors: List[str]) -> None:
    label = "board.json: resources"
    if not isinstance(raw, dict):
        errors.append(f"{label} must be an object")
        return
    for field in sorted(set(raw) - RESOURCE_FIELDS):
        errors.append(f"{label}: unknown field {field!r}")
    for field in ("slots", "port_base", "port_stride"):
        if field in raw and (not _is_int(raw[field]) or raw[field] < 1):
            errors.append(f"{label}: {field} must be a positive integer")
    if "slots" in raw and _is_int(raw["slots"]) and raw["slots"] > 64:
        errors.append(f"{label}: slots is {raw['slots']} (max. 64)")
    if "services" in raw:
        services = raw["services"]
        if not isinstance(services, dict):
            errors.append(f"{label}: services must be an object of {name: port offset}")
        else:
            for name, offset in services.items():
                if not _is_int(offset) or offset < 0:
                    errors.append(f"{label}: service {name!r} needs a non-negative integer offset")
    if "infra_patterns" in raw and not _is_str_list(raw["infra_patterns"]):
        errors.append(f"{label}: infra_patterns must be a list of strings")


def _check_budgets(raw, errors: List[str]) -> None:
    label = "board.json: budgets"
    if not isinstance(raw, dict):
        errors.append(f"{label} must be an object")
        return
    for key, value in raw.items():
        if key not in BUDGET_KEYS:
            errors.append(f"{label}: unknown budget {key!r} (known: {', '.join(sorted(BUDGET_KEYS))})")
            continue
        if not isinstance(value, dict):
            errors.append(f"{label}: budget {key!r} must be an object with limit and reason")
            continue
        for field in sorted(set(value) - {"limit", "reason"}):
            errors.append(f"{label}: budget {key!r} has unknown field {field!r}")
        if not _is_int(value.get("limit")) or value.get("limit", 0) < 1:
            errors.append(f"{label}: budget {key!r} needs a positive integer limit")
        if not _is_str(value.get("reason")):
            errors.append(f"{label}: budget {key!r} overrides the default without a reason")


def _check_contract(contract, index: int, errors: List[str]) -> None:
    label = f"board.json: contract {index + 1}"
    if not isinstance(contract, dict):
        errors.append(f"{label} is not an object")
        return
    if _is_str(contract.get("name")):
        label = f"board.json: contract {contract['name']}"
    else:
        errors.append(f"{label}: name must be a non-empty string")
    for field in sorted(set(contract) - CONTRACT_FIELDS):
        errors.append(f"{label}: unknown field {field!r}")
    if not _is_str(contract.get("path")):
        errors.append(f"{label}: path must be a non-empty string")
    if not isinstance(contract.get("version"), str) or not SEMVER.match(contract["version"] or ""):
        errors.append(f"{label}: version must be SemVer (e.g. 1.0.0)")
    for field in ("schema_files", "dependants"):
        if field in contract and not _is_str_list(contract[field]):
            errors.append(f"{label}: {field} must be a list of strings")
    if "fixtures_dir" in contract and not isinstance(contract["fixtures_dir"], str):
        errors.append(f"{label}: fixtures_dir must be a string")


def board_errors(board) -> List[str]:
    """Schema errors of a parsed board.json, [] when it is valid for its version.

    Strict per version: a field of schema 1.0 on a board without
    ``"schema_version": "1.0"`` is an error, and unknown fields are errors.
    """
    errors: List[str] = []
    if not isinstance(board, dict):
        return ["board.json: the board must be a JSON object"]

    version = schema_version(board)
    if board.get("schema_version") == SCHEMA_09:
        errors.append(
            "board.json: schema_version 0.9 is written by omitting the field; "
            "set schema_version to 1.0 to use the new fields")
    elif "schema_version" in board and board["schema_version"] not in SCHEMAS:
        errors.append(
            f"board.json: unknown schema_version {board['schema_version']!r} "
            f"(known: {', '.join(SCHEMAS)}; omit the field for 0.9)")
    allowed = BOARD_FIELDS_10 if version == SCHEMA_10 else BOARD_FIELDS_09
    for field in sorted(set(board) - allowed):
        if version == SCHEMA_09 and field in BOARD_FIELDS_10:
            errors.append(_needs_100("board.json", field))
        else:
            errors.append(f"board.json: unknown field {field!r}")

    for field in BOARD_REQUIRED:
        if field not in board:
            errors.append(f"board.json: mandatory field missing: {field}")
    if "project" in board and not _is_str(board.get("project")):
        errors.append("board.json: project must be a non-empty string")
    if "profile" in board and board.get("profile") not in PROFILES:
        errors.append("board.json: profile must be S, M or L")
    if "base_branch" in board and not _is_str(board.get("base_branch")):
        errors.append("board.json: base_branch must be a non-empty string")
    if "generator_version" in board:
        value = board["generator_version"]
        if value is not None and (not isinstance(value, str) or not SEMVER.match(value)):
            errors.append("board.json: generator_version must be SemVer (e.g. 0.9.0)")
    if "stage" in board and (not _is_int(board["stage"]) or board["stage"] < 1):
        errors.append("board.json: stage must be a positive integer")
    if "worktrees" in board and board["worktrees"] not in WORKTREE_MODES:
        errors.append(
            f"board.json: worktrees must be one of {sorted(WORKTREE_MODES)} (is {board['worktrees']!r})")

    tasks = board.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("board.json: tasks is missing or empty")
        return errors
    task_ids = [t.get("id") for t in tasks if isinstance(t, dict)]
    known_ids = set(task_ids)
    if len(known_ids) != len(task_ids):
        errors.append("board.json: duplicate task IDs")

    stages = board.get("stages")
    stage_id_list: List[str] = []
    if stages is not None:
        if not isinstance(stages, list):
            errors.append("board.json: stages must be an array")
            stages = []
        stage_id_list = [s.get("id") for s in stages if isinstance(s, dict)]
        for index, stage in enumerate(stages):
            _check_stage(stage, index, stage_id_list, errors)
        stage_set = set(stage_id_list)
        for index, stage in enumerate(stages):
            if isinstance(stage, dict):
                for dep in stage.get("depends_on") or []:
                    if isinstance(dep, str) and dep not in stage_set:
                        errors.append(
                            f"board.json: stage {stage.get('id')!r}: unknown stage dependency {dep!r}")

    packages = board.get("packages")
    package_list: List[str] = []
    if packages is not None:
        if not isinstance(packages, list):
            errors.append("board.json: packages must be an array")
            packages = []
        package_list = [p.get("path") for p in packages if isinstance(p, dict)]
        for index, package in enumerate(packages):
            _check_package(package, index, errors, package_list)

    if "resources" in board:
        _check_resources(board["resources"], errors)
    if "budgets" in board:
        _check_budgets(board["budgets"], errors)
    if "contracts" in board:
        contracts = board["contracts"]
        if not isinstance(contracts, list):
            errors.append("board.json: contracts must be an array")
        else:
            for index, contract in enumerate(contracts):
                _check_contract(contract, index, errors)

    for task in tasks:
        _check_task(task, version, known_ids, errors, set(stage_id_list), set(package_list))
    return errors
