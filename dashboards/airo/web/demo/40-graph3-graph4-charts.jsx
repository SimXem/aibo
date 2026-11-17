function CalibrationChart({ series, domainMax, fmt, baseRate }) {
  // A series may set `muted: true` (e.g. a bare/no-retrieval line drawn for
  // context, not as a headline result) to render dashed + low-opacity
  // instead of the default solid line, so it reads as background rather
  // than competing with the primary series.
  const box = React.useRef(null);
  const W = Math.max(300, useContainerWidth(box, 430)), H = 360;   // measured; web/shared/responsive.jsx
  const pad = { l: 52, r: 16, t: 14, b: 46 };
  const x = v => pad.l + (v / domainMax) * (W - pad.l - pad.r);
  const y = v => pad.t + (1 - v / domainMax) * (H - pad.t - pad.b);
  const ticks = domainMax <= 0.12 ? [0, 0.02, 0.04, 0.06, 0.08, 0.1]
    : Array.from({ length: 6 }, (_, i) => Math.round((i * domainMax / 5) * 1000) / 1000);
  const line = pts => pts.map((p, i) => (i === 0 ? "M" : "L") + x(p.pred).toFixed(1) + " " + y(p.obs).toFixed(1)).join(" ");
  return (
    <div ref={box} style={{ minWidth: 0 }}>
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={x(t)} x2={x(t)} y1={pad.t} y2={H - pad.b} stroke="var(--line-soft)" />
          <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--line-soft)" />
          <text x={x(t)} y={H - pad.b + 17} textAnchor="middle" fontSize="10" fill="var(--ink-faint)" className="mono">{fmt(t)}</text>
          <text x={pad.l - 8} y={y(t) + 3.5} textAnchor="end" fontSize="10" fill="var(--ink-faint)" className="mono">{fmt(t)}</text>
        </g>
      ))}
      <line x1={x(0)} y1={y(0)} x2={x(domainMax)} y2={y(domainMax)} stroke="var(--ink-faint)" strokeDasharray="4 4" opacity="0.7" />
      <text x={x(domainMax) - 4} y={y(domainMax) + 13} textAnchor="end" fontSize="9.5" fill="var(--ink-faint)">perfect calibration</text>
      {baseRate ? <g>
        <line x1={pad.l} x2={W - pad.r} y1={y(baseRate)} y2={y(baseRate)} stroke="var(--warn-ink)" strokeDasharray="3 3" opacity="0.8" />
        <text x={W - pad.r} y={y(baseRate) - 4} textAnchor="end" fontSize="9.5" fill="var(--warn-ink)">base rate {fmt(baseRate)} — where rare events actually land</text>
      </g> : null}
      {/* 95% intervals on the observed frequency. The series carry very
          different per-decile n, so without these the small-sample zigzag
          reads as miscalibration. Drawn under the dots. */}
      {series.map(s => s.data.pts.map((p, i) => (p.lo95 == null ? null : (
        <line key={s.key + "ci" + i} x1={x(p.pred)} x2={x(p.pred)} y1={y(p.lo95)} y2={y(p.hi95)}
          stroke={s.color} strokeWidth="1.4" opacity="0.42" strokeLinecap="round" />
      ))))}
      {series.map(s => <path key={s.key} d={line(s.data.pts)} fill="none" stroke={s.color} strokeWidth={s.muted ? 1.6 : 2}
        strokeLinejoin="round" strokeDasharray={s.muted ? "5 4" : undefined} opacity={s.muted ? 0.45 : 0.85} />)}
      {series.map(s => s.data.pts.map((p, i) => <circle key={s.key + i} cx={x(p.pred)} cy={y(p.obs)} r={s.muted ? 2.6 : 3.6}
        fill={s.color} opacity={s.muted ? 0.55 : 1}>
        {p.n ? <title>{`decile ${i + 1} · mean forecast ${(100 * p.pred).toFixed(1)}% · observed ${(100 * p.obs).toFixed(1)}% · n=${p.n}`
          + (p.lo95 != null ? ` · 95% CI ${(100 * p.lo95).toFixed(1)}–${(100 * p.hi95).toFixed(1)}%` : "")}</title> : null}
      </circle>))}
      <text x={(pad.l + W - pad.r) / 2} y={H - 4} textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Forecast probability (decile means)</text>
      <text x={-H / 2} y={13} transform="rotate(-90)" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Observed frequency</text>
    </svg>
    </div>
  );
}

