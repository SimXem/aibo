#!/usr/bin/env python3
"""Generate data/leap_policies.json from the LEAP Wave 12 survey documents.

LEAP Wave 12 ("Safety Policies", FRI, internal draft dated 2026-08-26) asks
its panel to forecast AI-caused catastrophe by 2050 CONDITIONAL on each of
several policies being in force. We ask our models the same conditionals, on
our own question set, with LEAP's wording. This script is the only place that
wording enters the repo: every scenario the runner can be asked, the text it
prepends to the prompt, and the sentence that tells the model HOW to
scenario, all come out of the two vendored documents under data/leap/.

    python3 code/make_leap_policies.py           # writes data/leap_policies.json
    python3 code/make_leap_policies.py --check    # verify the file is current

WHAT IS PARSED AND WHAT IS AUTHORED

  parsed     every policy's summary, background, historical baseline,
             resolution criteria, parts and dates (wave12-policies-*.md), and
             the conditioning instruction, horizon line and frontier-model
             definition (wave12-survey-*.md). Verbatim, less Google-Docs
             export escapes and bold/italic markers.
  authored   SCENARIOS below: which (policy, part) pairs become a scenario
             we run, their ids and short labels. Eight of them — the status
             quo, P1, both parts of P2 and P3, P4, and the P5 bundle. O1 and
             O2 are LEAP's OUTCOMES, not policies; they are parsed for the
             record (they are the questions our catastrophe:ai and
             ladder:ai:1M rows line up with) but are never a scenario.

NOTHING IS RECONCILED. LEAP's conditioning clause says the policy "remains in
effect through December 31, 2050" and LEAP elicits the outcome at 2050 only.
Our batch also asks 2100. The clause is carried as written — a 2100 cell
elicited under it is a forecast under a policy the prompt does not extend
past 2050, which is why the analysis reports 2030 and 2050 by default and
marks 2100. Rewording the clause for our horizons would buy a cleaner 2100
at the cost of the only comparison that exists, the LEAP panel's 2050.
"""
import argparse
import hashlib
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
POLICIES_MD = os.path.join(ROOT, "data", "leap", "wave12-policies-2026-08-26.md")
SURVEY_MD = os.path.join(ROOT, "data", "leap", "wave12-survey-2026-08-26.md")
OUT = os.path.join(ROOT, "data", "leap_policies.json")

SOURCE = {
    "panel": "LEAP",
    "wave": "Wave 12: Safety Policies",
    "status": "internal draft, received 2026-08-27; the fielded instrument may differ",
    "documents": [os.path.relpath(POLICIES_MD, ROOT), os.path.relpath(SURVEY_MD, ROOT)],
    "outcome_horizons": ["2050"],
    "policy_probability_horizons": ["2030", "2050"],
}

# The eight scenarios we run. (id, LEAP section, part, short label).
# A part is one of a policy's mutually exclusive variants — LEAP's (a)/(b).
SCENARIOS = [
    ("sq", "Status Quo", None, "Status quo (no new substantial AI policy)"),
    ("p1", "P1", None, "Federal preemption of state AI laws"),
    ("p2a", "P2", "a", "Compute cap on frontier R&D: US alone"),
    ("p2b", "P2", "b", "Compute cap on frontier R&D: US + China"),
    ("p3a", "P3", "a", "Pre-release authorization: US federal body"),
    ("p3b", "P3", "b", "Pre-release authorization: international body incl. US + China"),
    ("p4", "P4", None, "Federal strict liability, scaled insurance, punitive damages"),
    ("p5", "P5", None, "Bundle: P2b + P3b + P4"),
]
# P5 is defined by LEAP as "Policies 2b, 3b, 4". The bundle's description is
# those three policies' descriptions, in that order.
BUNDLE = [("P2", "b"), ("P3", "b"), ("P4", None)]

_HEADER = re.compile(r"^## (?:(O[12]|P[1-5])\. (.+)|(Status Quo))\s*$")
_ESCAPES = {r"\.": ".", r"\)": ")", r"\(": "(", r"\[": "[", r"\]": "]",
            r"\-": "-", r"\#": "#", r"\_": "_", r"\+": "+", r"\&": "&"}


def clean(line):
    """Drop Google-Docs export artefacts: a stray '## ' prefix, backslash
    escapes, bold/italic markers, trailing double-space line breaks."""
    if line.startswith("## "):
        line = line[3:]
    elif line == "##":
        line = ""
    for k, v in _ESCAPES.items():
        line = line.replace(k, v)
    line = re.sub(r"\*{2,3}(.+?)\*{2,3}", r"\1", line)
    line = re.sub(r" ", " ", line)
    return line.rstrip()


