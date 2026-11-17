"""The model panel: the top k of Epoch's index that we can run, one seat per family.

Every FRI dashboard that asks a standing panel of frontier models asks THIS
panel (AIRO since 2026-08-28; EEAI; the ForecastBench rounds through `names
sync`). It is not a hand-typed list: it is the PANEL_K highest-ECI models in
the newest snapshot of Epoch's index (fri_forecaster.eci, beside this module)
that MODELS below can run, re-ranked every time it is asked for. Until
2026-11-11 the rule and the table lived in AIRO's redlines/registry.py while
the index reader lived here; they are one thing and now sit together.

  k = 4            averaging the top 3-4 by ECI beat the single best-ranked
                   model and closed the gap to the hindsight-best one; at 5 the
                   marginal model is already below the frontier (AIRO's
                   docs/eci-top4-arm.md).
  one seat per     a model whose family already holds a seat is passed over
  family           and the next runnable model takes it: two versions of one
                   model are one opinion twice (2026-09-08).
  runnable         a model is runnable when it has a row: a hand row in MODELS,
                   or one a dashboard's box added on its own after probing the
                   model (AIRO's redlines.autoreg writes auto_models.json
                   beside the snapshots). A hand row wins.
  no fallback      the ensemble is the top k of the models this installation
                   holds an API key for. One of them that is NOT runnable
                   fails a new run (require(), 2026-11-13): no other model
                   takes its seat. So does a member whose calls fail, in each
                   dashboard's runner. A model whose lab's key is not held is
                   left out until there is one.

Everything the rule does out of the ordinary is a warning, returned and
printed once: a stale snapshot, a model passed over for its family, a model
above the cut with no row, a tie at the cut, a short panel.

    python -m fri_forecaster.panel [--dir DIR] [K]
        # the panel's top K (default PANEL_K), best first, one per line as
        # `<Epoch name> TAB <pi model id> TAB <lab>`: what `names sync` reads
"""
import json
import os
import sys
from pathlib import Path

from . import eci, keys

PANEL_K = 4
PANEL_SET = "eci_topk"

