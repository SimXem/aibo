"""Leaderboard names for ForecastBench submissions: <condition>-<place>, lower case.

The condition names what is submitted (e.g. an ensemble with research, the
same ensemble without, one model alone). The place names the configuration:
when anything that changes forecasts changes (members, options, prompts,
tools, pi), that condition moves to the next unused place in the registry's
list. Places carry no rank, so a regression never reads as a step backwards;
the order lives in the registry.

The registry records each name's settings in fri-utils' ModelRun shape, plus
a fingerprint of the code that shapes its forecasts (system prompt, question
prompt, tool descriptions). A registered entry is never edited: a new
configuration gets the next place.

`sync` keeps the registry in step with the panel, so a round never runs a
stale ensemble and never waits for a hand step. Given the panel (the models
this machine can run, best by ECI first), a condition whose members are not
the panel's top N, or whose code no longer matches its fingerprint, is
registered under its next place with the panel's top N and the live code.

An entry asks its members under the ForecastBench prompt (`research` says
whether with research) or, when it has `prompts`, under each of those AIRO
conditions (forecastbench.AIRO_CONDITIONS): its forecast is then the mean
over every member under every prompt.

A condition is submitted unless it says `"submit": false` (its members still
run, and their forecasts are kept for scoring afterwards), and anonymously
unless it says `"public": true`. ForecastBench takes at most 3 sets a round,
at most one of them public (2026-11-13); `conditions` refuses a registry
that breaks either.

The registry is private (it ties leaderboard names to a team) and lives
outside the repo: $FORECASTER_NAMES, else ~/.config/fri-forecaster/names.json.
examples/names.example.json shows its shape.

    python -m forecastbench.names conditions          # the submitted conditions, in set-number order
    python -m forecastbench.names conditions --all    # and those that only run
    python -m forecastbench.names public              # the condition submitted under the team's name, if any
    python -m forecastbench.names current <cond>      # its current name, or exit 1 if the code drifted
    python -m forecastbench.names members <cond>      # --member specs for `forecastbench build`
    python -m forecastbench.names sync [--dry-run] < panel   # register what the panel changed
    python -m forecastbench.names show
    python -m forecastbench.names fingerprint <cond>  # for registering a name by hand

The panel on sync's stdin is one model per line, best first:
`<Epoch name> TAB <pi model id> TAB <lab>` (AIRO's `python -m redlines.registry`
prints it). Names alone (`python -m fri_forecaster.eci --fetch --names`) rank
but cannot register a model: sync then keeps the current name and says so.
"""
import copy
import hashlib
import inspect
import json
import os
import sys
from datetime import date

from fri_forecaster import baseline
import forecastbench as fb
from fri_forecaster import harness, panel
from fri_forecaster.variants import VARIANTS

MAX_SETS = 3     # ForecastBench: at most 3 sets per round,
MAX_PUBLIC = 1   # at most one of them under the team's name (2026-11-13)


def registry_path():
    return os.environ.get("FORECASTER_NAMES") or os.path.expanduser("~/.config/fri-forecaster/names.json")


def load(path=None):
    path = path or registry_path()
    if not os.path.exists(path):
        sys.exit(f"no name registry at {path}: set FORECASTER_NAMES (examples/names.example.json shows the shape)")
    return json.load(open(path))


def save(reg, path=None):
    path = path or registry_path()
    with open(path + ".tmp", "w") as f:
        json.dump(reg, f, indent=1)
        f.write("\n")
    os.replace(path + ".tmp", path)


def code_of(research, prompts=None):
    """The code-side settings: what the registry entry cannot spell out."""
    if prompts:   # AIRO conditions: the Baseline loop, the question prompt, each instruction
        return {"system": baseline.SYSTEM, "loop": baseline.LOOP,
                "build_prompt": inspect.getsource(fb.build_prompt), "airo_prompt": inspect.getsource(fb.airo_prompt),
                "instructions": {p: VARIANTS[p] for p in prompts},
                "tool_descriptions": {**{t["name"]: t["description"] for t in baseline.research_tools()},
                                      "submit_forecast": fb.TOOL_DESCRIPTIONS["submit_forecast"]}}
    return {"system": fb.SYSTEM if research else fb.SYSTEM_NO_RESEARCH,
            "build_prompt": inspect.getsource(fb.build_prompt),
            "tool_descriptions": fb.TOOL_DESCRIPTIONS if research else {}}


