#!/usr/bin/env python3
"""Check a generated project against the rules of Polier.

Usage:
    python3 tools/check.py examples/minimal-cli
    python3 tools/check.py /path/to/project

No external dependencies. Exit 0 = no errors (warnings allowed),
exit 1 = at least one error.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # PL-15: optional, so a package without tools/drift.py still checks
    import drift as _drift  # noqa: E402
except Exception:  # noqa: BLE001
    _drift = None

from core import approvals, audit, dispatch, runs  # noqa: E402
from core.board import board_errors, stage_report, task_stage_id  # noqa: E402
from core.errors import PolierError  # noqa: E402
from core.evidence import verify_evidence  # noqa: E402
from core.policy import (POLICY, checks as policy_checks, limits as policy_limits,
                         load_policy, policy_errors)  # noqa: E402

REQUIRED = [
    "ARCHITECTURE.md",
    "AGENTS.md",
    "STATUS.md",
    "board.json",
    ".gitignore",
    "docs/module-map.md",
    "docs/quality.md",
]

PLACEHOLDER = re.compile(r"<\.\.\.>|<Name>|<Project name>|\bTODO\b|\bTBD\b")
STATUS = {
    "pending", "claimed", "in_progress", "verifying", "review",
    "rework", "done", "blocked", "failed",
}
QUESTION_STATUS = {"open", "answered", "dropped"}


# Word budgets per profile (PL-09). A board may override one with a reason.
BUDGETS = {
    "S": {"architecture": 600, "agents": 300, "status": 300, "brief": 800,
          "package_architecture": 400, "package_agents": 200},
    "M": {"architecture": 700, "agents": 350, "status": 500, "brief": 800,
          "package_architecture": 400, "package_agents": 200},
    "L": {"architecture": 800, "agents": 400, "status": 900, "brief": 900,
          "package_architecture": 400, "package_agents": 200},
}
BUDGET_MINIMUM = {"architecture": 300, "brief": 400}

# Context budgets. Tokens are estimated as characters / 4, a rough rule of thumb.
PACK_TOKEN_WARN = 15000          # context pack of one task; the worker budget of 30k input also holds prompt, tools and conversation
HANDOFF_MAX_LINES = 3
HANDOFF_MAX_CHARS = 200
TEXT_SUFFIXES = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".rs", ".go", ".java", ".kt", ".swift", ".c", ".h", ".cpp", ".cs", ".rb", ".php",
    ".sh", ".sql", ".html", ".css", ".cfg", ".ini",
}
MAX_FILE_BYTES = 200_000

def words(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").split())

def estimate_tokens(path: Path) -> int:
    """Rough token estimate of a file or folder; skips binary and very large files."""
    if path.is_dir():
        return sum(estimate_tokens(p) for p in sorted(path.rglob("*")) if p.is_file())
    if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > MAX_FILE_BYTES:
        return 0
    try:
        return len(path.read_text(encoding="utf-8")) // 4
    except (UnicodeDecodeError, OSError):
        return 0


def normalized(path: str) -> str:
    return path.strip().replace("\\", "/").rstrip("/")


def under(path: str, folder: str) -> bool:
    """True when `path` is `folder` or lies below it."""
    path, folder = normalized(path), normalized(folder)
    return path == folder or path.startswith(folder + "/")


def budget_limits(board: dict) -> tuple[dict, list[str]]:
    """Word budgets of the project profile, with the board's reasoned overrides."""
    profile = board.get("profile") if board.get("profile") in BUDGETS else "S"
    limits = dict(BUDGETS[profile])
    overrides: list[str] = []
    raw = board.get("budgets")
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in limits and isinstance(value, dict) and isinstance(value.get("limit"), int):
                limits[key] = value["limit"]
                overrides.append(
                    f"budgets.{key} overridden to {value['limit']} words "
                    f"(reason: {value.get('reason', '')})")
    return limits, overrides


