/* ============================ Timeline · live (window.__TIMELINE__) ============================ */
// How the AI-catastrophe forecast MOVES between elicitation dates: one dot
// per prompt condition since Oct 21, the ensemble median as an ink mark, at the horizon
// the picker selects (2030 to open). The lead panel of the Forecasts tab
// since 2026-09-08 (Nick: the series is the first thing a visitor sees, not
// a link to it) -- it was a standalone timeline.html from 2026-08-11 until
// then. One question since 2026-09-09 (Nick): the risk-category rail went,
// so the chart takes the panel's full width, as Graph 2's does; the blob
// (redlines/views/timeline.py, which reads the run log from
// redlines.runlog.SERIES_START on: one call per model per run, no re-run
// bands) still carries every bottom-line question, and this file reads the
// one row, catastrophe:ai.
const TL = (typeof window !== "undefined" && window.__TIMELINE__) || null;

// Formatters, tl-prefixed: this page is one script, and Graph 1 (cFmtBig,
// cFmtLoss) and the mock (niceMax, TimeSeriesChart) already own the plain names.
const tlFmt = v => (v == null ? "—" : v < 10 ? v.toFixed(2) + "%" : v.toFixed(1) + "%");
const tlFmtD = d => (d == null ? "—" : (d > 0 ? "+" : d < 0 ? "−" : "±") + Math.abs(d).toFixed(2) + " pp");
// Death-equivalents for the expected-loss rows: 2.44M, $24.4T.
const tlFmtBig = (v, prefix) => {
  if (v == null) return "—";
  const p = prefix || "";
  const units = [[1e15, "Q"], [1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "k"]];
  for (const [cut, suf] of units) if (Math.abs(v) >= cut) return p + Number((v / cut).toPrecision(3)) + suf;
  return p + Number(v.toPrecision(3));
};
const tlFmtLoss = v => (v == null ? "—" : tlFmtBig(v));
const tlFmtRatio = r => (r == null || !isFinite(r) ? "—" : "×" + (r >= 10 ? r.toFixed(0) : r.toFixed(2)));
// One formatter per row kind.
const tlFmtFor = q => (q && q.value_kind === "loss" ? tlFmtBig : tlFmt);

// Colors belong to prompt conditions, never to models or their array order.
// New condition IDs stay neutral until explicitly assigned a color here.
const TL_CONDITION_START = "2026-10-21";
const TL_CONDITIONS = {
  none: { label: "Baseline", color: "#0969da" },
  independent: { label: "Independent", color: "#bc4c00" },
  recent: { label: "Recent", color: "#1a7f37" },
  critical: { label: "Critical", color: "#8250df" },
  "two-step": { label: "Two-step", color: "#bf3989" },
};
const tlVariants = (q, horizon, snapshots) => {
  const info = Object.fromEntries(((TL && TL.variants) || []).map(v => [v.id, v]));
  return Object.entries(q.variants || {}).map(([id, hs]) => ({
    id, ...(TL_CONDITIONS[id] || { label: id, color: "var(--ink-soft)" }),
    vals: (hs[horizon] || []).map((v, i) => snapshots[i].date >= TL_CONDITION_START ? v : null),
    models: ((q.variantModels || {})[id] || {})[horizon] || [],
    text: (info[id] || {}).text,
  })).filter(v => v.vals.some(val => val != null));
};

// React owns the content; Tippy owns placement relative to the actual SVG dot.
function TimelinePointTooltip({ anchor, children }) {
  const [content] = useState(() => document.createElement("div"));
  const tooltip = React.useRef(null);
  React.useEffect(() => {
    if (!anchor || !window.tippy) return;
    const instance = window.tippy(anchor, {
      content, trigger: "manual", theme: "light-border", arrow: true,
      maxWidth: 340, offset: [0, 8], placement: "top", appendTo: () => document.body,
      animation: false,
    });
    tooltip.current = instance;
    instance.show();
    return () => { instance.destroy(); tooltip.current = null; };
  }, [anchor, content]);
  // Scale changes can move a pinned dot without changing its DOM element.
  React.useLayoutEffect(() => {
    if (tooltip.current && tooltip.current.popperInstance) tooltip.current.popperInstance.update();
  });
  return ReactDOM.createPortal(children, content);
}

