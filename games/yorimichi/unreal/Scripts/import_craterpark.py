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


def parent(textured):
    """A lit opaque parent: base colour from a texture on UV0 times Tint, or Tint alone."""
    name = 'M_CP_Textured' if textured else 'M_CP_Flat'; path = ROOT + '/Materials/' + name
    if E.does_asset_exist(path):
        m = E.load_asset(path); MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset(name, ROOT + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    tint = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -600, 0)
    tint.set_editor_property('parameter_name', 'Tint'); tint.set_editor_property('default_value', unreal.LinearColor(1, 1, 1, 1))
    colour = tint
    if textured:
        sample = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -600, -250)
        sample.set_editor_property('parameter_name', 'Base')
        sample.set_editor_property('texture', unreal.load_asset('/Engine/EngineResources/WhiteSquareTexture'))
        multiply = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -250, -100)
        MEL.connect_material_expressions(sample, 'RGB', multiply, 'A'); MEL.connect_material_expressions(tint, '', multiply, 'B')
        colour = multiply
    MEL.connect_material_property(colour, '', unreal.MaterialProperty.MP_BASE_COLOR)
    rough = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -250, 150)
    rough.set_editor_property('r', ROUGHNESS)
    MEL.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m); E.save_loaded_asset(m)
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
