/* ============================ WELFARE ============================ */
// The welfare instrument's page (redlines/views/welfare.py): life expectancy
// and GDP growth as five percentiles, unconditional and under the combined
// set's conditions. Built from the dashboard's own atoms, rail, CondText and
// EciTrendChart; the one new mark is a percentile box per row, laid out as
// CondDeltaChart lays out its rows. These are the welfare pilot's own
// components (welfare.html of 2026-10-01, protocol welfare-v1-pilot), as
// published; since 2026-10-22 the header shows the run date where the pilot
// said PILOT, and names the five prompts each number is the mean of.
const WF = (typeof window !== "undefined" && window.__WELFARE__) || null;

const wFmt = (v, unit) => (v == null ? "—" : unit === "years" ? v.toFixed(1) : v.toFixed(2) + "%");
const wFmtShift = (v, unit) => {
  if (v == null) return "—";
  const r = Number(wFmt(Math.abs(v), "years" === unit ? unit : null).replace("%", ""));
  return (r === 0 ? "±" : v > 0 ? "+" : "−") + wFmt(Math.abs(v), unit);
};
const wTick = (t, unit) => (unit === "years" ? String(Number(t.toPrecision(4))) : Number(t.toPrecision(3)) + "%");

function wTicks(values) {
  const v = values.filter(x => x != null && isFinite(x));
  let lo = Math.min(...v), hi = Math.max(...v);
  if (!(hi > lo)) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / 6;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
  const a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step;
  const ticks = [];
  for (let t = a; t <= b + step * 1e-6; t += step) ticks.push(Number(t.toFixed(10)));
  return { ticks, lo: a, hi: b };
}

const wQs = rows => rows.flatMap(r => r.models.map(m => m.q)).filter(Boolean);
const wAxisValues = rows => wQs(rows).flatMap(q => [q.p10, q.p90]);
const wMedian = xs => { const s = xs.filter(x => x != null).sort((a, b) => a - b); return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : null; };

// The cell's rows: the same-session unconditional first, then each condition
// of the tab's group.
function wCellRows(cell, group) {
  return [{ id: "unconditional", label: "Unconditional", sub: "each model, same session", models: cell.baselines },
          ...cell.bars.filter(b => !group || b.group === group).map(b => ({ id: b.id, label: b.label, sub: b.leapId, models: b.models }))];
}