def prompt_version(entry):
    return fb.AIRO_PROMPT_VERSION if entry.get("prompts") else fb.PROMPT_VERSION


def fingerprint(entry):
    """Hash of a name's recorded settings plus the live code they run with."""
    settings = {k: v for k, v in entry.items() if k in ("aggregate", "research", "harness", "members", "prompts")}
    blob = json.dumps({"settings": settings, "code": code_of(entry["research"], entry.get("prompts"))}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def next_place(reg, condition):
    used = {n.split("-", 1)[1] for n in reg["names"] if n.startswith(condition + "-")}
    return next((p for p in reg["places"] if p not in used), None)


def drift(entry):
    """What the live code no longer matches in a registered entry; [] when it runs it."""
    problems = []
    if entry["harness"]["pi"] != harness.PINNED_PI_VERSION:
        problems.append(f"pi {harness.PINNED_PI_VERSION}, registered {entry['harness']['pi']}")
    if entry["harness"]["prompt_version"] != prompt_version(entry):
        problems.append(f"prompt {prompt_version(entry)}, registered {entry['harness']['prompt_version']}")
    if fingerprint(entry) != entry["fingerprint"]:
        problems.append(f"fingerprint {fingerprint(entry)}, registered {entry['fingerprint']}")
    return problems


def current(reg, condition):
    """The name to submit under, after checking the code still matches it."""
    name = reg["conditions"][condition]["current"]
    problems = drift(reg["names"][name])
    if problems:
        sys.exit(f"{name}: the configuration changed ({'; '.join(problems)}). "
                 f"Register it as {condition}-{next_place(reg, condition)} in the registry.")
    return name


def member_specs(reg, condition):
    """`forecastbench build --member` specs, MODEL@THINKING,MODE: one per member
    under the ForecastBench prompt, one per member and prompt under AIRO's."""
    entry = reg["names"][current(reg, condition)]
    modes = [f"airo-{p}" for p in entry.get("prompts") or []] or ["research" if entry["research"] else "noresearch"]
    return [f"{m['pi_model']}@{m['options']['thinking']},{mode}" for mode in modes for m in entry["members"]]


def submitted(reg):
    """The conditions a round uploads, in set-number order, after checking
    ForecastBench's limits on them."""
    conds = [c for c, v in reg["conditions"].items() if v.get("submit", True)]
    public = public_of(reg)
    if len(conds) > MAX_SETS or len(public) > MAX_PUBLIC:
        sys.exit(f"the registry submits {len(conds)} conditions ({', '.join(conds)}), {len(public)} of them public "
                 f"({', '.join(public) or 'none'}): ForecastBench takes at most {MAX_SETS} sets a round and at most "
                 f"{MAX_PUBLIC} under the team's name. Mark the others \"submit\": false, or not public.")
    return conds


def public_of(reg):
    """The submitted conditions that go up under the team's name, not its anonymous one."""
    return [c for c, v in reg["conditions"].items() if v.get("submit", True) and v.get("public")]


def parse_panel(lines):
    """sync's stdin: `<Epoch name> TAB <pi model id> TAB <lab>` per line, best
    first. A name alone ranks but cannot be registered."""
    panel = []
    for line in lines:
        f = [p.strip() for p in line.rstrip("\n").split("\t")] + [None, None]
        if f[0]:
            panel.append({"eci_name": f[0], "pi_model": f[1] or None, "lab": f[2] or None})
    return panel


def known_members(reg, research, airo=False):
    """pi model id -> the member record an earlier name with the same research
    setting and the same prompt (ForecastBench's or AIRO's) gave that model (a
    one-shot baseline is a baseline for one setting), preferring a record that
    names its baseline."""
    known = {}
    for e in reg["names"].values():
        if e["research"] != research or bool(e.get("prompts")) != airo:
            continue
        for m in e["members"]:
            if m["pi_model"] not in known or (m.get("one_shot_baseline") and not known[m["pi_model"]].get("one_shot_baseline")):
                known[m["pi_model"]] = m
    return known


def member_for(model, like, known, airo=False):
    """A registry member for a panel model: its fri-utils identity from the
    record an earlier name gave the same pi model when there is one
    (known_members), else from its pi id; the options are `like`'s (one
    condition, one thinking level and tool set for every member), but for the
    thinking level under AIRO's prompts: each model's own top one."""
    old = known.get(model["pi_model"]) or {}
    provider, _, pid = model["pi_model"].partition("/")
    options = copy.deepcopy(like["options"])
    if airo:
        options["thinking"] = panel.reasoning_for(model["pi_model"])
    return {"pi_model": model["pi_model"], "model_key": old.get("model_key", pid), "provider": provider,
            "provider_model_id": old.get("provider_model_id", pid), "lab": old.get("lab") or model["lab"],
            "options": options, "one_shot_baseline": old.get("one_shot_baseline"),
            "eci_name": model["eci_name"]}


def sync(reg, condition, panel, today=None):
    """The name a round runs `condition` under, given the panel (parse_panel):
    the current one when its members are the panel's top N and the code still
    matches; else the next place, registered in `reg` with the panel's top N
    and the live code. -> (name, note). A panel without pi ids cannot register
    a new member: the current members are kept and the note warns."""
    cond = reg["conditions"][condition]
    name = cond["current"]
    entry = reg["names"][name]
    n = len(entry["members"])
    top = panel[:n]
    have, want = [m["eci_name"] for m in entry["members"]], [m["eci_name"] for m in top]
    changes, members, warning = drift(entry), entry["members"], None
    if set(have) != set(want):
        if len(top) == n and all(m["pi_model"] for m in top):
            changes.append(f"members {', '.join(have)} -> {', '.join(want)}")
            airo = bool(entry.get("prompts"))
            members = [member_for(m, entry["members"][0], known_members(reg, entry["research"], airo), airo) for m in top]
        else:
            warning = (f"WARNING: the top {n} is {', '.join(want) or 'unknown'} but the panel gives no pi ids "
                       f"to register; {name} keeps {', '.join(have)}")
    if not changes:
        return name, warning or f"{name}: the top {n} ({', '.join(have)}), code unchanged"
    place = next_place(reg, condition)
    if place is None:
        sys.exit(f"{condition}: every place in the registry is used; add places")
    new_name = f"{condition}-{place}"
    new = {"condition": condition, "reason": f"sync {today or date.today().isoformat()}: {'; '.join(changes)}",
           "aggregate": entry["aggregate"], "research": entry["research"],
           **({"prompts": list(entry["prompts"])} if entry.get("prompts") else {}),
           "harness": dict(entry["harness"], pi=harness.PINNED_PI_VERSION, prompt_version=prompt_version(entry)),
           "members": members}
    new["fingerprint"] = fingerprint(new)
    reg["names"][new_name] = new
    cond["current"] = new_name
    return new_name, f"{new_name}: registered, after {name} ({'; '.join(changes)})" + (f"; {warning}" if warning else "")


def main(argv=None, stdin=None):
    argv = sys.argv[1:] if argv is None else argv
    reg = load()
    cmd, arg = ([a for a in argv if not a.startswith("--")] + [None, None])[:2]
    if cmd == "conditions":
        print("\n".join(reg["conditions"] if "--all" in argv else submitted(reg)))
    elif cmd == "public":
        print("\n".join(public_of(reg)))
    elif cmd == "current" and arg:
        print(current(reg, arg))
    elif cmd == "members" and arg:
        print("\n".join(member_specs(reg, arg)))
    elif cmd == "fingerprint" and arg:
        print(fingerprint(reg["names"][reg["conditions"][arg]["current"]]))
    elif cmd == "sync":
        before = json.dumps(reg, sort_keys=True)
        panel = parse_panel(stdin or sys.stdin)
        notes = [sync(reg, c, panel)[1] for c in reg["conditions"]]
        changed = json.dumps(reg, sort_keys=True) != before
        if changed and "--dry-run" not in argv:
            save(reg)
        print("\n".join(("(dry run) " if changed and "--dry-run" in argv else "") + n for n in notes))
    elif cmd == "show":
        for ch, cond in reg["conditions"].items():
            e = reg["names"][cond["current"]]
            how = ("not submitted" if not cond.get("submit", True) else "public" if cond.get("public") else "anonymous")
            asked = f"AIRO {', '.join(e['prompts'])}" if e.get("prompts") else f"research {e['research']}"
            print(f"{cond['current']:18} {how:13} {len(e['members'])} member(s), {asked}: {cond['description']}")
    else:
        sys.exit("usage: python -m forecastbench.names current|members|fingerprint <condition> "
                 "| sync [--dry-run] | conditions [--all] | public | show")


if __name__ == "__main__":
    main()
