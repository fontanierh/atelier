"""FBX conservation diagnostics expand actual index/reference modes without losing duplicates."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('fbx_corner_diagnostic',
    Path(__file__).with_name('native') / 'fbx_corners.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def node(key, props=(), elements=()):
    return SimpleNamespace(id=key, props=list(props), elems=list(elements))


def attribute(key, field, values, *, mode=b'ByPolygonVertex', indices=None, name=b''):
    members = [node(b'Name', [name]), node(b'MappingInformationType', [mode]),
               node(b'ReferenceInformationType', [b'Direct' if indices is None else b'IndexToDirect']),
               node(field, [values])]
    if indices is not None:
        members.append(node(b'UVIndex', [indices]))
    return node(key, [0], members)


def fixture():
    geometry = node(b'Geometry', [1, b'Mesh\x00\x01Geometry', b'Mesh'], [
        node(b'Vertices', [[0., 0., 0., 1., 0., 0., 0., 1., 0.]]),
        node(b'PolygonVertexIndex', [[0, 1, -3]]),
        attribute(b'LayerElementNormal', b'Normals', [0., 0., 1.] * 3),
        attribute(b'LayerElementUV', b'UV', [.1, .2, .3, .4, .5, .6], indices=[2, 0, 1], name=b'Map'),
        attribute(b'LayerElementColor', b'Colors', [1., 0., 0., 1., 0., 1., 0., 1., 0., 0., 1., 1.],
                  mode=b'ByVertice', name=b'Paint'),
        node(b'LayerElementMaterial', [0], [node(b'MappingInformationType', [b'AllSame']),
                                           node(b'ReferenceInformationType', [b'IndexToDirect']),
                                           node(b'Materials', [[0]])])])
    model = node(b'Model', [2, b'Mesh\x00\x01Model', b'Mesh'])
    material = node(b'Material', [3, b'Stone\x00\x01Material', b''])
    root = node(b'', elements=[node(b'Objects', elements=[geometry, model, material]),
        node(b'Connections', elements=[node(b'C', [b'OO', 1, 2]), node(b'C', [b'OO', 3, 2])])])
    return root, geometry


def test_expands_uv_indices_and_vertex_colors_into_ordered_material_bound_corners():
    root, _ = fixture()
    result = reader.decode(root)
    assert not result['collision'] and sum(result['render'].values()) == 1
    frame, corners = next(iter(result['render']))
    assert frame == () and len(corners) == 3
    assert corners[0][0] == (0., 0., 0.) and corners[0][1] == 'Stone'
    assert corners[0][2] == ((b'LayerElementNormal', 0, '', (0., 0., 1.)),
                             (b'LayerElementUV', 0, 'Map', (.5, .6)),
                             (b'LayerElementColor', 0, 'Paint', (1., 0., 0., 1.)))
    assert corners[1][2][-1][-1] == (0., 1., 0., 1.)


def test_preserves_repeated_polygons_and_winding():
    root, geometry = fixture()
    expected = reader.decode(root)
    reader.child(geometry, b'PolygonVertexIndex').props[0] *= 2
    normal = reader.child(geometry, b'LayerElementNormal')
    reader.child(normal, b'Normals').props[0] *= 2
    uv = reader.child(geometry, b'LayerElementUV')
    reader.child(uv, b'UVIndex').props[0] *= 2
    repeated = reader.decode(root)
    assert repeated['render'] == {key: 2 for key in expected['render']}
    reader.child(geometry, b'PolygonVertexIndex').props[0] = [0, 2, -2] * 2
    assert reader.decode(root) != repeated


def test_missing_vertices_and_unknown_attribute_modes_refuse():
    root, geometry = fixture()
    reader.child(geometry, b'PolygonVertexIndex').props[0] = [0, 99, -3]
    with pytest.raises(ValueError, match='missing vertex'):
        reader.decode(root)
    root, geometry = fixture()
    uv = reader.child(geometry, b'LayerElementUV')
    reader.child(uv, b'MappingInformationType').props[0] = b'Unrecognized'
    with pytest.raises(ValueError, match='mapping'):
        reader.decode(root)


def test_polygon_cycle_comparison_preserves_winding_all_channels_and_duplicates():
    from collections import Counter
    root, _ = fixture()
    original = reader.decode(root)
    frame, corners = next(iter(original['render']))
    repeated = dict(render=Counter({(frame, corners): 3}), collision=Counter())
    rotated = dict(render=Counter({(frame, corners[1:] + corners[:1]): 3}), collision=Counter())
    assert reader.polygon_cycles(repeated) == reader.polygon_cycles(rotated)
    reversed_ = dict(render=Counter({(frame, tuple(reversed(corners))): 3}), collision=Counter())
    assert reader.polygon_cycles(repeated) != reader.polygon_cycles(reversed_)
    rotated['render'][(frame, corners[1:] + corners[:1])] = 2
    assert reader.polygon_cycles(repeated) != reader.polygon_cycles(rotated)
    changed = (corners[0][0], corners[0][1], (*corners[0][2], (b'LayerElementUV', 1, 'Extra', (0., 0.))))
    different = dict(render=Counter({(frame, (changed, *corners[1:])): 3}), collision=Counter())
    assert reader.polygon_cycles(repeated) != reader.polygon_cycles(different)
