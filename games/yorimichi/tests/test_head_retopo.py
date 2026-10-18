"""Behavioral checks for automatic UV painting and its guarded public launcher."""
import importlib.util
import copy
import io
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[1]/'tools'


def load(name):
    path = TOOLS/name
    spec = importlib.util.spec_from_file_location('retopo_test_'+path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unpack(data):
    magic, version, length = struct.unpack_from('<III', data)
    assert (magic, version, length) == (0x46546c67, 2, len(data))
    size, kind = struct.unpack_from('<I4s', data, 12)
    assert kind == b'JSON'
    doc = json.loads(data[20:20+size])
    binary_size, kind = struct.unpack_from('<I4s', data, 20+size)
    assert kind == b'BIN\0'
    return doc, data[28+size:28+size+binary_size]


def test_uv_shared_edge_is_not_overlap_but_duplicate_interiors_are():
    m = load('head_models/retopo.py')
    triangles = np.array([[[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 1], [0, 1]]])
    owner, bary = m.raster_uv(triangles, 16)
    assert set(owner[owner >= 0]) == {0, 1}
    np.testing.assert_allclose(bary[owner >= 0].sum(1), 1)
    with pytest.raises(ValueError, match='Overlapping'):
        m.raster_uv(np.repeat(triangles[:1], 2, axis=0), 16)
    with pytest.raises(ValueError, match='Invalid UV'):
        m.raster_uv(triangles.astype(float)*np.nan, 16)


def test_triangle_uv_islands_preserve_geometry_and_unselected_layout():
    m = load('head_models/retopo.py')
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0],
                         [1, 0, 0], [2, 0, 0], [1, 1, 0]], dtype='float32')
    faces = np.array([[0, 1, 2], [3, 4, 5]], dtype='uint32')
    uv = np.array([[[0, 0], [1, 0], [0, 1]],
                   [[0, 0], [1, 0], [0, 1]]], dtype='float32')
    before_vertices, before_faces, before_uv = vertices.copy(), faces.copy(), uv.copy()
    repaired, count = m.triangle_uv_islands(vertices, faces, uv, [False, True])
    assert count == 1
    np.testing.assert_array_equal(vertices, before_vertices)
    np.testing.assert_array_equal(faces, before_faces)
    np.testing.assert_array_equal(uv, before_uv)
    np.testing.assert_array_equal(repaired[0], uv[0])
    edge_a = repaired[1, 1]-repaired[1, 0]
    edge_b = repaired[1, 2]-repaired[1, 0]
    area = np.abs(edge_a[0]*edge_b[1]-edge_a[1]*edge_b[0])/2
    assert area == pytest.approx(0.5)


def test_surface_median_removes_isolated_color_and_keeps_inputs_and_large_features():
    m = load('head_models/retopo.py')
    colors = np.array([[0, 0, .01]]+[[.8, .4, .25]]*7, dtype='float32')
    points = np.zeros((65537, 3), dtype='float32')
    before_colors, before_points = colors.copy(), points.copy()
    class Tree:
        def query(self, positions, k, workers):
            assert len(positions) <= 32768
            if k == 1:
                return np.ones(len(positions)), np.zeros(len(positions), dtype=int)
            return np.ones((len(positions), k)), np.tile(np.arange(k), (len(positions), 1))
    filtered, distance = m.surface_median(Tree(), colors, points, 8)
    np.testing.assert_allclose(filtered, np.broadcast_to(colors[1], filtered.shape))
    nearest, _ = m.surface_median(Tree(), colors, points[:1], 1)
    np.testing.assert_array_equal(nearest[0], colors[0])
    np.testing.assert_array_equal(distance, np.ones(len(points)))
    np.testing.assert_array_equal(colors, before_colors)
    np.testing.assert_array_equal(points, before_points)
    dark = np.tile(colors[0], (8, 1))
    feature, _ = m.surface_median(Tree(), dark, points[:1], 8)
    np.testing.assert_array_equal(feature[0], dark[0])


def test_uv_repaint_glbs_keep_all_geometry_buffers_and_lit_material():
    m = load('head_models/retopo.py')
    vertices = np.array([[0, 0, 0], [1, .1, 0], [0, .2, 1], [1, 1, 1]], dtype='float32')
    faces = np.array([[0, 2, 1], [1, 2, 3]], dtype='uint32')
    uv = np.array([[[0, 0], [0, 1], [1, 0]], [[1, 0], [0, 1], [1, 1]]], dtype='float32')
    before = vertices.copy(), faces.copy(), uv.copy()
    a, binary_a = unpack(m.textured_glb(vertices, faces, uv, np.zeros((4, 4, 3), dtype='uint8')))
    b, binary_b = unpack(m.textured_glb(vertices, faces, uv, np.full((4, 4, 3), 255, dtype='uint8')))
    for i in range(4):
        view = a['bufferViews'][i]
        assert view == b['bufferViews'][i]
        start, size = view['byteOffset'], view['byteLength']
        assert binary_a[start:start+size] == binary_b[start:start+size]
    positions = np.frombuffer(binary_a, dtype='<f4', count=a['accessors'][0]['count']*3).reshape(-1, 3)
    view = a['bufferViews'][3]
    indices = np.frombuffer(binary_a, dtype='<u4', count=faces.size, offset=view['byteOffset'])
    expected = vertices[faces].reshape(-1, 3)[:, [0, 2, 1]].copy()
    expected[:, 2] *= -1
    np.testing.assert_array_equal(positions[indices], expected)
    assert len(positions) < faces.size
    assert 'COLOR_0' not in a['meshes'][0]['primitives'][0]['attributes']
    assert a['materials'] == b['materials']
    assert 'extensionsUsed' not in a and 'normalTexture' not in a['materials'][0]
    for actual, original in zip((vertices, faces, uv), before):
        np.testing.assert_array_equal(actual, original)


