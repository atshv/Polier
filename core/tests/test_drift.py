"""Generator drift and release manifest (PL-15): hashes, warnings, round-trip."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"pl_{name}", TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


manifest = load("manifest")
drift = load("drift")


def run_tool(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOLS / name), *args],
                          capture_output=True, text=True, check=False)


def make_package(package: Path) -> Path:
    """A minimal shipped package: VERSION, CHANGELOG.md, tools/check.py, docs/nested/note.md."""
    package = package.resolve()
    (package / "tools").mkdir(parents=True, exist_ok=True)
    (package / "docs" / "nested").mkdir(parents=True, exist_ok=True)
    (package / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (package / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (package / "tools" / "check.py").write_text("print('check')\n", encoding="utf-8")
    (package / "docs" / "nested" / "note.md").write_text("note\n", encoding="utf-8")
    (package / "package.json").write_text(json.dumps({
        "name": "polier-test", "version": "1.0.0",
        "files": ["VERSION", "tools/*.py", "docs/"],
    }), encoding="utf-8")
    return package


def temp_dir(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix)).resolve()


def make_project(base: Path) -> Path:
    """A project that keeps its Polier copy in .generator/."""
    project = base.resolve() / "project"
    make_package(project / ".generator")
    return project


class ManifestTool(unittest.TestCase):
    def test_write_then_check_round_trip(self):
        package = make_package(temp_dir("pl-manifest-"))
        target = manifest.write_manifest(package)
        self.assertEqual(target, package / "tools" / "manifest.json")
        self.assertTrue(target.is_file())
        data = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(data["version"], "1.0.0")
        dt.date.fromisoformat(data["generated"])
        self.assertEqual(list(data["files"]), sorted(data["files"]))
        self.assertEqual(data["count"], len(data["files"]))
        self.assertEqual(data["count"], 4)  # VERSION, CHANGELOG.md, tools/check.py, docs/nested/note.md
        self.assertIn("tools/check.py", data["files"])
        self.assertIn("docs/nested/note.md", data["files"])
        self.assertNotIn("tools/manifest.json", data["files"])
        self.assertTrue(all("/" in path or not path.startswith("\\") for path in data["files"]))

        result = manifest.check_manifest(package)
        self.assertTrue(result["ok"], result["lines"])
        self.assertEqual(run_tool("manifest.py", "--check", "--package", str(package)).returncode, 0)

        # Deterministic: a second write of unchanged files is byte-identical.
        before = target.read_bytes()
        manifest.write_manifest(package)
        self.assertEqual(target.read_bytes(), before)

    def test_check_reports_drift(self):
        package = make_package(temp_dir("pl-manifest-"))
        manifest.write_manifest(package)
        (package / "tools" / "check.py").write_text("print('edited')\n", encoding="utf-8")
        (package / "docs" / "nested" / "note.md").unlink()
        (package / "tools" / "new.py").write_text("x = 1\n", encoding="utf-8")

        result = manifest.check_manifest(package)
        self.assertFalse(result["ok"])
        self.assertEqual(result["modified"], ["tools/check.py"])
        self.assertEqual(result["missing"], ["docs/nested/note.md"])
        self.assertEqual(result["extra"], ["tools/new.py"])

        run = run_tool("manifest.py", "--check", "--package", str(package))
        self.assertEqual(run.returncode, 1)
        self.assertIn("tools/check.py", run.stdout)

        self.assertEqual(run_tool("manifest.py", "--write", "--package", str(package)).returncode, 0)
        self.assertEqual(run_tool("manifest.py", "--check", "--package", str(package)).returncode, 0)

    def test_custom_out(self):
        package = make_package(temp_dir("pl-manifest-"))
        out = package / "reviews" / "manifest.json"
        self.assertEqual(
            run_tool("manifest.py", "--write", "--package", str(package), "--out", str(out)).returncode, 0)
        self.assertTrue(out.is_file())
        self.assertEqual(
            run_tool("manifest.py", "--check", "--package", str(package), "--out", str(out)).returncode, 0)

    def test_shipped_files_follow_package_json(self):
        package = make_package(temp_dir("pl-manifest-"))
        (package / "tools" / "deep").mkdir()
        (package / "tools" / "deep" / "nested.py").write_text("", encoding="utf-8")
        (package / "README.md").write_text("readme\n", encoding="utf-8")
        files = manifest.shipped_files(package)
        self.assertIn("tools/check.py", files)
        self.assertNotIn("tools/deep/nested.py", files)  # * does not cross folders
        self.assertNotIn("README.md", files)              # not in package.json files
        self.assertIn("VERSION", files)                   # always shipped
        self.assertIn("CHANGELOG.md", files)              # always shipped

    def test_environment_errors_exit_2(self):
        empty = temp_dir("pl-manifest-")
        (empty / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        self.assertEqual(run_tool("manifest.py", "--write", "--package", str(empty)).returncode, 2)
        package = make_package(temp_dir("pl-manifest-"))
        self.assertEqual(run_tool("manifest.py", "--check", "--package", str(package)).returncode, 2)


class Drift(unittest.TestCase):
    def test_matching_copy_is_ok_without_warning(self):
        project = make_project(temp_dir("pl-drift-"))
        manifest.write_manifest(project / ".generator")

        report = drift.drift(project)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["files"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["version"], "1.0.0")
        self.assertEqual(report["package"], str((project / ".generator").resolve()))

        run = run_tool("drift.py", str(project))
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("DRIFT OK", run.stdout)

    def test_edited_or_missing_file_warns_and_exits_1(self):
        project = make_project(temp_dir("pl-drift-"))
        manifest.write_manifest(project / ".generator")
        (project / ".generator" / "tools" / "check.py").write_text("print('local edit')\n", encoding="utf-8")
        (project / ".generator" / "docs" / "nested" / "note.md").unlink()

        report = drift.drift(project)
        self.assertEqual(report["status"], "modified")
        self.assertEqual(report["files"], ["docs/nested/note.md", "tools/check.py"])
        warning = "\n".join(report["warnings"])
        self.assertIn("local edits or outdated copy", warning)
        self.assertIn("tools/check.py", warning)
        self.assertIn("docs/nested/note.md", warning)

        run = run_tool("drift.py", str(project))
        self.assertEqual(run.returncode, 1)
        self.assertIn("tools/check.py", run.stdout)

        run = run_tool("drift.py", str(project), "--json")
        self.assertEqual(run.returncode, 1)
        self.assertEqual(json.loads(run.stdout)["status"], "modified")

    def test_extra_files_are_ignored(self):
        project = make_project(temp_dir("pl-drift-"))
        manifest.write_manifest(project / ".generator")
        (project / ".generator" / "notes.md").write_text("added by the project\n", encoding="utf-8")
        report = drift.drift(project)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["files"], [])

    def test_missing_manifest_never_fails(self):
        project = make_project(temp_dir("pl-drift-"))
        self.assertIsNone(drift.load_manifest(project / ".generator"))
        report = drift.drift(project)
        self.assertEqual(report["status"], "missing-manifest")
        self.assertEqual(report["version"], "1.0.0")
        self.assertEqual(report["files"], [])
        self.assertTrue(report["warnings"])

        run = run_tool("drift.py", str(project))
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("manifest", run.stdout)

    def test_project_without_generator_copy_is_silent(self):
        project = temp_dir("pl-drift-")
        report = drift.drift(project)
        self.assertEqual(report["status"], "no-package")
        self.assertIsNone(report["package"])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["files"], [])
        self.assertIsNone(drift.package_dir(project))

        run = run_tool("drift.py", str(project))
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertNotIn("WARN", run.stdout)
        self.assertIn("no package", run.stdout)

    def test_generator_folder_needs_version_or_manifest(self):
        project = temp_dir("pl-drift-")
        (project / ".generator").mkdir()
        self.assertIsNone(drift.package_dir(project))
        report = drift.drift(project)
        self.assertEqual(report["status"], "no-package")
        self.assertEqual(report["warnings"], [])

    def test_package_dir_only_returns_the_project_copy(self):
        project = make_project(temp_dir("pl-drift-"))
        self.assertEqual(drift.package_dir(project), (project / ".generator").resolve())
        self.assertIsNone(drift.package_dir(temp_dir("pl-drift-")))

    def test_explicit_package_checks_the_plugin_copy(self):
        project = make_project(temp_dir("pl-drift-"))
        package = project / ".generator"
        manifest.write_manifest(package)
        plain = temp_dir("pl-drift-")  # a project without a local copy
        report = drift.drift(plain, package=package)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["package"], str(package.resolve()))
        self.assertEqual(report["warnings"], [])
        self.assertEqual(run_tool("drift.py", str(plain), "--package", str(package)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
