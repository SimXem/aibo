/* ============================ atoms ============================ */
function Panel({ children, style }) {
  return <div style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 14, boxShadow: "var(--shadow)", ...style }}>{children}</div>;
}
function ForecastUnavailable({ title, onDefinitions }) {
  return <Panel style={{ padding: 24, marginBottom: 24 }}>
    <h2 style={{ fontSize: 22, margin: "0 0 8px" }}>{title}</h2>
    <p style={{ fontSize: 13.5, color: "var(--ink-soft)", margin: 0 }}>Awaiting a complete four-model run under the revised counting rules.</p>
    {onDefinitions && <button className="linkbtn" onClick={onDefinitions}>Definitions →</button>}
  </Panel>;
}
function CountingWindow({ info, horizon }) {
  const windows = ((info || {}).countingWindows || {})[horizon] || [];
  if (!windows.length) return null;
  return <div style={{ fontSize: 12, lineHeight: 1.5, color: "var(--ink-soft)", marginTop: 8 }}>
    {windows.map((w, i) => <div key={i}>Eligible incident onset: {w.start} through {w.end}, inclusive ({w.timezone}). Count each incident’s first {w.harm_years} years of harm, even after the onset deadline. The start advances with each run, including for fixed-year deadlines.</div>)}
  </div>;
}
function Eyebrow({ children }) {
  return <div className="mono" style={{ fontSize: 11, letterSpacing: "0.09em", textTransform: "uppercase", color: "var(--ink-faint)", fontWeight: 500 }}>{children}</div>;
}
// `onClick` turns a legend entry into a filter control; `dim` greys the ones not
// currently selected. Both optional, so the eight read-only usages elsewhere are
// untouched — a legend entry only becomes interactive where a caller says so.
function LegendDot({ color, label, hollow, onClick, dim, title }) {
  const act = typeof onClick === "function";
  const ref = React.useRef(null);
  const tooltip = React.useRef(null);
  React.useEffect(() => {
    if (!title || !window.tippy || !ref.current) return;
    const instance = window.tippy(ref.current, {
      content: title, allowHTML: false, theme: "light-border", arrow: true,
      maxWidth: 360, offset: [0, 8], placement: "top",
    });
    tooltip.current = instance;
    return () => { instance.destroy(); tooltip.current = null; };
  }, [title]);
  return (
    <span
      role={act ? "button" : undefined}
      tabIndex={act || title ? 0 : undefined}
      ref={ref}
      onClick={onClick}
      onKeyDown={e => {
        if (e.key === "Escape" && tooltip.current) tooltip.current.hide();
        if (act && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onClick(); }
      }}
      style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 12.5, color: "var(--ink-soft)",
        opacity: dim ? 0.34 : 1, cursor: act ? "pointer" : title ? "help" : undefined,
        userSelect: act ? "none" : undefined, transition: "opacity .12s" }}>
      <span style={{ width: 11, height: 11, borderRadius: 3, background: hollow ? "var(--panel)" : color, border: hollow ? `2px solid ${color}` : "none" }}></span>{label}

    </span>
  );
}
// The question, in full, under a chart: its text, and the resolution
// criteria behind a toggle. Graph 1's block since 2026-08-18, shared with the
// Timeline since 2026-09-08 (Nick: the two panels' question UI must be
// identical). `q.text`, `q.criteria`, `q.details` as the view blobs carry them.
function ExpectedLossNote() {
  // One sentence about the fold, written by the pipeline that does it
  // (redlines/views/conditional.py::build, method.loss; the Capability blob
  // carries the same string), so the page cannot describe a calculation the
  // code does not do. Graph 1's loss rows carry the per-cause wording as the
  // fallback when the Conditional blob is not on the page.
  const method = (typeof COND !== "undefined" && COND && COND.method && COND.method.loss)
    || (((G1 && G1.questions) || []).find(q => q.valueKind === "loss") || {}).text;
  if (!method) return null;
  return (
    <div style={{ fontSize: 12, lineHeight: 1.5, color: "var(--ink-soft)", marginTop: 10 }}>
      <strong>Expected deaths.</strong> {method}
    </div>
  );
}
function QuestionBox({ q }) {
  const [showCriteria, setShowCriteria] = useState(false);
  return (
    <div style={{ border: "1px solid var(--line)", borderRadius: 10, padding: "12px 14px", marginTop: 14, background: "var(--bg)" }}>
      <div style={{ fontSize: 10.5, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-faint)", fontWeight: 600, marginBottom: 5 }}>
        The question
      </div>
      <div style={{ fontSize: 13.5, lineHeight: 1.5, color: "var(--ink)" }}>{q.text}</div>
      {(q.criteria || q.details) && (
        <button className="linkbtn" onClick={() => setShowCriteria(v => !v)}
          style={{ marginTop: 8, fontSize: 12.5 }}>
          {showCriteria ? "Hide resolution criteria" : "Resolution criteria →"}
        </button>
      )}
      {showCriteria && (
        <div style={{ marginTop: 9, paddingTop: 9, borderTop: "1px solid var(--line-soft)", fontSize: 12.5, lineHeight: 1.55, color: "var(--ink-soft)", whiteSpace: "pre-wrap", maxHeight: 320, overflowY: "auto" }}>
          {q.criteria}
          {q.details && Object.entries(q.details).map(([k, v]) => v && (
            <div key={k} style={{ marginTop: 10 }}>
              <div style={{ fontWeight: 600, color: "var(--ink)", textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</div>
              {v}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
function Stat({ label, value, color }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--ink-faint)", marginBottom: 2 }}>{label}</div>
      <div className="mono" style={{ fontSize: 18, fontWeight: 500, color }}>{value}</div>
    </div>
  );
}
function Toggle({ options, value, onChange }) {
  return (
    <div style={{ display: "flex", gap: 6, background: "var(--bg)", padding: 4, borderRadius: 10, border: "1px solid var(--line)", flexWrap: "wrap" }}>
      {options.map(o => (
        <button key={o.key} onClick={() => onChange(o.key)} style={{ border: "none", cursor: "pointer", padding: "6px 12px",
          borderRadius: 7, fontSize: 13, fontWeight: 500, background: value === o.key ? "var(--ink)" : "transparent",
          color: value === o.key ? "white" : "var(--ink-soft)" }}>{o.label}</button>
      ))}
    </div>
  );
}
// Log/linear switch for a chart's probability axis (Bridget, 2026-08-19).
// Linear is the default since 2026-09-08 (Nick), auto-scaled to the plotted
// values; log is the view for the tails, which linear flattens into the
// baseline. The helpers give a linear axis a rounded top and six ticks.
function linearTop(values) {
  const vs = values.filter(v => v != null && isFinite(v));
  return niceMax(Math.max(0.5, ...vs));
}
function linearTicks(top) {
  return Array.from({ length: 6 }, (_, i) => Number((i * top / 5).toPrecision(3)));
}
const fmtTick = t => String(Number(t.toPrecision(3)));
function ScaleToggle({ value, onChange, style }) {
  return (
    <span style={{ display: "inline-flex", gap: 4, ...style }}>
      {["log", "linear"].map(k => (
        <button key={k} onClick={() => onChange(k)} style={{ border: "1px solid var(--line)",
          background: value === k ? "var(--bg)" : "transparent", borderRadius: 7, cursor: "pointer",
          padding: "3px 9px", fontSize: 11.5, fontWeight: value === k ? 600 : 400,
          color: value === k ? "var(--ink)" : "var(--ink-soft)" }}>{k} scale</button>
      ))}
    </span>
  );
}
function ForecasterLegend({ active, setActive }) {
  const items = [FC.model, FC.super, FC.hybrid];
  return (
    <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
      {items.map(f => (
        <button key={f.key} onClick={() => setActive(a => ({ ...a, [f.key]: !a[f.key] }))}
          style={{ border: "none", background: "transparent", cursor: "pointer", padding: 0, opacity: active[f.key] ? 1 : 0.36 }}>
          <LegendDot color={f.color} label={f.label} hollow={f.key !== "model"} />
        </button>
      ))}
    </div>
  );
}
