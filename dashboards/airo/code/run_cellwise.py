#!/usr/bin/env python3
"""THE PER-CELL VARIANT: forecasts asked a cell at a time (2026-11-16), and the
context experiment built on it (2026-11-17).

The published instrument (code/run_unified.py) asks every question x horizon
cell under every scenario in ONE call, so each probability is given beside
6,131 others. This runner asks them in smaller calls, chosen by the
condition (redlines.experiments, unit = "cell"):

  - by default, one call per severity x horizon x scenario: the model never
    sees another severity, another horizon or another scenario, and never
    sees its own answers to them. On the incident ladder a severity is a rung,
    and a rung from 100 to 1B has a deaths and a damages question; both are
    asked in the one call. That is experiments/percell.toml.
  - `bundle` puts some of that context back. "horizons": the call asks its
    questions at every selected horizon at once. "severities": the call asks
    every selected target cell together, with the condition's
    `context_cells` beside them. Each answer is recorded with `target`
    saying whether it was a target or there as context. The four
    combinations are the arms of experiments/context.toml, which
    code/analyze_context.py reads.
  - `research = false`: no web_search or read_page, so every arm reads the
    same evidence (the model's own); `eci_step = false`: no ECI step and no
    ECI answer in the prompt (for a run that asks only the unconditional).
  - `cells`, `horizons`, `scenario_ids`: a selection fixed in the experiment
    file, which the command line may not change; without them the command
    line chooses, with the defaults below. `pairs` ("2030|sq", ...) fixes
    exactly which horizon x scenario cells are asked, for a design that is
    not a full grid (experiments/cellcheck.toml).

docs/coherence-experiment.md ran the first such contrast in 2026-08 for rungs
only, and found one-question-per-call ladders 46% incoherent.

WHAT A CALL SEES. The joint minimal prompt with everything that belongs to
other calls taken out, and nothing reworded that it keeps:

  - the head, which says how many questions there are and at how many
    horizons, under one condition
  - the questions' blocks exactly as run_unified.build_prompt renders them
    when asked for those questions at those horizons: the resolution criteria
    (once under a heading its questions share, as in the joint prompt), the
    shared incident rules (when an incident question is asked) and the onset
    intervals of those horizons only. Each question's text names the call's
    horizons where the set's text lists all six ("... by the end of 2030?").
  - the CONDITION section: the set's definitions (the ECI scale and its
    history), the model's own ECI forecast from the ECI step (below), and the
    one condition, rendered as in the joint prompt -- its group's heading,
    instruction, assumption sentence, definitions and horizon, then its item.
    The assumption sentences lose the clause that points at the other
    group's section, which a call does not have (CROSS_REFERENCES).
  - the horizon line, the prompt variant (VARIANTS) where the joint minimal
    prompt puts it, and the delivery sentence: a probability for each
    question x horizon cell, given as `forecasts` entries with question_id
    and horizon (the joint call's own cell format, one condition), a short
    rationale, and the sources used when the call may search

THE ECI STEP. The capability conditions are levels of the model's own
forecast of the frontier ECI ("your 10th-percentile value from
eci_forecast"), and every policy condition holds the frontier at its 50th
percentile. In the joint call that forecast is Step 1 of the same call. Here
it is a call of its own, one per model per condition per repeat, before any
cell: the set's definitions, the Step 1 text, the variant, and
submit_forecast with eci_forecast. Every cell prompt of that model,
condition and repeat then quotes the five numbers. It is not a probability,
and it is the only earlier answer a call is shown.

THE DEFAULT RUN (DEFAULT_CELLS, DEFAULT_HORIZONS; a condition with no
selection of its own; since 2026-11-17): the headline question,
catastrophe:ai (an AI-related catastrophe killing at least 10% of the
population), at all six horizons under every condition: 6 x 14 = 84 calls
and the ECI step per model per condition -- each answer the joint call gives
for that question, asked on its own, which code/analyze_percell.py sets
beside the joint call's. --cells, --severities and --causes choose other
cells (any of them replaces the default set; together they intersect),
--horizons and --scenarios the rest; each takes comma-separated names or
fnmatch patterns, and '*' is all of them. The earlier test run (AI incidents
at 100, 1M and 1B deaths and extinction, and disempowerment, at 2030, 2050
and 2100: 210 calls) is --cells 'ladder:ai:100,ladder:ai:1M,ladder:ai:1B,
ladder:ai:extinction,disempowerment' --horizons 2030,2050,2100.

ROWS. Two shapes, both under results/experiments/ (a cell condition never
publishes; redlines.experiments refuses it):

  <experiment>-<run>-cells.jsonl   the calls, as each completes: the ECI step
      (`step: "eci"`) and one row per question x horizon a call answered
      (`step: "cell"`: question_id, horizon, scenario_id, probability,
      `target`, `replicate`, `bundle`, the call's rationale and sources;
      `call_questions` and `call_horizons` say what the call held, and the
      prompt, evidence and usage ride on its first row only). This is the
      record; --resume reads it back.
  <experiment>-<run>-instrument.jsonl and <experiment>-<run>.jsonl   the
      cells ASSEMBLED into run_unified's row schema -- one row per (model,
      condition, repeat, question, scenario) with `forecasts` over the
      horizons -- and its unconditional slice, so redlines.coherence and the
      conditional analyses read a cell arm as they read the joint one.

Every row carries `unit: "cell"` and the protocol "percell:<the set's
protocol>", which no view's protocol line names: these rows can never be
read as the published series.

COST. Each call with research does its own. The runner refuses to start more
calls than --max-calls, which by default is one condition's default run
across the selected models (85 calls a model).

    python code/run_cellwise.py --condition none --dry-run
    python code/run_cellwise.py --condition none             # the default run, one prompt
    python code/run_cellwise.py --models "Opus 5.5" --max-calls 425   # all five prompts
    python code/run_cellwise.py --experiment context --dry-run
    python code/run_cellwise.py --experiment context --condition none-alone --condition none-horizons \\
        --models "Opus 5.5" --max-repeats 1                  # a pilot: 7 calls, to price the rest
    python code/run_cellwise.py --experiment context --models "Opus 5.5" --max-calls 138   # the context experiment
    python code/run_cellwise.py --resume results/experiments/<run>-cells.jsonl ...
    python code/run_cellwise.py --assemble results/experiments/<run>-cells.jsonl
"""
import argparse
import concurrent.futures as cf
import fnmatch
import hashlib
import json
import math
import os
import sys
import threading
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "code"))

