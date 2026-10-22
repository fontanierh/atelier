from collections import Counter
import copy
import math

import pytest

from atelier.mesh_cells import cell_face_groups


def mesh():
    vertices, faces = [], []
    for y in range(-8, 8):
        for x in range(-8, 8):
            start = len(vertices)
            vertices.extend(((x, y, 0), (x+.4, y, 0), (x+.4, y+.4, 0), (x, y+.4, 0)))
            faces.append(tuple(range(start, start+4)))
    return vertices, faces


def test_complete_membership_preserves_positions_winding_and_corner_selection():
    vertices, faces = mesh()
    before = copy.deepcopy((vertices, faces))
    groups = cell_face_groups(vertices, faces, 8, triangle_limit=8)
    assert Counter(i for _, _, _, indices in groups for i in indices) == Counter(range(len(faces)))
    assert all(sum(len(faces[i])-2 for i in indices) <= 8 for _, _, _, indices in groups)
    assert (vertices, faces) == before
    # The exporter selects corner attributes by the original loop membership.
    corners = [(i, corner) for i, face in enumerate(faces) for corner in range(len(face))]
    selected = [(i, corner) for _, _, _, indices in groups for i in indices for corner in range(len(faces[i]))]
    assert Counter(selected) == Counter(corners)
    assert groups == cell_face_groups(vertices, faces, 8, triangle_limit=8)


def test_small_cells_keep_floor_grid_names_and_original_face_order():
    vertices, faces = mesh()
    groups = cell_face_groups(vertices, faces, 8, triangle_limit=128)
    assert [(x, y, suffix) for x, y, suffix, _ in groups] == [(-1,-1,''), (-1,0,''), (0,-1,''), (0,0,'')]
    assert all(list(indices) == sorted(indices) for _, _, _, indices in groups)


def test_producer_assignment_centers_are_preserved_at_cell_boundaries():
    vertices, faces = mesh()
    groups = cell_face_groups(vertices, faces[:2], 128, triangle_limit=2, locations=[(-.001, 128), (128, -.001)])
    assert groups == [(-1, 1, '', (0,)), (1, -1, '', (1,))]


def test_new_geometry_in_one_grid_cell_does_not_rename_other_cells():
    vertices, faces = mesh()
    before = cell_face_groups(vertices, faces, 8, triangle_limit=8)
    changed = cell_face_groups(vertices, faces+[faces[0]], 8, triangle_limit=8)
    assert [row for row in before if row[:2] != (-1,-1)] == [row for row in changed if row[:2] != (-1,-1)]


@pytest.mark.parametrize('size', [0, -1, math.inf, math.nan, True])
def test_bad_sizes_refuse(size):
    with pytest.raises(ValueError):
        cell_face_groups([], [], size, triangle_limit=2)


@pytest.mark.parametrize('location', [(math.nan, 0), (0,), (0, math.inf)])
def test_bad_producer_centers_refuse(location):
    vertices, faces = mesh()
    with pytest.raises(ValueError):
        cell_face_groups(vertices, faces[:1], 128, triangle_limit=2, locations=[location])


def test_coincident_unresolvable_faces_refuse_instead_of_oversized_piece():
    with pytest.raises(ValueError, match='Coincident'):
        cell_face_groups([(0,0,0), (1,0,0), (0,1,0)], [(0,1,2)]*4, 128, triangle_limit=2)
