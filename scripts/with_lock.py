"""Serialise a command behind a named lock, with safe stale-lock takeover.

    python scripts/with_lock.py NAME [--timeout S] [--lock-dir DIR] -- command args...

NAME: letters, digits, '.', '_', '-' (max 64, no '..'). Default lock folder: `<git common dir>/orchestrator-locks`, so
every worktree of one repository shares the same lock (one check at a time across parallel builders); outside git it
falls back to `$CLAUDE_PROJECT_DIR/.orchestrator/locks`, then `./.orchestrator/locks`.
The lock is a directory holding owner.json {host, pid, ctime, token, since}; it is built under a temporary name and
renamed into place, so a lock never exists without its owner file. A lock is STALE only when it is on this host AND
(its pid is gone OR the pid's start time differs from the recorded one, which means the pid was reused). Same-host
liveness unknown -> treated as alive. A lock from another host is never taken. Takeover happens under a short
`NAME.lock.takeover` mutex and re-checks the owner token there, so two waiters can never both take over (one of them
would otherwise delete the other's fresh lock). Nothing here kills a process. On Windows the command is resolved with
shutil.which, so `npm` finds `npm.cmd`.
Exit codes: the command's code; 75 = timed out waiting; 2 = usage/error; 127 = command not found.
Why: a bare `until mkdir x.lock; do sleep; done` leaves everyone waiting forever after a crash.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]

NAME_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MUTEX_STALE_S = 30


def proc_state(pid):
    """Return (state, ctime): state is 'alive', 'gone' or 'unknown'; ctime is a float or None."""
    if sys.platform == "win32":
        h = _k32.OpenProcess(0x1000, False, pid)
        if not h:
            return ("gone", None) if ctypes.get_last_error() == 87 else ("unknown", None)
        try:
            code = wintypes.DWORD()
            if _k32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value != 259:
                return "gone", None
            c, e, k, u = (wintypes.FILETIME() for _ in range(4))
            if _k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
                ticks = (c.dwHighDateTime << 32) | c.dwLowDateTime
                return "alive", ticks / 1e7 - 11644473600
            return "alive", None
        finally:
            _k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "gone", None
    except PermissionError:
        return "alive", None
    try:
        with open(f"/proc/{pid}/stat") as f:
            return "alive", float(f.read().rsplit(")", 1)[1].split()[19])
    except OSError:
        return "alive", None


def is_stale(owner: dict, host: str) -> bool:
    if owner.get("host") != host:
        return False
    state, ctime = proc_state(int(owner.get("pid", -1)))
    if state == "gone":
        return True
    rec = owner.get("ctime")
    if state == "alive" and rec is not None and ctime is not None and abs(ctime - rec) > 2.0:
        return True  # pid reused by another process
    return False


def read_owner(lock: str):
    try:
        with open(os.path.join(lock, "owner.json")) as f:
            o = json.load(f)
        return o if isinstance(o, dict) else None
    except (OSError, ValueError):
        return None


def _bury(path: str):
    """Rename then delete, so nobody ever sees a half-deleted lock without its owner file."""
    grave = f"{path}.stale-{uuid.uuid4().hex}"
    os.rename(path, grave)
    shutil.rmtree(grave, ignore_errors=True)


def try_takeover(lock: str, host: str, seen_token) -> bool:
    """Remove a stale lock, but only under the takeover mutex and only if it is STILL the owner we judged stale."""
    mutex = lock + ".takeover"
    try:
        os.mkdir(mutex)
    except FileExistsError:
        try:  # a takeover holder that crashed: its mutex is only held for milliseconds
            if time.time() - os.path.getmtime(mutex) > MUTEX_STALE_S:
                shutil.rmtree(mutex, ignore_errors=True)
        except OSError:
            pass
        return False
    try:
        owner = read_owner(lock)
        if owner is None:
            if seen_token is not None or not os.path.isdir(lock) or time.time() - os.path.getmtime(lock) <= 30:
                return False
        elif owner.get("token") != seen_token or not is_stale(owner, host):
            return False
        _bury(lock)
        return True
    except OSError:
        return False
    finally:
        shutil.rmtree(mutex, ignore_errors=True)


def acquire(lock: str, timeout: float, host: str) -> dict:
    deadline = time.monotonic() + timeout
    me = {"host": host, "pid": os.getpid(), "ctime": proc_state(os.getpid())[1],
          "token": uuid.uuid4().hex, "since": time.time()}
    while True:
        tmp = f"{lock}.new-{me['token']}"
        os.mkdir(tmp)
        with open(os.path.join(tmp, "owner.json"), "w") as f:
            json.dump(me, f)
        try:
            os.rename(tmp, lock)  # fails if the lock exists (Windows: always; POSIX: target is never empty)
            return me
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
            if not os.path.isdir(lock):
                time.sleep(0.05)
                continue
        owner = read_owner(lock)
        if owner is None:
            try:
                if time.time() - os.path.getmtime(lock) > 30 and try_takeover(lock, host, None):
                    continue
            except OSError:
                continue
        elif is_stale(owner, host):
            if try_takeover(lock, host, owner.get("token")):
                sys.stderr.write(f"with_lock: took over stale lock held by pid {owner.get('pid')}\n")
                continue
        if time.monotonic() > deadline:
            who = f"pid {owner.get('pid')} on {owner.get('host')}" if owner else "unknown"
            sys.stderr.write(f"with_lock: timed out waiting for {lock} (held by {who})\n")
            raise TimeoutError
        time.sleep(0.2)


def release(lock: str, me: dict):
    o = read_owner(lock)  # remove only our own lock (file read and closed first: Windows cannot delete open files)
    if o and o.get("token") == me["token"]:
        try:
            _bury(lock)
        except OSError:
            pass


def default_lock_dir() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return os.path.join(os.path.abspath(r.stdout.strip()), "orchestrator-locks")
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.join(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd(), ".orchestrator", "locks")


def usage(msg: str) -> int:
    sys.stderr.write(f"with_lock: {msg}\n\n{__doc__}")
    return 2


def main(argv):
    if "--" not in argv:
        return usage("missing '--' before the command")
    i = argv.index("--")
    head, cmd = argv[:i], argv[i + 1:]
    if not head or not cmd:
        return usage("need a lock NAME and a command")
    name = head[0]
    if not NAME_RX.match(name) or ".." in name:
        return usage(f"bad lock name {name!r}: use letters, digits, '.', '_', '-'")
    timeout, lock_dir = 1800.0, None
    k = 1
    while k < len(head):
        if head[k] in ("--timeout", "--lock-dir"):
            if k + 1 >= len(head):
                return usage(f"{head[k]} needs a value")
            if head[k] == "--timeout":
                try:
                    timeout = float(head[k + 1])
                except ValueError:
                    return usage("--timeout needs a number of seconds")
            else:
                lock_dir = head[k + 1]
            k += 2
        else:
            return usage(f"unknown option {head[k]!r}")
    lock_dir = lock_dir or default_lock_dir()
    exe = shutil.which(cmd[0])
    if exe is None:
        sys.stderr.write(f"with_lock: command not found: {cmd[0]}\n")
        return 127
    cmd = [exe] + cmd[1:]
    os.makedirs(lock_dir, exist_ok=True)
    lock = os.path.join(lock_dir, name + ".lock")
    try:
        me = acquire(lock, timeout, socket.gethostname())
    except TimeoutError:
        return 75
    try:
        return subprocess.call(cmd)
    finally:
        release(lock, me)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
