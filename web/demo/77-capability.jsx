/* ============================ CAPABILITY: the frontier ECI and the forecast conditional on it ============================ */
// Nick, 2026-08-28: a "Capability" tab with two graphs -- the ECI history
// plus the models' own forecast of it (p25 / p50 / p75), and the questions
// conditional on progress, drawn by the SAME component as the Policy-levers
// chart with the model's three percentile worlds as the rows. The blob is
// redlines/views/capability.py; each variant (six months out; the end-of-2030
// set is off the tab for now) carries the same fields the policy blob does, so CondDeltaChart,
// CondDeltaTable and CondText render it unchanged through their `ctx`.
const CAP = (typeof window !== "undefined" && window.__CAPABILITY__) || null;

const capDate = s => new Date(s + (s.length === 10 ? "T00:00:00Z" : ""));
const capFmtDate = s => { const d = capDate(s); return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }); };
const capFmtEci = v => (v == null ? "—" : Number(v).toFixed(0));

/* ============================ the ECI chart ============================ */
// x is time (2023 -> just past the far target); y is the ECI score. The
// history is a step: the frontier stays where it is until a release beats
// it. The trend is metr_graph's p25-p75 band and p50 line, faint, from the
// anchor on -- the last frontier point, where the projection starts (its
// fitted value there sits on the point), so the cone grows out of the
// history. A forecast is one box plot at its target date -- the ENSEMBLE's
// (the median across models of each percentile): box from p25 to p75, a
// line at the median. One mark, not a whisker per model side by side --
// Nick, 2026-08-28: stacked whiskers "make it look like they're about
// different times". The
// active variant is drawn solid, the other faint, and clicking one
// switches the variant below. Per-model numbers are not on the page
// (Nick, 2026-08-28: no table under the chart); they are in the blob
// (forecast.models) and docs/conditional-forecasts.md.
function EciTrendChart({ eci, variants, active, onPick }) {
  const box = React.useRef(null);
  const cw = useContainerWidth(box, 900);
  const narrow = cw < 640;
  const W = Math.max(320, cw), H = narrow ? 300 : 360;
  const pad = { l: 60, r: narrow ? 14 : 24, t: 18, b: 32 };
  const hist = eci.history || [];
  const fc = variants.filter(v => v.forecast && v.forecast.models.length);
  const t0 = capDate("2023-01-01").getTime();
  const lastTarget = fc.reduce((m, v) => Math.max(m, capDate(v.targetDate).getTime()), 0);
  // The window ends eight months past the farthest target -- room for its
  // label on the right; the trend (the file runs to end-2030) is clipped to it.
  const t1 = Math.max(capDate("2027-06-30").getTime(), lastTarget + 240 * 86400e3);
  const curve = ((eci.trend && eci.trend.curve) || []).filter(c => capDate(c.date).getTime() <= t1);
  // The LEAP superforecasters' forecast of the same quantity (Wave 5: the top
  // US system's ECI at end-2026/2030/2040, p25/p50/p75), at the dates inside
  // the window -- end-2026, two months before the models' date (2026-09-03).
  const lp = CAP && CAP.leap;
  const lpPts = lp ? Object.keys(lp.dates).filter(d => capDate(d).getTime() <= t1).sort()
    .map(d => ({ date: d, ...((lp.dates[d] || {})[lp.shown || "superforecaster"] || {}) }))
    .filter(p => p.p50 != null) : [];
  const ys = [...hist.map(h => h.score), ...curve.flatMap(c => [c.p25, c.p75]),
              ...fc.flatMap(v => [v.forecast.ensemble.p25, v.forecast.ensemble.p75,
                                  v.forecast.ensemble.p10, v.forecast.ensemble.p90]),
              ...lpPts.flatMap(p => [p.p25, p.p75])].filter(v => v != null);
  const yLo = Math.floor((Math.min(...ys) - 4) / 10) * 10, yHi = Math.ceil((Math.max(...ys) + 4) / 10) * 10;
  const x = t => pad.l + ((typeof t === "number" ? t : capDate(t).getTime()) - t0) / (t1 - t0) * (W - pad.l - pad.r);
  const y = v => pad.t + (1 - (v - yLo) / (yHi - yLo)) * (H - pad.t - pad.b);
  const years = [];
  for (let yr = 2023; capDate(yr + "-01-01").getTime() <= t1; yr++) years.push(yr);
  const yTicks = [];
  for (let v = yLo; v <= yHi; v += (yHi - yLo) > 120 ? 20 : 10) yTicks.push(v);
  const [hv, setHv] = useState(null);
  // The step path: hold each score until the next new high.
  const step = hist.map((h, i) => {
    const xa = x(h.date), ya = y(h.score);
    const xb = i + 1 < hist.length ? x(hist[i + 1].date) : x(eci.trend && eci.trend.fit ? eci.trend.fit.anchor.date : h.date);
    return (i === 0 ? `M${xa},${ya}` : `L${xa},${ya}`) + `L${xb},${ya}`;
  }).join("");
  const band = curve.length ? "M" + curve.map(c => `${x(c.date)},${y(c.p75)}`).join("L") + "L" + [...curve].reverse().map(c => `${x(c.date)},${y(c.p25)}`).join("L") + "Z" : "";
  const p50 = curve.length ? "M" + curve.map(c => `${x(c.date)},${y(c.p50)}`).join("L") : "";
  const runDay = CAP && CAP.generatedAt ? CAP.generatedAt.slice(0, 10) : null;
  // Every label is its head alone -- the model or ensemble and its median,
  // centred under the lowest mark; the LEAP label is its head, left of its
  // box. The ranges and the dates live in the hover tooltip (Nick,
  // 2026-09-03: left of the boxes the three-line labels ran into each other
  // on a small screen; 2026-09-11: the narrow treatment at every width).
  const labels = fc.map(v => {
    const e = v.forecast.ensemble, ms = v.forecast.models;
    const who = ms.length === 1 ? ms[0].label : "ensemble";
    const head = (fc.length > 1 ? v.label + " · " : "") + (narrow ? "" : who + " ") + capFmtEci(e.p50);
    return { who, head };
  });
  // The lowest mark near the forecasts: the heads sit under it.
  const floor = Math.min(...fc.map(v => v.forecast.ensemble.p10 != null ? v.forecast.ensemble.p10 : v.forecast.ensemble.p25), ...lpPts.map(p => p.p25));
  return (
    <div ref={box} style={{ position: "relative", minWidth: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} onMouseLeave={() => setHv(null)}>
        {yTicks.map(v => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--line-soft)" />
            <text x={pad.l - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--ink-faint)" className="mono">{v}</text>
          </g>
        ))}
        {/* y-axis label (Nick, 2026-09-02) */}
        <text transform={`translate(12, ${(pad.t + H - pad.b) / 2}) rotate(-90)`} textAnchor="middle" fontSize="11" fill="var(--ink-soft)">Epoch Capabilities Index</text>
        {thinTicks(years, yr => x(yr + "-01-01"), narrow ? 40 : 0).map(yr => (
          <text key={yr} x={x(yr + "-01-01")} y={H - pad.b + 16} textAnchor="middle" fontSize="11" fill="var(--ink-faint)" className="mono">{yr}</text>
        ))}
        {runDay && <g>
          <line x1={x(runDay)} x2={x(runDay)} y1={pad.t} y2={H - pad.b} stroke="var(--ink-faint)" strokeDasharray="2 3" opacity="0.6" />
          <text x={x(runDay) + 4} y={pad.t + 10} fontSize="10.5" fill="var(--ink-faint)">forecast date</text>
        </g>}
        {band && <path d={band} fill="var(--ink-faint)" opacity="0.12" />}
        {p50 && <path d={p50} fill="none" stroke="var(--ink-faint)" strokeWidth="1.5" strokeDasharray="5 4" opacity="0.8" />}
        {curve.length > 0 && !narrow && (
          <text x={x(curve[curve.length - 1].date) - 4} y={y(curve[curve.length - 1].p50) - 6} textAnchor="end" fontSize="10.5" fill="var(--ink-faint)">ECI trend, median</text>
        )}
        <path d={step} fill="none" stroke="var(--ink)" strokeWidth="2" strokeLinejoin="round" />
        {hist.map(h => (
          <circle key={h.date + h.model} cx={x(h.date)} cy={y(h.score)} r={hv && hv.model === h.model ? 5 : 3.5}
            fill="var(--ink)" stroke="var(--panel)" strokeWidth="1.5" onMouseEnter={() => setHv({ x: x(h.date), y: y(h.score), model: h.model, title: h.model, lines: ["ECI " + h.score.toFixed(1) + " · " + capFmtDate(h.date)] })} style={{ cursor: "default" }} />
        ))}
        {fc.map((v, i) => {
          const on = v.key === active;
          const n = v.forecast.models.length;
          const xc = x(v.targetDate);
          // The ensemble: with one model, that model's own numbers.
          const e = v.forecast.ensemble;
          const { who, head } = labels[i];
          // The head alone, centred under the lowest mark; the quartiles,
          // the 10th–90th and the date are in the tooltip.
          const bw = narrow ? 12 : 16;
          const half = bw / 2;
          const lx = xc, ly = y(floor) + 16;
          const tip = { x: xc, y: y(e.p75), title: (fc.length > 1 ? v.label + " · " : "") + who + ": median " + capFmtEci(e.p50),
            lines: ["25–75th " + capFmtEci(e.p25) + "–" + capFmtEci(e.p75),
                    ...(e.p10 != null && e.p90 != null ? ["10–90th " + capFmtEci(e.p10) + "–" + capFmtEci(e.p90)] : []),
                    capFmtDate(v.targetDate) + (n > 1 ? " · " + n + " models" : "")] };
          return (
            <g key={v.key} opacity={on ? 1 : 0.4} onClick={() => onPick && onPick(v.key)} onMouseEnter={() => setHv(tip)} style={{ cursor: "pointer" }}>
              {/* Whiskers to the 10th and 90th percentiles (A4, asked since
                  2026-09-02); a day whose rows carry only the quartiles draws
                  the box alone. */}
              {e.p10 != null && e.p90 != null && <g stroke="var(--ink)" strokeOpacity="0.75" strokeWidth="1.5">
                <line x1={xc} x2={xc} y1={y(e.p90)} y2={y(e.p75)} />
                <line x1={xc} x2={xc} y1={y(e.p25)} y2={y(e.p10)} />
                <line x1={xc - half * 0.6} x2={xc + half * 0.6} y1={y(e.p90)} y2={y(e.p90)} />
                <line x1={xc - half * 0.6} x2={xc + half * 0.6} y1={y(e.p10)} y2={y(e.p10)} />
              </g>}
              <rect x={xc - half} y={y(e.p75)} width={bw} height={Math.max(2, y(e.p25) - y(e.p75))} rx="2" fill="var(--ink)" fillOpacity="0.14" stroke="var(--ink)" strokeOpacity="0.75" strokeWidth="1.5" />
              <line x1={xc - half} x2={xc + half} y1={y(e.p50)} y2={y(e.p50)} stroke="var(--ink)" strokeWidth="2.5" />
              <text x={lx} y={ly} textAnchor="middle" fontSize="12" fontWeight="600" fill="var(--ink)" paintOrder="stroke" stroke="var(--panel)" strokeWidth="3" strokeLinejoin="round">{head}</text>
            </g>
          );
        })}
        {lpPts.map(p => {
          const xc = x(p.date);
          const bw = narrow ? 12 : 16, half = bw / 2;
          // Label to the LEFT of the box, its top line at the p75 cap: the
          // models' box and label sit to the right, two months on, and the
          // frontier's last step runs below.
          const lx = xc - half - 8, ly = y(p.p75) + 4;
          const tip = { x: xc, y: y(p.p75), title: "LEAP superforecasters: median " + capFmtEci(p.p50),
            lines: ["25–75th " + capFmtEci(p.p25) + "–" + capFmtEci(p.p75), capFmtDate(p.date) + " · n=" + p.n] };
          return (
            <g key={"leap" + p.date} onMouseEnter={() => setHv(tip)}>
              <rect x={xc - half} y={y(p.p75)} width={bw} height={Math.max(2, y(p.p25) - y(p.p75))} rx="2" fill="var(--panel)" stroke="var(--ink)" strokeOpacity="0.75" strokeWidth="1.5" strokeDasharray="3 2" />
              <path d={`M${xc},${y(p.p50) - 6}L${xc + 6},${y(p.p50)}L${xc},${y(p.p50) + 6}L${xc - 6},${y(p.p50)}Z`} fill="var(--ink)" />
              <text x={lx} y={ly} textAnchor="end" fontSize="12" fontWeight="600" fill="var(--ink)" paintOrder="stroke" stroke="var(--panel)" strokeWidth="3" strokeLinejoin="round">{(narrow ? "LEAP " : "LEAP supers ") + capFmtEci(p.p50)}</text>
            </g>
          );
        })}
      </svg>
      {hv && (
        <div style={{ position: "absolute", left: Math.min(hv.x / W * 100, 65) + "%", top: Math.max(0, (hv.y / H) * 100 - 18) + "%", background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 8, padding: "6px 9px", boxShadow: "var(--shadow)", pointerEvents: "none", fontSize: 12, zIndex: 5, whiteSpace: "nowrap" }}>
          <div style={{ fontWeight: 600 }}>{hv.title}</div>
          {hv.lines.map(t => <div key={t} className="mono" style={{ color: "var(--ink-soft)" }}>{t}</div>)}
        </div>
      )}
    </div>
  );
}

