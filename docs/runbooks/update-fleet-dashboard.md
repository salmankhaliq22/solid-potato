# Update the Project Fleet dashboard

Use when the owner says "update the dashboard". Two dashboards exist:

- **v2 control room** (spec `docs/specs/fleet-control-room.md`): a plain HTML artifact built from `tools/fleet/control.html`. Its projects list (`projects/<name>`) and per-project data (`snapshot/<name>`, `snapshot/_meta`) live in the page database. This runbook refreshes it. It is published with the capabilities in `tools/fleet/control.capabilities.json`.
- **v1 dashboard** (`https://claude.ai/artifact/34vBev4QzzJYCR5746Grse`): frozen at its last refresh. The old steps are no longer run.

`<S>` below is a scratch directory (use the session scratchpad). `<URL>` is the v2 artifact URL.

## 0. Build and publish the page (only when `control.html` or `control_logic.js` changed)

    python tools/fleet/build_control.py     # writes tools/fleet/dist/control.html (logic inlined)

Publishing is an owner gate. Publish `tools/fleet/dist/control.html` with `capabilities` set to the contents of `tools/fleet/control.capabilities.json` (database writable by the owner only on `projects/` and `snapshot/`; `user` for the owner check; `mcp` limited to the Claude Code Remote connector tools `list_sessions`, `get_session`, `list_repos`, for the Live sessions panel and the repo picker). Always pass the whole file, or the page loses a capability. The page writes `projects/` (owner clicks Add, Archive, Unarchive); the refresh still owns `snapshot/` and the page never writes it.

## 1. Seed the projects (once, after first publish)

`tools/fleet/seed_projects.json` is the one-time seed: 5 docs in ArtifactData list shape (`{id, data}`), `resd` with `all_open_prs_wait: true`, `added_by: "seed"`. Write them with one `ArtifactData` `batch` of `set` writes to collection `projects` (doc_id = `id`, data = `data`). Never re-run it over a live list. `tools/fleet/config.json` is now only this seed plus the shared settings the builder reads (waiting labels, in-progress labels, active/quiet days); the project list lives in the page database.

## 2. List the projects

`ArtifactData` `list` on collection `projects`; save the output as `<S>/projects.json`. Keep only docs whose `archived` is not true (the builder also skips archived and invalid docs, with a warning).

## 3. Attach every kept repo

Each refresh is a fresh session, so run `add_repo` for EVERY kept project on every refresh. On failure write the reason (one line) to `<S>/dumps/<name>/not_connected.txt`; the page then shows "Not connected — grant the Claude GitHub app access to <repo>" and the old data is kept.

## 4. Dump each connected project

Create `<S>/dumps/<name>/` and save, using the GitHub MCP tools:

- `prs.json`: `list_pull_requests` state=open. Keep number, title, html_url, labels, draft, created_at, updated_at.
- `pr_<number>.json`: `pull_request_read` once per open PR (list results lack additions, deletions and mergeable_state). Keep body, additions, deletions, mergeable_state. Only the 30 PRs the page shows are needed; skip the rest. If missing, those fields stay blank in the page; never guess them.
- `merged.json`: `list_pull_requests` state=closed, sort=updated, direction=desc, perPage=30, then page=2, 3, ... until the oldest `updated_at` on the last page is older than 7 days. Concatenate pages. Same fields plus merged_at, closed_at. If the builder warns that `merged_7d` may be undercounted, fetch more pages.
- `issues.json`: `list_issues` state=OPEN. Keep number, title, html_url, labels, created_at, updated_at. The builder drops any issue whose number is in `prs.json` or `merged.json`, so dump both PR files first.
- `commits.json`: `list_commits` perPage=30 on the default branch. Keep sha, html_url, commit (message and author date). Newest first.
- `state.md`: `get_file_contents` for `.orchestrator/STATE.md`, only if it exists.

Issues or PRs with `[HITL]` in the title count as waiting on the owner. A project with no dump folder and no `not_connected.txt` is a mistake in the refresh: the builder names it on stderr, writes it as not connected ("No data was fetched for this project (refresh skipped it)"), still builds the others, and exits 1. Report it to the owner.

## 5. List the current snapshot, then build

Writes to an existing doc must carry its current version, so first run `ArtifactData` `list` on collection `snapshot` (every page, if the listing is paged) and save the output as `<S>/versions.json` (each doc's `id` and `version`; save `[]` if the collection is empty). Do this right before building, so the versions are fresh.

    python tools/fleet/build_fleet.py --dumps <S>/dumps --projects <S>/projects.json --versions <S>/versions.json --out <S>/out

`--versions` is required with `--projects`. (Optional: `--now <ISO>`, `--config <path>`.) The builder prints each doc and its size, writes `<S>/out/snapshot/<name>.json` and `snapshot/_meta.json`, and writes `<S>/out/batches.json`. Each doc is capped (30 PRs, 50 issues, 40 activity rows, PR bodies 4,000 characters) and trimmed under 240 KB. A project whose doc cannot fit is named on stderr, nothing is written for it, the others are built, and the exit code is 1. Report such a project to the owner.

## 6. Write the snapshot to the page database

`<S>/out/batches.json` is `{"batches": [{"bytes", "writes": [...]}]}`. Each write is already shaped for `ArtifactData` `batch`: `op`, `collection`, `doc_id`, `data`, plus `if_version` for a doc that already exists (taken from `<S>/versions.json`); new docs have no `if_version`. Pass each entry's `writes` array unchanged as the `batch` call's `writes`; do not add `bytes` or other keys. Send the batches IN ORDER, one `ArtifactData` `batch` call per entry (at most 50 writes and 1 MiB per batch; the plan keeps each under about 900 KB). The last batch holds `snapshot/_meta` alone: write it last, so a half-finished refresh shows "Stale" rather than fresh. A not-connected project with an existing snapshot uses `update` (merge), so its old lists stay; one with no snapshot yet gets a `set` of a minimal not-connected doc (empty lists, counts 0).

If a write is refused because a version changed (someone or something wrote in between), do not retry the same batch: list `snapshot` again, rebuild from step 5, and send the batches again.

## 7. Check and tell the owner

Open the page (`action: open`) and confirm the cards show "Data as of" today. Then two lines to the owner: what is waiting on them (count and the oldest item), and anything not connected, stale or too large.

## Adding or archiving a project

The owner does this on the page: "Add project" on the overview (name, repo, description, "Every open PR needs my OK"), "Archive project" on a project page (asks first), "Unarchive" in the archived list. Each click is one write to `projects/<name>`; nobody else sees the buttons and the database refuses their writes. A new project shows "Waiting for first refresh" until the next "update the dashboard". The manual route still works: `ArtifactData` `set` on `projects/<name>` with `{repo, blurb, archived: false, all_open_prs_wait, added_at, added_by}`, or `update` with `{archived: true}`.

Live sessions need the viewer to allow the Claude Code Remote connector; if they do not, the page says so and everything else works.

## Tests

    python -m unittest discover -s tools/fleet -v
    node tools/fleet/test_control_logic.js
