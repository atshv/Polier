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
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import PolierError

CACHE_TTL = 30.0
TIMEOUT = 20
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
REMOTE = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?$")


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
                                env={**os.environ, "GH_PROMPT_DISABLED": "1",
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


# -- account connection (2.5) -------------------------------------------------
#
# "Connect GitHub" signs the gh CLI in — with the device flow or a token — so
# the panel, the task PR/CI mapping and agent sessions that use gh all work.
# Polier itself still stores no credential: gh keeps the token in its own store.

HOST = "github.com"
LOGGED_IN = re.compile(r"Logged in to (\S+)(?: account| as) (\S+)")
SCOPES = re.compile(r"Token scopes:\s*(.*)")
PROTOCOL_LINE = re.compile(r"Git operations protocol:\s*(\S+)")
SOURCE = re.compile(r"Logged in to \S+(?: account| as) \S+ \(([^)]+)\)")


def auth_status(host: str = HOST) -> Dict[str, Any]:
    """Whether gh is installed and signed in, with the account and token scopes."""
    executable = shutil.which("gh")
    if not executable:
        return {"gh": False, "logged_in": False, "host": host, "user": None, "scopes": [],
                "reason": "the gh CLI is not installed", "install": "https://cli.github.com"}
    try:
        result = subprocess.run([executable, "auth", "status", "--hostname", host],
                                capture_output=True, text=True, check=False, timeout=TIMEOUT,
                                env={**os.environ, "GH_PROMPT_DISABLED": "1"})
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"gh": True, "logged_in": False, "host": host, "user": None, "scopes": [], "reason": str(exc)}
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    match = LOGGED_IN.search(text)
    logged_in = result.returncode == 0 and match is not None
    scopes_match = SCOPES.search(text)
    scopes = re.findall(r"'([^']+)'", scopes_match.group(1)) if scopes_match else []
    protocol = PROTOCOL_LINE.search(text)
    source = SOURCE.search(text)
    value: Dict[str, Any] = {
        "gh": True, "logged_in": logged_in, "host": host,
        "user": match.group(2) if match else None,
        "scopes": scopes, "protocol": protocol.group(1) if protocol else None,
        "source": source.group(1) if source else None,
    }
    if not logged_in:
        lines = [line.strip() for line in text.splitlines() if line.strip() and line.strip() != host]
        failing = [line for line in lines if line.startswith("X") or "not logged" in line.lower()]
        details = [line for line in lines if "invalid" in line.lower() or "expired" in line.lower()]
        reason = (failing[:1] + details[:1]) or lines[:1] or ["not signed in"]
        value["reason"] = " — ".join(line.strip(" -✓X!") for line in reason)[:300]
    missing = [scope for scope in ("repo", "read:org") if logged_in and scopes and scope not in scopes]
    value["missing_scopes"] = missing
    return value


def login_with_token(token: str, host: str = HOST) -> Dict[str, Any]:
    """Sign gh in with a personal access token (classic: repo, read:org)."""
    executable = shutil.which("gh")
    if not executable:
        raise PolierError("the gh CLI is not installed (https://cli.github.com)")
    token = (token or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{20,255}", token):
        raise PolierError("that does not look like a GitHub token")
    env = {key: value for key, value in os.environ.items() if key not in ("GH_TOKEN", "GITHUB_TOKEN")}
    result = subprocess.run([executable, "auth", "login", "--hostname", host, "--with-token"],
                            input=token + "\n", capture_output=True, text=True, check=False,
                            timeout=TIMEOUT, env={**env, "GH_PROMPT_DISABLED": "1"})
    if result.returncode != 0:
        raise PolierError((result.stderr or result.stdout or "gh auth login failed").strip().splitlines()[0][:300])
    clear_cache()
    return auth_status(host)


def logout(host: str = HOST) -> Dict[str, Any]:
    executable = shutil.which("gh")
    if not executable:
        raise PolierError("the gh CLI is not installed")
    current = auth_status(host)
    args = [executable, "auth", "logout", "--hostname", host]
    if current.get("user"):
        args += ["--user", str(current["user"])]
    result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=TIMEOUT,
                            env={**os.environ, "GH_PROMPT_DISABLED": "1"})
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "gh auth logout failed").strip().splitlines()[0][:300]
        if current.get("source") in ("GH_TOKEN", "GITHUB_TOKEN"):
            message = f"signed in through the {current['source']} environment variable; unset it to sign out"
        raise PolierError(message)
    clear_cache()
    return auth_status(host)


