/* ============================ CONDITIONAL ON: helpers ============================ */
const COND = (typeof window !== "undefined" && window.__CONDITIONAL__) || null;

/* ============================ helpers ============================ */
const cFmtP = v => (v == null ? "—" : v >= 10 ? v.toFixed(1) + "%" : v >= 1 ? v.toFixed(2) + "%" : v.toFixed(3) + "%");
const cFmtRatio = r => (r == null ? "—" : r >= 10 ? r.toFixed(0) + "×" : r.toFixed(2) + "×");
const cFmtBig = (v, prefix) => {
  if (v == null) return "—";
  const p = prefix || "";
  const units = [[1e15, "Q"], [1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "k"]];
  for (const [cut, suf] of units) if (Math.abs(v) >= cut) return p + Number((v / cut).toPrecision(3)) + suf;
  return p + Number(v.toPrecision(3));
};
// Death-equivalents, with the dollar reading at the ladder's own rate.
const cFmtLoss = v => (v == null ? "—" : cFmtBig(v));
const cFmtLossShort = cFmtLoss;
// One formatter per value kind: a probability cell prints percent, a loss cell
// prints deaths, a percentiles cell (the welfare page) its question's unit.
const cFmtV = (kind, v, unit) => (kind === "loss" ? cFmtLossShort(v) : kind === "percentiles" ? unitFmt(v, unit) : cFmtP(v));

// The one reading of a change the page plots: conditional ÷ unconditional, on
// a log axis so 1/2× and 2× sit the same distance from the baseline. It is the
// only measure that reads on a ~1% baseline AND applies to an expected loss.
const COND_MEASURE = { key: "ratio", label: "× baseline", axis: "conditional ÷ unconditional", fmt: cFmtRatio, zero: 1, scale: "log" };

// A tick set that brackets the extremes symmetrically about 1× (log scale).
function condSymmetricTicks(values) {
  const lv = values.filter(v => v != null && v > 0).map(v => Math.abs(Math.log2(v)));
  const top = Math.max(0.5, ...lv);
  const step = top <= 1 ? 0.5 : top <= 2 ? 1 : top <= 4 ? 2 : 4;
  const n = Math.ceil(top / step);
  const ticks = [];
  for (let i = -n; i <= n; i++) ticks.push(Math.pow(2, i * step));
  return { ticks, lo: Math.pow(2, -n * step), hi: Math.pow(2, n * step) };
}

// The expected-deaths axis: graph 2's deaths-ladder rung ticks, on a domain
// CROPPED to the data — the decades that bracket
// every value on every domain-specific row at every horizon (bars, dots,
// CIs, the band). One domain for all four causes and both horizons, so a
// bar's position means the same thing on every loss row; cropped, rather
// than graph 2's full 1k–Extinction span, because on the full span a bar and
// its band collapsed into a few pixels and whether the bar cleared the band
// could not be seen (Nick, 2026-08-27). The Extinction mark is drawn only
// when the domain reaches it.
function condSeverityAxis(values, ctx) {
  const C = ctx || COND;
  const v = (values || []).filter(x => x != null && x > 0);
  const lo = v.length ? Math.pow(10, Math.floor(Math.log10(Math.min(...v)))) : SEVERITY_AXIS.lo;
  const hi = v.length ? Math.pow(10, Math.ceil(Math.log10(Math.max(...v)))) : SEVERITY_AXIS.hi;
  const ticks = ((C && C.rungs) || []).map(r => r.deaths).filter(d => d >= lo && d <= hi);
  const refs = (typeof HIST !== "undefined" && HIST) ? HIST.events.filter(e => e.kind === "reference" && /extinction/i.test(e.label)) : [];
  const marks = refs.length ? refs.map(e => ({ v: e.central, label: e.short || e.label }))
                            : [{ v: 8.2e9, label: "Extinction" }];
  return { ticks, lo, hi, marks: marks.filter(m => m.v >= lo && m.v <= hi) };
}

