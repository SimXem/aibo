"""redlines.registry — the single model table: ids, labels, ECI, colors, architecture.

Before this module the model set was defined in five places under five naming
conventions:

  code/eci_scores.py     DEMO_MODEL_SET (9) + GAP_FILLERS (2) + ALT_HIGH_ANCHOR (1)
  archive/legacy-questions/run_forecasts.py  MODELS -- the frontier five
  code/make_demo_graph1.py  MODEL_COLORS      -- frontier-five display colors
  archive/litellm-runners/pandemic_smoke.py    SMOKE_MODELS      -- hand-typed ECI integers (!)
  code/make_demo_graph3.py  DASH_MODELS       -- ForecastBench display names

MODELS below is the union: one row per distinct model, tagged with every role
it plays. ECI is always looked up from a dated snapshot of the official Epoch
Capabilities Index by epoch_name at import time -- never hand-copied
(docs/model-set.md). Which snapshots exist, which is newest and how old it is
are redlines.eci's business; this module only says which vintage each number
comes from.

THE MODEL PANEL (since 2026-08-28) is not a hand-typed list. It is the
PANEL_K highest-ECI models in the NEWEST snapshot that this table can run
(panel()), re-ranked every time it is asked for -- the rule measured in
~/Projects/forecastbench-ensembling (docs/eci-top4-arm.md): average the top
3-4 by ECI; the specific list goes stale fast, so never inherit one. The
hand-typed frontier five survive as the named set `frontier5`, the panel the
series ran on until then.

Since 2026-11-11 the rule (top k, one seat per family) and the rows every
dashboard shares (key, family, label, id, Epoch name) are
fri_forecaster.panel, beside the index reader; this module adds AIRO's
columns (colors, chart roles, the pinned ECI vintage) and binds the rule to
AIRO's snapshots under data/.
"""
from datetime import date
import functools
import json
import sys
from pathlib import Path

from . import autoreg as _autoreg
from . import eci as _eci   # also puts packages/forecaster on the path
from fri_forecaster import panel as _panel

REPO_ROOT = Path(__file__).resolve().parent.parent
# Graph 4's vintage. Models already in this file keep its values, so the
# ladder and every tracked artifact stay byte-identical -- refreshing those
# values is a separate, deliberate change that has to be re-baselined against
# tests/. The 2026-09-08 snapshot (eci.SUPPLEMENT), then the newest, are
# consulted ONLY for models the pinned file predates (Claude Opus 5 shipped
# 2026-07-24, GPT-5.6 Sol 2026-07-09).
EPOCH_CSV = _eci.snapshot_path(_eci.PINNED)


def load_epoch_index(csv_path: Path = EPOCH_CSV, supplement: Path | None = None) -> dict[str, dict]:
    """Official Epoch Capabilities Index, keyed by exact model name -> row dict.

    The pinned snapshot wins; the supplements fill in only models it never
    had -- `supplement` if given, else the frozen eci.SUPPLEMENT snapshot and
    then the newest one, in that order (so a fetched snapshot adds new
    models without moving the ones already drawn).
    """
    idx = _eci.load(csv_path)
    chain = [supplement] if supplement else [_eci.snapshot_path(_eci.SUPPLEMENT), _eci.latest()[1]]
    for sup in chain:
        if sup and Path(sup).exists() and Path(sup) != Path(csv_path):
            for name, rec in _eci.load(sup).items():
                idx.setdefault(name, rec)
    return idx