/* ============================ the percentile chart ============================ */
// One row per condition, as in CondDeltaChart: label left, value right, the
// unconditional median as the vertical line. The mark is each model's
// percentiles: whisker p10–p90, box p25–p75, a heavy line at p50, in the
// model's colour.
function WelfareChart({ rows, unit, axisValues, picked, onPick, zero, valueText, conditions }) {
  const box = React.useRef(null);
  const cw = useContainerWidth(box, 900);
  const narrow = cw < 640;
  const W = Math.max(320, cw), rowH = narrow ? 66 : 44;
  const pad = narrow ? { l: 14, r: 14, t: 26, b: 34 } : { l: 250, r: 150, t: 26, b: 34 };
  const barY = cy => (narrow ? cy + 6 : cy);
  const maxChars = narrow ? Math.max(18, Math.floor((W - pad.l - pad.r - 96) / 6.6)) : 36;
  const clip = s => (s && s.length > maxChars ? s.slice(0, maxChars - 2) + "…" : s);
  const chip = (xLeft, yTop, text, perChar) => <rect x={xLeft - 3} y={yTop} width={(text || "").length * perChar + 6} height={15} rx="2" fill="var(--panel)" opacity="0.92" />;
  const H = pad.t + pad.b + rowH * rows.length;
  const { ticks, lo, hi } = wTicks(axisValues || wAxisValues(rows));
  const x = v => pad.l + Math.min(1, Math.max(0, (v - lo) / (hi - lo))) * (W - pad.l - pad.r);
  const rowY = i => pad.t + rowH * i + rowH / 2;
  const [hv, setHv] = useState(null);
  // The hovered box: its model's five percentiles, in EciTrendChart's
  // tooltip format. While it shows, the condition-text tooltip does not.
  const [bx, setBx] = useState(null);
  const x0 = zero == null ? null : x(zero);

  return (
    <div ref={box} style={{ position: "relative", minWidth: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} onMouseLeave={() => { setHv(null); setBx(null); }}>
        {thinTicks(ticks, x, narrow ? 38 : 0).map(t => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={pad.t - 4} y2={H - pad.b} stroke="var(--line-soft)" />
            <text x={x(t)} y={H - pad.b + 16} textAnchor="middle" fontSize="11" fill="var(--ink-faint)" className="mono">{wTick(t, unit)}</text>
          </g>
        ))}
        {x0 != null && <>
          <line x1={x0} x2={x0} y1={pad.t - 10} y2={H - pad.b} stroke="var(--ink)" strokeWidth="1.5" />
          <text x={x0} y={pad.t - 14} textAnchor={narrow ? (x0 < W * 0.3 ? "start" : x0 > W * 0.7 ? "end" : "middle") : "middle"} fontSize="11" fill="var(--ink-soft)" fontWeight="600">unconditional</text>
          <text x={narrow ? pad.l : pad.l - 8} y={H - pad.b + 30} textAnchor={narrow ? "start" : "end"} fontSize="11" fill="var(--ink-faint)">◀ lower</text>
          <text x={narrow ? W - pad.r : W - pad.r + 8} y={H - pad.b + 30} textAnchor={narrow ? "end" : "start"} fontSize="11" fill="var(--ink-faint)">higher ▶</text>
        </>}
        {rows.map((r, i) => {
          const cy = rowY(i), by = barY(cy);
          const isPicked = picked === r.id;
          const base = r.id === "unconditional";
          const vt = valueText(r);
          const n = r.models.length;
          const bh = n > 1 ? Math.max(6, 16 / n) : 14;
          return (
            <g key={r.id} onMouseEnter={() => setHv(r.id)} onClick={() => onPick && !base && onPick(r.id)} style={{ cursor: base ? "default" : "pointer" }}>
              <rect x={0} y={cy - rowH / 2} width={W} height={rowH} fill={base ? "var(--line-soft)" : (isPicked || hv === r.id ? "var(--line-soft)" : "transparent")} opacity={base ? 0.35 : 0.6} />
              {narrow ? <>
                {chip(pad.l, cy - 30, clip(r.label), 6.6)}
                <text x={pad.l} y={cy - 19} textAnchor="start" fontSize="12.5" fill="var(--ink)" fontWeight={isPicked || base ? 600 : 500}>{clip(r.label)}</text>
                {chip(W - pad.r - vt.length * 7.2, cy - 30, vt, 7.2)}
                <text x={W - pad.r} y={cy - 19} textAnchor="end" fontSize="12" fill="var(--ink)" className="mono" fontWeight="600">{vt}</text>
                {r.sub && chip(pad.l, cy + 16, r.sub, 6.3)}
                {r.sub && <text x={pad.l} y={cy + 27} textAnchor="start" fontSize="10.5" fill="var(--ink-faint)" className="mono">{r.sub}</text>}
              </> : <>
                <text x={pad.l - 14} y={cy + 4} textAnchor="end" fontSize="12.5" fill="var(--ink)" fontWeight={isPicked || base ? 600 : 500}>{clip(r.label)}</text>
                {r.sub && <text x={pad.l - 14} y={cy + 17} textAnchor="end" fontSize="10.5" fill="var(--ink-faint)" className="mono">{r.sub}</text>}
                <text x={W - pad.r + 12} y={cy + 4} fontSize="12" fill="var(--ink)" className="mono" fontWeight="600">{vt}</text>
              </>}
              {r.models.map((m, j) => {
                const q = m.q;
                if (!q) return null;
                const yy = by + (j - (n - 1) / 2) * (bh + 3);
                const c = m.color || "var(--ink)";
                const hollow = m.grounded === false;
                const tip = { x: x(q.p50), y: yy - bh / 2, title: m.label + (r.sub && r.id !== "unconditional" ? " · " + r.label : "") + ": median " + wFmt(q.p50, unit),
                  lines: ["25–75th " + wFmt(q.p25, unit) + "–" + wFmt(q.p75, unit), "10–90th " + wFmt(q.p10, unit) + "–" + wFmt(q.p90, unit)] };
                return (
                  <g key={m.label} onMouseEnter={() => setBx(tip)} onMouseLeave={() => setBx(null)}>
                    <rect x={x(q.p10) - 4} y={yy - bh / 2 - 4} width={x(q.p90) - x(q.p10) + 8} height={bh + 8} fill="transparent" />
                    <line x1={x(q.p10)} x2={x(q.p90)} y1={yy} y2={yy} stroke={c} strokeWidth="1.5" />
                    <line x1={x(q.p10)} x2={x(q.p10)} y1={yy - bh * 0.3} y2={yy + bh * 0.3} stroke={c} strokeWidth="1.5" />
                    <line x1={x(q.p90)} x2={x(q.p90)} y1={yy - bh * 0.3} y2={yy + bh * 0.3} stroke={c} strokeWidth="1.5" />
                    <rect x={x(q.p25)} y={yy - bh / 2} width={Math.max(2, x(q.p75) - x(q.p25))} height={bh} rx="2"
                      fill={hollow ? "var(--panel)" : c} fillOpacity={hollow ? 1 : 0.18} stroke={c} strokeWidth="1.5" />
                    <line x1={x(q.p50)} x2={x(q.p50)} y1={yy - bh / 2 - 2} y2={yy + bh / 2 + 2} stroke={c} strokeWidth="2.5" />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      {bx && (
        <div style={{ position: "absolute", left: Math.min(bx.x / W * 100, 65) + "%", top: (bx.y / H) * 100 + "%", transform: "translate(-50%, calc(-100% - 6px))", background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 8, padding: "6px 9px", boxShadow: "var(--shadow)", pointerEvents: "none", fontSize: 12, zIndex: 6, whiteSpace: "nowrap" }}>
          <div style={{ fontWeight: 600 }}>{bx.title}</div>
          {bx.lines.map(t => <div key={t} className="mono" style={{ color: "var(--ink-soft)" }}>{t}</div>)}
        </div>
      )}
      {!bx && hv != null && hv !== "unconditional" && conditions && (() => {
        const i = rows.findIndex(r => r.id === hv);
        const cond = conditions.find(c => c.id === hv);
        if (!cond) return null;
        const top = ((pad.t + rowH * i) / H) * 100;
        const desc = cond.description || "";
        const cut = desc.length > 900 ? desc.slice(0, 900).replace(/\s+\S*$/, "") + " …" : desc;
        return (
          <div style={{ position: "absolute", top: `${top}%`, right: 8, transform: "translateY(-100%)", background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 8, padding: "10px 12px", boxShadow: "var(--shadow)", pointerEvents: "none", width: 460, maxWidth: narrow ? "calc(100% - 16px)" : "60%", zIndex: 5 }}>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginBottom: 3 }}>What the model was told{cond.leapId ? <> · <span className="mono">{cond.leapId}</span></> : null}</div>
            <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>{cond.label}</div>
            {cond.assume && <div style={{ fontSize: 12.5, color: "var(--ink)", marginBottom: 6 }}><strong>Condition.</strong> {cond.assume}</div>}
            {cut && <div style={{ fontSize: 12, color: "var(--ink-soft)", whiteSpace: "pre-wrap", lineHeight: 1.45 }}>{cut}</div>}
            {desc.length > 900 && <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 6 }}>click the row for the full text</div>}
          </div>
        );
      })()}
    </div>
  );
}

function WelfareTable({ rows, unit, zeroOf }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="tv">
        <thead>
          <tr><th>condition</th><th>model</th>{["p10", "p25", "p50", "p75", "p90"].map(k => <th key={k}>{k}</th>)}<th>Δ p50</th></tr>
        </thead>
        <tbody>
          {rows.flatMap(r => r.models.map((m, j) => (
            <tr key={r.id + m.label} style={r.id === "unconditional" ? { fontWeight: 600 } : null}>
              <td>{j === 0 ? <>{r.label} {r.sub && r.id !== "unconditional" ? <span className="mono" style={{ color: "var(--ink-faint)" }}>{r.sub}</span> : null}</> : ""}</td>
              <td>{m.label}</td>
              {["p10", "p25", "p50", "p75", "p90"].map(k => <td key={k} className="mono">{m.q ? wFmt(m.q[k], unit) : "—"}</td>)}
              <td className="mono">{r.id === "unconditional" ? "" : wFmtShift(m.shift, unit)}</td>
            </tr>
          )))}
        </tbody>
      </table>
    </div>
  );
}

const WBoxSwatch = ({ label }) => (
  <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}>
    <svg width="34" height="14" viewBox="0 0 34 14"><line x1="1" x2="33" y1="7" y2="7" stroke="var(--ink-soft)" strokeWidth="1.5" /><line x1="1" x2="1" y1="3" y2="11" stroke="var(--ink-soft)" strokeWidth="1.5" /><line x1="33" x2="33" y1="3" y2="11" stroke="var(--ink-soft)" strokeWidth="1.5" /><rect x="9" y="1.5" width="16" height="11" rx="2" fill="var(--ink-soft)" fillOpacity="0.18" stroke="var(--ink-soft)" strokeWidth="1.5" /><line x1="17" x2="17" y1="0" y2="14" stroke="var(--ink)" strokeWidth="2.5" /></svg>
    {label}
  </span>
);

/* ============================ a conditional tab ============================ */
function WelfareCondPanel({ group }) {
  const params = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  const Q = WF.questions;
  const [qid, setQid] = useState(Q.some(x => x.id === params.get("q")) ? params.get("q") : Q[0].id);
  const [horizon, setHorizon] = useState(params.get("h"));
  const [picked, setPicked] = useState(null);
  const [showTable, setShowTable] = useState(false);
  const q = Q.find(x => x.id === qid) || Q[0];
  const hz = q.horizons.includes(horizon) ? horizon : q.horizons[0];
  const rows = wCellRows(q.byHorizon[hz], group);
  const axis = q.horizons.flatMap(h => wAxisValues(wCellRows(q.byHorizon[h], group)));
  const zero = wMedian(rows[0].models.map(m => m.q && m.q.p50));
  const cond = WF.conditions.find(c => c.id === picked);
  const valueText = r => {
    const p = wMedian(r.models.map(m => m.q && m.q.p50));
    return r.id === "unconditional" ? wFmt(p, q.unit) : wFmt(p, q.unit) + " · " + wFmtShift(wMedian(r.models.map(m => m.shift)), q.unit);
  };
  const variants = Object.keys(WF.eciForecast || {}).length ? [{ key: "6mo", label: "6 months", targetDate: WF.targetDate,
    forecast: { models: WF.models, ensemble: Object.fromEntries(["p10", "p25", "p50", "p75", "p90"].map(k => [k, wMedian(Object.values(WF.eciForecast).map(e => e && e[k]))])) } }] : [];

  return (
    <React.Fragment>
      {group === "capability" && CAP && variants.length > 0 && (
        <Panel style={{ padding: "18px 22px", marginBottom: 18 }}>
          <h2 style={{ fontSize: 22, marginTop: 0 }}>How models forecast frontier capability</h2>
          <div style={{ marginTop: 14 }}>
            <EciTrendChart eci={CAP.eci} variants={variants} active="6mo" />
          </div>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
            <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><span style={{ width: 18, height: 2, background: "var(--ink)" }}></span>Frontier ECI</span>
            <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><svg width="14" height="18" viewBox="0 0 14 18"><rect x="1.5" y="2" width="11" height="14" rx="2" fill="var(--ink)" fillOpacity="0.14" stroke="var(--ink)" strokeOpacity="0.75" strokeWidth="1.5" /><line x1="1.5" x2="12.5" y1="9" y2="9" stroke="var(--ink)" strokeWidth="2.5" /></svg>{WF.models.length === 1 ? WF.models[0].label : "Ensemble"}'s ECI percentiles</span>
            {CAP.leap && <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><svg width="14" height="18" viewBox="0 0 14 18"><rect x="1.5" y="2" width="11" height="14" rx="2" fill="var(--panel)" stroke="var(--ink)" strokeOpacity="0.75" strokeWidth="1.5" strokeDasharray="3 2" /><path d="M7,5L11,9L7,13L3,9Z" fill="var(--ink)" /></svg><span>LEAP supers (<a href={CAP.leap.url}>Wave 5</a>)</span></span>}
          </div>
        </Panel>
      )}

      <div className="rail-grid" style={{ gap: 18 }}>
        <Panel style={{ padding: 14 }}>
          <QuestionRail title="Question" value={q.id} onChange={setQid}
            items={Q.map(x => ({ key: x.id, label: x.railLabel || x.short, color: x.color, group: x.group }))} />
        </Panel>

        <div style={{ minWidth: 0 }}>
          <Panel style={{ padding: "18px 22px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
              <div style={{ minWidth: 0 }}>
                <h2 style={{ fontSize: 22, marginTop: 0 }}>{q.heading} — {hz}</h2>
              </div>
              <div style={{ flexShrink: 0 }}>
                <Toggle options={q.horizons.map(h => ({ key: h, label: h }))} value={hz} onChange={setHorizon} />
              </div>
            </div>

            <div style={{ marginTop: 14 }}>
              <WelfareChart rows={rows} unit={q.unit} axisValues={axis} zero={zero} valueText={valueText}
                conditions={WF.conditions} picked={picked} onPick={id => setPicked(picked === id ? null : id)} />
            </div>

            <QuestionBox q={q} />

            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
              {WF.models.map(m => <LegendDot key={m.label} color={m.color} label={m.label} />)}
              <WBoxSwatch label="10th · 25th–75th · 90th, median" />
              <button className="linkbtn" style={{ marginLeft: "auto" }} onClick={() => setShowTable(!showTable)}>{showTable ? "hide table" : "show table"}</button>
            </div>
            {showTable && <div style={{ marginTop: 12 }}><WelfareTable rows={rows} unit={q.unit} /></div>}
            <WelfareRationales q={q} context={q.heading} />
          </Panel>

          {group === "policy" && cond && <CondText cond={cond} conditioning={WF.conditioning.policy} />}
        </div>
      </div>
    </React.Fragment>
  );
}

/* ============================ rationales ============================ */
// ForecastRationales (65-rationales.jsx), for percentile forecasts: the same
// collapsible, model buttons, explanation, weakest assumption, sources and
// provenance; the table holds the model's unconditional percentiles on
// every horizon.
function WelfareRationales({ q, context, controls }) {
  const R = WF.rationales || { calls: {}, questions: {} };
  const [selected, setSelected] = useState("");
  const entries = R.questions[q.id] || {};
  const models = Object.keys(entries);
  const model = models.includes(selected) ? selected : models[0];
  const calls = (entries[model] || []).map(id => [id, R.calls[id]]).filter(([, c]) => c);
  const rows = q.horizons.map(h => [h, ((q.byHorizon[h].baselines || []).find(b => b.label === model) || {}).q]).filter(([, v]) => v);
  return <details style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--line-soft)", fontSize: 13, lineHeight: 1.6 }}>
    <summary style={{ cursor: "pointer", fontWeight: 600, color: "var(--ink)" }}>Model rationale for its forecasts</summary>
    {controls}
    <p style={{ margin: "10px 0", fontWeight: 600 }}>{context}</p>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {models.map(m => <button key={m} aria-pressed={model === m} onClick={() => setSelected(m)}
        style={{ padding: "7px 10px", border: "1px solid var(--line)", borderRadius: 8, cursor: "pointer", background: model === m ? "var(--ink)" : "var(--panel)", color: model === m ? "white" : "var(--ink)" }}>
        {m}
      </button>)}
    </div>
    {rows.length > 0 && <div style={{ overflowX: "auto", marginTop: 12 }}>
      <table className="tv" style={{ width: "auto", minWidth: 260 }}>
        <thead><tr><th>Horizon</th>{["p10", "p25", "p50", "p75", "p90"].map(k => <th key={k}>{k}</th>)}</tr></thead>
        <tbody>{rows.map(([h, v]) => <tr key={h}>
          <td>{h}</td>
          {["p10", "p25", "p50", "p75", "p90"].map(k => <td key={k} className="mono">{wFmt(v[k], q.unit)}</td>)}
        </tr>)}</tbody>
      </table>
    </div>}
    {!calls.length && <p>No explanation recorded for this forecast.</p>}
    {calls.map(([id, c]) => {
      const explanation = (c.debriefs || {})[q.id];
      return <div key={id} style={{ marginTop: 14 }}>
        <p style={{ fontSize: 12, color: "var(--ink-soft)" }}>{explanation ? "Model’s explanation for this question, recorded after its forecasts. Covers all horizons." : "Model’s original explanation for its full forecast batch; not specific to this question or horizon."}</p>
        <p style={{ whiteSpace: "pre-wrap" }}>{(explanation && explanation.rationale) || c.rationale || "No written rationale recorded."}</p>
        {explanation && explanation.weakest_link && <p><strong>Weakest assumption: </strong>{explanation.weakest_link}</p>}
        <details><summary style={{ cursor: "pointer" }}>Sources cited by this model</summary>
          <RationaleSources sources={(explanation && explanation.key_sources) || c.sources} />
        </details>
        <details style={{ marginTop: 8 }}><summary style={{ cursor: "pointer" }}>Original batch explanation and provenance</summary>
          {explanation && <p style={{ whiteSpace: "pre-wrap" }}>{c.rationale}</p>}
          <p style={{ overflowWrap: "anywhere", color: "var(--ink-soft)" }}>Model: {c.modelId}<br />Elicited: {c.elicitedAt}<br />Run: {c.run}<br />Call: {id}<br />Protocol: {c.protocol}</p>
        </details>
      </div>;
    })}
  </details>;
}

/* ============================ the forecasts tab ============================ */
// Every question x horizon, unconditional, one chart per unit.
function WelfareForecastsPanel() {
  const units = [...new Set(WF.questions.map(q => q.unit))];
  const [pick, setPick] = useState({});
  return (
    <React.Fragment>
      {units.map(u => {
        const qs = WF.questions.filter(q => q.unit === u);
        const rows = qs.flatMap(q => q.horizons.map(h => ({ id: q.id + "@" + h, label: q.short, sub: h, models: q.byHorizon[h].baselines })));
        return (
          <Panel key={u} style={{ padding: "18px 22px", marginBottom: 18 }}>
            <h2 style={{ fontSize: 22, marginTop: 0 }}>{qs[0].group}</h2>
            <div style={{ marginTop: 14 }}>
              <WelfareChart rows={rows} unit={u} zero={null}
                valueText={r => wFmt(wMedian(r.models.map(m => m.q && m.q.p50)), u)} />
            </div>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
              {WF.models.map(m => <LegendDot key={m.label} color={m.color} label={m.label} />)}
              <WBoxSwatch label="10th · 25th–75th · 90th, median" />
            </div>
            {(() => {
              const sel = qs.find(x => x.id === pick[u]) || qs[0];
              const controls = <div className="rationale-controls">
                <label>Question <select value={sel.id} onChange={e => setPick({ ...pick, [u]: e.target.value })}>{qs.map(x => <option key={x.id} value={x.id}>{x.short}</option>)}</select></label>
              </div>;
              return <WelfareRationales q={sel} context={sel.heading} controls={controls} />;
            })()}
          </Panel>
        );
      })}
    </React.Fragment>
  );
}

/* ============================ app ============================ */
function App() {
  const tabParam = new URLSearchParams(typeof location !== "undefined" ? location.search : "").get("tab");
  const [mainTab, setMainTab] = useState(["forecasts", "capability", "conditional"].includes(tabParam) ? tabParam : "forecasts");
  if (!WF) return <ForecastUnavailable title="Welfare" />;
  return (
    <React.Fragment>
      <header style={{ marginBottom: 20, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 24, flexWrap: "wrap" }}>
        <div style={{ minWidth: 0, flex: "1 1 520px" }}>
          <a href="https://forecastingresearch.org" title="Forecasting Research Institute"><img className="brand-logo" src="web/img/fri-logo.svg" alt="Forecasting Research Institute" width="231" height="37" /></a>
          <h1 style={{ fontSize: "clamp(25px, 7.5vw, 33px)", marginTop: 8, marginBottom: 6 }}>AIRO (Automated AI Risk Outlook)</h1>
        </div>
      </header>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 10, fontSize: 13, color: "var(--ink-soft)" }}>
        <span style={{ background: "var(--warn-bg)", border: "1px solid var(--warn-line)", borderRadius: 999, color: "var(--warn-ink)", fontWeight: 700, letterSpacing: "0.04em", padding: "3px 8px" }}>{WF.day}</span>
        <span className="mono">{WF.run} · {WF.protocol} · {WF.models.map(m => m.label + (WF.usage[m.label] && WF.usage[m.label].cost_usd != null ? " $" + WF.usage[m.label].cost_usd.toFixed(2) : "")).join(", ")}</span>
      </div>
      <details style={{ marginBottom: 14, fontSize: 13, color: "var(--ink-soft)" }}>
        <summary style={{ cursor: "pointer" }}>Each model's number is the mean of its forecasts under {WF.prompts.length} prompts</summary>
        <ol style={{ margin: "8px 0 0", paddingLeft: 22 }}>
          {WF.prompts.map(p => <li key={p.condition} style={{ marginBottom: 4 }}><span className="mono">{p.condition}</span>: {p.text || "the instrument as it stands, with no added instruction."}</li>)}
        </ol>
      </details>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 20 }}>
        <Toggle options={[{ key: "forecasts", label: "Forecasts" }, { key: "capability", label: "Capability" }, { key: "conditional", label: "Policy levers" }]}
          value={mainTab} onChange={setMainTab} />
      </div>
      {mainTab === "forecasts" && <WelfareForecastsPanel />}
      {mainTab === "capability" && <WelfareCondPanel group="capability" />}
      {mainTab === "conditional" && <WelfareCondPanel group="policy" />}
    </React.Fragment>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