/* ============================ the delta chart ============================ */
// One row per policy condition. The vertical line is the unconditional
// forecast; the bar is exp(median(log(per-model ratios))); the dots
// are the models. The grey band is the re-elicitation spread of the
// unconditional arms — a bar that does not clear it has not been shown to
// move anything.
//
// Two axes for two kinds of cell. A probability cell plots RATIOS: baselines
// differ twentyfold across models, so each dot is a model's move against its
// own baseline and the line is 1×. An expected-deaths cell plots LEVELS in
// deaths: the unit is the
// point, so the dots are absolute, the line is the ensemble-median baseline,
// and a top row shows each model's own unconditional value so a colour's move
// is still readable.
// Everything one cell puts on the axis: bar ends, model dots, per-row CIs,
// the unconditional's band and (loss cells) each model's own unconditional.
// Kept apart from the chart so a question's axis can span all its horizons.
function condAxisValues(cell) {
  // A percentiles cell plots levels: every model's 10th to 90th.
  if (cell.valueKind === "percentiles")
    return [...cell.baselines, ...cell.bars.flatMap(b => b.models)].flatMap(m => (m.q ? [m.q.p10, m.q.p90] : [m.p]));
  const loss = (cell.valueKind || "probability") === "loss";
  const base = cell.baselineMedian;
  const zero = loss ? base : 1;
  const vals = cell.bars.flatMap(b => [
    loss ? (b.ratio == null ? null : base * b.ratio) : b.ratio,
    ...b.models.map(m => (loss ? m.p : m.ratio)),
    ...(b.ci ? (loss ? [base * b.ci[0], base * b.ci[1]] : b.ci) : []),
  ]);
  if (loss) cell.baselines.forEach(b => vals.push(b.p));
  if (cell.baselineCi) vals.push(zero * cell.baselineCi[0], zero * cell.baselineCi[1]);
  return vals;
}

