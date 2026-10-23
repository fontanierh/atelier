"""Private services require pre-exec identity binding; shared services remain untouched."""
import os
import signal
import socket
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace

import pytest

from atelier.harness.safety import owned_service, guarded, guard, tree_guard
from test_tree_guard import Processes


def tables():
    api = Processes()
    api.add(1, 0, 'driver', 10)
    api.add(2, 1, 'python', 20)
    api.add(3, 2, 'helper', 30)
    api.add(4, 1, 'zenserver', 400)
    api.add(5, 4, 'helper', 500)
    api.add(6, 1, 'UnrealTraceServer', 600)
    return api


def test_exact_gated_service_and_descendants_counted_default_services_untouched():
    api = tables()
    tree = tree_guard.OwnedTree(api, 1, 100)
    tree.register_service((2, 200))
    api.rows[2].name = 'zenserver'  # same identity across exec
    assert sum(p['footprint_bytes'] for p in tree.sample()) == 60
    assert tree.services.evidence() == [[2, 200]]
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent == [3, 2, 1]
    assert 4 not in sent and 5 not in sent and 6 not in sent


def test_shared_child_of_private_service_is_unsupported_and_never_signalled():
    api = tables()
    tree = tree_guard.OwnedTree(api, 1, 100)
    tree.register_service((2, 200))
    api.rows[2].name = 'zenserver'
    api.rows[3].name = 'UnrealTraceServer'
    with pytest.raises(RuntimeError, match='unsupported unregistered shared service'):
        tree.sample()
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent == [2, 1]


@pytest.mark.parametrize('case', ['stale', 'foreign', 'already_shared', 'duplicate', 'root_gone'])
def test_ambiguous_or_retroactive_registration_refused(case):
    api = tables()
    tree = tree_guard.OwnedTree(api, 1, 100)
    key = (2, 200)
    if case == 'stale':
        api.rows[2].started = 999
    elif case == 'foreign':
        api.rows[2].parent = 0
    elif case == 'already_shared':
        api.rows[2].name = 'zenserver'
    elif case == 'duplicate':
        tree.register_service(key)
    elif case == 'root_gone':
        del api.rows[1]
    with pytest.raises(RuntimeError, match='fresh gated owned child'):
        tree.register_service(key)


def test_private_binding_never_transfers_to_reused_pid_or_its_children():
    api = tables()
    tree = tree_guard.OwnedTree(api, 1, 100)
    tree.register_service((2, 200))
    api.add(2, 1, 'zenserver', 999, started=999)
    api.add(7, 2, 'helper', 700)
    api.rows[3].parent = 0
    assert {p['pid'] for p in tree.sample()} == {1, 3}
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert set(sent) == {1, 3}


def test_launcher_discovery_cleanup_and_signal_use_same_exact_bindings(tmp_path, monkeypatch):
    api = tables()
    monkeypatch.setattr(guarded, 'process_tree', api)
    with ExitStack() as stack:
        tree = guarded.Descendants(1, 100, tmp_path, (), None, 10., stack)
        tree.register_service((2, 200))
        api.rows[2].name = 'zenserver'
        tree.poll()
        assert tree.shared_now() == {(4, 400), (6, 600)}
        sent = []
        monkeypatch.setattr(guarded.os, 'kill', lambda pid, sig: sent.append(pid))
        tree._unwind_recorded(0.)
        assert sent.count(2) == 2 and sent.count(3) == 2
        assert not set(sent) & {4, 5, 6}
        api.rows[2].started = 999
        tree.signal((2, 200), signal.SIGKILL)
        assert sent.count(2) == 2


def test_socket_transport_transfers_one_private_descriptor_and_rejects_eof():
    left, right = owned_service.channel()
    gate, peer = owned_service.channel()
    try:
        owned_service.send(left, {'hello': 1}, gate.fileno())
        data, descriptor = owned_service.receive(right, descriptor=True)
        assert data == {'hello': 1}
        assert not os.get_inheritable(descriptor)
        with socket.socket(fileno=descriptor) as received:
            owned_service.send(received, {'ok': True})
            assert owned_service.receive(peer) == {'ok': True}
        left.close()
        with pytest.raises(RuntimeError, match='lost private service channel'):
            owned_service.receive(right)
    finally:
        for endpoint in (left, right, gate, peer):
            endpoint.close()