def unitalic(s):
    s = s.strip()
    if s.startswith("*") and s.endswith("*") and not s.startswith("* "):
        s = s[1:-1]
    return s.strip()


def sections(path):
    """-> {key: {"title", "lines"}} in document order, key = 'O1'..'P5'/'Status Quo'."""
    out, key = {}, None
    for raw in open(path, encoding="utf-8").read().splitlines():
        m = _HEADER.match(raw)
        if m:
            key = m.group(1) or m.group(3)
            out[key] = {"title": (m.group(2) or key).strip(), "lines": []}
            continue
        if key:
            out[key]["lines"].append(clean(raw))
    return out


def _paragraphs(lines):
    paras, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln)
        elif cur:
            paras.append("\n".join(cur))
            cur = []
    if cur:
        paras.append("\n".join(cur))
    return paras


def parse_policy(key, sec):
    lines = sec["lines"]
    doc = {"leap_id": key, "title": sec["title"]}
    text = "\n".join(lines)
    m = re.search(r"\*Dates: ([^*]+)\*", text)
    doc["dates"] = [d.strip() for d in m.group(1).split(",")] if m else []

    # Summary: the first italic paragraph that is not a field label.
    for ln in lines:
        s = ln.strip()
        if (s.startswith("*") and s.endswith("*") and not s.startswith("* ")
                and not re.match(r"\*(Dates|Quantiles|Parts|Note)", s)):
            doc["summary"] = unitalic(s)
            break

    # Parts: numbered bold lines after "*Parts:*".
    parts = []
    in_parts = False
    for ln in lines:
        s = ln.strip()
        if s == "*Parts:*":
            in_parts = True
            continue
        if in_parts:
            pm = re.match(r"(\d+)\. (.+)", s)
            if pm:
                parts.append(pm.group(2).strip())
            elif s.startswith("*Note that these parts"):
                doc["parts_note"] = unitalic(s)
            elif s and not pm:
                in_parts = False
    if parts:
        doc["parts"] = {chr(ord("a") + i): p for i, p in enumerate(parts)}

    def field(label):
        i = next((n for n, ln in enumerate(lines)
                  if ln.strip().lower().startswith(label.lower())), None)
        if i is None:
            return None
        j = next((n for n in range(i + 1, len(lines))
                  if re.match(r"(Background|Historical baseline|Resolution [Cc]riteria)",
                              lines[n].strip())), len(lines))
        chunk = lines[i:j]
        chunk[0] = re.sub(r"^" + re.escape(label) + r":?\s*", "", chunk[0].strip(), flags=re.I)
        return "\n\n".join(_paragraphs(chunk)).strip()

    for lbl, k in (("Background", "background"),
                   ("Historical baseline", "historical_baseline"),
                   ("Resolution criteria", "resolution_criteria")):
        v = field(lbl)
        if v:
            doc[k] = v
    if key == "Status Quo":
        paras = _paragraphs(lines)
        doc["text"] = next(p for p in paras if p.startswith("Assume"))
        doc["note"] = next(p for p in paras if p.startswith("Note that"))
    # Nested emphasis ("**... *Unconditional***") leaves a stray asterisk
    # after the bold strip. Drop any asterisk that is not a bullet marker.
    for k, v in doc.items():
        if isinstance(v, str):
            doc[k] = re.sub(r"(?<![\n ])\*(?![ *])|(?<=\s)\*(?=[^\s*])", "", v)
    return doc


def parse_survey(path):
    text = open(path, encoding="utf-8").read()
    def grab(pattern):
        m = re.search(pattern, text, re.M)
        return clean(m.group(1)) if m else None
    return {
        "instruction": grab(r"^\* \*\*Conditional\*\*\. (.+)$"),
        "unconditional": grab(r"^\* \*\*Unconditional\.\*\* (.+)$"),
        "horizon": grab(r"^- \*\*Horizon:\*\* (.+)$"),
        "frontier_model": grab(r"^- \*\*Frontier model:\*\* (.+)$"),
        "outcome_question": grab(r"^\*\*In this question, we ask you to (.+)\*\*$"),
        "policy_probability_question": grab(r"^1\. \*\*(What is the probability that the relevant governing.+)\*\*\s*$"),
        "similarity_clause": grab(r"^(To account for the fact that there may be policies.+)$"),
    }