import run_unified as ru  # noqa: E402
from redlines import experiments  # noqa: E402
from redlines.pi_loop import call_tools  # noqa: E402

UNIT = "cell"
UNCONDITIONAL = ru.UNCONDITIONAL_KEY
# The test run (THE DEFAULT RUN above): cells by key, and horizons.
DEFAULT_CELLS = "catastrophe:ai"
DEFAULT_HORIZONS = "*"
# How many call prompts a dry run prints in full (the plan is always printed).
DEFAULT_SHOW = 6
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}

ECI_DELIVER = ("Call submit_forecast ONCE, with your {keys}, a short rationale, and the\n"
               "sources you used.")
ECI_ASKED = "Asked in a separate call -- {text}\nYour answer, {key}: {values}"


def protocol(policies):
    """The cell rows' protocol: the set's own, marked per-cell, so no view
    that reads the set's protocol line ever reads these rows."""
    return f"percell:{ru.set_protocol(policies)}"


def _n(k):
    return WORDS.get(k, str(k))


def head(nq, nh):
    """What the call holds, in words."""
    if nh == 1:
        if nq == 1:
            return ("Below is one question. Answer it at the one horizon it names, under the one\n"
                    "condition in the CONDITION section that follows the question.")
        return (f"Below are {_n(nq)} questions. Answer each at the one horizon it names, under the one\n"
                "condition in the CONDITION section that follows the questions.")
    if nq == 1:
        return (f"Below is one question. Answer it at each of the {_n(nh)} horizons it names, under\n"
                "the one condition in the CONDITION section that follows the question.")
    return (f"Below are {_n(nq)} questions. Answer each at each of the {_n(nh)} horizons it names,\n"
            "under the one condition in the CONDITION section that follows the questions.")


def deliver(ncells, research=True):
    """The delivery sentence: one probability per question x horizon cell."""
    extras = "a short rationale, and the sources you used" if research else "and a short rationale"
    if ncells == 1:
        return ("Call submit_forecast ONCE, with your probability in [0,1] for this question at\n"
                f"this horizon under this condition, {extras}. Give the probability as the one\n"
                "entry of forecasts, with its question_id and horizon.")
    return (f"Call submit_forecast ONCE, with your probability in [0,1] for each of the {ncells}\n"
            f"question x horizon cells under this condition, {extras}. Give the\n"
            "probabilities as forecasts, one entry per cell with its question_id and horizon.")


# ---- what a call asks ---------------------------------------------------------

def severity_name(q):
    """A question's severity, as --severities names it: the ladder rung
    ("100" .. "1B", "extinction"), "10%" for a share of the population,
    "extinction", or "none" (disempowerment)."""
    if q.get("rung"):
        return q["rung"]
    sv = q.get("severity") or {}
    if sv.get("kind") == "population_share":
        return f"{sv['share']:.0%}"
    return sv.get("kind") or "none"


def cell_key(q):
    """The severity a question belongs to: its id without the leg on the
    ladder ("ladder:ai:100"), so a rung's deaths and damages questions share
    one; any other question is its own."""
    if not q.get("leg"):
        return q["id"]
    suffix = f":{q['leg']}"
    if not q["id"].endswith(suffix):
        raise ValueError(f"{q['id']}: a ladder id ends with its leg ({suffix})")
    return q["id"][:-len(suffix)]


def severities(groups, by_group):
    """-> [(group, key, [questions])], one per severity in prompt order, a
    rung's legs in the set's leg order (deaths, then damages)."""
    out, at = [], {}
    for g in groups:
        for q in by_group[g["key"]]:
            k = cell_key(q)
            if k in at:
                out[at[k]][2].append(q)
            else:
                at[k] = len(out)
                out.append((g, k, [q]))
    for _, k, qs in out:
        if len({tuple(q["horizons"]) for q in qs}) > 1 or len(qs) > 2:
            raise ValueError(f"{k}: its questions are not one cell ({[q['id'] for q in qs]})")
    return out


def horizon_phrase(h, spec):
    """How a question's text names a horizon: 'within 6 months', 'by the end of 2030'."""
    roll = {r["id"]: r for r in spec.get("rolling") or []}.get(h)
    return roll["label"] if roll else f"by the end of {h}"


def at_horizons(q, hs, spec):
    """The question asked at `hs` alone: its text names those horizons where it
    listed them all, and it is asked over those only."""
    listed = " / ".join(horizon_phrase(x, spec) for x in q["horizons"])
    if q["text"].count(listed) != 1:
        raise ValueError(f"{q['id']}: its text does not list its horizons as {listed!r}; "
                         "update run_cellwise.at_horizons")
    if any(h not in q["horizons"] for h in hs):
        raise ValueError(f"{q['id']} is not asked at {hs}")
    return {**q, "text": q["text"].replace(listed, " / ".join(horizon_phrase(h, spec) for h in hs)),
            "horizons": list(hs)}


def question_block(gqs, hs, spec, today):
    """build_prompt's blocks for these questions ([(group, [questions])] in
    prompt order) at these horizons: the criteria, the incident rules and
    those horizons' onset intervals."""
    groups = [g for g, _ in gqs]
    by_group = {g["key"]: [at_horizons(q, hs, spec) for q in qs] for g, qs in gqs}
    nq = sum(len(qs) for _, qs in gqs)
    base, n, cells = ru.build_prompt(groups, by_group, list(hs), spec, today)
    assert (n, cells) == (nq, nq * len(hs)), (n, cells, nq, hs)
    lead = (f"Today is {today.isoformat()}.\n\nBelow are {n} forecasting questions, grouped by cause of "
            "catastrophe. Forecast\nall of them together, in one pass.\n\n")
    assert base.startswith(lead), "build_prompt's head changed; update run_cellwise.question_block"
    return base[len(lead):base.index("\nHorizons: ")]


def horizon_line(hs, spec, today):
    labels = ", ".join(f"{h} ({ru.horizon_label(h, spec, today)})" for h in hs)
    return f"Horizon: {labels}." if len(hs) == 1 else f"Horizons: {labels}."


# ---- the one condition --------------------------------------------------------

def check_set(policies, spec):
    """What this runner can ask: a grouped scenario set (the combined set)
    whose elicited quantities, if any, are the whole set's, over questions
    that each take one probability."""
    if not ru.set_groups(policies):
        raise ValueError(f"scenario set {ru.set_slug(policies)!r} has no groups; "
                         "run_cellwise asks grouped sets (data/combined_conditions.json)")
    if any(e.get("group") for e in ru.set_elicits(policies)):
        raise ValueError(f"scenario set {ru.set_slug(policies)!r} elicits per group; not supported per cell")
    if ru.value_mode(spec) != ru.PROBABILITY:
        raise ValueError("run_cellwise asks probability questions only")


