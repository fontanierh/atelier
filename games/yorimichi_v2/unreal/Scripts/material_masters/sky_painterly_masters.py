"""Sky and painterly masters from the pinned V1 donor 7eec0f98dd (docs/DECISIONS.md D01).

Original sources remain under adopted/japan/materials/base-materials/source/unreal/Scripts:
shared_materials.py sha256 8cf144f9752bffe771bbddfe984091ad4c288259bc00abba4a64fad5d6678720,
painterly_kernel.py sha256 70f9be7d03f23727829837b2334f3a84691de5bda4189a164c09868feac48077,
material_assets.py sha256 4f48db1203b44c5abca932291ce323f7247a655753167a5f72dfefe5ac4be50f.

The sky specializes master(unlit=True, fixed_tex=T_sky); the painterly graph and its pure kernel are copied below.
No V1 import, filesystem lookup, texture import or save runs here. The V2 importer loads declared reads, clears the
material, accepts the rebuilt graph against its original and owns the save. This self-contained module is copied
and pinned in each material-master record, including the kernel needed to recover Painterly's exact custom code.
"""
import math

try:
    import unreal
except ImportError:   # preparation and donor comparisons do not need the editor
    unreal = None


def _material(package):
    """Use the destination material the importer cleared, or create the scratch destination it requested."""
    folder, name = package.rsplit('/', 1)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        return unreal.EditorAssetLibrary.load_asset(package)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def _node(material, cls, x, y, **props):
    """Donor material_assets.py 34-38: create an expression with its stated properties."""
    expression = unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)
    for key, value in props.items():
        expression.set_editor_property(key, value)
    return expression


def _link(source, output, target, input_name):
    """Donor material_assets.py 41-42: connect the named source output and target input."""
    unreal.MaterialEditingLibrary.connect_material_expressions(source, output, target, input_name)


