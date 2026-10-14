// FRI Forecaster: the pi extension. Generic over what is being forecast.
//
// Factored out of code/pi_harness/redlines_tools.ts (2026-10-05). The
// driver (harness.py) writes $FORECASTER_OUT/spec.json:
//
//   tool_cli        absolute path of tool_cli.py (the research tools)
//   research_tools  which of web_search / read_page to offer ([] = no research)
//   min_research    research calls that must return before submitting
//   tools           {name: {description}} for every tool offered
//   cell_schema     JSON schema of ONE forecast cell
//   key_fields      fields of a cell that identify it, e.g. ["question_id","horizon"]
//   allowed_keys    every wanted key, fields joined by "|"
//   final_extra     {name: JSON schema} extra properties of submit_forecast
//
// Imports match the pi the harness is pinned to (harness.py
// PINNED_PI_VERSION; package.json: @earendil-works/pi-coding-agent 0.99.2).
//
// Tools: the research tools shell out to the Python implementations
// (tools.py, via tool_cli.py) so every harness shares one search
// stack; submit_cells appends pieces to pieces.jsonl; submit_forecast writes
// final.json. The driver merges them.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execFileSync } from "node:child_process";
import { appendFileSync, readFileSync, writeFileSync } from "node:fs";

const OUT = process.env.FORECASTER_OUT;
if (!OUT) throw new Error("FORECASTER_OUT is not set (the driver sets it)");
const PY = process.env.FORECASTER_PY || "python3";
const spec = JSON.parse(readFileSync(`${OUT}/spec.json`, "utf8"));
const keyFields: string[] = spec.key_fields;
const allowed = new Set<string>(spec.allowed_keys);
const minResearch: number = spec.min_research;
let research = 0;        // research calls that returned without an error
let researchFailed = 0;  // ...and those that did: they do NOT count toward the floor
const received = new Map<string, any>();
const cap = (s: string, n = 8000) => (s.length > n ? s.slice(0, n) : s);
const keyOf = (f: any) => keyFields.map((k) => String(f?.[k])).join("|");

function py(tool: string, args: any) {
  const out = execFileSync(PY, [spec.tool_cli, tool, JSON.stringify(args)],
    { encoding: "utf8", maxBuffer: 64 * 1024 * 1024, env: process.env });
  return JSON.parse(out);
}

function notYet(name: string) {
  return { content: [{ type: "text" as const, text: JSON.stringify({ error: `${name} is not offered yet: ${minResearch - research} more successful research call(s) must return first (${research} of ${minResearch} so far; ${researchFailed} failed)` }) }], details: {}, isError: true };
}

function missing() {
  return [...allowed].filter((k) => !received.has(k));
}

let finalDone = false;   // one final answer per call
let finalWarned = false; // one chance to fix unknown/missing keys, then accepted as is
const cells = Type.Array(Type.Unsafe<any>(spec.cell_schema));

export default function (pi: ExtensionAPI) {
  const research_tools: string[] = spec.research_tools;
  if (research_tools.includes("web_search")) pi.registerTool({
    name: "web_search", label: "web_search",
    description: spec.tools.web_search.description,
    parameters: Type.Object({
      query: Type.String(),
      max_results: Type.Optional(Type.Integer({ minimum: 1, maximum: 10 })),
      recent_days: Type.Optional(Type.Integer({ minimum: 1 })),
    }),
    async execute(_id, params) {
      const r = py("web_search", params);
      if (r && !r.error) research += 1; else researchFailed += 1;
      return { content: [{ type: "text", text: cap(JSON.stringify(r)) }], details: r };
    },
  });
  if (research_tools.includes("read_page")) pi.registerTool({
    name: "read_page", label: "read_page",
    description: spec.tools.read_page.description,
    parameters: Type.Object({ url: Type.String(), offset: Type.Optional(Type.Integer({ minimum: 0 })) }),
    async execute(_id, params) {
      const r = py("read_page", params);
      if (r && !r.error) research += 1; else researchFailed += 1;
      return { content: [{ type: "text", text: cap(JSON.stringify(r)) }], details: r };
    },
  });
  if (spec.tools.submit_cells) pi.registerTool({
    name: "submit_cells", label: "submit_cells",
    description: spec.tools.submit_cells.description,
    parameters: Type.Object({ forecasts: cells }),
    async execute(_id, params: any) {
      if (research < minResearch) return notYet("submit_cells");
      let n = 0;
      for (const f of params.forecasts || []) {
        if (f && typeof f === "object" && allowed.has(keyOf(f))) {
          received.set(keyOf(f), f);
          n += 1;
        }
      }
      appendFileSync(`${OUT}/pieces.jsonl`, JSON.stringify({ t: Date.now(), accepted: n, forecasts: params.forecasts }) + "\n");
      const miss = missing();
      const r = { accepted: n, received: received.size, of: allowed.size, missing: miss.length, missing_first: miss.slice(0, 20) };
      return { content: [{ type: "text", text: JSON.stringify(r) }], details: r };
    },
  });
  const finalProps: Record<string, any> = {
    forecasts: Type.Optional(cells),
    rationale: Type.String(),
    key_sources: Type.Optional(Type.Array(Type.String())),
  };
  for (const [k, s] of Object.entries(spec.final_extra || {})) finalProps[k] = Type.Unsafe<any>(s);
  pi.registerTool({
    name: "submit_forecast", label: "submit_forecast",
    description: spec.tools.submit_forecast.description,
    parameters: Type.Object(finalProps),
    async execute(_id, params: any) {
      if (research < minResearch) return notYet("submit_forecast");
      if (finalDone) return { content: [{ type: "text" as const, text: JSON.stringify({ error: "submit_forecast was already called; stop here." }) }], details: {}, isError: true };
      const unknown = (params.forecasts || []).filter((f: any) => !allowed.has(keyOf(f))).map(keyOf);
      const have = new Set([...received.keys(), ...(params.forecasts || []).map(keyOf).filter((k: string) => allowed.has(k))]);
      const stillMissing = [...allowed].filter((k) => !have.has(k));
      if ((unknown.length || stillMissing.length) && !finalWarned) {
        finalWarned = true;
        return { content: [{ type: "text" as const, text: JSON.stringify({ error: "not submitted: fix and call submit_forecast again", unknown_keys: unknown, missing_keys: stillMissing }) }], details: {}, isError: true };
      }
      finalDone = true;
      writeFileSync(`${OUT}/final.json`, JSON.stringify({ t: Date.now(), research, research_failed: researchFailed, answer: params }, null, 1));
      const r = { ok: true, received: received.size, of: allowed.size, in_final: (params.forecasts || []).length };
      return { content: [{ type: "text", text: JSON.stringify(r) + " Done: stop here." }], details: r };
    },
  });
}
