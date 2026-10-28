"""Rules as code: limits, protected paths, dependency manifests, approvals, commands.

A project without ``policy.json`` keeps working exactly as in 1.0:
``load_policy()`` returns ``{"enabled": False}`` and every matcher
(``protected_match``, ``manifest_match``, ``command_denial``) returns None, so
no new rule can fire. The defaults below are the template a generated project
gets, not a silent enforcement for an existing one.

Path patterns are ``/``-separated; ``**`` matches zero or more segments, while
``*`` and ``?`` stay inside one segment. A pattern without ``/`` matches the
basename at any depth (``.env`` matches ``.env`` and ``apps/web/.env``). The
comparison ignores case on macOS and Windows, like the file system
(``core.paths.CASE_INSENSITIVE``).

Command rules are matched against the plain text of each simple command of a
line (``core.shell.command_segments``): quotes and heredoc bodies never count
as commands, assignments and wrappers (``sudo``, ``env``, ``nohup``, ...) are
stripped before matching.
"""
from __future__ import annotations

import copy
import fnmatch
import json
from pathlib import Path
from typing import Dict, List, Optional

from .errors import PolierError
from .paths import CASE_INSENSITIVE, normalized
from .shell import command_segments

POLICY = "policy.json"

ACTIONS = (
    "new_dependency",
    "scope_change",
    "merge_to_base",
    "release",
    "reopen_done",
    "protected_path",
    "state_override",
)

DEFAULTS: Dict[str, object] = {
    "version": 1,
    "limits": {
        "max_attempts_per_task": 3,
        "max_in_progress": 2,
        "max_review_rounds": 3,
    },
    "scope": {
        "protected_paths": [".env", ".env.*", "secrets/**", "**/*.pem", "**/*.key",
                            "**/id_rsa*"],
    },
    "dependencies": {
        "approval": True,
        "manifests": ["package.json", "pyproject.toml", "Cargo.toml", "go.mod",
                      "Package.swift", "requirements.txt"],
    },
    "approvals": {
        "actions": ["new_dependency", "scope_change", "merge_to_base", "release",
                    "reopen_done", "protected_path"],
        "approver": "owner",
    },
    "commands": {
        "deny": ["git push*", "npm publish*", "pnpm publish*", "yarn publish*",
                 "docker push*", "gh release*", "kubectl apply*", "kubectl delete*",
                 "terraform apply*", "rm -rf /*"],
        "lead_only": ["*tools/state.py set*", "*tools/approve.py grant*",
                      "*tools/approve.py deny*", "*tools/worktree.py finish*"],
        "warn": ["*kill*", "*pkill*", "killall*"],
    },
    "checks": {
        "review_before_done": True,
        "handoff_before_done": True,
        "run_record": True,
        "disjoint_scopes": True,
    },
}

LIMIT_RANGES = {
    "max_attempts_per_task": (1, 10),
    "max_in_progress": (1, 64),
    "max_review_rounds": (1, 20),
}

_SECTIONS = {
    "limits": set(DEFAULTS["limits"]),
    "scope": set(DEFAULTS["scope"]),
    "dependencies": set(DEFAULTS["dependencies"]),
    "approvals": set(DEFAULTS["approvals"]),
    "commands": set(DEFAULTS["commands"]),
    "checks": set(DEFAULTS["checks"]),
}
_TOP_KEYS = frozenset({"version", "limits", "scope", "dependencies", "approvals",
                       "commands", "checks", "enabled"})


# ---------------------------------------------------------------------------
# loading and validation
# ---------------------------------------------------------------------------

