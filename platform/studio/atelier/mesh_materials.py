"""Finite vertex-colour material graphs for exact bounded GLB serialization.

This deliberately supports one three-node graph, not arbitrary shaders or images.
Schema-2 mesh packets and FBX exporters do not opt into this descriptor.
"""
import hashlib
import json
import math
import re

import numpy as np

FIELDS = {'kind', 'attribute', 'roughness', 'metallic', 'base_color_default',
          'viewport_color', 'viewport_roughness', 'viewport_metallic', 'viewport_specular',
          'backface_culling', 'default_profile_sha256'}
KIND = 'vertex_color_principled_v1'


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate(spec):
    """Validate only the declared finite graph; unsupported shader state must refuse."""
    if (type(spec) is not dict or set(spec) != FIELDS or spec['kind'] != KIND or spec['attribute'] != 'Color'
            or type(spec['backface_culling']) is not bool
            or not isinstance(spec['default_profile_sha256'], str)
            or not re.fullmatch('[0-9a-f]{64}', spec['default_profile_sha256'])):
        raise ValueError('Unsupported atomic vertex-colour material descriptor')
    def scalar(value):
        return type(value) in (int, float) and math.isfinite(value) and abs(value) <= np.finfo(np.float32).max and float(np.float32(value)) == value
    for key in ('roughness', 'metallic', 'viewport_roughness', 'viewport_metallic', 'viewport_specular'):
        if not scalar(spec[key]) or not 0 <= spec[key] <= 1: raise ValueError('Invalid material scalar: ' + key)
    for key in ('base_color_default', 'viewport_color'):
        if type(spec[key]) is not list or len(spec[key]) != 4 or not all(scalar(value) for value in spec[key]):
            raise ValueError('Invalid complete material colour: ' + key)
    return spec


def _value(value):
    if value is None or type(value) in (str, bool, int): return value
    if isinstance(value, float):
        if not math.isfinite(value): raise ValueError('Nonfinite shader default')
        return value
    try: result = [float(item) for item in value]
    except (TypeError, ValueError) as error: raise ValueError('Unsupported shader socket default') from error
    if not result or not all(math.isfinite(item) for item in result): raise ValueError('Invalid shader vector default')
    return result


def _profile(material, principled, output):
    result = dict(bsdf=[dict(identifier=socket.identifier, type=socket.type,
        value=_value(getattr(socket, 'default_value', None))) for socket in principled.inputs
        if socket.name not in ('Base Color', 'Metallic', 'Roughness')],
        output=[dict(identifier=socket.identifier, type=socket.type,
            value=_value(getattr(socket, 'default_value', None))) for socket in output.inputs],
        bsdf_properties={key: _value(getattr(principled, key)) for key in ('distribution', 'subsurface_method')
                         if hasattr(principled, key)},
        material_properties={key: _value(getattr(material, key)) for key in (
            'surface_render_method', 'use_transparency_overlap', 'use_backface_culling_shadow',
            'use_transparent_shadow', 'displacement_method', 'max_vertex_displacement',
            'thickness_mode', 'refraction_depth') if hasattr(material, key)},
        output_target=output.target)
    return result


def _default_profile():
    import bpy
    temporary = bpy.data.materials.new('_AtomicMaterialDefaults')
    try:
        temporary.use_nodes = True
        return _profile(temporary, temporary.node_tree.nodes.get('Principled BSDF'), temporary.node_tree.nodes.get('Material Output'))
    finally: bpy.data.materials.remove(temporary)


def capture(material):
    """@cc [owner:fontanierh,label:correctness] finite-vertex-colour-source-material
    Opt-in material fidelity MUST retain the actual VertexColor(Color)->Principled->Surface
    graph, float32 metallic/roughness/base/viewport values and backface policy. Every other
    shader input/property MUST equal the actual fresh tool defaults and be SHA-bound.
    Images, arbitrary nodes/links, animation and unsupported changed defaults MUST refuse;
    never replace them with a visually similar shader or export a bare default material.
    """
    if (material is None or material.library is not None or not material.use_nodes
            or material.animation_data is not None or material.node_tree.animation_data is not None):
        raise ValueError('Atomic material requires one static local node graph')
    nodes = list(material.node_tree.nodes)
    by_type = {node.bl_idname: node for node in nodes}
    if (len(nodes) != 3 or set(by_type) != {'ShaderNodeVertexColor', 'ShaderNodeBsdfPrincipled', 'ShaderNodeOutputMaterial'}
            or any(node.mute for node in nodes)):
        raise ValueError('Unsupported atomic material graph nodes')
    colour, principled, output = (by_type[key] for key in ('ShaderNodeVertexColor', 'ShaderNodeBsdfPrincipled', 'ShaderNodeOutputMaterial'))
    links = [(link.from_node.bl_idname, link.from_socket.name, link.to_node.bl_idname, link.to_socket.name)
             for link in material.node_tree.links]
    expected = [('ShaderNodeVertexColor', 'Color', 'ShaderNodeBsdfPrincipled', 'Base Color'),
                ('ShaderNodeBsdfPrincipled', 'BSDF', 'ShaderNodeOutputMaterial', 'Surface')]
    if sorted(links) != sorted(expected) or colour.layer_name != 'Color' or not output.is_active_output:
        raise ValueError('Unsupported atomic material graph links or colour layer')
    profile = _profile(material, principled, output)
    defaults = _default_profile()
    if _canonical(profile) != _canonical(defaults): raise ValueError('Unsupported nondefault vertex-colour shader state')
    signature = hashlib.sha256(_canonical(profile).encode()).hexdigest()
    return validate(dict(kind=KIND, attribute='Color', roughness=float(principled.inputs['Roughness'].default_value),
        metallic=float(principled.inputs['Metallic'].default_value),
        base_color_default=list(principled.inputs['Base Color'].default_value),
        viewport_color=list(material.diffuse_color), viewport_roughness=float(material.roughness),
        viewport_metallic=float(material.metallic), viewport_specular=float(material.specular_intensity),
        backface_culling=bool(material.use_backface_culling), default_profile_sha256=signature))


def capture_slots(obj):
    """Unused source slots contribute no descriptor or shader dependency to a leaf."""
    used = {face.material_index for face in obj.data.polygons}
    return [capture(material) if index in used else None for index, material in enumerate(obj.data.materials)]


def restore(label, spec):
    import bpy
    validate(spec)
    existing = bpy.data.materials.get(label)
    if existing is not None:
        if _canonical(capture(existing)) != _canonical(spec): raise ValueError('Existing material differs from its declared source graph')
        return existing
    material = bpy.data.materials.new(label)
    try:
        material.use_nodes = True
        material.diffuse_color = spec['viewport_color']; material.roughness = spec['viewport_roughness']
        material.metallic = spec['viewport_metallic']; material.specular_intensity = spec['viewport_specular']
        material.use_backface_culling = spec['backface_culling']
        principled = material.node_tree.nodes.get('Principled BSDF')
        principled.inputs['Base Color'].default_value = spec['base_color_default']
        principled.inputs['Roughness'].default_value = spec['roughness']
        principled.inputs['Metallic'].default_value = spec['metallic']
        colour = material.node_tree.nodes.new('ShaderNodeVertexColor'); colour.layer_name = 'Color'
        material.node_tree.links.new(colour.outputs['Color'], principled.inputs['Base Color'])
        if _canonical(capture(material)) != _canonical(spec): raise ValueError('Reconstructed material differs from exact source defaults or values')
        return material
    except BaseException:
        bpy.data.materials.remove(material)
        raise