def test_palette_masks_are_disjoint_and_do_not_claim_semantic_hair():
    m = load('head_models/retopo.py')
    rgb = np.array([[[.8, .4, .2], [.01, .01, .03], [.8, .8, .8], [.01, .01, .03]]])
    occupied = np.array([[True, True, True, False]])
    skin, dark, other = m.material_regions(rgb, occupied)
    np.testing.assert_array_equal(skin, [[True, False, False, False]])
    np.testing.assert_array_equal(dark, [[False, True, False, False]])
    np.testing.assert_array_equal(skin.astype(int)+dark+other, occupied.astype(int))


def test_embedded_texture_uses_gltf_top_left_origin():
    from PIL import Image
    m = load('head_models/retopo.py')
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1]], dtype='float32')
    f = np.array([[0, 1, 2]], dtype='uint32')
    uv = np.array([[[0, 0], [1, 0], [0, 1]]], dtype='float32')
    pixels = np.array([[[255, 0, 0], [0, 255, 0]], [[0, 0, 255], [255, 255, 0]]], dtype='uint8')
    doc, binary = unpack(m.textured_glb(v, f, uv, pixels))
    view = doc['bufferViews'][doc['images'][0]['bufferView']]
    start, size = view['byteOffset'], view['byteLength']
    embedded = np.array(Image.open(io.BytesIO(binary[start:start+size])))
    np.testing.assert_array_equal(embedded, pixels)


def test_dense_cleanup_only_replaces_color_interval_and_rejects_invalid_values():
    m = load('head_models/retopo.py')
    positions = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype='<f4')
    normals = np.tile([0., 0., 1.], (3, 1)).astype('<f4')
    colors = np.full((3, 3), .2, dtype='<f4')
    indices = np.array([0, 1, 2], dtype='<u4')
    binary = b''.join(a.tobytes() for a in [positions, normals, colors, indices])
    doc = dict(scene=0, scenes=[dict(nodes=[0])], nodes=[dict(mesh=0)],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0, NORMAL=1, COLOR_0=2), indices=3)])],
        materials=[dict(pbrMetallicRoughness=dict(roughnessFactor=.85))],
        buffers=[dict(byteLength=len(binary))],
        bufferViews=[dict(buffer=0, byteOffset=i*36, byteLength=36 if i < 3 else 12) for i in range(4)],
        accessors=[dict(bufferView=i, componentType=5126 if i < 3 else 5125,
                        count=3, type='VEC3' if i < 3 else 'SCALAR') for i in range(4)])
    before = copy.deepcopy(doc)
    replacement = np.full((3, 3), .7, dtype='float32')
    output = m.recolor_native(doc, binary, replacement)
    assert output[:72] == binary[:72] and output[108:] == binary[108:]
    assert output[72:108] == replacement.tobytes()
    assert doc == before
    with pytest.raises(ValueError, match='Invalid replacement'):
        m.recolor_native(doc, binary, replacement*np.nan)
    with pytest.raises(ValueError, match='Invalid replacement'):
        m.recolor_native(doc, binary, replacement*2)


def test_exterior_depth_repair_preserves_source_and_unsupported_openings(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS/'head_models'))
    m = load('head_models/surface.py')
    depth = np.full((3, 3), 2., dtype='float32')
    depth[1, 1] = np.inf
    median = np.full_like(depth, 2)
    coverage = np.ones(depth.shape, dtype=bool)
    output, repaired = m.repair_depth(depth, median, coverage, .0025)
    assert output[1, 1] == 2 and repaired.sum() == 1 and np.isinf(depth[1, 1])
    coverage[1, 1] = False
    output, repaired = m.repair_depth(depth, median, coverage, .0025)
    assert np.isinf(output[1, 1]) and not repaired.any()


def test_depth_normals_face_the_sampling_camera_and_topology_finds_edge_fans(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS/'head_models'))
    m = load('head_models/surface.py')
    yy, xx = np.mgrid[-1:2, -1:2]
    rays = np.zeros((3, 3, 6), dtype='float32')
    rays[..., 3:] = np.stack((xx, yy, np.ones_like(xx)), axis=-1)
    before = rays.copy()
    points, normals, valid = m.oriented_samples(rays, np.ones((3, 3), dtype='float32'))
    assert valid.sum() == 1 and valid[1, 1]
    np.testing.assert_array_equal(points[1, 1], [0, 0, 1])
    np.testing.assert_array_equal(normals[1, 1], [0, 0, -1])
    np.testing.assert_array_equal(rays, before)
    qa = m.topology(np.zeros((5, 3)), np.array([[0, 1, 2], [1, 0, 3], [0, 1, 4]]))
    assert qa['nonmanifold_edges'] == 1 and qa['boundary_edges'] == 6


