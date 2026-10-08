"""Camera see-through (docs/CAMERA.md), the way adventure does it. A thin thing between the chase camera and
Cairo (a trunk, a bush, a post, a rail, a lantern, a noren) fades out whole and comes back once it has passed.
Everything fades right at the lens. Cairo fades when the camera comes close to him. Solid things are never faded,
because the camera arm (JapanCameraArm.cpp) stays in front of them. The tree house's door curtains also bend round
him.

The game's USeeThroughComponent (Source/Yorimichi/SeeThrough.cpp) writes /Game/SeeThrough/MPC_SeeThrough every frame:

- Focus: Cairo's capsule centre (cm) and its half height.
- Fade: how strong the whole fades are (0..1), how much the sight lines widen toward him (cm), the range of the whole
  fade round the lens (cm), and how far from the camera a big thing still fades (cm).
- Eye: the camera position, smoothed (cm). The sight lines to him start there.
- Cut: the old hole's radius (cm), how far in front of him it starts (cm), the lens fade's strength (0..1), and the
  old hole's strength (0..1; 0 unless japan.SeeThroughHole is 1).
- Room, RoomSize, RoomShape: the tree house room he is in (centre, yaw in radians; half size, blend; round, wall band,
  eaves), for the old room cutaway (hole mode only).
- Trail0..Trail3: where he was every 0.3 s (cm) and how long ago (s): the path the curtains swing from.

Every mesh group gives its fade mode in custom primitive data 0 (FadeMode, which AJapanWorld sets from
JapanSeeThrough::FadeMode):
- 0, solid: only the lens fade, 5 to 15 cm (the camera stays 20 cm off solid things);
- 1: each instance fades whole, from its own position and bounds;
- 2: each piece of a merged mesh fades whole, from the centre and axis baked in its UV channels 1 to 4;
- 3: only the lens fade, 10 to 40 cm.

The collection lives outside /Game/Japan, which the world import clears, so the Cairo materials keep a valid reference.
Graphs made here:

- add_mask(material, ...): a masked, temporally dithered fade. In the vertex shader, WHOLE finds how much this
  instance or piece hides Cairo or crowds the lens. It passes the result through a vertex interpolator to the pixel
  shader, where KEEP applies it with the lens fade (and, in hole mode, the old hole and room cutaway). Shadow passes
  keep every pixel.
- CLOTH: the tree house's world position offset. It keeps the tree house's wind. Vertices whose vertex-colour alpha
  says how freely they hang (the noren: 0 down to the bottom of the band under the rod, 1 at the hem) also move: each
  strip moves whole to one side of Cairo as he passes (the strips part round him), and swings along his trail (cloth
  he walked through is dragged his way, swings back and settles within a second).
- character(material): Cairo's and the bokken's materials dither out within 60 cm of the camera (gone at 22 cm).

Run as a script (`atelier build yorimichi unreal.see_through`), it patches what other imports build without it:
- M_Foliage (leaves, bushes, flowers, litter);
- M_Grass (the grass tufts: lens fade only);
- M_Painted's mask pin, with the instances in PAINTED switched to masked (tree trunks, the road's guardrail, poles,
  stone lanterns, the torii);
- the playable characters' materials: those in a character.toml's unreal_path named after its `see_through` prefixes.
It also upgrades an M_TreeHouse carrying the first version. import_treehouse.py builds M_TreeHouse with
add_mask(pieces=True). A material carrying the first version (OLD, the hole round Cairo) is upgraded in place. Every
patch is idempotent.
"""
import tomllib
from pathlib import Path
import unreal

E = unreal.EditorAssetLibrary; MEL = unreal.MaterialEditingLibrary
FOLDER = '/Game/SeeThrough'; MPC = FOLDER+'/MPC_SeeThrough'
TAG = 'Japan see-through 2'
OLD = 'Japan see-through'          # the first version: a round hole round Cairo, cut per pixel
# The characters the camera fades near the lens: (unreal_path, material name prefixes) from their character.toml.
CHARACTERS = [(spec['unreal_path'], tuple(spec['see_through'])) for spec in
              (tomllib.loads(p.read_text()) for p in sorted((Path(__file__).resolve().parents[2] / 'assets' / 'characters').glob('*/character.toml')))
              if 'see_through' in spec]
