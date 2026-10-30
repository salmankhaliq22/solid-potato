# HANDOFF

Written by the orchestrator after each major block of work (a merged PR, a verify round, a decision, before stopping).
A fresh session resumes from this file alone: after `/clear`, say "Read .orchestrator/HANDOFF.md and resume".
Keep it under about 60 lines. Facts only; say UNCONFIRMED where you are not sure. Overwrite it each time (git keeps
the history if the owner commits it).

Updated (UTC): <yyyy-mm-dd hh:mm>   By: orchestrator   Session goal: <one line>

## Milestones
- [x] <done milestone> (PR #N merged / decision D-NNN)
- [ ] <next milestone> (issue #N)

## State
- Branch / worktree per open task: <task> -> <branch> at <path>, last commit <sha>
- Open PRs and their labels: #N `internal` | `needs-owner`, checks <green/red>, verdict <PASS/FAIL/PARTIAL + path>
- Running or lost agents (from `.orchestrator/STATE.md`): <none | list>
- Verify rounds used per task (max 3): <task>: <n>
- Spend so far (from `python scripts/metrics_log.py week`): tokens <n | unknown>, spawns <n>

## Waiting on the owner
- <one question, with the recommendation> (asked <when>)

## To do (in order)
1. <next concrete step, who does it>
2. <...>

## Resume steps
1. Read this file, then `.orchestrator/STATE.md`, then the decision log entries listed above.
2. Check reality before acting: `git status --short`, `git worktree list`, `gh pr list` (open PRs), and the
   verdict files named above. If anything differs from this file, trust git and GitHub, and fix this file first.
3. Re-dispatch lost agents as the orchestrate skill says (a lost verify round still counts).
4. Continue with "To do" item 1. Do not redo finished milestones.
