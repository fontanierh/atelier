"""Bounded single-mesh GLB export using the same atomic selection policy as FBX."""
from .fbx import validate_atomic_selection


def export_atomic_glb(path, *, triangle_limit=32768):
    """@cc [owner:fontanierh,label:correctness;performance] bounded-single-glb-export
    A GLB export MUST contain one bounded primary and only its owned authored collision.
    All mesh UV and colour channels MUST be requested. An exporter failure MUST prevent
    publication; no whole-scene or region-wide export fallback is permitted.
    """
    import bpy
    validate_atomic_selection(triangle_limit=triangle_limit)
    result = bpy.ops.export_scene.gltf(
        filepath=str(path), export_format='GLB', use_selection=True, export_yup=True,
        export_texcoords=True, export_normals=True, export_materials='EXPORT',
        export_vertex_color='ACTIVE', export_all_vertex_colors=True,
        export_animations=False, export_apply=False)
    if result != {'FINISHED'}:
        raise RuntimeError('Atomic GLB export did not finish')
    return result