/* ---------------- time-series chart ---------------- */
// Before Oct 21 only the median is visible until hovered or selected; then
// model answers appear as ink-gray circles. Since Oct 21 each prompt condition
// has a colored dot, with model answers in its details. No connecting lines.
// The ensemble median remains an ink mark, for the ONE horizon
// the panel's picker selects (Nick, 2026-09-09: a horizon picker, Graph 2's,
// in place of the six shaded lines of the day before). No line joins the
// medians since 2026-10-21 (project lead): the series spans a protocol change.
// Expected-deaths rows plot deaths on the shared severity axis (rung ticks,
// Extinction marked), log only. No intervals since 2026-10-21 (project
// lead): a date's draws are its prompt variants, not re-asks.
function TimelineChart({ q, snapshots, horizon, scale }) {
  const loss = q.value_kind === "loss";
  // Laid out in the width the panel gives it (web/shared/responsive.jsx);
  // under 620px the right-margin label goes — the tooltip carries it.
  const box = React.useRef(null);
  const cw = useContainerWidth(box, 880);
  const narrow = cw < 620;
  const W = Math.max(320, cw), H = narrow ? 340 : 400;
  const pad = { l: loss ? 74 : 54, r: narrow ? 16 : 128, t: 18, b: 44 };
  const n = snapshots.length;
  // Runs sit where they fall in calendar time -- a two-day gap is a third of
  // a six-day span -- never one slot per run. Labels that would collide give
  // way (the first and the latest always show); the hover reaches every run.
  const days = snapshots.map(s => Date.UTC(+s.date.slice(0, 4), +s.date.slice(5, 7) - 1, +s.date.slice(8, 10)) / 864e5);
  // Give the first chart a fixed year-to-date frame: the recent readings sit
  // in the left portion of the axis, making their small movement legible while
  // leaving room for subsequent assessments through December 31.
  const yearEnd = days.length ? Date.UTC(+snapshots[0].date.slice(0, 4), 11, 31) / 864e5 : 0;
  const axisEnd = n > 1 ? Math.max(days[n - 1], yearEnd) : yearEnd;
  const span = axisEnd > days[0] ? axisEnd - days[0] : 0;
  const xDay = day => (span === 0 ? (pad.l + W - pad.r) / 2 : pad.l + ((day - days[0]) / span) * (W - pad.l - pad.r));
  const x = i => xDay(days[i]);
  const xs = snapshots.map((_, i) => x(i));
  const futureTicks = [];
  if (n > 0 && axisEnd > days[n - 1]) {
    const last = new Date(days[n - 1] * 864e5);
    const year = last.getUTCFullYear();
    for (let month = last.getUTCMonth() + 1; month < 12; month++) {
      const day = Date.UTC(year, month, 1) / 864e5;
      if (day <= axisEnd) futureTicks.push({ day, label: new Date(day * 864e5).toLocaleString("en-US", { month: "short", timeZone: "UTC" }) + " 1" });
    }
  }
  const labelGap = 46;
  const labelled = new Set(n ? [n - 1] : []);
  for (let i = 0, lastX = -Infinity; i < n - 1; i++) {
    if (xs[i] - lastX >= labelGap && xs[n - 1] - xs[i] >= labelGap) { labelled.add(i); lastX = xs[i]; }
  }

  const h = horizon;
  const med = q.median[h] || [];
  const fmtV = tlFmtFor(q);
  const [active, setActive] = useState(null);         // { i, id, anchor }, null id = median
  const [pinned, setPinned] = useState(false);        // click/tap keeps the details open
  const hv = active ? active.i : null;
  const hvar = active && active.id != null ? active : null;
  const clear = () => { setActive(null); setPinned(false); };
  const hover = (e, i, id = null) => { if (!pinned) setActive({ i, id, anchor: e.currentTarget.lastElementChild }); };
  const leave = () => { if (!pinned) setActive(null); };
  const select = (e, i, id = null) => {
    e.stopPropagation();
    if (pinned && hv === i && (active && active.id) === id) clear();
    else { setActive({ i, id, anchor: e.currentTarget.lastElementChild }); setPinned(true); }
  };
  const keySelect = (e, i, id = null) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(e, i, id); }
  };
  const series = q.series.map(s => ({ ...s, vals: s.ps[h] || [] }));
  // Prompt variants (combined-v10): one dot per variant, the panel median of
  // that prompt's calls; the ink mark is the median of the models' means
  // over the five. On a variant date the models' means are not drawn
  // (project lead, 2026-10-21): hovering a variant dot lists only model
  // answers; the legend carries the prompt instruction. The unpooled sixth call is never in the
  // blob.
  const variants = tlVariants(q, h, snapshots);
  const hasVar = i => variants.some(v => v.vals[i] != null);
  const hovered = hvar && variants.find(v => v.id === hvar.id);
  const hoveredModels = hovered ? Object.entries(hovered.models[hvar.i] || {}) : [];

  let y, yticks, tickText, tickSub;
  if (loss) {
    const LO = (TL.severityAxis || {}).lo || 800, HI = (TL.severityAxis || {}).hi || 1.4e10;
    y = v => pad.t + (1 - Math.min(1, Math.max(0,
      (Math.log10(Math.max(v, LO)) - Math.log10(LO)) / (Math.log10(HI) - Math.log10(LO))))) * (H - pad.t - pad.b);
    const rungs = (TL.rungs || []).filter(r => r.deaths >= LO && r.deaths <= HI);
    yticks = rungs.map(r => r.deaths);
    tickText = t => (rungs.find(r => r.deaths === t) || {}).short;
    tickSub = () => null;
  } else if (scale === "linear") {
    // Linear (the default since 2026-09-08), topped just above the largest
    // value on the line or any model dot at this horizon, as Graph 1's
    // linear axis is.
    const top = linearTop([
      ...med,
      ...variants.flatMap(v => v.vals),
      ...series.flatMap(s => s.vals),
    ]);
    y = v => pad.t + (1 - Math.min(1, Math.max(0, v / top))) * (H - pad.t - pad.b);
    yticks = linearTicks(top);
    tickText = t => fmtTick(t) + "%";
    tickSub = () => null;
  } else {
    // Log axis, 0.01-100%, the same as Graph 1's: the view for the tails.
    const LO = 0.01, HI = 100;
    y = v => pad.t + (1 - Math.min(1, Math.max(0,
      (Math.log10(Math.max(v, LO)) - Math.log10(LO)) / (Math.log10(HI) - Math.log10(LO))))) * (H - pad.t - pad.b);
    yticks = [0.01, 0.1, 1, 10, 100];
    tickText = t => fmtTick(t) + "%";
    tickSub = () => null;
  }
  const marks = loss ? (TL.marks || []) : [];

  // Condition dots always remain on their date's vertical line. Their vertical
  // position alone encodes the forecast, even when nearby readings overlap.
  const variantDots = snapshots.flatMap((_, i) =>
    variants.filter(v => v.vals[i] != null).map(v => ({
      v, i, cx: x(i), cy: y(v.vals[i]),
    }))
  );

  const li = med.map((v, i) => (v != null ? i : -1)).reduce((a, b) => Math.max(a, b), -1);
  // Right-margin label: the latest median, kept above the date labels.
  const endLabel = li >= 0 ? { v: med[li], y: Math.min(y(med[li]), H - pad.b - 2), xi: li } : null;

  return (
    <div ref={box} style={{ position: "relative", minWidth: 0 }} onKeyDown={e => { if (e.key === "Escape") clear(); }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} onMouseLeave={leave} onClick={clear}>
        {yticks.map((t, i) => (
          <g key={i}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--line-soft)" />
            <text x={pad.l - 9} y={y(t) + (loss ? 0 : 4)} textAnchor="end" fontSize="11" fill="var(--ink-faint)" className="mono">{tickText(t)}</text>
            {tickSub(t) && <text x={pad.l - 9} y={y(t) + 11} textAnchor="end" fontSize="9.5" fill="var(--ink-faint)" className="mono">{tickSub(t)}</text>}
          </g>
        ))}
        {marks.map(m => (
          <g key={m.label}>
            <line x1={pad.l} x2={W - pad.r} y1={y(m.v)} y2={y(m.v)} stroke="var(--ink-faint)" strokeWidth="1" strokeDasharray="4 3" opacity="0.7" />
            <text x={pad.l - 9} y={y(m.v) + 4} textAnchor="end" fontSize="10" fill="var(--ink-soft)">{m.label}</text>
          </g>
        ))}

        {snapshots.map((s, i) => (
          <g key={s.date}>
            <line x1={x(i)} x2={x(i)} y1={pad.t} y2={H - pad.b} stroke="var(--line)" strokeWidth="1" opacity={labelled.has(i) ? 0.55 : 0.3} />
            {labelled.has(i) && <text x={x(i)} y={H - 18} textAnchor="middle" fontSize="12" fill="var(--ink-soft)" fontWeight="600">{s.label}</text>}
          </g>
        ))}
        {futureTicks.map(t => (
          <g key={t.day}>
            <line x1={xDay(t.day)} x2={xDay(t.day)} y1={pad.t} y2={H - pad.b} stroke="var(--line)" strokeWidth="1" strokeDasharray="3 4" opacity="0.55" />
            {xDay(t.day) - xs[n - 1] >= labelGap && W - pad.r - xDay(t.day) >= labelGap && (
              <text x={xDay(t.day)} y={H - 18} textAnchor="middle" fontSize="12" fill="var(--ink-faint)" fontWeight="600">{t.label}</text>
            )}
          </g>
        ))}
        {axisEnd > days[n - 1] && W - pad.r - xs[n - 1] >= labelGap && <text x={W - pad.r} y={H - 18} textAnchor="end"
          fontSize="12" fill="var(--ink-faint)" fontWeight="600">Dec 31</text>}
        {/* Historical model answers are revealed only for the active date. */}
        {series.map(s => (
          <g key={s.label}>
            {s.vals.map((v, i) => v == null || hasVar(i) || hv !== i ? null : (
              <circle key={"d" + i} cx={x(i)} cy={y(v)} r="4" fill="var(--ink-soft)" stroke="var(--panel)" strokeWidth="1.5" />
            ))}
          </g>
        ))}

        {!narrow && endLabel && (
          <text x={Math.max(x(endLabel.xi), ...variantDots.filter(d => d.i === endLabel.xi).map(d => d.cx)) + 10} y={endLabel.y + 4} fontSize="11.5" fill="var(--ink)" className="mono" fontWeight="700">
            by {h} {fmtV(endLabel.v)}
          </text>
        )}

        {hv != null && <line x1={x(hv)} x2={x(hv)} y1={pad.t} y2={H - pad.b} stroke="var(--ink-faint)" strokeDasharray="3 3" opacity="0.6" />}
        {hv != null && med[hv] != null && (
          <circle cx={x(hv)} cy={y(med[hv])} r="8" fill="none" stroke="var(--ink)" strokeOpacity="0.35" strokeWidth="2" />
        )}
        <rect x={pad.l} y={pad.t} width={Math.max(1, W - pad.l - pad.r)} height={H - pad.t - pad.b} fill="transparent"
          onMouseMove={leave} />

        {/* The median's marks, unjoined. The larger transparent target also works on touchscreens. */}
        {med.map((v, i) => v == null ? null : (
          <g key={"m" + i} role="button" tabIndex={0} style={{ cursor: "pointer" }}
            aria-label={`${snapshots[i].date}, ensemble median ${fmtV(v)}; show model forecasts`}
            aria-pressed={pinned && hv === i && !hvar}
            onMouseEnter={e => hover(e, i)} onMouseLeave={leave} onFocus={e => hover(e, i)} onBlur={leave}
            onClick={e => select(e, i)} onKeyDown={e => keySelect(e, i)}>
            <circle cx={x(i)} cy={y(v)} r="10" fill="transparent" />
            <circle cx={x(i)} cy={y(v)} r="5" fill="var(--panel)" stroke="var(--ink)" strokeWidth="2.6" />
          </g>
        ))}

        {/* One dot per prompt variant, above the hover layer so each can be hovered. */}
        {variantDots.map(({ v, i, cx, cy }) => (
          <g key={`${v.id}:${i}`} opacity={hvar && (hvar.id !== v.id || hvar.i !== i) ? 0.3 : 1}
            role="button" tabIndex={0} style={{ cursor: "pointer" }}
            aria-label={`${snapshots[i].date}, ${v.label} prompt ${fmtV(v.vals[i])}; show model forecasts`}
            aria-pressed={pinned && hv === i && hvar && hvar.id === v.id ? true : false}
            onMouseEnter={e => hover(e, i, v.id)} onMouseLeave={leave} onFocus={e => hover(e, i, v.id)} onBlur={leave}
            onClick={e => select(e, i, v.id)} onKeyDown={e => keySelect(e, i, v.id)}>
            <circle cx={cx} cy={cy} r="10" fill="transparent" />
            <circle cx={cx} cy={cy} r="4.5" fill={v.color} stroke="var(--panel)" strokeWidth="1.5" />
          </g>
        ))}
      </svg>

      {hovered && (
        <TimelinePointTooltip anchor={active.anchor}>
          {hoveredModels.map(([label, val]) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between", gap: 14, fontSize: 12 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--ink-soft)", flexShrink: 0 }}></span>{label}
              </span>
              <span className="mono">{fmtV(val)}</span>
            </div>
          ))}
        </TimelinePointTooltip>
      )}
      {hv != null && !hovered && (
        <TimelinePointTooltip anchor={active.anchor}>
          <div style={{ fontSize: 11, color: "var(--ink-faint)", marginBottom: 6 }}>
            {snapshots[hv].date} · <span style={{ color: "var(--ink)", fontWeight: 600 }}>by {h}</span>
            {hasVar(hv) ? ` · ${variants.filter(v => v.vals[hv] != null).length} prompts per model · each model = mean of its prompts`
              : snapshots[hv].draws > 1 ? ` · ${snapshots[hv].draws} draws per model · point = mean` : ""}{loss ? " · deaths" : ""}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 14, fontSize: 12.5, fontWeight: 600, marginBottom: 4 }}>
            <span>Ensemble median</span>
            <span className="mono">
              {fmtV(med[hv])}
            </span>
          </div>
          {variants.filter(v => v.vals[hv] != null).map(v => (
            <div key={"tv" + v.id} style={{ display: "flex", justifyContent: "space-between", gap: 14, fontSize: 12, color: "var(--ink-soft)" }}>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 9, height: 9, borderRadius: "50%", background: v.color, flexShrink: 0 }}></span>{v.label} prompt
              </span><span className="mono">{fmtV(v.vals[hv])}</span>
            </div>
          ))}
          {series.filter(s => s.vals[hv] != null).map(s => (
            <div key={s.label} style={{ display: "flex", justifyContent: "space-between", gap: 14, fontSize: 12 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--ink-soft)", flexShrink: 0 }}></span>{s.label}
                {s.legacy && <span style={{ color: "var(--ink-faint)" }}>· earlier panel</span>}
              </span>
              <span className="mono">
                {fmtV(s.vals[hv])}
              </span>
            </div>
          ))}
        </TimelinePointTooltip>
      )}
    </div>
  );
}