def test_blender_launcher_is_aggregate_guarded_and_python_errors_fail(monkeypatch, tmp_path):
    from atelier.harness.safety import guarded
    m = load('head_retopo.py')
    monkeypatch.setattr(m, 'REPO', tmp_path)
    calls = []
    monkeypatch.setattr(guarded, 'run', lambda *a, **kw: calls.append((a, kw)) or 19)
    root = tmp_path/'build/yorimichi/retopo'
    result = m.main(['remesh', '--root', str(root), '--source', 'input.npz',
                     '--output', str(root/'quads'), '--report', str(tmp_path/'guard'),
                     '--timeout', '240', '--memory-gib', '8'])
    command = calls[0][0][0]
    assert result == 19
    assert command[command.index('--threads')+1] == '3'
    assert command[command.index('--python-exit-code')+1] == '1'
    assert calls[0][1]['aggregate_tree'] is True
    assert calls[0][1]['limit_gib'] == 8 and calls[0][1]['timeout'] == 240
    with pytest.raises(SystemExit):
        m.main(['setup', '--root', str(tmp_path/'outside'), '--report', str(tmp_path/'g')])
    assert len(calls) == 1


def test_segmentation_projection_matches_pixel_center_rays(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS/'head_models'))
    m = load('head_models/masks.py')
    for yaw, pitch in [(-90, -5), (-30, 55), (150, -40)]:
        view = m.camera(yaw, pitch, 32)
        rays = m.camera_rays(view)
        points = rays[..., :3]+2*rays[..., 3:]
        screen, depth = m.project_points(points.reshape(-1, 3), view)
        yy, xx = np.mgrid[:32, :32]
        np.testing.assert_allclose(screen, np.stack((xx+.5, yy+.5), axis=-1).reshape(-1, 2), atol=1e-5)
        np.testing.assert_allclose(depth, 2, atol=1e-6)


def test_mask_repaint_retains_scene_metadata_and_all_four_streams(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS/'head_models'))
    m, r = load('head_models/masks.py'), load('head_models/retopo.py')
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1]], dtype='float32')
    f = np.array([[0, 1, 2]], dtype='uint32')
    uv = np.array([[[0, 0], [1, 0], [0, 1]]], dtype='float32')
    pixels = np.zeros((4, 4, 3), dtype='uint8')
    original = r.textured_glb(v, f, uv, pixels)
    doc, binary = unpack(original)
    before = copy.deepcopy(doc)
    def join(document, data):
        header = json.dumps(document).encode(); header += b' '*(-len(header) % 4)
        data += b'\0'*(-len(data) % 4)
        return (struct.pack('<III', 0x46546c67, 2, 28+len(header)+len(data))
                + struct.pack('<I4s', len(header), b'JSON')+header
                + struct.pack('<I4s', len(data), b'BIN\0')+data)
    pixels[1, 2] = [255, 30, 70]
    output = m.replace_image(SimpleNamespace(_join_glb=join), doc, binary, pixels)
    changed, after = unpack(output)
    start = doc['bufferViews'][4]['byteOffset']
    assert after[:start] == binary[:start] and doc == before
    assert changed['materials'] == doc['materials'] and changed['nodes'] == doc['nodes']
    assert r.verify_export(original, v, f) == r.verify_export(output, v, f)
    with pytest.raises(ValueError, match='Unexpected data'):
        m.replace_image(SimpleNamespace(_join_glb=join), doc, binary+b'non-image data', pixels)
    malicious = copy.deepcopy(changed)
    malicious['nodes'][0]['scale'] = [2, 2, 2]
    with pytest.raises(ValueError, match='identity-scene'):
        r.verify_export(join(malicious, after), v, f)


def test_mask_inference_launcher_guards_model_and_rejects_escaped_output(monkeypatch, tmp_path):
    from atelier.harness.safety import guarded
    m = load('head_masks.py')
    monkeypatch.setattr(m, 'REPO', tmp_path)
    calls = []
    monkeypatch.setattr(guarded, 'run', lambda *a, **kw: calls.append((a, kw)) or 0)
    root = tmp_path/'build/yorimichi/head'
    args = ['infer', '--root', str(root), '--views', str(root/'views'),
            '--output', str(root/'masks'), '--report', str(tmp_path/'guard')]
    assert m.main(args) == 0
    assert str(root/'sam-venv/bin/python') == calls[0][0][0][0]
    assert calls[0][1]['aggregate_tree'] and calls[0][1]['limit_gib'] == 8
    with pytest.raises(SystemExit):
        m.main(args+['--output', str(tmp_path/'escaped')])
    assert len(calls) == 1
