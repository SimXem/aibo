/* ============================ AXES: the forecast against an x-axis quantity ============================ */
// Ezra, 2026-09-02 (worklist C11/C12): the forecast conditional on FIXED
// levels of a quantity the reader can put on an x-axis -- the frontier ECI,
// the combined OpenAI + Anthropic revenue run-rate (LEAP Wave 11) and the
// year of Expert AGI (LEAP Wave 8) -- with the panel's own forecast of the
// quantity and the LEAP superforecasters' answer overlaid. The blob is
// redlines/views/axes.py (the axes instrument, data/axes_conditions.json).
// One component, an axis toggle; the paper's three axes (GDP, LFPR, METR)
// are not on the site.
const AX = (typeof window !== "undefined" && window.__AXES__) || null;

const axFmtX = (fmt, v) => {
  if (v == null) return "—";
  if (fmt === "money") return v >= 1000 ? "$" + (v / 1000).toFixed(v % 1000 ? 1 : 0) + "T" : "$" + Number(v).toFixed(0) + "B";
  if (fmt === "year") return String(Math.round(v));
  return Number(v).toFixed(0);
};
// Probabilities arrive in PERCENT (the conditional summary's unit, as on the
// Policy tab); losses in deaths.
const axFmtPct = v => {
  if (v == null) return "—";
  const p = Number(v);
  const t = p >= 10 ? p.toFixed(0) : p >= 1 ? p.toFixed(1) : p >= 0.1 ? p.toFixed(2) : p.toPrecision(2);
  return t.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "") + "%";
};
const axFmtLoss = v => v == null ? "—" : v >= 1e6 ? (v / 1e6).toPrecision(2) + "M" : v >= 1e3 ? (v / 1e3).toPrecision(2) + "k" : Number(v).toPrecision(2);
const axFmtY = (kind, v) => kind === "loss" ? axFmtLoss(v) : axFmtPct(v);
const axFmtDate = s => s ? new Date(s + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }) : "";

// The percentile pair a reference or forecast is drawn between: the outer
// pair it has (p10-p90, p5-p95, p25-p75), and the median.
function axSpan(obj, fields) {
  if (!obj) return null;
  // Percentile fields only: the AGI forecast also carries p_before_2100.
  const have = fields.filter(f => /^p\d+$/.test(f) && obj[f] != null);
  if (!have.length) return null;
  const num = f => Number(f.slice(1));
  const sorted = [...have].sort((a, b) => num(a) - num(b));
  const mid = obj.p50 != null ? obj.p50 : obj[sorted[Math.floor(sorted.length / 2)]];
  return { lo: obj[sorted[0]], hi: obj[sorted[sorted.length - 1]], mid, loName: sorted[0], hiName: sorted[sorted.length - 1] };
}

// The models' forecast of the axis quantity, drawn under the axis. On the ECI
// axis it is the frontier chart's own box -- the page has ONE models' ECI
// forecast, the one drawn against the METR trend above (Nick, 2026-09-02). On
// a LEAP axis it is this call's forecast of the quantity, the only one there is.
function axModelsForecast(axis) {
  const fc = axis.forecast || { models: [], fields: [] };
  const capVariant = (typeof CAP !== "undefined" && CAP && CAP.variants && CAP.variants.length)
    ? (CAP.variants.find(v => v.key === CAP.defaultVariant) || CAP.variants[0]) : null;
  const capEns = axis.key === "eci" && capVariant && capVariant.forecast && capVariant.forecast.ensemble ? capVariant.forecast.ensemble : null;
  const obj = capEns || fc.ensemble;
  const fields = capEns ? ["p10", "p25", "p50", "p75", "p90"] : (fc.fields || []);
  const n = capEns ? (capVariant.forecast.models || []).length : fc.models.length;
  const span = axSpan(obj, fields);
  const box = obj && obj.p25 != null && obj.p75 != null && fields.length > 3 ? [obj.p25, obj.p75] : null;
  return { span, box, n, own: Object.fromEntries(fc.models.filter(m => m.p50 != null).map(m => [m.label, m.p50])) };
}
const axPctPair = (lo, hi) => `${lo.slice(1)}–${hi.slice(1)}th`;
// What the axis measures, for the legend.
const axNoun = axis => axis.key === "eci" ? "frontier ECI" : axis.key === "agi" ? "the AGI year" : axis.short.toLowerCase();

