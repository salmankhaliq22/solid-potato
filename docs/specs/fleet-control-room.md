# Spec: Fleet control room (dashboard v2)

Status: DRAFT. Merging this spec's PR is the owner's approval; no code starts before then.
Decisions: `docs/decisions/D-20261031T002337-dashboard-v2-add-archive-projects-and-a-.md`, `D-20261031T002337-dashboard-merge-opens-the-pr-on-github.md`, `D-20261031T001035-dashboard-refreshes-only-on-request.md`. Milestone: Fleet v2 (issues filled in after approval).

## Plan
Today the Project Fleet dashboard (v1, https://claude.ai/artifact/34vBev4QzzJYCR5746Grse) is a read-only snapshot. The owner asked for one place to run everything: add or archive projects, click a project (for example resd) to see its details and progress, read its open PRs, and merge them.

Approach: a new plain HTML artifact (not the Dashboard type, which cannot do custom navigation, buttons or capabilities). Its project list and PR/issue data live in the page's shared database (`db` capability) instead of attached files. The page also asks the claude.ai "Claude Code Remote" connector (`mcp` capability) which Claude sessions are working on each project, live. GitHub data still comes from the orchestrator's refresh when the owner says "update the dashboard" (no schedule, owner decision). Merge is a button that opens the PR on GitHub, where the owner clicks Merge.

## Done means
- The owner opens the v2 page and sees one card per active project, totals, and a "waiting on you" list.
- Clicking a project card opens its project page; a back link returns to the overview.
- The project page shows every open PR with title, labels, why it waits, age, size (+/−) and its description as plain text (cut at about 4,000 characters, with "Read on GitHub").
- "Read on GitHub" and "Merge on GitHub" open the PR page in a new tab; "Merge on GitHub" shows only to the owner.
- The owner can add a project (it appears with "Waiting for first refresh") and archive or unarchive one; non-owners cannot.
- After "update the dashboard", archived projects are skipped and every active project shows fresh data and a "Data as of" time.
- The Live sessions panel lists Claude sessions for that project with status, or says plainly why it cannot (connector denied).
- All tests pass; a fresh reviewer gives PASS; the owner approves publishing.

## Views
**Overview.** Cards for active projects (name, blurb, status, waiting count, open PRs, merged this week, last activity). Totals row. "Waiting on you" list across projects, oldest first. "Data as of <time>" line. Archived projects in a collapsed list, each with Unarchive (owner only). "Add project" button (owner only).

**Project page** (one per project):
- Header: status, last activity, and from `.orchestrator/STATE.md` when present: stage, next step, blockers.
- Open PRs: title, labels, why waiting, age in days, size (+additions / −deletions), description as plain text (about 4,000 characters, then "… Read on GitHub"). Buttons "Read on GitHub" and "Merge on GitHub" (both link to the PR page; Merge only for the owner). If GitHub said the PR cannot merge cleanly (`mergeable_state`), show "Has conflicts" next to the button.
- Open issues: title, labels, age.
- This week's activity: merged PRs and commits.
- Live sessions: each Claude session for this repo with a status pill (Working, Blocked, Review ready, Completed, Failed), title, branch, last updated, and a link to https://claude.ai/code/<session_id>.
- "Data as of" line, and an Archive button (owner only).

**Add project** (owner only): repo picker filled from the connector's `list_repos` when allowed, otherwise a text box for owner/repo; name; one-line blurb; checkbox "Every open PR needs my OK" (`all_open_prs_wait`).

## Data model (page database)
| path | written by | contents |
|---|---|---|
| `projects/<name>` | owner, from the page | `{repo, blurb, archived, all_open_prs_wait, added_at, added_by}`. Replaces `tools/fleet/config.json` as the list of projects. |
| `snapshot/<name>` | orchestrator refresh | the v1 projects-row fields, plus `open_prs[]`, `open_issues[]`, `activity[]`. Each doc kept under 256 KB: PR bodies cut to 4,000 characters, lists capped. |
| `snapshot/_meta` | orchestrator refresh | `{updated_at}` |

Access rules: anyone signed in who can open the page may read; writes to `projects/` need admin (owner/editors); `snapshot/` is written by the orchestrator through the ArtifactData tool, acting as the owner. Archive sets `archived: true`: the project is kept, hidden from the overview and totals, and the refresh skips it.

## Deliverables
### F1: builder reads the db project list and emits snapshot docs
`build_fleet.py` gains `--projects <export.json>` (an ArtifactData list of `projects`, archived ones skipped), keeps PR `body`, `additions`, `deletions`, `mergeable_state` when dumped, and writes one `snapshot/<name>` doc per project plus `_meta`, with the size cut. Needs: none. Size: about 150 lines with tests.
**Acceptance:** new unit tests in `tools/fleet/test_build_fleet.py` pass (archived skipped, body truncation, size limit, missing fields tolerated); old tests still pass.

### F2: the control-room page
New `tools/fleet/control.html`: overview, project page, add/archive, live sessions. Declares `db`, `user` and `mcp` with only `list_sessions`, `get_session`, `list_repos`. Page logic (group sessions by repo URL from `get_session` sources, sort, truncate, status mapping) lives in pure functions tested with node. Needs: F1 (data shape). Size: about 400 lines; may be split into F2a (overview + project page) and F2b (add/archive + live sessions).
**Acceptance:** node tests of the pure functions pass; page works with the connector denied and with db empty (shows plain messages, no blank screen).

### F3: runbook and migration
Update `docs/runbooks/update-fleet-dashboard.md`: step 0 read `projects` with ArtifactData list; dump only non-archived projects; build; write snapshot docs in one batch. Seed `projects/` from `config.json` (5 projects; resd keeps `all_open_prs_wait`). Needs: F1, F2. Size: about 60 lines.
**Acceptance:** after publishing (owner gate), one functional pass: ArtifactData list of `projects` shows 5 docs, `snapshot` shows 5 docs plus `_meta`, and the page shows them.

## Order
F1 first. F2 can start in parallel once F1's data shape is agreed (different files). F3 last. Never two builders on the same files.

## Safety
- No secrets or tokens in the database. Data values are shown with `textContent` only (never as HTML), so a PR description cannot run code in the page.
- Merge stays on GitHub; the page cannot merge, close or push.
- The `mcp` capability lists only three read-only tools. A page that declares `mcp` cannot be shared publicly; that is fine (private page).
- If the viewer denies the connector, Live sessions and the repo picker say so and the rest works. If the database is unavailable, the page says so.

## Defaults this spec fixes (approved by merging)
| question | default | why |
|---|---|---|
| Where the project list lives | page database `projects/` | the owner edits it from the page |
| Who may add/archive | owner and editors only | stops viewers changing the fleet |
| PR description length | about 4,000 characters | keeps each doc small; full text on GitHub |
| Refresh | only when the owner asks | earlier owner decision; no schedule |
| v1 dashboard | stays until v2 is approved | the owner then decides whether to delete it |

## Owner's role
- Approve this spec (merge its PR).
- Approve publishing the new artifact.
- Decide whether to delete the v1 dashboard afterwards.
- Allow the Claude Code Remote connector on the page the first time (optional; the page works without it).

## Later (not in v2)
- Merge from the page directly, if a GitHub connector appears on claude.ai.
- A "message the orchestrator" button (`send_message`). A message from a page reaches a session as peer data, and the session may refuse anything destructive, so this needs its own design.
- Refresh from the page by starting a Claude session (`create_session`): uses subscription time, so it is `needs-owner`.
- A schedule for refreshes.

## Size and undo
About 600 changed lines in 3–4 PRs. Undo: revert the PRs; the v1 dashboard and `config.json` keep working because v1 is not touched until the owner deletes it. Deleting the v2 artifact (owner only) removes its page and database.

## Known limits and UNCONFIRMED items
- PR/issue data is only as fresh as the last refresh; live sessions are the only live part.
- UNCONFIRMED: whether every GitHub MCP list dump includes `additions`, `deletions` and `mergeable_state`; if not, the refresh needs one `pull_request_read` per PR, or those fields show blank.
- Sessions are matched to a project by repo URL; a session with no repo attached shows under "Other sessions" on the overview.
