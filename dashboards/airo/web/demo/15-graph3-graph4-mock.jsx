/* ============================ resolution / calibration ============================ */
function deciles(samples) {
  const s = [...samples].sort((a, b) => a.pred - b.pred);
  const N = s.length, G = 10, pts = [];
  const obar = s.reduce((a, x) => a + x.out, 0) / N;
  let res = 0;
  for (let g = 0; g < G; g++) {
    const lo = Math.floor(g * N / G), hi = Math.floor((g + 1) * N / G);
    const sl = s.slice(lo, hi);
    const mp = sl.reduce((a, x) => a + x.pred, 0) / sl.length;
    const mo = sl.reduce((a, x) => a + x.out, 0) / sl.length;
    pts.push({ pred: mp, obs: mo, n: sl.length });
    res += sl.length * (mo - obar) ** 2;
  }
  const brier = s.reduce((a, x) => a + (x.pred - x.out) ** 2, 0) / N;
  return { pts, resolution: res / N, brier, base: obar, spread: pts[9].pred - pts[0].pred };
}

// intermediate events: model predictions compressed toward 0.5 (low resolution) + noisy; superforecasters sharp.
function simIntermediate() {
  const rng = mulberry32(20260622);
  const model = [], sup = [];
  for (let k = 0; k < 3000; k++) {
    const q = 0.02 + 0.95 * rng();
    const out = rng() < q ? 1 : 0;
    model.push({ pred: clamp(0.5 + (q - 0.5) * 0.6 + (rng() - 0.5) * 0.34, 0.01, 0.99), out });
    sup.push({ pred: clamp(q + (rng() - 0.5) * 0.12, 0.01, 0.99), out });
  }
  return { model: deciles(model), sup: deciles(sup) };
}
// rare events (1–9¢ contracts): models over-forecast the tail; superforecasters near truth.
function simRare() {
  const rng = mulberry32(424242);
  const model = [], sup = [];
  for (let k = 0; k < 4000; k++) {
    const q = 0.004 + 0.095 * rng() * rng();
    const out = rng() < q ? 1 : 0;
    model.push({ pred: clamp(q * 1.9 + 0.006 + (rng() - 0.5) * 0.02, 0.001, 0.18), out });
    sup.push({ pred: clamp(q * 1.05 + (rng() - 0.5) * 0.008, 0.001, 0.18), out });
  }
  const m = deciles(model), s = deciles(sup);
  const base = (m.base + s.base) / 2;
  const brierRef = base * (1 - base); // climatology / base-rate reference
  m.bss = 1 - m.brier / brierRef; s.bss = 1 - s.brier / brierRef; m.ref = base; s.ref = base;
  return { model: m, sup: s, brierRef, base };
}
const INTER = simIntermediate();
const RARE = simRare();

// Live calibration results (injected by code/make_demo_graph3.py from ForecastBench).
const G3_RAW = (typeof window !== "undefined" && window.__GRAPH3__) || null;
// Every series the panel draws must be present with real decile points, or we
// fall back to the mock. Keep this list in step with the series in make_demo_graph3.py.
// The blob also ships a "bare" (zero-shot, no retrieval) series; it is NOT
// drawn — two green lines differing only by dash read as confusing (Nick,
// 2026-08-13) — its numbers live in the panel footnotes instead. Only the
// two drawn series are gated here.
const G3 = (G3_RAW && ["panel", "tools", "sup"].every(
  k => G3_RAW[k] && Array.isArray(G3_RAW[k].pts) && G3_RAW[k].pts.length
       && G3_RAW[k].split)) ? G3_RAW : null;

// Chart-ready series array for CalibrationChart (the 80-app.jsx call site's
// `series` prop): our grounded pipeline proxy vs the superforecasters.
// "panel" is the dashboard's own selection rule replayed on ForecastBench (top-4
// by ECI among the bench's bare configs each round, median-pooled; see
// redlines/views/graph3.py). "tools" is the maker-submitted Grok 4.20 / Gemini
// tournament systems, kept as a muted line for the retrieval comparison; it is
// NOT our panel (Nick, 2026-09-02).
const G3_SERIES = G3 ? [
  { key: "panel", color: "var(--dash)", data: G3.panel },
  { key: "super", color: "var(--super)", data: G3.sup },
  { key: "tools", color: "var(--ink-faint)", data: G3.tools, muted: true },
] : null;

// Live low-probability results (injected by code/make_demo_data.py from the real eval).
const G4 = (typeof window !== "undefined" && window.__GRAPH4__) || null;
const G4_SERIES = G4
  ? G4.models.map(m => ({ key: m.key, color: m.color, data: { pts: m.pts } }))
  : [{ key: "model", color: "var(--model)", data: RARE.model }, { key: "super", color: "var(--super)", data: RARE.sup }];
const G4_DOMAIN = G4 ? G4.domainMax : 0.1;
const G4_BASE = G4 ? G4.base : RARE.base;
const G4_SC = G4 ? G4.scatter : [];
const G4_FRONTIER = G4 ? G4_SC[G4_SC.length - 1] : null;   // highest ECI
const G4_BEST = G4 ? G4_SC.reduce((a, b) => (b.bss > a.bss ? b : a)) : null;
const G4_WORST = G4 ? G4_SC.reduce((a, b) => (b.bss < a.bss ? b : a)) : null;
const G4_GRAD = G4 ? "linear-gradient(90deg, " + G4.models.map(m => m.color).join(", ") + ")" : "";

