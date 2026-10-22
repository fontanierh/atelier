"""The static-mesh copier uses one whole-source corner map for every consumed channel."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location('world_mesh_pieces', Path(__file__).parents[1] / 'world/mesh_pieces.py')
PIECES = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(PIECES)


def fixture():
    positions = np.array([[-0., 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [-1, 0, 0]], dtype=np.float32)
    return dict(positions=positions, starts=np.array([0, 3]), counts=np.array([3, 4]),
                vertex_indices=np.array([0, 1, 2, 0, 2, 3, 4]),
                normals=np.arange(21, dtype=np.float32).reshape(7, 3),
                materials=np.array([2, 0]), smooth=np.array([True, False]), slots=('a', 'unused', 'b'),
                uvs=[('UV' + str(i), np.arange(14, dtype=np.float32).reshape(7, 2) + i * 100) for i in range(6)],
                colours=[('Corner', 'CORNER', 'FLOAT_COLOR', np.arange(28, dtype=np.float32).reshape(7, 4)),
                         ('Point', 'POINT', 'BYTE_COLOR', np.arange(20, dtype=np.float32).reshape(5, 4))])


def test_complete_corner_stream_and_material_table_survive_a_piece_boundary():
    source = fixture()
    piece = PIECES.subset(source, (1,))
    assert piece['faces'] == [[0, 1, 2, 3]] and piece['triangles'] == 2
    assert piece['slots'] == ('a', 'unused', 'b')
    assert piece['materials'].tolist() == [0] and piece['smooth'].tolist() == [False]
    assert piece['positions'].tobytes() == source['positions'][[0, 2, 3, 4]].tobytes()
    assert piece['normals'].tobytes() == source['normals'][3:].tobytes()
    for (name, actual), (expected_name, expected) in zip(piece['uvs'], source['uvs']):
        assert name == expected_name and actual.tobytes() == expected[3:].tobytes()
    assert piece['colours'][0][:3] == ('Corner', 'CORNER', 'FLOAT_COLOR')
    assert piece['colours'][0][3].tobytes() == source['colours'][0][3][3:].tobytes()
    assert piece['colours'][1][:3] == ('Point', 'POINT', 'BYTE_COLOR')
    assert piece['colours'][1][3].tobytes() == source['colours'][1][3][[0, 2, 3, 4]].tobytes()


def test_whole_source_and_individual_piece_triangle_ownership_agree():
    source = fixture()
    whole = PIECES.subset(source, (0, 1))
    parts = [PIECES.subset(source, (i,)) for i in range(2)]
    assert whole['triangles'] == sum(p['triangles'] for p in parts) == 3
    assert np.array_equal(np.concatenate([p['normals'] for p in parts]), whole['normals'])
    assert [p['slots'] for p in parts] == [source['slots'], source['slots']]


@pytest.mark.parametrize('members', [(), (1, 0), (0, 0), (-1,), (2,), (False,)])
def test_empty_reordered_duplicate_or_invalid_face_membership_refuses(members):
    with pytest.raises(ValueError, match='membership'):
        PIECES.subset(fixture(), members)
