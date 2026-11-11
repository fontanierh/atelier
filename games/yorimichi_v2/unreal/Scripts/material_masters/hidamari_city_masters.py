"""Hidamari city master builder: M_HDCity (city_parent), the textured parent of every Hidamari building, street and ground
material instance.

Extracted from the donor generator games/yorimichi/unreal/Scripts/city_material.py at the V2 source baseline (docs/DECISIONS.md
D01, donor blob sha256 0d7cf543...): city_parent is that file's lines 42-95 (parent). Its expressions, parameter names
(Tex, Tile, Strength, Macro, Gain), values, wiring and order are the donor's. Three things move out of the builder: no asset
is saved (the importer saves the one it accepts, after reading it back), no texture is imported or loaded here (the plaster
texture arrives through `reads`, the donor's `default` argument), and the module-level imports and the per-surface
instances (lines 1-41, 96-134) stay behind. Nothing runs at import: the module is functions only, so it imports without the
Unreal editor, where `unreal` is None and a builder cannot run.

The haze uses the shared master_haze.py implementation, which each record declares and pins beside this builder.
Its donor atmosphere.py and sea_look.py constants and graph are preserved there. The helper is loaded only from the
record's declared sources in the importer's private module namespace.

A builder takes the destination package path, the loaded reads ({package: asset}) and the recipe's arguments as keyword
arguments, and returns the rebuilt material.
"""
from . import master_haze as haze

try:
    import unreal
except ImportError:   # outside the editor: the functions are defined but cannot run
    unreal = None


# --- shared helpers (the same as swordcamp_masters.py) ---------------------------------------------------------------

def _material(package):
    """The material at a package path, reused when it exists (donor: E.load_asset, or AT.create_asset when it does not)."""
    folder, name = package.rsplit('/', 1)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        return unreal.EditorAssetLibrary.load_asset(package)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def _custom_inputs(names):
    """The shared helper builds the donor's ordered CustomInput structs."""
    return haze.custom_inputs(unreal, names)


# --- city_material.py lines 42-95 (parent) ---------------------------------------------------------------------------------

# The surface base (donor lines 68-78) and the glows keyed on the vertex colour (donor lines 80-87), verbatim.
BASE_CODE = '''
float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));
float2 p=UV/Tile;
float3 a=Texture2DSample(Tex,TexSampler,p).rgb*2;
float3 b=Texture2DSample(Tex,TexSampler,float2(p.x*.8-p.y*.6,p.x*.6+p.y*.8)*.2+.37).rgb*2;
float3 d=a*lerp(1,b,.35*Macro);
float2 w=P.xy*.0001;   // metres / 100
float n=sin(w.x*3.1+sin(w.y*2.3)*1.7)*sin(w.y*2.7+sin(w.x*1.9)*1.3)+.5*sin(w.x*7.3-w.y*6.1);
float grass=saturate((L.g-max(L.r,L.b))*5.5);
float3 meadow=lerp(float3(.85,.95,1.04),float3(1.15,1.07,.83),saturate(.5+.38*n));
return L*lerp(1,d,Strength)*(1+.11*Macro*n)*lerp(float3(1,1,1),meadow,grass*.72)*Gain;
'''

GLOW_CODE = '''
float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));
float lamp=step(.82,L.r)*step(.45,L.g)*step(L.g,.68)*step(L.b,.30);
float canvas=step(.70,L.r)*step(L.r,.79)*step(.55,L.g)*step(.35,L.b);
float leaf=step(.4,L.r)*step(.24,L.g)*step(L.b,.07);
float shop=step(.18,L.r)*step(L.r,.22)*step(.08,L.g)*step(L.g,.11)*step(.02,L.b)*step(L.b,.04);
float3 bounce=B*float3(.045,.034,.020)*saturate(-N.z);
return B*(.045+lamp*.9+canvas*.20+leaf*.38+shop*.15)+bounce;
'''

AO_CODE = '''
float hemi=lerp(.50,1.,saturate(N.z*.5+.5));
float luma=dot(Texture2DSample(Tex,TexSampler,UV/Tile).rgb,float3(.3,.59,.11));
float crevice=lerp(1.,clamp(.76+luma*.60,.68,1.),Strength);
return saturate(hemi*crevice);
'''


def city_parent(package, reads, *, texture):
    """donor parent(default), city_material.py lines 42-95: the textured parent of the Hidamari materials, upgraded with
    hemisphere + surface-crevice Forward SkyLight AO and warm eave ground bounce while preserving all parameters."""
    MEL = unreal.MaterialEditingLibrary
    default = reads[texture]
    m = _material(package)
    MEL.delete_all_material_expressions(m)

    def node(cls, x, y, **kw):
        e = MEL.create_material_expression(m, cls, x, y)
        for k, v in kw.items():
            e.set_editor_property(k, v)
        return e

    def custom(x, y, code, inputs, kind=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
        n = node(unreal.MaterialExpressionCustom, x, y, code=code, output_type=kind)
        n.set_editor_property('inputs', _custom_inputs([name for name, _, _ in inputs]))
        for name, src, out in inputs:
            assert MEL.connect_material_expressions(src, out, n, name), name
        return n

    vc = node(unreal.MaterialExpressionVertexColor, -900, 0)
    uv = node(unreal.MaterialExpressionTextureCoordinate, -900, 150)
    pos = node(unreal.MaterialExpressionWorldPosition, -900, 250)
    tex = node(unreal.MaterialExpressionTextureObjectParameter, -900, 350, parameter_name='Tex', texture=default)
    tile = node(unreal.MaterialExpressionScalarParameter, -900, 500, parameter_name='Tile', default_value=1.5)
    strength = node(unreal.MaterialExpressionScalarParameter, -900, 600, parameter_name='Strength', default_value=1.)
    macro = node(unreal.MaterialExpressionScalarParameter, -900, 700, parameter_name='Macro', default_value=.5)
    gain = node(unreal.MaterialExpressionScalarParameter, -900, 800, parameter_name='Gain', default_value=1.)
    vn = node(unreal.MaterialExpressionVertexNormalWS, -900, 900)
    base = custom(-450, 0, BASE_CODE, [('C', vc, ''), ('UV', uv, ''), ('P', pos, ''), ('Tex', tex, ''), ('Tile', tile, ''),
                                       ('Strength', strength, ''), ('Macro', macro, ''), ('Gain', gain, '')])
    glow = custom(-200, 300, GLOW_CODE, [('C', vc, ''), ('B', base, ''), ('N', vn, '')])
    ao = custom(-200, 480, AO_CODE, [('N', vn, ''), ('UV', uv, ''), ('Tex', tex, ''), ('Tile', tile, ''),
                                     ('Strength', strength, '')], unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    b, g = haze.apply(unreal, m, base, glow, x=50, y=0)
    assert MEL.connect_material_property(b, '', unreal.MaterialProperty.MP_BASE_COLOR)
    assert MEL.connect_material_property(g, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    assert MEL.connect_material_property(ao, '', unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    for prop, value, y in ((unreal.MaterialProperty.MP_ROUGHNESS, .87, 600), (unreal.MaterialProperty.MP_SPECULAR, .12, 700)):
        c = node(unreal.MaterialExpressionConstant, 50, y, r=value)
        MEL.connect_material_property(c, '', prop)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(m)
    return m
