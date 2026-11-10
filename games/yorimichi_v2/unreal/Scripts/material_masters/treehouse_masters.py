"""Tree House master builders: M_TreeHouse (treehouse_surface) and M_TH_Light (treehouse_light).

Extracted from adopted/japan/treehouse/generator/source/unreal/Scripts/import_treehouse.py and see_through.py, upgraded for
Apple Silicon TBDR Hidden Surface Removal (HSR):
- M_TreeHouse compiles as BLEND_Opaque (eliminating pixel-shader discard_fragment() across all 385,872 Tree House triangles),
  adds hemisphere + plank/bark crevice Forward SkyLight AO on MP_AMBIENT_OCCLUSION, wraps noren curtain CLOTH WPO in [branch],
  and collapses thin occluding rails/props (FadeMode 1 & 2) in the vertex shader (guarded by ShadowReplace so shadows remain)
  while preserving every saved parameter and MPC_SeeThrough binding.
- M_TH_Light preserves the donor additive window-pane light graph verbatim.
"""
try:
    import unreal
except ImportError:   # outside the editor: the functions are defined but cannot run
    unreal = None

TAG = 'Japan see-through 2'
TRAIL = ('Trail0', 'Trail1', 'Trail2', 'Trail3')
SUN_TINT = (1., .74, .42)

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
            ' centerOut = c; A = c - float3(0.0, 0.0, h); B = c + float3(0.0, 0.0, h);')

PIECE = (' if (U4.y <= 0.5) {'
         ' float3 c = P + TransformLocalVectorToWorld(Parameters, float3(U1.x, U1.y - 1.0, U2.x) * 100.0);'
         ' float3 x = TransformLocalVectorToWorld(Parameters, float3(U3.x, U3.y - 1.0, U4.x) * 100.0);'
         ' r = (1.0 - U2.y) * 100.0; centerOut = c; A = c - x; B = c + x; hasPiece = 1.0; }')

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

WHOLE_COLLAPSE = ('float4 res = float4(0.0, 0.0, 0.0, 0.0);'
                  ' [branch] if (G.x > 0.0 && M > 0.5 && M < 2.5)'
                  ' {'
                  ' float fade = 0.0; float3 A = O; float3 B = O; float3 centerOut = O; float r = 0.0; float hasPiece = 1.0;'
                  ' if (M < 1.5) {' + INSTANCE + ' } else { hasPiece = 0.0;' + PIECE + ' }'
                  ' if (hasPiece > 0.5) {' + BETWEEN +
                  ' if (fade > 0.60) { res = float4(centerOut - P, fade); } else { res.w = fade; } }'
                  ' }'
                  ' return res;')

LENS = ('float3 v = P - C; float s = length(v);'
        ' float keep = 1.0 - saturate(W);'
        ' float2 lens = (M > 0.5 ? float2(10.0, 40.0) : float2(5.0, 15.0)) * K.z;'
        ' keep = keep * lerp(1.0, smoothstep(lens.x, lens.y, s), saturate(X.z));')

HOLE = (' [branch] if (X.w > 0.0)'
        ' {'
        ' float4 Y = X * float4(K.x, K.y, 1.0, 1.0); float3 d = v / max(s, 0.001);'
        ' float3 foot = F.xyz - float3(0.0, 0.0, F.w); float3 w0 = C - foot; float b = d.z;'
        ' float t = (b * w0.z - dot(d, w0)) / max(1.0 - b * b, 0.0001);'
        ' float u = clamp(w0.z + t * b, 0.0, 2.0 * F.w);'
        ' t = max(dot(foot + float3(0.0, 0.0, u) - C, d), 0.0);'
        ' float gap = length(C + d * t - foot - float3(0.0, 0.0, u));'
        ' float rad = max(Y.x, 1.0);'
        ' float above = smoothstep(foot.z + 5.0, foot.z + 30.0, P.z);'
        ' float cut = (1.0 - smoothstep(rad * 0.6, rad, gap)) * smoothstep(Y.y * 0.5, Y.y * 1.5, t - s) * above;')