# ── The runnable models ──────────────────────────────────────────────────────
# key         a stable slug, what a dashboard keys its own columns on (AIRO's
#             colors and chart roles are in redlines/registry.py, by this key).
# family      the line whose versions supersede one another, for the one-seat
#             rule. By hand, and a judgement: Claude's tiers (Fable, Opus,
#             Sonnet, Haiku) are separate lines; OpenAI's plain GPT-n are one
#             line, the Pro tier another, and the code-named GPT-5.6 Sol /
#             GPT-6 Astra each their own -- so the 2026-09-08 panel seats Astra
#             beside GPT-5.5 Pro. Fold two families into one here if that ever
#             reads wrong; nothing else changes.
# label       the display name.
# model       `provider/id`. OpenAI ids that name the Responses API by a path
#             segment (`openai/responses/...`) are what AIRO's rows have always
#             recorded; pi_model() gives pi's spelling.
# epoch_name  Epoch's name for the model, exactly: the join to the index.
#
# Rows are never removed: a past run's panel is re-derived from its snapshot.
_FIELDS = ("key", "family", "label", "model", "epoch_name")
_ROWS = [
    ("gpt-3.5-turbo",     "gpt",           "GPT-3.5",        "openai/gpt-3.5-turbo-0125",                         "GPT-3.5 Turbo (Jan 2024)"),
    ("llama-3.3-70b",     "llama",         "Llama-3.3-70B",  "deepinfra/meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B"),
    ("gpt-4o",            "gpt",           "GPT-4o",         "openai/gpt-4o",                                     "GPT-4o (Nov 2024)"),
    ("deepseek-v3",       "deepseek",      "DeepSeek-V3",    "deepinfra/deepseek-ai/DeepSeek-V3",                 "DeepSeek-V3"),
    ("claude-sonnet-4-5", "claude-sonnet", "Sonnet 4.5",     "anthropic/claude-sonnet-4-5-20250929",              "Claude Sonnet 4.5"),
    ("gpt-5",             "gpt",           "GPT-5",          "openai/gpt-5-2025-08-07",                           "GPT-5"),
    ("claude-opus-4-6",   "claude-opus",   "Opus 4.6",       "anthropic/claude-opus-4-6",                         "Claude Opus 4.6"),
    ("claude-opus-4-8",   "claude-opus",   "Opus 4.8",       "anthropic/claude-opus-4-8",                         "Claude Opus 4.8"),
    ("claude-fable-5",    "claude-fable",  "Fable 5",        "anthropic/claude-fable-5",                          "Claude Fable 5"),
    ("gpt-4.1",           "gpt",           "GPT-4.1",        "openai/gpt-4.1-2025-04-14",                         "GPT-4.1"),
    ("claude-haiku-4-5",  "claude-haiku",  "Haiku 4.5",      "anthropic/claude-haiku-4-5-20251001",               "Claude Haiku 4.5"),
    ("gpt-5.5-pro",       "gpt-pro",       "GPT-5.5 Pro",    "openai/gpt-5.5-pro",                                "GPT-5.5 Pro"),
    ("gpt-5.5",           "gpt",           "GPT-5.5",        "openai/gpt-5.5",                                    "GPT-5.5"),
    ("gemini-3.1-pro",    "gemini-pro",    "Gemini 3.1 Pro", "gemini/gemini-3.1-pro-preview",                     "Gemini 3.1 Pro"),
    ("grok-4.20",         "grok",          "Grok 4.20",      "xai/grok-4.20",                                     "Grok 4.20"),
    # Added 2026-08-28 with the ECI top-4 arm.
    ("claude-opus-5",     "claude-opus",   "Opus 5",         "anthropic/claude-opus-5",                           "Claude Opus 5"),
    ("gpt-5.6-sol",       "gpt-sol",       "GPT-5.6 Sol",    "openai/gpt-5.6-sol",                                "GPT-5.6 Sol"),
    # Added 2026-09-08: the index's new top two. GPT-6 Astra takes the
    # Responses API: on /v1/chat/completions OpenAI refuses function tools for
    # it under any reasoning effort, and the research tools are the point.
    ("claude-fable-5-1",  "claude-fable",  "Fable 5.1",      "anthropic/claude-fable-5-1",                        "Claude Fable 5.1"),
    ("gpt-6-astra",       "gpt-astra",     "GPT-6 Astra",    "openai/responses/gpt-6-astra",                      "GPT-6 Astra"),
    # Added 2026-10-01: the index ranks them first and third, so they take the
    # claude-opus seat from Opus 5 and a claude-sonnet seat of their own.
    ("claude-opus-5-5",   "claude-opus",   "Opus 5.5",       "anthropic/claude-opus-5-5",                         "Claude Opus 5.5"),
    ("claude-sonnet-5-5", "claude-sonnet", "Sonnet 5.5",     "anthropic/claude-sonnet-5-5",                       "Claude Sonnet 5.5"),
]
MODELS = [dict(zip(_FIELDS, row)) for row in _ROWS]

AUTO_MODELS = "auto_models.json"

# Reasoning level per provider, pi's `--thinking`: the top rung, which is
# spelled differently per provider (AIRO's project lead, 2026-09-02: reasoning
# at its maximum; Anthropic's effort also governs how many tool calls the model
# makes, which is the point).
REASONING = {"anthropic": "max", "openai": "xhigh"}
REASONING_DEFAULT = "high"


def reasoning_for(model):
    """pi's `--thinking` for `model` (`provider/id`)."""
    return REASONING.get(model.split("/", 1)[0], REASONING_DEFAULT)


def pi_model(model):
    """A row's `model` -> pi's id for it. pi picks the API itself, so the
    Responses-API path segment is dropped; its provider for Gemini is
    `google` (a `gemini/` id is "not found": 2026-11-13, Gemini 4 Carbon sat
    out for it)."""
    model = model.replace("openai/responses/", "openai/", 1)
    return "google/" + model[len("gemini/"):] if model.startswith("gemini/") else model


