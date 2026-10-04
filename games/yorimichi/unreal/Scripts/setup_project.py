"""Editor-side setup (headless), run after the C++ module is built:

    "$UE/Engine/Binaries/Mac/UnrealEditor-Cmd" "$PROJ/Yorimichi.uproject" -run=pythonscript -script="$PROJ/Scripts/setup_project.py" -unattended -nop4 -nosplash

- purges /Game/Japan, imports textures, props, terrain, sea, the traveler (+ clips)
- builds the painterly materials (flat lit, masked foliage, unlit sky) and assigns them by slot name
- builds the level /Game/Japan/Maps/Slice: terrain, sun, sky light, fog, post-process, player start
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import os, glob, sys, unreal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from painterly_kernel import shader as painterly_shader
from foliage_material import enable_distance_fade
import atmosphere
ROOT = str(yori.OUT)
OUT = ROOT; TEX = os.path.join(ROOT, "textures")
REPORT = None
def LOG(msg):
    global REPORT
    if REPORT is None:
        REPORT = open(os.path.join(OUT, "setup_report.txt"), "w")
    unreal.log(msg); REPORT.write(str(msg) + "\n"); REPORT.flush()
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary


def opt(obj, name, value):
    try:
        obj.set_editor_property(name, value)
    except Exception as e:
        LOG(f"  (skipped {name}: {e})")


def import_fbx(path, dest, name, skeletal=False, materials=False, animations=False):
    task = unreal.AssetImportTask()
    task.filename = path; task.destination_path = dest; task.destination_name = name
    task.automated = True; task.replace_existing = True; task.save = True
    ui = unreal.FbxImportUI()
    ui.import_mesh = True; ui.import_materials = materials; ui.import_textures = materials
    ui.import_animations = animations; ui.import_as_skeletal = skeletal
    ui.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH if skeletal else unreal.FBXImportType.FBXIT_STATIC_MESH
    if skeletal:
        d = ui.skeletal_mesh_import_data
        opt(d, "normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        opt(d, "convert_scene", True); opt(d, "import_meshes_in_bone_hierarchy", True); opt(d, "use_t0_as_ref_pose", False)
        opt(d, "vertex_color_import_option", unreal.VertexColorImportOption.REPLACE)
        if animations:
            a = ui.anim_sequence_import_data
            opt(a, "import_bone_tracks", True); opt(a, "animation_length", unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    else:
        d = ui.static_mesh_import_data
        opt(d, "combine_meshes", True); opt(d, "generate_lightmap_u_vs", False); opt(d, "auto_generate_collision", False)
        opt(d, "normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        opt(d, "convert_scene", True); opt(d, "build_nanite", False)
        opt(d, "vertex_color_import_option", unreal.VertexColorImportOption.REPLACE)
    task.options = ui
    AT.import_asset_tasks([task])
    paths = list(task.imported_object_paths)
    LOG(f"imported {os.path.basename(path)} -> {paths}")
    return paths


def import_texture(path, dest):
    task = unreal.AssetImportTask()
    task.filename = path; task.destination_path = dest; task.automated = True; task.replace_existing = True; task.save = True
    AT.import_asset_tasks([task])
    p = list(task.imported_object_paths)
    texture = EAL.load_asset(p[0]) if p else None
    if texture and os.path.basename(path).startswith(('T_grass', 'T_leaf_', 'T_flower')):
        # Preserve the painted silhouette when sampling smaller mips. Sharpened
        # mips make thin alpha edges crawl; unsharpened averages stay quiet.
        texture.set_editor_property('do_scale_mips_for_alpha_coverage', True)
        texture.set_editor_property('alpha_coverage_thresholds', unreal.Vector4(0, 0, 0, .4))
        texture.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
        EAL.save_loaded_asset(texture)
    return texture


def purge():
    """Fresh import every run (a re-import keeps stale material slots). Animations go first: deleting the
    skeleton before its sequences makes the sequence delete fail."""
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = [a for a in reg.get_assets_by_path("/Game/Japan", recursive=True)]
    order = {"AnimSequence": 0, "SkeletalMesh": 1, "PhysicsAsset": 2, "Skeleton": 3}
    assets.sort(key=lambda a: order.get(str(a.asset_class_path.asset_name), 5))
    for a in assets:
        try:
            EAL.delete_asset(str(a.package_name))
        except Exception as e:
            LOG(f"  purge failed for {a.package_name}: {e}")
    LOG("purged /Game/Japan")


# ------------------------------------------------------------------ materials
def node(m, cls, x, y, **props):
    e = MEL.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, ao, b, bi):
    MEL.connect_material_expressions(a, ao, b, bi)


def make_mpc():
    mpc = create("MPC_Wind", unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
    ps = []
    for name, val in (("Wind", unreal.LinearColor(0.3, -0.95, 0.0, 0.0)), ("PlayerPos", unreal.LinearColor(0.0, 0.0, -100000.0, 0.0))):
        q = unreal.CollectionVectorParameter(); q.set_editor_property("parameter_name", name); q.set_editor_property("default_value", val); ps.append(q)
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
    MEL.recompile_material(m); EAL.save_loaded_asset(m)
    return m


def painterly_material():
    """Post-process look: sparse eight-sector Kuwahara (21 taps independent of brush size), then an
    optional BotW-style soft toon pass (luminance quantized into a few bands with smooth steps, thin depth-only
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
float2 uv = GetDefaultSceneTextureUV(Parameters, 14);
// SceneTexture UVs use the backing texture, which may differ from viewport resolution.
float2 d = GetSceneTextureBufferSize(14).zw;
float4 uvBounds = GetSceneTextureUVMinMax(14);
float2 uvMin = uvBounds.xy, uvMax = uvBounds.zw;
""" + painterly_shader() + """
if (Toon > 0.001 || Outline > 0.001)
{
    float2 depthUV = GetDefaultSceneTextureUV(Parameters, 1);
    float2 depthD = GetSceneTextureBufferSize(1).zw;
    float dc = SceneTextureLookup(depthUV, 1, false).r;
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
    float dl = SceneTextureLookup(depthUV + float2(-depthD.x, 0), 1, false).r, dr = SceneTextureLookup(depthUV + float2(depthD.x, 0), 1, false).r;
    float du = SceneTextureLookup(depthUV + float2(0, -depthD.y), 1, false).r, dd = SceneTextureLookup(depthUV + float2(0, depthD.y), 1, false).r;
    float dmin = min(min(dl, dr), min(du, dd));
    float edge = saturate((dc - dmin) / max(dmin * 0.10, 1.0) - 1.0);     // the pixel sits behind a nearer neighbour by more than 10% of its depth
    float far = 1.0 - saturate((dmin - 4000.0) / 60000.0);              // fade the ink with distance: far hills stay soft
    outc *= 1.0 - Outline * 0.75 * edge * far * notSky;
}
// Only visible player pixels retain their fine facial/cloth shading. Depth
// agreement prevents a player behind a wall from changing the wall's treatment.
// Character and equipped items keep the same original lighting treatment.
float player = ((abs(Stencil.r - 1.0) < 0.5 || abs(Stencil.r - 2.0) < 0.5) && abs(CustomZ.r - SceneZ.r) < 2.0) ? 1.0 : 0.0;
return lerp(outc, Scene, player * 0.85);
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
    MEL.recompile_material(m); EAL.save_loaded_asset(m)
    return m


def create(name, cls, factory):
    """Reuse named generated assets without emitting an unattended creation error."""
    path = f"/Game/Japan/Materials/{name}"
    a = EAL.load_asset(path) if EAL.does_asset_exist(path) else None
    if a is not None:
        if not isinstance(a, cls):
            raise TypeError(f"Unexpected asset class at {path}: {type(a)}")
        if isinstance(a, unreal.Material):
            MEL.delete_all_material_expressions(a)
        LOG(f"  reused existing {path}")
    else:
        a = AT.create_asset(name, "/Game/Japan/Materials", cls, factory)
    if a is None:
        raise RuntimeError(f"Failed to create {path}")
    return a


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
    MEL.recompile_material(m); EAL.save_loaded_asset(m)
    return m


def instance(name, parent, tex=None, tint=None):
    mi = create(name, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, parent)
    if tex is not None:
        ok = MEL.set_material_instance_texture_parameter_value(mi, "Tex", tex)
        LOG(f"  {name}: Tex <- {tex.get_name()} ok={ok} readback={MEL.get_material_instance_texture_parameter_value(mi, 'Tex')}")
    if tint is not None: MEL.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(*tint, 1.0))
    MEL.update_material_instance(mi); EAL.save_loaded_asset(mi)
    return mi


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
    MEL.recompile_material(m); EAL.save_loaded_asset(m)
    return m


