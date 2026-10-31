// Pure logic for the Project Fleet control room (no DOM). Inlined into control.html by build_control.py.
(function () {
  'use strict';
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

  // A skipped project (the refresh fetched nothing) is not an access problem: show its reason as written.
  function notConnectedText(repo, reason) {
    var r = typeof reason === 'string' ? reason : '';
    if (/^No data was fetched/.test(r)) return 'Not connected — ' + r;
    return 'Not connected — grant the Claude GitHub app access to ' + repo + (r ? ' (' + r + ')' : '');
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

  // db docs (snapshot.docs) -> project rows. d.data() is frozen: copy, never mutate it.
  function projectRows(docs) {
    return (docs || []).map(function (d) { return Object.assign({}, d.data(), { id: d.id }); });
  }

  // db docs of the snapshot collection -> {snaps: {name: doc}, meta}. Docs are kept as-is (read-only).
  function snapshotState(docs) {
    var snaps = {}, meta = null;
    (docs || []).forEach(function (d) {
      if (d.id === '_meta') meta = d.data() || null;
      else snaps[d.id] = d.data() || {};
    });
    return { snaps: snaps, meta: meta };
  }

  // Waiting rows across active projects, oldest first.
  // "Ready to merge" rows (internal PRs) are left out on purpose: they wait on the orchestrator, not the owner.
  function waitingAll(cards) {
    var rows = [];
    (cards || []).forEach(function (c) {
      if (c.snap && c.snap.connected !== false && Array.isArray(c.snap.waiting)) {
        c.snap.waiting.forEach(function (w) { if (w.why !== 'Ready to merge') rows.push(w); });
      }
    });
    return sortWaiting(rows);
  }

  // ================= PR 2: add / archive projects =================
  var REPO_RE = /^[\w.-]+\/[\w.-]+$/;

  // form: {name, repo, blurb, allOpenPrsWait}; existing: names already in projects/.
  // Returns {ok, errors: {field: message}, doc}. now/addedBy are passed in so this stays pure.
  function validateProjectForm(form, existing, now, addedBy) {
    var f = form || {}, errors = {};
    var name = String(f.name == null ? '' : f.name).trim();
    var repo = String(f.repo == null ? '' : f.repo).trim();
    var blurb = String(f.blurb == null ? '' : f.blurb).trim();
    if (!NAME_RE.test(name)) errors.name = 'Use lowercase letters, digits and dashes only (a-z, 0-9, -).';
    else if ((existing || []).indexOf(name) >= 0) errors.name = 'A project called ' + name + ' already exists (it may be archived).';
    if (!REPO_RE.test(repo)) errors.repo = 'Use the form owner/repo, for example salmankhaliq22/resd.';
    if (blurb.length > 200) errors.blurb = 'Keep the description under 200 characters.';
    if (Object.keys(errors).length) return { ok: false, errors: errors, doc: null };
    return {
      ok: true, errors: {}, name: name,
      doc: {
        repo: repo, blurb: blurb, archived: false, all_open_prs_wait: !!f.allOpenPrsWait,
        added_at: new Date(now == null ? Date.now() : now).toISOString(), added_by: addedBy || 'owner'
      }
    };
  }

  function writeErrorText(err) {
    var code = err && err.code;
    if (code === 'not_granted' || code === 'revoked') return 'Only the owner can change projects. The database refused the change.';
    if (code === 'unavailable') return 'The database is not reachable right now. Try again in a moment.';
    if (code === 'quota_exceeded' || code === 'resource_exhausted') return 'The database is full or busy. Try again later.';
    return 'The change was not saved' + (err && err.message ? ' (' + String(err.message).slice(0, 120) + ')' : '') + '.';
  }

  // ================= PR 2: Claude Code Remote sessions =================
  var SERVER = 'Claude Code Remote';
  var SESSION_ID_RE = /^session_[A-Za-z0-9]+$/;
  var DAY = 86400000;
  var BUCKETS = {
    SESSION_STATUS_BUCKET_WORKING: 'Working', SESSION_STATUS_BUCKET_BLOCKED: 'Blocked',
    SESSION_STATUS_BUCKET_REVIEW_READY: 'Review ready', SESSION_STATUS_BUCKET_COMPLETED: 'Completed',
    SESSION_STATUS_BUCKET_FAILED: 'Failed'
  };

  // A tool result -> its JSON object. Handles: CallToolResult (payload / structuredContent / text blocks),
  // a bare text-block array, a JSON string, and a {ccr: {...}} wrapper.
  function unwrapPayload(res) {
    var v = res, i, guard = 0;
    while (guard++ < 5) {
      if (v == null) return null;
      if (typeof v === 'string') { try { v = JSON.parse(v); continue; } catch (e) { return null; } }
      if (Array.isArray(v)) {
        var txt = null;
        for (i = 0; i < v.length; i++) if (v[i] && v[i].type === 'text' && typeof v[i].text === 'string') { txt = v[i].text; break; }
        if (txt === null) return null;
        v = txt; continue;
      }
      if (typeof v !== 'object') return null;
      if (v.payload !== undefined && v.payload !== null) { v = v.payload; continue; }
      if (v.structuredContent !== undefined && v.structuredContent !== null) { v = v.structuredContent; continue; }
      if (Array.isArray(v.content) && v.data === undefined && v.repos === undefined && v.id === undefined) { v = v.content; continue; }
      if (v.ccr !== undefined && v.ccr !== null && typeof v.ccr === 'object') { v = v.ccr; continue; }
      return v;
    }
    return null;
  }

  // Lowercase, drop https://github.com/ prefix, trailing .git and slashes -> "owner/repo".
  function normRepo(s) {
    if (typeof s !== 'string') return '';
    return s.trim().toLowerCase().replace(/^https?:\/\/(www\.)?github\.com\//, '').replace(/\/+$/, '').replace(/\.git$/, '').replace(/\/+$/, '');
  }

  function bucketLabel(b) { return BUCKETS[b] || 'Unknown'; }
  function bucketClass(b) {
    return b === 'SESSION_STATUS_BUCKET_WORKING' ? 'ok' : b === 'SESSION_STATUS_BUCKET_BLOCKED' ? 'warn'
      : b === 'SESSION_STATUS_BUCKET_FAILED' ? 'bad' : 'muted';
  }

  // list_sessions payload -> the sessions worth a get_session: not archived, not completed-and-old, newest 20.
  function pickSessions(payload, now, cap) {
    var rows = payload && Array.isArray(payload.data) ? payload.data : [];
    var max = cap == null ? 20 : cap, t = now == null ? Date.now() : now;
    var keep = rows.filter(function (s) {
      if (!s || typeof s.id !== 'string') return false;
      if (s.session_status === 'SESSION_STATUS_ARCHIVED') return false;
      if (s.status_bucket === 'SESSION_STATUS_BUCKET_COMPLETED') {
        var u = time(s.updated_at);
        if (u === null || t - u > 7 * DAY) return false;
      }
      return true;
    });
    keep.sort(function (a, b) { return (time(b.updated_at) || 0) - (time(a.updated_at) || 0); });
    return { picked: keep.slice(0, max), skippedByCap: Math.max(0, keep.length - max) };
  }

  // get_session payload -> {id, title, bucket, updated_at, repos: [normalised], branches: {repo: branch}}
  function sessionInfo(d, listRow) {
    var o = d || {}, row = listRow || {};
    var repos = [], branches = {};
    var ctx = o.session_context || {};
    (Array.isArray(ctx.sources) ? ctx.sources : []).forEach(function (src) {
      var g = src && src.git_repository;
      var r = g && normRepo(g.url);
      if (r && repos.indexOf(r) < 0) repos.push(r);
    });
    var cb = (o.external_metadata || {}).current_branches;
    if (cb && typeof cb === 'object') Object.keys(cb).forEach(function (k) { if (typeof cb[k] === 'string') branches[normRepo(k)] = cb[k]; });
    return {
      id: o.id || row.id, title: o.title || row.title || '',
      bucket: o.status_bucket || row.status_bucket || '', updated_at: o.updated_at || row.updated_at || '',
      repos: repos, branches: branches
    };
  }

  // infos: sessionInfo[]; projects: [{name, repo}] (active). -> {byProject: {name: [info+branch]}, other: [info]}
  function groupSessions(infos, projects) {
    var byRepo = {}, byProject = {}, other = [];
    (projects || []).forEach(function (p) { byRepo[normRepo(p.repo)] = p.name; byProject[p.name] = []; });
    (infos || []).forEach(function (s) {
      var hit = false;
      s.repos.forEach(function (r) {
        if (byRepo[r]) { hit = true; byProject[byRepo[r]].push(Object.assign({}, s, { branch: s.branches[r] || '' })); }
      });
      if (!hit) other.push(s);
    });
    Object.keys(byProject).forEach(function (k) { byProject[k].sort(function (a, b) { return (time(b.updated_at) || 0) - (time(a.updated_at) || 0); }); });
    other.sort(function (a, b) { return (time(b.updated_at) || 0) - (time(a.updated_at) || 0); });
    return { byProject: byProject, other: other };
  }

  function sessionHref(id) {
    return typeof id === 'string' && SESSION_ID_RE.test(id) ? safeHref('https://claude.ai/code/' + id) : null;
  }

  // list_repos payload -> sorted unique full_names matching REPO_RE.
  function repoNames(payload) {
    var rows = payload && Array.isArray(payload.repos) ? payload.repos : [], seen = {}, out = [];
    rows.forEach(function (r) {
      var n = r && r.full_name;
      if (typeof n === 'string' && REPO_RE.test(n) && !seen[n]) { seen[n] = 1; out.push(n); }
    });
    return out.sort(function (a, b) { return a.toLowerCase().localeCompare(b.toLowerCase()); });
  }

  // McpError -> plain sentence, branched on code (never on message text).
  function mcpErrorText(err) {
    var c = err && err.code;
    if (c === 'needs_reauth') return 'The Claude Code Remote connector needs you to sign in again (claude.ai, Settings, Connectors).';
    if (c === 'server_not_connected' || c === 'server_not_found' || c === 'not_in_manifest') return 'The Claude Code Remote connector is not connected for you. Add it in claude.ai, Settings, Connectors.';
    if (c === 'not_granted' || c === 'consent_required' || c === 'blocked_by_policy' || c === 'approval_required' || c === 'capability_disabled' || c === 'capability_removed') return 'Access to the Claude Code Remote connector was not allowed, so live sessions are not shown.';
    if (c === 'rate_limited') return 'The connector is busy. Try “Refresh sessions” in a minute.';
    if (c === 'server_unavailable' || c === 'upstream_error') return 'The Claude Code Remote connector is not reachable right now. Try “Refresh sessions” later.';
    return 'Live sessions could not be loaded. Try “Refresh sessions”.';
  }

  var L = {
    safeHref: safeHref, parseHash: parseHash, truncate: truncate, sortWaiting: sortWaiting,
    sortPrs: sortPrs, isStale: isStale, conflictsLabel: conflictsLabel, showingLabel: showingLabel,
    sizeLabel: sizeLabel, ageLabel: ageLabel, notConnectedText: notConnectedText,
    groupProjects: groupProjects, totals: totals, waitingAll: waitingAll,
    projectRows: projectRows, snapshotState: snapshotState,
    validateProjectForm: validateProjectForm, writeErrorText: writeErrorText, SERVER: SERVER,
    unwrapPayload: unwrapPayload, normRepo: normRepo, bucketLabel: bucketLabel, bucketClass: bucketClass,
    pickSessions: pickSessions, sessionInfo: sessionInfo, groupSessions: groupSessions,
    sessionHref: sessionHref, repoNames: repoNames, mcpErrorText: mcpErrorText
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = L;
  if (typeof window !== 'undefined') window.FleetLogic = L;
})();
