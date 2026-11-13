"""The quick track: the entry rule of ADR-0004 and the task it creates.

A quick task is an ordinary board task with ``track: quick``; it runs through
the same state machine, gates, review and handoff. ``qualifies`` decides
whether a request may use the track, ``create`` adds the task and its brief.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import factory
from .board import add_task, load_board, tasks_of
from .errors import PolierError
from .paths import inside, normalized
from .policy import load_policy, manifest_match, protected_match

class Refused(PolierError):
    """The request does not qualify; ``reasons`` lists why."""

    def __init__(self, reasons: List[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


NEXT = "pl_change new (tools/change.py new TITLE) to propose the change"

_BACKTICKED = re.compile(r"`([^`\n]+)`")
_PATHLIKE = re.compile(r"^[\w.\-]+(/[\w.\-]+)+/?$|^[\w\-]+\.[A-Za-z0-9]+$")
# a quick task in any other status is open and holds its files
FINISHED = {"done", "failed"}
# records and plan files written by Polier tools; platforms and traits live in factory.json
RECORD_FILES = ("factory.json", "board.json", "policy.json", "STATUS.md", "docs/factory.md")
RECORD_FOLDERS = ("runs", "reviews", "changes", "tasks")
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
            if t.get("track") == "quick" and t.get("status") not in FINISHED]
    if busy:
        reasons.append(f"a quick task is still open ({', '.join(map(str, busy))}); "
                       "finish it first, one at a time")
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
        if any(inside(rel, entry) for entry in RECORD_FILES + RECORD_FOLDERS):
            reasons.append(f"{rel} is a record or plan file of the line (platforms and traits "
                           "live in factory.json); changing it is not a quick task")
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


def _satisfies(root: Path, last: Optional[dict], given: Sequence[str]) -> List[str]:
    """`given` (validated against docs/quality.md) or the items of the task that last
    touched the files; PolierError when neither names one."""
    quality = root / "docs" / "quality.md"
    known = set(_DOD.findall(quality.read_text(encoding="utf-8", errors="replace"))) \
        if quality.is_file() else set()
    if given:
        unknown = [d for d in given if d not in known]
        if unknown:
            raise PolierError(f"--satisfies {', '.join(unknown)} is not a definition-of-done item "
                              "of docs/quality.md")
        return list(given)
    inherited = [d for d in (last or {}).get("satisfies") or [] if isinstance(d, str)]
    if not inherited:
        raise PolierError("no task has touched these files; name the definition-of-done item "
                          "with --satisfies D<n> (see docs/quality.md)")
    return inherited


def _accept_lines(accept: Sequence[str]) -> List[str]:
    lines = [" ".join(str(a).split()) for a in accept or [] if str(a).strip()]
    if not lines:
        raise PolierError('name the expected behaviour: --accept "WHEN <situation>, THEN <behaviour>"')
    for line in lines:
        if not re.match(r"^WHEN\b.*\bTHEN\b", line):
            raise PolierError(f'--accept must read "WHEN …, THEN …", got {line!r}')
    return lines


def _sections(task: dict, accept: Sequence[str]) -> Dict[str, str]:
    scope = "\n".join(f"- `{p}`" for p in task["scope_write"])
    criteria = "\n".join(f"A{n} {line}" for n, line in enumerate(accept, 1))
    gates = "\n".join(f"{n}. gate `{g}` as in `board.json` -> pass; the record under `reviews/evidence/` is the evidence"
                      for n, g in enumerate(task["gates"], 1))
    return {
        "Goal": f"""{task['goal']}

**Why:** a small change after the build station costs one task and reopens no station.

**Satisfies:** {', '.join(task.get('satisfies') or []) or 'none'}

**Operating the task:** claim, the lead sets `in_progress`, run the gates, the lead sets `verifying`, then `review`, then `done` or `rework`. Approvals and escalation: `docs/orchestration.md`.""",
        "Scope": f"Only these existing files change:\n\n{scope}",
        "Out of scope": """- Any other file, a new dependency, a protected path, a record of the line, a data model change or a change to the evidence of a must item. Such a change needs a proposal (`tools/change.py new`) and is not a quick task.
- Refactoring that the change itself does not need.""",
        "Acceptance": criteria,
        "Context pack": """**Read exactly:**