def elicited_lines(policies, elicited):
    """The ECI step's question and the model's answer, for a cell prompt.
    `elicited` None (a dry run) shows where the numbers go."""
    out = ""
    for e in ru.set_elicits(policies):
        got = (elicited or {}).get(e["key"])
        values = ", ".join(f"{f} {got[f]:g}" if got else f"{f} [from the ECI step]" for f in e["fields"])
        out += ECI_ASKED.format(text=e["text"], key=e["key"], values=values) + "\n\n"
    return out


# The one change to the condition text: each group's assumption sentence
# ends by pointing at the OTHER group's section, which a call never shows.
# Those clauses go; the rest of the sentence is kept verbatim. Keyed by the
# group, (clause, replacement), each required exactly once.
CROSS_REFERENCES = {
    "policy": (", the same level as condition eci_p50 in the CAPABILITY CONDITIONS section.", "."),
    "capability": (" -- not any of the conditions in the POLICY CONDITIONS section.", "."),
}


def own_assumption(group):
    """The group's assumption sentence without its pointer to the other group."""
    text = group["assumption"]
    if group["key"] in CROSS_REFERENCES:
        clause, repl = CROSS_REFERENCES[group["key"]]
        if text.count(clause) != 1:
            raise ValueError(f"group {group['key']!r}: its assumption no longer ends {clause!r}; "
                             "update run_cellwise.CROSS_REFERENCES")
        text = text.replace(clause, repl)
    return text


def reads_eci(cid, policies):
    """Does the condition refer to the model's eci_forecast?"""
    if cid == UNCONDITIONAL:
        return False
    x = next(s for s in policies["conditions"] if s["id"] == cid)
    return bool(x.get("field")) or "eci_forecast" in own_assumption(
        next(g for g in ru.set_groups(policies) if g["key"] == x["group"]))


def condition_block(cid, policies, elicited, eci_step=True):
    """The CONDITION section for one condition: the set's definitions, the
    ECI step's answer, then the condition as the joint prompt renders it."""
    c = policies["conditioning"]
    out = f"\n===== CONDITION =====\n\n{ru._definitions(policies)}\n\n"
    if eci_step:
        out += elicited_lines(policies, elicited)
    if cid == UNCONDITIONAL:
        return out + f"--- {UNCONDITIONAL} ---\nUnconditional: {c['unconditional_forecast']}\n\n=====\n"
    x = next(s for s in policies["conditions"] if s["id"] == cid)
    g = next(g for g in ru.set_groups(policies) if g["key"] == x["group"])
    out = out.rstrip("\n") + "\n"
    out += ru.GROUP_BLOCK.format(heading=g["heading"], instruction=g["instruction"],
                                 assumption=own_assumption(g),
                                 definitions=f"{g['definitions']}\n" if g.get("definitions") else "",
                                 elicit="", horizon=g["horizon"], items=ru._scenario_items([x]))
    return out + "\n=====\n"


def with_variant(text, variant):
    """The variant's instruction as its own paragraph before the delivery
    sentence, where the joint minimal prompt puts it."""
    v = ru.VARIANTS[variant]
    return f"{v}\n\n{text}" if v else text


def call_prompt(call, spec, policies, today, variant, elicited, research=True, eci_step=True):
    """The whole prompt of one call. `policies` is resolved (resolve_set)."""
    nq, nh = len(call["qids"]), len(call["hs"])
    return (f"Today is {today.isoformat()}.\n\n{head(nq, nh)}\n\n"
            f"{question_block(call['gqs'], call['hs'], spec, today)}"
            f"{condition_block(call['cid'], policies, elicited, eci_step)}\n"
            f"{horizon_line(call['hs'], spec, today)}\n\n" + with_variant(deliver(nq * nh, research), variant))


def eci_prompt(policies, today, variant):
    """The ECI step: the set's definitions and its Step 1 text, alone."""
    es = ru.set_elicits(policies)
    keys = " and ".join(f"{e['key']} ({len(e['fields'])} numbers)" for e in es)
    return (f"Today is {today.isoformat()}.\n\n{ru._definitions(policies)}\n\n"
            + "\n\n".join(e["text"] for e in es) + "\n\n"
            + with_variant(ECI_DELIVER.format(keys=keys), variant))


# ---- the tools -------------------------------------------------------------------

def cell_tool(qids, hs, research=True):
    """forecasts: one {question_id, horizon, probability} per cell of the call."""
    item = {"type": "object",
            "properties": {"question_id": {"type": "string", "enum": list(qids)},
                           "horizon": {"type": "string", "enum": list(hs)},
                           "probability": {"type": "number", "minimum": 0, "maximum": 1}},
            "required": ["question_id", "horizon", "probability"]}
    props = {"forecasts": {"type": "array", "items": item,
                           "description": f"one entry per question x horizon cell ({len(qids) * len(hs)})"},
             "rationale": {"type": "string"}}
    if research:
        props["key_sources"] = {"type": "array", "items": {"type": "string"}}
    return {
        "name": "submit_forecast",
        "description": "Submit your final answer: a probability for each question x horizon cell, a short "
                       "rationale" + (", and the key sources you read." if research else "."),
        "parameters": {"type": "object", "properties": props, "required": ["forecasts", "rationale"]},
    }


def eci_tool(policies):
    """submit_tool_joint's elicited objects, rationale and sources, no grid."""
    tool = ru.submit_tool_joint([], [], [], ru.set_elicits(policies))
    tool["parameters"]["properties"].pop("forecasts")
    tool["description"] = "Submit your final answer: your forecast, a short rationale, and the key sources you read."
    return tool


def clean_probability(raw):
    """A probability in [0,1], or None. A numeric string is read (some
    models stringify); NaN, infinities, booleans and anything else are not."""
    if isinstance(raw, str):
        try:
            raw = float(raw.strip())
        except ValueError:
            return None
    if not isinstance(raw, (int, float)) or isinstance(raw, bool) or not math.isfinite(raw):
        return None
    return float(raw) if 0 <= raw <= 1 else None


