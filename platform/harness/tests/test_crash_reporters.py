"""Ownership tests use a fake kernel: no process is launched or signalled."""
from types import SimpleNamespace
import struct
import sys

import pytest

from atelier.harness.safety.launch_ownership import ENVIRONMENT_KEY, LINEAGE_KEY, MAX_ANCESTORS, prepare
from atelier.harness.safety.mac_crash_reporters import Reporters, arguments_and_marker, reporter_for_native
from atelier.harness.safety.tree_guard import OwnedTree

# CrashReporter adoption reads a macOS kernel facility (libproc and the reporter's own argv);
# the guard has nothing to reconcile elsewhere, so the whole module runs in the macOS job.
pytestmark = pytest.mark.macos_only

NONCE = 'a' * 64
NATIVE = '/fixture/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor'
REPORTER = '/fixture/Engine/Binaries/Mac/CrashReportClientEditor.app/Contents/MacOS/CrashReportClientEditor'
FLAT_REPORTER = '/fixture/Engine/Binaries/Mac/CrashReportClientEditor'
CRASH = '/crashes/CrashReport-UE-Fixture-pid-2-' + 'b' * 32


class Kernel:
    def __init__(self):
        self.rows = {}
        self.argument_failure = set()
        self.roster_failure = False

    def add(self, pid, parent, name, executable, *, start=None, marker=NONCE, argv=()):
        self.rows[pid] = SimpleNamespace(parent=parent, name=name, executable=executable,
            started=start or pid * 100, marker=marker, argv=argv, footprint=10, exited=0)

    def started(self, pid):
        return self.live_start(pid)

    def live_start(self, pid):
        return self.rows[pid].started if pid in self.rows else None

    def name(self, pid):
        return self.rows[pid].name if pid in self.rows else ''

    def executable(self, pid):
        return self.rows[pid].executable

    def arguments(self, pid, nonce):
        if pid in self.argument_failure:
            raise OSError('unreadable')
        row = self.rows[pid]
        return row.argv, None if row.marker is None else row.marker == nonce

    def pids(self):
        if self.roster_failure:
            raise OSError('unreadable roster')
        return tuple(self.rows)

    def now(self):
        return 10000

    def usage(self, pid):
        if pid not in self.rows:
            raise ProcessLookupError(pid)
        return self.rows[pid]

    def owned_children(self, pid, start):
        if self.live_start(pid) != start:
            return []
        return [(child, row.started) for child, row in self.rows.items() if row.parent == pid]


def known_native():
    api = Kernel()
    api.add(1, 0, 'launcher', '/fixture/python')
    api.add(2, 1, 'UnrealEditor', NATIVE)
    reporters = Reporters(NONCE, api)
    reporters.bind_root(1, 100)
    tree = OwnedTree(api, 1, 100, reporters)
    tree.sample()
    return api, tree, reporters


def orphan(api, **kwargs):
    del api.rows[2]
    api.add(3, 0, 'CrashReportClient', REPORTER, argv=('CrashReportClient', CRASH), **kwargs)


def test_adopts_late_piped_reporter_after_native_exits_between_samples():
    api, tree, reporters = known_native()
    orphan(api)
    assert {row['pid'] for row in tree.sample()} == {1, 3}
    assert tree.parents[(3, 300)] == (2, 200)
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent == [3, 1]
    assert reporters.empty()
    assert NONCE not in str(reporters.evidence())
    assert CRASH not in str(reporters.evidence())


def test_foreign_marker_never_adopts_or_signals_other_reporter():
    api, tree, reporters = known_native()
    orphan(api, marker='c' * 64)
    assert {row['pid'] for row in tree.sample()} == {1}
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent == [1]
    assert reporters.empty()


