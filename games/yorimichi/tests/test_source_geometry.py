"""Pre-export source data preserves topology without depending on a whole export."""
import importlib
import json
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def geometry(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    return importlib.import_module('source_geometry')


def source(*, large=True):
    counts = np.asarray([4] * (16384 if large else 1) + [3, 3], dtype=np.int32)
    indices = np.concatenate([np.asarray([2, 0, 3, 1] if n == 4 else [3, 0, 2], dtype=np.int32)
                              for n in counts])
    corners = len(indices)
    return dict(positions=np.asarray([[0, -0., 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [7, 8, 9]], dtype='<f4'),
                counts=counts, starts=np.concatenate(([0], np.cumsum(counts)[:-1])),
                vertex_indices=indices, normals=np.tile(np.asarray([0, -0., 1], dtype='<f4'), (corners, 1)),
                materials=np.arange(len(counts), dtype=np.int32) % 2,
                smooth=np.arange(len(counts)) % 2 == 0, slots=('Stone', 'Wood'),
                uvs=[('UVMap', np.arange(corners * 2, dtype='<f4').reshape(-1, 2)),
                     ('Piece1', np.tile(np.asarray([-0., 0.75], dtype='<f4'), (corners, 1)))],
                colours=[('Corner', 'CORNER', 'FLOAT_COLOR', np.tile([0.5, -0., 0.25, 1], (corners, 1)).astype('<f4')),
                         ('Point', 'POINT', 'BYTE_COLOR', np.arange(20, dtype='<f4').reshape(5, 4) / 255)],
                selection=dict(uv_active='Piece1', uv_render='UVMap', colour_active='Point', colour_render='Corner'))


def write(geometry, root, original=None):
    original = source() if original is None else original
    frame = np.eye(4); frame[:3, 3] = [12, -4, 0.5]
    return geometry.write(root, original, owner='HD_Harbor', slots=list(original['slots']), matrix=frame.tolist())


def assert_equal(original, result):
    for field in ('positions', 'normals', 'materials', 'smooth'):
        assert result[field].tobytes() == original[field].tobytes(), field
    assert [i for face in result['faces'] for i in face] == original['vertex_indices'].tolist()
    assert [len(face) for face in result['faces']] == original['counts'].tolist()
    assert result['selection'] == original['selection']
    for before, after in zip(original['uvs'], result['uvs']):
        assert before[0] == after[0] and before[1].tobytes() == after[1].tobytes()
    for before, after in zip(original['colours'], result['colours']):
        assert before[:3] == after[:3] and before[3].tobytes() == after[3].tobytes()


def test_cross_packet_corner_order_shared_vertices_and_unused_vertices_roundtrip(geometry, tmp_path):
    root = tmp_path / 'source'
    original = source()
    value = write(geometry, root, original)
    assert len(value['pieces']) == 2
    assert value['kind'] == 'source_geometry'
    result = geometry.read(root, owner='HD_Harbor')
    assert_equal(original, result)
    assert result['matrix'][0][3] == 12
    assert result['slots'] == ['Stone', 'Wood']
    assert result['triangles'] == 32770
    # This data is not a final render/export plan, even though its packets are bounded.
    from region_mesh_parts import validate
    with pytest.raises(ValueError):
        validate(root)


def test_unchanged_packets_keep_mtime_and_complete_publication_retires_only_old_packets(geometry, tmp_path):
    root = tmp_path / 'source'
    before = write(geometry, root)
    times = {r['payload']: (root / r['payload']).stat().st_mtime_ns for r in before['pieces']}
    write(geometry, root)
    assert times == {p: (root / p).stat().st_mtime_ns for p in times}
    value = write(geometry, root, source(large=False))
    assert len(value['pieces']) == 1
    assert {p.name for p in root.iterdir()} == {'plan.json', value['pieces'][0]['payload']}
    assert_equal(source(large=False), geometry.read(root))


@pytest.mark.parametrize('mutation', ['foreign', 'missing', 'bytes', 'owner', 'indices', 'root_link'])
def test_incomplete_corrupt_foreign_or_linked_sources_refuse(geometry, tmp_path, mutation):
    root = tmp_path / 'source'; value = write(geometry, root, source(large=False))
    packet = root / value['pieces'][0]['payload']
    if mutation == 'foreign': (root / 'unexpected').write_bytes(b'keep')
    if mutation == 'missing': packet.unlink()
    if mutation == 'bytes': packet.write_bytes(packet.read_bytes() + b'changed')
    if mutation == 'owner': value['parent'] = 'HD_Other'
    if mutation == 'indices': value['pieces'][0]['vertices'][0] = -1
    if mutation in ('owner', 'indices'): (root / 'plan.json').write_text(json.dumps(value))
    if mutation == 'root_link':
        linked = tmp_path / 'linked'; linked.symlink_to(root, target_is_directory=True); root = linked
    with pytest.raises(ValueError): geometry.read(root, owner='HD_Harbor')


def test_shared_vertex_bit_changes_are_rejected_even_with_updated_packet_hash(geometry, tmp_path):
    from atelier import mesh_ir
    from atelier.export_manifest import sha
    root = tmp_path / 'source'; value = write(geometry, root)
    packet = root / value['pieces'][1]['payload']
    meta, piece = mesh_ir.decode(packet.read_bytes())
    piece['positions'][0, 1] = 0.0  # original negative zero remains significant
    mesh_ir.write(packet, mesh_ir.encode(piece, key=meta['asset'], slots=meta['slots'],
                                       matrix=meta['matrix'], options={}))
    value['pieces'][1]['sha256'] = sha(packet)
    (root / 'plan.json').write_text(json.dumps(value))
    with pytest.raises(ValueError, match='positions differ'): geometry.read(root)


def test_unowned_or_linked_output_refuses_before_writing(geometry, tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    outside = tmp_path / 'outside'; outside.write_bytes(b'keep')
    (root / 'HD_Harbor_Source0000.npz').symlink_to(outside)
    with pytest.raises(ValueError): write(geometry, root, source(large=False))
    assert outside.read_bytes() == b'keep'
    assert not (root / 'plan.json').exists()


def test_invalid_complete_source_refuses_before_destination_creation(geometry, tmp_path):
    original = source(large=False); original['normals'][0, 0] = np.nan
    root = tmp_path / 'source'
    with pytest.raises(ValueError): write(geometry, root, original)
    assert not root.exists()
