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


if __name__ == "__main__":
    unittest.main()
