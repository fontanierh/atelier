"""Import Brinecove (world/regions/brinecove/build.py) into its own /Game/Brinecove library.

Geometry keeps its local metre frame and material slots; each slot gets a region material instance. Three parents
share the island's haze (atmosphere.py): opaque painted surfaces, two-sided masked cards (leaves, palm fronds, the
scrolling waterfall curtain, foam lace) and soft translucent spray. Solid meshes collide with their own triangles;
foliage prototypes get generated LODs.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori  # noqa: E402
import json
import unreal
from atelier.native_protocol import native_context
from atelier import native_membership
from atelier.unreal_mesh_reuse import AssetGroup, MeshReuse, lods_match, set_if_changed
import atmosphere
import glb_mesh_validation

OUT = yori.OUT / 'brinecove'
ROOT = '/Game/Brinecove'
E = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
REGISTRY = unreal.AssetRegistryHelpers.get_asset_registry()
PARENTS = {'opaque': 'M_Brinecove', 'emissive': 'M_Brinecove', 'masked': 'M_BrinecoveMasked',
           'translucent': 'M_BrinecoveSpray', 'terrain': 'M_BrinecoveTerrain'}
MOTION = ('Drift', 'Wash', 'Layer')


def parent(name, blend):
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

    uv = node(unreal.MaterialExpressionTextureCoordinate)
    time = node(unreal.MaterialExpressionTime)
    tex = node(unreal.MaterialExpressionTextureObjectParameter, parameter_name='Tex',
               texture=E.load_asset('/Engine/EngineResources/WhiteSquareTexture'))
    colour = node(unreal.MaterialExpressionVectorParameter, parameter_name='Colour', default_value=unreal.LinearColor(.7, .6, .4, 1.))
    inputs = [('UV', uv, ''), ('T', time, ''), ('Tex', tex, ''), ('Colour', colour, ''), ('UseTex', scalar('UseTex', 0.), ''),
              ('Pan', scalar('Pan', 0.), '')]
    if blend == 'masked':
        inputs += [(key, scalar(key, 0.), '') for key in MOTION]

    def custom(code, kind):
        result = node(unreal.MaterialExpressionCustom, output_type=kind, code=code)
        args = []
        for key, _, _ in inputs:
            value = unreal.CustomInput()
            value.set_editor_property('input_name', key)
            args.append(value)
        result.set_editor_property('inputs', args)
        for key, expression, output in inputs:
            assert MEL.connect_material_expressions(expression, output, result, key), key
        return result

    sample = 'float4 s = Texture2DSample(Tex, TexSampler, UV + float2(0, frac(T * Pan)));\n'
    wash = ''
    if blend == 'masked':
        # Water motion: Layer adds a second, faster streak layer (the waterfall); Drift slides the lace along u and
        # Wash breathes the outer edge of a foam band (v 0 at the shore, 1 offshore) in and out with time.
        sample = ('float4 s = Texture2DSample(Tex, TexSampler, UV + float2(frac(T * Drift), frac(T * Pan)));\n'
                  'float4 s2 = Texture2DSample(Tex, TexSampler, UV * float2(0.71, 1.0) + float2(0.37, frac(T * Pan * 1.47)));\n'
                  's = lerp(s, max(s, s2), Layer);\n')
        wash = (' * lerp(1, (1 - smoothstep(0.5 + Wash * sin(T * 0.9 + UV.x * 1.7), 1.0, UV.y))'
                ' * (0.75 + 0.25 * sin(T * 1.3 + UV.x * 0.6)), step(0.001, Wash))')
    base = custom(sample + 'return lerp(Colour.rgb, s.rgb, UseTex);', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    glow = node(unreal.MaterialExpressionMultiply)
    assert MEL.connect_material_expressions(base, '', glow, 'A')
    assert MEL.connect_material_expressions(scalar('Glow', .045), '', glow, 'B')
    shaded, emission = atmosphere.apply(material, base, glow)
    assert MEL.connect_material_property(shaded, '', unreal.MaterialProperty.MP_BASE_COLOR)
    assert MEL.connect_material_property(emission, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    assert MEL.connect_material_property(scalar('Roughness', .88), '', unreal.MaterialProperty.MP_ROUGHNESS)
    assert MEL.connect_material_property(scalar('Metallic', 0.), '', unreal.MaterialProperty.MP_METALLIC)
    assert MEL.connect_material_property(scalar('Specular', .12), '', unreal.MaterialProperty.MP_SPECULAR)
    if blend != 'opaque':
        alpha = custom(sample + 'return lerp(1, s.a, UseTex)' + wash + ';', unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        material.set_editor_property('two_sided', True)
        if blend == 'masked':
            material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
            material.set_editor_property('opacity_mask_clip_value', .45)
            assert MEL.connect_material_property(alpha, '', unreal.MaterialProperty.MP_OPACITY_MASK)
        else:
            material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_TRANSLUCENT)
            fade = node(unreal.MaterialExpressionMultiply)
            assert MEL.connect_material_expressions(alpha, '', fade, 'A')
            assert MEL.connect_material_expressions(scalar('Opacity', .8), '', fade, 'B')
            assert MEL.connect_material_property(fade, '', unreal.MaterialProperty.MP_OPACITY)
    material.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(material)
    E.save_loaded_asset(material)
    return material


# Natural ground and rock in world space (metres): weights from height above the sea, slope and two value noises.
TERRAIN_WEIGHTS = """
float3 p = WP / 100.0;
float3 n = normalize(N);
float h = p.z - SeaZ / 100.0;
float slope = 1.0 - saturate(n.z);
float2 q = p.xy / 37.0; float2 i0 = floor(q); float2 f = frac(q); f = f * f * (3.0 - 2.0 * f);
float h00 = frac(sin(dot(i0, float2(127.1, 311.7))) * 43758.5453);
float h10 = frac(sin(dot(i0 + float2(1, 0), float2(127.1, 311.7))) * 43758.5453);
float h01 = frac(sin(dot(i0 + float2(0, 1), float2(127.1, 311.7))) * 43758.5453);
float h11 = frac(sin(dot(i0 + float2(1, 1), float2(127.1, 311.7))) * 43758.5453);
float n1 = lerp(lerp(h00, h10, f.x), lerp(h01, h11, f.x), f.y);
q = p.xy / 9.0; i0 = floor(q); f = frac(q); f = f * f * (3.0 - 2.0 * f);
h00 = frac(sin(dot(i0, float2(269.5, 183.3))) * 43758.5453);
h10 = frac(sin(dot(i0 + float2(1, 0), float2(269.5, 183.3))) * 43758.5453);
h01 = frac(sin(dot(i0 + float2(0, 1), float2(269.5, 183.3))) * 43758.5453);
h11 = frac(sin(dot(i0 + float2(1, 1), float2(269.5, 183.3))) * 43758.5453);
float n2 = lerp(lerp(h00, h10, f.x), lerp(h01, h11, f.x), f.y);
// High ground turns to rock on gentler slopes, so the backdrop ridge reads as one cliff face behind its outcrops.
float rockAt = lerp(0.36, 0.1, smoothstep(28.0, 45.0, h));  // ~40 degree ridge faces turn rock, 20 degree meadows stay
float rock = max(smoothstep(rockAt, rockAt + 0.16, slope + (n2 - 0.5) * 0.14), RockOnly);
float sand = (1.0 - smoothstep(1.1, 2.7, h + (n2 - 0.5) * 1.8)) * (1.0 - smoothstep(0.3, 0.55, slope)) * (1.0 - rock);
float green = (1.0 - rock) * (1.0 - sand);
float forest = smoothstep(0.3, 0.74, n1 + (n2 - 0.5) * 0.45) * 0.85;
float wF = green * forest, wM = green * (1.0 - forest), wS = sand, wR = rock;
float3 bw = pow(abs(n), 4.0); bw /= (bw.x + bw.y + bw.z);
float2 uS = p.xy / 4.0, uM = p.xy / 3.5, uF = p.xy / 4.5;
"""


def terrain_parent():
    """Sand, meadow, forest floor and rock blended per pixel, so shores and slopes change without cell edges.

    Flat layers project from above; rock projects on all three axes, so cliffs and rock meshes need no UVs and never
    stretch. Each layer's normal map (RGB) and cavity (A) drive the world-space normal and ambient occlusion only:
    the paintings already carry their own soft shading, so nothing darkens the base colour a second time. The
    meadow print is softened toward its own mean colour, so the standing groundcover carries the plant detail."""
    name = PARENTS['terrain']
    asset = ROOT + '/Materials/' + name
    material = E.load_asset(asset) if E.does_asset_exist(asset) else AT.create_asset(name, ROOT + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(material)

    def node(cls, **properties):
        result = MEL.create_material_expression(material, cls)
        for key, value in properties.items():
            result.set_editor_property(key, value)
        return result

    white = E.load_asset('/Engine/EngineResources/WhiteSquareTexture')
    inputs = [('WP', node(unreal.MaterialExpressionWorldPosition)), ('N', node(unreal.MaterialExpressionVertexNormalWS)),
              ('SeaZ', node(unreal.MaterialExpressionScalarParameter, parameter_name='SeaZ', default_value=0.)),
              ('RockOnly', node(unreal.MaterialExpressionScalarParameter, parameter_name='RockOnly', default_value=0.)),
              ('Tint', node(unreal.MaterialExpressionVectorParameter, parameter_name='Colour', default_value=unreal.LinearColor(1., 1., 1., 1.))),
              ('Cam', node(unreal.MaterialExpressionCameraPositionWS))]
    for layer in ('Sand', 'Meadow', 'Forest', 'Rock'):
        for key in (layer, layer + 'N'):
            inputs.append((key, node(unreal.MaterialExpressionTextureObjectParameter, parameter_name=key, texture=white)))

    def custom(code, kind):
        result = node(unreal.MaterialExpressionCustom, output_type=kind, code=TERRAIN_WEIGHTS + code)
        args = []
        for key, _ in inputs:
            value = unreal.CustomInput()
            value.set_editor_property('input_name', key)
            args.append(value)
        result.set_editor_property('inputs', args)
        for key, expression in inputs:
            assert MEL.connect_material_expressions(expression, '', result, key), key
        return result

    base = custom("""
