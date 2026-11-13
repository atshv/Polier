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
from .board import load_board
from .errors import PolierError
from .evidence import REVIEW_VERDICT

__all__ = ["CLASSES", "has_records", "parse_since", "report", "repeated_gate_failure", "long_review",
           "scope_pressure", "deferred_or_na", "stalled_approval", "busy_or_infra_gate"]

STALL_DAYS = 7
MAX_EXAMPLES = 3
RECORD_PARTS = ("board.json", "factory.json", "runs", "reviews")
SCOPE_WORDS = re.compile(r"\b(outside|out of) (the |its |my )?(write )?scope\b|\bscope (change|pressure)\b",
                         re.IGNORECASE)
CRITERION = re.compile(r"(?m)^\s*(?:-\s*)?criterion:[ \t]*(.+?)[ \t]*$")


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


def _evidence(folder) -> List[tuple]:
    """``(project-relative path, record)`` for every readable gate record.

    ``record_files`` and ``gate_records`` apply the same filters in the same
    order, so for one task they line up pair by pair.
    """
    pairs = []
    for task in _task_ids(folder):
        files = evidence.record_files(folder, task)
        records = evidence.gate_records(folder, task)
        pairs += [(f"reviews/evidence/{path.name}", record) for path, record in zip(files, records)]
    return pairs


def _task_ids(folder) -> List[str]:
    return sorted({r.get("task") for r in evidence.gate_records(folder) if isinstance(r.get("task"), str)})


def _run_ids(folder) -> List[str]:
    try:
        return sorted(p.stem for p in (Path(folder) / "runs").glob("*.json"))
    except OSError:
        return []


def _attempt_of(record: dict, event_at) -> int:
    """The number of the attempt a moment falls in (the last one started before it)."""
    moment, number = _moment(event_at), 0
    for attempt in record["attempts"]:
        started = _moment(attempt["started"])
        if started is not None and moment is not None and started <= moment:
            number = attempt["n"]
    return number


def repeated_gate_failure(folders, since=None) -> dict:
    """The same gate failing in at least two attempts of one task, from ``gate`` events in runs/."""
    hits = []
    for folder in folders:
        for task in _run_ids(folder):
            try:
                record = runs.load_run(folder, task)
            except PolierError:
                continue
            failing: Dict[str, dict] = {}
            for event in record["events"]:
                data = event["data"]
                if event["kind"] != "gate" or data.get("result") in ("pass", *evidence.INFRA_RESULTS) \
                        or not _recent(event["at"], since):
                    continue
                failing.setdefault(str(data.get("gate")), {}).setdefault(_attempt_of(record, event["at"]), data)
            for gate, by_attempt in sorted(failing.items()):
                if len(by_attempt) >= 2:
                    first = by_attempt[min(by_attempt)]
                    path = first.get("record") or f"runs/{task}.json"
                    hits.append(_hit(folder, path, f"{task}: gate {gate} failed in {len(by_attempt)} attempts"))
    return _result("repeated gate failure", hits, ["templates/gates/<stack>.md", "templates/task-brief.md"])


def _heading(criterion: str) -> str:
    """The part of a finding's criterion before ' / ', ' (' or ';'."""
    return re.split(r" / | \(|;", criterion, maxsplit=1)[0].strip()


def _criteria(text: str) -> List[str]:
    found = []
    for raw in CRITERION.findall(text):
        value = raw.strip()
        if value[:1] in ("'", '"') and value.endswith(value[0]) and len(value) > 1:
            value = value[1:-1]
        elif value[:1] in ("'", '"'):
            value = value[1:]
        if value.strip():
            found.append(value.strip())
    return found


def long_review(folders, since=None) -> dict:
    """Reviews with more than one round, with the findings grouped by criterion heading."""
    hits, by_heading = [], {}
    for folder in folders:
        for path in sorted((Path(folder) / "reviews").glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rounds = len(REVIEW_VERDICT.findall(text))
            if rounds > 1 and _recent(_mtime(path), since):
                headings = sorted({_heading(c) for c in _criteria(text)})
                for heading in headings:
                    by_heading[heading] = by_heading.get(heading, 0) + 1
                detail = f"{path.stem}: {rounds} review rounds"
                hits.append(_hit(folder, f"reviews/{path.name}",
                                 detail + (f"; findings on {', '.join(headings)}" if headings else "")))
    result = _result("long review", hits, ["prompt/rubric.md", "roles/<role>.md"])
    result["by_heading"] = dict(sorted(by_heading.items(), key=lambda item: (-item[1], item[0])))
    return result


def _text_of(question) -> str:
    return str(question.get("question") if isinstance(question, dict) else question or "")


def scope_pressure(folders, since=None) -> dict:
    """Open questions that name paths outside the scope. Stop-check reports are not recorded in runs/."""
    hits = []
    for folder in folders:
        board = load_board(folder, strict=False) or {}
        for question in board.get("open_questions") or []:
            if SCOPE_WORDS.search(_text_of(question)):
                label = question.get("id", "question") if isinstance(question, dict) else "question"
                hits.append(_hit(folder, "board.json", f"{label}: {_text_of(question)[:100]}"))
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
                                 f"{record.get('action')} for {record.get('task')} pending {days} days, threshold {STALL_DAYS}"))
    return _result("stalled approval", hits, ["prompt/orchestration.md"])


def busy_or_infra_gate(folders, since=None) -> dict:
    hits = []
    for folder in folders:
        for rel, record in _evidence(folder):
            if record.get("result") in evidence.INFRA_RESULTS \
                    and _recent(record.get("finished") or record.get("started"), since):
                hits.append(_hit(folder, rel,
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