def auto_models_path(snapshot_dir=None):
    """Where a box's automatic rows are: $FORECASTER_AUTO_MODELS, else
    auto_models.json beside the snapshots."""
    explicit = os.environ.get("FORECASTER_AUTO_MODELS")
    return Path(explicit) if explicit else eci._dir(snapshot_dir) / AUTO_MODELS


def load_auto(path):
    """The automatic rows at `path` ([] if there is no file), in this module's
    fields; an entry written by AIRO's autoreg spells `model` as `litellm_id`."""
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for e in json.loads(path.read_text(encoding="utf-8")):
        row = {f: e.get(f) for f in _FIELDS}
        row["model"] = row["model"] or e.get("litellm_id")
        out.append(row)
    return out


def models(auto=None, snapshot_dir=None):
    """Every runnable model: the hand rows, then the automatic ones (from
    `auto`, a path, or auto_models_path) that no hand row already covers."""
    out = [dict(m) for m in MODELS]
    hand = {m["epoch_name"] for m in out} | {m["key"] for m in out}
    for row in load_auto(auto or auto_models_path(snapshot_dir)):
        if row["epoch_name"] not in hand and row["key"] not in hand:
            out.append({**row, "auto": True})
    return out


class PanelError(RuntimeError):
    """The index's top k cannot all be run."""


# NO FALLBACK (2026-11-13). The ensemble is the top k by ECI of the models
# this installation holds an API key for. A model in it that cannot be run
# fails the run: no other model takes its seat. A model whose lab's key is
# not held is not in it at all, until there is a key. select() still seats
# the next runnable model either way, because a past run's panel is
# re-derived from its snapshot with the same rule; a NEW run must call
# require(), which refuses the panel when it is not that ensemble.
def unseated(ranked, table, k=PANEL_K, snapshot_name="the snapshot", held=None):
    """Why a new run may not use select()'s panel. -> (problems, omitted):
    `problems` are the models above the cut that cannot be run though their
    lab's key is held (and a short panel); `omitted`, the ones left out for
    want of a key. `held(provider)` defaults to keys.held."""
    held = held or keys.held
    chosen, warnings = select(ranked, table, k, snapshot_name)
    problems = [w for w in warnings if "panel is short" in w]
    omitted = []
    if chosen:
        cut, rows = chosen[-1][1], {m["epoch_name"] for m in table}
        for r in ranked:
            if r["model"] in rows or (r["eci"], -r["rank"]) <= (cut["eci"], -cut["rank"]):
                continue
            provider = keys.provider_of(r.get("organization"))
            if provider and held(provider):
                problems.append(f"{r['model']} is in the top {k} of {snapshot_name} and cannot be run, though "
                                f"{keys.KEY_FOR[provider]} is set (no row in fri_forecaster/panel.py, and no "
                                f"automatic one -- the autoreg log line says why)")
            else:
                omitted.append(f"{r['model']} is left out of the ensemble: no API key for its lab "
                               f"({keys.KEY_FOR.get(provider) or r.get('organization') or 'unknown'})")
    return problems, omitted


def require(ranked, table, k=PANEL_K, snapshot_name="the snapshot", held=None):
    """Refuse a panel that is not the ensemble: raise PanelError. -> the
    notes on models left out for want of a key."""
    problems, omitted = unseated(ranked, table, k, snapshot_name, held)
    if problems:
        raise PanelError("the ensemble cannot be seated, and no other model stands in: " + "; ".join(problems))
    return omitted


