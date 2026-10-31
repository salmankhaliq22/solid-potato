// Run: node tools/fleet/test_control_logic.js
const assert = require('assert');
const L = require('./control_logic.js');
let n = 0;
function t(name, fn) { fn(); n++; }

t('safeHref', () => {
  assert.strictEqual(L.safeHref('https://github.com/o/r/pull/1'), 'https://github.com/o/r/pull/1');
  assert.strictEqual(L.safeHref('https://claude.ai/code/session_abc'), 'https://claude.ai/code/session_abc');
  assert.strictEqual(L.safeHref('javascript:alert(1)'), null);
  assert.strictEqual(L.safeHref('http://github.com/o/r'), null);
  assert.strictEqual(L.safeHref('https://github.com.evil.com/x'), null);
  assert.strictEqual(L.safeHref('https://evil.com/https://github.com/'), null);
  assert.strictEqual(L.safeHref('https://github.com/a b'), null);
  assert.strictEqual(L.safeHref('https://github.com/\\@evil.com'), null);
  assert.strictEqual(L.safeHref(undefined), null);
  assert.strictEqual(L.safeHref('https://github.com/'), null);
});
t('conflicts', () => {
  assert.strictEqual(L.conflictsLabel('dirty'), 'Has conflicts');
  assert.strictEqual(L.conflictsLabel('unknown'), '');
  assert.strictEqual(L.conflictsLabel('clean'), '');
  assert.strictEqual(L.conflictsLabel(''), '');
});
t('stale', () => {
  const meta = { updated_at: '2026-10-31T12:00:00Z' };
  assert.strictEqual(L.isStale({ updated_at: '2026-10-30T12:00:00Z' }, meta), true);
  assert.strictEqual(L.isStale({ updated_at: '2026-10-31T12:00:00Z' }, meta), false);
  assert.strictEqual(L.isStale({ updated_at: '2026-10-31T12:00:01Z' }, meta), false);
  assert.strictEqual(L.isStale({}, meta), true);
  assert.strictEqual(L.isStale({ updated_at: '2026-10-30T12:00:00Z' }, null), false);
});
t('showing', () => {
  assert.strictEqual(L.showingLabel(30, 45), 'showing 30 of 45');
  assert.strictEqual(L.showingLabel(30, 30), '');
  assert.strictEqual(L.showingLabel(3, undefined), '');
});
t('truncate', () => {
  assert.deepStrictEqual(L.truncate('abc', 5), { text: 'abc', truncated: false });
  assert.deepStrictEqual(L.truncate('abcdef', 3), { text: 'abc', truncated: true });
  assert.deepStrictEqual(L.truncate(null, 3), { text: '', truncated: false });
});
t('sorting', () => {
  const w = L.sortWaiting([{ key: 'b', age_days: 1 }, { key: 'a', age_days: 5 }, { key: 'c', age_days: 5 }]);
  assert.deepStrictEqual(w.map(x => x.key), ['a', 'c', 'b']);
  const p = L.sortPrs([{ number: 1, age_days: 9 }, { number: 2, age_days: 1, why: 'x' }, { number: 3, age_days: 4, why: 'y' }]);
  assert.deepStrictEqual(p.map(x => x.number), [3, 2, 1]);
});
t('labels', () => {
  assert.strictEqual(L.sizeLabel({ additions: 7, deletions: 3 }), '+7 / −3');
  assert.strictEqual(L.sizeLabel({ additions: 0, deletions: 0 }), '+0 / −0');
  assert.strictEqual(L.sizeLabel({ additions: '', deletions: '' }), '');
  assert.strictEqual(L.sizeLabel({}), '');
  assert.strictEqual(L.ageLabel(0.4), 'today');
  assert.strictEqual(L.ageLabel(1.2), '1 day');
  assert.strictEqual(L.ageLabel(11), '11 days');
  assert.strictEqual(L.notConnectedText('o/r'), 'Not connected — grant the Claude GitHub app access to o/r');
});
t('hash', () => {
  assert.strictEqual(L.parseHash('#p-resd'), 'resd');
  assert.strictEqual(L.parseHash('#p-a-b1'), 'a-b1');
  assert.strictEqual(L.parseHash('#resd'), null);
  assert.strictEqual(L.parseHash('#p-Bad'), null);
  assert.strictEqual(L.parseHash(''), null);
});
t('grouping and totals', () => {
  const projects = [
    { id: 'b', repo: 'o/b', archived: true }, { id: 'a', repo: 'o/a', blurb: 'x' }, { id: 'c', repo: 'o/c' }, { id: 'Bad Name' }
  ];
  const meta = { updated_at: '2026-10-31T12:00:00Z' };
  const snaps = {
    a: { updated_at: '2026-10-30T00:00:00Z', waiting_on_you: 2, open_pr_count: 3, open_issue_count: 4, merged_7d: 1,
         waiting: [{ key: 'a#1', age_days: 3, why: 'Needs your decision' }, { key: 'a#2', age_days: 9, why: 'Ready to merge' }] },
    b: { updated_at: '2026-10-01T00:00:00Z' }
  };
  const g = L.groupProjects(projects, snaps, meta);
  assert.deepStrictEqual(g.active.map(c => c.name), ['a', 'c']);
  assert.deepStrictEqual(g.archived.map(c => c.name), ['b']);
  assert.strictEqual(g.active[0].stale, true);
  assert.strictEqual(g.active[1].waitingFirst, true);
  assert.strictEqual(g.archived[0].stale, true);
  const t = L.totals(g.active);
  assert.deepStrictEqual(t, { projects: 2, waiting: 2, openPrs: 3, openIssues: 4, merged7d: 1 });
  assert.deepStrictEqual(L.waitingAll(g.active).map(w => w.key), ['a#1']);
  const nc = L.groupProjects([{ id: 'a', repo: 'o/a' }], { a: { connected: false, updated_at: meta.updated_at } }, meta);
  assert.strictEqual(nc.active[0].notConnected, true);
  assert.strictEqual(nc.active[0].stale, false);
});
function deepFreeze(o) {
  if (o && typeof o === 'object') { Object.values(o).forEach(deepFreeze); Object.freeze(o); }
  return o;
}
function fdoc(id, data) { return Object.freeze({ id: id, data: () => data }); }
t('frozen db docs', () => {
  const pData = deepFreeze({ repo: 'o/a', blurb: 'x' });
  const rows = L.projectRows(Object.freeze([fdoc('a', pData), fdoc('b', undefined)]));
  assert.deepStrictEqual(rows, [{ repo: 'o/a', blurb: 'x', id: 'a' }, { id: 'b' }]);
  assert.strictEqual(pData.id, undefined);
  const meta = deepFreeze({ updated_at: '2026-10-31T12:00:00Z' });
  const snapA = deepFreeze({
    updated_at: '2026-10-30T00:00:00Z', waiting_on_you: 1, open_pr_count: 2, open_issue_count: 0, merged_7d: 0,
    open_prs: [{ number: 2, age_days: 1 }, { number: 1, age_days: 5, why: 'x' }],
    waiting: [{ key: 'a#2', age_days: 1, why: 'Needs your decision' }, { key: 'a#1', age_days: 5, why: 'Needs your decision' }]
  });
  const st = L.snapshotState(Object.freeze([fdoc('_meta', meta), fdoc('a', snapA), fdoc('z', null)]));
  assert.strictEqual(st.meta, meta);
  assert.deepStrictEqual(st.snaps.z, {});
  // the whole read path runs on frozen data without throwing (control_logic.js is strict mode)
  const g = L.groupProjects(Object.freeze(rows.map(r => Object.freeze(r))), st.snaps, st.meta);
  assert.strictEqual(g.active[0].stale, true);
  assert.deepStrictEqual(L.waitingAll(g.active).map(w => w.key), ['a#1', 'a#2']);
  assert.deepStrictEqual(L.sortPrs(snapA.open_prs).map(p => p.number), [1, 2]);
  assert.strictEqual(L.totals(g.active).openPrs, 2);
  assert.deepStrictEqual(L.projectRows(undefined), []);
  assert.deepStrictEqual(L.snapshotState(undefined), { snaps: {}, meta: null });
});
t('empty', () => {
  const g = L.groupProjects([], {}, null);
  assert.deepStrictEqual(g, { active: [], archived: [] });
  assert.strictEqual(L.totals([]).projects, 0);
});
console.log('control_logic: ' + n + ' test groups passed');