# ── The model table ─────────────────────────────────────────────────────────
# roles are a subset of:
#   frontier5      archive/legacy-questions/run_forecasts.py MODELS (news-grounded runner)
#   g4_ladder      code/eci_scores.py DEMO_MODEL_SET (the base 9-model ECI ladder;
#                  since 2026-08-27 also GPT-5.5 / Gemini 3.1 Pro / Grok 4.20, so
#                  every model the dashboard runs sits on Graph 4's ladder)
#   g4_gapfiller   code/eci_scores.py GAP_FILLERS (the +2 137/143 gap-fillers)
#   pandemic_smoke archive/litellm-runners/pandemic_smoke.py SMOKE_MODELS
#   graph3_dash    code/make_demo_graph3.py DASH_MODELS (ForecastBench display names)
#
# architecture: public facts only -- never guessed. One of:
#   "moe"          -- publicly documented mixture-of-experts (DeepSeek-V3's
#                      technical report).
#   "dense"        -- publicly documented dense transformer (Llama-3.3-70B's
#                      model card).
#   "distilled"    -- publicly documented distillation from a larger teacher.
#                      No row uses this today; reserved for when one does.
#   "undisclosed"  -- every closed-vendor model (OpenAI/Anthropic/Google/xAI):
#                      the lab has not published architecture details. This is
#                      not "we didn't check" -- it's the honest label for
#                      "the vendor keeps it private."
#
# TODO.md Phase 2's Graph-4 subset rule (redlines/views/graph4.py build()):
# the CLEAN SUBSET excludes architecture in {"moe", "distilled"} -- i.e.
# architectures known to behave differently from a plain dense transformer,
# which is a real confound for a capability-vs-skill trend line -- and keeps
# "dense" + "undisclosed". "undisclosed" stays IN the clean subset: absence of
# a public architecture claim is not evidence of a confounded one, and
# excluding on suspicion rather than fact would just be guessing with extra
# steps.
#
# colors: the frontier five's are the fixed categorical assignments from
# code/make_demo_graph1.py's MODEL_COLORS, CVD-validated against the demo's
# light panel; the 2026-08-28 panel members got theirs with the ECI top-4 arm.
# Every other row carries a muted spare so that, the day the index ranks it
# into the panel, the views can draw it -- none of those has been drawn yet,
# and they are chosen only to sit apart from the eight above and from the
# cause palette (CATEGORIES, data/autoarc_ladder.json).
# The rows themselves -- which models there are, their families, their ids --
# are fri_forecaster.panel.MODELS (packages/forecaster), shared by every
# dashboard since 2026-11-11. What is AIRO's is below, by the row's key:
# fb_name, color, architecture, roles. A shared row with no entry here fails
# the import by name: any runnable row can be ranked into the panel and must
# be drawable.
_AIRO = {
    # key:                (fb_name,                     color,      architecture,  roles)
    "gpt-3.5-turbo":      (None,                        "#6b7280",  "undisclosed", ["g4_ladder", "pandemic_smoke"]),
    "llama-3.3-70b":      (None,                        "#5b8c2a",  "dense",       ["g4_ladder", "pandemic_smoke"]),
    "gpt-4o":             (None,                        "#b8860b",  "undisclosed", ["g4_ladder", "pandemic_smoke"]),
    "deepseek-v3":        (None,                        "#1b5e9e",  "moe",         ["g4_ladder", "pandemic_smoke"]),
    "claude-sonnet-4-5":  (None,                        "#c2185b",  "undisclosed", ["g4_ladder", "pandemic_smoke"]),
    "gpt-5":              (None,                        "#2e7d32",  "undisclosed", ["g4_ladder", "pandemic_smoke"]),
    "claude-opus-4-6":    (None,                        "#795548",  "undisclosed", ["g4_ladder", "pandemic_smoke"]),
    "claude-opus-4-8":    ("Claude-Opus-4-8",           "#d97e2e",  "undisclosed", ["g4_ladder", "frontier5", "graph3_dash"]),
    "claude-fable-5":     (None,                        "#b52a55",  "undisclosed", ["g4_ladder", "frontier5"]),
    "gpt-4.1":            (None,                        "#00838f",  "undisclosed", ["g4_gapfiller", "pandemic_smoke"]),
    "claude-haiku-4-5":   (None,                        "#e0a020",  "undisclosed", ["g4_gapfiller", "pandemic_smoke"]),
    "gpt-5.5-pro":        (None,                        "#c25a2e",  "undisclosed", []),  # ALT_HIGH_ANCHOR; in the ECI panel since 2026-08-28
    "gpt-5.5":            ("GPT-5.5-2026-04-23",        "#4a76c9",  "undisclosed", ["g4_ladder", "pandemic_smoke", "frontier5", "graph3_dash"]),
    "gemini-3.1-pro":     ("Gemini-3.1-Pro-Preview",    "#1f8a70",  "undisclosed", ["g4_ladder", "pandemic_smoke", "frontier5", "graph3_dash"]),
    "grok-4.20":          ("Grok-4.20-0309-Reasoning",  "#8a63c9",  "undisclosed", ["g4_ladder", "pandemic_smoke", "frontier5", "graph3_dash"]),
    # Added 2026-08-28 with the ECI top-4 arm (docs/eci-top4-arm.md), now
    # panel members by rank. On Graph 4's ladder since 2026-08-28 evening
    # (project lead: Graph 4 should get Opus 5 and GPT-5.6 Sol) -- run through both
    # simulators exactly as the rest. Their ECI is the newest snapshot's, not
    # the pinned vintage (neither existed on 2026-07-07); the gap is about a
    # point (docs/model-set.md). GPT-5.5 Pro stays off: ~$100-250 per sim.
    "claude-opus-5":      (None,                        "#7a4fa3",  "undisclosed", ["g4_ladder", "pandemic_smoke"]),
    "gpt-5.6-sol":        (None,                        "#2f6f9f",  "undisclosed", ["g4_ladder", "pandemic_smoke"]),
    # Added 2026-09-08 with the ECI snapshot of that day: the index's new top
    # two. Panel members by rank from the first run after; not on Graph 4's
    # ladder (never run through the simulators).
    "claude-fable-5-1":   (None,                        "#8e2a63",  "undisclosed", []),
    "gpt-6-astra":        (None,                        "#0e7c7b",  "undisclosed", []),
    # Added 2026-10-01: Epoch's index of that day ranks them first and third
    # (167.3 and 165.2), so they take the claude-opus seat from Opus 5 and a
    # claude-sonnet seat of their own; GPT-5.5 Pro leaves the panel. Probed on
    # the box the same day: max (adaptive) reasoning accepted, and -- like
    # Fable 5.1 -- a forced tool_choice refused (pi never forces one). Not on
    # Graph 4's ladder.
    "claude-opus-5-5":    (None,                        "#4f5bd5",  "undisclosed", []),
    "claude-sonnet-5-5":  (None,                        "#d4892a",  "undisclosed", []),
}


