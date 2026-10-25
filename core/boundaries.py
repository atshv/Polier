"""Import boundaries between the packages of a monorepo (PL-07).

``find_violations`` is the pure check behind ``tools/boundaries.py`` and the
``boundaries`` gate of ``tools/check.py``. It reads the package map from
``board.json`` (``packages[].path`` and ``packages[].may_import``), scans the
source files of every package and reports cross-package imports that the
``may_import`` list does not allow.

Resolution order for an import specifier:

1. relative paths are resolved against the importing file,
2. TS/JS path aliases from every ``tsconfig*.json`` (root and packages),
3. workspace package names from ``package.json`` / ``pyproject.toml``,
4. known third-party and platform modules are ignored,
5. everything else is reported as a warning (unknown alias / unresolved path).

Only cross-package imports are violations; an import that stays inside its own
package is fine and imports that resolve to no package are warnings, never
errors. Standard library only, Python 3.9+.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

JS_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})
PY_SUFFIXES = frozenset({".py"})
C_SUFFIXES = frozenset({".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp"})
SOURCE_SUFFIXES = JS_SUFFIXES | PY_SUFFIXES | C_SUFFIXES

SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", "out", "target", "coverage", ".next", ".nuxt", ".turbo",
    ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".generated",
    "vendor", ".idea", ".vscode",
})

MAX_FILE_BYTES = 2_000_000

NODE_BUILTINS = frozenset({
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
    "events", "fs", "http", "http2", "https", "inspector", "module", "net",
    "os", "path", "perf_hooks", "process", "punycode", "querystring",
    "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
    "trace_events", "tty", "url", "util", "v8", "vm", "wasi",
    "worker_threads", "zlib",
})

# TS/JS import forms. The static form also covers side-effect imports and
# multi-line import/export lists.
JS_STATIC = re.compile(
    r"""(?<![\w$.])(?:import|export)\s+(?:[^;'"]{0,800}?\bfrom\s+)?['"]([^'"]+)['"]""",
    re.DOTALL,
)
JS_DYNAMIC = re.compile(r"""\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)""")
JS_REQUIRE = re.compile(r"""\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)""")

PY_FROM = re.compile(r"^[ \t]*from[ \t]+([.\w]+)[ \t]+import\b", re.MULTILINE)
PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w.]+(?:[ \t]*,[ \t]*[\w.]+)*)", re.MULTILINE)

C_INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*"([^"]+)"', re.MULTILINE)

_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"//[^\n]*")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


# ---------------------------------------------------------------------------
# small path helpers
# ---------------------------------------------------------------------------

def _norm(value: str) -> str:
    """A root-relative path in posix form without './' or a trailing '/'."""
    value = str(value).strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.rstrip("/")


def _rel_under(root: Path, candidate) -> Optional[str]:
    """`candidate` relative to `root` in posix form, or None when it escapes root."""
    try:
        rel = os.path.relpath(os.path.normpath(str(candidate)), str(root))
    except (ValueError, OSError):
        return None
    rel = rel.replace(os.sep, "/")
    if rel == ".." or rel.startswith("../") or rel.startswith("/"):
        return None
    return "" if rel == "." else rel


def _join(base: str, relative: str) -> Optional[str]:
    """Join two root-relative posix paths; None when the result escapes root."""
    joined = os.path.normpath(os.path.join(base, relative)) if base else os.path.normpath(relative)
    joined = joined.replace(os.sep, "/")
    if joined == ".." or joined.startswith("../") or joined.startswith("/") or os.path.isabs(joined):
        return None
    return "" if joined == "." else joined


