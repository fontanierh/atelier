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
import ferry_native  # noqa: E402

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
    if not E.save_loaded_asset(mat, True): raise ValueError('Current ferry parent material save failed')
    return mat


def wake_material():
    """M_FerryWake: translucent unlit Kelvin V-wake, hull foam collar and stern prop-wash ribbon; fades to zero below ~100 cm/s."""
    path = '/Game/Ferry/Materials/M_FerryWake'
    mat = E.load_asset(path) if E.does_asset_exist(path) else TOOLS.create_asset(
        'M_FerryWake', '/Game/Ferry/Materials', unreal.Material, unreal.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property('two_sided', True)
    mat.set_editor_property('compute_fog_per_pixel', True)
    uv = M.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -600, -100)
    time = M.create_material_expression(mat, unreal.MaterialExpressionTime, -600, 50)
    pos = M.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, -600, 200)
    speed = M.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -600, 350)
    speed.set_editor_property('parameter_name', 'SpeedCmPerS')
    speed.set_editor_property('default_value', 0.0)
    fade = M.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -600, 500)
    fade.set_editor_property('parameter_name', 'WakeFade')
    fade.set_editor_property('default_value', 0.0)
    scene_depth = M.create_material_expression(mat, unreal.MaterialExpressionSceneDepth, -600, 620)
    pixel_depth = M.create_material_expression(mat, unreal.MaterialExpressionPixelDepth, -600, 720)
    depth_gap = M.create_material_expression(mat, unreal.MaterialExpressionSubtract, -420, 660)
    M.connect_material_expressions(scene_depth, '', depth_gap, 'A')
    M.connect_material_expressions(pixel_depth, '', depth_gap, 'B')

    def custom_node(code, inputs, out_type, y):
        node = M.create_material_expression(mat, unreal.MaterialExpressionCustom, -200, y)
        node.set_editor_property('code', code)
        node.set_editor_property('output_type', out_type)
        args = []
        for key, _ in inputs:
            arg = unreal.CustomInput()
            arg.set_editor_property('input_name', key)
            args.append(arg)
        node.set_editor_property('inputs', args)
        for key, src in inputs:
            M.connect_material_expressions(src, '', node, key)
        return node

    col_code = '''
float xm = -94.0 + 136.0 * UV.x;
float ym = (UV.y - 0.5) * 32.0;
float2 wp = P.xy * 0.01;
float rip = 0.5 + 0.5 * sin(wp.x * 1.7 + wp.y * 1.3 - T * 2.4) * cos(xm * 0.65 - ym * 0.9 + T * 3.1);
float core = smoothstep(-50.0, -36.0, xm) * exp(-pow(ym / 2.6, 2.0));
return lerp(float3(0.58, 0.82, 0.86), float3(1.18, 1.24, 1.30), saturate(0.45 + 0.35 * rip + 0.35 * core));
'''
    col = custom_node(col_code, [('UV', uv), ('P', pos), ('T', time)], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -60)
    M.connect_material_property(col, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    op_code = '''
float spd_gate = smoothstep(95.0, 240.0, S) * saturate(F);
if (spd_gate <= 0.0001) return 0.0;
float xm = -94.0 + 136.0 * UV.x;
float ym = (UV.y - 0.5) * 32.0;
float ay = abs(ym);
float dx = max(0.0, 36.5 - xm);
float y_arm = 1.2 + 0.34 * dx;
float w_arm = 0.65 + 0.025 * dx;
float v_arm = exp(-pow((ay - y_arm) / w_arm, 2.0)) * smoothstep(37.0, 31.0, xm) * smoothstep(-92.0, -25.0, xm);
float hw = 5.6 * saturate((37.0 - abs(xm)) / 18.0);
float collar = exp(-pow((ay - hw - 0.45) / 0.75, 2.0)) * smoothstep(-40.0, -32.0, xm) * smoothstep(37.5, 32.0, xm);
float aft = max(0.0, -34.0 - xm);
float w_prop = 2.2 + 0.08 * aft;
float prop_wash = exp(-pow(ym / w_prop, 2.0)) * smoothstep(-32.0, -39.0, xm) * smoothstep(-94.0, -48.0, xm);
float turb = 0.65 + 0.35 * sin(xm * 0.55 + T * 4.2 + ay * 0.8) * cos(ym * 1.15 - T * 2.9);
float edge_fade = smoothstep(0.0, 0.06, UV.x) * smoothstep(1.0, 0.94, UV.x) * smoothstep(0.0, 0.06, UV.y) * smoothstep(1.0, 0.94, UV.y);
return saturate((0.75 * v_arm + 0.65 * collar + 0.85 * prop_wash) * turb) * edge_fade * spd_gate * 0.82;
'''
    op_code = op_code.replace('spd_gate * 0.82;', 'spd_gate * saturate(D / 15.0) * 0.82;')
    op = custom_node(op_code, [('UV', uv), ('T', time), ('S', speed), ('F', fade), ('D', depth_gap)], unreal.CustomMaterialOutputType.CMOT_FLOAT1, 180)
    M.connect_material_property(op, '', unreal.MaterialProperty.MP_OPACITY)
    M.recompile_material(mat)
    if not E.save_loaded_asset(mat, True): raise ValueError('Current ferry wake material save failed')
    return mat


def wake_mesh(mat):
    """FY_Wake: single flat wake ribbon mesh in /Game/Ferry/Ship assigned M_FerryWake with collision disabled."""
    dest = '/Game/Ferry/Ship/FY_Wake'
    mesh = E.load_asset(dest) if E.does_asset_exist(dest) else E.duplicate_asset('/Engine/BasicShapes/Plane', dest)
    if mesh is None:
        raise RuntimeError('Failed to create /Game/Ferry/Ship/FY_Wake from /Engine/BasicShapes/Plane')
    if mesh.get_material(0) != mat: mesh.set_material(0, mat)
    body = mesh.get_editor_property('body_setup')
    if body:
        if body.get_editor_property('collision_trace_flag') != unreal.CollisionTraceFlag.CTF_USE_DEFAULT:
            body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_DEFAULT)
    if EDITOR.get_simple_collision_count(mesh) or EDITOR.get_convex_collision_count(mesh):
        if not EDITOR.remove_collisions(mesh): raise ValueError('Current ferry wake collision reset failed')
    if not E.save_loaded_asset(mesh, True): raise ValueError('Current ferry wake mesh save failed')
    return mesh


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
        if not E.save_loaded_asset(mat, True): raise ValueError('Current ferry material instance save failed: ' + name)
        result[name] = mat
    return result


