"""Import boundaries between packages (PL-07).

Fixture trees with TS/JS, Python and C/C++ sources; the package map comes from
``packages[].may_import`` on the board.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.boundaries import find_violations

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def make_tree(files: dict, packages: list) -> Path:
    """Write a throwaway project tree and its board.json."""
    root = Path(tempfile.mkdtemp(prefix="pl-boundary-")).resolve()
    board = {
        "project": "suite",
        "profile": "L",
        "base_branch": "main",
        "schema_version": "1.0",
        "packages": [
            {"path": path, "kind": "package", "may_import": list(may_import)}
            for path, may_import in packages
        ],
        "tasks": [],
    }
    files = dict(files)
    files["board.json"] = json.dumps(board, indent=2)
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def load_board(root: Path) -> dict:
    return json.loads((root / "board.json").read_text(encoding="utf-8"))


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / "boundaries.py"), str(root), *args],
        capture_output=True, text=True, check=False,
    )


WEB_PACKAGE = {"apps/web/package.json": '{"name": "@canvas/web"}\n'}
SYNC_PACKAGE = {"services/sync/package.json": '{"name": "@canvas/sync"}\n'}


class TypeScript(unittest.TestCase):
    def test_import_into_package_not_in_may_import_is_a_violation(self):
        root = make_tree({
            **WEB_PACKAGE, **SYNC_PACKAGE,
            "services/sync/src/index.ts": "export const start = 1;\n",
            "apps/web/src/index.ts": "// entry\nimport { start } from '@canvas/sync';\n\nexport { start };\n",
        }, packages=[("apps/web", []), ("services/sync", [])])
        result = find_violations(root, load_board(root))
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["violations"]), 1, result)
        self.assertEqual(result["violations"][0], {
            "file": "apps/web/src/index.ts",
            "line": 2,
            "from_package": "apps/web",
            "to_package": "services/sync",
            "specifier": "@canvas/sync",
        })
        self.assertEqual(result["packages"], ["apps/web", "services/sync"])

    def test_allowed_imports_are_clean(self):
        root = make_tree({
            **WEB_PACKAGE,
            "packages/core/package.json": '{"name": "@canvas/core"}\n',
            "packages/core/src/index.ts": "export const core = 1;\n",
            "apps/web/src/local.ts": "export const local = 1;\n",
            "apps/web/src/index.ts": (
                "import { core } from '@canvas/core';\n"
                "import { local } from './local';\n"
                "export { core, local };\n"
            ),
        }, packages=[("apps/web", ["packages/core"]), ("packages/core", [])])
        result = find_violations(root, load_board(root))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["violations"], [])

    def test_require_and_dynamic_import_are_scanned(self):
        root = make_tree({
            **WEB_PACKAGE, **SYNC_PACKAGE,
            "services/sync/src/index.js": "module.exports = 1;\n",
            "apps/web/src/index.js": (
                "const sync = require('@canvas/sync');\n"
                "const later = import('@canvas/sync');\n"
            ),
        }, packages=[("apps/web", []), ("services/sync", [])])
        result = find_violations(root, load_board(root))
        self.assertEqual(len(result["violations"]), 2, result)

    def test_relative_import_into_another_package_counts(self):
        root = make_tree({
            "packages/core/src/index.ts": "export const core = 1;\n",
            "apps/web/src/index.ts": "import { core } from '../../../packages/core/src/index';\n",
        }, packages=[("apps/web", []), ("packages/core", [])])
        result = find_violations(root, load_board(root))
        self.assertEqual(len(result["violations"]), 1, result)
        self.assertEqual(result["violations"][0]["to_package"], "packages/core")

    def test_relative_import_inside_the_package_is_ignored(self):
        root = make_tree({
            "apps/web/src/b.ts": "export const b = 1;\n",
            "apps/web/src/a.ts": "import { b } from './b';\n",
        }, packages=[("apps/web", [])])
        result = find_violations(root, load_board(root))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["warnings"], [])


class Aliases(unittest.TestCase):
    TSCONFIG = """{
      // workspace aliases
      "compilerOptions": {
        "baseUrl": ".",
        "paths": {
          "@core/*": ["packages/core/src/*"],
        },
      },
    }
    """

    def _tree(self, may_import: list) -> Path:
        return make_tree({
            "tsconfig.json": self.TSCONFIG,
            "packages/core/src/peer.ts": "export const peer = 1;\n",
            "apps/web/src/use.ts": "import { peer } from '@core/peer';\n",
        }, packages=[("apps/web", may_import), ("packages/core", [])])

    def test_tsconfig_path_alias_is_resolved(self):
        root = self._tree([])
        result = find_violations(root, load_board(root))
        self.assertEqual(len(result["violations"]), 1, result)
        violation = result["violations"][0]
        self.assertEqual(violation["to_package"], "packages/core")
        self.assertEqual(violation["specifier"], "@core/peer")
        self.assertEqual(violation["line"], 1)
        # The trailing comma and the comment in the tsconfig must be tolerated.
        self.assertFalse(any("cannot parse tsconfig" in warning for warning in result["warnings"]),
                         result["warnings"])

    def test_known_alias_is_clean_when_allowed(self):
        root = self._tree(["packages/core"])
        result = find_violations(root, load_board(root))
        self.assertTrue(result["ok"], result)

    def test_unknown_alias_is_a_warning(self):
        root = make_tree({
            "tsconfig.json": self.TSCONFIG,
            "packages/core/src/peer.ts": "export const peer = 1;\n",
            "apps/web/src/use.ts": (
                "import { peer } from '@core/peer';\n"
                "import { ghost } from '@app/ghost';\n"
            ),
        }, packages=[("apps/web", ["packages/core"]), ("packages/core", [])])
        result = find_violations(root, load_board(root))
        self.assertTrue(result["ok"], result)
        warnings = "\n".join(result["warnings"])
        self.assertIn("unknown alias", warnings)
        self.assertIn("@app/ghost", warnings)
        self.assertIn("apps/web/src/use.ts:2", warnings)

    def test_unresolved_bare_import_warns_without_tsconfig(self):
        root = make_tree({
            "apps/web/src/index.ts": "import React from 'react';\n",
        }, packages=[("apps/web", [])])
        result = find_violations(root, load_board(root))
        self.assertTrue(result["ok"], result)
        self.assertTrue(any("unresolved import" in warning for warning in result["warnings"]),
                        result["warnings"])

    def test_declared_dependency_is_external(self):
        root = make_tree({
            "apps/web/package.json": '{"name": "@canvas/web", "dependencies": {"react": "^19.0.0"}}\n',
            "apps/web/src/index.ts": "import React from 'react';\n",
        }, packages=[("apps/web", [])])
        result = find_violations(root, load_board(root))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["warnings"], [])


class PythonAndCpp(unittest.TestCase):
    PY_FILES = {
        "services/api/pyproject.toml": '[project]\nname = "canvas-api"\n',
        "services/api/src/main.py": "from canvas_core.models import Item\n\nItem\n",
        "packages/core/pyproject.toml": '[project]\nname = "canvas-core"\n',
        "packages/core/src/canvas_core/models.py": "Item = object()\n",
    }

    def test_python_import_into_package_not_in_may_import(self):
        root = make_tree(self.PY_FILES, packages=[("services/api", []), ("packages/core", [])])
        result = find_violations(root, load_board(root))
        self.assertEqual(len(result["violations"]), 1, result)
        self.assertEqual(result["violations"][0], {
            "file": "services/api/src/main.py",
            "line": 1,
            "from_package": "services/api",
            "to_package": "packages/core",
            "specifier": "canvas_core.models",
        })

    def test_python_import_is_clean_when_allowed_and_stdlib_is_ignored(self):
        root = make_tree({
            **self.PY_FILES,
            "services/api/src/main.py": "from canvas_core.models import Item\nimport os\n",
        }, packages=[("services/api", ["packages/core"]), ("packages/core", [])])
        result = find_violations(root, load_board(root))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["warnings"], [])

    def test_cpp_include_from_another_package(self):
        root = make_tree({
            "packages/engine/include/engine.hpp": "#pragma once\n",
            "apps/web/src/native.cc": '#include "../../../packages/engine/include/engine.hpp"\n',
        }, packages=[("apps/web", []), ("packages/engine", [])])
        result = find_violations(root, load_board(root))
        self.assertEqual(len(result["violations"]), 1, result)
        self.assertEqual(result["violations"][0]["to_package"], "packages/engine")
        self.assertEqual(result["violations"][0]["line"], 1)

    def test_cpp_include_is_clean_when_allowed(self):
        root = make_tree({
            "packages/engine/include/engine.hpp": "#pragma once\n",
            "apps/web/src/native.cc": '#include "packages/engine/include/engine.hpp"\n',
        }, packages=[("apps/web", ["packages/engine"]), ("packages/engine", [])])
        result = find_violations(root, load_board(root))
        self.assertTrue(result["ok"], result)

    def test_cpp_include_inside_the_package_is_ignored(self):
        root = make_tree({
            "packages/engine/include/engine.hpp": "#pragma once\n",
            "packages/engine/src/engine.cpp": '#include "packages/engine/include/engine.hpp"\n',
        }, packages=[("packages/engine", [])])
        result = find_violations(root, load_board(root))
        self.assertTrue(result["ok"], result)


class Cli(unittest.TestCase):
    def test_violation_exits_1_and_names_file_and_line(self):
        root = make_tree({
            **WEB_PACKAGE, **SYNC_PACKAGE,
            "services/sync/src/index.ts": "export const start = 1;\n",
            "apps/web/src/index.ts": "import { start } from '@canvas/sync';\n",
        }, packages=[("apps/web", []), ("services/sync", [])])
        result = run_cli(root)
        self.assertEqual(result.returncode, 1, result)
        self.assertIn("apps/web/src/index.ts:1", result.stdout)
        self.assertIn("apps/web -> services/sync", result.stdout)
        self.assertIn("FAIL:", result.stdout)

    def test_clean_tree_exits_0(self):
        root = make_tree({
            "apps/web/src/index.ts": "export const x = 1;\n",
        }, packages=[("apps/web", [])])
        result = run_cli(root)
        self.assertEqual(result.returncode, 0, result)
        self.assertIn("OK:", result.stdout)

    def test_json_output(self):
        root = make_tree({
            **WEB_PACKAGE, **SYNC_PACKAGE,
            "services/sync/src/index.ts": "export const start = 1;\n",
            "apps/web/src/index.ts": "import { start } from '@canvas/sync';\n",
        }, packages=[("apps/web", []), ("services/sync", [])])
        result = run_cli(root, "--json")
        self.assertEqual(result.returncode, 1, result)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["violations"][0]["line"], 1)

    def test_no_packages_is_a_configuration_error(self):
        root = make_tree({}, packages=[])
        result = run_cli(root)
        self.assertEqual(result.returncode, 2, result)
        self.assertIn("no packages", result.stderr or result.stdout)

    def test_missing_board_is_a_configuration_error(self):
        root = Path(tempfile.mkdtemp(prefix="pl-boundary-")).resolve()
        result = run_cli(root)
        self.assertEqual(result.returncode, 2, result)

    def test_invalid_board_json_is_a_configuration_error(self):
        root = Path(tempfile.mkdtemp(prefix="pl-boundary-")).resolve()
        (root / "board.json").write_text("{not json", encoding="utf-8")
        result = run_cli(root)
        self.assertEqual(result.returncode, 2, result)


if __name__ == "__main__":
    unittest.main()
