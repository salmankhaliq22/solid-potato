"""Merge the base branch into the current branch (never rebase), run the check command, record a merge note.

    python scripts/merge_main.py --check-cmd CMD [--base origin/main] [--note DIR]
    python scripts/merge_main.py --no-check [--base origin/main] [--note DIR]

A check command is REQUIRED (git cannot see semantic clashes, for example two branches adding a package of the same
name, so the check runs after EVERY merge, not only after conflicts). `--no-check` is an explicit opt-out and is
written into the note. Refuses on tracked changes, on the base branch itself and on a detached HEAD (untracked files
such as check logs do not block). Runs `git merge --no-ff`. On conflict it lists the files, aborts nothing, and exits 3
so a person or the builder resolves them keeping BOTH sides' rows of append-style files, `git add`s them, and re-runs
this script (a finished merge is detected and committed; a failing commit, for example a rejecting pre-commit hook,
is reported, never hidden).
The note goes to `.orchestrator/runs/merge-notes/<branch>.md` by default (an ignored folder, so the tree stays clean).
Exit codes: 0 ok, 2 refused or git error, 3 conflicts, 4 check failed, 5 no check command given.
"""
import datetime
import os
import subprocess
import sys


def git(*a, check=True):
    return subprocess.run(["git", *a], capture_output=True, text=True, check=check)


def main(argv):
    base, note_dir, check_cmd, run_check = "origin/main", os.path.join(".orchestrator", "runs", "merge-notes"), None, True
    i = 0
    while i < len(argv):
        if argv[i] in ("--base", "--note", "--check-cmd"):
            if i + 1 >= len(argv):
                sys.stderr.write(f"{argv[i]} needs a value\n\n{__doc__}"); return 2
            if argv[i] == "--base":
                base = argv[i + 1]
            elif argv[i] == "--note":
                note_dir = argv[i + 1]
            else:
                check_cmd = argv[i + 1]
            i += 2
        elif argv[i] == "--no-check":
            run_check = False; i += 1
        else:
            sys.stderr.write(__doc__); return 2
    if run_check and not check_cmd:
        sys.stderr.write("refused: give the project check command with --check-cmd CMD (or opt out with --no-check)\n")
        return 5
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch in ("HEAD", "main", "master") or branch == base.split("/")[-1]:
        sys.stderr.write(f"refused: on '{branch}'. Merge main INTO a task branch.\n"); return 2
    unmerged = git("diff", "--name-only", "--diff-filter=U").stdout.split()
    merging = os.path.exists(os.path.join(git("rev-parse", "--git-dir").stdout.strip(), "MERGE_HEAD"))
    if unmerged:
        print("conflicts remain in:\n  " + "\n  ".join(unmerged)); return 3
    if not merging:
        if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
            sys.stderr.write("refused: tracked files have changes. Commit or stash your own changes first.\n"); return 2
        r = git("merge", "--no-ff", "--no-edit", base, check=False)
        if r.returncode != 0:
            files = git("diff", "--name-only", "--diff-filter=U").stdout.split()
            if not files:
                sys.stderr.write(r.stderr or r.stdout); return 2
            print("CONFLICTS (merge left open). Keep BOTH sides' rows in list-like files, then `git add` and\n"
                  "run this script again:\n  " + "\n  ".join(files)); return 3
    else:
        c = git("commit", "--no-edit", check=False)
        if c.returncode != 0:
            sys.stderr.write("refused: the merge commit failed; the merge is still open (MERGE_HEAD kept).\n"
                             + (c.stderr or c.stdout)); return 2
    if run_check:
        result = "OK" if subprocess.call(check_cmd, shell=True) == 0 else "FAILED"
    else:
        result = "skipped (--no-check)"
    sha = git("rev-parse", "--short", "HEAD").stdout.strip()
    os.makedirs(note_dir, exist_ok=True)
    path = os.path.join(note_dir, f"{branch.replace('/', '-')}.md")
    row = f"| {datetime.date.today()} | {base} | {sha} | {result} |\n"
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:  # append-only note
        if new:
            f.write(f"# Merge notes for {branch}\n\n| date | base | merge commit | check |\n|---|---|---|---|\n")
        f.write(row)
    print(f"merged {base} into {branch} at {sha}; check: {result}; note: {path}")
    return 4 if result == "FAILED" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
