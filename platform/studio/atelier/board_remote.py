"""Check explicitly configured Remote Control sessions; recover confirmed transport failures.

Run by the user's GUI launchd domain so credentials remain in macOS Keychain.
No prompt, transcript, access token, or refresh token is written to disk or logs.
"""
import ctypes
import fcntl
import json
import os
import plistlib
import re
import shlex
import signal
import socket
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path.home() / '.cache/atelier/remote-supervisor'
HOME = Path.home()
DOMAIN = f"gui/{os.getuid()}"
OWNED = {}
CLAUDE = '/opt/homebrew/bin/claude'
STARTUP_GRACE = 120
BAD_SAMPLES = 3
BAD_SECONDS = 60
RESTART_COOLDOWN = 300
MAX_RESTARTS_PER_HOUR = 3
TERM_GRACE = 90


class CheckError(Exception):
    """Only a fixed diagnostic category, never a credential-bearing error string."""


class Usage(ctypes.Structure):
    _fields_ = [("uuid", ctypes.c_ubyte * 16)] + [
        (name, ctypes.c_uint64) for name in (
            "user", "system", "idle_wakeups", "interrupt_wakeups", "pageins", "wired", "resident",
            "footprint", "started", "exited", "child_user", "child_system", "child_idle",
            "child_interrupt", "child_pageins", "child_elapsed", "read_bytes", "written_bytes",
        )
    ]


def process_start(pid):
    lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    lib.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    info = Usage()
    if lib.proc_pid_rusage(pid, 2, ctypes.byref(info)) or info.exited:
        return None
    return info.started


