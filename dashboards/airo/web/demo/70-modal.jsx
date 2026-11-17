/* ============================ details modal ============================ */
const INTERMEDIATE_EVENTS = [
  ["AI R&D acceleration", "Release dates of models hitting threshold scores on existing / new AI benchmarks; ‘speed-up’ task performance; reductions in $ or time to train a model that reaches a fixed benchmark."],
  ["Biosecurity", "New biology / wet-lab troubleshooting benchmarks; controlled human-uplift studies; public model safety-tier changes driven by CBRN concerns; nucleic-acid screening policy changes."],
  ["Cyber", "Autonomous cyber-range performance; AI-attributed cyber incidents; credible reports of AI agents finding consequential vulnerabilities in authorized settings."],
  ["Loss of control / power-seeking", "Autonomous replication, resource acquisition, shutdown evasion, deception of evaluators, or propagation beyond intended environments."],
  ["Geopolitical & baselines", "Taiwan conflict, nuclear escalation, WHO emergency declarations, major climate / natural-disaster indicators, and other non-AI baselines."],
];
// A question's resolution criteria, verbatim from the blob, behind a
// disclosure: the text is the question set's (redlines/questions.py), never
// typed here, so the modal cannot disagree with the questions it describes.
function Criteria({ title, criteria, details }) {
  const parts = [criteria, ...Object.values(details || {})].filter(Boolean);
  if (!parts.length) return null;
  return (
    <details style={{ fontSize: 12.5, color: "var(--ink-soft)", margin: "6px 0 0" }}>
      <summary style={{ cursor: "pointer" }}>{title}</summary>
      <div style={{ marginTop: 8, paddingLeft: 12, borderLeft: "2px solid var(--line)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
        {parts.join("\n")}
      </div>
    </details>
  );
}
function HumanDisempowermentDefinition() {
  const q = G1 && (G1.questions || []).find(q => q.id === "disempowerment");
  if (!q || !q.criteria) return null;
  const summary = q.criteria.split("\n").find(line => line.trim());
  return <React.Fragment>
    <p style={{ color: "var(--ink-soft)", margin: "0 0 6px", lineHeight: 1.55 }}>{summary.replace(/^\s*\*\s*/, "").trim()}</p>
    <Criteria title="Full definition and resolution criteria" criteria={q.criteria} details={q.details} />
  </React.Fragment>;
}
function Modal({ onClose }) {
  // The headline question (the Timeline's) for the catastrophe threshold and
  // its criteria; the ladder's shared criteria ride the Graph 2 blob.
  const cat = G1 && ((G1.questions || []).find(q => q.id === "catastrophe:ai") || G1.questions[0]);
  const ladder = (G2_RAW && G2_RAW.ladder) || null;
  const container = ((G2_RAW && G2_RAW.causeDefs) || []).find(c => c.container);
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(31, 35, 40, 0.45)", zIndex: 50,
      display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "clamp(14px, 6vw, 48px) 12px", overflowY: "auto" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: "var(--panel)", maxWidth: 760, width: "100%", borderRadius: 16,
        padding: "clamp(18px, 4vw, 28px) clamp(16px, 4.5vw, 32px) 36px", boxShadow: "var(--shadow)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
          <h2 style={{ fontSize: 24 }}>Definitions &amp; methodology</h2>
          <button onClick={onClose} style={{ border: "1px solid var(--line)", background: "var(--bg)", borderRadius: 8, cursor: "pointer", padding: "4px 11px", fontSize: 18, color: "var(--ink-soft)" }}>×</button>
        </div>

        <h3 style={{ fontSize: 17, marginTop: 18, marginBottom: 8 }}>What counts as “catastrophic”</h3>
        {/* Threshold and criteria from the question set. This section used
            to state its own numbers and disagreed with the questions it
            described; since 2026-09-10 the criteria are shown verbatim
            instead of paraphrased. */}
        {cat && (
          <p style={{ fontSize: 13.5, color: "var(--ink-soft)", marginTop: 0, marginBottom: 0 }}>
            Catastrophe threshold: <strong>{cat.severity}</strong>.
          </p>
        )}
        {cat && <Criteria title="Resolution criteria for the catastrophe question" criteria={cat.criteria} details={cat.details} />}

        <h3 style={{ fontSize: 17, marginTop: 22, marginBottom: 8 }}>Human disempowerment</h3>
        <div style={{ fontSize: 13.5 }}><HumanDisempowermentDefinition /></div>

        <h3 style={{ fontSize: 17, marginTop: 22, marginBottom: 8 }}>The severity ladder</h3>
        <p style={{ fontSize: 13.5, color: "var(--ink-soft)", marginTop: 0, marginBottom: 6 }}>
          Every incident category is asked at each rung, as two questions: one resolving on the deaths (or equivalent morbidity), one on the economic damages. The extinction rung has no dollar leg.
        </p>
        <ul style={{ fontSize: 13.5, color: "var(--ink-soft)", margin: "0 0 4px", paddingLeft: 20 }}>
          {((G2_RAW && G2_RAW.rungs) || []).map(r => <li key={r.rung} style={{ marginBottom: 3 }}>{r.label}</li>)}
        </ul>
        {ladder && <Criteria title="Resolution criteria for the ladder" criteria={ladder.criteria} details={ladder.details} />}
        <ExpectedLossNote />

        <h3 style={{ fontSize: 17, marginTop: 22, marginBottom: 8 }}>Risk categories</h3>
        {/* The incident types and Bridget's own definition of each, from the
            question set. */}
        <ul style={{ fontSize: 13.5, color: "var(--ink-soft)", margin: 0, paddingLeft: 20 }}>
          {((G2_RAW && G2_RAW.causeDefs) || []).map(c => (
            <li key={c.key} style={{ marginBottom: 3 }}>
              <strong style={{ color: c.color }}>{c.label}</strong>
              {c.container && <span style={{ color: "var(--ink-faint)" }}> (contains the other three)</span>}
              {c.definition ? " — " + c.definition : ""}
            </li>
          ))}
        </ul>
        {container && (
          <p style={{ fontSize: 13.5, color: "var(--ink-soft)", margin: "10px 0 0" }}>
            The categories overlap, and “{container.label}” contains the rest, so their probabilities cannot be added.
          </p>
        )}

        {/* Canary questions were deferred to v2 on the 2026-08-10 call and the
            data bank builds with include_canaries=False, so this section
            described a feature the dashboard does not have. Shown only when
            canary rows are actually present. */}
        {DB_RAW && DB_RAW.counts && DB_RAW.counts.canary > 0 && <>
        <h3 style={{ fontSize: 17, marginTop: 22, marginBottom: 8 }}>Intermediate (validation) events</h3>
        <p style={{ fontSize: 13.5, color: "var(--ink-soft)", marginTop: 0, marginBottom: 10 }}>
          Shorter-horizon questions selected to (a) resolve within ~6 months and (b) appreciably move the catastrophic forecast.
          They both validate subject-matter skill and feed the catastrophic estimates.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {INTERMEDIATE_EVENTS.map(([fam, sig]) => (
            <div key={fam} className="modal-grid" style={{ fontSize: 13, borderTop: "1px solid var(--line-soft)", paddingTop: 8 }}>
              <div style={{ fontWeight: 600 }}>{fam}</div>
              <div style={{ color: "var(--ink-soft)" }}>{sig}</div>
            </div>
          ))}
        </div>
        </>}
        {/* The "Forecaster cadence" section came off 2026-09-10 (Nick). */}
      </div>
    </div>
  );
}