def clean_call(answer, qids, hs):
    """{(question_id, horizon): probability} when every cell of the call has
    one (a later entry for a cell replaces an earlier one), else None."""
    got = {}
    for f in ru._as_list(answer.get("forecasts")):
        if isinstance(f, dict) and f.get("question_id") in qids and f.get("horizon") in hs:
            p = clean_probability(f.get("probability"))
            if p is not None:
                got[(f["question_id"], f["horizon"])] = p
    return got if len(got) == len(qids) * len(hs) else None


# ---- one call ----------------------------------------------------------------------

def _guard(condition):
    """The URL guard: the condition's own, to its calls only; or the
    process environment's, which reaches every call. -> (row fields, call env)."""
    own = condition["url_block_patterns"]
    guard = own or os.environ.get(ru.BLOCK_ENV) or None
    return ({"url_block_patterns": guard} if guard else {}), ({ru.BLOCK_ENV: own} if own else {})


def _ask(label, model_id, prompt, final_tool, groups, condition, retries, clean, allowed=()):
    """One call through pi, retried until `clean(answer)` is not None.
    -> (cleaned, answer, evidence, usage, attempts)."""
    _, env = _guard(condition)
    research = ru.minimal_tools(ru.research_tools(groups)[0]) if condition["research"] else []
    usage, attempts = {}, 0
    while True:
        attempts += 1
        try:
            answer, evidence = call_tools(
                model_id, prompt, research, final_tool, system=ru.MINIMAL_SYSTEM,
                max_iters=(condition["max_turns"] if condition.get("max_turns") is not None
                           else ru.MINIMAL_MAX_TURNS),
                min_evidence=0, usage=usage, partial_tool=None, coverage=None, debrief=None,
                allowed_keys=list(allowed), warn_missing=bool(allowed), **({"env": env} if env else {}))
        except Exception as exc:
            if attempts > retries:
                raise
            print(f"  retry {label} attempt {attempts}: {type(exc).__name__}: {str(exc)[:160]}")
            continue
        got = clean(answer)
        if got is not None:
            return got, answer, evidence, usage, attempts
        if attempts > retries:
            raise RuntimeError(f"no usable answer after {attempts} attempt(s): {str(answer)[:200]}")
        print(f"  retry {label} attempt {attempts}: unusable answer {str(answer)[:120]}")


def _provenance(answer, evidence):
    hits = sum(len((e.get("result") or {}).get("results") or [])
               for e in evidence if e.get("tool") == "web_search")
    read = {(e.get("args") or {}).get("url") for e in evidence if e.get("tool") == "read_page"}
    unread = [u for u in (answer.get("key_sources") or []) if isinstance(u, str) and u not in read]
    return {"rationale": answer.get("rationale"), "key_sources": answer.get("key_sources"),
            "grounded": hits > 0, "search_hits": hits, "evidence": evidence, "unread_sources": unread}


def _common(ctx, label, model_id, condition, prompt, rep):
    guard, _ = _guard(condition)
    return {"run_id": ctx["run_id"], "elicited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": model_id, "label": label, "run_date": ctx["today"].isoformat(),
            "instrument_version": ctx["spec"].get("instrument_version"),
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "prompt": prompt,
            "system_prompt": ru.MINIMAL_SYSTEM, "protocol": protocol(ctx["policies"]),
            "set_protocol": ru.set_protocol(ctx["policies"]), "scenario_set": ru.set_slug(ctx["policies"]),
            "unit": UNIT, "experiment": ctx["experiment"], "condition": condition["id"],
            "condition_sha256": condition["sha256"], "variant": condition["variant"],
            "bundle": list(condition["bundle"]), "research": condition["research"], "replicate": rep,
            "panel": ctx["panels"].get(condition["model_set"]), "pooled": False, **guard}


def base_call_id(ctx, label, condition, rep=1):
    """The run's id for one model under one condition and repeat: the
    assembled rows' call_id, and the stem of every call's."""
    return (f"{ctx['run_id']}:{ru.set_slug(ctx['policies'])}:{UNIT}:{label}"
            + (f":{condition['id']}" if condition["id"] != ru.DEFAULT_VARIANT else "")
            + (f"#{rep}" if condition["repeats"] > 1 else ""))


def elicited_field(ctx, values):
    es = ru.set_elicits(ctx["policies"])
    if not es:
        return None
    return {**values,
            "target_date": next((e.get("target_date") for e in es if e.get("target_months")),
                                es[0].get("target_date")),
            "targets": {e["key"]: e.get("target_date") for e in es}}


def run_eci(ctx, label, model_id, condition, retries, rep=1):
    """The ECI step for one model under one condition and repeat -> its row."""
    policies = ctx["policies"]
    es = ru.set_elicits(policies)
    prompt = eci_prompt(policies, ctx["today"], condition["variant"])

    def clean(answer):
        got = {e["key"]: ru.clean_elicit(answer.get(e["key"]), e) for e in es}
        return got if all(got.values()) else None

    got, answer, evidence, usage, attempts = _ask(f"{label} eci", model_id, prompt, eci_tool(policies),
                                                  ctx["groups"], condition, retries, clean)
    return {**_common(ctx, label, model_id, condition, prompt, rep), "step": "eci",
            "call_id": f"{base_call_id(ctx, label, condition, rep)}:eci",
            "elicited": elicited_field(ctx, got), "usage": usage, "attempts": attempts,
            **_provenance(answer, evidence)}


def scenario_stamp(ctx, cid, elicited):
    """The joint rows' `scenario` for this condition: None for unconditional;
    the level a self-elicited condition names, from the ECI step."""
    if cid == UNCONDITIONAL:
        return None
    policies = ctx["policies"]
    c = next(x for x in policies["conditions"] if x["id"] == cid)
    g = next((g for g in ru.set_groups(policies) if g["key"] == c.get("group")), {})
    stamp = {"id": cid, "leap_id": c.get("leap_id"), "label": c["label"],
             "source": (g.get("source") or {}).get("wave") or policies["source"]["wave"],
             "sha256": ctx["scenarios_sha256"], "set": ru.set_slug(policies), "group": c["group"]}
    if c.get("value") is not None:
        stamp["value"] = c["value"]
    elif c.get("field"):
        es = ru.set_elicits(policies)
        key = c.get("elicit") or (es[0]["key"] if es else None)
        stamp["value"] = ((elicited or {}).get(key) or {}).get(c["field"])
    return stamp


