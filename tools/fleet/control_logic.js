// Pure logic for the Project Fleet control room (no DOM). Inlined into control.html by build_control.py.
(function () {
  var NAME_RE = /^[a-z0-9-]+$/;
  var SAFE_PREFIXES = ['https://github.com/', 'https://claude.ai/code/'];

  // Returns the url only if it is a GitHub or claude.ai/code https link; otherwise null (show as text).
  function safeHref(url) {
    if (typeof url !== 'string') return null;
    if (/[\s\\\u0000-\u001f\u007f]/.test(url)) return null;
    for (var i = 0; i < SAFE_PREFIXES.length; i++) {
      if (url.indexOf(SAFE_PREFIXES[i]) === 0 && url.length > SAFE_PREFIXES[i].length) return url;
    }
    return null;
  }

  function parseHash(hash) {
    var m = /^#p-([a-z0-9-]+)$/.exec(String(hash || ''));
    return m ? m[1] : null;
  }

  function num(v) { var n = Number(v); return isFinite(n) ? n : 0; }
  function time(s) { var t = Date.parse(s); return isNaN(t) ? null : t; }

  // Cut text at n characters. Returns {text, truncated}.
  function truncate(text, n) {
    var s = typeof text === 'string' ? text : '';
    if (s.length <= n) return { text: s, truncated: false };
    return { text: s.slice(0, n), truncated: true };
  }

  // Oldest first (the thing waiting longest at the top); ties by key.
  function sortWaiting(rows) {
    return (rows || []).slice().sort(function (a, b) {
      return (num(b.age_days) - num(a.age_days)) || String(a.key).localeCompare(String(b.key));
    });
  }

  // PRs the owner must act on first, then oldest first.
  function sortPrs(prs) {
    return (prs || []).slice().sort(function (a, b) {
      var wa = a.why ? 0 : 1, wb = b.why ? 0 : 1;
      return (wa - wb) || (num(b.age_days) - num(a.age_days)) || (num(a.number) - num(b.number));
    });
  }

  function isStale(doc, meta) {
    if (!doc || !meta) return false;
    var m = time(meta.updated_at);
    if (m === null) return false;
    var d = time(doc.updated_at);
    return d === null || d < m;
  }

  function conflictsLabel(state) { return state === 'dirty' ? 'Has conflicts' : ''; }

  // "showing 30 of 45" only when the list was capped.
  function showingLabel(shown, total) {
    return num(total) > num(shown) ? 'showing ' + shown + ' of ' + total : '';
  }

  function sizeLabel(pr) {
    if (!pr || pr.additions === '' || pr.deletions === '' || pr.additions == null || pr.deletions == null) return '';
    return '+' + pr.additions + ' / −' + pr.deletions;
  }

  function ageLabel(days) {
    var d = num(days);
    if (d < 1) return 'today';
    var r = Math.floor(d);
    return r + (r === 1 ? ' day' : ' days');
  }

  function notConnectedText(repo) {
    return 'Not connected — grant the Claude GitHub app access to ' + repo;
  }

  // Join project docs with snapshot docs. projects: [{id, ...data}], snaps: {name: doc}.
  function groupProjects(projects, snaps, meta) {
    var active = [], archived = [];
    (projects || []).slice().sort(function (a, b) { return String(a.id).localeCompare(String(b.id)); }).forEach(function (p) {
      if (!NAME_RE.test(String(p.id))) return;
      var s = (snaps || {})[p.id] || null;
      var card = {
        name: p.id, repo: p.repo || '', blurb: p.blurb || '', project: p, snap: s,
        waitingFirst: !s,
        stale: !!s && isStale(s, meta),
        notConnected: !!s && s.connected === false
      };
      (p.archived ? archived : active).push(card);
    });
    return { active: active, archived: archived };
  }

  function totals(cards) {
    var t = { projects: 0, waiting: 0, openPrs: 0, openIssues: 0, merged7d: 0 };
    (cards || []).forEach(function (c) {
      t.projects++;
      if (!c.snap) return;
      t.waiting += num(c.snap.waiting_on_you);
      t.openPrs += num(c.snap.open_pr_count);
      t.openIssues += num(c.snap.open_issue_count);
      t.merged7d += num(c.snap.merged_7d);
    });
    return t;
  }

  // Waiting rows across active projects, oldest first.
  function waitingAll(cards) {
    var rows = [];
    (cards || []).forEach(function (c) {
      if (c.snap && Array.isArray(c.snap.waiting)) {
        c.snap.waiting.forEach(function (w) { if (w.why !== 'Ready to merge') rows.push(w); });
      }
    });
    return sortWaiting(rows);
  }

  var L = {
    safeHref: safeHref, parseHash: parseHash, truncate: truncate, sortWaiting: sortWaiting,
    sortPrs: sortPrs, isStale: isStale, conflictsLabel: conflictsLabel, showingLabel: showingLabel,
    sizeLabel: sizeLabel, ageLabel: ageLabel, notConnectedText: notConnectedText,
    groupProjects: groupProjects, totals: totals, waitingAll: waitingAll
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = L;
  if (typeof window !== 'undefined') window.FleetLogic = L;
})();
