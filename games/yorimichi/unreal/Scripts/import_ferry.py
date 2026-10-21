"""Import the audited ferry and terminals, including the moving brows' own UCX collision."""
import sys
from pathlib import Path
import json

WORLD = Path(__file__).resolve().parents[2] / 'world'
sys.path.insert(0, str(WORLD))
import yori  # noqa: E402
from regions.ferry import service  # noqa: E402

ROOT = yori.OUT / 'ferry'
DATA = json.loads((ROOT / 'service/service.json').read_text())
service.validate_service(DATA)
CUT = yori.OUT / 'hidamari/ferry/cut.json'
if json.loads(CUT.read_text())['failures']:
    raise ValueError('Hidamari ferry access cut failed')

# All data checks precede the first editor mutation.
import unreal  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesh_import import import_mesh  # noqa: E402

E = unreal.EditorAssetLibrary
M = unreal.MaterialEditingLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
unreal.load_module('StaticMeshEditor')
EDITOR = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
if EDITOR is None:
    raise RuntimeError('StaticMeshEditor subsystem is unavailable after loading its module')
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')


def material_parent():
    path = '/Game/Ferry/Materials/M_Ferry'
    mat = E.load_asset(path) if E.does_asset_exist(path) else TOOLS.create_asset(
        'M_Ferry', '/Game/Ferry/Materials', unreal.Material, unreal.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)
    tint = M.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -300, 0)
    tint.set_editor_property('parameter_name', 'Tint')
    M.connect_material_property(tint, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for key, prop, y in (('Roughness', unreal.MaterialProperty.MP_ROUGHNESS, 150),
                         ('Metallic', unreal.MaterialProperty.MP_METALLIC, 300)):
        node = M.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -300, y)
        node.set_editor_property('parameter_name', key)
        M.connect_material_property(node, '', prop)
    M.recompile_material(mat)
    E.save_loaded_asset(mat)
    return mat


def materials(parent, entries):
    result = {}
    for name, (rgb, roughness, metallic) in entries.items():
        path = '/Game/Ferry/Materials/' + name
        mat = E.load_asset(path) if E.does_asset_exist(path) else TOOLS.create_asset(
            name, '/Game/Ferry/Materials', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        M.set_material_instance_parent(mat, parent)
        def linear(value):
            value /= 255.
            return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
        M.set_material_instance_vector_parameter_value(mat, 'Tint', unreal.LinearColor(*(linear(v) for v in rgb), 1.))
        M.set_material_instance_scalar_parameter_value(mat, 'Roughness', roughness)
        M.set_material_instance_scalar_parameter_value(mat, 'Metallic', metallic)
        M.update_material_instance(mat)
        E.save_loaded_asset(mat)
        result[name] = mat
    return result


parent = material_parent()
ship = json.loads((ROOT / 'manifest.json').read_text())
terminals = json.loads((ROOT / 'terminals/manifest.json').read_text())
report = {}
for folder, dest, entries, palette in (
        (ROOT, '/Game/Ferry/Ship', ship['meshes'], ship['materials']),
        (ROOT / 'terminals', '/Game/Ferry/Terminals',
         {name: mesh for terminal in terminals['terminals'].values() for name, mesh in terminal['meshes'].items()},
         terminals['materials'])):
    mats = materials(parent, palette)
    names = list(entries)
    names += ['FY_Collision'] if folder == ROOT else ['FT_HD_Collision', 'FT_BC_Collision']
    for name in names:
        path = folder / 'assets' / f'{name}.fbx'
        mesh = import_mesh(path, dest, name, seed=ROOT / 'assets/FY_ImportSeed.fbx', fresh_slots=True)
        for index, slot in enumerate(mesh.static_materials):
            key = str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
            if key in mats:
                mesh.set_material(index, mats[key])
            elif not name.endswith('_Collision'):
                raise ValueError(f'{name}: undeclared material {key}')
        body = mesh.get_editor_property('body_setup')
        collision = name.endswith(('_Collision', '_Brow'))
        if collision:
            body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
            count = EDITOR.get_convex_collision_count(mesh)
            if count <= 0:
                raise ValueError(f'{name}: missing authored convex collision')
        else:
            count = 0
        E.save_loaded_asset(mesh)
        report[name] = {'triangles': mesh.get_num_triangles(0), 'convex_hulls': count}
        unreal.log(f'FERRY IMPORT {name}: {report[name]}')

(ROOT / 'import-report.json').write_text(json.dumps(report, indent=2) + '\n')
unreal.log('FERRY IMPORT COMPLETE')
