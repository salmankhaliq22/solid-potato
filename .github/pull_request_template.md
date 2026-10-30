Closes #

## What and why
(Two or three plain sentences.)

## Label
- [ ] `needs-owner` (users see it, or it touches data, privacy, security or cost; only the owner merges)
- [ ] `internal` (tests, refactors, tooling; the orchestrator may merge after green checks AND a fresh reviewer's PASS, recorded in the decision log)

## How to undo it
(One line: usually "revert this PR". For anything published or any data change: how to take it down or restore.)

## Size
(Changed lines from `git diff --shortstat main...HEAD`. Over about 400: say why, or how it could be split.)

## Evidence
| check | result |
|---|---|
| full check chain | (paste; anything not run says "not run") |
| attribution scan (`python <kit>/scripts/kit_check.py --scan-repo .`) | (paste its last line) |
| independent reviewer (fresh; model and why: strongest, or mid for small `internal` non-security work) | verdict, round, model, and the reviewer's reply pasted here (its evidence file is local and git-ignored) |

Findings fixed (list):

## Paperwork
- [ ] Decision/ADR/spec/docs updated where relevant
- [ ] No secrets, no large generated files, no tracking SDKs
- [ ] No AI attribution (no co-author trailer naming an AI, no "generated with" line) in commits, this text or files
- [ ] Main merged into this branch (no rebase)

## Anything the owner must decide
(One question and my recommendation, or "Nothing".)