/* ============================ ECI scatter (tail skill vs capability) ============================ */
function tipHTML(pt) {
  const f = v => (v == null ? "n/a" : (v >= 0 ? "+" : "") + v.toFixed(2));
  const civ = pt.bssCiv != null ? `CivBench ${f(pt.bssCiv)}` : "";
  const star = pt.bssStar != null ? `Starsim ${f(pt.bssStar)}` : "";
  const per = [civ, star].filter(Boolean).join(" &nbsp;·&nbsp; ");
  return `<div style="font-family:'Season Sans',sans-serif;font-size:12px;line-height:1.5">`
    + `<strong>${pt.label}</strong> &nbsp;<span style="color:#888">ECI ${pt.eci}</span><br>`
    + `Tail skill (2-sim avg): <strong>${f(pt.bss)}</strong><br>`
    + (per ? `<span style="color:#888">${per}</span><br>` : "")
    + (pt.meanPred != null ? `<span style="color:#888">avg forecast ${(pt.meanPred*100).toFixed(0)}%</span>` : "")
    + (pt.architecture ? `<br><span style="color:#888">architecture: ${pt.architecture}</span>` : "")
    + `</div>`;
}

// Spearman rank correlation, mirroring redlines/stats.py::spearman (same
// ranking, same n<2 -> 0 guard) so the chart's own numbers match the blob's
// "rho"/"rhoClean" exactly. Kept local rather than trusting a prop, so the
// chart is correct even if a caller only ever passes `points`.
function _rankCorr(xs, ys) {
  const n = xs.length;
  if (n < 2) return 0;
  const rankOf = vs => {
    const order = vs.map((_, i) => i).sort((a, b) => vs[a] - vs[b]);
    const r = new Array(n);
    order.forEach((i, k) => { r[i] = k; });
    return r;
  };
  const rx = rankOf(xs), ry = rankOf(ys);
  let d2 = 0;
  for (let i = 0; i < n; i++) d2 += (rx[i] - ry[i]) ** 2;
  return 1 - 6 * d2 / (n * (n * n - 1));
}