def check_packages(root: Path, board: dict, errors: list[str], warnings: list[str]) -> None:
    """Per-package layout (PL-06): folders exist, task scopes stay inside their package."""
    packages = board.get("packages") if isinstance(board.get("packages"), list) else []
    profile = board.get("profile")
    if profile == "L" and not packages:
        errors.append("board.json: profile L needs packages[] (the package map) — see templates/monorepo-layout.md")
        return
    tasks = [t for t in board.get("tasks", []) if isinstance(t, dict)]
    contracts = [c for c in board.get("contracts", []) if isinstance(c, dict)] \
        if isinstance(board.get("contracts"), list) else []
    contract_paths = [c.get("path") for c in contracts if isinstance(c.get("path"), str)]
    limits, _overrides = budget_limits(board)

    module_map = root / "docs/module-map.md"
    module_text = module_map.read_text(encoding="utf-8") if module_map.exists() else ""

    for package in packages:
        if not isinstance(package, dict):
            continue
        path = package.get("path")
        if not isinstance(path, str) or not path:
            continue
        folder = root / normalized(path)
        creates = any(
            under(str(scope), path)
            for task in tasks for scope in task.get("scope_write") or []
            if isinstance(scope, str))
        if not folder.exists():
            if not creates:
                errors.append(
                    f"board.json: package folder {path} does not exist and no task creates it in scope_write")
            continue
        if profile == "L":
            arch = folder / "ARCHITECTURE.md"
            if not arch.exists():
                errors.append(f"{path}: package ARCHITECTURE.md is missing (purpose, inputs, outputs, invariants)")
            elif words(arch) > limits["package_architecture"]:
                errors.append(f"{path}/ARCHITECTURE.md: {words(arch)} words (max. {limits['package_architecture']})")
            agents = folder / "AGENTS.md"
            if agents.exists() and words(agents) > limits["package_agents"]:
                warnings.append(f"{path}/AGENTS.md: {words(agents)} words (target max. {limits['package_agents']})")
        if module_text and path not in module_text:
            warnings.append(f"docs/module-map.md: package {path} is not listed in the package map")

    package_paths = {p.get("path") for p in packages if isinstance(p, dict) and isinstance(p.get("path"), str)}
    for task in tasks:
        package = task.get("package")
        if not isinstance(package, str) or package not in package_paths:
            continue
        for scope in task.get("scope_write") or []:
            if not isinstance(scope, str):
                continue
            if under(scope, package):
                continue
            if any(under(scope, c) for c in contract_paths):
                continue
            errors.append(
                f"{task.get('id')}: scope_write {scope} is outside its package {package} "
                f"(add the contract path to board.json contracts[] if it is a shared contract)")


def check_drift(root: Path, warnings: list[str]) -> None:
    """Warn when the project-local generator copy differs from its manifest (PL-15)."""
    if _drift is None:
        return
    try:
        report = _drift.drift(root)
    except Exception:  # noqa: BLE001  never fail the project check because of drift
        return
    warnings.extend(report.get("warnings") or [])


def check_environments(root: Path, warnings: list[str]) -> None:
    """docs/environments.md: every environment needs a smoke URL (PL-11)."""
    path = root / "docs/environments.md"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if not cells:
            continue
        name = cells[0].lower()
        if name not in ("local", "preview", "staging", "production"):
            continue
        if not any("http://" in cell or "https://" in cell for cell in cells[1:]):
            warnings.append(
                f"docs/environments.md: environment {cells[0]} has no smoke URL — "
                f"run tools/smoke.py after every deployment")


