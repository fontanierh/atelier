"""Restore the existing MeshIR corner stream without joining pieces or changing its format.

The three helpers are adopted from the #575 mesh_pieces implementation. The native readback
checks remain mandatory; portable decoder tests are not Blender geometry-fidelity proof.
"""
import numpy as np


def values(collection, property_name, width, dtype=np.float32):
    data = np.empty(len(collection) * width, dtype=dtype)
    collection.foreach_get(property_name, data)
    return data.reshape(-1, width) if width > 1 else data


def channel_selection(mesh):
    """Active/render roles are part of UV/color semantics, in addition to their values."""
    def selected(group, index):
        return group[index].name if 0 <= index < len(group) else None
    return dict(uv_active=mesh.uv_layers.active.name if mesh.uv_layers.active else None,
                uv_render=next((layer.name for layer in mesh.uv_layers if layer.active_render), None),
                colour_active=selected(mesh.color_attributes, mesh.color_attributes.active_color_index),
                colour_render=selected(mesh.color_attributes, mesh.color_attributes.render_color_index))


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
    if 'selection' in piece:
        selection = piece['selection']
        uv_names = [layer.name for layer in data.uv_layers]
        colour_names = [layer.name for layer in data.color_attributes]
        if uv_names:
            data.uv_layers.active_index = uv_names.index(selection['uv_active']) if selection['uv_active'] is not None else -1
            if selection['uv_render'] is not None:
                data.uv_layers[selection['uv_render']].active_render = True
        if colour_names:
            data.color_attributes.active_color_index = colour_names.index(selection['colour_active']) if selection['colour_active'] is not None else -1
            data.color_attributes.render_color_index = colour_names.index(selection['colour_render']) if selection['colour_render'] is not None else -1
        if channel_selection(data) != selection:
            raise ValueError('Static mesh active/render UV or colour selection differs')
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
