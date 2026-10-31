#!/usr/bin/env python3
"""Turn raw GitHub dumps into the Project Fleet datasets (stdlib only)."""
import argparse
import json
import os
import re
import sys
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


def build(dumps, config, now, keep_raw=False, activity_cap=40):
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
            "in_progress": 0, "merged_7d": 0, "merged_7d_capped": False, "stage": "", "next_step": "", "blockers": "",
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
        dated = [ci for ci in cinfos if ci[0]]
        if dated:
            newest = max(dated, key=lambda ci: ci[0])
            row["last_commit_msg"] = clip(newest[1], 90)
            stamps.append(newest[0])
        elif cinfos:
            row["last_commit_msg"] = clip(cinfos[0][1], 90)
        for x in prs:
            dt = parse_ts(x.get("updated_at"))
            if dt:
                stamps.append(dt)
        for x in merged:
            dt = parse_ts(x.get("merged_at"))
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
                owner_merge = bool(p.get("all_open_prs_wait")) and kind == "PR" and not wlab and not it.get("draft")
                if owner_merge:
                    wlab = "merge-needs-you"
                internal = kind == "PR" and has_label(labs, ["internal"]) and not it.get("draft")
                if has_label(labs, ipl):
                    row["in_progress"] += 1
                if internal and not wlab:
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
                    "why": "Needs your hands" if title_hitl else "Needs your OK to merge" if owner_merge else "Needs your decision" if wlab else "Ready to merge",
                    "age_days": days_between(now, created) if created else 0,
                    "_w": 0 if wlab else 1,
                })
        row["waiting_on_you"] = n_wait
        if keep_raw:
            row["_prs"], row["_issues"] = prs, issues

        if len(merged) >= 30:
            seen = [parse_ts(m.get("updated_at") or m.get("closed_at") or m.get("merged_at")) for m in merged]
            seen = [d for d in seen if d]
            if seen and min(seen) >= window:
                row["merged_7d_capped"] = True
                print("warning: %s merged.json has %d rows and none older than %d days; "
                      "merged_7d may be undercounted (fetch more pages)" % (name, len(merged), WINDOW_DAYS),
                      file=sys.stderr)

        merged_nums = set()
        for m in merged:
            dt = parse_ts(m.get("merged_at"))
            if not dt:
                continue
            if dt >= window:
                merged_nums.add(m.get("number"))
                row["merged_7d"] += 1
                activity.append({
                    "key": "%s:pr:%s" % (name, m.get("number")), "project": name,
                    "kind": "Merged PR", "title": clip(m.get("title", ""), 100),
                    "url": m.get("html_url", ""), "at": iso(dt), "_dt": dt,
                })
        for dt, msg, sha, url in cinfos:
            if not dt or dt < window:
                continue
            m = re.search(r"\(#(\d+)\)\s*$", msg) or re.match(r"Merge pull request #(\d+)", msg)
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
    if activity_cap:
        activity = activity[:activity_cap]
    for r in activity:
        r["days_ago"] = days_between(now, r.pop("_dt"))
    return projects, waiting, activity


# ---- v2: per-project snapshot docs (spec fleet-control-room F1) ----
MAX_PRS, MAX_ISSUES, MAX_ACTIVITY = 30, 50, 40
BODY_CAP, BODY_TRIM = 4000, 1000
DOC_LIMIT = 240 * 1024
BATCH_LIMIT = 900 * 1024
BATCH_WRITES = 50
NAME_RE = re.compile(r"[a-z0-9-]+", re.ASCII)
REPO_RE = re.compile(r"[\w.-]+/[\w.-]+", re.ASCII)


def doc_size(doc):
    return len(json.dumps(doc, ensure_ascii=False).encode("utf-8"))


