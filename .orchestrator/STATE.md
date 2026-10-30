# STATE (orchestrator-owned, at most 40 lines; written BEFORE any agent is spawned)

task: <id>   title: <...>
stage: interview|research|spec|issues|build|verify|fix|pr|release
owner_gate: waiting|none   last_approval: <what, when>

| stage | agent | model | effort | spawned (UTC) | status | verdict | evidence path | round |
|---|---|---|---|---|---|---|---|---|

(model/effort per the kit's docs/model-routing.md; a round whose verifier was lost still counts as used.)
reviewer: strongest | mid because <internal, non-security, small: say why>   (never weaker after a FAIL)
pr_label: needs-owner|internal   changed_lines: <n> (over ~400: split suggested)
spend: <tokens or "unknown">, spawns <n> / per-task soft cap <from docs/budget.md>  (at the cap: stop and ask)

next_step: <one line>
blockers: <one line; include any denied action and why it was needed>
resume: <agent id or partial-file path>   (agents from a dead session are LOST; re-dispatch from the partial file)
