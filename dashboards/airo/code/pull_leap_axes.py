#!/usr/bin/env python3
"""Vendor the LEAP questions our conditioning AXES mirror, with the panel's
answers, from FRI's data warehouse -> data/leap/axes-<date>.json.

The FRI economist's spec (2026-09-02): the dashboard conditions catastrophic
risk on three x-axis quantities -- the frontier ECI (ours), and two LEAP questions:
the combined OpenAI + Anthropic annualized revenue run-rate (Wave 11) and
the year of "Expert AGI" (Wave 8) -- and the paper adds three more LEAP
questions: US real-GDP growth and US labor-force participation (Wave 6) and
the longest METR 80% time horizon (Wave 8). Since 2026-09-03 it also
carries the one LEAP question that forecasts the ECI itself -- Wave 5's
"U.S. versus China Polarity", the top-performing American and Chinese
system's ECI at end-2026/2030/2040 (the FRI economist, 2026-09-02: the U.S.
vs. China question is where LEAP forecast the ECI of the top US and top
China models separately) -- so the ECI axis and the frontier chart have a human
forecast to draw beside the models'. The LEAP question is the single source
of truth for what each quantity IS; this file is the only place its wording
enters the repo, and the superforecaster answers it carries are what
code/make_axis_conditions.py sets the levels from and what the charts
overlay.

    ~/Projects/data-warehouse/.venv/bin/python code/pull_leap_axes.py   # needs ADC
                                                                       # (gcloud auth application-default login)

WHAT IS PULLED
  dim.dim_question_group   the question text, background and resolution
                           criteria, verbatim, with the unit (dim.dim_unit)
  dim.dim_question         one row per (horizon date, percentile) the panel
                           answered; scenario_id IS NULL only -- LEAP re-asks
                           some questions under AI-progress scenarios and
                           only the outright answer is comparable
  fact.fact_response       response_is_current and not
                           response_should_be_excluded; the current answer
                           of each panelist
  br.br_participant_group  the panel: superforecaster / expert / public
                           (and 'fri' staff, kept for the record, never used)

For each (question, horizon, percentile, panel) the file records n and the
distribution across panelists of that percentile: its median and its own
10/25/75/90th percentiles. "The superforecasters' median p50" is the number
the charts call the LEAP median; the spread of p50s across panelists is not
a forecast interval and is never drawn as one.
"""
import json
import os
import sys
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# The FRI data warehouse's BigQuery project, from the environment: it is
# internal infrastructure, not part of the public record.
PROJECT = os.environ.get("FRI_WAREHOUSE_PROJECT") or sys.exit(
    "FRI_WAREHOUSE_PROJECT is unset: the BigQuery project of the FRI data warehouse (internal)")

# (axis key, survey, question-group name, what the axis is, dimension). The
# group name is how the warehouse labels the question; the survey pins the
# wave. `dimension` is dim_question.question_dimension, for a group that asks
# the same question about several subjects (Wave 5's ECI question: the US
# system and the Chinese system are two sets of rows under one group); None
# for a group with one subject.
AXES = [
    ("revenue", "Wave 11: AI Industry Economics", "Frontier AI Company Revenue (2)",
     "combined OpenAI + Anthropic annualized revenue run-rate, billions of 2026 USD"),
    ("exists", "Wave 11: AI Industry Economics", "Frontier AI Company Revenue (1)",
     "companion: P(at least one of the two exists as an independent company) -- defines 'exists'"),
    ("agi_p", "Wave 8: Timelines", "Expert Artificial General Intelligence (AGI) (1)",
     "P(before 2100, >50% of the LEAP panel agrees Expert AGI exists)"),
    ("agi_year", "Wave 8: Timelines", "Expert Artificial General Intelligence (AGI) (2)",
     "the year Expert AGI first occurs, given it does before 2100"),
    ("gdp", "Wave 6: Economic Effects", "Change in Gross Domestic Product",
     "annualized change in US real GDP, percent"),
    ("lfpr", "Wave 6: Economic Effects", "Labor Force Participation Rate",
     "US labor force participation rate at the beginning of the year, percent"),
    ("metr", "Wave 8: Timelines", "80%, 8-Hour Task Horizon (1)",
     "longest METR 80% time horizon listed on 2026-12-31, hours"),
    ("metr_year", "Wave 8: Timelines", "80%, 8-Hour Task Horizon (2)",
     "the year an AI model first achieves 80% success on 8-hour tasks"),
    ("eci_us", "Wave 5: Security and Geopolitics", "U.S. versus China Polarity",
     "the top-performing American AI system's score on the Epoch Capabilities Index", "United States"),
    ("eci_cn", "Wave 5: Security and Geopolitics", "U.S. versus China Polarity",
     "the top-performing Chinese AI system's score on the Epoch Capabilities Index", "China"),
]
PANELS = ("superforecaster", "expert", "public", "fri")


