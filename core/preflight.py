"""Preflight: is everything in place before work starts or continues?

One list of checks for the machine (Python, git), the Polier package and, when
the folder is inside a project, the project itself (board, line, policy,
generated pages, claims, worktree state). Every check says ok, warn or fail and,
when not ok, what fixes it. Nothing is changed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from . import claims
from .board import board_errors, load_board, tasks_of
from .errors import PolierError

MIN_PYTHON = (3, 9)
PACKAGE = Path(__file__).resolve().parent.parent


def _check(name: str, level: str, detail: str, fix: str = "") -> dict:
    entry = {"check": name, "level": level, "detail": detail}
    if fix and level != "ok":
        entry["fix"] = fix
    return entry


def _git(root, *args) -> Optional[str]:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                                check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _find_project(start: Path) -> Optional[Path]:
    for folder in [start, *start.parents]:
        if (folder / "board.json").is_file() or (folder / "factory.json").is_file():
            return folder
    return None


def machine() -> List[dict]:
    out: List[dict] = []
    version = ".".join(str(n) for n in sys.version_info[:3])
    if sys.version_info[:2] >= MIN_PYTHON:
        out.append(_check("python", "ok", f"Python {version}"))
    else:
        out.append(_check("python", "fail", f"Python {version}; Polier needs 3.9 or newer",
                          "install Python 3.9+ and set the plugin option python to it"))
    if shutil.which("git"):
        out.append(_check("git", "ok", _git(".", "--version") or "git found"))
    else:
        out.append(_check("git", "fail", "git is not on the PATH",
                          "install git; claims, worktrees and the stop check need it"))
    return out


def package() -> List[dict]:
    version_file = PACKAGE / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "?"
    missing = [p for p in ("tools/guard.py", "tools/state.py", "tools/gate.py", "factory/catalog.json",
                           "roles/roles.json", "templates/AGENTS.template.md") if not (PACKAGE / p).is_file()]
    if missing:
        return [_check("polier", "fail", f"Polier {version}: missing {', '.join(missing)}",
                       "reinstall the plugin (dsh plugin add github:atshv/polier)")]
    return [_check("polier", "ok", f"Polier {version}")]


def _json_file(root: Path, name: str) -> Optional[dict]:
    try:
        data = json.loads((root / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def project(root: Path) -> List[dict]:
    out: List[dict] = []
    inside_git = _git(root, "rev-parse", "--is-inside-work-tree") == "true"
    if not inside_git:
        out.append(_check("repository", "fail", "the project is not a git repository",
                          "git init -b main, then commit the plan files"))
    else:
        name = _git(root, "config", "user.name")
        email = _git(root, "config", "user.email")
        if not (name and email):
            out.append(_check("repository", "warn", "git user.name or user.email is not set; commits will fail",
                              "git config user.name \"…\" and git config user.email \"…\""))
        elif _git(root, "rev-parse", "--verify", "HEAD") is None:
            out.append(_check("repository", "warn", "no commit yet",
                              "commit the plan files once the plan station is closed"))
        else:
            dirty = [line for line in (_git(root, "status", "--porcelain") or "").splitlines() if line]
            branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "?"
            if dirty:
                out.append(_check("repository", "warn", f"branch {branch}, {len(dirty)} uncommitted change(s)",
                                  "commit finished work before the next task starts"))
            else:
                out.append(_check("repository", "ok", f"branch {branch}, clean"))

    line = None
    if (root / "factory.json").is_file():
        line = _json_file(root, "factory.json")
        if line is None:
            out.append(_check("line", "fail", "factory.json is not valid JSON",
                              "restore it from git; only pl_factory writes it"))
        else:
            from . import factory
            station = factory.current_station(line)
            out.append(_check("line", "ok", f"current station: {station}" if station else "every station is closed"))
    else:
        out.append(_check("line", "warn", "no factory.json",
                          "start the line with pl_factory init (platforms, traits)"))

    board = None
    if (root / "board.json").is_file():
        try:
            board = load_board(root)
        except (PolierError, ValueError) as exc:
            out.append(_check("board", "fail", f"board.json cannot be read: {exc}",
                              "restore it from git or fix the JSON"))
        if board is not None:
            errors = board_errors(board)
            tasks = tasks_of(board)
            counts = {}
            for task in tasks:
                counts[task.get("status", "?")] = counts.get(task.get("status", "?"), 0) + 1
            summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) or "no tasks"
            if errors:
                out.append(_check("board", "fail", f"{len(errors)} schema error(s), first: {errors[0]}",
                                  "run pl_check and fix what it lists"))
            else:
                out.append(_check("board", "ok", f"{len(tasks)} task(s): {summary}"))
    elif line is not None and line.get("stations", {}).get("plan", {}).get("status") == "done":
        out.append(_check("board", "fail", "the plan station is closed but board.json is missing",
                          "restore board.json from git"))

    if board is not None:
        if (root / "policy.json").is_file():
            policy = _json_file(root, "policy.json")
            out.append(_check("policy", "ok" if policy is not None else "fail",
                              "policy.json present" if policy is not None else "policy.json is not valid JSON",
                              "fix the JSON; templates/policy.json is the reference"))
        else:
            out.append(_check("policy", "warn", "no policy.json: limits, protected paths and approvals are off",
                              "copy templates/policy.json and adjust it (plan station)"))
        status = root / "STATUS.md"
        if not status.is_file() or status.stat().st_mtime < (root / "board.json").stat().st_mtime - 1:
            out.append(_check("status page", "warn", "STATUS.md is missing or older than board.json",
                              "pl_check regenerates it"))
        else:
            out.append(_check("status page", "ok", "STATUS.md is current"))

    if inside_git:
        try:
            folder = claims.claim_dir(root)
        except PolierError:
            folder = None
        live = {c.get("task") for c in claims.live_claims(root)}
        stale = []
        if folder is not None and folder.is_dir():
            stale = sorted(p.stem for p in folder.glob("*.json") if p.stem not in live)
        running = {t.get("id") for t in tasks_of(board)} if board else set()
        unknown = sorted(t for t in live if running and t not in running)
        detail = f"{len(live)} live claim(s)" + (f" ({', '.join(sorted(live))})" if live else "")
        if stale or unknown:
            parts = []
            if stale:
                parts.append(f"expired: {', '.join(stale)}")
            if unknown:
                parts.append(f"not on the board: {', '.join(unknown)}")
            out.append(_check("claims", "warn", f"{detail}; {'; '.join(parts)}",
                              "an expired claim is taken over by the next pl_task; a session that crashed "
                              "mid-task should be resumed with pl_task on the same task"))
        else:
            out.append(_check("claims", "ok", detail))
    return out


def run(start) -> dict:
    """Every check for `start` (a folder): machine, package and, inside a project, the project."""
    start = Path(start).resolve()
    checks = machine() + package()
    root = _find_project(start)
    if root is None:
        checks.append(_check("project", "warn", "no Polier project in this folder or above",
                             "write project-input.md and call pl_factory init to start one"))
    else:
        checks.extend(project(root))
    worst = "fail" if any(c["level"] == "fail" for c in checks) else \
        "warn" if any(c["level"] == "warn" for c in checks) else "ok"
    return {"ok": worst != "fail", "result": worst, "project": str(root) if root else None, "checks": checks}
