"""Piece payloads preserve exact corner values and do not depend on sibling exports."""
import numpy as np
import pytest
from atelier import mesh_ir


def payload():
    piece = dict(positions=[[0, 0, 0], [1, 0, 0], [0, 1, 0]], faces=[[0, 1, 2]],
                 normals=[[0, -0.0, 1]] * 3, materials=[0], smooth=[True],
                 uvs=[('UVMap', [[0, 0], [1, 0], [0, 1]]),
                      ('Piece1', [[17.25, -0.0], [2.5, 3], [4, 5]])],
                 colours=[('Color', 'POINT', 'BYTE_COLOR', [[1, 0, 0, 1]] * 3)])
    return mesh_ir.encode(piece, key='Part', slots=['Material'], matrix=np.eye(4).tolist(), options={})


def test_exact_float32_corner_roundtrip_and_stable_payload():
    data = payload()
    assert data == payload()
    meta, piece = mesh_ir.decode(data)
    assert meta['asset'] == 'Part'
    assert piece['triangles'] == 1
    assert piece['faces'] == [[0, 1, 2]]
    assert piece['normals'].tobytes() == np.asarray([[0, -0.0, 1]] * 3, dtype='<f4').tobytes()
    assert piece['uvs'][1][1].tobytes() == np.asarray([[17.25, -0.0], [2.5, 3], [4, 5]], dtype='<f4').tobytes()
    assert piece['colours'][0][1:3] == ('POINT', 'BYTE_COLOR')


def test_unchanged_payload_does_not_rewrite_file(tmp_path):
    path = tmp_path / 'Part.npz'
    assert mesh_ir.write(path, payload())
    info = path.stat()
    assert not mesh_ir.write(path, payload())
    assert path.stat().st_mtime_ns == info.st_mtime_ns


def test_linked_destination_is_refused_without_changing_external_bytes(tmp_path):
    target = tmp_path / 'outside'; target.write_bytes(b'preserved')
    path = tmp_path / 'Part.npz'; path.symlink_to(target)
    with pytest.raises(ValueError): mesh_ir.write(path, payload())
    assert target.read_bytes() == b'preserved'


def test_unknown_channels_and_pickle_arrays_are_refused():
    import io
    arrays = dict(np.load(io.BytesIO(payload()), allow_pickle=False))
    arrays['unowned'] = np.array([1])
    stream = io.BytesIO(); np.savez_compressed(stream, **arrays)
    with pytest.raises(ValueError, match='undeclared'): mesh_ir.decode(stream.getvalue())
    arrays.pop('unowned'); arrays['positions'] = np.array([object()], dtype=object)
    stream = io.BytesIO(); np.savez_compressed(stream, **arrays)
    with pytest.raises(ValueError): mesh_ir.decode(stream.getvalue())


def remetadata(change):
    import io
    import json
    arrays = dict(np.load(io.BytesIO(payload()), allow_pickle=False))
    meta = json.loads(arrays['metadata'].tobytes())
    change(meta)
    arrays['metadata'] = np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8)
    stream = io.BytesIO(); np.savez_compressed(stream, **arrays)
    return stream.getvalue()


def test_channel_roles_survive_and_unknown_roles_refuse():
    data = remetadata(lambda meta: meta['selection'].update(uv_active='Piece1', uv_render='UVMap'))
    meta, piece = mesh_ir.decode(data)
    assert piece['selection'] == meta['selection']
    assert piece['selection']['uv_active'] == 'Piece1'
    with pytest.raises(ValueError, match='channel selection'):
        mesh_ir.decode(remetadata(lambda meta: meta['selection'].update(colour_render='Missing')))


@pytest.mark.parametrize('matrix', [np.zeros((4, 4)).tolist(),
    [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 1, 1]]])
def test_singular_or_projective_frames_refuse_before_export(matrix):
    with pytest.raises(ValueError, match='transform'):
        mesh_ir.decode(remetadata(lambda meta: meta.update(matrix=matrix)))
