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
import time

SHARED = frozenset({'zenserver', 'UnrealTraceServer'})


class OwnedTree:
    def __init__(self, api, pid, started):
        self.api = api
        self.root = (pid, started)
        self.parents = {self.root: None}
        self.depth = {self.root: 0}
        self.shared = set()

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
        # Recheck service names and pinned identities immediately before each signal. An
        # already-recorded shell may have exec'd a shared service since the last sample.
        for key in sorted(self.parents, key=self.depth.get, reverse=True):
            if key[0] == exclude_pid or key in self.excluded() or not self.same(key):
                continue
            try:
                send(key[0], signal.SIGKILL)
            except ProcessLookupError:
                pass


def write_report(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def run(pid, started, report, duration, stop_file, limit_gib=10.):
    from . import process_tree
    tree = OwnedTree(process_tree, pid, started)
    if not tree.same(tree.root):
        raise RuntimeError('The compound job is no longer the pinned owner')
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    began, peak = time.monotonic(), 0
    limit = int(limit_gib * 1024**3)
    try:
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
                state = 'complete' if all(p['pid'] in {pid, os.getpid()} for p in samples) else 'children_remain'
            value = dict(owner=pid, owner_started=started, time=time.time(), elapsed_seconds=elapsed,
                         footprint_bytes=total, peak_bytes=peak, limit_bytes=limit,
                         state=state, processes=samples)
            write_report(report, value)
            if state == 'complete':
                return 0
            if state != 'running':
                tree.stop_owned(exclude_pid=os.getpid())
                return 1
            time.sleep(.25)
    except BaseException:
        # Losing telemetry must stop the owned job, even if Unreal or the harness stalls.
        tree.stop_owned(exclude_pid=os.getpid())
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--expected-start', type=int, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--stop-file', type=Path, required=True)
    parser.add_argument('--duration', type=float, required=True)
    args = parser.parse_args()
    # There is deliberately no CLI switch to raise this compound job's 10 GiB ceiling.
    return run(args.pid, args.expected_start, args.report, args.duration, args.stop_file)


if __name__ == '__main__':
    raise SystemExit(main())