def read_projects(path):
    """Normalise an ArtifactData list ({id, data}) or bare objects into (docs, warnings).
    Archived and invalid docs are skipped."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, dict):
        for key in ("docs", "documents", "items", "data"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if isinstance(raw, list) and raw and all(isinstance(x, dict) and x.get("type") == "text" and "text" in x for x in raw):
        raw = json.loads(raw[0]["text"])
        if isinstance(raw, dict):
            raw = raw.get("docs") or raw.get("documents") or raw.get("items") or []
    docs, warns, seen = [], [], set()
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict):
            continue
        if isinstance(x.get("data"), dict) and "id" in x:
            d = dict(x["data"])
            d["name"] = x["id"]
        else:
            d = dict(x)
        name, repo = d.get("name"), d.get("repo")
        if d.get("archived"):
            continue
        if not (isinstance(name, str) and NAME_RE.fullmatch(name)):
            warns.append("skipped project with invalid name %r" % (name,))
            continue
        if not (isinstance(repo, str) and REPO_RE.fullmatch(repo)):
            warns.append("skipped project %s: invalid repo %r" % (name, repo))
            continue
        if name in seen:
            warns.append("skipped duplicate project %s" % name)
            continue
        seen.add(name)
        docs.append({"name": name, "repo": repo, "blurb": str(d.get("blurb") or ""),
                     "all_open_prs_wait": bool(d.get("all_open_prs_wait"))})
    return docs, warns


def load_pr_detail(folder, number):
    path = os.path.join(folder, "pr_%s.json" % number)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        if isinstance(raw, list) and raw and isinstance(raw[0], dict) and raw[0].get("type") == "text":
            raw = json.loads(raw[0]["text"])
        if isinstance(raw, list) and len(raw) == 1:
            raw = raw[0]
        return raw if isinstance(raw, dict) else {}
    except (ValueError, OSError):
        return {}


def cut_body(text, n):
    text = text if isinstance(text, str) else ""
    return text[:n], len(text) > n


def fit_doc(doc):
    """Trim a snapshot doc under DOC_LIMIT. Returns True if it fits."""
    if doc_size(doc) <= DOC_LIMIT:
        return True
    for key in ("activity", "open_issues"):
        while doc[key] and doc_size(doc) > DOC_LIMIT:
            del doc[key][len(doc[key]) // 2:]
    if doc_size(doc) <= DOC_LIMIT:
        return True
    for limit in (BODY_TRIM, 0):
        for pr in doc["open_prs"]:
            pr["body"], cut = cut_body(pr["body"], limit)
            pr["body_truncated"] = pr["body_truncated"] or cut
        if doc_size(doc) <= DOC_LIMIT:
            return True
    return False


def build_snapshots(dumps, plist, config, now):
    """Return (docs, errors). docs maps name -> (op, doc): op 'set' for a full doc,
    'update' for a not-connected partial that must merge into the old snapshot."""
    stamp = iso(now)
    conf = dict(config, projects=[p for p in plist if os.path.isdir(os.path.join(dumps, p["name"]))
                                  and not os.path.isfile(os.path.join(dumps, p["name"], "not_connected.txt"))])
    rows, waiting, activity = build(dumps, conf, now, keep_raw=True, activity_cap=None)
    rows = {r["project"]: r for r in rows}
    docs, errors = {}, []
    for p in plist:
        name = p["name"]
        folder = os.path.join(dumps, name)
        reason = None
        if os.path.isfile(os.path.join(folder, "not_connected.txt")):
            reason = first_line(load_text(folder, "not_connected.txt")) or "Not connected"
        elif not os.path.isdir(folder):
            reason = "No data was fetched for this project"
        if reason is not None:
            docs[name] = ("update", {"updated_at": stamp, "connected": False, "not_connected_reason": reason})
            continue
        row = rows[name]
        prs, issues = row.pop("_prs"), row.pop("_issues")
        mine = [w for w in waiting if w["project"] == name]
        why = {w["number"]: w["why"] for w in mine if w["kind"] == "PR"}
        wait_issue = {w["number"] for w in mine if w["kind"] == "Issue"}
        pr_rows = []
        for x in prs:
            created = parse_ts(x.get("created_at"))
            detail = load_pr_detail(folder, x.get("number"))
            body, cut = cut_body(detail.get("body"), BODY_CAP)
            def blank(v):
                return v if isinstance(v, (int, str)) and not isinstance(v, bool) else ""
            pr_rows.append({
                "number": x.get("number"), "title": clip(x.get("title", ""), 200), "url": x.get("html_url", ""),
                "labels": labels_of(x), "draft": bool(x.get("draft")), "created_at": iso(created),
                "updated_at": iso(parse_ts(x.get("updated_at"))),
                "age_days": days_between(now, created) if created else 0,
                "why": why.get(x.get("number"), ""), "body": body, "body_truncated": cut,
                "additions": blank(detail.get("additions")), "deletions": blank(detail.get("deletions")),
                "mergeable_state": blank(detail.get("mergeable_state")),
            })
        issue_rows = []
        for x in issues:
            created = parse_ts(x.get("created_at"))
            issue_rows.append({
                "number": x.get("number"), "title": clip(x.get("title", ""), 200), "url": x.get("html_url", ""),
                "labels": labels_of(x), "created_at": iso(created),
                "age_days": days_between(now, created) if created else 0,
                "_w": 0 if x.get("number") in wait_issue else 1,
            })
        pr_rows.sort(key=lambda r: (0 if r["why"] else 1, r["age_days"], r["number"] or 0))
        issue_rows.sort(key=lambda r: (r["_w"], r["age_days"], r["number"] or 0))
        for r in issue_rows:
            del r["_w"]
        row.pop("open_prs"), row.pop("open_issues")
        row["blurb"] = p["blurb"]
        doc = dict(row, updated_at=stamp, open_pr_count=len(prs), open_issue_count=len(issues),
                   open_prs=pr_rows[:MAX_PRS], open_issues=issue_rows[:MAX_ISSUES],
                   activity=[dict(a) for a in activity if a["project"] == name][:MAX_ACTIVITY], waiting=mine)
        if "not_connected_reason" in doc:
            del doc["not_connected_reason"]
        if not fit_doc(doc):
            errors.append("%s: snapshot still %d bytes after trimming (limit %d); nothing written for it"
                          % (name, doc_size(doc), DOC_LIMIT))
            continue
        docs[name] = ("set", doc)
    return docs, errors


def plan_batches(docs, meta):
    """Group writes into batches under BATCH_LIMIT bytes; _meta alone in the last one."""
    batches, cur, size = [], [], 0
    for name in sorted(docs):
        op, doc = docs[name]
        w = {"action": op, "collection": "snapshot", "doc_id": name, "data": doc}
        n = doc_size(w)
        if cur and (size + n > BATCH_LIMIT or len(cur) >= BATCH_WRITES):
            batches.append({"bytes": size, "writes": cur})
            cur, size = [], 0
        cur.append(w)
        size += n
    if cur:
        batches.append({"bytes": size, "writes": cur})
    w = {"action": "set", "collection": "snapshot", "doc_id": "_meta", "data": meta}
    batches.append({"bytes": doc_size(w), "writes": [w]})
    return batches


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main_v2(a, config, now):
    plist, warns = read_projects(a.projects)
    for w in warns:
        print("warning: " + w, file=sys.stderr)
    docs, errors = build_snapshots(a.dumps, plist, config, now)
    meta = {"updated_at": iso(now)}
    for name, (op, doc) in docs.items():
        write_json(os.path.join(a.out, "snapshot", name + ".json"), doc)
        print("snapshot/%s: %s, %d bytes" % (name, op, doc_size(doc)))
    write_json(os.path.join(a.out, "snapshot", "_meta.json"), meta)
    write_json(os.path.join(a.out, "batches.json"), {"batches": plan_batches(docs, meta)})
    for e in errors:
        print("error: " + e, file=sys.stderr)
    return 1 if errors else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dumps", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--projects", help="ArtifactData list of the projects collection (v2 snapshot output)")
    ap.add_argument("--now")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    a = ap.parse_args(argv)
    with open(a.config, encoding="utf-8") as fh:
        config = json.load(fh)
    now = parse_ts(a.now) if a.now else datetime.now(timezone.utc)
    if now is None:
        ap.error("bad --now")
    if a.projects:
        return main_v2(a, config, now)
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
