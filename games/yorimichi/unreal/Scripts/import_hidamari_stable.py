"""Import Henry's Hidamari stable (world/regions/hidamari_stable/build.py) into /Game/HidamariStable.

- SM_HS_Stable: the barn, gate, yard and paddock, LOD0 imported in place and LOD1/LOD2 attached as its LODs (no
  Nanite), with simple collision from the placements' axis-aligned boxes (UBelmonteTrainImportLibrary.SetSimpleBoxes)
  used as complex collision, so doorways and the aisle stay open.
- SM_HS_StallDoor and SM_HS_RoomDoor: the sliding leaves, three LODs each, one box of collision. AHidamariStable places
  them at the placements' door pivots.
- SM_HS_Ground, SM_HS_Road and SM_HS_RoadSign: the yard and paddock overlays, the road from the city's street, and
  the lanterns and sign where it starts, all with complex-as-simple collision. The pad and its slopes are Hidamari's
  own terrain (world/regions/hidamari_stable/layout.py grade), so nothing here draws grass.
The stable, its doors and the sign draw with Hidamari's vertex-colour material (/Game/Japan/Materials/M_Arcade). The
ground overlays and the road carry Hidamari's surface slots (HDS_<slug>, placements' `slots`) and take the city's
MI_HD_<slug> (/Game/Japan/Hidamari/Materials, city_material.py in unreal.world), as Hidamari's own yards and lanes do.
Bounds are checked against the build (Blender metres -> Unreal centimetres, y mirrored).

Writes Content/Data/hidamari_stable/stable.json, which AHidamariStable reads: placements.json with the asset root.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
from regions.hidamari_stable import layout as stable_layout
import hashlib
import json
import unreal

BUILD = yori.OUT / 'hidamari-stable'
ROOT = '/Game/HidamariStable'
MATERIAL = '/Game/Japan/Materials/M_Arcade'
CITY = '/Game/Japan/Hidamari/Materials'
DATA = Path(__file__).resolve().parents[1] / 'Content' / 'Data' / 'hidamari_stable'
E = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
REGISTRY = unreal.AssetRegistryHelpers.get_asset_registry()


def pipeline():
    generic = unreal.InterchangeGenericAssetsPipeline()
    mesh = generic.get_editor_property('mesh_pipeline')
    mesh.set_editor_property('import_static_meshes', True)
    mesh.set_editor_property('import_skeletal_meshes', False)
    mesh.set_editor_property('combine_static_meshes_behavior', unreal.InterchangeCombineStaticMeshesBehavior.ALL)
    mesh.set_editor_property('build_nanite', False)
    mesh.set_editor_property('collision', False)                   # set below from the placements
    mesh.set_editor_property('import_collision_according_to_mesh_name', False)
    generic.get_editor_property('animation_pipeline').set_editor_property('import_animations', False)
    stack = unreal.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(unreal.InterchangeGLTFPipeline())
    return stack


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def import_mesh(path, folder, target):
    task = unreal.AssetImportTask()
    for key, value in dict(filename=str(path), destination_path=folder, automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(key, value)
    task.set_editor_property('options', pipeline())
    AT.import_asset_tasks([task])
    meshes = [str(d.package_name) for d in REGISTRY.get_assets_by_path(folder, recursive=True)
              if str(d.asset_class_path.asset_name) == 'StaticMesh']
    assert len(meshes) == 1, (path, meshes)
    assert E.rename_asset(meshes[0], target), (path, 'rename failed', target)
    mesh = E.load_asset(target)
    assert mesh, target
    return mesh


def with_lods(name, files, screen_sizes, meshes):
    mesh = import_mesh(BUILD / files[0], f'{ROOT}/Source/{name}/LOD0', f'{ROOT}/{name}')
    for level, file in enumerate(files[1:], 1):
        source = import_mesh(BUILD / file, f'{ROOT}/Source/{name}/LOD{level}', f'{ROOT}/Source/{name}/{name}_LOD{level}')
        assert meshes.set_lod_from_static_mesh(mesh, level, source, 0, True) == level, (name, level)
    assert mesh.get_num_lods() == len(files), (name, mesh.get_num_lods())
    if len(files) > 1:
        assert meshes.set_lod_screen_sizes(mesh, screen_sizes[:len(files)]), name
    return mesh


def box(values):
    """Blender metres (x0, y0, z0, x1, y1, z1) to an Unreal box in cm (y mirrored)."""
    x0, y0, z0, x1, y1, z1 = values
    return box_cm([x0 * 100, -y1 * 100, z0 * 100], [x1 * 100, -y0 * 100, z1 * 100])


def box_cm(lo, hi):
    lo, hi = unreal.Vector(*lo), unreal.Vector(*hi)
    try:
        return unreal.Box(lo, hi, True)
    except TypeError:
        b = unreal.Box(); b.min = lo; b.max = hi; b.is_valid = True
        return b


def finish(mesh, material, trace, surfaces=None):
    slots = list(mesh.get_editor_property('static_materials'))
    for slot in slots:
        own = material
        if surfaces is not None:                 # Hidamari's surfaces: slot HDS_<slug> takes MI_HD_<slug>
            key = str(slot.get_editor_property('imported_material_slot_name')).split('.')[0].removeprefix('HDS_')
            assert key in surfaces, (mesh.get_name(), 'unexpected surface', key, surfaces)
            own = E.load_asset(f'{CITY}/MI_HD_{key}')
            assert own, f'{CITY}/MI_HD_{key} is missing: build unreal.world first'
        slot.set_editor_property('material_interface', own)
    mesh.set_editor_property('static_materials', slots)
    body = mesh.get_editor_property('body_setup'); assert body, mesh.get_name()
    body.set_editor_property('collision_trace_flag', trace)
    E.save_loaded_asset(mesh)


def bounds_cm(mesh):
    b = mesh.get_bounding_box()
    return [[b.min.x, b.min.y, b.min.z], [b.max.x, b.max.y, b.max.z]]


placements = json.loads((BUILD / 'placements.json').read_text(encoding='utf-8'))
manifest = json.loads((BUILD / 'manifest.json').read_text(encoding='utf-8'))
material = E.load_asset(MATERIAL)
assert material, f'{MATERIAL} is missing: build unreal.world first'
for key, entry in manifest['files'].items():
    assert sha(BUILD / entry['path']) == entry['sha256'], 'stale stable build: ' + key
(DATA / 'stable.json').unlink(missing_ok=True)
assert stable_layout.is_enabled(), 'Hidamari stable is disabled (ENABLED = False in hidamari_stable/layout.py)'
if E.does_directory_exist(ROOT):
    E.delete_directory(ROOT)
E.make_directory(ROOT)
unreal.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
unreal.load_module('StaticMeshEditor')                   # else get_editor_subsystem returns None
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
assert meshes, 'StaticMeshEditorSubsystem is unavailable'
library = unreal.BelmonteTrainImportLibrary
SIMPLE, COMPLEX = unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX, unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
report = {}
for entry in placements['meshes']:
    name = entry['name']
    files = entry.get('lods') or [entry['file']]
    mesh = with_lods(name, files, entry.get('lod_screen_sizes') or placements['meshes'][0]['lod_screen_sizes'], meshes)
    if name == 'SM_HS_Stable':
        boxes = [box(b['box']) for b in placements['collision']]
        assert library.set_simple_boxes(mesh, boxes) == len(boxes), name
        mesh.set_editor_property('lod_for_collision', 0)
        finish(mesh, material, SIMPLE)
    elif entry.get('collision') == 'complex':
        if entry.get('slots'):                   # metre UVs over tens of metres: keep them full precision
            build = meshes.get_lod_build_settings(mesh, 0)
            build.set_editor_property('use_full_precision_u_vs', True); meshes.set_lod_build_settings(mesh, 0, build)
        finish(mesh, material, COMPLEX, entry.get('slots'))
    else:                                        # a door leaf: one box round LOD0
        assert library.set_simple_boxes(mesh, [box_cm(*bounds_cm(mesh))]) == 1, name
        finish(mesh, material, SIMPLE)
    triangles = [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())]
    for level, file in enumerate(files):
        want = manifest['triangles'][Path(file).stem]
        if abs(triangles[level] - want) > max(2, want * .02):
            unreal.log_warning(f'HIDAMARI STABLE {name} LOD{level} has {triangles[level]} triangles, the build says {want}')
    report[name] = dict(lods=len(triangles), triangles=triangles, bounds_cm=bounds_cm(mesh))
    unreal.log(f'HIDAMARI STABLE {name}: triangles={triangles}')

# The stable's LOD0 bounds, Blender metres -> Unreal cm: x kept, y mirrored.
lo, hi = report['SM_HS_Stable']['bounds_cm']
assert lo[0] < placements['barn']['doorways'][0][0] * 100 < hi[0], ('unit/axis conversion', lo, hi)
assert lo[1] < -placements['barn']['centre'][1] * 100 < hi[1], ('unit/axis conversion', lo, hi)
DATA.mkdir(parents=True, exist_ok=True)
(DATA / 'stable.json').write_text(json.dumps(dict(placements, asset_root=ROOT), indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
(BUILD / 'import-report.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
unreal.log(f'HIDAMARI STABLE IMPORT COMPLETE: {len(report)} meshes, {len(placements["collision"])} boxes')
