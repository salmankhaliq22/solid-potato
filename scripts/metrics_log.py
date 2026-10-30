"""Append-only metrics log (JSONL) and summary, for the future measured self-improvement loop.

    python scripts/metrics_log.py add --task T --event E [--round 1-3] [--verdict PASS|FAIL|PARTIAL] [--findings K]
                                      [--conflicts C] [--wall-s S] [--tokens N] [--model M] [--effort E]
                                      [--note TEXT] [--file F]
    python scripts/metrics_log.py summary [--file F]
    python scripts/metrics_log.py week [--file F] [--days 7]     # weekly total for whats-open and docs/budget.md

Events: task_start, spawn (model, effort: the routing choice), verify (round, verdict, findings), merge_main
(conflicts), pr_open, pr_merged, task_done. Rounds are 1-3 (the loop cap). Default file: .orchestrator/metrics.jsonl.
Numbers come from what the orchestrator observed from verdict files and git, never from an agent grading itself.
Tokens are optional (UNCONFIRMED how to read them per subagent); `summary` prints "unknown" for a task with no
recorded count and "at least N" when only some of its spawns carry one. `summary` skips damaged lines (for example a torn
last line) and reports how many it skipped. `week` sums recorded tokens and counts spawns over the last N days; it
prints "unknown" for tokens when none were recorded and "at least N" when only some events carry a count. It never
estimates.
"""
import argparse
import collections
import json
import os
import sys
import time

EVENTS = ("task_start", "spawn", "verify", "merge_main", "pr_open", "pr_merged", "task_done")


def round_1_3(v):
    n = int(v)
    if not 1 <= n <= 3:
        raise argparse.ArgumentTypeError("round must be 1, 2 or 3 (the loop stops after round 3)")
    return n


def nonneg(v):
    n = int(v)
    if n < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return n


def add(a):
    if a.event == "verify" and (a.round is None or a.verdict is None):
        sys.stderr.write("refused: a verify event needs --round and --verdict\n")
        return 2
    rec = {"t": time.time(), "task": a.task, "event": a.event}
    for k in ("round", "verdict", "findings", "conflicts", "wall_s", "tokens", "model", "effort", "note"):
        v = getattr(a, k)
        if v is not None:
            rec[k] = v
    os.makedirs(os.path.dirname(a.file) or ".", exist_ok=True)
    with open(a.file, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return 0


def summary(a):
    per = collections.defaultdict(lambda: {"rounds": 0, "pass_round": None, "findings": [], "conflicts": 0,
                                           "wall_s": 0.0, "tokens": 0, "tok_n": 0,
                                           "spawns": 0})
    if not os.path.exists(a.file):
        print("no metrics yet"); return 0
    skipped = 0
    with open(a.file, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                t = per[str(r["task"])]
                if r["event"] == "verify":
                    t["rounds"] = max(t["rounds"], int(r.get("round", 0)))
                    t["findings"].append(r.get("findings", 0))
                    if r.get("verdict") == "PASS" and t["pass_round"] is None:
                        t["pass_round"] = r.get("round")
                t["conflicts"] += int(r.get("conflicts", 0) or 0)
                t["wall_s"] += float(r.get("wall_s", 0) or 0)
                t["spawns"] += r["event"] == "spawn"
                if r.get("tokens") is not None:
                    t["tokens"] += int(r["tokens"])
                    t["tok_n"] += 1
            except (ValueError, KeyError, TypeError, AttributeError):
                skipped += 1
    print("task | rounds_to_PASS | findings_per_round | conflicts | wall_s | tokens")
    for k, t in sorted(per.items()):
        print(f"{k} | {t['pass_round']} | {t['findings']} | {t['conflicts']} | {t['wall_s']:.0f} | {tok_text(t)}")
    if skipped:
        print(f"warning: skipped {skipped} damaged line(s) in {a.file}", file=sys.stderr)
    return 0


def tok_text(t: dict) -> str:
    """Never print 0 for 'nothing recorded' (owner rule: never invent a token count)."""
    if t["tok_n"] == 0:
        return "unknown"
    if t["tok_n"] < t["spawns"]:  # some spawns carry no count: the sum is only a lower bound
        return f"at least {t['tokens']}"
    return str(t["tokens"])


def week(a):
    since = time.time() - a.days * 86400
    tokens, with_tokens, spawns, skipped = 0, 0, 0, 0
    if os.path.exists(a.file):
        with open(a.file, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    if float(r["t"]) < since:
                        continue
                    spawns += r.get("event") == "spawn"
                    if r.get("tokens") is not None:
                        tokens += int(r["tokens"])
                        with_tokens += 1
                except (ValueError, KeyError, TypeError, AttributeError):
                    skipped += 1
    if with_tokens == 0:
        tok = "unknown (no token counts recorded)"
    elif with_tokens < spawns:  # some spawns carry no count, so the sum is only a lower bound
        tok = f"at least {tokens} (only {with_tokens} event(s) carry a count)"
    else:
        tok = str(tokens)
    print(f"last {a.days} days: tokens {tok}; agent spawns {spawns}")
    if skipped:
        print(f"warning: skipped {skipped} damaged line(s) in {a.file}", file=sys.stderr)
    return 0


def positive(v):
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return n


def main(argv):
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("add")
    s.add_argument("--task", required=True); s.add_argument("--event", required=True, choices=EVENTS)
    s.add_argument("--round", type=round_1_3); s.add_argument("--verdict", choices=("PASS", "FAIL", "PARTIAL"))
    s.add_argument("--findings", type=nonneg); s.add_argument("--conflicts", type=nonneg)
    s.add_argument("--wall-s", dest="wall_s", type=float); s.add_argument("--tokens", type=nonneg)
    s.add_argument("--model"); s.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"))
    s.add_argument("--note")
    s2 = sp.add_parser("summary")
    s3 = sp.add_parser("week")
    s3.add_argument("--days", type=positive, default=7)
    for x in (s, s2, s3):
        x.add_argument("--file", default=".orchestrator/metrics.jsonl")
    a = p.parse_args(argv)
    return {"add": add, "summary": summary, "week": week}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