float3 cS = Texture2DSample(Sand, SandSampler, uS).rgb * lerp(1.0, 0.72, 1.0 - smoothstep(0.2, 0.9, h));
float3 cM = Texture2DSample(Meadow, MeadowSampler, uM).rgb;
cM = lerp(Texture2DSampleLevel(Meadow, MeadowSampler, uM, 12).rgb, cM, 0.55);
float3 cF = Texture2DSample(Forest, ForestSampler, uF).rgb;
float3 cR = Texture2DSample(Rock, RockSampler, p.yz / 6.0).rgb * bw.x + Texture2DSample(Rock, RockSampler, p.xz / 6.0).rgb * bw.y
          + Texture2DSample(Rock, RockSampler, p.xy / 6.0).rgb * bw.z;
// Distant cliffs showed the 6 m rock print as wallpaper stripes (playtest note 1, 192 m away). Far away a second,
// rotated print at 23 m takes over half the colour, and a triplanar macro noise at 41 m and 13 m breaks the value
// and hue in broad patches; the xy-only noises above ran straight down a cliff face as vertical streaks.
float far = smoothstep(35.0, 150.0, length(WP - Cam) / 100.0);
float2 rq = float2(0.8, 0.6);
float3 cR2 = Texture2DSample(Rock, RockSampler, float2(dot(p.yz, rq), dot(p.yz, float2(-rq.y, rq.x))) / 23.0 + 0.37).rgb * bw.x
           + Texture2DSample(Rock, RockSampler, float2(dot(p.xz, rq), dot(p.xz, float2(-rq.y, rq.x))) / 23.0 + 0.61).rgb * bw.y
           + Texture2DSample(Rock, RockSampler, float2(dot(p.xy, rq), dot(p.xy, float2(-rq.y, rq.x))) / 23.0 + 0.13).rgb * bw.z;
