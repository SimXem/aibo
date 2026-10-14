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

The registry is private (it ties leaderboard names to a team) and lives
outside the repo: $FORECASTER_NAMES, else ~/.config/fri-forecaster/names.json.
examples/names.example.json shows its shape.

    python -m fri_forecaster.names conditions          # the conditions, in submission order
    python -m fri_forecaster.names current <cond>      # its current name, or exit 1 if the code drifted
    python -m fri_forecaster.names members <cond>      # --member specs for `forecastbench build`
    python -m fri_forecaster.names show
    python -m fri_forecaster.names fingerprint <cond>  # for registering a new name
    python -m fri_forecaster.names eci <cond>          # members' Epoch ECI names, one per line
"""
import hashlib
import inspect
import json
import os
import sys

from fri_forecaster import forecastbench as fb
from fri_forecaster import harness

REGISTRY = os.environ.get("FORECASTER_NAMES") or os.path.expanduser("~/.config/fri-forecaster/names.json")


def load(path=REGISTRY):
    if not os.path.exists(path):
        sys.exit(f"no name registry at {path}: set FORECASTER_NAMES (examples/names.example.json shows the shape)")
    return json.load(open(path))


def code_of(research):
    """The code-side settings: what the registry entry cannot spell out."""
    return {"system": fb.SYSTEM if research else fb.SYSTEM_NO_RESEARCH,
            "build_prompt": inspect.getsource(fb.build_prompt),
            "tool_descriptions": fb.TOOL_DESCRIPTIONS if research else {}}


def fingerprint(entry):
    """Hash of a name's recorded settings plus the live code they run with."""
    settings = {k: v for k, v in entry.items() if k in ("aggregate", "research", "harness", "members")}
    blob = json.dumps({"settings": settings, "code": code_of(entry["research"])}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def next_place(reg, condition):
    used = {n.split("-", 1)[1] for n in reg["names"] if n.startswith(condition + "-")}
    return next((p for p in reg["places"] if p not in used), None)


def current(reg, condition):
    """The name to submit under, after checking the code still matches it."""
    name = reg["conditions"][condition]["current"]
    entry = reg["names"][name]
    problems = []
    if entry["harness"]["pi"] != harness.PINNED_PI_VERSION:
        problems.append(f"pi {harness.PINNED_PI_VERSION}, registered {entry['harness']['pi']}")
    if entry["harness"]["prompt_version"] != fb.PROMPT_VERSION:
        problems.append(f"prompt {fb.PROMPT_VERSION}, registered {entry['harness']['prompt_version']}")
    if fingerprint(entry) != entry["fingerprint"]:
        problems.append(f"fingerprint {fingerprint(entry)}, registered {entry['fingerprint']}")
    if problems:
        sys.exit(f"{name}: the configuration changed ({'; '.join(problems)}). "
                 f"Register it as {condition}-{next_place(reg, condition)} in the registry.")
    return name


def member_specs(reg, condition):
    """`forecastbench build --member` specs: MODEL@THINKING,research|noresearch."""
    entry = reg["names"][current(reg, condition)]
    flag = "research" if entry["research"] else "noresearch"
    return [f"{m['pi_model']}@{m['options']['thinking']},{flag}" for m in entry["members"]]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    reg = load()
    cmd, arg = (argv + [None, None])[:2]
    if cmd == "conditions":
        print("\n".join(reg["conditions"]))
    elif cmd == "current" and arg:
        print(current(reg, arg))
    elif cmd == "members" and arg:
        print("\n".join(member_specs(reg, arg)))
    elif cmd == "eci" and arg:
        print("\n".join(m["eci_name"] for m in reg["names"][current(reg, arg)]["members"]))
    elif cmd == "fingerprint" and arg:
        print(fingerprint(reg["names"][reg["conditions"][arg]["current"]]))
    elif cmd == "show":
        for ch, cond in reg["conditions"].items():
            e = reg["names"][cond["current"]]
            print(f"{cond['current']:18} {len(e['members'])} member(s), research {e['research']}: {cond['description']}")
    else:
        sys.exit("usage: python -m fri_forecaster.names current|members|eci|fingerprint <condition> | conditions | show")


if __name__ == "__main__":
    main()
