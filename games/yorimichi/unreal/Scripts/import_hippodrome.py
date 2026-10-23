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
from atelier.unreal_mesh_reuse import MeshReuse, AssetGroup, set_if_changed
from atelier.native_protocol import native_context
from atelier import native_membership

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
    m = E.load_asset(dest + '/' + name) if E.does_asset_exist(dest + '/' + name) else AT.create_asset(name, dest, unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(m)
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
    path = ROOT + '/Materials/M_HD_Structure'
    material = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset('M_HD_Structure', ROOT + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(material)
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
E.make_directory(ROOT)
previous_meshes = native_membership.inventory(E, ROOT, 'SM_HD_')
material_paths=[ROOT+'/Materials/M_HD_Structure',*[ROOT+'/Materials/M_'+key for key in SURFACES]]
material_paths += [ROOT+'/Textures/T_Grass',ROOT+'/Textures/T_Dirt']
materials=AssetGroup(native_context(yori.GAME.name),'unreal.hippodrome',__file__,
    ('surface','structure_material'),parameters=SURFACES,sources=[OUT/'textures'/file for file in data['textures'].values()])
if not materials.matches(material_paths):
    structure_material()
    for key,spec in SURFACES.items():surface(key,*spec)
    materials.validated(material_paths)
master=E.load_asset(ROOT+'/Materials/M_HD_Structure')
surfaces={key:E.load_asset(ROOT+'/Materials/M_'+key) for key in SURFACES}


def validate_reused_mesh(mesh, expected):
    if not mesh or mesh.get_num_triangles(0)!=expected['triangles']:return False
    slots=list(mesh.get_editor_property('static_materials'))
    if len(slots)!=1 or mesh.get_material(0) is None:return False
    if expected['material'] in surfaces:
        if mesh.get_material(0)!=surfaces[expected['material']]:return False
    else:
        instance=mesh.get_material(0)
        if not isinstance(instance,unreal.MaterialInstanceConstant):return False
        if instance.get_editor_property('parent')!=master:return False
        if not MEL.get_material_instance_texture_parameter_value(instance,'BaseColorTexture'):return False
    body=mesh.get_editor_property('body_setup')
    if not body or body.get_editor_property('collision_trace_flag')!=unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE or not body.get_editor_property('double_sided_geometry'):return False
    box=mesh.get_bounding_box();lo,hi=expected['min'],expected['max']
    actual=[box.min.x,box.min.y,box.min.z,box.max.x,box.max.y,box.max.z]
    wanted=[lo[0]*100,-hi[1]*100,lo[2]*100,hi[0]*100,-lo[1]*100,hi[2]*100]
    return max(abs(a-b) for a,b in zip(actual,wanted))<1.

reuse=MeshReuse(native_context(yori.GAME.name),'unreal.hippodrome',__file__,('import_mesh','pipeline'),
    report_member='generated/hippodrome/region/build-report.json',validation_functions=('validate_reused_mesh',))
result = {}
for entry in data['meshes']:
    name = entry['name']; expected = report['meshes'][name]
    path = OUT / 'glb' / f'{name}.glb'
    assert sha(path) == expected['sha256'], 'stale region build: ' + name
    target=ROOT+'/'+name
    mesh=reuse.acquire(name,target,geometry=expected,sources=[(target,path,expected['sha256'])],
        donor_geometry=lambda saved: saved.get('meshes',{}).get(name),
        validator=lambda candidate: validate_reused_mesh(candidate,expected))
    reused=mesh is not None
    if mesh is None:
        if E.does_asset_exist(target):assert E.delete_asset(target),target
        mesh,found=import_mesh(path,name)
        reuse.imported(name)
    else:found=assets_in(f'{ROOT}/Meshes/{name}')
    assert mesh.get_num_triangles(0) == expected['triangles'], (name, mesh.get_num_triangles(0), expected['triangles'])
    slots = list(mesh.get_editor_property('static_materials'))
    assert len(slots) == 1, (name, 'one material slot expected', len(slots))
    if expected['material'] in surfaces:
        if mesh.get_material(0)!=surfaces[expected['material']]:mesh.set_material(0,surfaces[expected['material']])
    else:
        instance=mesh.get_material(0)
        assert isinstance(instance,unreal.MaterialInstanceConstant),(name,'missing imported painted material')
        if not reused:restyle(instance,master)
    body = mesh.get_editor_property('body_setup'); assert body, name
    set_if_changed(body,'collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    set_if_changed(body,'double_sided_geometry', True)
    assert E.save_loaded_asset(mesh,only_if_is_dirty=True),name
    box = mesh.get_bounding_box()
    lo, hi = [box.min.x, box.min.y, box.min.z], [box.max.x, box.max.y, box.max.z]
    want_lo = [expected['min'][0] * 100, -expected['max'][1] * 100, expected['min'][2] * 100]
    want_hi = [expected['max'][0] * 100, -expected['min'][1] * 100, expected['max'][2] * 100]
    assert max(abs(a - b) for a, b in zip(lo + hi, want_lo + want_hi)) < 1., (name, 'unit/axis conversion', lo, hi, want_lo, want_hi)
    assert validate_reused_mesh(mesh,expected),name
    reuse.validated(name)
    result[name] = {'triangles': expected['triangles'], 'bounds_cm': [lo, hi]}
    unreal.log(f'HIPPODROME {name}: {expected["triangles"]} triangles')
native_membership.retire(E,previous_meshes,[entry['name'] for entry in data['meshes']],ROOT,'SM_HD_')
reuse.finish()
DATA.mkdir(parents=True, exist_ok=True)
shutil.copy2(OUT / 'hippodrome.json', DATA / 'hippodrome.json')
(OUT.parent / 'import-report.json').write_text(json.dumps(result, indent=1) + '\n')
unreal.log(f'HIPPODROME IMPORT COMPLETE: {len(result)} meshes')