TRAIL = ('Trail0', 'Trail1', 'Trail2', 'Trail3')
VECTORS = (('Focus', (0., 0., -100000., 90.)), ('Cut', (55., 35., 0., 0.)), ('Room', (0., 0., -100000., 0.)),
           ('RoomSize', (100., 100., 100., 0.)), ('RoomShape', (0., 60., 90., 0.)),
           *((name, (0., 0., -100000., 10.)) for name in TRAIL),
           ('Fade', (0., 30., 60., 250.)), ('Eye', (0., 0., -100000., 0.)))
OPACITY = unreal.MaterialProperty.MP_OPACITY_MASK
# The instances of M_Painted (setup_project.py) that may stand between the camera and Cairo:
# - tree trunks (Bark);
# - the road's guardrail (Paint, a slot of the terrain mesh);
# - poles (Concrete, Metal, Wood, Paint);
# - stone lanterns (Stone);
# - the torii (Vermilion, Tile).
# RoofTile, Plaster and Lattice have no mesh in the world today. The ground, road, water, rock, far forest and sky
# stay opaque: he stands on them, or they are too big or far to matter, and masking costs on every pixel drawn. The
# houses and the village kit use M_Village, which is not patched (docs/CAMERA.md).
PAINTED = ('Bark', 'RoofTile', 'Tile', 'Plaster', 'Wood', 'Lattice', 'Vermilion', 'Paint', 'Metal', 'Stone', 'Concrete')
# CutScale, per material or instance:
# - x: the old hole's radius;
# - y: how far in front of him the old hole starts;
# - z: the lens fade's distances;
# - w: unused.
# M_Foliage: leaves fade from 80 cm off the lens, so a branch by the camera never fills the screen. M_Grass: blades
# fade from 1 m (gone at 25 cm). MI_Paint, the guardrail: in hole mode the hole starts 9 cm in front of him.
SCALES = {'M_Foliage': (1., 1., 2., 1.), 'M_Grass': (1., 1., 2.5, 1.), 'M_Painted': (1., 1., 1., 1.),
          'MI_Paint': (1., .25, 1., 1.)}

# The pixel's dither threshold: interleaved gradient noise, stepped every frame so TAA blends it into a soft fade.
DITHER = ('float2 px = Parameters.SvPosition.xy + float(View.StateFrameIndexMod8) * float2(32.665, 11.815);'
          ' float n = frac(52.9829189 * frac(dot(px, float2(0.06711056, 0.00583715))));'
          ' return keep > n ? 1.0 : 0.0;')

# WHOLE, in the vertex shader. The piece a vertex belongs to is a segment A..B with a radius r (cm, world space).
# - INSTANCE (mode 1): from the instance's mesh bounds, turned and scaled by the instance. A thin thing (at most
#   1.5 m across) is a vertical capsule inside its box. A big one (a tree's crown, the torii) is its box's height.
# - PIECE (mode 2): from the bake in UV1..UV4 (metres, Blender axes; the import flipped every v, which 1 - v undoes,
#   and Blender's y is Unreal's -y). A vertex with nothing baked (UV4.v 1 after the flip) does not fade.
# O instance origin, P vertex (rest), U1..U4 the bake.
INSTANCE = (' float3 bc = GetPrimitiveData(Parameters).InstanceLocalBoundsCenter;'
            ' float3 be = GetPrimitiveData(Parameters).InstanceLocalBoundsExtent;'
            ' float3 c = O + TransformLocalVectorToWorld(Parameters, bc);'
            ' float3 e = abs(TransformLocalVectorToWorld(Parameters, float3(be.x, 0.0, 0.0)))'
            ' + abs(TransformLocalVectorToWorld(Parameters, float3(0.0, be.y, 0.0)))'
            ' + abs(TransformLocalVectorToWorld(Parameters, float3(0.0, 0.0, be.z)));'
            ' r = max(e.x, e.y); float h = r > 150.0 ? e.z : max(e.z - r, 0.0);'
            ' A = c - float3(0.0, 0.0, h); B = c + float3(0.0, 0.0, h);')
