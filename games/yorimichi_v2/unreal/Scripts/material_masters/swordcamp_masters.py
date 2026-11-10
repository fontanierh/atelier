"""Sword Camp master builders: M_SwordCamp (build_material) and M_RoninBody (build_ronin_body_material).

Extracted from the donor generator games/yorimichi/unreal/Scripts/import_swordcamp.py at the V2 source baseline
(docs/DECISIONS.md D01, donor blob sha256 86ce7b5e...): build_material is that file's lines 46-113 and
build_ronin_body_material its lines 116-171. Their expressions, parameter names, values, wiring and order are the donor's.
Three things move out of the builder: no asset is saved (the importer saves the one it accepts, after reading it back),
no texture is imported or loaded here (the importer passes every read in), and the module-level imports and the atlas
import (donor lines 1-45) stay behind. Nothing runs at import: the module is functions only, so it imports without the
Unreal editor, where `unreal` is None and a builder cannot run.

The haze that build_material calls is atmosphere.apply (donor atmosphere.py lines 14-62, blob sha256 b59478df...), which
reads the sea_look.py constants num and f3 (lines 38-45), HORIZON (line 50) and HAZE_CM, FAR, FAR_COLOUR (lines 67-69,
blob sha256 ffae53cd...). Only the apply path the Sword Camp graph takes is copied: the glow-less branch has no caller.
Each copy below is marked with the donor line it comes from.

A builder takes the destination package path, the loaded reads ({package: asset}) and the recipe's arguments as keyword
arguments, and returns the rebuilt material.
"""
try:
    import unreal
except ImportError:   # outside the editor: the functions are defined but cannot run
    unreal = None


# --- copied from sea_look.py (donor lines 38-45, 50, 67-69) -----------------------------------------------------------

def num(x):
    """HLSL float literal (sea_look.py lines 38-40)."""
    return repr(float(x))


def f3(c):
    """HLSL float3 literal (sea_look.py lines 43-45)."""
    return 'float3(%s)' % ','.join(num(x) for x in c)


HORIZON = (0.126, 0.311, 0.720)                       # sea_look.py line 50
HAZE_CM = 900000.0                                     # sea_look.py line 67
FAR = 0.74                                             # sea_look.py line 68
FAR_COLOUR = tuple(round(c * FAR, 4) for c in HORIZON)  # sea_look.py line 69


# --- copied from atmosphere.py (donor lines 17-21, 25-27, 30-33 and the apply path of 37-62) -------------------------------
START_CM = 3000.0                                      # atmosphere.py line 19: the first 30 m are untouched
COLOUR = FAR_COLOUR                                    # atmosphere.py line 18
SHARE = f'saturate(1-exp(-max(D-{num(START_CM)},0)/{num(HAZE_CM)}))'   # atmosphere.py line 21


def _haze_code_base(expr='B'):
    """atmosphere.code_base (atmosphere.py lines 25-27)."""
    return f'return ({expr})*(1-{SHARE});'


def _haze_code_glow(expr='E'):
    """atmosphere.code_glow (atmosphere.py lines 30-32)."""
    return f'float h={SHARE}; return ({expr})*(1-h)+{f3(COLOUR)}*h;'


def _haze_custom(m, code, inputs, x, y):
    """atmosphere._custom (atmosphere.py lines 35-47 by the donor's order): a Custom node with named inputs, wired."""
    MEL = unreal.MaterialEditingLibrary
    n = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, x, y)
    n.set_editor_property('code', code)
    n.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    n.set_editor_property('inputs', _custom_inputs([name for name, _, _ in inputs]))
    for name, src, out in inputs:
        assert MEL.connect_material_expressions(src, out, n, name), name
    return n


def _haze_apply(m, base, glow, x, y):
    """atmosphere.apply with base_out and glow_out left at '' (atmosphere.py lines 50-62, glow given): the haze depth node,
    then the base-colour node at (x, y) and the emissive node at (x, y + 200). Returns (base, glow)."""
    MEL = unreal.MaterialEditingLibrary
    depth = MEL.create_material_expression(m, unreal.MaterialExpressionPixelDepth, x - 200, y + 300)
    b = _haze_custom(m, _haze_code_base(), [('B', base, ''), ('D', depth, '')], x, y)
    g = _haze_custom(m, _haze_code_glow(), [('E', glow, ''), ('D', depth, '')], x, y + 200)
    return b, g


# --- shared helpers (donor: the per-builder loops; `_material` is the hippodrome builder's) ----------------------------

def _material(package):
    """The material at a package path, reused when it exists (donor: EAL.load_asset, or AT.create_asset when it does not)."""
    folder, name = package.rsplit('/', 1)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        return unreal.EditorAssetLibrary.load_asset(package)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def _custom_inputs(names):
    """One CustomInput per name, in order (the donor's `for key in (...)` loops)."""
    out = []
    for key in names:
        arg = unreal.CustomInput()
        arg.set_editor_property('input_name', key)
        out.append(arg)
    return out


# --- M_SwordCamp -----------------------------------------------------------------------------------------------------------