def _rows():
    missing = [m["key"] for m in _panel.MODELS if m["key"] not in _AIRO]
    if missing:
        raise KeyError(f"fri_forecaster.panel.MODELS rows with no entry in redlines/registry.py _AIRO "
                       f"(fb_name, color, architecture, roles): {', '.join(missing)}")
    return [(m["key"], m["family"], m["label"], m["model"], _AIRO[m["key"]][0], m["epoch_name"],
             *_AIRO[m["key"]][1:]) for m in _panel.MODELS]


_ROWS = _rows()

# Graph-4 clean-subset rule (TODO.md Phase 2). A model is excluded from the
# "clean subset" trend iff its architecture is a known-confounded one -- see
# the architecture field comment above for what's in/out and why.
CONFOUNDED_ARCHITECTURES = frozenset({"moe", "distilled"})

_FIELDS = ("key", "family", "label", "litellm_id", "fb_name", "epoch_name", "color", "architecture", "roles")


def _build_models(auto_path: Path = _autoreg.AUTO_MODELS) -> list[dict]:
    idx = load_epoch_index()
    out = []
    for row in _ROWS:
        d = dict(zip(_FIELDS, row))
        rec = idx.get(d["epoch_name"]) if d["epoch_name"] else None
        if rec is None:
            raise KeyError(f"Epoch name not in CSV: {d['epoch_name']!r} (key={d['key']!r})")
        # The pinned vintage (Graph 4's), as before. Integers: both formats
        # the pinned file has ever been in carried whole scores.
        d["eci"], d["ci_low"], d["ci_high"] = int(rec["eci"]), rec["ci_low"], rec["ci_high"]
        if d["color"] is None:
            raise ValueError(f"registry row {d['key']!r} has no color; any runnable row "
                             "can be ranked into the panel and must be drawable")
        out.append(d)
    # The rows the box added on its own (redlines.autoreg, 2026-10-07) for
    # models the index ranked into the panel with no row here. A hand row
    # for the same model wins; an entry whose model no snapshot in data/
    # scores (a checkout without the box's newest fetch) is left out.
    hand = {d["epoch_name"] for d in out} | {d["key"] for d in out}
    for e in _autoreg.load(auto_path):
        rec = idx.get(e["epoch_name"])
        if rec is None or e["epoch_name"] in hand or e["key"] in hand:
            continue
        d = {f: e.get(f) for f in _FIELDS}
        d["roles"] = list(d["roles"] or [])
        d["eci"], d["ci_low"], d["ci_high"] = int(rec["eci"]), rec["ci_low"], rec["ci_high"]
        d["auto"] = True
        out.append(d)
    return out


