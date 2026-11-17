// The page: window.__EEAI__ (eeai/build.py) -> the header, the GDP panel, the
// other indicators, the AI progress answers, the download. Plain DOM.
//
// Two controls are page-wide (state): split -- false shows the unconditional
// forecast, true the three AI-progress scenarios in its place -- and horizon,
// the date the numbers are about and the timeline runs out to. One belongs to
// each chart area (historyOf, the little toggle at the right of its controls;
// the areas are "hero", the GDP panel, and "grid", the other indicators): the
// timeline with the current forecast, or how the forecast for that date has
// moved from run to run.
const D = window.__EEAI__ || { questions: [], runs: [], scenarios: [] };
const state = { split: false, horizon: "2030" };
const DATES = [...new Set(D.questions.flatMap(q => q.horizons.map(z => z.id)))].sort();
// The view is in the address (#split=1&horizon=2030&history=hero,grid), so a link opens the same charts.
const said = new URLSearchParams(location.hash.slice(1));
if (said.get("split") === "1") state.split = true;
if (DATES.includes(said.get("horizon"))) state.horizon = said.get("horizon");
const historyOf = new Set((said.get("history") || "").split(",").filter(a => a === "hero" || a === "grid"));
const remember = () => { try { history.replaceState(null, "", `#split=${state.split ? 1 : 0}&horizon=${state.horizon}`
  + (historyOf.size ? `&history=${[...historyOf].join(",")}` : "")); } catch (e) {} };
const open = new Set();
const root = document.getElementById("root");
const charts = [];

// A control was used: change, redraw, and keep that control where it was on
// the screen (the page above it may have changed height) and focused.
function act(ev, change) {
  const k = ev.currentTarget.dataset.k, top = ev.currentTarget.getBoundingClientRect().top;
  change(); render(); remember();
  const b = [...root.querySelectorAll("[data-k]")].find(b => b.dataset.k === k);
  if (!b) return;
  window.scrollBy(0, b.getBoundingClientRect().top - top);
  b.focus({ preventScroll: true });
  b.classList.add("just");        // the one control that changed gets a small press animation
}
function seg(where, label, options, key, untitled) {
  return h("div", { class: "seg", role: "group", "aria-label": label }, !untitled && h("span", { class: "lab" }, label),
    options.map(([value, text]) => h("button", { type: "button", "aria-pressed": String(state[key] === value),
      "data-k": `${where}|${key}|${value}`, onclick: ev => act(ev, () => { state[key] = value; }) }, text)));
}
function controls(where) {
  return h("div", { class: "controls" },
    seg(where, "Forecast shown", [[false, "Unconditional"], [true, "Conditional on AI progress"]], "split", true),
    seg(where, "Horizon", DATES.map(d => [d, d]), "horizon"), viewToggle(where));
}
// A chart area's own little toggle: the current forecast on the timeline, or that forecast's history.
function viewToggle(where) {
  const hist = historyOf.has(where);
  return h("div", { class: "mini", role: "group", "aria-label": "View" },
    [[false, "Current", "Current forecast"], [true, "History", "Forecast history"]].map(([v, text, title]) =>
      h("button", { type: "button", title, "aria-pressed": String(hist === v), "data-k": `${where}|view|${v}`,
        onclick: ev => act(ev, () => { v ? historyOf.add(where) : historyOf.delete(where); }) }, text)));
}
function keep(id, summary, body) {
  const d = h("details", open.has(id) ? { open: "" } : {}, h("summary", {}, summary), h("div", { class: "body" }, body));
  d.addEventListener("toggle", () => d.open ? open.add(id) : open.delete(id));
  return d;
}
function chartBox(q, size) {
  const box = h("div", { class: "chart" }), where = size === "hero" ? "hero" : "grid";
  charts.push(() => drawChart(box, q, { ...state, size, target: horizonOf(q), view: historyOf.has(where) ? "history" : "now",
    order: D.latest ? D.latest.models : [] }));
  return box;
}
// The date the headline number and the history view are about: the one selected, or the question's last.
const horizonOf = q => q.horizons.some(z => z.id === state.horizon) ? state.horizon : q.horizons[q.horizons.length - 1].id;
const unitWord = q => q.unit === "% per year" ? "per year" : q.unit.startsWith("%") ? q.unit.slice(1).trim() : q.unit;

