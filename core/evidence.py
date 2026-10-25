"""Verify the gate records that done tasks list as evidence."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import List, Tuple

# A record with one of these results is not proof that the gate passed: it
# describes the infrastructure around the gate (PL-03), so the task must be
# rerun alone instead of being marked failed.
INFRA_RESULTS = frozenset({"infra", "busy", "timeout"})


def _plain(path: str) -> str:
    return path.strip().replace("\\", "/").rstrip("/")


def _has_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=False)
    except FileNotFoundError:
        return False
    return True


def verify_evidence(root, board: dict) -> Tuple[List[str], List[str]]:
    """(errors, warnings) for every done task: each record exists, belongs to the
    task, passed, matches its log's checksum, and every listed gate has one."""
    root = Path(root)
    errors: List[str] = []
    warnings: List[str] = []
    head_ok = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False).returncode == 0 \
        if _has_git() else False

    for task in board.get("tasks", []):
        if not isinstance(task, dict) or task.get("status") != "done":
            continue
        tid = task.get("id", "?")
        entries = [e for e in task.get("evidence", []) if isinstance(e, str)]
        records = [e for e in entries if e.strip().endswith(".json")]
        if entries and not records:
            warnings.append(f"{tid}: evidence is free text; use the record paths printed by tools/gate.py")
            continue
        passed: set = set()
        rejected: set = set()
        for entry in records:
            rel = _plain(entry)
            path = (root / rel).resolve()
            if not path.is_file():
                errors.append(f"{tid}: evidence record missing: {rel}")
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                errors.append(f"{tid}: evidence record is not valid JSON: {rel}")
                continue
            gate = record.get("gate", "?")
            if record.get("task") != tid:
                errors.append(f"{tid}: evidence record {rel} belongs to task {record.get('task')!r}")
                continue
            log = path.parent / str(record.get("log", ""))
            if not record.get("log") or not log.is_file():
                errors.append(f"{tid}: log file of {rel} is missing")
                continue
            digest = hashlib.sha256(log.read_bytes()).hexdigest()
            if digest != record.get("log_sha256"):
                errors.append(f"{tid}: log of {rel} was changed after the gate ran (checksum mismatch)")
                continue
            if record.get("result") in INFRA_RESULTS:
                rejected.add(gate)
                errors.append(
                    f"{tid}: gate {gate} hit an infrastructure failure, rerun alone: {rel}")
                continue
            if record.get("exit_code") != 0:
                errors.append(f"{tid}: gate {gate} failed in {rel} (exit {record.get('exit_code')})")
                continue
            passed.add(gate)
            commit = record.get("commit")
            if head_ok and commit:
                ancestor = subprocess.run(
                    ["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "HEAD"],
                    capture_output=True, check=False)
                if ancestor.returncode != 0:
                    warnings.append(f"{tid}: record {rel} was made on commit {commit[:10]}, which is not in HEAD's history")
        for gate in task.get("gates", []):
            if isinstance(gate, str) and gate not in passed and gate not in rejected:
                errors.append(f"{tid}: no passing gate record for '{gate}' (run it with tools/gate.py --name {gate})")
    return errors, warnings
