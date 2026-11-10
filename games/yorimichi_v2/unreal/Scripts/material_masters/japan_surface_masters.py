"""Four Japan surface masters prepared from donor 7eec0f98dd; no native acceptance is claimed here.

The generator graphs, HLSL, node order and constants come from shared_materials.py (M_Painted,
M_Foliage, M_Grass) and import_village.py (M_Village). The separately pinned master_haze helper owns
the shared atmosphere/sea constants and graph. Foliage and camera fading remain in this builder.
There are no runtime donor imports. Reads are supplied by the importer; only the importer saves packages.
Source hashes and the native comparison requirements are in docs/inventory/japan-surfaces-prep.md.
"""
from . import master_haze as haze

try:
    import unreal
except ImportError:
    unreal = None


def _material(package):
    """Create or load the destination; the importer has already emptied an existing graph."""
    folder, name = package.rsplit('/', 1)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        return unreal.EditorAssetLibrary.load_asset(package)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def node(material, cls, x, y, **properties):
    """The donor material_assets.node helper, with the editor obtained at call time."""
    expression = unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)
    for key, value in properties.items():
        expression.set_editor_property(key, value)
    return expression


def link(source, output, destination, input_name):
    assert unreal.MaterialEditingLibrary.connect_material_expressions(source, output, destination, input_name)


def _finish(material):
    unreal.MaterialEditingLibrary.recompile_material(material)
    return material


def enable_distance_fade(material):
    # HISM only blends LODs when EVERY section opts in, including opaque bark.
    material.set_editor_property('dithered_lod_transition',True)
    edit = unreal.MaterialEditingLibrary
    source = edit.get_material_property_input_node(material,unreal.MaterialProperty.MP_OPACITY_MASK)
    if source.get_editor_property('desc') == 'Japan instance distance fade': return
    output = edit.get_material_property_input_node_output_name(material,unreal.MaterialProperty.MP_OPACITY_MASK)
    fade = edit.create_material_expression(material,unreal.MaterialExpressionPerInstanceFadeAmount,-300,-350)
    multiply = edit.create_material_expression(material,unreal.MaterialExpressionMultiply,0,-350)
    multiply.set_editor_property('desc','Japan instance distance fade')
    assert edit.connect_material_expressions(source,output,multiply,'A')
    assert edit.connect_material_expressions(fade,'',multiply,'B')
    assert edit.connect_material_property(multiply,'',unreal.MaterialProperty.MP_OPACITY_MASK)

def wind_graph(m, mpc):
    """World position offset: gusting sway along the wind + a push away from the player, scaled by vertex colour R"""
    MEL = unreal.MaterialEditingLibrary
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