def describe(p, part=None):
    """The policy as a LEAP panelist sees it on the Policies tab."""
    out = [f"{p['leap_id']}. {p['title']}", f"Summary: {p['summary']}"]
    if part:
        out.append(f"Part ({part}) is assumed: {p['parts'][part]}"
                   + (f" ({p['parts_note']})" if p.get("parts_note") else ""))
    for lbl, k in (("Background", "background"),
                   ("Historical baseline", "historical_baseline"),
                   ("Resolution criteria", "resolution_criteria")):
        if p.get(k):
            out.append(f"{lbl}:\n{p[k]}")
    return "\n\n".join(out)


def build():
    secs = sections(POLICIES_MD)
    policies = {k: parse_policy(k, s) for k, s in secs.items()}
    survey = parse_survey(SURVEY_MD)
    # LEAP's definition of the unconditional forecast lives in the Status Quo
    # note ("conceptually distinct from Unconditional, for which you should
    # forecast the world as you expect it to unfold ..."). The joint instrument
    # labels its unconditional column with it, verbatim.
    m = re.search(r"for which you should (forecast the world[^.]*\.)",
                  policies.get("Status Quo", {}).get("note") or "")
    survey["unconditional_forecast"] = m.group(1) if m else None
    missing = [k for k, v in survey.items() if not v]
    if missing:
        sys.exit(f"survey parse failed for {missing} in {SURVEY_MD}")
    for k in ("P1", "P2", "P3", "P4", "P5", "Status Quo", "O1", "O2"):
        if k not in policies:
            sys.exit(f"section {k} not found in {POLICIES_MD}")
    for k in ("P1", "P2", "P3", "P4"):
        for f in ("summary", "background", "historical_baseline", "resolution_criteria"):
            if not policies[k].get(f):
                sys.exit(f"{k} is missing {f}")
    for k in ("P2", "P3"):
        if set(policies[k].get("parts", {})) != {"a", "b"}:
            sys.exit(f"{k} should have parts a and b")

    one_liners = "\n".join(f"- {policies[k]['leap_id']}: {policies[k]['summary']}"
                           for k in ("P1", "P2", "P3", "P4", "P5"))
    scenarios = []
    for cid, key, part, label in SCENARIOS:
        p = policies[key]
        c = {"id": cid, "leap_id": key + (f" ({part})" if part else ""),
             "label": label, "policy": key, "part": part}
        if key == "Status Quo":
            c["assume"] = p["text"]
            c["description"] = (f"{p['note']}\n\nThe policies listed in this "
                                f"survey, for the stringency comparison:\n{one_liners}")
        elif key == "P5":
            c["assume"] = p["summary"]
            c["description"] = "\n\n---\n\n".join(
                describe(policies[k], pt) for k, pt in BUNDLE)
        else:
            c["assume"] = p["summary"] if not part else (
                f"{p['summary']} Part ({part}): {p['parts'][part]}")
            c["description"] = describe(p, part)
        scenarios.append(c)

    return {
        "title": "LEAP Wave 12 policy conditions, as the runner prepends them",
        "source": SOURCE,
        "generated_by": os.path.relpath(__file__, ROOT),
        "conditioning": survey,
        "conditions": scenarios,
        "policies": policies,
        "notes": {
            "horizon": ("LEAP's clause keeps the policy in force through 2050 "
                        "and elicits the outcome at 2050 only. Our 2030 cells "
                        "have no human counterpart; our 2100 cells are elicited "
                        "under a clause that does not extend past 2050. Carried "
                        "verbatim, not reworded — see code/make_leap_policies.py."),
            "outcomes": ("O1/O2 are LEAP's outcome questions, not conditions. O1 "
                         "pairs with catastrophe:ai (both: AI proximate cause, "
                         "10% of population, 5-year window from 2025-12-31); O2 "
                         "pairs loosely with ladder:ai:1M (LEAP: deaths only, "
                         "5-year window; ours: deaths or $10T, 3-year window)."),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    if not os.path.exists(POLICIES_MD):
        # A public clone: the LEAP source under data/leap/ is internal and not
        # published, so the set cannot be regenerated or checked here; the
        # tracked file stands as is. Tests skip on this exit code.
        sys.exit(f"{os.path.relpath(POLICIES_MD, ROOT)} is not present (internal LEAP source); "
                 "the tracked scenario set stands as is")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    doc = build()
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if args.check:
        cur = open(args.out, encoding="utf-8").read() if os.path.exists(args.out) else ""
        if cur != text:
            sys.exit(f"{args.out} is stale — rerun {os.path.relpath(__file__, ROOT)}")
        print("ok")
        return
    open(args.out, "w", encoding="utf-8").write(text)
    for c in doc["conditions"]:
        h = hashlib.sha256(c["description"].encode()).hexdigest()[:8]
        print(f"  {c['id']:4} {c['leap_id']:12} {len(c['description']):6d} chars  {h}  {c['label']}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