def check_versions(root: Path, board: dict, warnings: list[str]) -> None:
    """Profile L: every manifest dependency must be pinned in docs/versions.md (PL-13)."""
    if board.get("profile") != "L":
        return
    versions = root / "docs/versions.md"
    if not versions.exists():
        warnings.append("docs/versions.md is missing (profile L: pin every tool and library with source URL and date)")
        return
    text = versions.read_text(encoding="utf-8").lower()
    names: set[str] = set()
    for manifest in sorted(root.rglob("package.json")):
        if "node_modules" in manifest.parts:
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for key in ("dependencies", "devDependencies"):
            for name in (data.get(key) or {}):
                names.add(name)
    for name in sorted(names):
        if name.lower() not in text:
            warnings.append(f"docs/versions.md: dependency {name} is in a manifest but not pinned with a source")


def check_stages(root: Path, board: dict, errors: list[str], warnings: list[str]) -> None:
    """Stage exit gates and stop points (PL-08)."""
    if not isinstance(board.get("stages"), list) or not board.get("stages"):
        return
    report = {entry["id"]: entry for entry in stage_report(board, root)}
    for sid, entry in report.items():
        if not entry["exit_gates"]:
            warnings.append(f"stage {sid}: no exit_gates declared — the stage cannot be checked mechanically")
    for task in board.get("tasks", []):
        if not isinstance(task, dict) or task.get("status") != "in_progress":
            continue
        sid = task_stage_id(board, task)
        entry = report.get(sid) if sid else None
        if entry is None:
            continue
        if entry["stopped"]:
            errors.append(f"{task.get('id')}: stage {sid} is stopped by the owner — do not work there")
        elif entry["incomplete_deps"]:
            errors.append(
                f"{task.get('id')}: stage {sid} needs stage(s) {', '.join(entry['incomplete_deps'])} complete first")


def paths_overlap(a: str, b: str) -> bool:
    a, b = normalized(a), normalized(b)
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def check_links(root: Path, errors: list[str]) -> None:
    for path in root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text):
            target = target.strip()
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / target).resolve().exists():
                errors.append(f"{path.relative_to(root)}: broken link: {target}")


def check_git(root: Path, warnings: list[str]) -> None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        warnings.append("git not found; repo check skipped")
        return
    if result.stdout.strip() != "true":
        warnings.append("no git repository: run git init and commit `chore: scaffold`")


