"""The quick track: the entry rule of ADR-0004 and the task it creates.

A quick task is an ordinary board task with ``track: quick``; it runs through
the same state machine, gates, review and handoff. ``qualifies`` decides
whether a request may use the track, ``create`` adds the task and its brief.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from . import factory
from .board import add_task, load_board, tasks_of
from .errors import PolierError
from .paths import inside, normalized
from .policy import load_policy, manifest_match, protected_match

NEXT = "pl_change new (tools/change.py new TITLE) to propose the change"

_BACKTICKED = re.compile(r"`([^`\n]+)`")
_PATHLIKE = re.compile(r"^[\w.\-]+(/[\w.\-]+)+/?$|^[\w\-]+\.[A-Za-z0-9]+$")
# statuses of a task that has changed, or is changing, its files
TOUCHED = {"done", "in_progress", "verifying", "review", "rework"}
_DOD = re.compile(r"^\s*(?:[-*]|\d+\.)?\s*\**(D\d+)\**[\s:.]", re.M)
_ID_NUMBER = re.compile(r"^M([0-9]+)$")


def _scope_paths(root: Path, scope: Sequence[str]) -> Tuple[List[str], List[str]]:
    """The normalized scope paths and the reasons the scope itself is unusable."""
    paths: List[str] = []
    reasons: List[str] = []
    if not scope:
        return paths, ["the scope is empty; name the files the change touches"]
    base = root.resolve()
    for raw in scope:
        rel = normalized(raw)
        if not rel or rel.startswith("/") or rel == ".." or rel.startswith("../") \
                or re.match(r"^[A-Za-z]:/", rel):
            reasons.append(f"{raw!r} is not a path inside the project")
            continue
        target = (base / rel).resolve()
        if base != target and base not in target.parents:
            reasons.append(f"{raw!r} is outside the project")
        elif target.is_dir():
            reasons.append(f"{rel} is a folder; the quick track names files")
        elif not target.is_file():
            reasons.append(f"{rel} does not exist; the quick track changes existing files only")
        elif rel not in paths:
            paths.append(rel)
    return paths, reasons


def _data_model_paths(root: Path) -> List[str]:
    model = root / "docs" / "data-model.md"
    if not model.is_file():
        return []
    found = ["docs/data-model.md"]
    for token in _BACKTICKED.findall(model.read_text(encoding="utf-8", errors="replace")):
        if _PATHLIKE.match(token.strip()):
            found.append(normalized(token))
    return found


def _is_data_model(root: Path, rel: str) -> Optional[str]:
    if rel.startswith("migrations/") or "/migrations/" in rel:
        return "a migration"
    for entry in _data_model_paths(root):
        if inside(rel, entry):
            return "named in docs/data-model.md"
    return None


def _must_evidence(root: Path, data: dict) -> List[str]:
    paths: List[str] = []
    for item_id, entry in (data.get("items") or {}).items():
        try:
            level = factory.catalog_item(item_id).get("level")
        except PolierError:
            continue
        if level != "must" or not isinstance(entry, dict):
            continue
        for evidence in entry.get("evidence") or []:
            value = str(evidence).strip()
            if value and not value.startswith("task:"):
                paths.append(normalized(value.split("#", 1)[0]))
    return paths


def _line_problems(root: Path) -> List[str]:
    """Reasons the line or the board refuse a quick task, whatever the scope."""
    reasons: List[str] = []
    data = factory.load(root)
    if data is None or (data.get("stations") or {}).get("build", {}).get("status") != "done":
        reasons.append("the build station is not closed; finish the line first")
    board = load_board(root)
    busy = [t.get("id") for t in tasks_of(board)
            if t.get("track") == "quick" and t.get("status") == "in_progress"]
    if busy:
        reasons.append(f"a quick task is already in progress ({', '.join(map(str, busy))})")
    return reasons


def qualifies(root, scope: Sequence[str], title: str) -> Tuple[bool, List[str]]:
    """(ok, reasons): whether the request may use the quick track."""
    root = Path(root)
    reasons: List[str] = []
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 120:
        reasons.append("the title must have 3 to 120 characters")
    reasons += _line_problems(root)
    paths, scope_reasons = _scope_paths(root, scope)
    reasons += scope_reasons

    policy = load_policy(root)
    data = factory.load(root) or {}
    evidence = _must_evidence(root, data)
    for rel in paths:
        pattern = manifest_match(policy, rel)
        if pattern:
            reasons.append(f"{rel} is a dependency manifest ({pattern})")
        pattern = protected_match(policy, rel)
        if pattern:
            reasons.append(f"{rel} is a protected path ({pattern})")
        kind = _is_data_model(root, rel)
        if kind:
            reasons.append(f"{rel} is a data model file ({kind})")
        if any(inside(rel, entry) for entry in evidence):
            reasons.append(f"{rel} is the evidence of a must item")
    return not reasons, reasons


def _next_id(root: Path, board: dict) -> str:
    numbers = [0]
    names = [str(t.get("id")) for t in tasks_of(board)]
    names += [p.stem for p in (root / "tasks").glob("M*.md")]
    names += [p.stem for p in (root / "runs").glob("M*.json")]
    for name in names:
        match = _ID_NUMBER.match(name)
        if match:
            numbers.append(int(match.group(1)))
    return f"M{max(numbers) + 1:02d}"


def _last_toucher(board: dict, paths: Sequence[str]) -> Optional[dict]:
    found = None
    for entry in tasks_of(board):
        if entry.get("status") not in TOUCHED:
            continue
        for rel in paths:
            if any(inside(rel, w) for w in entry.get("scope_write") or []):
                found = entry
    return found


def _satisfies(root: Path, board: dict, last: Optional[dict]) -> List[str]:
    """The definition-of-done items the task serves: those of the task that last touched
    the files, else of any task on the board, else the first one of docs/quality.md."""
    for entry in [last] + list(reversed(tasks_of(board))):
        if entry and entry.get("satisfies"):
            return list(entry["satisfies"])[:3]
    quality = root / "docs" / "quality.md"
    if quality.is_file():
        found = _DOD.search(quality.read_text(encoding="utf-8", errors="replace"))
        if found:
            return [found.group(1)]
    return []


def _brief(task: dict) -> str:
    scope = "\n".join(f"- `{p}`" for p in task["scope_write"])
    gates = "\n".join(f"{n}. gate `{g}` as in `board.json`; the record under `reviews/evidence/` is the evidence"
                      for n, g in enumerate(task["gates"], 1))
    return f"""# {task['id']} — {task['title']}