/* ---------------- table view ---------------- */
function TimelineTable({ q, horizon, snapshots }) {
  const loss = q.value_kind === "loss";
  const fmtV = tlFmtFor(q);
  const rows = [
    { label: "Ensemble median", color: "var(--ink)", vals: q.median[horizon] || [], bold: true },
    ...q.series.map(s => ({ label: s.label, color: "var(--ink-soft)", vals: s.ps[horizon] || [] })),
  ];
  // Change first -> last: percentage points for a probability, a ratio for a loss.
  const change = v => {
    const a = v[0], b = v[v.length - 1];
    if (a == null || b == null || v.length < 2) return "—";
    return loss ? tlFmtRatio(b / a) : tlFmtD(b - a);
  };
  return (
    <div style={{ overflowX: "auto" }}>
    <table className="tv">
      <thead>
        <tr>
          <th>Forecaster</th>
          {snapshots.map(s => <th key={s.date}>{s.label}</th>)}
          <th>Change</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.label}>
            <td style={{ fontWeight: r.bold ? 600 : 400 }}>
              <span style={{ display: "inline-block", width: 9, height: 9, borderRadius: "50%", background: r.color, marginRight: 7 }}></span>
              {r.label}
            </td>
            {r.vals.map((v, i) => (
              <td key={i} className="mono">
                {fmtV(v)}
              </td>
            ))}
            <td className="mono" style={{ color: "var(--ink-soft)" }}>{change(r.vals)}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

/* ---------------- the panel ---------------- */
// The AI-catastrophe row alone (Nick, 2026-09-09): the headline is one
// number moving, not a rail of seven. The other bottom-line questions stay
// in the blob and in the data bank.
const TL_HEADLINE = "catastrophe:ai";

// The same panel, one row each: the headline (catastrophe:ai) and, since
// 2026-09-10 (Nick), the expected-deaths row loss:ai as "Statistical lives
// lost" -- the deaths ladder's eight rungs folded to a floor on E[deaths], on
// the shared severity axis (see the LossPanel below and
// redlines/views/timeline.py::_loss_row).
function TimelinePanel(props = {}) {
  const q = TL && TL.questions.find(q => q.id === (props.qid || TL_HEADLINE));
  if (!q || !q.horizons.length || !TL.snapshots.length) return <ForecastUnavailable title={props.title || "Probability of an AI catastrophe"} />;
  return <TimelinePanelCurrent {...props} />;
}
function TimelinePanelCurrent({ qid = TL_HEADLINE, title = "Probability of an AI catastrophe", sub = "Forecasts over time" } = {}) {
  const snapshots = TL.snapshots;
  const q = TL.questions.find(x => x.id === qid) || TL.questions[0];
  // The horizon picker, Graph 2's toggle: opens on 2030 like every other
  // horizon toggle (Nick, 2026-08-27), and is what the line, the dots, the
  // numbers below and the table all read.
  const [hz, setHz] = useState(q.horizons.includes("2030") ? "2030" : q.horizons[q.horizons.length - 1]);
  const [showTable, setShowTable] = useState(false);
  const [scale, setScale] = useState("linear");     // Graph 1's switch, the same default

  const med = q.median[hz] || [];
  const first = med.find(v => v != null);
  // Series can be ragged (a question not re-asked in the newest run), so
  // every "latest" statistic keys off the most recent snapshot in which THIS
  // question has data, not the most recent snapshot -- otherwise a stale
  // question reads "0 of 4 reporting" next to a live median.
  const li = med.map((v, i) => (v != null ? i : -1)).reduce((a, b) => Math.max(a, b), -1);
  const latest = li >= 0 ? med[li] : null;
  const loss = q.value_kind === "loss";
  const fmtV = loss ? tlFmtLoss : tlFmt;
  // Change since the first snapshot: pp for a probability, a ratio for a loss.
  const delta = first != null && latest != null && med.length > 1 ? (loss ? latest / first : latest - first) : null;
  const up = delta != null && (loss ? delta > 1 : delta > 0), flat = delta == null || (loss ? delta === 1 : delta === 0);
  // Flagged when this question was not re-asked in the newest run.
  const staleAt = li >= 0 && li < snapshots.length - 1 ? snapshots[li].label : null;

  const variants = tlVariants(q, hz, snapshots);

  // Who declined, per date, for the chip under the question -- Graph 1's
  // chip is per model; here a model can decline on one date and not another.
  const declined = Object.entries(q.declined).filter(([, ls]) => ls.length);

  return (
    <Panel style={{ padding: 24, marginBottom: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 12 }}>
        <div>
          {/* Headline and subhead (Nick, 2026-09-09), no eyebrow: the number
              first, the series second. */}
          <h2 style={{ fontSize: 22, marginTop: 0, marginBottom: 4 }}>{title}</h2>
          <p style={{ color: "var(--ink-soft)", fontSize: 13.5, margin: 0 }}>{sub}</p>
        </div>
        <Toggle options={q.horizons.map(h => ({ key: h, label: "by " + h }))} value={hz} onChange={setHz} />
      </div>

      {/* No rail: the chart takes the panel's full width, as Graph 2's does. */}
      <div style={{ marginTop: 16, minWidth: 0 }}>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 6, alignItems: "center" }}>
          <LegendDot color="var(--ink)" label="Ensemble median" hollow />
          {variants.map(v => <LegendDot key={v.id} color={v.color} label={v.label} title={v.text || "No added instruction."} />)}
          {/* The scale switch at the legend row's right end, where Graph 2 keeps its own. */}
          {!loss && <ScaleToggle value={scale} onChange={setScale} style={{ marginLeft: "auto" }} />}
        </div>

        <TimelineChart key={hz} q={q} snapshots={snapshots} horizon={hz} scale={scale} />
        <p style={{ fontSize: 12, color: "var(--ink-soft)", margin: "6px 0 0" }}>
          {variants.length > 0 ? "From Oct 21, colors identify prompt conditions; hover the legend to read each prompt. " : ""}
          Hover or select a point to see model forecasts.
        </p>
        {loss && <>
          <CountingWindow info={TL.instrumentInfo} horizon={hz} />
          <p style={{ fontSize: 12, color: "var(--ink-soft)" }}>Each run starts its incident window on its own elicitation date. A fixed-year forecast therefore covers a changing interval; movement is not solely a change of belief about the same event.</p>
        </>}

        {/* The question, in full, below the chart -- Graph 1's block, shared. */}
        <QuestionBox q={q} />
        {declined.length > 0 && (
          <div style={{ marginTop: 10, fontSize: 12.5, color: "var(--warn-ink)", background: "var(--warn-bg)", border: "1px solid var(--warn-line)", borderRadius: 8, padding: "7px 11px", display: "inline-block" }}>
            ⚠ Declined this question (returned no forecast), excluded from that date's median: {declined.map(([d, ls]) => `${d} — ${ls.join(", ")}`).join(" · ")}
          </div>
        )}

        <div style={{ display: "flex", gap: 22, marginTop: 12, paddingTop: 14, borderTop: "1px solid var(--line-soft)", flexWrap: "wrap", alignItems: "flex-start" }}>
          <Stat label={(staleAt ? "As of " + staleAt : "Latest") + " — ensemble median, by " + hz} value={fmtV(latest)} color="var(--ink)" />
          <Stat label={"Change since " + snapshots[0].label} value={loss ? tlFmtRatio(delta) : tlFmtD(delta)} color={flat ? "var(--ink-soft)" : (up ? "var(--model)" : "var(--super)")} />
          <div style={{ marginLeft: "auto" }}>
            <button className="linkbtn" onClick={() => setShowTable(v => !v)}>
              {showTable ? "Hide table" : "Show as table"}
            </button>
          </div>
        </div>

        {!loss && <ForecastRationales qid={q.id} context={q.short || title}
          date={li >= 0 ? snapshots[li].date : null}
          forecasts={q.horizons.map(h => ({ key: h, values: Object.fromEntries(q.series.map(s => [s.label, (s.ps[h] || [])[li]])) }))} />}
        {showTable && (
          <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--line-soft)" }}>
            <TimelineTable q={q} horizon={hz} snapshots={snapshots} />
          </div>
        )}
      </div>
    </Panel>
  );
}

// "Statistical lives lost": the loss:ai row, between the headline and the
// severity ladders (Nick, 2026-09-10; the shared "AI risk dashboard" mockup's
// panel 2, which was computed from this row). Nothing new is elicited: the
// deaths ladder's eight rungs are P(cumulative deaths >= x) at eight points,
// and the row is that survival function integrated with every band valued at
// its lower rung -- a floor on expected deaths.
function LossPanel() {
  // No explainer box under the chart (Nick, 2026-09-10): the question text
  // the blob carries already says what the fold is, and ExpectedLossNote
  // rides the Definitions modal and Graph 1's loss rows.
  return (
    <TimelinePanel qid="loss:ai"
      title="Statistical lives lost"
      sub="Expected deaths from AI-related incidents · a lower bound" />
  );
}