def check_board(root: Path, errors: list[str], warnings: list[str]) -> None:
    path = root / "board.json"
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"board.json: invalid JSON: {exc}")
        return

    # Schema version, allowed fields, ID pattern, stage/package references.
    schema = board_errors(board)
    if schema:
        errors.extend(schema)
        return

    tasks = board["tasks"]
    known = {t.get("id") for t in tasks}
    needed_by_others = {d for t in tasks for d in t.get("depends_on", []) if isinstance(t, dict)}

    for task in tasks:
        tid = task.get("id", "?")
        if task.get("status") == "done" and tid in needed_by_others and not task.get("handoff"):
            warnings.append(f"{tid}: done and other tasks depend on it, but no handoff (max. {HANDOFF_MAX_LINES} lines)")
        if task["complexity"] >= 7:
            errors.append(f"{tid}: complexity >= 7 — split the task")
        if task.get("status") == "done" and not task.get("evidence"):
            errors.append(f"{tid}: status done without evidence — record the gate output")

        for allowed in task.get("scope_write", []):
            for forbidden in task.get("scope_write_forbidden", []):
                if paths_overlap(allowed, forbidden):
                    errors.append(
                        f"{tid}: path is in both scope_write and scope_write_forbidden: {allowed} / {forbidden}"
                    )

    # Cycles
    graph = {t["id"]: t.get("depends_on", []) for t in tasks if "id" in t}
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        if state.get(node) == 1:
            errors.append("board.json: cycle: " + " -> ".join(stack + [node]))
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in graph.get(node, []):
            if dep in graph:
                visit(dep, stack + [node])
        state[node] = 2

    for node in graph:
        visit(node, [])

    # Overlapping write scopes within the same parallel group
    groups: dict[str, list[dict]] = {}
    for task in tasks:
        group = task.get("parallel_group")
        if group:
            groups.setdefault(group, []).append(task)
    for group, group_tasks in groups.items():
        for i, a in enumerate(group_tasks):
            for b in group_tasks[i + 1:]:
                for pa in a.get("scope_write", []):
                    for pb in b.get("scope_write", []):
                        if paths_overlap(pa, pb):
                            errors.append(
                                f"parallel group {group}: scope overlap {a.get('id')} / {b.get('id')}: {pa} vs {pb}"
                            )

    # An S side strand needs a shared contract task
    if board.get("profile") == "S":
        by_id = {t.get("id"): t for t in tasks if isinstance(t, dict)}
        for group, group_tasks in groups.items():
            if len(group_tasks) < 2:
                continue
            common = set(group_tasks[0].get("depends_on", []))
            for task in group_tasks[1:]:
                common &= set(task.get("depends_on", []))
            contracts = [
                tid for tid in common
                if tid in by_id and any(
                    str(path).startswith("docs/contracts/")
                    for path in by_id[tid].get("scope_write", [])
                )
            ]
            if not contracts:
                errors.append(
                    f"parallel group {group}: an S side strand needs a shared contract task "
                    f"with scope_write under docs/contracts/ that both tasks depend on via depends_on."
                )

    # Decisions and open questions (optional, but checked if present)
    for decision in board.get("decisions", []):
        if not isinstance(decision, dict):
            errors.append("board.json: decisions entry is not an object")
            continue
        for key in ("date", "id", "title"):
            if key not in decision:
                errors.append(f"board.json: decision {decision.get('id', '?')} is missing {key}")
        file = decision.get("file")
        if file and not (root / file).exists():
            errors.append(f"board.json: ADR file missing: {file}")

    for question in board.get("open_questions", []):
        if not isinstance(question, dict):
            errors.append("board.json: open_questions entry is not an object")
            continue
        qid = question.get("id", "?")
        if "question" not in question:
            errors.append(f"board.json: question {qid} has no text")
        if question.get("status") not in QUESTION_STATUS:
            errors.append(f"board.json: question {qid} has an invalid status")
        for blocked in question.get("blocks", []):
            if blocked not in known:
                errors.append(f"board.json: question {qid} blocks unknown task {blocked}")


def ids_in(pattern: str, text: str) -> list[str]:
    return re.findall(pattern, text, re.MULTILINE)


def backticked(line: str) -> set[str]:
    return {normalized(p) for p in re.findall(r"`([^`]+)`", line)}


def field_line(text: str, label: str) -> str | None:
    match = re.search(rf"^.*\*\*{label}:\*\*(.*)$", text, re.MULTILINE)
    return match.group(1) if match else None


def check_status_fresh(root: Path, board: dict, errors: list[str]) -> None:
    status = root / "STATUS.md"
    if not status.exists():
        return
    spec = importlib.util.spec_from_file_location(
        "render_status", Path(__file__).with_name("render_status.py"))
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    current = status.read_text(encoding="utf-8")
    strip = getattr(module, "strip_claims", lambda text: text)
    if strip(current).strip() != module.render(board, root, with_claims=False).strip():
        errors.append("STATUS.md is out of date with board.json — run tools/render_status.py")


def check_version(board: dict, warnings: list[str]) -> None:
    package = Path(__file__).resolve().parent.parent / "VERSION"
    if not package.exists():
        return
    current = package.read_text(encoding="utf-8").strip()
    used = board.get("generator_version")
    if not used:
        warnings.append(f"board.json: generator_version missing (package is {current}); see CHANGELOG.md")
    elif used != current:
        warnings.append(
            f"board.json: project uses generator {used}, package is {current}; see CHANGELOG.md before updating")


