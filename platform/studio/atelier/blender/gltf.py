"""Bounded single-mesh GLB export using the same atomic selection policy as FBX."""
from .fbx import validate_atomic_selection


def export_atomic_glb(path, *, triangle_limit=32768, options=None, finite_materials=False):
    """@cc [owner:fontanierh,label:correctness;performance] bounded-single-glb-export
    A GLB export MUST contain one bounded primary and only its owned authored collision.
    All mesh UV and colour channels MUST be requested. Declared supported options MUST
    be applied, and unknown options MUST refuse. Texture images remain separately owned
    products and MUST NOT be silently embedded or changed by the mesh export. An exporter failure MUST prevent
    publication; no whole-scene or region-wide export fallback is permitted. An explicit
    finite-material route MAY use original AUTO traversal only after every used material
    passes the image-free three-node graph validator; default/schema2 stays NONE.
    """
    options = {} if options is None else dict(options)
    if set(options) - {'export_apply', 'export_image_format'}:
        raise ValueError('Unsupported declared atomic GLB export option')
    apply = options.get('export_apply', False)
    image_format = options.get('export_image_format', 'AUTO' if finite_materials else 'NONE')
    if (type(apply) is not bool or type(finite_materials) is not bool
            or image_format != ('AUTO' if finite_materials else 'NONE')):
        raise ValueError('Atomic GLB requires explicit geometry policy and externally owned images')
    import bpy
    validate_atomic_selection(triangle_limit=triangle_limit)
    if finite_materials:
        from atelier.mesh_materials import capture_slots
        for obj in bpy.context.selected_objects:
            if obj.type == 'MESH': capture_slots(obj)
    result = bpy.ops.export_scene.gltf(
        filepath=str(path), export_format='GLB', use_selection=True, export_yup=True,
        export_texcoords=True, export_normals=True, export_materials='EXPORT',
        export_vertex_color='ACTIVE', export_all_vertex_colors=True,
        export_animations=False, export_apply=apply, export_image_format=image_format,
        export_skins=False, export_cameras=False, export_lights=False, export_extras=False)
    if result != {'FINISHED'}:
        raise RuntimeError('Atomic GLB export did not finish')
    return result
