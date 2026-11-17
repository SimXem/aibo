/* ============================ question rail (shared by index.html and timeline.html) ============================ */
// Referenced from both manifests as ../shared/question-rail.jsx so the two
// pages' rails are one component, not two copies.
// The question rail, one component for every tab that has one (Graph 1, the
// Policy-levers tab): a title, sections named by `group`, one row per item
// with its colour dot; the selected row is outlined on the page background.
// Nick, 2026-08-27: the two tabs' rails looked different — "why have them be
// different?" — so they no longer can.
// On a phone (the .rail-grid column has collapsed under the chart's) the
// same items render as a wrapping row of chips, group headings inline, so
// the rail costs three lines instead of a screen.
function QuestionRail({ title, items, value, onChange }) {
  const groups = [...new Set(items.map(it => it.group || ""))];
  const narrow = useNarrow(760);
  const heading = <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginBottom: 4, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase" }}>{title}</div>;
  if (narrow) {
    return (
      <div>
        {heading}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          {groups.map(g => (
            <React.Fragment key={g || "all"}>
              {g && <div style={{ width: "100%", fontSize: 11, color: "var(--ink-faint)", fontWeight: 600, margin: "6px 0 0" }}>{g}</div>}
              {items.filter(it => (it.group || "") === g).map(it => {
                const sel = it.key === value;
                return (
                  <button key={it.key} onClick={() => onChange(it.key)} style={{ display: "inline-flex", alignItems: "center", gap: 7,
                    border: "1px solid " + (sel ? "var(--ink)" : "var(--line)"), background: sel ? "var(--ink)" : "var(--panel)",
                    color: sel ? "white" : "var(--ink)", cursor: "pointer", padding: "6px 11px", borderRadius: 999,
                    fontSize: 12.5, fontWeight: sel ? 600 : 500, lineHeight: 1.2 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 3, background: it.color || "var(--ink-faint)", flexShrink: 0,
                      outline: sel ? "1px solid rgba(255,255,255,0.7)" : "none" }}></span>
                    <span>{it.label}</span>
                  </button>
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {heading}
      <div style={{ maxHeight: 620, overflowY: "auto", display: "flex", flexDirection: "column", gap: 2, paddingRight: 4 }}>
        {groups.map(g => (
          <div key={g || "all"} style={{ marginBottom: 8 }}>
            {g && <div style={{ fontSize: 11, color: "var(--ink-faint)", fontWeight: 600, margin: "6px 10px 4px" }}>{g}</div>}
            {items.filter(it => (it.group || "") === g).map(it => {
              const sel = it.key === value;
              return (
                <button key={it.key} onClick={() => onChange(it.key)} style={{ display: "flex", alignItems: "center", gap: 8,
                  textAlign: "left", width: "100%", border: "1px solid " + (sel ? "var(--line)" : "transparent"),
                  background: sel ? "var(--bg)" : "transparent", cursor: "pointer", padding: "7px 10px",
                  borderRadius: 9, marginBottom: 2 }}>
                  <span style={{ width: 10, height: 10, borderRadius: 3, background: it.color || "var(--ink-faint)", flexShrink: 0 }}></span>
                  <span style={{ fontSize: 13, color: "var(--ink)", fontWeight: sel ? 600 : 500, lineHeight: 1.25 }}>{it.label}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