def _merge(base: dict, update: dict) -> dict:
    """`base` deep-merged with `update`: nested objects are merged, everything else replaced."""
    out = copy.deepcopy(base)
    for key, value in (update or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_policy(root, strict: bool = False) -> dict:
    """The policy of `root` with the defaults filled in.

    Without ``policy.json`` the result is ``{"enabled": False}`` (and a
    PolierError with ``strict``). A file that exists but cannot be read or
    parsed is an error in every mode: a broken policy must not silently
    disable its own rules. Semantic problems are left to `policy_errors`.
    """
    path = Path(root) / POLICY
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        if strict:
            raise PolierError(
                f"no policy.json in {root} (a 1.0 project does not need one)") from exc
        return {"enabled": False}
    except OSError as exc:
        raise PolierError(f"policy.json is unreadable: {exc}") from exc
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise PolierError(f"policy.json is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PolierError("policy.json must be a JSON object")
    if strict:
        errors = policy_errors(parsed)
        if errors:
            raise PolierError("; ".join(errors))
    policy = _merge(DEFAULTS, parsed)
    policy["enabled"] = True
    return policy


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list_problem(value) -> Optional[str]:
    if not isinstance(value, list):
        return "must be a list of non-empty strings"
    if any(not _is_text(item) for item in value):
        return "must be a list of non-empty strings"
    return None


def _section_problems(label: str, section, key: str, errors: List[str]) -> None:
    if section is None:
        return
    if not isinstance(section, dict):
        errors.append(f"policy.json: {label} must be an object")
        return
    for unknown in sorted(set(section) - _SECTIONS[key]):
        errors.append(f"policy.json: {label} has unknown key {unknown!r}")


def policy_errors(policy) -> List[str]:
    """Every semantic problem of a policy object; [] when it is valid.

    Unknown keys (at the top level and in every section), a version other than
    1, lists that are not lists of non-empty strings, non-boolean checks and
    limits outside their range are errors. ``{"enabled": False}`` is valid:
    there is nothing to check.
    """
    if not isinstance(policy, dict):
        return ["policy.json: the policy must be a JSON object"]
    if policy.get("enabled") is False:
        return []
    errors: List[str] = []
    for unknown in sorted(set(policy) - _TOP_KEYS):
        errors.append(f"policy.json: unknown key {unknown!r}")

    version = policy.get("version", 1)
    if not _is_int(version) or version != 1:
        errors.append(f"policy.json: version must be 1 (is {version!r})")

    for key in ("limits", "scope", "dependencies", "approvals", "commands", "checks"):
        _section_problems(key, policy.get(key), key, errors)

    limits = policy.get("limits") if isinstance(policy.get("limits"), dict) else {}
    for key, (low, high) in LIMIT_RANGES.items():
        if key not in limits:
            continue
        value = limits[key]
        if not _is_int(value) or not low <= value <= high:
            errors.append(
                f"policy.json: limits.{key} must be an integer {low}–{high} (is {value!r})")

    scope = policy.get("scope") if isinstance(policy.get("scope"), dict) else {}
    if "protected_paths" in scope:
        problem = _string_list_problem(scope["protected_paths"])
        if problem:
            errors.append(f"policy.json: scope.protected_paths {problem}")

    dependencies = policy.get("dependencies") if isinstance(policy.get("dependencies"), dict) else {}
    if "approval" in dependencies and not isinstance(dependencies["approval"], bool):
        errors.append("policy.json: dependencies.approval must be true or false")
    if "manifests" in dependencies:
        problem = _string_list_problem(dependencies["manifests"])
        if problem:
            errors.append(f"policy.json: dependencies.manifests {problem}")

    approvals = policy.get("approvals") if isinstance(policy.get("approvals"), dict) else {}
    if "actions" in approvals:
        problem = _string_list_problem(approvals["actions"])
        if problem:
            errors.append(f"policy.json: approvals.actions {problem}")
        else:
            for action in approvals["actions"]:
                if action not in ACTIONS:
                    errors.append(
                        f"policy.json: approvals.actions has unknown action {action!r} "
                        f"(known: {', '.join(ACTIONS)})")
    if "approver" in approvals and not _is_text(approvals["approver"]):
        errors.append("policy.json: approvals.approver must be a non-empty string")

    commands = policy.get("commands") if isinstance(policy.get("commands"), dict) else {}
    for key in ("deny", "lead_only", "warn"):
        if key in commands:
            problem = _string_list_problem(commands[key])
            if problem:
                errors.append(f"policy.json: commands.{key} {problem}")

    checks = policy.get("checks") if isinstance(policy.get("checks"), dict) else {}
    for key, value in checks.items():
        if not isinstance(value, bool):
            errors.append(f"policy.json: checks.{key} must be true or false")
    return errors


def enabled(policy) -> bool:
    """True when the policy enforces its rules; a raw policy object counts as enabled."""
    if not isinstance(policy, dict) or not policy:
        return False
    return bool(policy.get("enabled", True))


def _raw_section(policy, key: str) -> dict:
    policy = policy if isinstance(policy, dict) else {}
    raw = policy.get(key)
    return raw if isinstance(raw, dict) else {}


def limits(policy) -> Dict[str, int]:
    """The three limits with the defaults for missing or invalid values."""
    raw = _raw_section(policy, "limits")
    out = dict(DEFAULTS["limits"])
    for key in out:
        value = raw.get(key)
        if _is_int(value):
            out[key] = value
    return out


def action_required(policy, action: str) -> bool:
    """True when `action` is listed in approvals.actions of an enabled policy."""
    if not enabled(policy):
        return False
    raw = _raw_section(policy, "approvals").get("actions")
    actions = raw if isinstance(raw, list) else DEFAULTS["approvals"]["actions"]
    return action in actions


def approver(policy) -> str:
    """Who grants approvals; "owner" by default."""
    raw = _raw_section(policy, "approvals").get("approver")
    return raw if _is_text(raw) else DEFAULTS["approvals"]["approver"]


def checks(policy) -> Dict[str, bool]:
    """The checks of the policy with defaults for every missing flag."""
    raw = _raw_section(policy, "checks")
    out = dict(DEFAULTS["checks"])
    for key in out:
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    return out


# ---------------------------------------------------------------------------
# patterns
# ---------------------------------------------------------------------------

def glob_match(pattern, text) -> bool:
    """fnmatch-style match, case-insensitive on every OS (command rules)."""
    if not isinstance(pattern, str) or not isinstance(text, str):
        return False
    return fnmatch.fnmatchcase(text.casefold(), pattern.casefold())


def _segments_match(pattern: List[str], index: int, target: List[str], position: int) -> bool:
    if index == len(pattern):
        return position == len(target)
    head = pattern[index]
    if head == "**":
        if _segments_match(pattern, index + 1, target, position):
            return True
        return position < len(target) and _segments_match(pattern, index, target, position + 1)
    if position >= len(target):
        return False
    return (fnmatch.fnmatchcase(target[position], head)
            and _segments_match(pattern, index + 1, target, position + 1))


def path_matches(pattern, rel) -> bool:
    """True when the project-relative path `rel` matches `pattern`.

    ``**`` matches zero or more segments and a pattern without ``/`` matches
    the basename at any depth. Case is ignored on macOS and Windows.
    """
    pattern = normalized(pattern)
    rel = normalized(rel)
    if not pattern:
        return False
    if CASE_INSENSITIVE:
        pattern, rel = pattern.casefold(), rel.casefold()
    segments = rel.split("/") if rel else []
    if "/" not in pattern:
        basename = segments[-1] if segments else ""
        return bool(basename) and fnmatch.fnmatchcase(basename, pattern)
    return _segments_match(pattern.split("/"), 0, segments, 0)


def _first_match(patterns, rel) -> Optional[str]:
    if not isinstance(patterns, list):
        return None
    for pattern in patterns:
        if _is_text(pattern) and path_matches(pattern, rel):
            return pattern
    return None


def protected_match(policy, rel) -> Optional[str]:
    """The first protected pattern `rel` matches, or None (also when the policy is off)."""
    if not enabled(policy):
        return None
    patterns = _raw_section(policy, "scope").get(
        "protected_paths", DEFAULTS["scope"]["protected_paths"])
    return _first_match(patterns, rel)


def manifest_match(policy, rel) -> Optional[str]:
    """The first dependency manifest `rel` matches, or None (also when the policy is off)."""
    if not enabled(policy):
        return None
    patterns = _raw_section(policy, "dependencies").get(
        "manifests", DEFAULTS["dependencies"]["manifests"])
    return _first_match(patterns, rel)


# ---------------------------------------------------------------------------
# command rules
# ---------------------------------------------------------------------------

def _read_rule(policy, rule: str) -> List[str]:
    raw = _raw_section(policy, "commands").get(rule, DEFAULTS["commands"][rule])
    return [item for item in raw if _is_text(item)] if isinstance(raw, list) else []


def _denial_reason(rule: str, pattern: str, segment: str, role: str) -> str:
    if rule == "lead_only":
        return (f"only the lead may run a command matching {pattern!r} "
                f"(role {role} ran {segment!r})")
    return (f"the command matches deny pattern {pattern!r} ({segment!r}); "
            "it is blocked for every role")


def command_denial(policy, command, role: str = "worker") -> Optional[dict]:
    """The first command rule `command` breaks, or None.

    ``deny`` blocks every role, ``lead_only`` only the roles ``worker`` and
    ``reviewer``. The result is
    ``{"rule", "pattern", "command", "reason"}`` and names the matched segment
    in the reason. With the policy off nothing is denied.
    """
    if not enabled(policy):
        return None
    text = "" if command is None else str(command)
    if not text.strip():
        return None
    for rule in ("deny", "lead_only"):
        if rule == "lead_only" and role not in ("worker", "reviewer"):
            continue
        for pattern in _read_rule(policy, rule):
            for segment in command_segments(text):
                if glob_match(pattern, segment):
                    return {
                        "rule": rule,
                        "pattern": pattern,
                        "command": text,
                        "reason": _denial_reason(rule, pattern, segment, role),
                    }
    return None
