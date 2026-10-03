"""Import verified community-park FBXs, UV1 surface maps and exact riding collision."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
import hashlib
import json
import runpy
import unreal

OUT = yori.OUT / 'communitypark'
ROOT = '/Game/CommunityPark'
E = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
helper = runpy.run_path(str(Path(__file__).with_name('import_megapark.py')))
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')


def sha(file):
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()


def texture(spec):
    name = 'T_'+spec['slot']; dest = ROOT+'/Textures'
    task = unreal.AssetImportTask(); task.filename = str(OUT / 'textures' / spec['file'])
    task.destination_path = dest; task.destination_name = name
    task.automated = True; task.save = True; task.replace_existing = True
    AT.import_asset_tasks([task]); value = E.load_asset(dest+'/'+name)
    assert value, name
    value.set_editor_property('srgb', True)
    value.set_editor_property('address_x', unreal.TextureAddress.TA_WRAP)
    value.set_editor_property('address_y', unreal.TextureAddress.TA_WRAP)
    E.save_loaded_asset(value)
    return value


def materials():
    result = {}
    for spec in json.loads((OUT / 'textures' / 'materials.json').read_text()):
        assert spec['texcoord'] == 1
        name = 'M_'+spec['slot']; dest = ROOT+'/Materials'
        m = E.load_asset(dest+'/'+name) if E.does_asset_exist(dest+'/'+name) else AT.create_asset(name, dest, unreal.Material, unreal.MaterialFactoryNew())
        MEL.delete_all_material_expressions(m)
        m.set_editor_property('two_sided', spec['double_sided'])
        uv = MEL.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate)
        uv.set_editor_property('coordinate_index', 1)
        sample = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSample)
        sample.set_editor_property('texture', texture(spec))
        sample.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        assert MEL.connect_material_expressions(uv, '', sample, 'UVs')
        assert MEL.connect_material_property(sample, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
        for key, prop in [('roughness', unreal.MaterialProperty.MP_ROUGHNESS), ('metallic', unreal.MaterialProperty.MP_METALLIC)]:
            constant = MEL.create_material_expression(m, unreal.MaterialExpressionConstant)
            constant.set_editor_property('r', spec[key]); MEL.connect_material_property(constant, '', prop)
        MEL.layout_material_expressions(m); MEL.recompile_material(m); E.save_loaded_asset(m)
        result[spec['slot']] = m
    ground = E.load_asset('/Game/Japan/Materials/M_NorthGate')
    assert ground, 'Import the island ground material before the community park'
    result['CP_Ground'] = ground
    return result


build = json.loads((OUT / 'build-report.json').read_text())
park = json.loads((OUT / 'park.json').read_text())
assert sha(OUT / 'park.json') == build['park_sha256'], 'Rebuild changed community park manifest'
assert sha(OUT / 'source' / 'megapark-textured.glb') == build['source_sha256'], 'Changed community park source'
surfaces = materials(); report = {'meshes': {}, 'source_instances': build['source_instances']}
subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
for entry in park['meshes']:
    name = entry['name']; expected = build['meshes'][name]; file = OUT / 'assets' / (name+'.fbx')
    assert sha(file) == expected['sha256'], 'Incomplete export: '+name
    existing = E.load_asset(ROOT+'/'+name)
    if existing:
        existing.set_editor_property('static_materials', [])
    mesh = helper['import_mesh'](file, name, ROOT, OUT/'assets/SM_CP_Seed.fbx')
    assert mesh.get_num_triangles(0) == expected['triangles'], (name, 'changed triangle count')
    slots = list(mesh.get_editor_property('static_materials'))
    assert len(slots) == 1, (name, 'one authored surface required')
    key = str(slots[0].get_editor_property('imported_material_slot_name'))
    assert key == expected['material'] and key in surfaces, (name, key, expected['material'])
    slots[0].set_editor_property('material_interface', surfaces[key]); mesh.set_editor_property('static_materials', slots)
    assert subsystem.get_num_uv_channels(mesh, 0) >= 2, (name, 'UV0 and UV1 required')
    mesh.set_editor_property('allow_cpu_access', True)
    body = mesh.get_editor_property('body_setup'); assert body, name
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    body.set_editor_property('double_sided_geometry', True)
    E.save_loaded_asset(mesh)
    bounds = mesh.get_bounding_box()
    lo = [bounds.min.x, bounds.min.y, bounds.min.z]; hi = [bounds.max.x, bounds.max.y, bounds.max.z]
    want_lo = [expected['min'][0]*100, -expected['max'][1]*100, expected['min'][2]*100]
    want_hi = [expected['max'][0]*100, -expected['min'][1]*100, expected['max'][2]*100]
    assert max(abs(a-b) for a,b in zip(lo+hi, want_lo+want_hi)) < .5, (name, 'unit/axis conversion', lo, hi)
    triangles = OUT / 'import-audit' / (name+'.triangles.f64')
    triangles.parent.mkdir(exist_ok=True)
    assert unreal.MegaParkValidation.dump_mesh_triangles(mesh, unreal.Vector(), str(triangles))
    report['meshes'][name] = {'bounds_min_cm': lo, 'bounds_max_cm': hi, 'material': key,
                            'uv_channels': subsystem.get_num_uv_channels(mesh, 0)}
(OUT / 'import-report.json').write_text(json.dumps(report, indent=2)+'\n')
unreal.log('COMMUNITY PARK IMPORT COMPLETE')