DEVICE_CODE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b")
DEVICE_URL = re.compile(r"(https://\S*github\S*/login/device)")


class DeviceLogin:
    """One ``gh auth login --web`` run: exposes the one-time code and waits for it.

    The dashboard shows the code and a link to the device page; the user
    confirms in the browser and gh finishes on its own. Only one login runs at
    a time.
    """

    def __init__(self, host: str = HOST, on_change=None) -> None:
        self.host = host
        self.on_change = on_change
        self.lock = threading.Lock()
        self.process: Optional[subprocess.Popen] = None
        self.state: Dict[str, Any] = {"status": "idle"}

    def view(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.state)

    def _set(self, **values: Any) -> None:
        with self.lock:
            self.state.update(values)
        if self.on_change:
            try:
                self.on_change(self.view())
            except Exception:  # noqa: BLE001 - a listener must not break the login
                pass

    def start(self, scopes: Optional[List[str]] = None, wait: float = 20.0) -> Dict[str, Any]:
        executable = shutil.which("gh")
        if not executable:
            raise PolierError("the gh CLI is not installed (https://cli.github.com)")
        with self.lock:
            if self.process and self.process.poll() is None:
                return dict(self.state)
        args = [executable, "auth", "login", "--hostname", self.host, "--web",
                "--git-protocol", "https", "--skip-ssh-key"]
        for scope in scopes or []:
            args += ["--scopes", scope]
        env = {key: value for key, value in os.environ.items() if key not in ("GH_TOKEN", "GITHUB_TOKEN")}
        env.update({"GH_BROWSER": "true", "BROWSER": "true", "GH_NO_UPDATE_NOTIFIER": "1"})
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        with self.lock:
            self.process = process
            self.state = {"status": "starting", "code": None, "url": "https://github.com/login/device",
                          "started": _now(), "error": None, "output": []}
        ready = threading.Event()
        threading.Thread(target=self._follow, args=(process, ready), daemon=True).start()
        ready.wait(wait)
        return self.view()

    def _follow(self, process: subprocess.Popen, ready: threading.Event) -> None:
        output: List[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            text = line.strip()
            if not text:
                continue
            output.append(text[:300])
            code = DEVICE_CODE.search(text)
            url = DEVICE_URL.search(text)
            if url:
                self._set(url=url.group(1))
            if code and not self.view().get("code"):
                self._set(status="waiting", code=code.group(1), output=output[-12:])
                try:
                    assert process.stdin is not None
                    process.stdin.write("\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                ready.set()
        exit_code = process.wait()
        for stream in (process.stdin, process.stdout):
            try:
                if stream:
                    stream.close()
            except (OSError, ValueError):
                pass
        if self.view().get("status") == "cancelled":
            ready.set()
            return
        clear_cache()
        if exit_code == 0:
            status = auth_status(self.host)
            self._set(status="done", user=status.get("user"), finished=_now(), output=output[-12:])
        else:
            self._set(status="failed", finished=_now(), output=output[-12:],
                      error=(output[-1] if output else f"gh exited with {exit_code}"))
        ready.set()

    def cancel(self) -> Dict[str, Any]:
        with self.lock:
            process = self.process
        if process and process.poll() is None:
            self._set(status="cancelled", finished=_now())
            try:
                process.terminate()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
        return self.view()
