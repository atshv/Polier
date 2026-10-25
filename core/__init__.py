"""Polier core: the enforcement rules without any harness.

Every adapter (DeepSeek Harness, Claude Code, git hooks) and every CLI in
tools/ calls these functions. Standard library only, Python 3.9+.

The modules group the rules:

- ``board``: reading and validating board.json (schema 0.9 and 1.0), task
  selection, stage reporting and the ready list.
- ``scope``: the write guard and the stop check (write scopes, lead-owned
  files, worktree enforcement, foreign changes).
- ``gate`` / ``evidence``: gate records (pass, fail, timeout, busy, infra) and
  the verification of the records a done task lists.
- ``slots``: runtime slots per worktree (ports, database, bucket) - PL-02.
- ``locks``: exclusive gates - PL-03.
- ``claims``: cross-harness task claims with a heartbeat - PL-04.
- ``shell``: the files a shell command visibly writes - PL-16.
- ``boundaries``: package import rules - PL-07.
"""
from __future__ import annotations

from . import boundaries, claims, locks, slots
from .board import (active_tasks, board_errors, find_root, load_board, pick_task,
                    ready_tasks, schema_version, stage_report, task_stage_id)
from .claims import live_claims
from .errors import PolierError
from .evidence import verify_evidence
from .gate import run_gate, write_record
from .locks import acquire_lock, release_lock
from .scope import changed_files, check_stop, check_write, scope_check

__all__ = [
    "PolierError",
    "active_tasks", "board_errors", "find_root", "load_board", "pick_task", "ready_tasks",
    "schema_version", "stage_report", "task_stage_id",
    "changed_files", "check_stop", "check_write", "scope_check",
    "run_gate", "write_record", "verify_evidence",
    "acquire_lock", "release_lock", "live_claims",
    "boundaries", "claims", "locks", "slots",
]
