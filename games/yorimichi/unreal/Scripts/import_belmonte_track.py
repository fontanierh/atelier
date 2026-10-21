"""Import the Belmonte railway track into /Game/BelmonteTrack for ABelmonteTrack (Source/Yorimichi/BelmonteTrack.h).

Reads build/yorimichi/belmonte-track/runtime/track.json (tools/belmonte_track_data.py) and the Train Builder's GLBs:

- every mesh as SM_TK_<Name> with its LODs (no Nanite; screen sizes from the runtime data);
- material slots by name: MI_B_* are the Belmonte environment's instances (/Game/Belmonte/Materials, through the
  Belmonte build report's names), MI_TK_* are instances of M_Belmonte with the GLB's colour (the soot-black tunnel
  lining, the signal red, the bank grass), and MI_TK_LampGlow an unlit emissive (M_TK_Glow);
- collision as track.json gives it per piece (chunks LOD2, linings LOD1, viaduct LOD2, banks LOD1) through
  LODForCollision, used as complex-as-simple; buffer stops, stop boards and portals collide on their last LOD.

Then copies the runtime data to Content/Data/belmonte_track/track.json and writes import-report.json beside it.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
import json
import shutil
import unreal

TRACK = yori.OUT / 'belmonte-track'
RUNTIME = TRACK / 'runtime' / 'track.json'
BELMONTE_REPORT = yori.OUT / 'products/belmonte/materials.json'
ROOT = '/Game/BelmonteTrack'
DATA = Path(__file__).resolve().parents[1] / 'Content' / 'Data' / 'belmonte_track'
E = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
REGISTRY = unreal.AssetRegistryHelpers.get_asset_registry()


def pipeline():
    generic = unreal.InterchangeGenericAssetsPipeline()
    mesh = generic.get_editor_property('mesh_pipeline')
    mesh.set_editor_property('import_static_meshes', True)
    mesh.set_editor_property('import_skeletal_meshes', False)
    mesh.set_editor_property('combine_static_meshes_behavior', unreal.InterchangeCombineStaticMeshesBehavior.ALL)
    mesh.set_editor_property('build_nanite', False)
    mesh.set_editor_property('collision', False)
    mesh.set_editor_property('import_collision_according_to_mesh_name', False)
    generic.get_editor_property('animation_pipeline').set_editor_property('import_animations', False)
    stack = unreal.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(unreal.InterchangeGLTFPipeline())
    return stack


def import_mesh(path, folder, target):
    task = unreal.AssetImportTask()
    for key, value in dict(filename=str(path), destination_path=folder, automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(key, value)
    task.set_editor_property('options', pipeline())
    AT.import_asset_tasks([task])
    found = [str(d.package_name) for d in REGISTRY.get_assets_by_path(folder, recursive=True)
             if str(d.asset_class_path.asset_name) == 'StaticMesh']
    assert len(found) == 1, (path, found)
    assert E.rename_asset(found[0], target), (path, 'rename failed', target)
    mesh = E.load_asset(target)
    assert mesh, target
    return mesh


def glb_materials(path):
    """name -> the glTF material record of a GLB (for the MI_TK_* colours)."""
    data = Path(path).read_bytes()
    length = int.from_bytes(data[12:16], 'little')
    return {m.get('name'): m for m in json.loads(data[20:20 + length]).get('materials', [])}


def glow_parent():
    path = f'{ROOT}/Materials/M_TK_Glow'
    material = AT.create_asset('M_TK_Glow', f'{ROOT}/Materials', unreal.Material, unreal.MaterialFactoryNew())
    material.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    colour = MEL.create_material_expression(material, unreal.MaterialExpressionVectorParameter)
    colour.set_editor_property('parameter_name', 'Colour')
    colour.set_editor_property('default_value', unreal.LinearColor(1., .72, .38, 1.))
    strength = MEL.create_material_expression(material, unreal.MaterialExpressionScalarParameter)
    strength.set_editor_property('parameter_name', 'Strength')
    strength.set_editor_property('default_value', 8.)
    product = MEL.create_material_expression(material, unreal.MaterialExpressionMultiply)
    assert MEL.connect_material_expressions(colour, '', product, 'A')
    assert MEL.connect_material_expressions(strength, '', product, 'B')
    assert MEL.connect_material_property(product, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    material.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(material)
    E.save_loaded_asset(material)
    assert E.does_asset_exist(path)
    return material


def track_material(name, record, glow):
    """MI_TK_<name>: M_Belmonte with the GLB's flat colour (white vertex colour -> Colour), or the glow."""
    path = f'{ROOT}/Materials/{name}'
    instance = AT.create_asset(name, f'{ROOT}/Materials', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    pbr = (record or {}).get('pbrMetallicRoughness', {})
    r, g, b = (pbr.get('baseColorFactor') or [.5, .5, .5, 1])[:3]
    if name == 'MI_TK_LampGlow':
        MEL.set_material_instance_parent(instance, glow)
        er, eg, eb = (record or {}).get('emissiveFactor') or [r, g, b]
        strength = ((record or {}).get('extensions', {}).get('KHR_materials_emissive_strength', {}).get('emissiveStrength', 8.))
        MEL.set_material_instance_vector_parameter_value(instance, 'Colour', unreal.LinearColor(er, eg, eb, 1.))
        # The lamps are seen under the tunnels' lowered exposure (runtime data `exposure.bias`): the glow makes up for it.
        MEL.set_material_instance_scalar_parameter_value(instance, 'Strength', float(strength) * 2 ** -min(BIAS, 0.))
    else:
        MEL.set_material_instance_parent(instance, E.load_asset('/Game/Belmonte/Materials/M_Belmonte'))
        MEL.set_material_instance_vector_parameter_value(instance, 'Colour', unreal.LinearColor(r, g, b, 1.))
        # Soot: the lining keeps half its recorded albedo, so the sky's unshadowed fill reads near black between lamps.
        for key, value in (('WhiteVertex', 1.), ('Strength', 0.), ('Terrain', 0.), ('Brightness', .5 if name == 'MI_TK_TunnelLining' else 1.),
                           ('Roughness', float(pbr.get('roughnessFactor', .9)))):
            MEL.set_material_instance_scalar_parameter_value(instance, key, value)
    MEL.update_material_instance(instance)
    E.save_loaded_asset(instance)
    assert E.does_asset_exist(path)
    return instance


BIAS = 0.


def main():
    global BIAS
    data = json.loads(RUNTIME.read_text())
    BIAS = data.get('exposure', {}).get('bias', 0.)
    unreal.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    # The Belmonte report keys its materials by their Haras path (/Game/Haras/Belmonte/Materials/MI_B_x.MI_B_x).
    belmonte = {key.rsplit('/', 1)[-1].split('.')[0]: f"/Game/Belmonte/Materials/{entry['name']}"
                for key, entry in json.loads(BELMONTE_REPORT.read_text())['materials'].items()}
    if E.does_directory_exist(ROOT):
        E.delete_directory(ROOT)
    E.make_directory(ROOT)
    E.make_directory(f'{ROOT}/Materials')
    glow = glow_parent()
    materials = {}
    # Collision LOD per mesh: the pieces' own (chunks, linings, viaduct, banks); the last LOD for solid instances.
    collision = {p['name']: p['collision'] for p in data['pieces']}
    for group in data['instances']:
        if group['collision']:
            name = group['mesh'].rsplit('/', 1)[1].split('.')[0]
            collision[name] = len(data['meshes'][name]['lods']) - 1
    report = {'meshes': {}, 'materials': {}}
    for index, (name, spec) in enumerate(sorted(data['meshes'].items())):
        levels = [TRACK / p for p in spec['lods']]
        mesh = import_mesh(levels[0], f'{ROOT}/Source/{name}/LOD0', f'{ROOT}/{name}')
        for level, path in enumerate(levels[1:], 1):
            source = import_mesh(path, f'{ROOT}/Source/{name}/LOD{level}', f'{ROOT}/Source/{name}/{name}_LOD{level}')
            assert editor.set_lod_from_static_mesh(mesh, level, source, 0, True) == level, (name, level)
        if len(levels) > 1:
            assert editor.set_lod_screen_sizes(mesh, spec['screen_sizes']), name
        records = glb_materials(levels[0])
        slots = list(mesh.get_editor_property('static_materials'))
        for i, slot in enumerate(slots):
            slot_name = str(slot.get_editor_property('material_slot_name'))
            imported = str(slot.get_editor_property('imported_material_slot_name')) or slot_name
            key = next((m for m in spec['materials'] if imported.startswith(m)), imported.split('_LOD')[0])
            if key.startswith('MI_B_'):
                assert key in belmonte, (name, key, 'not a Belmonte material')
                material = E.load_asset(belmonte[key])
            else:
                if key not in materials:
                    materials[key] = track_material(key, records.get(key), glow)
                material = materials[key]
            assert material, (name, key)
            mesh.set_material(i, material)
            report['materials'].setdefault(key, material.get_path_name())
        lod = collision.get(name, -1)
        body = mesh.get_editor_property('body_setup')
        if lod >= 0 and body:
            mesh.set_editor_property('lod_for_collision', min(lod, mesh.get_num_lods() - 1))
            body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            body.set_editor_property('double_sided_geometry', True)
        E.save_loaded_asset(mesh, only_if_is_dirty=False)
        report['meshes'][name] = {'lods': mesh.get_num_lods(), 'triangles': [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())],
                                  'collision_lod': lod}
        unreal.log(f'BELMONTE TRACK IMPORT {index + 1}/{len(data["meshes"])} {name}')
    # The imported glTF materials and LOD sources are no longer referenced: every slot now points at a track or
    # Belmonte material, and the LODs were copied into their meshes.
    E.delete_directory(f'{ROOT}/Source')
    DATA.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RUNTIME, DATA / 'track.json')
    (TRACK / 'runtime' / 'import-report.json').write_text(json.dumps(report, indent=1))
    unreal.log(f'BELMONTE TRACK IMPORT COMPLETE meshes={len(report["meshes"])} materials={len(report["materials"])}')


main()