PIECE = (' if (U4.y > 0.5) return 0.0;'
         ' float3 c = P + TransformLocalVectorToWorld(Parameters, float3(U1.x, U1.y - 1.0, U2.x) * 100.0);'
         ' float3 x = TransformLocalVectorToWorld(Parameters, float3(U3.x, U3.y - 1.0, U4.x) * 100.0);'
         ' r = (1.0 - U2.y) * 100.0; A = c - x; B = c + x;')
# Then, for a piece anywhere near the camera or the way to him:
# - near: the piece's surface within 30 to 60 cm of the camera (G.z) fades it whole, before the lens clips it;
# - between: the closest approach between the piece's segment and three sight lines, from the smoothed camera (E) to
#   his head, chest and knees. The lines widen toward him by G.y (his body), and the piece must be in front of him.
#   Within 30 cm, it fades. A big thing counts only by a 40 cm core along its axis (a trunk), and only within G.w
#   (2.5 m, gone by 3.5 m) of the camera: further off it may hide him for a moment, as a tree does in the adventure library, rather
#   than a whole crown vanishing next to him.
# C camera, E smoothed camera, F body centre + half height, G Fade, M the group's fade mode.
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


def whole(pieces):
    """WHOLE's code: modes 1 (and 2 with pieces) fade; the others return 0 at once."""
    shape = ' if (M < 1.5) {' + INSTANCE + ' }' + (' else {' + PIECE + ' }' if pieces else '')
    return ('float fade = 0.0;'
            f' [branch] if (G.x > 0.0 && M > 0.5 && M < {2.5 if pieces else 1.5})'
            ' {'
            ' float3 A = O; float3 B = O; float r = 0.0;' + shape + BETWEEN +
            ' }'
            ' return fade;')


# KEEP, in the pixel shader. P pixel, C camera, X Cut, W the whole fade, M fade mode, K CutScale. Then the lens fade:
# solid things (the camera stays 20 cm off them) within 15 cm, the rest within 40 cm, times K.z.
LENS = ('float3 v = P - C; float s = length(v);'
        ' float keep = 1.0 - saturate(W);'
        ' float2 lens = (M > 0.5 ? float2(10.0, 40.0) : float2(5.0, 15.0)) * K.z;'
        ' keep = keep * lerp(1.0, smoothstep(lens.x, lens.y, s), saturate(X.z));')

# The old hole (hole mode, X.w > 0), F body centre + half height. A pixel goes where the ray from the camera through
# it passes within the radius of Cairo's body axis, and the pixel is in front of him and above his feet.
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

# The old room cutaway (hole mode). R room centre + yaw, S half size + blend, H round / wall band / eaves, RM this
# material's share of the room cut.
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
        ' cut = max(cut, RM * S.w * away * max(walls, roof));')

HOLE_END = ' keep = keep * (1.0 - saturate(cut * X.w)); }'

NEAR = ('float s = length(P - C);'
        ' float keep = lerp(1.0, smoothstep(22.0, 60.0, s), saturate(X.z));')

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
    """The parameter collection. Missing parameters are appended, and the existing ones are kept as they are (with
    their ids), so the materials that read them stay valid."""
    if E.does_asset_exist(MPC):
        mpc = E.load_asset(MPC)
    else:
        E.make_directory(FOLDER)
        mpc = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            'MPC_SeeThrough', FOLDER, unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
    ps = list(mpc.get_editor_property('vector_parameters'))
    have = {str(p.get_editor_property('parameter_name')) for p in ps}
    missing = [(name, value) for name, value in VECTORS if name not in have]
    if not missing: return mpc
    for name, value in missing:
        q = unreal.CollectionVectorParameter(); q.set_editor_property('parameter_name', name)
        q.set_editor_property('default_value', unreal.LinearColor(*value)); ps.append(q)
    mpc.set_editor_property('vector_parameters', ps)
    E.save_loaded_asset(mpc)
    unreal.log(f'SEE-THROUGH collection {MPC}: added {", ".join(n for n, _ in missing)}')
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