ship = json.loads((ROOT / 'manifest.json').read_text())
terminals = json.loads((ROOT / 'terminals/manifest.json').read_text())
ship_state = ferry_native.configure(ROOT, ship)
terminal_state = ferry_native.configure_terminals(ROOT / 'terminals', terminals)
parent = material_parent()
report = {}
wake_mat = wake_material()
wake = wake_mesh(wake_mat)
report['FY_Wake'] = {'triangles': wake.get_num_triangles(0), 'convex_hulls': 0, 'material': wake_mat.get_path_name()}
unreal.log(f'FERRY IMPORT FY_Wake: {report["FY_Wake"]}')
for folder, dest, entries, palette in (
        (ROOT, '/Game/Ferry/Ship', ship['meshes'], ship['materials']),
        (ROOT / 'terminals', '/Game/Ferry/Terminals',
         {name: mesh for terminal in terminals['terminals'].values() for name, mesh in terminal['meshes'].items()},
         terminals['materials'])):
    mats = materials(parent, palette)
    state = ship_state if folder == ROOT else terminal_state
    names = list(entries)
    names += ['FY_Collision'] if folder == ROOT else ['FT_HD_Collision', 'FT_BC_Collision']
    for name in names:
        path = folder / 'atomic-assets' / f'{name}.fbx'
        options = dict(before_import=lambda name=name, dest=dest: ferry_native.prepare_source(name, dest),
                       reuse_validator=lambda mesh, name=name, state=state, mats=mats: ferry_native.reusable(mesh, name, state, mats))
        mesh = import_mesh(path, dest, name, fresh_slots=True, **options)
        for index, slot in enumerate(mesh.static_materials):
            key = str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
            if key in mats:
                if mesh.get_material(index) != mats[key]:
                    mesh.set_material(index, mats[key])
            elif not name.endswith('_Collision'):
                raise ValueError(f'{name}: undeclared material {key}')
        body = mesh.get_editor_property('body_setup')
        collision = name.endswith(('_Collision', '_Brow'))
        if collision:
            if body.get_editor_property('collision_trace_flag') != unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX:
                body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
            count = EDITOR.get_convex_collision_count(mesh)
            if count <= 0:
                raise ValueError(f'{name}: missing authored convex collision')
        else:
            count = 0
        if not ferry_native.reusable(mesh, name, state, mats):
            raise ValueError('Current ferry native source/material/hull validation failed: ' + name)
        if not E.save_loaded_asset(mesh, True):
            raise ValueError('Current ferry native save failed: ' + name)
        report[name] = {'triangles': mesh.get_num_triangles(0), 'convex_hulls': count}
        unreal.log(f'FERRY IMPORT {name}: {report[name]}')

retired = ferry_native.retire_all((ship_state, terminal_state))
(ROOT / 'import-report.json').write_text(json.dumps(report, indent=2) + '\n')
unreal.log('FERRY IMPORT COMPLETE')