@pytest.mark.parametrize('field,value', [
    ('executable', '/other/Engine/Binaries/Mac/CrashReportClientEditor.app/Contents/MacOS/CrashReportClientEditor'),
    ('argv', ('CrashReportClient', CRASH.replace('pid-2-', 'pid-999-'))),
    ('argv', ('CrashReportClient', CRASH.replace('b' * 32, 'not-a-run-uuid'))),
    ('argv', ('forged-argv0', CRASH)),
    ('started', 150),
])
def test_matching_marker_without_complete_native_proof_refuses_empty_success(field, value):
    api, tree, reporters = known_native()
    orphan(api)
    setattr(api.rows[3], field, value)
    tree.sample()
    assert not reporters.adopted and not reporters.empty()
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent == [1]


def test_current_marker_with_never_observed_native_stays_unresolved():
    api = Kernel()
    api.add(1, 0, 'launcher', '/fixture/python')
    api.add(3, 0, 'CrashReportClient', REPORTER, argv=('CrashReportClient', CRASH))
    reporters = Reporters(NONCE, api)
    tree = OwnedTree(api, 1, 100, reporters)
    reporters.reconcile(tree)
    assert not reporters.adopted and not reporters.empty()


@pytest.mark.parametrize('native_observed', [False, True])
def test_redacted_or_ambiguous_marker_never_proves_reporter_foreign(native_observed):
    api, tree, reporters = known_native()
    if not native_observed:
        reporters.natives.clear()
    orphan(api, marker=None)
    reporters.reconcile(tree)
    assert not reporters.adopted and not reporters.empty()
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent == [1]


@pytest.mark.parametrize('executable', [REPORTER, FLAT_REPORTER])
def test_both_installed_editor_reporter_layouts_have_exact_ownership(executable):
    api, tree, reporters = known_native()
    orphan(api)
    api.rows[3].executable = executable
    tree.sample()
    assert reporters.adopted[(3, 300)]['executable'] == executable


def test_noneditor_reporter_is_not_an_editor_sibling():
    api, tree, reporters = known_native()
    orphan(api)
    api.rows[3].executable = REPORTER.replace('CrashReportClientEditor', 'CrashReportClient')
    tree.sample()
    assert not reporters.adopted and not reporters.empty()


def test_unreadable_process_name_falls_back_to_kernel_executable():
    api, tree, reporters = known_native()
    orphan(api)
    api.rows[3].name = ''
    tree.sample()
    assert (3, 300) in reporters.adopted


def test_unreadable_name_and_executable_cannot_certify_empty(monkeypatch):
    api, tree, reporters = known_native()
    orphan(api)
    api.rows[3].name = ''
    executable = api.executable

    def unreadable(pid):
        if pid == 3:
            raise OSError('unreadable executable')
        return executable(pid)

    monkeypatch.setattr(api, 'executable', unreadable)
    tree.sample()
    assert not reporters.adopted and not reporters.empty()


def test_native_pid_reuse_does_not_admit_a_newer_reporter():
    api, tree, reporters = known_native()
    orphan(api, start=500)
    api.add(2, 0, 'UnrealEditor', NATIVE, start=400, marker='c' * 64)
    tree.sample()
    assert not reporters.adopted and not reporters.empty()


def test_reporter_pid_reuse_never_signals_new_process():
    api, tree, reporters = known_native()
    orphan(api)
    tree.sample()
    api.rows[3].started = 999
    api.rows[3].marker = 'c' * 64
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent == [1]


def test_rechecks_reporter_marker_before_signal():
    api, tree, reporters = known_native()
    orphan(api)
    tree.sample()
    api.rows[3].marker = 'c' * 64
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent == [1]
    assert not reporters.empty()


def test_rechecks_reporter_start_after_final_executable_read(monkeypatch):
    api, tree, reporters = known_native()
    orphan(api)
    tree.sample()
    executable = api.executable
    reads = []

    def reused_on_second_read(pid):
        result = executable(pid)
        if pid == 3:
            reads.append(pid)
            if len(reads) == 2:
                api.rows[3].started = 999
        return result

    monkeypatch.setattr(api, 'executable', reused_on_second_read)
    assert not reporters.signal_allowed((3, 300))


