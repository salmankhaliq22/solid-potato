"""Work out GitHub Project board state from GitHub events (pure logic), and print a dry-run plan.

OPTIONAL / LATER (owner decision 2026-10-30): projects run without a board; the `whats-open` summary is the overview.
Trigger to add a board: more than about 20 open issues at once, and then GitHub's built-in Project automations only.
This script stays as a tested, offline consistency check for such a board; nothing in the default loop runs it.

Method taken from the `resd` project (read-only study): board Status is DERIVED from issue/PR events, never set by
agents. Rules, in order:
  closed -> Done | an open, unmerged linked PR -> Review | started -> In progress |
  currently Backlog/Ready/In progress -> keep (a human's choice; never demoted) | else Ready if it has a milestone, otherwise Backlog.
Gap fixed here: issues missing from the board are planned as ADD (resd's sync never added them).

    python scripts/board_sync.py --from-json issues.json      # offline plan; JSON list of issue dicts (see below)
    python scripts/board_sync.py --from-json issues.json --labels engineering,research
                                   # also WARN on issues without exactly one of these (optional labels; off by default)
    python scripts/board_sync.py --repo OWNER/REPO ...        # REFUSED (exit 3): live mode is not built yet

Issue dict: {number, title, state: open|closed, milestone: str|null, labels: [..], pr_open: bool, started: bool,
             board_status: str|null (null = not on board)}.
Live mode refuses until it really reads the board's Status and the linked-PR / started state: a plan built without
them would ADD every issue and demote a real "In progress" to Ready/Backlog. Until then, build the JSON by hand (or
with `gh project item-list --format json` plus `gh pr list`) and use --from-json. Applying a plan (gh project
item-add / item-edit) is the orchestrator's job after the owner says yes, and is UNTESTED here (needs a token with
the `project` scope). Second run on a synced board must plan 0 changes.
"""
import json
import sys

STATUSES = ("Backlog", "Ready", "In progress", "Review", "Done")


def desired_status(i: dict) -> str:
    if i.get("state") == "closed":
        return "Done"
    if i.get("pr_open"):
        return "Review"
    if i.get("started"):
        return "In progress"
    if i.get("board_status") in ("Backlog", "Ready", "In progress"):
        return i["board_status"]  # never move a card backwards from In progress on a missing `started` signal
    return "Ready" if i.get("milestone") else "Backlog"


OPTIONAL_CLASS_LABELS = ("engineering", "research")


def classify_ok(i: dict, labels=OPTIONAL_CLASS_LABELS) -> bool:
    """The issue carries exactly one of the given classification labels (optional rule, off by default)."""
    labs = set(i.get("labels") or [])
    return len(labs & set(labels)) == 1


def plan(issues: list, class_labels=None) -> list:
    """class_labels=None (default): no label rule. A tuple such as ("engineering", "research") turns the WARN on."""
    out = []
    for i in sorted(issues, key=lambda x: x["number"]):
        want = desired_status(i)
        have = i.get("board_status")
        if have is None:
            out.append({"issue": i["number"], "action": "ADD", "status": want})
        elif have != want:
            out.append({"issue": i["number"], "action": "SET", "from": have, "to": want})
        if class_labels and not classify_ok(i, class_labels):
            out.append({"issue": i["number"], "action": "WARN", "text": "needs exactly one of " + "|".join(class_labels)})
    return out


def main(argv):
    class_labels = None
    if len(argv) >= 2 and argv[0] == "--from-json":
        rest = argv[2:]
        if rest[:1] == ["--labels"] and len(rest) == 2:
            class_labels = tuple(x.strip() for x in rest[1].split(",") if x.strip())
        elif rest:
            sys.stderr.write(__doc__)
            return 2
        with open(argv[1], encoding="utf-8") as f:
            issues = json.load(f)
    elif argv and argv[0] == "--repo":
        sys.stderr.write("refused: live mode does not read the board Status or PR/started state yet, so its plan "
                         "would re-add every issue and demote work in progress. Use --from-json.\n")
        return 3
    else:
        sys.stderr.write(__doc__); return 2
    p = plan(issues, class_labels)
    for row in p:
        print(json.dumps(row))
    print(f"# dry run: {len(p)} planned change(s); nothing written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