function ECIScatter({ points }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!window.tippy || !ref.current) return;
    const nodes = ref.current.querySelectorAll("[data-tippy-content]");
    const inst = appTooltip(nodes, { allowHTML: true });
    return () => inst.forEach(i => i.destroy());
  }, []);
  const box = React.useRef(null);
  const W = Math.max(300, useContainerWidth(box, 430)), H = 360;   // measured; web/shared/responsive.jsx
  const pad = { l: 46, r: 44, t: 18, b: 42 };
  // MoE models are a known confound for this trend (registry.py's
  // CONFOUNDED_ARCHITECTURES), so they are not plotted at all — the chart is
  // the clean subset. The footnote below still names them and reports what
  // including them would do to rho, so nothing is cut silently.
  const drawn = points.filter(p => !p.excluded);
  const dropped = points.filter(p => p.excluded);
  // The panel ensemble (C13, 2026-09-02): the median of the panel's
  // predictions per question, scored like a model (graph4.py::ensemble_pairs).
  // Its own mark, off the ladder: not a model, not in rho.
  const ens = (typeof G4 !== "undefined" && G4 && G4.ensemble && G4.ensemble.bss != null) ? G4.ensemble : null;
  const xs = drawn.map(p => p.eci), ys = drawn.map(p => p.bss).concat(ens ? [ens.bss] : []);
  const xmin = Math.min(...xs) - 3, xmax = Math.max(...xs) + 3;
  const ymin = Math.min(...ys, 0) - 0.6, ymax = Math.max(...ys, 0) + 0.6;
  const x = v => pad.l + (v - xmin) / (xmax - xmin) * (W - pad.l - pad.r);
  const y = v => pad.t + (1 - (v - ymin) / (ymax - ymin)) * (H - pad.t - pad.b);
  const xt0 = Math.ceil(xmin / 10) * 10;
  const xticks = []; for (let v = xt0; v <= xmax; v += 10) xticks.push(v);
  const ystep = (ymax - ymin) > 8 ? 2 : 1;
  const yt0 = Math.ceil(ymin / ystep) * ystep, yticks = []; for (let v = yt0; v <= ymax; v += ystep) yticks.push(v);

  const rhoFull = Math.round(_rankCorr(points.map(p => p.eci), points.map(p => p.bss)) * 100) / 100;
  const rhoClean = Math.round(_rankCorr(xs, ys) * 100) / 100;
  const fmtRho = v => (v >= 0 ? "+" : "") + v.toFixed(2);
  const axisBottom = H - pad.b, axisTop = pad.t;

  // Greedy label placement. A fixed stagger cannot survive the top-right
  // cluster (Opus 4.8 / Fable 5 sit ~5 ECI apart), so each label takes the
  // first candidate slot that hits neither a dot nor an already-placed label.
  const dots = drawn.map(p => ({ cx: x(p.eci), cy: y(p.bss) }));
  // Fourteen models since 2026-08-27, eight of them between ECI 147 and
  // 161: the slot list reaches further (diagonals, a third tier) and the
  // boxes are padded so "touching" counts as a hit.
  const SLOTS = [                                  // [dx, dy, textAnchor]
    [0, -14, "middle"], [0, 17, "middle"], [10, 3.5, "start"], [-10, 3.5, "end"],
    [10, -9, "start"], [-10, -9, "end"], [10, 15, "start"], [-10, 15, "end"],
    [0, -26, "middle"], [0, 29, "middle"], [12, -21, "start"], [-12, -21, "end"],
    [12, 27, "start"], [-12, 27, "end"], [0, -38, "middle"], [0, 41, "middle"],
    // Sixteen models since 2026-08-28, five of them within four ECI points
    // at the top right: a fourth tier, further out, and wide diagonals.
    [14, -33, "start"], [-14, -33, "end"], [14, 39, "start"], [-14, 39, "end"],
    [0, -50, "middle"], [0, 53, "middle"], [16, -45, "start"], [-16, -45, "end"],
  ];
  const boxOf = (lx, ly, w, anchor) => ({
    x0: (anchor === "start" ? lx : anchor === "end" ? lx - w : lx - w / 2) - 2,
    x1: (anchor === "start" ? lx + w : anchor === "end" ? lx : lx + w / 2) + 2,
    y0: ly - 10, y1: ly + 4,
  });
  const hits = (b, c) => !(b.x1 < c.x0 || b.x0 > c.x1 || b.y1 < c.y0 || b.y0 > c.y1);
  const taken = dots.map(d => ({ x0: d.cx - 7, x1: d.cx + 7, y0: d.cy - 7, y1: d.cy + 7 }));
  // The panel's labels are placed first, so they get the nearest free slots
  // (the same rule as Graphs 5 and 6), then the rest in ECI order.
  const order = drawn.map((pt, i) => i).sort((a, b) => (drawn[b].inPanel ? 1 : 0) - (drawn[a].inPanel ? 1 : 0));
  const placedByIndex = new Array(drawn.length);
  order.forEach(i => {
    const pt = drawn[i];
    const cx = dots[i].cx, cy = dots[i].cy;
    const w = pt.label.length * 5.9 + 2;          // ~5.9px per glyph at 10px, plus a hair of air
    let best = null;
    for (const [dx, dy, anchor] of SLOTS) {
      const ly = cy + dy;
      if (ly < axisTop + 4 || ly > axisBottom - 2) continue;      // stay off the axes
      const lx = Math.min(Math.max(cx + dx, w / 2 + 2), W - w / 2 - 2);
      const b = boxOf(lx, ly, w, anchor);
      if (b.x0 < 2 || b.x1 > W - 2) continue;                     // stay in the viewBox
      if (taken.some(t => hits(b, t))) continue;
      best = { lx, ly, anchor, box: b, leader: dx === 0 };
      break;
    }
    if (!best) {                                                  // nothing free — fall back above
      const ly = cy - 14, lx = Math.min(Math.max(cx, w / 2 + 2), W - w / 2 - 2);
      best = { lx, ly, anchor: "middle", box: boxOf(lx, ly, w, "middle"), leader: true };
    }
    taken.push(best.box);
    placedByIndex[i] = { pt, cx, cy, lx: best.lx, ly: best.ly, anchor: best.anchor, leader: best.leader };
  });
  const placed = placedByIndex;

  return (
    <div ref={box} style={{ minWidth: 0 }}>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {xticks.map((v, i) => (
          <g key={"x" + i}>
            <line x1={x(v)} x2={x(v)} y1={pad.t} y2={H - pad.b} stroke="var(--line-soft)" />
            <text x={x(v)} y={H - pad.b + 15} textAnchor="middle" fontSize="10" fill="var(--ink-faint)" className="mono">{v}</text>
          </g>
        ))}
        {yticks.map((v, i) => (
          <g key={"y" + i}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke={v === 0 ? "var(--warn-line)" : "var(--line-soft)"} strokeWidth={v === 0 ? 1.4 : 1} />
            <text x={pad.l - 6} y={y(v) + 3} textAnchor="end" fontSize="10" fill="var(--ink-faint)" className="mono">{v > 0 ? "+" + v : v}</text>
          </g>
        ))}
        <text x={pad.l + 2} y={y(0) - 4} textAnchor="start" fontSize="9.5" fill="var(--warn-ink)">0 = forecasting the true probability</text>
        {placed.map((L, i) => (
          <g key={i}>
            {L.leader && <line x1={L.cx} y1={L.cy} x2={L.lx} y2={L.ly + (L.ly < L.cy ? 4 : -9)} stroke="var(--line-soft)" strokeWidth="0.8" />}
            {/* The panel's models in their own colours -- the same as on every
                other chart -- and the rest of the ladder in the one retired
                gray, both from the blob (redlines/views/graph4.py; Nick,
                2026-09-08). Before that the panel was an accent green. */}
            <circle cx={L.cx} cy={L.cy} r={L.pt.inPanel ? 6.5 : 5} fill={L.pt.color}
              fillOpacity={L.pt.inPanel ? 1 : 0.85} stroke="var(--panel)" strokeWidth="1.2"
              style={{ cursor: "pointer" }} data-tippy-content={tipHTML(L.pt)} />
            {/* a panel-coloured chip so the label reads over the base-rate line and grid */}
            <rect x={L.anchor === "start" ? L.lx - 2 : L.anchor === "end" ? L.lx - L.pt.label.length * 5.9 - 2 : L.lx - L.pt.label.length * 2.95 - 2}
              y={L.ly - 9} width={L.pt.label.length * 5.9 + 4} height={12} rx="2" fill="var(--panel)" opacity="0.85" />
            <text x={L.lx} y={L.ly} textAnchor={L.anchor} fontSize="10" fill={L.pt.inPanel ? "var(--ink)" : "var(--ink-soft)"}
              fontWeight={L.pt.inPanel ? 600 : 400}>{L.pt.label}</text>
          </g>
        ))}
        {ens && (() => {
          const cx = x(ens.eci), cy = y(ens.bss);
          const tip = `<div style="font-family:'Season Sans',sans-serif;font-size:12px;line-height:1.5"><strong>Panel ensemble</strong><br>`
            + `median of ${ens.members.join(", ")}` + (ens.absent && ens.absent.length ? ` (${ens.absent.join(", ")} not on these benches)` : "") + `<br>`
            + `Tail skill: <strong>${(ens.bss >= 0 ? "+" : "") + ens.bss.toFixed(2)}</strong>`
            + (ens.bssCiv != null ? ` &nbsp;<span style="color:#888">CivBench ${(ens.bssCiv >= 0 ? "+" : "") + ens.bssCiv.toFixed(2)}</span>` : "")
            + (ens.bssStar != null ? ` &nbsp;<span style="color:#888">Starsim ${(ens.bssStar >= 0 ? "+" : "") + ens.bssStar.toFixed(2)}</span>` : ` &nbsp;<span style="color:#888">CivBench only: no shared Starsim draws</span>`)
            + `</div>`;
          return <g>
            {/* No text label: it lands in the top-right cluster where every
                slot is taken; the legend names the mark and the tooltip
                carries the numbers. */}
            <path d={diamondPath(cx, cy, 8)} fill="var(--panel)" stroke="var(--ink)" strokeWidth="2.2" style={{ cursor: "pointer" }} data-tippy-content={tip} />
          </g>;
        })()}
        <text x={(pad.l + W - pad.r) / 2} y={H - 4} textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Epoch Capabilities Index (ECI) →</text>
        <text x={-H / 2} y={13} transform="rotate(-90)" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Brier skill (2-sim avg)</text>
      </svg>
      <div style={{ display: "flex", gap: 14, marginTop: 6, flexWrap: "wrap" }}>
        {drawn.filter(p => p.inPanel).map(p => <LegendDot key={p.label} color={p.color} label={p.label + " (panel)"} />)}
        <LegendDot color={(drawn.find(p => !p.inPanel) || {}).color || "var(--ink-faint)"} label="Other models on the ladder" />
        {ens && <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><svg width="14" height="14" viewBox="0 0 16 16"><path d={diamondPath(8, 8, 6.5)} fill="var(--panel)" stroke="var(--ink)" strokeWidth="2" /></svg>panel ensemble (median of {ens.members.length}{ens.bssStar == null ? "; CivBench only" : ""})</span>}
      </div>
      <div style={{ marginTop: 10 }}>
        <Stat label={`Capability ↔ skill (ρ), ${drawn.length} models`} value={fmtRho(rhoClean)} color="var(--model)" />
      </div>
      {dropped.length ? (
        <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 6 }}>
          Not shown: {dropped.map(p => p.label).join(", ")} — MoE architecture is a known confound for this
          trend (see <code>docs/methodology.md</code>). Adding {dropped.length > 1 ? "them" : "it"} back would
          move ρ to {fmtRho(rhoFull)}.
        </div>
      ) : null}
    </div>
  );
}