def build_materials(T):
    white = T["T_white"]         # the parameter default must be a real texture: a missing default fails the compile (grey grid material)
    mpc = make_mpc()
    lit = master("M_Painted", white=white); fol = master("M_Foliage", masked=True, white=white, mpc=mpc); sky = master("M_Sky", unlit=True, white=white, fixed_tex=T["T_sky"])
    MI = {}
    MI["LeafBroad"] = instance("MI_LeafBroad", fol, T["T_leaf_broad"]); MI["LeafCedar"] = instance("MI_LeafCedar", fol, T["T_leaf_cedar"])
    MI["LeafPine"] = instance("MI_LeafPine", fol, T["T_leaf_pine"]); MI["LeafOchre"] = instance("MI_LeafOchre", fol, T["T_leaf_ochre"])
    MI["Grass"] = instance("MI_Grass", grass_material(white, mpc), T["T_grass"])
    MI["LeafMaple"] = instance("MI_LeafMaple", fol, T["T_leaf_maple"]); MI["LeafGinkgo"] = instance("MI_LeafGinkgo", fol, T["T_leaf_ginkgo"])
    MI["LeafSmall"] = instance("MI_LeafSmall", fol, T["T_leaf_small"]); MI["Litter"] = instance("MI_Litter", fol, T["T_litter"])
    MI["Flower"] = instance("MI_Flower", fol, T["T_flower"]); MI["LeafOchreSmall"] = instance("MI_LeafOchreSmall", fol, T["T_leaf_ochre_small"])
    MI["LeafMapleLo"] = instance("MI_LeafMapleLo", fol, T["T_leaf_maple_lo"]); MI["LeafGinkgoLo"] = instance("MI_LeafGinkgoLo", fol, T["T_leaf_ginkgo_lo"]); MI["LeafBroadLo"] = instance("MI_LeafBroadLo", fol, T["T_leaf_broad_lo"])
    MI["RoofTile"] = instance("MI_RoofTile", lit, T["T_rooftile"], (0.40, 0.42, 0.48)); MI["FarForest"] = instance("MI_FarForest", lit, T["T_farforest"], (0.50, 0.40, 0.20))
    MI["_cloud"] = cloud_shadow_material(T["T_cloudmask"])
    MI["_painterly"] = painterly_material()
    MI["Bark"] = instance("MI_Bark", lit, T["T_bark"]); MI["Concrete"] = instance("MI_Concrete", lit, T["T_concrete"])
    MI["Ground"] = instance("MI_Ground", lit, T["T_ground"]); MI["Road"] = instance("MI_Road", lit, T["T_road"], (0.34, 0.33, 0.33)); MI["Water"] = instance("MI_Water", lit, T["T_water"])
    MI["Sky"] = instance("MI_Sky", sky, None, (1.35, 1.35, 1.35))
    flat = {"Paint": (0.85, 0.85, 0.82), "Stone": (0.50, 0.50, 0.47), "Vermilion": (0.62, 0.12, 0.06), "Plaster": (0.80, 0.74, 0.62), "Tile": (0.16, 0.17, 0.20),
            "Wood": (0.18, 0.11, 0.07), "Feather": (0.92, 0.92, 0.90), "FeatherDark": (0.10, 0.10, 0.12), "Metal": (0.08, 0.08, 0.09),
            "Rock": (0.30, 0.27, 0.24), "Lattice": (0.14, 0.10, 0.08), "Moss": (0.30, 0.38, 0.16)}
    for k, c in flat.items():
        MI[k] = instance("MI_" + k, lit, white, c)
    return MI