def tag(m):
    """Which see-through m's opacity mask has somewhere upstream (another patch may have wrapped it): TAG, OLD or
    None."""
    descs = {str(e.get_editor_property('desc')) for e in upstream(m, MEL.get_material_property_input_node(m, OPACITY))}
    return TAG if TAG in descs else OLD if OLD in descs else None


def done(m):
    """Whether the opacity mask has a see-through, of either version."""
    return tag(m) is not None


def stale(m, blend=True):
    """Whether m's opacity mask still leads to a see-through that a rebuild deleted. import_treehouse.py,
    import_cairo.py rebuilds its materials with delete_all_material_expressions, which leaves
    the opacity mask on the deleted nodes: done() still finds the tag, and the material fails to compile (Missing input
    Shadow) and renders as the default. Those imports reset the material to opaque, and the see-through (blend) always
    leaves it masked; a shadow switch that lost an input is stale too."""
    if not done(m): return False
    if blend and m.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_OPAQUE: return True
    return any(isinstance(e, unreal.MaterialExpressionShadowReplace) and None in MEL.get_inputs_for_material_expression(m, e)
               for e in upstream(m, MEL.get_material_property_input_node(m, OPACITY)))


def unwrap(m):
    """Take the first version (OLD) off m. Its own nodes are deleted. Its root is returned to take the new one: the
    Multiply that holds whatever fed the mask before, or the shadow switch when nothing did. Whatever the root feeds
    (the opacity mask, or the instance distance fade that foliage_material.py wraps round it) stays connected. None
    when the graph is not the one the first version made."""
    root = next((e for e in upstream(m, MEL.get_material_property_input_node(m, OPACITY))
                 if str(e.get_editor_property('desc')) == OLD), None)
    if isinstance(root, unreal.MaterialExpressionMultiply):
        inputs = MEL.get_inputs_for_material_expression(m, root)
        switch = inputs[1] if len(inputs) > 1 else None
        if not isinstance(switch, unreal.MaterialExpressionShadowReplace): return None
        gone = upstream(m, switch)
    elif isinstance(root, unreal.MaterialExpressionShadowReplace):
        gone = [e for e in upstream(m, root) if e.get_path_name() != root.get_path_name()]
    else:
        return None
    for e in gone: MEL.delete_material_expression(m, e)
    return root


def masked(m):
    """Opaque becomes masked (clip 0.5); masked keeps its own clip value. Translucent materials are left alone."""
    mode = m.get_editor_property('blend_mode')
    if mode == unreal.BlendMode.BLEND_OPAQUE:
        m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
        m.set_editor_property('opacity_mask_clip_value', .5)
    return mode in (unreal.BlendMode.BLEND_OPAQUE, unreal.BlendMode.BLEND_MASKED)


def into_mask(m, keep, x, y, alone=False, root=None):
    """Switch the dither off in shadow passes (what fades still casts its shadow) and multiply it into whatever
    already feeds the opacity mask (alone: replace it). root: the first version's root (unwrap), which takes the new
    switch in place."""
    source = None if alone or root is not None else MEL.get_material_property_input_node(m, OPACITY)
    output = MEL.get_material_property_input_node_output_name(m, OPACITY) if source is not None else ''
    switch = root if isinstance(root, unreal.MaterialExpressionShadowReplace) else node(m, unreal.MaterialExpressionShadowReplace, x, y)
    one = node(m, unreal.MaterialExpressionConstant, x-200, y+120, r=1.)
    link(keep, '', switch, 'Default'); link(one, '', switch, 'Shadow')
    if root is not None:
        if switch is not root: link(switch, '', root, 'B')
        root.set_editor_property('desc', TAG)
        return
    out = switch
    if source is not None:
        out = node(m, unreal.MaterialExpressionMultiply, x+250, y)
        link(source, output, out, 'A'); link(switch, '', out, 'B')
    out.set_editor_property('desc', TAG)
    assert MEL.connect_material_property(out, '', OPACITY)


