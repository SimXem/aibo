"""The per-cell runner (code/run_cellwise.py) and its two experiments:
experiments/percell.toml, one call per severity x horizon x scenario (a
rung's deaths and damages questions together), and experiments/context.toml,
the 2x2 on what else a call holds, which code/analyze_context.py reads. No
model is called: call_tools is replaced throughout, and nothing reads keys."""
import argparse
import hashlib
import io
import json
import math
import os
import random
import re
import shutil
import sys
import tempfile
import statistics as st
import unittest
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "code"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_context as ac  # noqa: E402
import analyze_cellcheck as acc  # noqa: E402
import analyze_percell as apc  # noqa: E402
import run_cellwise as rc  # noqa: E402
import zipfile  # noqa: E402
from redlines import experiments, pi_loop, registry  # noqa: E402
from test_pi_loop import FakeRun  # noqa: E402

ru = rc.ru
TODAY = date(2026, 11, 16)
PERCELL = experiments.load("percell")
CONTEXT = experiments.load("context")
AIRO = experiments.load("airo")
POLICIES, GROUPS, BY_GROUP, HORIZONS, SPEC = rc.load_instrument(ru.COMBINED, TODAY)
QUESTIONS = [(g, q) for g in GROUPS for q in BY_GROUP[g["key"]]]
SCENARIO_IDS = [c["id"] for c in POLICIES["conditions"]]
CELLS = {k: (g, qs) for g, k, qs in rc.severities(GROUPS, BY_GROUP)}
ECI = {"eci_forecast": {"p10": 171.5, "p25": 173.25, "p50": 176.0, "p75": 179.0, "p90": 183.5}}
BANNED = ["must respect", "non-increasing", "must not increase", "may not exceed", "strictly harder",
          "contains every specific cause", "consistent with each other", "logical relation"]
LISTED = ("within 6 months / within 12 months / by the end of 2028 / by the end of 2030 / "
          "by the end of 2050 / by the end of 2100")


