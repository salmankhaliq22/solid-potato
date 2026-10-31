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

t('not connected text and waiting', () => {
  assert.strictEqual(L.notConnectedText('o/r', 'No data was fetched for this project (refresh skipped it)'),
    'Not connected — No data was fetched for this project (refresh skipped it)');
  assert.ok(!/grant/.test(L.notConnectedText('o/r', 'No data was fetched for x')));
  assert.strictEqual(L.notConnectedText('o/r', 'no access'), 'Not connected — grant the Claude GitHub app access to o/r (no access)');
  const projects = [{ id: 'a', repo: 'o/a' }, { id: 'b', repo: 'o/b' }];
  const w = { key: 'x#1', why: 'Needs OK', age_days: 1 };
  const snaps = { a: { connected: false, waiting: [w] }, b: { connected: true, waiting: [Object.assign({}, w, { key: 'y#1' })] } };
  const g = L.groupProjects(projects, snaps, null);
  assert.deepStrictEqual(L.waitingAll(g.active).map(x => x.key), ['y#1']);
});
t('validateProjectForm', () => {
  const ok = L.validateProjectForm({ name: 'my-proj', repo: 'o/r.x-1', blurb: ' hi ', allOpenPrsWait: true }, ['a'], Date.UTC(2026, 9, 31), 'u1');
  assert.ok(ok.ok);
  assert.strictEqual(ok.name, 'my-proj');
  assert.deepStrictEqual(ok.doc, { repo: 'o/r.x-1', blurb: 'hi', archived: false, all_open_prs_wait: true, added_at: '2026-10-31T00:00:00.000Z', added_by: 'u1' });
  assert.strictEqual(L.validateProjectForm({ name: 'a', repo: 'o/r' }, ['a']).errors.name.indexOf('already exists') >= 0, true);
  ['My', 'a b', '', 'a_b', 'a/b'].forEach(n => assert.ok(L.validateProjectForm({ name: n, repo: 'o/r' }, []).errors.name, n));
  ['', 'o', 'o/', '/r', 'o/r/x', 'o r/x', 'https://github.com/o/r'].forEach(r => assert.ok(L.validateProjectForm({ name: 'n', repo: r }, []).errors.repo, r));
  const d = L.validateProjectForm({ name: 'n', repo: 'o/r' }, [], 0).doc;
  assert.strictEqual(d.all_open_prs_wait, false);
  assert.strictEqual(d.added_by, 'owner');
  assert.strictEqual(L.writeErrorText({ code: 'not_granted' }).indexOf('owner') >= 0, true);
});
t('unwrapPayload', () => {
  const obj = { data: [{ id: 'session_a' }] };
  assert.deepStrictEqual(L.unwrapPayload(obj), obj);
  assert.deepStrictEqual(L.unwrapPayload({ ccr: obj }), obj);
  assert.deepStrictEqual(L.unwrapPayload({ payload: obj, content: [] }), obj);
  assert.deepStrictEqual(L.unwrapPayload({ payload: { ccr: obj } }), obj);
  assert.deepStrictEqual(L.unwrapPayload({ structuredContent: obj }), obj);
  assert.deepStrictEqual(L.unwrapPayload({ content: [{ type: 'text', text: JSON.stringify(obj) }] }), obj);
  assert.deepStrictEqual(L.unwrapPayload([{ type: 'text', text: JSON.stringify({ ccr: obj }) }]), obj);
  assert.deepStrictEqual(L.unwrapPayload({ payload: JSON.stringify(obj) }), obj);
  assert.strictEqual(L.unwrapPayload({ payload: 'not json' }), null);
  assert.strictEqual(L.unwrapPayload(null), null);
  assert.strictEqual(L.unwrapPayload([]), null);
});
t('normRepo', () => {
  assert.strictEqual(L.normRepo('https://github.com/Owner/Repo.git'), 'owner/repo');
  assert.strictEqual(L.normRepo('https://github.com/Owner/Repo'), 'owner/repo');
  assert.strictEqual(L.normRepo('Owner/Repo'), 'owner/repo');
  assert.strictEqual(L.normRepo('Owner/Repo.git/'), 'owner/repo');
  assert.strictEqual(L.normRepo(null), '');
});
const NOW = Date.parse('2026-10-31T12:00:00Z');
const B = 'SESSION_STATUS_BUCKET_';
function mk(id, bucket, updated, status) { return { id, title: id, session_status: status || 'SESSION_STATUS_IDLE', status_bucket: B + bucket, updated_at: updated }; }
t('pickSessions', () => {
  const rows = [
    mk('session_old', 'COMPLETED', '2026-10-20T00:00:00Z'),
    mk('session_recentdone', 'COMPLETED', '2026-10-28T00:00:00Z'),
    mk('session_arch', 'WORKING', '2026-10-31T00:00:00Z', 'SESSION_STATUS_ARCHIVED'),
    mk('session_oldwork', 'WORKING', '2026-09-01T00:00:00Z'),
    mk('session_new', 'WORKING', '2026-10-31T10:00:00Z')
  ];
  const r = L.pickSessions({ data: rows }, NOW);
  assert.deepStrictEqual(r.picked.map(s => s.id), ['session_new', 'session_recentdone', 'session_oldwork']);
  assert.strictEqual(L.pickSessions({ data: rows }, NOW, 1).skippedByCap, 2);
  assert.deepStrictEqual(L.pickSessions(null, NOW).picked, []);
  const many = [];
  for (let i = 0; i < 30; i++) many.push(mk('session_' + i, 'WORKING', new Date(NOW - i * 60000).toISOString()));
  const c = L.pickSessions({ data: many }, NOW);
  assert.strictEqual(c.picked.length, 20);
  assert.strictEqual(c.picked[0].id, 'session_0');
  assert.strictEqual(c.skippedByCap, 10);
});
t('sessions grouping and links', () => {
  const det = (id, url, branch, bucket) => ({ id, title: 't ' + id, status_bucket: B + bucket, updated_at: '2026-10-31T10:00:00Z',
    session_context: { sources: [{ git_repository: { url, revision: 'main' } }] },
    external_metadata: { current_branches: { 'salmankhaliq22/resd': branch } } });
  const infos = [
    L.sessionInfo(det('session_a', 'https://github.com/Salmankhaliq22/resd.git', 'feat-1', 'WORKING')),
    L.sessionInfo(det('session_b', 'https://github.com/other/thing', 'x', 'BLOCKED')),
    L.sessionInfo({ id: 'session_c', title: 'bare' }, { status_bucket: B + 'FAILED' })
  ];
  const g = L.groupSessions(infos, [{ name: 'resd', repo: 'salmankhaliq22/resd' }, { name: 'empty', repo: 'o/e' }]);
  assert.deepStrictEqual(g.byProject.resd.map(s => s.id), ['session_a']);
  assert.strictEqual(g.byProject.resd[0].branch, 'feat-1');
  assert.deepStrictEqual(g.byProject.empty, []);
  assert.deepStrictEqual(g.other.map(s => s.id).sort(), ['session_b', 'session_c']);
  assert.strictEqual(L.bucketLabel(B + 'REVIEW_READY'), 'Review ready');
  assert.strictEqual(L.bucketLabel('zzz'), 'Unknown');
  assert.strictEqual(L.sessionHref('session_AbC123'), 'https://claude.ai/code/session_AbC123');
  assert.strictEqual(L.sessionHref('session_a/../x'), null);
  assert.strictEqual(L.sessionHref('abc'), null);
  assert.strictEqual(L.sessionHref(undefined), null);
});
t('repoNames and mcpErrorText', () => {
  assert.deepStrictEqual(L.repoNames({ repos: [{ full_name: 'b/x' }, { full_name: 'A/y' }, { full_name: 'b/x' }, { full_name: 'bad' }, {}] }), ['A/y', 'b/x']);
  assert.deepStrictEqual(L.repoNames(null), []);
  assert.ok(/sign in again/.test(L.mcpErrorText({ code: 'needs_reauth' })));
  assert.ok(/not allowed/.test(L.mcpErrorText({ code: 'not_granted' })));
  assert.ok(/could not be loaded/.test(L.mcpErrorText(new Error('x'))));
});
console.log('control_logic: ' + n + ' test groups passed');