def test_failed_roster_and_possible_owned_argument_reads_stay_unknown():
    api, tree, reporters = known_native()
    orphan(api)
    api.argument_failure.add(3)
    tree.sample()
    assert not reporters.empty() and not reporters.adopted
    api.argument_failure.clear()
    api.roster_failure = True
    reporters.reconcile(tree)
    assert reporters.scan_failed and not reporters.empty()


@pytest.mark.parametrize('adopt_first', [False, True])
def test_failed_start_read_is_not_a_proved_exit(monkeypatch, adopt_first):
    api, tree, reporters = known_native()
    orphan(api)
    if adopt_first:
        tree.sample()
        assert (3, 300) in reporters.adopted
    live_start = api.live_start

    def unreadable(pid):
        if pid == 3:
            raise OSError('start identity unavailable')
        return live_start(pid)

    monkeypatch.setattr(api, 'live_start', unreadable)
    reporters.reconcile(tree)
    assert not reporters.empty() and reporters.evidence()['unresolved_pids'] == [3]
    if adopt_first:
        assert not reporters.signal_allowed((3, 300))


def test_root_context_must_match_before_monitor_readiness():
    api = Kernel()
    api.add(1, 0, 'launcher', '/fixture/python', marker='c' * 64)
    with pytest.raises(ValueError, match='gated root'):
        Reporters(NONCE, api).bind_root(1, 100)


def test_context_is_fresh_private_immutable_and_single_use():
    original = {'PATH': '/fixture/bin'}
    first, second = prepare(original), prepare(original)
    assert first.nonce != second.nonce and ENVIRONMENT_KEY not in original
    assert first.nonce not in repr(first) and '/fixture/bin' not in repr(first)
    with pytest.raises(TypeError):
        first.environment['PATH'] = '/changed'
    with pytest.raises(ValueError):
        first.claim({**first.environment, 'PATH': '/changed'})
    assert first.claim(first.environment) == first.nonce
    with pytest.raises(ValueError):
        first.claim(first.environment)


def test_nested_context_retains_strict_ancestor_ownership_without_reusing_current_nonce():
    outer = prepare({})
    inner = prepare(outer.environment)
    assert inner.nonce != outer.nonce and inner.environment[LINEAGE_KEY] == outer.nonce
    argv = ('CrashReportClient', CRASH)
    raw = procargs(argv, [key + '=' + value for key, value in inner.environment.items()])
    assert arguments_and_marker(raw, outer.nonce) == (argv, True)
    assert arguments_and_marker(raw, inner.nonce) == (argv, True)
    assert arguments_and_marker(raw, NONCE) == (argv, False)


@pytest.mark.parametrize('changes', [
    {ENVIRONMENT_KEY: 'malformed', LINEAGE_KEY: ''},
    {ENVIRONMENT_KEY: NONCE},
    {LINEAGE_KEY: ''},
    {ENVIRONMENT_KEY: NONCE, LINEAGE_KEY: NONCE},
    {ENVIRONMENT_KEY: NONCE, LINEAGE_KEY: 'c' * 64 + ':' + 'c' * 64},
])
def test_invalid_inherited_context_refuses_before_launch(changes):
    with pytest.raises(ValueError, match='ancestry'):
        prepare(changes)


def test_nested_depth_never_silently_drops_ancestors():
    context = prepare({})
    for _ in range(MAX_ANCESTORS):
        context = prepare(context.environment)
    with pytest.raises(ValueError, match='depth exhausted'):
        prepare(context.environment)


def procargs(argv, environment):
    return (struct.pack('=i', len(argv)) + b'/kernel/executable\0\0'
            + b'\0'.join(item.encode() for item in argv) + b'\0'
            + b'\0'.join(item.encode() for item in environment) + b'\0')


