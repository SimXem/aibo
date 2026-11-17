/* ============================ conditional benches (FAQ tab, was "Why trust this?": Graphs 5 and 6) ============================ */
// Two skill-vs-capability charts on the same x-axis (the ECI roster of
// data/causal/models.csv; redlines/roster.py): the observational conditional
// bench (weather pairs; redlines/views/observational.py) and the StarSim causal
// bench (redlines/views/causal.py). Each dot is one model; the dashboard's own
// panel is drawn in its own colours (gray for the rest) and always labelled, the rest of the
// roster in grey with the ends of the range labelled and everything on hover.
const OBS = (typeof window !== "undefined" && window.__OBSERVATIONAL__) || null;
const CAUSAL = (typeof window !== "undefined" && window.__CAUSAL__) || null;

// A tie-aware rank correlation, mirroring redlines/stats.py::spearman_ties
// (average ranks for ties -- scipy's convention, which both benches' published
// numbers use), so a chart's own rho matches its blob's.
function _rankCorrTies(xs, ys) {
  const n = xs.length;
  if (n < 2) return 0;
  const ranks = v => {
    const order = v.map((_, i) => i).sort((a, b) => v[a] - v[b]);
    const r = new Array(n);
    let i = 0;
    while (i < n) {
      let j = i;
      while (j + 1 < n && v[order[j + 1]] === v[order[i]]) j++;
      for (let k = i; k <= j; k++) r[order[k]] = (i + j) / 2 + 1;
      i = j + 1;
    }
    return r;
  };
  const rx = ranks(xs), ry = ranks(ys);
  const mx = rx.reduce((a, b) => a + b, 0) / n, my = ry.reduce((a, b) => a + b, 0) / n;
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < n; i++) { num += (rx[i] - mx) * (ry[i] - my); dx += (rx[i] - mx) ** 2; dy += (ry[i] - my) ** 2; }
  const den = Math.sqrt(dx * dy);
  return den ? num / den : 0;
}

const fmtSigned = v => (v == null ? "n/a" : (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2));

