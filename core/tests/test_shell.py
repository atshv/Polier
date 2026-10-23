"""core.shell: which files a command line writes, before it runs."""
from __future__ import annotations

import os
import tempfile
import unittest

from core.scope import is_tracked
from core.shell import write_targets

from .fixtures import project, task


def found(command: str, cwd: str = "/p"):
    targets, unresolved = write_targets(command, cwd)
    return [(t.path, t.how) for t in targets], unresolved


class Redirections(unittest.TestCase):
    def test_write_redirections(self):
        for op in (">", ">>", ">|", "&>", "&>>", "<>", "2>", ">&"):
            with self.subTest(op):
                self.assertEqual(found(f"echo x {op} out.txt")[0], [("/p/out.txt", "write")])

    def test_fd_duplication_and_reads_are_not_writes(self):
        self.assertEqual(found("make 2>&1 < in.txt | grep x")[0], [])
        self.assertEqual(found("cat <<< word")[0], [])

    def test_no_spaces_and_quotes(self):
        self.assertEqual(found("echo a>b;echo c>>'my file'")[0], [("/p/b", "write"), ("/p/my file", "write")])
        self.assertEqual(found('echo "#x" > h')[0], [("/p/h", "write")])

    def test_heredoc_body_is_data(self):
        command = "cat > out.txt <<'EOF'\nnot > a.txt\nEOF\ntouch b"
        self.assertEqual(found(command)[0], [("/p/out.txt", "write"), ("/p/b", "write")])

    def test_comments_end_at_the_line(self):
        self.assertEqual(found("ls # note > x\nrm f")[0], [("/p/f", "delete")])


class Commands(unittest.TestCase):
    def test_common_writers(self):
        cases = {
            "tee -a log.txt": [("/p/log.txt", "write")],
            "touch a b": [("/p/a", "write"), ("/p/b", "write")],
            "truncate -s 0 f": [("/p/f", "write")],
            "rm -rf build": [("/p/build", "delete")],
            "unlink f": [("/p/f", "delete")],
            "cp a b": [("/p/b", "write")],
            "cp a b dir/": [("/p/dir/a", "write"), ("/p/dir/b", "write")],
            "cp -t d a": [("/p/d/a", "write")],
            "mv old new": [("/p/new", "write"), ("/p/old", "delete")],
            "ln -s target link": [("/p/link", "write")],
            "install -m 644 a /p/bin/a": [("/p/bin/a", "write")],
            "sed -i s/a/b/ f1 f2": [("/p/f1", "write"), ("/p/f2", "write")],
            "sed -e s/a/b/ --in-place f": [("/p/f", "write")],
            "sed s/a/b/ f": [],
            "perl -pi -e s/a/b/ f": [("/p/f", "write")],
            "perl -pie s/a/b/ f": [("/p/f", "write")],
            "dd if=/dev/zero of=img bs=1": [("/p/img", "write")],
        }
        for command, expected in cases.items():
            with self.subTest(command):
                self.assertEqual(found(command)[0], expected)

    def test_copy_into_an_existing_folder(self):
        root = tempfile.mkdtemp()
        os.mkdir(os.path.join(root, "dir"))
        self.assertEqual(found("cp a dir", root)[0], [(os.path.join(root, "dir", "a"), "write")])

    def test_wrappers_assignments_and_nested_shells(self):
        self.assertEqual(found("FOO=1 sudo -E rm x")[0], [("/p/x", "delete")])
        self.assertEqual(found("env A=b tee f")[0], [("/p/f", "write")])
        self.assertEqual(found("bash -c 'echo hi > x'")[0], [("/p/x", "write")])
        self.assertEqual(found("eval echo hi '>' y")[0], [("/p/y", "write")])

    def test_cd_moves_the_base(self):
        self.assertEqual(found("cd src && echo x > ../README.md")[0], [("/p/README.md", "write")])
        self.assertEqual(found("(cd sub; touch y); touch z")[0], [("/p/sub/y", "write"), ("/p/z", "write")])
        self.assertEqual(found("cd $DIR && touch y"), ([], ["y"]))

    def test_unresolved_and_invisible(self):
        self.assertEqual(found("echo $F > $G"), ([], ["$G"]))
        self.assertEqual(found("touch *.py"), ([], ["*.py"]))
        self.assertEqual(found('echo "open quote'), ([], ['echo "open quote']))
        # Not visible to a static look; the stop check covers these.
        for command in ("python -c \"open('x','w')\"", "git checkout -- .", "make", "find . -delete",
                        "xargs rm < list", "npm install"):
            with self.subTest(command):
                self.assertEqual(found(command)[0], [])

    def test_home(self):
        self.assertEqual(found("touch ~/x")[0], [(os.path.expanduser("~/x"), "write")])


class Tracked(unittest.TestCase):
    def test_is_tracked(self):
        root = project([task()])
        (root / "new.txt").write_text("n\n")
        self.assertTrue(is_tracked(root, "README.md"))
        self.assertTrue(is_tracked(root, "src"))
        self.assertFalse(is_tracked(root, "new.txt"))
        self.assertFalse(is_tracked(root, "missing/dir"))


if __name__ == "__main__":
    unittest.main()
