"""M_HDCity, the textured material of Hidamari's buildings, streets and ground, and its instance per surface.

The world build gives every face of a textured city mesh a material slot named HDS_<slug> after the surface it is
made of, and UVs in metres (world/regions/hidamari/surfaces.py). The surfaces are Sunburst paintings turned into
neutral detail maps (tools/hidamari_textures.py: linear colour over its own mean, at half). The vertex colour, the
game's calibrated palette, times 2 x the detail gives the surface its colour. A second sample, turned and five times
larger, and a slow world-space variation keep large surfaces (ground, streets, long walls) from repeating. The
paper-lamp, canvas, leaf and shop-window glows are M_Arcade's (arcade_material.py), keyed on the vertex colour. The
haze is shared with the sea and the land (atmosphere.py).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
import unreal
import atmosphere

E = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
SRC = yori.OUT / 'hidamari' / 'textures'
TEX = '/Game/Japan/Hidamari/Textures'
MAT = '/Game/Japan/Hidamari/Materials'
# Detail strength and slow variation per surface (default 1 and .5): the ground varies most, the glows not at all.
STRENGTH = {'flat': 0., 'paint': .7, 'roof': .8, 'metal': .8}
PROP_MACRO = 0.   # a Tripo atlas must not be sampled turned
MACRO = {'grass': 1., 'earth': 1., 'moss': 1., 'flagstone': .8, 'sidewalk': .6, 'asphalt': .6, 'gravel': .6,
         'flat': 0.}


def texture(slug, source=None, name=None):
    name = name or f'T_HD_{slug}'
    task = unreal.AssetImportTask(); task.filename = str(source or SRC / f'{slug}.png'); task.destination_path = TEX
    task.destination_name = name; task.automated = True; task.replace_existing = True; task.save = True
    AT.import_asset_tasks([task])
    tex = E.load_asset(f'{TEX}/{name}'); assert tex, slug
    tex.set_editor_property('srgb', True)
    tex.set_editor_property('max_texture_size', 1024)
    tex.set_editor_property('lod_group', unreal.TextureGroup.TEXTUREGROUP_WORLD)
    E.save_loaded_asset(tex)
    return tex


def parent(default):
    path = MAT + '/M_HDCity'
    m = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset('M_HDCity', MAT, unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(m)

    def node(cls, x, y, **kw):
        e = MEL.create_material_expression(m, cls, x, y)
        for k, v in kw.items(): e.set_editor_property(k, v)
        return e

    def custom(x, y, code, inputs):
        n = node(unreal.MaterialExpressionCustom, x, y, code=code, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        args = []
        for name, _, _ in inputs:
            a = unreal.CustomInput(); a.set_editor_property('input_name', name); args.append(a)
        n.set_editor_property('inputs', args)
        for name, src, out in inputs: assert MEL.connect_material_expressions(src, out, n, name), name
        return n
    vc = node(unreal.MaterialExpressionVertexColor, -900, 0)
    uv = node(unreal.MaterialExpressionTextureCoordinate, -900, 150)
    pos = node(unreal.MaterialExpressionWorldPosition, -900, 250)
    tex = node(unreal.MaterialExpressionTextureObjectParameter, -900, 350, parameter_name='Tex', texture=default)
    tile = node(unreal.MaterialExpressionScalarParameter, -900, 500, parameter_name='Tile', default_value=1.5)
    strength = node(unreal.MaterialExpressionScalarParameter, -900, 600, parameter_name='Strength', default_value=1.)
    macro = node(unreal.MaterialExpressionScalarParameter, -900, 700, parameter_name='Macro', default_value=.5)
    gain = node(unreal.MaterialExpressionScalarParameter, -900, 800, parameter_name='Gain', default_value=1.)
    base = custom(-450, 0, '''
float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));
float2 p=UV/Tile;
float3 a=Texture2DSample(Tex,TexSampler,p).rgb*2;
float3 b=Texture2DSample(Tex,TexSampler,float2(p.x*.8-p.y*.6,p.x*.6+p.y*.8)*.2+.37).rgb*2;
float3 d=a*lerp(1,b,.35*Macro);
float2 w=P.xy*.0001;   // metres / 100
float n=sin(w.x*3.1+sin(w.y*2.3)*1.7)*sin(w.y*2.7+sin(w.x*1.9)*1.3)+.5*sin(w.x*7.3-w.y*6.1);
return L*lerp(1,d,Strength)*(1+.11*Macro*n)*Gain;
''', [('C', vc, ''), ('UV', uv, ''), ('P', pos, ''), ('Tex', tex, ''), ('Tile', tile, ''), ('Strength', strength, ''),
      ('Macro', macro, ''), ('Gain', gain, '')])
    # M_Arcade's glows, keyed on the (linear) vertex colour and applied to the textured colour
    glow = custom(-200, 300, '''
float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));
float lamp=step(.82,L.r)*step(.45,L.g)*step(L.g,.68)*step(L.b,.30);
float canvas=step(.70,L.r)*step(L.r,.79)*step(.55,L.g)*step(.35,L.b);
float leaf=step(.4,L.r)*step(.24,L.g)*step(L.b,.07);
float shop=step(.18,L.r)*step(L.r,.22)*step(.08,L.g)*step(L.g,.11)*step(.02,L.b)*step(L.b,.04);
return B*(.045+lamp*.9+canvas*.20+leaf*.38+shop*.15);
''', [('C', vc, ''), ('B', base, '')])
    b, g = atmosphere.apply(m, base, glow, x=50, y=0)
    assert MEL.connect_material_property(b, '', unreal.MaterialProperty.MP_BASE_COLOR)
    assert MEL.connect_material_property(g, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop, value, y in ((unreal.MaterialProperty.MP_ROUGHNESS, .87, 600), (unreal.MaterialProperty.MP_SPECULAR, .12, 700)):
        c = node(unreal.MaterialExpressionConstant, 50, y, r=value); MEL.connect_material_property(c, '', prop)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(m); E.save_loaded_asset(m)
    return m


def instance(par, slug, tex, tile, gain=1., name=None):
    name = name or f'MI_HD_{slug}'; path = f'{MAT}/{name}'
    mi = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, MAT, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, par)
    MEL.set_material_instance_texture_parameter_value(mi, 'Tex', tex)
    MEL.set_material_instance_scalar_parameter_value(mi, 'Tile', float(tile))
    MEL.set_material_instance_scalar_parameter_value(mi, 'Strength', float(STRENGTH.get(slug, 1.)))
    MEL.set_material_instance_scalar_parameter_value(mi, 'Macro', float(MACRO.get(slug, .5)))
    MEL.set_material_instance_scalar_parameter_value(mi, 'Gain', float(gain))
    MEL.update_material_instance(mi); E.save_loaded_asset(mi)
    return mi


def materials():
    """{slug: material instance}, 'flat' (the vertex colour alone) included."""
    info = json.loads((SRC / 'textures.json').read_text())
    tex = {slug: texture(slug) for slug in info}
    par = parent(tex.get('plaster') or next(iter(tex.values())))
    mis = {slug: instance(par, slug, tex[slug], d['tile_m']) for slug, d in info.items()}
    mis['flat'] = instance(par, 'flat', tex.get('plaster') or next(iter(tex.values())), 1.)
    mis['_parent'] = par
    return mis


def prop_materials(par, report):
    """MI_HD_P_<slug> for every fitted Tripo prop (world/regions/hidamari/props.py): its own texture, at Tile 1 on its
    atlas UVs, at its gain (the material doubles the texture, as for a detail map)."""
    path = yori.OUT / 'hidamari' / 'props' / 'props.json'
    if not path.exists(): return {}
    mis = {}
    for key, info in json.loads(path.read_text()).items():
        tex = texture(key, path.parent / f'{key}.png', f'T_{key}')
        mi = instance(par, key, tex, 1., info['gain'] / 2, name=f'MI_{key}')
        MEL.set_material_instance_scalar_parameter_value(mi, 'Macro', PROP_MACRO); MEL.update_material_instance(mi)
        E.save_loaded_asset(mi); mis[key] = mi
    report['props'] = sorted(mis)
    return mis
