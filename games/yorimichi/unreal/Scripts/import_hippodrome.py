"""Import the Hidamari Hippodrome (world/regions/hippodrome/build.py) into /Game/Hippodrome.

Each GLB becomes a static mesh SM_HD_<Part> with complex-as-simple collision (people walk the platform, climb the
grandstand and stop at the rails). The course's own surfaces get small materials of their own: the tiling turf and
raked dirt maps (world-scaled UVs), stone for the skirts and white paint for the rails. The Tripo structures keep their
painted maps on the venue's own M_HD_Structure material. Bounds are checked against
the build report (Blender metres -> Unreal centimetres, y mirrored).

Copies hippodrome.json to Content/Data/hippodrome/, which AHippodrome reads to place the venue meshes.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
import json
import runpy
import shutil
import unreal

OUT = yori.OUT / 'hippodrome' / 'region'
ROOT = '/Game/Hippodrome'
DATA = Path(__file__).resolve().parents[1] / 'Content' / 'Data' / 'hippodrome'
E = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
REGISTRY = unreal.AssetRegistryHelpers.get_asset_registry()
helper = runpy.run_path(str(Path(__file__).with_name('import_megapark.py'))); sha = helper['sha']
# name: (colour map or linear RGB, roughness, two-sided)
SURFACES = {'HD_Grass': ('T_HD_Grass.png', .95, False), 'HD_Dirt': ('T_HD_Dirt.png', .95, False),
            'HD_Stone': ((.36, .35, .32), .9, True), 'HD_Rail': ((.86, .85, .80), .6, False)}


def surface(key, colour, roughness, two_sided):
    name = 'M_' + key; dest = ROOT + '/Materials'
    m = AT.create_asset(name, dest, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property('two_sided', two_sided)
    if isinstance(colour, str):
        node = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSample)
        node.set_editor_property('texture', helper['texture'](OUT / 'textures' / colour, 'T_' + key[3:], dest=ROOT + '/Textures', wrap=True))
        node.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        assert MEL.connect_material_property(node, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    else:
        node = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector)
        node.set_editor_property('constant', unreal.LinearColor(*colour, 1.))
        assert MEL.connect_material_property(node, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for value, prop in [(roughness, unreal.MaterialProperty.MP_ROUGHNESS), (0., unreal.MaterialProperty.MP_METALLIC),
                        (.3, unreal.MaterialProperty.MP_SPECULAR)]:
        constant = MEL.create_material_expression(m, unreal.MaterialExpressionConstant); constant.set_editor_property('r', value)
        assert MEL.connect_material_property(constant, '', prop)
    MEL.layout_material_expressions(m); MEL.recompile_material(m); E.save_loaded_asset(m)
    return m



def structure_material():
    material = AT.create_asset('M_HD_Structure', ROOT + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    material.set_editor_property('two_sided', True)
    base = MEL.create_material_expression(material, unreal.MaterialExpressionTextureSampleParameter2D)
    base.set_editor_property('parameter_name', 'BaseColorTexture')
    base.set_editor_property('texture', E.load_asset('/Engine/EngineResources/WhiteSquareTexture'))
    assert MEL.connect_material_property(base, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    fill = MEL.create_material_expression(material, unreal.MaterialExpressionMultiply)
    fill.set_editor_property('const_b', .3)
    assert MEL.connect_material_expressions(base, 'RGB', fill, 'A')
    assert MEL.connect_material_property(fill, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for value, prop in [(.7, unreal.MaterialProperty.MP_ROUGHNESS), (.3, unreal.MaterialProperty.MP_SPECULAR)]:
        node = MEL.create_material_expression(material, unreal.MaterialExpressionConstant)
        node.set_editor_property('r', value)
        assert MEL.connect_material_property(node, '', prop)
    MEL.recompile_material(material)
    E.save_loaded_asset(material)
    return material

def pipeline():
    generic = unreal.InterchangeGenericAssetsPipeline()
    mesh = generic.get_editor_property('mesh_pipeline')
    mesh.set_editor_property('import_static_meshes', True)
    mesh.set_editor_property('import_skeletal_meshes', False)
    mesh.set_editor_property('combine_static_meshes_behavior', unreal.InterchangeCombineStaticMeshesBehavior.ALL)
    # Plain meshes like the rest of the island: Nanite's fallback would simplify the flat grass grid (and LOD0's count).
    mesh.set_editor_property('build_nanite', False)
    generic.get_editor_property('animation_pipeline').set_editor_property('import_animations', False)
    stack = unreal.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(unreal.InterchangeGLTFPipeline())
    return stack


def assets_in(folder):
    found = {}
    for data in REGISTRY.get_assets_by_path(folder, recursive=True):
        found.setdefault(str(data.asset_class_path.asset_name), []).append(str(data.package_name))
    return found


def import_mesh(path, name):
    folder = f'{ROOT}/Meshes/{name}'
    task = unreal.AssetImportTask()
    for key, value in dict(filename=str(path), destination_path=folder, automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(key, value)
    task.set_editor_property('options', pipeline())
    AT.import_asset_tasks([task])
    found = assets_in(folder)
    assert len(found.get('StaticMesh', [])) == 1, (name, found)
    target = f'{ROOT}/{name}'
    assert E.rename_asset(found['StaticMesh'][0], target), (name, 'rename failed')
    return E.load_asset(target), found


def restyle(instance, master):
    """A Tripo structure's glTF material onto the adventure character look, keeping its painted map."""
    albedo = MEL.get_material_instance_texture_parameter_value(instance, 'BaseColorTexture')
    MEL.clear_all_material_instance_parameters(instance)
    MEL.set_material_instance_parent(instance, master)
    if albedo:
        MEL.set_material_instance_texture_parameter_value(instance, 'BaseColorTexture', albedo)
    MEL.update_material_instance(instance); E.save_loaded_asset(instance, False)
    return instance