function legend(range, history) {
  const items = history ? [] : [h("span", { style: "color: var(--ink)" }, h("i", { class: "sw" }), h("span", {}, "Actual"))];
  if (state.split) for (const sc of SCEN) items.push(h("span", { style: `color: ${sc.color}` }, h("i", { class: "sw" }), h("span", { style: "color: var(--ink-soft)" }, sc.label)));
  else {
    items.push(h("span", { style: "color: var(--uncond)" }, h("i", { class: "sw dash" }), h("span", { style: "color: var(--ink-soft)" }, "Unconditional (panel median)")));
    if (range) items.push(h("span", {}, h("i", { class: "sw band" }), range));
  }
  if (history) {
    if (D.questions.some(q => q.horizons.some(z => z.id === state.horizon && z.actual))) items.push(h("span", { style: "color: var(--ink)" }, h("i", { class: "sw" }), h("span", {}, "Outcome")));
  } else if (D.questions.some(q => q.horizons.some(z => z.actual && z.asked))) items.push(h("span", {}, h("i", { class: "sw ring" }), "Forecast for a date whose outcome is in"));
  return h("div", { class: "legend" }, items);
}

function modelTable(q, hz) {
  const cell = (m, sc) => {
    const c = ((m.forecasts[hz] || {})[sc] || {});
    return c.p50 == null ? "–" : fmt(q, c.p50) + (c.p10 != null && c.p90 != null ? ` (${fmt(q, c.p10, true)} to ${fmt(q, c.p90, true)})` : "");
  };
  const ens = sc => { const p10 = val(q, hz, sc, "p10"), p90 = val(q, hz, sc, "p90");
    return fmt(q, val(q, hz, sc)) + (p10 != null && p90 != null ? ` (${fmt(q, p10, true)} to ${fmt(q, p90, true)})` : ""); };
  const cols = ["unconditional", "slow", "moderate", "rapid"];
  return h("div", { class: "scroll" }, h("table", { class: "tv" },
    h("thead", {}, h("tr", {}, h("th", {}, `${hz}`), h("th", {}, "Unconditional"), h("th", {}, "Slow"), h("th", {}, "Moderate"), h("th", {}, "Rapid"))),
    h("tbody", {},
      h("tr", {}, h("td", {}, h("b", {}, "Panel median")), cols.map(c => h("td", { class: "mono" }, ens(c)))),
      q.models.map(m => h("tr", {}, h("td", {}, m.label), cols.map(c => h("td", { class: "mono" }, cell(m, c))))))));
}
const rationales = q => q.models.map(m => h("p", {}, h("span", { class: "who" }, m.label + ": "), m.rationale || "No rationale given."));
function rationale(q, hz) {
  return keep("why:" + q.id, "Model forecasts and rationale", [modelTable(q, hz), rationales(q)]);
}
// Each date whose outcome is in: the outcome, and every forecast with its miss.
function outcomes(q) {
  const cols = [UNCOND].concat(SCEN), rows = q.horizons.filter(z => z.actual && cols.some(c => val(q, z.id, c.id) != null));
  if (!rows.length) return null;
  const cell = (z, c) => { const v = val(q, z.id, c.id), d = v - z.actual.value;
    return v == null ? "–" : `${fmt(q, v)} (${missText(q, d)})`; };
  return h("div", { class: "scroll" }, h("table", { class: "tv" },
    h("thead", {}, h("tr", {}, h("th", {}, "Date"), h("th", {}, "Outcome"), cols.map(c => h("th", {}, c.label.replace(" progress", ""))))),
    h("tbody", {}, rows.map(z => h("tr", {}, h("td", {}, z.id), h("td", { class: "mono" }, fmt(q, z.actual.value)),
      cols.map(c => h("td", { class: "mono" }, cell(z, c))))))));
}
const defined = q => [
  q.preamble && h("p", {}, q.preamble),
  h("p", {}, q.stem + (q.horizons[0].text ? "\n" + q.horizons.map(z => "• " + z.text).join("\n") : "")),
  h("p", {}, q.details)];
