"""Host-only recovery faults; no native jobs, services or real evidence access."""
import copy
import json
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import finalize_foliage_host_receipt as finalizer


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return dict(path=str(path), sha256=finalizer.digest(path.read_bytes()))


def approved_tail(monkeypatch):
    tail = b'TraceServer stopped without errors.\n'
    monkeypatch.setattr(finalizer, 'APPROVED_TAIL_BYTES', len(tail))
    monkeypatch.setattr(finalizer, 'APPROVED_TAIL_SHA256', finalizer.digest(tail))
    return tail


def test_exact_bound_prefix_and_only_approved_tail(monkeypatch):
    tail = approved_tail(monkeypatch); prefix = b'native completed\n'
    expected = finalizer.digest(prefix)
    assert finalizer.prefix_proof(prefix, expected)['classifier'] == 'unchanged'
    proof = finalizer.prefix_proof(prefix + tail, expected)
    assert proof['prefix_bytes'] == len(prefix) and proof['tail_sha256'] == finalizer.digest(tail)
    for changed in (b'changed\n' + tail, prefix + b'unknown\n', prefix + tail + b'error\n', prefix + tail[:-1]):
        with pytest.raises(ValueError):
            finalizer.prefix_proof(changed, expected)


def test_snapshot_refuses_replacement_and_append_races(tmp_path, monkeypatch):
    prefix = b'bound\n'; path = tmp_path / 'stdout.log'; path.write_bytes(prefix)
    binding = dict(path=str(path), sha256=finalizer.digest(prefix)); original = finalizer.stable_read
    calls = 0
    def racing(path, *args):
        nonlocal calls
        calls += 1
        if calls == 2:
            path.write_bytes(prefix + b'late\n')
        return original(path, *args)
    monkeypatch.setattr(finalizer, 'stable_read', racing)
    with pytest.raises(ValueError, match='raced'):
        finalizer.snapshot_stdout(binding, tmp_path / 'snapshot.log')
    assert not (tmp_path / 'snapshot.log').exists()


def test_same_bytes_replacement_is_not_stable(tmp_path):
    path = tmp_path / 'stdout.log'; path.write_bytes(b'bound\n')
    record = finalizer.snapshot_stdout(dict(path=str(path), sha256=finalizer.digest(path.read_bytes())), tmp_path / 'snapshot.log')
    replacement = tmp_path / 'replacement'; replacement.write_bytes(path.read_bytes()); replacement.replace(path)
    with pytest.raises(ValueError, match='across comparison'):
        finalizer.unchanged_snapshot(record)


def fixture(tmp_path, monkeypatch):
    root = tmp_path / 'evidence'; source = tmp_path / 'source'; receiver = tmp_path / 'receiver'; producer = tmp_path / 'producer'
    for path in (root, source, receiver, producer):
        path.mkdir()
    monkeypatch.chdir(receiver)
    native = dict(engine_build_id='fixture', modules={'Yorimichi': {'sha256': 'native'}}, compile_fingerprint='built')
    compared = dict(schema=1, native_geometry_complete=True, owners=18, authored_lods=84, source_lod_packages=66,
                    native_packages=84, native_pages=150, complete=False, native_complete=False,
                    production_runtime_complete=False, normal_native_reuse=False, assets={}, scope='fixture only')
    calls = []; hosts = {}; launches = {}; tail = approved_tail(monkeypatch)
    for phase in ('original', 'current'):
        folder = root / phase; launch = dict(phase=phase)
        spec = dict(phase=phase, source=str(source), receiving=str(receiver), producer=str(producer),
                    source_head=finalizer.SOURCE_HEAD, receiving_head=finalizer.RECEIVING_HEAD, producer_head='producer',
                    package='/Game/AtelierValidation/Foliage_0123456789ab', content=str(receiver / 'Content'),
                    manifests={'fixture': 'exact'}, launch=launch, inputs={'fixture': 'exact'})
        spec_row = write(folder / 'spec.json', spec)
        marker = 'FOLIAGE ACTUAL18/84/150 NATIVE FIXTURE COMPLETE ' + phase + ' ' + spec_row['sha256']
        log = folder / 'guard/stdout.log'; log.parent.mkdir(); prefix = (marker + '\n').encode(); log.write_bytes(prefix)
        stdout = dict(path=str(log), sha256=finalizer.digest(prefix))
        if phase == 'current':
            log.write_bytes(prefix + tail)
        whole = write(folder / 'whole-result.json', dict(phase=phase, exit_code=0, native=native,
                    spec_sha256=spec_row['sha256'], source_head=spec['source_head'], receiving_head=spec['receiving_head'],
                    producer_head=spec['producer_head'], launch=launch,
                    argv=['-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0']))
        guard = dict(receipt=write(folder / 'guard/memory-health-tree.json', dict(state='child_exited', cleanup_complete=True,
                    processes=[], footprint_bytes=0)), stdout=stdout, marker=marker, whole_result=whole)
        engine = write(folder / 'engine.log', {'ddc': 'fixture'})
        host = dict(native=native, whole_exit=0, guard_empty=True, fixture_absent=True, guard=guard,
                    spec_sha256=spec_row['sha256'], launch=launch, engine_log=engine, startup_ddc={'ddc': 'fixture'})
        write(folder / 'host-result.json', host); hosts[phase] = host; launches[phase] = launch
        write(folder / 'native.json', {phase: {'retained': phase}})
        write(folder / 'cleanup.json', dict(root=str(receiver / 'Content/AtelierValidation/Foliage_0123456789ab'),
                    remaining={}, allowed_packages=[spec['package'] + '/Japan/Assets/Tree']))
    old = dict(**compared, whole_exit=0, guards_empty=True, fixture_absent=True, native=native,
               source_head=finalizer.SOURCE_HEAD, receiving_head=finalizer.RECEIVING_HEAD,
               original_guard=hosts['original']['guard'], current_guard=hosts['current']['guard'], launches=launches)
    write(root / 'host-result.json', old)
    def compare(records, manifests):
        calls.append('compare')
        assert records == {'original': {'retained': 'original'}, 'current': {'retained': 'current'}}
        assert manifests == {'fixture': 'exact'}
        return copy.deepcopy(compared)
    def guard_binding(record):
        calls.append('guard')
        assert finalizer.digest(Path(record['stdout']['path']).read_bytes()) == record['stdout']['sha256']
        assert record['stdout']['path'].endswith('-stdout.log')
        assert json.loads(Path(record['whole_result']['path']).read_text())['exit_code'] == 0
    modules = dict(foliage_native_equivalence=SimpleNamespace(bound_inputs=lambda spec: calls.append('inputs'), compare=compare),
                   atomic_equivalence=SimpleNamespace(guard_binding=guard_binding,
                        artifact=lambda binding: Path(binding['path']).read_bytes()),
                   track_native_equivalence=SimpleNamespace(check_private_launch=lambda spec: spec['launch'],
                        startup_ddc=lambda launch, text: json.loads(text)),
                   network_review_common=SimpleNamespace(current_native_build=lambda ctx: native))
    monkeypatch.setattr(finalizer, 'original_api', lambda source, spec: modules)
    heads = {source: finalizer.SOURCE_HEAD, receiver: finalizer.RECEIVING_HEAD, producer: 'producer'}
    monkeypatch.setattr(finalizer, 'clean_head', lambda path: heads.get(path, 'independent-finalizer-head'))
    from atelier import build
    monkeypatch.setattr(build, 'Context', lambda name: SimpleNamespace(game_dir=receiver / 'games/yorimichi'))
    return root, calls, modules