cR = lerp(cR, cR * 0.45 + cR2 * 0.55, 0.15 + 0.6 * far);
float2 planes[3] = { p.yz, p.xz, p.xy };
float wts[3] = { bw.x, bw.y, bw.z };
float macro = 0.0;
for (int k = 0; k < 3; k++) {
    for (int o = 0; o < 2; o++) {
        float2 mq = planes[k] / (o == 0 ? 41.0 : 13.0) + float(o) * 7.3;
        float2 mi = floor(mq); float2 mf = frac(mq); mf = mf * mf * (3.0 - 2.0 * mf);
        float a = frac(sin(dot(mi, float2(41.3, 289.1))) * 43758.5453);
        float b = frac(sin(dot(mi + float2(1, 0), float2(41.3, 289.1))) * 43758.5453);
        float c0 = frac(sin(dot(mi + float2(0, 1), float2(41.3, 289.1))) * 43758.5453);
        float d = frac(sin(dot(mi + float2(1, 1), float2(41.3, 289.1))) * 43758.5453);
        macro += wts[k] * (o == 0 ? 0.65 : 0.35) * lerp(lerp(a, b, mf.x), lerp(c0, d, mf.x), mf.y);
    }
}
float3 breakup = lerp(float3(0.84, 0.86, 0.9), float3(1.1, 1.04, 0.95), macro);
cR *= lerp(float3(1, 1, 1), breakup, 0.55 + 0.45 * far);
float3 c = wS * cS + wM * cM + wF * cF + wR * cR * Tint.rgb;
return c * lerp(0.88, 1.08, n1);
""", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    shading = custom("""
float4 tS = Texture2DSample(SandN, SandNSampler, uS); float4 tM = Texture2DSample(MeadowN, MeadowNSampler, uM);
float4 tF = Texture2DSample(ForestN, ForestNSampler, uF);
float4 rx = Texture2DSample(RockN, RockNSampler, p.yz / 6.0); float4 ry = Texture2DSample(RockN, RockNSampler, p.xz / 6.0);
float4 rz = Texture2DSample(RockN, RockNSampler, p.xy / 6.0);
float2 flat2 = (tS.xy * 2 - 1) * wS + (tM.xy * 2 - 1) * wM * 0.6 + (tF.xy * 2 - 1) * wF;
float3 rockN = bw.x * float3(0, rx.x * 2 - 1, rx.y * 2 - 1) + bw.y * float3(ry.x * 2 - 1, 0, ry.y * 2 - 1)
             + bw.z * float3(rz.x * 2 - 1, rz.y * 2 - 1, 0);
