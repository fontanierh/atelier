"""The shared deterministic FBX exporter for static, skeletal and animation assets.

The installed exporter is part of the action's tool identity. This narrow adapter scopes its
header clock and ID allocator to one export; it does not alter geometry or material slots.
"""
from contextlib import contextmanager
import datetime
import hashlib
import json
from pathlib import Path, PureWindowsPath
import struct


def stable_id(key):
    if isinstance(key, int) and 0 <= key < 2 ** 63:
        return key
    if not isinstance(key, (str, tuple)):
        raise ValueError(f'Unsupported FBX identifier key: {type(key).__name__}')
    encoded = json.dumps(key, ensure_ascii=True, separators=(',', ':')).encode()
    return max(1, int.from_bytes(hashlib.sha256(encoded).digest()[:8], 'little') & (2 ** 63 - 1))


@contextmanager
def stable_export():
    """@cc [owner:fontanierh,label:correctness] deterministic-fbx-metadata
    Production exports MUST use stable metadata and IDs independent of process hash seeds,
    wall time and preceding exports. Exporter state MUST be restored even on failure.
    """
    from io_scene_fbx import export_fbx_bin, fbx_utils

    header, allocate = export_fbx_bin.fbx_header_elements, fbx_utils._key_to_uuid
    media_path = export_fbx_bin._gen_vid_path
    keys, ids = fbx_utils._keys_to_uuids, fbx_utils._uuids_to_keys

    def fixed_header(root, scene_data, time=None):
        result = header(root, scene_data, time=datetime.datetime(1970, 1, 1))
        # Authoring-file location is provenance, not geometry. Remove it
        # without baking an incidental authoring filename/path into the package.
        normalized = 0
        for extension in root.elems:
            if extension.id != b'FBXHeaderExtension':
                continue
            for scene in extension.elems:
                if scene.id != b'SceneInfo':
                    continue
                for properties in scene.elems:
                    if properties.id == b'Properties70':
                        for entry in properties.elems:
                            if (entry.id == b'P' and entry.props
                                    and entry.props[0][4:] == b'Original|ApplicationNativeFile'):
                                value = entry.props[-1]
                                if (entry.props_type[0] != ord('S') or entry.props_type[-1] != ord('S')
                                        or len(value) < 4 or struct.unpack('<I', value[:4])[0] != len(value)-4):
                                    raise ValueError('Unsupported FBX authoring-file metadata layout')
                                entry.props[-1] = struct.pack('<I', 0)
                                normalized += 1
        if normalized != 1:
            raise ValueError('Unsupported FBX authoring-file metadata layout')
        return result

    def relative_media_path(image, scene_data):
        _, relative = media_path(image, scene_data)
        if Path(relative).is_absolute() or PureWindowsPath(relative).is_absolute():
            raise ValueError('FBX media must use relative resource paths')
        # Both FBX fields can use the same source-relative reference. The exporter
        # still owns any requested texture copies/embedding through scene settings.
        return relative, relative

    def fixed_id(used, key):
        value = stable_id(key)
        if value in used:
            raise ValueError('FBX identifier collision; export cannot be certified deterministic')
        return fbx_utils.UUID(value)

    export_fbx_bin.fbx_header_elements = fixed_header
    export_fbx_bin._gen_vid_path = relative_media_path
    fbx_utils._key_to_uuid = fixed_id
    fbx_utils._keys_to_uuids, fbx_utils._uuids_to_keys = {}, {}
    try:
        yield
    finally:
        export_fbx_bin.fbx_header_elements = header
        export_fbx_bin._gen_vid_path = media_path
        fbx_utils._key_to_uuid = allocate
        fbx_utils._keys_to_uuids, fbx_utils._uuids_to_keys = keys, ids


def export_fbx(**options):
    """@cc [owner:fontanierh,label:correctness;performance] deterministic-production-fbx
    Every production FBX export MUST use deterministic clock/IDs and relative resource
    metadata, independent of checkout path, process hash seed and preceding exports.
    Geometry, transforms, materials, UVs, colour, skeleton, collision and animation
    options MUST pass through unchanged. Failure MUST not report a completed export.
    """
    import bpy
    options.setdefault('path_mode', 'RELATIVE')
    if options['path_mode'] == 'ABSOLUTE':
        raise ValueError('Production FBX exports require relative resource paths')
    with stable_export():
        result = bpy.ops.export_scene.fbx(**options)
    if result != {'FINISHED'}:
        raise RuntimeError('FBX export did not finish')
    return result


def validate_atomic_selection(*, triangle_limit=32768):
    """Validate finalized single-mesh geometry before either production mesh exporter."""
    import bpy
    if type(triangle_limit) is not int or not 1 <= triangle_limit <= 32768:
        raise ValueError('Invalid atomic mesh triangle budget')
    selected = list(bpy.context.selected_objects)
    render = [o for o in selected if o.type == 'MESH' and not o.name.startswith('UCX_')]
    if len(render) != 1 or any(o.type != 'MESH' for o in selected):
        raise ValueError('Atomic FBX requires exactly one primary render mesh')
    primary = render[0]
    if getattr(primary, 'modifiers', ()):
        raise ValueError('Atomic mesh geometry must be finalized before export')
    primary.data.calc_loop_triangles()
    if not 0 < len(primary.data.loop_triangles) <= triangle_limit:
        raise ValueError('Atomic FBX render mesh exceeds its triangle budget')
    hulls = [o for o in selected if o is not primary]
    expected = {f'UCX_{primary.name}_{index:02d}' for index in range(len(hulls))}
    if {o.name for o in hulls} != expected or any(getattr(o, 'modifiers', ()) for o in hulls):
        raise ValueError('Atomic FBX contains unrelated collision or unfinished geometry')
    return primary


def world_color(scene):
    """Capture the exact source ambient input consumed by the FBX material serializer."""
    if scene.world is None:return None
    return validate_world_color(list(scene.world.color))


def validate_world_color(value):
    import math
    if (type(value) is not list or len(value)!=3
            or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in value)):
        raise ValueError('Invalid explicit FBX source world colour')
    return value


def export_atomic_fbx(*, triangle_limit=32768, scene_world_color=None, **options):
    """@cc [owner:fontanierh,label:correctness;performance] bounded-single-mesh-export
    An atomic world export MUST select exactly one render mesh, at most 32768 triangles,
    plus only its explicitly numbered authored UCX objects. It MUST NOT export the scene,
    join unrelated logical meshes, silently omit modifiers or bypass the shared deterministic
    exporter. Reject invalid selection or budgets before writing any FBX bytes.
    An explicitly captured source world colour MUST reproduce the FBX material ambient
    input within this export only; undeclared scene state MUST remain unchanged.
    """
    if options.get('use_selection') is not True or options.get('object_types') != {'MESH'}:
        raise ValueError('Atomic FBX must explicitly export selected mesh objects only')
    validate_atomic_selection(triangle_limit=triangle_limit)
    if scene_world_color is None:return export_fbx(**options)
    validate_world_color(scene_world_color)
    import bpy
    scene=bpy.context.scene;previous=scene.world
    world=bpy.data.worlds.new('_AtomicExportWorld')
    try:
        world.color=scene_world_color;scene.world=world
        return export_fbx(**options)
    finally:
        scene.world=previous
        bpy.data.worlds.remove(world)
