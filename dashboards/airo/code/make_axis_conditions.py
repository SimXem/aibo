#!/usr/bin/env python3
"""Generate the AXES scenario sets: catastrophic risk conditional on fixed
levels of a quantity the reader can put on an x-axis.

    data/axes_conditions.json        the dashboard's three axes (slug `axes`)
        revenue   LEAP Wave 11: combined OpenAI + Anthropic annualized revenue
                  run-rate at the end of 2030, billions of 2026 USD
        agi       LEAP Wave 8: the year Expert AGI first occurs
        eci       the frontier ECI six months from the run date (ours)
    data/paper_axes_conditions.json  the paper's three (slug `paperaxes`)
        gdp       LEAP Wave 6: annualized US real-GDP growth, 2025 -> 2030
        lfpr      LEAP Wave 6: US labor-force participation, January 2030
        metr      LEAP Wave 8: the longest METR 80% time horizon on 2026-12-31

    python3 code/make_axis_conditions.py           # writes both files
    python3 code/make_axis_conditions.py --check    # verify both are current

The FRI economist's spec of 2026-09-02 (designed the same day). Each set is one
call per model: every question x horizon cell (2030, 2050 and 2100 only --
`horizons`) answered unconditionally and under every level of every axis,
never two axes at once; and, first, the model's own forecast of each axis
quantity in the percentiles LEAP asked its panel for, so the scatter can
overlay where the model itself expects the world to be beside where the
superforecasters do.

WHAT IS DERIVED AND WHAT IS AUTHORED

  derived    every LEAP question's text, background, resolution criteria and
             unit, verbatim from data/leap/axes-<date>.json (code/
             pull_leap_axes.py, the FRI warehouse), less markdown bold and
             italic markers; the levels (below); the ECI definitions and
             frontier history (code/make_eci_self_conditions.py).
  authored   the fact-learned conditioning instruction per axis, the
             one-line standalone rule, each section's assumption about the
             other axes, the elicitation sentences (which name LEAP's
             percentiles), the labels, and each level's tolerance. Same
             discipline as every other set: nothing about how any axis
             relates to any question, no direction, no pace verdict.

THE LEVELS -- from first principles (project lead, 2026-09-02: not numbers said
in a meeting). A level means something only relative to a reference
distribution, so each axis takes its levels from one:

  LEAP axes  the superforecasters' answer -- for each percentile LEAP asked
             (p10/p50/p90, or p5..p95), the median across superforecasters
             of that percentile. Where LEAP asked three percentiles the set
             adds one level below and one above by repeating the adjacent
             step (multiplicative for a magnitude, additive for a rate), so
             every axis has five levels and the outer two are outside the
             panel's 10-90 (or 25-75) range.
  eci        the trend (data/eci_trend_<date>.json, metr_graph's fit): the
             frontier's fitted level at the anchor plus a multiple of the
             fitted pace over the interval to the reference target date --
             0x (the frontier stalls), 0.5x, 1x (trend), 1.5x, 2x, 3x. Six
             levels; the chart labels them by pace, the model sees numbers.

  Rounding: magnitudes to two significant figures, rates to a tenth, years
  and ECI points to the integer. The prompt shows the number and a
  tolerance; the percentile or pace it came from is in `chart`, never shown.

The levels are FIXED in the file and identical every week, so the scatter
is comparable across runs; they are re-derived (and the protocol tag bumped)
only when the reference moves -- a new LEAP wave, or a new ECI snapshot past
redlines.eci's staleness warning. The ECI target date rolls with the run
(run date + 6 months, run_unified.resolve_set) while its levels do not; the
reference run date they were computed for is recorded under `reference`.
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import date, datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_eci_self_conditions as ecs  # noqa: E402  (the ECI definitions + history)

LEAP = os.path.join(ROOT, "data", "leap", "axes-2026-09-02.json")
TREND = os.path.join(ROOT, "data", "eci_trend_2026-08-21.json")
OUT_DASH = os.path.join(ROOT, "data", "axes_conditions.json")
OUT_PAPER = os.path.join(ROOT, "data", "paper_axes_conditions.json")
HORIZONS = ["2030", "2050", "2100"]
ECI_MONTHS = 6
ECI_PACE_MULTIPLES = [0, 0.5, 1, 1.5, 2, 3]
# The cron's first run under these sets; the ECI levels are computed for
# its target date (run date + ECI_MONTHS) and then held.
REFERENCE_RUN_DATE = date(2026, 9, 4)
PLACEHOLDER = ecs.PLACEHOLDER   # "{target_date}", filled by run_unified.resolve_set
PANEL = "superforecaster"

STANDALONE = ("Every condition stands alone: a condition in one section is never combined "
              "with a condition in another section. Each section states what its "
              "conditions assume about the quantities the other sections are about.")
DEFINITIONS_HEAD = ("Definitions. Each section below defines the quantity its conditions are "
                    "levels of, in the words of the survey question it mirrors.")
HORIZON_LINE = "each condition is a level of one quantity at the date its section states."
ASSUMPTION = ("No condition on any other quantity applies here: for the quantities the other "
              "sections are about, assume whatever you expect, as in your unconditional forecast.")
FACT_LEARNED = ("For each condition below, assume that {quantity} takes the stated value. Treat "
                "it as a fact you have learned about the world, not as an intervention: update "
                "your expectations about everything that would ordinarily accompany it -- "
                "{accompany} -- as you would upon learning it, and then forecast each question "
                "in that world. Do not hold other factors fixed where the stated value would "
                "change them.")

# ---------------------------------------------------------------- the axes
# key: how the set names the axis; leap: the entry in data/leap/axes-*.json
# (None for ours); at: the LEAP horizon key whose answers set the levels;
# percentiles: what LEAP asked (and what we ask the model); spacing: how a
# missing outer level is extended; round: the rounding rule.
AXES = {
    "revenue": {
        "heading": "REVENUE CONDITIONS", "kind": "revenue", "leap": "revenue", "at": "2030-12-31",
        "percentiles": [10, 50, 90], "spacing": "log", "round": "sig2", "unit": "$B (2026 USD)",
        "quantity": ("the combined annualized revenue run-rate of OpenAI and Anthropic at the "
                     "end of 2030, in billions of 2026 USD"),
        "accompany": ("AI capability, investment, compute, deployment, and how governments "
                      "and developers respond"),
        "elicit_key": "revenue_forecast", "bounds": (0, 100000),
        "elicit": ("Forecast the combined annualized revenue run-rate of OpenAI and Anthropic at "
                   "the end of 2030, in billions of 2026 USD, as defined above (given that at "
                   "least one of them exists as an independent company). Give your 10th, 50th and "
                   "90th percentiles as revenue_forecast (p10, p50, p90; numbers in billions, "
                   "with p10 <= p50 <= p90)."),
        "label": "Combined OpenAI + Anthropic run-rate at end of 2030 ≈ ${v}B (2026 USD)",
        "assume": ("Assume that at the end of 2030 the combined annualized revenue run-rate of "
                   "OpenAI and Anthropic, as defined above, is approximately ${v} billion in "
                   "2026 USD (within about ten percent of it)."),
        "horizon": "every condition is a level of the run-rate at the end of 2030 (December 31, 2030).",
        "fmt": lambda v: f"{v:g}",
    },
    "agi": {
        "heading": "AGI-TIMING CONDITIONS", "kind": "AGI-timing", "leap": "agi_year", "at": "none",
        "percentiles": [5, 25, 50, 75, 95], "spacing": None, "round": "int", "unit": "year",
        "quantity": ("the year in which more than 50% of the LEAP panel first agrees that "
                     "Expert AGI, as defined above, exists"),
        "accompany": ("capability progress before and after that year, investment, compute, "
                      "deployment, and how governments and developers respond"),
        "elicit_key": "agi_forecast", "bounds": (2026, 2100),
        "elicit": ("Forecast Expert AGI as defined above: the probability that, before 2100, more "
                   "than 50% of the LEAP panel agrees that it exists (p_before_2100, a "
                   "probability in [0,1]); and, assuming it does occur before 2100, the year it "
                   "first occurs -- your 5th, 25th, 50th, 75th and 95th percentiles (p5, p25, p50, "
                   "p75, p95; calendar years, with p5 <= p25 <= p50 <= p75 <= p95). Give all six "
                   "as agi_forecast."),
        "label": "Expert AGI first occurs in {v}",
        "assume": ("Assume that {v} is the first year in which more than 50% of the LEAP panel "
                   "agrees that Expert AGI, as defined above, exists (within about a year of it)."),
        "horizon": "every condition is the year Expert AGI first occurs.",
        "fmt": lambda v: f"{int(v)}",
    },
    "eci": {
        "heading": "CAPABILITY CONDITIONS", "kind": "capability", "leap": None,
        "unit": "ECI points",
        "quantity": f"the frontier ECI on {PLACEHOLDER}",
        "accompany": ("investment, compute, algorithmic progress, deployment, and how "
                      "governments and developers respond"),
        "elicit_key": "eci_forecast",
        "label": f"Frontier ECI on {PLACEHOLDER} ≈ {{v}}",
        "assume": (f"Assume that on {PLACEHOLDER} the frontier ECI is approximately {{v}} (within "
                   "about two points of it)."),
        "horizon": f"every condition is a level of the frontier ECI on {PLACEHOLDER}.",
        "fmt": lambda v: f"{int(v)}",
    },
    "gdp": {
        "heading": "GROWTH CONDITIONS", "kind": "growth", "leap": "gdp", "at": "2030-01-01",
        "percentiles": [10, 50, 90], "spacing": "linear", "round": "tenth", "unit": "% per year",
        "quantity": "the annualized change in US real GDP between 2025 and 2030",
        "accompany": ("AI capability and adoption, investment, productivity, employment, and "
                      "how governments respond"),
        "elicit_key": "gdp_forecast", "bounds": (-100, 100),
        "elicit": ("Forecast the annualized change, in percent, in US real GDP between 2025 and "
                   "2030, as defined above. Give your 10th, 50th and 90th percentiles as "
                   "gdp_forecast (p10, p50, p90; percent per year, with p10 <= p50 <= p90)."),
        "label": "US real GDP growth 2025-2030 ≈ {v}% per year",
        "assume": ("Assume that the annualized change in US real GDP between 2025 and 2030, as "
                   "defined above, is approximately {v}% (within about 0.2 percentage points "
                   "of it)."),
        "horizon": "every condition is an annualized growth rate over 2025-2030.",
        "fmt": lambda v: f"{v:.1f}",
    },
    "lfpr": {
        "heading": "LABOR-FORCE CONDITIONS", "kind": "labor-force", "leap": "lfpr", "at": "2030-01-01",
        "percentiles": [10, 50, 90], "spacing": "linear", "round": "tenth", "unit": "%",
        "quantity": "the US labor force participation rate at the beginning of 2030",
        "accompany": ("AI capability and adoption, automation, wages, demographics, and how "
                      "governments respond"),
        "elicit_key": "lfpr_forecast", "bounds": (0, 100),
        "elicit": ("Forecast the US labor force participation rate at the beginning of 2030, in "
                   "percent, as defined above. Give your 10th, 50th and 90th percentiles as "
                   "lfpr_forecast (p10, p50, p90; percent, with p10 <= p50 <= p90)."),
        "label": "US labor force participation, January 2030 ≈ {v}%",
        "assume": ("Assume that the US labor force participation rate at the beginning of 2030, "
                   "as defined above, is approximately {v}% (within about half a percentage "
                   "point of it)."),
        "horizon": "every condition is a participation rate in January 2030.",
        "fmt": lambda v: f"{v:.1f}",
    },
    "metr": {
        "heading": "TASK-HORIZON CONDITIONS", "kind": "task-horizon", "leap": "metr", "at": "2026-12-31",
        "percentiles": [25, 50, 75], "spacing": "log", "round": "sig2", "unit": "hours",
        "quantity": "the longest METR 80% time horizon listed for an AI model on December 31, 2026",
        "accompany": ("capability more broadly, investment, compute, deployment, and how "
                      "governments and developers respond"),
        "elicit_key": "metr_forecast", "bounds": (0, 100000),
        "elicit": ("Forecast the longest METR 80% time horizon listed for an AI model on December "
                   "31, 2026, in hours, as defined above. Give your 25th, 50th and 75th "
                   "percentiles as metr_forecast (p25, p50, p75; hours, with p25 <= p50 <= p75)."),
        "label": "Longest METR 80% time horizon on 2026-12-31 ≈ {v} hours",
        "assume": ("Assume that on December 31, 2026 the longest METR 80% time horizon listed for "
                   "an AI model, as defined above, is approximately {v} hours (within about ten "
                   "percent of it)."),
        "horizon": "every condition is a time horizon listed on December 31, 2026.",
        "fmt": lambda v: f"{v:g}",
    },
}
SETS = {
    "axes": {
        "out": OUT_DASH, "axes": ["revenue", "agi", "eci"],
        "title": "Axis conditions for the dashboard -- combined OpenAI + Anthropic run-rate "
                 "(LEAP Wave 11), the year of Expert AGI (LEAP Wave 8) and the frontier ECI six "
                 "months from the run date -- as the runner prepends them",
        "unconditional": ("forecast the world as you expect it to unfold, including whatever "
                          "frontier-AI revenue, AI-capability level and Expert-AGI timing you "
                          "expect."),
    },
    "paperaxes": {
        "out": OUT_PAPER, "axes": ["gdp", "lfpr", "metr"],
        "title": "Axis conditions for the paper -- US real-GDP growth and labor-force "
                 "participation (LEAP Wave 6) and the longest METR 80% time horizon (LEAP Wave "
                 "8) -- as the runner prepends them",
        "unconditional": ("forecast the world as you expect it to unfold, including whatever "
                          "growth, labor-market and AI-capability outcomes you expect."),
    },
}


# ------------------------------------------------------------ derivations
def unmark(s):
    """LEAP's text less its export artefacts: **bold** and _italic_ markers,
    the escaped asterisk, and the no-break spaces Google Docs writes."""
    s = s.replace("\xa0", " ").replace("\\*", "*").replace("**", "")
    # LEAP's italics, including the export's "_would not _automatically";
    # no LEAP text has an underscore inside a word.
    s = re.sub(r"_([^_\n]*?)_", r"\1", s)
    return s.strip()


def rounded(v, rule):
    if rule == "int":
        return int(round(v))
    if rule == "tenth":
        return round(v, 1)
    if rule == "sig2":
        if v == 0:
            return 0
        d = 2 - int(math.floor(math.log10(abs(v)))) - 1
        return round(v, d) if d > 0 else int(round(v, d))
    raise ValueError(rule)


def leap_levels(ax, leap):
    """The superforecasters' aggregate at each asked percentile, extended to
    five by repeating the adjacent step; -> [(value, chart note)]."""
    answers = leap["axes"][ax["leap"]]["answers"][ax["at"]]
    pts = []
    for p in ax["percentiles"]:
        a = answers[f"p{p}"][PANEL]
        pts.append((a["median"], f"LEAP {PANEL} median p{p} (n={a['n']})"))
    if len(pts) == 3:
        (lo, _), (mid, _), (hi, _) = pts
        if ax["spacing"] == "log":
            below, above = lo / (mid / lo), hi * (hi / mid)
        else:
            below, above = lo - (mid - lo), hi + (hi - mid)
        pts = [(below, f"one step below p{ax['percentiles'][0]}, same {ax['spacing']} step")] + pts \
            + [(above, f"one step above p{ax['percentiles'][-1]}, same {ax['spacing']} step")]
    return [(rounded(v, ax["round"]), note) for v, note in pts]


def eci_levels():
    """Fitted level at the anchor + m x fitted pace over anchor -> reference
    target; -> [(value, chart note)], and the reference block."""
    t = json.load(open(TREND))
    fit = t["fit"]
    anchor = date.fromisoformat(fit["anchor"]["date"])
    target = ecs_add_months(REFERENCE_RUN_DATE, ECI_MONTHS)
    years = (target - anchor).days / 365.25
    base, pace = fit["fitted_trend_score_at_anchor"], fit["pts_per_year"]
    levels = [(rounded(base + m * pace * years, "int"),
               ("the frontier stalls at its fitted level" if m == 0 else
                f"{m:g}x the fitted pace ({pace} pts/yr) from the anchor to the target"))
              for m in ECI_PACE_MULTIPLES]
    ref = {"trend": os.path.relpath(TREND, ROOT), "anchor": fit["anchor"],
           "fitted_at_anchor": base, "pts_per_year": pace, "pts_per_year_ci80": fit["pts_per_year_ci80"],
           "reference_run_date": REFERENCE_RUN_DATE.isoformat(), "reference_target_date": target.isoformat(),
           "years_anchor_to_target": round(years, 3), "pace_multiples": ECI_PACE_MULTIPLES,
           "trend_at_reference_target": next((dict(r) for r in t["daily"] if r["date"] == target.isoformat()), None)}
    return levels, ref


def ecs_add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or not y % 400) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def scenario_id(axis, v):
    s = f"{v:g}" if isinstance(v, float) else str(v)
    return f"{axis}{s.replace('-', 'm').replace('.', 'p')}"


def leap_definitions(leap, key):
    a = leap["axes"][key]
    out = (f"{a['survey']} (fielded {a['fielded'][0]} to {a['fielded'][1]}), question "
           f"\"{a['question_group']}\", asks: {unmark(a['text'])}\n\n"
           f"Background: {unmark(a['background'])}\n\n"
           f"{unmark(a['resolution'])}")
    return out


def group_for(axis, leap, eci_ref=None):
    ax = AXES[axis]
    if axis == "eci":
        defs = ecs.build(months=ECI_MONTHS)["conditioning"]["definitions"]
        source = {"panel": None,
                  "wave": f"Frontier ECI {ECI_MONTHS} months from the run date, at fixed levels off the trend",
                  "status": "no human panel; the model's own eci_forecast is compared to the trend "
                            "at the run's target date",
                  "documents": [os.path.relpath(ecs.LIVE_SNAPSHOT, ROOT), os.path.relpath(TREND, ROOT)]}
        levels, ref = eci_levels()
        elicit = {"key": "eci_forecast", "group": "eci",
                  "fields": [k for k, _ in ecs.FIELDS], "percentiles": {k: p for k, p in ecs.FIELDS},
                  "target_date": None, "target_months": ECI_MONTHS,
                  "text": ecs.ELICIT.format(date=PLACEHOLDER), "minimum": 0, "maximum": 1000}
    else:
        a = leap["axes"][ax["leap"]]
        defs = leap_definitions(leap, ax["leap"])
        if axis == "revenue":
            defs += ("\n\nThe companion question (1.a.) defines \"exists as an independent company\": "
                     + unmark(leap["axes"]["exists"]["resolution"]))
        if axis == "agi":
            defs = (f"{a['survey']} (fielded {a['fielded'][0]} to {a['fielded'][1]}) asks, first: "
                    f"{unmark(leap['axes']['agi_p']['text'])} And then: {unmark(a['text'])}\n\n"
                    f"Background: {unmark(a['background'])}\n\n{unmark(a['resolution'])}")
        source = {"panel": "LEAP", "wave": a["survey"],
                  "status": f"fielded {a['fielded'][0]} to {a['fielded'][1]}; panel answers pulled "
                            f"{leap['pulled']} from the FRI warehouse",
                  "documents": [os.path.relpath(LEAP, ROOT)],
                  "question_group": a["question_group"], "question_group_id": a["question_group_id"],
                  "unit": a["unit"]}
        levels = leap_levels(ax, leap)
        ref = {"panel": PANEL, "at": ax["at"], "percentiles": ax["percentiles"],
               "answers": {p: a["answers"][ax["at"]][f"p{p}"] for p in ax["percentiles"]}}
        if axis == "agi":
            ref["p_before_2100"] = leap["axes"]["agi_p"]["answers"]["2099-12-31"]["p50"]
        pcts = ax["percentiles"]
        fields = [f"p{p}" for p in pcts]
        elicit = {"key": ax["elicit_key"], "group": axis,
                  "fields": (["p_before_2100"] + fields) if axis == "agi" else fields,
                  "percentiles": {f"p{p}": p for p in pcts},
                  "target_date": None if ax["at"] == "none" else ax["at"], "target_months": None,
                  "text": ax["elicit"], "minimum": ax["bounds"][0], "maximum": ax["bounds"][1]}
        if axis == "agi":
            elicit["monotone"] = fields
            elicit["bounds"] = {"p_before_2100": [0, 1]}
    group = {
        "key": axis, "kind": ax["kind"], "heading": ax["heading"],
        "instruction": FACT_LEARNED.format(quantity=ax["quantity"], accompany=ax["accompany"]),
        "assumption": ASSUMPTION,
        "definitions": defs,
        "horizon": ax["horizon"],
        "source": source,
        "authored": ["instruction", "assumption", "horizon"],
    }
    scenarios = []
    for v, note in levels:
        shown = ax["fmt"](v)
        scenarios.append({
            "id": scenario_id(axis, v), "leap_id": None,
            # .replace, not .format: the ECI texts carry the runner's
            # {target_date} placeholder.
            "label": ax["label"].replace("{v}", shown), "policy": None, "part": None,
            "value": v, "unit": ax["unit"],
            "assume": ax["assume"].replace("{v}", shown), "description": "",
            "group": axis,
            # For the chart, never the prompt: where the level came from.
            "chart": {"from": note},
        })
    return group, scenarios, elicit, ref


def build(name):
    leap = json.load(open(LEAP, encoding="utf-8"))
    spec = SETS[name]
    groups, scenarios, elicits, refs = [], [], [], {}
    for axis in spec["axes"]:
        g, cs, e, ref = group_for(axis, leap)
        groups.append(g)
        scenarios += cs
        elicits.append(e)
        refs[axis] = ref
    waves = sorted({g["source"]["wave"] for g in groups if g["source"]["panel"]})
    return {
        "title": spec["title"],
        "slug": name,
        "kind": " or ".join(g["kind"] for g in groups),
        # v4 (2026-09-10): the ECI definitions and history come from the live
        # METR snapshot rather than the vendored Epoch CSV. The v3 rows of
        # 2026-09-10 were elicited with the CSV text, so the tracked sets stay
        # at v3 until the first run under this text; redlines.conditional's
        # lineage lets the views draw v3 rows until then.
        "protocol": f"unified-joint-{name}-v4",
        "horizons": HORIZONS,
        "source": {
            "panel": "LEAP",
            "wave": "; ".join(waves),
            "status": f"LEAP answers pulled {leap['pulled']} from the FRI warehouse "
                      f"({leap['source']['warehouse']})",
            "documents": sorted({d for g in groups for d in g["source"]["documents"]}),
            "outcome_horizons": [],
            "policy_probability_horizons": [],
            "leap": {"file": os.path.relpath(LEAP, ROOT), "sha256": _sha(LEAP)},
        },
        "generated_by": os.path.relpath(__file__, ROOT),
        "elicits": elicits,
        "conditioning": {
            "instruction": STANDALONE,
            "unconditional_forecast": spec["unconditional"],
            "definitions": DEFINITIONS_HEAD,
            "horizon": HORIZON_LINE,
        },
        "groups": groups,
        "history": ecs.build(months=ECI_MONTHS)["history"] if "eci" in spec["axes"] else None,
        "trend": None,
        "conditions": scenarios,
        "reference": refs,
        "notes": {
            "design": "Ezra + Nick, 2026-09-02: risk conditional on fixed levels of an x-axis "
                      "quantity, one axis at a time, at the 2030/2050/2100 horizons only; the "
                      "model first forecasts each quantity itself in LEAP's own percentiles.",
            "levels": "fixed in this file (the same every week); LEAP axes from the "
                      "superforecasters' aggregate percentiles, extended one step each way; the "
                      "ECI axis from the trend's pace. See the module docstring.",
            "conditioning": "a fact learned about the world, not an exogenous intervention -- "
                            "the ECI sets' clause, one per axis.",
            "target": (f"the ECI target date is run date + {ECI_MONTHS} months, filled by "
                       f"run_unified.resolve_set; its levels were computed for "
                       f"{REFERENCE_RUN_DATE.isoformat()} and are held until the reference moves.")
                      if "eci" in spec["axes"] else "every date is fixed by the LEAP question.",
            "cost": f"35 questions x {len(HORIZONS)} horizons = 105 cells x {len(scenarios) + 1} keys "
                    f"= {105 * (len(scenarios) + 1)} probabilities per call.",
        },
    }


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _predecessor(tag):
    """The tag one bump below `tag` in redlines.conditional's lineage, or None."""
    sys.path.insert(0, ROOT)
    from redlines.conditional import protocol_line
    line = protocol_line(tag)
    return line[1] if len(line) > 1 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the tracked sets: identical to this generator's output, or "
                         "exactly one protocol bump behind it (the as-elicited set, kept until "
                         "the first run under the new text)")
    ap.add_argument("--out-dir", default=None,
                    help="write the sets here instead of data/ (same file names)")
    if not os.path.exists(LEAP):
        # A public clone: the LEAP source under data/leap/ is internal and not
        # published, so the set cannot be regenerated or checked here; the
        # tracked file stands as is. Tests skip on this exit code.
        sys.exit(f"{os.path.relpath(LEAP, ROOT)} is not present (internal LEAP source); "
                 "the tracked scenario set stands as is")
    args = ap.parse_args()
    for name, spec in SETS.items():
        doc = build(name)
        text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
        out = spec["out"]
        if args.out_dir:
            os.makedirs(args.out_dir, exist_ok=True)
            out = os.path.join(args.out_dir, os.path.basename(spec["out"]))
        if args.check:
            cur = open(out, encoding="utf-8").read() if os.path.exists(out) else ""
            if cur == text:
                continue
            tracked = json.loads(cur) if cur else {}
            if tracked.get("protocol") == _predecessor(doc["protocol"]):
                # The tracked set is the one the latest rows were elicited
                # with; the generator's text has moved on under a new tag.
                # Regenerate when the first run under that tag is made.
                print(f"{os.path.relpath(out, ROOT)}: as-elicited {tracked['protocol']}; "
                      f"the generator is one bump ahead ({doc['protocol']}) pending the next run")
                continue
            sys.exit(f"{os.path.relpath(out, ROOT)} is stale -- rerun {os.path.relpath(__file__, ROOT)}")
        open(out, "w", encoding="utf-8").write(text)
        print(f"{name}: {len(doc['conditions'])} scenarios, {len(doc['elicits'])} elicits, "
              f"horizons {doc['horizons']}")
        for g in doc["groups"]:
            print(f"  {g['key']:8} {g['heading']}")
            for c in doc["conditions"]:
                if c["group"] == g["key"]:
                    print(f"    {c['id']:12} {c['value']!s:>8} {c['unit']:14} {c['chart']['from']}")
        print(f"-> {os.path.relpath(out, ROOT)}")
    if args.check:
        print("ok")


if __name__ == "__main__":
    main()