function definition(q) {
  return keep("def:" + q.id, "Question and definition", defined(q));
}

// A small chart's details open full-screen: a tile is too narrow for a table
// of four forecasts or a page of rationale. One dialog, outside #root so a
// redraw of the page leaves it alone; the browser's own modal dialog gives
// the focus trap, Escape, and focus back on the link that opened it.
const modal = h("dialog", { class: "modal", "aria-labelledby": "modal-title" });
document.body.append(modal);
modal.addEventListener("click", ev => { if (ev.target === modal) modal.close(); });   // a click on the backdrop
function openModal(q, title, body) {
  modal.replaceChildren(
    h("header", {}, h("div", {}, h("p", { class: "eyebrow" }, q.category), h("h2", { id: "modal-title" }, `${q.short}: ${title}`)),
      h("button", { type: "button", class: "close", "aria-label": "Close", onclick: () => modal.close() }, "×")),
    h("div", { class: "body" }, body));
  modal.showModal();
  modal.querySelector(".body").scrollTop = 0;
}
function more(q, title, body) {
  return h("button", { type: "button", class: "more", onclick: () => openModal(q, title, body()) }, title);
}

function hero(q) {
  const hz = horizonOf(q), v = val(q, hz, "unconditional"), p10 = val(q, hz, "unconditional", "p10"), p90 = val(q, hz, "unconditional", "p90");
  const span = `${hz - 5} to ${hz}`, history = historyOf.has("hero");
  const first = q.series[0], firstV = first && (((first.ensemble[hz] || {}).unconditional || {}).p50);
  const delta = q.series.length > 1 && firstV != null ? v - firstV : null;
  const probs = D.part1 && D.part1.scenario_probabilities.ensemble;
  return h("section", { class: "card" },
    h("div", { class: "head" }, h("div", {}, h("h2", {}, `US real GDP growth, ${span}`),
      h("p", { class: "sub", style: "color: var(--ink-soft); margin: 4px 0 0" }, history
        ? `How the panel's forecast of annualized growth has moved, each time it was asked` + (q.series.length < 2 ? " (once so far)" : "")
        : "Panel forecast of annualized growth, with the five-year growth record behind it"))),
    state.split ? h("div", { class: "stats" }, SCEN.map(sc => h("div", { class: "stat" },
      h("div", { class: "k" }, h("i", { class: "sw dot", style: `color: ${sc.color}; margin-right: 7px` }), sc.label),
      h("div", { class: "v mono" }, fmt(q, val(q, hz, sc.id)), h("small", {}, "per year")))))
    : h("div", { class: "stats" },
      h("div", { class: "stat" }, h("div", { class: "k" }, "Latest panel median, annualized"), h("div", { class: "v big mono" }, fmt(q, v), h("small", {}, "per year"))),
      p10 != null && h("div", { class: "stat" }, h("div", { class: "k" }, "80% range"), h("div", { class: "v mono" }, `${fmt(q, p10)} to ${fmt(q, p90)}`)),
      delta != null
        ? h("div", { class: "stat" }, h("div", { class: "k" }, `Change since ${first.date}`), h("div", { class: "v mono " + (delta >= 0 ? "up" : "down") }, `${delta >= 0 ? "+" : "−"}${Math.abs(delta).toFixed(2)} pp`))
        : h("div", { class: "stat" }, h("div", { class: "k" }, "First asked"), h("div", { class: "v mono" }, first ? first.date : "–"))),
    controls("hero"), legend(q.uncertainty && "Unconditional 80% range", history), chartBox(q, "hero"),
    h("div", { class: "well" },
      h("p", { class: "eyebrow" }, "The question"),
      h("p", {}, `${q.stem} ${q.horizons.find(z => z.id === hz).text} Each point is the annualized change over the five years before it, so every forecast is a later point on the same line. The survey asks about 2030 and 2050; the nearer dates are FRI's additions. When the record reaches a date, its forecast stays on the chart as a ring beside the outcome.`),
      h("hr"),
      h("p", { class: "eyebrow" }, "Scenarios"),
      h("p", {}, "AI progress is one of three descriptions of what AI can do by the end of 2030: slow, moderate or rapid. A scenario holds if a panel of experts asked then would most often pick it."
        + (probs ? ` The models put the chances at ${Math.round(probs.slow)}% slow, ${Math.round(probs.moderate)}% moderate and ${Math.round(probs.rapid)}% rapid.` : ""))),
    outcomes(q) && keep("out:" + q.id, "Forecasts against outcomes", outcomes(q)), rationale(q, hz), definition(q));
}

