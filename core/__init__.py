"""Polier core: the enforcement rules without any harness.

Every adapter (DeepSeek Harness, Claude Code, git hooks) and every CLI in
tools/ calls these functions. Standard library only, Python 3.9+.
"""
from __future__ import annotations

from .board import active_tasks, find_root, load_board, pick_task, ready_tasks
from .errors import PolierError
from .evidence import verify_evidence
from .gate import run_gate
from .scope import changed_files, check_stop, check_write, scope_check

__all__ = [
    "PolierError",
    "active_tasks", "find_root", "load_board", "pick_task", "ready_tasks",
    "changed_files", "check_stop", "check_write", "scope_check",
    "run_gate", "verify_evidence",
]
