# Update the Project Fleet dashboard

Use when the owner says "update the dashboard". The dashboard is the claude.ai
artifact `https://claude.ai/artifact/34vBev4QzzJYCR5746Grse`. It reads three
datasets (`projects`, `waiting`, `activity`) built from GitHub dumps by
`tools/fleet/build_fleet.py`. Projects are listed in `tools/fleet/config.json`.

`<S>` below is a scratch directory (use the session scratchpad).

## 1. Dump each connected project

For every project in `config.json`, create `<S>/dumps/<name>/` and save, using the GitHub MCP tools:

- `prs.json`: `list_pull_requests` state=open. Keep fields number, title, html_url, labels, draft, created_at, updated_at.
- `merged.json`: `list_pull_requests` state=closed, sort=updated, direction=desc, perPage=30, then page=2, 3, ... until the oldest `updated_at` on the last page is older than 7 days (a busy repo can have 30+ merges in a week). Concatenate all pages into one `merged.json`. Same fields plus merged_at, closed_at. If the builder warns that `merged_7d` may be undercounted, fetch more pages.
- `issues.json`: `list_issues` state=OPEN. Keep number, title, labels, created_at, updated_at. GitHub issue lists can include PRs; the builder drops any issue whose number is in `prs.json` or `merged.json`, so dump both PR files first.
- `commits.json`: `list_commits` perPage=30 on the default branch. Keep sha, html_url, commit (message and author date). Newest first.
- `state.md`: `get_file_contents` for `.orchestrator/STATE.md`, only if it exists.

A repo the session cannot reach gets no folder; it shows as "Not connected". Issues or PRs with `[HITL]` in the title count as waiting on the owner.

## 2. Build the datasets

    python tools/fleet/build_fleet.py --dumps <S>/dumps --out <S>/out

(Optional: `--now <ISO>` for a fixed clock, `--config <path>`.) Check `<S>/out` has `projects.json`, `waiting.json`, `activity.json`, `_manifest.json`.

## 3. Upload

For each of `projects.json`, `waiting.json`, `activity.json`, call Artifact publish with `asset: true`, `url: https://claude.ai/artifact/34vBev4QzzJYCR5746Grse` and the file path. Note each returned `/_blob` url.

## 4. Point the datasets at the new files

`ArtifactData` `list` on collection `datasets` to get each doc and its version. Then one `batch` of `update` writes, one per dataset, setting
`source: {kind: "file", url: <new /_blob url>, name: "<id>.json"}` and `updated: {at: <now ISO>, by: "orchestrator"}`, each pinned with `if_version`.

## 5. Check

Read the `data/users/me` doc `check` (up to 5 times, until it reflects the new data). If it still shows errors after 5 reads, report that.

## 6. Tell the owner

Two lines: what is waiting on them (count and the oldest item), and anything not connected or stale.

## Adding a project

Edit `tools/fleet/config.json` (name, repo, blurb) and attach the repo to the session (`add_repo`). Optional `"all_open_prs_wait": true` on a project (used for `resd`, where nothing merges until the owner names the PR) lists every open non-draft PR without another waiting label as "merge-needs-you" and counts it in waiting_on_you. Run the steps above.

## Tests

    python -m unittest discover -s tools/fleet -v
