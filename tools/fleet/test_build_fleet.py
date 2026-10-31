import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

import build_fleet as bf

NOW = "2026-10-31T12:00:00Z"
CFG = {
    "projects": [
        {"name": "alpha", "repo": "o/alpha", "blurb": "A"},
        {"name": "beta", "repo": "o/beta", "blurb": ""},
        {"name": "gone", "repo": "o/gone", "blurb": ""},
    ],
    "waiting_labels": ["needs-owner", "needs-parent", "owner-only", "HITL"],
    "in_progress_labels": ["in-progress", "review"],
    "active_days": 2,
    "quiet_days": 7,
}


def commit(sha, msg, date):
    return {"sha": sha, "html_url": "http://c/" + sha, "commit": {"message": msg, "author": {"date": date}}}


def pr(n, labels=None, draft=False, created="2026-10-20T12:00:00Z", updated="2026-10-21T12:00:00Z", **kw):
    d = {"number": n, "title": "PR %d" % n, "html_url": "http://pr/%d" % n, "labels": labels,
         "draft": draft, "created_at": created, "updated_at": updated}
    d.update(kw)
    return d


class Base(unittest.TestCase):
    def run_build(self, files):
        with tempfile.TemporaryDirectory() as d:
            for proj, fs in files.items():
                os.makedirs(os.path.join(d, proj))
                for name, content in fs.items():
                    with open(os.path.join(d, proj, name), "w") as fh:
                        fh.write(content if isinstance(content, str) else json.dumps(content))
            now = bf.parse_ts(NOW)
            projects, waiting, activity = bf.build(d, CFG, now)
        return {p["project"]: p for p in projects}, waiting, activity


class Normalise(unittest.TestCase):
    def test_shapes(self):
        rows = [{"number": 1}]
        self.assertEqual(bf.normalise(rows), rows)
        for k in ("items", "issues", "pull_requests", "data"):
            self.assertEqual(bf.normalise({k: rows}), rows)
        self.assertEqual(bf.normalise([{"type": "text", "text": json.dumps(rows)}]), rows)
        self.assertEqual(bf.normalise([{"type": "text", "text": json.dumps({"issues": rows})}]), rows)
        self.assertEqual(bf.normalise("garbage"), [])
        self.assertEqual(bf.normalise(None), [])

    def test_labels(self):
        self.assertEqual(bf.labels_of({"labels": ["a", {"name": "b"}]}), ["a", "b"])
        self.assertEqual(bf.labels_of({"labels": None}), [])
        self.assertEqual(bf.labels_of({}), [])