/* ============================ severity ladder ============================ */
function SeverityLadder({ latestByKey, selKey }) {
  const max = Math.max(...SEVERITY.map(s => latestByKey[s.key]));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontSize: 11.5, color: "var(--ink-faint)", fontWeight: 600 }}>LATEST MODEL FORECAST BY SEVERITY (Total AI-enabled)</div>
      {SEVERITY.map(s => {
        const v = latestByKey[s.key];
        const sel = s.key === selKey;
        return (
          <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 142, fontSize: 12.5, color: sel ? "var(--ink)" : "var(--ink-soft)", fontWeight: sel ? 600 : 400 }}>{s.label}</div>
            <div style={{ flex: 1, background: "var(--line-soft)", borderRadius: 5, height: 16, position: "relative" }}>
              <div style={{ width: `${Math.max(2, (v / max) * 100)}%`, height: "100%", borderRadius: 5, background: sel ? "var(--model)" : "rgba(188, 76, 0, 0.4)" }}></div>
            </div>
            <div className="mono" style={{ width: 48, textAlign: "right", fontSize: 12.5, fontWeight: 500, color: sel ? "var(--model)" : "var(--ink-soft)" }}>{v.toFixed(2)}%</div>
          </div>
        );
      })}
      <div style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>Probabilities are weakly monotone — a more severe threshold can never be more likely.</div>
    </div>
  );
}

