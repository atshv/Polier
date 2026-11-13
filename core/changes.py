"""Change proposals: ``changes/C<NN>/proposal.md`` with deltas to the living docs.

A proposal (ADR-0003) holds a status line, why, what, linked board tasks and one
delta block per target ``file#heading`` (ADDED, MODIFIED with old and new text,
REMOVED). ``apply`` merges the deltas only when a granted ``scope_change``
approval names the proposal ID in its note and every linked task is done, then
sets the status to ``applied``. Everything is checked in memory first; nothing
is written unless every delta applies.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import approvals, policy
from .board import load_board, tasks_of
from .errors import PolierError
from .factory import _slug
from .paths import normalized

PACKAGE = Path(__file__).resolve().parent.parent
TEMPLATE = PACKAGE / "templates" / "change-proposal.md"
CHANGES = "changes"
STATUSES = ("draft", "applied")
KINDS = ("ADDED", "MODIFIED", "REMOVED")

ID_RE = re.compile(r"^C[0-9]{2,}$")
TITLE_RE = re.compile(r"^#\s+(C[0-9]{2,})\s+[—–-]+\s+(.+?)\s*$")
STATUS_RE = re.compile(r"\*\*Status:\*\*\s*([A-Za-z]+)")
STATUS_FIELD_RE = re.compile(r"\*\*Status:\*\*.*?(?= · \*\*|$)", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
DELTA_RE = re.compile(r"^###\s+`([^`]+)`\s+[—–-]+\s+([A-Za-z]+)\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
LABEL_RE = re.compile(r"^\*{0,2}(Old|New):?\*{0,2}:?\s*$", re.IGNORECASE)
LIST_RE = re.compile(r"^\s*([-*+]|[0-9]+\.)\s")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
STRAY_DELTA_RE = re.compile(r"^###\s+`[^`]+#[^`]*`\s+[—–-]+\s+[A-Za-z]+\s*$")
RECORD_DIRS = ("changes", "reviews", "tasks", "runs")
RECORD_FILES = ("board.json", "factory.json", "policy.json")


# ---------------------------------------------------------------------------
# paths and IDs
# ---------------------------------------------------------------------------

def valid_id(value) -> bool:
    """True for a proposal ID of the form C01."""
    return isinstance(value, str) and bool(ID_RE.fullmatch(value.strip()))


def proposal_path(root, change_id: str) -> Path:
    return Path(root) / CHANGES / change_id / "proposal.md"


def ids(root) -> List[str]:
    """The IDs of every proposal folder, sorted by number."""
    folder = Path(root) / CHANGES
    try:
        found = [p.name for p in folder.iterdir()
                 if p.is_dir() and ID_RE.fullmatch(p.name) and (p / "proposal.md").is_file()]
    except OSError:
        return []
    return sorted(found, key=lambda name: int(name[1:]))


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, path)


def _blank_comments(text: str) -> str:
    """The text with HTML comments replaced by blanks; offsets and lines stay."""
    return COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------

def _fenced(lines: List[str]) -> List[bool]:
    """For each line, True when it is inside a code fence or is a fence line."""
    flags, fence = [], None
    for line in lines:
        match = FENCE_RE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
                flags.append(True)
                continue
            flags.append(False)
            continue
        flags.append(True)
        if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) \
                and line.strip() == match.group(1):
            fence = None
    return flags


def _read_block(body: List[str], start: int) -> Tuple[Optional[str], int]:
    """The fenced block that starts at or after `start`; (text, next index)."""
    i = start
    while i < len(body) and not body[i].strip():
        i += 1
    if i >= len(body) or not FENCE_RE.match(body[i]):
        return None, start
    fence = FENCE_RE.match(body[i]).group(1)
    j = i + 1
    while j < len(body) and body[j].strip() != fence:
        j += 1
    if j >= len(body):
        return None, start
    return "\n".join(body[i + 1:j]), j + 1


def _parse_delta_body(kind: str, body: List[str]) -> dict:
    """Old, new and added text of one delta body; raises ValueError on a bad one."""
    if kind == "ADDED":
        text, after = _read_block(body, 0)
        if text is not None and not any(line.strip() for line in body[after:]):
            added = text
        else:
            added = "\n".join(body).strip("\n")
            flags = _fenced(body)
            for line, inside in zip(body, flags):
                if not inside and HEADING_RE.match(line):
                    raise ValueError(f"ADDED text contains the heading {line.strip()!r} outside a "
                                     "fenced block; put the text in a ```markdown block")
        if not added.strip():
            raise ValueError("ADDED has no text")
        return {"added": added}
    blocks: Dict[str, str] = {}
    i = 0
    while i < len(body):
        label = LABEL_RE.match(body[i].strip())
        if label:
            text, nxt = _read_block(body, i + 1)
            if text is None:
                raise ValueError(f"{label.group(1)}: has no fenced block")
            blocks[label.group(1).lower()] = text
            i = nxt
        else:
            i += 1
    if not blocks.get("old", "").strip():
        raise ValueError(f"{kind} needs an Old: block with the text")
    if kind == "MODIFIED" and "new" not in blocks:
        raise ValueError("MODIFIED needs a New: block")
    if kind == "REMOVED" and "new" in blocks:
        raise ValueError("REMOVED takes only an Old: block")
    return {"old": blocks["old"], "new": blocks.get("new")}


def parse(text: str) -> dict:
    """Parse a proposal; the result has `id`, `title`, `status`, `tasks`,
    `deltas` and `errors` (a list of problems; [] when the proposal is valid)."""
    errors: List[str] = []
    clean = _blank_comments(text)
    lines = clean.split("\n")
    fenced = _fenced(lines)

    change_id = title = None
    for line in lines:
        match = TITLE_RE.match(line)
        if match:
            change_id, title = match.group(1), match.group(2)
        break
    if change_id is None:
        errors.append("the first line must be '# C<NN> — <title>'")

    status_match = STATUS_RE.search(clean)
    status = status_match.group(1).lower() if status_match else None
    if status is None:
        errors.append("no '**Status:** draft' line")
    elif status not in STATUSES:
        errors.append(f"unknown status {status!r} (known: {', '.join(STATUSES)})")

    sections: Dict[str, Tuple[int, int]] = {}
    heads = [(i, HEADING_RE.match(line)) for i, line in enumerate(lines) if not fenced[i]]
    heads = [(i, m) for i, m in heads if m]
    for pos, (i, m) in enumerate(heads):
        if len(m.group(1)) == 2:
            end = next((j for j, n in heads[pos + 1:] if len(n.group(1)) <= 2), len(lines))
            sections.setdefault(_slug(m.group(2)), (i, end))

    tasks: List[str] = []
    if "linked-tasks" in sections:
        start, end = sections["linked-tasks"]
        for line in lines[start + 1:end]:
            item = re.match(r"^\s*[-*]\s+`?([A-Za-z][A-Za-z0-9._-]*)`?\s*$", line)
            if item:
                tasks.append(item.group(1))

    deltas: List[dict] = []
    key = next((k for k in sections if k.startswith("deltas")), None)
    if key:
        start, end = sections[key]
        marks = [i for i in range(start + 1, end)
                 if not fenced[i] and lines[i].startswith("### ")]
        for pos, i in enumerate(marks):
            stop = marks[pos + 1] if pos + 1 < len(marks) else end
            match = DELTA_RE.match(lines[i])
            number = pos + 1
            if not match or "#" not in match.group(1):
                errors.append(f"delta {number}: heading must read ### `file#heading` — ADDED|MODIFIED|REMOVED")
                continue
            kind = match.group(2).upper()
            target, _, heading = match.group(1).partition("#")
            if kind not in KINDS:
                errors.append(f"delta {number} ({match.group(1)}): unknown kind {match.group(2)!r}")
                continue
            try:
                body = _parse_delta_body(kind, lines[i + 1:stop])
            except ValueError as exc:
                errors.append(f"delta {number} ({match.group(1)} {kind}): {exc}")
                continue
            deltas.append({"number": number, "file": target.strip(), "heading": heading.strip(),
                           "kind": kind, **body})
    inside = range(*sections[key]) if key else range(0)
    for i, line in enumerate(lines):
        if i not in inside and not fenced[i] and STRAY_DELTA_RE.match(line):
            errors.append(f"line {i + 1}: delta heading {line.strip()!r} is outside the deltas section; "
                          "an unfenced level-1 or level-2 heading inside a delta body ends the "
                          "section, so put such text in a ```markdown block")
    return {"id": change_id, "title": title, "status": status, "tasks": tasks,
            "deltas": deltas, "errors": errors}


def load(root, change_id: str) -> dict:
    """The parsed proposal `change_id`; PolierError when it does not exist."""
    if not valid_id(change_id):
        raise PolierError(f"invalid change id {change_id!r} (expected C plus at least 2 digits)")
    path = proposal_path(root, change_id.strip())
    try:
        proposal = parse(_read(path))
    except (OSError, UnicodeDecodeError) as exc:
        raise PolierError(f"no proposal {change_id}: {exc}") from exc
    if proposal["id"] and proposal["id"] != change_id.strip():
        proposal["errors"].append(f"title names {proposal['id']} but the folder is {change_id}")
    return proposal


# ---------------------------------------------------------------------------
# new and link
# ---------------------------------------------------------------------------

def create(root, title: str, by: str = "owner") -> str:
    """Create the next proposal from the template with status draft; its ID."""
    title = " ".join(str(title or "").split())
    if not title:
        raise PolierError("a proposal needs a title")
    by = " ".join(str(by or "").split()) or "owner"
    load_board(root)
    try:
        template = _read(TEMPLATE)
    except OSError as exc:
        raise PolierError(f"template missing: {exc}") from exc
    folder = Path(root) / CHANGES
    number = max([int(name[1:]) for name in ids(root)] or [0]) + 1
    while True:
        change_id = f"C{number:02d}"
        try:
            (folder / change_id).mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            number += 1
    text = (template.replace("{{ID}}", change_id).replace("{{TITLE}}", title)
            .replace("{{BY}}", by).replace("{{DATE}}", dt.date.today().isoformat()))
    _write(proposal_path(root, change_id), text)
    return change_id


def link(root, change_id: str, task_ids: List[str]) -> List[str]:
    """Link board tasks to a proposal; the task list afterwards.

    PolierError when the proposal or a task does not exist; nothing is written then.
    """
    proposal = load(root, change_id)
    known = {t.get("id") for t in tasks_of(load_board(root))}
    for task_id in task_ids:
        if task_id not in known:
            raise PolierError(f"task {task_id} is not on the board")
    merged = list(proposal["tasks"])
    merged += [t for t in dict.fromkeys(task_ids) if t not in merged]
    path = proposal_path(root, change_id)
    text = _read(path)
    lines = text.split("\n")
    flags = _fenced(_blank_comments(text).split("\n"))
    clean = _blank_comments(text).split("\n")
    start = next((i for i, l in enumerate(clean)
                  if not flags[i] and re.match(r"^##\s+Linked tasks\s*$", l)), None)
    block = [f"- {t}" for t in merged]
    if start is None:
        at = next((i for i, l in enumerate(clean) if not flags[i] and re.match(r"^##\s+Approval\b", l)),
                  len(lines))
        lines[at:at] = ["## Linked tasks", ""] + block + [""]
    else:
        end = next((i for i in range(start + 1, len(lines))
                    if not flags[i] and clean[i].startswith("## ")), len(lines))
        lines[start + 1:end] = [""] + block + [""]
    _write(path, "\n".join(lines))
    return merged


# ---------------------------------------------------------------------------
# approval and tasks
# ---------------------------------------------------------------------------

def find_approval(root, change_id: str) -> Optional[dict]:
    """The newest granted scope_change approval whose requested note starts with `change_id`."""
    pattern = re.compile(rf"^\s*{re.escape(change_id)}(?![A-Za-z0-9])")
    # the requested note comes first; the owner's grant note is appended after ' | '
    found = [r for r in approvals.load_all(root)
             if r.get("status") == "granted" and r.get("action") == "scope_change"
             and isinstance(r.get("note"), str) and pattern.match(r["note"].split(" | ", 1)[0])]
    return found[-1] if found else None


def open_tasks(root, task_ids: List[str]) -> List[str]:
    """The linked tasks that are not done (a task missing from the board counts)."""
    status = {t.get("id"): t.get("status") for t in tasks_of(load_board(root))}
    return [t for t in task_ids if status.get(t) != "done"]


def status_of(root, proposal: dict) -> dict:
    """Approval and task state of a proposal, for `show`."""
    approval = find_approval(root, proposal["id"] or "")
    return {"approval": approval["id"] if approval else None,
            "open_tasks": open_tasks(root, proposal["tasks"])}


# ---------------------------------------------------------------------------
# applying deltas
# ---------------------------------------------------------------------------

def _section(lines: List[str], heading: str) -> Tuple[int, int]:
    """Line range [start, end) of the section; start is the heading line.

    ValueError when the heading is missing or appears more than once.
    """
    want = _slug(heading)
    fenced = _fenced(lines)
    heads = [(i, HEADING_RE.match(l)) for i, l in enumerate(lines) if not fenced[i]]
    heads = [(i, m) for i, m in heads if m]
    hits = [(pos, i, m) for pos, (i, m) in enumerate(heads) if _slug(m.group(2)) == want]
    if not hits:
        raise ValueError(f"heading {heading!r} not found")
    if len(hits) > 1:
        raise ValueError(f"heading {heading!r} appears {len(hits)} times (ambiguous)")
    pos, start, match = hits[0]
    level = len(match.group(1))
    end = next((j for j, n in heads[pos + 1:] if len(n.group(1)) <= level), len(lines))
    return start, end


def _add(lines: List[str], start: int, end: int, text: str) -> None:
    """Insert `text` at the end of the section, next to a table or list it extends."""
    new = text.split("\n")
    body = range(start + 1, end)
    last = max([i for i in body if lines[i].strip()], default=start)
    first = new[0].lstrip()
    tight = False
    if first.startswith("|"):
        rows = [i for i in body if lines[i].lstrip().startswith("|")]
        if rows:
            last, tight = rows[-1], True
    elif LIST_RE.match(new[0]):
        items = [i for i in body if LIST_RE.match(lines[i])]
        if items:
            last = max(i for i in body if LIST_RE.match(lines[i])
                       or (lines[i].startswith((" ", "\t")) and lines[i].strip()))
            tight = True
    lines[last + 1:last + 1] = new if tight else [""] + new


def _replace(lines: List[str], start: int, end: int, old: str, new: Optional[str]) -> List[str]:
    """The lines with `old` replaced by `new` (or removed) under the heading."""
    head, body, tail = lines[:start + 1], "\n".join(lines[start + 1:end]), lines[end:]
    count = body.count(old)
    if count == 0:
        raise ValueError("old text not found under the heading")
    if count > 1:
        raise ValueError(f"old text occurs {count} times under the heading (ambiguous)")
    at = body.index(old)
    stop = at + len(old)
    if new is None:
        if (at == 0 or body[at - 1] == "\n") and stop < len(body) and body[stop] == "\n":
            stop += 1
        body = body[:at] + body[stop:]
    else:
        body = body[:at] + new + body[stop:]
    return head + body.split("\n") + tail


def _forbidden_target(root: Path, rel: str) -> Optional[str]:
    """Why a delta may not target `rel` (relative to the project), or None."""
    rel = normalized(rel)
    parts = rel.lower().split("/")
    if parts[0] in RECORD_DIRS:
        return f"{parts[0]}/ holds records, not living docs"
    if rel.lower() in RECORD_FILES:
        return f"{rel} is a record"
    hit = policy.protected_match(policy.load_policy(root), rel)
    if hit:
        return f"{rel} is a protected path ({hit})"
    return None


def merge(root, deltas: List[dict]) -> Dict[Path, str]:
    """Apply every delta in memory; {path: new text}. PolierError names the failing delta."""
    root = Path(root).resolve()
    texts: Dict[Path, List[str]] = {}
    for delta in deltas:
        label = f"delta {delta['number']} ({delta['file']}#{delta['heading']} {delta['kind']})"
        target = (root / delta["file"]).resolve()
        if root != target and root not in target.parents:
            raise PolierError(f"{label}: file is outside the project")
        for rel in (delta["file"], target.relative_to(root).as_posix()):
            why = _forbidden_target(root, rel)
            if why:
                raise PolierError(f"{label}: {why}")
        if target not in texts:
            try:
                texts[target] = _read(target).split("\n")
            except (OSError, UnicodeDecodeError) as exc:
                raise PolierError(f"{label}: cannot read {delta['file']}: {exc}") from exc
        lines = texts[target]
        try:
            start, end = _section(lines, delta["heading"])
            if delta["kind"] == "ADDED":
                _add(lines, start, end, delta["added"])
            else:
                new = delta["new"] if delta["kind"] == "MODIFIED" else None
                texts[target] = _replace(lines, start, end, delta["old"], new)
        except ValueError as exc:
            raise PolierError(f"{label}: {exc}") from exc
    return {path: "\n".join(lines) for path, lines in texts.items()}


def apply(root, change_id: str, by: str = "owner") -> dict:
    """Merge the deltas of a proposal and mark it applied.

    Returns {"applied": bool, "changed": [file#heading, ...], "note": str}.
    PolierError (nothing written) when the proposal is invalid, a delta does not
    apply, no granted scope_change approval names the ID or a linked task is not done.
    """
    proposal = load(root, change_id)
    if proposal["status"] == "applied":
        return {"applied": False, "changed": [], "note": f"{change_id} is already applied; nothing to do"}
    if proposal["errors"]:
        raise PolierError(f"{change_id} is not valid: " + "; ".join(proposal["errors"]))
    written = merge(root, proposal["deltas"])
    approval = find_approval(root, change_id)
    if approval is None:
        raise PolierError(f"no granted scope_change approval names {change_id} in its note "
                          f"(tools/approve.py request --action scope_change --note '{change_id} …')")
    pending = open_tasks(root, proposal["tasks"])
    if pending:
        raise PolierError(f"linked task(s) not done: {', '.join(pending)}")
    path = proposal_path(root, change_id)
    text = _read(path)
    stamp = f"**Status:** applied {dt.date.today().isoformat()} by {' '.join(str(by).split()) or 'owner'}"
    text, count = STATUS_FIELD_RE.subn(lambda _m: stamp, text, count=1)
    if count != 1:
        raise PolierError(f"{change_id}: status line not found")
    for target, content in written.items():
        _write(target, content)
    _write(path, text)
    changed = list(dict.fromkeys(f"{d['file']}#{d['heading']}" for d in proposal["deltas"]))
    return {"applied": True, "changed": changed, "approval": approval.get("id"),
            "note": f"{change_id} applied by {by}"}