class Build(Base):
    def test_status_thresholds_and_not_connected(self):
        p, _, _ = self.run_build({
            "alpha": {"commits.json": [commit("a" * 40, "x", "2026-10-30T12:00:00Z")]},
            "beta": {"commits.json": [commit("b" * 40, "x", "2026-10-26T12:00:00Z")]},
        })
        self.assertEqual(p["alpha"]["status"], "Active")
        self.assertEqual(p["alpha"]["last_activity_days"], 1.0)
        self.assertEqual(p["beta"]["status"], "Quiet")
        self.assertEqual(p["gone"]["status"], "Not connected")
        self.assertFalse(p["gone"]["connected"])
        self.assertEqual(p["gone"]["last_activity_days"], -1)

    def test_idle_and_pr_updates_count(self):
        p, _, _ = self.run_build({
            "alpha": {"commits.json": [commit("a" * 40, "x", "2026-09-01T00:00:00Z")]},
            "beta": {"prs.json": [pr(1, updated="2026-10-31T00:00:00Z")]},
        })
        self.assertEqual(p["alpha"]["status"], "Idle")
        self.assertEqual(p["beta"]["status"], "Active")

    def test_all_open_prs_wait(self):
        global CFG
        old = CFG
        CFG = dict(old, projects=[dict(old["projects"][0], all_open_prs_wait=True)])
        try:
            p, w, _ = self.run_build({"alpha": {"prs.json": [
                pr(1, None), pr(2, None, draft=True), pr(3, ["needs-owner"]), pr(4, ["internal"])]}})
        finally:
            CFG = old
        by = {r["number"]: r for r in w}
        self.assertEqual(sorted(by), [1, 3, 4])
        self.assertEqual((by[1]["label"], by[1]["why"]), ("merge-needs-you", "Needs your OK to merge"))
        self.assertEqual(by[3]["label"], "needs-owner")
        self.assertEqual(p["alpha"]["waiting_on_you"], 3)

    def test_waiting_sort_and_internal(self):
        p, w, _ = self.run_build({"alpha": {
            "prs.json": [
                pr(1, ["internal"], created="2026-10-01T12:00:00Z"),
                pr(2, [{"name": "needs-owner"}], created="2026-10-25T12:00:00Z"),
                pr(3, ["internal"], draft=True),
                pr(4, None),
            ],
            "issues.json": {"issues": [
                {"number": 9, "title": "I", "labels": ["HITL"], "created_at": "2026-10-10T12:00:00Z"},
                {"number": 2, "title": "dup of pr", "labels": ["HITL"], "created_at": "2026-10-10T12:00:00Z"},
            ]},
        }})
        keys = [r["key"] for r in w]
        self.assertEqual(keys, ["alpha#9", "alpha#2", "alpha#1"])
        self.assertEqual(w[0]["why"], "Needs your decision")
        self.assertEqual(w[2]["label"], "internal")
        self.assertEqual(w[2]["why"], "Ready to merge")
        self.assertEqual(w[2]["age_days"], 30.0)
        a = p["alpha"]
        self.assertEqual((a["open_prs"], a["open_issues"], a["waiting_on_you"], a["ready_internal"]), (4, 1, 2, 1))

    def test_title_hitl(self):
        p, w, _ = self.run_build({"alpha": {
            "issues.json": [{"number": 5, "title": "[P1] [HITL] M-01 Google setup", "labels": [],
                             "created_at": "2026-10-30T12:00:00Z"}],
            "prs.json": [pr(6, None, **{"title": "thing [hitl]"})],
        }})
        self.assertEqual(sorted(r["key"] for r in w), ["alpha#5", "alpha#6"])
        for r in w:
            self.assertEqual(r["label"], "HITL")
            self.assertEqual(r["why"], "Needs your hands")
        self.assertEqual(p["alpha"]["waiting_on_you"], 2)

    def test_state_md(self):
        state = ("stage: building  extra\n- next_step: ship it\nblockers: <none | list>\n")
        p, _, _ = self.run_build({"alpha": {"state.md": state}})
        self.assertEqual(p["alpha"]["stage"], "building")
        self.assertEqual(p["alpha"]["next_step"], "ship it")
        self.assertEqual(p["alpha"]["blockers"], "")

    def test_dedupe_and_window(self):
        merged = [
            pr(7, merged_at="2026-10-30T12:00:00Z", closed_at="2026-10-30T12:00:00Z"),
            pr(8, merged_at="2026-10-01T12:00:00Z", closed_at="2026-10-01T12:00:00Z"),
            pr(9, merged_at=None, closed_at="2026-10-30T12:00:00Z"),
        ]
        commits = [
            commit("1" * 40, "Add thing (#7)\n\nbody", "2026-10-30T11:00:00Z"),
            commit("2" * 40, "Direct commit", "2026-10-29T12:00:00Z"),
            commit("3" * 40, "Old commit", "2026-10-01T12:00:00Z"),
        ]
        p, _, act = self.run_build({"alpha": {"merged.json": merged, "commits.json": commits}})
        self.assertEqual(p["alpha"]["merged_7d"], 1)
        self.assertEqual([r["key"] for r in act], ["alpha:pr:7", "alpha:c:2222222"])
        self.assertEqual(act[0]["kind"], "Merged PR")
        self.assertEqual(act[0]["days_ago"], 1.0)
        self.assertEqual(act[1]["kind"], "Commit")

    def test_activity_cap(self):
        commits = [commit("%040d" % i, "c%d" % i, "2026-10-30T12:00:00Z") for i in range(50)]
        _, _, act = self.run_build({"alpha": {"commits.json": commits}})
        self.assertEqual(len(act), 40)

    def test_merge_commit_dedupe_and_window_scope(self):
        merged = [pr(7, merged_at="2026-10-30T12:00:00Z"), pr(8, merged_at="2026-10-01T12:00:00Z")]
        commits = [
            commit("1" * 40, "Merge pull request #7 from o/branch", "2026-10-30T11:00:00Z"),
            commit("2" * 40, "Merge pull request #8 from o/old", "2026-10-30T10:00:00Z"),
        ]
        _, _, act = self.run_build({"alpha": {"merged.json": merged, "commits.json": commits}})
        self.assertEqual([r["key"] for r in act], ["alpha:pr:7", "alpha:c:2222222"])

    def test_capped_flag_and_warning(self):
        import contextlib
        import io
        merged = [pr(i, merged_at="2026-10-30T12:00:00Z", updated_at="2026-10-30T12:00:00Z") for i in range(1, 31)]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            p, _, _ = self.run_build({"alpha": {"merged.json": merged}})
        self.assertTrue(p["alpha"]["merged_7d_capped"])
        self.assertIn("alpha", err.getvalue())
        merged[-1]["updated_at"] = "2026-10-01T12:00:00Z"
        p, _, _ = self.run_build({"alpha": {"merged.json": merged}})
        self.assertFalse(p["alpha"]["merged_7d_capped"])

    def test_last_commit_is_newest_by_date(self):
        commits = [commit("1" * 40, "older", "2026-10-29T12:00:00Z"),
                   commit("2" * 40, "newest", "2026-10-30T12:00:00Z")]
        p, _, _ = self.run_build({"alpha": {"commits.json": commits}})
        self.assertEqual(p["alpha"]["last_commit_msg"], "newest")
        self.assertEqual(p["alpha"]["last_activity_at"], "2026-10-30T12:00:00Z")

    def test_closed_unmerged_does_not_count_as_activity(self):
        merged = [pr(9, merged_at=None, updated_at="2026-10-31T11:00:00Z", closed_at="2026-10-31T11:00:00Z")]
        p, _, _ = self.run_build({"alpha": {"merged.json": merged}})
        self.assertEqual(p["alpha"]["last_activity_at"], "")
        self.assertEqual(p["alpha"]["status"], "Idle")

    def test_ready_internal_excludes_waiting_label(self):
        prs = [pr(1, labels=["internal"]), pr(2, labels=["internal", "needs-owner"])]
        p, _, _ = self.run_build({"alpha": {"prs.json": prs}})
        self.assertEqual(p["alpha"]["ready_internal"], 1)
        self.assertEqual(p["alpha"]["waiting_on_you"], 1)


