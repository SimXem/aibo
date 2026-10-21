"""code/pull.sh brings the box's checkout up to upstream before a job: rebuilt
outputs the pull also changes are backed up and replaced, anything else in
the way stops it and pages.

Each test builds an upstream repository, a box clone of it and a dev clone
that pushes the incoming commits, all under a temp root, with a stub curl
that records each page. Nothing outside the temp root is touched."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

STUB_CURL = '#!/usr/bin/env bash\necho "$*" >> "$PAGES"\n'


class TestPull(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.home, bin_ = t / "home", t / "bin"
        self.home.mkdir()
        bin_.mkdir()
        (bin_ / "curl").write_text(STUB_CURL)
        (bin_ / "curl").chmod(0o755)
        self.pages = t / "pages"
        self.env = {"PATH": f"{bin_}:{os.environ['PATH']}", "HOME": str(self.home),
                    "NTFY_TOPIC": "test", "PAGES": str(self.pages),
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                    "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_NOSYSTEM": "1"}
        upstream, self.dev, self.box = t / "upstream.git", t / "dev", t / "box"
        self.git(t, "init", "-q", "--bare", "-b", "main", str(upstream))
        self.git(t, "clone", "-q", str(upstream), str(self.dev))
        (self.dev / "code").mkdir()
        for f in ("pull.sh", "notify.sh"):
            shutil.copy(ROOT / "code" / f, self.dev / "code" / f)
        for f in ("src.py", "index.html", "results/graph.json", "data/x_conditions.json", "pyproject.toml"):
            self.write(self.dev, f, "v1\n")
        self.commit("first")
        self.git(t, "clone", "-q", str(upstream), str(self.box))

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(self, repo, f, text):
        (repo / f).parent.mkdir(parents=True, exist_ok=True)
        (repo / f).write_text(text)

    def commit(self, msg, files=None):
        for f, text in (files or {}).items():
            self.write(self.dev, f, text)
        self.git(self.dev, "add", "-A")
        self.git(self.dev, "commit", "-qm", msg)
        self.git(self.dev, "push", "-q", "origin", "main")

    def pull(self):
        r = subprocess.run(["bash", str(self.box / "code" / "pull.sh")], env=self.env,
                           capture_output=True, text=True)
        pages = self.pages.read_text().splitlines() if self.pages.exists() else []
        return r.returncode, pages

    def head(self, repo):
        return self.git(repo, "rev-parse", "HEAD")

    def test_up_to_date_does_nothing(self):
        rc, pages = self.pull()
        self.assertEqual((rc, pages), (0, []))
        self.assertIn("up to date", (self.home / "logs" / "pull.log").read_text())

    def test_fast_forwards(self):
        self.commit("change", {"src.py": "v2\n"})
        rc, pages = self.pull()
        self.assertEqual((rc, pages), (0, []))
        self.assertEqual(self.head(self.box), self.head(self.dev))

    def test_a_rebuilt_output_the_pull_changes_is_backed_up_and_replaced(self):
        self.write(self.box, "results/graph.json", "box\n")
        self.write(self.box, "index.html", "box\n")
        self.commit("rebuild", {"results/graph.json": "v2\n", "index.html": "v2\n"})
        rc, pages = self.pull()
        self.assertEqual((rc, pages), (0, []))
        self.assertEqual(self.head(self.box), self.head(self.dev))
        self.assertEqual((self.box / "results/graph.json").read_text(), "v2\n")
        [backup] = (self.home / "backups").iterdir()
        self.assertEqual((backup / "results/graph.json").read_text(), "box\n")
        self.assertEqual((backup / "index.html").read_text(), "box\n")

    def test_a_rebuilt_output_the_pull_leaves_alone_is_kept(self):
        self.write(self.box, "results/graph.json", "box\n")
        self.commit("change", {"src.py": "v2\n"})
        rc, _ = self.pull()
        self.assertEqual(rc, 0)
        self.assertEqual((self.box / "results/graph.json").read_text(), "box\n")
        self.assertFalse((self.home / "backups").exists())

    def test_any_other_clash_stops_the_pull_and_pages(self):
        before = self.head(self.box)
        self.write(self.box, "src.py", "hotfix\n")
        self.commit("change", {"src.py": "v2\n"})
        rc, pages = self.pull()
        self.assertEqual(rc, 1)
        self.assertEqual(self.head(self.box), before)
        self.assertEqual((self.box / "src.py").read_text(), "hotfix\n")
        self.assertTrue(any("Box code not updated" in p and "src.py" in p for p in pages), pages)

    def test_a_commit_only_on_the_box_stops_the_pull(self):
        self.write(self.box, "local.txt", "x\n")
        self.git(self.box, "add", "local.txt")
        self.git(self.box, "commit", "-qm", "local")
        self.commit("change", {"src.py": "v2\n"})
        rc, pages = self.pull()
        self.assertEqual(rc, 1)
        self.assertTrue(any("commits upstream does not" in p for p in pages), pages)

    def test_a_dependency_change_pages_after_pulling(self):
        self.commit("deps", {"pyproject.toml": "v2\n"})
        rc, pages = self.pull()
        self.assertEqual(rc, 0)
        self.assertEqual(self.head(self.box), self.head(self.dev))
        self.assertTrue(any("dependencies changed" in p and "pyproject.toml" in p for p in pages), pages)


if __name__ == "__main__":
    unittest.main()
