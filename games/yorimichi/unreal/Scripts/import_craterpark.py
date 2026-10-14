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
RESTYLE = OUT / 'textures'
E = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
# Matte like the terrain and the Mega Park: the engine's default specular put a pale sky sheen on every surface.
ROUGHNESS = 1.
# The baked occlusion (build.py ao, vertex colour R): how much it takes from the sky's fill (Ambient Occlusion, as the
# Mega Park's lightmap occlusion) and from the albedo itself (a cavity darkening the sun sees too).
OCCLUSION = .6
CAVITY = .3


# The park's own hillside carries snow like the caldera round it (docs/CRATERPARK.md, "Snow"); the skating surfaces,
# the edge guard and its coping, foundations and bridges stay clear.
SNOWY = {'material_024'}


def parent(kind):
    """A lit opaque parent, kind 'Textured' (Base on UV0), 'World' (Base world-aligned on three axes, Metres per tile)
    or 'Flat'; its colour times Tint, darkened by the mesh's baked occlusion (Occlusion, Cavity). Where Snow is 1, snow
    lies on the faces that look up, in world-space patches with crisp edges that follow the placed park."""
    name = 'M_CP_' + kind; path = ROOT + '/Materials/' + name
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

    white = unreal.load_asset('/Engine/EngineResources/WhiteSquareTexture')
    tint = node(unreal.MaterialExpressionVectorParameter, parameter_name='Tint', default_value=unreal.LinearColor(1, 1, 1, 1))
    snow = node(unreal.MaterialExpressionScalarParameter, parameter_name='Snow', default_value=0.)
    normal = node(unreal.MaterialExpressionVertexNormalWS); world = node(unreal.MaterialExpressionWorldPosition)
    colour = tint
    if kind == 'Textured':
        sample = node(unreal.MaterialExpressionTextureSampleParameter2D, parameter_name='Base', texture=white)
        colour = node(unreal.MaterialExpressionMultiply)
        MEL.connect_material_expressions(sample, 'RGB', colour, 'A'); MEL.connect_material_expressions(tint, '', colour, 'B')
    elif kind == 'World':
        texture = node(unreal.MaterialExpressionTextureObjectParameter, parameter_name='Base', texture=white)
        metres = node(unreal.MaterialExpressionScalarParameter, parameter_name='Metres', default_value=8.)
        colour = custom('float3 w=pow(abs(N),4.);w/=w.x+w.y+w.z;float3 p=W/(M*100.);'
                        'float3 c=Texture2DSample(Tex,TexSampler,p.yz).rgb*w.x+Texture2DSample(Tex,TexSampler,p.xz).rgb*w.y'
                        '+Texture2DSample(Tex,TexSampler,p.xy).rgb*w.z;return c*T;',
                        {'Tex': (texture, ''), 'M': (metres, ''), 'N': (normal, ''), 'W': (world, ''), 'T': (tint, '')})
    # The occlusion is stored sRGB-encoded (FBX colors_type SRGB, as the skate park's vertex colours).
    ao = custom('return V<=.04045?V/12.92:pow((V+.055)/1.055,2.4);', {'V': (node(unreal.MaterialExpressionVertexColor), 'R')},
                unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    occlusion = node(unreal.MaterialExpressionScalarParameter, parameter_name='Occlusion', default_value=OCCLUSION)
    cavity = node(unreal.MaterialExpressionScalarParameter, parameter_name='Cavity', default_value=CAVITY)
    inputs = {'B': (colour, ''), 'S': (snow, ''), 'N': (normal, ''), 'W': (world, ''), 'A': (ao, ''), 'C': (cavity, '')}
    # Snow lies on the hillside's flatter tops and benches; its steeper sides (over about 33 degrees) show the volcanic
    # ground in bands, as the targets' outcrops. Patterned holes (world-space sines) read as spots and dashes across the
    # banks; a soft ramp left the dark ground smeared through.
    # Smooth value noise (about 26 m and 9 m) leaves a little under half the flat ground bare in broad patches, so the
    # block never reads as a white sheet (sine patterns read as spots).
    noise = ''.join('float2 q{k}=W.xy/{s}.+{o};float2 i{k}=floor(q{k});float2 f{k}=frac(q{k});f{k}=f{k}*f{k}*(3-2*f{k});'
                    'float4 h{k}=frac(sin(float4(dot(i{k},float2(127.1,311.7)),dot(i{k}+float2(1,0),float2(127.1,311.7)),'
                    'dot(i{k}+float2(0,1),float2(127.1,311.7)),dot(i{k}+float2(1,1),float2(127.1,311.7))))*43758.5453);'
                    'float v{k}=lerp(lerp(h{k}.x,h{k}.y,f{k}.x),lerp(h{k}.z,h{k}.w,f{k}.x),f{k}.y);'.format(k=k, s=s, o=o)
                    for k, s, o in ((0, 2600, .17), (1, 900, .61)))
    cover = noise + 'float m=S*saturate((N.z-.84)/.06)*saturate(((v0+.5*v1)/1.5-.42)/.12);'
    base = custom(cover + 'return lerp(B*lerp(1.,A,C),float3(.80,.83,.88),m);', inputs)
    shade = custom('return lerp(1.,A,K);', {'A': (ao, ''), 'K': (occlusion, '')}, unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    rough = custom(cover + 'return lerp(%.2f,.6,m);' % ROUGHNESS, inputs, unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    specular = custom(cover + 'return lerp(0.,.35,m);', inputs, unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    dark = node(unreal.MaterialExpressionConstant3Vector, constant=unreal.LinearColor(0., 0., 0., 1.))
    for n, prop in ((base, unreal.MaterialProperty.MP_BASE_COLOR), (rough, unreal.MaterialProperty.MP_ROUGHNESS),
                    (specular, unreal.MaterialProperty.MP_SPECULAR), (dark, unreal.MaterialProperty.MP_EMISSIVE_COLOR),
                    (shade, unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)):
        assert MEL.connect_material_property(n, '', prop)
    MEL.layout_material_expressions(m); MEL.recompile_material(m); E.save_loaded_asset(m)
    return m


def materials():
    """One instance per source material, with the restyled textures (tools/craterpark_textures.py finish): a painted
    texture on its own UVs, or a world-aligned one for the untextured hillside, foundations, bridges and edge guard."""
    restyle = json.loads((RESTYLE / 'textures.json').read_text())
    parents = {kind: parent(kind) for kind in ('Textured', 'World', 'Flat')}
    result = {}
    for spec in json.loads((SOURCE / 'materials.json').read_text()):
        name = 'MI_CP_' + spec['id']; dest = ROOT + '/Materials'; path = dest + '/' + name
        mi = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, dest, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        painted = restyle['textures'].get(spec['texture']) if spec['texture'] else None
        aligned = restyle.get('world_aligned', {}).get(spec['id'])
        kind = 'Textured' if painted else 'World' if aligned else 'Flat'
        MEL.set_material_instance_parent(mi, parents[kind])
        entry = painted or aligned
        if entry:
            assert megapark.sha(RESTYLE / entry['png']) == entry['sha256'], entry['png']
            texture = megapark.texture(RESTYLE / entry['png'], 'T_CP_' + Path(entry['png']).stem, dest=ROOT + '/Textures', wrap=True)
            MEL.set_material_instance_texture_parameter_value(mi, 'Base', texture)
        if aligned:
            MEL.set_material_instance_scalar_parameter_value(mi, 'Metres', float(aligned['metres']))
        # The restyled images carry their colour, already an albedo for the island's light (craterpark_textures.py
        # palette means); a flat material keeps the source's sRGB base colour.
        colour = [1., 1., 1.] if entry else spec['baseColor']
        tint = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in colour]
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
    # The drawn meshes carry their baked occlusion as vertex colour (build.py ao); the collision needs none.
    plain = megapark.import_mesh
    megapark.import_mesh = lambda path, name, dest=None, seed=None, vertex_colors=False: plain(
        path, name, dest, seed, vertex_colors or name.startswith('SM_CP_'))
    E.make_directory(ROOT + '/Meshes')
    mis = materials(); results = []
    # The riding collision is placed in a throwaway level, so the editor cooks it here into the shared cache instead of
    # the game cooking about 600k triangles as the island loads (over the memory guard).
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assert unreal.EditorLoadingAndSavingUtils.new_blank_map(False), 'Could not open a scratch level'
    for entry in report['render'] + report['collision']:
        collision = entry['name'].startswith('UC_')
        megapark.mesh_actor(entry, collision, mis, actors, editor, results, place=collision)
        if not collision:
            # Only the riding collision is read on the CPU (the skating snapshot); the drawn meshes keep no CPU copy.
            mesh = E.load_asset(ROOT + '/Meshes/' + entry['name'])
            mesh.set_editor_property('allow_cpu_access', False); E.save_loaded_asset(mesh)
    E.save_directory(ROOT, only_if_is_dirty=True, recursive=True)
    result = {'root': ROOT, 'source_sha256': report['scene_sha256'], 'meshes': results, 'materials': len(mis),
              'render_triangles': sum(e['triangles'] for e in results if not e['collision']),
              'collision_triangles': sum(e['triangles'] for e in results if e['collision'])}
    (OUT / 'import-report.json').write_text(json.dumps(result, indent=2) + '\n')
    print('CRATERPARK IMPORT COMPLETE', result['render_triangles'], result['collision_triangles'], flush=True)


if __name__ == '__main__': main()