def check_consistency(root: Path, board: dict, errors: list[str], warnings: list[str]) -> None:
    """Cross-artifact checks: briefs vs board, AD/ADR references, DoD traceability."""
    tasks = {t.get("id"): t for t in board.get("tasks", []) if isinstance(t, dict)}

    # Task briefs must agree with their board entry
    for brief in sorted((root / "tasks").glob("*.md")):
        rel = brief.relative_to(root)
        text = brief.read_text(encoding="utf-8")
        heading = re.match(r"#\s+([A-Za-z][A-Za-z0-9-]*)\s+—\s+(.+)", text)
        if not heading:
            errors.append(f"{rel}: first line must be '# <ID> — <title>'")
            continue
        tid, title = heading.group(1), heading.group(2).strip()
        task = tasks.get(tid)
        if task is None:
            errors.append(f"{rel}: task {tid} is not on the board")
            continue
        if brief.stem != tid:
            errors.append(f"{rel}: file name does not match task ID {tid}")
        if title != task.get("title"):
            errors.append(f"{rel}: title {title!r} differs from board.json {task.get('title')!r}")

        brief_acc = ids_in(r"^(A\d+)\s+WHEN\b", text)
        if brief_acc != task.get("acceptance", []):
            errors.append(
                f"{rel}: acceptance {brief_acc} differs from board.json {task.get('acceptance', [])}")

        scope = field_line(text, "Scope")
        if scope is None:
            errors.append(f"{rel}: '**Scope:**' line is missing")
        elif backticked(scope) != {normalized(p) for p in task.get("scope_write", [])}:
            errors.append(f"{rel}: scope {sorted(backticked(scope))} differs from board.json scope_write")

        satisfies = field_line(text, "Satisfies")
        brief_sat = sorted(set(ids_in(r"\b(D\d+)\b", satisfies or "")))
        if brief_sat != sorted(set(task.get("satisfies", []))):
            errors.append(
                f"{rel}: satisfies {brief_sat} differs from board.json {sorted(task.get('satisfies', []))}")

    # Every AD-n reference must be defined in ARCHITECTURE.md
    sources = [root / "board.json", root / "AGENTS.md",
               *sorted((root / "tasks").glob("*.md")), *sorted((root / "docs").rglob("*.md"))]
    sources = [p for p in sources if p.exists()]
    arch = root / "ARCHITECTURE.md"
    defined_ad = set(ids_in(r"^\|\s*(AD-\d+)\s*\|", arch.read_text(encoding="utf-8"))) if arch.exists() else set()
    for path in sources:
        for ref in sorted(set(ids_in(r"\b(AD-\d+)\b", path.read_text(encoding="utf-8"))) - defined_ad):
            errors.append(f"{path.relative_to(root)}: {ref} is not defined in ARCHITECTURE.md")

    # Every ADR reference must exist as a decision on the board or a file in docs/adr/
    defined_adr = {d.get("id") for d in board.get("decisions", []) if isinstance(d, dict)}
    defined_adr |= {m.group(1) for p in (root / "docs/adr").glob("ADR-*.md")
                    if (m := re.match(r"(ADR-\d{3,4})", p.name))}
    for path in [*sources, arch]:
        if not path.exists():
            continue
        for ref in sorted(set(ids_in(r"\b(ADR-\d{3,4})\b", path.read_text(encoding="utf-8"))) - defined_adr):
            errors.append(f"{path.relative_to(root)}: {ref} has no decision on the board and no file in docs/adr/")

    # Traceability: definition-of-done scenarios D1..Dn ↔ tasks
    quality = root / "docs/quality.md"
    if not quality.exists():
        return
    dod = set(ids_in(r"^\s*(?:[-*]|\d+\.)?\s*\**(D\d+)\**[\s:.]", quality.read_text(encoding="utf-8")))
    if not dod:
        warnings.append("docs/quality.md: no definition-of-done IDs (D1, D2 …); traceability skipped")
        return
    covered: set[str] = set()
    for tid, task in tasks.items():
        sat = task.get("satisfies", [])
        if not sat:
            errors.append(f"{tid}: satisfies is missing — which definition-of-done item does it serve?")
        for ref in sat:
            if ref not in dod:
                errors.append(f"{tid}: satisfies unknown definition-of-done item {ref}")
        covered |= set(sat)
    for ref in sorted(dod - covered, key=lambda r: int(r[1:])):
        errors.append(f"docs/quality.md: {ref} is not covered by any task (satisfies)")


