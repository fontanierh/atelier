"""Tree house meshes, textures and props into the game (29 Sep 2026).

- Textures from build/yorimichi/treehouse/textures (tools/treehouse_textures.py finish) become T_TH_<slug>.
- M_TreeHouse: the village material's look (distance haze, matte, cloth wind from vertex alpha), with the palette in sRGB
  with a texture: base colour = vertex colour x texture x Gain, so a surface's neutral detail map (Gain 2) keeps the
  calibrated palette and a picture's Gain sets its brightness. Glow lights paper from inside.
- One instance MI_TH_<slot> per material slot the build uses (slot name = texture slug), and one per prop.
- TH_Structure and TH_Trunks use their own triangles as collision; TH_Dressing has none. Props (build/yorimichi/treehouse/props,
  world/regions/treehouse/props.py) get their UCX boxes, if any.
Writes build/yorimichi/treehouse/import-report.json.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json, runpy
from pathlib import Path
import unreal
HERE = Path(__file__).resolve().parent
helper = runpy.run_path(str(HERE/'import_village.py'))
E = unreal.EditorAssetLibrary; MEL = unreal.MaterialEditingLibrary; AT = unreal.AssetToolsHelpers.get_asset_tools()
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
OUT = yori.OUT/'treehouse'; TEX = '/Game/Japan/Treehouse/Textures'; MAT = '/Game/Japan/Treehouse/Materials'
GLOW = {'paper': 3., 'glass': .3, 'noren_cream': .05}   # paper is only lanterns now


# The legacy FBX factory opens the Message Log when a NEW mesh has a build warning, which crashes a commandlet; an
# existing asset takes the reimport path. So a new mesh is first created from a small placeholder that builds cleanly.
PLACEHOLDER = yori.OUT/'village'/'assets'/'Village_Sign.fbx'


def import_mesh(path, dest, name):
    if not E.does_asset_exist(f'{dest}/{name}'): helper['import_mesh'](PLACEHOLDER, dest, name)
    return helper['import_mesh'](path, dest, name)


def texture(path, name):
    task = unreal.AssetImportTask(); task.filename = str(path); task.destination_path = TEX; task.destination_name = name
    task.automated = True; task.replace_existing = True; task.save = True
    AT.import_asset_tasks([task])
    tex = E.load_asset(f'{TEX}/{name}'); assert tex, path
    tex.set_editor_property('srgb', True)
    tex.set_editor_property('max_texture_size', 1024)
    tex.set_editor_property('lod_group', unreal.TextureGroup.TEXTUREGROUP_WORLD)
    E.save_loaded_asset(tex)
    return tex


def parent(default):
    path = MAT+'/M_TreeHouse'
    m = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset('M_TreeHouse', MAT, unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(m)

    def node(cls, x, y, **kw):
        e = MEL.create_material_expression(m, cls, x, y)
        for k, v in kw.items(): e.set_editor_property(k, v)
        return e

    def link(a, ao, b, bi): assert MEL.connect_material_expressions(a, ao, b, bi), (ao, bi)

    def custom(x, y, code, names, kind=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
        n = node(unreal.MaterialExpressionCustom, x, y, code=code, output_type=kind)
        args = []
        for k in names:
            a = unreal.CustomInput(); a.set_editor_property('input_name', k); args.append(a)
        n.set_editor_property('inputs', args)
        return n
    vc = node(unreal.MaterialExpressionVertexColor, -900, 0)
    tex = node(unreal.MaterialExpressionTextureSampleParameter2D, -900, 200, parameter_name='Tex', texture=default)
    gain = node(unreal.MaterialExpressionScalarParameter, -900, 420, parameter_name='Gain', default_value=2.)
    glow = node(unreal.MaterialExpressionScalarParameter, -900, 520, parameter_name='Glow', default_value=0.)
    # Blender's FBX export already encodes the float vertex colour as sRGB, and the village material decodes that once,
    # so its palette is linear albedo. The tree house palette is sRGB, as picked from the paintings: decode twice.
    base = custom(-550, 100, 'float3 L=lerp(C/12.92,pow((C+0.055)/1.055,2.4),step(0.04045,C));'
                  ' L=lerp(L/12.92,pow((L+0.055)/1.055,2.4),step(0.04045,L)); return L*T*G;', ['C', 'T', 'G'])
    link(vc, '', base, 'C'); link(tex, 'RGB', base, 'T'); link(gain, '', base, 'G')
    depth = node(unreal.MaterialExpressionPixelDepth, -550, 350)
    haze = custom(-300, 350, 'return saturate((D-7000.)/220000.)*.5;', ['D'], unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    link(depth, '', haze, 'D')
    fog = node(unreal.MaterialExpressionConstant3Vector, -300, 480, constant=unreal.LinearColor(.64, .68, .76, 1))
    mix = node(unreal.MaterialExpressionLinearInterpolate, -50, 100)
    link(base, '', mix, 'A'); link(fog, '', mix, 'B'); link(haze, '', mix, 'Alpha')
    assert MEL.connect_material_property(mix, '', unreal.MaterialProperty.MP_BASE_COLOR)
    emit = custom(-50, 350, 'return B*(.06+W);', ['B', 'W']); link(base, '', emit, 'B'); link(glow, '', emit, 'W')
    assert MEL.connect_material_property(emit, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop, v, y in ((unreal.MaterialProperty.MP_ROUGHNESS, 1., 600), (unreal.MaterialProperty.MP_SPECULAR, 0., 700)):
        c = node(unreal.MaterialExpressionConstant, -50, y, r=v); MEL.connect_material_property(c, '', prop)
    wind = custom(-50, 850, 'float phase=T*1.7+P.x*.002+P.y*.003; return float3(sin(phase)*2.2,cos(phase*.81)*1.3,sin(phase*1.3)*.4)*W*W;',
                  ['T', 'P', 'W'])
    t = node(unreal.MaterialExpressionTime, -300, 850); p = node(unreal.MaterialExpressionWorldPosition, -300, 950)
    link(t, '', wind, 'T'); link(p, '', wind, 'P'); link(vc, 'A', wind, 'W')
    assert MEL.connect_material_property(wind, '', unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(m); E.save_loaded_asset(m)
    return m


def instance(name, par, tex, gain, glow=0.):
    path = f'{MAT}/{name}'
    mi = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, MAT, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, par)
    MEL.set_material_instance_texture_parameter_value(mi, 'Tex', tex)
    MEL.set_material_instance_scalar_parameter_value(mi, 'Gain', float(gain))
    MEL.set_material_instance_scalar_parameter_value(mi, 'Glow', float(glow))
    MEL.update_material_instance(mi); E.save_loaded_asset(mi)
    return mi


def assign(mesh, mis, report):
    slots = list(mesh.get_editor_property('static_materials')); used = []
    for i, s in enumerate(slots):
        key = str(s.get_editor_property('material_slot_name')).removeprefix('TH_')
        mi = mis.get(key)
        if mi is None: report.setdefault('missing_slots', []).append(f'{mesh.get_name()}:{key}'); continue
        mesh.set_material(i, mi); used.append(key)
    return used


# Sunlight through the windows (treehouse/build.py sunlight()): additive and unlit, so it only brightens what is behind.
SUN_TINT = (1., .74, .42)      # linear warm gold, the paintings' window light
LIGHT = {'beam': dict(Shape=0., Intensity=.32), 'pool': dict(Shape=1., Intensity=1.3), 'pane': dict(Shape=1., Intensity=.06)}


def light_parent():
    path = MAT+'/M_TH_Light'
    m = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset('M_TH_Light', MAT, unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(m)
    m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property('two_sided', True)
    m.set_editor_property('used_with_instanced_static_meshes', True)     # AJapanWorld draws TH_Dressing as an instance

    def node(cls, x, y, **kw):
        e = MEL.create_material_expression(m, cls, x, y)
        for k, v in kw.items(): e.set_editor_property(k, v)
        return e
    code = ('float2 q=abs(UV*2.0-1.0);'
            ' float facing=pow(abs(dot(normalize(N),normalize(V))),1.5);'
            ' float edge=pow(saturate(sin(3.14159*UV.x)),1.5);'
            ' float beam=facing*edge*lerp(1.0,0.3,saturate(UV.y));'
            ' float d=pow(pow(q.x,4.0)+pow(q.y,4.0),0.25);'
            ' float bars=smoothstep(0.02,0.07,q.x)*smoothstep(0.02,0.07,q.y);'
            ' float pool=smoothstep(0.0,0.55,1.0-d)*lerp(1.0,bars,0.8);'
            ' float near=saturate((D-40.0)/160.0);'
            ' return T*lerp(beam,pool,S)*I*near;')
    c = node(unreal.MaterialExpressionCustom, -400, 0, code=code, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    names = ['T', 'N', 'V', 'UV', 'S', 'I', 'D']; args = []
    for k in names:
        a = unreal.CustomInput(); a.set_editor_property('input_name', k); args.append(a)
    c.set_editor_property('inputs', args)
    tint = node(unreal.MaterialExpressionVectorParameter, -800, 0, parameter_name='Tint', default_value=unreal.LinearColor(*SUN_TINT, 1.))
    src = {'T': (tint, ''), 'N': (node(unreal.MaterialExpressionVertexNormalWS, -800, 200), ''),
           'V': (node(unreal.MaterialExpressionCameraVectorWS, -800, 300), ''),
           'UV': (node(unreal.MaterialExpressionTextureCoordinate, -800, 400), ''),
           'S': (node(unreal.MaterialExpressionScalarParameter, -800, 500, parameter_name='Shape', default_value=0.), ''),
           'I': (node(unreal.MaterialExpressionScalarParameter, -800, 600, parameter_name='Intensity', default_value=.5), ''),
           'D': (node(unreal.MaterialExpressionPixelDepth, -800, 700), '')}
    for k, (e, o) in src.items(): assert MEL.connect_material_expressions(e, o, c, k), k
    assert MEL.connect_material_property(c, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m); E.save_loaded_asset(m)
    mis = {}
    for slot, params in LIGHT.items():
        path = f'{MAT}/MI_TH_{slot}'
        mi = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(f'MI_TH_{slot}', MAT, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, m)
        for k, v in params.items(): MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
        MEL.update_material_instance(mi); E.save_loaded_asset(mi); mis[slot] = mi
    return mis


def trees(report):
    """The tall canopy trees (world/regions/treehouse/trees.py) join the island's foliage: M_Foliage instances keyed by slot
    name, the new atlases with the same alpha-coverage mips as the others, and no collision (their names start with
    Tree, so AJapanWorld also lets the camera through them and sways them)."""
    src = OUT/'trees'; info = json.loads((src/'trees.json').read_text())
    foliage = E.load_asset('/Game/Japan/Materials/M_Foliage'); assert foliage
    for colour in ('crimson', 'amber'):
        task = unreal.AssetImportTask(); task.filename = str(src/f'T_leaf_{colour}.png')
        task.destination_path = '/Game/Japan/Textures'; task.automated = True; task.replace_existing = True; task.save = True
        AT.import_asset_tasks([task])
        t = E.load_asset(f'/Game/Japan/Textures/T_leaf_{colour}'); assert t
        t.set_editor_property('do_scale_mips_for_alpha_coverage', True)
        t.set_editor_property('alpha_coverage_thresholds', unreal.Vector4(0, 0, 0, .4))
        t.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
        E.save_loaded_asset(t)
        path = f'/Game/Japan/Materials/MI_Leaf{colour.title()}'
        mi = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(
            f'MI_Leaf{colour.title()}', '/Game/Japan/Materials', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, foliage); MEL.set_material_instance_texture_parameter_value(mi, 'Tex', t)
        MEL.update_material_instance(mi); E.save_loaded_asset(mi)
    for name, d in info.items():
        # The first import of a new mesh crashes the commandlet, so a missing (or wrongly slotted) tree starts as a copy
        # of the island tree with the same slots and the new FBX is reimported over it.
        path = f'/Game/Japan/Assets/{name}'; want = sorted(['Bark', d['slot']])
        slots = lambda m: sorted(str(s.get_editor_property('imported_material_slot_name')) for s in m.get_editor_property('static_materials'))
        top = lambda m: m.get_bounding_box().max.z / 100          # metres; the tree's crown top from trees.json
        if E.does_asset_exist(path) and (slots(E.load_asset(path)) != want or E.load_asset(path).get_num_lods() != 1): E.delete_asset(path)
        if not E.does_asset_exist(path):
            assert E.duplicate_asset('/Game/Japan/Assets/Tree_Maple_A', path), name
            # The copy keeps the template's far models: drop them (the reimport rebuilds with one).
            E.load_asset(path).set_num_source_models(1)
        mesh = helper['import_mesh'](src/f'{name}.fbx', '/Game/Japan/Assets', name)
        if abs(top(mesh)-d['crown_hi']) > .5:
            # The copy carries the template's Interchange import data, so its first FBX reimport skips the unit
            # conversion (a tree 100 times too small); the second one finds FBX data to update and imports in metres.
            mesh = helper['import_mesh'](src/f'{name}.fbx', '/Game/Japan/Assets', name)
        assert abs(top(mesh)-d['crown_hi']) < .5 and mesh.get_num_lods() == 1, (name, top(mesh), mesh.get_num_lods())
        assert slots(mesh) == want, (name, slots(mesh))
        for i, s in enumerate(mesh.get_editor_property('static_materials')):
            key = str(s.get_editor_property('imported_material_slot_name'))
            mi = E.load_asset(f'/Game/Japan/Materials/MI_{d["leaf"] if key == d["slot"] else key}'); assert mi, key
            mesh.set_material(i, mi)
        mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        E.save_loaded_asset(mesh)
        report.setdefault('trees', []).append(name)


def main():
    report = {'textures': 0, 'meshes': {}, 'props': {}}
    if (OUT/'trees/trees.json').exists(): trees(report)
    info = json.loads((OUT/'textures/textures.json').read_text()); tex = {}
    for slug in info:
        tex[slug] = texture(OUT/'textures'/f'{slug}.png', f'T_TH_{slug}'); report['textures'] += 1
    par = parent(tex['wood_plank'])
    mis = {slug: instance(f'MI_TH_{slug}', par, tex[slug], d['gain'], GLOW.get(slug, 0.)) for slug, d in info.items()}
    mis.update(light_parent())
    manifest = json.loads((OUT/'manifest.json').read_text())
    for name, solid in (('TH_Structure', True), ('TH_Trunks', True), ('TH_Dressing', False)):
        # A reimport keeps the old material slot list, so faces of a new material land in a stale slot:
        # start the asset afresh whenever the build's slots changed.
        path = f'/Game/Japan/Assets/{name}'
        if E.does_asset_exist(path):
            old = sorted(str(s.get_editor_property('material_slot_name')).removeprefix('TH_')
                         for s in E.load_asset(path).get_editor_property('static_materials'))
            if old != sorted(manifest[name]['slots']):
                E.delete_asset(path); report.setdefault('fresh', []).append(name)
        mesh = import_mesh(OUT/'assets'/f'{name}.fbx', '/Game/Japan/Assets', name)
        used = assign(mesh, mis, report)
        flag = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if solid else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX
        mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag', flag)
        E.save_loaded_asset(mesh)
        report['meshes'][name] = {'slots': used, 'collision': 'complex' if solid else 'none'}
    props = OUT/'props/props.json'
    if props.exists():
        for key, d in json.loads(props.read_text()).items():
            t = texture(OUT/'props'/f'{key}.png', f'T_{key}')
            mi = instance(f'MI_{key}', par, t, d['gain'], d.get('glow', 0.))
            mesh = import_mesh(OUT/'props'/f'{key}.fbx', '/Game/Japan/Assets', key)
            for i in range(len(mesh.get_editor_property('static_materials'))): mesh.set_material(i, mi)
            flag = unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX
            mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag', flag)
            E.save_loaded_asset(mesh)
            report['props'][key] = {'gain': d['gain'], 'boxes': d.get('boxes', 0)}
    (OUT/'import-report.json').write_text(json.dumps(report, indent=2)+'\n')
    unreal.log('TREEHOUSE IMPORT COMPLETE')


main()
