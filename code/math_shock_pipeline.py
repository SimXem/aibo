#!/usr/bin/env python3
"""The math-problem knowledge-shock pipeline as a step of its own, from this
repository's root (2026-11-10).

The project lives at experiments/math-shock/, a git subtree of
github.com/SimXem/math-problem-info-shock (its README says what each stage
does). Models forecast when open math problems will be solved; a follow-up
shows them which were. It runs apart from AIRO's math-shock pretask
(code/run_math_shock.py), which asks the pack built from one of its runs
before AIRO's or the welfare page's prompt.

    python code/math_shock_pipeline.py prepare  config/runs/w1-r1.yaml          # data, sample, statements, prompts
    python code/math_shock_pipeline.py forecast config/runs/w1-r1.yaml --stub   # free offline dry run
    python code/math_shock_pipeline.py forecast config/runs/w1-r1.yaml          # PAID: batch API, half price
    python code/math_shock_pipeline.py followup config/followups/w1-r1-f2.yaml  # PAID
    python code/math_shock_pipeline.py test                                     # its tests: no network, no API
    python code/math_shock_pipeline.py pack --run w1-r1                         # the pretask's pack (build_math_shock_pack.py)

Paths after a stage are the project's (relative to experiments/math-shock/),
as in its README, and every other argument goes through to the stage
(--models, --samples, --direct, --stub, --no-fetch, ...). `prepare` drafts
any missing problem statement through the API (PAID); the frozen ones are
reused.

The interpreter: $MATH_SHOCK_PYTHON, else experiments/math-shock/.venv/bin/python
(make it as its README does:
  python3 -m venv experiments/math-shock/.venv
  experiments/math-shock/.venv/bin/pip install -r experiments/math-shock/requirements.lock.txt),
else this one. API keys: this repository's (redlines.llm.load_keys --
$REDLINES_ENV_FILE, else ~/.config/redlines/env, else .env), and then, for any
still unset, the project's own experiments/math-shock/.env (its pipeline/llm.py).
"""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT = os.path.join(ROOT, "experiments", "math-shock")
PYTHON_ENV = "MATH_SHOCK_PYTHON"
# The project's three runners (pipeline/stage_*.py), which may call the API.
STAGES = {"prepare": "pipeline.stage_prepare", "forecast": "pipeline.stage_forecast",
          "followup": "pipeline.stage_followup"}
OTHER = {"test": "the project's tests (no network, no API)",
         "pack": "the pretask's pack from one of its runs (code/build_math_shock_pack.py)"}


def python():
    """The interpreter the project runs under (this file's docstring)."""
    venv = os.path.join(PROJECT, ".venv", "bin", "python")
    return os.environ.get(PYTHON_ENV) or (venv if os.path.exists(venv) else sys.executable)


def command(step, args):
    """-> (argv, cwd, whether it needs the API keys)."""
    if step in STAGES:
        return [python(), "-m", STAGES[step], *args], PROJECT, True
    if step == "test":
        return [python(), "-m", "unittest", "discover", "-s", "tests", "-t", ".", *args], PROJECT, False
    if step == "pack":
        return [sys.executable, os.path.join(ROOT, "code", "build_math_shock_pack.py"), *args], ROOT, False
    raise ValueError(step)


def environment(keys):
    env = dict(os.environ)
    if keys:
        sys.path.insert(0, ROOT)
        from redlines.llm import load_keys
        saved = dict(os.environ)
        try:
            load_keys()             # into os.environ, never over what is set
            env = dict(os.environ)
        finally:
            os.environ.clear()
            os.environ.update(saved)
    return env


def usage():
    steps = "\n".join(f"  {s:9} {m}" for s, m in [*((s, m) for s, m in STAGES.items()), *OTHER.items()])
    return f"usage: python code/math_shock_pipeline.py STEP [ARGS...]\n\n{steps}\n\n" + __doc__.split("\n\n")[2]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in {**STAGES, **OTHER}:
        print(usage(), file=sys.stderr if argv and argv[0] not in ("-h", "--help") else sys.stdout)
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    cmd, cwd, keys = command(argv[0], argv[1:])
    return subprocess.run(cmd, cwd=cwd, env=environment(keys)).returncode


if __name__ == "__main__":
    sys.exit(main())