def _shared_material(package, white, *, masked=False, mpc=None):
    """The lit branch of shared_materials.master, with its supplied white texture and optional wind collection."""
    MEL = unreal.MaterialEditingLibrary
    U = unreal
    m = _material(package)
    tex = MEL.create_material_expression(m, U.MaterialExpressionTextureSampleParameter2D, -700, 0)
    tex.set_editor_property('parameter_name', 'Tex')
    tex.set_editor_property('texture', white)
    tint = MEL.create_material_expression(m, U.MaterialExpressionVectorParameter, -700, 300)
    tint.set_editor_property('parameter_name', 'Tint')
    tint.set_editor_property('default_value', U.LinearColor(1, 1, 1, 1))
    mul0 = MEL.create_material_expression(m, U.MaterialExpressionMultiply, -350, 100)
    MEL.connect_material_expressions(tex, 'RGB', mul0, 'A')
    MEL.connect_material_expressions(tint, '', mul0, 'B')
    mul, haze_glow = haze.apply(unreal, m, mul0, x=260, y=300)
    MEL.connect_material_property(haze_glow, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    if masked:
        vc = node(m, U.MaterialExpressionVertexColor, -350, -150)
        gg = node(m, U.MaterialExpressionComponentMask, -200, -150, r=False, g=True, b=False, a=False)
        link(vc, '', gg, '')
        sh = node(m, U.MaterialExpressionMultiply, -50, -150, const_b=0.5)
        link(gg, '', sh, 'A')
        sh2 = node(m, U.MaterialExpressionAdd, 80, -150, const_b=0.5)
        link(sh, '', sh2, 'A')
        dark = node(m, U.MaterialExpressionMultiply, 200, 0)
        link(mul, '', dark, 'A')
        link(sh2, '', dark, 'B')
        MEL.connect_material_property(dark, '', U.MaterialProperty.MP_BASE_COLOR)
        m.set_editor_property('shading_model', U.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
        ss = node(m, U.MaterialExpressionMultiply, 320, 120, const_b=0.22)
        link(dark, '', ss, 'A')
        MEL.connect_material_property(ss, '', U.MaterialProperty.MP_SUBSURFACE_COLOR)
    else:
        MEL.connect_material_property(mul, '', U.MaterialProperty.MP_BASE_COLOR)
    rough = MEL.create_material_expression(m, U.MaterialExpressionConstant, -350, 350)
    rough.set_editor_property('r', 1.0)
    spec = MEL.create_material_expression(m, U.MaterialExpressionConstant, -350, 450)
    spec.set_editor_property('r', 0.0)
    MEL.connect_material_property(rough, '', U.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(spec, '', U.MaterialProperty.MP_SPECULAR)
    if masked:
        m.set_editor_property('blend_mode', U.BlendMode.BLEND_MASKED)
        m.set_editor_property('two_sided', True)
        m.set_editor_property('opacity_mask_clip_value', 0.4)
        MEL.connect_material_property(tex, 'A', U.MaterialProperty.MP_OPACITY_MASK)
        enable_distance_fade(m)
        if mpc is not None:
            wind_graph(m, mpc)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    m.set_editor_property('used_with_skeletal_mesh', True)
    return m


# Fresh camera-fade overlay from see_through.py. No collection creation, instance edits or upgrade path.

TAG = 'Japan see-through 2'

DITHER = ('float2 px = Parameters.SvPosition.xy + float(View.StateFrameIndexMod8) * float2(32.665, 11.815);'
          ' float n = frac(52.9829189 * frac(dot(px, float2(0.06711056, 0.00583715))));'
          ' return keep > n ? 1.0 : 0.0;')

INSTANCE = (' float3 bc = GetPrimitiveData(Parameters).InstanceLocalBoundsCenter;'
            ' float3 be = GetPrimitiveData(Parameters).InstanceLocalBoundsExtent;'
            ' float4 logical = GetPrimitiveData(Parameters).CustomPrimitiveData[1];'
            ' if (logical.w > 0.5) {'
            ' bc = GetPrimitiveData(Parameters).CustomPrimitiveData[0].yzw; be = logical.xyz; }'
            ' float3 c = O + TransformLocalVectorToWorld(Parameters, bc);'
            ' float3 e = abs(TransformLocalVectorToWorld(Parameters, float3(be.x, 0.0, 0.0)))'
            ' + abs(TransformLocalVectorToWorld(Parameters, float3(0.0, be.y, 0.0)))'
            ' + abs(TransformLocalVectorToWorld(Parameters, float3(0.0, 0.0, be.z)));'
            ' r = max(e.x, e.y); float h = r > 150.0 ? e.z : max(e.z - r, 0.0);'
            ' A = c - float3(0.0, 0.0, h); B = c + float3(0.0, 0.0, h);')

BETWEEN = (' float3 ab = B - A; float ab2 = dot(ab, ab); bool big = r > 150.0; float rb = big ? 40.0 : r;'
           ' [branch] if (length((A + B) * 0.5 - C) < sqrt(ab2) * 0.5 + r + length(F.xyz - C) + F.w + 300.0)'
           ' {'
           ' float t0 = saturate(dot(C - A, ab) / max(ab2, 1.0));'
           ' float nearness = 1.0 - smoothstep(G.z * 0.5, G.z, length(A + ab * t0 - C) - rb);'
           ' float cover = 0.0; float3 w = E.xyz - A;'
           ' for (int k = 0; k < 3; k++)'
           ' {'
           ' float3 d1 = F.xyz + float3(0.0, 0.0, (k == 0 ? 0.8 : (k == 1 ? 0.15 : -0.55)) * F.w) - E.xyz;'
           ' float aa = max(dot(d1, d1), 1.0); float bb = dot(d1, ab); float cc = dot(d1, w); float ff = dot(ab, w);'
           # closest points between the sight line E + d1 sv and the piece A + ab tv (sv, tv in 0..1)
           ' float sv = saturate(-cc / aa); float tv = 0.0;'
           ' if (ab2 > 1.0)'
           ' {'
           ' float den = aa * ab2 - bb * bb;'
           ' sv = den > aa * ab2 * 0.0001 ? saturate((bb * ff - cc * ab2) / den) : 0.0;'
           ' tv = (bb * sv + ff) / ab2;'
           ' if (tv < 0.0) { tv = 0.0; sv = saturate(-cc / aa); }'
           ' else if (tv > 1.0) { tv = 1.0; sv = saturate((bb - cc) / aa); }'
           ' }'
           ' float3 q = A + ab * tv; float len = sqrt(aa);'
           ' float gap = length(E.xyz + d1 * sv - q) - rb - G.y * sv;'
           ' float depth = dot(q - E.xyz, d1) / len;'
           ' float front = 1.0 - smoothstep(len - 30.0, len - 5.0, depth);'
           ' float reach = big ? 1.0 - smoothstep(G.w, G.w + 100.0, depth) : 1.0;'
           ' cover = max(cover, (1.0 - smoothstep(0.0, 30.0, gap)) * front * reach);'
           ' }'
           ' fade = G.x * max(nearness, cover);'
           ' }')

LENS = ('float3 v = P - C; float s = length(v);'
        ' float keep = 1.0 - saturate(W);'
        ' float2 lens = (M > 0.5 ? float2(10.0, 40.0) : float2(5.0, 15.0)) * K.z;'
        ' keep = keep * lerp(1.0, smoothstep(lens.x, lens.y, s), saturate(X.z));')

HOLE = (' [branch] if (X.w > 0.0)'
        ' {'
        ' float4 Y = X * float4(K.x, K.y, 1.0, 1.0); float3 d = v / max(s, 0.001);'
        ' float3 foot = F.xyz - float3(0.0, 0.0, F.w); float3 w0 = C - foot; float b = d.z;'
        # closest approach between the view ray and the body's axis (feet to head)
        ' float t = (b * w0.z - dot(d, w0)) / max(1.0 - b * b, 0.0001);'
        ' float u = clamp(w0.z + t * b, 0.0, 2.0 * F.w);'
        ' t = max(dot(foot + float3(0.0, 0.0, u) - C, d), 0.0);'
        ' float gap = length(C + d * t - foot - float3(0.0, 0.0, u));'
        ' float rad = max(Y.x, 1.0);'
        ' float above = smoothstep(foot.z + 5.0, foot.z + 30.0, P.z);'
        ' float cut = (1.0 - smoothstep(rad * 0.6, rad, gap)) * smoothstep(Y.y * 0.5, Y.y * 1.5, t - s) * above;')

HOLE_END = ' keep = keep * (1.0 - saturate(cut * X.w)); }'

def whole():
    """The donor WHOLE code for instance mode 1; the shared parents do not use merged-piece mode 2."""
    shape = ' if (M < 1.5) {' + INSTANCE + ' }'
    return ('float fade = 0.0;'
            ' [branch] if (G.x > 0.0 && M > 0.5 && M < 1.5)'
            ' {'
            ' float3 A = O; float3 B = O; float r = 0.0;' + shape + BETWEEN +
            ' }'
            ' return fade;')

def _see_custom(m, x, y, code, names):
    kind = unreal.CustomMaterialOutputType.CMOT_FLOAT1
    n = node(m, unreal.MaterialExpressionCustom, x, y, code=code, output_type=kind, description=TAG)
    args = []
    for k in names:
        a = unreal.CustomInput(); a.set_editor_property('input_name', k); args.append(a)
    n.set_editor_property('inputs', args)
    return n

def _see_params(m, collection, x, y, *names):
    """CollectionParameter nodes reading the named vectors of the collection."""
    mpc = collection
    return [node(m, unreal.MaterialExpressionCollectionParameter, x, y+110*k, collection=mpc, parameter_name=n)
            for k, n in enumerate(names)]

def _see_into_mask(m, keep, x, y):
    """The donor's fresh overlay: shadow passes retain pixels and the old opacity input stays multiplied in."""
    MEL = unreal.MaterialEditingLibrary
    opacity = unreal.MaterialProperty.MP_OPACITY_MASK
    source = MEL.get_material_property_input_node(m, opacity)
    output = MEL.get_material_property_input_node_output_name(m, opacity) if source is not None else ''
    switch = node(m, unreal.MaterialExpressionShadowReplace, x, y)
    one = node(m, unreal.MaterialExpressionConstant, x-200, y+120, r=1.)
    link(keep, '', switch, 'Default'); link(one, '', switch, 'Shadow')
    out = switch
    if source is not None:
        out = node(m, unreal.MaterialExpressionMultiply, x+250, y)
        link(source, output, out, 'A'); link(switch, '', out, 'B')
    out.set_editor_property('desc', TAG)
    assert MEL.connect_material_property(out, '', opacity)


def _see_through(m, collection, *, scale, whole_fade=True):
    """Apply the donor fresh world overlay. The importer supplies the existing shared collection and an empty rebuild;
    this path cannot create/change that collection, patch instances, or upgrade an older live graph.
    """
    x, y = -900, 1400
    names = ['P', 'C', 'F', 'X', 'W', 'M', 'K']
    keep = _see_custom(m, x, y, LENS + HOLE + HOLE_END + ' ' + DITHER, names)
    p = node(m, unreal.MaterialExpressionWorldPosition, x-450, y)
    c = node(m, unreal.MaterialExpressionCameraPositionWS, x-450, y+100)
    link(p, '', keep, 'P'); link(c, '', keep, 'C')
    focus, cut = _see_params(m, collection, x-450, y+200, 'Focus', 'Cut')
    link(focus, '', keep, 'F'); link(cut, '', keep, 'X')
    # The group's fade mode (AJapanWorld sets it); 0, solid, where nothing sets it.
    mode = node(m, unreal.MaterialExpressionScalarParameter, x-450, y+560, parameter_name='FadeMode', default_value=0.,
                use_custom_primitive_data=True, primitive_data_index=0)
    link(mode, '', keep, 'M')
    k = node(m, unreal.MaterialExpressionVectorParameter, x-450, y+660, parameter_name='CutScale',
             default_value=unreal.LinearColor(*(scale or (1., 1., 1., 1.))))
    link(k, 'RGBA', keep, 'K')
    if whole_fade:
        inputs = ['M', 'O', 'P', 'C', 'E', 'F', 'G']
        fade = _see_custom(m, x-900, y-400, whole(), inputs)
        link(mode, '', fade, 'M'); link(p, '', fade, 'P'); link(c, '', fade, 'C'); link(focus, '', fade, 'F')
        link(node(m, unreal.MaterialExpressionObjectPositionWS, x-1350, y-400), '', fade, 'O')
        eye, amount = _see_params(m, collection, x-1350, y-300, 'Eye', 'Fade')
        link(eye, '', fade, 'E'); link(amount, '', fade, 'G')
        # Per vertex, handed to the pixels: the value is the same over a whole instance or piece.
        between = node(m, unreal.MaterialExpressionVertexInterpolator, x-450, y-400)
        link(fade, '', between, ''); link(between, '', keep, 'W')
    else:
        link(node(m, unreal.MaterialExpressionConstant, x-450, y-100, r=0.), '', keep, 'W')
    _see_into_mask(m, keep, x+300, y)
    return True

def painted_material(package, reads, *, white, see_through):
    """M_Painted: donor shared_materials.master, the opaque lit branch, default texture T_white."""
    texture, collection = reads[white], reads[see_through]
    material = _shared_material(package, texture)
    _see_through(material, collection, scale=(1., 1., 1., 1.))
    return _finish(material)


def foliage_material(package, reads, *, white, wind, see_through):
    """M_Foliage: two-sided foliage, distance fade and vertex-colour-scaled wind/player push."""
    texture, collection, camera = reads[white], reads[wind], reads[see_through]
    material = _shared_material(package, texture, masked=True, mpc=collection)
    _see_through(material, camera, scale=(1., 1., 2., 1.))
    return _finish(material)


def grass_material(package, reads, *, white, wind, coverage, see_through):
    """@cc [owner:fontanierh,label:correctness] japan-grass-keeps-coverage-and-normal
    Grass keeps the donor world-up normal on both faces, temporal instance fading, and wind scaled by .28.
    Its white texture, wind and camera collections, and engine coverage function must all be supplied before touching a material.
    """
    texture, collection, function, camera = reads[white], reads[wind], reads[coverage], reads[see_through]
    MEL = unreal.MaterialEditingLibrary
    m = _shared_material(package, texture, masked=True, mpc=collection)
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
    dither.set_material_function(function)
    assert MEL.connect_material_expressions(fade, '', dither, 'Alpha Threshold')
    assert MEL.connect_material_property(dither, '', unreal.MaterialProperty.MP_OPACITY_MASK)
    wind = MEL.get_material_property_input_node(m, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    gentle = node(m, unreal.MaterialExpressionMultiply, 250, 1200, const_b=.28)
    link(wind, '', gentle, 'A')
    MEL.connect_material_property(gentle, '', unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    _see_through(m, camera, scale=(1., 1., 2.5, 1.), whole_fade=False)
    return _finish(m)

def village_material(package, reads):
    """M_Village: donor vertex-colour conversion, paper-light glow, shared haze and vertex-alpha wind."""
    MEL = unreal.MaterialEditingLibrary
    m = _material(package)
    def node(cls,x,y,**kwargs):
        e=MEL.create_material_expression(m,cls,x,y)
        for k,v in kwargs.items():e.set_editor_property(k,v)
        return e
    def link(a,ao,b,bi):assert MEL.connect_material_expressions(a,ao,b,bi)
    vc=node(unreal.MaterialExpressionVertexColor,-650,0)
    linear=node(unreal.MaterialExpressionCustom,-430,0,
        code='return lerp(C/12.92,pow((C+0.055)/1.055,2.4),step(0.04045,C));',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    arg=unreal.CustomInput();arg.set_editor_property('input_name','C');linear.set_editor_property('inputs',[arg])
    link(vc,'',linear,'C')
    rough=node(unreal.MaterialExpressionConstant,200,450,r=1.0)
    spec=node(unreal.MaterialExpressionConstant,200,550,r=0.0)
    MEL.connect_material_property(rough,'',unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(spec,'',unreal.MaterialProperty.MP_SPECULAR)
    # Only paper lights emit noticeably. A universal fill flattened the timber.
    fill=node(unreal.MaterialExpressionCustom,200,650,
        code='float lamp=step(.80,C.r)*step(.35,C.g)*step(C.g,.72)*step(C.b,.30); return C*(.06+lamp*.8);',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    arg=unreal.CustomInput();arg.set_editor_property('input_name','C');fill.set_editor_property('inputs',[arg])
    link(linear,'',fill,'C')
    # aerial perspective shared with the sea and the land (atmosphere.py)
    base,glow=haze.apply(unreal,m,linear,fill,x=420,y=0)
    assert MEL.connect_material_property(base,'',unreal.MaterialProperty.MP_BASE_COLOR)
    assert MEL.connect_material_property(glow,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    wind=node(unreal.MaterialExpressionCustom,400,850,
        code='float phase=T*1.7+P.x*.002+P.y*.003; return float3(sin(phase)*2.2,cos(phase*.81)*1.3,sin(phase*1.3)*.4)*W*W;',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    args=[]
    for key in ('T','P','W'):
        arg=unreal.CustomInput();arg.set_editor_property('input_name',key);args.append(arg)
    wind.set_editor_property('inputs',args)
    time=node(unreal.MaterialExpressionTime,-400,850)
    pos=node(unreal.MaterialExpressionWorldPosition,-400,950)
    link(time,'',wind,'T');link(pos,'',wind,'P');link(vc,'A',wind,'W')
    MEL.connect_material_property(wind,'',unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    return _finish(m)