MODELS = _build_models()


# ── Cause-category palette (code/make_demo_graph1.py CATEGORIES, verbatim) ────
# Rail groups. TWO now, not four (Auto-ARC swap, 2026-08-18): the three
# cross-cutting questions, then the incident types Graph 1 features at the 1M
# rung. Nuclear left the question set entirely and Biorisk stopped being a
# top-level category -- it is one of four AI incident types. The per-CAUSE
# palette moved to data/autoarc_ladder.json, where the causes themselves live;
# these two colors are only the rail's group headings.
# Single source of truth -- the timeline page groups its rail the same way.
# Unified cause palette (2026-08-13): one hue per cause across every surface
# (Graph 1/timeline rail dots, Graph 2 curves + supers diamonds), chosen to
# not collide with the model palette above — the old values reused model hues
# (rail purple = Grok, G2 ai-crimson = Fable, bio-teal = Gemini, nuclear-blue
# = GPT-5.5), so the same color meant different things on different graphs.
# Validated (CVD + normal-vision separation + chroma/lightness, dataviz
# six-checks) as the trio #33a8bd/#a63d76/#a1801a on the page surface; slate
# is the deliberate neutral for the aggregate, matching Graph 1's black
# ensemble convention. The cyan's 2.7:1 surface contrast is relieved by
# direct curve-end labels wherever it draws as a line.
# code/make_ladder_questions.py::CAUSES carries the same four values.
CATEGORIES = [
    ("crosscutting", "Catastrophe & disempowerment", "#3a4150"),
    ("incident",     "AI incident types",            "#33a8bd"),
]


def by_role(role: str) -> list[dict]:
    """MODELS entries carrying `role`, in MODELS order."""
    return [m for m in MODELS if role in m["roles"]]


def demo_set_with_eci(include_gap_fillers: bool = False) -> list[dict]:
    """Join the demo ladder (+ optional gap-fillers) to ECI, sorted ascending.

    Byte-exact port of code/eci_scores.py::demo_set_with_eci -- same dict shape
    (model_id, label, epoch_name, access, eci, ci_low, ci_high), same sort, same
    values. Consumed by run_eval.py and make_demo_combined.py.
    """
    roles = {"g4_ladder"} | ({"g4_gapfiller"} if include_gap_fillers else set())
    rows = [m for m in MODELS if roles & set(m["roles"])]
    out = [{"model_id": m["litellm_id"], "label": m["label"], "epoch_name": m["epoch_name"],
            "access": m["litellm_id"].split("/", 1)[0], "eci": m["eci"],
            "ci_low": m["ci_low"], "ci_high": m["ci_high"]}
           for m in rows]
    return sorted(out, key=lambda r: r["eci"])


# archive/legacy-questions/run_forecasts.py's frontier five and
# code/make_demo_graph1.py's MODEL_COLORS share this exact order (by ECI
# descending, as both files had it hand-typed) -- not derivable by sorting
# since it isn't ascending, so it's pinned explicitly.
_FRONTIER_ORDER = ["claude-fable-5", "gpt-5.5", "claude-opus-4-8", "gemini-3.1-pro", "grok-4.20"]



def frontier_models() -> list[tuple[str, str]]:
    """(label, litellm_id) pairs in the legacy runner's original MODELS order
    (archive/legacy-questions/run_forecasts.py): the hand-picked panel the
    series ran on until 2026-08-28."""
    by = {m["key"]: m for m in MODELS}
    return [(by[k]["label"], by[k]["litellm_id"]) for k in _FRONTIER_ORDER]


