/* ============================ mock data ============================ */
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

const MONTHS = ["Jun ’25","Jul ’25","Aug ’25","Sep ’25","Oct ’25","Nov ’25","Dec ’25","Jan ’26","Feb ’26","Mar ’26","Apr ’26","May ’26","Jun ’26"];
const SURVEY_IDX = [0, 3, 6, 9, 12]; // superforecaster surveys are quarterly

// start/end = headline (≥10M deaths) model forecast (%) at the 12-month horizon.
const CATEGORIES = [
  { key: "totcat", label: "Total catastrophic risk (AI + non-AI)", color: "#24292f", start: 4.4, end: 6.0, vol: 0.26, emphasis: true },
  { key: "totai",  label: "Total AI-enabled risk",                color: "#8250df", start: 3.1, end: 4.6, vol: 0.22 },
  { key: "cbrn",   label: "AI-enabled CBRN",                      color: "#1b7c83", start: 1.1, end: 1.9, vol: 0.14 },
  { key: "cyber",  label: "AI-enabled cyber / infrastructure",   color: "#bc4c00",  start: 1.4, end: 2.7, vol: 0.20 },
  { key: "control",label: "Loss of control / power-seeking",      color: "#cf222e",  start: 0.6, end: 1.5, vol: 0.16 },
  { key: "geo",    label: "AI-enabled geopolitical / nuclear",    color: "#1a7f37", start: 2.0, end: 2.4, vol: 0.18 },
  { key: "nonai",  label: "Non-AI baseline (pandemic, nuclear, natural)", color: "#6e7781", start: 1.8, end: 1.9, vol: 0.10, baseline: true },
];

const HORIZONS = {
  "12mo": { label: "Within 12 months", scale: 1 },
  "5yr":  { label: "Within 5 years",   scale: 3.6 },
};

const SEVERITY = [
  { key: "1M",  label: "≥ 1 million deaths",   factor: 1.70 },
  { key: "10M", label: "≥ 10 million deaths",  factor: 1.00, headline: true },
  { key: "1B",  label: "≥ 1 billion deaths",   factor: 0.42 },
  { key: "ext", label: "Human extinction",     factor: 0.18 },
];

const FC = {
  model:  { key: "model",  label: "Models (monthly)",          color: "var(--model)" },
  super:  { key: "super",  label: "Superforecasters (quarterly)", color: "var(--super)" },
  hybrid: { key: "hybrid", label: "Hybrid — model after seeing humans (quarterly)", color: "var(--hybrid)" },
};

// returns { model:[13 monthly], super:[{i,v} quarterly], hybrid:[{i,v} quarterly] }
function buildPanel(cat, horizonKey, sevFactor) {
  const h = HORIZONS[horizonKey];
  const f = sevFactor == null ? 1 : sevFactor;
  const seed = (cat.key.length * 911) ^ Math.round(cat.start * 1000) ^ (horizonKey === "5yr" ? 7777 : 31) ^ Math.round(f * 100);
  const rng = mulberry32(seed);
  const n = MONTHS.length;
  const trend = i => (cat.start + (cat.end - cat.start) * (i / (n - 1))) * h.scale * f;
  const model = [];
  for (let i = 0; i < n; i++) {
    model.push(Math.max(0.02, trend(i) + (rng() - 0.5) * 2 * cat.vol * h.scale * f));
  }
  const sup = SURVEY_IDX.map(i => {
    const v = trend(i) * 0.70 + (rng() - 0.5) * cat.vol * h.scale * f * 0.5;
    return { i, v: Math.max(0.02, v) };
  });
  const hybrid = SURVEY_IDX.map((i, k) => {
    // model's revised estimate after viewing the superforecaster panel: pulled partway toward humans
    const v = model[i] * 0.6 + sup[k].v * 0.4 + (rng() - 0.5) * cat.vol * h.scale * f * 0.25;
    return { i, v: Math.max(0.02, v) };
  });
  return { model, sup, hybrid };
}

/* ============================ chart helpers ============================ */
function niceMax(v) {
  const steps = [0.5,1,2,2.5,3,4,5,6,8,10,12,15,20,25,30,40,50,60,80];
  for (const s of steps) if (s >= v) return s;
  return Math.ceil(v / 10) * 10;
}

