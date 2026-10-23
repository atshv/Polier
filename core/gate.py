"""Gate records: run one gate command, keep the full output, write a checksummed record."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Union

EVIDENCE = Path("reviews") / "evidence"
NAME = re.compile(r"[A-Za-z0-9_.-]+")
ERROR_LINE = re.compile(r"error|fail|traceback|exception|assert|panic|fatal", re.IGNORECASE)


def valid_name(value: str) -> bool:
    """Task IDs and gate names may only contain letters, digits, '.', '_' and '-'."""
    return bool(NAME.fullmatch(value or ""))


def git(root: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return result.stdout if result.returncode == 0 else None


def new_base(folder: Path, stem: str) -> Path:
    """A path stem in `folder` for which neither .log nor .json exists yet."""
    base = folder / stem
    n = 2
    while (folder / f"{base.name}.log").exists() or (folder / f"{base.name}.json").exists():
        base = folder / f"{stem}-{n}"
        n += 1
    return base


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_gate(command: Union[str, Sequence[str]], task: str, name: str, root=".", *,
             shell: bool = False, timeout: int = 600) -> dict:
    """Run a gate in `root` and write <root>/reviews/evidence/<task>-<name>-<time>.log and .json.

    `command` is an argument list, or one string run through the system shell
    when `shell` is true. Never overwrites a record. Returns the record plus
    `output`, `log_path` and `record_path`; exit code 124 means timeout, 127
    command not found.
    """
    if not valid_name(task) or not valid_name(name):
        raise ValueError("--task and --name may only contain letters, digits, '.', '_' and '-'")
    argv: List[str] = [command] if shell else list(command)
    if shell and not isinstance(command, str):
        raise ValueError("a shell gate takes one command string")
    if not argv:
        raise ValueError("gate command missing")

    root = Path(root).resolve()
    folder = root / EVIDENCE
    folder.mkdir(parents=True, exist_ok=True)
    started = dt.datetime.now(dt.timezone.utc)
    base = new_base(folder, f"{task}-{name}-{started.strftime('%Y%m%dT%H%M%SZ')}")
    log, record_path = folder / f"{base.name}.log", folder / f"{base.name}.json"
    commit = (git(root, "rev-parse", "HEAD") or "").strip() or None
    status = git(root, "status", "--porcelain")

    shown = " ".join(" ".join(argv).split())
    try:
        result = subprocess.run(
            argv[0] if shell else argv, cwd=root, capture_output=True, text=True,
            timeout=timeout, check=False, shell=shell,
        )
        code = result.returncode
        output = (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired as exc:
        code = 124
        output = ((exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        output += f"\n[gate.py] stopped after {timeout}s\n"
    except FileNotFoundError:
        code = 127
        output = f"[gate.py] command not found: {argv[0]}\n"

    finished = dt.datetime.now(dt.timezone.utc)
    log.write_text(f"$ {shown}\n[exit {code}]\n\n{output}", encoding="utf-8")
    record = {
        "task": task,
        "gate": name,
        "command": shown,
        "exit_code": code,
        "started": started.isoformat(timespec="seconds"),
        "finished": finished.isoformat(timespec="seconds"),
        "commit": commit,
        "dirty": bool(status.strip()) if status is not None else None,
        "log": log.name,
        "log_sha256": sha256(log),
    }
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return {**record, "output": output, "log_path": log, "record_path": record_path, "root": root}


def summary(result: dict, tail: int = 15, max_errors: int = 15) -> List[str]:
    """Short report of a run_gate() result: one line on success, error and last lines on failure.
    The last line is always `record: <path>`."""
    root = result["root"]
    rel = result["log_path"].relative_to(root)
    rel_record = result["record_path"].relative_to(root).as_posix()
    lines = result["output"].splitlines()
    name, code = result["gate"], result["exit_code"]

    if code == 0:
        return [f"GATE {name}: PASS (exit 0) — {len(lines)} lines in {rel}", f"record: {rel_record}"]

    out = [f"GATE {name}: FAIL (exit {code}) — {result['command']}"]
    errors = [line for line in lines if ERROR_LINE.search(line)]
    if errors:
        out.append(f"-- first {min(len(errors), max_errors)} of {len(errors)} error lines")
        out += [line[:300] for line in errors[:max_errors]]
    out.append(f"-- last {min(len(lines), tail)} lines")
    out += [line[:300] for line in lines[-tail:]]
    out.append(f"-- full output: {rel}")
    out.append(f"record: {rel_record}")
    return out
