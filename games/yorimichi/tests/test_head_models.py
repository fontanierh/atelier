"""Guarded experiment dispatch and source identity checks, without ML runtimes."""
import importlib.util
from pathlib import Path
import pytest

TOOLS = Path(__file__).resolve().parents[1]/'tools'


def load(path):
    spec = importlib.util.spec_from_file_location('head_models_test_'+path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_large_head_job_reserves_and_enforces_same_whole_tree_limit(monkeypatch, tmp_path):
    from atelier.harness.safety import guarded
    from atelier.ai.meshaxiom import guarded as mesh_guarded
    module = load(TOOLS/'head_models.py')
    monkeypatch.setattr(module, 'REPO', tmp_path)
    calls = {}
    def reserve(command, report, timeout, purpose, memory):
        calls['reservation'] = (command, report, timeout, purpose, memory)
        return 'explicit-session'
    def run(command, report, **kwargs):
        calls['run'] = (command, report, kwargs)
        return 23
    monkeypatch.setattr(mesh_guarded, 'admission_for', reserve)
    monkeypatch.setattr(guarded, 'run', run)
    runtime = tmp_path/'build/yorimichi/models'
    result = module.main(['native', 'generate', '--root', str(runtime), '--report', str(tmp_path/'guard'),
                          '--memory-gib', '14', '--', '--image', 'reference.png'])
    command, report, options = calls['run']
    assert result == 23
    assert calls['reservation'][:2] == (command, report)
    assert calls['reservation'][-1] == options['limit_gib'] == 14
    assert options['aggregate_tree'] is True
    assert options['admission'] == 'explicit-session'
    assert command[:2] == [str(runtime/'pixal-venv/bin/python'), '-u']
    assert command[-2:] == ['--image', 'reference.png']


def test_head_job_refusal_never_runs_a_worker(monkeypatch, tmp_path):
    from atelier.harness.safety import guarded
    module = load(TOOLS/'head_models.py')
    monkeypatch.setattr(module, 'REPO', tmp_path)
    def refused(*args, **kwargs):
        raise RuntimeError('admission unavailable')
    monkeypatch.setattr(guarded, 'run', refused)
    runtime = tmp_path/'build/yorimichi/models'
    with pytest.raises(RuntimeError, match='admission unavailable'):
        module.main(['trellis', 'setup', '--root', str(runtime), '--report', str(tmp_path/'guard')])
    assert not runtime.exists()


@pytest.mark.parametrize('change', ['revision', 'patch'])
def test_source_identity_rejects_unreviewed_revision_or_patch(monkeypatch, tmp_path, change):
    support = load(TOOLS/'head_models/support.py')
    def output(command, **kwargs):
        if command[-2:] == ['rev-parse', 'HEAD']:
            return 'wrong' if change == 'revision' else support.SOURCES['trellis2mlx'][1]
        return 'unexpected source patch' if change == 'patch' else ''
    monkeypatch.setattr(support.subprocess, 'check_output', output)
    with pytest.raises(ValueError, match='Unreviewed|Unexpected'):
        support.verify_source(tmp_path, 'trellis')


def test_dense_triangle_proof_keeps_winding_and_duplicate_counts():
    import numpy as np
    geometry = load(TOOLS/'head_models/geometry.py')
    triangle = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], dtype='float32')
    # Degenerates remain native triangles too; repeated minima cannot alter the comparison.
    degenerate = triangle[[0, 0, 1]]
    source = np.array([triangle, triangle, degenerate])
    equivalent = np.array([np.roll(degenerate, 1, axis=0), np.roll(triangle, 2, axis=0), triangle])
    equivalent[equivalent == 0] = -0.
    assert geometry.same_triangles(source, equivalent)
    assert not geometry.same_triangles(source, source[:, ::-1])
    assert not geometry.same_triangles(source, source[:2])
    changed = source.copy()
    changed[0, 0, 0] = np.nextafter(np.float32(0), np.float32(1))
    assert not geometry.same_triangles(source, changed)
    with pytest.raises(ValueError, match='Nonfinite'):
        geometry.canonical_triangles(np.full((1, 3, 3), np.nan))