// Generic model-vs-ECI scatter. `points` need {label, eci, inPanel} and the y
// field named by `yKey`. `band` = {lo, hi, line, label} shades a reference
// band (the noise ceiling); `refs` = [{y, label, color}] draws dashed
// reference lines (climatology / the simulator's own distribution). `tip(pt)`
// returns tooltip HTML.
function BenchScatter({ points, yKey, yDomain, yTicks, yLabel, yFmt, band, refs, tip }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!window.tippy || !ref.current) return;
    const nodes = ref.current.querySelectorAll("[data-tippy-content]");
    const inst = appTooltip(nodes, { allowHTML: true });
    return () => inst.forEach(i => i.destroy());
  }, [points]);
  const box = React.useRef(null);
  const W = Math.max(300, useContainerWidth(box, 430)), H = 340;   // measured; web/shared/responsive.jsx
  const pad = { l: 46, r: 16, t: 16, b: 42 };
  const drawn = points.filter(p => p[yKey] != null);
  const xs = drawn.map(p => p.eci);
  const xmin = Math.floor((Math.min(...xs) - 2) / 5) * 5, xmax = Math.ceil((Math.max(...xs) + 2) / 5) * 5;
  const [ymin, ymax] = yDomain;
  const x = v => pad.l + (v - xmin) / (xmax - xmin) * (W - pad.l - pad.r);
  const y = v => pad.t + (1 - (Math.min(Math.max(v, ymin), ymax) - ymin) / (ymax - ymin)) * (H - pad.t - pad.b);
  const xticks = []; for (let v = Math.ceil(xmin / 10) * 10; v <= xmax; v += 10) xticks.push(v);
  const fmt = yFmt || (v => v.toFixed(1));

  // Which dots get a label: the panel, the best, the worst, the top of the
  // ladder. Everything else is on hover -- with two dozen models, labelling
  // all of them is what makes the roster unreadable.
  const best = drawn.reduce((a, b) => (b[yKey] > a[yKey] ? b : a));
  const worst = drawn.reduce((a, b) => (b[yKey] < a[yKey] ? b : a));
  const top = drawn.reduce((a, b) => (b.eci > a.eci ? b : a));
  const labelled = new Set(drawn.filter(p => p.inPanel).concat([best, worst, top]).map(p => p.label));

  // Greedy placement for the labelled subset, the same slot walk Graph 4 uses.
  const dots = drawn.map(p => ({ cx: x(p.eci), cy: y(p[yKey]) }));
  const SLOTS = [[0, -13, "middle"], [10, 3.5, "start"], [-10, 3.5, "end"], [0, 16, "middle"],
    [10, -9, "start"], [-10, -9, "end"], [10, 14, "start"], [-10, 14, "end"], [0, -25, "middle"], [0, 28, "middle"],
    // Further out, for the crowd at the top right (32 models on Graph 5, a
    // dozen of them within 0.05 of each other): wide sides and a third tier.
    [22, 3.5, "start"], [-22, 3.5, "end"], [22, -14, "start"], [-22, -14, "end"], [22, 20, "start"], [-22, 20, "end"],
    [36, 3.5, "start"], [-36, 3.5, "end"], [0, 40, "middle"], [14, 32, "start"], [-14, 32, "end"], [0, -37, "middle"]];
  // Boxes are padded (a label is 10px type on a 12px chip; "touching" is a
  // hit), and the panel's labels are placed first so they get the best slots.
  const boxOf = (lx, ly, w, anchor) => ({
    x0: (anchor === "start" ? lx : anchor === "end" ? lx - w : lx - w / 2) - 3,
    x1: (anchor === "start" ? lx + w : anchor === "end" ? lx : lx + w / 2) + 3, y0: ly - 11, y1: ly + 5 });
  const hits = (b, c) => !(b.x1 < c.x0 || b.x0 > c.x1 || b.y1 < c.y0 || b.y0 > c.y1);
  const taken = dots.map(d => ({ x0: d.cx - 7, x1: d.cx + 7, y0: d.cy - 7, y1: d.cy + 7 }));
  const labels = [];
  const order = drawn.map((pt, i) => [pt, i]).filter(([pt]) => labelled.has(pt.label))
    .sort((a, b) => (b[0].inPanel ? 1 : 0) - (a[0].inPanel ? 1 : 0));
  order.forEach(([pt, i]) => {
    const { cx, cy } = dots[i], w = pt.label.length * 6.1 + 2;
    let best = null;
    for (const [dx, dy, anchor] of SLOTS) {
      const ly = cy + dy;
      if (ly < pad.t + 4 || ly > H - pad.b - 2) continue;
      const lx = Math.min(Math.max(cx + dx, w / 2 + 2), W - w / 2 - 2);
      const b = boxOf(lx, ly, w, anchor);
      if (b.x0 < 2 || b.x1 > W - 2 || taken.some(t => hits(b, t))) continue;
      best = { lx, ly, anchor, box: b }; break;
    }
    if (!best) {
      // Nothing free: take the in-bounds slot that overlaps the least, rather
      // than always "above" (which is what put DeepSeek V4 Flash on top of Sol).
      let least = Infinity;
      for (const [dx, dy, anchor] of SLOTS) {
        const ly = Math.min(Math.max(cy + dy, pad.t + 4), H - pad.b - 2);
        const lx = Math.min(Math.max(cx + dx, w / 2 + 2), W - w / 2 - 2);
        const b = boxOf(lx, ly, w, anchor);
        const overlap = taken.reduce((a, t) => a + (hits(b, t) ? Math.max(0, Math.min(b.x1, t.x1) - Math.max(b.x0, t.x0)) * Math.max(0, Math.min(b.y1, t.y1) - Math.max(b.y0, t.y0)) : 0), 0);
        if (overlap < least) { least = overlap; best = { lx, ly, anchor, box: b }; }
      }
    }
    taken.push(best.box);
    labels.push({ pt, ...best, w });
  });

  return (
    <div ref={box} style={{ minWidth: 0 }}>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {xticks.map((v, i) => (
          <g key={"x" + i}>
            <line x1={x(v)} x2={x(v)} y1={pad.t} y2={H - pad.b} stroke="var(--line-soft)" />
            <text x={x(v)} y={H - pad.b + 15} textAnchor="middle" fontSize="10" fill="var(--ink-faint)" className="mono">{v}</text>
          </g>
        ))}
        {yTicks.map((v, i) => (
          <g key={"y" + i}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--line-soft)" />
            <text x={pad.l - 6} y={y(v) + 3} textAnchor="end" fontSize="10" fill="var(--ink-faint)" className="mono">{fmt(v)}</text>
          </g>
        ))}
        {band ? <g>
          <rect x={pad.l} y={y(band.hi)} width={W - pad.l - pad.r} height={Math.max(0, y(band.lo) - y(band.hi))} fill="var(--dash)" opacity="0.09" />
          <line x1={pad.l} x2={W - pad.r} y1={y(band.line)} y2={y(band.line)} stroke="var(--ink-soft)" strokeDasharray="5 4" />
          <text x={pad.l + 6} y={y(band.line) + 13} fontSize="9.5" fill="var(--ink-soft)">{band.label}</text>
        </g> : null}
        {(refs || []).map((r, i) => (
          <g key={"r" + i}>
            <line x1={pad.l} x2={W - pad.r} y1={y(r.y)} y2={y(r.y)} stroke={r.color} strokeDasharray="3 3" opacity="0.85" />
            <text x={W - pad.r} y={y(r.y) + (r.below ? 12 : -4)} textAnchor="end" fontSize="9.5" fill={r.color}>{r.label}</text>
          </g>
        ))}
        {drawn.map((p, i) => (
          <circle key={p.id || p.label} cx={dots[i].cx} cy={dots[i].cy} r={p.inPanel ? 6 : 4.5}
            fill={p.color || "var(--ink-faint)"} fillOpacity={p.inPanel ? 1 : 0.85}
            stroke="var(--panel)" strokeWidth="1.2" style={{ cursor: "pointer" }} data-tippy-content={tip(p)} />
        ))}
        {labels.map((L, i) => (
          <g key={"l" + i}>
            <rect x={L.anchor === "start" ? L.lx - 2 : L.anchor === "end" ? L.lx - L.w - 2 : L.lx - L.w / 2 - 2}
              y={L.ly - 9} width={L.w + 4} height={12} rx="2" fill="var(--panel)" opacity="0.85" />
            <text x={L.lx} y={L.ly} textAnchor={L.anchor} fontSize="10" fill={L.pt.inPanel ? "var(--ink)" : "var(--ink-soft)"}
              fontWeight={L.pt.inPanel ? 600 : 400}>{L.pt.label}</text>
          </g>
        ))}
        <text x={(pad.l + W - pad.r) / 2} y={H - 4} textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Epoch Capabilities Index (ECI) →</text>
        <text x={-H / 2} y={13} transform="rotate(-90)" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">{yLabel}</text>
      </svg>
      <div style={{ display: "flex", gap: 14, marginTop: 6, flexWrap: "wrap" }}>
        {/* Panel members in their own colours, the same as on every other
            chart; the rest of the roster in the one retired gray. Both come
            from the blob (redlines/roster.py; Nick, 2026-09-08). */}
        {drawn.filter(p => p.inPanel).map(p => <LegendDot key={p.id || p.label} color={p.color} label={p.label + " (panel)"} />)}
        <LegendDot color={(drawn.find(p => !p.inPanel) || {}).color || "var(--ink-faint)"} label="Other models on the ECI roster (hover for names)" />
      </div>
    </div>
  );
}

