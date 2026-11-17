// EEAI's charts, two views of one question on one frame (frame, endLabels,
// hover are shared):
//
// drawTimeline: a question's history, then the panel's medians at each
// horizon -- either the unconditional forecast (dashed, with its 80% band
// where the survey asks for one) or, split by AI progress, one line per
// scenario and no unconditional line. A date whose outcome is in the record
// (horizon.actual) keeps its forecast as a ring beside the outcome, tied to
// it by a stem: the length of the stem is the miss. A filled dot is a date
// still ahead; a ring is a date whose outcome is in. The survey
// asks for points, not paths: the lines only join the latest data to those
// points.
//
// drawHistory: how the forecast for ONE date has moved, run by run -- x is
// when the panel was asked, y what it said; the outcome, once the record has
// it, is a level line across.
const SCEN = [
  { id: "slow", label: "Slow progress", color: "var(--slow)" },
  { id: "moderate", label: "Moderate progress", color: "var(--moderate)" },
  { id: "rapid", label: "Rapid progress", color: "var(--rapid)" },
];
const UNCOND = { id: "unconditional", label: "Unconditional", color: "var(--uncond)" };
const NS = "http://www.w3.org/2000/svg";

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid);
  return el;
}
function s(tag, attrs, text) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) el.setAttribute(k, v);
  if (text != null) el.textContent = text;
  return el;
}

function fmt(q, v, bare) {
  if (v == null) return "–";
  const n = v.toLocaleString("en-US", { minimumFractionDigits: q.decimals, maximumFractionDigits: q.decimals });
  if (q.unit.includes("US$")) return "$" + n;
  return q.unit.startsWith("%") && !bare ? n + "%" : n;
}
// A miss, signed, to one more decimal than the values beside it (so 2.5 against 2.5 can read −0.07).
const missText = (q, d) => (d >= 0 ? "+" : "−") + fmt({ ...q, decimals: q.decimals ? q.decimals + 1 : 0 }, Math.abs(d), true);
const yearOf = d => +d.slice(0, 4) + (+d.slice(5, 7) - 1) / 12;
const val = (q, hz, sc, p) => (((q.ensemble || {})[hz] || {})[sc] || {})[p || "p50"];

function niceTicks(lo, hi, n) {
  const span = hi - lo || 1, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(m => m >= raw);
  const out = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-6; t += step) out.push(+t.toFixed(10));
  return out;
}

