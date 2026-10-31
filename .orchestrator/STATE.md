# STATE (orchestrator-owned, at most 40 lines; written BEFORE any agent is spawned)

task: T1   title: Cross-project dashboard (Project Fleet)
stage: build
owner_gate: none   last_approval: projects + on-request refresh (docs/decisions, 2026-10-31)

| stage | agent | model | effort | spawned (UTC) | status | verdict | evidence path | round |
|---|---|---|---|---|---|---|---|---|
| build | builder (fleet builder script + page) | sonnet | high | 2026-10-31 | running | - | tools/fleet/ | - |

reviewer: strongest (owner-visible page)
pr_label: needs-owner   changed_lines: tbd
spend: unknown, spawns 1 / per-task soft cap (docs/budget.md not filled in yet)

next_step: builder writes tools/fleet (data builder + tests + page); orchestrator dumps GitHub data
blockers: resd and oneblockatatime not accessible to the Claude GitHub App; no GitHub connector on claude.ai (no live queries)
resume: dashboard https://claude.ai/artifact/34vBev4QzzJYCR5746Grse