def add_mask(m, room=False, blend=True, scale=None, whole_fade=True, pieces=False, x=-900, y=1400):
    """The see-through on material m.
    - blend: make an opaque m masked (clip 0.5). Leave it off for an opaque parent whose instances switch to masked
      (mask_instance).
    - whole_fade: WHOLE in the vertex shader, so instances (and, with pieces, baked pieces) fade whole. Without it
      (grass), only the lens fade.
    - pieces: also fade mode 2, from the bake in UV1..UV4 (the tree house).
    - scale: CutScale's default (1, 1, 1, 1 when None).
    - room: in hole mode, also the old room cutaway, weighted by the scalar parameter RoomCut. RoomCut is 1; the
      trunks' instance sets 0, so the old camphor is never cut at ceiling height.
    A material with the first version is upgraded in place."""
    old = stale(m, blend)       # a rebuilt material: its opacity mask is the see-through's alone (into_mask)
    root = None
    if not old and tag(m) == OLD:
        root = unwrap(m)
        if root is None:
            unreal.log_warning(f'SEE-THROUGH {m.get_name()} keeps the first version: its graph is not the one it made')
            return False
    elif (done(m) and not old) or (blend and not masked(m)):
        return False
    names = ['P', 'C', 'F', 'X', 'W', 'M', 'K'] + (['R', 'S', 'H', 'RM'] if room else [])
    keep = custom(m, x, y, LENS + HOLE + (ROOM if room else '') + HOLE_END + ' ' + DITHER, names)
    p = node(m, unreal.MaterialExpressionWorldPosition, x-450, y)
    c = node(m, unreal.MaterialExpressionCameraPositionWS, x-450, y+100)
    link(p, '', keep, 'P'); link(c, '', keep, 'C')
    focus, cut, *rooms = params(m, x-450, y+200, 'Focus', 'Cut', *(('Room', 'RoomSize', 'RoomShape') if room else ()))
    link(focus, '', keep, 'F'); link(cut, '', keep, 'X')
    for pin, e in zip(('R', 'S', 'H'), rooms): link(e, '', keep, pin)
    # The group's fade mode (AJapanWorld sets it); 0, solid, where nothing sets it.
    mode = node(m, unreal.MaterialExpressionScalarParameter, x-450, y+560, parameter_name='FadeMode', default_value=0.,
                use_custom_primitive_data=True, primitive_data_index=0)
    link(mode, '', keep, 'M')
    k = node(m, unreal.MaterialExpressionVectorParameter, x-450, y+660, parameter_name='CutScale',
             default_value=unreal.LinearColor(*(scale or (1., 1., 1., 1.))))
    link(k, 'RGBA', keep, 'K')
    if room:
        share = node(m, unreal.MaterialExpressionScalarParameter, x-450, y+760, parameter_name='RoomCut', default_value=1.)
        link(share, '', keep, 'RM')
    if whole_fade:
        inputs = ['M', 'O', 'P', 'C', 'E', 'F', 'G'] + (['U1', 'U2', 'U3', 'U4'] if pieces else [])
        fade = custom(m, x-900, y-400, whole(pieces), inputs)
        link(mode, '', fade, 'M'); link(p, '', fade, 'P'); link(c, '', fade, 'C'); link(focus, '', fade, 'F')
        link(node(m, unreal.MaterialExpressionObjectPositionWS, x-1350, y-400), '', fade, 'O')
        eye, amount = params(m, x-1350, y-300, 'Eye', 'Fade')
        link(eye, '', fade, 'E'); link(amount, '', fade, 'G')
        for i in range(1, 5 if pieces else 1):
            link(node(m, unreal.MaterialExpressionTextureCoordinate, x-1350, y-100+100*i, coordinate_index=i), '', fade, f'U{i}')
        # Per vertex, handed to the pixels: the value is the same over a whole instance or piece.
        between = node(m, unreal.MaterialExpressionVertexInterpolator, x-450, y-400)
        link(fade, '', between, ''); link(between, '', keep, 'W')
    else:
        link(node(m, unreal.MaterialExpressionConstant, x-450, y-100, r=0.), '', keep, 'W')
    into_mask(m, keep, x+300, y, alone=old, root=root)
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
    """Cairo and the bokken: masked, dithered out within 60 cm of the camera. Their opacity mask is the see-through's
    alone, so a stale one is replaced. The first version's is the same and is kept."""
    old = stale(m)
    if (done(m) and not old) or not masked(m): return False
    keep = custom(m, -900, 900, NEAR + ' ' + DITHER, ['P', 'C', 'X'])
    link(node(m, unreal.MaterialExpressionWorldPosition, -1300, 900), '', keep, 'P')
    link(node(m, unreal.MaterialExpressionCameraPositionWS, -1300, 1000), '', keep, 'C')
    link(params(m, -1300, 1100, 'Cut')[0], '', keep, 'X')
    into_mask(m, keep, -600, 900, alone=old)
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
    """Recompile and save m; the translator's errors go to the log (the shader compiler's come later, as usual)."""
    errors = MEL.recompile_material(m)
    if errors: unreal.log_error(f'SEE-THROUGH {m.get_name()} does not compile: {"; ".join(str(e) for e in errors)}')
    E.save_loaded_asset(m)
    return not errors


