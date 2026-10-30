---
name: Recurring work checklist
about: One run of repeating work (an episode, a monthly chore). Box n is step n; ★ marks an owner approval point.
title: "<what> <number or date>: checklist"
labels: ""
---

Copy the steps of this project's recurring workflow below (one box per step, in order: the n-th box is step n).
Agents tick a box only when that step's output exists. A box marked ★ is ticked ONLY after the owner's explicit yes,
recorded in `docs/decisions/` (name the decision id in the box). Agents stop at every ★ box and ask.

## Steps
- [ ] 1. <step> (output: <file or link>)
- [ ] 2. ★ Owner approves: <what the owner reads or checks> (decision: <id>)
- [ ] 3. <step>
- [ ] 4. ★ Owner approves: <publish / upload / spend / schedule and its copy> (decision: <id>)
- [ ] 5. Retro: agent drafts 5 lines (skill `retro`); owner picks at most one change

## Links
- Spec or workflow description:
- PRs:

## Blocked?
(One line: what is missing and who can unblock it.)
