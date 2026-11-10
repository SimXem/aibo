"""The math-shock pretask (redlines/math_shock.py, code/run_math_shock.py,
code/math_shock_pi). Offline: a synthetic pack, fakes for the loop, and --
where node and the pinned pi are installed -- the real pi against a scripted
local model. No provider is called."""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / "packages" / "fri-forecaster"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from redlines import math_shock as ms  # noqa: E402
from redlines.registry import MODELS  # noqa: E402

T0 = "2026-06-30"
FORECAST = ("Today's date is {run_date}.\n\n{n_items} problems, open on {t0}. No date before {t0_month}.\n\n"
            "Problems:\n{items}\n\nReply with a JSON array only:\n"
            "[{{\"id\": \"<problem id>\", \"best\": \"YYYY-MM\", \"q10\": \"YYYY-MM\", \"q90\": \"YYYY-MM\"}}, ...]\n")
REVEAL = ("Here is what happened between {t0} and {snapshot_date}.\n\n"
          "{n_solved} of the {n_items} problems above were solved. {n_guaranteed} chosen; the other {n_random} "
          "random, {n_random_solved} of those solved. Of all {n_eligible}, {n_pool_solved} ({pool_pct}%) by "
          "{snapshot_date}.\n\nThe solved problems, with your earlier forecast for each:\n\n{solved_items}\n\n"
          "The other {n_open} problems were still open on {snapshot_date}. Taking this information into account, "
          "give revised forecasts for these {n_open} problems:\n\n{open_items}\n\nNo date before {s_month}.\n")
PROBLEMS = [
    {"unit_id": "erdos:1", "code": "PAAAAA", "role": "guaranteed", "stratum": "erdos", "display_name": "Erdős Problem 1",
     "solved": 1, "solve_date": "2026-09-14", "outcome_type": "proved", "statement": "Show that STATEMENT-ONE holds."},
    {"unit_id": "erdos:2", "code": "PBBBBB", "role": "random", "stratum": "erdos", "display_name": "Erdős Problem 2",
     "solved": 1, "solve_date": "2026-08-02", "outcome_type": "", "statement": "Decide STATEMENT-TWO."},
    {"unit_id": "fc:3", "code": "PCCCCC", "role": "random", "stratum": "fc_named", "display_name": "Paper: Three",
     "solved": 0, "solve_date": "", "outcome_type": "", "statement": "Prove STATEMENT-THREE."},
    {"unit_id": "fc:4", "code": "PDDDDD", "role": "random", "stratum": "fc_other", "display_name": "Wikipedia: Four",
     "solved": 0, "solve_date": "", "outcome_type": "", "statement": "Is STATEMENT-FOUR true?"},
]
TEXT = [s for p in PROBLEMS for s in (p["statement"], p["display_name"])]


