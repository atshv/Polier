"""scripts/release.py: versions and changelog sections from Conventional Commits."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent
SCRIPT = PACKAGE / "scripts" / "release.py"


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def repo(version: str = "1.2.0") -> Path:
    root = Path(tempfile.mkdtemp(prefix="pl-release-"))
    (root / "VERSION").write_text(version + "\n")
    (root / "package.json").write_text(json.dumps({"name": "x", "version": version}, indent=2) + "\n")
    (root / "CHANGELOG.md").write_text(f"# Changelog\n\nIntro.\n\n## {version}\n\nOld.\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: start")
    git(root, "tag", f"v{version}")
    return root


def commit(root: Path, message: str) -> None:
    (root / "f.txt").write_text(message)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *args], capture_output=True, text=True)


def outputs(path: Path) -> dict:
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


class Release(unittest.TestCase):
    def test_no_release_without_releasable_commits(self):
        root = repo()
        commit(root, "docs: typo")
        commit(root, "not conventional at all")
        out = root / "out.txt"
        result = run(root, "--write", "--github-output", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs(out)["release"], "false")
        self.assertEqual((root / "VERSION").read_text().strip(), "1.2.0")

    def test_feat_bumps_minor_and_writes_the_section(self):
        root = repo()
        commit(root, "feat(plugin): live context")
        commit(root, "fix: guard message")
        out, notes = root / "out.txt", root / "notes.md"
        result = run(root, "--write", "--notes", str(notes), "--github-output", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs(out), {"release": "true", "version": "1.3.0", "tag": "v1.3.0",
                                        "prerelease": "false", "changed": "true"})
        self.assertEqual((root / "VERSION").read_text().strip(), "1.3.0")
        self.assertEqual(json.loads((root / "package.json").read_text())["version"], "1.3.0")
        text = (root / "CHANGELOG.md").read_text()
        self.assertLess(text.index("## 1.3.0"), text.index("## 1.2.0"))
        self.assertIn("**Features**", text)
        self.assertIn("- **plugin:** live context", text)
        self.assertIn("- guard message", text)
        self.assertTrue(notes.read_text().startswith("**Features**"))

    def test_fix_bumps_patch_and_breaking_bumps_major(self):
        root = repo()
        commit(root, "fix: one")
        self.assertIn("v1.2.1", run(root).stdout)
        commit(root, "refactor!: drop the old command\n\nBREAKING CHANGE: /pl is gone")
        self.assertIn("v2.0.0", run(root).stdout)
        run(root, "--write")
        self.assertIn("- drop the old command — /pl is gone", (root / "CHANGELOG.md").read_text())

    def test_before_1_0_features_bump_the_patch_and_breaking_the_minor(self):
        root = repo("0.4.2")
        commit(root, "feat: new tool")
        out = root / "out.txt"
        result = run(root, "--github-output", str(out))
        self.assertIn("v0.4.3", result.stdout)
        self.assertIn("pre-release", result.stdout)
        self.assertEqual(outputs(out)["prerelease"], "true")
        commit(root, "feat!: new shape")
        self.assertIn("v0.5.0", run(root).stdout)

    def test_version_can_go_back_when_reset_by_hand(self):
        root = repo("4.3.0")
        (root / "VERSION").write_text("0.4.3\n")
        (root / "CHANGELOG.md").write_text("# Changelog\n\n## 0.4.3\n\nReset.\n\n## 4.3.0\n\nOld.\n")
        commit(root, "chore: reset the version")
        self.assertIn("v0.4.3 (hand-made, pre-release", run(root).stdout)
        git(root, "tag", "v0.4.3")
        commit(root, "feat: next")
        self.assertIn("v0.4.4", run(root).stdout)

    def test_hand_made_release_keeps_its_section(self):
        root = repo()
        (root / "VERSION").write_text("2.0.0\n")
        (root / "CHANGELOG.md").write_text("# Changelog\n\n## 2.0.0\n\nHand-written.\n\n## 1.2.0\n\nOld.\n")
        commit(root, "chore: bump")
        notes = root / "notes.md"
        result = run(root, "--write", "--notes", str(notes))
        self.assertIn("v2.0.0 (hand-made", result.stdout)
        self.assertEqual(notes.read_text().strip(), "Hand-written.")
        self.assertEqual((root / "CHANGELOG.md").read_text().count("## 2.0.0"), 1)

    def test_release_commits_are_ignored(self):
        root = repo()
        commit(root, "chore(release): v1.2.0")
        self.assertIn("no release", run(root).stdout)


if __name__ == "__main__":
    unittest.main()