def run_call(ctx, label, model_id, condition, call, elicited, retries, rep=1):
    """One call: its questions at its horizons under its condition -> one row
    per question x horizon, the call's prompt, evidence and usage on the first."""
    spec, today, cid = ctx["spec"], ctx["today"], call["cid"]
    prompt = call_prompt(call, spec, ctx["policies"], today, condition["variant"], elicited,
                         condition["research"], condition["eci_step"])
    qids, hs = call["qids"], call["hs"]
    got, answer, evidence, usage, attempts = _ask(
        f"{label} {call['key']}", model_id, prompt, cell_tool(qids, hs, condition["research"]),
        ctx["groups"], condition, retries, lambda a: clean_call(a, qids, hs),
        allowed=[f"{q}|{h}" for q in qids for h in hs])
    base = base_call_id(ctx, label, condition, rep)
    shared = {**_common(ctx, label, model_id, condition, prompt, rep), "step": "cell",
              "call_id": f"{base}:{call['key']}", "run_call_id": base,
              "call_questions": list(qids), "call_horizons": list(hs), "scenario_id": cid,
              "scenario": scenario_stamp(ctx, cid, elicited),
              "elicited": elicited_field(ctx, elicited) if elicited else None,
              "usage": usage, "attempts": attempts, **_provenance(answer, evidence)}
    rows, first = [], True
    for g, qs in call["gqs"]:
        for q in qs:
            for h in hs:
                p = got[(q["id"], h)]
                rows.append({**shared, "question_id": q["id"], "horizon": h, "probability": p,
                             "forecasts": [{"horizon": h, "probability": p}], "target": q["id"] in call["targets"],
                             "resolves_on": {h: ru.resolves_on(h, today, spec)},
                             "counting_window": ru.counting_windows(q, [h], today, spec),
                             "cause": q.get("cause"), "group": g["key"],
                             **({} if first else {"prompt": None, "evidence": [], "usage": None})})
                first = False
    return rows


# ---- assembling the cells into the joint schema ---------------------------------

def assemble(cell_rows, questions):
    """Cell rows -> run_unified's rows: one per (model, condition, repeat,
    scenario, question), `forecasts` over the horizons answered, in horizon
    order. `questions`: [(group, question)] in prompt order, which the rows follow."""
    by = {}
    for r in cell_rows:
        if r.get("step") == "cell":
            by.setdefault((r["label"], r["condition"], r.get("replicate", 1)), []).append(r)
    out = []
    for (label, cond, rep), rows in by.items():
        first = rows[0]
        call_id = first["run_call_id"]
        asked = [UNCONDITIONAL] + [s for s in dict.fromkeys(r["scenario_id"] for r in rows) if s != UNCONDITIONAL]
        cells = {(r["question_id"], r["scenario_id"]): {} for r in rows}
        for r in rows:
            cells[(r["question_id"], r["scenario_id"])][r["horizon"]] = r
        for cid in asked:
            for g, q in questions:
                got = cells.get((q["id"], cid))
                if not got:
                    continue
                hs = [h for h in q["horizons"] if h in got]
                one = got[hs[0]]
                out.append({
                    "run_id": first["run_id"], "elicited_at": max(c["elicited_at"] for c in got.values()),
                    "question_id": q["id"], "model": first["model"], "label": label,
                    "forecasts": [{"horizon": h, "probability": got[h]["probability"]} for h in hs],
                    "rationale": None, "key_sources": None,
                    "grounded": all(c["grounded"] for c in got.values()),
                    "search_hits": sum(c["search_hits"] for c in got.values()),
                    "evidence": [], "usage": None, "delivery": None, "unread_sources": None,
                    "debrief": None, "debrief_status": None,
                    "resolves_on": {h: got[h]["resolves_on"][h] for h in hs},
                    "run_date": first["run_date"], "instrument_version": first["instrument_version"],
                    # None for a question with no onset window (cross-cutting), as in the joint rows.
                    "counting_window": ({h: got[h]["counting_window"][h] for h in hs}
                                        if all(got[h]["counting_window"] for h in hs) else None),
                    "prompt_sha256": None, "prompt": None, "system_prompt": None,
                    "protocol": first["protocol"], "set_protocol": first["set_protocol"],
                    "scenario_set": first["scenario_set"], "call_id": call_id,
                    "attempts": max(c["attempts"] for c in got.values()),
                    "batch_size": len(one["call_questions"]),
                    "cause": q.get("cause"), "group": g["key"], "asked_horizons": q.get("horizons"),
                    "raw_forecasts": None, "scenario": one["scenario"], "elicited": one["elicited"],
                    "experiment": first["experiment"], "condition": cond, "replicate": rep,
                    "condition_sha256": first["condition_sha256"], "arm": UNIT,
                    "variant": first["variant"], "bundle": first.get("bundle", []), "target": one.get("target", True),
                    "joint_scenarios": asked, "panel": first["panel"], "unit": UNIT, "pooled": False,
                    "cell_calls": {h: got[h]["call_id"] for h in hs},
                    **({"url_block_patterns": first["url_block_patterns"]}
                       if first.get("url_block_patterns") else {}),
                })
    return out


def write_assembled(cell_rows, questions, out, cond_out):
    rows = assemble(cell_rows, questions)
    with open(cond_out, "w") as fc, open(out, "w") as f:
        for r in rows:
            fc.write(json.dumps(r) + "\n")
            if r["scenario"] is None:
                f.write(json.dumps(r) + "\n")
    return rows


# ---- the plan ---------------------------------------------------------------------

def _pick(names, pattern, what):
    """Names matching a comma-separated list of names or fnmatch patterns
    (None: all), in their own order; a pattern matching nothing is refused."""
    if not pattern:
        return list(names)
    pats = [p.strip() for p in pattern.split(",") if p.strip()]
    dead = [p for p in pats if not any(fnmatch.fnmatchcase(n, p) for n in names)]
    if dead:
        sys.exit(f"--{what} {dead} matched none of: {', '.join(names)}")
    return [n for n in names if any(fnmatch.fnmatchcase(n, p) for p in pats)]