# ── The panel: top-k by ECI, from the newest snapshot ────────────────────────
# k = 4. ~/Projects/forecastbench-ensembling: averaging the top 3-4 by ECI
# beats the single best-ranked model and closes the gap to the hindsight-best
# one; at 5 the marginal model is already below the frontier. Ties at the cut
# are broken by Epoch's own rank order and WARNed, so a panel that hinges on
# a coin-flip says so in the log. ONE SEAT PER FAMILY (2026-09-08): a model
# whose family already holds a seat is passed over, named in a WARN, and the
# next runnable model takes the seat -- two versions of one model are one
# opinion twice, not two members (see `family` in fri_forecaster.panel).
PANEL_K = _panel.PANEL_K
PANEL_SET = _panel.PANEL_SET


def _warn(msg):
    print(f"WARN: {msg}", file=sys.stderr)


@functools.lru_cache(maxsize=None)
def _select(k, snapshot):
    """-> (members, warnings): members are (registry row, index record) pairs,
    best first. The rule is fri_forecaster.panel.select; this binds it to
    AIRO's rows and snapshots. Cached per (k, snapshot) so a build that asks
    five views' worth of times reads the CSV once and warns once."""
    day, path = snapshot
    chosen, warnings = _panel.select(_eci.ranked(path), MODELS, k, path.name, _eci.stale_message())
    for w in warnings:
        _warn(w)
    return tuple(chosen), tuple(warnings)


def panel(k=PANEL_K, snapshot=None):
    """The model panel: the k highest-ECI runnable models in the newest
    snapshot, best first, as (registry row, index record) pairs. Prints a
    WARN for a stale snapshot, an unrunnable model above the cut, or a tie
    at it (once per process per snapshot)."""
    snapshot = snapshot or _eci.latest()
    members, _ = _select(k, snapshot)
    return list(members)


def snapshot_of(rows):
    """(date, path) of the snapshot the newest stamped row's panel was chosen
    from, or None when no row carries one or that file is not in data/."""
    stamped = [r for r in rows if (r.get("panel") or {}).get("snapshot")]
    if not stamped:
        return None
    newest = max(stamped, key=lambda r: (r.get("run_date") or "", r.get("elicited_at") or ""))
    day = date.fromisoformat(newest["panel"]["snapshot"])
    path = _eci.snapshot_path(day)
    return (day, path) if path.exists() else None


@functools.lru_cache(maxsize=None)
def record_snapshot():
    """(date, path) of the snapshot the newest scheduled run (results/runs/)
    chose its panel from; the newest snapshot when no run says."""
    from .runlog import RUNS_DIR
    for p in sorted(RUNS_DIR.glob("*.jsonl"), reverse=True):
        with open(p, encoding="utf-8") as f:
            first = next((line for line in f if line.strip()), None)
        snap = snapshot_of([json.loads(first)]) if first else None
        if snap:
            return snap
    return _eci.latest()


def published_panel(k=PANEL_K, rows=None):
    """The panel the DASHBOARD draws: the one the newest run was chosen as
    (its rows' stamped snapshot -- `rows` if given, else results/runs/),
    not panel(), the one the NEXT run will be. Since 2026-10-01 the index is
    fetched before every run, so the two differ from the fetch until that
    run lands; the views must not blank or recolor in between. Same rule,
    same registry: a past run's panel is re-derived from its snapshot."""
    snap = (snapshot_of(rows) if rows is not None else None) or record_snapshot()
    return panel(k, snap)


def panel_warnings(k=PANEL_K, snapshot=None):
    snapshot = snapshot or _eci.latest()
    return list(_select(k, snapshot)[1])


def unseated(k=PANEL_K):
    """Why a NEW run may not go ahead on the newest snapshot's panel
    (fri_forecaster.panel.unseated). -> (problems, omitted): a top-k model
    that cannot be run though its lab's key is held fails the run; one whose
    lab's key is not held is left out of the ensemble."""
    day, path = _eci.latest()
    return _panel.unseated(_eci.ranked(path), MODELS, k, path.name)


