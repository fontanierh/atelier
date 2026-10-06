"""Run one heavy child (Unreal, a Blender render) under the machine's render lock and the independent memory guard.

    python -m atelier.safety.guarded --report DIR [--timeout SECONDS] [--purpose TEXT] [--no-lock]
                                     [--small GIB] [--kind job|game|compile] -- COMMAND ...

Two protections, because they do different jobs:

* `render_lock` gives this process a render slot, so a second harness in another checkout is refused instead of
  launching alongside. A per-process memory ceiling cannot stop two Unreals from exhausting shared memory between them.
  The big slot is the machine's only one unless two are switched on (see `render_lock`); `small_gib` (`--small`), the
  job's expected peak, lets a small job use the second, small slot beside a big one.
* `memory_guard` runs as a sibling watching this exact child, pinned to its pid and start time, at a 10 GiB ceiling,
  or 4 GiB in the small slot.

Ownership is registered the instant the child exists, so every later failure still reaps it: the monitor failing to
start, an exception, Ctrl-C, or the deadline. `timeout=0` means no deadline (interactive play); the ceiling is never
lifted either way.

A launcher whose heavy work runs in descendants (UAT's BuildCookRun starts the cook as UnrealEditor-Cmd, and
compilers) passes `watch`: every descendant is recorded by pid and start time as it appears, and those whose executable
name is in `watch` get their own memory guard (`memory-health-<name>-<pid>.json`) under the same ceiling and the same
outer slot turn. When the run ends, for any reason, recorded descendants still running as the same processes are stopped,
deepest first, before the child itself; nothing else is ever signalled. `progress` prints a line that often while the child is quiet.
"""
import argparse, os, signal, subprocess, sys, time
from contextlib import ExitStack
from pathlib import Path

from .guard import attach as attach_memory_guard, reap
from .memory_guard import usage
from .render_lock import KINDS, SMALL_LIMIT_GIB, render_lock
from .process import spawn


def descendants(root):
    """(pid, executable name) of every live descendant of `root`, parents before children."""
    listing = subprocess.run(['ps', '-axo', 'pid=,ppid=,comm='], capture_output=True, text=True).stdout
    children = {}
    for line in listing.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append((int(parts[0]), os.path.basename(parts[2].strip())))
    found, queue = [], [root]
    while queue:
        for pid, name in children.get(queue.pop(0), []):
            found.append((pid, name)); queue.append(pid)
    return found


class Descendants:
    """The child's process tree as it grows: identities recorded on sight, heavy ones guarded."""
    def __init__(self, root, folder, watch, duration, limit_gib, stack):
        self.root, self.folder, self.watch, self.duration, self.limit_gib, self.stack = root, folder, set(watch), duration, limit_gib, stack
        self.owned, self.guarded = {}, []

    def poll(self):
        for pid, name in descendants(self.root):
            if pid in self.owned:
                continue
            try:
                self.owned[pid] = usage(pid).started
            except ProcessLookupError:
                continue
            if name in self.watch:
                monitor = self.stack.enter_context(attach_memory_guard(
                    pid, self.folder/f'memory-health-{name}-{pid}.json', duration=self.duration, limit_gib=self.limit_gib))
                self.guarded.append((pid, name, monitor))
                print(f'guarding {name} pid {pid}, report {self.folder/f"memory-health-{name}-{pid}.json"}', flush=True)

    def same(self, pid):
        try:
            return usage(pid).started == self.owned[pid]
        except ProcessLookupError:
            return False

    def unwind(self, grace=10.):
        """Stop recorded descendants that are still the same processes, deepest first."""
        live = [pid for pid in reversed(list(self.owned)) if self.same(pid)]
        for pid in live:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic()+grace
        while time.monotonic() < deadline and any(self.same(pid) for pid in live):
            time.sleep(.2)
        for pid in live:
            if self.same(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def last_line(path):
    try:
        with open(path, 'rb') as handle:
            handle.seek(max(0, os.path.getsize(path)-4096))
            lines = [line for line in handle.read().decode(errors='ignore').splitlines() if line.strip()]
        return lines[-1].strip()[:160] if lines else ''
    except OSError:
        return ''


def run(command, folder, timeout=0., purpose=None, lock=True, env=None, limit_gib=10., small_gib=None, kind='job',
        on_slot=None, watch=(), progress=0.):
    """Run `command` to completion and return its exit status. `small_gib` and `kind` go to `render_lock`;
    `on_slot(slot, why)` hears which slot the child runs in."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    horizon = timeout if timeout > 0 else None
    with ExitStack() as stack:
        slot = None
        if lock:
            def taken(name, why):
                nonlocal slot
                slot = name
                if on_slot is not None:
                    on_slot(name, why)
            stack.enter_context(render_lock(purpose or Path(command[0]).name, small_gib=small_gib, kind=kind,
                                            on_slot=taken))
        if slot == 'small':
            limit_gib = min(limit_gib, SMALL_LIMIT_GIB)
        log = stack.enter_context((folder/'stdout.log').open('w'))
        child = spawn(command, kind=kind, stdout=log, stderr=subprocess.STDOUT, env=env)
        stack.callback(reap, child)
        where = f', small render slot, {limit_gib:g} GiB limit' if slot == 'small' else ''
        print(f'pid {child.pid}, guard report {folder/"memory-health.json"}{where}', flush=True)
        monitor = stack.enter_context(attach_memory_guard(child.pid, folder/'memory-health.json',
                                                          duration=horizon, limit_gib=limit_gib))
        tree = None
        if watch:
            tree = Descendants(child.pid, folder, watch, horizon, limit_gib, stack)
            # Runs before the child is reaped; after a success it only reaps leftovers such as shader workers.
            stack.callback(tree.unwind)
        started = time.monotonic()
        deadline = started+horizon if horizon else None
        spoken = started
        while child.poll() is None:
            if tree is not None:
                tree.poll()
            if progress and time.monotonic()-spoken >= progress:
                spoken = time.monotonic()
                watched = ', '.join(f'{name} {pid}' for pid, name, _ in tree.guarded if tree.same(pid)) if tree else ''
                print(f'{(spoken-started)/60:.0f} min{f" [{watched}]" if watched else ""}: {last_line(folder/"stdout.log")}', flush=True)
            if monitor is not None and monitor.poll() is not None and child.poll() is None:
                raise SystemExit('memory guard exited before the child')
            if deadline is not None and time.monotonic() > deadline:
                raise SystemExit(f'child exceeded {timeout} s')
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        return child.returncode or 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, help='directory for memory-health.json and stdout.log')
    parser.add_argument('--timeout', type=float, default=0, help='seconds before the child is stopped, 0 for none')
    parser.add_argument('--purpose', default=None, help='recorded in the lock file for a clearer refusal')
    parser.add_argument('--no-lock', action='store_true', help='skip the render lock (the memory guard stays)')
    parser.add_argument('--small', type=float, default=None, metavar='GIB',
                        help='expected peak in GiB: the job may use the small render slot (at most 3 GiB, 4 GiB limit)')
    parser.add_argument('--kind', choices=KINDS, default='job', help='recorded in the lock file; games and compiles '
                        'always use the big slot, and a compile waits for a small job to finish')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command and args.command[0] == '--' else args.command
    if not command:
        raise SystemExit('nothing to run')
    return run(command, args.report, args.timeout, args.purpose, lock=not args.no_lock, small_gib=args.small,
               kind=args.kind)


if __name__ == '__main__':
    sys.exit(main())