function tile(q) {
  const hz = horizonOf(q), v = val(q, hz, "unconditional"), p10 = val(q, hz, "unconditional", "p10"), p90 = val(q, hz, "unconditional", "p90");
  return h("div", { class: "tile" },
    h("div", { class: "cat" }, q.category), h("h3", {}, q.short),
    state.split
      ? h("div", { class: "num chips mono" }, SCEN.map(sc => h("span", { title: sc.label }, h("i", { class: "sw dot", style: `color: ${sc.color}` }), h("b", {}, fmt(q, val(q, hz, sc.id))))), h("span", {}, `${unitWord(q)} in ${hz}`))
      : h("div", { class: "num mono" }, h("b", {}, fmt(q, v)), ` ${unitWord(q)} in ${hz}`, p10 != null && ` · 80%: ${fmt(q, p10, true)} to ${fmt(q, p90, true)}`),
    chartBox(q, "mini"),
    outcomes(q) && more(q, "Forecasts against outcomes", () => outcomes(q)),
    more(q, "Model forecasts and rationale", () => [q.horizons.map(z => modelTable(q, z.id)), rationales(q)]),
    more(q, "Question and definition", () => defined(q)));
}

function progress() {
  const p = D.part1; if (!p) return null;
  const sp = p.scenario_probabilities, e = sp.ensemble;
  const pct = x => x == null ? "–" : Math.round(x) + "%";
  return h("section", { class: "card" }, h("h2", {}, "AI progress by 2030"),
    h("p", { class: "sub" }, "How likely the models think each scenario is, and two capability milestones"),
    e && h("div", { class: "bar", role: "img", "aria-label": `Slow ${pct(e.slow)}, moderate ${pct(e.moderate)}, rapid ${pct(e.rapid)}` },
      SCEN.map(sc => h("div", { style: `flex: ${e[sc.id]} 0 0; background: ${sc.color}`, title: `${sc.label}: ${pct(e[sc.id])}` }))),
    e && h("div", { class: "legend" }, SCEN.map(sc => h("span", {}, h("i", { class: "sw dot", style: `color: ${sc.color}` }), `${sc.label} ${pct(e[sc.id])}`))),
    h("div", { class: "scroll", style: "margin-top: 14px" }, h("table", { class: "tv" },
      h("thead", {}, h("tr", {}, h("th", {}, "Probability"), h("th", {}, "Panel median"), D.latest.models.map(mo => h("th", {}, mo)))),
      h("tbody", {},
        SCEN.map(sc => h("tr", {}, h("td", {}, sc.label), h("td", { class: "mono" }, pct(e && e[sc.id])), D.latest.models.map(mo => h("td", { class: "mono" }, pct((sp.models[mo] || {})[sc.id]))))),
        [["household_robot", "A household robot does four of five chores reliably"], ["reliability", "Frontier AI needs minimal oversight for most tasks"]].map(([id, text]) =>
          h("tr", {}, h("td", {}, text), h("td", { class: "mono" }, pct(p[id].ensemble)), D.latest.models.map(mo => h("td", { class: "mono" }, pct(p[id].models[mo])))))))));
}