report = json.loads((OUT / 'build-report.json').read_text())
data = json.loads((OUT / 'hippodrome.json').read_text())
if E.does_directory_exist(ROOT):
    E.delete_directory(ROOT)
E.make_directory(ROOT)
master = structure_material()
surfaces = {key: surface(key, *spec) for key, spec in SURFACES.items()}
result = {}
for entry in data['meshes']:
    name = entry['name']; expected = report['meshes'][name]
    path = OUT / 'glb' / f'{name}.glb'
    assert sha(path) == expected['sha256'], 'stale region build: ' + name
    mesh, found = import_mesh(path, name)
    assert mesh.get_num_triangles(0) == expected['triangles'], (name, mesh.get_num_triangles(0), expected['triangles'])
    slots = list(mesh.get_editor_property('static_materials'))
    assert len(slots) == 1, (name, 'one material slot expected', len(slots))
    if expected['material'] in surfaces:
        slots[0].set_editor_property('material_interface', surfaces[expected['material']])
    else:
        instances = found.get('MaterialInstanceConstant', [])
        assert len(instances) == 1, (name, instances)
        slots[0].set_editor_property('material_interface', restyle(E.load_asset(instances[0]), master))
    mesh.set_editor_property('static_materials', slots)
    body = mesh.get_editor_property('body_setup'); assert body, name
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    body.set_editor_property('double_sided_geometry', True)
    E.save_loaded_asset(mesh)
    box = mesh.get_bounding_box()
    lo, hi = [box.min.x, box.min.y, box.min.z], [box.max.x, box.max.y, box.max.z]
    want_lo = [expected['min'][0] * 100, -expected['max'][1] * 100, expected['min'][2] * 100]
    want_hi = [expected['max'][0] * 100, -expected['min'][1] * 100, expected['max'][2] * 100]
    assert max(abs(a - b) for a, b in zip(lo + hi, want_lo + want_hi)) < 1., (name, 'unit/axis conversion', lo, hi, want_lo, want_hi)
    result[name] = {'triangles': expected['triangles'], 'bounds_cm': [lo, hi]}
    unreal.log(f'HIPPODROME {name}: {expected["triangles"]} triangles')
DATA.mkdir(parents=True, exist_ok=True)
shutil.copy2(OUT / 'hippodrome.json', DATA / 'hippodrome.json')
(OUT / 'import-report.json').write_text(json.dumps(result, indent=1) + '\n')
unreal.log(f'HIPPODROME IMPORT COMPLETE: {len(result)} meshes')