def check_context_packs(root: Path, board: dict, warnings: list[str]) -> None:
    """Warn when what a worker must load for one task grows large (estimate)."""
    base = [root / n for n in ("ARCHITECTURE.md", "AGENTS.md", "STATUS.md", "docs/module-map.md")]
    base_tokens = sum(estimate_tokens(p) for p in base if p.exists())
    for task in board.get("tasks", []):
        if not isinstance(task, dict) or task.get("status") == "done":
            continue
        tid = task.get("id", "?")
        brief = root / "tasks" / f"{tid}.md"
        if not brief.exists():
            continue
        reads = [root / normalized(p) for p in task.get("scope_read", []) if isinstance(p, str)]
        extra = {p for p in reads if p.exists() and p not in base}
        total = base_tokens + estimate_tokens(brief) + sum(estimate_tokens(p) for p in extra)
        if total > PACK_TOKEN_WARN:
            warnings.append(
                f"{tid}: context pack is about {total} tokens (warning at {PACK_TOKEN_WARN}); "
                f"trim scope_read, split the task or shorten the base files")

def check_evidence(root: Path, board: dict, errors: list[str], warnings: list[str]) -> None:
    """Done tasks: evidence must point to gate.py records that passed and match their logs."""
    found_errors, found_warnings = verify_evidence(root, board)
    errors.extend(found_errors)
    warnings.extend(found_warnings)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_runs(root: Path, board: dict, errors: list[str]) -> None:
    """Validate every ``runs/<ID>.json``: JSON, task vs file name, state, attempts."""
    folder = root / "runs"
    if not folder.is_dir():
        return
    known = {task.get("id") for task in board.get("tasks") or [] if isinstance(task, dict)}
    for path in sorted(folder.glob("*.json")):
        rel = path.relative_to(root).as_posix()
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            errors.append(f"{rel}: cannot be read ({exc})")
            continue
        except ValueError as exc:
            errors.append(f"{rel}: invalid JSON ({exc})")
            continue
        if not isinstance(record, dict):
            errors.append(f"{rel}: must be a JSON object")
            continue
        task = record.get("task")
        if task != path.stem:
            errors.append(f"{rel}: task {task!r} does not match the file name {path.stem!r}")
        if task not in known:
            errors.append(f"{rel}: task {task!r} is not on the board")
        state = record.get("state")
        if state not in runs.STATES:
            errors.append(f"{rel}: unknown state {state!r} (known: {', '.join(runs.STATES)})")
        attempt = record.get("attempt")
        if not _is_int(attempt) or attempt < 0:
            errors.append(f"{rel}: attempt must be a non-negative integer (is {attempt!r})")
        attempts = record.get("attempts")
        if not isinstance(attempts, list):
            errors.append(f"{rel}: attempts must be a list")
            continue
        for index, entry in enumerate(attempts, 1):
            number = entry.get("n") if isinstance(entry, dict) else None
            if not _is_int(number) or number < 1:
                errors.append(f"{rel}: attempts[{index - 1}] needs an integer n")


def _check_attempt_limits(root: Path, board: dict, policy: dict, errors: list[str]) -> None:
    """A run record may never use more attempts than the policy allows."""
    limit = policy_limits(policy)["max_attempts_per_task"]
    for task in board.get("tasks") or []:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        tid = task["id"]
        try:
            used = runs.attempt_count(root, tid)
        except PolierError:
            continue
        if used > limit:
            errors.append(f"{tid}: {used} attempts used (max_attempts_per_task is {limit}) — "
                          f"escalate instead of another attempt")


