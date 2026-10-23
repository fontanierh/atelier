"""Read actual FBX polygon corners for source/control conservation diagnostics.

This compares numeric exported positions/normals, named UV/color values, material
names and object transforms with complete winding and multiplicity. It does not
claim whole-file identity or signed-zero equivalence. No FBX code is executed.
"""
from collections import Counter

import numpy as np


def child(node, key, *, optional=False):
    found = [item for item in node.elems if item.id == key]
    if optional and not found:
        return None
    if len(found) != 1:
        raise ValueError('FBX diagnostic requires exactly one ' + key.decode())
    return found[0]


def property_value(node, key):
    item = child(node, key)
    if len(item.props) != 1:
        raise ValueError('Malformed FBX diagnostic property')
    return item.props[0]


def label(value):
    return value.split(b'\x00\x01', 1)[0].decode('utf-8')


def vectors(value, width):
    result = np.asarray(value, dtype=np.float64)
    if result.ndim != 1 or len(result) % width or not np.isfinite(result).all():
        raise ValueError('Malformed or nonfinite FBX vector array')
    return result.reshape(-1, width)


def expanded(layer, field, indices, width, loops, vertices, polygons):
    values = vectors(property_value(layer, field), width)
    reference = property_value(layer, b'ReferenceInformationType')
    if reference == b'IndexToDirect':
        mapping = np.asarray(property_value(layer, indices))
        if mapping.ndim != 1 or mapping.dtype.kind not in 'iu' or np.any(mapping < 0) or np.any(mapping >= len(values)):
            raise ValueError('Malformed FBX attribute indices')
        values = values[mapping]
    elif reference != b'Direct':
        raise ValueError('Unsupported FBX attribute reference mode')
    mode = property_value(layer, b'MappingInformationType')
    selectors = {b'ByPolygonVertex': np.arange(len(loops)), b'ByVertice': loops,
                 b'ByPolygon': polygons, b'AllSame': np.zeros(len(loops), dtype=int)}
    lengths = {b'ByPolygonVertex': len(loops), b'ByVertice': vertices,
               b'ByPolygon': int(polygons.max()) + 1, b'AllSame': 1}
    if mode not in selectors or len(values) != lengths[mode]:
        raise ValueError('Unsupported or incomplete FBX attribute mapping')
    return values[selectors[mode]]


def decode(root):
    objects = child(root, b'Objects').elems
    table = {item.props[0]: item for item in objects}
    if len(table) != len(objects):
        raise ValueError('Duplicate FBX object identity')
    connections = [item.props for item in child(root, b'Connections').elems if item.id == b'C']
    result = dict(render=Counter(), collision=Counter())
    for geometry in (item for item in objects if item.id == b'Geometry'):
        models = [table[row[2]] for row in connections if len(row) == 3 and row[0] == b'OO'
                  and row[1] == geometry.props[0] and row[2] in table and table[row[2]].id == b'Model']
        if len(models) != 1:
            raise ValueError('FBX diagnostic requires an unambiguous model frame')
        model = models[0]
        materials = [label(table[row[1]].props[1]) for row in connections if len(row) == 3
                     and row[0] == b'OO' and row[2] == model.props[0]
                     and row[1] in table and table[row[1]].id == b'Material']
        points = vectors(property_value(geometry, b'Vertices'), 3)
        raw = np.asarray(property_value(geometry, b'PolygonVertexIndex'))
        if raw.ndim != 1 or raw.dtype.kind not in 'iu' or not len(raw) or raw[-1] >= 0:
            raise ValueError('Malformed or incomplete FBX polygons')
        ends = raw < 0
        vertices = np.where(ends, -raw - 1, raw)
        if np.any(vertices < 0) or np.any(vertices >= len(points)):
            raise ValueError('FBX polygon references a missing vertex')
        polygons = np.r_[0, np.cumsum(ends[:-1])]
        layers = []
        for key, field, indices, width in ((b'LayerElementNormal', b'Normals', b'NormalsIndex', 3),
                                          (b'LayerElementUV', b'UV', b'UVIndex', 2),
                                          (b'LayerElementColor', b'Colors', b'ColorIndex', 4)):
            found = sorted((item for item in geometry.elems if item.id == key), key=lambda n: n.props[0])
            if key == b'LayerElementNormal' and len(found) != 1:
                raise ValueError('FBX diagnostic requires current exported corner normals')
            for layer in found:
                name = child(layer, b'Name', optional=True)
                name = name.props[0].decode() if name is not None else ''
                values = expanded(layer, field, indices, width, vertices, len(points), polygons)
                layers.append((key, layer.props[0], name, values))
        material = child(geometry, b'LayerElementMaterial', optional=True)
        if material is None:
            if len(materials) > 1:
                raise ValueError('FBX lacks its material assignment table')
            slots = np.full(len(raw), 0 if materials else -1)
        else:
            if property_value(material, b'ReferenceInformationType') != b'IndexToDirect':
                raise ValueError('Unsupported FBX material reference mode')
            indices = np.asarray(property_value(material, b'Materials'))
            mode = property_value(material, b'MappingInformationType')
            if indices.ndim != 1 or indices.dtype.kind not in 'iu':
                raise ValueError('Malformed FBX material indices')
            if mode == b'AllSame' and len(indices) == 1:
                slots = np.repeat(indices, len(raw))
            elif mode == b'ByPolygon' and len(indices) == int(polygons.max()) + 1:
                slots = indices[polygons]
            else:
                raise ValueError('Unsupported or incomplete FBX material mapping')
        frame = child(model, b'Properties70', optional=True)
        transforms = tuple(sorted((p.props[0], tuple(p.props[4:])) for p in frame.elems
            if p.id == b'P' and p.props[0] in (b'Lcl Translation', b'Lcl Rotation', b'Lcl Scaling',
                b'GeometricTranslation', b'GeometricRotation', b'GeometricScaling'))) if frame else ()
        if any(not np.isfinite(values).all() for _, values in transforms):
            raise ValueError('Nonfinite FBX model transform')
        counter = result['collision' if label(model.props[1]).startswith('UCX_') else 'render']
        corners = []
        for index, vertex in enumerate(vertices):
            slot = int(slots[index])
            if slot < -1 or slot >= len(materials) or (slot == -1 and materials):
                raise ValueError('FBX polygon has no current material binding')
            corners.append((tuple(points[vertex]), materials[slot] if slot >= 0 else None,
                            tuple((kind, number, name, tuple(values[index]))
                                  for kind, number, name, values in layers)))
            if ends[index]:
                if len(corners) < 3:
                    raise ValueError('FBX diagnostic encountered a short polygon')
                counter[(transforms, tuple(corners))] += 1
                corners = []
    if not result['render']:
        raise ValueError('FBX diagnostic requires positive render geometry')
    return result


def read(path):
    from io_scene_fbx import parse_fbx
    root, _ = parse_fbx.parse(str(path))
    return decode(root)