def eci_topk_models() -> list[tuple[str, str]]:
    """(label, litellm_id) pairs for the panel, ECI-descending."""
    return [(m["label"], m["litellm_id"]) for m, _ in panel()]


def panel_provenance(model_set=PANEL_SET, k=PANEL_K):
    """What a run should stamp on its rows: which set, and for the panel,
    which snapshot chose it and how old that was."""
    if model_set != PANEL_SET:
        return {"set": model_set}
    day, path = _eci.latest()
    return {"set": model_set, "k": k, "snapshot": day.isoformat(),
            "age_days": _eci.age_days(),
            "members": [{"label": m["label"], "eci": r["eci"], "rank": r["rank"]}
                        for m, r in panel(k)]}


MODEL_SETS = {PANEL_SET: eci_topk_models, "frontier5": frontier_models}
DEFAULT_MODEL_SET = PANEL_SET


# Every model outside the current panel draws in this one muted gray, on
# every chart (project lead, 2026-09-08: current models keep a consistent
# color scheme everywhere; deprecated models, out of the ensemble, are shown
# in gray). A panel member's color is its registry row's, the same on every
# surface; a model that leaves the panel turns gray everywhere the next
# build, and its row keeps its color for the day it returns. Apart from the
# ink (#1f2328), the faint ink (#6e7781) and the model palette.
RETIRED_COLOR = "#a3a9b1"


def color_for(model: dict, members=None) -> str:
    """The color a chart draws `model` (a MODELS row) in: its own if it holds
    a panel seat, RETIRED_COLOR otherwise."""
    if members is None:
        members = {m["key"] for m, _ in published_panel()}
    return model["color"] if model["key"] in members else RETIRED_COLOR


def model_colors() -> list[tuple[str, str]]:
    """(label, color) for every model the views may draw: the published panel
    (published_panel) first, in panel order and in its own colors, then every other registry
    model by ECI descending (newest snapshot's value where it has one, the
    pinned one otherwise), all in RETIRED_COLOR.

    A superset on purpose. The run log holds the retired panels' history and
    the current one's future; a view iterates this list and skips models
    absent from its data, so a panel change needs no edit here.
    """
    members = [m["key"] for m, _ in published_panel()]
    by_key = {m["key"]: m for m in MODELS}
    current = {r["model"]: r["eci"] for r in _eci.ranked(record_snapshot()[1])}
    rest = sorted((m for m in MODELS if m["key"] not in members),
                  key=lambda m: (-current.get(m["epoch_name"], m["eci"]), m["label"]))
    return [(by_key[k]["label"], by_key[k]["color"]) for k in members] + \
           [(m["label"], RETIRED_COLOR) for m in rest]


def main(argv=None):
    """`python -m redlines.registry [K]`: the panel's top K runnable models (default
    PANEL_K), best first, one per line as `<Epoch name> TAB <pi model id> TAB <lab>`:
    the panel as forecastbench.names sync reads it, so a ForecastBench round on
    this machine runs the same ensemble as the AIRO runs do, less any model
    whose lab's key the caller's keys file lacks. Exits 1 when a model in the
    index's top PANEL_K cannot be run though its key is held: no other model
    stands in."""
    from .pi_loop import pi_model
    argv = sys.argv[1:] if argv is None else argv
    k = int(argv[0]) if argv else PANEL_K
    from fri_forecaster import keys
    problems, omitted = unseated()   # the panel itself (PANEL_K), however many are printed
    for note in omitted:
        print(f"NOTE: {note}", file=sys.stderr)
    if problems:
        sys.exit("FATAL: the ensemble cannot be seated, and no other model stands in: " + "; ".join(problems))
    for m, r in panel(k):
        model = pi_model(m["litellm_id"])
        if not keys.held(model.split("/", 1)[0]):   # a row from another keys file (AIRO's), no key in this one
            print(f"NOTE: {r['model']} is left out of the ensemble: no API key for {model.split('/', 1)[0]} here", file=sys.stderr)
            continue
        print(r["model"], model, r.get("organization") or "", sep="\t")


if __name__ == "__main__":
    main()