def soft_colour_grade(settings):
    """Soft painted light, retaining broad value gradients and warm/cool depth."""
    values = {
        'color_contrast': unreal.Vector4(.98, .98, .98, 1),
        'color_gain': unreal.Vector4(1.02, 1.0, .98, 1),
        'color_gamma': unreal.Vector4(1.025, 1.025, 1.025, 1),
        'color_gain_shadows': unreal.Vector4(.94, .98, 1.055, 1),
        'color_gain_highlights': unreal.Vector4(1.025, 1.005, .97, 1),
        'bloom_intensity': .18,
        'vignette_intensity': .16,
        'ambient_occlusion_intensity': .45,
    }
    for name, value in values.items():
        settings.set_editor_property('override_' + name, True)
        settings.set_editor_property(name, value)


def assign(mesh_path, MI):
    m = EAL.load_asset(mesh_path)
    if not m: return
    mats = list(m.get_editor_property("static_materials"))
    changed = False
    for i, sm in enumerate(mats):
        slot = str(sm.get_editor_property("imported_material_slot_name")) or str(sm.get_editor_property("material_slot_name"))
        key = slot.split(".")[0]
        if key in MI:
            m.set_material(i, MI[key]); changed = True
        else:
            LOG(f"  no material for slot '{slot}' on {mesh_path}")
    if changed: EAL.save_loaded_asset(m)