def build_material(package, reads, *, texture):
    """donor build_material(atlas_tex), import_swordcamp.py lines 46-113: the Sword Camp props' painted atlas, with a
    vertex-colour fill, the haze, a constant roughness .92 and specular .04, and a wind offset on the world position.
    `texture` is the read package of the atlas (the donor's T_SwordCampAtlas, the texture record texture/swordcamp/atlas)."""
    MEL = unreal.MaterialEditingLibrary
    atlas_tex = reads[texture]
    m = _material(package)
    MEL.delete_all_material_expressions(m)

    def node(cls, x, y, **kwargs):
        e = MEL.create_material_expression(m, cls, x, y)
        for k, v in kwargs.items():
            e.set_editor_property(k, v)
        return e

    def link(a, ao, b, bi):
        assert MEL.connect_material_expressions(a, ao, b, bi)

    tex = node(unreal.MaterialExpressionTextureSampleParameter2D, -700, 0, parameter_name='Tex', texture=atlas_tex)
    vc = node(unreal.MaterialExpressionVertexColor, -700, 260)
    fill = node(
        unreal.MaterialExpressionCustom,
        -320,
        120,
        code='return C*(.06+saturate(G)*.95);',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3,
    )
    fill.set_editor_property('inputs', _custom_inputs(['C', 'G']))
    link(tex, 'RGB', fill, 'C')
    link(vc, 'R', fill, 'G')

    base, glow = _haze_apply(m, tex, fill, x=120, y=0)
    assert MEL.connect_material_property(base, '', unreal.MaterialProperty.MP_BASE_COLOR)
    assert MEL.connect_material_property(glow, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    rough = node(unreal.MaterialExpressionConstant, 120, 420, r=0.92)
    spec = node(unreal.MaterialExpressionConstant, 120, 520, r=0.04)
    MEL.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(spec, '', unreal.MaterialProperty.MP_SPECULAR)

    wind = node(
        unreal.MaterialExpressionCustom,
        120,
        680,
        code='float phase=T*2.1+P.x*.003+P.y*.004; return float3(sin(phase)*2.4,cos(phase*.85)*1.6,sin(phase*1.4)*.5)*W*W;',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3,
    )
    wind.set_editor_property('inputs', _custom_inputs(['T', 'P', 'W']))
    time_node = node(unreal.MaterialExpressionTime, -360, 680)
    pos_node = node(unreal.MaterialExpressionWorldPosition, -360, 780)
    link(time_node, '', wind, 'T')
    link(pos_node, '', wind, 'P')
    link(vc, 'A', wind, 'W')
    MEL.connect_material_property(wind, '', unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)

    m.set_editor_property('two_sided', True)
    m.set_editor_property('used_with_static_lighting', False)
    MEL.recompile_material(m)
    return m


# --- M_RoninBody -----------------------------------------------------------------------------------------------------------

def build_ronin_body_material(package, reads, *, texture):
    """donor build_ronin_body_material(atlas_tex), import_swordcamp.py lines 116-171: the skeletal Ronin body, its tunic
    recoloured by CoatTint, with roughness .7, metallic 0 and specular .3. `texture` is the atlas read, as for M_SwordCamp."""
    MEL = unreal.MaterialEditingLibrary
    atlas_tex = reads[texture]
    m = _material(package)
    MEL.delete_all_material_expressions(m)
    m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    m.set_editor_property('two_sided', False)
    m.set_editor_property('used_with_skeletal_mesh', True)
    m.set_editor_property('used_with_static_lighting', False)

    tex = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -640, 0)
    tex.set_editor_property('parameter_name', 'BaseTex')
    tex.set_editor_property('texture', atlas_tex)

    tint = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -640, 260)
    tint.set_editor_property('parameter_name', 'CoatTint')
    tint.set_editor_property('default_value', unreal.LinearColor(0.16, 0.30, 0.62, 1.0))

    recol = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -240, 80)
    recol.set_editor_property(
        'code',
        'float coat=saturate((C.r-C.g*2.15-0.02)*18.0)*saturate((0.18-C.g)*16.0); '
        'float luma=dot(C,float3(0.299,0.587,0.114)); '
        'float3 dyed=saturate((luma/0.11)*pow(saturate(T),1.35)); '
        'return lerp(C,dyed,coat);',
    )
    recol.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    recol.set_editor_property('inputs', _custom_inputs(['C', 'T']))
    assert MEL.connect_material_expressions(tex, 'RGB', recol, 'C')
    assert MEL.connect_material_expressions(tint, '', recol, 'T')
    assert MEL.connect_material_property(recol, '', unreal.MaterialProperty.MP_BASE_COLOR)

    fill = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, 80, 120)
    fill.set_editor_property('const_b', 0.30)
    assert MEL.connect_material_expressions(recol, '', fill, 'A')
    assert MEL.connect_material_property(fill, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    for val, prop, y in [
        (0.7, unreal.MaterialProperty.MP_ROUGHNESS, 320),
        (0.0, unreal.MaterialProperty.MP_METALLIC, 400),
        (0.3, unreal.MaterialProperty.MP_SPECULAR, 480),
    ]:
        c = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, 80, y)
        c.set_editor_property('r', val)
        assert MEL.connect_material_property(c, '', prop)

    MEL.recompile_material(m)
    return m
