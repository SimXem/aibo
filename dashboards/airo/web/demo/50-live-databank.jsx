/* ============================ data bank · live (window.__DATABANK__) ============================ */
const DB_RAW = (typeof window !== "undefined" && window.__DATABANK__) || null;
const DB = (DB_RAW && Array.isArray(DB_RAW.rows)) ? DB_RAW : null;

function LiveDataBank() {
  if (!DB.rows.length) return <ForecastUnavailable title="Forecast data" />;
  return <LiveDataBankCurrent />;
}
function LiveDataBankCurrent() {
  // Canaries are deferred to v2 (2026-08-10 call), so the blob may carry none.
  // Everything canary-specific — the tab, the default view, the "moves" column —
  // is driven off what is actually present rather than assumed.
  const hasCanaries = DB.rows.some(r => r.kind === "canary");
  // Driven by the data, never by a flag typed here: the column appears the run
  // after a panel's numbers land, and not before.
  const hasHuman = DB.rows.some(r => r.super != null);
  const [filter, setFilter] = useState(hasCanaries ? "canary" : "bottom-line");
  const [expanded, setExpanded] = useState(null);
  // Open at five rows (Nick, 2026-08-19). The full listing was Nick's own
  // 2026-08-18 ask — a short table then read as "this is the whole set" —
  // but the "showing 5 of 35" count, the show-all button and the CSV link
  // now say otherwise, and 35 rows of table buried the panels around it.
  const [limit, setLimit] = useState(5);
  // Two views, one state (Nick, 2026-08-19 — the per-horizon toggle is gone,
  // the CSV button has its spot): "headline" shows each question once at its
  // own longest horizon, the bottom line; "all" is the whole grid, one row
  // per (question, horizon), because a "show all" that silently kept one
  // horizon per question read as the full dataset when it wasn't. hk null
  // means "use the row's own headline numbers".
  const HZS = DB.horizons || [];
  const [hz, setHz] = useState("headline");
  const rows = DB.rows.filter(r => filter === "all" ? true : r.kind === filter);
  const drows = hz === "all"
    ? rows.flatMap(r => {
        const hs = r.byHorizon ? HZS.filter(o => r.byHorizon[o.key]) : [];
        return hs.length ? hs.map(o => ({ r, hk: o.key, hlabel: o.label }))
                         : [{ r, hk: null, hlabel: r.horizon }];
      })
    : rows.map(r => ({ r, hk: null, hlabel: r.horizon }));
  const shown = drows.slice(0, limit);
  const fmtP = v => (v >= 10 ? v.toFixed(0) : v >= 1 ? v.toFixed(1) : v.toFixed(2)) + "%";
  // The cell a display-row shows: {median, n} or null.
  const at = d => d.hk == null
    ? { median: d.r.median, n: d.r.n_models }
    : (d.r.byHorizon || {})[d.hk] || null;
  // The dataset download moved to the page header on 2026-08-27 (every
  // forecast from every run, redlines/export.py); this table is a preview.
  const TABS = hasCanaries ? [
    { key: "canary", label: "Canaries" },
    { key: "bottom-line", label: "Bottom-line" },
    { key: "all", label: "All" },
  ] : [];
  const th = { padding: "7px 12px 7px 0", fontWeight: 600, borderBottom: "1px solid var(--line)", whiteSpace: "nowrap" };
  const td = { padding: "8px 12px 8px 0", whiteSpace: "nowrap" };
  // one line per row: truncate the question, detail lives in the expansion
  const clip = { maxWidth: 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };
  return (
    <Panel style={{ padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <div><h2 style={{ fontSize: 20, marginTop: 0 }}>Forecasts &amp; resolutions</h2></div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <a href="redlines-data.zip" download="airo-data.zip" title="everything: forecasts.csv, rationales.csv, the raw logs with every search and page read, the questions and conditions" style={{ display: "inline-flex", alignItems: "center", background: "var(--ink)", color: "white", textDecoration: "none", borderRadius: 8, padding: "6px 10px", fontSize: 12.5, fontWeight: 700, whiteSpace: "nowrap" }}>⤓ Download forecasts</a>
          {TABS.length > 0 && <Toggle options={TABS} value={filter} onChange={k => { setFilter(k); setLimit(5); setExpanded(null); }} />}
        </div>
      </div>
      <div style={{ overflowX: "auto", marginTop: 12 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, tableLayout: "auto" }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--ink-faint)", fontSize: 11.5, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              <th style={th}>Question</th>
              <th style={th}>Category</th>
              <th style={th}>Horizon</th>
              {/* "Models" said nothing about what the number was (Bridget,
                  2026-08-19). It is the ensemble median. */}
              <th style={{ ...th, textAlign: "right" }} title="median across the frontier models that answered">Model median</th>
              {/* Hidden while empty. The column stays in the row schema so a
                  panel can fill it without churning every consumer, but a
                  header over 35 em-dashes reads as missing data rather than
                  as "no panel has forecast these questions". */}
              {hasHuman && <th style={{ ...th, textAlign: "right" }}>Supers</th>}
              {hasCanaries && <th style={{ ...th, textAlign: "right" }}>Moves</th>}
              <th style={th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((d, i) => { const r = d.r; return (
              <React.Fragment key={i}>
                <tr style={{ borderBottom: "1px solid var(--line-soft)", cursor: r.kind === "canary" ? "pointer" : "default" }}
                  onClick={() => r.kind === "canary" && setExpanded(expanded === i ? null : i)}>
                  <td style={{ ...td, ...clip }} title={r.question}>
                    {r.kind === "canary" && <span style={{ color: "var(--ink-faint)", marginRight: 6, fontSize: 10 }}>{expanded === i ? "▾" : "▸"}</span>}
                    {r.question}
                  </td>
                  <td style={{ ...td, color: "var(--ink-soft)" }}>{r.category}</td>
                  <td style={{ ...td, color: "var(--ink-soft)" }}>{at(d) ? d.hlabel : "—"}</td>
                  <td style={{ ...td, textAlign: "right" }} className="mono"
                    title={at(d) ? "median of " + at(d).n + " model" + (at(d).n > 1 ? "s" : "") : undefined}>
                    {at(d) ? fmtP(at(d).median) : "—"}
                  </td>
                  
                  {hasHuman && (
                    <td style={{ ...td, textAlign: "right", color: "var(--super)" }} className="mono"
                      title={r.superSource ? "Human baseline: " + r.superSource : undefined}>
                      {r.super != null ? <span>{fmtP(r.super)}</span> : "—"}
                    </td>
                  )}
                  {hasCanaries && (
                    <td style={{ ...td, textAlign: "right" }} className="mono">
                      {r.coupling != null
                        ? <span style={{ color: r.coupling >= 5 ? "var(--warn-ink)" : "var(--ink-soft)", fontWeight: r.coupling >= 5 ? 600 : 400 }}>{r.coupling.toFixed(1)}</span>
                        : <span style={{ color: "var(--ink-faint)" }}>—</span>}
                    </td>
                  )}
                  <td style={td}>
                    <span style={{ fontSize: 11.5, padding: "2px 8px", borderRadius: 20, whiteSpace: "nowrap",
                      background: "var(--line-soft)", color: "var(--ink-soft)" }}>
                      {r.kind === "canary" ? "Scoreable" : "Open"}
                    </span>
                  </td>
                </tr>
                {expanded === i && r.kind === "canary" && (
                  <tr style={{ borderBottom: "1px solid var(--line-soft)", background: "var(--bg)" }}>
                    <td colSpan={7} style={{ padding: "10px 12px 12px 17px", fontSize: 12.5, color: "var(--ink-soft)", whiteSpace: "normal" }}>
                      <div style={{ marginBottom: 5 }}>{r.question}</div>
                      <div style={{ marginBottom: 5 }}><strong style={{ color: "var(--ink)" }}>Canary for</strong> {r.parent} · <strong style={{ color: "var(--ink)" }}>resolves</strong> {r.resolves} · {r.res_source}</div>
                      <div style={{ marginBottom: 5 }}><strong style={{ color: "var(--ink)" }}>Criteria</strong> {r.criteria}</div>
                      {r.coupling_to && (
                        <div><strong style={{ color: "var(--ink)" }}>Coupling</strong> yes vs no swings “{r.coupling_to}” by <span className="mono">{r.coupling.toFixed(1)}</span> points</div>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ); })}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, flexWrap: "wrap", gap: 8 }}>
        <span style={{ fontSize: 12.5, color: "var(--ink-faint)" }}>
          showing {shown.length} of {drows.length} {hz === "all" ? "forecasts (question × horizon)" : "questions"} · model median = the ensemble median; hover a value for how many models answered
          {filter === "canary" ? " · “moves” = points the linked catastrophic forecast swings on resolution" : ""}
        </span>
        {/* ALL means all: every question at every horizon, not the longest
            horizon of each (Nick, 2026-08-19). */}
        {hz === "all" && limit >= drows.length
          ? <button onClick={() => { setHz("headline"); setLimit(5); }} style={{ border: "1px solid var(--line)", background: "var(--bg)",
              borderRadius: 8, cursor: "pointer", padding: "4px 11px", fontSize: 12.5, color: "var(--ink-soft)" }}>collapse to bottom line</button>
          : <button onClick={() => { setHz("all"); setLimit(9999); }} style={{ border: "1px solid var(--line)", background: "var(--bg)",
              borderRadius: 8, cursor: "pointer", padding: "4px 11px", fontSize: 12.5, color: "var(--ink-soft)" }}>show all — every horizon</button>}
      </div>
    </Panel>
  );
}
