"""Camera see-through (docs/CAMERA.md): what stands between the chase camera and Cairo dithers away, Cairo fades when
the camera comes close to him, and the tree house's door curtains bend round him.

The game's USeeThroughComponent (Source/Yorimichi/SeeThrough.cpp) writes /Game/SeeThrough/MPC_SeeThrough every frame:

- Focus: Cairo's capsule centre (cm) and its half height.
- Cut: the cut's radius round him (cm), how far in front of him it starts (cm), the near-camera fade (0/1) and the
  cut's strength (0..1; 0 in the editor and the fixed review views).
- Room, RoomSize, RoomShape: the tree house room he is in (centre, yaw in radians; half size, blend; round, wall band,
  eaves) from treehouse/runtime.json.
- Trail0..Trail3: where he was every 0.3 s (cm) and how long ago (s): the path the curtains swing from.

The collection lives outside /Game/Japan, which the world import clears, so the Cairo materials keep a valid reference.
Graphs made here:

- add_mask(material, room): a masked, temporally dithered cut. A pixel goes where the ray from the camera through it
  passes within the radius of Cairo's body axis and the pixel is in front of him, above his feet (the floor he stands
  on stays); with room, also the walls of his room on the camera's side and its roof over his head while the camera
  is outside it. Within 40 cm of the camera everything fades (no half-clipped planks). Shadow passes keep every pixel.
- CLOTH: the tree house's world position offset: its wind, plus, for vertices whose vertex-colour alpha says how
  freely they hang (the noren: 0 down to the bottom of the band under the rod, 1 at the hem), each strip moved whole
  to one side of Cairo as he passes (the strips part round him) and a swing along his trail: cloth he walked through
  is dragged his way, swings back and settles within a second.
- character(material): Cairo's and the bokken's materials dither out within 60 cm of the camera (22 cm: gone).

Run as a script (`atelier build yorimichi unreal.see_through`), it patches what other imports build without it:
M_Foliage (leaves, bushes, flowers, litter), M_Grass (the grass tufts), M_Painted's mask pin with the instances in
PAINTED switched to masked (tree trunks, the road's guardrail, poles, torii), and /Game/Cairo's materials.
M_Grass and M_Painted carry the scaled cut (add_mask(scale=...)): a CutScale vector parameter per material or
instance (SCALES), and code that skips the pixels no cut can reach.
import_treehouse.py builds M_TreeHouse with it. Every patch is idempotent.
"""
import unreal

E = unreal.EditorAssetLibrary; MEL = unreal.MaterialEditingLibrary
FOLDER = '/Game/SeeThrough'; MPC = FOLDER+'/MPC_SeeThrough'
TAG = 'Japan see-through'
TRAIL = ('Trail0', 'Trail1', 'Trail2', 'Trail3')
VECTORS = (('Focus', (0., 0., -100000., 90.)), ('Cut', (55., 35., 0., 0.)), ('Room', (0., 0., -100000., 0.)),
           ('RoomSize', (100., 100., 100., 0.)), ('RoomShape', (0., 60., 90., 0.)),
           *((name, (0., 0., -100000., 10.)) for name in TRAIL))
OPACITY = unreal.MaterialProperty.MP_OPACITY_MASK
# M_Painted's instances (setup_project.py) that may stand between the camera and Cairo: tree trunks (Bark), the road's
# guardrail (Paint, a slot of the terrain mesh), poles (Metal, Wood), the torii (Vermilion, Tile). RoofTile, Plaster
# and Lattice have no mesh in the world today. The ground, road, water, rock and stone, the far forest and the sky stay
# opaque (he stands on them, or they are too big or far to matter, and masking costs on every pixel drawn). The
# houses and the village kit use M_Village, which is not cut: see docs/CAMERA.md.
PAINTED = ('Bark', 'RoofTile', 'Tile', 'Plaster', 'Wood', 'Lattice', 'Vermilion', 'Paint', 'Metal')
# CutScale (radius, front margin, near-camera fade distances, unused) on the materials with the scaled cut. M_Grass:
# blades fade from 1 m from the camera (gone at 25 cm), so a tuft by the lens never fills the screen. MI_Paint, the
# guardrail: the cut starts 9 cm in front of him instead of 35 cm, so the rail is gone even when he walks along it
# (his capsule keeps him 22 cm from it); the rail under his feet when he grinds stays, being under his feet.
SCALES = {'M_Grass': (1., 1., 2.5, 1.), 'M_Painted': (1., 1., 1., 1.), 'MI_Paint': (1., .25, 1., 1.)}

