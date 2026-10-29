"""GitHub/CI status (2.4): a read-only panel fed by the ``gh`` CLI.

Polier never talks to GitHub itself. If the project has a GitHub ``origin`` and
the ``gh`` CLI is installed and authenticated, this module lists the open pull
requests and the recent workflow runs and maps them to tasks by branch
(``task/<ID>`` or the task's ``branch``). Without ``gh``, a remote or auth the
panel explains why it is unavailable — it never fails the dashboard.

Results are cached for 30 seconds; nothing is written and no credentials are
read or stored.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CACHE_TTL = 30.0
TIMEOUT = 20
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
REMOTE = __import__("re").compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?$")


def clear_cache() -> None:
    _CACHE.clear()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _remote(root: Path) -> Optional[Tuple[str, str, str]]:
    try:
        result = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                                capture_output=True, text=True, check=False, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    url = (result.stdout or "").strip()
    match = REMOTE.search(url)
    if not match:
        return None
    return match.group(1), match.group(2), url


def _gh(args: List[str]) -> Tuple[bool, str, str]:
    executable = shutil.which("gh")
    if not executable:
        return False, "", "the gh CLI is not installed"
    try:
        result = subprocess.run([executable, *args], capture_output=True, text=True,
                                check=False, timeout=TIMEOUT,
                                env={**__import__("os").environ, "GH_PROMPT_DISABLED": "1",
                                     "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired:
        return False, "", "gh timed out"
    except OSError as exc:
        return False, "", str(exc)
    if result.returncode != 0:
        return False, "", (result.stderr or result.stdout or "gh failed").strip().splitlines()[0][:300]
    return True, result.stdout or "", ""


def _check_state(pr: dict) -> str:
    checks = pr.get("statusCheckRollup") or []
    states = []
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        value = check.get("conclusion") or check.get("state") or ""
        states.append(str(value).upper())
    if not states:
        return "none"
    if any(state in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED") for state in states):
        return "fail"
    if any(state in ("PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "REQUESTED", "WAITING") for state in states):
        return "pending"
    if any(state in ("SUCCESS", "PASSED", "COMPLETED") for state in states):
        return "pass"
    return "pending"


def status(root, *, force: bool = False) -> Dict[str, Any]:
    """PRs, CI runs and their task mapping; available=false explains the reason."""
    root = Path(root).resolve()
    key = str(root)
    cached = _CACHE.get(key)
    if cached and not force and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    remote = _remote(root)
    if remote is None:
        value = {"available": False, "reason": "no GitHub origin remote", "repo": None,
                 "remote": None, "prs": [], "runs": [], "tasks": {},
                 "counts": {"prs": 0, "runs": 0, "failing_checks": 0}, "generated_at": _now()}
        _CACHE[key] = (time.time(), value)
        return value
    owner, repo, url = remote
    ok, stdout, error = _gh(["pr", "list", "--repo", f"{owner}/{repo}", "--state", "open",
                             "--limit", "50", "--json",
                             "number,title,state,url,headRefName,isDraft,updatedAt,statusCheckRollup"])
    if not ok:
        value = {"available": False, "reason": error, "repo": f"{owner}/{repo}", "remote": url,
                 "prs": [], "runs": [], "tasks": {},
                 "counts": {"prs": 0, "runs": 0, "failing_checks": 0}, "generated_at": _now()}
        _CACHE[key] = (time.time(), value)
        return value
    try:
        prs = json.loads(stdout)
    except ValueError:
        prs = []
    prs = [pr for pr in prs if isinstance(pr, dict)]
    for pr in prs:
        pr["checks"] = _check_state(pr)
        pr.pop("statusCheckRollup", None)
    ok_runs, runs_out, _ = _gh(["run", "list", "--repo", f"{owner}/{repo}", "--limit", "10",
                                "--json", "databaseId,name,status,conclusion,headBranch,url,createdAt,event"])
    runs: List[dict] = []
    if ok_runs:
        try:
            runs = [run for run in json.loads(runs_out) if isinstance(run, dict)]
        except ValueError:
            runs = []
    tasks: Dict[str, Dict[str, Any]] = {}
    try:
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        board = {}
    by_branch = {str(pr.get("headRefName") or ""): pr for pr in prs}
    for task in board.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id"))
        branch = task.get("branch") or f"task/{task_id}"
        pr = by_branch.get(str(branch))
        entry: Dict[str, Any] = {"branch": branch}
        if pr:
            entry["pr"] = {"number": pr.get("number"), "title": pr.get("title"),
                           "state": pr.get("state"), "url": pr.get("url"),
                           "checks": pr.get("checks"), "draft": pr.get("isDraft")}
        runs_for_branch = [run for run in runs if str(run.get("headBranch") or "") == str(branch)]
        if runs_for_branch:
            latest = max(runs_for_branch, key=lambda run: str(run.get("createdAt") or ""))
            entry["ci"] = {"status": latest.get("status"), "conclusion": latest.get("conclusion"),
                           "url": latest.get("url"), "name": latest.get("name"),
                           "at": latest.get("createdAt")}
        if pr or runs_for_branch:
            tasks[task_id] = entry
    value = {
        "available": True,
        "repo": f"{owner}/{repo}",
        "remote": url,
        "generated_at": _now(),
        "prs": prs,
        "runs": runs,
        "tasks": tasks,
        "counts": {"prs": len(prs), "runs": len(runs),
                   "failing_checks": len([pr for pr in prs if pr.get("checks") == "fail"])},
    }
    _CACHE[key] = (time.time(), value)
    return value
