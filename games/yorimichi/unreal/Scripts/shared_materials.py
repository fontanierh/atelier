"""The only writer of the shared world textures, materials and parameter collections."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))

import json
import unreal
import yori
from asset_catalog import TEXTURES, material_bindings, shared_packages
from material_assets import create, instance, import_texture, node, link, opt, save_material
from painterly_kernel import shader as painterly_shader
from vertex_material import material as vertex_material
from foliage_material import enable_distance_fade, enable_bark_lod_blend, supports_lod_blend
import atmosphere
import see_through

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
LOG = unreal.log


def make_mpc():
    mpc = create("MPC_Wind", unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
    previous = {str(p.get_editor_property('parameter_name')): p
                for p in mpc.get_editor_property('vector_parameters')}
    ps = []
    for name, val in (("Wind", unreal.LinearColor(0.3, -0.95, 0.0, 0.0)), ("PlayerPos", unreal.LinearColor(0.0, 0.0, -100000.0, 0.0)), ("SunDirection", unreal.LinearColor(-.778, .449, .438, 1.0))):
        # Keep the parameter GUID: other packages reference it without deriving data from it.
        q = previous.get(name) or unreal.CollectionVectorParameter()
        q.set_editor_property("parameter_name", name)
        q.set_editor_property("default_value", val)
        ps.append(q)
    mpc.set_editor_property("vector_parameters", ps)
    EAL.save_loaded_asset(mpc)
    return mpc


def wind_graph(m, mpc):
    """World position offset: gusting sway along the wind + a push away from the player, scaled by vertex colour R"""
    U = unreal
    WP = node(m, U.MaterialExpressionWorldPosition, -2200, 800); T = node(m, U.MaterialExpressionTime, -2200, 1100)
    VC = node(m, U.MaterialExpressionVertexColor, -600, 1300)
    Wind = node(m, U.MaterialExpressionCollectionParameter, -2200, 1300, collection=mpc, parameter_name="Wind")
    PP = node(m, U.MaterialExpressionCollectionParameter, -2200, 1500, collection=mpc, parameter_name="PlayerPos")
    mx = node(m, U.MaterialExpressionComponentMask, -2000, 700, r=True, g=False, b=False, a=False); link(WP, "", mx, "")
    my = node(m, U.MaterialExpressionComponentMask, -2000, 800, r=False, g=True, b=False, a=False); link(WP, "", my, "")
    mz = node(m, U.MaterialExpressionComponentMask, -2000, 900, r=False, g=False, b=True, a=False); link(WP, "", mz, "")
    px = node(m, U.MaterialExpressionMultiply, -1800, 700, const_b=0.0011); link(mx, "", px, "A")
    py = node(m, U.MaterialExpressionMultiply, -1800, 800, const_b=0.0016); link(my, "", py, "A")
    ph = node(m, U.MaterialExpressionAdd, -1600, 750); link(px, "", ph, "A"); link(py, "", ph, "B")
    t1 = node(m, U.MaterialExpressionMultiply, -1800, 1000, const_b=0.28); link(T, "", t1, "A")
    a1 = node(m, U.MaterialExpressionAdd, -1600, 950); link(t1, "", a1, "A"); link(ph, "", a1, "B")
    s1 = node(m, U.MaterialExpressionSine, -1400, 950); link(a1, "", s1, "")
    t2 = node(m, U.MaterialExpressionMultiply, -1800, 1150, const_b=0.7); link(T, "", t2, "A")
    pz = node(m, U.MaterialExpressionMultiply, -1800, 900, const_b=0.002); link(mz, "", pz, "A")
    a2 = node(m, U.MaterialExpressionAdd, -1600, 1150); link(t2, "", a2, "A"); link(pz, "", a2, "B")
    s2 = node(m, U.MaterialExpressionSine, -1400, 1150); link(a2, "", s2, "")
    s1w = node(m, U.MaterialExpressionMultiply, -1200, 950, const_b=0.6); link(s1, "", s1w, "A")
    s2w = node(m, U.MaterialExpressionMultiply, -1200, 1150, const_b=0.3); link(s2, "", s2w, "A")
    sw = node(m, U.MaterialExpressionAdd, -1000, 1000); link(s1w, "", sw, "A"); link(s2w, "", sw, "B")
    sw2 = node(m, U.MaterialExpressionAdd, -850, 1000, const_b=0.5); link(sw, "", sw2, "A")
    amp = node(m, U.MaterialExpressionMultiply, -700, 1000, const_b=16.0); link(sw2, "", amp, "A")
    wrgb = node(m, U.MaterialExpressionComponentMask, -2000, 1300, r=True, g=True, b=True, a=False); link(Wind, "", wrgb, "")
    off = node(m, U.MaterialExpressionMultiply, -550, 1050); link(wrgb, "", off, "A"); link(amp, "", off, "B")
    # push away from the player (horizontal)
    prgb = node(m, U.MaterialExpressionComponentMask, -2000, 1500, r=True, g=True, b=True, a=False); link(PP, "", prgb, "")
    d = node(m, U.MaterialExpressionSubtract, -1800, 1450); link(WP, "", d, "A"); link(prgb, "", d, "B")
    dxy = node(m, U.MaterialExpressionComponentMask, -1600, 1450, r=True, g=True, b=False, a=False); link(d, "", dxy, "")
    dot = node(m, U.MaterialExpressionDotProduct, -1400, 1400); link(dxy, "", dot, "A"); link(dxy, "", dot, "B")
    dist = node(m, U.MaterialExpressionSquareRoot, -1250, 1400); link(dot, "", dist, "")
    fr = node(m, U.MaterialExpressionDivide, -1100, 1400, const_b=170.0); link(dist, "", fr, "A")
    om = node(m, U.MaterialExpressionOneMinus, -950, 1400); link(fr, "", om, "")
    sat = node(m, U.MaterialExpressionSaturate, -820, 1400); link(om, "", sat, "")
    pamp = node(m, U.MaterialExpressionMultiply, -700, 1400, const_b=70.0); link(sat, "", pamp, "A")
    nrm = node(m, U.MaterialExpressionNormalize, -1250, 1550); link(dxy, "", nrm, "")
    push = node(m, U.MaterialExpressionMultiply, -550, 1450); link(nrm, "", push, "A"); link(pamp, "", push, "B")
    zero = node(m, U.MaterialExpressionConstant, -550, 1600, r=0.0)
    push3 = node(m, U.MaterialExpressionAppendVector, -400, 1500); link(push, "", push3, "A"); link(zero, "", push3, "B")
    total = node(m, U.MaterialExpressionAdd, -300, 1150); link(off, "", total, "A"); link(push3, "", total, "B")
    vcr = node(m, U.MaterialExpressionComponentMask, -400, 1300, r=True, g=False, b=False, a=False); link(VC, "", vcr, "")
    wpo = node(m, U.MaterialExpressionMultiply, -150, 1200); link(total, "", wpo, "A"); link(vcr, "", wpo, "B")
    MEL.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)


def cloud_shadow_material(tex):
    U = unreal
    m = create("M_CloudShadow", U.Material, U.MaterialFactoryNew())
    m.set_editor_property("material_domain", U.MaterialDomain.MD_LIGHT_FUNCTION)
    WP = node(m, U.MaterialExpressionWorldPosition, -1200, 0); T = node(m, U.MaterialExpressionTime, -1200, 300)
    xy = node(m, U.MaterialExpressionComponentMask, -1000, 0, r=True, g=True, b=False, a=False); link(WP, "", xy, "")
    sc = node(m, U.MaterialExpressionMultiply, -800, 0, const_b=0.000022); link(xy, "", sc, "A")
    tx = node(m, U.MaterialExpressionMultiply, -1000, 300, const_b=0.0045); link(T, "", tx, "A")
    ty = node(m, U.MaterialExpressionMultiply, -1000, 400, const_b=0.0016); link(T, "", ty, "A")
    tv = node(m, U.MaterialExpressionAppendVector, -800, 350); link(tx, "", tv, "A"); link(ty, "", tv, "B")
    uv = node(m, U.MaterialExpressionAdd, -600, 150); link(sc, "", uv, "A"); link(tv, "", uv, "B")
    ts = node(m, U.MaterialExpressionTextureSample, -400, 100, texture=tex); link(uv, "", ts, "UVs")
    mul = node(m, U.MaterialExpressionMultiply, -200, 100, const_b=0.4); link(ts, "R", mul, "A")
    om = node(m, U.MaterialExpressionOneMinus, -50, 100); link(mul, "", om, "")
    MEL.connect_material_property(om, "", U.MaterialProperty.MP_EMISSIVE_COLOR)
    save_material(m)
    return m


def painterly_material():
    """Post-process look: sparse eight-sector Kuwahara (21 taps independent of brush size), then an
    optional adventure-style soft toon pass (luminance quantized into a few bands with smooth steps, thin depth-only
    outlines, the sky excluded by depth). Every knob is a scalar parameter driven at runtime by the settings menu."""
    U = unreal
    m = create("M_Painterly", U.Material, U.MaterialFactoryNew())
    m.set_editor_property("material_domain", U.MaterialDomain.MD_POST_PROCESS)
    m.set_editor_property("blendable_location", U.BlendableLocation.BL_SCENE_COLOR_AFTER_TONEMAPPING)
    scene = node(m, U.MaterialExpressionSceneTexture, -700, 0, scene_texture_id=U.SceneTextureId.PPI_POST_PROCESS_INPUT0)
    stencil = node(m, U.MaterialExpressionSceneTexture, -900, -180, scene_texture_id=U.SceneTextureId.PPI_CUSTOM_STENCIL)
    custom_depth = node(m, U.MaterialExpressionSceneTexture, -900, -300, scene_texture_id=U.SceneTextureId.PPI_CUSTOM_DEPTH)
    scene_depth = node(m, U.MaterialExpressionSceneTexture, -900, -420, scene_texture_id=U.SceneTextureId.PPI_SCENE_DEPTH)
    params = [("Strength", 0.35), ("Radius", 2.0), ("Toon", 0.0), ("Bands", 5.0), ("Soft", 0.5), ("Outline", 0.0), ("SkyDepth", 600000.0)]
    pnodes = [node(m, U.MaterialExpressionScalarParameter, -700, 200 + 90 * i, parameter_name=n, default_value=v) for i, (n, v) in enumerate(params)]
    code = """
