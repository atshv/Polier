"""The interview wizard and its plan draft (2.0).

The wizard does not replace the generator: it collects the Phase-A answers in a
structured form, stores them in the dashboard runtime folder and composes one
prompt file for a headless generator session (``prompt/generator.md`` plus the
answers). The session writes the real artifacts (``ARCHITECTURE.md``,
``board.json``, ``tasks/*.md``, ``policy.json``); the dashboard shows them and
"approve" records that the owner accepted the plan. From then on the normal
task loop applies.

Draft shape (``<git-common-dir>/polier/dashboard/plan.json``)::

    {"version": 1, "status": "draft"|"approved", "mode": "greenfield",
     "answers": {...}, "created": ..., "updated": ..., "approved_at": null,
     "prompt": {"path": "...", "session": "..."} }
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import board as board_mod
from . import runtime as runtime_mod
from .errors import PolierError

VERSION = 1
MODES = ("greenfield", "brownfield")
PLAN = "plan.json"
PROMPT = "generator-prompt.md"

# The interview fields and their labels. The order is the wizard order.
FIELDS: List[Dict[str, Any]] = [
    {"key": "mode", "label": "Mode", "kind": "choice", "choices": list(MODES),
     "help": "Greenfield: a new project. Brownfield: plan the next stages of an existing repository."},
    {"key": "name", "label": "Project name", "kind": "text", "required": True,
     "help": "Short working title, as it should appear in README and board.json."},
    {"key": "goal", "label": "Goal in one or two sentences", "kind": "text", "required": True,
     "help": "What the product does and for whom. This becomes the goal in the architecture."},
    {"key": "non_goals", "label": "Non-goals for v1", "kind": "text",
     "help": "What the project explicitly should not do."},
    {"key": "platform", "label": "Platform and runtime", "kind": "text",
     "help": "e.g. desktop web, mobile web, CLI; browser and OS support."},
    {"key": "stack", "label": "Language and stack", "kind": "text",
     "help": "e.g. TypeScript/Node, C++/WebAssembly, Python; package manager."},
    {"key": "backend", "label": "Backend and database", "kind": "text",
     "help": "e.g. own HTTP API, PostgreSQL, object storage; or none for a local tool."},
    {"key": "realtime", "label": "Realtime and collaboration", "kind": "text",
     "help": "e.g. WebSocket + CRDT for shared documents, or none."},
    {"key": "auth", "label": "Authentication and accounts", "kind": "text",
     "help": "e.g. self-hosted Ory Kratos, email magic link, no accounts."},
    {"key": "design", "label": "Design system and languages", "kind": "text",
     "help": "e.g. own token set, light/dark, English and German UI text."},
    {"key": "hosting", "label": "Hosting and operations", "kind": "text",
     "help": "e.g. local first, CH/EU hosting, Docker Compose; CI and release path."},
    {"key": "release", "label": "Release and versioning", "kind": "text",
     "help": "e.g. SemVer 0.0.1, tagged main, changelog entries per change."},
    {"key": "constraints", "label": "Hard constraints", "kind": "text",
     "help": "licences, privacy, budgets, hardware, deadlines, things that must not change."},
    {"key": "questions", "label": "Open questions and answers", "kind": "pairs",
     "help": "Question/answer pairs the generator should treat as decided; unanswered ones go to board.json open_questions."},
]
REQUIRED = ("name", "goal", "mode")
MAX_FIELD = 8000


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _path(root) -> Path:
    return runtime_mod.runtime_dir(root) / PLAN


def field_keys() -> List[str]:
    return [field["key"] for field in FIELDS]


def load(root) -> Dict[str, Any]:
    draft = runtime_mod.read_json(_path(root))
    if not draft:
        draft = {
            "version": VERSION, "status": "draft", "mode": "greenfield",
            "answers": {key: "" for key in field_keys()},
            "created": _now(), "updated": _now(), "approved_at": None, "prompt": {},
        }
        draft["answers"]["questions"] = []
    draft.setdefault("answers", {})
    for key in field_keys():
        draft["answers"].setdefault(key, [] if key == "questions" else "")
    draft.setdefault("status", "draft")
    draft.setdefault("mode", draft["answers"].get("mode") or "greenfield")
    return draft


def validate(answers: Dict[str, Any], mode: str) -> List[str]:
    errors: List[str] = []
    if mode not in MODES:
        errors.append(f"mode must be one of {', '.join(MODES)}")
    for key in REQUIRED:
        if not isinstance(answers.get(key), str) or not answers.get(key).strip():
            errors.append(f"{key} is required")
    for key, value in answers.items():
        if key == "questions":
            if not isinstance(value, list) or any(
                    not isinstance(pair, dict) or not isinstance(pair.get("question"), str)
                    for pair in value):
                errors.append("questions must be a list of {question, answer} objects")
            continue
        if not isinstance(value, str):
            errors.append(f"{key} must be text")
            continue
        if len(value) > MAX_FIELD:
            errors.append(f"{key} is too long (max {MAX_FIELD} characters)")
    return errors


def save_answers(root, answers: Dict[str, Any], mode: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(answers, dict):
        raise PolierError("answers must be an object")
    draft = load(root)
    chosen = (mode or answers.get("mode") or draft.get("mode") or "greenfield")
    unknown = set(answers) - set(field_keys())
    if unknown:
        raise PolierError("unknown interview field(s): " + ", ".join(sorted(unknown)))
    merged = dict(draft.get("answers") or {})
    merged.update({key: value for key, value in answers.items() if value is not None})
    errors = validate(merged, chosen)
    if errors:
        raise PolierError("; ".join(errors))
    draft.update({"version": VERSION, "mode": chosen, "answers": merged, "updated": _now()})
    if draft.get("status") == "approved":
        draft["status"] = "draft"
        draft["approved_at"] = None
    runtime_mod.write_json(_path(root), draft)
    return draft


def _answers_block(answers: Dict[str, Any]) -> str:
    lines = []
    for field in FIELDS:
        value = answers.get(field["key"])
        if field["key"] == "questions":
            pairs = [pair for pair in value if isinstance(pair, dict) and pair.get("question")]
            if not pairs:
                continue
            lines.append("Open questions:")
            for pair in pairs:
                lines.append(f"- Q: {pair.get('question', '').strip()}")
                if pair.get("answer"):
                    lines.append(f"  A: {pair['answer'].strip()}")
            continue
        if isinstance(value, str) and value.strip():
            lines.append(f"- {field['label']}: {value.strip()}")
    return "\n".join(lines)


def generator_prompt(root, package_root: Path, draft: Optional[Dict[str, Any]] = None) -> str:
    """The complete prompt for the planning session."""
    draft = draft or load(root)
    answers = draft.get("answers") or {}
    errors = validate(answers, draft.get("mode") or "greenfield")
    if errors:
        raise PolierError("the interview is incomplete: " + "; ".join(errors))
    template = Path(package_root) / "prompt" / "generator.md"
    try:
        generator = template.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolierError(f"cannot read the generator prompt at {template}: {exc}") from exc
    mode = draft.get("mode") or "greenfield"
    where = ("Create the project in the current working directory." if mode == "greenfield"
             else "The repository already exists; read its current state before planning "
                  "and keep every done or running task intact.")
    return f"""{generator}

