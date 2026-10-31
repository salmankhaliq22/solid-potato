#!/usr/bin/env python3
"""Turn raw GitHub dumps into the Project Fleet datasets (stdlib only)."""
import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone

WRAP_KEYS = ("items", "issues", "pull_requests", "data")
WINDOW_DAYS = 7


def parse_ts(value):
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else ""


def normalise(raw):
    """Return a list of dict rows from a bare array, wrapper object or MCP text wrapper."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if isinstance(raw, dict):
        for key in WRAP_KEYS:
            if key in raw:
                return normalise(raw[key])
        return []
    if not isinstance(raw, list):
        return []
    if raw and all(isinstance(x, dict) and x.get("type") == "text" and "text" in x for x in raw):
        out = []
        for part in raw:
            out.extend(normalise(part["text"]))
        return out
    return [x for x in raw if isinstance(x, dict)]


def labels_of(item):
    out = []
    for lab in item.get("labels") or []:
        if isinstance(lab, str):
            out.append(lab)
        elif isinstance(lab, dict) and lab.get("name"):
            out.append(str(lab["name"]))
    return out


def load_json(folder, name):
    path = os.path.join(folder, name)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        text = fh.read().strip()
    if not text:
        return []
    return normalise(text)


def load_text(folder, name):
    path = os.path.join(folder, name)
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def state_field(text, field):
    pat = re.compile(r"^\s*(?:[-*]\s*)?\**%s\**\s*:\s*(.*)$" % re.escape(field), re.I)
    for line in text.splitlines():
        m = pat.match(line)
        if not m:
            continue
        val = m.group(1).split("  ")[0].strip().strip("*").strip()
        if "<" in val or "|" in val:
            continue
        if val:
            return val
    return ""


def clip(text, n):
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def first_line(text):
    return (text or "").strip().split("\n")[0].strip()


def days_between(now, dt):
    return round((now - dt).total_seconds() / 86400.0, 1)


def has_label(item_labels, wanted):
    low = {w.lower(): w for w in wanted}
    for lab in item_labels:
        if lab.lower() in low:
            return lab
    return None


def commit_info(c):
    commit = c.get("commit") or {}
    author = commit.get("author") or {}
    committer = commit.get("committer") or {}
    dt = parse_ts(author.get("date")) or parse_ts(committer.get("date"))
    return dt, first_line(commit.get("message", "")), str(c.get("sha", "")), c.get("html_url", "")


def build(dumps, config, now):
    wl = config.get("waiting_labels", [])
    ipl = config.get("in_progress_labels", [])
    active_d = config.get("active_days", 2)
    quiet_d = config.get("quiet_days", 7)
    window = now - timedelta(days=WINDOW_DAYS)
    projects, waiting, activity = [], [], []

    for p in config["projects"]:
        name, repo = p["name"], p["repo"]
        folder = os.path.join(dumps, name)
        row = {
            "project": name, "repo": repo, "url": "https://github.com/" + repo,
            "blurb": p.get("blurb", ""), "connected": False, "status": "Not connected",
            "last_activity_at": "", "last_activity_days": -1, "last_commit_msg": "",
            "open_prs": 0, "waiting_on_you": 0, "ready_internal": 0, "open_issues": 0,
            "in_progress": 0, "merged_7d": 0, "stage": "", "next_step": "", "blockers": "",
        }
        if not os.path.isdir(folder):
            projects.append(row)
            continue
        row["connected"] = True
        prs = load_json(folder, "prs.json")
        merged = load_json(folder, "merged.json")
        issues = load_json(folder, "issues.json")
        commits = load_json(folder, "commits.json")
        state = load_text(folder, "state.md")

        pr_numbers = {x.get("number") for x in prs + merged}
        issues = [i for i in issues if i.get("number") not in pr_numbers and "pull_request" not in i]

        stamps = []
        cinfos = [commit_info(c) for c in commits]
        if cinfos:
            row["last_commit_msg"] = clip(cinfos[0][1], 90)
        stamps += [ci[0] for ci in cinfos[:1] if ci[0]]
        for x in prs + merged:
            for k in ("updated_at", "merged_at"):
                dt = parse_ts(x.get(k))
                if dt:
                    stamps.append(dt)
        if stamps:
            last = max(stamps)
            d = days_between(now, last)
            row["last_activity_at"] = iso(last)
            row["last_activity_days"] = d
            row["status"] = "Active" if d <= active_d else "Quiet" if d <= quiet_d else "Idle"
        else:
            row["status"] = "Idle"

        row["open_prs"] = len(prs)
        row["open_issues"] = len(issues)
        n_wait = 0
        for kind, items in (("PR", prs), ("Issue", issues)):
            for it in items:
                labs = labels_of(it)
                wlab = has_label(labs, wl)
                title_hitl = not wlab and "[hitl]" in (it.get("title") or "").lower()
                if title_hitl:
                    wlab = "HITL"
                internal = kind == "PR" and has_label(labs, ["internal"]) and not it.get("draft")
                if has_label(labs, ipl):
                    row["in_progress"] += 1
                if internal:
                    row["ready_internal"] += 1
                if not (wlab or internal):
                    continue
                if wlab:
                    n_wait += 1
                created = parse_ts(it.get("created_at"))
                waiting.append({
                    "key": "%s#%s" % (name, it.get("number")), "project": name, "kind": kind,
                    "number": it.get("number"), "title": clip(it.get("title", ""), 100),
                    "url": it.get("html_url", ""), "label": wlab or "internal",
                    "why": "Needs your hands" if title_hitl else "Needs your decision" if wlab else "Ready to merge",
                    "age_days": days_between(now, created) if created else 0,
                    "_w": 0 if wlab else 1,
                })
        row["waiting_on_you"] = n_wait

        merged_nums = set()
        for m in merged:
            dt = parse_ts(m.get("merged_at"))
            if not dt:
                continue
            merged_nums.add(m.get("number"))
            if dt >= window:
                row["merged_7d"] += 1
                activity.append({
                    "key": "%s:pr:%s" % (name, m.get("number")), "project": name,
                    "kind": "Merged PR", "title": clip(m.get("title", ""), 100),
                    "url": m.get("html_url", ""), "at": iso(dt), "_dt": dt,
                })
        for dt, msg, sha, url in cinfos:
            if not dt or dt < window:
                continue
            m = re.search(r"\(#(\d+)\)\s*$", msg)
            if m and int(m.group(1)) in merged_nums:
                continue
            activity.append({
                "key": "%s:c:%s" % (name, sha[:7]), "project": name, "kind": "Commit",
                "title": clip(msg, 100), "url": url, "at": iso(dt), "_dt": dt,
            })

        row["stage"] = state_field(state, "stage")
        row["next_step"] = state_field(state, "next_step")
        row["blockers"] = state_field(state, "blockers")
        projects.append(row)

    waiting.sort(key=lambda r: (r["_w"], -r["age_days"], r["key"]))
    for r in waiting:
        del r["_w"]
    activity.sort(key=lambda r: r["_dt"], reverse=True)
    activity = activity[:40]
    for r in activity:
        r["days_ago"] = days_between(now, r.pop("_dt"))
    return projects, waiting, activity


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dumps", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--now")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    a = ap.parse_args(argv)
    with open(a.config, encoding="utf-8") as fh:
        config = json.load(fh)
    now = parse_ts(a.now) if a.now else datetime.now(timezone.utc)
    if now is None:
        ap.error("bad --now")
    projects, waiting, activity = build(a.dumps, config, now)
    os.makedirs(a.out, exist_ok=True)
    files = {"projects.json": projects, "waiting.json": waiting, "activity.json": activity}
    for fname, rows in files.items():
        with open(os.path.join(a.out, fname), "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2)
            fh.write("\n")
    with open(os.path.join(a.out, "_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"updated_at": iso(now), "files": list(files)}, fh, indent=2)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
