# Spec: Fleet control room (dashboard v2)

Status: DRAFT. Merging this spec's PR is the owner's approval; no code starts before then.
Decisions: `docs/decisions/D-20261031T002337-dashboard-v2-add-archive-projects-and-a-.md`, `D-20261031T002337-dashboard-merge-opens-the-pr-on-github.md`, `D-20261031T001035-dashboard-refreshes-only-on-request.md`. Milestone: Fleet v2 (issues filled in after approval).

## Plan
Today the Project Fleet dashboard (v1, https://claude.ai/artifact/34vBev4QzzJYCR5746Grse) is a read-only snapshot. The owner asked for one place to run everything: add or archive projects, click a project (for example resd) to see its details and progress, read its open PRs, and merge them.

Approach: a new plain HTML artifact (not the Dashboard type, which cannot do custom navigation, buttons or capabilities). Its project list and PR/issue data live in the page's shared database (`db` capability). The page also asks the claude.ai "Claude Code Remote" connector (`mcp` capability) which Claude sessions are working on each project, live. GitHub data still comes from the orchestrator's refresh when the owner says "update the dashboard" (no schedule, owner decision). Merge is a button that opens the PR on GitHub, where the owner clicks Merge.

## Done means
- The owner opens the v2 page and sees one card per active project, totals, and a "waiting on you" list.
- Clicking a project card opens its project page; a back link returns to the overview.
- The project page shows every open PR with title, labels, why it waits, age, size (+/−) when known, and its description as plain text (cut at 4,000 characters, with "Read on GitHub").
- "Read on GitHub" and "Merge on GitHub" open the PR page in a new tab; "Merge on GitHub" shows only to the owner.
- Only the owner can add, archive or unarchive a project; for everyone else the buttons are hidden and the database refuses the write. A new project shows "Waiting for first refresh".
- Unarchiving shows the old snapshot marked "from <date> — say 'update the dashboard' to refresh".
- After "update the dashboard", archived projects are skipped and every active project shows fresh data and a "Data as of" time; a project whose data is older than the last refresh shows "Stale".
- A project the refresh cannot reach shows "Not connected — grant the Claude GitHub app access to <repo>".
- The Live sessions panel lists Claude sessions for that project with status, or says plainly why it cannot (connector denied). Sessions with no matching project are in a collapsed "Other sessions" list on the overview.
- A link is clickable only if it starts with `https://github.com/` or `https://claude.ai/code/`; anything else shows as plain text.
- All tests pass; a fresh reviewer gives PASS; the owner approves publishing.

## Views
**Overview.** Cards for active projects (name, blurb, status, waiting count, open PRs (`open_pr_count`), open issues (`open_issue_count`), merged this week, last activity, "Stale" or "Not connected" when true). Totals row. "Waiting on you" list across projects, oldest first. "Data as of <time>" line. "Other sessions" (collapsed). Archived projects in a collapsed list, each with Unarchive (owner only). "Add project" button (owner only).

**Project page** (one per project):
- Header: status, last activity, and from `.orchestrator/STATE.md` when present: stage, next step, blockers.
- Open PRs: title, labels, why waiting, age in days, size (+additions / −deletions; blank if unknown), description as plain text (4,000 characters, then "… Read on GitHub"). Buttons "Read on GitHub" and "Merge on GitHub" (both link to the PR page; Merge only for the owner). "Has conflicts" next to the button only when `mergeable_state` is `"dirty"`; nothing for `"unknown"` or any other value.
- Open issues: title, labels, age.
- When a list is capped, it says "showing 30 of N" (N from `open_pr_count` / `open_issue_count`).
- This week's activity: merged PRs and commits.
- Live sessions: each Claude session for this repo with a status pill (Working, Blocked, Review ready, Completed, Failed), title, branch, last updated, and a link to `https://claude.ai/code/<session_id>`.
- "Data as of" line, and an Archive button (owner only).

**Add project** (owner only): repo picker filled from the connector's `list_repos` when allowed, otherwise a text box for owner/repo; name; one-line blurb; checkbox "Every open PR needs my OK" (`all_open_prs_wait`). The page rejects a repo not matching `^[\w.-]+/[\w.-]+$` or a name not matching `^[a-z0-9-]+$`, and the builder skips such docs with a warning.

## Data model (page database)
| path | written by | contents |
|---|---|---|
| `projects/<name>` | owner only | `{repo, blurb, archived, all_open_prs_wait, added_at, added_by}`. The list of projects (replaces `tools/fleet/config.json`, which stays only as the one-time seed). |
| `snapshot/<name>` | owner only (the orchestrator refresh, acting as the owner) | v1 projects-row fields plus `updated_at`, `connected` (with `not_connected_reason` when false), `open_pr_count`, `open_issue_count`, `open_prs[]`, `open_issues[]`, `activity[]`, `waiting[]` (per-item rows as in v1 `waiting.json`: key, kind, number, title, url, label, why, age_days). |
| `snapshot/_meta` | owner only (the orchestrator refresh) | `{updated_at}` |

Access rules: both `projects/` and `snapshot/` are writable by the owner only (db rule write: `"owner"`); everyone who can open the page reads. Archive sets `archived: true`: the project is kept, hidden from the overview and totals, and the refresh skips it; its old snapshot doc is kept.

The builder stores `open_pr_count` and `open_issue_count` BEFORE capping; cards and totals use those counts. Caps per snapshot doc: 30 open PRs, 50 open issues, 40 activity rows, PR body 4,000 characters. The builder measures the UTF-8 JSON size of each doc and trims (activity, then issues, oldest first, then PR bodies to 1,000 characters) until it is under 240 KB. If still over, it drops PR bodies; if still over, it fails with an error naming the project, writes nothing for that project, and the other projects continue.

## Deliverables (two PRs)
### PR 1 = F1 + F2 + F3: builder, screens from snapshot, runbook
**F1 builder.** `build_fleet.py` gains `--projects <export.json>` (an ArtifactData list of `projects`; archived and invalid docs skipped) and writes one `snapshot/<name>` doc per project plus `_meta`. It REQUIRES `body`, `additions`, `deletions`, `mergeable_state` from the per-PR dump (`pr_<number>.json`); if absent, those fields are blank, never guessed. Applies the caps and the 240 KB trim. Size: about 150 lines with tests.
**Acceptance:** new tests in `tools/fleet/test_build_fleet.py` pass: archived skipped; invalid repo/name skipped; body truncation; counts stored before capping; a doc still too big after trims drops PR bodies, then fails naming the project while others are built; per-PR fields missing → blank; a worst case (200 PRs with 60,000-character bodies, 500 issues, 300 commits) stays under 240 KB; `waiting[]` matches v1 rows; `updated_at` set; old tests still pass.

**F2 screens.** New `tools/fleet/control.html`: overview and project page, read from `snapshot/` only. Declares `db` (write rule `"owner"` on `projects/` and `snapshot/`) and `user`. Link building, sorting, truncation and "Stale"/"Has conflicts" logic live in pure functions tested with node.
**Acceptance:** node tests pass, including: a `javascript:` URL and an `http://` URL get no href; "dirty" shows "Has conflicts" and "unknown" shows nothing; "Stale" when a doc's `updated_at` is older than `_meta.updated_at`. Page works with db empty (plain message, no blank screen).

**F3 runbook and migration.** Update `docs/runbooks/update-fleet-dashboard.md`:
1. ArtifactData list of `projects`; keep non-archived docs.
2. Each refresh is a fresh session, so run `add_repo` for EVERY kept doc on every refresh: on success set `connected: true`; on failure set `connected: false` with the reason (page shows "Not connected — grant the Claude GitHub app access to <repo>").
3. Dump as in v1, plus `pull_request_read` once per open PR (list results lack additions/deletions/mergeable_state — verified), saved as `pr_<number>.json` keeping body, additions, deletions, mergeable_state.
4. Build; write snapshot docs with ArtifactData batches (documented limit: at most 50 writes and 1 MiB per batch), each kept under about 900 KB (for example 3 docs of ≤ 240 KB per batch); write `_meta` last, in its own final batch.
Seed `projects/` once from `config.json` (5 projects; resd keeps `all_open_prs_wait`) and the runbook's description of `config.json` says it is now only the one-time seed (JSON has no comments). Once F3 merges, v1 is no longer refreshed and freezes at its last refresh.
**Acceptance:** after publishing (owner gate), one functional pass: `projects` has 5 docs, `snapshot` has 5 docs plus `_meta`, and the page shows them.

### PR 2 = F4: add/archive and live sessions
Add project, Archive and Unarchive (owner only; Unarchive shows the old snapshot with "from <date> — say 'update the dashboard' to refresh"). Adds `mcp` with only `list_sessions`, `get_session`, `list_repos`. Sessions: `list_sessions` (mine, limit 30); skip archived sessions; skip completed sessions last updated more than 7 days ago; `get_session` for at most the 20 newest left; match each to a project by repo, normalised (lowercase, trailing `.git` removed, `https://github.com/` prefix removed); unmatched ones go to "Other sessions". Session links only for ids matching `^session_[A-Za-z0-9]+$`. Size: about 250 lines with tests.
**Acceptance:** node tests pass, including repo matching (`https://github.com/Owner/Repo.git` matches `owner/repo`), the 7-day skip and the 20-session cap; the page's declared db rules contain write `"owner"` for `projects/` and `snapshot/`; page works with the connector denied (plain message). Manual check in the functional pass: an ArtifactData write to `projects/` with `as_level: "interact"` is refused (a write the rules refuse at a lowered level "reads as not found"); if that cannot be observed, report UNCONFIRMED.

## Order
PR 1 first, then PR 2. Never two builders on the same files. Each PR over about 400 lines says so and suggests a split.

## Safety
- No secrets or tokens in the database.
- Data values are shown with `textContent` only (never as HTML), so a PR description cannot run code in the page. Links get an href only for `https://github.com/` or `https://claude.ai/code/` URLs; repo and name are validated as above.
- Both `projects/` and `snapshot/` are writable by the owner only (db rule write: `"owner"`); everyone who can open the page reads.
- Merge stays on GitHub; the page cannot merge, close or push.
- The `mcp` capability lists only three read-only tools. The Artifact capabilities guidance says an mcp manifest is "a viewer-consented grant that bars public sharing"; that is fine (private page).
- If the viewer denies the connector, Live sessions and the repo picker say so and the rest works. If the database is unavailable, the page says so.

## Defaults this spec fixes (approved by merging)
| question | default | why |
|---|---|---|
| Where the project list lives | page database `projects/` | the owner edits it from the page |
| Who may add/archive/unarchive | the owner only | stops anyone else changing the fleet |
| PR description length | 4,000 characters | keeps each doc small; full text on GitHub |
| Refresh | only when the owner asks | earlier owner decision; no schedule |
| v1 dashboard | frozen at its last refresh once F3 merges | the owner then decides whether to delete it |

## Owner's role
- Approve this spec (merge its PR).
- Approve publishing the new artifact.
- Decide whether to delete the v1 dashboard afterwards.
- Allow the Claude Code Remote connector on the page the first time (optional; the page works without it).
- Grant the Claude GitHub app access to any repo shown as "Not connected".

## Later (not in v2)
- Merge from the page directly, if a GitHub connector appears on claude.ai.
- A "message the orchestrator" button (`send_message`). A message from a page reaches a session as peer data, and the session may refuse anything destructive, so this needs its own design.
- Refresh from the page by starting a Claude session (`create_session`): uses subscription time, so it is `needs-owner`.
- A schedule for refreshes.

## Size and undo
About 600 changed lines in 2 PRs. Undo: revert the PRs; the v1 dashboard keeps showing its last data and `config.json` is untouched, so reverting F3 restores v1 refreshes. Deleting the v2 artifact (owner only) removes its page and database.

## Known limits
- PR/issue data is only as fresh as the last refresh; live sessions are the only live part.
- One `pull_request_read` per open PR makes a refresh slower on busy repos (at most 30 per project by the cap).