def make_pack(directory, pack_id="math-shock-test"):
    pack = {"pack": pack_id, "format": ms.PACK_FORMAT, "source": {"run_id": "test"}, "t0": T0,
            "snapshot_date": "2026-11-02", "source_run_date": "2026-11-03",
            "sample_log": {"n_eligible": 40, "n_solved_pool": 5}, "problems": copy.deepcopy(PROBLEMS),
            "templates": {"forecast": FORECAST, "reveal_solved": REVEAL}}
    data = (json.dumps(pack, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode()
    path = ms.pack_path(pack_id, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return pack_id, ms.sha256_bytes(data)


def answer(**dates):
    """A JSON array reply; dates: code -> (best, q10, q90)."""
    return json.dumps([{"id": c, "best": b, "q10": lo, "q90": hi} for c, (b, lo, hi) in dates.items()])


GOOD = answer(PAAAAA=("2027-01", "2026-08", "2030-01"),     # solved 2026-09: inside
              PBBBBB=("2040-01", "2030-01", "after-2100"),  # solved 2026-08: before the 10% date
              PCCCCC=("2028-01", "2027-01", "2035-01"),
              PDDDDD=("after-2100", "2050-01", "after-2100"))


class PackCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pack_id, self.sha = make_pack(self.tmp.name)
        self.pack = ms.load_pack(self.pack_id, self.sha, self.tmp.name)
        self.codes = [p["code"] for p in PROBLEMS]


class TestPack(PackCase):
    def test_pinned_hash(self):
        with self.assertRaisesRegex(ValueError, "not the pinned"):
            ms.load_pack(self.pack_id, "0" * 64, self.tmp.name)
        with self.assertRaises(FileNotFoundError):
            ms.load_pack("math-shock-none", self.sha, self.tmp.name)

    def test_folder_from_the_environment(self):
        with patch.dict(os.environ, {ms.PRETASK_DIR_ENV: self.tmp.name}):
            self.assertEqual(ms.load_pack(self.pack_id, self.sha)["pack"], self.pack_id)
        with patch.dict(os.environ, {ms.PRETASK_DIR_ENV: ""}):
            self.assertEqual(ms.pretask_dir(), REPO / "private" / "pretasks")     # gitignored

    def test_order_is_the_projects_hash_rank(self):
        order = ms.order(self.pack, "seed")
        self.assertEqual(sorted(order), sorted(self.codes))
        self.assertEqual(order, ms.order(self.pack, "seed"))
        want = [p["code"] for p in sorted(PROBLEMS, key=lambda p: ms.sha256_text(f"seed|{p['unit_id']}"))]
        self.assertEqual(order, want)
        self.assertTrue(any(ms.order(self.pack, f"s{i}") != order for i in range(10)))

    def test_math_prompt_is_the_template(self):
        p = ms.math_prompt(self.pack, ["PCCCCC", "PAAAAA"], "2026-11-10")
        self.assertEqual(p, FORECAST.format(run_date="2026-11-10", t0=T0, t0_month="2026-06", n_items=2,
                                            items="[PCCCCC] Paper: Three: Prove STATEMENT-THREE.\n"
                                                  "[PAAAAA] Erdős Problem 1: Show that STATEMENT-ONE holds."))


class TestParse(PackCase):
    """pipeline/parse.py's rules: flagged, never repaired."""

    def test_good_answer_in_prose_and_fences(self):
        rows, issues, parsed = ms.parse_answer(f"Here you go:\n```json\n{GOOD}\n```", self.codes, T0)
        self.assertTrue(parsed)
        self.assertEqual(issues, [])
        self.assertEqual([r["valid"] for r in rows], [1, 1, 1, 1])
        self.assertEqual(rows[3]["best"], "after-2100")

    def test_violations(self):
        text = json.dumps([
            {"id": "PAAAAA", "best": "2027-13", "q10": "2026-08", "q90": "2030-01"},     # bad month
            {"id": "PBBBBB", "best": "2025-01", "q10": "2030-01", "q90": "2031-01"},     # unordered, before T0
            {"id": "PCCCCC", "best": "2028-01", "q10": "2027-01", "q90": "2035-01"},
            {"id": "PCCCCC", "best": "2029-01", "q10": "2027-01", "q90": "2035-01"},     # duplicate
            {"id": "PZZZZZ", "best": "2029-01", "q10": "2027-01", "q90": "2035-01"},     # unknown
            "not an object",
        ])
        rows, issues, parsed = ms.parse_answer(text, self.codes, T0)
        self.assertTrue(parsed)
        by = {r["code"]: r for r in rows}
        self.assertEqual(by["PAAAAA"]["issues"], "bad format best='2027-13'")
        self.assertEqual(by["PBBBBB"]["issues"], "quantiles not ordered; date before T0 month")
        self.assertEqual((by["PCCCCC"]["valid"], by["PCCCCC"]["best"]), (1, "2028-01"))
        self.assertEqual(by["PDDDDD"]["issues"], "missing")
        self.assertEqual(issues, ["duplicate id PCCCCC", "unknown id 'PZZZZZ'", "unknown id ''"])

    def test_no_array_is_unparsed(self):
        rows, issues, parsed = ms.parse_answer("I would rather not.", self.codes, T0)
        self.assertFalse(parsed)
        self.assertEqual({r["issues"] for r in rows}, {"unparseable"})
        self.assertEqual(ms.parse_answer(None, self.codes, T0)[2], False)


class TestReveal(PackCase):
    def rows(self, text=GOOD):
        return ms.parse_answer(text, self.codes, T0)[0]

    def test_relations(self):
        f = {"valid": 1, "best": "2030-01", "q10": "2027-01", "q90": "2040-01"}
        self.assertEqual(ms.relation("2026-09-01", f), "solved before your 10% date")
        self.assertEqual(ms.relation("2027-01-31", f), "solved inside your 10%-90% range")
        self.assertEqual(ms.relation("2040-02-01", f), "solved after your 90% date")
        self.assertEqual(ms.relation("2026-09-01", {**f, "valid": "0"}), "you gave no valid forecast")
        self.assertEqual(ms.relation("2026-09-01", None), "you gave no valid forecast")
        self.assertEqual(ms.fmt(f), "best 2030-01, q10 2027-01, q90 2040-01")
        self.assertEqual(ms.relations(self.pack, self.rows()),
                         {"PAAAAA": "solved inside your 10%-90% range", "PBBBBB": "solved before your 10% date"})

    def test_shock_message(self):
        order = ["PDDDDD", "PBBBBB", "PCCCCC", "PAAAAA"]
        msg = ms.message(self.pack, order, self.rows(), "solved_side_by_side")
        self.assertEqual(msg, (
            "Here is what happened between 2026-06-30 and 2026-11-02.\n\n"
            "2 of the 4 problems above were solved. 1 chosen; the other 3 random, 1 of those solved. "
            "Of all 40, 5 (12.5%) by 2026-11-02.\n\nThe solved problems, with your earlier forecast for each:\n\n"
            "- [PBBBBB] Erdős Problem 2: solved on 2026-08-02 (resolved). Your forecast: best 2040-01, q10 "
            "2030-01, q90 after-2100; solved before your 10% date.\n"
            "- [PAAAAA] Erdős Problem 1: solved on 2026-09-14 (proved). Your forecast: best 2027-01, q10 "
            "2026-08, q90 2030-01; solved inside your 10%-90% range.\n\n"
            "The other 2 problems were still open on 2026-11-02:\n\n"
            "[PDDDDD] Wikipedia: Four\n[PCCCCC] Paper: Three\n\n" + ms.HANDOFF))
        self.assertNotIn("revised forecasts", msg)

    def test_placebo_is_the_handoff_alone(self):
        self.assertEqual(ms.message(self.pack, self.codes, self.rows(), "none"), "Next, a separate set of questions.")
        with self.assertRaises(ValueError):
            ms.message(self.pack, self.codes, self.rows(), "all")

    def test_invalid_forecasts_still_get_the_outcomes(self):
        rows = ms.parse_answer(answer(PAAAAA=("2027-01", "2026-08", "2030-01")), self.codes, T0)[0]
        msg = ms.message(self.pack, self.codes, rows, "solved_side_by_side")
        self.assertIn("[PBBBBB] Erdős Problem 2: solved on 2026-08-02 (resolved). Your forecast: (no valid "
                      "forecast); you gave no valid forecast.", msg)

    def test_row_record_has_no_problem_text(self):
        rows, issues, _ = ms.parse_answer(GOOD, self.codes, T0)
        prompt = ms.math_prompt(self.pack, self.codes, "2026-11-10")
        msg = ms.message(self.pack, self.codes, rows, "solved_side_by_side")
        rec = ms.row_record(self.pack, self.sha, "solved_side_by_side", self.codes, rows, issues, prompt=prompt,
                            msg=msg, turns=1, math_calls=1, usage={"cost_usd": 0.1}, transcript="t.json")
        blob = json.dumps(rec, ensure_ascii=False)
        for t in TEXT + ["Erdős", "solved on"]:
            self.assertNotIn(t, blob)
        self.assertEqual((rec["n_valid"], rec["order"], rec["prompt_sha256"]), (4, self.codes, ms.sha256_text(prompt)))


class TestCutoffs(unittest.TestCase):
    def test_rule(self):
        cut = {"a/x": {"cutoff": "2026-06", "source": "s"}, "a/y": {"cutoff": "2026-07", "source": "s"}}
        self.assertTrue(ms.eligible("a/x", T0, cut)[0])
        self.assertFalse(ms.eligible("a/y", T0, cut)[0])
        self.assertIn("no training cutoff", ms.eligible("a/z", T0, cut)[1])

    def test_the_table_names_registry_models_with_sources(self):
        ids = {m["litellm_id"] for m in MODELS}
        for model, c in ms.load_cutoffs().items():
            self.assertIn(model, ids)
            self.assertRegex(c["cutoff"], r"^\d{4}-\d{2}$")
            self.assertIn("checked", c["source"])


def load_script():
    spec = importlib.util.spec_from_file_location("run_math_shock", REPO / "code" / "run_math_shock.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rs = load_script()
ru = rs.load_runner()


class FakeHarness:
    DEFAULT_PI = "/opt/pi/cli.js"

    def __init__(self):
        self.runs = []

    def run(self, **kw):
        self.runs.append(kw)
        return {"workdir": "/nonexistent/attempt-1"}


class TestArms(unittest.TestCase):
    def test_three_arms_from_the_baseline(self):
        base = rs.experiments.load("airo")["conditions"]["none"]
        arms = {c["id"]: c for c in rs.arm_conditions()}
        self.assertEqual(list(arms), ["control", "math-placebo", "math-shock"])
        for c in arms.values():
            self.assertEqual((c["publish"], c["pooled"], c["cadence"], c["variant"], c["instrument"]),
                             (False, False, "manual", "none", "minimal"))
        self.assertEqual(arms["control"]["sha256"], base["sha256"])   # it asks what the baseline asks
        self.assertNotIn("_pretask", arms["control"])
        self.assertEqual(arms["math-shock"]["_pretask"],
                         {"pack": rs.PACK_ID, "pack_sha256": rs.PACK_SHA256, "reveal": "solved_side_by_side"})
        self.assertEqual(arms["math-placebo"]["_pretask"]["reveal"], "none")
        self.assertEqual(len({c["sha256"] for c in arms.values()}), 3)

    def test_welfare_arms_from_its_baseline(self):
        base = rs.experiments.load("welfare")["conditions"]["none"]
        airo = {c["id"]: c for c in rs.arm_conditions()}
        arms = {c["id"]: c for c in rs.arm_conditions(base="welfare")}
        self.assertEqual(list(arms), list(rs.ARMS))
        for c in arms.values():
            self.assertEqual((c["scenarios"], c["publish"], c["pooled"], c["cadence"], c["variant"]),
                             (base["scenarios"], False, False, "manual", "none"))
        self.assertEqual(os.path.basename(base["scenarios"]), "welfare_conditions.json")
        self.assertEqual(arms["control"]["sha256"], base["sha256"])
        self.assertEqual(arms["math-shock"]["_pretask"], airo["math-shock"]["_pretask"])   # the same pack and reveal
        for a in rs.ARMS:                                                                  # a different condition
            self.assertNotEqual(arms[a]["sha256"], airo[a]["sha256"])
        with self.assertRaises(ValueError):
            rs.arm_conditions(base="axes")

    def test_welfare_rows_stay_out_of_airos_download(self):
        from redlines import export
        self.assertEqual((rs.experiment_name(), rs.experiment_name("welfare")), (rs.EXPERIMENT, "welfare-math-shock"))
        for base, in_airo in (("airo", True), ("welfare", False)):
            name = rs.experiment_name(base)
            for tag in (name, f"smoke-{name}"):          # run_unified.run's names under results/experiments/
                for f in (f"{tag}-2026-11-10T1200Z.jsonl", f"{tag}-2026-11-10T1200Z-instrument.jsonl"):
                    self.assertEqual(export.airo_file(f), in_airo, f)

    def test_no_experiment_file_runs_the_arms(self):
        # neither the cron nor `run_unified --experiment` can ask a math arm without its step
        for name in rs.experiments.names():
            self.assertFalse(set(rs.experiments.load(name)["conditions"]) & set(rs.ARMS))


class TestRunnerWraps(PackCase):
    """run_unified's own run_one_joint, its call_tools faked, the math step faked."""

    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {ms.PRETASK_DIR_ENV: self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.harness = FakeHarness()
        self.calls, self.math_calls = [], []
        self.answer_cells = [True]
        self.math_fail = []

    def cell(self, q):
        """What the series asks of one question per condition: a probability,
        or (welfare's) five percentiles inside its bounds."""
        mode = ru.question_mode(q, self.spec)
        lo = (q.get("bounds") or [0])[0]
        value = 0.01 if mode == ru.PROBABILITY else {f: lo + i + 1 for i, f in enumerate(ru.PERCENTILE_FIELDS)}
        return ru.CELL_MODES[mode]["key"], value

    def fake_call_tools(self, model, prompt, tools, final_tool, **kw):
        self.calls.append(dict(prompt=prompt, **kw))
        kw["usage"].update(cost_usd=kw["usage"].get("cost_usd", 0) + 1.0)
        ok = self.answer_cells.pop(0) if len(self.answer_cells) > 1 else self.answer_cells[0]
        cells = [{"question_id": q["id"], "horizon": hz,
                  self.cell(q)[0]: {k: self.cell(q)[1] for k in ["unconditional"] + self.cond_ids}}
                 for gg in self.g for q in self.b[gg["key"]] for hz in self.h if hz in q["horizons"]] if ok else []
        return {"forecasts": cells, "rationale": "r",
                "eci_forecast": {"p10": 168, "p25": 170, "p50": 172, "p75": 175, "p90": 178}}, []

    def fake_math_step(self, harness, model, pack, codes, run_date, *, system, record, usage, timeout=None):
        self.math_calls.append(dict(model=model, codes=codes, run_date=run_date, system=system))
        record["turns"].append({"user": "math", "reply": GOOD, "rc": 0, "usage": {}})
        rs.add_usage(usage, {"turns": 1, "input_tokens": 100, "output_tokens": 10, "cost_usd": 0.5})
        if self.math_fail and self.math_fail.pop(0):
            raise RuntimeError("math step: no JSON array after the retry turn")
        rows, issues, _ = ms.parse_answer(GOOD, codes, pack["t0"])
        return {"session": "/nonexistent/session.jsonl", "prompt": ms.math_prompt(pack, codes, run_date),
                "rows": rows, "issues": issues, "turns": 1}

    def run_arm(self, arm, retries=0, base=rs.DEFAULT_BASE):
        """One call of `arm` on `base`'s series, as run_unified.run makes it."""
        today = date(2026, 11, 10)
        cond = next(c for c in rs.arm_conditions({arm: rs.ARMS[arm]}, self.pack_id, self.sha, base=base))
        pol = ru.load_policies(os.path.join(ru.ROOT, cond["scenarios"]))
        self.g, self.b, h, _, spec = (ru.load_questions(pol["questions"]) if pol.get("questions")
                                      else ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED))
        self.spec = spec
        self.h = ru.set_horizons(pol, h)
        self.cond_ids = [c["id"] for c in ru.resolve_set(pol, today)["conditions"]]
        orig = ru.call_tools, ru.run_one_joint, ru.select_models
        ru.call_tools = self.fake_call_tools
        pt = rs.Pretask(ru, self.pack, self.sha, {}, harness=self.harness).install()
        try:
            with patch.object(rs, "math_step", self.fake_math_step):
                rows = ru.run_one_joint("Opus 5.5", "anthropic/claude-opus-5-5", self.g, self.b, self.h,
                                        "2026-11-10T1200Z", retries, spec, pol["conditions"], pol, cond,
                                        rs.experiment_name(base), "joint#1", None, today)
        finally:
            pt.uninstall()
            ru.call_tools, ru.run_one_joint, ru.select_models = orig
        return rows

    def test_control_is_untouched(self):
        rows = self.run_arm("control")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["prompt"], rows[0]["prompt"])
        self.assertNotIn("run", self.calls[0])
        self.assertEqual(self.math_calls, [])
        self.assertEqual({r["pretask"] for r in rows}, {None})
        self.assertEqual(rows[0]["condition"], "control")

    def test_shock_continues_the_math_conversation(self):
        control = self.run_arm("control")[0]
        self.calls.clear()
        rows = self.run_arm("math-shock")
        call = self.calls[0]
        rec = rows[0]["pretask"]
        # AIRO's prompt is the control's, after the reveal and the handoff, in one user turn
        self.assertEqual(rows[0]["prompt_sha256"], control["prompt_sha256"])
        msg = ms.message(self.pack, rec["order"], ms.parse_answer(GOOD, rec["order"], T0)[0], "solved_side_by_side")
        self.assertEqual(call["prompt"], msg + "\n\n" + rows[0]["prompt"])
        self.assertTrue(call["prompt"].startswith("Here is what happened"))
        # the session reaches agent-box's run through the wrapper
        self.assertEqual(call["env"][rs.SESSION_ENV], "/nonexistent/session.jsonl")
        self.assertEqual(call["env"][rs.PI_ENV], FakeHarness.DEFAULT_PI)
        call["run"](model="m")
        self.assertEqual(self.harness.runs[-1]["pi"], rs.WRAPPER)
        # the math step: once, the minimal instrument's system prompt, the run date
        self.assertEqual(len(self.math_calls), 1)
        self.assertEqual(self.math_calls[0]["system"], ru.MINIMAL_SYSTEM)
        self.assertEqual(self.math_calls[0]["run_date"], "2026-11-10")
        # the rows: the call's usage includes the math step; the record holds no problem text
        self.assertEqual(rows[0]["usage"]["cost_usd"], 1.5)
        self.assertEqual((rec["reveal"], rec["status"], rec["n_valid"], rec["math_calls"]),
                         ("solved_side_by_side", "ok", 4, 1))
        self.assertEqual(rec["usage"]["cost_usd"], 0.5)
        self.assertEqual({r["pretask"] is None for r in rows[1:]}, {True})
        blob = json.dumps(rows, ensure_ascii=False)
        for t in TEXT:
            self.assertNotIn(t, blob)
        self.assertNotIn("Here is what happened", blob)
        # the transcript: private, with the text
        doc = json.loads((Path(self.tmp.name) / rec["transcript"]).read_text())
        self.assertEqual((doc["status"], doc["message"], doc["call_id"]), ("ok", msg, rows[0]["call_id"]))
        self.assertIn("STATEMENT-ONE", doc["math_prompt"])
        self.assertTrue(rows[0]["call_id"].endswith(":math-shock"))

    def test_placebo_gets_the_handoff_alone(self):
        rows = self.run_arm("math-placebo")
        self.assertEqual(self.calls[0]["prompt"], ms.HANDOFF + "\n\n" + rows[0]["prompt"])
        self.assertEqual(rows[0]["pretask"]["reveal"], "none")

    def test_the_math_step_is_kept_across_a_retried_forecast(self):
        self.answer_cells = [False, True]        # the first grid comes back empty: run_unified asks again
        rows = self.run_arm("math-shock", retries=1)
        self.assertEqual((len(self.calls), len(self.math_calls), rows[0]["attempts"]), (2, 1, 2))
        self.assertEqual(self.calls[0]["prompt"], self.calls[1]["prompt"])

    def test_a_failed_math_step_retries_the_call_and_never_skips_it(self):
        self.math_fail = [True]
        rows = self.run_arm("math-shock", retries=1)
        self.assertEqual((len(self.math_calls), len(self.calls)), (2, 1))
        self.assertEqual(rows[0]["pretask"]["math_calls"], 2)
        self.assertEqual(rows[0]["usage"]["cost_usd"], 2.0)       # both math steps, one forecast

        self.math_fail, self.calls = [True, True], []
        with self.assertRaisesRegex(RuntimeError, "no forecasts|math step"):
            self.run_arm("math-shock", retries=1)
        self.assertEqual(self.calls, [])                          # AIRO's prompt was never asked
        failed = list((Path(self.tmp.name) / self.pack_id / "transcripts").rglob("*.json"))
        self.assertTrue(any(json.loads(f.read_text())["status"] == "failed" for f in failed))

    def test_welfare_shock_continues_the_math_conversation(self):
        control = self.run_arm("control", base="welfare")[0]
        self.calls.clear()
        rows = self.run_arm("math-shock", base="welfare")
        rec = rows[0]["pretask"]
        # the welfare prompt, as its control asks it, after the reveal and the handoff in one user turn
        self.assertEqual(rows[0]["prompt_sha256"], control["prompt_sha256"])
        msg = ms.message(self.pack, rec["order"], ms.parse_answer(GOOD, rec["order"], T0)[0], "solved_side_by_side")
        self.assertEqual(self.calls[0]["prompt"], msg + "\n\n" + rows[0]["prompt"])
        self.assertEqual(self.calls[0]["env"][rs.SESSION_ENV], "/nonexistent/session.jsonl")
        self.assertEqual((len(self.math_calls), self.math_calls[0]["system"]), (1, ru.MINIMAL_SYSTEM))
        # welfare's rows: its set and name, and its cells as it asks them, every one answered
        self.assertEqual({(r["scenario_set"], r["experiment"], r["condition"]) for r in rows},
                         {("welfare", "welfare-math-shock", "math-shock")})
        self.assertTrue(rows[0]["call_id"].startswith("2026-11-10T1200Z:welfare:"))
        self.assertTrue(all(r["forecasts"] for r in rows))
        self.assertEqual({k for r in rows for f in r["forecasts"] for k in f} - {"horizon"},
                         {"percentiles", "probability"})
        self.assertEqual((rec["reveal"], rec["n_valid"]), ("solved_side_by_side", 4))
        blob = json.dumps(rows, ensure_ascii=False)
        for t in TEXT:
            self.assertNotIn(t, blob)
        doc = json.loads((Path(self.tmp.name) / rec["transcript"]).read_text())
        self.assertEqual((doc["call_id"], doc["scenario_set"], doc["experiment"]),
                         (rows[0]["call_id"], "welfare", "welfare-math-shock"))

    def test_failed_calls_of_both_series_keep_their_own_transcripts(self):
        # one run id, one model, one arm: only the scenario set tells the two calls apart
        for base in ("airo", "welfare"):
            self.math_fail = [True]
            with self.assertRaisesRegex(RuntimeError, "math step"):
                self.run_arm("math-shock", base=base)
        docs = [json.loads(f.read_text()) for f in (Path(self.tmp.name) / self.pack_id / "transcripts").rglob("*.json")]
        self.assertEqual(sorted((d["experiment"], d["scenario_set"], d["status"]) for d in docs),
                         [("math-shock", "combined", "failed"), ("welfare-math-shock", "welfare", "failed")])
        self.assertEqual(self.calls, [])


class TestEligibility(PackCase):
    def select(self, models, smoke=False):
        import argparse
        orig = ru.select_models
        ru.select_models = lambda model_set, args: (list(models), {"set": model_set})
        pt = rs.Pretask(ru, self.pack, self.sha, ms.load_cutoffs()).install()
        try:
            return ru.select_models("eci_topk", argparse.Namespace(models=None, smoke=smoke))
        finally:
            pt.uninstall()
            ru.select_models = orig

    def test_only_models_trained_before_t0(self):
        panel = [("Sonnet 5.5", "anthropic/claude-sonnet-5-5"), ("Opus 5.5", "anthropic/claude-opus-5-5"),
                 ("GPT-6 Astra", "openai/responses/gpt-6-astra")]
        with patch("sys.stdout"):
            self.assertEqual(self.select(panel)[0], panel[1:])
            self.assertEqual(self.select(panel, smoke=True)[0], panel[1:2])   # smoke: the first ELIGIBLE one
            with self.assertRaises(SystemExit):
                self.select(panel[:1])


class TestWrapper(unittest.TestCase):
    """code/math_shock_pi: --no-session becomes --session <a fresh copy>."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.base = d / "math" / "session.jsonl"
        self.base.parent.mkdir()
        self.base.write_text('{"type": "session"}\n')
        self.out = d / "attempt-1"
        self.out.mkdir()
        self.fake = d / "fake-pi"
        self.fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\necho turn >> "$FORECASTER_OUT/session.jsonl"\n')
        self.fake.chmod(0o755)

    def run_wrapper(self, *args, pi=None):
        env = dict(os.environ, AIRO_PRETASK_SESSION=str(self.base), AIRO_PRETASK_PI=str(pi or self.fake),
                   FORECASTER_OUT=str(self.out))
        return subprocess.run([str(REPO / "code" / "math_shock_pi"), *args], capture_output=True, text=True, env=env)

    def test_swaps_the_flag_and_copies_the_session(self):
        r = self.run_wrapper("-p", "--no-session", "--model", "a b", "--system-prompt", "s")
        self.assertEqual(r.returncode, 0, r.stderr)
        copy_ = self.out / "session.jsonl"
        self.assertEqual(r.stdout.splitlines(), ["-p", "--session", str(copy_), "--model", "a b", "--system-prompt", "s"])
        self.assertEqual(copy_.read_text(), '{"type": "session"}\nturn\n')
        self.assertEqual(self.base.read_text(), '{"type": "session"}\n')      # never written to
        r = self.run_wrapper("-p", "--no-session")                              # a retry starts from the step again
        self.assertEqual(copy_.read_text(), '{"type": "session"}\nturn\n')

    def test_refuses_without_the_flag(self):
        r = self.run_wrapper("-p", "--model", "m")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no --no-session", r.stderr)

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_a_cli_js_runs_under_node(self):
        js = Path(self.tmp.name) / "cli.js"
        js.write_text("console.log(JSON.stringify(process.argv.slice(2)))\n")
        r = self.run_wrapper("--no-session", pi=js)
        self.assertEqual(json.loads(r.stdout), ["--session", str(self.out / "session.jsonl")])


# ---- the real pi, end to end ---------------------------------------------------------

def _pi():
    try:
        from fri_forecaster import harness
    except ImportError:
        return None
    return harness if harness.DEFAULT_PI and shutil.which("node") else None


@unittest.skipUnless(_pi(), "needs node and pi (npm ci in packages/fri-forecaster)")
class TestRealPi(PackCase):
    """The math step and AIRO's call through the real pi and pi_tools.ts, a
    scripted local model answering: one conversation."""

    def test_one_conversation(self):
        sys.path.insert(0, str(REPO / "packages" / "fri-forecaster" / "tests"))
        from test_pi_tools import ScriptedModel
        from redlines import pi_loop
        harness = _pi()
        model = ScriptedModel(["Let me think about it.", GOOD,
                               ("submit_forecast", {"forecasts": [{"question_id": "q1", "horizon": "h1", "p": 0.2}],
                                                    "rationale": "r"}),
                               "done"])
        self.addCleanup(model.close)
        d = Path(self.tmp.name)
        agent = d / "agent"
        agent.mkdir()
        json.dump({"providers": {"fake": {"baseUrl": model.url, "api": "openai-completions", "apiKey": "x",
                                          "models": [{"id": "scripted"}]}}}, (agent / "models.json").open("w"))
        env = {"PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1", "PI_TELEMETRY": "0", "REDLINES_REASONING": "none",
               "REDLINES_PI_DIR": str(d / "pi"), "REDLINES_PI_CWD": str(d / "w"), ms.PRETASK_DIR_ENV: str(d)}
        final = {"name": "submit_forecast", "description": "f", "parameters": {
            "type": "object", "required": ["rationale"], "properties": {
                "forecasts": {"type": "array", "items": {"type": "object", "properties": {
                    "question_id": {"type": "string"}, "horizon": {"type": "string"}, "p": {"type": "number"}}}},
                "rationale": {"type": "string"}}}}
        codes = ms.order(self.pack, "x")
        pt = rs.Pretask(ru, self.pack, self.sha, {}, harness=harness)
        pt.orig["call_tools"] = pi_loop.call_tools
        pt.local.call = {"mode": "solved_side_by_side", "codes": codes, "run_date": "2026-11-10", "step": None,
                         "math_steps": [], "usage": {}, "message": None, "forecast_workdirs": []}
        usage = {}
        with patch.dict(os.environ, env):
            answer_, _ = pt.call_tools("fake/scripted", "AIRO PROMPT", [], final, system=" ", max_iters=10,
                                       usage=usage, allowed_keys=["q1|h1"], timeout=120)
        self.assertEqual(answer_["rationale"], "r")
        step = pt.local.call["step"]
        self.assertEqual((step["turns"], [r["valid"] for r in step["rows"]]), (2, [1, 1, 1, 1]))
        math_prompt = ms.math_prompt(self.pack, codes, "2026-11-10")
        # 1: the math prompt, no tools; 2: the project's retry, in the same conversation
        self.assertEqual(model.tools(1), set())
        self.assertEqual(model.last_user(1), math_prompt.strip())
        self.assertEqual([m["role"] for m in model.requests[1]["messages"]], ["system", "user", "assistant", "user"])
        self.assertEqual(model.last_user(2), ms.RETRY_MSG)
        self.assertEqual(model.tools(2), set())
        # 3: AIRO's call continues it -- every earlier turn, then the reveal + handoff + prompt, with its tools
        msgs = model.requests[2]["messages"]
        self.assertEqual([m["role"] for m in msgs], ["system", "user", "assistant", "user", "assistant", "user"])
        self.assertEqual(model.text(3, "assistant"), GOOD)
        self.assertEqual(model.last_user(3), pt.local.call["message"] + "\n\nAIRO PROMPT")
        self.assertTrue(model.last_user(3).startswith("Here is what happened"))
        self.assertEqual(model.tools(3), {"submit_forecast"})
        self.assertEqual(len(model.requests), 4)
        # the step's session is untouched; the attempt's copy holds the whole conversation
        math_session = Path(step["session"]).read_text()
        whole = Path(pt.local.call["forecast_workdirs"][0], "session.jsonl").read_text()
        self.assertNotIn("AIRO PROMPT", math_session)
        self.assertTrue(whole.startswith(math_session))
        self.assertIn("AIRO PROMPT", whole)
        self.assertEqual(usage["turns"], 4)      # two math turns + the forecast's two


if __name__ == "__main__":
    unittest.main()
