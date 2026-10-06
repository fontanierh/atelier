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
deepest first, before the child itself. Shared engine services a cook starts (Zen, Unreal Trace Server) and anything
under them are never signalled, nor is anything outside the recorded tree. `progress` prints a line that often while the child is quiet.
"""
import argparse, os, signal, subprocess, sys, time
from contextlib import ExitStack
from pathlib import Path

from .guard import attach as attach_memory_guard, reap
from . import process_tree
from .render_lock import KINDS, SMALL_LIMIT_GIB, render_lock
from .process import spawn


# Engine services a cook may start and other work then shares: recorded, never guarded or signalled.
SHARED_SERVICES = frozenset({'zenserver', 'UnrealTraceServer'})


class Descendants:
    """The child's process tree as it grows. Records are keyed by (pid, start) and reached only through pinned parents;
    names are read again on every poll, so a child first seen as `sh` that execs the cook still gets its guard."""
    def __init__(self, root, root_start, folder, watch, duration, limit_gib, stack):
        self.root, self.folder, self.watch, self.duration, self.limit_gib, self.stack = (
            (root, root_start), folder, set(watch), duration, limit_gib, stack)
        self.depth, self.parent, self.guarded, self.shared = {}, {}, {}, set()

    def same(self, key):
        return process_tree.started(key[0]) == key[1]

    def poll(self):
        # Walk from the root and from every recorded process still alive: an intermediate that lost the root's
        # ancestry (its parent exited) can still start the cook.
        queue = [(*self.root, 0)] + [(*key, depth) for key, depth in self.depth.items()
                                     if key not in self.shared and self.same(key)]
        seen = set()
        while queue:
            parent, parent_start, depth = queue.pop()
            if (parent, parent_start) in seen:
                continue
            seen.add((parent, parent_start))
            for child, child_start in process_tree.owned_children(parent, parent_start):
                key = (child, child_start)
                self.depth.setdefault(key, depth+1)
                self.parent.setdefault(key, (parent, parent_start))
                if process_tree.name(child) in SHARED_SERVICES:
                    self.shared.add(key)
                if key not in self.shared:
                    queue.append((child, child_start, depth+1))
        for key in self.depth:
            if key in self.guarded or key in self.shared or not self.same(key):
                continue
            label = process_tree.name(key[0])
            if label in SHARED_SERVICES:   # a child that exec'd a shared service after it was recorded
                self.shared.add(key)
                continue
            if label not in self.watch:
                continue
            report = self.folder/f'memory-health-{label}-{key[0]}.json'
            monitor = self.stack.enter_context(attach_memory_guard(
                key[0], report, duration=self.duration, limit_gib=self.limit_gib, expected_start=key[1]))
            if monitor is None:
                if self.same(key):
                    raise SystemExit(f'could not guard {label} {key[0]}')
                continue
            self.guarded[key] = (label, monitor)
            print(f'guarding {label} pid {key[0]}, report {report}', flush=True)

    def check(self):
        """A watched process must never outlive its guard."""
        for key, (label, monitor) in self.guarded.items():
            if monitor.poll() is not None and self.same(key):
                raise SystemExit(f'memory guard for {label} {key[0]} exited before it')

    def shared_now(self):
        """Recorded processes at or under a shared service, judged on current names: a recorded `sh` may have exec'd
        zenserver since the last poll, and everything under it is then the service's too."""
        for key in self.depth:
            if key not in self.shared and self.same(key) and process_tree.name(key[0]) in SHARED_SERVICES:
                self.shared.add(key)

        def under(key):
            seen = set()
            while key in self.parent and key not in seen:
                if key in self.shared:
                    return True
                seen.add(key)
                key = self.parent[key]
            return key in self.shared
        return {key for key in self.depth if under(key)}

    def unwind(self, grace=10.):
        """Stop recorded descendants that are still the same processes, deepest first, never a shared service or
        anything under one."""
        excluded = self.shared_now()
        live = sorted((key for key in self.depth if key not in excluded), key=self.depth.get, reverse=True)
        for key in live:
            self.signal(key, signal.SIGTERM)
        deadline = time.monotonic()+grace
        while time.monotonic() < deadline and any(self.same(key) for key in live):
            time.sleep(.2)
        for key in live:
            self.signal(key, signal.SIGKILL)

    def signal(self, key, number):
        """Signal one recorded process only if its pinned identity still holds at this instant and it has not become a
        shared service."""
        if self.same(key) and process_tree.name(key[0]) not in SHARED_SERVICES:
            try:
                os.kill(key[0], number)
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
            tree = Descendants(child.pid, process_tree.started(child.pid), folder, watch, horizon, limit_gib, stack)
            # Runs before the child is reaped; after a success it only reaps leftovers such as shader workers.
            stack.callback(tree.unwind)
        started = time.monotonic()
        deadline = started+horizon if horizon else None
        spoken = started
        while child.poll() is None:
            if tree is not None:
                tree.poll()
                tree.check()
            if progress and time.monotonic()-spoken >= progress:
                spoken = time.monotonic()
                watched = ', '.join(f'{label} {key[0]}' for key, (label, _) in tree.guarded.items() if tree.same(key)) if tree else ''
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