/* ============================ the panel ============================ */
function CapabilityPanel({ onDefinitions }) {
  const variants = (CAP && CAP.variants || []).filter(v => v.questions && v.questions.length);
  if (!CAP || !variants.length) {
    return <ForecastUnavailable title="Forecasts conditional on AI capability" onDefinitions={onDefinitions} />;
  }
  // ?cap=<variant>&q=<question id>&h=<horizon> deep-links a chart.
  const params = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  const [vkey, setVkey] = useState(variants.some(v => v.key === params.get("cap")) ? params.get("cap") : (CAP.defaultVariant || variants[0].key));
  const V = variants.find(v => v.key === vkey) || variants[0];
  const Q = V.questions;
  const [qid, setQid] = useState(Q.some(x => x.id === params.get("q")) ? params.get("q") : Q[0].id);
  const [horizon, setHorizon] = useState(V.horizons.includes(params.get("h")) ? params.get("h") : V.defaultHorizon);
  const [picked, setPicked] = useState(null);
  const [showTable, setShowTable] = useState(false);
  const q = Q.find(x => x.id === qid) || Q[0];
  const hz = q.horizons.includes(horizon) ? horizon : q.horizons[0];
  const cell = q.byHorizon[hz];
  const eci = CAP.eci;

  return (
    <React.Fragment>
      <Panel style={{ padding: "16px 22px", marginBottom: 18 }}>
        <h2 style={{ fontSize: 22, marginTop: 0, marginBottom: 6 }}>How does the forecast depend on the pace of AI progress?</h2>
        <p style={{ color: "var(--ink-soft)", fontSize: 13.5, maxWidth: 820, margin: 0 }}>
          Models' forecasts of frontier <a href="https://epoch.ai/benchmarks/eci" target="_blank" rel="noopener"
          style={{ color: "var(--link)" }}>Epoch Capabilities Index</a>, along with risks conditional on those ECI scores.
        </p>
      </Panel>

      <Panel style={{ padding: "18px 22px", marginBottom: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div style={{ minWidth: 0 }}>
            <h2 style={{ fontSize: 22, marginTop: 0 }}>How models forecast frontier capability</h2>
          </div>
          {variants.length > 1 && <div style={{ flexShrink: 0 }}>
            <Toggle options={variants.map(v => ({ key: v.key, label: v.label }))} value={vkey} onChange={k => { setVkey(k); setPicked(null); }} />
          </div>}
        </div>
        <div style={{ marginTop: 14 }}>
          <EciTrendChart eci={eci} variants={variants} active={vkey} onPick={k => { setVkey(k); setPicked(null); }} />
        </div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
          <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><span style={{ width: 18, height: 2, background: "var(--ink)" }}></span>Frontier ECI</span>
          <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><svg width="14" height="18" viewBox="0 0 14 18"><rect x="1.5" y="2" width="11" height="14" rx="2" fill="var(--ink)" fillOpacity="0.14" stroke="var(--ink)" strokeOpacity="0.75" strokeWidth="1.5" /><line x1="1.5" x2="12.5" y1="9" y2="9" stroke="var(--ink)" strokeWidth="2.5" /></svg>Ensemble's ECI percentiles</span>
          {CAP && CAP.leap && <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><svg width="14" height="18" viewBox="0 0 14 18"><rect x="1.5" y="2" width="11" height="14" rx="2" fill="var(--panel)" stroke="var(--ink)" strokeOpacity="0.75" strokeWidth="1.5" strokeDasharray="3 2" /><path d="M7,5L11,9L7,13L3,9Z" fill="var(--ink)" /></svg><span>LEAP supers (<a href={CAP.leap.url}>Wave 5</a>)</span></span>}
          <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><span style={{ width: 18, height: 10, background: "var(--ink-faint)", opacity: 0.25 }}></span><span>ECI trend (<a href={eci.trend.url}>Peter Wildeford</a>)</span></span>
        </div>
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
                <h2 style={{ fontSize: 22, marginTop: 0, marginBottom: 4 }}>{q.heading || q.short} — by {hz}</h2>
                <div style={{ fontSize: 12.5, color: "var(--ink-soft)" }}>Risk conditional on each model's own estimates for frontier ECI on {capFmtDate(V.targetDate)}.</div>
              </div>
              <div style={{ flexShrink: 0 }}>
                <Toggle options={q.horizons.map(h => ({ key: h, label: "by " + h }))} value={hz} onChange={setHorizon} />
              </div>
            </div>

            {cell.note && <div style={{ fontSize: 12.5, color: "var(--warn-ink)", background: "var(--warn-bg)", border: "1px solid var(--warn-line)", borderRadius: 8, padding: "6px 10px", margin: "12px 0 0" }}>{cell.note}.</div>}

            <div style={{ marginTop: 14 }}>
              <CondDeltaChart cell={cell} ctx={V} picked={picked} onPick={id => setPicked(picked === id ? null : id)}
                axisValues={q.valueKind === "loss"
                  ? Q.filter(x => x.valueKind === "loss").flatMap(x => x.horizons.flatMap(h => condAxisValues(x.byHorizon[h])))
                  : q.horizons.flatMap(h => condAxisValues(q.byHorizon[h]))} />
            </div>

            <QuestionBox q={q} />

            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
              {V.models.map(m => <LegendDot key={m.label} color={m.color} label={m.label} />)}
              <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><svg width="22" height="14" viewBox="0 0 22 14"><rect x="1" y="2" width="16" height="10" rx="2" fill="var(--ink-soft)" opacity="0.38" /><line x1="17" x2="17" y1="0" y2="14" stroke="var(--ink)" strokeWidth="2.5" /></svg>median conditional change</span>
              <span style={{ fontSize: 12.5, color: "var(--ink-soft)", display: "inline-flex", alignItems: "center", gap: 7 }}><span style={{ width: 10, height: 10, borderRadius: 5, border: "2px solid var(--ink-soft)", background: "var(--panel)" }}></span>no search evidence</span>
              <button className="linkbtn" style={{ marginLeft: "auto" }} onClick={() => setShowTable(!showTable)}>{showTable ? "hide table" : "show table"}</button>
            </div>
            {showTable && <div style={{ marginTop: 12 }}><CondDeltaTable cell={cell} ctx={V} /></div>}
            {q.valueKind === "loss" && <CountingWindow info={V.instrumentInfo} horizon={hz} />}
            {onDefinitions && <button className="linkbtn" onClick={onDefinitions} style={{ fontSize: 12, marginTop: 10 }}>Definitions →</button>}
          </Panel>

        </div>
      </div>
    </React.Fragment>
  );
}