---

## Dashboard interview (owner answers)

The owner answered the Phase-A interview in the Polier dashboard. Treat these
answers as decided; where they leave something open, choose a conservative
default, record it in `board.json` → `open_questions`, and continue without
asking.

Mode: {mode}
{where}

{_answers_block(answers)}

## Dashboard run instructions

- Work autonomously in this session: no interactive questions are possible.
- Write the real artifacts (`ARCHITECTURE.md`, `board.json`, `tasks/*.md`,
  `policy.json`, `AGENTS.md`, `README.md`, `STATUS.md`) following the generator
  prompt above.
- Keep the board valid: `python3 <polier>/tools/check.py .` must pass when you
  are done.
- At the end print a short summary: project name, profile, number of stages and
  tasks, open questions, and the commands the owner should run first.
"""


def record_prompt(root, package_root: Path) -> Dict[str, Any]:
    """Build the prompt, store it in the runtime folder and return path + text."""
    draft = load(root)
    text = generator_prompt(root, package_root, draft)
    folder = runtime_mod.sub(root, "plan")
    target = folder / f"generator-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
    runtime_mod.write_text(target, text)
    draft["prompt"] = {"path": str(target), "created": _now()}
    draft["updated"] = _now()
    runtime_mod.write_json(_path(root), draft)
    return {"path": str(target), "text": text, "draft": draft}


def approve(root, package_root: Path) -> Dict[str, Any]:
    """Accept the plan: the generated board must exist, be valid and be the plan."""
    root = Path(root).resolve()
    draft = load(root)
    errors = validate(draft.get("answers") or {}, draft.get("mode") or "greenfield")
    if errors:
        raise PolierError("the interview is incomplete: " + "; ".join(errors))
    board = board_mod.load_board(root)
    if board is None:
        raise PolierError("no board.json yet: run the planning session first, then approve")
    problems = board_mod.board_errors(board)
    if problems:
        raise PolierError("board.json is invalid: " + "; ".join(problems))
    draft.update({"status": "approved", "approved_at": _now(), "updated": _now()})
    runtime_mod.write_json(_path(root), draft)
    return {
        "status": "approved",
        "approved_at": draft["approved_at"],
        "project": board.get("project"),
        "tasks": len(board.get("tasks") or []),
        "stages": len(board.get("stages") or []),
    }


def status(root) -> Dict[str, Any]:
    draft = load(root)
    return {
        "version": draft.get("version"),
        "status": draft.get("status"),
        "mode": draft.get("mode"),
        "answers": draft.get("answers"),
        "required": list(REQUIRED),
        "fields": FIELDS,
        "prompt": draft.get("prompt"),
        "created": draft.get("created"),
        "updated": draft.get("updated"),
        "approved_at": draft.get("approved_at"),
        "board_present": (Path(root) / "board.json").is_file(),
    }