def _check_running_scopes(board: dict, errors: list[str]) -> None:
    """Two tasks may not be in progress at the same time if their write scopes overlap."""
    running = [task for task in board.get("tasks") or []
               if isinstance(task, dict) and task.get("status") == "in_progress"]
    for index, left in enumerate(running):
        for right in running[index + 1:]:
            overlap = None
            for first in left.get("scope_write") or []:
                for second in right.get("scope_write") or []:
                    if (isinstance(first, str) and isinstance(second, str)
                            and paths_overlap(first, second)):
                        overlap = (first, second)
                        break
                if overlap:
                    break
            if overlap:
                errors.append(
                    f"{left.get('id')} and {right.get('id')} are both in_progress with "
                    f"overlapping scope_write: {overlap[0]} / {overlap[1]}")


def _check_dispatch(root: Path, board: dict, policy: dict,
                    errors: list[str], warnings: list[str]) -> None:
    """Scope conflicts between parallel tasks are errors; blocked tasks are warnings."""
    try:
        report = dispatch.plan(root, board, policy)
    except (PolierError, OSError) as exc:
        warnings.append(f"dispatch: the plan could not be built ({exc})")
        return
    if policy_checks(policy)["disjoint_scopes"]:
        for conflict in report.get("conflicts") or []:
            paths = ", ".join(str(entry) for entry in conflict.get("paths") or [])
            errors.append(f"dispatch: {conflict.get('a')} and {conflict.get('b')} share "
                          f"{paths} in one parallel group")
    for entry in report.get("blocked") or []:
        warnings.append(f"dispatch: {entry.get('id')} is blocked — {entry.get('reason')}")


def _check_orchestration_docs(root: Path, warnings: list[str]) -> None:
    """Name the 1.1 files in the project docs; missing references are warnings only."""
    agents = root / "AGENTS.md"
    readme = root / "README.md"
    try:
        agents_text = agents.read_text(encoding="utf-8") if agents.is_file() else ""
        readme_text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    except OSError:
        return
    if agents.is_file() and "tools/state.py" not in agents_text:
        warnings.append("AGENTS.md: tools/state.py is not mentioned — 1.1 state changes go through it")
    orchestration = root / "docs/orchestration.md"
    if not orchestration.is_file():
        warnings.append("docs/orchestration.md is missing — the one-page orchestration model belongs there")
    combined = f"{agents_text}\n{readme_text}"
    if combined.strip() and "runs/" not in combined:
        warnings.append("AGENTS.md/README.md: runs/ is not mentioned — run records are committed with the task")
    if combined.strip() and "policy.json" not in combined:
        warnings.append("AGENTS.md/README.md: policy.json is not mentioned — the limits and rules live there")
    if orchestration.is_file() and combined.strip() and "orchestration.md" not in combined:
        warnings.append("AGENTS.md/README.md: docs/orchestration.md is not mentioned — point at the one-page loop")