// The y frame is FIXED per question across every horizon and every axis, so
// the horizon toggle moves the curves up the chart instead of rescaling the
// axis under them (Nick, 2026-09-02: on an auto-scaled axis "all of the model
// and LEAP forecasts seem to be static regardless of horizon").
function axYDomain(qid) {
  const vals = [];
  (AX.axes || []).forEach(a => {
    const qq = (a.questions || []).find(x => x.id === qid);
    if (!qq) return;
    Object.values(qq.byHorizon).forEach(c => {
      c.levels.forEach(l => l.models.forEach(m => { if (m.p != null) vals.push(m.p); }));
      (c.humans || []).forEach(h => { if (h.p != null) vals.push(h.p); });
    });
  });
  return vals.length ? [Math.min(...vals), Math.max(...vals)] : null;
}

const AxLegendItem = ({ children }) => <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}>{children}</span>;

function AxisScatter({ axis, q, hz, models, yDomain, trailing }) {
  const box = React.useRef(null);
  const cw = useContainerWidth(box, 900);
  const narrow = cw < 640;
  const W = Math.max(320, cw), H = narrow ? 380 : 470;
  const cell = q.byHorizon[hz];
  const kind = cell.valueKind;
  const levels = axis.levels.map(l => ({ ...l, cell: cell.levels.find(c => c.id === l.id) }));
  const ref = axis.reference || {};
  const refFields = ref.kind === "leap" ? (ref.percentiles || []).map(p => "p" + p) : ["p25", "p50", "p75"];
  const refObj = ref.kind === "leap" ? (ref.panels || {})[ref.shown || "superforecaster"] : ref;
  const refSpan = axSpan(refObj, refFields);
  // The LEAP panel's forecast of the quantity: the reference itself on a LEAP
  // axis; on the ECI axis, Wave 5's forecast of the top US system's ECI at
  // end-2026 (axis.leap) -- the one human forecast of the ECI there is (Ezra,
  // 2026-09-02), two months before the axis's own date, so the page names it.
  const leap = ref.kind === "leap" ? ref : (axis.leap || null);
  const leapFields = leap ? (leap.percentiles || []).map(p => "p" + p) : [];
  const leapObj = leap ? (leap.panels || {})[leap.shown || "superforecaster"] : null;
  const leapSpan = axSpan(leapObj, leapFields);
  const leapDated = leap && ref.kind === "trend" && leap.at;
  const ens = axModelsForecast(axis);
  const noun = axNoun(axis);
  // Under the axis title, one row per reference the axis has: the METR trend,
  // the LEAP panel, the models' own forecast -- three on the ECI axis, two on
  // a LEAP axis -- so the bottom padding follows the row count.
  const hasTrend = !!(refSpan && ref.kind === "trend");
  const rowsN = (hasTrend ? 1 : 0) + (leapSpan ? 1 : 0) + (ens.span ? 1 : 0);
  const pad = { l: 58, r: narrow ? 16 : 28, t: 16, b: 104 + Math.max(0, rowsN - 2) * 26 };

  // x: the levels plus every glyph that has to fit.
  const sx = axis.scale === "log" ? (v => Math.log10(v)) : (v => v);
  const xsRaw = [...levels.map(l => l.value),
                 ...(refSpan ? [refSpan.lo, refSpan.hi] : []), ...(leapSpan ? [leapSpan.lo, leapSpan.hi] : []),
                 ...(ens.span ? [ens.span.lo, ens.span.hi] : [])]
    .filter(v => v != null && (axis.scale !== "log" || v > 0));
  const xLo0 = Math.min(...xsRaw), xHi0 = Math.max(...xsRaw);
  const xPad = (sx(xHi0) - sx(xLo0)) * 0.06 || 1;
  const xLo = sx(xLo0) - xPad, xHi = sx(xHi0) + xPad;
  const x = v => pad.l + (sx(v) - xLo) / (xHi - xLo) * (W - pad.l - pad.r);
  // y: log over the question's whole range (every horizon, every axis); a
  // probability floor of 0.01% (percent units), a loss floor of one.
  const floor = kind === "loss" ? 1 : 0.01;
  // The LEAP superforecasters' unconditional rides along at their own median of
  // the quantity, on every axis.
  const humans = leapSpan ? (cell.humans || []).filter(h => h.p != null) : [];
  const dom = yDomain || [floor, floor * 10];
  const yLo = Math.floor(Math.log10(Math.max(dom[0], floor)));
  const yHiE = Math.ceil(Math.log10(Math.max(dom[1], floor * 10)));
  const yHi = kind === "loss" ? yHiE : Math.min(yHiE, 2);
  const y = v => pad.t + (1 - (Math.log10(Math.max(v, floor)) - yLo) / (yHi - yLo || 1)) * (H - pad.t - pad.b);
  // 1-2-5 ticks per decade, within the domain.
  const yTicks = [];
  for (let e = yLo; e <= yHi; e++) for (const m of [1, 2, 5]) { const v = m * Math.pow(10, e); if (v <= Math.pow(10, yHi) * 1.0001) yTicks.push(v); }
  const xTicks = levels.map(l => l.value);
  const [hv, setHv] = useState(null);
  const axisY = H - pad.b;
  // Two reference rows under the axis title: the outside reference (METR trend
  // or LEAP), then the models' own forecast of the quantity.
  const glyphTrend = axisY + 56;
  const glyphLeap = glyphTrend + (hasTrend ? 26 : 0);
  const glyphModels = glyphLeap + (leapSpan ? 26 : 0);
  const medians = levels.filter(l => l.cell && l.cell.median != null);
  const path = pts => pts.length ? "M" + pts.map(p => `${x(p.x)},${y(p.p)}`).join("L") : "";
  const fx = v => axFmtX(axis.fmt, v);
  return (
    <div ref={box} style={{ position: "relative", minWidth: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} onMouseLeave={() => setHv(null)}>
        {yTicks.map(v => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--line-soft)" />
            <text x={pad.l - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--ink-faint)" className="mono">{axFmtY(kind, v)}</text>
          </g>
        ))}
        <line x1={pad.l} x2={W - pad.r} y1={axisY} y2={axisY} stroke="var(--line)" />
        {thinTicks(xTicks, v => x(v), narrow ? 34 : 0).map(v => (
          <g key={v}>
            <line x1={x(v)} x2={x(v)} y1={axisY} y2={axisY + 5} stroke="var(--ink-faint)" />
            <text x={x(v)} y={axisY + 18} textAnchor="middle" fontSize="11" fill="var(--ink-faint)" className="mono">{fx(v)}</text>
          </g>
        ))}
        <text x={(pad.l + W - pad.r) / 2} y={axisY + 34} textAnchor="middle" fontSize="11" fill="var(--ink-soft)">{axis.xTitle}</text>
        {/* the panel median through the levels */}
        <path d={path(medians.map(l => ({ x: l.value, p: l.cell.median })))} fill="none" stroke="var(--ink)" strokeWidth="3" strokeOpacity="0.35" strokeLinejoin="round" />
        {/* dots per model; the only line is the panel median (Nick, 2026-09-02: as everywhere else) */}
        {models.map(m => {
          const pts = levels.map(l => ({ x: l.value, id: l.id, p: l.cell && (l.cell.models.find(mm => mm.label === m.label) || {}).p }))
            .filter(p => p.p != null);
          return (
            <g key={m.label}>
              {pts.map(p => (
                <circle key={p.id} cx={x(p.x)} cy={y(p.p)} r={hv && hv.label === m.label && hv.id === p.id ? 5.5 : 4} fill={m.color} stroke="var(--panel)" strokeWidth="1.2"
                  onMouseEnter={() => setHv({ label: m.label, id: p.id, x: p.x, p: p.p, kind: "level" })} style={{ cursor: "default" }} />
              ))}
            </g>
          );
        })}
        {/* the LEAP superforecasters' unconditional, at their own median of the quantity */}
        {humans.map(h => (
          <g key={"h" + h.panel + h.group} onMouseEnter={() => setHv({ label: `${h.panel} superforecasters${h.date ? " (" + h.date.slice(0, 4) + ")" : ""}`, id: null, x: leapSpan.mid, p: h.p, kind: "human" })} style={{ cursor: "default" }}>
            <path d={`M${x(leapSpan.mid)},${y(h.p) - 7}L${x(leapSpan.mid) + 7},${y(h.p)}L${x(leapSpan.mid)},${y(h.p) + 7}L${x(leapSpan.mid) - 7},${y(h.p)}Z`} fill="var(--ink)" />
          </g>
        ))}
        {/* under the axis: the trend (ECI only), the LEAP panel, then the models' own forecast of the quantity */}
        {hasTrend && (
          // the frontier chart's encoding: p25-p75 band, dashed median
          <g>
            <title>{`Peter Wildeford's ECI trend on ${axFmtDate(ref.at)}: median ${fx(refSpan.mid)}, 25–75th ${fx(refSpan.lo)}–${fx(refSpan.hi)}`}</title>
            <rect x={x(refSpan.lo)} y={glyphTrend - 7} width={Math.max(2, x(refSpan.hi) - x(refSpan.lo))} height="14" fill="var(--ink-faint)" opacity="0.25" />
            <line x1={x(refSpan.mid)} x2={x(refSpan.mid)} y1={glyphTrend - 9} y2={glyphTrend + 9} stroke="var(--ink)" strokeWidth="1.5" strokeDasharray="3 2" />
          </g>
        )}
        {leapSpan && (
          <g>
            <title>{`LEAP superforecasters' forecast of ${leapDated ? "the top US system's ECI on " + axFmtDate(leap.at) : noun} (n=${leapObj && leapObj.n}): median ${fx(leapSpan.mid)}, ${axPctPair(leapSpan.loName, leapSpan.hiName)} ${fx(leapSpan.lo)}–${fx(leapSpan.hi)}`}</title>
            <line x1={x(leapSpan.lo)} x2={x(leapSpan.hi)} y1={glyphLeap} y2={glyphLeap} stroke="var(--ink)" strokeWidth="1.5" opacity="0.8" />
            <line x1={x(leapSpan.lo)} x2={x(leapSpan.lo)} y1={glyphLeap - 5} y2={glyphLeap + 5} stroke="var(--ink)" strokeWidth="1.5" opacity="0.8" />
            <line x1={x(leapSpan.hi)} x2={x(leapSpan.hi)} y1={glyphLeap - 5} y2={glyphLeap + 5} stroke="var(--ink)" strokeWidth="1.5" opacity="0.8" />
            <path d={`M${x(leapSpan.mid)},${glyphLeap - 7}L${x(leapSpan.mid) + 7},${glyphLeap}L${x(leapSpan.mid)},${glyphLeap + 7}L${x(leapSpan.mid) - 7},${glyphLeap}Z`} fill="var(--ink)" />
          </g>
        )}
        {ens.span && (
          // the frontier chart's box plot, on its side: inner quartiles as the box
          // when the call asked for them, the outer pair as whiskers
          <g>
            <title>{`models' forecast of ${noun} (median of ${ens.n}): ${fx(ens.span.mid)}${ens.box ? `, 25–75th ${fx(ens.box[0])}–${fx(ens.box[1])}, whiskers ${axPctPair(ens.span.loName, ens.span.hiName)} ${fx(ens.span.lo)}–${fx(ens.span.hi)}` : `, ${axPctPair(ens.span.loName, ens.span.hiName)} ${fx(ens.span.lo)}–${fx(ens.span.hi)}`}`}</title>
            {ens.box && <line x1={x(ens.span.lo)} x2={x(ens.box[0])} y1={glyphModels} y2={glyphModels} stroke="var(--ink)" strokeWidth="1.2" opacity="0.7" />}
            {ens.box && <line x1={x(ens.box[1])} x2={x(ens.span.hi)} y1={glyphModels} y2={glyphModels} stroke="var(--ink)" strokeWidth="1.2" opacity="0.7" />}
            {ens.box && <line x1={x(ens.span.lo)} x2={x(ens.span.lo)} y1={glyphModels - 4} y2={glyphModels + 4} stroke="var(--ink)" strokeWidth="1.2" opacity="0.7" />}
            {ens.box && <line x1={x(ens.span.hi)} x2={x(ens.span.hi)} y1={glyphModels - 4} y2={glyphModels + 4} stroke="var(--ink)" strokeWidth="1.2" opacity="0.7" />}
            <rect x={x(ens.box ? ens.box[0] : ens.span.lo)} y={glyphModels - 7} width={Math.max(2, x(ens.box ? ens.box[1] : ens.span.hi) - x(ens.box ? ens.box[0] : ens.span.lo))} height="14" rx="2" fill="var(--ink)" fillOpacity="0.14" stroke="var(--ink)" strokeOpacity="0.75" strokeWidth="1.5" />
            <line x1={x(ens.span.mid)} x2={x(ens.span.mid)} y1={glyphModels - 9} y2={glyphModels + 9} stroke="var(--ink)" strokeWidth="2.5" />
          </g>
        )}
      </svg>
      {/* one legend, short labels (Nick, 2026-09-02); the numbers are on the glyphs' tooltips */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
        {models.map(m => <LegendDot key={m.label} color={m.color} label={m.label} />)}
        <AxLegendItem><span style={{ width: 18, height: 3, background: "var(--ink)", opacity: 0.35 }}></span>panel median</AxLegendItem>
        {hasTrend && <AxLegendItem>
          <svg width="18" height="12" viewBox="0 0 18 12"><rect x="0" y="1" width="18" height="10" fill="var(--ink-faint)" opacity="0.25" /><line x1="9" x2="9" y1="0" y2="12" stroke="var(--ink)" strokeWidth="1.5" strokeDasharray="3 2" /></svg>
          <span>ECI trend (<a href={ref.url} target="_blank" rel="noopener" style={{ color: "var(--link)" }}>Peter Wildeford</a>): median, 25–75th band</span>
        </AxLegendItem>}
        {leapSpan && <AxLegendItem>
          <svg width="14" height="14" viewBox="0 0 14 14"><path d="M7,0L14,7L7,14L0,7Z" fill="var(--ink)" /></svg>{`LEAP superforecasters${leapDated ? " (" + axFmtDate(leap.at) + ")" : ""}: median, ${axPctPair(leapSpan.loName, leapSpan.hiName)} whiskers`}
        </AxLegendItem>}
        {ens.span && <AxLegendItem>
          <svg width="18" height="14" viewBox="0 0 18 14"><rect x="1" y="2" width="16" height="10" rx="2" fill="var(--ink)" fillOpacity="0.14" stroke="var(--ink)" strokeOpacity="0.75" strokeWidth="1.5" /><line x1="9" x2="9" y1="0" y2="14" stroke="var(--ink)" strokeWidth="2.5" /></svg>{`model forecast: median${ens.box ? ", 25–75th box" : ""}, ${axPctPair(ens.span.loName, ens.span.hiName)} whiskers`}
        </AxLegendItem>}
        {trailing}
      </div>
      {hv && (
        <PointTooltip box={box} x={x(hv.x)} y={y(hv.p)}>
          <div style={{ fontWeight: 600 }}>{hv.label}</div>
          <div className="mono" style={{ color: "var(--ink-soft)" }}>
            {hv.kind === "human" ? `unconditional ${axFmtY(kind, hv.p)} · their own median ${fx(hv.x)}`
              : `${fx(hv.x)} → ${axFmtY(kind, hv.p)}`}
          </div>
        </PointTooltip>
      )}
    </div>
  );
}

