"""Targeted skate pier + trick skateboard import (docs/SKATE.md, games/yorimichi/world/regions/skatepark/README.md).

Imports build/yorimichi/skatepark/assets/*.fbx into /Game/SkatePark and the three board parts into
/Game/SkatePark/Board. Park materials use the generated Sunset Pier surface maps;
the board retains the existing vertex-colour material M_Village (loaded, never rebuilt).
Park meshes that block use complex collision as simple (the render mesh is the riding surface);
the floor paint and the board get no collision. No other asset is touched. Writes
build/yorimichi/skatepark/import-report.json.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib
import json
import runpy
from pathlib import Path
import unreal
from atelier import mesh_geometry, native_membership
from skatepark import pieces

HERE = Path(__file__).resolve().parent
JAPAN = yori.OUT
OUT = JAPAN / 'skatepark'
helper = runpy.run_path(str(HERE / 'import_village.py'))     # import_mesh only; its main() does not run
# Targeted park imports have their own small, clean seed; they do not require village build intermediates.
helper['import_mesh'].__globals__['PLACEHOLDER'] = OUT / 'board/SM_SkateWheel.fbx'
E = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


build = json.loads((OUT / 'build-report.json').read_text())
PARK = yori.REGIONS / 'skatepark' / 'park.json'   # the committed gameplay contract
logical = json.loads(PARK.read_text())
assert sha(PARK) == build['identity']['park_json_sha256'], 'park.json changed after the build; rebuild'
park = json.loads((OUT / 'runtime-park.json').read_text())
assert park == pieces.runtime_park(logical, build['pieces']['members']), 'Invalid generated pier runtime membership'
assert sha(OUT / 'runtime-park.json') == build['identity']['runtime_park_sha256'], 'Changed pier runtime roster'
expected_exports = {'assets/' + row['name'] + '.fbx' for row in park['meshes']}
expected_exports.update('board/' + name + '.fbx' for name in ('SM_SkateDeck', 'SM_SkateTruck', 'SM_SkateWheel'))
assert set(build['identity']['exports']) == expected_exports, 'Incomplete or foreign pier source exports'
for rel, digest in build['identity']['exports'].items():
    assert sha(OUT / rel) == digest, 'Stale or incomplete skate pier export: ' + rel

material = E.load_asset('/Game/Japan/Materials/M_Village')
assert material, 'M_Village is missing: import the village first'
E.make_directory('/Game/SkatePark'); E.make_directory('/Game/SkatePark/Board')
previous = {path for path in native_membership.inventory(E, '/Game/SkatePark', 'SM_')
            if pieces.owned_name(path.rsplit('/', 1)[-1])}


def box_cm(mesh):
    b = mesh.get_bounding_box()
    return [round(b.min.x, 2), round(b.min.y, 2), round(b.min.z, 2)], [round(b.max.x, 2), round(b.max.y, 2), round(b.max.z, 2)]


def check_axes(name, mesh, expect):
    """Blender metres (x, y, z) arrive as Unreal centimetres (x, -y, z)."""
    lo, hi = box_cm(mesh)
    want_lo = [expect['min'][0] * 100, -expect['max'][1] * 100, expect['min'][2] * 100]
    want_hi = [expect['max'][0] * 100, -expect['min'][1] * 100, expect['max'][2] * 100]
    err = max(abs(a - b) for a, b in zip(lo + hi, want_lo + want_hi))
    assert err < 0.5, (name, 'unit/axis conversion', lo, hi, want_lo, want_hi)
    return lo, hi


report = {'park': {}, 'board': {}}
owned_textures = set()


def texture(file, name, role):
    dest = '/Game/SkatePark/Textures'; asset = dest + '/' + name
    owned_textures.add(asset)
    path = OUT / 'textures' / file; digest = sha(path)
    tex = E.load_asset(asset) if E.does_asset_exist(asset) else None
    if tex is None or E.get_metadata_tag(tex, 'AtelierSourceSha256') != digest:
        task = unreal.AssetImportTask(); task.filename = str(path); task.destination_path = dest
        task.destination_name = name; task.automated = True; task.save = True; task.replace_existing = True
        AT.import_asset_tasks([task]); tex = E.load_asset(asset); assert tex, file
        E.set_metadata_tag(tex, 'AtelierSourceSha256', digest)
    tex.set_editor_property('srgb', role == 'albedo')
    tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP if role == 'normal'
                            else unreal.TextureCompressionSettings.TC_DEFAULT)
    assert E.save_loaded_asset(tex), (name, 'texture save failed')
    return tex


def materials():
    specs = json.loads((OUT / 'textures/textures.json').read_text())
    specs['painted'] = {**specs['steel'], 'metallic': 0.}
    result = {}
    for key, entry in specs.items():
        dest = '/Game/SkatePark/Materials'; name = 'M_Pier_' + key
        m = E.load_asset(dest + '/' + name) if E.does_asset_exist(dest + '/' + name) else AT.create_asset(name, dest, unreal.Material, unreal.MaterialFactoryNew())
        MEL.delete_all_material_expressions(m)
        def node(cls, **values):
            n = MEL.create_material_expression(m, cls)
            for k, v in values.items(): n.set_editor_property(k, v)
            return n
        def link(a, output, b, input):
            assert MEL.connect_material_expressions(a, output, b, input), (key, output, input)
        samples = {}
        for role, file in entry['maps'].items():
            tex = texture(file, 'T_Pier_' + key + '_' + role, role)
            sampler = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if role == 'normal' else (
                unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR if role == 'roughness' else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
            samples[role] = node(unreal.MaterialExpressionTextureSample, texture=tex, sampler_type=sampler)
        if key == 'mural':
            colour = samples['albedo']; colour_output = 'RGB'
        else:
            vc = node(unreal.MaterialExpressionVertexColor)
            colour = node(unreal.MaterialExpressionCustom,
                          code='float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); return L*D*2;',
                          output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
            args = []
            for k in ('C', 'D'):
                arg = unreal.CustomInput(); arg.set_editor_property('input_name', k); args.append(arg)
            colour.set_editor_property('inputs', args)
            link(vc, '', colour, 'C'); link(samples['albedo'], 'RGB', colour, 'D'); colour_output = ''
        assert MEL.connect_material_property(colour, colour_output, unreal.MaterialProperty.MP_BASE_COLOR)
        if 'normal' in samples: MEL.connect_material_property(samples['normal'], 'RGB', unreal.MaterialProperty.MP_NORMAL)
        if 'roughness' in samples: MEL.connect_material_property(samples['roughness'], 'R', unreal.MaterialProperty.MP_ROUGHNESS)
        metal = node(unreal.MaterialExpressionConstant, r=entry['metallic'])
        MEL.connect_material_property(metal, '', unreal.MaterialProperty.MP_METALLIC)
        fill = node(unreal.MaterialExpressionMultiply, const_b=.035)
        link(colour, colour_output, fill, 'A'); MEL.connect_material_property(fill, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        MEL.layout_material_expressions(m); MEL.recompile_material(m)
        assert E.save_loaded_asset(m), (name, 'material save failed')
        result['Pier_' + key] = m
    return result


surfaces = materials()
for entry in park['meshes']:
    name = entry['name']
    # The common helper seeds/reset slots only on an actual native import miss. Clearing slots
    # here would destroy the current package before its geometry-reuse validator can read it.
    mesh = helper['import_mesh'](OUT / 'assets' / f'{name}.fbx', '/Game/SkatePark', name, fresh_slots=True)
    slots = list(mesh.get_editor_property('static_materials')); found = set()
    for slot in slots:
        key = str(slot.get_editor_property('imported_material_slot_name'))
        assert key in surfaces, (name, 'unknown surface', key)
        found.add(key)
    if any(slot.get_editor_property('material_interface') != surfaces[str(slot.get_editor_property('imported_material_slot_name'))]
           for slot in slots):
        for slot in slots:
            slot.set_editor_property('material_interface', surfaces[str(slot.get_editor_property('imported_material_slot_name'))])
        mesh.set_editor_property('static_materials', slots)
    assert found == set(build['material_slots'][name]), (name, found, build['material_slots'][name])
    if not mesh.get_editor_property('allow_cpu_access'):
        mesh.set_editor_property('allow_cpu_access', True)  # Cooked riding snapshots need positions.
    if mesh.get_editor_property('complex_collision_mesh') is not None:
        mesh.set_editor_property('complex_collision_mesh', None)
    if mesh.get_editor_property('lod_for_collision') != 0:
        mesh.set_editor_property('lod_for_collision', 0)
    body = mesh.get_editor_property('body_setup'); assert body, name
    flag = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if entry['blocks'] else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX
    if body.get_editor_property('collision_trace_flag') != flag:
        body.set_editor_property('collision_trace_flag', flag)
    assert E.save_loaded_asset(mesh), (name, 'save failed')
    assert mesh.get_num_triangles(0) == build['meshes'][name]['triangles'], (name, 'native triangle mismatch')
    assert mesh.get_num_triangles(0) <= pieces.TRIANGLE_LIMIT, (name, 'native piece exceeds budget')
    assert mesh.get_editor_property('allow_cpu_access') is True
    assert mesh.get_editor_property('complex_collision_mesh') is None
    assert mesh.get_editor_property('lod_for_collision') == 0
    assert body.get_editor_property('collision_trace_flag') == flag
    lo, hi = check_axes(name, mesh, build['meshes'][name])
    report['park'][name] = {'asset': entry['asset'], 'blocks': entry['blocks'], 'collision': str(flag), 'bounds_min_cm': lo, 'bounds_max_cm': hi,
                          'materials': sorted(found)}

for name in ('SM_SkateDeck', 'SM_SkateTruck', 'SM_SkateWheel'):
    mesh = helper['import_mesh'](OUT / 'board' / f'{name}.fbx', '/Game/SkatePark/Board', name)
    assert len(mesh.static_materials) == 1, (name, 'expected one material slot')
    mesh.set_material(0, material)
    body = mesh.get_editor_property('body_setup')
    if body: body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    assert E.save_loaded_asset(mesh), (name, 'board save failed')
    lo, hi = check_axes(name, mesh, build['meshes'][name])
    report['board'][name] = {'asset': '/Game/SkatePark/Board/' + name, 'bounds_min_cm': lo, 'bounds_max_cm': hi}

deck = report['board']['SM_SkateDeck']
assert abs(deck['bounds_max_cm'][2] - 4.5) < 0.05 and abs(deck['bounds_max_cm'][1] - 10.25) < 0.05, ('deck contract', deck)
truck = report['board']['SM_SkateTruck']
assert abs(truck['bounds_max_cm'][2]) < 0.05 and truck['bounds_min_cm'][0] < -3.5, ('truck origin / kingpin toward -X', truck)
report['trees'] = {}
for name, rows in park.get('trees', {}).items():
    assert E.does_asset_exist('/Game/Japan/Assets/' + name), ('missing island tree', name)
    report['trees'][name] = len(rows)
report['materials'] = {name: m.get_path_name() for name, m in surfaces.items()}
report['park_json_sha256'] = build['identity']['park_json_sha256']
report['runtime_park_sha256'] = build['identity']['runtime_park_sha256']
assets = [row['asset'] for row in park['meshes']]
assets += ['/Game/SkatePark/Board/' + name for name in report['board']]
assets += [value.split('.')[0] for value in report['materials'].values()]
assets += sorted(owned_textures)
content = yori.GAME / 'unreal/Content'
report['assets'] = assets
report['files'] = mesh_geometry.package_inventory(content, assets)
report['retired'] = native_membership.retire(E, previous, [row['name'] for row in park['meshes']],
                                            '/Game/SkatePark', 'SM_')
assert mesh_geometry.package_inventory(content, assets) == report['files'], 'Pier packages changed during retirement'
(OUT / 'import-report.json').write_text(json.dumps(report, indent=2) + '\n')
unreal.log('SKATEPARK IMPORT COMPLETE')