def test_bad_descriptor_count_closes_received_descriptors():
    left, right = owned_service.channel()
    try:
        owned_service.send(left, {'hello': 1})
        with pytest.raises(RuntimeError, match='message/descriptor'):
            owned_service.receive(right, descriptor=True)
    finally:
        left.close()
        right.close()


@pytest.mark.parametrize('failure', [None, 'monitor', 'telemetry', 'gate_identity'])
def test_go_only_after_both_trackers_and_actual_child_guard_ready(tmp_path, monkeypatch, failure):
    controller = owned_service.Controller()
    gate, peer = owned_service.channel()
    events = []
    key = (2, 200)
    monitor = SimpleNamespace(poll=lambda: None)
    tree = SimpleNamespace(folder=tmp_path, root=(1, 100), guarded={}, service_reports={},
                           register_service=lambda k: events.append(('launcher', k)),
                           check=lambda: events.append(('check', key)), same=lambda k: True,
                           services=SimpleNamespace(validate=lambda k: events.append(('pre_go', k))))
    def register(k, token):
        events.append(('aggregate', k))
        if failure == 'monitor':
            raise RuntimeError('lost aggregate registration')
    aggregate = SimpleNamespace(register_service=register)
    @contextmanager
    def attach(*args, **kwargs):
        events.append(('actual', key))
        yield monitor
    monkeypatch.setattr(guard, 'attach', attach)
    def ready(*args, **kwargs):
        events.append(('ready', key))
        if failure == 'telemetry':
            raise RuntimeError('lost actual-child telemetry')
    monkeypatch.setattr(guard, 'wait_ready', ready)
    request = dict(identity=list(key), token='a' * 32, invocation=controller.invocation)
    try:
        owned_service.send(controller.driver, request, gate.fileno())
        gate.close()
        owned_service.send(peer, dict(gated=[2, 999] if failure == 'gate_identity' else list(key), token=request['token']))
        if failure != 'gate_identity':
            owned_service.send(controller.driver, dict(**request, released=True))
        with ExitStack() as stack:
            if failure:
                with pytest.raises(RuntimeError):
                    controller.poll(tree, aggregate, stack, 30., 10.)
                with pytest.raises(RuntimeError, match='lost private service channel'):
                    owned_service.receive(peer)
            else:
                controller.poll(tree, aggregate, stack, 30., 10.)
                assert owned_service.receive(peer) == dict(go=list(key), token=request['token'])
                assert owned_service.receive(controller.driver) == dict(**request, adopted=True)
                assert owned_service.receive(controller.driver) == dict(**request, ready=True)
                assert [event[0] for event in events] == ['launcher', 'actual', 'ready', 'aggregate', 'check', 'pre_go']
    finally:
        controller.close()
        gate.close()
        peer.close()


def test_lost_registration_channel_fails_before_service_exec():
    controller = owned_service.Controller()
    controller.driver.close()
    try:
        with pytest.raises(RuntimeError, match='lost private service channel'):
            controller.poll(None, None, None, None, None)
    finally:
        controller.close()


def test_spawn_requires_invocation_capability(monkeypatch):
    monkeypatch.delenv(owned_service.ENV_FD, raising=False)
    with pytest.raises(RuntimeError, match='enabled guarded compound driver'):
        owned_service.spawn(['unused'])


@pytest.mark.parametrize('case', ['invocation', 'identity', 'token', 'extra'])
def test_strict_request_binding(case):
    request = dict(identity=[2, 200], token='a' * 32, invocation='b' * 32)
    if case == 'invocation': request['invocation'] = 'c' * 32
    if case == 'identity': request['identity'] = [True, 200]
    if case == 'token': request['token'] = '!' * 32
    if case == 'extra': request['extra'] = 1
    with pytest.raises(RuntimeError):
        owned_service.validate_request(request, 'b' * 32)


