"""Project-relative paths with forward slashes, the form every scope rule compares."""
from __future__ import annotations

import os
import posixpath
import re

_DRIVE = re.compile(r"^[A-Za-z]:/")


def normalized(path) -> str:
    """Forward slashes, no trailing slash, `.` and `..` resolved; '' for the root."""
    path = str(path if path is not None else "").strip().replace("\\", "/")
    if not path:
        return ""
    clean = posixpath.normpath(path)
    return "" if clean == "." else clean.rstrip("/")


def inside(path, entry) -> bool:
    """True if `path` equals `entry` or lies below the folder `entry`."""
    path, entry = normalized(path), normalized(entry)
    if not entry:
        return False
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