# The pixel's dither threshold: interleaved gradient noise, stepped every frame so TAA blends it into a soft fade.
DITHER = ('float2 px = Parameters.SvPosition.xy + float(View.StateFrameIndexMod8) * float2(32.665, 11.815);'
          ' float n = frac(52.9829189 * frac(dot(px, float2(0.06711056, 0.00583715))));'
          ' return keep > n ? 1.0 : 0.0;')

# P pixel, C camera, F body centre + half height, X radius / front margin / near fade / strength (cm, world space).
BODY = ('float3 v = P - C; float s = length(v); float3 d = v / max(s, 0.001);'
        ' float3 foot = F.xyz - float3(0.0, 0.0, F.w); float3 w0 = C - foot; float b = d.z;'
        # closest approach between the view ray and the body's axis (feet to head)
        ' float t = (b * w0.z - dot(d, w0)) / max(1.0 - b * b, 0.0001);'
        ' float u = clamp(w0.z + t * b, 0.0, 2.0 * F.w);'
        ' t = max(dot(foot + float3(0.0, 0.0, u) - C, d), 0.0);'
        ' float gap = length(C + d * t - foot - float3(0.0, 0.0, u));'
        ' float rad = max(X.x, 1.0);'
        ' float above = smoothstep(foot.z + 5.0, foot.z + 30.0, P.z);'
        ' float cut = (1.0 - smoothstep(rad * 0.6, rad, gap)) * smoothstep(X.y * 0.5, X.y * 1.5, t - s) * above;')

# R room centre + yaw, S half size + blend, H round / wall band / eaves, M this material's share of the room cut.
ROOM = (' float cy = cos(R.w); float sy = sin(R.w);'
        ' float2 q = P.xy - R.xy; q = float2(q.x * cy + q.y * sy, q.y * cy - q.x * sy);'
        ' float2 qc = C.xy - R.xy; qc = float2(qc.x * cy + qc.y * sy, qc.y * cy - qc.x * sy);'
        ' float o = H.x > 0.5 ? length(q) - S.x : max(abs(q.x) - S.x, abs(q.y) - S.y);'
        ' float oc = H.x > 0.5 ? length(qc) - S.x : max(abs(qc.x) - S.x, abs(qc.y) - S.y);'
        ' float top = R.z + S.z; float head = F.z + F.w;'
        # only while the camera is outside the room or over its top
        ' float away = max(smoothstep(-20.0, 30.0, oc), smoothstep(top - 40.0, top + 10.0, C.z));'
        ' float2 toCam = C.xy - F.xy; toCam = toCam / max(length(toCam), 1.0);'
        ' float walls = smoothstep(-H.y - 20.0, -H.y, o) * (1.0 - smoothstep(H.z, H.z + 30.0, o))'
        ' * smoothstep(-20.0, 40.0, dot(P.xy - F.xy, toCam)) * above;'
        # the ceiling and roof: from 60 cm under the room's top (never lower than just over his head) up to 3 m over it
        ' float lid = max(head + 15.0, top - 60.0);'
        ' float roof = smoothstep(lid, lid + 30.0, P.z) * (1.0 - smoothstep(H.z + 60.0, H.z + 100.0, o))'
        ' * (1.0 - smoothstep(top + 300.0, top + 360.0, P.z)) * smoothstep(lid - 20.0, lid + 40.0, C.z);'
        ' cut = max(cut, M * S.w * away * max(walls, roof));')

KEEP = (' float keep = 1.0 - saturate(cut * X.w);'
        ' keep = keep * lerp(1.0, smoothstep(10.0, 40.0, s), saturate(X.z));')

NEAR = ('float s = length(P - C);'
        ' float keep = lerp(1.0, smoothstep(22.0, 60.0, s), saturate(X.z));')

# The scaled cut (add_mask(scale=...)), for materials without the room cutaway: K is the material's CutScale. Before
# BODY, it scales the radius and the front margin, then leaves at once, keeping the pixel, when no cut can reach it:
# every ray the hole takes passes within R (half height + radius) of his centre, so a pixel beyond that sphere, or
# outside the cone the sphere makes from the camera, stays, unless the near-camera fade reaches it. On grass and bark
# that is almost every pixel drawn, which then costs a few instructions instead of the whole cut.
SCALED = ('X = X * float4(K.x, K.y, 1.0, 1.0);'
          ' float3 e0 = P - C; float ee = dot(e0, e0); float3 f0 = F.xyz - C; float ff = dot(f0, f0);'
          ' float R = F.w + max(X.x, 1.0); float fa = dot(e0, f0); float fr = sqrt(ff) + R; float nr = 40.0 * K.z;'
          ' float clear = max(step(fr * fr, ee), step(R * R, ff) * max(step(fa, 0.0), step(fa * fa, ee * (ff - R * R))));'
          ' [branch] if (max(clear, step(X.w, 0.0)) * max(step(nr * nr, ee), step(X.z, 0.0)) > 0.5) return 1.0; ')

