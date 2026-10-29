"""Project-relative paths with forward slashes, the form every scope rule compares."""
from __future__ import annotations

import os
import platform
import posixpath
import re
import subprocess
from pathlib import Path
from typing import Optional

from .errors import PolierError

_DRIVE = re.compile(r"^[A-Za-z]:/")

# macOS and Windows file systems are case-insensitive by default: `Board.json`
# is the same file as `board.json` (PL-16). Elsewhere the comparison stays exact.
CASE_INSENSITIVE = platform.system() in ("Darwin", "Windows")


def normalized(path) -> str:
    """Forward slashes, no trailing slash, `.` and `..` resolved; '' for the root."""
    path = str(path if path is not None else "").strip().replace("\\", "/")
    if not path:
        return ""
    clean = posixpath.normpath(path)
    return "" if clean == "." else clean.rstrip("/")


def inside(path, entry) -> bool:
    """True if `path` equals `entry` or lies below the folder `entry`.

    On macOS and Windows the comparison ignores case, as the file system does.
    """
    path, entry = normalized(path), normalized(entry)
    if not entry:
        return False
    if CASE_INSENSITIVE:
        path, entry = path.casefold(), entry.casefold()
    return path == entry or path.startswith(entry + "/")


def is_absolute(path: str) -> bool:
    """POSIX or Windows absolute path, after normalization."""
    return path.startswith("/") or bool(_DRIVE.match(path))


def outside(rel: str) -> bool:
    """True for a project-relative path that leaves the project."""
    return rel == ".." or rel.startswith("../") or is_absolute(rel)


def resolve(base, target) -> str:
    """`target` as an absolute path; relative targets are taken from `base`."""
    return os.path.abspath(os.path.join(str(base), str(target)))


def relative(root, target) -> str:
    """Path of `target` relative to `root`, with forward slashes; starts with '../' when outside."""
    try:
        rel = os.path.relpath(str(target), str(root))
    except ValueError:  # another drive on Windows
        return normalized(target)
    return normalized(rel.replace(os.sep, "/"))


# ---------------------------------------------------------------------------
# git locations shared by all worktrees of a project (PL-02, PL-03, PL-04)
# ---------------------------------------------------------------------------

def _git(root, *args: str) -> Optional[str]:
    """stdout of a git command, or None when git is missing or the call fails."""
    try:
        result = subprocess.run(["git", "-C", str(root), *args],
                                capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def git_common_dir(root) -> Path:
    """The .git folder shared by every worktree of the repo (`<repo>/.git`).

    Raises PolierError when `root` is not inside a git repository.
    """
    value = _git(root, "rev-parse", "--git-common-dir")
    if not value:
        raise PolierError(f"not a git repository: {root}")
    path = Path(value)
    if not path.is_absolute():
        # `git rev-parse` reports this path relative to the folder it ran in (`root`).
        path = Path(root) / path
    return path.resolve()


def main_checkout(root) -> Path:
    """The main working tree of the repo (slot 0), also from inside a linked worktree."""
    return git_common_dir(root).parent


def is_main_checkout(root) -> bool:
    """True when `root` is the main working tree; False in a linked worktree or outside git."""
    try:
        top = _git(root, "rev-parse", "--show-toplevel")
        return bool(top) and Path(top).resolve() == main_checkout(root)
    except PolierError:
        return False