function AxesPanel() {
  if (!AX || !AX.axes || !AX.axes.length) return null;
  const params = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  const [akey, setAkey] = useState(AX.axes.some(a => a.key === params.get("axis")) ? params.get("axis") : AX.defaultAxis);
  const axis = AX.axes.find(a => a.key === akey) || AX.axes[0];
  const Q = axis.questions || [];
  const [qid, setQid] = useState(Q.some(x => x.id === params.get("q")) ? params.get("q") : AX.defaultQuestion);
  const [horizon, setHorizon] = useState(AX.horizons.includes(params.get("h")) ? params.get("h") : AX.defaultHorizon);
  const [showText, setShowText] = useState(false);
  if (!Q.length) {
    return <ForecastUnavailable title="Forecasts conditional on revenue, capability and timing" />;
  }
  const q = Q.find(x => x.id === qid) || Q[0];
  const hz = q.horizons.includes(horizon) ? horizon : q.horizons[0];
  const cell = q.byHorizon[hz];
  const ref = axis.reference || {};
  const refObj = ref.kind === "leap" ? (ref.panels || {})[ref.shown || "superforecaster"] : null;
  return (
    <React.Fragment>
      <Panel style={{ padding: "16px 22px", marginBottom: 18, marginTop: 18 }}>
        <Eyebrow>Graph · Conditional on revenue, capability, timing</Eyebrow>
        <h2 style={{ fontSize: 22, marginTop: 6, marginBottom: 6 }}>How do forecasts change conditional on lab revenue, capability, or the timing of AGI?</h2>
        <p style={{ color: "var(--ink-soft)", fontSize: 13.5, maxWidth: 860, margin: 0 }}>
          Risks conditional on ECI, revenue, and the year AGI is achieved (questions taken from{" "}
          <a href="https://leap.forecastingresearch.org" target="_blank" rel="noopener" style={{ color: "var(--link)" }}>LEAP</a>).
        </p>
      </Panel>
      <div className="rail-grid" style={{ gap: 18 }}>
        <Panel style={{ padding: 14 }}>
          <QuestionRail title="Question" value={q.id} onChange={setQid}
            items={Q.map(x => ({ key: x.id, label: x.railLabel || x.short, color: x.color, group: x.group }))} />
        </Panel>
        <div style={{ minWidth: 0 }}>
          <Panel style={{ padding: "18px 22px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
              <div style={{ minWidth: 0 }}>
                <Eyebrow>{q.group}{q.severity ? " · " + q.severity : ""}</Eyebrow>
                <h2 style={{ fontSize: 22, marginTop: 6, marginBottom: 4 }}>{q.heading || q.short} — by {hz}</h2>
                <div style={{ fontSize: 12.5, color: "var(--ink-soft)" }}>conditional on {axis.phrase}{axis.targetDate ? " (" + axFmtDate(axis.targetDate) + (axis.key === "eci" ? ", the same date at every horizon" : "") + ")" : ""}</div>
              </div>
              <div style={{ flexShrink: 0, display: "flex", gap: 10, flexWrap: "wrap" }}>
                <Toggle options={AX.axes.map(a => ({ key: a.key, label: a.short }))} value={akey} onChange={k => setAkey(k)} />
                <Toggle options={q.horizons.map(h => ({ key: h, label: "by " + h }))} value={hz} onChange={setHorizon} />
              </div>
            </div>
            <div style={{ marginTop: 14 }}>
              <AxisScatter axis={axis} q={q} hz={hz} models={AX.models} yDomain={axYDomain(q.id)}
                trailing={<button className="linkbtn" style={{ marginLeft: "auto" }} onClick={() => setShowText(!showText)}>{showText ? "hide what the model was told" : "what the model was told"}</button>} />
              {q.valueKind === "loss" && <ExpectedLossNote />}
              {q.valueKind === "loss" && <CountingWindow info={AX.instrumentInfo} horizon={hz} />}
            </div>
            {showText && <div style={{ marginTop: 12, fontSize: 12.5, color: "var(--ink-soft)", display: "grid", gap: 8 }}>
              <div><b>Conditioning instruction (ours).</b> {axis.instruction}</div>
              <div><b>The other axes.</b> {axis.assumption}</div>
              <div><b>Its own forecast first.</b> {axis.elicit.text}</div>
              {ref.kind === "leap" && refObj && <div><b>LEAP.</b> {ref.wave}, "{ref.question}", fielded {ref.fielded[0]} to {ref.fielded[1]}; superforecasters n={refObj.n}{ref.pBefore2100 ? `; P(before 2100) ${axFmtPct(ref.pBefore2100.superforecaster * 100)}` : ""}. Levels: {axis.levels.map(l => axFmtX(axis.fmt, l.value) + " (" + l.from + ")").join("; ")}.</div>}
              {ref.kind === "trend" && <div><b>Trend.</b> {ref.source}; {ref.pace} points a year. Levels: {axis.levels.map(l => axFmtX(axis.fmt, l.value) + " (" + l.from + ")").join("; ")}.</div>}
            </div>}
          </Panel>
        </div>
      </div>
    </React.Fragment>
  );
}