- `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `docs/module-map.md`
- the files of the scope and the tests next to them

**Do not read:** other task briefs and unrelated modules.

**Budget:** at most 20k tokens input.""",
        "Specifications": """- **Layer/module:** the module that owns the files of the scope.
- **Changed files:** the files listed under Scope; no new files unless a test for the change needs one in the scope.
- **Behaviour:** the smallest change that satisfies the acceptance; keep the style of the surrounding code and the contracts it follows.""",
        "Pitfalls": """- A file outside the scope is blocked by the write guard; do not work around it. Stop and report it, the lead decides whether a proposal is needed.
- A test that fails after the change is a finding about the change; never weaken an existing test to make it pass.""",
        "Edge cases": """- Empty input, a missing file, or a value at the limit of what the code accepts: decide each and cover the ones the change touches with a test.
- If the change turns out to touch a dependency manifest, the data model or a protected path, stop with status blocked and say why.""",
        "Gates": f"""{gates}

A gate passes when command, exit code and expected output match. The task passes when all gates are green, the acceptance is evidenced and the reviewer gives pass with no blockers. If a gate fails: read the cause, fix the code, rerun the gate.""",
        "Limits": f"""- **Scope:** {', '.join(f'`{p}`' for p in task['scope_write'])}
- **Stop:** 3 attempts; when blocked, `status: blocked` and the reason
- No architecture change; no new dependencies without approval""",
    }


def _brief(task: dict, accept: Sequence[str]) -> str:
    """The brief, built from templates/task-brief.md: known sections filled, the UI section dropped."""
    template = (Path(__file__).resolve().parent.parent / "templates" / "task-brief.md").read_text(encoding="utf-8")
    filled = _sections(task, accept)
    blocks = re.split(r"(?m)^(?=## )", template)
    out = [f"# {task['id']} — {task['title']}\n\n> Role: `{task.get('role', 'backend-builder')}`. "
           "Quick track: one small change after the build station, same gates and review as any task.\n"]
    for block in blocks[1:]:
        name = block.splitlines()[0][3:].strip()
        if name in filled:
            out.append(f"## {name}\n\n{filled[name]}\n")
        elif name.startswith("Output"):
            out.append(block.rstrip().replace("Mxx", task["id"]) + "\n")
    return "\n".join(out)


def create(root, title: str, scope: Sequence[str], accept: Sequence[str],
           gates: Optional[Sequence[str]] = None, role: Optional[str] = None,
           satisfies: Sequence[str] = ()) -> dict:
    """Add the quick task and its brief; Refused (with ``reasons``) when the request does
    not qualify, PolierError when an input is missing or invalid.

    ID choice, the entry rule, the brief and the board write all happen under the
    board lock. Returns ``{"task": id, "brief": path, "gates": [...]}``.
    """
    root = Path(root)
    lines = _accept_lines(accept)
    chosen = [g.strip() for g in gates or [] if isinstance(g, str) and g.strip()]
    if gates and not chosen:
        raise PolierError("--gate needs gate names")
    made: dict = {}

    def build(board: dict) -> dict:
        ok, reasons = qualifies(root, scope, title)
        if not ok:
            raise Refused(reasons)
        paths, _ = _scope_paths(root, scope)
        last = _last_toucher(board, paths)
        done = _satisfies(root, last, satisfies)
        text = title.strip()
        task = {
            "id": _next_id(root, board), "title": text, "goal": text.rstrip(".") + ".",
            "status": "pending", "depends_on": [], "complexity": 1,
            "stage": board.get("stage", 1), "scope_write": paths,
            "acceptance": [f"A{n}" for n in range(1, len(lines) + 1)],
            "gates": chosen or list((last or {}).get("gates") or []) or ["tests"],
            "satisfies": done, "track": "quick",
        }
        role_id = role or (last or {}).get("role")
        if role_id:
            task["role"] = role_id
        made.update(task=task["id"], brief=f"tasks/{task['id']}.md", gates=task["gates"])
        return task

    def write_brief(task: dict) -> Path:
        path = root / "tasks" / f"{task['id']}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "x", encoding="utf-8") as stream:
            stream.write(_brief(task, lines))
        return path

    add_task(root, build, write_brief)
    return made