def cut_scale(mi, value):
    """Give an instance its own CutScale; False when it has it already or its parent has no CutScale."""
    want = unreal.LinearColor(*value)
    have = MEL.get_material_instance_vector_parameter_value(mi, 'CutScale')
    if all(abs(getattr(have, c) - getattr(want, c)) < 1e-4 for c in 'rgba'): return False
    if not MEL.set_material_instance_vector_parameter_value(mi, 'CutScale', want):
        # The parent patched earlier in this run: the lookup by name uses its parameter list from before the patch, so
        # write the override itself (the parent's CutScale is there once it is saved).
        if tag(mi.get_editor_property('parent')) != TAG:
            unreal.log_warning(f'SEE-THROUGH {mi.get_name()}: no CutScale on its parent'); return False
        info = unreal.MaterialParameterInfo(name='CutScale', association=unreal.MaterialParameterAssociation.GLOBAL_PARAMETER,
                                            index=-1)
        values = [v for v in mi.get_editor_property('vector_parameter_values')
                  if str(v.get_editor_property('parameter_info').get_editor_property('name')) != 'CutScale']
        values.append(unreal.VectorParameterValue(parameter_info=info, parameter_value=want))
        mi.set_editor_property('vector_parameter_values', values)
    MEL.update_material_instance(mi)
    return True


def material(name):
    path = '/Game/Japan/Materials/' + name
    return E.load_asset(path) if E.does_asset_exist(path) else None


TREE = '/Game/Japan/Treehouse/Materials/M_TreeHouse'


def main():
    collection()
    changed = []
    foliage = material('M_Foliage')
    if foliage and add_mask(foliage, blend=False, scale=SCALES['M_Foliage']):    # masked already, with its own clip
        save(foliage); changed.append('M_Foliage')
    grass = material('M_Grass')
    if grass and add_mask(grass, scale=SCALES['M_Grass'], whole_fade=False):     # masked already (its instance fade)
        save(grass); changed.append('M_Grass')
    painted = material('M_Painted')
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
    for folder, prefixes in CHARACTERS:
        for path in sorted(E.list_assets(folder, recursive=False)):
            name = path.rsplit('/', 1)[-1].split('.')[0]
            if not name.startswith(prefixes): continue
            m = E.load_asset(path)
            if isinstance(m, unreal.Material) and character(m):
                save(m); changed.append(name)
    # The tree house: import_treehouse.py builds it; an earlier import carries the first version, upgraded here.
    tree = E.load_asset(TREE) if E.does_asset_exist(TREE) else None
    if tree and tag(tree) == OLD and not stale(tree) and add_mask(tree, room=True, pieces=True):
        save(tree); changed.append('M_TreeHouse')
    ready = tree is not None and tag(tree) == TAG and not stale(tree)
    unreal.log(f'SEE-THROUGH COMPLETE patched {len(changed)}: {", ".join(changed) or "nothing new"}; '
               f'M_TreeHouse {"has it" if ready else "needs unreal.treehouse"}')


if __name__ == '__main__':
    main()
