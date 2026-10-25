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

from core.board import board_errors  # noqa: E402
from core.evidence import verify_evidence  # noqa: E402

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


# Context budgets. Tokens are estimated as characters / 4, a rough rule of thumb.
STATUS_WORD_LIMIT = 300          # STATUS.md is read in every session
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
    if status.read_text(encoding="utf-8").strip() != module.render(board).strip():
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


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors: list[str] = []
    warnings: list[str] = []

    for name in REQUIRED:
        if not (root / name).exists():
            errors.append(f"mandatory file missing: {name}")

    if (root / "ARCHITECTURE.md").exists():
        count = words(root / "ARCHITECTURE.md")
        if count > 800:
            errors.append(f"ARCHITECTURE.md: {count} words (max. 800)")
        elif count < 300:
            warnings.append(f"ARCHITECTURE.md: only {count} words — fine for a small project, otherwise check.")

    if (root / "AGENTS.md").exists():
        count = words(root / "AGENTS.md")
        if count > 400:
            warnings.append(f"AGENTS.md: {count} words (target max. 400)")

    if (root / "STATUS.md").exists():
        count = words(root / "STATUS.md")
        if count > STATUS_WORD_LIMIT:
            warnings.append(f"STATUS.md: {count} words (target max. {STATUS_WORD_LIMIT}); it is read in every session")

    for brief in sorted((root / "tasks").glob("*.md")):
        count = words(brief)
        if not 400 <= count <= 800:
            errors.append(f"{brief.relative_to(root)}: {count} words (target 400–800)")

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
        try:
            board = json.loads((root / "board.json").read_text(encoding="utf-8"))
        except ValueError:
            board = None
        if isinstance(board, dict):
            check_consistency(root, board, errors, warnings)
            check_context_packs(root, board, warnings)
            check_evidence(root, board, errors, warnings)
            check_version(board, warnings)
            check_status_fresh(root, board, errors)

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
