"""Import verified community-park FBXs, UV1 surface maps and exact riding collision."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
import json
import runpy
import unreal

OUT = yori.OUT / 'communitypark'
# communitypark.source.FILE; that module needs numpy, which Unreal's Python lacks.
SOURCE = yori.ASSETS / 'communitypark' / 'megapark-textured.glb'
ROOT = '/Game/CommunityPark'
E = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
helper = runpy.run_path(str(Path(__file__).with_name('import_megapark.py'))); sha = helper['sha']
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
unreal.load_module('StaticMeshEditor')


def surface(key, colour, roughness, metallic, two_sided, uv_index=0):
    name = 'M_'+key; dest = ROOT+'/Materials'
    m = E.load_asset(dest+'/'+name) if E.does_asset_exist(dest+'/'+name) else AT.create_asset(name, dest, unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(m)
    m.set_editor_property('two_sided', two_sided)
    if isinstance(colour, str):
        if uv_index:
            uv = MEL.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate)
            uv.set_editor_property('coordinate_index', uv_index)
        node = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSample)
        node.set_editor_property('texture', helper['texture'](OUT/'textures'/colour, 'T_'+key, dest=ROOT+'/Textures', wrap=True))
        node.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        if uv_index:
            assert MEL.connect_material_expressions(uv, '', node, 'UVs')
        assert MEL.connect_material_property(node, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    else:
        node = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector)
        node.set_editor_property('constant', unreal.LinearColor(*colour, 1.))
        assert MEL.connect_material_property(node, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for value, prop in [(roughness, unreal.MaterialProperty.MP_ROUGHNESS), (metallic, unreal.MaterialProperty.MP_METALLIC)]:
        node = MEL.create_material_expression(m, unreal.MaterialExpressionConstant); node.set_editor_property('r', value)
        assert MEL.connect_material_property(node, '', prop)
    MEL.layout_material_expressions(m); MEL.recompile_material(m); E.save_loaded_asset(m)
    return m


def materials():
    """The source slots (colour maps on UV1) and the authored surfaces, as world/regions/communitypark/build.py lists them."""
    result = {}
    for spec in json.loads((OUT / 'textures' / 'materials.json').read_text()):
        result[spec['slot']] = surface(spec['slot'], spec.get('file') or spec['colour'], spec['roughness'], spec['metallic'],
                                       spec.get('double_sided', False), spec.get('texcoord', 0))
    ground = E.load_asset('/Game/Japan/Materials/M_NorthGate')
    assert ground, 'Import the island ground material before the community park'
    result['CP_Ground'] = ground
    return result


build = json.loads((OUT / 'build-report.json').read_text())
park = json.loads((OUT / 'park.json').read_text())
assert sha(OUT / 'park.json') == build['park_sha256'], 'Rebuild changed community park manifest'
assert sha(SOURCE) == build['source_sha256'], 'Changed community park source'
for name in park['trees']:
    assert E.does_asset_exist('/Game/Japan/Assets/'+name), 'Missing woodland mesh: '+name
surfaces = materials(); report = {'meshes': {}, 'source_instances': build['source_instances']}
subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
for entry in park['meshes']:
    name = entry['name']; expected = build['meshes'][name]; file = OUT / 'assets' / (name+'.fbx')
    assert sha(file) == expected['sha256'], 'Incomplete export: '+name
    existing = E.load_asset(ROOT+'/'+name) if E.does_asset_exist(ROOT+'/'+name) else None
    if existing:
        existing.set_editor_property('static_materials', [])
    mesh = helper['import_mesh'](file, name, ROOT, OUT/'assets/SM_CP_Seed.fbx', vertex_colors=name=='SM_CP_Ground')
    assert mesh.get_num_triangles(0) == expected['triangles'], (name, 'changed triangle count')
    slots = list(mesh.get_editor_property('static_materials'))
    assert len(slots) == 1, (name, 'one authored surface required')
    key = str(slots[0].get_editor_property('imported_material_slot_name'))
    assert key == expected['material'] and key in surfaces, (name, key, expected['material'])
    slots[0].set_editor_property('material_interface', surfaces[key]); mesh.set_editor_property('static_materials', slots)
    assert subsystem.get_num_uv_channels(mesh, 0) >= 2, (name, 'UV0 and UV1 required')
    if name == 'SM_CP_Ground':
        assert subsystem.has_vertex_colors(mesh), 'Ground colour data was lost during FBX import'
    mesh.set_editor_property('allow_cpu_access', True)
    body = mesh.get_editor_property('body_setup'); assert body, name
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
                             if entry['blocks'] else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
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