ROOM = (' float cy = cos(R.w); float sy = sin(R.w);'
        ' float2 q = P.xy - R.xy; q = float2(q.x * cy + q.y * sy, q.y * cy - q.x * sy);'
        ' float2 qc = C.xy - R.xy; qc = float2(qc.x * cy + qc.y * sy, qc.y * cy - qc.x * sy);'
        ' float o = H.x > 0.5 ? length(q) - S.x : max(abs(q.x) - S.x, abs(q.y) - S.y);'
        ' float oc = H.x > 0.5 ? length(qc) - S.x : max(abs(qc.x) - S.x, abs(qc.y) - S.y);'
        ' float top = R.z + S.z; float head = F.z + F.w;'
        ' float away = max(smoothstep(-20.0, 30.0, oc), smoothstep(top - 40.0, top + 10.0, C.z));'
        ' float2 toCam = C.xy - F.xy; toCam = toCam / max(length(toCam), 1.0);'
        ' float walls = smoothstep(-H.y - 20.0, -H.y, o) * (1.0 - smoothstep(H.z, H.z + 30.0, o))'
        ' * smoothstep(-20.0, 40.0, dot(P.xy - F.xy, toCam)) * above;'
        ' float lid = max(head + 15.0, top - 60.0);'
        ' float roof = smoothstep(lid, lid + 30.0, P.z) * (1.0 - smoothstep(H.z + 60.0, H.z + 100.0, o))'
        ' * (1.0 - smoothstep(top + 300.0, top + 360.0, P.z)) * smoothstep(lid - 20.0, lid + 40.0, C.z);'
        ' cut = max(cut, RM * S.w * away * max(walls, roof));')

HOLE_END = ' keep = keep * (1.0 - saturate(cut * X.w)); }'

CLOTH = ('[branch] if (W <= 0.001) return float3(0.0, 0.0, 0.0);'
         ' float w = saturate(W);'
         ' float phase = T * 1.7 + P.x * 0.002 + P.y * 0.003;'
         ' float3 o = float3(sin(phase) * 2.2, cos(phase * 0.81) * 1.3, sin(phase * 1.3) * 0.4) * w * w;'
         ' float tl = length(A.xy); float2 a = A.xy / max(tl, 0.001); float2 b = float2(-a.y, a.x);'
         ' float2 d = P.xy - F.xy;'
         ' float mid = dot(d, a) + ((min(floor(U.x * 6.0), 5.0) + 0.5) / 6.0 - U.x) * 85.0; float across = dot(d, b);'
         ' float rho = length(float2(mid, across)); float2 e = float2(mid, across * 0.3);'
         ' float2 part = (a * e.x + b * e.y) / max(length(e), 4.0) * 30.0 * (1.0 - smoothstep(6.5, 50.0, rho))'
         ' * (1.0 - smoothstep(F.w, F.w + 25.0, abs(P.z - F.z))) * saturate(tl * 2.0 - 0.5);'
         ' float4 tr[5] = { float4(F.xyz, 0.0), T0, T1, T2, T3 };'
         ' float2 sum = float2(0.0, 0.0); float ksum = 0.0001; float kmax = 0.0;'
         ' for (int i = 0; i < 4; i++)'
         ' {'
         ' float2 ab = tr[i].xy - tr[i + 1].xy; float seg = length(ab);'
         ' float h = saturate(dot(P.xy - tr[i + 1].xy, ab) / max(seg * seg, 1.0));'
         ' float age = lerp(tr[i + 1].w, tr[i].w, h);'
         ' float z = lerp(tr[i + 1].z, tr[i].z, h);'
         ' float reach = (1.0 - smoothstep(25.0, 55.0, length(P.xy - tr[i + 1].xy - ab * h)))'
         ' * (1.0 - smoothstep(F.w + 20.0, F.w + 70.0, abs(P.z - z)))'
         ' * saturate(seg / 15.0) * (1.0 - smoothstep(0.65, 0.9, age));'
         ' float speed = seg / max(tr[i + 1].w - tr[i].w, 0.005);'
         ' float amp = min(speed * 0.05, 22.0) * exp(-1.6 * age) * cos(6.5 * age);'
         ' float k = reach * reach;'
         ' sum += ab / max(seg, 0.001) * amp * k; ksum += k; kmax = max(kmax, reach);'
         ' }'
         ' float2 push = (part + sum / ksum * kmax) * smoothstep(0.0, 0.3, w);'
         ' float len = max(w * 55.0, 2.0); float dl = length(push);'
         ' float2 swing = push * len / sqrt(len * len + dl * dl);'
         ' o += float3(swing, len - sqrt(max(len * len - dot(swing, swing), 0.0)));'
         ' return o;')


