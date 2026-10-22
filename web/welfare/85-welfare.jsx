/* ============================ WELFARE: the app ============================ */
// welfare.html (redlines/views/welfare.py; 2026-10-22): AIRO's own panels --
// the Timeline and Graph 1 on the Forecasts tab, the Capability and Policy
// levers tabs, the FAQ's prompt and panel answers -- drawn from the welfare
// log through the same blobs index.html's read. Every cell is five
// percentiles in its question's unit (valueKind "percentiles"): a dot is a
// median, its bar the 25th-75th and 10th-90th. __WELFARE__ carries what only
// this page shows: the day, the five prompts, the cost.
const WF = (typeof window !== "undefined" && window.__WELFARE__) || null;

// The Timeline, one question at a time, chosen on the rail Graph 1 uses.
function WelfareTimeline() {
  const Q = (TL && TL.questions) || [];
  const [qid, setQid] = useState(Q.length ? Q[0].id : null);
  if (!Q.length) return <TimelinePanel qid="" title="Welfare forecasts over time" />;
  const q = Q.find(x => x.id === qid) || Q[0];
  return (
    <div className="rail-grid" style={{ gap: 18 }}>
      <Panel style={{ padding: 14, alignSelf: "start" }}>
        <QuestionRail title="Question" value={q.id} onChange={setQid}
          items={Q.map(x => ({ key: x.id, label: x.railLabel || x.short, color: x.color, group: x.group }))} />
      </Panel>
      <div style={{ minWidth: 0 }}>
        <TimelinePanel key={q.id} qid={q.id} title={q.heading} sub="Forecasts over time" />
      </div>
    </div>
  );
}

// The FAQ: AIRO's items and disclosures, with the welfare instrument's answers.
function WelfareFaq() {
  const [open, setOpen] = useState(() => { const o = {}; faqParam().forEach(id => { o[id] = true; }); return o; });
  const item = (id, q, body) => <FaqItem key={id} id={id} q={q} open={!!open[id]} onToggle={() => setOpen(o => ({ ...o, [id]: !o[id] }))}>{body}</FaqItem>;
  return (
    <Panel style={{ padding: "24px 28px 8px" }}>
      <div className="faq">
        <h2 style={{ fontSize: 22, marginTop: 6, marginBottom: 18 }}>About these forecasts</h2>
        {item("elicit", "How are these forecasts made?", <React.Fragment>
          <p>With AIRO's instrument, asked of five welfare questions instead of AIRO's catastrophe questions. In one call, each model gives its 10th, 25th, 50th, 75th and 90th percentiles for every question and horizon: once unconditionally, under each of eight LEAP Wave 12 AI policies, and at five levels of frontier AI capability (its own percentiles of the Epoch Capabilities Index six months out).</p>
          <p>Each model is asked five times a run, once under each prompt below. Its number is the mean of the five, each percentile on its own.</p>
          <ol>{((WF && WF.prompts) || []).map(p => <li key={p.condition}><span className="mono">{p.condition}</span>: {p.text || "no added instruction."}</li>)}</ol>
          <PromptDisclosure />
        </React.Fragment>)}
        {item("panel", "Which models are in the ensemble?", <React.Fragment>
          <p>AIRO's: the frontier models ranked highest on the Epoch Capabilities Index that we can run. The ensemble's forecast is the median across models of each percentile.</p>
          <PanelMembers />
        </React.Fragment>)}
        {item("read", "How do I read the charts?", <React.Fragment>
          <p>A dot is a median (50th percentile). The thick bar behind it spans the 25th to 75th percentile and the thin one the 10th to 90th. On the Policy levers and Capability tabs the top row is each model's unconditional forecast and the vertical line their median; each condition's row shows each model's forecast under it, and the number at the right is the ensemble median with its change from the unconditional.</p>
        </React.Fragment>)}
      </div>
    </Panel>
  );
}

function App() {
  const tabRaw = new URLSearchParams(typeof location !== "undefined" ? location.search : "").get("tab");
  const [mainTab, setMainTab] = useState(["forecasts", "capability", "conditional", "faq"].includes(tabRaw) ? tabRaw : "forecasts");
  return (
    <React.Fragment>
      <header style={{ marginBottom: 20 }}>
        <a href="https://forecastingresearch.org" title="Forecasting Research Institute"><img className="brand-logo" src="web/img/fri-logo.svg" alt="Forecasting Research Institute" width="231" height="37" /></a>
        <h1 style={{ fontSize: "clamp(25px, 7.5vw, 33px)", marginTop: 8, marginBottom: 6 }}>AIRO: life expectancy and economic growth</h1>
        <p style={{ color: "var(--ink-soft)", maxWidth: 760, margin: 0 }}>
          Tracking life expectancy and economic growth at multiple horizons, as forecast by an ensemble of frontier
          LLMs: unconditionally, under AI policies, and at different levels of AI capability.
        </p>
      </header>
      {WF && WF.day && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 10, fontSize: 13, color: "var(--ink-soft)" }}>
          <span style={{ background: "var(--warn-bg)", border: "1px solid var(--warn-line)", borderRadius: 999, color: "var(--warn-ink)", fontWeight: 700, letterSpacing: "0.04em", padding: "3px 8px" }}>{WF.day}</span>
          <span className="mono">{WF.protocol} · {Object.entries(WF.usage).map(([m, c]) => m + " $" + c.toFixed(2)).join(", ")}</span>
        </div>
      )}
      <details style={{ marginBottom: 14, fontSize: 13, color: "var(--ink-soft)" }}>
        <summary style={{ cursor: "pointer" }}>Each model's number is the mean of its forecasts under {((WF && WF.prompts) || []).length} prompts</summary>
        <ol style={{ margin: "8px 0 0", paddingLeft: 22 }}>
          {((WF && WF.prompts) || []).map(p => <li key={p.condition} style={{ marginBottom: 4 }}><span className="mono">{p.condition}</span>: {p.text || "no added instruction."}</li>)}
        </ol>
      </details>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 20 }}>
        <Toggle options={[{ key: "forecasts", label: "Forecasts" }, { key: "capability", label: "Capability" }, { key: "conditional", label: "Policy levers" }, { key: "faq", label: "FAQ" }]}
          value={mainTab} onChange={setMainTab} />
      </div>
      {mainTab === "forecasts" && <React.Fragment><WelfareTimeline /><LiveGraph1 /></React.Fragment>}
      {mainTab === "capability" && <CapabilityPanel />}
      {mainTab === "conditional" && <ConditionalPanel />}
      {mainTab === "faq" && <WelfareFaq />}
    </React.Fragment>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
