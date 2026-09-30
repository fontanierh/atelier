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
"""
import argparse, subprocess, sys, time
from contextlib import ExitStack
from pathlib import Path

from .guard import attach as attach_memory_guard, reap
from .render_lock import KINDS, SMALL_LIMIT_GIB, render_lock


def run(command, folder, timeout=0., purpose=None, lock=True, env=None, limit_gib=10., small_gib=None, kind='job',
        on_slot=None):
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
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
        stack.callback(reap, child)
        where = f', small render slot, {limit_gib:g} GiB limit' if slot == 'small' else ''
        print(f'pid {child.pid}, guard report {folder/"memory-health.json"}{where}', flush=True)
        monitor = stack.enter_context(attach_memory_guard(child.pid, folder/'memory-health.json',
                                                          duration=horizon, limit_gib=limit_gib))
        deadline = time.monotonic()+horizon if horizon else None
        while child.poll() is None:
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
