// Server-render a page's <App/> per tab, with the React and Babel builds the
// page itself loads, to check it renders and (DUMP) to compare two renders.
//   node ssr.js <dl dir> <page.html> [tab ...]      a tab may carry params: "conditional&prompt=critical"
// <dl dir> holds, downloaded from unpkg.com: @babel/standalone@7.29.0/babel.min.js,
// react@18.3.1/umd/react.development.js and
// react-dom@18.3.1/umd/react-dom-server-legacy.browser.development.js.
// PROBES="a|b" lists strings to look for in the text; TEXT=n prints the first n
// characters of text; DUMP=prefix writes <prefix>-<tab>.html.
const fs = require("fs"), vm = require("vm"), path = require("path");
const [dl, page, ...tabs] = process.argv.slice(2);
const html = fs.readFileSync(page, "utf8");
const run = (ctx, file) => vm.runInContext(fs.readFileSync(path.join(dl, file), "utf8"), ctx, { filename: file });
for (const tab of tabs.length ? tabs : ["forecasts"]) {
  const ctx = vm.createContext({ console, URLSearchParams, TextEncoder, TextDecoder, Intl, setTimeout, clearTimeout,
                                 location: { search: "?tab=" + tab } });
  ctx.window = ctx; ctx.self = ctx; ctx.globalThis = ctx; ctx.window.location = ctx.location;
  run(ctx, "react.development.js");
  run(ctx, "react-dom-server-legacy.browser.development.js");
  run(ctx, "babel.min.js");
  for (const m of html.matchAll(/<script>(window\.__[A-Z0-9]+__ = [\s\S]*?);<\/script>/g)) vm.runInContext(m[1], ctx);
  let src = html.match(/<script type="text\/babel">([\s\S]*)<\/script>/)[1];
  src = src.replace(/ReactDOM\.createRoot\(document\.getElementById\("root"\)\)\.render\(<App \/>\);/,
                    "globalThis.__out = ReactDOMServer.renderToString(<App />);");
  vm.runInContext(ctx.Babel.transform(src, { presets: ["react"] }).code, ctx, { filename: "page.jsx" });
  const out = ctx.__out.replace(/<!-- -->/g, "");
  const text = out.replace(/<style[^]*?<\/style>/g, "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  console.log(`== ${tab}: ${out.length} chars`);
  if (process.env.DUMP) fs.writeFileSync(process.env.DUMP + "-" + tab + ".html", out);
  if (process.env.TEXT) console.log(text.slice(0, +process.env.TEXT));
  for (const probe of (process.env.PROBES || "").split("|").filter(Boolean))
    console.log(`   ${text.includes(probe) ? "has" : "no "}  ${probe}`);
}