def test_bounded_process_argument_parser_does_not_expose_environment():
    argv = ('CrashReportClient', CRASH)
    fields = [ENVIRONMENT_KEY + '=' + NONCE, LINEAGE_KEY + '=']
    data = procargs(argv, ['PRIVATE_OTHER=value', *fields])
    assert arguments_and_marker(data, NONCE) == (argv, True)
    assert arguments_and_marker(data, 'c' * 64) == (argv, False)
    for fields in ([], [ENVIRONMENT_KEY + '=' + NONCE], fields + fields,
                   [ENVIRONMENT_KEY + '=malformed', LINEAGE_KEY + '='],
                   [ENVIRONMENT_KEY + '=' + NONCE, LINEAGE_KEY + '=' + NONCE]):
        assert arguments_and_marker(procargs(argv, fields), NONCE) == (argv, None)
    for invalid in (b'', struct.pack('=i', -1) + b'x\0', struct.pack('=i', 9000) + b'x\0',
                    struct.pack('=i', 2) + b'/exe\0\0one\0'):
        with pytest.raises(ValueError):
            arguments_and_marker(invalid, NONCE)


def test_controller_loss_reconciles_before_killing_native_and_publishes_empty_cleanup(tmp_path, monkeypatch):
    import json
    from atelier.harness.safety import mac_crash_reporters, process_tree, tree_guard
    api = Kernel()
    api.add(1, 0, 'launcher', '/fixture/python')
    api.add(2, 1, 'UnrealEditor', NATIVE)
    api.add(3, 0, 'CrashReportClient', REPORTER, argv=('CrashReportClient', CRASH))
    reporters = Reporters(NONCE, api)
    monkeypatch.setattr(mac_crash_reporters, 'Reporters', lambda nonce: reporters)
    for name in ('usage', 'started', 'name', 'owned_children'):
        monkeypatch.setattr(process_tree, name, getattr(api, name))
    monkeypatch.setattr(tree_guard, 'controller_live', lambda pin: False)
    stop_owned = tree_guard.OwnedTree.stop_owned
    sent = []

    def send(pid, number):
        sent.append(pid)
        del api.rows[pid]

    monkeypatch.setattr(tree_guard.OwnedTree, 'stop_owned',
                        lambda tree: stop_owned(tree, send))
    destination = tmp_path / 'aggregate.json'
    assert tree_guard.run_child(1, 100, destination, controller=(99, 9900), launch_nonce=NONCE) == 1
    value = json.loads(destination.read_text())
    assert value['state'] == 'controller_exited' and value['cleanup_complete'] is True
    assert value['cleanup_processes'] == [] and value['cleanup_footprint_bytes'] == 0
    assert sent == [3, 2, 1]
    assert value['late_reporters']['adopted'] == [{'pid': 3, 'started': 300, 'native': [2, 200]}]


def test_compound_stop_rechecks_new_reporters_before_success(tmp_path, monkeypatch):
    import json
    from atelier.harness.safety import mac_crash_reporters, process_tree, tree_guard
    api, tree, reporters = known_native()
    del api.rows[2]
    monkeypatch.setattr(mac_crash_reporters, 'Reporters', lambda nonce: reporters)
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: tree)
    for name in ('usage', 'started', 'name', 'owned_children'):
        monkeypatch.setattr(process_tree, name, getattr(api, name))
    reconcile = reporters.reconcile
    scans = []

    def after_sample(candidate):
        reconcile(candidate)
        scans.append(True)
        if len(scans) == 1:
            api.add(3, 0, 'CrashReportClient', REPORTER, argv=('CrashReportClient', CRASH))

    monkeypatch.setattr(reporters, 'reconcile', after_sample)
    sent = []
    stop_owned = tree.stop_owned
    def send(pid, number):
        sent.append(pid)
        del api.rows[pid]

    monkeypatch.setattr(tree, 'stop_owned', lambda **kwargs: stop_owned(send, **kwargs))
    stop_file = tmp_path / 'stop'
    stop_file.write_text('')
    destination = tmp_path / 'aggregate.json'
    assert tree_guard.run(1, 100, destination, 10, stop_file, launch_nonce=NONCE) == 1
    value = json.loads(destination.read_text())
    assert value['state'] == 'children_remain'
    assert {row['pid'] for row in value['processes']} == {1, 3}
    assert sent == [3, 1]
    assert value['cleanup_complete'] and value['cleanup_processes'] == []


