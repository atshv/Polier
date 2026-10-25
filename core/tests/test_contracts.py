"""Machine-readable contracts with version rules (PL-12).

Temporary git repositories with a contract on the board: fixtures, schema
version rules and the dependant coverage of the running task.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.board import load_board
from core.tests import fixtures

TOOLS = Path(__file__).resolve().parents[2] / "tools"
_MODULE = None


def contracts_module():
    global _MODULE
    if _MODULE is None:
        spec = importlib.util.spec_from_file_location("pl_contracts", TOOLS / "contracts.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        _MODULE = module
    return _MODULE


BASE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "count": {"type": "integer"},
    },
    "required": ["title"],
}


def contract_entry(**extra) -> dict:
    entry = {
        "name": "sync-events",
        "path": "contracts/sync",
        "version": "1.0.0",
        "schema_files": ["contracts/sync/schema.json"],
        "fixtures_dir": "contracts/sync/fixtures",
        "dependants": [],
    }
    entry.update(extra)
    return entry


def write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def commit(root: Path, message: str = "contracts") -> None:
    fixtures.git(root, "add", "-A")
    fixtures.git(root, "commit", "-q", "-m", message)


def branch(root: Path, name: str) -> None:
    fixtures.git(root, "checkout", "-q", "-b", name)


def edit_board(root: Path, change) -> None:
    board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    change(board)
    (root / "board.json").write_text(json.dumps(board, indent=2), encoding="utf-8")


def set_version(root: Path, version: str) -> None:
    edit_board(root, lambda board: board["contracts"][0].__setitem__("version", version))


def set_schema(root: Path, schema: dict) -> None:
    write(root, "contracts/sync/schema.json", json.dumps(schema, indent=2))


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / "contracts.py"), *args],
        capture_output=True, text=True, check=False,
    )


def make_project(contract=None, schema=None, tasks=None,
                 fixture_sides=("valid", "invalid"), create_fixtures=True,
                 create_path=True) -> Path:
    """A temporary git repository with one contract committed on `main`."""
    root = fixtures.project(tasks if tasks is not None else [fixtures.task()])
    entry = dict(contract) if contract is not None else contract_entry()
    board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    board["schema_version"] = "1.0"
    board["contracts"] = [entry]
    (root / "board.json").write_text(json.dumps(board, indent=2), encoding="utf-8")

    if create_path:
        (root / entry["path"]).mkdir(parents=True, exist_ok=True)
        for schema_file in entry.get("schema_files") or []:
            write(root, schema_file,
                  json.dumps(schema if schema is not None else BASE_SCHEMA, indent=2))
    if create_fixtures and entry.get("fixtures_dir"):
        for side in ("valid", "invalid"):
            if side not in fixture_sides:
                continue
            name = "ok.json" if side == "valid" else "broken.json"
            write(root, f"{entry['fixtures_dir']}/{side}/{name}", "{}\n")
    commit(root)
    return root


def add_optional_property(schema: dict) -> dict:
    changed = json.loads(json.dumps(schema))
    changed["properties"]["note"] = {"type": "string"}
    return changed


class ContractFiles(unittest.TestCase):
    def test_valid_contract_is_clean(self):
        root = make_project()
        errors, warnings = contracts_module().contract_errors(root, load_board(root))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_missing_invalid_fixture_is_an_error(self):
        root = make_project(fixture_sides=("valid",))
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        joined = "\n".join(errors)
        self.assertIn("sync-events", joined)
        self.assertIn("invalid", joined)

    def test_missing_valid_fixture_is_an_error(self):
        root = make_project(fixture_sides=("invalid",))
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        self.assertTrue(any("valid" in error for error in errors), errors)

    def test_missing_fixtures_dir_is_an_error(self):
        root = make_project(create_fixtures=False)
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        self.assertTrue(any("fixtures_dir" in error for error in errors), errors)

    def test_missing_contract_path_is_named(self):
        entry = contract_entry(
            path="contracts/ghost",
            schema_files=[],
            fixtures_dir="contracts/ghost/fixtures",
        )
        root = make_project(contract=entry, create_path=False, create_fixtures=False)
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        self.assertTrue(any("contracts/ghost" in error for error in errors), errors)

    def test_invalid_schema_json_is_an_error(self):
        root = make_project()
        write(root, "contracts/sync/schema.json", "{not json")
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        self.assertTrue(any("is not valid JSON" in error for error in errors), errors)


class Versions(unittest.TestCase):
    def test_schema_changed_without_version_bump_is_an_error(self):
        root = make_project()
        branch(root, "task/change")
        set_schema(root, add_optional_property(BASE_SCHEMA))
        commit(root, "change")
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        joined = "\n".join(errors)
        self.assertIn("sync-events", joined)
        self.assertIn("minor required", joined)
        result = run_cli("check", "--root", str(root), "--base", "main")
        self.assertEqual(result.returncode, 1, result)
        self.assertIn("minor required", result.stdout)

    def test_uncommitted_schema_change_is_detected(self):
        root = make_project()
        set_schema(root, add_optional_property(BASE_SCHEMA))
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        self.assertIn("minor required", "\n".join(errors))

    def test_added_optional_property_with_minor_bump_is_clean(self):
        root = make_project()
        branch(root, "task/change")
        set_schema(root, add_optional_property(BASE_SCHEMA))
        set_version(root, "1.1.0")
        commit(root, "add note")
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        self.assertEqual(errors, [])

    def test_removed_field_with_minor_bump_needs_major(self):
        root = make_project()
        branch(root, "task/change")
        schema = json.loads(json.dumps(BASE_SCHEMA))
        del schema["properties"]["count"]
        set_schema(root, schema)
        set_version(root, "1.1.0")
        commit(root, "remove count")
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        joined = "\n".join(errors)
        self.assertIn("removed property count", joined)
        self.assertIn("major required", joined)
        result = run_cli("check", "--root", str(root), "--base", "main")
        self.assertEqual(result.returncode, 1, result)
        self.assertIn("major required", result.stdout)

    def test_removed_field_with_major_bump_is_clean(self):
        root = make_project()
        branch(root, "task/change")
        schema = json.loads(json.dumps(BASE_SCHEMA))
        del schema["properties"]["count"]
        set_schema(root, schema)
        set_version(root, "2.0.0")
        commit(root, "remove count")
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        self.assertEqual(errors, [])

    def test_renamed_field_needs_major(self):
        root = make_project()
        branch(root, "task/change")
        schema = {
            "type": "object",
            "properties": {
                "heading": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["heading"],
        }
        set_schema(root, schema)
        set_version(root, "1.1.0")
        commit(root, "rename title")
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        joined = "\n".join(errors)
        self.assertIn("renamed property title -> heading", joined)
        self.assertIn("major required", joined)

    def test_non_schema_file_needs_at_least_a_patch_bump(self):
        root = make_project()
        branch(root, "task/change")
        write(root, "contracts/sync/README.md", "events contract\n")
        commit(root, "document the contract")
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        self.assertIn("patch required", "\n".join(errors))

    def test_unknown_base_branch_only_warns(self):
        root = make_project()
        errors, warnings = contracts_module().contract_errors(
            root, load_board(root), base_branch="no-such-branch")
        self.assertEqual(errors, [])
        self.assertTrue(any("no-such-branch" in warning or "cannot compare" in warning
                            for warning in warnings), warnings)


class SchemaDiff(unittest.TestCase):
    def test_compare_schemas_reports_added_removed_and_renamed(self):
        module = contracts_module()
        old = {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "userName": {"type": "string", "description": "login"},
            },
            "required": ["id"],
        }
        new = {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "username": {"type": "string", "description": "login"},
                "note": {"type": "string"},
            },
            "required": ["id"],
        }
        changes = module.compare_schemas(old, new)
        self.assertEqual(changes["renamed"], ["userName -> username"])
        self.assertEqual(changes["added"], ["note"])
        self.assertEqual(changes["removed"], [])
        back = module.compare_schemas(new, old)
        self.assertEqual(back["removed"], ["note"])
        self.assertEqual(back["renamed"], ["username -> userName"])
        self.assertEqual(module.compare_schemas(old, old),
                         {"added": [], "removed": [], "renamed": []})

    def test_required_change_messages(self):
        module = contracts_module()
        self.assertIsNone(module.required_change("major", "1.0.0", "2.0.0"))
        self.assertEqual(module.required_change("major", "1.0.0", "1.1.0"), "major required")
        self.assertIsNone(module.required_change("minor", "1.0.0", "1.1.0"))
        self.assertEqual(module.required_change("minor", "1.0.0", "1.0.1"), "minor required")
        self.assertIsNone(module.required_change("patch", "1.0.0", "1.0.1"))
        self.assertEqual(module.required_change("patch", "1.0.0", "1.0.0"), "patch required")
        self.assertIsNone(module.required_change("major", None, "0.1.0"))


class Dependants(unittest.TestCase):
    DEPENDANT = "apps/web/src/api.ts"

    def _changed_project(self, **task_extra) -> Path:
        entry = contract_entry(dependants=[self.DEPENDANT])
        root = make_project(contract=entry, tasks=[fixtures.task(**task_extra)])
        branch(root, "task/change")
        set_schema(root, add_optional_property(BASE_SCHEMA))
        set_version(root, "1.1.0")
        commit(root, "add note")
        return root

    def test_changed_contract_and_missing_dependant_is_an_error(self):
        root = self._changed_project()
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        joined = "\n".join(errors)
        self.assertIn(self.DEPENDANT, joined)
        self.assertIn("M01", joined)
        result = run_cli("check", "--root", str(root), "--base", "main")
        self.assertEqual(result.returncode, 1, result)
        self.assertIn(self.DEPENDANT, result.stdout)

    def test_dependant_in_scope_write_is_clean(self):
        root = self._changed_project(scope_write=["src/app.py", self.DEPENDANT])
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        self.assertEqual(errors, [])

    def test_contract_followups_is_a_warning_only(self):
        root = self._changed_project(contract_followups=[self.DEPENDANT])
        errors, warnings = contracts_module().contract_errors(root, load_board(root))
        self.assertEqual(errors, [])
        self.assertTrue(any("contract_followups" in warning for warning in warnings), warnings)

    def test_task_argument_overrides_the_in_progress_task(self):
        root = self._changed_project()
        board = load_board(root)
        board["tasks"][0]["status"] = "pending"
        errors, _ = contracts_module().contract_errors(root, board, task="M01")
        self.assertIn(self.DEPENDANT, "\n".join(errors))
        errors, warnings = contracts_module().contract_errors(root, board)
        self.assertEqual(errors, [])
        self.assertTrue(any("no task is in_progress" in warning for warning in warnings), warnings)


class NestedProject(unittest.TestCase):
    """A project root below the git top level: git show needs the repo prefix."""

    def test_project_in_a_subdirectory_of_a_repository(self):
        repo = Path(tempfile.mkdtemp(prefix="pl-contract-nested-")).resolve()
        fixtures.git(repo, "init", "-q", "-b", "main")
        fixtures.git(repo, "config", "user.email", "t@example.com")
        fixtures.git(repo, "config", "user.name", "t")
        root = repo / "projects" / "suite"
        board = {
            "project": "suite", "profile": "S", "base_branch": "main",
            "schema_version": "1.0", "tasks": [fixtures.task()],
            "contracts": [contract_entry()],
        }
        write(root, "board.json", json.dumps(board, indent=2))
        write(root, "contracts/sync/schema.json", json.dumps(BASE_SCHEMA, indent=2))
        write(root, "contracts/sync/fixtures/valid/ok.json", "{}\n")
        write(root, "contracts/sync/fixtures/invalid/broken.json", "{}\n")
        commit(repo, "scaffold")
        errors, warnings = contracts_module().contract_errors(root, load_board(root))
        self.assertEqual(errors, [])
        self.assertFalse(any("cannot read board.json" in warning for warning in warnings), warnings)
        set_schema(root, add_optional_property(BASE_SCHEMA))
        errors, _ = contracts_module().contract_errors(root, load_board(root))
        self.assertIn("minor required", "\n".join(errors))


class Cli(unittest.TestCase):
    def test_check_clean_exit_0(self):
        root = make_project()
        result = run_cli("check", "--root", str(root), "--base", "main")
        self.assertEqual(result.returncode, 0, result)
        self.assertIn("OK:", result.stdout)

    def test_check_json(self):
        root = make_project()
        result = run_cli("check", "--root", str(root), "--base", "main", "--json")
        self.assertEqual(result.returncode, 0, result)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["contracts"][0]["name"], "sync-events")

    def test_list_exit_0(self):
        root = make_project()
        result = run_cli("list", "--root", str(root))
        self.assertEqual(result.returncode, 0, result)
        self.assertIn("sync-events", result.stdout)
        self.assertIn("1.0.0", result.stdout)
        self.assertIn("contracts/sync", result.stdout)

    def test_missing_board_exit_2(self):
        root = Path(tempfile.mkdtemp(prefix="pl-contract-")).resolve()
        result = run_cli("check", "--root", str(root))
        self.assertEqual(result.returncode, 2, result)

    def test_unknown_task_exit_2(self):
        root = make_project()
        result = run_cli("check", "--root", str(root), "--task", "NOPE")
        self.assertEqual(result.returncode, 2, result)

    def test_usage_without_subcommand_exit_2(self):
        result = run_cli()
        self.assertEqual(result.returncode, 2, result)


if __name__ == "__main__":
    unittest.main()
