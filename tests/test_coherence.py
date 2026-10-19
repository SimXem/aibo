"""Guard the unified forecast protocol against a silent regression.

The protocol's whole claim is that asking every question in one call makes the
panels mutually consistent (docs/coherence-experiment.md). Nothing enforced that
claim: someone could point redlines/runlog.py back at the retired log, or break
the batching in code/run_unified.py, and every panel would still build and every
other test would still pass. The numbers would just quietly contradict each other
again, as they did for 5.9% of all checkable constraints before 2026-08-14.

Three kinds of guard here, because they fail for different reasons:

  * PROVENANCE — every forecast of a batched question must come from a
    unified-batch call. This catches a repointed run log or a half-merged legacy
    file immediately and exactly, with no thresholds to argue about.

  * PROMPT PURITY — code/run_unified.py must state no relation between the
    questions. See test_prompt_states_no_constraint.

  * RATES ARE REPORTED, NOT ASSERTED (changed 2026-08-18) — the violation rate is
    a RESULT of this project, not an invariant of its build.

Until 2026-08-18 this file failed the build when LADDER or CROSS exceeded 2.0%.
That was wrong twice over. The prompt was telling the model to satisfy those very
constraints, so the ceilings were policing a number the prompt had already fixed;
and treating a measured rate as a build invariant means the only way to keep the
suite green is to keep the prompt that manufactures it. Both are gone. The rates
print, and the only surviving ceiling is a SMOKE bound so wide that crossing it
means the run is broken rather than incoherent.

Expect the rates to rise, HORIZON most of all — it read 0.0% because the prompt
said "probabilities are non-decreasing across horizons" in every arm ever run.
A rise is the measurement starting to work.

What still fails the build: a repointed run log, a re-instructed prompt, an audit
that has stopped discriminating (test_audit_still_detects_incoherence), and a
constraint that checks nothing at all.

Run with:  python3 -m unittest tests.test_coherence -v   (from the repo root)
"""
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from redlines.coherence import (CONSTRAINTS, audit, load_spec, read,  # noqa: E402
                                totals)
from redlines.questions import all_questions, horizon_sort_key  # noqa: E402
from redlines.config import UNBATCHED  # noqa: E402
from redlines.instrument import instrument_rows  # noqa: E402
from redlines.runlog import KNOWN_PROTOCOLS, load_runlog  # noqa: E402
from redlines.conditional import COMBINED_PROTOCOL  # noqa: E402

LEGACY = REPO / "archive" / "legacy-forecasts" / "forecast_runs.jsonl"
LEGACY_RUNS = REPO / "archive" / "legacy-forecasts" / "runs"

# v1 stated the coherence constraints in the prompt; v2 (2026-08-18) does not.
# Both are legitimate batch provenance, so both satisfy the provenance guard —
# but they are NOT interchangeable evidence, which is why the rate report below
# prints the mix rather than pooling them silently.
PROTOCOLS = KNOWN_PROTOCOLS   # redlines.runlog: the one list of tags the log may carry
INSTRUCTED = {"unified-batch-v1"}


class TestProtocolRegistry(unittest.TestCase):
    """The published set's tag and the code's idea of it are one string."""

    def test_combined_set_carries_the_registered_protocol(self):
        import json
        spec = json.loads((REPO / "data" / "combined_conditions.json").read_text())
        self.assertEqual(spec["protocol"], COMBINED_PROTOCOL)
        self.assertIn(COMBINED_PROTOCOL, PROTOCOLS)

# The only surviving ceiling, and it is not a coherence standard. Half of all
# checkable pairs contradicting each other is not a model with poor coherence;
# it is a truncated grid, a mis-keyed question id, or an audit reading the wrong
# column. Anything below this prints and passes.
#
# For reference, the rates these constraints have actually produced:
#
#   constraint  per-question   unified batch, prompt stating the constraints
#   HORIZON        0.0%          0.0%   <- both arms were instructed; meaningless
#   LADDER         9.5%          0.0%
#   CROSS          4.5%          0.0%
#   BRACKET       22.2%          1.7%   <- rests on wording judgments
#   SUBSET         4.6%          0.0%
#
# The right-hand column is not a baseline to defend. It is the number this
# change exists to replace with an honest one.
SMOKE_CEILING = 50.0