def plan_cells(groups, by_group, horizons, scenario_ids, args):
    """-> [(group, key, [questions], horizon, condition id)], one per cell,
    severity-major in prompt order, then horizon, then unconditional and the
    scenarios. `args` names cells (by key: "ladder:ai:1M", "disempowerment"),
    severities, causes, horizons and scenarios (None: all); a cell is
    selected when every filter keeps it. `pairs` ("<horizon>|<scenario>"),
    when given, keeps exactly those horizon x scenario cells, each of which
    must be one the selected questions are asked at."""
    sevs = severities(groups, by_group)
    keep_k = set(_pick([k for _, k, _ in sevs], getattr(args, "cells", None), "cells"))
    keep_s = set(_pick(list(dict.fromkeys(severity_name(qs[0]) for _, _, qs in sevs)),
                       getattr(args, "severities", None), "severities"))
    keep_g = set(_pick([g["key"] for g in groups], getattr(args, "causes", None), "causes"))
    keep_h = _pick(horizons, getattr(args, "horizons", None), "horizons")
    keep_c = _pick([UNCONDITIONAL] + list(scenario_ids), getattr(args, "scenarios", None), "scenarios")
    cells = [(g, k, qs, h, cid) for g, k, qs in sevs
             if k in keep_k and severity_name(qs[0]) in keep_s and g["key"] in keep_g
             for h in keep_h if h in qs[0]["horizons"] for cid in keep_c]
    pairs = getattr(args, "pairs", None)
    if pairs:
        want = [tuple(p.split("|", 1)) for p in pairs]
        have = {(h, cid) for _, _, _, h, cid in cells}
        dead = [f"{h}|{c}" for h, c in want if (h, c) not in have]
        if dead:
            sys.exit(f"pairs {dead} name no selected cell (horizons: {', '.join(horizons)}; "
                     f"scenarios: {', '.join([UNCONDITIONAL] + list(scenario_ids))})")
        cells = [c for c in cells if (c[3], c[4]) in set(want)]
    return cells


def plan_calls(groups, by_group, horizons, scenario_ids, args, bundle=(), context=None):
    """The selected cells (plan_cells) gathered into calls -> [call], where a
    call is {key, gqs: [(group, [questions])] in prompt order, qids, hs, cid,
    targets}. Without a bundle, one call per cell. "horizons": a cell's
    selected horizons in one call. "severities": every selected cell in one
    call, with the `context` cells (names or patterns, comma-separated) beside
    them at the same horizons."""
    cells = plan_cells(groups, by_group, horizons, scenario_ids, args)
    sevs = severities(groups, by_group)
    extra = []
    if "severities" in bundle and context:
        targets = {k for _, k, _, _, _ in cells}
        wanted = set(_pick([k for _, k, _ in sevs], context, "context_cells"))
        extra = [(g, k, qs) for g, k, qs in sevs if k in wanted and k not in targets]
    calls = {}
    for g, k, qs, h, cid in cells:
        ck = (None if "severities" in bundle else k, None if "horizons" in bundle else h, cid)
        c = calls.setdefault(ck, {"cells": {}, "hs": [], "cid": cid})
        c["cells"][k] = (g, qs)
        if h not in c["hs"]:
            c["hs"].append(h)
    out = []
    for c in calls.values():
        hs = [h for h in horizons if h in c["hs"]]
        targets = list(c["cells"])
        # The call's questions in the published prompt's order (a ladder's
        # deaths leg, then its damages leg), under their groups' headings.
        members = {q["id"] for _, qs in c["cells"].values() for q in qs} | {q["id"] for _, _, qs in extra for q in qs}
        gqs = [(g, [q for q in by_group[g["key"]] if q["id"] in members]) for g in groups]
        gqs = [(g, qs) for g, qs in gqs if qs]
        key = ("+".join(targets) + ("+context" if extra else "") + "|" + "+".join(hs) + "|" + c["cid"])
        out.append({"key": key, "gqs": gqs, "qids": [q["id"] for _, qs in gqs for q in qs], "hs": hs,
                    "cid": c["cid"], "targets": {q["id"] for k in targets for q in c["cells"][k][1]}})
    return out


def default_plan(groups, by_group, horizons, scenario_ids):
    """The test run's calls (THE DEFAULT RUN): what --max-calls is sized by."""
    return plan_calls(groups, by_group, horizons, scenario_ids,
                      argparse.Namespace(cells=DEFAULT_CELLS, horizons=DEFAULT_HORIZONS))


def selection(condition, args):
    """The cells, severities, causes, horizons and scenarios a condition asks:
    its own fixed selection where it has one, else the command line, else the
    defaults. A command-line flag for a part the condition fixes is refused."""
    pairs = condition.get("pairs")
    own = {"cells": condition["cells"], "horizons": condition["horizons"], "scenarios": condition["scenario_ids"]}
    if pairs:                                       # pairs fix both the horizons and the scenarios
        own.update(horizons=["*"], scenarios=["*"])
    for k, v in own.items():
        if v is not None and getattr(args, k) is not None:
            sys.exit(f"refusing --{k}: condition {condition['id']!r} fixes its own "
                     f"({', '.join(pairs if pairs and k != 'cells' else v)})")
    sel = argparse.Namespace(
        cells=",".join(own["cells"]) if own["cells"] else args.cells,
        severities=args.severities, causes=args.causes,
        horizons=",".join(own["horizons"]) if own["horizons"] else args.horizons,
        scenarios=",".join(own["scenarios"]) if own["scenarios"] else args.scenarios,
        pairs=list(pairs) if pairs else None)
    if not (sel.cells or sel.severities or sel.causes):
        sel.cells = DEFAULT_CELLS
    if not sel.horizons:
        sel.horizons = DEFAULT_HORIZONS
    return sel


def load_instrument(path, today):
    """The scenario set at `path`, resolved for `today`, and its questions."""
    policies = ru.resolve_set(ru.load_policies(path), today)
    groups, by_group, horizons, skipped, spec = (ru.load_questions(policies["questions"]) if policies.get("questions")
                                                 else ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED))
    horizons = ru.set_horizons(policies, horizons)
    check_set(policies, spec)
    return policies, groups, by_group, horizons, spec


def read_cells(path):
    return [json.loads(line) for line in open(path) if line.strip()]