def test_non_socket_descriptor_rejected_and_closed():
    left, right = owned_service.channel()
    reader, writer = os.pipe()
    try:
        owned_service.send(left, {}, reader)
        with pytest.raises(RuntimeError, match='not a socket'):
            owned_service.receive(right, descriptor=True)
    finally:
        left.close(); right.close(); os.close(reader); os.close(writer)


def test_missing_message_body_has_bounded_refusal():
    left, right = owned_service.channel()
    right.settimeout(.02)
    try:
        left.sendall((100).to_bytes(4, 'big'))
        with pytest.raises(TimeoutError):
            owned_service.receive(right)
    finally:
        left.close(); right.close()


# This fixture uses fake legacy admission and ordinary Python children only.
# No installed broker, shared service or engine-like process name is involved.
from test_compile_tree_guard import admissions, assert_gone


def test_python_only_compound_roundtrip_one_admission_and_full_cleanup(tmp_path, admissions):
    import json
    import sys
    marker = tmp_path / 'service.json'
    command = ('import json,os,subprocess,sys,time; '
               'from atelier.harness.safety.process_tree import started; '
               f'open({str(marker)!r},"w").write(json.dumps([os.getpid(),started(os.getpid())])); '
               'subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]); time.sleep(.6)')
    driver = ('import sys; from atelier.harness.safety.owned_service import spawn; '
              f'child=spawn([sys.executable,"-c",{command!r}]); '
              'raise SystemExit(child.wait())')
    folder = tmp_path / 'guard'
    assert guarded.run([sys.executable, '-c', driver], folder, timeout=10., owned_services=True) == 0
    record = json.loads((folder/'memory-health-tree.json').read_text())
    key = json.loads(marker.read_text())
    assert record['owned_services'] == [key]
    assert record['state'] == 'child_exited' and record['cleanup_complete']
    assert record['processes'] == []
    assert len(admissions) == 1
    assert_gone(*key)


def test_python_gate_never_execs_after_controller_dies_between_bindings(tmp_path, admissions, monkeypatch):
    import json
    import sys
    marker = tmp_path / 'executed'
    captured = []
    def fail_between_bindings(self, key, token):
        captured.append(key)
        raise RuntimeError('controller failed after launcher binding before aggregate ack')
    monkeypatch.setattr(guard.TreeMonitor, 'register_service', fail_between_bindings)
    driver = ('import sys; from atelier.harness.safety.owned_service import spawn; '
              f'spawn([sys.executable,"-c",{("open("+repr(str(marker))+",\"w\").write(\"ran\")")!r}])')
    with pytest.raises(RuntimeError, match='controller failed after launcher'):
        guarded.run([sys.executable, '-c', driver], tmp_path/'guard', timeout=10., owned_services=True)
    assert not marker.exists()
    assert len(captured) == 1
    assert_gone(*captured[0])
    record = json.loads((tmp_path/'guard/memory-health-tree.json').read_text())
    assert record['cleanup_complete'] is True