// The axis is fixed per question, not per horizon: switching 2030 → 2050
// moves the marks, never the ticks, so a policy's effect at two horizons
// can be compared by eye. For a probability cell `axisValues` is the union
// over the question's horizons; for a loss cell it is the union over EVERY
// loss row and horizon (condSeverityAxis crops the rung axis to it). A cell
// shown alone falls back to its own values.
// `ctx` is the blob the chart reads its conditions, rungs and method text
// from: the policy blob (default) or one Capability-tab variant, which has
// the same shape. One component, two tabs (Nick, 2026-08-28: the capability
// chart "should be IDENTICAL to the Policy Levers graph").
function CondDeltaChart({ cell, onPick, picked, axisValues, ctx }) {
  const C = ctx || COND;
  const M = COND_MEASURE;
  const kind = cell.valueKind || "probability";
  const loss = kind === "loss";
  // A percentiles cell (the welfare page, 2026-10-22) plots levels as a loss
  // cell does -- the unconditional row on top, the line at its ensemble
  // median -- on a linear axis in the question's unit, each model's dot at
  // its median with its 10th-90th bar behind, the models a few pixels apart.
  const pct = kind === "percentiles";
  const level = loss || pct;
  const lane = (j, n) => (pct ? (j - (n - 1) / 2) * 5 : 0);
  const fmtLevel = v => (pct ? unitFmt(v, cell.unit) : cFmtBig(v));
  const rows = cell.bars;
  // Width is measured (web/shared/responsive.jsx). Under 640px the policy
  // name and value sit ABOVE each bar instead of flanking it, the rows grow
  // taller, and the axis thins its ticks — the same rows at readable size
  // rather than a desktop chart scaled to 40%.
  const box = React.useRef(null);
  const cw = useContainerWidth(box, 900);
  const narrow = cw < 640;
  const W = Math.max(320, cw), rowH = narrow ? 66 : 44;
  const pad = narrow ? { l: 14, r: 14, t: 26, b: loss ? 46 : 34 } : { l: 250, r: 150, t: 26, b: loss ? 46 : 34 };
  const barY = cy => (narrow ? cy + 6 : cy);            // where the bar, whisker and dots sit within a row
  const maxChars = narrow ? Math.max(18, Math.floor((W - pad.l - pad.r - 96) / 6.6)) : 40;
  const clip = s => (s.length > maxChars ? s.slice(0, maxChars - 2) + "…" : s);
  // Phone rows: the texts sit over the baseline band and the unconditional
  // line, so each rides a panel-coloured chip (estimated width, as graph 2's
  // end labels do). Right-aligned texts pass their left edge.
  const chip = (xLeft, yTop, text, perChar) => <rect x={xLeft - 3} y={yTop} width={text.length * perChar + 6} height={15} rx="2" fill="var(--panel)" opacity="0.92" />;
  const baseRow = level ? 1 : 0;                      // the unconditional row, level cells only
  const H = pad.t + pad.b + rowH * (rows.length + baseRow);
  const base = cell.baselineMedian;
  // Position value for the ensemble bar end and for a model's dot.
  const barVal = b => (pct ? (b.shift == null ? null : base + b.shift) : loss ? (b.ratio == null ? null : base * b.ratio) : b.ratio);
  const dotVal = m => (level ? m.p : m.ratio);
  const zero = level ? base : 1;
  // Each row carries its own 95% interval (as ratios); on a loss axis it is
  // placed on the ensemble-median baseline like the bar.
  const ciOf = b => (b.ci ? (loss ? [base * b.ci[0], base * b.ci[1]] : b.ci) : null);
  // No intervals on the page (Nick, 2026-09-02: dots + the median change, no CIs).
  // The blob still carries the bootstrap (b.ci, cell.baselineCi) for the CSV and
  // the paper; the chart draws the model dots, the bar to the median and a
  // line at it.
  const vals = axisValues || condAxisValues(cell);
  const { ticks, lo, hi, marks = [] } = pct ? unitTicks(vals) : loss ? condSeverityAxis(vals, C) : condSymmetricTicks(vals);
  const x = v => {
    const t = pct ? (v - lo) / (hi - lo) : (Math.log(Math.max(v, 1e-9)) - Math.log(lo)) / (Math.log(hi) - Math.log(lo));
    return pad.l + Math.min(1, Math.max(0, t)) * (W - pad.l - pad.r);
  };
  const x0 = x(zero);
  // Match the deaths ladder: the rung's death count.
  const tickLabel = t => (pct ? unitTick(t, cell.unit) : loss ? cFmtBig(t) : (t >= 1 ? t.toFixed(t === Math.round(t) ? 0 : 1) + "×" : "1/" + (1 / t).toFixed(1 / t === Math.round(1 / t) ? 0 : 1)));
  const tickSub = () => null;
  const rowY = i => pad.t + rowH * (i + baseRow) + rowH / 2;
  const [hv, setHv] = useState(null);      // hovered condition: shows its policy text

  return (
    <div ref={box} style={{ position: "relative", minWidth: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} onMouseLeave={() => setHv(null)}>
        {thinTicks(ticks, x, narrow ? 38 : 0).map(t => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={pad.t - 4} y2={H - pad.b} stroke="var(--line-soft)" />
            <text x={x(t)} y={H - pad.b + 16} textAnchor="middle" fontSize="11" fill="var(--ink-faint)" className="mono">{tickLabel(t)}</text>
            {tickSub(t) && <text x={x(t)} y={H - pad.b + 28} textAnchor="middle" fontSize="10" fill="var(--ink-faint)" className="mono">{tickSub(t)}</text>}
          </g>
        ))}
        {marks.map(m => (
          <g key={m.label}>
            <line x1={x(m.v)} x2={x(m.v)} y1={pad.t - 4} y2={H - pad.b} stroke="var(--ink-faint)" strokeWidth="1" strokeDasharray="4 3" opacity="0.7" />
            <text x={x(m.v)} y={H - pad.b + 16} textAnchor="middle" fontSize="10" fill="var(--ink-soft)">{m.label}</text>
          </g>
        ))}
        <line x1={x0} x2={x0} y1={pad.t - 10} y2={H - pad.b} stroke="var(--ink)" strokeWidth="1.5" />
        <text x={x0} y={pad.t - 14} textAnchor={narrow ? (x0 < W * 0.3 ? "start" : x0 > W * 0.7 ? "end" : "middle") : "middle"} fontSize="11" fill="var(--ink-soft)" fontWeight="600">{level ? "unconditional, ensemble median" : "unconditional"}</text>
        <text x={narrow ? pad.l : pad.l - 8} y={H - pad.b + (loss ? 42 : 30)} textAnchor={narrow ? "start" : "end"} fontSize="11" fill="var(--ink-faint)">◀ lower</text>
        <text x={narrow ? W - pad.r : W - pad.r + 8} y={H - pad.b + (loss ? 42 : 30)} textAnchor={narrow ? "end" : "start"} fontSize="11" fill="var(--ink-faint)">higher ▶</text>
        {level && (() => {
          // The unconditional row: each model's own same-session baseline.
          const cy = pad.t + rowH / 2;
          return (
            <g>
              <rect x={0} y={cy - rowH / 2} width={W} height={rowH} fill="var(--line-soft)" opacity="0.35" />
              {narrow ? <>
                {chip(pad.l, cy - 30, "Unconditional", 6.8)}
                <text x={pad.l} y={cy - 19} textAnchor="start" fontSize="12.5" fill="var(--ink)" fontWeight={600}>Unconditional</text>
                {chip(W - pad.r - fmtLevel(base).length * 7.2, cy - 30, fmtLevel(base), 7.2)}
                <text x={W - pad.r} y={cy - 19} textAnchor="end" fontSize="12" fill="var(--ink)" className="mono" fontWeight="600">{fmtLevel(base)}</text>
                {chip(pad.l, cy + 16, "each model, same session", 6.3)}
                <text x={pad.l} y={cy + 27} textAnchor="start" fontSize="10.5" fill="var(--ink-faint)" className="mono">each model, same session</text>
                {chip(W - pad.r - ("median of " + cell.baselines.length).length * 6.3, cy + 16, "median of " + cell.baselines.length, 6.3)}
                <text x={W - pad.r} y={cy + 27} textAnchor="end" fontSize="10.5" fill="var(--ink-faint)" className="mono">median of {cell.baselines.length}</text>
              </> : <>
                <text x={pad.l - 14} y={cy + 4} textAnchor="end" fontSize="12.5" fill="var(--ink)" fontWeight={600}>Unconditional</text>
                <text x={pad.l - 14} y={cy + 17} textAnchor="end" fontSize="10.5" fill="var(--ink-faint)" className="mono">each model, same session</text>
                <text x={W - pad.r + 12} y={cy + 4} fontSize="12" fill="var(--ink)" className="mono" fontWeight="600">{fmtLevel(base)}</text>
                <text x={W - pad.r + 12} y={cy + 17} fontSize="10.5" fill="var(--ink-faint)" className="mono">median of {cell.baselines.length}</text>
              </>}
              {cell.baselines.map((b, j) => b.p == null ? null : (
                <React.Fragment key={b.label}>
                  {pct && <PctBar q={b.q} pos={x} at={barY(cy) + lane(j, cell.baselines.length)} color={b.color || "var(--ink)"} />}
                  <circle cx={x(b.p)} cy={barY(cy) + lane(j, cell.baselines.length)} r="4.5" fill={b.color || "var(--ink)"} stroke="var(--panel)" strokeWidth="2" />
                </React.Fragment>
              ))}
            </g>
          );
        })()}
        {rows.map((b, i) => {
          const cy = rowY(i);
          const v = barVal(b);
          const xe = v == null ? x0 : x(v);
          const isPicked = picked === b.id;
          const by = barY(cy);
          const valueText = pct ? fmtLevel(v) + " · " + unitShift(b.shift, cell.unit) : loss ? cFmtBig(v) + " · " + M.fmt(b.ratio) : M.fmt(b.ratio);
          return (
            <g key={b.id} onMouseEnter={() => setHv(b.id)} onClick={() => onPick && onPick(b.id)} style={{ cursor: "pointer" }}>
              <rect x={0} y={cy - rowH / 2} width={W} height={rowH} fill={isPicked || hv === b.id ? "var(--line-soft)" : "transparent"} opacity="0.6" />
              {narrow ? <>
                {chip(pad.l, cy - 30, clip(b.label), 6.6)}
                <text x={pad.l} y={cy - 19} textAnchor="start" fontSize="12.5" fill="var(--ink)" fontWeight={isPicked ? 600 : 500}>{clip(b.label)}</text>
                {chip(W - pad.r - valueText.length * 7.2, cy - 30, valueText, 7.2)}
                <text x={W - pad.r} y={cy - 19} textAnchor="end" fontSize="12" fill="var(--ink)" className="mono" fontWeight="600">{valueText}</text>
                {chip(pad.l, cy + 16, b.leapId, 6.3)}
                <text x={pad.l} y={cy + 27} textAnchor="start" fontSize="10.5" fill="var(--ink-faint)" className="mono">{b.leapId}</text>
              </> : <>
                <text x={pad.l - 14} y={cy + 4} textAnchor="end" fontSize="12.5" fill="var(--ink)" fontWeight={isPicked ? 600 : 500}>{clip(b.label)}</text>
                <text x={pad.l - 14} y={cy + 17} textAnchor="end" fontSize="10.5" fill="var(--ink-faint)" className="mono">{b.leapId}</text>
                <text x={W - pad.r + 12} y={cy + 4} fontSize="12" fill="var(--ink)" className="mono" fontWeight="600">{valueText}</text>
              </>}
              {v != null && (
                <rect x={Math.min(x0, xe)} y={by - 9} width={Math.max(1.5, Math.abs(xe - x0))} height={18}
                  fill="var(--ink-soft)" opacity="0.38" rx={3} />
              )}
              {/* the median change itself, as a line */}
              {v != null && <line x1={xe} x2={xe} y1={by - 11} y2={by + 11} stroke="var(--ink)" strokeWidth="2.5" />}
              {/* A hollow dot is a call that ran with no search evidence
                  (grounded=false): it answered from memory, not the news. */}
              {b.models.map((m, j) => dotVal(m) == null ? null : (
                <React.Fragment key={m.label}>
                  {pct && <PctBar q={m.q} pos={x} at={by + lane(j, b.models.length)} color={m.color || "var(--ink)"} />}
                  <circle cx={x(dotVal(m))} cy={by + lane(j, b.models.length)} r="4.5"
                    fill={m.grounded === false ? "var(--panel)" : (m.color || "var(--ink)")}
                    stroke={m.grounded === false ? (m.color || "var(--ink)") : "var(--panel)"} strokeWidth="2" />
                </React.Fragment>
              ))}
            </g>
          );
        })}
      </svg>
      {hv != null && (() => {
        const b = rows.find(r => r.id === hv);
        const i = rows.indexOf(b);
        const cond = (C.conditions || []).find(c => c.id === b.id) || {};
        const top = ((pad.t + rowH * (i + baseRow)) / H) * 100;
        const desc = cond.description || "";
        const cut = desc.length > 900 ? desc.slice(0, 900).replace(/\s+\S*$/, "") + " …" : desc;
        return (
          <div style={{ position: "absolute", top: `${top}%`, right: 8, transform: "translateY(-100%)", background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 8, padding: "10px 12px", boxShadow: "var(--shadow)", pointerEvents: "none", width: 460, maxWidth: narrow ? "calc(100% - 16px)" : "60%", zIndex: 5 }}>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginBottom: 3 }}>What the model was told{b.leapId ? <> · <span className="mono">{b.leapId}</span></> : null}</div>
            <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>{b.label}</div>
            {cond.assume && <div style={{ fontSize: 12.5, color: "var(--ink)", marginBottom: 6 }}><strong>Condition.</strong> {cond.assume}</div>}
            {cut && <div style={{ fontSize: 12, color: "var(--ink-soft)", whiteSpace: "pre-wrap", lineHeight: 1.45 }}>{cut}</div>}
            {desc.length > 900 && <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 6 }}>click the row for the full text</div>}
          </div>
        );
      })()}
      {loss && <ExpectedLossNote />}
    </div>
  );
}