def _material(package):
    folder, name = package.rsplit('/', 1)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        return unreal.EditorAssetLibrary.load_asset(package)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def _custom_inputs(names):
    args = []
    for key in names:
        arg = unreal.CustomInput()
        arg.set_editor_property('input_name', key)
        args.append(arg)
    return args


def treehouse_surface(package, reads, *, texture, see_through):
    """M_TreeHouse: BLEND_Opaque for full Apple Silicon TBDR HSR across walls/floors/roofs/trunks, Surface AO,
    [branch]-gated noren cloth WPO, and vertex-stage piece/prop collapse for camera occlusion."""
    default_tex, collection = reads[texture], reads[see_through]
    MEL = unreal.MaterialEditingLibrary
    m = _material(package)
    MEL.delete_all_material_expressions(m)
    m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    m.set_editor_property('opacity_mask_clip_value', .5)

    def node(cls, x, y, **kw):
        e = MEL.create_material_expression(m, cls, x, y)
        for k, v in kw.items():
            e.set_editor_property(k, v)
        return e

    def link(a, ao, b, bi):
        assert MEL.connect_material_expressions(a, ao, b, bi), (ao, bi)

    def custom(x, y, code, names, kind=unreal.CustomMaterialOutputType.CMOT_FLOAT3, description=''):
        kw = dict(code=code, output_type=kind)
        if description:
            kw['description'] = description
        n = node(unreal.MaterialExpressionCustom, x, y, **kw)
        n.set_editor_property('inputs', _custom_inputs(names))
        return n

    def mpc_params(x, y, *names):
        return [node(unreal.MaterialExpressionCollectionParameter, x, y + 110 * idx,
                     collection=collection, parameter_name=n) for idx, n in enumerate(names)]

    vc = node(unreal.MaterialExpressionVertexColor, -900, 0)
    tex = node(unreal.MaterialExpressionTextureSampleParameter2D, -900, 200, parameter_name='Tex', texture=default_tex)
    gain = node(unreal.MaterialExpressionScalarParameter, -900, 420, parameter_name='Gain', default_value=2.)
    glow = node(unreal.MaterialExpressionScalarParameter, -900, 520, parameter_name='Glow', default_value=0.)
    vn = node(unreal.MaterialExpressionVertexNormalWS, -900, 620)
    base = custom(-550, 100,
                  'float3 L=lerp(C/12.92,pow((C+0.055)/1.055,2.4),step(0.04045,C));'
                  ' L=lerp(L/12.92,pow((L+0.055)/1.055,2.4),step(0.04045,L)); return L*T*G;',
                  ['C', 'T', 'G'])
    link(vc, '', base, 'C')
    link(tex, 'RGB', base, 'T')
    link(gain, '', base, 'G')
    depth = node(unreal.MaterialExpressionPixelDepth, -550, 350)
    haze = custom(-300, 350, 'return saturate((D-7000.)/220000.)*.5;', ['D'],
                  unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    link(depth, '', haze, 'D')
    fog = node(unreal.MaterialExpressionConstant3Vector, -300, 480, constant=unreal.LinearColor(.64, .68, .76, 1))
    mix = node(unreal.MaterialExpressionLinearInterpolate, -50, 100)
    link(base, '', mix, 'A')
    link(fog, '', mix, 'B')
    link(haze, '', mix, 'Alpha')
    assert MEL.connect_material_property(mix, '', unreal.MaterialProperty.MP_BASE_COLOR)
    emit = custom(-50, 350, 'return B*(.06+W+float3(.035,.025,.014)*saturate(-N.z));', ['B', 'W', 'N'])
    link(base, '', emit, 'B')
    link(glow, '', emit, 'W')
    link(vn, '', emit, 'N')
    assert MEL.connect_material_property(emit, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    ao = custom(-50, 480,
                'float hemi=lerp(.50,1.,saturate(N.z*.5+.5));'
                ' float luma=dot(T,float3(.3,.59,.11));'
                ' return saturate(hemi*clamp(.76+luma*.48,.70,1.));',
                ['N', 'T'], unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    link(vn, '', ao, 'N')
    link(tex, 'RGB', ao, 'T')
    assert MEL.connect_material_property(ao, '', unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    for prop, v, y in ((unreal.MaterialProperty.MP_ROUGHNESS, 1., 600), (unreal.MaterialProperty.MP_SPECULAR, 0., 700)):
        c = node(unreal.MaterialExpressionConstant, -50, y, r=v)
        assert MEL.connect_material_property(c, '', prop)

    # Cloth WPO + vertex-stage piece/instance collapse (ShadowReplace retains shadows while hiding camera occluders).
    t = node(unreal.MaterialExpressionTime, -500, 850)
    p = node(unreal.MaterialExpressionWorldPosition, -1350, 1400)
    cam = node(unreal.MaterialExpressionCameraPositionWS, -1350, 1500)
    focus, cut, room, room_size, room_shape = mpc_params(-1350, 1600, 'Focus', 'Cut', 'Room', 'RoomSize', 'RoomShape')
    eye, amount = mpc_params(-2250, 1100, 'Eye', 'Fade')
    trails = mpc_params(-550, 1150, *TRAIL)
    mode = node(unreal.MaterialExpressionScalarParameter, -1350, 2150, parameter_name='FadeMode', default_value=0.,
                use_custom_primitive_data=True, primitive_data_index=0)
    cut_scale = node(unreal.MaterialExpressionVectorParameter, -1350, 2250, parameter_name='CutScale',
                     default_value=unreal.LinearColor(1., 1., 1., 1.))
    room_cut = node(unreal.MaterialExpressionScalarParameter, -1350, 2350, parameter_name='RoomCut', default_value=1.)

    cloth_pins = ['T', 'P', 'W', 'A', 'U', 'F', *TRAIL]
    cloth_wpo = custom(-300, 850, CLOTH, cloth_pins, unreal.CustomMaterialOutputType.CMOT_FLOAT3, TAG)
    link(t, '', cloth_wpo, 'T')
    link(p, '', cloth_wpo, 'P')
    link(vc, 'A', cloth_wpo, 'W')
    link(node(unreal.MaterialExpressionVertexTangentWS, -550, 950), '', cloth_wpo, 'A')
    link(node(unreal.MaterialExpressionTextureCoordinate, -550, 1050), '', cloth_wpo, 'U')
    link(focus, '', cloth_wpo, 'F')
    for pin, tr in zip(TRAIL, trails):
        link(tr, '', cloth_wpo, pin)

    whole_inputs = ['M', 'O', 'P', 'C', 'E', 'F', 'G', 'U1', 'U2', 'U3', 'U4']
    whole_node = custom(-1800, 1000, WHOLE_COLLAPSE, whole_inputs, unreal.CustomMaterialOutputType.CMOT_FLOAT4, TAG)
    link(mode, '', whole_node, 'M')
    link(node(unreal.MaterialExpressionObjectPositionWS, -2250, 1000), '', whole_node, 'O')
    link(p, '', whole_node, 'P')
    link(cam, '', whole_node, 'C')
    link(eye, '', whole_node, 'E')
    link(focus, '', whole_node, 'F')
    link(amount, '', whole_node, 'G')
    for idx in range(1, 5):
        link(node(unreal.MaterialExpressionTextureCoordinate, -2250, 1300 + 100 * idx, coordinate_index=idx), '',
             whole_node, f'U{idx}')

    collapse_xyz = node(unreal.MaterialExpressionComponentMask, -1450, 950, r=True, g=True, b=True, a=False)
    link(whole_node, '', collapse_xyz, '')
    collapse_view = node(unreal.MaterialExpressionShadowReplace, -1200, 950)
    zero3 = node(unreal.MaterialExpressionConstant3Vector, -1450, 1060, constant=unreal.LinearColor(0., 0., 0., 1.))
    link(collapse_xyz, '', collapse_view, 'Default')
    link(zero3, '', collapse_view, 'Shadow')
    total_wpo = node(unreal.MaterialExpressionAdd, -50, 850)
    link(cloth_wpo, '', total_wpo, 'A')
    link(collapse_view, '', total_wpo, 'B')
    assert MEL.connect_material_property(total_wpo, '', unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    m.set_editor_property('max_world_position_offset_displacement', 60.)

    # Keep the see-through mask rooted on MP_OPACITY_MASK (inactive while BLEND_Opaque, active if an instance masks)
    # so every parameter and collection binding remains wired and zero parameters are dropped.
    fade_w = node(unreal.MaterialExpressionComponentMask, -1450, 1160, r=False, g=False, b=False, a=True)
    link(whole_node, '', fade_w, '')
    between = node(unreal.MaterialExpressionVertexInterpolator, -1200, 1160)
    link(fade_w, '', between, '')
    keep_names = ['P', 'C', 'F', 'X', 'W', 'M', 'K', 'R', 'S', 'H', 'RM']
    keep = custom(-900, 1400, LENS + HOLE + ROOM + HOLE_END + ' ' + DITHER, keep_names,
                  unreal.CustomMaterialOutputType.CMOT_FLOAT1, TAG)
    link(p, '', keep, 'P')
    link(cam, '', keep, 'C')
    link(focus, '', keep, 'F')
    link(cut, '', keep, 'X')
    link(between, '', keep, 'W')
    link(mode, '', keep, 'M')
    link(cut_scale, 'RGBA', keep, 'K')
    link(room, '', keep, 'R')
    link(room_size, '', keep, 'S')
    link(room_shape, '', keep, 'H')
    link(room_cut, '', keep, 'RM')
    mask_switch = node(unreal.MaterialExpressionShadowReplace, -600, 1400, desc=TAG)
    one = node(unreal.MaterialExpressionConstant, -800, 1520, r=1.)
    link(keep, '', mask_switch, 'Default')
    link(one, '', mask_switch, 'Shadow')
    assert MEL.connect_material_property(mask_switch, '', unreal.MaterialProperty.MP_OPACITY_MASK)

    m.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(m)
    return m


def treehouse_light(package, reads):
    """donor light_parent(), import_treehouse.py lines 129-166: unlit additive window-pane daylight glow."""
    MEL = unreal.MaterialEditingLibrary
    m = _material(package)
    MEL.delete_all_material_expressions(m)
    m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property('two_sided', True)
    m.set_editor_property('used_with_instanced_static_meshes', True)

    def node(cls, x, y, **kw):
        e = MEL.create_material_expression(m, cls, x, y)
        for k, v in kw.items():
            e.set_editor_property(k, v)
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
    names = ['T', 'N', 'V', 'UV', 'S', 'I', 'D']
    c.set_editor_property('inputs', _custom_inputs(names))
    tint = node(unreal.MaterialExpressionVectorParameter, -800, 0, parameter_name='Tint',
                default_value=unreal.LinearColor(*SUN_TINT, 1.))
    src = {
        'T': (tint, ''),
        'N': (node(unreal.MaterialExpressionVertexNormalWS, -800, 200), ''),
        'V': (node(unreal.MaterialExpressionCameraVectorWS, -800, 300), ''),
        'UV': (node(unreal.MaterialExpressionTextureCoordinate, -800, 400), ''),
        'S': (node(unreal.MaterialExpressionScalarParameter, -800, 500, parameter_name='Shape', default_value=0.), ''),
        'I': (node(unreal.MaterialExpressionScalarParameter, -800, 600, parameter_name='Intensity', default_value=.5), ''),
        'D': (node(unreal.MaterialExpressionPixelDepth, -800, 700), ''),
    }
    for k, (e, o) in src.items():
        assert MEL.connect_material_expressions(e, o, c, k), k
    assert MEL.connect_material_property(c, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    return m
