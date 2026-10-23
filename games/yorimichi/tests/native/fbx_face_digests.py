"""Bounded-memory complete numeric FBX polygon evidence for large real source controls."""
from collections import Counter
import hashlib
import struct

import numpy as np

from fbx_corners import child, expanded, label, property_value, vectors


def read(path):
    """Hash complete ordered numeric corners, channel names, material and authored frame.

    Digests are evidence of numeric polygon equality, not binary FBX-file identity.
    They avoid retaining millions of nested Python tuples during a real terrain proof.
    """
    from io_scene_fbx import parse_fbx
    root, _ = parse_fbx.parse(str(path))
    objects = child(root, b'Objects').elems
    table = {item.props[0]: item for item in objects}
    if len(table) != len(objects): raise ValueError('Duplicate FBX object')
    connections = [item.props for item in child(root, b'Connections').elems if item.id == b'C']
    result = dict(render=Counter(), collision=Counter())
    for geometry in (item for item in objects if item.id == b'Geometry'):
        models = [table[row[2]] for row in connections if len(row) == 3 and row[0] == b'OO'
                  and row[1] == geometry.props[0] and row[2] in table and table[row[2]].id == b'Model']
        if len(models) != 1: raise ValueError('Ambiguous FBX geometry frame')
        model = models[0]
        materials = [label(table[row[1]].props[1]) for row in connections if len(row) == 3
                     and row[0] == b'OO' and row[2] == model.props[0]
                     and row[1] in table and table[row[1]].id == b'Material']
        points = vectors(property_value(geometry, b'Vertices'), 3)
        raw = np.asarray(property_value(geometry, b'PolygonVertexIndex'))
        if raw.ndim != 1 or raw.dtype.kind not in 'iu' or not len(raw) or raw[-1] >= 0:
            raise ValueError('Malformed FBX polygon inventory')
        ends = np.flatnonzero(raw < 0) + 1
        starts = np.r_[0, ends[:-1]]
        indices = np.where(raw < 0, -raw - 1, raw)
        if np.any(indices < 0) or np.any(indices >= len(points)) or np.any(ends - starts < 3):
            raise ValueError('Invalid FBX polygon indices')
        polygons = np.repeat(np.arange(len(ends)), ends - starts)
        layers, names = [points[indices]], []
        for key, field, direct, width in ((b'LayerElementNormal', b'Normals', b'NormalsIndex', 3),
                                          (b'LayerElementUV', b'UV', b'UVIndex', 2),
                                          (b'LayerElementColor', b'Colors', b'ColorIndex', 4)):
            found = sorted((item for item in geometry.elems if item.id == key), key=lambda n: n.props[0])
            if key == b'LayerElementNormal' and len(found) != 1: raise ValueError('Missing FBX corner normals')
            for layer in found:
                name = child(layer, b'Name', optional=True)
                names.append((key, layer.props[0], name.props[0] if name else b'', width))
                layers.append(expanded(layer, field, direct, width, indices, len(points), polygons))
        # A row contains EVERY exported corner channel, never a representative sample.
        values = np.ascontiguousarray(np.concatenate(layers, axis=1), dtype='<f8')
        values[values == 0] = 0.  # Numeric equality treats signed zero identically.
        if not np.isfinite(values).all(): raise ValueError('Nonfinite exported corners')
        material = child(geometry, b'LayerElementMaterial', optional=True)
        if material is None:
            if len(materials) > 1: raise ValueError('Missing material assignment')
            slots = np.full(len(ends), 0 if materials else -1)
        else:
            if property_value(material, b'ReferenceInformationType') != b'IndexToDirect':
                raise ValueError('Unsupported FBX material reference')
            slots = np.asarray(property_value(material, b'Materials'))
            mode = property_value(material, b'MappingInformationType')
            if mode == b'AllSame' and len(slots) == 1: slots = np.repeat(slots, len(ends))
            elif mode != b'ByPolygon' or len(slots) != len(ends): raise ValueError('Malformed material mapping')
        frame = child(model, b'Properties70', optional=True)
        transforms = tuple(sorted((p.props[0], tuple(p.props[4:])) for p in frame.elems
            if p.id == b'P' and p.props[0] in (b'Lcl Translation', b'Lcl Rotation', b'Lcl Scaling',
                b'GeometricTranslation', b'GeometricRotation', b'GeometricScaling'))) if frame else ()
        common = repr((transforms, names)).encode()
        counter = result['collision' if label(model.props[1]).startswith('UCX_') else 'render']
        width = values.shape[1] * values.dtype.itemsize
        buffer = memoryview(values).cast('B')
        for index, (start, end) in enumerate(zip(starts, ends)):
            slot = int(slots[index])
            if slot < -1 or slot >= len(materials) or (slot == -1 and materials):
                raise ValueError('Invalid material binding')
            digest = hashlib.sha256(common)
            digest.update(repr(materials[slot] if slot >= 0 else None).encode())
            digest.update(struct.pack('<I', end-start))
            digest.update(buffer[start*width:end*width])
            counter[digest.digest()] += 1
    if not result['render']: raise ValueError('No FBX render geometry')
    return result