def test_independent_aggregate_drains_gated_service_after_controller_process_death(tmp_path):
    import json
    import subprocess
    import sys
    import time
    identities = tmp_path / 'identities.json'
    executed = tmp_path / 'executed'
    folder = tmp_path / 'guard'
    service = 'open('+repr(str(executed))+',"w").write("ran")'
    driver = ('import sys; from atelier.harness.safety.owned_service import spawn; '
              f'spawn([sys.executable,"-c",{service!r}])')
    controller = f'''
import os,json,sys
from pathlib import Path
from contextlib import contextmanager
from atelier.harness import capacity_runtime,capacity_compat
from atelier.harness.safety import guarded,guard,process_tree
capacity_runtime.DEFAULT_CONFIG=Path({str(tmp_path/'absent-client')!r})
capacity_compat.DEFAULT_RECORD=Path({str(tmp_path/'absent-cutover')!r})
os.environ.pop('ATELIER_CAPACITY_CLIENT',None)
@contextmanager
def admitted(purpose,**options):
    options['on_slot']('big','')
    yield
guarded.render_lock=admitted
def die(self,key,token):
    Path({str(identities)!r}).write_text(json.dumps(dict(root=[self.pid,self.started],service=list(key),monitor=[self.process.pid,process_tree.started(self.process.pid)])))
    os._exit(23)
guard.TreeMonitor.register_service=die
guarded.run([sys.executable,'-c',{driver!r}],Path({str(folder)!r}),timeout=15.,owned_services=True)
'''
    process = subprocess.Popen([sys.executable, '-c', controller], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        process.communicate(timeout=12.)
        assert process.returncode == 23
        pins = json.loads(identities.read_text())
        assert_gone(*pins['root'])
        assert_gone(*pins['service'])
        assert not executed.exists()
        deadline = time.monotonic() + 5.
        while True:
            record = json.loads((folder/'memory-health-tree.json').read_text())
            if record['state'] != 'running' or time.monotonic() >= deadline:
                break
            time.sleep(.02)
        assert record['state'] == 'controller_exited'
        assert record['cleanup_complete'] is True
        assert record['processes'] == []
        assert_gone(*pins['monitor'])
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=3.)


def test_launcher_refuses_newly_execed_unregistered_service_below_private_root(tmp_path, monkeypatch):
    api = tables()
    monkeypatch.setattr(guarded, 'process_tree', api)
    with ExitStack() as stack:
        tree = guarded.Descendants(1, 100, tmp_path, (), None, 10., stack)
        tree.register_service((2, 200))
        api.rows[2].name = 'zenserver'
        tree.poll()
        api.rows[3].name = 'UnrealTraceServer'
        with pytest.raises(RuntimeError, match='unsupported unregistered shared service'):
            tree.poll()
        sent = []
        monkeypatch.setattr(guarded.os, 'kill', lambda pid, sig: sent.append(pid))
        with pytest.raises(RuntimeError, match='unsupported unregistered shared service'):
            tree.unwind(0.)
        assert sent == [2, 2]


def test_unregistered_same_name_services_keep_default_exclusions(tmp_path, monkeypatch):
    api = tables()
    api.rows[2].name = 'zenserver'
    tree = tree_guard.OwnedTree(api, 1, 100)
    assert {p['pid'] for p in tree.sample()} == {1}
    monkeypatch.setattr(guarded, 'process_tree', api)
    with ExitStack() as stack:
        launcher = guarded.Descendants(1, 100, tmp_path, (), None, 10., stack)
        launcher.poll()
        sent = []
        monkeypatch.setattr(guarded.os, 'kill', lambda pid, sig: sent.append(pid))
        launcher.unwind(0.)
        assert sent == []


def test_duplicate_or_excessive_registration_cannot_expand_authority():
    api = tables()
    registrations = owned_service.Registrations(api, (1, 100))
    registrations.register((2, 200), set())
    with pytest.raises(RuntimeError):
        registrations.register((2, 200), set())
    for pid in range(10, 10 + owned_service.MAX_SERVICES-1):
        api.add(pid, 1, 'python', 1)
        registrations.register((pid, pid*100), set())
    api.add(1000, 1, 'python', 1)
    with pytest.raises(RuntimeError):
        registrations.register((1000, 100000), set())
    assert len(registrations.evidence()) == owned_service.MAX_SERVICES


def test_live_driver_losing_capability_after_go_fails_and_drains_service(tmp_path, admissions):
    import json
    import sys
    marker = tmp_path / 'service.json'
    service = ('import os,json,time; from atelier.harness.safety.process_tree import started; '
               f'open({str(marker)!r},"w").write(json.dumps([os.getpid(),started(os.getpid())])); '
               'time.sleep(30)')
    driver = ('import os,sys,time; from atelier.harness.safety.owned_service import spawn,ENV_FD; '
              f'child=spawn([sys.executable,"-c",{service!r}]); '
              f'\nwhile not os.path.exists({str(marker)!r}): time.sleep(.005)\n'
              'os.close(int(os.environ[ENV_FD])); time.sleep(30)')
    with pytest.raises(owned_service.ChannelClosed):
        guarded.run([sys.executable, '-c', driver], tmp_path/'guard', timeout=10., owned_services=True)
    assert_gone(*json.loads(marker.read_text()))


