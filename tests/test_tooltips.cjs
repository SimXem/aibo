// Run: node --test tests/test_tooltips.cjs (no npm dependencies).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

test('shared tooltip policy, SVG placement, updates and cleanup', () => {
  let options, shown = 0, destroyed = 0, updated = 0;
  const body = {};
  const effects = [];
  const refs = [];
  let cursor = 0;
  const context = vm.createContext({
    window: { tippy(target, opts) {
      options = opts;
      return { show() { shown++; }, destroy() { destroyed++; },
        popperInstance: { update() { updated++; } } };
    } },
    document: { body, createElement: () => ({}) },
    useState: init => [init()],
    React: {
      useRef(value) { const i = cursor++; return refs[i] || (refs[i] = { current: value }); },
      useLayoutEffect(effect) { effects.push(effect); },
    },
    ReactDOM: { createPortal: (children, content) => ({ children, content }) },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/shared/tooltips.jsx'), 'utf8'), context);
  context.appTooltip({}, { content: 'Legend' });
  assert.equal(options.theme, 'airo');
  assert.equal(options.placement, 'right');
  assert.equal(options.appendTo(), body);
  let scale = 0.5;
  const svg = {
    createSVGPoint: () => ({ x: 0, y: 0, matrixTransform(m) {
      return { x: this.x * m.scale + 100, y: this.y * m.scale + 300 };
    } }),
    getScreenCTM: () => ({ scale }),
  };
  const box = { current: { querySelector: () => svg } };
  const portal = context.PointTooltip({ box, x: 40, y: 80, children: 'Forecast' });
  assert.equal(portal.children, 'Forecast');
  const cleanup = effects[0]();
  effects[1]();
  assert.equal(shown, 1);
  assert.equal(options.getReferenceClientRect().left, 120);
  assert.equal(options.getReferenceClientRect().top, 340);
  // Same chart, new dimensions and point: callback must read the latest values.
  scale = 2;
  cursor = 0;
  context.PointTooltip({ box, x: 50, y: 100, children: 'Changed' });
  effects[3]();
  assert.equal(options.getReferenceClientRect().left, 200);
  assert.equal(options.getReferenceClientRect().top, 500);
  assert.equal(updated, 2);
  cleanup();
  assert.equal(destroyed, 1);
  cursor = 0;
  context.PointTooltip({ anchor: { getBoundingClientRect: () => ({ top: 900 }) } });
  const cleanupPinned = effects[4]();
  assert.equal(options.getReferenceClientRect().top, 900);
  cleanupPinned();
  assert.equal(destroyed, 2);
});

test('all app tooltip callers use the shared implementation', () => {
  const demo = path.join(__dirname, '../web/demo');
  for (const file of fs.readdirSync(demo).filter(name => name.endsWith('.jsx'))) {
    const source = fs.readFileSync(path.join(demo, file), 'utf8');
    assert.ok(!source.includes('window.tippy('), file);
    assert.ok(!source.includes('position: "absolute"'), file);
  }
});

test('timeline rejects shadow/unknown conditions in retained snapshots and aggregates', () => {
  const source = fs.readFileSync(path.join(__dirname, '../web/demo/19-live-timeline.jsx'), 'utf8')
    .split('/* ---------------- time-series chart ---------------- */')[0];
  const context = vm.createContext({ window: { __TIMELINE__: { variants: [{ id: 'ai-banned' }] } } });
  vm.runInContext(source, context);
  const values = v => ({ '2030': [v] });
  const answers = v => ({ '2030': [{ A: v, B: v + 2 }] });
  const q = { horizons: ['2030'], median: values(99), rerun: values(null),
    variants: { none: values(2), independent: values(4), 'ai-banned': values(99), 'future-shadow': values(88) },
    variantModels: { none: answers(1), independent: answers(3), 'ai-banned': answers(99), 'future-shadow': answers(88) },
    series: ['A', 'B'].map(label => ({ label, ps: values(99), draws: values([99]), lo: values(99), hi: values(99) })) };
  context.q = q;
  context.snapshots = [{ date: '2026-10-21' }];
  assert.equal(vm.runInContext('tlVariants(q, "2030", snapshots).map(v => v.id).join(",")', context), 'none,independent');
  const clean = vm.runInContext('tlPublicQuestion(q)', context);
  assert.equal(clean.median['2030'][0], 3); // median of public-only model means 2,4
  assert.equal(clean.series[0].ps['2030'][0], 2);
  assert.equal(clean.series[1].ps['2030'][0], 4);
  assert.equal(Object.keys(clean.variants).join(','), 'none,independent');
  assert.equal(Object.keys(clean.variantModels).join(','), 'none,independent');
  assert.equal(q.median['2030'][0], 99); // do not mutate the stored snapshot
  context.clean = clean;
  assert.equal(vm.runInContext('tlPublicQuestion(clean) === clean', context), true);
});
