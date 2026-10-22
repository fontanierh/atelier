"""One complete-corner copier for bounded static Blender mesh pieces.

Importing this module does not start Blender. Capture normals on the whole source before subdivision;
piece boundaries must not recalculate smoothing from an incomplete neighbourhood.
"""
import numpy as np


def values(collection, property_name, width, dtype=np.float32):
    data = np.empty(len(collection) * width, dtype=dtype)
    collection.foreach_get(property_name, data)
    return data.reshape(-1, width) if width > 1 else data


def capture(mesh):
    """@cc [owner:fontanierh,label:correctness] complete-static-mesh-corner-capture
    Partitioning MUST capture whole-source corner normals, all UV/colour layers, face materials and
    smoothing before making children. Unsupported exported attributes or colour domains and nonfinite
    values MUST refuse. A child MUST retain the source's complete ordered material table.
    """
    result = dict(positions=values(mesh.vertices, 'co', 3),
                  starts=values(mesh.polygons, 'loop_start', 1, np.int32),
                  counts=values(mesh.polygons, 'loop_total', 1, np.int32),
                  vertex_indices=values(mesh.loops, 'vertex_index', 1, np.int32),
                  normals=values(mesh.corner_normals, 'vector', 3),
                  materials=values(mesh.polygons, 'material_index', 1, np.int32),
                  smooth=values(mesh.polygons, 'use_smooth', 1, np.bool_),
                  slots=tuple(mesh.materials),
                  uvs=[(layer.name, values(layer.data, 'uv', 2)) for layer in mesh.uv_layers],
                  colours=[(layer.name, layer.domain, layer.data_type, values(layer.data, 'color', 4))
                           for layer in mesh.color_attributes])
    known = {'position', 'material_index', 'sharp_face', 'sharp_edge', 'custom_normal'}
    known.update(name for name, _ in result['uvs'])
    known.update(name for name, _, _, _ in result['colours'])
    unsupported = [a.name for a in mesh.attributes
                   if not a.is_internal and not a.name.startswith('.') and a.name not in known]
    if unsupported:
        raise ValueError('Unsupported static mesh attributes: ' + ', '.join(unsupported))
    arrays = [result['positions'], result['normals'], *(v for _, v in result['uvs'])]
    for name, domain, kind, colour in result['colours']:
        if domain not in ('POINT', 'CORNER') or kind not in ('FLOAT_COLOR', 'BYTE_COLOR'):
            raise ValueError('Unsupported static mesh colour layer: ' + name)
        arrays.append(colour)
    if any(not np.isfinite(a).all() for a in arrays):
        raise ValueError('Nonfinite static mesh attributes')
    if len(result['normals']) != len(mesh.loops):
        raise ValueError('Missing whole-source corner normals')
    return result


def subset(source, members):
    """Keep complete faces in source order and map every corner channel through the same loop IDs."""
    members = tuple(members)
    if (not members or members != tuple(sorted(set(members)))
            or any(type(i) is not int or not 0 <= i < len(source['counts']) for i in members)):
        raise ValueError('Invalid or reordered static mesh face membership')
    selected = np.asarray(members, dtype=np.int32)
    counts, starts = source['counts'], source['starts']
    if np.any(counts[selected] < 3):
        raise ValueError('Static mesh piece contains a degenerate face')
    loops = np.concatenate([np.arange(starts[i], starts[i] + counts[i]) for i in selected])
    used, remapped = np.unique(source['vertex_indices'][loops], return_inverse=True)
    lengths = counts[selected]
    return dict(positions=source['positions'][used], normals=source['normals'][loops],
                faces=[a.tolist() for a in np.split(remapped, np.cumsum(lengths)[:-1])],
                materials=source['materials'][selected], smooth=source['smooth'][selected], slots=source['slots'],
                uvs=[(name, uv[loops]) for name, uv in source['uvs']],
                colours=[(name, domain, kind, colour[used if domain == 'POINT' else loops])
                         for name, domain, kind, colour in source['colours']],
                used=used, loops=loops, triangles=int(sum(lengths - 2)))


def create_mesh(name, piece):
    """@cc [owner:fontanierh,label:correctness] exact-static-piece-corner-normals
    Captured float32 normals MUST remain bitwise identical in the child corner stream.
    Use Blender's FLOAT_VECTOR CORNER custom_normal attribute; the convenience setter
    encodes short2 fan-space normals and MUST NOT silently quantize this source boundary.
    """
    import bpy
    data = bpy.data.meshes.new(name)
    data.from_pydata(piece['positions'].tolist(), [], piece['faces'])
    data.update()
    for material in piece['slots']:
        data.materials.append(material)
    data.polygons.foreach_set('material_index', piece['materials'])
    data.polygons.foreach_set('use_smooth', piece['smooth'])
    normals = data.attributes.new(name='custom_normal', type='FLOAT_VECTOR', domain='CORNER')
    if (normals.name != 'custom_normal' or normals.data_type != 'FLOAT_VECTOR'
            or normals.domain != 'CORNER' or len(normals.data) != len(piece['normals'])):
        raise ValueError('Missing exact static mesh corner normal storage')
    normals.data.foreach_set('vector', piece['normals'].ravel())
    for name, uv in piece['uvs']:
        data.uv_layers.new(name=name).data.foreach_set('uv', uv.ravel())
    for name, domain, kind, colour in piece['colours']:
        data.color_attributes.new(name=name, type=kind, domain=domain).data.foreach_set('color', colour.ravel())
    if (not np.array_equal(values(data.vertices, 'co', 3), piece['positions'])
            or values(data.corner_normals, 'vector', 3).tobytes() != piece['normals'].tobytes()
            or not np.array_equal(values(data.polygons, 'material_index', 1, np.int32), piece['materials'])
            or not np.array_equal(values(data.polygons, 'use_smooth', 1, np.bool_), piece['smooth'])):
        raise ValueError('Static mesh piece geometry/material/normal readback differs')
    for name, uv in piece['uvs']:
        if not np.array_equal(values(data.uv_layers[name].data, 'uv', 2), uv):
            raise ValueError('Static mesh piece UV readback differs: ' + name)
    for name, _, _, colour in piece['colours']:
        if not np.allclose(values(data.color_attributes[name].data, 'color', 4), colour, atol=1e-7, rtol=0):
            raise ValueError('Static mesh piece colour readback differs: ' + name)
    return data
