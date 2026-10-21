"""Shared Blender export for local metre-scale model builders.

Model generation is independent from instance placement. Material slots retain
logical names; owning material and runtime steps supply their current bindings.
"""
import math
from .gltf import glb_parts


def mesh_object(builder, materials):
    import bpy
    used = sorted(set(builder.mats))
    index = {name: i for i, name in enumerate(used)}
    mesh = bpy.data.meshes.new(builder.name)
    mesh.from_pydata(builder.verts, [], builder.faces)
    uv_layer = mesh.uv_layers.new(name='UVMap')
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = builder.uvs[loop.vertex_index]
    for name in used:
        mesh.materials.append(materials[name])
    custom = builder.normals is not None
    for poly, mat in zip(mesh.polygons, builder.mats):
        poly.material_index = index[mat]
        poly.use_smooth = custom
    mesh.validate(verbose=False)
    mesh.update()
    if custom:
        normals = list(builder.normals)
        for poly in mesh.polygons:
            for v in poly.vertices:
                if normals[v] is None:
                    normals[v] = tuple(poly.normal)
        mesh.normals_split_custom_set_from_vertices(normals)
    obj = bpy.data.objects.new(builder.name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def export(obj, path):
    """@cc [owner:fontanierh,label:correctness] independent-source-model-export
    Shared model exports MUST preserve local metre-scale geometry, normals, logical material
    slots and established axis conversion. They MUST NOT include placements or runtime scene
    transforms from another owner; every consumed model source MUST be a declared product.
    """
    import bpy
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True, export_apply=True,
                              export_yup=True, export_animations=False, export_skins=False, export_cameras=False,
                              export_lights=False, export_extras=False, export_normals=True,
                              export_image_format='NONE', export_materials='EXPORT')


def glb_info(path):
    """Triangle count, material slot names and bounds (local metres, z up) of an exported GLB."""
    doc, _ = glb_parts(path.read_bytes())
    triangles, low, high = 0, [math.inf] * 3, [-math.inf] * 3
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            triangles += doc['accessors'][primitive['indices']]['count'] // 3
            accessor = doc['accessors'][primitive['attributes']['POSITION']]
            # glTF is y up: (x, z, -y) in Blender's frame.
            (ax, ay, az), (bx, by, bz) = accessor['min'], accessor['max']
            for k, (lo, hi) in enumerate(((ax, bx), (-bz, -az), (ay, by))):
                low[k], high[k] = min(low[k], lo), max(high[k], hi)
    return triangles, [m['name'] for m in doc.get('materials', [])], [low, high]
