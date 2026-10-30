# Budget (owner-set; agents read it, never raise it)

The owner fills in the numbers. Until a number is filled in, agents treat that cap as 0 and ask before spending.
Anything that adds cost is a `needs-owner` PR. The orchestrator checks these caps before every spawn
(skill `orchestrate`, "Spend caps") and the `whats-open` summary shows the weekly total.

## Caps
| cap | value | what happens at the cap |
|---|---|---|
| Monthly cap (all AI tokens and paid services) | <owner fills in, e.g. "USD 50" or "N tokens"> | All new agent spawns stop; the orchestrator asks the owner. |
| Per-task soft cap, tokens | <owner fills in, or "unknown" if tokens cannot be read> | The orchestrator stops and asks: continue or stop? |
| Per-task soft cap, agent spawns (always countable) | <owner fills in, e.g. 12> | Same as above; used when token counts are unknown. |
| Weekly total | shown in `whats-open` | Report only (from `python scripts/metrics_log.py week`; "unknown" when no token counts were recorded). |

## How numbers are measured
- Tokens are recorded only when a tool or the platform reported them (`metrics_log.py add --tokens N`). Agents never
  estimate or invent a token count; an unknown number is written as "unknown".
- Spawns are counted from `metrics_log.py` events (`--event spawn`).

## Recurring costs (subscriptions, services)
| item | cost per month | approved by (decision id) |
|---|---|---|

## Change log
(Each cap change is a decision in `docs/decisions/`; the owner makes it.)
