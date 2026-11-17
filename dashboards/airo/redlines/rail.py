"""The Graph-1-style question rail, in one place so every panel that draws it
draws the same one.

Graph 1 and the Timeline both rail the whole question set grouped by the
workbook's Category column, and both must agree — on which questions exist, on
what each category is called, and on each rung's label. They drifted once
already (Graph 1 listed one rung per incident while Graph 2 drew eight; the two
graphs named the same causes differently). This module is the single source for
all three, built from the ladder spec, so a question-set change relabels every
panel from here.
"""
from .questions import (cause_category, ladder_index, load_crosscutting, severity_label)

# The dot colour for the cross-cutting categories (catastrophe / disempowerment).
CROSS_COLOR = "#3a4150"

# The rail's two sections. Every panel that groups questions uses these
# words (Graph 1, the Timeline, the Conditional-on tab).
GROUP_CROSS = "Cross-cutting"
GROUP_DOMAIN = "Domain-specific"


def panel_questions(spec):
    """The whole set in rail order: cross-cutting first, then every incident
    question, cause by cause, leg by leg (deaths, then damages) and rung by
    rung — not just the featured 1M rungs."""
    index = ladder_index(spec)
    order = []
    for c in spec["causes"]:
        for leg in spec["legs"]:
            for r in spec["rungs"]:
                q = index.get((c["key"], r["short"], leg["key"]))
                if q:
                    order.append(q)
    return load_crosscutting() + order


def cause_meta(spec):
    """key -> {label, color} for each incident cause, the category name read
    from the SSOT (questions.cause_category) so it matches Graph 2's curves."""
    return {c["key"]: {"label": cause_category(c), "color": c["color"]}
            for c in spec["causes"]}


def rail_meta(q, meta):
    """(category-key, category-label, category-colour, rail-label) for one
    question. The category label is the workbook's 'Category' — the incident
    sheet name for a rung, the question's own name for a cross-cutting one;
    the rail label is the rung's severity for an incident, the name otherwise."""
    if q.get("category") == "crosscutting":
        label = q.get("name") or q.get("short")
        return (f"cross:{q['id']}", label, CROSS_COLOR, label)
    cm = meta[q["cause"]]
    return (f"inc:{q['cause']}", cm["label"], cm["color"], severity_label(q))


def grouping(qs, spec):
    """-> (per_question, categories): `per_question[id]` is {category, railLabel}
    and `categories` is the ordered rail groups {key, label, color}. Both views
    build their questions from this, so their rails are identical by construction.
    """
    meta = cause_meta(spec)
    per_question, cat_index, cat_order = {}, {}, []
    for q in qs:
        cat_key, cat_label, cat_color, rail_label = rail_meta(q, meta)
        per_question[q["id"]] = {"category": cat_key, "railLabel": rail_label}
        if cat_key not in cat_index:
            cat_index[cat_key] = {"key": cat_key, "label": cat_label,
                                  "color": cat_color,
                                  # The rail's two sections (project lead, 2026-08-27):
                                  # the cross-cutting questions, then the
                                  # per-cause rows.
                                  "group": GROUP_CROSS if cat_key.startswith("cross:")
                                           else GROUP_DOMAIN}
            cat_order.append(cat_key)
    return per_question, [cat_index[k] for k in cat_order]