function download() {
  return D.download && h("a", { class: "dl", href: D.download, download: D.download,
    title: "Everything: forecasts.csv, rationales.csv, the AI progress answers, the questions, the history, and the run files with every search and page read" },
    "⤓ Download data");
}

function render() {
  charts.length = 0;
  // Hold the page's height while it is rebuilt: a chart measures its box as it
  // is drawn, and a page that is briefly shorter would lose its scroll position.
  root.style.minHeight = root.offsetHeight + "px";
  root.classList.remove("still");
  const gdp = D.questions.find(q => q.id === "gdp"), rest = D.questions.filter(q => q.id !== "gdp");
  const L = D.latest;
  // replaceChildren would print a `false` as text, so the absent sections are filtered out.
  root.replaceChildren(...[
    h("header", {},
      h("div", { class: "top" },
        h("a", { href: "https://forecastingresearch.org", title: "Forecasting Research Institute" }, h("img", { class: "brand-logo", src: "web/img/fri-logo.svg", alt: "Forecasting Research Institute", width: 231, height: 37 })),
        download()),
      h("h1", {}, "EEAI (Economic Effects of AI)"),
      h("p", { class: "lede" }, "A panel of frontier AI models takes FRI's Economic Effects of AI survey: where the US economy is heading by 2030 and 2050, and how that depends on how fast AI improves."),
      L && h("p", { class: "meta" }, `Latest run ${L.date} · ${L.models.join(", ")} · each model searches the web before answering`),
      D.synthetic && h("div", { class: "banner", role: "status" }, h("b", {}, "Placeholder data. "), "These numbers are made up to show the layout. No model has been asked yet.")),
    !L && h("section", { class: "card" }, h("h2", {}, "No forecasts yet"), h("p", { class: "empty" }, "The panel has not been asked. The questions are ready; the first run will fill this page.")),
    L && gdp && hero(gdp),
    L && h("section", { class: "card" }, h("h2", {}, "The other indicators"),
      h("p", { class: "sub" }, `The survey's 14 other questions. Each panel has its own scale; ` + (historyOf.has("grid")
        ? `the line is the panel's forecast for ${state.horizon}, each time it was asked.`
        : `the line is the record, the dots are the panel's medians for each date asked, out to ${state.horizon}.`)),
      controls("grid"), legend("80% range, where the survey asks for one", historyOf.has("grid")), h("div", { class: "grid" }, rest.map(tile))),
    L && progress(),
    D.download && h("section", { class: "card" }, h("div", { class: "head" },
      h("div", {}, h("h2", {}, "Download data"),
        h("p", { class: "sub", style: "color: var(--ink-soft); margin: 4px 0 0; max-width: 640px" }, "Every forecast from every model in every run, each model's rationale, the questions, and the run files with every search and page read.")),
      download())),
    h("footer", {}, "Questions and scenario definitions are from the Forecasting Research Institute's Economic Effects of AI survey. ",
      "The panel is the four highest-ranked models on Epoch's Capabilities Index that FRI can run, one per model family. ",
      "Forecasts are not yet scored against outcomes.")].filter(Boolean));
  for (const draw of charts) draw();
  root.style.minHeight = "";
}
let timer;
// (a resize redraws the charts where they stand: "still", so the forecasts do not fade in again)
window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(() => { root.classList.add("still"); charts.forEach(d => d()); }, 120); });
render();