def test_finalization_keeps_old_evidence_and_records_complete_lineage(tmp_path, monkeypatch):
    root, calls, _ = fixture(tmp_path, monkeypatch)
    old_paths = [root / 'host-result.json', root / 'original/host-result.json', root / 'current/host-result.json']
    before = {str(p): p.read_bytes() for p in old_paths}
    result = finalizer.finalize(root, root / 'finalized-fixture')
    assert {str(p): p.read_bytes() for p in old_paths} == before
    lineage = result['finalization']
    assert lineage['no_new_native_execution'] is True and lineage['tool']['head'] == 'independent-finalizer-head'
    assert all(row['sha256'] == finalizer.digest(before[path]) for path, row in lineage['original_receipts'].items())
    assert lineage['phases']['current']['stdout_finalization']['appended_bytes'] > 0
    assert calls.count('compare') == 1 and calls.count('guard') == 4 and calls.count('inputs') == 4
    assert result['native_geometry_complete'] and not result['native_complete'] and not result['normal_native_reuse']
    assert (root / 'finalized-fixture/finalized-host-result.json').is_file()
    with pytest.raises(ValueError, match='Fresh'):
        finalizer.finalize(root, root / 'finalized-fixture')


@pytest.mark.parametrize('fault', ['compare', 'live_append', 'physical_remnant', 'retained_changed'])
def test_refusals_never_publish_final_receipt(tmp_path, monkeypatch, fault):
    root, _, modules = fixture(tmp_path, monkeypatch)
    compare = modules['foliage_native_equivalence'].compare
    def changed(records, manifests):
        result = compare(records, manifests)
        if fault == 'compare':
            raise ValueError('native geometry differs')
        if fault == 'live_append':
            with (root / 'current/guard/stdout.log').open('ab') as stream:
                stream.write(b'late\n')
        if fault == 'physical_remnant':
            spec = json.loads((root / 'current/spec.json').read_text())
            (Path(spec['content']) / spec['package'].removeprefix('/Game/')).mkdir(parents=True)
        if fault == 'retained_changed':
            (root / 'current/native.json').write_text('{"changed": true}')
        return result
    modules['foliage_native_equivalence'].compare = changed
    before = (root / 'host-result.json').read_bytes()
    with pytest.raises(ValueError):
        finalizer.finalize(root, root / 'finalized-refusal')
    assert not (root / 'finalized-refusal/finalized-host-result.json').exists()
    assert (root / 'host-result.json').read_bytes() == before


def test_receiver_build_stays_bound_when_original_source_prepends_its_studio(tmp_path):
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
    (world / 'yori.py').write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'platform/studio'))\n")
    modules = [native / 'foliage_native_equivalence.py', tools / 'atomic_equivalence.py',
               native / 'track_native_equivalence.py', tools / 'network_review_common.py']
    for module in modules:
        module.write_text('import yori\n')
    spec = dict(inputs={str(p): finalizer.digest(p.read_bytes()) for p in modules})
    spec_file = tmp_path / 'spec.json'; spec_file.write_text(json.dumps(spec))
    program = r'''
import importlib.util, json, pathlib, sys
receiver, source, tool, spec_file = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(receiver / 'platform/studio'))
loading = importlib.util.spec_from_file_location('finalizer', tool)
finalizer = importlib.util.module_from_spec(loading); loading.loader.exec_module(finalizer)
api = finalizer.original_api(source, json.loads(spec_file.read_text()))
assert sys.path[0] == str(source / 'platform/studio')
assert pathlib.Path(api['foliage_native_equivalence'].__file__).is_relative_to(source)
assert pathlib.Path(finalizer.build.__file__).is_relative_to(receiver)
assert finalizer.build.Context('yorimichi').game_dir == receiver / 'games/yorimichi'
'''
    result = subprocess.run([sys.executable, '-I', '-S', '-c', program, str(receiver), str(source),
                             str(Path(finalizer.__file__).absolute()), str(spec_file)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
