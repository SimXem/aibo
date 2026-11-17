// Capture real dashboard UI for the manuscript, without changing its styling.
// Set PLAYWRIGHT_MODULE to an installed Playwright package if it is not local.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { isDeepStrictEqual } = require('node:util');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const out = path.join(root, 'paper', 'screenshots');
const input = path.join(root, 'index.html');
const viewport = { width: 1000, height: 1800 };
const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const load = name => JSON.parse(fs.readFileSync(path.join(root, 'results', name), 'utf8'));

async function settled(page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
}

async function panelRect(heading) {
  return heading.evaluate(el => {
    let panel = el.parentElement;
    while (panel && panel.style.borderRadius !== '14px') panel = panel.parentElement;
    if (!panel) throw new Error('Dashboard panel not found');
    const r = panel.getBoundingClientRect();
    const svg = [...panel.querySelectorAll('svg')].find(el => el.getBoundingClientRect().width > 500);
    if (!svg) throw new Error('Chart SVG not found');
    return { x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height,
      chartBottom: svg.getBoundingClientRect().bottom + scrollY };
  });
}

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  try {
    const page = await browser.newPage({ viewport, deviceScaleFactor: 3 });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(pathToFileURL(input).href);
    const title = page.getByRole('heading', { name: 'Probability of an AI catastrophe', exact: true });
    await title.waitFor();
    await settled(page);
    const data = await page.evaluate(() => ({
      headline: window.__GRAPH1__, timeline: window.__TIMELINE__, capability: window.__CAPABILITY__
    }));
    // Refuse a stale assembled page: its displayed numbers must match the
    // tracked blobs used to generate the paper's figures and numbers.tex.
    for (const [key, file] of [['headline', 'graph1_data.json'],
      ['timeline', 'timeline_data.json'], ['capability', 'capability_data.json']]) {
      assert.ok(isDeepStrictEqual(data[key], load(file)),
        `Assembled dashboard differs from results/${file}; rebuild it before capture.`);
    }

    const forecast = await panelRect(title);
    const tabs = await page.getByRole('button', { name: 'Forecasts', exact: true }).boundingBox();
    const forecastClip = { x: forecast.x, y: tabs.y - 6, width: forecast.width,
      height: forecast.chartBottom + 10 - (tabs.y - 6) };
    await page.screenshot({ path: path.join(out, 'forecast-history.png'),
      clip: forecastClip, animations: 'disabled' });

    await page.getByRole('button', { name: 'Capability', exact: true }).click();
    const capabilityTitle = page.getByRole('heading', { name: 'How models forecast frontier capability', exact: true });
    await capabilityTitle.waitFor();
    await settled(page);
    const { chartBottom, ...capabilityClip } = await panelRect(capabilityTitle);
    await page.screenshot({ path: path.join(out, 'frontier-capability.png'),
      clip: capabilityClip, animations: 'disabled' });
    assert.deepEqual(errors, []);
    const variant = data.capability.variants.find(v => v.key === data.capability.defaultVariant);
    const manifest = {
      capturedAt: new Date().toISOString(), source: 'Local assembled AIRO dashboard (index.html)',
      sourceSha256: sha(input), viewport, deviceScaleFactor: 3,
      forecastHorizon: '2030', timelineSnapshots: data.timeline.snapshots,
      capabilityTarget: variant.targetDate, capabilityRuns: variant.runs,
      files: [
        { file: 'forecast-history.png', clip: forecastClip },
        { file: 'frontier-capability.png', clip: capabilityClip }
      ].map(x => ({ ...x, sha256: sha(path.join(out, x.file)) }))
    };
    fs.writeFileSync(path.join(out, 'capture.json'), JSON.stringify(manifest, null, 2) + '\n');
    console.log('Captured two dashboard views; all three data blobs match the paper inputs.');
    console.log(JSON.stringify({ forecastClip, capabilityClip, capabilityTarget: variant.targetDate }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