/* ============================ the table view ============================ */
function CondDeltaTable({ cell, ctx }) {
  const C = ctx || COND;
  const kind = cell.valueKind || "probability";
  // A percentiles cell's change is its median's shift, and each value
  // carries its 10th-90th.
  const M = kind === "percentiles" ? { key: "shift", fmt: d => unitShift(d, cell.unit) } : COND_MEASURE;
  const range = m => (m.q ? <span style={{ color: "var(--ink-faint)" }}> [{unitFmt(m.q.p10, cell.unit)}–{unitFmt(m.q.p90, cell.unit)}]</span> : null);
  const models = cell.baselines.map(b => b.label);
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="tv">
        <thead>
          <tr><th>condition</th>{models.map(m => <th key={m}>{m}</th>)}<th>ensemble</th></tr>
        </thead>
        <tbody>
          <tr style={{ fontWeight: 600 }}>
            <td>unconditional (same session)</td>
            {cell.baselines.map(b => <td key={b.label} className="mono" title={b.values.map(v => cFmtV(kind, v, cell.unit)).join(" · ")}>{cFmtV(kind, b.p, cell.unit)}{range(b)}{b.n > 1 ? <span style={{ color: "var(--ink-faint)" }}> ×{b.n}</span> : null}</td>)}
            <td className="mono">{cFmtV(kind, cell.baselineMedian, cell.unit)}</td>
          </tr>
          {cell.bars.map(b => (
            <tr key={b.id}>
              <td>{b.label} <span className="mono" style={{ color: "var(--ink-faint)" }}>{b.leapId}</span></td>
              {models.map(m => {
                const r = b.models.find(x => x.label === m);
                return <td key={m} className="mono">{r ? <>{cFmtV(kind, r.p, cell.unit)}{range(r)} <span style={{ color: "var(--ink-soft)" }}>({M.fmt(r[M.key])})</span>{r.grounded === false ? " †" : ""}</> : "—"}</td>;
              })}
              <td className="mono">{cFmtV(kind, b.pMedian, cell.unit)} <span style={{ color: "var(--ink-soft)" }}>({M.fmt(b[M.key])})</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      {kind === "loss" && <ExpectedLossNote />}
    </div>
  );
}

/* ============================ CONDITIONAL ON: panel ============================ */
function CondText({ cond, conditioning, labels }) {
  if (!cond) return null;
  const L = Object.assign({ instruction: "Conditioning instruction (LEAP's, verbatim).",
                            description: "Policy, as shown to the model (LEAP's text, verbatim).",
                            assumption: "Also assumed (ours, in the single instrument)." }, labels || {});
  return (
    <Panel style={{ padding: "16px 20px", marginTop: 14 }}>
      <Eyebrow>What the model was told{cond.leapId ? " · " + cond.leapId : ""}</Eyebrow>
      <h3 style={{ fontSize: 18, marginTop: 6, marginBottom: 8 }}>{cond.label}</h3>
      <p style={{ margin: "0 0 10px", fontSize: 13.5, color: "var(--ink-soft)" }}>
        <strong style={{ color: "var(--ink)" }}>Condition.</strong> {cond.assume}
      </p>
      <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-soft)" }}>
        <strong style={{ color: "var(--ink)" }}>{L.instruction}</strong> {conditioning.instruction}
      </p>
      {/* The combined instrument (policies and capability conditions in one
          call) adds one sentence per section saying what it holds the other
          quantity at; the standalone sets have none, and print nothing. */}
      {conditioning.assumption && (
        <p style={{ margin: "8px 0 0", fontSize: 13.5, color: "var(--ink-soft)" }}>
          <strong style={{ color: "var(--ink)" }}>{L.assumption}</strong> {conditioning.assumption}
        </p>
      )}
      {cond.description && (
        <div style={{ margin: "12px 0 0", fontSize: 12.5, color: "var(--ink-soft)", whiteSpace: "pre-wrap", lineHeight: 1.5, borderTop: "1px solid var(--line-soft)", paddingTop: 10 }}>
          <strong style={{ color: "var(--ink)" }}>{L.description}</strong>{"\n"}{cond.description}
        </div>
      )}
    </Panel>
  );
}


function ConditionalPanel({ ctx } = {}) {
  // `ctx`: a blob of COND's shape in its place (the welfare page's prompt toggle).
  const C = ctx || COND;
  if (!C || !C.questions.length) {
    return <ForecastUnavailable title="Forecasts conditional on policies" />;
  }
  // ?q=<question id>&h=<horizon> deep-links a chart.
  const params = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  const [qid, setQid] = useState(C.questions.some(x => x.id === params.get("q")) ? params.get("q") : C.questions[0].id);
  const [horizon, setHorizon] = useState(C.horizons.includes(params.get("h")) ? params.get("h") : C.defaultHorizon);
  const [picked, setPicked] = useState(null);
  const [showTable, setShowTable] = useState(false);
  const Q = C.questions;

  const q = Q.find(x => x.id === qid) || Q[0];
  const hz = q.horizons.includes(horizon) ? horizon : q.horizons[0];
  const cell = q.byHorizon[hz];
  const cond = C.conditions.find(c => c.id === picked);

  return (
    <React.Fragment>
      <Panel style={{ padding: "16px 22px", marginBottom: 18 }}>
        <h2 style={{ fontSize: 22, marginTop: 0, marginBottom: 6 }}>How would policies change the forecast?</h2>
        <p style={{ color: "var(--ink-soft)", fontSize: 13.5, maxWidth: 820, margin: "0 0 6px" }}>
          How would these forecasts change if certain policies were enacted, effective immediately? (These questions come from the {C.source.panel} {C.source.wave} survey, currently underway with human respondents.)
        </p>
        <p style={{ color: "var(--ink-faint)", fontSize: 12.5, margin: 0 }}>
          Run {C.runs.join(", ")} · {C.rows} rows · {Object.keys(C.repeats || {}).length} models × {Object.values(C.repeats || {})[0] || "?"} repeats
          {C.instrument && C.instrument.group ? " · elicited in one call with the capability conditions (" + C.protocol + ")" : ""}
        </p>
      </Panel>

      <div className="rail-grid" style={{ gap: 18 }}>
        <Panel style={{ padding: 14 }}>
          {/* The same rail as Graph 1's (QuestionRail, 60-atoms.jsx): labels
              and colours come from the blob (railLabel, color), which takes
              them from the same rail module and ladder spec Graph 1 uses. */}
          <QuestionRail title="Question" value={q.id} onChange={setQid}
            items={Q.map(x => ({ key: x.id, label: x.railLabel || x.short, color: x.color, group: x.group }))} />
        </Panel>

        <div style={{ minWidth: 0 }}>
          <Panel style={{ padding: "18px 22px" }}>
            {/* The horizon toggle always sits top-right; nothing else shares
                its row — until the row is too narrow for both, when it wraps
                beneath the title. */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
              <div style={{ minWidth: 0 }}>
                <h2 style={{ fontSize: 22, marginTop: 0 }}>{q.heading || q.short} — by {hz}</h2>
              </div>
              <div style={{ flexShrink: 0 }}>
                <Toggle options={q.horizons.map(h => ({ key: h, label: "by " + h }))} value={hz} onChange={setHorizon} />
              </div>
            </div>

            {cell.note && <div style={{ fontSize: 12.5, color: "var(--warn-ink)", background: "var(--warn-bg)", border: "1px solid var(--warn-line)", borderRadius: 8, padding: "6px 10px", margin: "12px 0 0" }}>{cell.note}.</div>}

            <div style={{ marginTop: 14 }}>
              <CondDeltaChart cell={cell} ctx={C} picked={picked} onPick={id => setPicked(picked === id ? null : id)}
                axisValues={q.valueKind === "loss"
                  ? Q.filter(x => x.valueKind === "loss").flatMap(x => x.horizons.flatMap(h => condAxisValues(x.byHorizon[h])))
                  : q.horizons.flatMap(h => condAxisValues(q.byHorizon[h]))} />
            </div>

            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
              {C.models.map(m => <LegendDot key={m.label} color={m.color} label={m.label} />)}
              <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><svg width="22" height="14" viewBox="0 0 22 14"><rect x="1" y="2" width="16" height="10" rx="2" fill="var(--ink-soft)" opacity="0.38" /><line x1="17" x2="17" y1="0" y2="14" stroke="var(--ink)" strokeWidth="2.5" /></svg>median conditional change</span>
              <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><span style={{ width: 10, height: 10, borderRadius: 5, border: "2px solid var(--ink-soft)", background: "var(--panel)" }}></span>no search evidence</span>
              {q.valueKind === "percentiles" && <PctLegend label="median, 25th–75th, 10th–90th percentile" />}
              <button className="linkbtn" style={{ marginLeft: "auto" }} onClick={() => setShowTable(!showTable)}>{showTable ? "hide table" : "show table"}</button>
            </div>
            {showTable && <div style={{ marginTop: 12 }}><CondDeltaTable cell={cell} ctx={C} /></div>}
            {q.valueKind === "loss" && <CountingWindow info={C.instrumentInfo} horizon={hz} />}
          </Panel>

          <CondText cond={cond} conditioning={C.conditioning} />
        </div>
      </div>
    </React.Fragment>
  );
}