function ObservationalPanel({ embedded }) {
  const d = OBS;
  const pts = d.models;
  const rho = _rankCorrTies(pts.map(p => p.eci), pts.map(p => p.rho));
  const tip = p => `<div style="font-family:'Season Sans',sans-serif;font-size:12px;line-height:1.5">`
    + `<strong>${p.label}</strong> &nbsp;<span style="color:#888">ECI ${p.eci.toFixed(0)}</span><br>`
    + `Rank ρ, implied vs measured: <strong>${fmtSigned(p.rho)}</strong> (${p.pairsScored} pairs)<br>`
    + `<span style="color:#888">direction ${p.direction.k}/${p.direction.n} · control shift ${p.controlShift == null ? "n/a" : p.controlShift.toFixed(3)} `
    + `${p.pass ? "✓ passes" : "✕ fails"} the ${d.bar} bar · coherence ε ${p.coherence.toFixed(3)}</span>`
    + `<br><span style="color:#888">${p.responses} responses</span></div>`;
  const runDate = Array.isArray(d.run.due) ? d.run.due.join(", ") : d.run.due;
  // The axis starts at 0.5 when every model clears it (the four-model run
  // did) and drops in 0.1 steps to fit the weakest model otherwise -- GPT-3.5
  // answers 0.5 to everything and lands near 0. 0 = chance is always drawn
  // when it is in range.
  const minRho = Math.min(...pts.map(p => p.rho));
  const obsYMin = Math.min(0.5, Math.floor((minRho - 0.05) * 10) / 10);
  const obsYTicks = []; for (let v = obsYMin; v <= 1.0001; v += 0.1) obsYTicks.push(Math.round(v * 10) / 10);
  return (
    <FigFrame embedded={embedded}>
      <Eyebrow>Graph 5 · Conditional forecasts · real-world</Eyebrow>
      <h2 style={{ fontSize: 20, marginTop: 6, marginBottom: 4 }}>Conditionals (real-world)</h2>
      <p style={{ color: "var(--ink-soft)", fontSize: 13, marginTop: 0, marginBottom: 8 }}>
        Forecasting skill on pairs of ForecastBench weather questions that are near-duplicates, positively correlated,
        or independent in two years of resolution data. Tests conditional forecasting.
      </p>
      <BenchScatter points={pts} yKey="rho" yDomain={[obsYMin, 1.0]} yTicks={obsYTicks}
        yLabel="Rank ρ, implied vs measured association"
        band={{ lo: d.noise.lo, hi: d.noise.hi, line: d.noise.ceiling,
          label: `noise ceiling ${d.noise.ceiling.toFixed(2)} [${d.noise.lo.toFixed(2)}–${d.noise.hi.toFixed(2)}]` }}
        tip={tip} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--line-soft)" }}>
        <Stat label={`Capability ↔ skill (ρ), ${pts.length} models`} value={fmtSigned(rho)} color="var(--model)" />
        <Stat label={`Best — ${d.best.label}`} value={fmtSigned(d.best.rho)} color="var(--dash)" />
        <Stat label="Pass the pre-registered bar" value={`${d.nPass} of ${pts.length}`} color="var(--ink)" />
        <Stat label="Noise ceiling" value={d.noise.ceiling.toFixed(2)} color="var(--ink-soft)" />
      </div>
    </FigFrame>
  );
}

