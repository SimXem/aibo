/* Original model explanations; no generated ensemble or revision narrative. */
const RATIONALES = window.__RATIONALES__ || { calls: {}, questions: {} };
// Horizon keys are shared with the severity ladder, whose labels carry the
// dated window ("within 12 months (by 2027-09-16)"); fall back to "by <key>".
const rationaleHorizonLabel = h => (((typeof G2 !== "undefined" && G2) || {}).horizonLabels || {})[h] || "by " + h;
const rationalePct = v => (v == null ? "—" : Number(v.toPrecision(4)) + "%");
function RationaleSources({ sources }) {
  if (!sources.length) return <p>No sources recorded for this explanation.</p>;
  return <ul style={{ paddingLeft: 20 }}>{sources.map((s, i) => {
    const url = typeof s === "string" ? s : s.url;
    const safe = typeof url === "string" && /^https?:\/\//i.test(url);
    return <li key={i} style={{ marginBottom: 6, overflowWrap: "anywhere" }}>
      {safe ? <a href={url} target="_blank" rel="noopener noreferrer">{url}</a> : String(url || "Source not recorded")}
      {s.contribution && <span> — {s.contribution}</span>}
    </li>;
  })}</ul>;
}
const rationaleConditionKey = c => c.condition || c.promptVariant || "unrecorded";
// One condition only. Raw call probabilities are fractions; convert to percent
// once, after averaging any repeat calls that answered this question/horizon.
function rationaleConditionForecasts(qid, horizons, models, calls) {
  return horizons.map(key => {
    const values = {}, counts = {};
    models.forEach(model => {
      const ps = calls.filter(([, c]) => c.model === model)
        .map(([, c]) => (((c.forecasts || {})[qid] || {})[key]))
        .filter(p => typeof p === "number" && Number.isFinite(p));
      counts[model] = ps.length;
      values[model] = ps.length ? 100 * ps.reduce((sum, p) => sum + p, 0) / ps.length : null;
    });
    return { key, values, counts };
  });
}
function RationaleForecastTable({ rows, models, conditionLabel }) {
  if (!rows.length || !models.length) return null;
  const repeated = rows.some(row => models.some(model => row.counts[model] > 1));
  return <div style={{ overflowX: "auto", marginTop: 12 }}>
    <table className="tv" style={{ width: "auto", minWidth: 260 }}>
      <caption style={{ textAlign: "left", fontWeight: 600, paddingBottom: 6 }}>
        {conditionLabel} prompt: forecasts by model
      </caption>
      <thead><tr><th scope="col">Horizon</th>{models.map(model => <th scope="col" key={model}>{model}</th>)}</tr></thead>
      <tbody>{rows.map(row => <tr key={row.key}>
        <td>{rationaleHorizonLabel(row.key)}</td>
        {models.map(model => <td key={model} className="mono"
          title={row.counts[model] > 1 ? `Mean of ${row.counts[model]} recorded calls` : undefined}>
          {rationalePct(row.values[model])}
        </td>)}
      </tr>)}</tbody>
    </table>
    {repeated && <p style={{ fontSize: 12, color: "var(--ink-soft)" }}>Each cell averages the available repeat calls for that model and horizon within this prompt condition.</p>}
  </div>;
}
function RationaleExplanation({ id, call: c, qid }) {
  const explanation = (c.debriefs || {})[qid];
  const prompt = (RATIONALES.prompts || {})[c.promptId];
  return <div style={{ marginTop: 16 }}>
    <details>
      <summary style={{ cursor: "pointer" }}>Model rationale</summary>
      <p style={{ fontSize: 12, color: "var(--ink-soft)" }}>{explanation ? "Model’s explanation for this question, recorded after its forecasts. Covers all horizons." : "Model’s original explanation for its full forecast batch; not specific to this question or horizon."}</p>
      <p style={{ whiteSpace: "pre-wrap" }}>{(explanation && explanation.rationale) || c.rationale || "No written rationale recorded."}</p>
      {explanation && explanation.weakest_link && <p><strong>Weakest assumption: </strong>{explanation.weakest_link}</p>}
      <details><summary style={{ cursor: "pointer" }}>Sources cited by this model</summary>
        <RationaleSources sources={(explanation && explanation.key_sources) || c.sources} />
      </details>
      <details style={{ marginTop: 8 }}><summary style={{ cursor: "pointer" }}>Original batch explanation and provenance</summary>
        {explanation && <p style={{ whiteSpace: "pre-wrap" }}>{c.rationale}</p>}
        <p style={{ overflowWrap: "anywhere", color: "var(--ink-soft)" }}>Model: {c.modelId}<br />Elicited: {c.elicitedAt}<br />Run: {c.run}<br />Call: {id}<br />Instrument: {c.instrument}<br />Protocol: {c.protocol}<br />Prompt condition: {c.condition || "Not recorded"}<br />Scenario: unconditional</p>
        <a href="redlines-data.zip" download="airo-data.zip">Download original forecasts, explanations and logs</a>
      </details>
    </details>
    <details style={{ marginTop: 8 }}><summary style={{ cursor: "pointer" }}>View full prompt</summary>
      {prompt ? <>
        {prompt.system && prompt.system.trim() && <><p style={{ fontWeight: 600 }}>System prompt</p><pre className="faq-pre">{prompt.system}</pre></>}
        <p style={{ fontWeight: 600 }}>User prompt</p>
        <pre className="faq-pre">{prompt.user}</pre>
      </> : <p>Full prompt not recorded for this call.</p>}
    </details>
  </div>;
}
// `forecasts` supplies the chart's horizons and model roster, not its pooled
// probabilities. The comparison table uses only archived calls for the chosen
// prompt condition, question, and displayed date.
function ForecastRationales({ qid, context, forecasts = [], date, controls }) {
  const [selectedCondition, setSelectedCondition] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [selectedCall, setSelectedCall] = useState("");
  const entries = RATIONALES.questions[qid] || {};
  const models = Object.keys(entries).filter(m => forecasts.some(f => (f.values || {})[m] != null));
  const allCalls = models.flatMap(model => (entries[model] || []).map(id => [id, RATIONALES.calls[id]]))
    .filter(([, c]) => c && (!date || c.date === date));
  const order = RATIONALES.conditionOrder || [];
  const rank = condition => order.includes(condition) ? order.indexOf(condition) : order.length;
  const conditions = [...new Set(allCalls.map(([, c]) => rationaleConditionKey(c)))].sort((a, b) => rank(a) - rank(b));
  const condition = conditions.includes(selectedCondition) ? selectedCondition : conditions[0];
  const conditionCalls = allCalls.filter(([, c]) => rationaleConditionKey(c) === condition);
  const availableModels = models.filter(model => conditionCalls.some(([, c]) => c.model === model));
  const model = availableModels.includes(selectedModel) ? selectedModel : availableModels[0];
  const calls = conditionCalls.filter(([, c]) => c.model === model);
  const current = calls.find(([id]) => id === selectedCall) || calls[0];
  const chosen = current && current[1];
  const label = c => c.promptLabel || "Unrecorded";
  const rows = rationaleConditionForecasts(qid, forecasts.map(f => f.key), models, conditionCalls);
  return <details style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--line-soft)", fontSize: 13, lineHeight: 1.6 }}>
    <summary style={{ cursor: "pointer", fontWeight: 600, color: "var(--ink)" }}>Model rationale for its forecasts</summary>
    {controls}
    <p style={{ margin: "10px 0", fontWeight: 600 }}>{context}</p>
    {!chosen ? <p>No explanation recorded for this forecast.</p> : <>
      <div className="rationale-controls">
        <label>Prompt condition<select value={condition} onChange={e => setSelectedCondition(e.target.value)}>
          {conditions.map(key => <option key={key} value={key}>{label(allCalls.find(([, c]) => rationaleConditionKey(c) === key)[1])}</option>)}
        </select></label>
      </div>
      <p style={{ fontWeight: 600, marginBottom: 4 }}>{label(chosen)} prompt</p>
      <p style={{ fontWeight: 600, marginTop: 0 }}>
        {chosen.promptVariant === "none" ? "No additional instruction." : chosen.promptInstruction || "Added instruction text is not available for this call."}
      </p>
      <RationaleForecastTable rows={rows} models={models} conditionLabel={label(chosen)} />
      {conditions.length > 1 && <p style={{ fontSize: 12, color: "var(--ink-soft)" }}>The main charts average across prompt conditions; this table shows the selected condition.</p>}
      <div className="rationale-controls">
        <label>Model<select value={model} onChange={e => setSelectedModel(e.target.value)}>
          {availableModels.map(name => <option key={name} value={name}>{name}</option>)}
        </select></label>
        {calls.length > 1 && <label>Explanation from call<select value={current[0]} onChange={e => setSelectedCall(e.target.value)}>
          {calls.map(([id], index) => <option key={id} value={id}>Call {index + 1}</option>)}
        </select></label>}
      </div>
      <RationaleExplanation key={`${qid}:${current[0]}`} id={current[0]} call={chosen} qid={qid} />
    </>}
  </details>;
}
// `causes`: [{key, label, rungs}], each cause's rungs from BOTH ladders (the
// deaths questions, then the damages ones), keyed by question id.
function LadderRationales({ causes, date }) {
  const [causeKey, setCauseKey] = useState("ai");
  const [qid, setQid] = useState(null);
  const cause = causes.find(c => c.key === causeKey) || causes[0];
  if (!cause) return null;
  const rung = cause.rungs.find(r => r.qid === qid) || cause.rungs.find(r => r.rung === "1M") || cause.rungs[0];
  if (!rung) return null;
  // The same question on every horizon the ladder was elicited on, on
  // whichever ladder it sits.
  const forecasts = G2.horizons.map(h => {
    let r = null;
    Object.values((G2.byHorizon[h] || {}).legs || {}).some(side => {
      const c = (side.causes || []).find(x => x.key === cause.key);
      r = c && c.rungs.find(x => x.qid === rung.qid);
      return !!r;
    });
    return { key: h, values: (r && r.per_model) || {} };
  });
  const controls = <div className="rationale-controls">
    <label>Explain cause <select value={cause.key} onChange={e => setCauseKey(e.target.value)}>{causes.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}</select></label>
    <label>Severity <select value={rung.qid} onChange={e => setQid(e.target.value)}>{cause.rungs.map(r => <option key={r.qid} value={r.qid}>{r.label}</option>)}</select></label>
  </div>;
  return <ForecastRationales qid={rung.qid} forecasts={forecasts} date={date} controls={controls}
    context={`${cause.label} · ${rung.label}`} />;
}