def command(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        raise CheckError("local_command_failed") from None
    if result.returncode:
        raise CheckError("local_command_failed")
    return result.stdout


def launch_pid(label):
    try:
        output = command(["/bin/launchctl", "print", f"{DOMAIN}/{label}"])
    except CheckError:
        return None
    match = re.search(r"^\s*pid = (\d+)\s*$", output, re.M)
    return int(match[1]) if match else None


def validate_service(label):
    name, cwd = OWNED[label]
    try:
        path = HOME / "Library/LaunchAgents" / f"{label}.plist"
        data = plistlib.loads(path.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        raise CheckError("service_configuration_invalid") from None
    expected = [CLAUDE, "remote-control", "--name", name,
                "--capacity", "1", "--permission-mode", "bypassPermissions"]
    argv = data.get("ProgramArguments", [])
    resumed = (len(argv) == 8 and argv[:4] == expected[:4]
               and argv[4] == "--session-id" and re.fullmatch(r"session_[A-Za-z0-9]{16,64}", argv[5])
               and argv[6:] == expected[6:])
    if (data.get("Label") != label or (argv != expected and not resumed)
            or data.get("WorkingDirectory") != str(cwd) or data.get("KeepAlive") is not True):
        raise CheckError("service_configuration_changed")
    return cwd


def inbox_responsive(cwd, server_pid):
    """Auth-only frame: checks the existing event loop without a prompt or new turn."""
    members = family(server_pid, process_table())
    directory = HOME / ".claude/sessions"
    for pid in members - {server_pid}:
        try:
            record = json.loads((directory / f"{pid}.json").read_text())
            if record.get("cwd") != str(cwd) or record.get("pid") != pid:
                continue
            # Registry timestamps are UTC, independently of the caller's locale.
            started = subprocess.check_output(["/bin/ps", "-p", str(pid), "-o", "lstart="],
                text=True, timeout=2, env={**os.environ, "TZ": "UTC", "LC_ALL": "C"}).strip()
            if record.get("procStart") != started:
                continue
            path = Path(record["messagingSocketPath"])
            metadata, parent = path.lstat(), path.parent.stat()
            if (not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700):
                return None
            keys = list(directory.glob(f"{pid}.*.key"))
            if len(keys) != 1:
                return None
            key = json.loads(keys[0].read_text())
            if key.get("procStart") != record.get("procStart"):
                return None
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(1)
                client.connect(str(path))
                client.sendall((json.dumps({"type": "auth", "token": key["peerToken"]}) + "\n").encode())
                time.sleep(.15)
                client.shutdown(socket.SHUT_WR)
                return client.recv(1) == b""
        except TimeoutError:
            return False
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            continue
    return None


def stale_read_only_query(pid):
    """A confirmed stuck session may abandon a bounded, non-mutating search."""
    try:
        elapsed = command(["/bin/ps", "-p", str(pid), "-o", "etime="]).strip()
        days, clock = elapsed.split("-", 1) if "-" in elapsed else ("0", elapsed)
        age = int(days) * 86400
        for component, scale in zip(reversed(clock.split(":")), (1, 60, 3600)):
            age += int(component) * scale
        argv = shlex.split(command(["/bin/ps", "-p", str(pid), "-o", "args="]).strip())
    except (CheckError, ValueError):
        return False
    if age < 120 or not argv:
        return False
    name = Path(argv[0]).name
    if name == "head":
        return True
    if name in ("find", "bfs"):
        return not any(value.startswith(("-exec", "-ok", "-delete", "-fprint", "-fls", "-fprintf"))
                       for value in argv[1:])
    return False


def pin_resume(label, session):
    """Use the native resume flag on recovery, retaining the existing remote URL."""
    if not re.fullmatch(r"cse_[A-Za-z0-9]{16,64}", session):
        raise CheckError("resume_identity_invalid")
    path = HOME / "Library/LaunchAgents" / f"{label}.plist"
    data = plistlib.loads(path.read_bytes())
    name, _ = OWNED[label]
    data["ProgramArguments"] = [CLAUDE, "remote-control", "--name", name,
        "--session-id", "session_" + session.removeprefix("cse_"), "--permission-mode", "bypassPermissions"]
    temporary = path.with_suffix(".plist.tmp")
    temporary.write_bytes(plistlib.dumps(data))
    temporary.chmod(0o600)
    temporary.replace(path)


def retiring_live(entry):
    pid, started = entry['pid'], entry['started']
    if not started or process_start(pid) != started:
        return False
    table = process_table()
    if pid not in table or table[pid][2] != entry['executable']:
        raise CheckError("retiring_process_changed")
    if (Path(table[pid][2]).name not in {'claude', 'claude.exe', 'zsh', 'bash', 'sh', 'sleep'}
            and not stale_read_only_query(pid)):
        raise CheckError("retiring_work_protected")
    if restart_blocker(pid, started, table):
        raise CheckError("retiring_work_protected")
    return True


def finish_retiring(state):
    retiring = state.get("retiring", [])
    for entry in retiring:
        # Only identities captured from this service before bootout may be signalled.
        if retiring_live(entry):
            os.kill(entry['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if all(process_start(e['pid']) != e['started'] for e in retiring):
            state.pop('retiring', None)
            return
        time.sleep(.1)
    for entry in retiring:
        if retiring_live(entry):
            os.kill(entry['pid'], signal.SIGKILL)
    time.sleep(.2)
    if any(process_start(e['pid']) == e['started'] for e in retiring):
        raise CheckError("waiting_for_retiring_workers")
    state.pop('retiring', None)


def recover_service(label, session, state):
    pid = launch_pid(label)
    table = process_table()
    started = process_start(pid) if pid is not None else None
    if not started or pid not in table:
        raise CheckError('process_changed')
    blocker = restart_blocker(pid, started, table)
    if blocker:
        raise CheckError('recovery_deferred_' + blocker)
    state['retiring'] = []
    for child in family(pid, table):
        child_start = process_start(child)
        if child in table and child_start:
            state['retiring'].append({'pid': child, 'started': child_start, 'executable': table[child][2]})
    if launch_pid(label) != pid or process_start(pid) != started:
        state.pop('retiring', None)
        raise CheckError('process_changed')
    pin_resume(label, session)
    # bootout removes supervision before termination, so a replacement cannot race
    # the previous worker on its transcript. launchd owns process-group cleanup.
    command(["/bin/launchctl", "bootout", f"{DOMAIN}/{label}"])
    finish_retiring(state)
    time.sleep(.3)  # launchd can acknowledge bootout before removing its registration.
    command(["/bin/launchctl", "bootstrap", DOMAIN,
             str(HOME / "Library/LaunchAgents" / f"{label}.plist")])


def current_session(cwd, pid):
    # Native pointer tracks replacement sessions too, without parsing private logs.
    project = re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))
    path = HOME / ".claude/projects" / project / "bridge-pointer.json"
    try:
        pointer = json.loads(path.read_text())
        started = subprocess.check_output(
            ["/bin/ps", "-p", str(pid), "-o", "lstart="], text=True, timeout=5,
            stderr=subprocess.DEVNULL, env={**os.environ, "TZ": "UTC", "LC_ALL": "C"},
        ).strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        raise CheckError("native_session_starting") from None
    session = pointer.get("sessionId", "")
    if (pointer.get("pid") != pid or pointer.get("procStart") != started
            or not re.fullmatch(r"session_[A-Za-z0-9]{16,64}", session)):
        raise CheckError("native_session_starting")
    return "cse_" + session.removeprefix("session_")


def keychain_token():
    try:
        raw = command(["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"])
        token = json.loads(raw).get("claudeAiOauth", {}).get("accessToken")
    except (CheckError, ValueError, AttributeError):
        raise CheckError("keychain_auth_unavailable") from None
    if not isinstance(token, str) or not token:
        raise CheckError("keychain_auth_unavailable")
    return token


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def remote_status(session, token):
    request = urllib.request.Request(
        f"https://api.anthropic.com/v1/code/sessions/{session}",
        headers={"Authorization": f"Bearer {token}", "anthropic-version": "2023-06-01",
                 "anthropic-client-platform": "claude_code_cli", "User-Agent": "claude-code-remote-watchdog"},
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=6) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise CheckError(f"remote_http_{exc.code}") from None
    except (OSError, ValueError, urllib.error.URLError):
        raise CheckError("remote_api_unavailable") from None
    if not isinstance(data, dict):
        raise CheckError("remote_response_invalid")
    record = data.get("response_shape", data.get("session", data))
    if not isinstance(record, dict):
        raise CheckError("remote_response_invalid")
    return record


def decide(state, now, identity, connection):
    """Pure recovery policy; API/auth errors reset consecutive failure evidence."""
    if state.get("identity") != identity:
        state.update(identity=identity, first_seen=now, bad_count=0, first_bad=None, pending=None)
    if connection == "connected":
        state.update(bad_count=0, first_bad=None, pending=None)
        return "healthy"
    if connection != "disconnected":
        state.update(bad_count=0, first_bad=None)
        return "unknown"
    state["bad_count"] = state.get("bad_count", 0) + 1
    if state.get("first_bad") is None:
        state["first_bad"] = now
    if now - state["first_seen"] < STARTUP_GRACE:
        return "startup_grace"
    if state["bad_count"] < BAD_SAMPLES or now - state["first_bad"] < BAD_SECONDS:
        return "confirming_disconnect"
    pending = state.get("pending")
    if pending:
        return "kill" if now - pending["time"] >= TERM_GRACE else "waiting_for_restart"
    restarts = [stamp for stamp in state.get("restarts", []) if 0 <= now - stamp < 3600]
    state["restarts"] = restarts
    if restarts and now - restarts[-1] < RESTART_COOLDOWN:
        return "restart_cooldown"
    if len(restarts) >= MAX_RESTARTS_PER_HOUR:
        return "restart_budget_wait"
    return "terminate"


def process_table():
    rows = command(["/bin/ps", "-axo", "pid=,ppid=,stat=,comm="])
    table = {}
    for line in rows.splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4 and fields[0].isdigit() and fields[1].isdigit():
            table[int(fields[0])] = (int(fields[1]), fields[2], fields[3])
    return table


def family(pid, table):
    found = {pid}
    while True:
        larger = found | {child for child, (parent, _, _) in table.items() if parent in found}
        if larger == found:
            return found
        found = larger


def restart_blocker(pid, started, table=None, locks=None, start_reader=process_start):
    """Read render records only; never acquire, truncate, remove or override their locks."""
    table = process_table() if table is None else table
    if pid not in table or start_reader(pid) != started:
        return "process_changed"
    descendants = family(pid, table)
    if locks is None:
        locks = []
        for name in ("render.lock", "render.small.lock"):
            path = HOME / ".cache/atelier" / name
            try:
                record = json.loads(path.read_text() or "{}")
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                return "render_record_unreadable"
            if not isinstance(record, dict):
                return "render_record_unreadable"
            locks.append(record)
    for record in locks:
        holder = record.get("pid")
        if isinstance(holder, int) and holder in descendants:
            live_start = start_reader(holder)
            if live_start is not None and record.get("started", live_start) == live_start:
                return "active_render_holder"
    # An actual tool subprocess may be doing valuable work even without a render lock.
    # Allow native Claude workers and idle shell/sleep waiters; defer every other tool.
    allowed = {"claude", "claude.exe", "zsh", "bash", "sh", "sleep"}
    for child in descendants:
        _, status, executable = table[child]
        if (child != pid and not status.startswith("Z") and Path(executable).name not in allowed
                and not stale_read_only_query(child)):
            return "active_tool_process"
    return None


def atomic_state(state):
    temporary = ROOT / "status.json.tmp"
    with temporary.open("w") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(0o600)
    temporary.replace(ROOT / "status.json")


def report(state, health, label):
    if state.get("health") != health:
        print(json.dumps({"time": int(time.time()), "session": OWNED[label][0], "health": health}), flush=True)
    state["health"] = health


def check_session(label, state, token):
    now = time.time()
    state['name'] = OWNED[label][0]
    state["checked_at"] = now
    pid = launch_pid(label)
    state["pid"] = pid
    if not pid:
        if state.get("pending"):
            validate_service(label)
            finish_retiring(state)
            command(["/bin/launchctl", "bootstrap", DOMAIN,
                str(HOME / "Library/LaunchAgents" / f"{label}.plist")])
        decide(state, now, None, None)
        report(state, "waiting_for_launchd", label)
        return
    started = process_start(pid)
    if not started:
        raise CheckError("process_identity_unavailable")
    identity = f"{pid}:{started}"
    cwd = validate_service(label)
    session = current_session(cwd, pid)
    state["url"] = "https://claude.ai/code/session_" + session.removeprefix("cse_")
    try:
        record = remote_status(session, token)
    except CheckError as exc:
        if str(exc) != "remote_http_401":
            raise
        record = remote_status(session, keychain_token())
    # Closing/archiving a session deliberately must not trigger an automatic takeover.
    session_status = str(record.get("status", "")).lower().rsplit("_", 1)[-1]
    connection = str(record.get("connection_status", "")).lower().rsplit("_", 1)[-1]
    state["connection"] = connection if connection in ("connected", "disconnected") else "unknown"
    responsive = inbox_responsive(cwd, pid)
    state["inbox_responsive"] = responsive
    if connection == "connected" and responsive is False:
        connection = "disconnected"
    if session_status not in ("active", "running"):
        connection = None
    action = decide(state, now, identity, connection)
    if action in ("terminate", "kill"):
        blocker = restart_blocker(pid, started)
        if blocker:
            report(state, "recovery_deferred_" + blocker, label)
            return
        if launch_pid(label) != pid or process_start(pid) != started:
            report(state, "process_changed", label)
            return
        signal = "SIGTERM" if action == "terminate" else "SIGKILL"
        if action == "terminate":
            state.setdefault("restarts", []).append(now)
            state["pending"] = {"time": now, "signal": signal}
            recover_service(label, session, state)
        else:
            command(["/bin/launchctl", "kill", signal, f"{DOMAIN}/{label}"])
            # Do not keep sending SIGKILL while launchd starts the replacement.
            state["pending"]["time"] = now
            state["pending"]["signal"] = signal
        report(state, "recovery_" + signal.lower(), label)
    else:
        report(state, action, label)


def configure(path):
    """Machine-specific labels, names and directories stay in a private config file."""
    global OWNED, ROOT, CLAUDE
    data = json.loads(Path(path).read_text())
    services = data.get('services')
    if not isinstance(services, dict) or not services:
        raise ValueError('remote-watch config requires explicitly owned services')
    configured = {}
    for label, item in services.items():
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,120}', label):
            raise ValueError('invalid owned launchd label')
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            raise ValueError('each owned service needs a name and working directory')
        cwd = Path(item['cwd'])
        if not cwd.is_absolute():
            raise ValueError('working directories must be absolute')
        configured[label] = (item['name'], cwd)
    executable = data.get('claude', CLAUDE)
    if not isinstance(executable, str) or not Path(executable).is_absolute():
        raise ValueError('Claude executable must be absolute')
    OWNED, ROOT, CLAUDE = configured, Path(path).resolve().parent, executable


def main(config=None):
    if config is not None:
        configure(config)
    os.umask(0o077)
    with (ROOT / "watchdog.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        try:
            state = json.loads((ROOT / "status.json").read_text())
            if not isinstance(state, dict) or not isinstance(state.get("sessions"), dict):
                state = {}
        except (OSError, ValueError):
            state = {}
        state.setdefault("sessions", {})
        try:
            token = keychain_token()
            auth_error = None
        except CheckError as exc:
            token, auth_error = None, str(exc)
        for label in OWNED:
            session_state = state["sessions"].setdefault(label, {})
            try:
                if auth_error:
                    raise CheckError(auth_error)
                check_session(label, session_state, token)
            except CheckError as exc:
                decide(session_state, time.time(), session_state.get("identity"), None)
                session_state["checked_at"] = time.time()
                report(session_state, str(exc), label)
            except Exception:
                # Unexpected failures are visible, but raw exception text could contain secrets.
                decide(session_state, time.time(), session_state.get("identity"), None)
                session_state["checked_at"] = time.time()
                report(session_state, "watchdog_check_failed", label)
            state["checked_at"] = time.time()
            atomic_state(state)
