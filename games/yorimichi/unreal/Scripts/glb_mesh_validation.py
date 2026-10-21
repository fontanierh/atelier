"""Read-only admission checks for the region importers' existing Interchange meshes."""
from pathlib import Path

from atelier.gltf import glb_parts
from atelier.unreal_mesh_reuse import imported_source_matches
import unreal

# Kept equal to every setter in both unchanged import_mesh implementations by CI.
MESH_OPTIONS = dict(import_static_meshes=True, import_skeletal_meshes=False,
                    combine_static_meshes_behavior='ALL', build_nanite=False)
ANIMATION_OPTIONS = dict(import_animations=False)


def source_matches(mesh, source, out):
    """Only the same generated product may move between checkout roots."""
    data = mesh.get_editor_property('asset_import_data')
    if not isinstance(data, unreal.InterchangeAssetImportData):
        return False
    names = list(data.script_extract_filenames())
    if len(names) != 1 or not imported_source_matches(mesh, source):
        return False
    recorded = str(names[0])
    # Inspect unnormalised components, so Path cannot erase traversal or empty parts.
    if not recorded.startswith('/') or any(part in ('', '.', '..') for part in recorded.split('/')[1:]):
        return False
    source = Path(source).resolve()
    out = Path(out).resolve()
    relative = source.relative_to(out)
    tail = (out.name, *relative.parts)
    return Path(recorded).resolve() == source or tuple(Path(recorded).parts[-len(tail):]) == tail


def options_match(mesh):
    data = mesh.get_editor_property('asset_import_data')
    if not isinstance(data, unreal.InterchangeAssetImportData):
        return False
    pipelines = list(data.get_pipelines())
    if (len(pipelines) != 2 or not isinstance(pipelines[0], unreal.InterchangeGenericAssetsPipeline)
            or not isinstance(pipelines[1], unreal.InterchangeGLTFPipeline)):
        return False
    generic = pipelines[0]
    mesh_pipeline = generic.get_editor_property('mesh_pipeline')
    animation = generic.get_editor_property('animation_pipeline')
    for name, expected in MESH_OPTIONS.items():
        if name == 'combine_static_meshes_behavior':
            expected = getattr(unreal.InterchangeCombineStaticMeshesBehavior, expected)
        if mesh_pipeline.get_editor_property(name) != expected:
            return False
    if any(animation.get_editor_property(name) != expected for name, expected in ANIMATION_OPTIONS.items()):
        return False
    # These engine defaults affect geometry too, even though the importers do not set them.
    translation = generic.get_editor_property('import_offset_translation')
    rotation = generic.get_editor_property('import_offset_rotation')
    return (all(value == 0 for value in (translation.x, translation.y, translation.z,
                                       rotation.pitch, rotation.yaw, rotation.roll))
            and generic.get_editor_property('import_offset_uniform_scale') == 1.)


def validate_mesh(mesh, source, entry, slot_count, *, out, tolerance_cm, minimum_triangles=1.):
    """@cc [owner:fontanierh,label:correctness] warm-glb-admission
    Historical adoption MUST prove the recorded source path and hash, saved import options,
    LOD0 triangles, material-slot count and authored bounds. Any unavailable property or
    failed check MUST miss without mutating the asset; current owner finishing still runs.
    """
    try:
        if not mesh or not source_matches(mesh, source, out) or not options_match(mesh):
            return False
        triangles = mesh.get_num_triangles(0)
        if not entry['triangles'] * minimum_triangles <= triangles <= entry['triangles']:
            return False
        if len(mesh.get_editor_property('static_materials')) != slot_count:
            return False
        low, high = entry['bounds_m']
        expected = [low[0]*100, -high[1]*100, low[2]*100, high[0]*100, -low[1]*100, high[2]*100]
        box = mesh.get_bounding_box()
        actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
        return all(abs(a-b) < tolerance_cm for a, b in zip(actual, expected))
    except Exception:
        # Optional compatibility evidence is never a reason to skip ordinary import.
        return False


def collision_entry(source):
    """Read the baked, identity-node hull GLB when its report has only path and hash."""
    doc, _ = glb_parts(Path(source).read_bytes())
    lows, highs, materials, triangles = [], [], set(), 0
    for node in doc['nodes']:
        if any(key in node for key in ('matrix', 'translation', 'rotation', 'scale')):
            raise ValueError('Collision validation requires baked node transforms')
        if 'mesh' not in node:
            continue
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            if primitive.get('mode', 4) != 4:
                raise ValueError('Collision source must contain triangles')
            positions = doc['accessors'][primitive['attributes']['POSITION']]
            indices = doc['accessors'][primitive['indices']]
            if indices['count'] % 3:
                raise ValueError('Incomplete collision triangles')
            triangles += indices['count'] // 3
            lows.append(positions['min'])
            highs.append(positions['max'])
            materials.add(primitive.get('material'))
    if not lows or not triangles:
        raise ValueError('Empty collision source')
    low = [min(v[i] for v in lows) for i in range(3)]
    high = [max(v[i] for v in highs) for i in range(3)]
    # glTF Y-up to authored metres (the same frame as the Belmonte report).
    return dict(triangles=triangles, bounds_m=[[low[0], -high[2], low[1]],
                                             [high[0], -low[2], high[1]]]), len(materials)