def check_orchestration(root: Path, board: dict, errors: list[str], warnings: list[str]) -> None:
    """1.1 checks: policy, audit, approvals, run records, scopes, dispatch and docs.

    Everything past the policy warning runs only when ``policy.json`` exists, so
    a 0.9/1.0 project keeps its 1.0 result (warnings only, exit 0).
    """
    if not (root / POLICY).is_file():
        warnings.append("policy.json is missing — the 1.1 orchestration checks are off "
                        "(a 1.0 project keeps working)")
        return
    try:
        policy = load_policy(root)
    except PolierError as exc:
        errors.append(str(exc))
        return
    problems = policy_errors(policy)
    if problems:
        errors.extend(problems)
        return

    try:
        report = audit.audit(root, board, policy)
    except PolierError as exc:
        errors.append(f"audit: {exc}")
    else:
        errors.extend(report.get("errors") or [])
        warnings.extend(report.get("warnings") or [])

    errors.extend(approvals.errors(root, board))
    _check_runs(root, board, errors)
    _check_attempt_limits(root, board, policy, errors)
    _check_running_scopes(board, errors)
    _check_dispatch(root, board, policy, errors, warnings)
    _check_orchestration_docs(root, warnings)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors: list[str] = []
    warnings: list[str] = []

    for name in REQUIRED:
        if not (root / name).exists():
            errors.append(f"mandatory file missing: {name}")

    board: dict | None = None
    if (root / "board.json").exists():
        try:
            loaded = json.loads((root / "board.json").read_text(encoding="utf-8"))
        except ValueError:
            loaded = None
        board = loaded if isinstance(loaded, dict) else None
    limits, overrides = budget_limits(board or {})
    for line in overrides:
        warnings.append(line)

    if (root / "ARCHITECTURE.md").exists():
        count = words(root / "ARCHITECTURE.md")
        if count > limits["architecture"]:
            errors.append(f"ARCHITECTURE.md: {count} words (max. {limits['architecture']} for profile {(board or {}).get('profile', 'S')})")
        elif count < BUDGET_MINIMUM["architecture"]:
            warnings.append(f"ARCHITECTURE.md: only {count} words — fine for a small project, otherwise check.")

    if (root / "AGENTS.md").exists():
        count = words(root / "AGENTS.md")
        if count > limits["agents"]:
            warnings.append(f"AGENTS.md: {count} words (target max. {limits['agents']})")

    if (root / "STATUS.md").exists():
        count = words(root / "STATUS.md")
        if count > limits["status"]:
            warnings.append(f"STATUS.md: {count} words (target max. {limits['status']}); it is read in every session")

    for brief in sorted((root / "tasks").glob("*.md")):
        count = words(brief)
        if count > limits["brief"] or count < BUDGET_MINIMUM["brief"]:
            errors.append(f"{brief.relative_to(root)}: {count} words (target {BUDGET_MINIMUM['brief']}–{limits['brief']})")

    for path in [root / "ARCHITECTURE.md", root / "AGENTS.md", root / "STATUS.md",
                 *sorted((root / "tasks").glob("*.md"))]:
        if path.exists():
            for match in PLACEHOLDER.finditer(path.read_text(encoding="utf-8")):
                errors.append(f"{path.relative_to(root)}: placeholder found: {match.group(0)}")

    if (root / "AGENTS.md").exists():
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        for needle in ("git status", "commit", "scope"):
            if needle not in agents.lower():
                errors.append(f"AGENTS.md: '{needle}' is missing")

    if (root / "docs/module-map.md").exists():
        module_map = (root / "docs/module-map.md").read_text(encoding="utf-8").lower()
        for needle in ("UI", "logic", "data"):
            if needle.lower() not in module_map:
                errors.append(f"docs/module-map.md: layer '{needle}' is missing")

    if (root / "board.json").exists():
        check_board(root, errors, warnings)
        if board is not None:
            check_consistency(root, board, errors, warnings)
            check_context_packs(root, board, warnings)
            check_evidence(root, board, errors, warnings)
            check_version(board, warnings)
            check_stages(root, board, errors, warnings)
            check_packages(root, board, errors, warnings)
            check_versions(root, board, warnings)
            check_status_fresh(root, board, errors)
            check_orchestration(root, board, errors, warnings)

    if board is not None and isinstance(board.get("resources"), dict):
        gitignore = root / ".gitignore"
        if gitignore.exists() and ".polier-slot" not in gitignore.read_text(encoding="utf-8"):
            warnings.append(".gitignore: runtime slot file .polier-slot is not ignored")
    check_environments(root, warnings)
    check_drift(root, warnings)
    check_links(root, errors)
    check_git(root, warnings)

    for warning in warnings:
        print(f"WARN: {warning}")

    if errors:
        print(f"FAIL: {len(errors)} finding(s) in {root}\n")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {root} passes the mandatory checks." + (f" ({len(warnings)} warning(s))" if warnings else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
