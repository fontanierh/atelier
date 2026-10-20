"""Import the committed Belmonte environment into its own /Game/Belmonte library.

Geometry keeps its authored metre scale and material slots. The shared island
lighting and haze light simple painterly surfaces; no Haras shaders or systems
are imported. Source hulls are collision only, and plants reuse island assets.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori  # noqa: E402
import json
import runpy
import unreal
import atmosphere
import ground_grain

OUT = yori.OUT / 'belmonte'
ROOT = '/Game/Belmonte'
E = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
REGISTRY = unreal.AssetRegistryHelpers.get_asset_registry()


def parent():
    name = 'M_Belmonte'
    asset = ROOT + '/Materials/' + name
    material = E.load_asset(asset) if E.does_asset_exist(asset) else AT.create_asset(name, ROOT + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(material)

    def node(cls, **properties):
        result = MEL.create_material_expression(material, cls)
        for key, value in properties.items():
            result.set_editor_property(key, value)
        return result

    def scalar(key, value):
        return node(unreal.MaterialExpressionScalarParameter, parameter_name=key, default_value=value)

    def colour(key, value):
        return node(unreal.MaterialExpressionVectorParameter, parameter_name=key, default_value=unreal.LinearColor(*value, 1.))

    vc = node(unreal.MaterialExpressionVertexColor)
    uv = node(unreal.MaterialExpressionTextureCoordinate)
    world = node(unreal.MaterialExpressionWorldPosition)
    tex = node(unreal.MaterialExpressionTextureObjectParameter, parameter_name='Tex',
               texture=E.load_asset('/Engine/EngineResources/WhiteSquareTexture'))
    inputs = [('C', vc, ''), ('Alpha', vc, 'A'), ('UV', uv, ''), ('World', world, ''), ('Tex', tex, ''), ('Tile', scalar('Tile', 4.), ''),
              ('Colour', colour('Colour', (.7, .6, .4)), ''), ('Tint', colour('Tint', (1., 1., 1.)), ''),
              ('WhiteVertex', scalar('WhiteVertex', 0.), ''), ('Strength', scalar('Strength', 0.), ''),
              ('Brightness', scalar('Brightness', 1.), ''), ('Atlas', scalar('Atlas', 0.), ''),
              ('Terrain', scalar('Terrain', 0.), ''), ('Dry', colour('Dry', (.40, .37, .18)), ''),
              ('Green', colour('Green', (.16, .24, .08)), ''), ('Dirt', colour('Dirt', (.42, .30, .17)), ''),
              ('Rock', colour('Rock', (.36, .37, .35)), '')]
    base = node(unreal.MaterialExpressionCustom, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                code='''
float3 vertexLinear = lerp(C.rgb/12.92, pow((C.rgb+.055)/1.055, 2.4), step(.04045, C.rgb));
float white = step(.995, min(C.r, min(C.g, C.b))) * WhiteVertex;
float3 paint = lerp(vertexLinear, Colour.rgb, white);
float4 weights = float4(C, Alpha);
weights /= max(dot(weights, float4(1,1,1,1)), .001);
float3 ground = weights.r*Dry.rgb + weights.g*Green.rgb + weights.b*Dirt.rgb + weights.a*Rock.rgb;
paint = lerp(paint, ground, Terrain);
float2 coord=lerp(UV/Tile,World.xy/(Tile*100),Terrain);
float3 detail = Texture2DSample(Tex, TexSampler, coord).rgb;
float3 surface = lerp(1, detail*lerp(2,1,Atlas), Strength);
if(Terrain>.5){
'''+ground_grain.code('Tex','TexSampler','World')+'''
surface=groundDetail;
}
return paint * Tint.rgb * surface * Brightness;
''')
    custom_inputs = []
    for key, _, _ in inputs:
        value = unreal.CustomInput()
        value.set_editor_property('input_name', key)
        custom_inputs.append(value)
    base.set_editor_property('inputs', custom_inputs)
    for key, expression, output in inputs:
        assert MEL.connect_material_expressions(expression, output, base, key), key
    fill = node(unreal.MaterialExpressionMultiply, const_b=.045)
    assert MEL.connect_material_expressions(base, '', fill, 'A')
    shaded, emission = atmosphere.apply(material, base, fill)
    assert MEL.connect_material_property(shaded, '', unreal.MaterialProperty.MP_BASE_COLOR)
    assert MEL.connect_material_property(emission, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    assert MEL.connect_material_property(scalar('Roughness', .87), '', unreal.MaterialProperty.MP_ROUGHNESS)
    assert MEL.connect_material_property(scalar('Specular', .12), '', unreal.MaterialProperty.MP_SPECULAR)
    material.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(material)
    E.save_loaded_asset(material)
    return material


def textures(report):
    result = {}
    for file in sorted({entry['texture'] for entry in report['materials'].values() if entry['texture']}):
        name = Path(file).stem
        task = unreal.AssetImportTask()
        task.filename = str(OUT / 'textures' / file)
        task.destination_path = ROOT + '/Textures'
        task.destination_name = name
        task.automated = True
        task.replace_existing = True
        task.save = True
        AT.import_asset_tasks([task])
        asset = E.load_asset(ROOT + '/Textures/' + name)
        assert asset, file
        asset.set_editor_property('srgb', True)
        asset.set_editor_property('max_texture_size', 1024)
        asset.set_editor_property('lod_group', unreal.TextureGroup.TEXTUREGROUP_WORLD)
        E.save_loaded_asset(asset)
        result[file] = asset
    return result


def join_parent(texture):
    name = 'M_BelmonteJoin'; folder = ROOT + '/Materials'
    material = E.load_asset(folder+'/'+name) if E.does_asset_exist(folder+'/'+name) else AT.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(material)
    def node(cls, **properties):
        result = MEL.create_material_expression(material, cls)
        for key, value in properties.items(): result.set_editor_property(key, value)
        return result
    vc = node(unreal.MaterialExpressionVertexColor)
    world = node(unreal.MaterialExpressionWorldPosition)
    assert texture
    ground = node(unreal.MaterialExpressionTextureObjectParameter, parameter_name='Ground', texture=texture)
    inputs = [('C', vc, ''), ('Alpha', vc, 'A'), ('World', world, ''), ('Ground', ground, '')]
    shade = node(unreal.MaterialExpressionCustom, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                 code='''float3 valley=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));
'''+ground_grain.code('Ground','GroundSampler','World')+'\nreturn valley*groundDetail;')
    custom_inputs = []
    for key, _, _ in inputs:
        value = unreal.CustomInput(); value.set_editor_property('input_name', key); custom_inputs.append(value)
    shade.set_editor_property('inputs', custom_inputs)
    for key, expression, output in inputs:
        assert MEL.connect_material_expressions(expression, output, shade, key)
    fill = node(unreal.MaterialExpressionCustom, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                code='return Shade*.045*(1-Alpha);')
    values = []
    for key in ['Shade', 'Alpha']:
        value = unreal.CustomInput(); value.set_editor_property('input_name', key); values.append(value)
    fill.set_editor_property('inputs', values)
    assert MEL.connect_material_expressions(shade, '', fill, 'Shade')
    assert MEL.connect_material_expressions(vc, 'A', fill, 'Alpha')
    base, emission = atmosphere.apply(material, shade, fill)
    assert MEL.connect_material_property(base, '', unreal.MaterialProperty.MP_BASE_COLOR)
    assert MEL.connect_material_property(emission, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop,code in [(unreal.MaterialProperty.MP_ROUGHNESS,'return lerp(.87,1.,A);'),
                      (unreal.MaterialProperty.MP_SPECULAR,'return lerp(.12,0.,A);')]:
        value=node(unreal.MaterialExpressionCustom,output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,code=code)
        alpha=unreal.CustomInput();alpha.set_editor_property('input_name','A');value.set_editor_property('inputs',[alpha])
        assert MEL.connect_material_expressions(vc,'A',value,'A')
        assert MEL.connect_material_property(value,'',prop)
    material.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(material); E.save_loaded_asset(material)
    return material


def surfaces(report, master, images):
    ground={entry['texture'] for entry in report['materials'].values() if entry.get('terrain')}
    assert len(ground)==1,ground
    join = join_parent(images[ground.pop()])
    for entry in report['materials'].values():
        name = entry['name']
        path = ROOT + '/Materials/' + name
        material = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, ROOT + '/Materials', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        MEL.clear_all_material_instance_parameters(material)
        MEL.set_material_instance_parent(material, join if entry.get('join') else master)
        if entry.get('join'):
            MEL.update_material_instance(material)
            E.save_loaded_asset(material)
            continue
        for key, value in [('Colour', entry['colour']), ('Tint', entry['tint'])] + list(entry['layers'].items()):
            MEL.set_material_instance_vector_parameter_value(material, key, unreal.LinearColor(*value[:3], 1.))
        for key, value in [('Tile', entry['tile_m']), ('WhiteVertex', float(entry['white_vertex'])),
                           ('Terrain', float(entry['terrain'])), ('Brightness', entry['brightness']),
                           ('Atlas', float(entry['atlas'])), ('Strength', float(bool(entry['texture']))),
                           ('Roughness', .25 if entry['water'] else .87)]:
            MEL.set_material_instance_scalar_parameter_value(material, key, float(value))
        if entry['texture']:
            MEL.set_material_instance_texture_parameter_value(material, 'Tex', images[entry['texture']])
        MEL.update_material_instance(material)
        E.save_loaded_asset(material)


def import_mesh(path, name):
    generic = unreal.InterchangeGenericAssetsPipeline()
    pipeline = generic.get_editor_property('mesh_pipeline')
    pipeline.set_editor_property('import_static_meshes', True)
    pipeline.set_editor_property('import_skeletal_meshes', False)
    pipeline.set_editor_property('combine_static_meshes_behavior', unreal.InterchangeCombineStaticMeshesBehavior.ALL)
    pipeline.set_editor_property('build_nanite', False)
    generic.get_editor_property('animation_pipeline').set_editor_property('import_animations', False)
    stack = unreal.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(unreal.InterchangeGLTFPipeline())
    folder = ROOT + '/Import/' + name
    task = unreal.AssetImportTask()
    task.filename = str(path)
    task.destination_path = folder
    task.options = stack
    task.automated = True
    task.replace_existing = True
    task.save = True
    AT.import_asset_tasks([task])
    found = [str(asset.package_name) for asset in REGISTRY.get_assets_by_path(folder, recursive=True)
             if str(asset.asset_class_path.asset_name) == 'StaticMesh']
    assert len(found) == 1, (name, found)
    target = ROOT + '/Meshes/' + name
    assert E.rename_asset(found[0], target), target
    return E.load_asset(target)


def generate_terrain_lods(mesh):
    """Two reduced LODs for refined valley terrain tiles over 12,000 triangles; collision stays on LOD0."""
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    assert editor is not None, 'StaticMeshEditor subsystem is unavailable'
    options = unreal.StaticMeshReductionOptions()
    options.set_editor_property('auto_compute_lod_screen_size', False)
    plan = ((1., 1.), (.5, .35), (.25, .15))
    levels = []
    for percent, screen in plan:
        level = unreal.StaticMeshReductionSettings()
        level.set_editor_property('percent_triangles', percent)
        level.set_editor_property('screen_size', screen)
        levels.append(level)
    options.set_editor_property('reduction_settings', levels)
    assert editor.set_lods(mesh, options) == len(plan), (mesh.get_name(), 'LOD generation')
    assert editor.set_lod_screen_sizes(mesh, [screen for _, screen in plan]), (mesh.get_name(), 'LOD screen sizes')


def main():
    """@cc [owner:fontanierh,label:correctness] collision-hull-distance-fields
    Separate source collision hulls MUST disable LOD0 mesh distance-field generation. This
    optimization MUST NOT change visible-mesh build settings, hull geometry or physics association.
    """
    report = json.loads((OUT / 'build-report.json').read_text())
    runtime = json.loads((OUT / 'runtime.json').read_text())
    defaults = {}
    for group in runtime['groups']:
        if not group['plant']:
            defaults.setdefault(group['asset'].split('.')[-1], group['materials'])
    E.make_directory(ROOT)
    surfaces(report, parent(), textures(report))
    imported = {}
    for index, entry in enumerate(report['meshes']):
        name = entry['name']
        target = ROOT + '/Meshes/' + name
        if E.does_asset_exist(target):
            E.delete_asset(target)
        mesh = import_mesh(OUT / entry['path'], name)
        assert len(mesh.get_editor_property('static_materials')) == len(defaults[name]), (name, 'material slots')
        for slot, path in enumerate(defaults[name]):
            material = E.load_asset(path)
            assert material, path
            mesh.set_material(slot, material)
        assert mesh.get_num_triangles(0) == entry['triangles'], (name, 'triangle count', mesh.get_num_triangles(0), entry['triangles'])
        if entry.get('collision'):
            collision_name = name + '_Collision'
            if E.does_asset_exist(ROOT + '/Meshes/' + collision_name):
                E.delete_asset(ROOT + '/Meshes/' + collision_name)
            collision = import_mesh(OUT / 'glb' / Path(entry['collision']['path']).name, collision_name)
            # This asset supplies physics through complex_collision_mesh; no component draws it.
            unreal.load_module('StaticMeshEditor')       # the commandlet loads it only on request
            editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
            assert editor is not None, 'StaticMeshEditor subsystem is unavailable'
            settings = editor.get_lod_build_settings(collision, 0)
            settings.set_editor_property('distance_field_resolution_scale', 0.)
            editor.set_lod_build_settings(collision, 0, settings)
            ground = E.load_asset(ROOT + '/Materials/MI_BM_Ground')
            for slot in range(len(collision.get_editor_property('static_materials'))):
                collision.set_material(slot, ground)
            mesh.set_editor_property('complex_collision_mesh', collision)
            E.save_loaded_asset(collision)
        body = mesh.get_editor_property('body_setup')
        if name.startswith('SM_BM_BT_Terrain_'):
            mesh.set_editor_property('allow_cpu_access', name in {'SM_BM_BT_Terrain_0_0', 'SM_BM_BT_Terrain_4_4'})
            if entry['triangles'] > 12000:
                generate_terrain_lods(mesh)
        assert body, name
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        body.set_editor_property('double_sided_geometry', True)
        E.save_loaded_asset(mesh)
        box = mesh.get_bounding_box()
        low, high = entry['bounds_m']
        expected = [low[0]*100, -high[1]*100, low[2]*100, high[0]*100, -low[1]*100, high[2]*100]
        actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
        assert max(abs(a-b) for a, b in zip(actual, expected)) < 1., (name, 'bounds', actual, expected)
        imported[name] = {'triangles': mesh.get_num_triangles(0), 'bounds_cm': actual,
                          'collision_hulls': bool(entry.get('collision'))}
        unreal.log(f'BELMONTE IMPORT {index + 1}/{len(report["meshes"])} {name}')
    (OUT / 'import-report.json').write_text(json.dumps(imported, indent=1) + '\n')
    # Both render and collision assets now reference only the region's materials.
    # Drop Interchange's placeholder materials and rename redirectors.
    E.delete_directory(ROOT + '/Import')
    runpy.run_path(str(Path(__file__).with_name('racing_tv_material.py')))
    unreal.log(f'BELMONTE IMPORT COMPLETE: {len(imported)} meshes')


main()
