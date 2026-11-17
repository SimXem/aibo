#!/usr/bin/env python3
"""Generate the historical-event severity markers for Graph 2's severity axis.

WHY THIS EXISTS. The paper's lead author, 2026-08-17: show a CDF rather than a
PDF, with dashed lines for the Black Death, COVID and other historical events.
The reason was that a threshold stated in bare numbers tells a reader nothing
about whether the number is frightening -- a 1% chance of a COVID-scale event
is roughly the background pathogen risk, while a 1% chance of ten times that is
not. Graph 2 is already the exceedance curve asked for. This file supplies the
context marks it was missing.

THREE EVENTS, DELIBERATELY. COVID-19, the Black Death and World War II (project
lead, 2026-08-18: start with just these three, keep it simple). All three land
between 14M and 85M, so they anchor the right-hand third of the axis and nothing
below it. Adding a lower rung later -- Bhopal, Hiroshima and Nagasaki, the 2004
tsunami -- is one dict in EVENTS; an event carries whichever legs it has.

PLUS ONE DAMAGES-ONLY EVENT (project lead, 2026-09-10): NotPetya, the 2017 wiper,
drawn as a single line at its ~$10B damages figure. It has no deaths, so it
appears on the damages ladder alone, where it anchors the foot of that axis
between the $2.2B and $22B rungs, which nothing else does. It is a point, not
a band: the $10B is one official estimate, not a published range, and the
note says so.

PLUS TWO DEFINITIONAL REFERENCE MARKS (lead author's notes, 2026-08-19: extend the
severity graph toward extinction, include "Extinction", and show the Black
Death as a population share and as a death count separately). "Black Death
(25% of population)" and "Extinction" are not historical tolls -- each is a
share of the people alive TODAY, drawn at the question set's own population
basis (`population_basis()`) so these marks and the 10%-of-population
catastrophe questions can never disagree about how many people are alive.
They carry kind="reference" and are points, not bands, deliberately: a band
would assert an estimate where there is only arithmetic; whether the Black
Death truly killed a quarter of the world belongs in the note. Their job is
the top decade of the axis, which the events above cannot reach: in absolute
deaths the Black Death sits beside COVID-19, while as a share of humanity it
was ~2.5x the 10% catastrophe threshold -- exactly what an absolute-deaths
axis cannot show without them.

EVERY NUMBER HERE IS A RANGE, AND IS DRAWN AS ONE. The Black Death's European
toll spans 25-50 million depending on the assumed mortality rate; World War II
spans 70-85 million across compilations. A dashed line at a single value would
assert a precision the historiography does not have, so each event carries
(low, central, high) and Graph 2 renders a shaded band.

WHERE AN EVENT SITS. Since 2026-10-19 the ladder is two ladders, deaths and
damages, asked apart, and an event is drawn on the ladder(s) whose figure it
has: COVID-19 on both (14.8M excess deaths; $12.5T output loss), NotPetya on
the damages ladder alone, the Black Death, World War II and the two reference
marks on the deaths ladder alone. Nothing is converted between the two. (Until
then one deaths-OR-damages question per rung put every mark on one axis at
max(deaths, damages / the ladder's $2.2M value of a statistical life).)

THESE MARKS ARE NOT COMPARABLE TO THE CURVES, AND THE PANEL SAYS SO. Every
curve on Graph 2 is the probability of an AI-RELATED incident inside a horizon
window. All three events below are non-AI, and all three accumulated over years
the rolling windows do not span. They calibrate the severity axis. They are not
base rates for the quantity being forecast, and CAVEAT is rendered under the
chart so no reader takes them for one.

SOURCING. There is no single machine-readable feed spanning these three: WHO
covers COVID-19, World War II exists only as a compilation of national
estimates, and the Black Death exists only in the historiography. So this is a
hand-curated table in which every row carries its own citation, checked on the
date in `verified`. Prefer the upstream source over an aggregator when citing.

    python3 code/make_historical_events.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "historical_events.json"
CROSSCUTTING = (Path(__file__).resolve().parent.parent
                / "data" / "autoarc_crosscutting.json")

VERIFIED = "2026-08-18"

CAVEAT = (
    "These marks locate historical events and two definitional reference "
    "points on the severity axis. They are NOT comparable to the curves: "
    "every curve is the probability of an AI-related incident inside one "
    "horizon window, while the historical events are non-AI and accumulated "
    "over years. Bands show the range across published estimates, not "
    "measurement error; the reference marks (Black Death as a population "
    "share, Extinction) are definitions drawn at today's population, not "
    "tolls. Each mark appears only on the ladder(s) it has a figure for."
)

# deaths / damages_usd are {low, central, high}. Omit `damages_usd` where no
# credible aggregate figure exists -- an event is drawn on the ladder(s) it
# has a figure for, so a missing leg simply does not appear there.
EVENTS = [
    {
        "id": "notpetya",
        "label": "NotPetya (~$10B damages)",
        "short": "NotPetya: $10B",
        "span": "2017",
        "basis": "damages only — the White House's ~$10B estimate",
        "deaths": None,
        "damages_usd": {"low": 10e9, "central": 10e9, "high": 10e9},
        "verified": "2026-09-10",
        "source": {
            "org": "White House estimate, as reported by Wired (Greenberg, "
                   "2018)",
            "title": "The Untold Story of NotPetya, the Most Devastating "
                     "Cyberattack in History: \"more than $10 billion in "
                     "total damages\" (Tom Bossert, then Homeland Security "
                     "adviser)",
            "url": "https://www.wired.com/story/notpetya-cyberattack-ukraine-russia-code-crashed-the-world/",
        },
        "note": "DAMAGES ONLY: no deaths are attributed to NotPetya, so it "
                "appears on the damages ladder alone, at $10B. The $10B is "
                "a single U.S. government estimate in 2017 dollars (the "
                "rungs are stated in 2026 USD; inflating it would move the "
                "mark a few percent, invisible on a log axis). Disclosed "
                "corporate write-downs alone (Merck, Maersk, FedEx/TNT, "
                "Saint-Gobain, Mondelez) sum to over $3B. It is here to show "
                "where the costliest cyberattack on record sits: near the "
                "foot of the damages ladder.",
    },
    {
        "id": "covid-19",
        "label": "COVID-19",
        "short": "COVID-19",
        "span": "2020-2021",
        "basis": "excess mortality, the accounting the ladder's criteria ask for",
        "deaths": {"low": 13.23e6, "central": 14.83e6, "high": 16.58e6},
        "damages_usd": {"low": 12.5e12, "central": 12.5e12, "high": 22e12},
        "source": {
            "org": "World Health Organization",
            "title": "Global excess deaths associated with COVID-19, "
                     "January 2020 - December 2021: 14.83M (13.23-16.58M)",
            "url": "https://www.who.int/data/stories/global-excess-deaths-associated-with-covid-19-january-2020-december-2021",
        },
        "note": "Excess mortality, not the ~7M laboratory-confirmed deaths — the "
                "ladder's criteria ask for excess mortality attributable to the "
                "event. On the damages ladder it is drawn at the IMF's cumulative "
                "output loss, $12.5T over 2020-21 rising to $22T through 2025.",
    },
    {
        "id": "black-death",
        "label": "Black Death (Europe)",
        "short": "Black Death",
        "span": "1347-1352",
        "basis": "European deaths at 40-60% mortality of a ~80M population",
        "deaths": {"low": 25e6, "central": 35e6, "high": 50e6},
        "damages_usd": None,
        "source": {
            "org": "Benedictow 2004; Alfani & Murphy 2017, Journal of "
                   "Economic History 77(1), 314-343",
            "title": "The Black Death 1346-1353: The Complete History "
                     "(up to 60% mortality), reviewed against the 40-60% "
                     "range in Plague and Lethal Epidemics in the "
                     "Pre-Industrial World",
            "url": "https://www.cambridge.org/core/journals/journal-of-economic-history/article/plague-and-lethal-epidemics-in-the-preindustrial-world/1D2D564AD8560ABACAF9D81A65F27CED",
        },
        "note": "EUROPE ONLY. Global tolls of 75-200M circulate but rest on "
                "far weaker evidence. In absolute deaths this lands beside "
                "COVID-19; as a share of the population it is orders of "
                "magnitude worse, which is precisely what an absolute-deaths "
                "axis cannot show.",
    },
    {
        "id": "world-war-ii",
        "label": "World War II",
        "short": "World War II",
        "span": "1939-1945",
        "basis": "total military and civilian deaths",
        "deaths": {"low": 70e6, "central": 77e6, "high": 85e6},
        "damages_usd": None,
        "source": {
            "org": "Compiled national estimates; battle-death subset in the "
                   "Correlates of War project",
            "title": "The 70-85M range synthesises national archives, postwar "
                     "demographic studies and census-loss estimates; only the "
                     "~16.6M battle-death subset comes from a single dataset",
            "url": "https://correlatesofwar.org/data-sets/COW-war/",
        },
        "note": "This is a compilation, not one source. It is included because "
                "it is the reference point every reader already has for "
                "'the worst thing that has happened', and excluding it would "
                "leave the top of the axis unanchored.",
    },
]


def population_basis():
    """The population the reference marks are drawn against.

    Read from the question set itself -- the same `world_pop` that converts
    "10% of population" into 820M for the catastrophe questions -- never
    retyped here, so the marks and the questions cannot disagree about how
    many people are alive. If the question set moves its basis, these marks move
    with it on the next regeneration.
    """
    return json.loads(CROSSCUTTING.read_text())["world_pop"]


# The conventional "quarter of the world's population" summary of the Black
# Death. The share itself is soft -- see the mark's note -- but the MARK is
# definitional: this share, applied to the people alive today.
BLACK_DEATH_WORLD_SHARE = 0.25


def reference_marks(pop):
    """The two kind="reference" marks, computed against `pop`.

    Points (low = central = high), not bands: a band would dress arithmetic
    up as an estimate. The historiographic uncertainty lives in the notes.
    """
    bn = f"~{pop / 1e9:.1f}B"
    cat = f"{pop * 0.10 / 1e6:.0f}M"
    share_deaths = BLACK_DEATH_WORLD_SHARE * pop
    point = lambda v: {"low": v, "central": v, "high": v}  # noqa: E731
    return [
        {
            "id": "black-death-share",
            "kind": "reference",
            "label": "Black Death (25% of population)",
            "short": "Black Death 25%",
            "span": "1347-1352 share, at today's population",
            "basis": f"25% of the {bn} alive today",
            "deaths": point(share_deaths),
            "damages_usd": None,
            "verified": "2026-08-19",
            "source": {
                "org": "U.S. Census Bureau, Historical Estimates of World "
                       "Population (compiling Biraben, Durand, McEvedy & "
                       "Jones); Alchon 2003",
                "title": "Compiled world-population estimates fall from "
                         "~443-475M on the eve of the plague to 350-375M "
                         "after it",
                "url": "https://www.census.gov/data/tables/time-series/demo/international-programs/historical-est-worldpop.html",
            },
            "note": "DEFINITIONAL, not a second death toll: the conventional "
                    "'quarter of the world's population' summary of the Black "
                    "Death, applied to the people alive today. The share "
                    "rests on medieval demography (world population estimates "
                    "fall from ~443-475M to ~350-375M across the plague "
                    "century — roughly a sixth to a quarter), evidence far "
                    "weaker than the Europe-only band this file also draws. "
                    "The mark exists to show scale: as a count the Black "
                    "Death sits beside COVID-19; as a share of humanity it "
                    "was ~2.5x the 10% catastrophe threshold.",
        },
        {
            "id": "extinction",
            "kind": "reference",
            "label": "Extinction",
            "short": "Extinction",
            "span": "hypothetical",
            "basis": f"everyone alive — the question set's {bn} population "
                     "basis",
            "deaths": point(pop),
            "damages_usd": None,
            "verified": "2026-08-19",
            "source": {
                "org": "United Nations, World Population Prospects 2024",
                "title": f"World population {bn} — the figure the question "
                         "set carries as world_pop and converts '10% of "
                         f"population' through ({cat})",
                "url": "https://population.un.org/wpp/",
            },
            "note": "Not an event and not an estimate: the position is "
                    "simply the number of people alive, on the same "
                    "population basis as the catastrophe questions. It tops "
                    "out the severity axis so a reader can see how far the "
                    "1B rung and the Black Death's population share still "
                    "sit from everyone.",
        },
    ]


def check_bands(ev):
    """An event has at least one leg, and every band it has is ordered."""
    if not ev["deaths"] and not ev["damages_usd"]:
        raise ValueError(f"{ev['id']}: no deaths and no damages — unplaceable")
    for leg in ("deaths", "damages_usd"):
        band = ev[leg]
        if band and not band["low"] <= band["central"] <= band["high"]:
            raise ValueError(f"{ev['id']}: {leg} band not ordered: {band}")


def build():
    events = []
    for ev in EVENTS + reference_marks(population_basis()):
        check_bands(ev)
        events.append({
            "id": ev["id"],
            "kind": ev.get("kind", "event"),
            "label": ev["label"],
            "short": ev["short"],
            "span": ev["span"],
            "basis": ev["basis"],
            "deaths": ev["deaths"],
            "damages_usd": ev["damages_usd"],
            "source": ev["source"],
            "note": ev["note"],
            "verified": ev.get("verified", VERIFIED),
        })
    # The deaths ladder's order; a damages-only mark has no place in it and leads.
    events.sort(key=lambda e: (e["deaths"] or {}).get("central", 0))
    return {
        "title": "Historical events, placed on the Auto-ARC severity ladders",
        "provenance": {
            "requested_by": "Jason Abaluck, 2026-08-17 call; reference marks "
                            "from his 2026-08-19 notes",
            "scope": "COVID-19, Black Death and World War II "
                     "(Nick, 2026-08-18), plus two definitional reference "
                     "marks — Black Death as a population share, and "
                     "Extinction — at the question set's population basis "
                     "(Jason, 2026-08-19), plus NotPetya on the damages ladder "
                     "(Nick, 2026-09-10).",
            "curated_by": "this project — hand-curated, one citation per row",
            "generated_by": "code/make_historical_events.py",
            "verified": VERIFIED,
            "status": "Figures checked against the cited sources on the "
                      "`verified` date. Re-check before the paper is frozen.",
        },
        "caveat": CAVEAT,
        "events": events,
    }


if __name__ == "__main__":
    blob = build()
    OUT.write_text(json.dumps(blob, indent=2) + "\n")
    print(f"{len(blob['events'])} events -> {OUT.name}")