def _toml(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
    f.write(text)
    f.close()
    return f.name


def joint_prompt(variant="none"):
    p, _, _ = ru.build_prompt_joint(GROUPS, BY_GROUP, HORIZONS, SPEC, POLICIES["conditions"], POLICIES, TODAY)
    return ru.minimal_joint_prompt(p, variant)


def calls(bundle=(), context=None, **sel):
    return rc.plan_calls(GROUPS, BY_GROUP, HORIZONS, SCENARIO_IDS, argparse.Namespace(**sel), bundle, context)


def one_call(key, h, cid):
    (c,) = calls(cells=key, horizons=h, scenarios=cid)
    return c


def cell(key, h, cid, variant="none", elicited=ECI, **kw):
    return rc.call_prompt(one_call(key, h, cid), SPEC, POLICIES, TODAY, variant, elicited, **kw)


ARMS = {"alone": [], "horizons": ["horizons"], "severities": ["severities"], "both": ["horizons", "severities"]}
AI_CONTEXT = "ladder:ai:*,extinction:ai"


def arm(name):
    """An arm on the context experiment's selection; the severity arms with the AI context beside the target."""
    c = CONTEXT["conditions"]["none-alone"]
    return calls(ARMS[name], AI_CONTEXT, cells=",".join(c["cells"]),
                 horizons=",".join(c["horizons"]), scenarios=",".join(c["scenario_ids"]))


def answer_for(call, p=0.01):
    return {"forecasts": [{"question_id": q, "horizon": h, "probability": p} for q in call["qids"] for h in call["hs"]],
            "rationale": "r", "key_sources": ["u"]}


class TestTheExperiments(unittest.TestCase):
    def test_percell_mirrors_airos_pooled_prompts_unpublished_by_hand(self):
        self.assertEqual(list(PERCELL["conditions"]), AIRO["pooled"])
        for cid, c in PERCELL["conditions"].items():
            self.assertEqual((c["unit"], c["publish"], c["pooled"], c["instrument"], c["cadence"], c["scenarios"]),
                             ("cell", False, False, "minimal", "manual", "data/combined_conditions.json"), cid)
            self.assertEqual((c["bundle"], c["research"], c["eci_step"], c["cells"]), ([], True, True, None))
            self.assertEqual(c["variant"], AIRO["conditions"][cid]["variant"])
            self.assertNotEqual(c["sha256"], AIRO["conditions"][cid]["sha256"])   # the unit is hashed
        self.assertNotIn("percell", [name for name, *_ in experiments.due(date(2026, 11, 18))])   # a Wednesday

    def test_context_asks_the_headline_ai_question_alone_or_at_every_horizon_under_three_published_prompts(self):
        conds = CONTEXT["conditions"]
        arms = {"alone": ([], 6), "horizons": (["horizons"], 10)}
        self.assertEqual({k: (c["variant"], c["bundle"], c["repeats"]) for k, c in conds.items()},
                         {f"{v}-{a}": (v, b, r) for v in ("none", "independent", "recent") for a, (b, r) in arms.items()})
        for c in conds.values():
            # search on and no URL guard, as in the airo conditions of the same prompts
            self.assertEqual((c["unit"], c["publish"], c["research"], c["eci_step"], c["url_block_patterns"]),
                             ("cell", False, True, False, None))
            self.assertEqual((c["cells"], c["horizons"], c["scenario_ids"], c["context_cells"]),
                             (["catastrophe:ai"], ["6mo", "12mo", "2028", "2030", "2050", "2100"], ["unconditional"], None))
            self.assertEqual(c["variant"], AIRO["conditions"][c["variant"]]["variant"])
        self.assertEqual(len({c["sha256"] for c in conds.values()}), 6)
        per_prompt = sum(c["repeats"] * len(arm(k.split("-")[1])) for k, c in conds.items() if c["variant"] == "none")
        self.assertEqual(per_prompt, 6 * 6 + 10 * 1)

    def test_no_existing_hash_moves(self):
        base = dict(experiments.DEFAULTS, scenarios="data/combined_conditions.json")
        keep = {k: base[k] for k in experiments.DEFAULTS
                if k not in experiments.UNHASHED + ("unit", "news_cache", "max_turns", "prior_baseline",
                                                     "prior_self", "recent_news") + experiments.CELL_SETTINGS}
        self.assertEqual(experiments.condition_sha256(base),
                         hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest())
        for k, v in (("unit", "cell"), ("bundle", ["horizons"]), ("research", False), ("eci_step", False),
                     ("cells", ["x"]), ("context_cells", ["y"])):
            self.assertNotEqual(experiments.condition_sha256(base), experiments.condition_sha256(dict(base, **{k: v})), k)

    def test_what_cannot_run_as_written_is_refused(self):
        head = 'scenarios = "data/combined_conditions.json"\ninstrument = "minimal"\nunit = "cell"\n'
        for body, why in (('publish = true\n[conditions.a]\n', 'unit "cell" requires'),
                          ('cadence = ["wed"]\n[conditions.a]\n', 'unit "cell" requires'),
                          ('[conditions.a]\ninstrument = "standard"\n', 'unit "cell" requires'),
                          ('bundle = ["rungs"]\n[conditions.a]\n', "bundle"),
                          ('bundle = ["horizons", "horizons"]\n[conditions.a]\n', "bundle"),
                          ('research = "no"\n[conditions.a]\n', "research must be"),
                          ('cells = "catastrophe:ai"\n[conditions.a]\n', "cells must be"),
                          ('horizons = []\n[conditions.a]\n', "horizons must be")):
            with self.assertRaisesRegex(ValueError, why):
                experiments.load(_toml(head + body))
        with self.assertRaisesRegex(ValueError, "unit 'rows' is not one of"):
            experiments.load(_toml('scenarios = "data/combined_conditions.json"\nunit = "rows"\n[conditions.a]\n'))
        with self.assertRaisesRegex(ValueError, r"\['research'\] apply to unit \"cell\" conditions only"):
            experiments.load(_toml('scenarios = "data/combined_conditions.json"\nresearch = false\n[conditions.a]\n'))
        self.assertTrue(experiments.load(_toml(head + "[conditions.a]\n")))

    def test_each_runner_refuses_the_others_conditions(self):
        with patch.object(sys, "argv", ["run_unified.py", "--experiment", "percell", "--dry-run"]), \
                self.assertRaisesRegex(SystemExit, "run_cellwise"):
            ru.main()
        with self.assertRaisesRegex(SystemExit, "are joint"):
            rc.main(["--experiment", "airo", "--condition", "none", "--dry-run"])


class TestThePlan(unittest.TestCase):
    def test_a_rungs_deaths_and_damages_are_one_cell(self):
        self.assertEqual(len(CELLS), 4 * 9 + 5)
        self.assertEqual([q["id"] for q in CELLS["ladder:bio:1M"][1]], ["ladder:bio:1M:deaths", "ladder:bio:1M:damages"])
        self.assertEqual([q["id"] for q in CELLS["ladder:bio:extinction"][1]], ["ladder:bio:extinction:deaths"])
        self.assertEqual(sum(len(qs) for _, qs in CELLS.values()), 73)       # every question, once
        self.assertEqual(len(calls()), 41 * 6 * 14)                            # the full grid, by call

    def test_the_default_run_is_the_headline_question_at_every_horizon_and_scenario(self):
        plan = rc.default_plan(GROUPS, BY_GROUP, HORIZONS, SCENARIO_IDS)
        self.assertEqual(plan, calls(cells=rc.DEFAULT_CELLS, horizons=rc.DEFAULT_HORIZONS))
        self.assertEqual({tuple(c["qids"]) for c in plan}, {("catastrophe:ai",)})
        self.assertEqual(len(plan), 6 * 14)
        self.assertEqual({(c["hs"][0], c["cid"]) for c in plan}, {(h, s) for h in HORIZONS for s in SCENARIO_IDS + ["unconditional"]})
        self.assertTrue(all(len(c["hs"]) == 1 and set(c["qids"]) == c["targets"] for c in plan))
        self.assertEqual(plan[0]["key"], "catastrophe:ai|6mo|unconditional")
        earlier = calls(cells="ladder:ai:100,ladder:ai:1M,ladder:ai:1B,ladder:ai:extinction,disempowerment",
                        horizons="2030,2050,2100")                           # the docstring's earlier test run
        self.assertEqual(len(earlier), 5 * 3 * 14)

    def test_the_selection_filters_by_name_or_pattern_and_keeps_a_rung_whole(self):
        plan = calls(severities="1M,extinction", causes="cyber,crosscutting", horizons="6mo,2030",
                     scenarios="unconditional,eci_*")
        self.assertEqual(sorted({c["key"].split("|")[0] for c in plan}),
                         ["extinction:ai", "extinction:general", "ladder:cyber:1M", "ladder:cyber:extinction"])
        self.assertEqual(len(plan), 4 * 2 * 6)
        for k, v in (("horizons", "2040"), ("severities", "5%"), ("causes", "nuclear"), ("cells", "ladder:ai:100k:deaths")):
            with self.assertRaisesRegex(SystemExit, "matched none"):
                calls(**{k: v})

    def test_the_context_arms(self):
        alone, hz, sev, both = (arm(k) for k in ("alone", "horizons", "severities", "both"))
        self.assertEqual([(c["qids"], c["hs"]) for c in alone], [(["catastrophe:ai"], [h]) for h in HORIZONS])
        self.assertEqual([(c["qids"], c["hs"]) for c in hz], [(["catastrophe:ai"], HORIZONS)])
        context = [q["id"] for q in BY_GROUP["ai"]] + ["catastrophe:ai", "extinction:ai"]
        self.assertEqual(len(context), 19)
        self.assertEqual(context[:3], ["ladder:ai:100:deaths", "ladder:ai:1k:deaths", "ladder:ai:10k:deaths"])  # deaths leg first
        self.assertEqual([(c["qids"], c["hs"]) for c in sev], [(context, [h]) for h in HORIZONS])
        self.assertEqual([(c["qids"], c["hs"]) for c in both], [(context, HORIZONS)])
        for c in alone + hz + sev + both:
            self.assertEqual((c["targets"], c["cid"]), ({"catastrophe:ai"}, "unconditional"))
        self.assertEqual(both[0]["key"], "catastrophe:ai+context|6mo+12mo+2028+2030+2050+2100|unconditional")
        self.assertEqual([g["key"] for g, _ in both[0]["gqs"]], ["ai", "crosscutting"])

    def test_a_fixed_selection_is_not_the_command_lines_to_change(self):
        a = argparse.Namespace(cells=None, severities=None, causes=None, horizons="2030", scenarios=None)
        with self.assertRaisesRegex(SystemExit, "refusing --horizons: condition 'none-alone' fixes its own"):
            rc.selection(CONTEXT["conditions"]["none-alone"], a)
        a.horizons = None
        s = rc.selection(CONTEXT["conditions"]["none-alone"], a)
        self.assertEqual((s.cells, s.horizons, s.scenarios), ("catastrophe:ai", "6mo,12mo,2028,2030,2050,2100", "unconditional"))
        s = rc.selection(PERCELL["conditions"]["none"], a)
        self.assertEqual((s.cells, s.horizons, s.scenarios), (rc.DEFAULT_CELLS, rc.DEFAULT_HORIZONS, None))
        a.causes = "bio"
        self.assertIsNone(rc.selection(PERCELL["conditions"]["none"], a).cells)   # any choice replaces the default set


class TestThePrompts(unittest.TestCase):
    def test_one_severity_at_one_horizon_under_one_condition(self):
        p = cell("ladder:cyber:1k", "2030", "p4")
        self.assertEqual(re.findall(r"^--- (\S+?)(?: \(severity.*)? ---$", p, re.M),
                         ["ladder:cyber:1k:deaths", "ladder:cyber:1k:damages", "p4"])
        self.assertIn("causes 1,000 deaths (or equivalent morbidity) by the end of 2030?", p)
        self.assertIn("causes $2.2 billion in economic damages by the end of 2030?", p)
        self.assertTrue(p.startswith(f"Today is 2026-11-16.\n\n{rc.head(2, 1)}\n\n"))
        self.assertIn("Below are two questions. Answer each at the one horizon it names", p)
        for other in ("within 6 months", "within 12 months", "2028", "2050", "2100"):
            self.assertNotIn(other, p.split("===== CONDITION =====")[0], other)
        self.assertIn("Incident onset intervals (inclusive UTC calendar dates):\n  2030: 2026-11-16 through 2030-12-31\n", p)
        self.assertTrue(p.rstrip().endswith(rc.deliver(2)))
        self.assertIn("for each of the 2\nquestion x horizon cells under this condition, a short rationale, and the sources", p)
        self.assertFalse([b for b in BANNED if b in p.lower()])

    def test_what_it_keeps_is_the_joint_prompts_text(self):
        joint = joint_prompt()
        p = cell("ladder:cyber:1k", "2030", "p4")
        rules = p[p.index("===== APPLIES TO EVERY INCIDENT"):p.index("Incident onset intervals")]
        self.assertIn(rules, joint)
        group = p[p.index("===== AI-RELATED CYBER INCIDENT ====="):p.index("--- ladder:cyber:1k:deaths")]
        self.assertIn(group, joint)
        item = p[p.index("--- p4 ---"):p.rindex("\n=====\n")]
        self.assertIn(item, joint)
        self.assertIn(ru._definitions(POLICIES), p)
        for q in CELLS["ladder:cyber:1k"][1]:
            self.assertIn(q["text"], joint)
            self.assertIn(q["text"].replace(LISTED, "by the end of 2030"), p)

    def test_at_every_horizon_with_every_ai_severity_the_questions_read_as_in_the_joint_prompt(self):
        joint = joint_prompt()
        (call,) = arm("both")
        p = rc.call_prompt(call, SPEC, POLICIES, TODAY, "none", None, research=False, eci_step=False)
        self.assertTrue(p.startswith("Today is 2026-11-16.\n\nBelow are 19 questions. Answer each at each of the six horizons"))
        ai = p[p.index("===== AI-RELATED INCIDENT ====="):p.index("===== CROSS-CUTTING =====")]
        self.assertIn(ai, joint)                                              # the whole AI ladder, verbatim
        for qid in ("catastrophe:ai", "extinction:ai"):
            start = p.index(f"--- {qid} (")
            block = p[start:p.index("\n--- ", start + 1) if qid == "catastrophe:ai" else p.index("=====", start)]
            self.assertIn(block, joint)
        onset = p[p.index("===== APPLIES TO EVERY INCIDENT"):p.index("\n\n\n===== CONDITION")]
        self.assertIn(onset, joint)
        self.assertIn("Horizons: 6mo (within 6 months (by 2027-05-16)), 12mo", p)
        self.assertTrue(p.rstrip().endswith(rc.deliver(114, research=False)))
        self.assertNotIn("sources", p.split("===== CONDITION")[1].split("=====\n\n")[-1])
        self.assertNotIn("Asked in a separate call", p)
        alone = rc.call_prompt(arm("alone")[3], SPEC, POLICIES, TODAY, "none", None, research=False, eci_step=False)
        self.assertIn("deaths reaching at least 10% of the population alive at the start "
                      "of the measurement window) will occur by the end of 2030?", alone)
        self.assertNotIn("AI-RELATED INCIDENT", alone)

    def test_the_assumptions_lose_only_their_pointer_to_the_other_section(self):
        joint = joint_prompt()
        for cid, key in (("p1", "policy"), ("eci_p10", "capability")):
            clause, _ = rc.CROSS_REFERENCES[key]
            p = cell("ladder:ai:100", "2028", cid)
            self.assertIn(clause, joint)
            self.assertNotIn(clause, p)
            g = next(g for g in ru.set_groups(POLICIES) if g["key"] == key)
            self.assertIn(rc.own_assumption(g), p)
        with self.assertRaisesRegex(ValueError, "CROSS_REFERENCES"):
            rc.own_assumption({"key": "policy", "assumption": "reworded"})
        self.assertEqual([c for c in ["unconditional"] + SCENARIO_IDS if rc.reads_eci(c, POLICIES)], SCENARIO_IDS)

    def test_the_model_sees_its_own_eci_forecast_unless_the_condition_drops_the_step(self):
        p = cell("ladder:bio:1M", "6mo", "eci_p90")
        self.assertIn("Your answer, eci_forecast: p10 171.5, p25 173.25, p50 176, p75 179, p90 183.5", p)
        self.assertIn("Horizon: 6mo (within 6 months (by 2027-05-16)).", p)
        self.assertIn("p90 [from the ECI step]", cell("ladder:bio:1M", "6mo", "eci_p90", elicited=None))
        self.assertNotIn("eci_forecast", cell("disempowerment", "2050", "unconditional", eci_step=False))

    def test_the_variant_goes_before_delivery_in_calls_and_in_the_eci_step(self):
        v = ru.VARIANTS["two-step"]
        for p in (cell("disempowerment", "2050", "p5", "two-step"), rc.eci_prompt(POLICIES, TODAY, "two-step")):
            self.assertEqual(p.count(v), 1)
            self.assertLess(p.index(v), p.index("Call submit_forecast ONCE"))

    def test_every_cell_of_the_grid_builds(self):
        plan = calls()
        for c in plan[::53] + [c for c in plan if c["cid"] in ("p5", "unconditional")][:40]:
            rc.call_prompt(c, SPEC, POLICIES, TODAY, "none", ECI)


class TestTheCalls(unittest.TestCase):
    def setUp(self):
        self.ctx = {"run_id": "2026-11-16T1200Z", "today": TODAY, "spec": SPEC, "policies": POLICIES,
                    "groups": GROUPS, "experiment": "percell", "panels": {"eci_topk": {"set": "eci_topk"}},
                    "scenarios_sha256": "s"}
        self.seen = []

    def fake(self, *answers):
        answers = list(answers)

        def call(model, prompt, tools, final_tool, **kw):
            self.seen.append({"prompt": prompt, "tools": tools, "final": final_tool, **kw})
            kw["usage"].update(cost_usd=0.5, turns=3)
            return answers.pop(0), [{"tool": "web_search", "args": {}, "result": {"results": [1, 2]}}]
        return patch.object(rc, "call_tools", call)

    def test_the_eci_step_then_a_two_question_call(self):
        c = PERCELL["conditions"]["none"]
        with self.fake({**ECI, "rationale": "r", "key_sources": []}):
            eci = rc.run_eci(self.ctx, "Opus", "anthropic/x", c, 0)
        self.assertEqual((eci["step"], eci["elicited"]["eci_forecast"]), ("eci", ECI["eci_forecast"]))
        self.assertNotIn("forecasts", self.seen[0]["final"]["parameters"]["properties"])
        call = one_call("ladder:misalign:10k", "2050", "eci_p25")
        answer = {"forecasts": json.dumps([{"question_id": "ladder:misalign:10k:deaths", "horizon": "2050", "probability": "0.03"},
                                           {"question_id": "ladder:misalign:10k:damages", "horizon": "2050", "probability": 0.05}]),
                  "rationale": "r", "key_sources": ["u"]}
        with self.fake(answer):
            rows = rc.run_call(self.ctx, "Opus", "anthropic/x", c, call, eci["elicited"], 0)
        s = self.seen[-1]
        self.assertEqual((s["system"], s["min_evidence"], s["partial_tool"], s["debrief"], s["coverage"], s["warn_missing"]),
                         (ru.MINIMAL_SYSTEM, 0, None, None, None, True))
        self.assertEqual(s["allowed_keys"], ["ladder:misalign:10k:deaths|2050", "ladder:misalign:10k:damages|2050"])
        self.assertEqual([t["name"] for t in s["tools"]], ["web_search", "read_page"])
        self.assertEqual(s["final"]["parameters"]["properties"]["forecasts"]["items"]["properties"]["question_id"]["enum"],
                         call["qids"])
        self.assertIn("p25 173.25", s["prompt"])
        self.assertEqual([(r["question_id"], r["probability"], r["target"]) for r in rows],
                         [("ladder:misalign:10k:deaths", 0.03, True), ("ladder:misalign:10k:damages", 0.05, True)])
        for r in rows:
            self.assertEqual((r["call_id"], r["horizon"], r["scenario_id"], r["scenario"]["value"], r["replicate"]),
                             ("2026-11-16T1200Z:combined:cell:Opus:ladder:misalign:10k|2050|eci_p25", "2050", "eci_p25", 173.25, 1))
            self.assertEqual((r["protocol"], r["unit"], r["pooled"], r["bundle"], r["research"]),
                             ("percell:unified-joint-combined-v12", "cell", False, [], True))
            self.assertEqual(list(r["counting_window"]), ["2050"])
        self.assertEqual((rows[0]["prompt"], rows[0]["usage"]["cost_usd"]), (s["prompt"], 0.5))
        self.assertEqual((rows[1]["prompt"], rows[1]["usage"], rows[1]["evidence"]), (None, None, []))

    def test_a_call_missing_or_spoiling_a_probability_is_asked_again_then_fails(self):
        call = one_call("ladder:ai:1B", "2030", "unconditional")
        half = {"forecasts": [{"question_id": "ladder:ai:1B:deaths", "horizon": "2030", "probability": 0.001}], "rationale": "r"}
        with self.fake(half, answer_for(call, 0.002)), redirect_stdout(io.StringIO()):
            rows = rc.run_call(self.ctx, "M", "m", PERCELL["conditions"]["recent"], call, ECI, 1)
        self.assertEqual([(r["probability"], r["attempts"]) for r in rows], [(0.002, 2), (0.002, 2)])
        self.assertTrue(rows[0]["call_id"].endswith(":recent:ladder:ai:1B|2030|unconditional"))
        spoiled = {"forecasts": [{"question_id": "catastrophe:ai", "horizon": "2030", "probability": float("nan")}], "rationale": "r"}
        with self.fake(spoiled), self.assertRaisesRegex(RuntimeError, "no usable"):
            rc.run_call(self.ctx, "M", "m", PERCELL["conditions"]["none"], one_call("catastrophe:ai", "2030", "unconditional"), ECI, 0)
        for bad in (True, "x", None, -0.1, 1.5):
            self.assertIsNone(rc.clean_probability(bad), bad)

    def test_a_context_call(self):
        (call,) = arm("both")
        c = {**CONTEXT["conditions"]["recent-horizons"], "id": "recent-both", "bundle": ["horizons", "severities"]}
        self.ctx["experiment"] = "context"
        with self.fake(answer_for(call)):
            rows = rc.run_call(self.ctx, "M", "m", c, call, None, 0, rep=7)
        s = self.seen[-1]
        self.assertEqual([t["name"] for t in s["tools"]], ["web_search", "read_page"])   # search on, as published
        self.assertIn("key_sources", s["final"]["parameters"]["properties"])
        self.assertIn(ru.VARIANTS["recent"], s["prompt"])
        self.assertNotIn("Asked in a separate call", s["prompt"])
        self.assertEqual(len(rows), 19 * 6)
        self.assertEqual(sorted((r["question_id"], r["horizon"]) for r in rows if r["target"]),
                         sorted(("catastrophe:ai", h) for h in HORIZONS))
        self.assertEqual({(r["replicate"], r["run_call_id"], r["variant"]) for r in rows},
                         {(7, "2026-11-16T1200Z:combined:cell:M:recent-both#7", "recent")})
        self.assertEqual({tuple(r["bundle"]) for r in rows}, {("horizons", "severities")})
        with self.fake(answer_for(call)):                                    # and a condition without search
            rc.run_call(self.ctx, "M", "m", {**c, "research": False}, call, None, 0)
        self.assertEqual(self.seen[-1]["tools"], [])
        self.assertNotIn("key_sources", self.seen[-1]["final"]["parameters"]["properties"])
        self.assertNotIn("sources you used", self.seen[-1]["prompt"])

    def test_a_guard_travels_with_the_call_and_is_stamped(self):
        c = {**PERCELL["conditions"]["none"], "url_block_patterns": "example\\.org"}
        call = one_call("disempowerment", "2100", "p1")
        with self.fake(answer_for(call, 0.1)):
            (row,) = rc.run_call(self.ctx, "M", "m", c, call, ECI, 0)
        self.assertEqual(self.seen[-1]["env"], {ru.BLOCK_ENV: "example\\.org"})
        self.assertEqual(row["url_block_patterns"], "example\\.org")

    def test_pi_checks_the_calls_cells(self):
        call = one_call("ladder:ai:100", "2030", "unconditional")
        run = FakeRun(answer_for(call, 0.4))
        tool = rc.cell_tool(call["qids"], call["hs"])
        answer, _ = pi_loop.call_tools("anthropic/x", "P", [], tool, system=" ", run=run,
                                       allowed_keys=["ladder:ai:100:deaths|2030"], warn_missing=True)
        self.assertEqual(len(answer["forecasts"]), 2)
        self.assertEqual(run.kw["cell_schema"], tool["parameters"]["properties"]["forecasts"]["items"])
        self.assertEqual((run.kw["warn_missing_keys"], run.kw["cells_tool"]), (True, False))
        self.assertEqual(run.kw["tool_parameters"]["submit_forecast"], tool["parameters"])
        run = FakeRun({"eci_forecast": ECI["eci_forecast"], "rationale": "r"})
        pi_loop.call_tools("anthropic/x", "P", [], rc.eci_tool(POLICIES), system=" ", run=run)
        self.assertEqual((run.kw["cell_schema"], run.kw["warn_missing_keys"]), ({"type": "object"}, False))


class TestAssembly(unittest.TestCase):
    def rows(self):
        ctx = {"run_id": "R", "today": TODAY, "spec": SPEC, "policies": POLICIES, "groups": GROUPS,
               "experiment": "percell", "panels": {}, "scenarios_sha256": "s"}
        c = PERCELL["conditions"]["none"]
        out = []
        for key, h, cid, p in (("ladder:ai:100", "2030", "unconditional", 0.3), ("ladder:ai:100", "6mo", "unconditional", 0.01),
                               ("ladder:ai:100", "6mo", "eci_p50", 0.02), ("catastrophe:general", "2100", "unconditional", 0.05)):
            call = one_call(key, h, cid)
            with patch.object(rc, "call_tools", lambda *a, **k: (answer_for(call, p), [])):
                out += rc.run_call(ctx, "M", "m", c, call, ECI, 0)
        return out

    def test_calls_assemble_into_the_joint_rows(self):
        rows = rc.assemble(self.rows(), QUESTIONS)
        self.assertEqual([(r["question_id"], r["scenario"] and r["scenario"]["id"]) for r in rows],
                         [("ladder:ai:100:deaths", None), ("ladder:ai:100:damages", None), ("catastrophe:general", None),
                          ("ladder:ai:100:deaths", "eci_p50"), ("ladder:ai:100:damages", "eci_p50")])
        a = rows[0]
        self.assertEqual(a["forecasts"], [{"horizon": "6mo", "probability": 0.01}, {"horizon": "2030", "probability": 0.3}])
        self.assertEqual((a["batch_size"], rows[2]["batch_size"], a["replicate"]), (2, 1, 1))
        self.assertEqual({r["call_id"] for r in rows}, {"R:combined:cell:M"})
        self.assertIsNone(rows[2]["counting_window"])
        self.assertEqual(rows[3]["scenario"]["value"], 176.0)
        with tempfile.TemporaryDirectory() as d:
            cells = os.path.join(d, "percell-R-cells.jsonl")
            with open(cells, "w") as f:
                for r in self.rows():
                    f.write(json.dumps(r) + "\n")
            with redirect_stdout(io.StringIO()):
                rc.main(["--assemble", cells])
            self.assertEqual(len(open(os.path.join(d, "percell-R-instrument.jsonl")).readlines()), 5)
            self.assertEqual(len(open(os.path.join(d, "percell-R.jsonl")).readlines()), 3)


class TestTheRunner(unittest.TestCase):
    MODELS = ([("A", "a/x"), ("B", "b/y")], {"set": "eci_topk"})

    def run_main(self, *argv):
        stop = SystemExit("past the cap")
        with patch.object(ru, "select_models", lambda *a: self.MODELS), \
                patch.object(rc, "call_tools", side_effect=AssertionError("called")), \
                patch.object(ru, "eci_preflight", side_effect=stop), patch.object(ru, "load_keys", side_effect=stop), \
                redirect_stdout(io.StringIO()) as out:
            try:
                rc.main(list(argv))
            except SystemExit as e:
                return out.getvalue(), str(e)
        return out.getvalue(), None

    def test_the_default_run_of_one_condition_fits_the_default_cap(self):
        out, why = self.run_main("--condition", "none")
        self.assertIn("2 ECI step(s) + 168 cell call(s)", out)
        self.assertIn("84 call(s): 1 target question(s) x 6 horizon(s) x 14 condition(s)", out)
        self.assertEqual(why, "past the cap")                                 # went on to the preflight

    def test_more_than_that_is_refused_before_any_call(self):
        out, why = self.run_main()                                            # all five conditions
        self.assertIn("10 ECI step(s) + 840 cell call(s)", out)
        self.assertRegex(why, r"850 calls is more than --max-calls 170 \(by default one condition's default run for 2 model")
        out, why = self.run_main("--condition", "none", "--cells", "*", "--horizons", "*")
        self.assertIn("3444 call(s): 73 target question(s) x 6 horizon(s) x 14 condition(s)", out)
        self.assertRegex(why, "more than --max-calls 170")
        _, why = self.run_main("--condition", "none", "--max-calls", "30")
        self.assertRegex(why, r"170 calls is more than --max-calls 30\.")
        _, why = self.run_main("--max-calls", "850")                         # all five prompts, deliberately
        self.assertEqual(why, "past the cap")

    def test_the_context_experiment_plans_138_calls_a_model_and_no_eci_step(self):
        out, why = self.run_main("--experiment", "context")
        self.assertIn("0 ECI step(s) + 276 cell call(s)", out)
        self.assertRegex(why, "276 calls is more than --max-calls 170")       # more than the default run
        out, why = self.run_main("--experiment", "context", "--max-calls", "276")
        self.assertIn("recent-horizons x10 per model, variant recent, bundle horizons, research on: "
                      "1 call(s): 1 target question(s) x 6 horizon(s) x 1 condition(s)", out)
        self.assertIn("recent-alone x6 per model, variant recent, bundle none, research on: "
                      "6 call(s): 1 target question(s) x 6 horizon(s) x 1 condition(s)", out)
        self.assertEqual(why, "past the cap")                                 # stopped at the keys, before any call
        _, why = self.run_main("--experiment", "context", "--cells", "disempowerment")
        self.assertRegex(why, "refusing --cells: condition 'none-alone' fixes its own")
        out, _ = self.run_main("--experiment", "context", "--condition", "none-alone", "--condition", "none-horizons",
                               "--max-repeats", "1")
        self.assertIn("0 ECI step(s) + 14 cell call(s)", out)                # a pilot: (6 + 1) calls x 2 models

    def test_a_dry_run_calls_nothing(self):
        with patch.object(rc, "call_tools", side_effect=AssertionError("called")), \
                redirect_stdout(io.StringIO()) as out:
            rc.main(["--condition", "none", "--condition", "two-step", "--severities", "1k", "--causes", "bio",
                     "--horizons", "2030", "--dry-run", "--show", "2"])
            rc.main(["--experiment", "context", "--dry-run", "--show", "1"])
        text = out.getvalue()
        self.assertEqual(text.count("/ ECI step:"), 2)
        self.assertIn("/ ladder:bio:1k|2030|unconditional: 2 question(s) x 1 horizon(s)", text)
        self.assertIn("12 more call prompt(s) not shown", text)
        self.assertIn("/ catastrophe:ai|6mo+12mo+2028+2030+2050+2100|unconditional: 1 question(s) x 6 horizon(s)", text)


def synthetic_run(d, effect, arms, prompts=("none", "independent", "recent"), models=("A", "B"),
                  call_sd=0.05, noise=0.05, seed=4):
    """A cells log with known effects. `effect(model, prompt, bundle, horizon)` is
    an answer's log-odds before noise; a call's shift is shared by its answers."""
    rng = random.Random(seed)
    rows = []
    for m in models:
        for v in prompts:
            for bundle, repeats in arms:
                for rep in range(1, repeats + 1):
                    hz = "horizons" in bundle
                    shift = {h: rng.gauss(0, call_sd) for h in HORIZONS}
                    for h in HORIZONS:
                        call = f"R:{m}:{v}:{'+'.join(bundle) or 'alone'}#{rep}" + ("" if hz else f":{h}")
                        x = effect(m, v, bundle, h) + shift[HORIZONS[0] if hz else h] + rng.gauss(0, noise)
                        rows.append({"step": "cell", "target": True, "scenario_id": "unconditional", "label": m,
                                     "run_id": "R", "run_date": "2026-11-17", "replicate": rep, "bundle": list(bundle),
                                     "variant": v, "call_id": call, "question_id": "catastrophe:ai", "horizon": h,
                                     "probability": 1 / (1 + math.exp(-x))})
                        rows.append({**rows[-1], "target": False, "question_id": "extinction:ai"})   # context: ignored
    path = os.path.join(d, "context-R-cells.jsonl")
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


BASE = {h: -9 + i * 1.3 for i, h in enumerate(HORIZONS)}     # 6mo near 1e-4, 2100 near 0.07, as published


class TestTheRegression(unittest.TestCase):
    """The model on a synthetic run of the context experiment's design, with known coefficients."""
    B3 = 0.3
    G1 = {"6mo": -0.2, "12mo": -0.1, "2028": 0.0, "2030": 0.0, "2050": 0.1, "2100": 0.3}
    G3 = {"none": 0.0, "independent": 0.2, "recent": -0.1}

    def effect(self, m, v, bundle, h):
        other = "horizons" in bundle
        return (BASE[h] + {"none": 0, "independent": -0.3, "recent": 0.2}[v] + (0.5 if (v, h) == ("recent", "6mo") else 0)
                + {"A": 0, "B": 0.8}[m] + other * (self.B3 + self.G1[h] + self.G3[v]))

    def test_it_recovers_the_coefficients(self):
        arms = [(c["bundle"], c["repeats"]) for k, c in CONTEXT["conditions"].items() if k.startswith("none-")]
        with tempfile.TemporaryDirectory() as d:
            path = synthetic_run(d, self.effect, arms, call_sd=0.3, noise=0.3)
            obs, left_out = ac.load_obs([path])
            self.assertEqual((len(obs), left_out), (2 * 3 * (6 * 6 + 10 * 6), 0))
            reg = ac.regression(obs)
        self.assertEqual(reg["reference"], {"horizon": "2030", "prompt": "none", "model": "A", "day": "2026-11-17"})
        self.assertEqual((reg["n"], reg["clusters"]), (576, 2 * 3 * (6 * 6 + 10)))
        self.assertEqual(len(reg["coefficients"]), 1 + 5 + 2 + 1 + 5 + 10 + 2 + 1)
        b, se = reg["coefficients"]["model[B]"]
        self.assertLess(abs(b - 0.8), 4 * se)
        for h in HORIZONS:
            for v in ("none", "independent", "recent"):
                est, se = reg["effect_of_other_horizons"][h][v]
                self.assertLess(abs(est - (self.B3 + self.G1[h] + self.G3[v])), 4 * se, (h, v))
            est, se = reg["effect_of_other_horizons"][h]["all prompts"]
            self.assertLess(abs(est - (self.B3 + self.G1[h] + 0.1 / 3)), 4 * se, h)
        b, se = reg["coefficients"]["HOR[6mo] x PROMPT[recent]"]
        self.assertLess(abs(b - 0.5), 4 * se)

    def test_clustering_widens_the_horizons_arm_and_a_missing_arm_stops_it(self):
        arms = [([], 6), (["horizons"], 10)]
        with tempfile.TemporaryDirectory() as d:
            shared = ac.regression(ac.load_obs([synthetic_run(d, self.effect, arms, call_sd=0.6, noise=0.05)])[0])
            alone = ac.load_obs([synthetic_run(d, self.effect, [([], 6)])])[0]
        # with the noise all at the call, the horizons calls carry six answers but one draw
        self.assertGreater(shared["coefficients"]["OTHERHOR"][1], 0.15)
        self.assertIsNone(ac.regression(alone))


class TestTheAnalysis(unittest.TestCase):
    """The 2x2 on a synthetic run with known effects, the regression beside it."""
    TWO_BY_TWO = [([], 2), (["horizons"], 10), (["severities"], 2), (["horizons", "severities"], 10)]

    def write_run(self, d, h_eff, s_eff, inter=0.0, noise=0.05):
        def effect(m, v, bundle, h):
            hb, sb = "horizons" in bundle, "severities" in bundle
            return BASE[h] + h_eff * hb + s_eff * sb + inter * (hb and sb)
        return synthetic_run(d, effect, self.TWO_BY_TWO, noise=noise, call_sd=noise)

    def test_it_recovers_known_effects(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write_run(d, h_eff=0.4, s_eff=-0.2, inter=0.1)
            data, clipped, n = ac.load([path])
            self.assertEqual((clipped, n), (0, 2 * 6 * 3 * (2 + 10 + 2 + 10)))
            pool = ac.pooled({m: ac.effects(arms, ac.scopes(data)["all horizons"]) for m, arms in data.items()})
            for name, want in (("horizons", 0.4 + 0.05), ("severities", -0.2 + 0.05), ("interaction", 0.1)):
                est, se = pool[name]
                self.assertLess(abs(est - want), 4 * se + 0.02, name)
            by_h = ac.effects(data[("none", "A")], ac.scopes(data)["2030"])
            self.assertAlmostEqual(by_h["horizons"][0], 0.45, delta=0.2)
            with redirect_stdout(io.StringIO()) as out:
                ac.main([path, "--json", os.path.join(d, "effects.json")])
            text = out.getvalue()
            self.assertIn("== all horizons (6 target(s)) ==", text)
            self.assertIn("prompt recent", text)
            self.assertIn("over 6 prompt x model unit(s)", text)
            self.assertIn("== Regression: Y = log-odds of catastrophe:ai; 432 answers", text)   # the alone + horizons arms
            self.assertIn("== Effect of the other horizons in the call", text)
            report = json.load(open(os.path.join(d, "effects.json")))
            self.assertEqual((report["rows"], report["regression"]["n"]), (n, 432))

    def test_an_incomplete_arm_is_said_to_be(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write_run(d, 0, 0)
            rows = [json.loads(l) for l in open(path) if "severities" not in l]
            with open(path, "w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            data, _, _ = ac.load([path])
            self.assertIsNone(ac.effects(data[("none", "A")], ac.scopes(data)["all horizons"]))
            with redirect_stdout(io.StringIO()) as out:
                ac.main([path])
            self.assertNotIn("== all horizons", out.getvalue())               # no 2x2 without its severity arms
            self.assertIn("== Regression", out.getvalue())


SIDS = ["unconditional", "sq", "p1", "p2a", "p2b", "p3a", "p3b", "p4", "p5",
        "eci_p10", "eci_p25", "eci_p50", "eci_p75", "eci_p90"]


def joint_and_cells(d, common=0.3, by_h=None, cell=None, models=("A", "B", "C", "D"),
                    prompts=("none", "independent", "recent", "critical", "two-step"),
                    joint_days=("2026-11-13",), cell_day="2026-11-13", seed=7):
    """A joint instrument file and a cells log of catastrophe:ai with a known
    common shift, horizon part `by_h` and one cell's extra shift `cell`
    ((horizon, scenario, shift)); the joint call's draw is shared by its cells."""
    rng = random.Random(seed)
    by_h = by_h or {h: 0.0 for h in HORIZONS}
    level = {(h, s): BASE[h] + 0.1 * i for h in HORIZONS for i, s in enumerate(SIDS)}
    stamp = lambda s: None if s == "unconditional" else {"id": s, "group": "capability" if s.startswith("eci") else "policy"}  # noqa: E731
    joint, cells = [], []
    for m in models:
        for v in prompts:
            unit = rng.gauss(0, 0.15)                                 # the pair's own shift
            for day in joint_days:
                draw = rng.gauss(0, 0.38)                             # the joint call's
                for s in SIDS:
                    fc = []
                    for h in HORIZONS:
                        x = level[(h, s)] + common + by_h[h] + unit + draw + rng.gauss(0, 0.4)
                        if cell and (h, s) == cell[:2]:
                            x += cell[2]
                        fc.append({"horizon": h, "probability": 1 / (1 + math.exp(-x))})
                    joint.append({"question_id": "catastrophe:ai", "label": m, "condition": v, "variant": v,
                                  "scenario": stamp(s), "forecasts": fc, "call_id": f"{day}:joint:{m}:{v}",
                                  "run_date": day, "protocol": "unified-joint-combined-v12",
                                  "elicited": {"eci_forecast": {"p50": 190.0}}})
            for s in SIDS:
                for h in HORIZONS:
                    x = level[(h, s)] + rng.gauss(0, 0.55)
                    cells.append({"step": "cell", "unit": "cell", "target": True, "bundle": [], "label": m,
                                  "condition": v, "variant": v, "question_id": "catastrophe:ai", "horizon": h,
                                  "scenario_id": s, "scenario": stamp(s), "probability": 1 / (1 + math.exp(-x)),
                                  "call_id": f"C:{m}:{v}:{h}:{s}", "run_date": cell_day,
                                  "set_protocol": "unified-joint-combined-v12", "protocol": "percell:unified-joint-combined-v12",
                                  "elicited": {"eci_forecast": {"p50": 192.0}}})
        joint.append({**joint[-1], "condition": "ai-banned", "variant": "ai-banned"})      # no cell partner
    paths = []
    for name, rows in (("joint.jsonl", joint), ("percell-R-cells.jsonl", cells)):
        paths.append(os.path.join(d, name))
        with open(paths[-1], "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    return paths


class TestTheJointComparison(unittest.TestCase):
    BY_H = {"6mo": 0.4, "12mo": 0.2, "2028": 0.0, "2030": -0.1, "2050": -0.2, "2100": -0.3}

    def run_it(self, *extra, **kw):
        with tempfile.TemporaryDirectory() as d:
            paths = joint_and_cells(d, **kw)
            obs, _ = apc.load_obs(paths, "catastrophe:ai")
            obs, _ = apc.joint_days(obs, [x for x in extra if x[:2] == "20"])
            res = apc.decompose(obs)
            with redirect_stdout(io.StringIO()) as out:
                apc.main(paths + ["--json", os.path.join(d, "r.json"), *extra])
            self.assertEqual(json.load(open(os.path.join(d, "r.json")))["sizes"]["common_shift"],
                             res["sizes"]["common_shift"])
        return res, out.getvalue()

    def test_it_recovers_the_common_shift_the_horizon_part_and_the_odd_cell(self):
        res, text = self.run_it(by_h=self.BY_H, cell=("2030", "eci_p90", 1.5))
        self.assertEqual((len(res["units"]), len(res["cells"])), (20, 84))
        self.assertEqual(res["unpaired"]["joint only"], [(m, "ai-banned") for m in "ABCD"])
        e = res["common_shift"]
        self.assertLess(abs(e["est"] - (0.3 + 1.5 / 84)), 4 * e["se"])
        self.assertLess(e["p"], 0.05)          # 20 joint calls: the common shift is the hard part
        for h, want in self.BY_H.items():
            got = res["by_horizon"][h]["cell"]
            want += (1.5 / 14 - 1.5 / 84) if h == "2030" else -1.5 / 84
            self.assertLess(abs(got["est"] - want), 4 * got["se"], h)
        self.assertLess(res["horizon_test"]["p"], 0.001)
        self.assertEqual((res["horizon_test"]["df1"], res["scenario_test"]["df1"]), (5, 13))
        odd = max(res["per_cell"], key=lambda r: r["cell_shift"]["est"])
        self.assertEqual((odd["horizon"], odd["scenario"]), ("2030", "eci_p90"))
        self.assertLess(odd["shift"]["q"], 0.01)
        self.assertLess(odd["cell_shift"]["p"], 0.001)
        self.assertGreater(res["sizes"]["horizon_part_sd"], 0.15)
        self.assertAlmostEqual(res["eci_p50_gap"]["est"], 2.0)
        self.assertIn("20 replicate(s) (model x prompt)", text)
        self.assertIn("84 cell(s) in every replicate: 6 horizon(s) x 14 scenario(s)", text)
        self.assertIn("left out, joint only: A / ai-banned", text)
        self.assertNotIn("different days", text)
        self.assertRegex(text, r"2030    eci_p90 .* q=0\.\d+  \*")

    def test_no_shift_finds_none(self):
        res, _ = self.run_it(common=0.0, seed=11)
        self.assertGreater(res["common_shift"]["p"], 0.01)
        self.assertGreater(res["horizon_test"]["p"], 0.01)
        self.assertLess(sum(r["shift"]["q"] < 0.1 for r in res["per_cell"]), 3)

    def test_the_days_and_a_second_joint_day(self):
        days = dict(joint_days=("2026-11-13", "2026-11-18"), cell_day="2026-11-18")
        res, text = self.run_it(**days)                                 # by default: the cells' own day only
        self.assertIn("joint call(s) of 2026-11-18; cells of 2026-11-18\n", text)
        self.assertEqual(res["joint_day_sd"]["replicates"], 0)
        res, text = self.run_it("--joint-day", "2026-11-13", **days)    # another day, said so
        self.assertIn("joint call(s) of 2026-11-13; cells of 2026-11-18  -- different days", text)
        res, text = self.run_it("--joint-day", "2026-11-13", "--joint-day", "2026-11-18", **days)
        self.assertIn("joint call(s) of 2026-11-13, 2026-11-18; cells of 2026-11-18  -- different days", text)
        self.assertEqual(res["joint_day_sd"]["replicates"], 20)
        self.assertAlmostEqual(res["joint_day_sd"]["cells"], 0.4, delta=0.1)   # the within-call noise

    def test_too_few_replicates_say_so(self):
        res, text = self.run_it(models=("A",))
        self.assertEqual(len(res["units"]), 5)
        self.assertIn("all scenarios' cell parts 0: not testable: 5 replicate(s) for 13 dimension(s)", text)
        self.assertIn("p=", text.split("-- The common shift:")[1].splitlines()[0])

    def test_the_distributions(self):
        self.assertAlmostEqual(apc.t_p(2.0, 10), 0.0734, places=4)
        self.assertAlmostEqual(apc.f_p(4.1, 2, 10), 0.0501, places=4)
        self.assertAlmostEqual(apc.t_p(1.959964, 10 ** 6), 0.05, places=4)
        self.assertEqual(apc.bh([0.01, 0.04, 0.03, 0.2]), [0.04, 0.04 * 4 / 3, 0.04 * 4 / 3, 0.2])


# ---- the cellcheck experiment (experiments/cellcheck.toml) -------------------

CELLCHECK = experiments.load("cellcheck")
PROMPTS = ["none", "independent", "recent", "critical", "two-step"]
PAIR = (("Opus 5.5", "anthropic/claude-opus-5-5"), ("GPT-6.2 Astra", "openai/responses/gpt-6.2-astra"))


class TestTheCellcheckExperiment(unittest.TestCase):
    run_main = TestTheRunner.run_main
    MODELS = (list(PAIR), {"set": "cellcheck"})

    def test_it_asks_the_twenty_cells_of_the_design(self):
        got = {}
        for cid, c in CELLCHECK["conditions"].items():
            self.assertEqual((c["unit"], c["model_set"], c["repeats"], c["cells"], c["variant"] in (cid, "none")),
                             ("cell", "cellcheck", 5, ["catastrophe:ai"], True))
            plan = calls(**vars(rc.selection(c, argparse.Namespace(cells=None, severities=None, causes=None,
                                                                    horizons=None, scenarios=None))))
            self.assertTrue(all(k["qids"] == ["catastrophe:ai"] and len(k["hs"]) == 1 for k in plan))
            got[cid] = sorted((k["hs"][0], k["cid"]) for k in plan)
        self.assertEqual(sum(map(len, got.values())), 20)
        grid = {"none": ["unconditional", "p2a", "p1"], "independent": ["p1", "eci_p90", "eci_p25"],
                "recent": ["p2a", "eci_p25", "unconditional"], "critical": ["eci_p25", "p1", "eci_p90"],
                "two-step": ["eci_p90", "unconditional", "p2a"]}                      # 2030, 2050, 2100
        five = {"eci_p90", "p1", "unconditional", "p2a", "eci_p25"}
        for i, h in enumerate(("2030", "2050", "2100")):                 # the same five scenarios at each horizon
            self.assertEqual({row[i] for row in grid.values()}, five, h)
        for cid, row in grid.items():                                   # and no prompt tied to one of them
            self.assertEqual(len(set(row)), 3, cid)
            self.assertTrue({(h, sid) for h, sid in zip(("2030", "2050", "2100"), row)} <= set(got[cid]), cid)
        extra = sorted((cid, h, sid) for cid, cells in got.items() for h, sid in cells
                       if (h, sid) not in set(zip(("2030", "2050", "2100"), grid[cid])))
        self.assertEqual(extra, [("independent", "2050", "eci_p75"), ("independent", "6mo", "eci_p25"),
                                 ("none", "2030", "p3b"), ("recent", "6mo", "p4"), ("two-step", "2100", "eci_p75")])

    def test_every_cell_is_the_seeded_draw(self):
        """The file's twenty cells are what its header says the generator gives:
        five scenarios, dealt to the prompts afresh at each horizon until no
        prompt repeats one, then five extra cells, all from one seed."""
        rng = random.Random(20261117)
        scenarios = ["unconditional"] + SCENARIO_IDS
        five = rng.sample(scenarios, 5)
        while True:
            deal = {h: rng.sample(five, 5) for h in ("2030", "2050", "2100")}
            if all(len({deal[h][i] for h in deal}) == 3 for i in range(5)):
                break
        fixed = {(PROMPTS[i], h, deal[h][i]) for h in deal for i in range(5)}
        pool = [(p, h, s) for p in PROMPTS for h in HORIZONS for s in scenarios if (p, h, s) not in fixed]
        self.assertEqual(len(pool), 405)
        drawn = fixed | set(rng.sample(pool, 5))
        asked = {(cid, *p.split("|")) for cid, c in CELLCHECK["conditions"].items() for p in c["pairs"]}
        self.assertEqual(asked, drawn)

    def test_the_run_is_250_calls_and_needs_the_cap_raised(self):
        out, why = self.run_main("--experiment", "cellcheck")
        self.assertIn("50 ECI step(s) + 200 cell call(s)", out)
        self.assertRegex(why, r"250 calls is more than --max-calls 170")
        out, why = self.run_main("--experiment", "cellcheck", "--max-calls", "250")
        self.assertEqual(why, "past the cap")                                 # on to the keys: no call made
        _, why = self.run_main("--experiment", "cellcheck", "--horizons", "2030")
        self.assertRegex(why, "refusing --horizons: condition 'none' fixes its own")

    def test_the_model_set_is_opus_and_astra_outside_the_panel(self):
        self.assertEqual(registry.MODEL_SETS["cellcheck"](), list(PAIR))
        self.assertNotIn("GPT-6.2 Astra", [m["label"] for m in registry.MODELS])   # the panel table is untouched
        with redirect_stdout(io.StringIO()):
            models, stamp = ru.select_models("cellcheck", argparse.Namespace(models=None, smoke=False))
        self.assertEqual((models, stamp), (list(PAIR), {"set": "cellcheck"}))
        self.assertEqual(pi_loop.pi_model(PAIR[1][1]), "openai/gpt-6.2-astra")

    def test_pairs_and_model_set_are_checked(self):
        head = 'scenarios = "data/combined_conditions.json"\ninstrument = "minimal"\nunit = "cell"\n'
        for body, why in (('pairs = ["2030-sq"]\n[conditions.a]\n', "must each be"),
                          ('pairs = ["2030|sq", "2030|sq"]\n[conditions.a]\n', "names a cell twice"),
                          ('pairs = ["2030|sq"]\nhorizons = ["2030"]\n[conditions.a]\n', "pairs fixes"),
                          ('model_set = "mine"\n[conditions.a]\n', "model_set 'mine' is not one of")):
            with self.assertRaisesRegex(ValueError, why):
                experiments.load(_toml(head + body))
        c = experiments.load(_toml(head + 'pairs = ["2040|sq", "2030|nope"]\n[conditions.a]\n'))["conditions"]["a"]
        sel = rc.selection(c, argparse.Namespace(cells=None, severities=None, causes=None, horizons=None, scenarios=None))
        with self.assertRaisesRegex(SystemExit, r"pairs \['2040\|sq', '2030\|nope'\] name no selected cell"):
            calls(**vars(sel))
        base = dict(experiments.DEFAULTS, scenarios="data/combined_conditions.json")
        self.assertNotEqual(experiments.condition_sha256(base), experiments.condition_sha256(dict(base, pairs=["2030|sq"])))


def cellcheck_data(d, shift=0.0, seed=3, day="2026-11-18", astra_joint_id="openai/responses/gpt-6.2-astra"):
    """The download (a zip of joint logs, two days) and a cellcheck cells log
    with a known shift between the arms (log-odds, isolated minus unified)."""
    rng = random.Random(seed)
    level = {(h, s): BASE[h] + 0.1 * i for h in HORIZONS for i, s in enumerate(SIDS)}
    stamp = lambda s: None if s == "unconditional" else {"id": s, "group": "capability" if s.startswith("eci") else "policy"}  # noqa: E731
    ex = lambda y: 1 / (1 + math.exp(-y))  # noqa: E731
    days = {"2026-11-13": [], day: []}
    for label, mid in PAIR:
        jid = astra_joint_id if label == "GPT-6.2 Astra" else mid
        for jd, rows in days.items():
            for v in PROMPTS + ["ai-banned"]:
                draw = rng.gauss(0, 0.38)
                for s in SIDS:
                    rows.append({"question_id": "catastrophe:ai", "label": label, "model": jid, "condition": v,
                                 "variant": v, "scenario": stamp(s), "run_date": jd, "experiment": "airo",
                                 "call_id": f"{jd}T1200Z:combined:joint#1:{label}" + ("" if v == "none" else f":{v}"),
                                 "protocol": "unified-joint-combined-v12", "elicited": {"eci_forecast": {"p50": 190.0}},
                                 "forecasts": [{"horizon": h, "probability": ex(level[(h, s)] + draw + rng.gauss(0, 0.4))}
                                               for h in HORIZONS],
                                 **({"pooled": False} if v == "ai-banned" else {})})
                    rows.append({**rows[-1], "question_id": "extinction:ai"})
    cells = []
    for label, mid in PAIR:
        for cid, c in CELLCHECK["conditions"].items():
            for rep in range(1, 6):
                cells.append({"step": "eci", "label": label, "condition": cid, "replicate": rep,
                              "elicited": {"eci_forecast": {"p50": 192.0}}})
                for pair in c["pairs"]:
                    h, s = pair.split("|")
                    p = ex(level[(h, s)] + shift + rng.gauss(0, 0.5))
                    cells.append({"step": "cell", "unit": "cell", "target": True, "bundle": [], "label": label,
                                  "model": mid, "condition": cid, "variant": c["variant"], "replicate": rep,
                                  "question_id": "catastrophe:ai", "horizon": h, "scenario_id": s,
                                  "scenario": stamp(s), "probability": p, "forecasts": [{"horizon": h, "probability": p}],
                                  "call_id": f"R:cell:{label}:{cid}#{rep}:catastrophe:ai|{h}|{s}", "run_date": day,
                                  "set_protocol": "unified-joint-combined-v12",
                                  "elicited": {"eci_forecast": {"p50": 192.0}}})
    zp = os.path.join(d, "redlines-data.zip")
    with zipfile.ZipFile(zp, "w") as z:
        for jd, rows in days.items():
            z.writestr(f"raw/conditional_runs_combined/{jd}T1200Z.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
            z.writestr(f"raw/runs/{jd}T1200Z.jsonl",                       # the unconditional slice: not read
                       "".join(json.dumps(r) + "\n" for r in rows if r["scenario"] is None))
    cp = os.path.join(d, "cellcheck-R-cells.jsonl")
    with open(cp, "w") as f:
        for r in cells:
            f.write(json.dumps(r) + "\n")
    return zp, cp, cells, days


class TestTheCellcheckAnalysis(unittest.TestCase):
    def run_it(self, *extra, **kw):
        with tempfile.TemporaryDirectory() as d:
            zp, cp, cells, days = cellcheck_data(d, **kw)
            obs, _ = apc.load_obs([zp, cp], "catastrophe:ai")
            with redirect_stdout(io.StringIO()) as out:
                acc.main([zp, cp, "--sims", "400", "--json", os.path.join(d, "r.json"), *extra])
            res = json.load(open(os.path.join(d, "r.json")))
        return res, out.getvalue(), cells, days, obs

    def test_same_arms_pass_and_the_mae_is_as_computed(self):
        res, text, cells, days, obs = self.run_it(shift=0.0)
        self.assertEqual((res["joint_day"], res["cell_days"]), ("2026-11-18", ["2026-11-18"]))
        for label, _ in PAIR:
            m = res["models"][label]
            self.assertEqual((m["k"], m["df_iso"]), (20, 80))
            self.assertTrue(all(r["n"] == 5 and r["m"] == 1 for r in m["cells"]))   # one joint call: ai-banned, raw/runs out
            self.assertGreater(m["test"]["p"], 0.01)
            self.assertGreater(m["p_mae_p"], 0.01)
            self.assertAlmostEqual(m["rho"], 0.47, delta=0.3)                        # the joint calls' shared draw
            # the MAE by hand: the 5 repeats' mean probability against the joint call's
            joint = {(r["condition"], f["horizon"], (r["scenario"] or {}).get("id", "unconditional")): f["probability"]
                     for r in days["2026-11-18"] if r["label"] == label and r["question_id"] == "catastrophe:ai"
                     and r["condition"] != "ai-banned" for f in r["forecasts"]}
            iso = defaultdict(list)
            for r in cells:
                if r["step"] == "cell" and r["label"] == label:
                    iso[(r["condition"], r["horizon"], r["scenario_id"])].append(r["probability"])
            self.assertAlmostEqual(m["mae_p"], st.fmean(abs(st.fmean(v) - joint[k]) for k, v in iso.items()))
            self.assertAlmostEqual((m["eci_p50"]["cell"], m["eci_p50"]["joint"]) == (192.0, 190.0), True)
        self.assertIn("-- both models: 40 cells", text)
        self.assertNotIn("NOTE", text)
        self.assertGreater(res["together"]["test"]["p"], 0.01)

    def test_a_shift_is_found(self):
        res, text, *_ = self.run_it(shift=1.0)
        for label, _ in PAIR:
            m = res["models"][label]
            self.assertLess(m["test"]["p"], 0.01)       # 20 cells from 5 joint calls, each sharing its draw
            self.assertLess(m["p_mae_y"], 0.01)
            self.assertLess(abs(m["mean_d"] - 1.0), 4 * m["se_mean_d"])
        self.assertLess(res["together"]["p_mae_p"], 0.01)

    def test_another_joint_day_and_another_model_id_are_said(self):
        res, text, *_ = self.run_it("--joint-day", "2026-11-13", astra_joint_id="openai/responses/gpt-6.2-astra-2026-11-17")
        self.assertEqual(res["joint_day"], "2026-11-13")
        self.assertIn("NOTE the joint calls are of 2026-11-13, the isolated cells of 2026-11-18", text)
        self.assertIn("NOTE GPT-6.2 Astra: the isolated cells ran openai/responses/gpt-6.2-astra, the joint calls "
                      "openai/responses/gpt-6.2-astra-2026-11-17", text)

    def test_the_percell_report_says_this_is_not_a_grid(self):
        with tempfile.TemporaryDirectory() as d:
            zp, cp, *_ = cellcheck_data(d)
            with redirect_stdout(io.StringIO()) as out:
                apc.main([zp, cp])
        self.assertIn("use code/analyze_cellcheck.py", out.getvalue())

    def test_chi_square(self):
        self.assertAlmostEqual(apc.chi2_p(31.410433, 20), 0.05, places=5)
        self.assertAlmostEqual(apc.chi2_p(3.841459, 1), 0.05, places=5)
        self.assertAlmostEqual(apc.chi2_p(0.5, 3), 0.9189, places=4)


class TestCellcheckEndToEnd(unittest.TestCase):
    """The real runner on experiments/cellcheck.toml with a scripted model (no
    API, no keys), then the real analysis on its log beside a published zip:
    what each cell prompt holds, which cells are asked, and that every cell's
    isolated mean and published answer reach the report unchanged."""

    ECI = {"Opus 5.5": [172.0, 175.0, 178.0, 182.0, 186.0], "GPT-6.2 Astra": [171.0, 174.5, 177.5, 181.0, 185.5]}

    def test_the_run_and_its_analysis(self):
        items = {c["id"]: ru._scenario_items([c]).strip() for c in
                 rc.load_instrument(str(REPO / "data/combined_conditions.json"), date.today())[0]["conditions"]}
        rng, seen = random.Random(5), []

        def model(model_id, prompt, tools, final, **kw):
            label = "Opus 5.5" if "claude" in model_id else "GPT-6.2 Astra"
            if "forecasts" not in final["parameters"]["properties"]:
                return {"eci_forecast": dict(zip(("p10", "p25", "p50", "p75", "p90"), self.ECI[label])),
                        "rationale": "r", "key_sources": []}, []
            (key,) = kw["allowed_keys"]
            q, h = key.split("|")
            seen.append((label, h, [c for c, t in items.items() if t in prompt], prompt))
            return {"forecasts": [{"question_id": q, "horizon": h, "probability": 1 / (1 + math.exp(-(BASE[h] + rng.gauss(0, 0.5))))}],
                    "rationale": "r", "key_sources": []}, []

        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "data"))
            shutil.copy(REPO / "data/combined_conditions.json", os.path.join(d, "data"))
            with patch.object(rc, "ROOT", d), patch.object(rc, "call_tools", model), \
                    patch.object(ru, "load_keys", lambda: None), patch.object(ru, "eci_preflight", lambda p: None), \
                    patch.dict(os.environ, {"TAVILY_API_KEY": "test"}), redirect_stdout(io.StringIO()):
                rc.main(["--experiment", "cellcheck", "--max-calls", "250", "--workers", "4"])
            out = os.path.join(d, "results", "experiments")
            log = os.path.join(out, next(f for f in os.listdir(out) if f.endswith("-cells.jsonl")))
            rows = [json.loads(line) for line in open(log)]
            cells = [r for r in rows if r["step"] == "cell"]
            self.assertEqual((len(rows) - len(cells), len(cells)), (50, 200))
            want = {(cid, *p.split("|")) for cid, c in CELLCHECK["conditions"].items() for p in c["pairs"]}
            for label, _ in PAIR:
                got = defaultdict(list)
                for r in cells:
                    if r["label"] == label:
                        got[(r["condition"], r["horizon"], r["scenario_id"])].append(r["replicate"])
                self.assertEqual(set(got), want, label)
                self.assertTrue(all(sorted(v) == [1, 2, 3, 4, 5] for v in got.values()), label)
            for r in cells:                                         # what each cell prompt holds
                p, sid = r["prompt"], r["scenario_id"]
                self.assertEqual([c for c, t in items.items() if t in p], [] if sid == "unconditional" else [sid])
                self.assertIn(f"p50 {self.ECI[r['label']][2]:g}", p)              # its own ECI step's numbers
                v = experiments.VARIANTS[CELLCHECK["conditions"][r["condition"]]["variant"]]
                self.assertTrue(v is None or v in p)
                others = [experiments.VARIANTS[x] for x in PROMPTS[1:] if experiments.VARIANTS[x] != v]
                self.assertFalse(any(o in p for o in others))
                self.assertFalse(any(f"by the end of {y}" in p for y in ("2030", "2050", "2100") if y != r["horizon"]))
            joint = []
            for label, mid in PAIR:
                for v in PROMPTS:
                    for sid in ["unconditional"] + SCENARIO_IDS:
                        joint.append({"question_id": "catastrophe:ai", "label": label, "model": mid, "condition": v,
                                      "scenario": None if sid == "unconditional" else {"id": sid},
                                      "run_date": cells[0]["run_date"], "call_id": f"J:{label}:{v}",
                                      "forecasts": [{"horizon": h, "probability": 1 / (1 + math.exp(-(BASE[h] + rng.gauss(0, 0.5))))}
                                                    for h in HORIZONS]})
            zp = os.path.join(d, "redlines-data.zip")
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr("raw/conditional_runs_combined/x.jsonl", "".join(json.dumps(r) + "\n" for r in joint))
            res = acc.analyse(apc.load_obs([zp, log], "catastrophe:ai")[0], sims=20)
        for label, _ in PAIR:
            m = res["models"][label]
            self.assertEqual(m["k"], 20)
            for c in m["cells"]:
                mine = [r["probability"] for r in cells if (r["label"], r["condition"], r["horizon"], r["scenario_id"])
                        == (label, c["prompt"], c["horizon"], c["scenario"])]
                theirs = [f["probability"] for r in joint for f in r["forecasts"]
                          if (r["label"], r["condition"], (r["scenario"] or {}).get("id", "unconditional"), f["horizon"])
                          == (label, c["prompt"], c["scenario"], c["horizon"])]
                self.assertAlmostEqual(c["iso_mean_p"], st.fmean(mine))
                self.assertAlmostEqual(c["uni_p"], theirs[0])


if __name__ == "__main__":
    unittest.main()