class TestLiveLogCoherence(unittest.TestCase):
    """The run log the dashboard actually builds from."""

    @classmethod
    def setUpClass(cls):
        cls.rows = load_runlog()
        # The audit reads the CURRENT instrument's rows: its relations name
        # today's question ids, and an earlier instrument's answers must not
        # be scored against them (redlines.instrument).
        current = instrument_rows(cls.rows)
        cls.results = audit(read(rows=current))
        if not current:
            # No forecasts yet: a fresh checkout, or the window between
            # re-versioning the questions and the next run. There is nothing
            # to say about coherence, and saying it loudly would train people
            # to ignore this file.
            raise unittest.SkipTest("no forecasts under the current instrument yet")

    def test_every_batched_forecast_came_from_a_batch(self):
        """A batched question forecast outside a batch is a protocol regression.

        Questions in config.UNBATCHED are the documented exception — #2 nests
        under no rung of the bio ladder, so it is elicited on its own and cannot
        carry the batch tag.
        """
        stray = sorted({r["question_id"] for r in self.rows
                        if r.get("protocol") not in PROTOCOLS
                        and r["question_id"] not in UNBATCHED})
        self.assertEqual(
            stray, [],
            f"{len(stray)} question(s) in the live log were not elicited by any "
            f"of {PROTOCOLS}: {stray[:5]}. Either redlines/runlog.py::RUNLOG points "
            "somewhere it should not, or a legacy file was merged into the live "
            "series. See archive/legacy-forecasts/README.md.")

    def test_every_constraint_checks_something(self):
        """A constraint checking zero pairs is the failure mode that hides.

        A rate of 0.0% out of 0 pairs reads identically to perfect coherence in
        every report we publish. This is the assertion that used to ride along
        inside the ceiling test and is the half of it worth keeping: a question
        set swap that orphans a relation must fail loudly, not silently score
        full marks.
        """
        empty = [k for k in CONSTRAINTS if self.results[k]["n"] == 0]
        self.assertEqual(
            empty, [],
            f"{empty} checked no pairs at all. Either the question ids in "
            "redlines/coherence.py's relation maps no longer match the question "
            "set, or the audit is not seeing the run log. A constraint that "
            "checks nothing reports 0.0% and looks like success.")

    def test_rates_are_reported_and_not_absurd(self):
        """Print every rate; fail only if the run itself looks broken.

        The rates are this project's finding, so they are output, not a
        threshold to keep green. SMOKE_CEILING is not a coherence standard —
        see its comment.
        """
        lines = []
        for key in CONSTRAINTS:
            r = self.results[key]
            lines.append(f"    {key:<8} {r['bad']:>4}/{r['n']:<5} = {r['rate']:>5.1f}%")
        t = totals(self.results)
        lines.append(f"    {'TOTAL':<8} {t['bad']:>4}/{t['n']:<5} = {t['rate']:>5.1f}%")

        # Say which arm produced these numbers. A rate from v1 rows is a report
        # of our own prompt; only v2 rows measure anything. Pooling the two
        # without saying so is how a contaminated number gets published.
        mix = {}
        for r in self.rows:
            mix[r.get("protocol")] = mix.get(r.get("protocol"), 0) + 1
        dirty = sorted(p for p in mix if p in INSTRUCTED)
        header = ("post-hoc coherence"
                  if not dirty else
                  f"coherence — WARNING: {sum(mix[p] for p in dirty)} of "
                  f"{len(self.rows)} rows are {dirty}, elicited with the "
                  f"constraints stated in the prompt. These rates report that "
                  f"instruction back, not the models")
        print(f"\n  {header}:\n" + "\n".join(lines))

        over = [(k, self.results[k]["rate"]) for k in CONSTRAINTS
                if self.results[k]["rate"] > SMOKE_CEILING]
        self.assertEqual(
            over, [],
            f"{over} exceed the {SMOKE_CEILING}% smoke bound. At this rate the "
            "run is broken, not incoherent — check for a truncated grid, a "
            "mis-keyed question id, or an audit reading the wrong horizon. "
            f"First failures: {self.results[over[0][0]]['examples'][:3] if over else ''}")

    def test_prompt_states_no_constraint(self):
        """The runner must not tell the model how the questions relate.

        Coherence is measured after the fact (redlines/coherence.py). If the
        prompt states the relations, the measurement reports the instruction
        back to us and the dashboard's coherence claim means nothing. This
        guards the deletion made 2026-08-18; see code/run_unified.py's
        docstring for the evidence and for how far past the ladder experiment
        it goes.

        Matched against the prompt literals only, not the whole file — the
        module docstring quotes the removed block on purpose.
        """
        src = (REPO / "code" / "run_unified.py").read_text()
        literals = re.findall(r'^(?:PROMPT|SYSTEM|QUANTITY_NOTE)\s*=\s*'
                              r'(?:\(?\s*)?["\']{1,3}(.*?)["\']{1,3}\s*\)?$',
                              src, re.S | re.M)
        self.assertTrue(literals, "could not find the prompt literals to check")
        blob = " ".join(literals).lower()
        banned = ["must respect", "non-decreasing", "non-increasing",
                  "must not increase", "may not exceed", "strictly harder",
                  "contains every specific cause", "consistent with each other",
                  "logical relation"]
        found = [p for p in banned if p in blob]
        self.assertEqual(
            found, [],
            f"code/run_unified.py's prompt states {found}. Coherence must be "
            "measured, not instructed — a stated constraint makes every rate "
            "this suite prints a report of our own prompt.")


