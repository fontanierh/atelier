"""Bounded spatial grouping preserves complete input faces and stable cell identities."""
from collections import Counter
import math

import pytest

from atelier.mesh_partition import face_groups


def mesh():
    vertices, faces = [], []
    for y in range(8):
        for x in range(8):
            start = len(vertices)
            vertices.extend(((x, y, 0), (x + .4, y, 1), (x + .4, y + .4, 1), (x, y + .4, 0)))
            faces.append(tuple(range(start, start + 4)))
    return vertices, faces


def test_spatial_groups_are_complete_bounded_and_deterministic():
    vertices, faces = mesh()
    groups = face_groups(vertices, faces, (0, 0, 8, 8), triangle_limit=8)
    assert len(groups) == 16
    assert Counter(index for _, indices in groups for index in indices) == Counter(range(len(faces)))
    assert all(sum(len(faces[index]) - 2 for index in indices) <= 8 for _, indices in groups)
    assert groups == face_groups(vertices, faces, (0, 0, 8, 8), triangle_limit=8)
    assert vertices == mesh()[0] and faces == mesh()[1]


def test_unrelated_occupied_child_changes_do_not_rekey_other_children():
    vertices, faces = mesh()
    original = dict(face_groups(vertices, faces, (0, 0, 8, 8), triangle_limit=8))
    # Duplicate a face only in lower-left child 00; other occupied child names/indices stay exact.
    changed = dict(face_groups(vertices, faces + [faces[0]], (0, 0, 8, 8), triangle_limit=8))
    assert {key: value for key, value in changed.items() if not key.startswith('00')} == {
        key: value for key, value in original.items() if not key.startswith('00')}


def test_two_sides_of_cards_share_the_same_spatial_piece():
    vertices, faces = mesh()
    paired = [face for source in faces for face in (source, tuple(reversed(source)))]
    groups = face_groups(vertices, paired, (0, 0, 8, 8), triangle_limit=16)
    owners = {index: suffix for suffix, indices in groups for index in indices}
    assert all(owners[index] == owners[index + 1] for index in range(0, len(paired), 2))


def test_small_and_empty_meshes_keep_the_unsuffixed_identity():
    vertices, faces = mesh()
    assert face_groups(vertices, faces[:2], (0, 0, 8, 8), triangle_limit=4) == [('', (0, 1))]
    assert face_groups([], [], (0, 0, 8, 8), triangle_limit=4) == []


@pytest.mark.parametrize('vertices,faces,bounds,limit', [
    ([(math.nan, 0, 0)] * 3, [(0, 1, 2)], (0, 0, 1, 1), 1),
    ([(0, 0, 0)] * 3, [(0, 1, 3)], (0, 0, 1, 1), 1),
    ([(0, 0, 0)] * 3, [(0, 1)], (0, 0, 1, 1), 1),
    ([(0, 0, 0)] * 4, [(0, 1, 2, 3)], (0, 0, 1, 1), 1),
    ([(2, 2, 0)] * 3, [(0, 1, 2)], (0, 0, 1, 1), 1),
    ([], [], (0, 0, 0, 1), 1), ([], [], (0, 0, 1, 1), 0),
])
def test_invalid_or_unbounded_geometry_refuses(vertices, faces, bounds, limit):
    with pytest.raises(ValueError):
        face_groups(vertices, faces, bounds, triangle_limit=limit)


def test_coincident_overbudget_geometry_refuses_instead_of_escaping_budget():
    with pytest.raises(ValueError, match='Coincident'):
        face_groups([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)] * 9,
                    (0, 0, 2, 2), triangle_limit=8, max_depth=3)


def test_explicit_assignments_preserve_an_existing_pre_cleanup_cell_choice():
    vertices, faces = mesh()
    # Face cleanup can change its centroid; the existing producer cell uses pre-cleanup centers.
    locations = [(.5, .5), (1.5, 1.5)]
    assert face_groups(vertices, faces[-2:], (0, 0, 2, 2), triangle_limit=2,
                       locations=locations) == [('0', (0,)), ('3', (1,))]
    with pytest.raises(ValueError, match='cover every face'):
        face_groups(vertices, faces[-2:], (0, 0, 2, 2), triangle_limit=2, locations=[])
