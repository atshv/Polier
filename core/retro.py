"""Error classes over the records of Polier projects (ADR-0002), read-only.

One function per class; each takes the project folders and returns
``{class, count, examples, points_at}``. Nothing here writes into a folder.
Records are read with the loaders of ``core.runs``, ``core.approvals``,
``core.evidence`` and ``core.board``; a record a loader cannot read is named
in ``skipped`` by ``report``.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import approvals, evidence, factory, runs
from .board import load_board, tasks_of
from .errors import PolierError
from .evidence import REVIEW_VERDICT

__all__ = ["CLASSES", "has_records", "parse_since", "report", "repeated_gate_failure", "long_review",
           "scope_pressure", "deferred_or_na", "stalled_approval", "busy_or_infra_gate"]

STALL_DAYS = 7
MAX_EXAMPLES = 3
RECORD_PARTS = ("board.json", "factory.json", "runs", "reviews")
SCOPE_WORDS = re.compile(r"\b(outside|out of) (the |its |my )?(write )?scope\b|\bscope (change|pressure)\b",
                         re.IGNORECASE)
CRITERION = re.compile(r"(?m)^\s*(?:-\s*)?criterion:\s*[\"']?([^\"'\n]+)")


def parse_since(value: str) -> dt.datetime:
    """A ``YYYY-MM-DD`` date as UTC midnight; PolierError otherwise."""
    try:
        day = dt.datetime.strptime(str(value), "%Y-%m-%d")
    except ValueError as exc:
        raise PolierError(f"--since needs a date YYYY-MM-DD, got {value!r}") from exc
    return day.replace(tzinfo=dt.timezone.utc)


def _moment(value) -> Optional[dt.datetime]:
    if not isinstance(value, str):
        return None
    try:
        moment = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def _recent(value, since) -> bool:
    """True when there is no cut-off, no usable date, or the date is not before the cut-off."""
    moment = _moment(value)
    return since is None or moment is None or moment >= since


def _mtime(path: Path) -> Optional[str]:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()
    except OSError:
        return None


def has_records(folder) -> bool:
    return any((Path(folder) / part).exists() for part in RECORD_PARTS)


def _result(name: str, hits: List[dict], points_at: List[str]) -> dict:
    return {"class": name, "count": len(hits), "examples": hits[:MAX_EXAMPLES], "points_at": points_at}


def _hit(folder, rel: str, detail: str) -> dict:
    return {"record": f"{folder}/{rel}".replace("\\", "/"), "detail": detail}


def _evidence_rel(record: dict) -> str:
    log = record.get("log")
    if isinstance(log, str) and log.endswith(".log"):
        return f"reviews/evidence/{log[:-4]}.json"
    return f"reviews/evidence ({record.get('task')}/{record.get('gate')})"


def _task_ids(folder) -> List[str]:
    return sorted({r.get("task") for r in evidence.gate_records(folder) if isinstance(r.get("task"), str)})


def _is_failure(record: dict) -> bool:
    return record.get("exit_code") not in (0, None) and record.get("result") not in evidence.INFRA_RESULTS


def repeated_gate_failure(folders, since=None) -> dict:
    hits = []
    for folder in folders:
        failing: Dict[tuple, list] = {}
        for record in evidence.gate_records(folder):
            if _is_failure(record) and _recent(record.get("finished") or record.get("started"), since):
                failing.setdefault((record.get("task"), record.get("gate")), []).append(record)
        for (task, gate), found in sorted(failing.items(), key=lambda item: str(item[0])):
            if len(found) >= 2:
                hits.append(_hit(folder, _evidence_rel(found[0]), f"{task}: gate {gate} failed {len(found)} times"))
    return _result("repeated gate failure", hits, ["templates/gates/<stack>.md", "templates/task-brief.md"])


def long_review(folders, since=None) -> dict:
    hits = []
    for folder in folders:
        for path in sorted((Path(folder) / "reviews").glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rounds = len(REVIEW_VERDICT.findall(text))
            if rounds > 1 and _recent(_mtime(path), since):
                headings = sorted({c.strip() for c in CRITERION.findall(text)})
                detail = f"{path.stem}: {rounds} review rounds"
                hits.append(_hit(folder, f"reviews/{path.name}",
                                 detail + (f"; findings on {', '.join(headings)}" if headings else "")))
    return _result("long review", hits, ["prompt/rubric.md", "roles/<role>.md"])


def _text_of(question) -> str:
    return str(question.get("question") if isinstance(question, dict) else question or "")


def scope_pressure(folders, since=None) -> dict:
    hits = []
    for folder in folders:
        board = load_board(folder, strict=False) or {}
        for question in board.get("open_questions") or []:
            if SCOPE_WORDS.search(_text_of(question)):
                label = question.get("id", "question") if isinstance(question, dict) else "question"
                hits.append(_hit(folder, "board.json", f"{label}: {_text_of(question)[:100]}"))
        for task in tasks_of(board):
            tid = task.get("id")
            if not isinstance(tid, str) or not (Path(folder) / "runs" / f"{tid}.json").is_file():
                continue
            for event in runs.load_run(folder, tid)["events"]:
                if event["kind"] in ("scope", "stop_check") and _recent(event["at"], since):
                    hits.append(_hit(folder, f"runs/{tid}.json", f"{tid}: {event['kind']} event"))
    return _result("scope pressure", hits, ["prompt/generator.md", "templates/task-brief.md"])


def deferred_or_na(folders, since=None) -> dict:
    hits = []
    for folder in folders:
        try:
            line = factory.load(folder) or {}
        except PolierError:
            continue
        items = line.get("items") if isinstance(line.get("items"), dict) else {}
        for item_id, entry in sorted(items.items()):
            if isinstance(entry, dict) and entry.get("status") in ("deferred", "na"):
                hits.append(_hit(folder, "factory.json",
                                 f"{item_id} {entry['status']}: {str(entry.get('reason') or '')[:80]}"))
    return _result("deferred or n/a item", hits, ["factory/catalog.json"])


def stalled_approval(folders, since=None, now=None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    hits = []
    for folder in folders:
        for record in approvals.load_all(folder):
            asked = _moment(record.get("requested_at"))
            if record.get("status") != "pending" or asked is None or not _recent(record.get("requested_at"), since):
                continue
            days = (now - asked).days
            if days >= STALL_DAYS:
                hits.append(_hit(folder, f"reviews/approvals/{record.get('id')}.json",
                                 f"{record.get('action')} for {record.get('task')} pending {days} days"))
    return _result("stalled approval", hits, ["prompt/orchestration.md"])


def busy_or_infra_gate(folders, since=None) -> dict:
    hits = []
    for folder in folders:
        for record in evidence.gate_records(folder):
            if record.get("result") in evidence.INFRA_RESULTS \
                    and _recent(record.get("finished") or record.get("started"), since):
                hits.append(_hit(folder, _evidence_rel(record),
                                 f"{record.get('task')}: gate {record.get('gate')} {record.get('result')}"))
    return _result("busy or infra gate", hits, ["templates/gates/", "docs/slots.md"])


CLASSES: List[Callable] = [repeated_gate_failure, long_review, scope_pressure, deferred_or_na,
                           stalled_approval, busy_or_infra_gate]


def _unreadable(folder: Path) -> List[str]:
    """Record files a loader would silently drop, so the report can name them."""
    found = []
    for pattern in ("board.json", "factory.json", "runs/*.json", "reviews/evidence/*.json",
                    "reviews/approvals/*.json"):
        for path in sorted(folder.glob(pattern)):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                found.append(path.relative_to(folder).as_posix())
    return found


def report(folders, since=None, now=None) -> dict:
    """``{classes, skipped}`` over the folders; classes without a signal are left out."""
    usable, skipped, seen = [], [], set()
    for given in folders:
        folder = Path(given)
        key = folder.resolve()
        if key in seen:
            continue
        seen.add(key)
        if not has_records(folder):
            skipped.append({"folder": str(given), "reason": "no board.json, factory.json, runs/ or reviews/"})
            continue
        usable.append(folder)
        for rel in _unreadable(folder):
            skipped.append({"folder": str(given), "reason": f"unreadable record {rel}"})
    classes = []
    for function in CLASSES:
        found = function(usable, since, now) if function is stalled_approval else function(usable, since)
        if found["count"]:
            classes.append(found)
    return {"classes": classes, "skipped": skipped}
