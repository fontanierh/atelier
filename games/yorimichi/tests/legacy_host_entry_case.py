"""Hosted T1a fixture: ordinary managed CLI over the real source-bound Rust binary.

This script is invoked by the Rust registry case, not collected as an independent
pytest case. Helper cache publication is fixture setup, not tested Cargo bootstrap.
There is no production test mode: the real entry/host/bootstrap/provider are used.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import time

from atelier.build_v2.controller_client import (
    ControllerExecutable, _private_root, capture_controller, verified_controller, write_control,
)
from atelier.paths import REPO
from atelier.harness.capacity_protocol import boot_id
from atelier.harness.safety import process_tree
from atelier.harness.safety.tree_guard import OwnedTree


def signal_readonly_owned(tree, number, *, send=os.kill):
    """Use the existing fresh shared-exclusion-aware target policy, never a group sweep."""
    tree.stop_owned(send=lambda pid, ignored: send(pid, number))


def observed_call(arguments, environment, evidence):
    """Linux test-owned readonly actors only; never a production cleanup authority."""
    boot = boot_id()
    timed_out = False
    cleanup_required = False
    tree = None
    with (evidence / 'stdout.log').open('xb') as stdout, (evidence / 'stderr.log').open('xb') as stderr:
        os.fchmod(stdout.fileno(), 0o600)
        os.fchmod(stderr.fileno(), 0o600)
        process = subprocess.Popen(arguments, cwd=REPO, env=environment, stdout=stdout,
                                   stderr=stderr, start_new_session=True)
        try:
            started = process_tree.started(process.pid)
            assert started is not None, 'owned normal CLI identity unavailable'
            assert os.getpgid(process.pid) == process.pid, 'readonly test caller has no private session'
            tree = OwnedTree(process_tree, process.pid, started)
            deadline = time.monotonic() + 18
            while True:
                tree.discover()
                assert not tree.excluded(), 'unexpected shared service below readonly fixture'
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    raise AssertionError('normal caller exceeded the owned hosted deadline')
                try:
                    process.communicate(timeout=min(.01, remaining))
                    break
                except subprocess.TimeoutExpired:
                    pass
            tree.discover()
        finally:
            if tree is not None:
                cleanup_required = any(tree.same(key) for key in tree.parents)
                # On failure only: normal TERM, then bounded escalation of identities
                # still independently pinned by the existing process-tree provider.
                # This is the root-approved test group, not native/guard cleanup policy.
                for number in (signal.SIGTERM, signal.SIGKILL):
                    remaining = [key for key in tree.parents if tree.same(key)]
                    if not remaining:
                        break
                    signal_readonly_owned(tree, number)
                    end = time.monotonic() + 2
                    while time.monotonic() < end:
                        tree.discover()
                        if not any(tree.same(key) for key in tree.parents):
                            break
                        time.sleep(.01)
                if process.poll() is not None:
                    process.wait()
                observations = {
                    'boot': boot, 'timed_out': timed_out,
                    'cleanup_required': cleanup_required,
                    'test_session': process.pid,
                    'root': list(tree.root),
                    'identities': [{'pid': key[0], 'started': key[1],
                                    'parent': list(parent) if parent else None,
                                    'terminal': not tree.same(key)}
                                   for key, parent in tree.parents.items()],
                }
                write_control(evidence, 'owned-observations.json', observations)
                assert all(row['terminal'] for row in observations['identities']), (
                    'owned test actor terminal state is unknown; logs/fence retained')
            else:
                # No birth identity means Unknown, never a pass. The unreaped owned
                # Popen handle still permits stopping ONLY this fixture's own caller.
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                write_control(evidence, 'owned-observations.json', {
                    'boot': boot, 'state': 'unknown', 'reason': 'caller birth identity unavailable'})
    assert not timed_out
    assert not cleanup_required, 'normal exit left live owned actors; test cleanup is not passing proof'
    assert tree is not None and boot_id() == boot
    return process.returncode, tree, boot


def main(binary):
    assert sys.platform.startswith('linux'), 'this test-owned lifecycle case is Linux-only'
    binary = Path(binary).resolve(strict=True)
    captured = capture_controller(REPO)
    raw = binary.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    candidate = ControllerExecutable(binary, captured.digest, digest)
    with verified_controller(candidate):
        pass
    helper = _private_root(REPO / 'build/build-v2/controller/helpers' / captured.digest)
    with (helper / 'atelier-build-v2').open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fchmod(stream.fileno(), 0o500)
        os.fsync(stream.fileno())
    write_control(helper, 'controller.json', {'version': 1, 'source': captured.digest, 'binary': digest})
    print(f'HOSTED_HELPER_SETUP source={captured.digest} binary={digest}', flush=True)
    # Drop test-runner/compiler injection context, not a production environment
    # override. The original ordinary console entry then captures its real context.
    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith(('ATELIER_', 'PYTHON', 'DYLD_', 'LD_'))}
    environment['ATELIER_AGENT'] = 'hosted-legacy-entry'
    owned_course = REPO / 'games/yorimichi/unreal/Content/Data/racing/belmonte_courses.json'
    assert not owned_course.exists(), 'case requires the fresh hosted checkout output'
    evidence = _private_root(REPO / 'build/build-v2/legacy-host-entry-test')
    code, tree, boot = observed_call(
        [str(REPO / '.venv/bin/atelier'), 'build', 'yorimichi', 'data.stage'], environment, evidence)
    stdout = (evidence / 'stdout.log').read_text()
    stderr = (evidence / 'stderr.log').read_text()
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    assert code != 0, 'discovery-only slice must never certify build completion'
    scopes = [line.removeprefix('Managed legacy authority control: ')
              for line in stdout.splitlines() if line.startswith('Managed legacy authority control: ')]
    assert len(scopes) == 1, 'original normal entry did not publish one scoped control locator'
    control = Path(scopes[0])
    assert control.parent == REPO / 'build/build-v2/legacy-host'
    manifest = json.loads((control / 'startup.json').read_bytes())
    host = manifest['host']
    assert host['boot'] == boot and manifest['source_digest'] == captured.digest
    host_key = (host['pid'], int(host['started']))
    assert tree.parents.get(host_key) == tree.root, 'actual owned host was not observed'
    schedulers = [key for key, parent in tree.parents.items() if parent == host_key]
    assert len(schedulers) == 1, 'actual owned scheduler identity was not observed unambiguously'
    assert all(not tree.same(key) for key in (tree.root, host_key, schedulers[0]))
    scheduler_log = (control / 'scheduler.log').read_text()
    write_control(evidence, 'startup-binding.json', {
        'source': captured.digest, 'binary': digest, 'nonce': manifest['nonce'],
        'host': host, 'scheduler': {'pid': schedulers[0][0], 'started': schedulers[0][1], 'boot': boot},
    })
    with (evidence / 'scheduler.log').open('xb') as copy:
        os.fchmod(copy.fileno(), 0o600)
        copy.write(scheduler_log.encode())
    sys.stdout.write(scheduler_log)
    assert 'Managed captured recipe discovery:' in scheduler_log, 'actual captured Graph was not reached'
    assert 'HELD Unsupported before Context/task preparation' in scheduler_log
    assert 'legacy authority bootstrap failed (AuthorityRefused)' in scheduler_log
    assert 'Managed legacy build held/refused' in stdout
    assert not owned_course.exists()
    assert not (REPO / 'build/yorimichi/.state/file-hashes.sqlite3').exists()
    assert not (REPO / 'build/yorimichi/stamps').exists()
    assert not (REPO / 'build/build-v2/install/index.json').exists()
    assert not (REPO / 'build/build-v2/install/receipts').exists()
    epoch = REPO / 'build/build-v2/install/legacy-epoch.json'
    epoch_present = epoch.exists() or epoch.is_symlink()
    write_control(evidence, 'selection-observation.json', {'epoch_present': epoch_present})
    assert not epoch_present
    print('HOSTED_REAL_ENTRY_GRAPH_HELD no mutation permission or completion certified', flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('expected the actual compiled source-bound controller binary')
    main(sys.argv[1])