# ------------------------------------------------------------------ level
def build_level(terrain_mesh, W, MI):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    map_path = "/Game/Japan/Maps/Slice"
    if True:
        les.new_level(map_path)
        t = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
        t.set_actor_label("Terrain"); t.static_mesh_component.set_static_mesh(terrain_mesh); t.set_mobility(unreal.ComponentMobility.STATIC)
        sun = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 3000))
        # unreal.Rotator(roll, pitch, yaw): the sun sits 44 deg up, shining from the south-west (over the sea) toward the hill
        sun.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=-48.0, yaw=15.0), False)      # sun behind the traveler (west-south-west): the road is lit along its length, tree shadows fall forward
        L = sun.light_component
        L.set_editor_property("forward_shading_priority", 1)
        L.set_mobility(unreal.ComponentMobility.MOVABLE); L.set_intensity(7.0)
        L.set_light_color(unreal.LinearColor(1.0, 0.90, 0.76, 1.0))
        opt(L, "light_source_angle", 5.0); opt(L, "dynamic_shadow_distance_movable_light", 30000.0); opt(L, "dynamic_shadow_cascades", 4)
        opt(L, "cascade_distribution_exponent", 2.5); opt(L, "atmosphere_sun_light", False); opt(L, "shadow_bias", 0.6)
        sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 3000))
        S = sky.light_component; S.set_mobility(unreal.ComponentMobility.MOVABLE)
        S.set_editor_property("real_time_capture", False); S.set_intensity(3.8)     # captured once at load: the painted dome lights the shadows
        S.set_light_color(unreal.LinearColor(0.95, 0.96, 1.0, 1.0))
        opt(S, "lower_hemisphere_color", unreal.LinearColor(0.30, 0.36, 0.46, 1.0))
        fog = eas.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))
        F = fog.component
        F.set_editor_property("fog_density", 0.0); F.set_editor_property("fog_height_falloff", 6.0)   # height fog off: any layer thick enough to see fogs the sky dome; haze lives in the materials   # haze hugs the valleys: thick along the road, thin from above
        opt(F, "second_fog_data", unreal.ExponentialHeightFogData(fog_density=0.0, fog_height_falloff=1.0, fog_height_offset=0.0))   # no tall layer: it fogs the sky dome
        F.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.72, 0.80, 0.90, 1.0)) if hasattr(F, "fog_inscattering_luminance") else None
        opt(F, "fog_inscattering_luminance", unreal.LinearColor(0.62, 0.70, 0.83, 1.0)); opt(F, "start_distance", 3000.0); opt(F, "fog_cutoff_distance", 1200000.0)
        opt(F, "fog_max_opacity", 0.55)
        LOG(f"fog readback: cutoff={F.get_editor_property('fog_cutoff_distance')} density={F.get_editor_property('fog_density')} start={F.get_editor_property('start_distance')}")
        ppv = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
        ppv.set_editor_property("unbound", True)
        s = ppv.settings
        def ov(name, value):
            s.set_editor_property("override_" + name, True); s.set_editor_property(name, value)
        # fixed exposure in EV100: the sun is 7 lux, lit ground sits near EV 3; 1.2 keeps it bright with the painted sky brighter still
        ov("auto_exposure_method", unreal.AutoExposureMethod.AEM_HISTOGRAM); ov("auto_exposure_bias", 1.24)
        ov("auto_exposure_min_brightness", 1.2); ov("auto_exposure_max_brightness", 1.2)
        ov("color_saturation", unreal.Vector4(1.0, 1.0, 1.0, 1.0))
        ov("indirect_lighting_intensity", 3.0); ov("lumen_scene_lighting_quality", 1.0); ov("lumen_final_gather_quality", 1.0)
        ov("dynamic_global_illumination_method", unreal.DynamicGlobalIlluminationMethod.LUMEN)
        ov("film_toe", 0.3); ov("film_shoulder", 0.28); ov("film_slope", 0.7)
        ov("ambient_occlusion_radius", 120.0)
        ov("screen_space_reflection_intensity", 0.0); ov("motion_blur_amount", 0.0)
        soft_colour_grade(s)
        s.set_editor_property("weighted_blendables", unreal.WeightedBlendables(array=[unreal.WeightedBlendable(weight=1.0, object=MI["_painterly"])]))
        ppv.set_editor_property("settings", s)
        ps = W["player_start"]
        p = eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(ps[0] * 100, -ps[1] * 100, ps[2] * 100 + 100))
        p.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=0.0, yaw=-ps[3]), False)
    world = unreal.EditorLevelLibrary.get_editor_world()
    ok = unreal.EditorLoadingAndSavingUtils.save_map(world, map_path)
    if not ok:
        raise RuntimeError(f"Failed to save {map_path}")
    LOG(f"level saved: {map_path} ok={ok}")