def _read_text(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if "\x00" in text:
        return None
    return text


def _load_jsonc(path: Path):
    """JSON with the tolerances of tsconfig.json: comments and trailing commas."""
    text = path.read_text(encoding="utf-8")
    text = _COMMENT_BLOCK.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text)
    text = _COMMENT_LINE.sub("", text)
    text = _TRAILING_COMMA.sub(r"\1", text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# package map
# ---------------------------------------------------------------------------

def _packages(board) -> List[dict]:
    """The board's package map as [{path, kind, may_import}] with normalised paths."""
    out: List[dict] = []
    for entry in (board or {}).get("packages") or []:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        may_import = entry.get("may_import")
        allowed = []
        if isinstance(may_import, list):
            allowed = [_norm(item) for item in may_import if isinstance(item, str) and item.strip()]
        out.append({"path": _norm(path), "kind": entry.get("kind"), "may_import": allowed})
    return out


def _owner_of(packages: List[dict], rel_path: str) -> Optional[dict]:
    """The package that contains `rel_path`; the longest matching path wins."""
    best = None
    for package in packages:
        path = package["path"]
        if not path:
            continue
        if rel_path == path or rel_path.startswith(path + "/"):
            if best is None or len(path) > len(best["path"]):
                best = package
    return best


def _source_files(root: Path, packages: List[dict]) -> Dict[str, dict]:
    """Every relevant source file, mapped to the package that owns it."""
    found: Dict[str, dict] = {}
    for package in packages:
        base = root / package["path"]
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(str(base)):
            dirnames[:] = sorted(
                name for name in dirnames
                if name not in SKIP_DIRS and not name.startswith(".")
            )
            for name in sorted(filenames):
                suffix = os.path.splitext(name)[1].lower()
                if suffix not in SOURCE_SUFFIXES:
                    continue
                rel = _rel_under(root, Path(dirpath) / name)
                if not rel:
                    continue
                owner = _owner_of(packages, rel)
                if owner is not None:
                    found[rel] = owner
    return found


# ---------------------------------------------------------------------------
# workspace names, dependencies and tsconfig aliases
# ---------------------------------------------------------------------------

def _dependency_names(path: Path) -> Set[str]:
    """Package names declared as dependencies in a package.json."""
    names: Set[str] = set()
    if not path.is_file():
        return names
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return names
    if not isinstance(data, dict):
        return names
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            names.update(str(name) for name in block)
    return names


def _pyproject_name(path: Path) -> Optional[str]:
    """The distribution name from [project] or [tool.poetry]."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.strip("[]").strip()
            continue
        if section not in ("project", "tool.poetry"):
            continue
        match = re.match(r"""name\s*=\s*['"]([^'"]+)['"]""", stripped)
        if match:
            return match.group(1)
    return None


def _workspace_names(root: Path, packages: List[dict], warn) -> Tuple[Dict[str, str], Dict[str, str], Set[str]]:
    """JS package names, Python module names and known third-party dependencies."""
    js_names: Dict[str, str] = {}
    py_names: Dict[str, str] = {}
    dependencies: Set[str] = set()

    root_package = root / "package.json"
    dependencies |= _dependency_names(root_package)

    for package in packages:
        base = root / package["path"]
        package_json = base / "package.json"
        if package_json.is_file():
            dependencies |= _dependency_names(package_json)
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                warn(f"{_rel_under(root, package_json)}: cannot parse package.json ({exc}); its name is ignored")
                data = None
            name = data.get("name") if isinstance(data, dict) else None
            if isinstance(name, str) and name.strip():
                js_names[name.strip()] = package["path"]
        pyproject = base / "pyproject.toml"
        if pyproject.is_file():
            name = _pyproject_name(pyproject)
            if name:
                py_names[_python_module(name)] = package["path"]
    return js_names, py_names, dependencies


def _python_module(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.strip().lower())


def _match_alias(pattern: str, specifier: str) -> Optional[str]:
    """Wildcard match of a tsconfig paths key; returns the captured '*' or None."""
    if "*" in pattern:
        prefix, suffix = pattern.split("*", 1)
        if (specifier.startswith(prefix) and specifier.endswith(suffix)
                and len(specifier) >= len(prefix) + len(suffix)):
            return specifier[len(prefix):len(specifier) - len(suffix)] if suffix else specifier[len(prefix):]
        return None
    return "" if specifier == pattern else None


class _Aliases:
    """TS/JS path aliases of a project, collected from every tsconfig."""

    def __init__(self) -> None:
        self._patterns: List[dict] = []
        self.declared = False

    def add(self, root: Path, tsconfig: Path, scope: Optional[str], warn) -> None:
        try:
            data = _load_jsonc(tsconfig)
        except (ValueError, OSError) as exc:
            warn(f"{_rel_under(root, tsconfig)}: cannot parse tsconfig ({exc}); its aliases are ignored")
            return
        if not isinstance(data, dict):
            return
        options = data.get("compilerOptions")
        if not isinstance(options, dict):
            return
        paths = options.get("paths")
        if not isinstance(paths, dict) or not paths:
            return
        self.declared = True
        base_dir = tsconfig.parent
        base_url = options.get("baseUrl")
        if isinstance(base_url, str) and base_url.strip():
            base_dir = Path(os.path.normpath(os.path.join(str(base_dir), base_url)))
        base_rel = _rel_under(root, base_dir)
        if base_rel is None:
            return
        for key, targets in paths.items():
            if not isinstance(key, str) or not isinstance(targets, list):
                continue
            templates = [target for target in targets if isinstance(target, str)]
            if not templates:
                continue
            self._patterns.append({
                "key": key, "targets": templates, "base": base_rel,
                "scope": scope, "specificity": len(key),
            })

    def resolve(self, specifier: str, from_package: str) -> Optional[List[str]]:
        """Root-relative candidates for `specifier`, or None when no alias matches."""
        best = None
        for pattern in self._patterns:
            if pattern["scope"] is not None and pattern["scope"] != from_package:
                continue
            capture = _match_alias(pattern["key"], specifier)
            if capture is None:
                continue
            if best is None or pattern["specificity"] > best[0]["specificity"]:
                best = (pattern, capture)
        if best is None:
            return None
        pattern, capture = best
        candidates = []
        for template in pattern["targets"]:
            value = os.path.normpath(os.path.join(pattern["base"], template.replace("*", capture)))
            rel = value.replace(os.sep, "/")
            if rel == ".." or rel.startswith("../") or rel.startswith("/"):
                continue
            candidates.append("" if rel == "." else rel)
        return candidates


def _collect_aliases(root: Path, packages: List[dict], warn) -> _Aliases:
    aliases = _Aliases()
    root_tsconfig = root / "tsconfig.json"
    if root_tsconfig.is_file():
        aliases.add(root, root_tsconfig, None, warn)
    for package in packages:
        base = root / package["path"]
        if not base.is_dir():
            continue
        for path in sorted(base.glob("tsconfig*.json")):
            if path.is_file():
                aliases.add(root, path, package["path"], warn)
    return aliases


# ---------------------------------------------------------------------------
# import extraction
# ---------------------------------------------------------------------------

def _line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _js_imports(text: str) -> List[Tuple[int, str]]:
    out: Dict[Tuple[int, int], Tuple[int, str]] = {}
    for pattern in (JS_STATIC, JS_DYNAMIC, JS_REQUIRE):
        for match in pattern.finditer(text):
            out[(match.start(), match.start(1))] = (_line_of(text, match.start()), match.group(1))
    return [out[key] for key in sorted(out)]


def _py_imports(text: str) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for match in PY_FROM.finditer(text):
        module = match.group(1)
        level = len(module) - len(module.lstrip("."))
        out.append((_line_of(text, match.start()), ("." * level) + module.lstrip(".")))
    for match in PY_IMPORT.finditer(text):
        for part in match.group(1).split(","):
            module = part.strip()
            if module:
                out.append((_line_of(text, match.start()), module))
    return out


def _c_includes(text: str) -> List[Tuple[int, str]]:
    return [(_line_of(text, match.start()), match.group(1)) for match in C_INCLUDE.finditer(text)]


# ---------------------------------------------------------------------------
# specifier classification
# ---------------------------------------------------------------------------

def _is_external_js(specifier: str, root: Path, dependencies: Set[str]) -> bool:
    """True for platform modules and packages that are not part of the workspace."""
    if specifier.startswith("node:"):
        return True
    if specifier.startswith("@"):
        name = "/".join(specifier.split("/")[:2])
    else:
        name = specifier.split("/")[0]
    if not name:
        return False
    if name in NODE_BUILTINS:
        return True
    if name in dependencies:
        return True
    try:
        if (root / "node_modules" / name).is_dir():
            return True
    except OSError:
        pass
    return False


def _looks_like_alias(specifier: str) -> bool:
    """Specifiers a project would resolve itself rather than fetch from npm."""
    return specifier.startswith(("@/", "~/", "#", "$/")) or (
        specifier.startswith("@") and "/" in specifier)


def _js_package_for(specifier: str, js_names: Dict[str, str]) -> Optional[str]:
    best = None
    for name, package_path in js_names.items():
        if specifier == name or specifier.startswith(name + "/"):
            if best is None or len(name) > len(best[0]):
                best = (name, package_path)
    return best[1] if best else None


def find_violations(root, board) -> dict:
    """Cross-package imports that the package map does not allow.

    Returns ``{"ok": bool, "violations": [...], "warnings": [...],
    "packages": [...]}``. A violation is a dict with the keys ``file``,
    ``line``, ``from_package``, ``to_package`` and ``specifier``. Warnings are
    strings for imports that cannot be resolved to a package. Never raises and
    never writes.
    """
    root = Path(os.path.abspath(str(root)))
    packages = _packages(board)
    result: Dict[str, object] = {
        "ok": True,
        "violations": [],
        "warnings": [],
        "packages": [package["path"] for package in packages],
    }
    violations: List[dict] = result["violations"]  # type: ignore[assignment]
    warnings: List[str] = result["warnings"]  # type: ignore[assignment]
    seen_warnings: Set[str] = set()

    def warn(message: str) -> None:
        if message not in seen_warnings:
            seen_warnings.add(message)
            warnings.append(message)

    if not packages:
        warn("board.json declares no packages; the boundary check has nothing to inspect")
        return result
    if not root.is_dir():
        warn(f"project root does not exist: {root}")
        return result

    for package in packages:
        if not (root / package["path"]).is_dir():
            warn(f"package path {package['path']!r} does not exist on disk")

    js_names, py_names, dependencies = _workspace_names(root, packages, warn)
    aliases = _collect_aliases(root, packages, warn)
    package_paths = {package["path"] for package in packages}

    allowed: Dict[str, Set[str]] = {}
    for package in packages:
        resolved: Set[str] = set()
        for entry in package["may_import"]:
            if entry in package_paths:
                resolved.add(entry)
            elif entry in js_names:
                resolved.add(js_names[entry])
            elif entry in py_names:
                resolved.add(py_names[entry])
            else:
                warn(f"package {package['path']}: may_import entry {entry!r} is not a declared "
                     f"package, package name or Python module")
        allowed[package["path"]] = resolved

    seen_violations: Set[Tuple[str, int, str, str, str]] = set()

    def check(owner: dict, target: Optional[dict], file_rel: str, line: int, specifier: str) -> None:
        if target is None or target["path"] == owner["path"]:
            return
        if target["path"] in allowed[owner["path"]]:
            return
        key = (file_rel, line, owner["path"], target["path"], specifier)
        if key in seen_violations:
            return
        seen_violations.add(key)
        violations.append({
            "file": file_rel,
            "line": line,
            "from_package": owner["path"],
            "to_package": target["path"],
            "specifier": specifier,
        })

    def resolve_js(owner: dict, file_rel: str, line: int, specifier: str) -> None:
        if specifier.startswith(("./", "../")) or specifier in (".", ".."):
            target_rel = _join(os.path.dirname(file_rel), specifier)
            if target_rel is None:
                warn(f"{file_rel}:{line}: import {specifier!r} escapes the project root")
                return
            target = _owner_of(packages, target_rel)
            if target is None:
                warn(f"{file_rel}:{line}: relative import {specifier!r} leaves the declared packages")
                return
            check(owner, target, file_rel, line, specifier)
            return
        if specifier.startswith("/"):
            target = _owner_of(packages, _norm(specifier))
            if target is None:
                warn(f"{file_rel}:{line}: absolute import {specifier!r} maps to no package")
            else:
                check(owner, target, file_rel, line, specifier)
            return
        candidates = aliases.resolve(specifier, owner["path"])
        if candidates is not None:
            owners = []
            for candidate in candidates:
                target = _owner_of(packages, candidate)
                if target is not None and target not in owners:
                    owners.append(target)
            if not owners:
                warn(f"{file_rel}:{line}: tsconfig alias {specifier!r} resolves to no package")
                return
            for target in owners:
                check(owner, target, file_rel, line, specifier)
            return
        package_path = _js_package_for(specifier, js_names)
        if package_path is not None:
            check(owner, next(p for p in packages if p["path"] == package_path), file_rel, line, specifier)
            return
        if _is_external_js(specifier, root, dependencies):
            return
        if _looks_like_alias(specifier):
            warn(f"{file_rel}:{line}: unknown alias {specifier!r} (no tsconfig path matches and no package owns it)")
        elif aliases.declared:
            warn(f"{file_rel}:{line}: unresolved import {specifier!r} (no tsconfig path matches and no package owns it)")
        else:
            warn(f"{file_rel}:{line}: unresolved import {specifier!r} (no package owns it)")

    def resolve_python(owner: dict, file_rel: str, line: int, module: str) -> None:
        level = len(module) - len(module.lstrip("."))
        name = module.lstrip(".")
        if level:
            base = os.path.dirname(file_rel)
            for _ in range(level - 1):
                base = os.path.dirname(base)
            if not name:
                return
            target_rel = _join(base, name.replace(".", "/"))
            if target_rel is None:
                warn(f"{file_rel}:{line}: relative import {module!r} escapes the project root")
                return
            target = _owner_of(packages, target_rel)
            if target is None:
                warn(f"{file_rel}:{line}: relative import {module!r} leaves the declared packages")
                return
            check(owner, target, file_rel, line, module)
            return
        parts = [part for part in name.split(".") if part]
        if not parts:
            return
        target = None
        mapped = py_names.get(_python_module(parts[0]))
        if mapped:
            target = next(p for p in packages if p["path"] == mapped)
        if target is None:
            target = _owner_of(packages, "/".join(parts))
        if target is None:
            # Standard library and third-party imports are not part of the map.
            return
        check(owner, target, file_rel, line, module)

    def resolve_c(owner: dict, file_rel: str, line: int, include: str) -> None:
        include = include.replace("\\", "/")
        candidates: List[str] = []
        file_dir = os.path.dirname(file_rel)
        for relative in (include,):
            joined = _join(file_dir, relative)
            if joined:
                candidates.append(joined)
        package_root = _join(owner["path"], include)
        if package_root:
            candidates.append(package_root)
        root_level = _join("", include)
        if root_level:
            candidates.append(root_level)
        for candidate in candidates:
            if (root / candidate).is_file():
                target = _owner_of(packages, candidate)
                if target is None:
                    warn(f"{file_rel}:{line}: include {include!r} resolves outside the declared packages")
                    return
                check(owner, target, file_rel, line, include)
                return
        textual = _norm(include)
        target = _owner_of(packages, textual)
        if target is not None:
            check(owner, target, file_rel, line, include)
            return
        if include.startswith("/"):
            return
        warn(f"{file_rel}:{line}: cannot resolve include {include!r} to a package")

    files = _source_files(root, packages)
    for file_rel in sorted(files):
        owner = files[file_rel]
        text = _read_text(root / file_rel)
        if text is None:
            continue
        suffix = os.path.splitext(file_rel)[1].lower()
        if suffix in JS_SUFFIXES:
            for line, specifier in _js_imports(text):
                resolve_js(owner, file_rel, line, specifier)
        elif suffix in PY_SUFFIXES:
            for line, module in _py_imports(text):
                resolve_python(owner, file_rel, line, module)
        elif suffix in C_SUFFIXES:
            for line, include in _c_includes(text):
                resolve_c(owner, file_rel, line, include)

    violations.sort(key=lambda item: (item["file"], item["line"], item["specifier"], item["to_package"]))
    result["ok"] = not violations
    return result
