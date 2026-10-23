"""An independent aggregate footprint guard for one owned compound job on macOS.

Start this monitor before launching any heavy children, then wait for its `running` receipt.
It adds the physical footprint of the pinned owner and its owned descendants, retaining
ownership when an intermediate exits. Shared engine services and their children are excluded.
Individual game guards and the outer render lock remain required.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time

SHARED = frozenset({'zenserver', 'UnrealTraceServer'})


def adopt_reporters(launch_nonce):
    """macOS CrashReporter reconciliation; other kernels have no reporters to adopt."""
    if launch_nonce is None or sys.platform != 'darwin':
        return None
    from .mac_crash_reporters import Reporters
    return Reporters(launch_nonce)


class OwnedTree:
    def __init__(self, api, pid, started, reporters=None):
        self.api = api
        self.root = (pid, started)
        self.parents = {self.root: None}
        self.depth = {self.root: 0}
        self.shared = set()
        self.reporters = reporters

    def same(self, key):
        return self.api.started(key[0]) == key[1]

    def excluded(self):
        for key in self.parents:
            if self.same(key) and self.api.name(key[0]) in SHARED:
                self.shared.add(key)
        result = set(self.shared)
        for key in self.parents:
            ancestor, visited = key, set()
            while ancestor is not None and ancestor not in visited:
                if ancestor in self.shared:
                    result.add(key)
                    break
                visited.add(ancestor)
                ancestor = self.parents.get(ancestor)
        return result

    def discover(self):
        excluded = self.excluded()
        pending = [key for key in self.parents if key not in excluded and self.same(key)]
        seen = set()
        while pending:
            parent = pending.pop()
            if parent in seen:
                continue
            seen.add(parent)
            if self.api.name(parent[0]) in SHARED:
                self.shared.add(parent)
                continue
            for child in self.api.owned_children(*parent):
                if child not in self.parents:
                    self.parents[child] = parent
                    self.depth[child] = self.depth[parent] + 1
                if child not in excluded:
                    pending.append(child)
        if self.reporters is not None and self.reporters.observe(self, seen):
            self.reporters.reconcile(self)

    def sample(self):
        self.discover()
        excluded = self.excluded()
        samples = []
        for key in self.parents:
            if key in excluded:
                continue
            try:
                value = self.api.usage(key[0])
            except ProcessLookupError:
                continue
            if value.started == key[1] and not value.exited:
                samples.append(dict(pid=key[0], started=key[1], footprint_bytes=value.footprint,
                                    name=self.api.name(key[0]), depth=self.depth[key]))
        return samples

    def stop_owned(self, send=os.kill, exclude_pid=None):
        if self.reporters is not None:
            self.reporters.reconcile(self)
        # Recheck service names and pinned identities immediately before each signal. An
        # already-recorded shell may have exec'd a shared service since the last sample.
        for key in sorted(self.parents, key=self.depth.get, reverse=True):
            # Retain historical ancestry, but do not rescan it for every departed compiler.
            if key[0] == exclude_pid or not self.same(key):
                continue
            if key in self.excluded() or not self.same(key):
                continue
            if self.reporters is not None and not self.reporters.signal_allowed(key):
                continue
            try:
                send(key[0], signal.SIGKILL)
            except ProcessLookupError:
                pass


def write_report(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def drain_owned(tree, timeout=2., exclude_pid=None):
    """Observe the retained pinned tree exit, including children found during cleanup."""
    deadline = time.monotonic() + timeout
    empty_samples = 0
    while True:
        try:
            # Remember native identities before stopping their ancestors. Reconcile
            # again after exit, including reporters spawned during the first stop.
            observed = True
            try:
                tree.sample()
            except (OSError, RuntimeError):
                observed = False  # Still try to stop previously pinned processes.
            if exclude_pid is None:
                tree.stop_owned()
            else:
                tree.stop_owned(exclude_pid=exclude_pid)
            remaining = [row for row in tree.sample() if row['pid'] != exclude_pid]
            empty = observed and not remaining and (tree.reporters is None or tree.reporters.empty())
            empty_samples = empty_samples + 1 if empty else 0
            if empty_samples >= 2:
                return True
        except (OSError, RuntimeError):
            # Telemetry loss cannot certify emptiness. Retry the existing pinned
            # cleanup within the same bound; never infer ownership from a failed read.
            empty_samples = 0
        if time.monotonic() >= deadline:
            return False
        time.sleep(.02)



def controller_live(pin):
    from atelier.harness.safety import process_tree
    try:
        sample = process_tree.usage(pin[0])
        return sample.started == pin[1] and not sample.exited
    except ProcessLookupError:
        return False  # Losing controller observation stops only this guard's owned workload.

def run_child(pid, started, report, duration=None, limit_gib=10., controller=None, launch_nonce=None):
    """@cc [owner:fontanierh,label:safety] owned-child-aggregate-limit
    Every sampled owned process MUST contribute to the simultaneous footprint limit except shared
    engine services and their descendants. Failure or launcher exit MUST stop the retained pinned
    tree, and successful terminal receipts MUST require observed tree exit. Cleanup that cannot
    complete within its bound MUST fail; PID reuse MUST NOT transfer ownership. A bound controller
    disappearing MUST stop the owned tree and publish controller_exited with post-drain cleanup,
    never successful completion. Independent guards MUST outlive the controller process group.
    """
    from atelier.harness.safety import process_tree
    adopted = adopt_reporters(launch_nonce)
    tree = OwnedTree(process_tree, pid, started, adopted)
    report = Path(report)
    began, peak = time.monotonic(), 0
    limit = int(limit_gib * 1024**3)
    try:
        if adopted is not None:
            adopted.bind_root(pid, started)
        if not tree.same(tree.root):
            raise RuntimeError('The launcher is no longer the pinned owner')
        while True:
            samples = tree.sample()
            total = sum(p['footprint_bytes'] for p in samples)
            peak = max(peak, total)
            elapsed = time.monotonic() - began
            state = 'running'
            if total > limit:
                state = 'memory_limit'
            elif duration is not None and elapsed >= duration:
                state = 'test_duration'
            elif controller is not None and not controller_live(controller):
                state = 'controller_exited'
            elif not any((p['pid'], p['started']) == tree.root for p in samples):
                state = 'child_exited'
            value = dict(owner=pid, owner_started=started, time=time.time(), observed_monotonic=time.monotonic(),
                         elapsed_seconds=elapsed,
                         footprint_bytes=total, peak_bytes=peak, limit_bytes=limit,
                         state=state, processes=samples)
            if controller is not None:
                value['controller'] = list(controller)
            if state != 'running':
                value['cleanup_complete'] = drain_owned(tree)
                # drain_owned may have ended helpers from the pre-cleanup sample. Publish
                # the observed post-drain tree, including any newly discovered survivor.
                remaining = tree.sample()
                remaining_total = sum(p['footprint_bytes'] for p in remaining)
                if state == 'child_exited':
                    value.update(processes=remaining, footprint_bytes=remaining_total)
                else:
                    # Keep the established offending sample for failure diagnostics.
                    value.update(cleanup_processes=remaining, cleanup_footprint_bytes=remaining_total)
                value['cleanup_complete'] = value['cleanup_complete'] and not remaining
                if adopted is not None:
                    value['cleanup_complete'] = value['cleanup_complete'] and adopted.empty()
                    value['late_reporters'] = adopted.evidence()
                value['peak_bytes'] = max(value['peak_bytes'], remaining_total)
                if not value['cleanup_complete']:
                    value['termination_reason'], value['state'] = state, 'cleanup_incomplete'
                    state = 'cleanup_incomplete'
                value['observed_monotonic'] = time.monotonic()
                value['time'] = time.time()
            write_report(report, value)
            if state != 'running':
                return 0 if state == 'child_exited' else 1
            time.sleep(.25)
    except BaseException:
        drain_owned(tree)
        raise


def run(pid, started, report, duration, stop_file, limit_gib=10., launch_nonce=None):
    from atelier.harness.safety import process_tree
    adopted = adopt_reporters(launch_nonce)
    tree = OwnedTree(process_tree, pid, started, adopted)
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    began, peak = time.monotonic(), 0
    limit = int(limit_gib * 1024**3)
    try:
        if adopted is not None:
            adopted.bind_root(pid, started)
        if not tree.same(tree.root):
            raise RuntimeError('The compound job is no longer the pinned owner')
        while True:
            samples = tree.sample()
            total = sum(p['footprint_bytes'] for p in samples)
            peak = max(peak, total)
            elapsed = time.monotonic() - began
            state = 'running'
            if total > limit:
                state = 'memory_limit'
            elif elapsed > duration:
                state = 'test_duration'
            elif not tree.same(tree.root):
                state = 'owner_exited'
            elif Path(stop_file).exists():
                # The harness asks to stop only after all owned games and helpers have
                # exited. Keep protecting the job if a game tree remains alive.
                if adopted is not None:
                    adopted.reconcile(tree)
                    samples = tree.sample()
                    total = sum(p['footprint_bytes'] for p in samples)
                    peak = max(peak, total)
                state = 'complete' if all(p['pid'] in {pid, os.getpid()} for p in samples) else 'children_remain'
                if adopted is not None and not adopted.empty():
                    state = 'cleanup_incomplete'
            value = dict(owner=pid, owner_started=started, time=time.time(), elapsed_seconds=elapsed,
                         footprint_bytes=total, peak_bytes=peak, limit_bytes=limit,
                         state=state, processes=samples)
            if adopted is not None:
                value['late_reporters'] = adopted.evidence()
            if state == 'complete':
                write_report(report, value)
                return 0
            if state != 'running':
                value['cleanup_complete'] = drain_owned(tree, exclude_pid=os.getpid())
                remaining = [row for row in tree.sample() if row['pid'] != os.getpid()]
                value.update(cleanup_processes=remaining,
                             cleanup_footprint_bytes=sum(row['footprint_bytes'] for row in remaining))
                value['cleanup_complete'] = value['cleanup_complete'] and not remaining
                if adopted is not None:
                    value['cleanup_complete'] = value['cleanup_complete'] and adopted.empty()
                    value['late_reporters'] = adopted.evidence()
                if not value['cleanup_complete']:
                    value.update(state='cleanup_incomplete', termination_reason=state)
                write_report(report, value)
                return 1
            write_report(report, value)
            time.sleep(.25)
    except BaseException:
        # Losing telemetry must stop the owned job, even if Unreal or the harness stalls.
        drain_owned(tree, exclude_pid=os.getpid())
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--expected-start', type=int, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--stop-file', type=Path)
    parser.add_argument('--duration', type=float)
    parser.add_argument('--controller-pid', type=int)
    parser.add_argument('--controller-start', type=int)
    parser.add_argument('--child', action='store_true', help='guard an owned launcher until it exits')
    parser.add_argument('--launch-context-fd', type=int, help='private inherited launch ownership context')
    parser.add_argument('--limit-gib', type=float, default=10.)
    args = parser.parse_args()
    nonce = None
    if args.launch_context_fd is not None:
        if args.launch_context_fd < 3:
            parser.error('private context requires a separate inherited descriptor')
        from .launch_ownership import read_private_pipe
        nonce = read_private_pipe(args.launch_context_fd)
    if (args.controller_pid is None) != (args.controller_start is None):
        parser.error('controller PID and start must be provided together')
    if args.controller_pid is not None and (not args.child or args.controller_pid <= 0 or args.controller_start <= 0):
        parser.error('a positive controller identity is only valid with --child')
    if args.child:
        if args.stop_file is not None:
            parser.error('--child does not use --stop-file')
        return run_child(args.pid, args.expected_start, args.report, args.duration, args.limit_gib,
                         None if args.controller_pid is None else (args.controller_pid, args.controller_start), nonce)
    if args.stop_file is None or args.duration is None or args.limit_gib != 10.:
        parser.error('compound guards require --stop-file and --duration, with the fixed 10 GiB ceiling')
    # There is deliberately no CLI switch to raise this compound job's 10 GiB ceiling.
    return run(args.pid, args.expected_start, args.report, args.duration, args.stop_file, launch_nonce=nonce)


if __name__ == '__main__':
    raise SystemExit(main())