def describe(calls):
    """'1 call(s): 1 target question (+18 context) x 6 horizon(s) x 1 condition(s)'."""
    targets = {q for c in calls for q in c["targets"]}
    context = {q for c in calls for q in c["qids"]} - targets
    return (f"{len(calls)} call(s): {len(targets)} target question(s)"
            + (f" (+{len(context)} context)" if context else "")
            + f" x {len({h for c in calls for h in c['hs']})} horizon(s) x {len({c['cid'] for c in calls})} condition(s)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Forecasts a cell at a time (see the module docstring).")
    ap.add_argument("--experiment", default="percell", help="experiments/<name>.toml; its conditions must have unit = \"cell\"")
    ap.add_argument("--condition", action="append", default=[], help="run only this condition (repeatable)")
    ap.add_argument("--models", help="comma-separated label filter")
    ap.add_argument("--smoke", action="store_true", help="one model only")
    ap.add_argument("--cells", help="cells by key -- ladder:<cause>:<rung> (deaths and damages together) or a "
                                    "cross-cutting question id -- names or patterns, comma-separated, '*' for all. "
                                    "With none of --cells/--severities/--causes, the test run's: "
                                    + DEFAULT_CELLS.replace("%", "%%"))
    ap.add_argument("--severities", help="ladder rungs (100 .. 1B, extinction), 10%%, extinction, none (default: all)")
    ap.add_argument("--causes", help="question groups: ai, bio, cyber, misalign, crosscutting (default: all)")
    ap.add_argument("--horizons", help="horizons, comma-separated, '*' for all (default: "
                                       + ("all" if DEFAULT_HORIZONS == "*" else DEFAULT_HORIZONS) + ")")
    ap.add_argument("--scenarios", help="unconditional and/or scenario ids or patterns, comma-separated (default: all)")
    ap.add_argument("--max-calls", type=int, default=None,
                    help="refuse to start more calls than this (default: one condition's default run "
                         "across the selected models)")
    ap.add_argument("--max-repeats", type=int, default=None,
                    help="ask at most this many of each condition's repeats (a pilot; --resume adds the rest)")
    ap.add_argument("--retries", type=int, default=2, help="re-ask a call that errs or answers unusably")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--allow-ungrounded", action="store_true", help="run a researching condition without Tavily")
    ap.add_argument("--resume", metavar="CELLS_JSONL",
                    help="continue that run (same UTC day): skip what it holds, reuse its ECI steps")
    ap.add_argument("--assemble", metavar="CELLS_JSONL",
                    help="rebuild the assembled files from a cells log and exit; no model is called")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and prompts; no model is called")
    ap.add_argument("--show", type=int, default=DEFAULT_SHOW, help="call prompts a dry run prints in full per condition")
    args = ap.parse_args(argv)

    if args.assemble:
        return assemble_only(args.assemble)
    try:
        exp = experiments.load(args.experiment)
    except (OSError, ValueError) as e:
        sys.exit(f"experiment {args.experiment!r}: {e}")
    unknown = [c for c in args.condition if c not in exp["conditions"]]
    if unknown:
        sys.exit(f"unknown --condition {unknown}; {exp['name']} has {', '.join(exp['conditions'])}")
    conditions = [exp["conditions"][c] for c in (args.condition or exp["conditions"])]
    joint = [c["id"] for c in conditions if c["unit"] != UNIT]
    if joint:
        sys.exit(f"refusing: {exp['name']} condition(s) {joint} are joint; run them with code/run_unified.py")
    if len({c["scenarios"] for c in conditions}) > 1:
        sys.exit("refusing: these conditions ask different scenario sets; run each with its own --condition list")
    path = os.path.join(ROOT, conditions[0]["scenarios"])

    today = datetime.now(timezone.utc).date()
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    done_rows = []
    if args.resume:
        done_rows = read_cells(args.resume)
        if not done_rows:
            sys.exit(f"--resume {args.resume}: no rows")
        if done_rows[0]["run_date"] != today.isoformat():
            sys.exit(f"refusing to resume a run of {done_rows[0]['run_date']} on {today}: "
                     "its prompts' date and rolling horizons would differ")
        run_id = done_rows[0]["run_id"]
    try:
        policies, groups, by_group, horizons, spec = load_instrument(path, today)
    except ValueError as e:
        sys.exit(str(e))
    scenario_ids = [c["id"] for c in policies["conditions"]]
    plans = {}
    for c in conditions:
        plans[c["id"]] = plan_calls(groups, by_group, horizons, scenario_ids, selection(c, args),
                                    c["bundle"], ",".join(c["context_cells"]) if c["context_cells"] else None)
        if not plans[c["id"]]:
            sys.exit(f"condition {c['id']!r}: no cells selected")
        eci_readers = sorted({k["cid"] for k in plans[c["id"]] if reads_eci(k["cid"], policies)})
        if not c["eci_step"] and eci_readers:
            sys.exit(f"condition {c['id']!r} has eci_step = false but asks {eci_readers}, which read the ECI step")
    eci_of = {c["id"]: bool(c["eci_step"] and ru.set_elicits(policies)) for c in conditions}

    if args.dry_run:
        return dry_run(exp, conditions, plans, eci_of, policies, spec, today, args.show)

    panels = {ms: ru.select_models(ms, argparse.Namespace(models=args.models, smoke=args.smoke))
              for ms in dict.fromkeys(c["model_set"] for c in conditions)}
    have_eci = {(r["label"], r["condition"], r.get("replicate", 1)): r["elicited"]
                for r in done_rows if r.get("step") == "eci"}
    have_cell = {(r["label"], r["condition"], r.get("replicate", 1), r["question_id"], r["horizon"], r["scenario_id"])
                 for r in done_rows if r.get("step") == "cell"}
    reps = {c["id"]: min(c["repeats"], args.max_repeats or c["repeats"]) for c in conditions}
    pairs = [(c, label, model, rep) for c in conditions for label, model in panels[c["model_set"]][0]
             for rep in range(1, reps[c["id"]] + 1)]
    eci_todo = [(c, l, m, rep) for c, l, m, rep in pairs if eci_of[c["id"]] and (l, c["id"], rep) not in have_eci]
    call_todo = [(c, l, m, rep, k) for c, l, m, rep in pairs for k in plans[c["id"]]
                 if any((l, c["id"], rep, q, h, k["cid"]) not in have_cell for q in k["qids"] for h in k["hs"])]
    n_calls = len(eci_todo) + len(call_todo)
    n_models = max(len(p[0]) for p in panels.values())
    cap = args.max_calls if args.max_calls is not None else \
        n_models * (1 + len(default_plan(groups, by_group, horizons, scenario_ids)))
    print(f"run {run_id} experiment {exp['name']}, protocol {protocol(policies)}: "
          f"{len(pairs)} model x condition x repeat run(s); {len(eci_todo)} ECI step(s) + {len(call_todo)} cell call(s)"
          + (f" ({len(have_eci)} ECI step(s) and {len(have_cell)} answered cell(s) already in {args.resume})"
             if args.resume else ""))
    for c in conditions:
        print(f"    {c['id']:12} x{reps[c['id']]} per model, variant {c['variant']}, bundle {'+'.join(c['bundle']) or 'none'}, "
              f"research {'on' if c['research'] else 'off'}: {describe(plans[c['id']])}")
    if n_calls > cap:
        sys.exit(f"refusing: {n_calls} calls is more than --max-calls {cap}"
                 + ("" if args.max_calls is not None else
                    f" (by default one condition's default run for {n_models} model(s))")
                 + ". Each call is a paid model call; narrow it with --condition, --models, "
                   "--cells, --horizons or --scenarios, or raise --max-calls deliberately.")
    if not n_calls:
        print("nothing to do")
        return
    if any(eci_of.values()):
        ru.eci_preflight(path)
    ru.load_keys()
    if any(c["research"] for c in conditions) and not os.environ.get("TAVILY_API_KEY") and not args.allow_ungrounded:
        sys.exit("refusing to run: TAVILY_API_KEY is unset, so every web_search fails and the "
                 "forecasts would be ungrounded.\n  override: --allow-ungrounded")

    exp_dir = os.path.join(ROOT, "results", "experiments")
    os.makedirs(exp_dir, exist_ok=True)
    cells_out = args.resume or os.path.join(exp_dir, f"{exp['name']}-{run_id}-cells.jsonl")
    stem = cells_out[:-len("-cells.jsonl")] if cells_out.endswith("-cells.jsonl") else cells_out
    out, cond_out = f"{stem}.jsonl", f"{stem}-instrument.jsonl"
    ctx = {"run_id": run_id, "today": today, "spec": spec, "policies": policies, "groups": groups,
           "experiment": exp["name"], "panels": {ms: p[1] for ms, p in panels.items()},
           "scenarios_sha256": hashlib.sha256(ru.scenarios_block(policies["conditions"], policies).encode()).hexdigest()}
    lock = threading.Lock()
    new_rows, failed, spent = [], 0, 0.0
    eci = dict(have_eci)
    with open(cells_out, "a") as f, cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        def keep(rows):
            nonlocal spent
            with lock:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
                    spent += (row.get("usage") or {}).get("cost_usd") or 0.0
                f.flush()
                new_rows.extend(rows)

        futs = {ex.submit(run_eci, ctx, l, m, c, args.retries, rep): (c, l, rep) for c, l, m, rep in eci_todo}
        for fut in cf.as_completed(futs):
            c, l, rep = futs[fut]
            try:
                row = fut.result()
            except Exception as e:
                failed += 1
                print(f"  FAIL  {l}:{c['id']}#{rep} ECI step: {type(e).__name__}: {str(e)[:160]} (its cells are skipped)")
                continue
            keep([row])
            eci[(l, c["id"], rep)] = row["elicited"]
            print(f"  done  {l}:{c['id']}#{rep} ECI step {row['elicited']}, {ru.usage_line([row])}")
        runnable = [t for t in call_todo if not eci_of[t[0]["id"]] or (t[1], t[0]["id"], t[3]) in eci]
        futs = {ex.submit(run_call, ctx, l, m, c, k, eci.get((l, c["id"], rep)), args.retries, rep):
                (c, l, rep, k) for c, l, m, rep, k in runnable}
        for fut in cf.as_completed(futs):
            c, l, rep, k = futs[fut]
            tag = f"{l}:{c['id']}#{rep} {k['key']}"
            try:
                rows = fut.result()
            except Exception as e:
                failed += 1
                print(f"  FAIL  {tag}: {type(e).__name__}: {str(e)[:160]}")
                continue
            keep(rows)
            shown = ", ".join(f"{r['question_id']}@{r['horizon']} {r['probability']:g}" for r in rows if r["target"])
            print(f"  done  {tag} {shown}, {ru.usage_line(rows)}")
    rows = write_assembled(done_rows + new_rows, [(g, q) for g in groups for q in by_group[g["key"]]], out, cond_out)
    print(f"{len(new_rows)} row(s) ok, {failed} call(s) failed, ${spent:.2f} priced spend -> {cells_out} (calls); "
          f"{len(rows)} assembled row(s) -> {cond_out} (instrument) + {out} (unconditional)")
    if failed:
        print(f"  rerun the failures with: --resume {cells_out} (same filters, same UTC day)")
        sys.exit(1)