/* ============================ time-series chart ============================ */
function TimeSeriesChart({ panel, active }) {
  const W = 880, H = 380;
  const pad = { l: 46, r: 70, t: 16, b: 40 };
  const n = MONTHS.length;
  const x = i => pad.l + (i / (n - 1)) * (W - pad.l - pad.r);

  const lines = [];
  if (active.model)  lines.push({ ...FC.model,  pts: panel.model.map((v, i) => ({ i, v })), kind: "line" });
  if (active.super)  lines.push({ ...FC.super,  pts: panel.sup,    kind: "marker" });
  if (active.hybrid) lines.push({ ...FC.hybrid, pts: panel.hybrid, kind: "marker" });

  const allV = lines.flatMap(l => l.pts.map(p => p.v));
  const bandTop = active.model ? Math.max(...panel.model) * 1.32 : 0;
  const ymax = niceMax(Math.max(...allV, bandTop, 0.5) * 1.05);
  const y = v => pad.t + (1 - v / ymax) * (H - pad.t - pad.b);
  const yticks = Array.from({ length: 6 }, (_, i) => (ymax / 5) * i);
  const box = React.useRef(null);
  const [hv, setHv] = useState(null);

  const linePath = pts => pts.map((p, k) => (k === 0 ? "M" : "L") + x(p.i).toFixed(1) + " " + y(p.v).toFixed(1)).join(" ");
  let band = null;
  if (active.model) {
    const sp = 0.30;
    const up = panel.model.map((v, i) => x(i) + "," + y(v * (1 + sp))).join(" ");
    const dn = panel.model.map((v, i) => x(i) + "," + y(v * (1 - sp))).reverse().join(" ");
    band = up + " " + dn;
  }

  return (
    <div ref={box} style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} onMouseLeave={() => setHv(null)}>
        {yticks.map((t, i) => (
          <g key={i}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--line-soft)" />
            <text x={pad.l - 9} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--ink-faint)" className="mono">{t.toFixed(t < 10 ? 1 : 0)}%</text>
          </g>
        ))}
        {MONTHS.map((m, i) => {
          const survey = SURVEY_IDX.includes(i);
          return (
            <g key={i}>
              {survey && <line x1={x(i)} x2={x(i)} y1={pad.t} y2={H - pad.b} stroke="var(--super)" strokeWidth="1" opacity="0.10" />}
              {(i % 2 === 0) && <text x={x(i)} y={H - 14} textAnchor="middle" fontSize="10.5" fill={survey ? "var(--ink-soft)" : "var(--ink-faint)"} fontWeight={survey ? 600 : 400}>{m}</text>}
            </g>
          );
        })}
        {band && <polygon points={band} fill="var(--model)" opacity="0.09" />}
        {lines.map(l => (
          <path key={l.key} d={linePath(l.pts)} fill="none" stroke={l.color}
            strokeWidth={l.kind === "line" ? 2.6 : 1.6} strokeDasharray={l.kind === "marker" ? "5 4" : "none"}
            strokeLinejoin="round" strokeLinecap="round" opacity={l.kind === "line" ? 1 : 0.85} />
        ))}
        {lines.filter(l => l.kind === "marker").map(l => (
          <g key={l.key + "-m"}>{l.pts.map((p, k) => <circle key={k} cx={x(p.i)} cy={y(p.v)} r="4" fill="var(--panel)" stroke={l.color} strokeWidth="2" />)}</g>
        ))}
        {lines.map(l => {
          const last = l.pts[l.pts.length - 1];
          return <text key={l.key + "-lab"} x={x(last.i) + 8} y={y(last.v) + 4} fontSize="11" fill={l.color} className="mono" fontWeight="500">{last.v.toFixed(1)}%</text>;
        })}
        {hv != null && <line x1={x(hv)} x2={x(hv)} y1={pad.t} y2={H - pad.b} stroke="var(--ink-faint)" strokeDasharray="3 3" opacity="0.6" />}
        {MONTHS.map((m, i) => (
          <rect key={"hit" + i} x={x(i) - (W - pad.l - pad.r) / (2 * (n - 1))} y={pad.t}
            width={(W - pad.l - pad.r) / (n - 1)} height={H - pad.t - pad.b} fill="transparent" onMouseEnter={() => setHv(i)} />
        ))}
      </svg>
      {hv != null && (() => {
        const rows = lines.map(l => ({ l, p: l.pts.find(p => p.i === hv) })).filter(r => r.p);
        if (!rows.length) return null;
        return (
          <PointTooltip box={box} x={x(hv)} y={y(rows[0].p.v)}>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginBottom: 5 }}>{MONTHS[hv]}{SURVEY_IDX.includes(hv) ? " · survey" : ""}</div>
            {rows.map(({ l, p }) => (
              <div key={l.key} style={{ display: "flex", justifyContent: "space-between", gap: 14, fontSize: 12 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 9, height: 9, borderRadius: 2, background: l.color }}></span>{l.label.split(" (")[0].split(" — ")[0]}</span>
                <span className="mono" style={{ fontWeight: 500 }}>{p.v.toFixed(2)}%</span>
              </div>
            ))}
          </PointTooltip>
        );
      })()}
    </div>
  );
}