def test_vertex_bake_matches_colors_by_decoder_coordinates_without_mutation():
    import numpy as np
    bake = load(TOOLS/'head_models/vertex_bake.py')
    coords = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]])
    attributes = np.array([[.1, .2, .3], [.4, .5, .6], [.7, .8, .9]], dtype='float32')
    original = attributes.copy()
    assert np.array_equal(bake.vertex_colors(coords, coords[[2, 0, 1]], attributes[[2, 0, 1]], 8), attributes)
    assert np.array_equal(attributes, original)
    missing = coords.copy()
    missing[1] = [2, 0, 0]
    with pytest.raises(ValueError, match='Missing'):
        bake.vertex_colors(coords, missing, attributes, 8)
    with pytest.raises(ValueError, match='Duplicate'):
        bake.vertex_colors(coords, coords[[0, 0, 2]], attributes, 8)


def test_vertex_photo_preserves_unobserved_colors_geometry_and_bindings():
    import copy
    import numpy as np
    photo = load(TOOLS/'head_models/vertex_photo.py')
    positions = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype='<f4')
    normals = np.tile([0., 0., 1.], (3, 1)).astype('<f4')
    colors = np.full((3, 3), .2, dtype='<f4')
    indices = np.array([0, 1, 2], dtype='<u4')
    payload = b''.join(a.tobytes() for a in [positions, normals, colors, indices])
    doc = dict(scene=0, scenes=[dict(nodes=[0])], nodes=[dict(mesh=0)],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0, NORMAL=1, COLOR_0=2), indices=3)])],
        buffers=[dict(byteLength=len(payload))],
        bufferViews=[dict(buffer=0, byteOffset=i*36, byteLength=36 if i<3 else 12) for i in range(4)],
        accessors=[dict(bufferView=i, componentType=5126 if i<3 else 5125, count=3, type='VEC3' if i<3 else 'SCALAR') for i in range(4)])
    original = copy.deepcopy(doc)
    output, painted, _ = photo.replace_colors(doc, payload, colors, np.array([1., 0., .5]), np.full((3, 3), 255.))
    assert painted == 2 and doc == original
    assert output[:72] == payload[:72] and output[108:] == payload[108:]
    result = np.frombuffer(output, dtype='<f4', offset=72, count=9).reshape(3, 3)
    assert np.array_equal(result[0], [1, 1, 1])
    assert np.array_equal(result[1], colors[1])
    assert np.allclose(result[2], .6)
    assert photo.replace_colors(doc, payload, colors, np.zeros(3), np.full((3, 3), 255.))[0] == payload
    malicious = copy.deepcopy(doc); malicious['bufferViews'][2]['byteOffset'] = 36
    with pytest.raises(ValueError, match='Overlapping'):
        photo.native_arrays(malicious, payload)
    malicious = copy.deepcopy(doc); malicious['nodes'][0]['scale'] = [2, 2, 2]
    with pytest.raises(ValueError, match='identity scene'):
        photo.native_arrays(malicious, payload)
    with pytest.raises(ValueError, match='Invalid photo support'):
        photo.replace_colors(doc, payload, colors, np.array([1., float('nan'), 0.]), np.full((3, 3), 255.))


def test_unlit_material_keeps_geometry_and_existing_material_properties():
    import copy
    module = load(TOOLS/'head_models/materials.py')
    document = dict(asset=dict(version='2.0'), nodes=[dict(mesh=0)],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0, NORMAL=1, COLOR_0=2), indices=3, material=0)])],
        materials=[dict(doubleSided=True, pbrMetallicRoughness=dict(baseColorFactor=[1, 1, 1, 1], roughnessFactor=.85, metallicFactor=0))])
    before = copy.deepcopy(document)
    converted = module.unlit_document(document)
    assert document == before
    assert converted['nodes'] == document['nodes'] and converted['meshes'] == document['meshes']
    assert converted['materials'][0]['pbrMetallicRoughness'] == document['materials'][0]['pbrMetallicRoughness']
    assert converted['materials'][0]['extensions'] == {'KHR_materials_unlit': {}}
    converted['nodes'][0]['mesh'] = 9
    assert document == before
    with pytest.raises(ValueError, match='unextended'):
        module.unlit_document(converted)
