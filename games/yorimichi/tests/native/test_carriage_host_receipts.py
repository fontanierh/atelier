"""One-off host orchestration faults. Native calls are fake; retained evidence is temporary."""
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import carriage_host_receipts as host


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))
    return dict(path=str(path), sha256=host.digest(path.read_bytes()))


def approved(monkeypatch):
    tail = b'approved complete TraceServer tail\n'
    monkeypatch.setattr(host, 'APPROVED_TAIL_BYTES', len(tail))
    monkeypatch.setattr(host, 'APPROVED_TAIL_SHA256', host.digest(tail))
    return tail


def test_original_prefix_accepts_only_exact_reviewed_append(monkeypatch):
    tail = approved(monkeypatch); prefix = b'whole0 marker\n'; old = host.digest(prefix)
    assert host.prefix_proof(prefix + tail, old)['appended_bytes'] == len(tail)
    for value in (b'changed\n' + tail, prefix + b'unknown\n', prefix + tail + b'error\n', prefix + tail[:-1]):
        with pytest.raises(ValueError):
            host.prefix_proof(value, old)


def test_freezing_refuses_race_and_live_append_does_not_invalidate_frozen_current(tmp_path, monkeypatch):
    path = tmp_path / 'stdout'; path.write_bytes(b'marker\n')
    frozen = host.frozen_current_stdout(path, tmp_path / 'frozen', 'marker')
    path.write_bytes(path.read_bytes() + b'late shared service output\n')
    assert host.digest(Path(frozen['snapshot']['path']).read_bytes()) == frozen['snapshot']['sha256']
    original = host.stable_read; calls = 0
    def racing(path, *args):
        nonlocal calls
        calls += 1
        if calls == 2:
            path.write_bytes(b'changed during snapshot\n')
        return original(path, *args)
    monkeypatch.setattr(host, 'stable_read', racing)
    with pytest.raises(ValueError, match='raced'):
        host.frozen_current_stdout(path, tmp_path / 'raced', 'marker')
    assert not (tmp_path / 'raced').exists()


def fake_session(tmp_path, monkeypatch):
    root = tmp_path / 'evidence'; root.mkdir(); source = tmp_path / 'old-source'; receiver = tmp_path / 'receiver'
    source.mkdir(); receiver.mkdir(); events = []; retained = host.Retained(); native = {'native': 'unchanged'}
    tool = dict(path='independent-tool', sha256='tool-sha', head='new-host-head')
    package = '/Game/AtelierValidation/Carriage_0123456789ab'; content = receiver / 'games/yorimichi/unreal/Content'
    expected = {**{f'body{k}': 3 for k in range(7)}, **{f'door{k}': 1 for k in range(60)}}
    specs = {}; original = None
    for phase in ('original', 'current'):
        base = root / phase; base.mkdir(); document = root / ('document-' + phase + '.json'); put(document, {'vehicles': phase})
        spec = dict(phase=phase, source=str(source), source_head=host.SOURCE_HEAD, receiving=str(receiver),
                    receiving_head=host.RECEIVING_HEAD, content=str(content), package=package, output=str(base),
                    document=str(document), inputs={}, launch=dict(args=['private-arg'], startup_log=str(base / 'engine.log')))
        script = source / 'games/yorimichi/tests/native/carriage_native_equivalence.py'
        script.parent.mkdir(parents=True, exist_ok=True); script.write_bytes(b'# old native driver\n')
        spec['inputs'][str(script)] = host.digest(script.read_bytes())
        put(base / 'spec.json', spec); specs[phase] = spec; retained.load(base / 'spec.json')
        put(base / 'native.json', {phase: {name: {'policy_scope': 'fixture'} for name in expected}})
        put(base / 'materials.json', {'phase': phase}); put(base / 'poses.json', {'phase': phase})
        put(base / 'cleanup.json', dict(root=str(content / package.removeprefix('/Game/')), remaining={},
                                       allowed_packages=[package + '/body']))
    def artifact(binding):
        data = Path(binding['path']).read_bytes()
        assert host.digest(data) == binding['sha256']
        return data
    def guard_binding(guard):
        events.append('guard')
        assert b'CARRIAGE ACTUAL67/81' in artifact(guard['stdout'])
        assert json.loads(artifact(guard['whole_result']))['exit_code'] == 0
    proof = SimpleNamespace(check_private_launch=lambda spec: spec['launch'], startup_ddc=lambda launch, text: {'ddc': 'private'})
    generic = SimpleNamespace(artifact=artifact, guard_binding=guard_binding)
    def strict_cleanup(spec, record):
        events.append('strict_cleanup'); assert record['remaining'] == {}
    session = SimpleNamespace(root=root, source=source, receiver=receiver, specs=specs, retained=retained, native=native,
        proof=proof, generic=generic, api={'run_track_native_equivalence': SimpleNamespace(strict_cleanup=strict_cleanup)},
        ctx=SimpleNamespace(env=lambda: {}), tool_binding=lambda: tool,
        inputs=lambda: events.append('inputs'), startup=lambda phase, value: events.append('startup-' + phase))
    def metadata(phase):
        events.append('metadata-' + phase)
        return (retained.load(root / phase / 'native.json'), retained.load(Path(specs[phase]['document']))['vehicles'],
                retained.load(root / phase / 'materials.json'), retained.load(root / phase / 'poses.json'))
    def finish():
        events.append('finish'); retained.check()
    session.metadata = metadata; session.finish = finish
    def factory(workspace, output):
        session.output = Path(output); assert not session.output.exists(); return session
    monkeypatch.setattr(host, 'Session', factory)
    monkeypatch.setattr(host, 'empty_owned_tree', lambda path: events.append('empty-root-tree'))
    return session, events, artifact