def select(ranked, table, k=PANEL_K, snapshot_name="the snapshot", stale=None):
    """THE RULE. `ranked` is the index best first (eci.ranked); `table` the
    runnable rows, each with at least `epoch_name` and `family` (a dashboard
    may pass its own rows, with its own extra columns, and gets them back).
    -> (members, warnings): members are (row, index record) pairs, best
    first; `stale` is a staleness warning to lead with, if any."""
    by_epoch = {m["epoch_name"]: m for m in table}
    chosen, unrunnable, passed, warnings = [], [], [], []
    if stale:
        warnings.append(stale)
    seated = {}
    for r in ranked:
        m = by_epoch.get(r["model"])
        if m is None:
            unrunnable.append(r)
            continue
        if m["family"] in seated:
            passed.append((m, r, seated[m["family"]]))
            continue
        chosen.append((m, r))
        seated[m["family"]] = m
        if len(chosen) == k:
            break
    for m, r, holder in passed:
        warnings.append(f"passed over {r['model']} ({r['eci']:g}): its family "
                        f"({m['family']}) already holds a seat through {holder['epoch_name']}; "
                        f"the next runnable model took the seat")
    if len(chosen) < k:
        warnings.append(f"only {len(chosen)} of the top {k} in {snapshot_name} are models the "
                        f"registry can run; the panel is short")
    if chosen:
        cut = chosen[-1][1]
        above = [r["model"] for r in unrunnable if (r["eci"], -r["rank"]) > (cut["eci"], -cut["rank"])]
        if above:
            warnings.append(f"the index ranks {', '.join(above)} above the panel's cut but the "
                            f"registry cannot run them (no row in fri_forecaster/panel.py, and no "
                            f"automatic one -- the autoreg log line says why); "
                            f"skipped, the next runnable model took the seat")
        tied = [r["model"] for r in ranked if r["eci"] == cut["eci"]
                and r["model"] not in {m["epoch_name"] for m, _ in chosen}]
        if tied:
            warnings.append(f"tie at the cut: {cut['model']} ({cut['eci']:g}) is in the panel "
                            f"and {', '.join(tied)} ({cut['eci']:g}) out, on Epoch's rank order")
    return chosen, warnings


def panel(k=PANEL_K, snapshot=None, snapshot_dir=None, auto=None, warn=True):
    """The panel for a dashboard with no table of its own: the k highest-ECI
    models of `snapshot` ((date, path); the newest in `snapshot_dir` by
    default), best first. Raises PanelError when one of them cannot be run,
    unless `snapshot` is given (a past run's panel, re-derived).
    -> (members, provenance). A member is its row
    plus `pi_model`, `reasoning`, and the index's `eci`, `rank` and
    `organization`; `provenance` is what a run stamps on its rows (which
    snapshot chose the panel, how old it was, the warnings)."""
    day, path = snapshot or eci.latest(snapshot_dir)
    stale = None if snapshot else eci.stale_message(snapshot_dir=snapshot_dir)
    ranked, table = eci.ranked(path), models(auto, snapshot_dir)
    chosen, warnings = select(ranked, table, k, Path(path).name, stale)
    if not snapshot:
        warnings = warnings + require(ranked, table, k, Path(path).name)
    if warn:
        for w in warnings:
            print(f"WARN: {w}", file=sys.stderr)
    members = [{**m, "pi_model": pi_model(m["model"]), "reasoning": reasoning_for(m["model"]),
                "eci": r["eci"], "rank": r["rank"], "organization": r.get("organization")}
               for m, r in chosen]
    provenance = {"set": PANEL_SET, "k": k, "snapshot": day.isoformat(),
                  "age_days": eci.age_days(snapshot_dir=snapshot_dir) if not snapshot else None,
                  "members": [{"label": m["label"], "eci": m["eci"], "rank": m["rank"]} for m in members],
                  "warnings": warnings}
    return members, provenance


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    snapshot_dir = None
    if "--dir" in args:
        i = args.index("--dir")
        snapshot_dir = args[i + 1]
        del args[i:i + 2]
    k = int(args[0]) if args else PANEL_K
    try:
        members, _ = panel(k, snapshot_dir=snapshot_dir)
    except (FileNotFoundError, PanelError) as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1
    for m in members:
        print(m["epoch_name"], m["pi_model"], m["organization"] or "", sep="\t")
    return 0


if __name__ == "__main__":
    sys.exit(main())