class TestGuardActuallyFires(unittest.TestCase):
    """A guard that cannot detect its target is worse than no guard."""

    def test_audit_still_detects_incoherence(self):
        """The audit must discriminate, now that no ceiling asserts it does.

        This used to audit the retired per-question log, whose numbers were
        known-bad (LADDER 9.5%, BRACKET 22.2%). That fixture died with the
        Auto-ARC swap: it is keyed on XPT question ids, so the current audit
        reads nothing from it and scores a serene 0.0% — which is exactly the
        failure this guard exists to catch, arriving as a false pass.

        So the fixture is synthetic now, and better for it: build a forecast
        grid that breaks each constraint on purpose and assert the audit says
        so. It depends on no run log, and it survives the next question swap.
        """
        spec = load_spec()
        lab = "TestModel"
        rungs = [r["short"] for r in spec["rungs"]]
        rel = spec["relations"]
        top, sub = rel["cross"]["container"], rel["cross"]["contained"][0]
        deaths, damages = rel["legs"]["contained"], rel["legs"]["container"]
        hs = sorted([h for h in spec["horizons"]],
                    key=lambda h: horizon_sort_key(h, spec))
        near, far = hs[0], hs[-1]

        P = {}
        # HORIZON: a cumulative probability that falls as the horizon extends.
        P[(f"ladder:{top}:{rungs[0]}:{deaths}", lab)] = {near: 40.0, far: 10.0}
        # LADDER: a harder threshold made more likely than an easier one.
        P[(f"ladder:{sub}:{rungs[0]}:{deaths}", lab)] = {far: 5.0}
        P[(f"ladder:{sub}:{rungs[1]}:{deaths}", lab)] = {far: 50.0}
        # CROSS: a contained cause above its container.
        P[(f"ladder:{top}:{rungs[1]}:{deaths}", lab)] = {far: 1.0}
        # LEG: a rung's deaths question above its damages question.
        P[(f"ladder:{top}:{rungs[0]}:{damages}", lab)] = {far: 1.0}
        # BRACKET and SUBSET: the narrower event above the broader one.
        b = rel["bracket"][0]
        P[(b["narrower"], lab)] = {far: 99.0}
        P[(f"ladder:{b['cause']}:{b['rung']}:{b['leg']}", lab)] = {far: 1.0}
        for pair in rel["subset"]:
            P[(pair["narrower"], lab)] = {far: 99.0}
            P.setdefault((pair["broader"], lab), {})[far] = 1.0

        results = audit(P, labels=[lab])
        for key in CONSTRAINTS:
            with self.subTest(constraint=key):
                self.assertGreater(
                    results[key]["bad"], 0,
                    f"{key} did not flag a forecast built to violate it. The "
                    "audit has stopped measuring; suspect redlines/coherence.py "
                    "or a relation whose question ids no longer resolve.")

    @unittest.skipUnless(LEGACY.exists(), "retired log not present")
    def test_legacy_log_fails_provenance(self):
        rows = load_runlog(LEGACY, LEGACY_RUNS)
        tagged = [r for r in rows if r.get("protocol") in PROTOCOLS]
        self.assertEqual(tagged, [], "retired rows must carry no batch tag")

