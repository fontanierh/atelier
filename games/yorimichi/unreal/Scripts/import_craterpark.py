"""Import Crater Park's meshes, textures and materials into /Game/CraterPark (docs/CRATERPARK.md).

Only /Game/CraterPark is written. The island places the park at runtime from craterpark/park.json
(ASuperUltraMegaPark::Spawn); there is no standalone level.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yori
import json
import unreal
import import_megapark as megapark

OUT = yori.OUT / 'craterpark'
SOURCE = yori.ASSETS / 'craterpark'
ROOT = '/Game/CraterPark'
E = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
ROUGHNESS = .8


# The park's own hillside and edge guard carry snow like the caldera round them (docs/CRATERPARK.md, "Snow"): the block
# and the boundary; the skating surfaces, foundations and bridges stay clear.
SNOWY = {'material_024', 'material_027'}


def parent(textured):
    """A lit opaque parent: base colour from a texture on UV0 times Tint, or Tint alone; where Snow is 1, snow lies on
    the faces that look up, in world-space patches that follow the placed park."""
    name = 'M_CP_Textured' if textured else 'M_CP_Flat'; path = ROOT + '/Materials/' + name
    if E.does_asset_exist(path):
        m = E.load_asset(path); MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset(name, ROOT + '/Materials', unreal.Material, unreal.MaterialFactoryNew())

    def node(kind, **properties):
        n = MEL.create_material_expression(m, kind, 0, 0)
        for k, v in properties.items(): n.set_editor_property(k, v)
        return n

    def custom(code, inputs, kind=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
        n = node(unreal.MaterialExpressionCustom, code=code, output_type=kind)
        args = []
        for key in inputs:
            arg = unreal.CustomInput(); arg.set_editor_property('input_name', key); args.append(arg)
        n.set_editor_property('inputs', args)
        for key, (source, output) in inputs.items(): assert MEL.connect_material_expressions(source, output, n, key)
        return n

    tint = node(unreal.MaterialExpressionVectorParameter, parameter_name='Tint', default_value=unreal.LinearColor(1, 1, 1, 1))
    snow = node(unreal.MaterialExpressionScalarParameter, parameter_name='Snow', default_value=0.)
    colour = tint
    if textured:
        sample = node(unreal.MaterialExpressionTextureSampleParameter2D, parameter_name='Base',
                      texture=unreal.load_asset('/Engine/EngineResources/WhiteSquareTexture'))
        colour = node(unreal.MaterialExpressionMultiply)
        MEL.connect_material_expressions(sample, 'RGB', colour, 'A'); MEL.connect_material_expressions(tint, '', colour, 'B')
    inputs = {'B': (colour, ''), 'S': (snow, ''), 'N': (node(unreal.MaterialExpressionVertexNormalWS), ''),
              'W': (node(unreal.MaterialExpressionWorldPosition), '')}
    cover = ('float up=saturate((N.z-.55)/.3);'
             'float a=sin(W.x*.0021+sin(W.y*.0017)*2.3)*sin(W.y*.0019+sin(W.x*.0013)*1.9);'
             'float b=sin(W.x*.011+sin(W.y*.009)*1.7)*sin(W.y*.012+sin(W.x*.008)*1.4);'
             'float m=S*up*saturate((.62+.45*a+.18*b)*2.5);')
    base = custom(cover + 'return lerp(B,float3(.80,.83,.88),m);', inputs)
    rough = custom(cover + 'return lerp(%.2f,.55,m);' % ROUGHNESS, inputs, unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    dark = node(unreal.MaterialExpressionConstant3Vector, constant=unreal.LinearColor(0., 0., 0., 1.))
    for n, prop in ((base, unreal.MaterialProperty.MP_BASE_COLOR), (rough, unreal.MaterialProperty.MP_ROUGHNESS),
                    (dark, unreal.MaterialProperty.MP_EMISSIVE_COLOR)):
        assert MEL.connect_material_property(n, '', prop)
    MEL.layout_material_expressions(m); MEL.recompile_material(m); E.save_loaded_asset(m)
    return m


def materials():
    parents = {True: parent(True), False: parent(False)}
    result = {}
    for spec in json.loads((SOURCE / 'materials.json').read_text()):
        name = 'MI_CP_' + spec['id']; dest = ROOT + '/Materials'; path = dest + '/' + name
        mi = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, dest, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        textured = bool(spec['texture'])
        MEL.set_material_instance_parent(mi, parents[textured])
        if textured:
            texture = megapark.texture(SOURCE / spec['texture'], 'T_CP_' + Path(spec['texture']).stem.replace('-', '_'),
                                       dest=ROOT + '/Textures', wrap=True)
            MEL.set_material_instance_texture_parameter_value(mi, 'Base', texture)
        # The source's base colours are sRGB.
        tint = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in spec['baseColor']]
        MEL.set_material_instance_vector_parameter_value(mi, 'Tint', unreal.LinearColor(*tint, 1.))
        MEL.set_material_instance_scalar_parameter_value(mi, 'Snow', float(spec['id'] in SNOWY))
        overrides = mi.get_editor_property('base_property_overrides')
        overrides.set_editor_property('override_two_sided', True); overrides.set_editor_property('two_sided', spec['doubleSided'])
        mi.set_editor_property('base_property_overrides', overrides)
        MEL.update_material_instance(mi); E.save_loaded_asset(mi); result[spec['id']] = mi
    return result


def main():
    report = json.loads((OUT / 'build.json').read_text())
    assert megapark.sha(SOURCE / 'scene.json') == report['scene_sha256'], 'Rebuild Crater Park first (world.craterpark)'
    unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    # import_megapark's mesh helpers write to the Crater Park's own folder and seed.
    megapark.OUT = OUT; megapark.ROOT = ROOT; megapark.SEED = 'SM_CP_ImportSeed'
    E.make_directory(ROOT + '/Meshes')
    mis = materials(); results = []
    for entry in report['render'] + report['collision']:
        collision = entry['name'].startswith('UC_')
        megapark.mesh_actor(entry, collision, mis, None, editor, results, place=False)
    E.save_directory(ROOT, only_if_is_dirty=True, recursive=True)
    result = {'root': ROOT, 'source_sha256': report['scene_sha256'], 'meshes': results, 'materials': len(mis),
              'render_triangles': sum(e['triangles'] for e in results if not e['collision']),
              'collision_triangles': sum(e['triangles'] for e in results if e['collision'])}
    (OUT / 'import-report.json').write_text(json.dumps(result, indent=2) + '\n')
    print('CRATERPARK IMPORT COMPLETE', result['render_triangles'], result['collision_triangles'], flush=True)


if __name__ == '__main__': main()
