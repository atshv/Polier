#!/usr/bin/env python3
"""Repository checks beyond the tests: generated pages, dead code, syntax.

Usage:
    python3 scripts/check.py        (npm run check)

1. factory/CATALOG.md matches factory/catalog.json.
2. docs/tools.md matches the plugin's tool definitions.
3. pyflakes finds nothing in core/, tools/, scripts/ and tests/*.py.
4. Every export of plugin/lib/*.mjs is imported somewhere else in plugin/ or scripts/.
5. node --check passes for every plugin and script module.

Exit 0 when all pass, 1 otherwise. Needs pyflakes (pip install pyflakes).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run(argv, **kw):
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, **kw)


def main() -> int:
    problems = []
    from core import factory
    if (ROOT / "factory" / "CATALOG.md").read_text(encoding="utf-8") != factory.catalog_markdown():
        problems.append("factory/CATALOG.md is stale: python3 tools/factory.py catalog --write")
    doc = run(["node", "scripts/tools-doc.mjs", "--stdout"])
    if doc.returncode != 0:
        problems.append(f"scripts/tools-doc.mjs failed: {doc.stderr.strip()[-500:]}")
    elif (ROOT / "docs" / "tools.md").read_text(encoding="utf-8") != doc.stdout:
        problems.append("docs/tools.md is stale: node scripts/tools-doc.mjs")
    flakes = run([sys.executable, "-m", "pyflakes", "core", "tools", "scripts", *map(str, sorted((ROOT / "tests").glob("*.py")))])
    if flakes.returncode != 0:
        output = flakes.stdout.strip() or flakes.stderr.strip()
        problems.append("pyflakes:\n" + output)
    modules = sorted((ROOT / "plugin").rglob("*.mjs")) + sorted((ROOT / "scripts").glob("*.mjs"))
    sources = {path: path.read_text(encoding="utf-8") for path in modules}
    for path in sorted((ROOT / "plugin" / "lib").glob("*.mjs")):
        for name in re.findall(r"^export (?:async )?(?:function|const) ([A-Za-z_$][\w$]*)", sources[path], re.M):
            used = any(re.search(rf"\b{re.escape(name)}\b", text) for other, text in sources.items() if other != path)
            if not used:
                problems.append(f"{path.relative_to(ROOT)}: export {name} is never imported")
    for path in modules:
        result = run(["node", "--check", str(path)])
        if result.returncode != 0:
            problems.append(f"{path.relative_to(ROOT)}: {result.stderr.strip()[-300:]}")
    for problem in problems:
        print(f"FAIL: {problem}")
    if not problems:
        print("OK: generated pages current, no dead code found, modules parse")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