def main():
    from google.cloud import bigquery
    c = bigquery.Client(project=PROJECT)

    def q(sql):
        return [dict(r) for r in c.query(sql).result()]

    out = {
        "what": "LEAP questions mirrored as conditioning axes, with the panel's answers",
        "pulled": date.today().isoformat(),
        "source": {
            "warehouse": f"BigQuery {PROJECT} (FRI data-warehouse, dbt dimensional model)",
            "tables": ["dim.dim_survey", "dim.dim_question_group", "dim.dim_question",
                       "dim.dim_unit", "fact.fact_response", "br.br_participant_group"],
            "filter": "response_is_current and not response_should_be_excluded; "
                      "dim_question.scenario_id is null (the outright question, not a scenario)",
            "aggregate": "per (question, horizon, percentile, panel): n, and across panelists "
                         "the median and the 10/25/75/90th percentiles of that answer",
        },
        "axes": {},
    }
    for key, survey, name, what, *dim in AXES:
        dim = dim[0] if dim else None
        g = q(f"""
            select s.survey_name, s.survey_start_date, s.survey_end_date, g.question_group_id,
                   g.question_group_number, g.question_group_text, g.question_group_background_info,
                   g.question_group_resolution_criteria, u.unit_name, u.unit_display_text,
                   u.unit_abbreviation, u.unit_min_value, u.unit_max_value
            from `{PROJECT}.dim.dim_question_group` g
            join `{PROJECT}.dim.dim_survey` s using (survey_id)
            left join `{PROJECT}.dim.dim_unit` u using (unit_id)
            where s.survey_name = '{survey}' and g.question_group_name = '{name}'""")
        if len(g) != 1:
            sys.exit(f"{key}: expected one question group for {survey!r} / {name!r}, got {len(g)}")
        g = g[0]
        gid = g["question_group_id"]
        dist = q(f"""
            with base as (
              select qq.question_id, cast(qq.question_horizon_date as string) hz, qq.question_percentile pct,
                     pg.participant_group_name panel, f.response_value v
              from `{PROJECT}.fact.fact_response` f
              join `{PROJECT}.dim.dim_question` qq on qq.question_id = f.question_id
              left join `{PROJECT}.br.br_participant_group` pg
                on pg.participant_id = f.participant_id and pg.project_id = 'leap'
              where qq.question_group_id = '{gid}' and qq.scenario_id is null
                {f"and qq.question_dimension = '{dim}'" if dim else ""}
                and f.response_is_current and not f.response_should_be_excluded
                and f.response_value is not null)
            select hz, pct, panel, count(*) n,
                   approx_quantiles(v, 100)[offset(50)] med,
                   approx_quantiles(v, 100)[offset(10)] q10, approx_quantiles(v, 100)[offset(25)] q25,
                   approx_quantiles(v, 100)[offset(75)] q75, approx_quantiles(v, 100)[offset(90)] q90
            from base group by hz, pct, panel order by hz, pct, panel""")
        answers = {}
        for r in dist:
            if r["panel"] not in PANELS:
                continue
            hz = r["hz"] or "none"
            pct = f"p{int(r['pct'])}"
            answers.setdefault(hz, {}).setdefault(pct, {})[r["panel"]] = {
                "n": r["n"], "median": r["med"],
                "q10": r["q10"], "q25": r["q25"], "q75": r["q75"], "q90": r["q90"]}
        out["axes"][key] = {
            "what": what,
            "survey": g["survey_name"],
            "fielded": [str(g["survey_start_date"]), str(g["survey_end_date"])],
            "question_group": name,
            "question_group_number": g["question_group_number"],
            "question_group_id": gid,
            "dimension": dim,
            "text": g["question_group_text"],
            "background": g["question_group_background_info"],
            "resolution": g["question_group_resolution_criteria"],
            "unit": {"name": g["unit_name"], "display": g["unit_display_text"],
                     "abbreviation": g["unit_abbreviation"],
                     "min": g["unit_min_value"], "max": g["unit_max_value"]},
            # {horizon date or "none": {p10/p50/...: {panel: {n, median, q10..q90}}}}
            "answers": answers,
        }
        print(f"  {key:10} {survey} / {name}: "
              + ", ".join(f"{hz}:{'/'.join(sorted(a))}" for hz, a in answers.items()))
    path = os.path.join(ROOT, "data", "leap", f"axes-{out['pulled']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"-> {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