def seal_fixture(session, monkeypatch):
    root = session.root; spec = session.specs['original']; base = root / 'original'
    spec_sha = session.retained.rows[str(base / 'spec.json')]['sha256']
    marker = 'CARRIAGE ACTUAL67/81 VEHICLE FIXTURE COMPLETE original ' + spec_sha
    prefix = marker.encode() + b'\n'; prefix += b'x' * (2493961 - len(prefix) - 1) + b'\n'
    log = base / 'guard/stdout.log'; log.parent.mkdir(); log.write_bytes(prefix + approved(monkeypatch))
    whole = dict(phase='original', exit_code=0, native=session.native, spec_sha256=spec_sha,
                 source_head=host.SOURCE_HEAD, receiving_head=host.RECEIVING_HEAD, work_seconds=2400, queue_seconds=1200)
    whole_row = put(base / 'whole-result.json', whole)
    receipt = put(base / 'guard/memory-health-tree.json', {'state': 'child_exited'})
    original = dict(phase='original', whole_exit=0, native=session.native, spec_sha256=spec_sha,
                   source_head=host.SOURCE_HEAD, receiving_head=host.RECEIVING_HEAD, complete=False, native_complete=False,
                   guard_empty=True, fixture_absent=True, guard=dict(marker=marker, receipt=receipt,
                   whole_result=whole_row, stdout=dict(path=str(log), sha256=host.digest(prefix))))
    put(base / 'host-result.json', original)
    return original


def test_original_recovery_preserves_invocation_and_old_receipt_lineage(tmp_path, monkeypatch):
    session, events, _ = fake_session(tmp_path, monkeypatch); original = seal_fixture(session, monkeypatch)
    path = session.root / 'original/host-result.json'; before = path.read_bytes()
    result = host.seal_original(session.root, session.root / 'sealed-original-01')
    assert path.read_bytes() == before and result['finalization']['original_receipt']['sha256'] == host.digest(before)
    assert result['finalization']['no_new_native_execution'] and result['finalization']['original_phase_only']
    assert result['finalization']['tool']['head'] == 'new-host-head'
    assert result['guard']['whole_result'] == original['guard']['whole_result'] and result['native'] == original['native']
    assert result['finalization']['stdout_finalization']['prefix_bytes'] == 2493961
    assert 'empty-root-tree' in events and 'metadata-original' in events and 'finish' in events


@pytest.mark.parametrize('fault', ['unknown_tail', 'changed_prefix', 'root_alive', 'fixture_present'])
def test_original_recovery_refuses_without_publishing(tmp_path, monkeypatch, fault):
    session, _, _ = fake_session(tmp_path, monkeypatch); original = seal_fixture(session, monkeypatch)
    if fault in ('unknown_tail', 'changed_prefix'):
        path = Path(original['guard']['stdout']['path']); data = path.read_bytes()
        path.write_bytes((b'changed' + data[7:]) if fault == 'changed_prefix' else data + b'unknown\n')
    if fault == 'root_alive':
        monkeypatch.setattr(host, 'empty_owned_tree', lambda path: host.require(False, 'root alive'))
    if fault == 'fixture_present':
        spec = session.specs['original']; (Path(spec['content']) / spec['package'].removeprefix('/Game/')).mkdir(parents=True)
    output = session.root / 'sealed-original-refusal'
    with pytest.raises(ValueError):
        host.seal_original(session.root, output)
    assert not (output / 'sealed-original-host-result.json').exists()