def sky_material(package, reads, *, texture):
    """@cc [owner:fontanierh,label:correctness] sky-fixed-unlit-donor
    Preserve the donor's unlit fixed sky sample and Tint graph, including is_sky=False and its usage flags. The declared
    texture must already be loaded before the destination is touched; compiling the graph never saves a package.
    Donor: shared_materials.py master, 169-221, called with unlit=True and fixed_tex=T_sky.
    """
    fixed_tex = reads[texture]
    MEL = unreal.MaterialEditingLibrary
    m = _material(package)
    tex = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSample, -700, 0)
    tex.set_editor_property('texture', fixed_tex)
    tint = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -700, 300)
    tint.set_editor_property('parameter_name', 'Tint')
    tint.set_editor_property('default_value', unreal.LinearColor(1, 1, 1, 1))
    mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -350, 100)
    MEL.connect_material_expressions(tex, 'RGB', mul, 'A')
    MEL.connect_material_expressions(tint, '', mul, 'B')
    MEL.connect_material_property(mul, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    m.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property('two_sided', True)
    m.set_editor_property('is_sky', False)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    m.set_editor_property('used_with_skeletal_mesh', True)
    MEL.recompile_material(m)
    return m


# painterly_kernel.py 9-57, copied without changing its arithmetic or emitted HLSL.
def kernel():
    taps = []
    for y in range(-2, 3):
        for x in range(-2, 3):
            if x * x + y * y > 5:
                continue
            u, v = x / math.sqrt(5), y / math.sqrt(5)
            weights = []
            for k in range(8):
                a = k * math.pi / 4
                px = u * math.cos(a) + v * math.sin(a)
                py = -u * math.sin(a) + v * math.cos(a)
                w = max(0.0, px + 0.35 - 3.5 * py * py)
                weights.append(w * w * math.exp(-2.5 * (u * u + v * v)))
            taps.append((u, v, weights))
    totals = [sum(t[2][k] for t in taps) for k in range(8)]
    return [(x, y, tuple(w / totals[k] for k, w in enumerate(ws))) for x, y, ws in taps]


def painterly_shader():
    lines = [
        "float3 outc = Scene.rgb;",
        "float player = ((abs(Stencil.r - 1.0) < 0.5 || abs(Stencil.r - 2.0) < 0.5) && abs(CustomZ.r - SceneZ.r) < 2.0) ? 1.0 : 0.0;",
        # Simplify far woodland into painted masses while keeping nearby grass
        # and character silhouettes readable. SceneZ is linear depth in cm.
        "float distancePaint = smoothstep(1800.0, 14000.0, SceneZ.r);",
        "float strength = lerp(Strength, Strength + (1.0 - Strength) * 0.25, distancePaint);",
        "float weight = strength * (1.0 - player * 0.85);",
        # Fast [branch] early-out on sky (> 500,000 cm) and near-zero effective weight: saves 23 scene reads/pixel,
        # while compositing zero-texture Ghibli Mie sun-glow & sunlit-cream/lavender horizon cumulus on sky dome rays!
        "[branch] if (SceneZ.r > 500000.0 || SceneZ.r > SkyDepth * 0.85 || (weight <= 0.005 && Toon <= 0.005 && Outline <= 0.005)) {",
        "    float3 skyCol = Scene.rgb;",
        "    [branch] if (SceneZ.r > 1200000.0) {",
        "        float3 rd = normalize(-Parameters.CameraVector);",
        "        [branch] if (rd.z > 0.015) {",
        "            float3 sunD = normalize(ResolvedView.DirectionalLightDirection.xyz + float3(0.0, 0.0, 1e-5));",
        "            float mu = saturate(dot(rd, sunD));",
        "            float horBand = exp(-max(rd.z - 0.015, 0.0) * 6.5);",
        "            skyCol += float3(0.18, 0.13, 0.06) * (pow(mu, 10.0) * 0.55 + pow(mu, 3.0) * 0.22 * horBand);",
        "            float2 hdir = rd.xy / max(length(rd.xy), 1e-4);",
        "            float c1 = sin(hdir.x * 5.0 + hdir.y * 3.0 + sin(hdir.y * 7.0 - hdir.x * 4.0) * 0.55);",
        "            float c2 = sin(hdir.y * 9.0 - hdir.x * 6.0 + 1.3) * 0.45 + sin(hdir.x * 15.0 + hdir.y * 11.0) * 0.22;",
        "            float topH = 0.085 + 0.052 * c1 + 0.026 * c2;",
        "            float baseH = 0.032 + 0.008 * sin(hdir.x * 3.0 - hdir.y * 4.0);",
        "            float billow = smoothstep(topH + 0.014, topH - 0.010, rd.z) * smoothstep(baseH - 0.010, baseH + 0.012, rd.z);",
        "            float cluster = smoothstep(0.08, 0.52, c1 + 0.55 * c2);",
        "            float cmask = billow * cluster * 0.58;",
        "            float crown = saturate((rd.z - baseH) / max(topH - baseH, 0.012));",
        "            float3 cShade = float3(0.68, 0.73, 0.88);",
        "            float3 cLit = lerp(float3(0.97, 0.95, 0.91), float3(1.00, 0.94, 0.84), pow(mu, 3.0));",
        "            float3 cCol = lerp(cShade, cLit, smoothstep(0.18, 0.78, crown + mu * 0.16));",
        "            skyCol = lerp(skyCol, cCol, cmask);",
        "        }",
        "    }",
        "    return skyCol;",
        "}",
        "[branch] if (weight > 0.005) {",
        "float radius = clamp(Radius * (1.0 + distancePaint), 1.0, 8.0);",
    ]
    for k in range(8):
        lines.append(f"float3 m{k} = 0, s{k} = 0;")
    for i, (x, y, weights) in enumerate(kernel()):
        sample = "Scene.rgb" if x == 0 and y == 0 else f"SceneTextureLookup(clamp(uv + float2({x:.9f}, {y:.9f}) * radius * d, uvMin, uvMax), 14, true).rgb"
        lines.append(f"float3 c{i} = {sample};")
        lines.append(f"float3 c2_{i} = c{i} * c{i};")
        for k, weight in enumerate(weights):
            if weight > 0:
                lines.append(f"m{k} += c{i} * {weight:.10f}; s{k} += c2_{i} * {weight:.10f};")
    lines.append("float3 acc = 0; float wt = 0;")
    for k in range(8):
        lines.extend([
            f"float3 var{k} = s{k} - m{k} * m{k};",
            f"float v{k} = max(0.0, var{k}.r + var{k}.g + var{k}.b);",
            # (sqrt(v) * 16)^4 == 65536 * v^2; no sqrt/pow required.
            f"float w{k} = rcp(1.0 + 65536.0 * v{k} * v{k});",
            f"acc += m{k} * w{k}; wt += w{k};",
        ])
    lines.extend(["outc = lerp(Scene.rgb, acc / max(wt, 1e-8), strength);", "}"])
    return "\n".join(lines)


# shared_materials.py 103-166; only creation, helper names and save ownership changed.
def painterly_material(package, reads):
    """@cc [owner:fontanierh,label:correctness] painterly-donor-graph-and-kernel
    The post-tonemapping graph, four scene-texture IDs, runtime parameter defaults and kernel-generated HLSL equal the
    donor shared_materials.py 103-166. Only the V2 importer saves the accepted destination.

    Post-process look: sparse eight-sector Kuwahara (21 taps independent of brush size), then an
    optional adventure-style soft toon pass (luminance quantized into a few bands with smooth steps, thin depth-only
    outlines, the sky excluded by depth). Every knob is a scalar parameter driven at runtime by the settings menu."""
    U = unreal
    MEL = U.MaterialEditingLibrary
    m = _material(package)
    m.set_editor_property("material_domain", U.MaterialDomain.MD_POST_PROCESS)
    m.set_editor_property("blendable_location", U.BlendableLocation.BL_SCENE_COLOR_AFTER_TONEMAPPING)
    scene = _node(m, U.MaterialExpressionSceneTexture, -700, 0, scene_texture_id=U.SceneTextureId.PPI_POST_PROCESS_INPUT0)
    stencil = _node(m, U.MaterialExpressionSceneTexture, -900, -180, scene_texture_id=U.SceneTextureId.PPI_CUSTOM_STENCIL)
    custom_depth = _node(m, U.MaterialExpressionSceneTexture, -900, -300, scene_texture_id=U.SceneTextureId.PPI_CUSTOM_DEPTH)
    scene_depth = _node(m, U.MaterialExpressionSceneTexture, -900, -420, scene_texture_id=U.SceneTextureId.PPI_SCENE_DEPTH)
    params = [("Strength", 0.35), ("Radius", 2.0), ("Toon", 0.0), ("Bands", 5.0), ("Soft", 0.5), ("Outline", 0.0), ("SkyDepth", 600000.0)]
    pnodes = [_node(m, U.MaterialExpressionScalarParameter, -700, 200 + 90 * i, parameter_name=n, default_value=v) for i, (n, v) in enumerate(params)]
    code = """
float2 uv = GetDefaultSceneTextureUV(Parameters, 14);
// SceneTexture UVs use the backing texture, which may differ from viewport resolution.
float2 d = GetSceneTextureBufferSize(14).zw;
float4 uvBounds = GetSceneTextureUVMinMax(14);
float2 uvMin = uvBounds.xy, uvMax = uvBounds.zw;
""" + painterly_shader() + """
[branch] if (Toon > 0.001 || Outline > 0.001)
{
    float2 depthUV = GetDefaultSceneTextureUV(Parameters, 1);
    float2 depthD = GetSceneTextureBufferSize(1).zw;
    float dc = SceneZ.r;
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
return lerp(outc, Scene.rgb, player * 0.85);
"""
    cust = _node(m, U.MaterialExpressionCustom, -300, 100, code=code, output_type=U.CustomMaterialOutputType.CMOT_FLOAT3, description="Painterly")
    ins = []
    for name in ["Scene", "Stencil", "CustomZ", "SceneZ"] + [n for n, _ in params]:
        ci = U.CustomInput(); ci.set_editor_property("input_name", name); ins.append(ci)
    cust.set_editor_property("inputs", ins)
    _link(scene, "Color", cust, "Scene")
    _link(stencil, "Color", cust, "Stencil")
    _link(custom_depth, "Color", cust, "CustomZ")
    _link(scene_depth, "Color", cust, "SceneZ")
    for (n, _), pn in zip(params, pnodes): _link(pn, "", cust, n)
    MEL.connect_material_property(cust, "", U.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    return m