def assemble_only(cells_path):
    rows = read_cells(cells_path)
    if not rows:
        sys.exit(f"{cells_path}: no rows")
    from datetime import date
    today = date.fromisoformat(rows[0]["run_date"])
    exp = experiments.load(rows[0]["experiment"])
    path = os.path.join(ROOT, exp["conditions"][rows[0]["condition"]]["scenarios"])
    _, groups, by_group, _, _ = load_instrument(path, today)
    stem = cells_path[:-len("-cells.jsonl")] if cells_path.endswith("-cells.jsonl") else cells_path
    out = write_assembled(rows, [(g, q) for g in groups for q in by_group[g["key"]]],
                          f"{stem}.jsonl", f"{stem}-instrument.jsonl")
    print(f"{len(out)} assembled row(s) -> {stem}-instrument.jsonl + {stem}.jsonl")


def dry_run(exp, conditions, plans, eci_of, policies, spec, today, show):
    """The plan, the ECI step's prompt and the first `show` call prompts per
    condition; numbers the ECI step would supply are shown as placeholders."""
    print(f"##### {exp['name']} [{protocol(policies)}]: conditions {', '.join(c['id'] for c in conditions)} #####")
    for c in conditions:
        calls = plans[c["id"]]
        print(f"##### {c['id']}: per model x{c['repeats']} repeat(s) of {describe(calls)}"
              + (" (+1 ECI step)" if eci_of[c["id"]] else "") + f", bundle {'+'.join(c['bundle']) or 'none'}, "
              f"research {'on' if c['research'] else 'off'} #####")
        if eci_of[c["id"]]:
            p = eci_prompt(policies, today, c["variant"])
            print(f"##### {c['id']} / ECI step: {len(p)} chars #####\n{p}")
        for k in calls[:show]:
            p = call_prompt(k, spec, policies, today, c["variant"], None, c["research"], c["eci_step"])
            print(f"##### {c['id']} / {k['key']}: {len(k['qids'])} question(s) x {len(k['hs'])} horizon(s), "
                  f"{len(p)} chars #####\n{p}")
        if len(calls) > show:
            print(f"##### {c['id']}: {len(calls) - show} more call prompt(s) not shown (--show) #####")
        print(f"##### URL GUARD ({ru.BLOCK_ENV}): {c['url_block_patterns'] or os.environ.get(ru.BLOCK_ENV) or 'off'} #####")


if __name__ == "__main__":
    main()