def test_current_launch_keeps_old_driver_and_guards_freezes_before_exact_compare(tmp_path, monkeypatch):
    session, events, artifact = fake_session(tmp_path, monkeypatch); original = seal_fixture(session, monkeypatch)
    sealed_path = session.root / 'sealed.json'; put(sealed_path, {'sealed': True}); session.retained.load(sealed_path)
    # Current orchestration consumes a separately tested sealed-original gate.
    monkeypatch.setattr(host, 'validate_sealed_original', lambda session, path: original)
    original_log = original['guard']['stdout']['path']
    # Replace only the fake guard binding with one permitting old mutable original in this orchestration unit.
    def guard_binding(value):
        if value is original['guard']:
            return
        artifact(value['stdout']); events.append('guard-frozen')
    session.generic.guard_binding = guard_binding
    selected = {}
    class Command:
        def __init__(self, script, marker, **kwargs):
            selected.update(script=script, marker=marker, options=kwargs)
        @contextmanager
        def prepared(self, ctx):
            yield ['UnrealEditor-Cmd', 'private-arg'], {}
    monkeypatch.setattr(host.build, 'UnrealScript', Command)
    from atelier.harness.safety import guarded
    def fake_run(argv, guard, **kwargs):
        events.append('native-whole'); selected['guard'] = kwargs
        guard.mkdir(); (guard / 'stdout.log').write_text(selected['marker'] + '\ncomplete native output\n')
        put(guard / 'memory-health-tree.json', {'state': 'child_exited'})
        put(session.root / 'current/engine.log', {'ddc': 'private'})
        return 0
    monkeypatch.setattr(guarded, 'run', fake_run)
    freezing = host.frozen_current_stdout
    def freeze(*args):
        events.append('freeze'); return freezing(*args)
    monkeypatch.setattr(host, 'frozen_current_stdout', freeze)
    def compare(records, vehicles, materials, poses):
        events.append('compare')
        assert set(records) == {'original', 'current'} and len(records['original']) == len(records['current']) == 67
        assert vehicles == 'current' and materials == poses == {'original': {'phase': 'original'}, 'current': {'phase': 'current'}}
        with (session.root / 'current/guard/stdout.log').open('ab') as stream:
            stream.write(b'late shared TraceServer output\n')
        return dict(fixture_geometry_complete=True, complete=False, native_complete=False, native_task_reuse=False)
    session.proof.compare = compare
    result = host.run_current(session.root, session.root / 'current-host-01', sealed_path)
    assert selected['script'] == session.source / 'games/yorimichi/tests/native/carriage_native_equivalence.py'
    assert selected['guard']['timeout'] == 2400 and selected['guard']['queue_seconds'] == 1200
    assert selected['guard']['limit_gib'] == 10 and selected['guard']['track_tree'] is True
    assert selected['guard']['env']['ATELIER_CARRIAGE_NATIVE_SPEC'] == str(session.root / 'current/spec.json')
    assert events.index('native-whole') < events.index('empty-root-tree') < events.index('freeze') < events.index('compare')
    assert result['fixture_geometry_complete'] and not result['native_complete'] and not result['native_task_reuse']
    assert result['host_orchestration']['tool']['head'] == 'new-host-head'
    assert result['current_guard']['stdout']['path'].endswith('current-host-01/current-stdout.log')
    assert Path(original_log).exists()


def test_sealed_original_revalidates_old_receipt_lineage_and_tool_identity(tmp_path, monkeypatch):
    session, _, _ = fake_session(tmp_path, monkeypatch); seal_fixture(session, monkeypatch)
    output = session.root / 'sealed-original-01'; host.seal_original(session.root, output)
    sealed_path = output / 'sealed-original-host-result.json'
    sealed = host.validate_sealed_original(session, sealed_path)
    assert sealed['finalization']['no_new_native_execution']
    binding = session.tool_binding
    session.tool_binding = lambda: dict(binding(), head='other-host-commit')
    with pytest.raises(ValueError, match='lineage'):
        host.validate_sealed_original(session, sealed_path)
    session.tool_binding = binding
    path = session.root / 'original/host-result.json'; path.write_text('{"overwritten": true}')
    with pytest.raises(AssertionError):
        host.validate_sealed_original(session, sealed_path)