def test_only_installed_kernel_native_layout_defines_expected_crc():
    assert reporter_for_native(NATIVE) == {REPORTER, FLAT_REPORTER}
    assert reporter_for_native(NATIVE.replace('UnrealEditor', 'UnrealEditor-Cmd')) == {REPORTER, FLAT_REPORTER}
    assert reporter_for_native('/fixture/Engine/Binaries/Mac/UnrealEditor-Cmd') == {REPORTER, FLAT_REPORTER}
    assert reporter_for_native('/arbitrary/UnrealEditor') is None
    assert reporter_for_native(NATIVE.replace('/fixture/', '/fixture/../other/')) is None


@pytest.mark.parametrize('compound', [False, True])
def test_exception_cleanup_reconciles_reporter_spawned_during_native_stop(tmp_path, monkeypatch, compound):
    from atelier.harness.safety import mac_crash_reporters, process_tree, tree_guard
    api = Kernel()
    api.add(1, 0, 'launcher', '/fixture/python')
    api.add(2, 1, 'UnrealEditor', NATIVE)
    reporters = Reporters(NONCE, api)
    monkeypatch.setattr(mac_crash_reporters, 'Reporters', lambda nonce: reporters)
    for name in ('usage', 'started', 'name', 'owned_children'):
        monkeypatch.setattr(process_tree, name, getattr(api, name))
    stop_owned = tree_guard.OwnedTree.stop_owned
    sent = []

    def send(pid, number):
        sent.append(pid)
        del api.rows[pid]
        if pid == 2:
            api.add(3, 0, 'CrashReportClient', REPORTER, argv=('CrashReportClient', CRASH))

    monkeypatch.setattr(tree_guard.OwnedTree, 'stop_owned',
                        lambda tree, **kwargs: stop_owned(tree, send, **kwargs))

    def broken_receipt(*args):
        raise OSError('fixture receipt unavailable')

    monkeypatch.setattr(tree_guard, 'write_report', broken_receipt)
    with pytest.raises(OSError, match='fixture receipt unavailable'):
        if compound:
            tree_guard.run(1, 100, tmp_path / 'aggregate.json', 10, tmp_path / 'not-stopped', launch_nonce=NONCE)
        else:
            tree_guard.run_child(1, 100, tmp_path / 'aggregate.json', launch_nonce=NONCE)
    assert sent == [2, 1, 3]
    assert not api.rows and reporters.empty()
    assert (3, 300) in reporters.adopted


def test_private_context_pipe_transports_only_one_marker_and_closes_descriptors():
    import os
    from atelier.harness.safety.launch_ownership import private_pipe, read_private_pipe
    with private_pipe(NONCE) as descriptor:
        duplicate = os.dup(descriptor)
        assert read_private_pipe(duplicate) == NONCE
        with pytest.raises(OSError):
            os.fstat(duplicate)
    with pytest.raises(OSError):
        os.fstat(descriptor)


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS kernel lifecycle evidence')
def test_actual_kernel_probe_reads_only_the_current_test_process():
    import os
    from atelier.harness.safety.mac_crash_reporters import KernelProbe
    api = KernelProbe()
    pid = os.getpid()
    start = api.live_start(pid)
    assert 0 < start <= api.now()
    assert os.path.samefile(api.executable(pid), sys.executable)
    argv, marker = api.arguments(pid, NONCE)
    assert argv and isinstance(argv[0], str)
    assert marker is None or type(marker) is bool
    assert pid in api.pids()
    assert api.live_start(pid) == start


def test_kernel_roster_is_scoped_to_launch_user_not_inaccessible_system_daemons():
    import ctypes
    import os
    from atelier.harness.safety.mac_crash_reporters import KernelProbe
    calls = []

    def list_pids(kind, user, buffer, size):
        calls.append((kind, user))
        if buffer is not None:
            buffer[0] = os.getpid()
        return ctypes.sizeof(ctypes.c_int)

    api = object.__new__(KernelProbe)
    api.lib = SimpleNamespace(proc_listpids=list_pids)
    assert api.pids() == (os.getpid(),)
    assert calls == [(4, os.geteuid()), (4, os.geteuid())]

