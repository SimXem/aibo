"""The math-problem knowledge-shock project inside this repository
(experiments/math-shock/, a git subtree, 2026-11-10): its own tests, the
pretask's pack rebuilt from it, and the step that runs it
(code/math_shock_pipeline.py). Offline: no provider is called."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
PROJECT = REPO / "experiments" / "math-shock"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bp = _load("build_math_shock_pack", REPO / "code" / "build_math_shock_pack.py")
mp = _load("math_shock_pipeline", REPO / "code" / "math_shock_pipeline.py")
rs = _load("run_math_shock", REPO / "code" / "run_math_shock.py")
# The project's commit the pinned pack (code/run_math_shock.py PACK_SHA256)
# was built from, on 2026-11-10: the subtree's first `git subtree add`.
PINNED_COMMIT = "85e802c688dc19a283b8d7516785d86f455a0ef0"

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


class TestTheProject(unittest.TestCase):
    @unittest.skipUnless(HAVE_YAML, "needs PyYAML (pip install -e '.[test]')")
    def test_its_own_tests_pass_through_the_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, str(REPO / "code" / "math_shock_pipeline.py"), "test"],
                               capture_output=True, text=True, timeout=300,
                               env={**os.environ, mp.PYTHON_ENV: sys.executable, "TMPDIR": tmp,
                                    "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertRegex(r.stderr, r"Ran \d+ tests")

    def test_its_code_is_the_projects(self):
        # run locks hash pipeline/, rules/ and templates/ (its common.source_hash): the copy keeps the layout
        for d in ("pipeline", "rules", "templates", "config", "runs/w1-r1", "statements"):
            self.assertTrue((PROJECT / d).is_dir(), d)


class TestThePack(unittest.TestCase):
    def test_the_subtree_rebuilds_the_pinned_pack(self):
        with patch("sys.stdout"):
            pack, run = bp.build(bp.SOURCE, "w1-r1")
            bp.parity(pack, run)
        # Whatever else the subtree has gained since, w1-r1's pack is the pinned one.
        pack["source"]["commit"] = PINNED_COMMIT
        self.assertEqual(bp.ms.sha256_bytes(bp.serialize(pack)), rs.PACK_SHA256)
        self.assertEqual((pack["pack"], len(pack["problems"])), (rs.PACK_ID, 60))


def _git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
                          env=env).stdout.strip()


class TestSourceCommit(unittest.TestCase):
    """The commit a pack names: a checkout's HEAD; a subtree's upstream
    commit while unchanged from it, else the host's HEAD and the path."""

    def test_a_checkout_and_a_subtree(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, host = Path(tmp) / "proj", Path(tmp) / "host"
            for d in (proj, host):
                d.mkdir()
                _git(d, "init", "-q", "-b", "main")
            (proj / "a.txt").write_text("a\n")
            _git(proj, "add", "a.txt")
            _git(proj, "commit", "-q", "-m", "one")
            head = _git(proj, "rev-parse", "HEAD")
            self.assertEqual(bp.source_commit(proj), head)
            (host / "readme").write_text("host\n")
            _git(host, "add", "readme")
            _git(host, "commit", "-q", "-m", "host")
            _git(host, "subtree", "add", "-q", "--prefix=x/proj", str(proj), "main")
            self.assertEqual(bp.source_commit(host / "x" / "proj"), head)
            (host / "readme").write_text("host, changed\n")              # elsewhere in the host: still the project's
            _git(host, "commit", "-q", "-am", "elsewhere")
            self.assertEqual(bp.source_commit(host / "x" / "proj"), head)
            (host / "x" / "proj" / "a.txt").write_text("b\n")             # the copy itself: no project commit has it
            _git(host, "commit", "-q", "-am", "changed")
            self.assertEqual(bp.source_commit(host / "x" / "proj"), f"{_git(host, 'rev-parse', 'HEAD')}:x/proj")
            self.assertIsNone(bp.source_commit(Path(tmp)))


class TestTheStep(unittest.TestCase):
    def test_each_step_runs_where_it_should(self):
        with patch.dict(os.environ, {mp.PYTHON_ENV: "/opt/py"}):
            cmd, cwd, keys = mp.command("forecast", ["config/runs/w1-r1.yaml", "--stub"])
            self.assertEqual((cmd, cwd, keys),
                             (["/opt/py", "-m", "pipeline.stage_forecast", "config/runs/w1-r1.yaml", "--stub"],
                              mp.PROJECT, True))
            self.assertEqual(mp.command("followup", ["c.yaml"])[0][1:3], ["-m", "pipeline.stage_followup"])
            self.assertEqual(mp.command("prepare", ["c.yaml"])[0][1:3], ["-m", "pipeline.stage_prepare"])
            cmd, cwd, keys = mp.command("test", [])
            self.assertEqual((cmd[1:5], cwd, keys), (["-m", "unittest", "discover", "-s"], mp.PROJECT, False))
            cmd, cwd, keys = mp.command("pack", ["--run", "w1-r1"])
            self.assertEqual((cmd[0], cmd[1:], cwd, keys),
                             (sys.executable, [str(REPO / "code" / "build_math_shock_pack.py"), "--run", "w1-r1"],
                              str(REPO), False))
        self.assertEqual(Path(mp.PROJECT), PROJECT)

    def test_the_api_stages_get_this_repositorys_keys_and_nothing_leaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "env"
            env_file.write_text("ANTHROPIC_API_KEY=sk-test\n")
            with patch.dict(os.environ, {"REDLINES_ENV_FILE": str(env_file)}):
                os.environ.pop("ANTHROPIC_API_KEY", None)
                self.assertEqual(mp.environment(True)["ANTHROPIC_API_KEY"], "sk-test")
                self.assertNotIn("ANTHROPIC_API_KEY", os.environ)            # the parent's environment is untouched
                self.assertNotIn("ANTHROPIC_API_KEY", mp.environment(False))  # tests and packs get no keys

    def test_an_unknown_step_is_refused(self):
        with patch("sys.stderr"), patch("sys.stdout"):
            self.assertEqual(mp.main(["nonsense"]), 2)
            self.assertEqual(mp.main(["--help"]), 0)


if __name__ == "__main__":
    unittest.main()