def test_receiver_package_is_bound_before_original_source_imports(tmp_path):
    import subprocess
    source, receiver = tmp_path / 'source', tmp_path / 'receiver'
    for root in (source, receiver):
        package = root / 'platform/studio/atelier'; package.mkdir(parents=True)
        (package / '__init__.py').write_text('')
        (package / 'build.py').write_text(
            "from pathlib import Path\nclass Context:\n"
            "    def __init__(self, name):\n"
            "        self.game_dir = Path(__file__).resolve().parents[3] / 'games' / name\n")
    native = source / 'games/yorimichi/tests/native'; native.mkdir(parents=True)
    tools = source / 'games/yorimichi/tools'; tools.mkdir(parents=True)
    world = source / 'games/yorimichi/world'; world.mkdir(parents=True)
    (world / 'yori.py').write_text("import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'platform/studio'))\n")
    paths = [native / (name + '.py') for name in ('carriage_native_equivalence', 'track_native_equivalence', 'run_track_native_equivalence')]
    paths += [tools / (name + '.py') for name in ('atomic_equivalence', 'network_review_common')]
    for path in paths:
        path.write_text('import yori\n')
    spec = tmp_path / 'spec.json'; spec.write_text(json.dumps(dict(inputs={str(p): host.digest(p.read_bytes()) for p in paths})))
    code = r'''
import importlib.util, json, pathlib, sys
receiver, source, tool, spec = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(receiver / 'platform/studio'))
loading = importlib.util.spec_from_file_location('host', tool)
host = importlib.util.module_from_spec(loading); loading.loader.exec_module(host)
modules = host.original_api(source, json.loads(spec.read_text()))
assert sys.path[0] == str(source / 'platform/studio')
assert pathlib.Path(modules['carriage_native_equivalence'].__file__).is_relative_to(source)
assert pathlib.Path(host.build.__file__).is_relative_to(receiver)
assert host.build.Context('yorimichi').game_dir == receiver / 'games/yorimichi'
'''
    result = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(receiver), str(source),
                             str(Path(host.__file__).absolute()), str(spec)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_failed_native_whole_is_recorded_before_success_empty_or_snapshot_gates(tmp_path, monkeypatch):
    session, events, _ = fake_session(tmp_path, monkeypatch); original = seal_fixture(session, monkeypatch)
    sealed = session.root / 'sealed.json'; put(sealed, {'sealed': True})
    monkeypatch.setattr(host, 'validate_sealed_original', lambda session, path: original)
    class Command:
        def __init__(self, *args, **kwargs):
            pass
        @contextmanager
        def prepared(self, ctx):
            yield ['actual-editor-argv', 'private-arg'], {}
    monkeypatch.setattr(host.build, 'UnrealScript', Command)
    from atelier.harness.safety import guarded
    monkeypatch.setattr(guarded, 'run', lambda *args, **kwargs: 7)
    monkeypatch.setattr(host, 'empty_owned_tree', lambda path: pytest.fail('failure must preserve whole before cleanup gate'))
    monkeypatch.setattr(host, 'frozen_current_stdout', lambda *args: pytest.fail('failure cannot create success stdout snapshot'))
    output = session.root / 'current-host-failed'
    with pytest.raises(ValueError, match='actual whole outcome retained'):
        host.run_current(session.root, output, sealed)
    whole = json.loads((output / 'whole-result.json').read_text())
    assert whole['exit_code'] == 7 and whole['argv'] == ['actual-editor-argv', 'private-arg']
    assert whole['native'] == session.native and whole['source_head'] == host.SOURCE_HEAD
    assert whole['receiving_head'] == host.RECEIVING_HEAD and whole['host_tool'] == session.tool_binding()
    assert whole['native_driver']['path'].startswith(str(session.source))
    assert not (output / 'current-host-result.json').exists() and not (output / 'paired-host-result.json').exists()
    assert not (output / 'current-stdout.log').exists() and 'compare' not in events