def test_duplicate_json_fields_refused():
    left, right = owned_service.channel()
    try:
        raw = b'{"identity":[1,2],"identity":[3,4]}'
        left.sendall(len(raw).to_bytes(4,'big') + raw)
        with pytest.raises(RuntimeError, match='duplicate private service message field'):
            owned_service.receive(right)
    finally:
        left.close(); right.close()


def test_two_received_gate_descriptors_are_both_closed_on_refusal(monkeypatch):
    import array
    left, right = owned_service.channel()
    gate, peer = owned_service.channel()
    closed = []
    original = os.close
    def close(fd):
        closed.append(fd)
        original(fd)
    try:
        left.sendmsg([b'\0\0\0\2{}'], [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[gate.fileno(),peer.fileno()]))])
        monkeypatch.setattr(owned_service.os,'close',close)
        with pytest.raises(RuntimeError, match='message/descriptor'):
            owned_service.receive(right, descriptor=True)
        assert len(closed) == 2
        for fd in closed:
            with pytest.raises(OSError): os.fstat(fd)
    finally:
        left.close(); right.close(); gate.close(); peer.close()


@pytest.mark.parametrize('option', ['env','pass_fds','preexec_fn','start_new_session','shell','close_fds'])
def test_spawn_options_cannot_replace_or_leak_gate(option):
    with pytest.raises(TypeError):
        owned_service.spawn(['unused'], **{option: None})


@pytest.mark.parametrize('case', ['missing','malformed','stale','future','nan','pid','start','limit','state'])
def test_alive_private_monitor_needs_ongoing_fresh_bound_telemetry(tmp_path, monkeypatch, case):
    import json
    import time
    api = tables()
    monkeypatch.setattr(guarded, 'process_tree', api)
    with ExitStack() as stack:
        tree = guarded.Descendants(1,100,tmp_path,(),None,10.,stack)
        tree.register_service((2,200))
        path = tmp_path/'private.json'
        tree.service_reports[(2,200)] = path
        tree.guarded[(2,200)] = ('owned-service', SimpleNamespace(poll=lambda: None))
        value = dict(pid=2,process_start=200,time=time.time(),limit_bytes=10*1024**3,state='running')
        path.write_text(json.dumps(value))
        tree.check()
        changes={'stale':dict(time=time.time()-6), 'future':dict(time=time.time()+60),
                 'nan':dict(time=float('nan')), 'pid':dict(pid=999),'start':dict(process_start=999),
                 'limit':dict(limit_bytes=1), 'state':dict(state='memory_limit')}
        if case=='missing': path.unlink()
        elif case=='malformed': path.write_text('{')
        else:
            value.update(changes[case]);path.write_text(json.dumps(value))
        with pytest.raises(RuntimeError, match='lost its live receipt'):
            tree.check()


def test_live_but_stale_private_guard_fails_and_drains_after_go(tmp_path, admissions, monkeypatch):
    import json
    import sys
    marker=tmp_path/'service.json'
    service=('import os,json,time;from atelier.harness.safety.process_tree import started;'
             f'open({str(marker)!r},"w").write(json.dumps([os.getpid(),started(os.getpid())]));time.sleep(30)')
    driver=('import sys,time;from atelier.harness.safety.owned_service import spawn;'
            f'child=spawn([sys.executable,"-c",{service!r}]);child.wait()')
    original=guard.process_guard_receipt
    def stale(pid, started, report, limit):
        if marker.exists() and 'owned-service' in str(report): return False
        return original(pid,started,report,limit)
    monkeypatch.setattr(guard,'process_guard_receipt',stale)
    with pytest.raises(RuntimeError, match='lost its live receipt'):
        guarded.run([sys.executable,'-c',driver],tmp_path/'guard',timeout=10.,owned_services=True)
    assert_gone(*json.loads(marker.read_text()))
