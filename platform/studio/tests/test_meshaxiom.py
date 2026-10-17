"""Checkpoint identity checks must fail closed before allocating model memory."""
import hashlib
import json

import pytest

from atelier.ai.meshaxiom import install


def payloads(tmp_path, monkeypatch):
    folder = tmp_path/'models/weights'
    folder.mkdir(parents=True)
    checksums = {}
    for kind in ('vertex', 'topology', 'vae'):
        data = f'fixture-{kind}'.encode()
        (folder/f'{kind}-ema.pt').write_bytes(data)
        checksums[kind] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(install, 'CHECKPOINTS', checksums)
    return folder


def test_changed_checkpoint_rejected_even_when_size_matches(tmp_path, monkeypatch):
    folder = payloads(tmp_path, monkeypatch)
    path = folder/'vertex-ema.pt'
    data = path.read_bytes()
    path.write_bytes(b'X'+data[1:])
    with pytest.raises(ValueError, match='hash mismatch'):
        install.verify_one(tmp_path, 'vertex')


def test_incomplete_payload_cannot_produce_verification_receipt(tmp_path, monkeypatch):
    folder = payloads(tmp_path, monkeypatch)
    (folder/'topology-ema.pt').unlink()
    with pytest.raises(FileNotFoundError):
        install.verify(tmp_path)
    assert not (tmp_path/'verified.json').exists()


def test_complete_payload_receipt_identifies_every_consumed_file(tmp_path, monkeypatch):
    payloads(tmp_path, monkeypatch)
    install.verify(tmp_path)
    records = json.loads((tmp_path/'verified.json').read_text())
    assert {r['sha256'] for r in records} == set(install.CHECKPOINTS.values())
    for record in records:
        assert hashlib.sha256((tmp_path/'models'/record['file']).read_bytes()).hexdigest() == record['sha256']


@pytest.mark.parametrize('flag,value', [('--face-budget', '-1'), ('--max-nodes', '26001'), ('--stop-level', '10')])
def test_unsafe_worker_arguments_fail_before_allocating_or_creating_output(tmp_path, monkeypatch, flag, value):
    from atelier.ai.meshaxiom import worker
    output = tmp_path/'result'
    monkeypatch.setattr('sys.argv', ['worker', '--root', str(tmp_path), '--image', str(tmp_path/'image.png'),
                                    '--stage', 'vertex', '--output', str(output), flag, value])
    with pytest.raises(SystemExit) as error:
        worker.main()
    assert error.value.code == 2
    assert not output.exists()


def vertex_fixture(tmp_path):
    from types import SimpleNamespace
    from atelier.ai.meshaxiom import MODEL_REVISION, SOURCE_REVISION
    image=tmp_path/'image.png';image.write_bytes(b'image A')
    vertices=tmp_path/'vertices.npz';vertices.write_bytes(b'vertices A')
    report=dict(status='complete',stage='vertex',source_revision=SOURCE_REVISION,model_revision=MODEL_REVISION,
                face_budget=2000,steps=20,seed=99,input_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                vertices_sha256=hashlib.sha256(vertices.read_bytes()).hexdigest())
    (tmp_path/'vertex-report.json').write_text(json.dumps(report))
    return SimpleNamespace(output=tmp_path,image=image,face_budget=2000,steps=20,seed=99)


def test_topology_resume_rejects_changed_reference(tmp_path):
    from atelier.ai.meshaxiom.worker import validate_vertex_input
    args=vertex_fixture(tmp_path)
    validate_vertex_input(args)
    args.image.write_bytes(b'image B')
    with pytest.raises(ValueError,match='does not match'):
        validate_vertex_input(args)


def test_topology_resume_rejects_modified_vertices(tmp_path):
    from atelier.ai.meshaxiom.worker import validate_vertex_input
    args=vertex_fixture(tmp_path)
    (tmp_path/'vertices.npz').write_bytes(b'vertices B')
    with pytest.raises(ValueError,match='byte identity'):
        validate_vertex_input(args)


def test_upstream_edits_are_rejected_even_at_pinned_head(monkeypatch,tmp_path):
    outputs=iter([install.SOURCE_REVISION,' M src/model.py'])
    monkeypatch.setattr(install.subprocess,'check_output',lambda *a,**kw:next(outputs))
    with pytest.raises(ValueError,match='must be clean'):
        install.verify_source(tmp_path)


def test_larger_session_reserves_full_cpu_memory_gpu_without_changing_shared_profile(monkeypatch):
    from types import SimpleNamespace
    from atelier.ai.meshaxiom.guarded import admission_for
    from atelier.harness import capacity_runtime, capacity_client
    request = dict(resources=dict(memory_mib=10240, gpu_mib=0, cpu_millis=8000),
                   checkout='fixture', locks=['checkout:fixture'], performance=True)
    original = json.loads(json.dumps(request))
    baseline = SimpleNamespace(request=request, mode='capacity', socket_path='/fixture/socket',
                               timeout=2, cutover='/fixture/cutover')
    monkeypatch.setattr(capacity_runtime, 'configured_session', lambda **kw: baseline)
    monkeypatch.setattr(capacity_client, 'AdmissionSession', lambda *a, **kw: (a, kw))
    (endpoint, selected), options = admission_for(['python'], 'report', 3600, 'model', 16)
    assert request == original
    assert selected['resources'] == dict(memory_mib=16384, gpu_mib=16384, cpu_millis=8000)
    assert selected['locks'] == request['locks'] and selected['checkout'] == request['checkout']
    assert selected['performance'] is True
    assert endpoint == baseline.socket_path and options['cutover'] == baseline.cutover


@pytest.mark.parametrize('ceiling', [9, 17])
def test_session_ceiling_rejected_before_admission(ceiling):
    from atelier.ai.meshaxiom.guarded import admission_for
    with pytest.raises(ValueError, match='10–16 GiB'):
        admission_for([], 'report', 3600, 'model', ceiling)