KEEP_SCALED = (' float keep = 1.0 - saturate(cut * X.w);'
               ' keep = keep * lerp(1.0, smoothstep(10.0 * K.z, 40.0 * K.z, s), saturate(X.z));')

# T time, P vertex (rest), W vertex-colour alpha (how freely it hangs), A vertex tangent (the way the picture's u runs
# across the curtain), U its uv, F body centre + half height, T0..T3 the trail (the newest first; w: age in s). Only
# vertices with alpha move:
# - the wind the tree house always had;
# - the parting: each strip (u in sixths of a curtain about 85 cm wide, as treehouse/build.py cuts the noren; its
#   middle is found from the vertex's u, and a curtain 40% wider or narrower still finds it within 4 cm) moves whole,
#   straight away from his
#   body's axis through the strip's middle, 30 cm when he is at it, nothing from 50 cm off: ahead of him as he comes,
#   aside as he passes, behind him as he leaves, turning smoothly round him, so a strip keeps its width, never tears
#   and never flips through him (except within 4 cm of its very middle, where it would have to drape over him);
# - near any point of his path, a swing along the way he went there, starting where he is and decaying as the point
#   ages (a damped oscillation: dragged on, back past rest, settled within 0.9 s). A trail segment weighs in by its
#   length and its age, so a new sample or a dropped old one never makes the cloth jump.
# Each vertex then swings on a circle as long as it hangs below the band (alpha x 55 cm): pushed aside, it rises, and
# however hard it is pushed it never leaves the strip's length.
CLOTH = ('if (W <= 0.001) return float3(0.0, 0.0, 0.0);'
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


def collection():
    """The parameter collection, made once. An existing one is kept as it is when its parameters match, so the
    materials that read it stay valid."""
    names = [n for n, _ in VECTORS]
    if E.does_asset_exist(MPC):
        mpc = E.load_asset(MPC)
        if [str(p.get_editor_property('parameter_name')) for p in mpc.get_editor_property('vector_parameters')] == names:
            return mpc
    else:
        E.make_directory(FOLDER)
        mpc = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            'MPC_SeeThrough', FOLDER, unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
    ps = []
    for name, value in VECTORS:
        q = unreal.CollectionVectorParameter(); q.set_editor_property('parameter_name', name)
        q.set_editor_property('default_value', unreal.LinearColor(*value)); ps.append(q)
    mpc.set_editor_property('vector_parameters', ps)
    E.save_loaded_asset(mpc)
    unreal.log(f'SEE-THROUGH collection {MPC}: {", ".join(names)}')
    return mpc


def node(m, cls, x, y, **kw):
    e = MEL.create_material_expression(m, cls, x, y)
    for k, v in kw.items(): e.set_editor_property(k, v)
    return e


def link(a, ao, b, bi): assert MEL.connect_material_expressions(a, ao, b, bi), (a.get_name(), ao, bi)


def custom(m, x, y, code, names, kind=unreal.CustomMaterialOutputType.CMOT_FLOAT1):
    n = node(m, unreal.MaterialExpressionCustom, x, y, code=code, output_type=kind, description=TAG)
    args = []
    for k in names:
        a = unreal.CustomInput(); a.set_editor_property('input_name', k); args.append(a)
    n.set_editor_property('inputs', args)
    return n


def params(m, x, y, *names):
    """CollectionParameter nodes reading the named vectors of the collection."""
    mpc = collection()
    return [node(m, unreal.MaterialExpressionCollectionParameter, x, y+110*k, collection=mpc, parameter_name=n)
            for k, n in enumerate(names)]


def upstream(m, e):
    """e and every expression feeding it."""
    seen, todo = {}, [e]
    while todo:
        x = todo.pop()
        if x is None or x.get_path_name() in seen: continue
        seen[x.get_path_name()] = x
        todo.extend(MEL.get_inputs_for_material_expression(m, x))
    return list(seen.values())


def done(m):
    """Whether the opacity mask already has the see-through somewhere upstream (another patch may have wrapped it)."""
    return any(e.get_editor_property('desc') == TAG for e in upstream(m, MEL.get_material_property_input_node(m, OPACITY)))


def scaled(m):
    """Whether m's see-through is the scaled cut (its Custom node reads K)."""
    return any(isinstance(e, unreal.MaterialExpressionCustom) and e.get_editor_property('description') == TAG
               and 'K' in [str(i.get_editor_property('input_name')) for i in e.get_editor_property('inputs')]
               for e in upstream(m, MEL.get_material_property_input_node(m, OPACITY)))


def strip(m):
    """Take an earlier add_mask off a material whose opacity mask had nothing else (M_Painted, patched before the
    scaled cut): the mask's input is then the see-through's own shadow switch, and all that feeds it is the
    see-through's. Anything else is left alone (False)."""
    out = MEL.get_material_property_input_node(m, OPACITY)
    if not isinstance(out, unreal.MaterialExpressionShadowReplace) or out.get_editor_property('desc') != TAG:
        return False
    for e in upstream(m, out): MEL.delete_material_expression(m, e)
    return True


def masked(m):
    """Opaque becomes masked (clip 0.5); masked keeps its own clip value. Translucent materials are left alone."""
    mode = m.get_editor_property('blend_mode')
    if mode == unreal.BlendMode.BLEND_OPAQUE:
        m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
        m.set_editor_property('opacity_mask_clip_value', .5)
    return mode in (unreal.BlendMode.BLEND_OPAQUE, unreal.BlendMode.BLEND_MASKED)


def into_mask(m, keep, x, y):
    """Switch the dither off in shadow passes (the cut-away still casts its shadow) and multiply it into whatever
    already feeds the opacity mask."""
    source = MEL.get_material_property_input_node(m, OPACITY)
    output = MEL.get_material_property_input_node_output_name(m, OPACITY) if source is not None else ''
    switch = node(m, unreal.MaterialExpressionShadowReplace, x, y)
    one = node(m, unreal.MaterialExpressionConstant, x-200, y+120, r=1.)
    link(keep, '', switch, 'Default'); link(one, '', switch, 'Shadow')
    out = switch
    if source is not None:
        out = node(m, unreal.MaterialExpressionMultiply, x+250, y)
        link(source, output, out, 'A'); link(switch, '', out, 'B')
    out.set_editor_property('desc', TAG)
    assert MEL.connect_material_property(out, '', OPACITY)


def add_mask(m, room=False, blend=True, scale=None, x=-900, y=1400):
    """The see-through on material m. blend: make an opaque m masked (clip 0.5); leave it off for an opaque parent whose
    instances switch to masked (mask_instance). room: also the room cutaway, weighted by the
    scalar parameter RoomCut (1; the trunks' instance sets 0 so the old camphor is never cut at ceiling height).
    scale: the scaled cut instead (SCALED, no room), with the vector parameter CutScale defaulting to scale."""
    if done(m) or (blend and not masked(m)): return False
    assert not (room and scale), 'the scaled cut has no room cutaway'
    names = ['P', 'C', 'F', 'X'] + (['R', 'S', 'H', 'M'] if room else []) + (['K'] if scale else [])
    code = SCALED + BODY + KEEP_SCALED if scale else BODY + (ROOM if room else '') + KEEP
    cut = custom(m, x, y, code + ' ' + DITHER, names)
    link(node(m, unreal.MaterialExpressionWorldPosition, x-450, y), '', cut, 'P')
    link(node(m, unreal.MaterialExpressionCameraPositionWS, x-450, y+100), '', cut, 'C')
    vectors = params(m, x-450, y+200, 'Focus', 'Cut', *(('Room', 'RoomSize', 'RoomShape') if room else ()))
    for pin, e in zip(names[2:], vectors): link(e, '', cut, pin)
    if room:
        share = node(m, unreal.MaterialExpressionScalarParameter, x-450, y+760, parameter_name='RoomCut', default_value=1.)
        link(share, '', cut, 'M')
    if scale:
        k = node(m, unreal.MaterialExpressionVectorParameter, x-450, y+760, parameter_name='CutScale',
                 default_value=unreal.LinearColor(*scale))
        link(k, 'RGBA', cut, 'K')
    into_mask(m, cut, x+300, y)
    return True


def mask_instance(mi):
    """An instance of an opaque parent carrying add_mask(blend=False): masked through its property overrides."""
    o = mi.get_editor_property('base_property_overrides')
    if o.get_editor_property('override_blend_mode') and o.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_MASKED:
        return False
    o.set_editor_property('override_blend_mode', True); o.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
    o.set_editor_property('override_opacity_mask_clip_value', True); o.set_editor_property('opacity_mask_clip_value', .5)
    mi.set_editor_property('base_property_overrides', o)
    MEL.update_material_instance(mi)
    return True


def character(m):
    """Cairo and the bokken: masked, dithered out within 60 cm of the camera."""
    if done(m) or not masked(m): return False
    keep = custom(m, -900, 900, NEAR + ' ' + DITHER, ['P', 'C', 'X'])
    link(node(m, unreal.MaterialExpressionWorldPosition, -1300, 900), '', keep, 'P')
    link(node(m, unreal.MaterialExpressionCameraPositionWS, -1300, 1000), '', keep, 'C')
    link(params(m, -1300, 1100, 'Cut')[0], '', keep, 'X')
    into_mask(m, keep, -600, 900)
    return True


def cloth(m, t, p, w, x=-300, y=1100):
    """The tree house's world position offset: CLOTH from time t, the vertex position p and its alpha w (expression,
    output name)."""
    pins = ['T0', 'T1', 'T2', 'T3']
    offset = custom(m, x, y, CLOTH, ['T', 'P', 'W', 'A', 'U', 'F', *pins], unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    link(t, '', offset, 'T'); link(p, '', offset, 'P'); link(w[0], w[1], offset, 'W')
    link(node(m, unreal.MaterialExpressionVertexTangentWS, x-250, y+100), '', offset, 'A')
    link(node(m, unreal.MaterialExpressionTextureCoordinate, x-250, y+200), '', offset, 'U')
    for pin, e in zip(['F', *pins], params(m, x-250, y+300, 'Focus', *TRAIL)): link(e, '', offset, pin)
    # A strip swings on a circle no longer than it hangs (55 cm at the hem), so it moves at most 55 cm from rest on
    # any axis: the instance culling bounds grow by that.
    m.set_editor_property('max_world_position_offset_displacement', 60.)
    return offset


def save(m):
    MEL.recompile_material(m); E.save_loaded_asset(m)


def cut_scale(mi, value):
    """Give an instance its own CutScale; False when it has it already or its parent has no scaled cut."""
    want = unreal.LinearColor(*value)
    have = MEL.get_material_instance_vector_parameter_value(mi, 'CutScale')
    if all(abs(getattr(have, c) - getattr(want, c)) < 1e-4 for c in 'rgba'): return False
    if not MEL.set_material_instance_vector_parameter_value(mi, 'CutScale', want):
        unreal.log_warning(f'SEE-THROUGH {mi.get_name()}: no CutScale on its parent'); return False
    MEL.update_material_instance(mi)
    return True


def material(name):
    path = '/Game/Japan/Materials/' + name
    return E.load_asset(path) if E.does_asset_exist(path) else None


def main():
    collection()
    changed = []
    foliage = material('M_Foliage')
    if foliage and add_mask(foliage, blend=False):          # masked already, with its own clip value
        save(foliage); changed.append('M_Foliage')
    grass = material('M_Grass')
    if grass and add_mask(grass, scale=SCALES['M_Grass']):  # masked already (its instance fade), so it stays masked
        save(grass); changed.append('M_Grass')
    painted = material('M_Painted')
    if painted and done(painted) and not scaled(painted) and not strip(painted):
        unreal.log_warning('SEE-THROUGH M_Painted keeps its earlier cut: something else feeds its opacity mask')
    if painted and add_mask(painted, blend=False, scale=SCALES['M_Painted']):   # opaque: only masked instances use it
        save(painted); changed.append('M_Painted')
    for name in PAINTED:
        mi = material(f'MI_{name}')
        if mi and painted and mask_instance(mi):
            E.save_loaded_asset(mi); changed.append(f'MI_{name}')
    for name, value in SCALES.items():
        mi = material(name) if name.startswith('MI_') else None
        if mi and cut_scale(mi, value):
            E.save_loaded_asset(mi); changed.append(f'{name} CutScale')
    for path in sorted(E.list_assets('/Game/Cairo', recursive=False)):
        name = path.rsplit('/', 1)[-1].split('.')[0]
        if not name.startswith(('M_Cairo', 'M_Bokken')): continue
        m = E.load_asset(path)
        if isinstance(m, unreal.Material) and character(m):
            save(m); changed.append(name)
    tree = '/Game/Japan/Treehouse/Materials/M_TreeHouse'
    ready = E.does_asset_exist(tree) and done(E.load_asset(tree))
    unreal.log(f'SEE-THROUGH COMPLETE patched {len(changed)}: {", ".join(changed) or "nothing new"}; '
               f'M_TreeHouse {"has it" if ready else "needs unreal.treehouse"}')


if __name__ == '__main__':
    main()
