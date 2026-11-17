#!/usr/bin/env python3
"""The EEAI question set: FRI's "Economic Effects of AI" expert survey, as data.

    python3 eeai/make_questions.py            # write eeai/data/questions.json and history.csv
    python3 eeai/make_questions.py --check    # exit 1 if either would change

Reads the survey as its authors wrote it and writes what the panel is asked
(eeai/instrument.py renders it; nothing else reads the documents):

  eeai/data/source/survey.md          the survey (the AI scenarios, the question stems)
  eeai/data/source/supplementary.md   the supplementary materials (each question's
                                      definition and resolution source, the
                                      instructions on percentiles and conditionals)
  eeai/data/source/history.csv        the historical base-rate data the survey charts

The sources are FRI's internal documents and are not in the repository
(eeai/data/source/ is gitignored, like data/leap/); the two outputs are tracked,
and this script exits with a message when the sources are absent. Wording is
taken verbatim -- only the markdown is cleaned (escapes, images, links written
out, a lost superscript restored). What is NOT taken, by decision (2026-11-11):

  Part 2 (short-term forecasts) and Part 4 (policies)   their dates have passed
                                                        or are weeks away
  the "do not look up" knowledge quiz, the worldview    they measure the
  multiple-choice items, policy support, Part 5         respondent, not the world
  Change in Employment by Occupation                    its occupation subsets are
                                                        in a sheet outside the survey

What is ADDED (2026-11-11): each question is also asked at the beginning of
2027, 2028 and 2029, in the survey's 2030 wording with its years moved back
(`added` on the horizon), so forecasts start resolving before 2030.

Everything specific to this reading of the survey -- ids, units, which CSV
series is which question's history -- is the QUESTIONS table below.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "eeai" / "data" / "source"
OUT = ROOT / "eeai" / "data" / "questions.json"
HISTORY_OUT = ROOT / "eeai" / "data" / "history.csv"

# v2 (2026-11-11): the survey's questions, each also asked at the beginning of
# 2027, 2028 and 2029 (NEAR), so forecasts start resolving before 2030. The
# survey's own dates and wording are unchanged, so v1 rows continue under v2.
INSTRUMENT = "eeai-survey-v2"
CONTINUES = ["eeai-survey-v1"]
NEAR = (2027, 2028, 2029)

SCENARIOS = [("slow", "Slow Progress"), ("moderate", "Moderate Progress"), ("rapid", "Rapid Progress")]
INDICATORS = ["Summary", "Research", "Problem-solving", "Creativity", "Agency", "Robotics"]

# id, the survey's heading, the supplementary heading, the history series, the
# unit, sanity bounds for an answer, and how many decimals the page shows.
# `uncertainty` is the survey's tag: 10th and 90th percentiles are asked for
# the unconditional forecast and the rapid scenario. `fill` names what the
# stem's bracketed slot becomes when one survey question is three.
QUESTIONS = [
    dict(id="gdp", category="Economic Activity", survey="Change in Gross Domestic Product",
         short="Real GDP growth", history="gdp", unit="% per year", bounds=(-100, 1000), decimals=1),
    dict(id="labor_productivity", category="Economic Activity", survey="Change in Labor Productivity",
         short="Labor productivity growth", history="labor_productivity", unit="% per year", bounds=(-100, 1000), decimals=1),
    dict(id="tfp", category="Economic Activity", survey="Change in Total Factor Productivity",
         short="Total factor productivity growth", history="tfp", unit="% per year", bounds=(-100, 1000), decimals=1),
    dict(id="lfpr", category="Labor Markets", survey="Labor Force Participation Rate",
         short="Labor force participation", history="lfpr", unit="%", bounds=(0, 100), decimals=1),
    dict(id="unemployment", category="Labor Markets", survey="Unemployment Rate",
         short="Unemployment rate", history="unemployment", unit="%", bounds=(0, 100), decimals=1),
    dict(id="youth_unemployment", category="Labor Markets", survey="Youth Unemployment Rate",
         short="Youth unemployment rate (ages 20-24)", history="youth_unemployment", unit="%", bounds=(0, 100), decimals=1),
    dict(id="jobs_business_analytical", category="Labor Markets", survey="Share of Job Categories",
         supplementary="Share of Business and Analytical Jobs", fill="business and analytical",
         title="Share of Business and Analytical Jobs", short="Business and analytical jobs",
         history="whitecollar", unit="% of labor force", bounds=(0, 100), decimals=1),
    dict(id="jobs_skilled_trade_industrial", category="Labor Markets", survey="Share of Job Categories",
         supplementary="Share of Business and Analytical Jobs", fill="skilled trade and industrial",
         title="Share of Skilled Trade and Industrial Jobs", short="Skilled trade and industrial jobs",
         history="bluecollar", unit="% of labor force", bounds=(0, 100), decimals=1),
    dict(id="jobs_care_service", category="Labor Markets", survey="Share of Job Categories",
         supplementary="Share of Business and Analytical Jobs", fill="care and service",
         title="Share of Care and Service Jobs", short="Care and service jobs",
         history="pinkcollar", unit="% of labor force", bounds=(0, 100), decimals=1),
    dict(id="wealth_inequality", category="Economic Inequality", survey="Wealth Inequality",
         short="Wealth share of the top 10%", history="wealth_inequality", unit="%", bounds=(0, 100), decimals=1),
    dict(id="labor_share", category="Economic Inequality", survey="Labor Share",
         short="Labor share of output", history="labor_share", unit="%", bounds=(0, 100), decimals=1),
    dict(id="median_household_income", category="Income and Well-Being", survey="Median Household Income",
         short="Real median household income", history="median_household_income", unit="2023 US$",
         bounds=(0, 1e8), decimals=0),
    dict(id="life_satisfaction", category="Income and Well-Being", survey="Life Satisfaction",
         short="Life satisfaction (0-10 ladder)", history="life_satisfaction", unit="Cantril ladder, 0-10",
         bounds=(0, 10), decimals=2),
    dict(id="work_hours_assisted", category="AI Adoption", survey="Work Hours Assisted by Generative AI",
         short="Work hours assisted by generative AI", history="work_hours_assisted", unit="% of work hours",
         bounds=(0, 100), decimals=1),
    dict(id="ai_electricity", category="AI Adoption", survey="AI Electricity Consumption",
         short="AI share of electricity use", history="ai_electricity", unit="% of U.S. electricity",
         bounds=(0, 100), decimals=1),
]


def clean(text):
    """Markdown as exported from the survey document -> plain text, wording untouched."""
    text = re.sub(r"!\[\]\[image\d+\]", "", text)
    # The export flattened superscripts: "(GDP in 2030 / GDP in 2025)1/5", "(100% + 2.70%)2".
    text = re.sub(r"\\?\)1/5", ")^(1/5)", text)
    text = re.sub(r"%\)2(?=\s)", "%)^2", text)
    text = re.sub(r"\[([^\]\[]+)\]\((https?://[^)\s]+)\)", lambda m: f"{m.group(1)} ({m.group(2)})", text)
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!$=<>~|])", r"\1", text)
    text = re.sub(r"\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*", lambda m: m.group(1) or m.group(2), text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", text)
    text = re.sub(r"\[\^\d+\]", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"^ (?=\S)", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def section(text, heading, level, end=None):
    """The body under the first heading of `level` whose text is `heading`
    (anchors such as {#details} ignored), up to the next heading of that level
    or above, or of `end`'s if given."""
    pat = re.compile(rf"^{'#' * level} +{re.escape(heading)}(?: +\\?\[[^\n]*)?(?: *\{{#[^}}]*\}})? *$", re.M)
    m = pat.search(text)
    if not m:
        raise SystemExit(f"heading not found: {'#' * level} {heading}")
    rest = text[m.end():]
    stop = re.search(rf"^#{{1,{end or level}}} ", rest, re.M)
    return rest[:stop.start()] if stop else rest


def details_of(supp_part3, heading):
    body = section(supp_part3, heading, 2)
    return clean(section(body, "Details", 3))


def scenarios_of(survey):
    block = section(survey, "AI scenarios", 4)
    rows = [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in block.splitlines() if line.startswith("|")]
    by = {clean(r[0]): r[1:] for r in rows if clean(r[0]) in INDICATORS}
    missing = [i for i in INDICATORS if i not in by]
    if missing:
        raise SystemExit(f"scenario table rows not found: {missing}")
    preamble = clean(block[:block.index("| Indicator")])
    footnote = re.search(r"^\[\^1\]:\s*(.+?)(?=\n\s*\[https)", survey, re.S | re.M)
    scenarios = [{"id": sid, "label": label,
                  "indicators": [{"name": ind, "text": clean(by[ind][i])} for ind in INDICATORS]}
                 for i, (sid, label) in enumerate(SCENARIOS)]
    return preamble, scenarios, clean(footnote.group(1)) if footnote else None


def stem_of(block):
    """A question's block -> (preamble, stem, [(horizon id, its wording)])."""
    lines = [ln.rstrip() for ln in block.strip().splitlines()]
    bullets = [clean(ln.lstrip("- ").strip()) for ln in lines if ln.startswith("- **")]
    bold = [i for i, ln in enumerate(lines) if ln.startswith("**")]
    if not bold:
        raise SystemExit(f"no question stem in: {block[:80]!r}")
    preamble = clean("\n".join(lines[:bold[0]]))
    stem = clean(lines[bold[0]])
    horizons = []
    for b in bullets:
        year = re.findall(r"(20\d\d)\?", b)
        if not year:
            raise SystemExit(f"no year in horizon: {b!r}")
        horizons.append((year[-1], b))
    if not horizons:
        # The date is in the stem itself ("... at the beginning of 2030?"): split it off.
        m = re.search(r"\s((?:the beginning of )?(20\d\d)\?)$", stem)
        if not m:
            raise SystemExit(f"no year in stem: {stem!r}")
        stem, horizons = stem[:m.start()], [(m.group(2), m.group(1))]
    return preamble, stem, horizons


def near_horizons(horizons):
    """The survey's 2030 wording with its years moved back: the same question
    at the beginning of each NEAR year (a five-year window stays five years)."""
    text = dict(horizons).get("2030")
    if text is None:
        raise SystemExit(f"no 2030 horizon to derive the near dates from: {horizons!r}")
    return [(str(y), re.sub(r"\b20\d\d\b", lambda m: str(int(m.group(0)) + y - 2030), text)) for y in NEAR]


def build():
    if not (SOURCE / "survey.md").exists():
        raise SystemExit(f"the survey documents are not at {SOURCE.relative_to(ROOT)}/ (internal to FRI, "
                         "not in the repository); the tracked eeai/data/questions.json stands")
    survey = (SOURCE / "survey.md").read_text(encoding="utf-8")
    supp = (SOURCE / "supplementary.md").read_text(encoding="utf-8")
    part1, part3 = section(survey, "Part 1: AI Progress", 2), section(survey, "Part 3: Economic Outcomes Conditional on AI Progress", 2)
    supp3 = section(supp, "Economic Outcomes Conditional on AI Progress", 1)
    other = section(supp, "Other Survey Text", 1)

    preamble, scenarios, footnote = scenarios_of(survey)
    scen_q = clean(section(part1, "Probability of AI Scenarios", 3).split("####")[0])
    part1_questions = [
        {"id": "scenario_probabilities", "title": "Probability of AI Scenarios", "kind": "probabilities",
         "fields": [s for s, _ in SCENARIOS], "sum": 100, "text": scen_q,
         "details": clean(section(section(supp, "Probability of AI Scenarios", 2), "Details", 3))},
        {"id": "indicator_importance", "title": "Relative Importance of Indicators", "kind": "allocation",
         "fields": ["research", "problem_solving", "creativity", "agency", "robotics"], "sum": 100,
         "text": clean(section(part1, "Relative Importance of Indicators", 3))},
        {"id": "household_robot", "title": "Capability in Controlling Physical Systems", "kind": "probability",
         "text": clean(section(part1, "Capability in Controlling Physical Systems", 3))},
        {"id": "reliability", "title": "Reliability", "kind": "probability",
         "text": clean(section(part1, "Reliability", 3))},
    ]

    history = {}
    with open(SOURCE / "history.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        history.setdefault(r["target_variable_id"], []).append((r["date"], r["value"]))

    questions = []
    for q in QUESTIONS:
        heading = q["survey"]
        tags = re.search(rf"^#### +{re.escape(heading)} +\\\[([^\n]*?)\\\]", part3, re.M)
        if not tags:
            raise SystemExit(f"no tags on the survey's heading: {heading}")
        tags = [t.strip() for t in tags.group(1).split(";")]
        pre, stem, horizons = stem_of(section(part3, heading, 4))
        if q.get("fill"):
            slot = re.search(r"\[[^\]]*/[^\]]*\]", stem)
            stem = stem.replace(slot.group(0), q["fill"])
        if q["history"] not in history:
            raise SystemExit(f"no history series {q['history']!r} for {q['id']}")
        questions.append({
            "id": q["id"], "title": q.get("title") or heading, "short": q["short"], "category": q["category"],
            "unit": q["unit"], "bounds": list(q["bounds"]), "decimals": q["decimals"],
            "uncertainty": "uncertainty" in tags,
            "preamble": pre or None, "stem": stem,
            # `added`: a date FRI added; the survey asks 2030 and 2050 only.
            "horizons": [{"id": h, "text": text, "added": True} for h, text in near_horizons(horizons)]
                        + [{"id": h, "text": text, "added": False} for h, text in horizons],
            "details": details_of(supp3, q.get("supplementary") or heading),
            "history": q["history"],
        })

    conditional = clean(section(section(other, "Part 3: Economic Outcomes", 2), "Conditional Forecasting", 3))
    conditional, _, rationale = conditional.partition("\n—\n")
    percentiles = clean(section(section(other, "Part 2: Short-Term Forecasting", 2), "Percentiles", 3))
    percentiles = re.sub(r" ?In the illustration below, [^.]*\.(?:\d+\.)?", "", percentiles)
    percentiles = percentiles.replace("In this section, we ask", "We ask")
    percentiles = re.sub(r"\n+(?=Your \d0th percentile)", "\n\n", percentiles)
    doc = {
        "instrument": INSTRUMENT,
        "continues": CONTINUES,
        "source": "Economic Effects of AI: an Expert Survey (Forecasting Research Institute), "
                  "Part 1 (AI progress) and Part 3 (economic outcomes conditional on AI progress)",
        "scenarios": {"preamble": preamble, "footnote": footnote, "items": scenarios},
        "instructions": {"percentiles": percentiles.strip(), "conditional": conditional.strip(),
                         "rationale": re.sub(r"^Rationale question in each forecasting question:\s*", "", rationale.strip())},
        "part1": part1_questions,
        "questions": questions,
    }
    hist_rows = sorted(((q["history"], d, v) for q in questions for d, v in history[q["history"]]),
                       key=lambda r: ([x["history"] for x in questions].index(r[0]), r[1]))
    hist = "series,date,value\n" + "".join(f"{s},{d},{v}\n" for s, d, v in hist_rows)
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n", hist


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    text, hist = build()
    if "--check" in argv:
        stale = [p.name for p, want in ((OUT, text), (HISTORY_OUT, hist))
                 if not p.exists() or p.read_text(encoding="utf-8") != want]
        if stale:
            print(f"stale: {', '.join(stale)} (run eeai/make_questions.py)", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    HISTORY_OUT.write_text(hist, encoding="utf-8")
    doc = json.loads(text)
    print(f"{OUT.relative_to(ROOT)}: {len(doc['questions'])} questions, {len(doc['part1'])} Part 1 items, "
          f"{len(doc['scenarios']['items'])} scenarios; {HISTORY_OUT.relative_to(ROOT)}: {hist.count(chr(10)) - 1} points")
    return 0


if __name__ == "__main__":
    sys.exit(main())