function CausalPanel({ embedded }) {
  const d = CAUSAL;
  const pts = d.models;
  const h = d.headline;
  const tip = p => `<div style="font-family:'Season Sans',sans-serif;font-size:12px;line-height:1.5">`
    + `<strong>${p.label}</strong> &nbsp;<span style="color:#888">ECI ${p.eci.toFixed(0)}</span><br>`
    + `Intervention skill, pooled: <strong>${p.recovered.toFixed(2)}</strong><br>`
    + `<span style="color:#888">by coverage — 25% ${p.perRung["25"].intervention == null ? "n/a" : p.perRung["25"].intervention.toFixed(2)} · `
    + `50% ${p.perRung["50"].intervention == null ? "n/a" : p.perRung["50"].intervention.toFixed(2)} · `
    + `90% ${p.perRung["90"].intervention == null ? "n/a" : p.perRung["90"].intervention.toFixed(2)}</span><br>`
    // The same model's skill on the no-vaccine question -- an easier forecast
    // it answered in a separate prompt -- NOT a base-rate forecaster (Ezra,
    // 2026-09-02, read "baseline" as one).
    + `<span style="color:#888">same model on the no-vaccine question: ${p.baseline == null ? "n/a" : p.baseline.toFixed(2)}</span></div>`;
  return (
    <FigFrame embedded={embedded}>
      <Eyebrow>Graph 6 · Conditional forecasts · simulated</Eyebrow>
      <h2 style={{ fontSize: 20, marginTop: 6, marginBottom: 4 }}>Interventions (simulated)</h2>
      <p style={{ color: "var(--ink-soft)", fontSize: 13, marginTop: 0, marginBottom: 8 }}>
        Forecasting skill on interventions (infection rates in a simulated epidemic conditional on a vaccine with a
        given efficacy and coverage rate). Tests forecasting on causal interventions.
      </p>
      <BenchScatter points={pts} yKey="recovered" yDomain={[-0.05, 1.05]} yTicks={[0, 0.25, 0.5, 0.75, 1.0]}
        yLabel="Intervention skill (share of recoverable CRPS)" yFmt={v => v.toFixed(2)}
        // The two anchors of the CRPS skill score, in words (Nick, 2026-09-03):
        // 1 = the simulator's own distribution for that world and vaccine; 0 =
        // the bench's fixed reference, the spread of outcomes pooled over every
        // world and coverage -- "climatology" in the dataset's own terms, a word
        // that confused two readers in one evening. Ignoring the vaccine scores
        // about -5 on this scale, far below the chart.
        refs={[{ y: 1, label: "true distribution", color: "var(--ink-faint)" },
               { y: 0, label: "guessing the all-worlds spread", color: "var(--warn-ink)", below: true }]}
        tip={tip} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--line-soft)" }}>
        <Stat label={`Capability ↔ skill (ρ), ${h.n} models`} value={fmtSigned(h.rho)} color="var(--model)" />
        <Stat label={`Best — ${d.best.label}`} value={d.best.recovered.toFixed(2)} color="var(--dash)" />
        <Stat label="Same models, no-vaccine question (ρ)" value={fmtSigned(h.baselineRho)} color="var(--ink-soft)" />
        <Stat label="p (intervention ρ)" value={h.p.toFixed(4)} color="var(--ink-soft)" />
      </div>
    </FigFrame>
  );
}