class TestPanelsAgree(unittest.TestCase):
    """Every panel must report the SAME human baseline for the same question.

    They already share one source — data/starter_questions.json, read through
    redlines.questions.human_anchor — so this is not a check that the data is
    single-sourced. It is a check that each view asks the source the same
    QUESTION. On 2026-08-14 the timeline asked for one pinned year (gap_year)
    and labelled the answer a "fixed baseline", so its By-2050 panel drew the
    2100 superforecaster number: 9.09% where Graph 1 showed 3.85%. Same table,
    different query, and nothing failed.
    """

    @classmethod
    def setUpClass(cls):
        cls.g1 = json.loads((REPO / "results" / "graph1_data.json").read_text())
        cls.tl = json.loads((REPO / "results" / "timeline_data.json").read_text())

    def test_graph1_and_timeline_agree_on_human_baselines(self):
        """Where both panels draw a human number for the same (question,
        horizon, panel, group), it must be the SAME number. One source, so a
        disagreement means a view queried it differently — the 2026-08-14 bug,
        when the timeline's By-2050 panel drew the 2100 superforecaster value.

        Graph 1 carries humans as a list, one entry per (panel, group), each
        with a per-horizon `ps`; the timeline would carry the same shape. Both
        are flattened to (question, horizon, panel, group) -> median and
        compared where they overlap.
        """
        def flat(blob):
            out = {}
            for q in blob["questions"]:
                for hm in (q.get("human") or []):
                    for h, v in (hm.get("ps") or {}).items():
                        out[(q["id"], h, hm["panel"], hm["group"])] = v
            return out

        g, t = flat(self.g1), flat(self.tl)
        # The timeline's human render path is still removed (only Graph 1 was
        # turned on 2026-08-18), so it plots none and there is nothing to
        # cross-check. Skip rather than pass vacuously; restore humans to the
        # timeline and this test bites.
        if not t:
            self.skipTest("timeline plots no human series yet — only Graph 1 "
                          "was turned on 2026-08-18")
        shared = set(g) & set(t)
        self.assertTrue(shared, "both panels carry humans but overlap on no "
                                "(question, horizon, panel, group) — a blob "
                                "changed shape and this test went vacuous")
        bad = [f"{k}: graph1={g[k]} timeline={t[k]}"
               for k in sorted(shared) if abs(g[k] - t[k]) > 1e-9]
        self.assertEqual(bad, [], f"{len(bad)} panel disagreement(s): {bad[:5]}")

    def test_timeline_baselines_are_per_horizon(self):
        """A scalar here is the old bug's shape, not a value to compare."""
        for q in self.tl["questions"]:
            x = q.get("xpt")
            if not x:
                continue
            with self.subTest(question=q["id"]):
                self.assertIsInstance(x, dict)
                self.assertTrue(set(x) <= set(q["horizons"]),
                                f"{q['id']}: xpt keys {sorted(x)} are not horizons")

if __name__ == "__main__":
    unittest.main()