PLIST = [{"name": "alpha", "repo": "o/alpha", "blurb": "A", "all_open_prs_wait": False},
         {"name": "beta", "repo": "o/beta", "blurb": "", "all_open_prs_wait": False}]


class Snapshots(unittest.TestCase):
    def snap(self, files, plist=PLIST, cfg=CFG):
        with tempfile.TemporaryDirectory() as d:
            for proj, fs in files.items():
                os.makedirs(os.path.join(d, proj))
                for name, content in fs.items():
                    with open(os.path.join(d, proj, name), "w", encoding="utf-8") as fh:
                        fh.write(content if isinstance(content, str) else json.dumps(content))
            import contextlib
            import io
            with contextlib.redirect_stderr(io.StringIO()):
                return bf.build_snapshots(d, plist, cfg, bf.parse_ts(NOW))

    def test_basic_doc_counts_before_cap_and_pr_fields(self):
        prs = [pr(i, ["needs-owner"] if i == 1 else None) for i in range(1, 36)]
        issues = [{"number": 100 + i, "title": "I", "labels": [], "created_at": "2026-10-20T12:00:00Z"} for i in range(60)]
        docs, errs = self.snap({"alpha": {
            "prs.json": prs, "issues.json": issues,
            "pr_1.json": {"body": "x" * 5000, "additions": 7, "deletions": 3, "mergeable_state": "dirty"},
            "pr_2.json": [{"type": "text", "text": json.dumps({"body": "hi", "additions": 0, "deletions": 0, "mergeable_state": "clean"})}],
        }, "beta": {}})
        self.assertEqual(errs, [])
        op, d = docs["alpha"]
        self.assertEqual(op, "set")
        self.assertEqual((d["open_pr_count"], d["open_issue_count"]), (35, 60))
        self.assertEqual((len(d["open_prs"]), len(d["open_issues"])), (30, 50))
        self.assertEqual(d["updated_at"], NOW)
        self.assertTrue(d["connected"])
        first = d["open_prs"][0]
        self.assertEqual(first["number"], 1)  # waiting first
        self.assertEqual(len(first["body"]), 4000)
        self.assertTrue(first["body_truncated"])
        self.assertEqual((first["additions"], first["deletions"], first["mergeable_state"]), (7, 3, "dirty"))
        self.assertEqual(first["why"], "Needs your decision")
        p2 = [x for x in d["open_prs"] if x["number"] == 2][0]
        self.assertEqual((p2["body"], p2["additions"], p2["mergeable_state"]), ("hi", 0, "clean"))

    def test_missing_pr_detail_is_blank(self):
        docs, _ = self.snap({"alpha": {"prs.json": [pr(1)]}, "beta": {}})
        x = docs["alpha"][1]["open_prs"][0]
        self.assertEqual((x["body"], x["additions"], x["deletions"], x["mergeable_state"]), ("", "", "", ""))

    def test_waiting_matches_v1_rows(self):
        files = {"alpha": {"prs.json": [pr(1, ["internal"]), pr(2, ["needs-owner"])]}, "beta": {}}
        docs, _ = self.snap(files)
        with tempfile.TemporaryDirectory() as d:
            for proj, fs in files.items():
                os.makedirs(os.path.join(d, proj))
                for n, c in fs.items():
                    open(os.path.join(d, proj, n), "w").write(json.dumps(c))
            _, w, _ = bf.build(d, dict(CFG, projects=PLIST), bf.parse_ts(NOW))
        self.assertEqual(docs["alpha"][1]["waiting"], [r for r in w if r["project"] == "alpha"])
        self.assertEqual(len(docs["alpha"][1]["waiting"]), 2)

    def test_not_connected_partial(self):
        docs, errs = self.snap({"alpha": {"not_connected.txt": "no access\nsecond"}, "beta": {}})
        op, d = docs["alpha"]
        self.assertEqual(op, "update")
        self.assertEqual(d, {"updated_at": NOW, "connected": False, "not_connected_reason": "no access"})

    def test_missing_folder_is_not_connected(self):
        docs, _ = self.snap({"alpha": {}})
        self.assertFalse(docs["beta"][1]["connected"])

    def test_worst_case_under_limit(self):
        prs = [pr(i, ["needs-owner"]) for i in range(1, 201)]
        files = {"pr_%d.json" % i: {"body": "é" * 60000, "additions": 1, "deletions": 1, "mergeable_state": "clean"}
                 for i in range(1, 201)}
        issues = [{"number": 1000 + i, "title": "t" * 150, "labels": ["a"] * 5, "created_at": "2026-10-01T00:00:00Z"} for i in range(500)]
        commits = [commit("%040d" % i, "m" * 90, "2026-10-30T12:00:00Z") for i in range(300)]
        files.update({"prs.json": prs, "issues.json": issues, "commits.json": commits})
        docs, errs = self.snap({"alpha": files, "beta": {}})
        self.assertEqual(errs, [])
        d = docs["alpha"][1]
        self.assertLessEqual(bf.doc_size(d), bf.DOC_LIMIT)
        self.assertEqual(d["open_pr_count"], 200)
        self.assertEqual(len(d["open_prs"]), 30)

    def test_trim_chain_drops_bodies_then_fails_naming_project(self):
        import unittest.mock as mock
        prs = [pr(i) for i in range(1, 6)]
        files = {"pr_%d.json" % i: {"body": "x" * 4000} for i in range(1, 6)}
        files["prs.json"] = prs
        with mock.patch.object(bf, "DOC_LIMIT", 1500):
            docs, errs = self.snap({"alpha": files, "beta": {}})
        self.assertNotIn("alpha", docs)
        self.assertIn("beta", docs)
        self.assertEqual(len(errs), 1)
        self.assertIn("alpha", errs[0])
        # limit loose enough that dropping bodies suffices
        with mock.patch.object(bf, "DOC_LIMIT", 4000):
            docs, errs = self.snap({"alpha": files, "beta": {}})
        self.assertEqual(errs, [])
        self.assertTrue(all(x["body"] == "" and x["body_truncated"] for x in docs["alpha"][1]["open_prs"]))

    def test_read_projects(self):
        exp = [
            {"id": "a", "data": {"repo": "o/a", "blurb": "x", "archived": False, "all_open_prs_wait": True}},
            {"id": "b", "data": {"repo": "o/b", "archived": True}},
            {"id": "Bad Name", "data": {"repo": "o/c"}},
            {"id": "c", "data": {"repo": "not a repo"}},
            {"name": "d", "repo": "o/d.git"},
            {"id": "e"},
        ]
        for payload in (exp, {"docs": exp}):
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                json.dump(payload, fh)
            import contextlib
            import io
            with contextlib.redirect_stderr(io.StringIO()):
                plist, warns = bf.read_projects(fh.name)
            os.unlink(fh.name)
            self.assertEqual([p["name"] for p in plist], ["a", "d"])
            self.assertTrue(plist[0]["all_open_prs_wait"])
            self.assertEqual(len(warns), 3)

    def test_batches_meta_last_and_size(self):
        docs = {"n%d" % i: ("set", {"x": "y" * 300000}) for i in range(7)}
        bs = bf.plan_batches(docs, {"updated_at": NOW})
        self.assertEqual(bs[-1]["writes"][0]["doc_id"], "_meta")
        self.assertEqual(len(bs[-1]["writes"]), 1)
        self.assertTrue(all(b["bytes"] < 1024 * 1024 for b in bs))
        self.assertEqual(sum(len(b["writes"]) for b in bs[:-1]), 7)

    def test_main_writes_files(self):
        with tempfile.TemporaryDirectory() as t:
            dumps, out = os.path.join(t, "d"), os.path.join(t, "o")
            os.makedirs(os.path.join(dumps, "alpha"))
            proj = os.path.join(t, "p.json")
            json.dump([{"id": "alpha", "data": {"repo": "o/alpha"}}], open(proj, "w"))
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                rc = bf.main(["--dumps", dumps, "--out", out, "--projects", proj, "--now", NOW])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(os.path.join(out, "snapshot", "alpha.json")))
            self.assertEqual(json.load(open(os.path.join(out, "snapshot", "_meta.json"))), {"updated_at": NOW})
            self.assertTrue(os.path.isfile(os.path.join(out, "batches.json")))


if __name__ == "__main__":
    unittest.main()