> Role: `{task.get('role', 'backend-builder')}`. Quick track: one small change after the build station, same gates and review as any task.

## Goal

{task['goal']}

**Why:** a small change after the build station costs one task and reopens no station.

**Satisfies:** {', '.join(task.get('satisfies') or []) or 'none'}

**Operating the task:** claim, the lead sets `in_progress`, run the gates, the lead sets `verifying`, then `review`, then `done` or `rework`. Approvals and escalation: `docs/orchestration.md`.

## Scope

Only these existing files change:

{scope}

## Out of scope

- Any other file, a new dependency, a protected path, a data model change or a change to the evidence of a must item. Such a change needs a proposal (`tools/change.py new`) and is not a quick task.
- Refactoring that the change itself does not need.

## Acceptance

A1 WHEN the change is made, THEN the system SHALL behave as the goal says and every listed gate passes.

## Context pack

**Read exactly:**

- `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `docs/module-map.md`
- the files of the scope and the tests next to them

**Do not read:** other task briefs and unrelated modules.

**Budget:** at most 20k tokens input.

## Specifications

- **Layer/module:** the module that owns the files of the scope.
- **Changed files:** the files listed under Scope; no new files unless a test for the change needs one in the scope.
- **Behaviour:** the smallest change that satisfies the goal; keep the style of the surrounding code and the contracts it follows.

## Pitfalls

- A file outside the scope is blocked by the write guard; do not work around it. Stop and report it, the lead decides whether a proposal is needed.
- A test that fails after the change is a finding about the change; never weaken an existing test to make it pass.

## Edge cases

- Empty input, a missing file, or a value at the limit of what the code accepts: decide each and cover the ones the change touches with a test.
- If the change turns out to touch a dependency manifest, the data model or a protected path, stop with status blocked and say why.

## Gates

{gates}

A gate passes when command, exit code and expected output match. The task passes when all gates are green, the acceptance is evidenced and the reviewer gives pass with no blockers. If a gate fails: read the cause, fix the code, rerun the gate.

## Limits

- **Scope:** {', '.join(f'`{p}`' for p in task['scope_write'])}
- **Stop:** 3 attempts; when blocked, report status blocked and the reason
- No architecture change; no new dependency

## Output

Report the task ID, the changed files, the gate record paths, how the acceptance was verified and open questions; separate what was observed from what was inferred.
"""


def create(root, title: str, scope: Sequence[str], gates: Optional[Sequence[str]] = None,
           role: Optional[str] = None) -> dict:
    """Add the quick task and its brief; PolierError with the reasons when refused.

    Returns ``{"task": id, "brief": path, "gates": [...]}``.
    """
    root = Path(root)
    ok, reasons = qualifies(root, scope, title)
    if not ok:
        raise PolierError("; ".join(reasons))
    board = load_board(root)
    paths, _ = _scope_paths(root, scope)
    last = _last_toucher(board, paths)
    chosen = [g.strip() for g in gates or [] if isinstance(g, str) and g.strip()]
    if gates and not chosen:
        raise PolierError("--gate needs gate names")
    if not chosen:
        chosen = list((last or {}).get("gates") or []) or ["tests"]
    role = role or (last or {}).get("role")
    title = title.strip()
    task = {
        "id": _next_id(root, board), "title": title, "goal": title.rstrip(".") + ".",
        "status": "pending", "depends_on": [], "complexity": 1,
        "stage": board.get("stage", 1), "scope_write": paths, "acceptance": ["A1"],
        "gates": chosen, "track": "quick",
    }
    satisfies = _satisfies(root, board, last)
    if satisfies:
        task["satisfies"] = satisfies
    if role:
        task["role"] = role
    brief = root / "tasks" / f"{task['id']}.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text(_brief(task), encoding="utf-8")
    try:
        add_task(root, task)
    except PolierError:
        brief.unlink()
        raise
    return {"task": task["id"], "brief": f"tasks/{task['id']}.md", "gates": chosen}