// The frame both views share: the svg, the scales, the y grid and the baseline.
function frame(box, q, size, x0, x1, ys) {
  const hero = size === "hero";
  const W = Math.max(240, box.clientWidth || 600);
  const H = hero ? Math.max(300, Math.min(460, W * 0.5)) : 150;
  const labels = hero && W >= 620;
  const m = { l: hero ? 50 : 34, r: labels ? 178 : 14, t: 14, b: 26 };
  let lo = Math.min(...ys), hi = Math.max(...ys);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.12; lo -= pad; hi += pad;
  const X = v => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r), Y = v => m.t + (hi - v) / (hi - lo) * (H - m.t - m.b);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  // Tick labels carry as many decimals as the step between them needs, so no two read the same.
  const ticks = niceTicks(lo, hi, hero ? 5 : 4), gap = ticks.length > 1 ? ticks[1] - ticks[0] : 1;
  let decimals = 0;
  while (decimals < 4 && Math.abs(gap * 10 ** decimals - Math.round(gap * 10 ** decimals)) > 1e-6) decimals++;
  for (const t of ticks) {
    svg.append(s("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), stroke: "var(--line-soft)" }));
    // Thousands are written short ($80k): the full figure does not fit beside a small chart.
    const label = gap >= 1000 ? fmt({ ...q, decimals: 0 }, t / 1000, true) + "k" : fmt({ ...q, decimals }, t, true);
    svg.append(s("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, label));
  }
  svg.append(s("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: "var(--line)" }));
  const path = pts => pts.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(" ");
  return { svg, X, Y, W, H, m, hero, labels, x0, x1, path,
    tick: (x, text) => svg.append(s("text", { x: X(x), y: H - 6, "text-anchor": "middle" }, text)),
    // (class "fc": a forecast mark; the page fades those in when a control redraws the chart)
    dot: (x, y, sc, ring) => svg.append(s("circle", { class: "fc", cx: X(x), cy: Y(y), r: hero ? 4.5 : 3.5,
      fill: ring ? "var(--panel)" : sc.color, stroke: ring ? sc.color : "var(--panel)", "stroke-width": 2 })) };
}

// Each series named at its last point (the hero chart, when it is wide enough).
function endLabels(f, q, ends) {
  if (!f.labels) return;
  ends.sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) ends[i].ly = Math.max(ends[i].y, (ends[i - 1].ly ?? ends[i - 1].y) + 17);
  for (const e of ends) f.svg.append(s("text", { class: "end", x: e.x + 12, y: (e.ly ?? e.y) + 4,
    "font-weight": e.sc.id === "unconditional" ? 600 : 400 }, `${e.sc.label} ${fmt(q, e.v)}`));
}

// Hover: a crosshair on the nearest stop ({x, ...}) and a tooltip of rows(stop).
const tipRow = (label, text) => h("div", { class: "row" }, h("i", {}, label), h("span", { class: "mono" }, text));
const withRange = (q, v, p10, p90) => fmt(q, v) + (p10 != null && p90 != null ? `  (${fmt(q, p10, true)} to ${fmt(q, p90, true)})` : "");
// Who said what: the panel's median and each model's own median, a column per series shown.
// `models` is one run's {model: {horizon: {scenario: {p50}}}}; `order` lists the models as the panel ranks them.
function breakdown(q, series, hz, median, models, order) {
  const labels = Object.keys(models || {}).sort((a, b) => ((order || []).indexOf(a) + 1 || 99) - ((order || []).indexOf(b) + 1 || 99));
  const grid = h("div", { class: "who", style: `grid-template-columns: auto repeat(${series.length}, auto)` });
  if (series.length > 1) grid.append(h("span", {}), ...series.map(sc => h("i", {}, h("u", { style: `background: ${sc.color}` }), sc.label.replace(" progress", ""))));
  grid.append(h("b", {}, "Panel median"), ...series.map(sc => h("b", { class: "mono" }, median(sc))));
  for (const m of labels) grid.append(h("i", {}, m), ...series.map(sc =>
    h("span", { class: "mono" }, fmt(q, (((models[m] || {})[hz] || {})[sc.id] || {}).p50))));
  return grid;
}
// The run whose forecast for a date the page shows: the latest that asked about it.
const runFor = (q, hz) => q.series.filter(r => r.ensemble[hz]).pop() || {};
function hover(f, box, stops, rows) {
  const { svg, X, W, H, m } = f;
  const cross = s("line", { y1: m.t, y2: H - m.b, stroke: "var(--ink-faint)", "stroke-dasharray": "3 3", visibility: "hidden" });
  const hit = s("rect", { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: "transparent" });
  svg.append(cross, hit);
  const tip = h("div", { class: "tip", hidden: "" });
  const show = ev => {
    const r = svg.getBoundingClientRect(), k = W / r.width, px = (ev.clientX - r.left) * k;
    const xv = f.x0 + (px - m.l) / (W - m.l - m.r) * (f.x1 - f.x0);
    const st = stops.reduce((a, b) => Math.abs(b.x - xv) < Math.abs(a.x - xv) ? b : a);
    cross.setAttribute("x1", X(st.x)); cross.setAttribute("x2", X(st.x)); cross.setAttribute("visibility", "visible");
    tip.replaceChildren(...rows(st).filter(Boolean));
    tip.hidden = false;
    const left = X(st.x) / k, tw = tip.offsetWidth;
    tip.style.left = Math.max(0, Math.min(r.width - tw, left + (left + tw + 14 > r.width ? -tw - 10 : 10))) + "px";
    tip.style.top = "6px";
  };
  hit.addEventListener("pointermove", show);
  hit.addEventListener("pointerdown", show);
  hit.addEventListener("pointerleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); });
  box.replaceChildren(svg, tip);
}

function drawChart(box, q, opts) {
  return opts.view === "history" ? drawHistory(box, q, opts) : drawTimeline(box, q, opts);
}

function drawTimeline(box, q, opts) {
  const hero = opts.size === "hero";
  const horizons = q.horizons.filter(z => +z.id <= +opts.horizon);
  const ahead = horizons.filter(z => !z.actual), settled = horizons.filter(z => z.actual);
  const series = opts.split ? SCEN : [UNCOND];
  const x0 = hero ? 2000 : 2008, hist = q.history.map(([d, v]) => [yearOf(d), v, d]).filter(p => p[0] >= x0);
  const last = hist[hist.length - 1];
  const x1 = Math.max(...horizons.map(z => +z.id), last ? last[0] : 0) + (hero ? 0.6 : 0.8);
  const ys = hist.map(p => p[1]);
  for (const z of horizons) for (const sc of series) for (const p of ["p10", "p50", "p90"]) {
    const v = val(q, z.id, sc.id, p);
    if (v != null && (p === "p50" || sc.id === "unconditional")) ys.push(v);
  }
  const f = frame(box, q, opts.size, x0, x1, ys), { svg, X, Y } = f;
  svg.setAttribute("aria-label", `${q.short}: history and the panel's median forecasts. The table under "Model forecasts and rationale" has the numbers.`);
  const step = x1 - x0 > 30 ? 10 : 5;
  for (let yr = Math.ceil(x0 / step) * step; yr <= x1; yr += step) f.tick(yr, yr);
  if (!last) { box.replaceChildren(svg); return; }
  const band = opts.split ? [] : ahead.filter(z => val(q, z.id, "unconditional", "p10") != null && val(q, z.id, "unconditional", "p90") != null);
  if (band.length) {
    const up = [[last[0], last[1]]].concat(band.map(z => [+z.id, val(q, z.id, "unconditional", "p90")]));
    const dn = band.map(z => [+z.id, val(q, z.id, "unconditional", "p10")]).reverse();
    svg.append(s("path", { class: "fc", d: f.path(up.concat(dn)) + " Z", fill: "var(--band)" }));
  }
  if (hist.length > 1) svg.append(s("path", { d: f.path(hist), fill: "none", stroke: "var(--ink)", "stroke-width": hero ? 2 : 1.6, "stroke-linejoin": "round" }));
  svg.append(s("circle", { cx: X(last[0]), cy: Y(last[1]), r: hero ? 4 : 3, fill: "var(--ink)", stroke: "var(--panel)", "stroke-width": 2 }));
  const ends = [];
  for (const sc of series) {
    const un = sc.id === "unconditional";
    for (const z of settled) {
      const v = val(q, z.id, sc.id), xa = yearOf(z.actual.date);
      if (v == null) continue;
      const p10 = val(q, z.id, sc.id, "p10"), p90 = val(q, z.id, sc.id, "p90");
      if (un && p10 != null && p90 != null) svg.append(s("line", { class: "fc", x1: X(xa), x2: X(xa), y1: Y(p10), y2: Y(p90), stroke: "var(--band)", "stroke-width": 7, "stroke-linecap": "round" }));
      svg.append(s("line", { class: "fc", x1: X(xa), x2: X(xa), y1: Y(z.actual.value), y2: Y(v), stroke: sc.color, "stroke-width": 1.5, opacity: 0.6 }));
      f.dot(xa, v, sc, true);
    }
    const pts = ahead.map(z => [+z.id, val(q, z.id, sc.id)]).filter(p => p[1] != null);
    if (!pts.length) continue;
    svg.append(s("path", { class: "fc", d: f.path([[last[0], last[1]]].concat(pts)), fill: "none", stroke: sc.color,
      "stroke-width": 2, "stroke-dasharray": un ? "6 5" : null, "stroke-linecap": "round" }));
    for (const p of pts) f.dot(p[0], p[1], sc);
    ends.push({ sc, y: Y(pts[pts.length - 1][1]), x: X(pts[pts.length - 1][0]), v: pts[pts.length - 1][1] });
  }
  endLabels(f, q, ends);
  // The stops: a data point, or a date asked about (its outcome's point, once there is one).
  const done = new Set(settled.map(z => z.actual.date));
  const stops = hist.filter(p => !done.has(p[2])).map(p => ({ x: p[0], hist: p }))
    .concat(horizons.map(z => ({ x: z.actual ? yearOf(z.actual.date) : +z.id, hz: z })));
  const kind = opts.split ? "" : " · unconditional";
  hover(f, box, stops, st => {
    if (st.hist) return [h("b", {}, st.hist[2].slice(0, 4)), tipRow("Actual", fmt(q, st.hist[1]))];
    const z = st.hz, who = runFor(q, z.id).models;
    if (!z.actual) return [h("b", {}, `Forecast for ${z.id}${kind}`),
      breakdown(q, series, z.id, sc => withRange(q, val(q, z.id, sc.id), val(q, z.id, sc.id, "p10"), val(q, z.id, sc.id, "p90")), who, opts.order)];
    const a = z.actual.value;
    return [h("b", {}, `${z.id}: forecast and outcome${kind}`), tipRow("Outcome", fmt(q, a)),
      breakdown(q, series, z.id, sc => { const v = val(q, z.id, sc.id); return fmt(q, v) + (v == null ? "" : `  (${missText(q, v - a)})`); }, who, opts.order),
      z.asked && tipRow("Forecast made", z.asked)];
  });
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function drawHistory(box, q, opts) {
  const z = q.horizons.find(z => z.id === opts.target), series = opts.split ? SCEN : [UNCOND];
  const at = (r, sc, p) => ((r.ensemble[z.id] || {})[sc.id] || {})[p || "p50"];
  const runs = q.series.filter(r => series.some(sc => at(r, sc) != null)).map(r => ({ ...r, x: Date.parse(r.at) / 864e5 }));
  if (!runs.length) { box.replaceChildren(h("p", { class: "empty" }, `No forecast for ${z.id} yet.`)); return; }
  const span = runs[runs.length - 1].x - runs[0].x, pad = span ? span * 0.06 : 1;
  const ys = z.actual ? [z.actual.value] : [];
  for (const r of runs) for (const sc of series) for (const p of ["p10", "p50", "p90"])
    if (at(r, sc, p) != null && (p === "p50" || sc.id === "unconditional")) ys.push(at(r, sc, p));
  const f = frame(box, q, opts.size, runs[0].x - pad, runs[runs.length - 1].x + pad, ys), { svg, X, Y } = f;
  svg.setAttribute("aria-label", `${q.short}: how the panel's median forecast for ${z.id} has changed from run to run.`);
  // A run's label is its date -- with the year once the runs span one, and the time when two share a day.
  const days = runs.map(r => r.date), clock = new Set(days).size < days.length, years = span > 300;
  const name = r => `${+r.date.slice(8, 10)} ${MONTHS[+r.date.slice(5, 7) - 1]}` + (years ? ` ${r.date.slice(0, 4)}` : "")
    + (clock && days.filter(d => d === r.date).length > 1 ? ` ${r.at.slice(11, 16)}` : "");
  let edge = -Infinity;
  for (const r of runs) {
    const w = name(r).length * 6.6 + 14;                 // about the label's width at 12px
    if (X(r.x) - w / 2 < edge) continue;
    f.tick(r.x, name(r)); edge = X(r.x) + w / 2;
  }
  const band = opts.split ? [] : runs.filter(r => at(r, UNCOND, "p10") != null && at(r, UNCOND, "p90") != null);
  if (band.length > 1) svg.append(s("path", { class: "fc", fill: "var(--band)",
    d: f.path(band.map(r => [r.x, at(r, UNCOND, "p90")]).concat(band.map(r => [r.x, at(r, UNCOND, "p10")]).reverse())) + " Z" }));
  else for (const r of band) svg.append(s("line", { class: "fc", x1: X(r.x), x2: X(r.x), y1: Y(at(r, UNCOND, "p10")), y2: Y(at(r, UNCOND, "p90")),
    stroke: "var(--band)", "stroke-width": 9, "stroke-linecap": "round" }));
  if (z.actual) {
    svg.append(s("line", { x1: f.m.l, x2: f.W - f.m.r, y1: Y(z.actual.value), y2: Y(z.actual.value), stroke: "var(--ink)", "stroke-width": 1.6 }));
    svg.append(s("text", { class: "end", x: f.m.l + 6, y: Y(z.actual.value) - 6 }, `Outcome ${fmt(q, z.actual.value)}`));
  }
  const ends = [];
  for (const sc of series) {
    const pts = runs.filter(r => at(r, sc) != null).map(r => [r.x, at(r, sc)]);
    if (!pts.length) continue;
    if (pts.length > 1) svg.append(s("path", { class: "fc", d: f.path(pts), fill: "none", stroke: sc.color, "stroke-width": 2,
      "stroke-dasharray": sc.id === "unconditional" ? "6 5" : null, "stroke-linecap": "round", "stroke-linejoin": "round" }));
    for (const p of pts) f.dot(p[0], p[1], sc);
    ends.push({ sc, y: Y(pts[pts.length - 1][1]), x: X(pts[pts.length - 1][0]), v: pts[pts.length - 1][1] });
  }
  endLabels(f, q, ends);
  hover(f, box, runs, r => [h("b", {}, `Asked ${r.date}` + (clock ? ` ${r.at.slice(11, 16)}` : "") + ` · forecast for ${z.id}` + (opts.split ? "" : ", unconditional")),
    breakdown(q, series, z.id, sc => withRange(q, at(r, sc), at(r, sc, "p10"), at(r, sc, "p90")), r.models, opts.order),
    z.actual && tipRow("Outcome", fmt(q, z.actual.value))]);
}