#if SHADING_PATH_MOBILE
#define ATELIER_SCENE_TEXTURE(UV, ID, FILTERED) MobileSceneTextureLookup(Parameters, ID, UV)
#else
#define ATELIER_SCENE_TEXTURE(UV, ID, FILTERED) SceneTextureLookup(UV, ID, FILTERED)
#endif
float2 uv = GetDefaultSceneTextureUV(Parameters, 14);
// SceneTexture UVs use the backing texture, which may differ from viewport resolution.
float2 d = GetSceneTextureBufferSize(14).zw;
float4 uvBounds = GetSceneTextureUVMinMax(14);
float2 uvMin = uvBounds.xy, uvMax = uvBounds.zw;
""" + painterly_shader(lookup="ATELIER_SCENE_TEXTURE") + """
if (Toon > 0.001 || Outline > 0.001)
{
    float2 depthUV = GetDefaultSceneTextureUV(Parameters, 1);
    float2 depthD = GetSceneTextureBufferSize(1).zw;
    float dc = ATELIER_SCENE_TEXTURE(depthUV, 1, false).r;
    float notSky = 1.0 - saturate((dc - SkyDepth * 0.7) / (SkyDepth * 0.3));
    // soft bands: luminance snapped to the centre of its band, with a smooth step between bands
    float lum = dot(outc, float3(0.299, 0.587, 0.114));
    float nb = max(Bands, 2.0);
    float b = lum * nb; float fl = floor(b); float fr = b - fl;
    float sw = max(Soft, 0.02) * 0.5;
    float q = fl + smoothstep(0.5 - sw, 0.5 + sw, fr);
    float lq = (q + 0.5) / nb;
    float3 toon = outc * (lq / max(lum, 1e-3));
    toon = lerp(toon, saturate(toon), 1.0);
    outc = lerp(outc, toon, Toon * notSky);
    // outlines: depth discontinuities only (no normal edges: leaves would turn into a scribble)
    float dl = ATELIER_SCENE_TEXTURE(depthUV + float2(-depthD.x, 0), 1, false).r, dr = ATELIER_SCENE_TEXTURE(depthUV + float2(depthD.x, 0), 1, false).r;
    float du = ATELIER_SCENE_TEXTURE(depthUV + float2(0, -depthD.y), 1, false).r, dd = ATELIER_SCENE_TEXTURE(depthUV + float2(0, depthD.y), 1, false).r;
    float dmin = min(min(dl, dr), min(du, dd));
    float edge = saturate((dc - dmin) / max(dmin * 0.10, 1.0) - 1.0);     // the pixel sits behind a nearer neighbour by more than 10% of its depth
    float far = 1.0 - saturate((dmin - 4000.0) / 60000.0);              // fade the ink with distance: far hills stay soft
    outc *= 1.0 - Outline * 0.75 * edge * far * notSky;
}
// Only visible player pixels retain their fine facial/cloth shading. Depth
// agreement prevents a player behind a wall from changing the wall's treatment.
// Character and equipped items keep the same original lighting treatment.
float player = ((abs(Stencil.r - 1.0) < 0.5 || abs(Stencil.r - 2.0) < 0.5) && abs(CustomZ.r - SceneZ.r) < 2.0) ? 1.0 : 0.0;
float3 result = lerp(outc, Scene, player * 0.85);
#undef ATELIER_SCENE_TEXTURE
return result;
"""
    cust = node(m, U.MaterialExpressionCustom, -300, 100, code=code, output_type=U.CustomMaterialOutputType.CMOT_FLOAT3, description="Painterly")
    ins = []
    for name in ["Scene", "Stencil", "CustomZ", "SceneZ"] + [n for n, _ in params]:
        ci = U.CustomInput(); ci.set_editor_property("input_name", name); ins.append(ci)
    cust.set_editor_property("inputs", ins)
    link(scene, "Color", cust, "Scene")
    link(stencil, "Color", cust, "Stencil")
    link(custom_depth, "Color", cust, "CustomZ")
    link(scene_depth, "Color", cust, "SceneZ")
    for (n, _), pn in zip(params, pnodes): link(pn, "", cust, n)
    MEL.connect_material_property(cust, "", U.MaterialProperty.MP_EMISSIVE_COLOR)
    save_material(m)
    return m


def master(name, masked=False, unlit=False, white=None, fixed_tex=None, mpc=None):
    m = create(name, unreal.Material, unreal.MaterialFactoryNew())
    if fixed_tex is not None:       # the sky: a plain sample, no parameter
        tex = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSample, -700, 0)
        tex.set_editor_property("texture", fixed_tex)
    else:
        tex = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -700, 0)
        tex.set_editor_property("parameter_name", "Tex"); tex.set_editor_property("texture", white)
    tint = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -700, 300)
    tint.set_editor_property("parameter_name", "Tint"); tint.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    mul0 = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -350, 100)
    MEL.connect_material_expressions(tex, "RGB", mul0, "A"); MEL.connect_material_expressions(tint, "", mul0, "B")
    mul = mul0
    if not unlit:
        # aerial perspective (atmosphere.py): the sea's haze, as emission; the dome is unlit and untouched
        mul, haze = atmosphere.apply(m, mul0, x=260, y=300)
        MEL.connect_material_property(haze, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if masked:
        # interior leaves are darker (vertex colour G = 0 deep inside .. 1 on the shell): the canopy reads as a full mass
        U = unreal
        vc = node(m, U.MaterialExpressionVertexColor, -350, -150)
        gg = node(m, U.MaterialExpressionComponentMask, -200, -150, r=False, g=True, b=False, a=False); link(vc, "", gg, "")
        sh = node(m, U.MaterialExpressionMultiply, -50, -150, const_b=0.5); link(gg, "", sh, "A")
        sh2 = node(m, U.MaterialExpressionAdd, 80, -150, const_b=0.5); link(sh, "", sh2, "A")
        dark = node(m, U.MaterialExpressionMultiply, 200, 0); link(mul, "", dark, "A"); link(sh2, "", dark, "B")
        MEL.connect_material_property(dark, "", U.MaterialProperty.MP_BASE_COLOR)
        # leaves let light through: two-sided foliage with a subsurface colour, so undersides glow instead of going black
        m.set_editor_property("shading_model", U.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
        ss = node(m, U.MaterialExpressionMultiply, 320, 120, const_b=0.22); link(dark, "", ss, "A")
        MEL.connect_material_property(ss, "", U.MaterialProperty.MP_SUBSURFACE_COLOR)
    else:
        MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR if unlit else unreal.MaterialProperty.MP_BASE_COLOR)
    if not unlit:
        rough = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -350, 350); rough.set_editor_property("r", 1.0)
        spec = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -350, 450); spec.set_editor_property("r", 0.0)
        MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
        MEL.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)
    if masked:
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        m.set_editor_property("two_sided", True)
        m.set_editor_property("opacity_mask_clip_value", 0.4)
        MEL.connect_material_property(tex, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
        enable_distance_fade(m)
        if mpc is not None: wind_graph(m, mpc)
    if unlit:
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        m.set_editor_property("two_sided", True)
        opt(m, "is_sky", False)     # with is_sky the height fog was applied to the dome despite the cutoff distance
        LOG(f"sky material is_sky={m.get_editor_property('is_sky')}")
    m.set_editor_property("used_with_instanced_static_meshes", True)     # the props are HISM instances: without this the game falls back to the grid material
    m.set_editor_property("used_with_skeletal_mesh", True)
    save_material(m)
    return m


def grass_material(white, mpc):
    m = master('M_Grass', masked=True, white=white, mpc=mpc)
    # Both faces must shade like the meadow. The usual backface normal flip
    # otherwise gives neighbouring crossed cards alternating light/dark stripes.
    m.set_editor_property('tangent_space_normal', False)
    up = node(m, unreal.MaterialExpressionConstant3Vector, -400, 950,
              constant=unreal.LinearColor(0, 0, 1, 1))
    # UE only applies TwoSidedSign to tangent-space normals; a world-space
    # constant stays upward on both sides without an extra sign correction.
    MEL.connect_material_property(up, '', unreal.MaterialProperty.MP_NORMAL)
    # Mesh silhouettes need temporal coverage fading; multiplying their opaque
    # alpha by fade would otherwise remove every blade at the clip threshold.
    fade = node(m, unreal.MaterialExpressionPerInstanceFadeAmount, -450, 1150)
    dither = node(m, unreal.MaterialExpressionMaterialFunctionCall, -150, 1100)
    function = unreal.load_object(None, '/Engine/Functions/Engine_MaterialFunctions02/Utility/DitherTemporalAA.DitherTemporalAA')
    if not function: raise RuntimeError('Missing engine foliage coverage function')
    dither.set_material_function(function)
    assert MEL.connect_material_expressions(fade, '', dither, 'Alpha Threshold')
    assert MEL.connect_material_property(dither, '', unreal.MaterialProperty.MP_OPACITY_MASK)
    wind = MEL.get_material_property_input_node(m, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    gentle = node(m, unreal.MaterialExpressionMultiply, 250, 1200, const_b=.28)
    link(wind, '', gentle, 'A')
    MEL.connect_material_property(gentle, '', unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    save_material(m)
    return m


def build_materials(T):
    white = T["T_white"]         # the parameter default must be a real texture: a missing default fails the compile (grey grid material)
    mpc = make_mpc()
    lit = master("M_Painted", white=white); fol = master("M_Foliage", masked=True, white=white, mpc=mpc); sky = master("M_Sky", unlit=True, white=white, fixed_tex=T["T_sky"])
    MI = {}
    MI["LeafBroad"] = instance("MI_LeafBroad", fol, T["T_leaf_broad"]); MI["LeafCedar"] = instance("MI_LeafCedar", fol, T["T_leaf_cedar"])
    MI["LeafPine"] = instance("MI_LeafPine", fol, T["T_leaf_pine"]); MI["LeafOchre"] = instance("MI_LeafOchre", fol, T["T_leaf_ochre"])
    MI["Grass"] = instance("MI_Grass", grass_material(white, mpc), T["T_grass"])
    # Ginkgo crowns read gold, not cream (assets/craterpark/concepts/target-f_*.jpg): screen colour about
    # (224, 164, 85) where the plain leaf texture showed (222, 202, 145); the tint is that ratio squared (screen ~ albedo^0.5).
    MI["LeafMaple"] = instance("MI_LeafMaple", fol, T["T_leaf_maple"]); MI["LeafGinkgo"] = instance("MI_LeafGinkgo", fol, T["T_leaf_ginkgo"], tint=(1., .72, .42))
    MI["LeafSmall"] = instance("MI_LeafSmall", fol, T["T_leaf_small"]); MI["Litter"] = instance("MI_Litter", fol, T["T_litter"])
    MI["Flower"] = instance("MI_Flower", fol, T["T_flower"]); MI["LeafOchreSmall"] = instance("MI_LeafOchreSmall", fol, T["T_leaf_ochre_small"])
    MI["RoofTile"] = instance("MI_RoofTile", lit, T["T_rooftile"], (0.40, 0.42, 0.48))
    MI["_cloud"] = cloud_shadow_material(T["T_cloudmask"])
    MI["_painterly"] = painterly_material()
    MI["Bark"] = instance("MI_Bark", lit, T["T_bark"]); MI["Concrete"] = instance("MI_Concrete", lit, T["T_concrete"])
    MI["BarkOlive"] = instance("MI_BarkOlive", lit, T["T_bark_olive"])
    MI["BarkTuscan"] = instance("MI_BarkTuscan", lit, T["T_bark_olive"], (.65, .55, .4))
    for key in ("Bark", "BarkOlive", "BarkTuscan"):
        enable_bark_lod_blend(MI[key]); EAL.save_loaded_asset(MI[key])
    MI["Ground"] = instance("MI_Ground", lit, T["T_ground"]); MI["Road"] = instance("MI_Road", lit, T["T_road"], (0.34, 0.33, 0.33)); MI["Water"] = instance("MI_Water", lit, T["T_water"])
    MI["Sky"] = instance("MI_Sky", sky, None, (1.35, 1.35, 1.35))
    flat = {"Paint": (0.85, 0.85, 0.82), "Stone": (0.50, 0.50, 0.47), "Vermilion": (0.62, 0.12, 0.06), "Plaster": (0.80, 0.74, 0.62), "Tile": (0.16, 0.17, 0.20),
            "Wood": (0.18, 0.11, 0.07), "Feather": (0.92, 0.92, 0.90), "FeatherDark": (0.10, 0.10, 0.12), "Metal": (0.08, 0.08, 0.09),
            "Rock": (0.30, 0.27, 0.24), "Lattice": (0.14, 0.10, 0.08), "Moss": (0.30, 0.38, 0.16)}
    for k, c in flat.items():
        MI[k] = instance("MI_" + k, lit, white, c)
    return MI


def main():
    """@cc [owner:fontanierh,label:correctness] complete-shared-material-owner
    This action MUST own every catalogue texture, material and collection overlay. Its interface
    MUST describe the final saved assets; failed compilation or saving MUST prevent completion.
    """
    textures = {}
    for filename in TEXTURES:
        texture = import_texture(str(yori.TEXTURES / filename), '/Game/Japan/Textures')
        if texture is None:
            raise RuntimeError('Texture import failed: ' + filename)
        textures[Path(filename).stem] = texture
    build_materials(textures)
    vertex_material()
    see_through.world_materials()
    owned = []
    for package in shared_packages():
        asset = EAL.load_asset(package)
        if asset is None:
            raise RuntimeError('Shared asset missing: ' + package)
        owned.append(asset)
    if not EAL.save_loaded_assets(owned, False):
        raise RuntimeError('Could not save every owned shared material package')
    # Consumers need the material's stable interface, not every shader graph byte. Native package
    # inventories still detect external edits before this interface can be trusted by a build.
    interface = {path: {'lod_blend': supports_lod_blend(EAL.load_asset(path))}
                 for slot, path in material_bindings().items() if not slot.startswith('_')}
    report = yori.OUT / 'materials/foliage-interface.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(interface, sort_keys=True, indent=2) + '\n')
    LOG('SHARED MATERIALS COMPLETE')


if __name__ == '__main__':
    main()
