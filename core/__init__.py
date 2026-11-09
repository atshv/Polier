"""Polier core: the enforcement rules without any harness.

The DeepSeek Harness plugin (through tools/) and every CLI in tools/ call
these functions. Standard library only, Python 3.9+.

The modules group the rules:

- ``board``: reading and validating board.json, task
  selection, stage reporting and the ready list.
- ``scope``: the write rules and the stop check (write scopes, lead-owned
  files, worktree enforcement, foreign changes).
- ``guard``: the answer for one harness tool call (write or command), with
  the messages the session sees.
- ``gate`` / ``evidence``: gate records (pass, fail, timeout, busy, infra) and
  the verification of the records a done task lists.
- ``slots``: runtime slots per worktree (ports, database, bucket).
- ``locks``: exclusive gates.
- ``claims``: cross-harness task claims with a heartbeat.
- ``shell``: the files a shell command visibly writes, and the
  command segments a policy rule is matched against.
- ``boundaries``: package import rules.
- ``policy``: policy.json as code (limits, protected paths, dependency
  manifests, approval actions, command rules).
- ``runs``: runs/<ID>.json, the attempts and events of one task.
- ``approvals``: reviews/approvals/AP-NNN.json, the human decisions.
- ``state``: the task state machine, its checkpoints and the atomic write of
  board.json.
- ``factory``: the software factory line - nine stations from idea to
  operate, the checklist catalog and the evidence per item (factory.json).
"""
from __future__ import annotations

from . import approvals, boundaries, claims, factory, locks, policy, runs, slots, state
from .approvals import has_grant, request as request_approval
from .board import (active_tasks, board_errors, find_root, load_board, pick_task,
                    ready_tasks, stage_report, task_stage_id)
from .claims import live_claims
from .errors import PolierError
from .evidence import gate_records, passing_gates, verify_evidence
from .gate import run_gate, write_record
from .locks import acquire_lock, release_lock
from .policy import (action_required, approver, command_denial, enabled as policy_enabled,
                     glob_match, limits, load_policy, manifest_match, path_matches,
                     policy_errors, protected_match)
from .runs import attempt_count, last_event, load_run, record_gate, run_state, summary
from .scope import changed_files, check_stop, check_write, scope_check
from .state import TransitionBlocked, check_transition, set_status, status_of
from .state import TRANSITIONS as STATE_TRANSITIONS

__all__ = [
    "PolierError", "TransitionBlocked",
    "active_tasks", "board_errors", "find_root", "load_board", "pick_task", "ready_tasks",
    "stage_report", "task_stage_id",
    "changed_files", "check_stop", "check_write", "scope_check",
    "run_gate", "write_record", "verify_evidence", "gate_records", "passing_gates",
    "acquire_lock", "release_lock", "live_claims",
    "load_policy", "policy_errors", "policy_enabled", "limits", "action_required",
    "approver", "path_matches", "protected_match", "manifest_match", "command_denial",
    "glob_match",
    "load_run", "attempt_count", "run_state", "last_event", "record_gate", "summary",
    "has_grant", "request_approval",
    "check_transition", "set_status", "status_of", "STATE_TRANSITIONS",
    "approvals", "boundaries", "claims", "factory", "locks", "policy", "runs", "slots", "state",
]