def main():
    if os.environ.get('JAPAN_ONLY') == 'original-materials':
        # Targeted rollback: no texture/mesh import, level save, foliage rebuild or water edit.
        white = EAL.load_asset('/Game/Japan/Textures/T_white')
        if not white: raise RuntimeError('Missing original material texture')
        master('M_Painted', white=white)
        from cape_boy_material import create as character_material
        character_material()
        LOG('ORIGINAL MATERIALS RESTORED'); return
    if os.environ.get('JAPAN_ONLY') == 'visuals':
        # Update only the look assets. Keep the level, collisions, characters,
        # animation imports and all authored foliage LODs intact.
        for path in sorted(glob.glob(os.path.join(TEX, 'T_*'))):
            if os.path.basename(path).startswith(('T_grass', 'T_leaf_', 'T_flower')):
                import_texture(path, '/Game/Japan/Textures')
        white = EAL.load_asset('/Game/Japan/Textures/T_white')
        mpc = EAL.load_asset('/Game/Japan/Materials/MPC_Wind')
        if not white or not mpc: raise RuntimeError('Missing world material inputs')
        instance('MI_Grass', grass_material(white, mpc), EAL.load_asset('/Game/Japan/Textures/T_grass'))
        for name in ('Grass_A', 'Grass_B'):
            import_fbx(os.path.join(OUT, 'assets', name + '.fbx'), '/Game/Japan/Assets', name)
            assign('/Game/Japan/Assets/' + name, {'Grass': EAL.load_asset('/Game/Japan/Materials/MI_Grass')})
        import import_foliage_lods
        import_foliage_lods.main(('Grass_A', 'Grass_B'))
        painterly_material()
        world = unreal.EditorLoadingAndSavingUtils.load_map('/Game/Japan/Maps/Slice')
        if not world: raise RuntimeError('Missing playable map')
        volumes = [a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
                   if isinstance(a, unreal.PostProcessVolume)]
        if len(volumes) != 1: raise RuntimeError('Expected one scene colour grade')
        settings = volumes[0].settings
        soft_colour_grade(settings)
        volumes[0].set_editor_property('settings', settings)
        assert unreal.EditorLoadingAndSavingUtils.save_map(world, '/Game/Japan/Maps/Slice')
        LOG('VISUAL MATERIALS COMPLETE'); return
    if os.environ.get("JAPAN_ONLY") == "painterly":      # rebuild just the post-process material (no purge/import)
        painterly_material(); LOG("painterly material rebuilt"); LOG("level saved (painterly only)"); return
    import json
    W = json.load(open(os.path.join(OUT, "world.json")))
    purge()
    T = {}
    for path in sorted(glob.glob(os.path.join(TEX, "T_*"))):
        name = os.path.splitext(os.path.basename(path))[0]
        T[name] = import_texture(path, "/Game/Japan/Textures")
        LOG(f"texture {name}: {T[name]}")
    MI = build_materials(T)
    for path in sorted(glob.glob(os.path.join(OUT, "assets", "*.fbx"))):
        name = os.path.splitext(os.path.basename(path))[0]
        import_fbx(path, "/Game/Japan/Assets", name)
        assign(f"/Game/Japan/Assets/{name}", MI)
    import_fbx(os.path.join(OUT, "terrain.fbx"), "/Game/Japan", "Terrain")
    assign("/Game/Japan/Terrain", MI)
    terrain = EAL.load_asset("/Game/Japan/Terrain")
    if terrain:
        bs = terrain.get_editor_property("body_setup")
        if bs: bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        EAL.save_loaded_asset(terrain)
    # props need collision too (trees, poles, rails): complex-as-simple is fine for a demo; the houses have their own import
    for name in ("Pole", "Pole_Lamp", "Guardrail", "Lantern", "Torii", "Tree_Broad_A", "Tree_Broad_B", "Tree_Broad_C", "Tree_Pine_A", "Tree_Pine_B", "Tree_Cedar_A", "Tree_Cedar_B"):
        m = EAL.load_asset(f"/Game/Japan/Assets/{name}")
        if m:
            bs = m.get_editor_property("body_setup")
            if bs: bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            EAL.save_loaded_asset(m)
    # Every foliage LOD preserves its own source tree, atlas and proportions.
    import import_foliage_lods
    import_foliage_lods.main()
    import runpy
    runpy.run_path(os.path.join(os.path.dirname(__file__), "import_wanderer.py"), run_name="__main__")
    if W.get("village"):
        import import_village
        import_village.main(terrain=False)
    if os.path.exists(os.path.join(OUT,"hidamari","manifest.json")):
        runpy.run_path(os.path.join(os.path.dirname(__file__),"import_hidamari.py"),run_name="__main__")
    if os.path.exists(os.path.join(OUT,"sailboat","manifest.json")):
        runpy.run_path(os.path.join(os.path.dirname(__file__),"import_sailboat.py"),run_name="__main__")
    if W.get("zeppelin"):
        runpy.run_path(os.path.join(os.path.dirname(__file__),"import_zeppelin.py"),init_globals={"ASSETS_ONLY":True},run_name="__main__")
    build_level(terrain, W, MI)


if __name__ == "__main__":
    main()
