# CLAUDE.md

Keep this short and current (target: under 60 lines). Owner = the repo owner (not necessarily a developer); they approve by merging PRs.

## What this is
<one paragraph: the project and who it is for>

## Stack and checks
- Stack: <fill in>
- Fast tier (every push; aim under 2 minutes): `<command>`. Run it through `python scripts/with_lock.py check -- <command>`.
- Slow tier (before releases, toolchain changes and anything risky): `<command>` (about <N> minutes).
- Missing prerequisites FAIL with the fix; they never skip.

## Non-negotiable rules
1. Decisions are written down: `docs/decisions/` (one file per decision, append-only, `scripts/decision_log.py`). A short spec in `docs/specs/` only if the work takes more than about a day, users will see it, or it costs money; the owner approves it by merging it. Smaller work is one issue with clear "Done means" lines.
2. Every piece of work is a GitHub issue (search for duplicates first). One issue = one branch = one worktree = one PR. Never push to `main`; never force-push or rebase. Merge main INTO the branch (`python scripts/merge_main.py --check-cmd "<fast tier>"`). Push with the plain form `git push -u origin <branch>` (other push forms ask the owner). After each major block, the orchestrator rewrites `.orchestrator/HANDOFF.md`; to restart, `/clear` and "Read .orchestrator/HANDOFF.md and resume". Keep PRs small: over about 400 changed lines, say so and suggest a split (a guideline, not a block).
3. Label every PR: `needs-owner` (users see it, or data/privacy/security/cost; only the owner merges) or `internal` (the orchestrator may merge after green checks AND a fresh reviewer's PASS, recorded in the decision log). Issues only the owner can do get `owner-only`. `engineering`/`research`/`governance` are optional, off by default.
4. Before a PR opens, a FRESH reviewer that did not write the code checks it: the strongest model for `needs-owner`, security and hooks work; a mid model is allowed for small `internal` work (reason in STATE.md). Fix and verify at most 3 rounds, then stop and tell the owner in one plain line.
5. Never skip or weaken a test; never raise a budget or tolerance to get green. Report it.
6. Unapproved work never reaches production (flags or draft status). Data/schema changes: reader first, writer later.
7. No secrets in chat or git. Caps and costs live in `docs/budget.md` (monthly cap, per-task soft cap: stop and ask); anything adding cost is `needs-owner`. Never invent facts or token counts; claims need a source (or say UNCONFIRMED).
8. The orchestrator does not verify work itself and does not write code; it delegates and reads verdicts.
9. If a tool call is denied, stop and ask the owner. Never work around a guard.
10. Talk to the owner in plain words: outcome first, one recommendation, short.
11. No AI attribution anywhere: no co-author trailer naming an AI and no "generated with" line in commits, PR text or files (the guard denies them).
12. The orchestrator picks model and effort per task (the kit's `docs/model-routing.md`) and records the choice in STATE.md.
13. Every PR says how to undo it. After each episode or milestone, a 5-line retro (skill `retro`); the owner picks at most one change.

## Owner gates
(1) spec approval, (2) merging `needs-owner` PRs, (3) any publish, upload, release or schedule, (4) spend, going past a cap, credentials, account changes, deletions, (5) creating repos, (6) changing guard rules. <add project gates>

## Where things live
- `docs/decisions/`, `docs/specs/`, `docs/budget.md`, `docs/adr/` (only for choices that are hard to reverse), `.orchestrator/STATE.md`, `.orchestrator/metrics.jsonl`
- Recurring work: issue template `checklist.md` (box n = step n; ★ = owner approval point).
- Verifier evidence: `.orchestrator/runs/<task>/verification/` in the main checkout (local, git-ignored); the PR body carries the verifier's verdict and reply. Merge notes: `.orchestrator/runs/merge-notes/`.
- Locks: `scripts/with_lock.py` uses `<git common dir>/orchestrator-locks`, shared by all worktrees.
- Protected (agents are denied; the owner edits by hand): secrets, `approvals/`, `.claude/`, `CLAUDE.md`, `.github/workflows/`, `.orchestrator/protected.json`, the kit's helper scripts. See the kit's `docs/LIMITS.md`.
- Overview: skill `whats-open` (plain summary). No board by default; add a GitHub Project with built-in automations only when more than about 20 issues are open.
- Orchestrator kit: plugin `habibi` (skills `/habibi:orchestrate`, `interview`, `spec-to-issues`, `verify-work`, `release`, `whats-open`, `retro`).