float3 world = normalize(n + float3(flat2 * 0.8, 0) + rockN * wR * 1.1);
float ao = wS * tS.a + wM * tM.a + wF * tF.a + wR * (rx.a * bw.x + ry.a * bw.y + rz.a * bw.z);
return float4(world, ao);
""", unreal.CustomMaterialOutputType.CMOT_FLOAT4)
    normal = node(unreal.MaterialExpressionComponentMask, r=True, g=True, b=True, a=False)
    occlusion = node(unreal.MaterialExpressionComponentMask, r=False, g=False, b=False, a=True)
    assert MEL.connect_material_expressions(shading, '', normal, '')
    assert MEL.connect_material_expressions(shading, '', occlusion, '')
    glow = node(unreal.MaterialExpressionMultiply)
    assert MEL.connect_material_expressions(base, '', glow, 'A')
    assert MEL.connect_material_expressions(node(unreal.MaterialExpressionConstant, r=.045), '', glow, 'B')
    shaded, emission = atmosphere.apply(material, base, glow)
    material.set_editor_property('tangent_space_normal', False)
    assert MEL.connect_material_property(shaded, '', unreal.MaterialProperty.MP_BASE_COLOR)
    assert MEL.connect_material_property(emission, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    assert MEL.connect_material_property(normal, '', unreal.MaterialProperty.MP_NORMAL)
    assert MEL.connect_material_property(occlusion, '', unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    assert MEL.connect_material_property(node(unreal.MaterialExpressionConstant, r=.9), '', unreal.MaterialProperty.MP_ROUGHNESS)
    assert MEL.connect_material_property(node(unreal.MaterialExpressionConstant, r=.1), '', unreal.MaterialProperty.MP_SPECULAR)
    material.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(material)
    E.save_loaded_asset(material)
    return material


def textures(report):
    result = {}
    files = {entry['texture'] for entry in report['materials'].values() if entry['texture']}
    for entry in report['materials'].values():
        files |= {f for f in list(entry.get('layers', {}).values()) + list(entry.get('normals', {}).values()) if f}
    for file in sorted(files):
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
        # Normal-and-cavity maps are data, not colour.
        asset.set_editor_property('srgb', not name.endswith('_n'))
        asset.set_editor_property('max_texture_size', 1024)
        asset.set_editor_property('lod_group', unreal.TextureGroup.TEXTUREGROUP_WORLD)
        E.save_loaded_asset(asset)
        result[file] = asset
    return result


def surfaces(report, images):
    parents = {kind: parent(name, 'opaque' if kind == 'emissive' else kind) for kind, name in PARENTS.items()
               if kind not in ('emissive', 'terrain')}
    parents['emissive'] = parents['opaque']
    parents['terrain'] = terrain_parent()
    for key, entry in report['materials'].items():
        name = entry['name']
        path = ROOT + '/Materials/' + name
        material = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, ROOT + '/Materials', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        MEL.clear_all_material_instance_parameters(material)
        MEL.set_material_instance_parent(material, parents[entry['kind']])
        MEL.set_material_instance_vector_parameter_value(material, 'Colour', unreal.LinearColor(*entry['colour'][:3], 1.))
        if entry['kind'] == 'terrain':
            MEL.set_material_instance_scalar_parameter_value(material, 'RockOnly', 1. if entry['rock_only'] else 0.)
            for key, file in list(entry['layers'].items()) + list(entry['normals'].items()):
                assert file, (key, 'terrain layer texture')
                MEL.set_material_instance_texture_parameter_value(material, key, images[file])
            MEL.update_material_instance(material)
            E.save_loaded_asset(material)
            continue
        for key, value in entry.get('motion', {}).items():
            MEL.set_material_instance_scalar_parameter_value(material, key, float(value))
        scalars = {'UseTex': float(bool(entry['texture'])), 'Pan': float(entry['pan']), 'Roughness': float(entry['roughness']),
                   'Metallic': .6 if entry['metal'] else 0., 'Glow': 1.6 if entry['kind'] == 'emissive' else .045}
        for parameter, value in scalars.items():
            MEL.set_material_instance_scalar_parameter_value(material, parameter, value)
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


def keep_full_precision_uvs(mesh):
    """Brinecove's faces are box-projected in world metres, so its UVs reach ~650 tiles from the origin. Half-precision
    UVs step by 1/16 to 1/2 of a tile out there: narrow faces such as the terrace stair nosings collapsed to a single
    texel row and showed as streaks (Op410 review). Hidamari and Belmonte import their metre UVs the same way."""
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    assert editor is not None, 'StaticMeshEditor subsystem is unavailable'
    build = editor.get_lod_build_settings(mesh, 0)
    if not build.get_editor_property('use_full_precision_u_vs'):
        build.set_editor_property('use_full_precision_u_vs', True)
        editor.set_lod_build_settings(mesh, 0, build)


def generate_lods(mesh):
    """Three reduced levels for a foliage prototype; cards keep their silhouettes at a distance."""
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    assert editor is not None, 'StaticMeshEditor subsystem is unavailable'
    options = unreal.StaticMeshReductionOptions()
    options.set_editor_property('auto_compute_lod_screen_size', False)
    plan = ((1., 1.), (.45, .3), (.2, .12), (.08, .04))
    levels = []
    for percent, screen in plan:
        level = unreal.StaticMeshReductionSettings()
        level.set_editor_property('percent_triangles', percent)
        level.set_editor_property('screen_size', screen)
        levels.append(level)
    options.set_editor_property('reduction_settings', levels)
    assert editor.set_lods(mesh, options) == len(plan), (mesh.get_name(), 'LOD generation')
    assert editor.set_lod_screen_sizes(mesh, [screen for _, screen in plan]), (mesh.get_name(), 'LOD screen sizes')


def validate_reused_mesh(mesh, entry):
    return glb_mesh_validation.validate_mesh(mesh, OUT / entry['path'], entry, len(entry['slots']),
        out=yori.OUT, tolerance_cm=2., minimum_triangles=.98)


def main():
    report = json.loads((OUT / 'build-report.json').read_text())
    E.make_directory(ROOT)
    previous_meshes = native_membership.inventory(E, ROOT + '/Meshes', 'SM_BC_')
    texture_files = {entry['texture'] for entry in report['materials'].values() if entry['texture']}
    for entry in report['materials'].values():
        texture_files |= {file for file in list(entry.get('layers', {}).values())
                         + list(entry.get('normals', {}).values()) if file}
    texture_files = sorted(texture_files)
    material_packages = sorted({ROOT + '/Materials/' + name for name in list(PARENTS.values())
        + [entry['name'] for entry in report['materials'].values()]}
        | {ROOT + '/Textures/' + Path(file).stem for file in texture_files})
    materials = AssetGroup(native_context(yori.GAME.name), 'unreal.brinecove', __file__,
        ('parent', 'terrain_parent', 'textures', 'surfaces'), parameters=report['materials'],
        sources=[OUT / 'textures' / file for file in texture_files], support=[Path(atmosphere.__file__)])
    if not materials.matches(material_packages):
        surfaces(report, textures(report))
        materials.validated(material_packages)
    reuse = MeshReuse(native_context(yori.GAME.name), 'unreal.brinecove', __file__,
                      ('import_mesh', 'keep_full_precision_uvs', 'generate_lods'),
                      report_member='generated/brinecove/build-report.json',
                      validation_functions=('validate_reused_mesh',))
    def geometry(entry):
        return dict(entry, lods=bool(entry.get('lods')))
    imported = {}
    for index, entry in enumerate(report['meshes']):
        name = entry['name']
        target = ROOT + '/Meshes/' + name
        mesh = reuse.acquire(name, target, geometry=geometry(entry),
                             donor_geometry=lambda saved: next((geometry(row) for row in saved.get('meshes', [])
                                                                if row['name'] == name), None),
                             sources=[(target, OUT / entry['path'], entry['sha256'])],
                             validator=lambda mesh: validate_reused_mesh(mesh, entry))
        reused = mesh is not None
        if mesh is None:
            if E.does_asset_exist(target):
                assert E.delete_asset(target), target
            mesh = import_mesh(OUT / entry['path'], name)
            reuse.imported(name)
        # Foliage prototypes sample an atlas cell (UVs within 0-1) and the terrain material projects by world position;
        # every other surface samples its world-metre UVs.
        if not entry.get('lods') and any(report['materials'][key]['kind'] != 'terrain' for key in entry['slots']):
            keep_full_precision_uvs(mesh)
        slots = mesh.get_editor_property('static_materials')
        assert len(slots) == len(entry['slots']), (name, 'material slots', len(slots), entry['slots'])
        for slot, key in enumerate(entry['slots']):
            material = E.load_asset(f"{ROOT}/Materials/{report['materials'][key]['name']}")
            assert material, key
            if mesh.get_material(slot) != material:
                mesh.set_material(slot, material)
            assert mesh.get_material(slot) == material, (name, 'material binding', slot)
        # Unreal drops a few degenerate slivers from the procedural kit.
        triangles = mesh.get_num_triangles(0)
        assert entry['triangles'] * .98 <= triangles <= entry['triangles'], (name, 'triangle count', triangles, entry['triangles'])
        body = mesh.get_editor_property('body_setup')
        assert body, name
        if entry['collision']:
            set_if_changed(body, 'collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            set_if_changed(body, 'double_sided_geometry', True)
            assert body.get_editor_property('collision_trace_flag') == unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE, name
            assert body.get_editor_property('double_sided_geometry'), name
        if entry.get('lods'):
            plan = ((1., 1.), (.45, .3), (.2, .12), (.08, .04))
            if not reused or not lods_match(mesh, plan):
                generate_lods(mesh)
            assert lods_match(mesh, plan), name
        assert E.save_loaded_asset(mesh, only_if_is_dirty=True), name
        box = mesh.get_bounding_box()
        low, high = entry['bounds_m']
        expected = [low[0] * 100, -high[1] * 100, low[2] * 100, high[0] * 100, -low[1] * 100, high[2] * 100]
        actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
        assert max(abs(a - b) for a, b in zip(actual, expected)) < 2., (name, 'bounds', actual, expected)
        imported[name] = {'triangles': triangles, 'bounds_cm': actual, 'collision': entry['collision']}
        reuse.validated(name)
        unreal.log(f'BRINECOVE IMPORT {index + 1}/{len(report["meshes"])} {name} reused={int(reused)}')
    current_names = [entry['name'] for entry in report['meshes']]
    retired = native_membership.retire(E, previous_meshes, current_names, ROOT + '/Meshes', 'SM_BC_')
    unreal.log(f'NATIVE MEMBERSHIP RETIRED: {len(retired)} superseded packages')
    (OUT / 'import-report.json').write_text(json.dumps(imported, indent=1) + '\n')
    E.delete_directory(ROOT + '/Import')
    reuse.finish()
    unreal.log(f'BRINECOVE IMPORT COMPLETE: {len(imported)} meshes')


main()
