"""Step 2 of the body swap: keep the existing head and hands, replace everything else with the Tripo clothed body,
skin it on the unchanged r07 skeleton and save a reviewable rig.

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_body_swap_assemble.py

Faces of the Tripo body are classified by their baked base colour (skin, hair, white, yellow, olive, black, cream).
The head, hair, neck skin and hand skin are removed; the old `Body · head` and `Body · hands_forearms` regions stay.
Skin weights come from the r07 base body by nearest-face interpolation, pruned to four influences and smoothed.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import json, math, sys
from pathlib import Path
import bpy, bmesh
import numpy as np
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).parent))
from atelier.blender import renderdev
# ROOT (the archive) comes from _archive
BASE = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
import os
SWAP_DIR = os.environ.get('BODY_SWAP_DIR', 'body-swap-r01')
SWAP_STEM = os.environ.get('BODY_SWAP_STEM', 'WarmOriginal-BodySwap-r01')
HEADLESS = bool(os.environ.get('BODY_SWAP_HEADLESS'))
SWAP = BASE / SWAP_DIR
OUT = SWAP / 'assembled'; OUT.mkdir(exist_ok=True)
STEM = SWAP_STEM
bpy.ops.wm.open_mainfile(filepath=str(SWAP / 'fit/WarmOriginal-BodySwap-aligned.blend'))
s = bpy.context.scene; arm = next(o for o in s.objects if o.type == 'ARMATURE')
gen = bpy.data.objects['Tripo clothed body (raw, aligned)']
base = next(o for o in s.objects if o.get('base_body'))
def bone(n):
    b = arm.data.bones['mixamorig:' + n]; return arm.matrix_world @ b.head_local
NECK = bone('Neck')

# 1. classify faces by baked base colour
mat = gen.data.materials[0]
tex = next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.outputs[0].links and n.outputs[0].links[0].to_socket.name == 'Base Color')
img = tex.image; W, H = img.size
px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)[:, :, :3]
uv = gen.data.uv_layers.active.data
me = gen.data
classes = []
def classify(c):
    """Measured on this bake: skin (.93,.70,.50), tee (.92,.75,.36), white (.95,.9,.9), trousers (.41,.38,.29),
    hair (.32,.27,.24), shoes black (.18,.18,.17) / cream (.9,.86,.8). Hair and trousers are too close in colour
    to separate, so only skin, white, yellow and black are named; the rest is 'dark' and geometry decides."""
    r, g, b = c
    if max(c) < .25: return 'black'
    if min(c) > .78: return 'white'
    if r > .8 and .55 < g < .82 and .40 < b < .62: return 'skin'
    if r > .8 and g > .6 and b < .42: return 'yellow'
    return 'dark'
for p in me.polygons:
    samples = []
    for li in list(p.loop_indices):
        u = uv[li].uv
        samples.append(px[int(np.clip(u[1] % 1.0 * H, 0, H - 1)), int(np.clip(u[0] % 1.0 * W, 0, W - 1))])
    u = np.mean([uv[li].uv[:] for li in p.loop_indices], axis=0)
    samples.append(px[int(np.clip(u[1] % 1.0 * H, 0, H - 1)), int(np.clip(u[0] % 1.0 * W, 0, W - 1))])
    votes = [classify(c_) for c_ in samples]
    classes.append(max(set(votes), key=votes.count))
classes = np.array(classes)
counts = {k: int((classes == k).sum()) for k in set(classes)}
del px
# 2. remove head, hair, neck skin and hands from the generated body
centres = np.array([(p.center)[:] for p in me.polygons])
r_neck = np.hypot(centres[:, 0] - NECK.x, centres[:, 1] - NECK.y)
# head and hair: the hair core sits inside r .20 above z .20 and everything above z .21; the neck skin column above
# z .17 inside r .055 (the tee's collar base ring reaches out to r .09 at z .17 and must stay)
if HEADLESS:
    # generated without head or hands: only open the collar top if Tripo capped the neck stump
    remove = (centres[:, 2] > .15) & (r_neck < .03) & (np.abs(np.array([p.normal.z for p in me.polygons])) > .6)
else:
    remove = ((centres[:, 2] > .20) & (r_neck < .20)) | (centres[:, 2] > .21) | ((centres[:, 2] > .17) & (r_neck < .05))
# the generated neck skin and the chest fill inside the collar (r < 45 mm from z .14 up); the kept body region
# `under_sweatshirt` provides the real chest skin under the collar, so nothing generated is needed there
if not HEADLESS:
    remove |= (centres[:, 2] > .14) & (r_neck < .035)   # the tee's nape sits at r .04-.05, the neck skin inside .035
# hands: the white cuffs end at |y| .415; everything beyond is hand, and the wrist skin inside the cuff exit (a thin
# column around the arm axis, radius under 33 mm, while the cuff sits at 45 mm) goes too
# Wrists: the generated shell tapers from the cuff straight into the wrist skin (no separate tube), so the only
# clean cut is a plane at the cuff end. Find it per side from the radius profile along the arm: the cuff is
# round and over 55 mm across in both directions (it ends near |y| .345, where the kept forearm piece begins),
# the wrist narrower and the palm flat; cut after the last cuff bin.
WRIST_CUT = {}
for sign, side in (() if HEADLESS else ((1, 'Left'), (-1, 'Right'))):
    y_cut = .345
    for y0 in np.arange(.30, .40, .002):
        binm = (np.sign(centres[:, 1]) == sign) & (np.abs(centres[:, 1]) >= y0) & (np.abs(centres[:, 1]) < y0 + .002)
        if binm.sum() < 4:
            continue
        ext = centres[binm].max(axis=0) - centres[binm].min(axis=0)   # the cuff is round (x and z extents > 70 mm),
        if min(ext[0], ext[2]) > .055 and y0 + .002 <= .37:             # the wrist and the flat palm are not
            y_cut = y0 + .002
    WRIST_CUT[side] = round(float(y_cut), 4)
    remove |= (np.sign(centres[:, 1]) == sign) & (np.abs(centres[:, 1]) > y_cut)
classes_kept = classes[~remove]   # face order is preserved by the delete (only removed faces drop out)
gen.name = 'Body · outfit (Tripo skate r01)'
bm = bmesh.new(); bm.from_mesh(me)
GARMENT = bm.faces.layers.int.new('garment')   # before any BMFace reference is held (a new layer invalidates them)
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.where(remove)[0]], context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
# connected components: keep the torso (largest); drop pieces that live entirely past the wrists or inside the collar
seen = set(); comps = []
for f in bm.faces:
    if f in seen:
        continue
    stack = [f]; comp = []; seen.add(f)
    while stack:
        g = stack.pop(); comp.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h not in seen:
                    seen.add(h); stack.append(h)
    comps.append(comp)
comps.sort(key=len, reverse=True)
dropped = []
for comp in comps[1:]:
    C = np.array([f.calc_center_median()[:] for f in comp])
    past_wrist = np.abs(C[:, 1]).min() > .33
    in_collar = C[:, 2].min() > .14 and np.hypot(C[:, 0] - NECK.x, C[:, 1] - NECK.y).max() < .09
    if past_wrist or in_collar or len(comp) < 12:
        dropped.append({'faces': len(comp), 'centre': C.mean(axis=0).round(3).tolist(), 'why': 'wrist' if past_wrist else ('collar' if in_collar else 'stray')})
        bmesh.ops.delete(bm, geom=comp, context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
# straighten the cuff cut: boundary vertices past the cut plane snap onto it (the deleted faces leave a saw edge)
snapped = 0
for v in bm.verts:
    if v.is_boundary and abs(v.co.y) > .30 and not HEADLESS:
        side = 'Left' if v.co.y > 0 else 'Right'
        if abs(v.co.y) > WRIST_CUT[side] - .008:
            v.co.y = math.copysign(WRIST_CUT[side], v.co.y); snapped += 1
COMPONENTS = {'kept_components': len(comps) - len(dropped), 'dropped': dropped}
# garment tag per face from the surviving components' extents: 1 tee (torso + short sleeves), 2 white hem band,
# 3 trousers and shoes, 4 white sleeves, 0 anything else
bm.faces.ensure_lookup_table()
garments = {}
for comp in comps:
    if not comp or not comp[0].is_valid:
        continue
    C = np.array([f.calc_center_median()[:] for f in comp]); lo, hi = C.min(axis=0), C.max(axis=0)
    tag = 0
    if len(comp) > 800 and hi[2] > .15 and np.abs(C[:, 1]).max() > .2 and lo[2] > -.2: tag = 1
    elif lo[2] < -.4: tag = 3
    elif np.abs(C[:, 1]).min() > .15 and hi[2] > .05: tag = 4
    elif -.22 < lo[2] and hi[2] < -.02 and np.abs(C[:, 1]).max() < .16 and len(comp) < 800: tag = 2   # white hem band
    for f in comp:
        f[GARMENT] = tag
    garments[tag] = garments.get(tag, 0) + len(comp)
COMPONENTS['garment_faces'] = garments
bm.to_mesh(me); bm.free(); me.update()
# 3. old regions: keep head and hands, drop the rest and the old equipment
keep_regions = {'head', 'hands_forearms', 'under_sweatshirt'}   # the chest stays: it is what shows inside the collar
removed_objects = []
for o in list(s.objects):
    if o.type != 'MESH' or o is gen or o is base:
        continue
    if o.get('body_region') in keep_regions:
        o.hide_render = False; o.hide_set(False); o['hidden_by_slot'] = ''
        if o.get('body_region') == 'under_sweatshirt':   # exposed only inside the collar: keep the upper chest and
            skin = next(m for m in bpy.data.materials if m.name.startswith('Clean skin'))   # shoulders, as skin,
            o.data.materials[0] = skin                                                       # shrunk 2.5 mm inward
            _bm = bmesh.new(); _bm.from_mesh(o.data)
            _M = o.matrix_world
            def _keep(c):   # the front chest seen inside the collar, and the forearms from the elbow (inside the white sleeves,
                collar = c.z >= .13 and math.hypot(c.x - NECK.x, c.y - NECK.y) <= .042 and c.x >= NECK.x - .015   # continuous with the kept hands)
                forearm = abs(c.y) > .30 and c.z > .05     # only the last 3.5 cm inside the sleeve mouth: the base forearm is thicker than the generated sleeve higher up
                return collar or forearm
            bmesh.ops.delete(_bm, geom=[f for f in _bm.faces if not _keep(_M @ f.calc_center_median())], context='FACES')
            bmesh.ops.delete(_bm, geom=[v for v in _bm.verts if not v.link_faces], context='VERTS')
            _caps = bmesh.ops.holes_fill(_bm, edges=[e for e in _bm.edges if e.is_boundary and abs((_M @ e.verts[0].co).y) > .29 and abs((_M @ e.verts[0].co).y) < .31], sides=0)
            bmesh.ops.triangulate(_bm, faces=_caps['faces'])
            bmesh.ops.delete(_bm, geom=[v for v in _bm.verts if not v.link_faces], context='VERTS')
            _bm.normal_update()
            for v in _bm.verts:
                yy = abs((_M @ v.co).y)
                if yy < .2:
                    v.co -= v.normal * .005   # the collar fill sits well inside the collar ring
                elif yy < .33:   # the forearm skin sits 3 mm inside the (slimmer) generated sleeve, fading out at the wrist
                    v.co -= v.normal * .003 * float(min(1.0, (.33 - yy) / .02))
            _bm.to_mesh(o.data); _bm.free(); o.data.update()
        continue
    if o.get('body_region') or o.get('outfit_slot') or o.get('equipment_id'):
        removed_objects.append(o.name); bpy.data.objects.remove(o, do_unlink=True)
# 4. skin weights from the base body (nearest face, interpolated), then prune and smooth
gen.parent = arm; gen.matrix_parent_inverse = arm.matrix_world.inverted()
for g in base.vertex_groups:
    gen.vertex_groups.new(name=g.name)
dt = gen.modifiers.new('Weights from base body', 'DATA_TRANSFER')
dt.object = base; dt.use_vert_data = True; dt.data_types_verts = {'VGROUP_WEIGHTS'}; dt.vert_mapping = 'POLYINTERP_NEAREST'
dt.layers_vgroup_select_src = 'ALL'; dt.layers_vgroup_select_dst = 'NAME'
bpy.ops.object.select_all(action='DESELECT'); gen.select_set(True); bpy.context.view_layer.objects.active = gen
base.hide_viewport = False; base.hide_set(False)
bpy.ops.object.modifier_apply(modifier=dt.name)
names = [g.name for g in gen.vertex_groups]
n = len(me.vertices)
Wt = np.zeros((n, len(names)))
for v in me.vertices:
    for g in v.groups:
        Wt[v.index, g.group] = g.weight
# finger bones never drive cloth (fold them into the hand); the hand bone itself stays so the cuff follows the
# wrist like the r07 white sleeve did
for i, nm in enumerate(names):
    if 'Hand' in nm and nm.split('Hand')[1]:
        side = 'Left' if 'Left' in nm else 'Right'
        j = names.index(f'mixamorig:{side}Hand'); Wt[:, j] += Wt[:, i]; Wt[:, i] = 0
# garment-aware weights (a wide tee must not take the torso side or the thighs as its nearest body):
garment_face = np.array([d.value for d in me.attributes['garment'].data]) if 'garment' in me.attributes else np.zeros(len(me.polygons), int)
vert_garment = np.zeros(n, int)
votes = {}
for pl in me.polygons:
    for vi in pl.vertices:
        votes.setdefault(vi, []).append(int(garment_face[pl.index]))
for vi, vs in votes.items():
    vert_garment[vi] = max(set(vs), key=vs.count)
Pv = np.array([v.co[:] for v in me.vertices])
def gi(nm):
    return names.index(nm) if nm in names else None
def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)
TORSO = [nm for nm in names if any(k in nm for k in ('Hips', 'Spine', 'Neck', 'Shoulder'))]
LEGS = [nm for nm in names if any(k in nm for k in ('UpLeg', 'Leg', 'Foot', 'Toe'))]
ARMS = [nm for nm in names if any(k in nm for k in ('Arm', 'Hand'))]
tee = np.where((vert_garment == 1) | (vert_garment == 2))[0]
for i in tee:
    w = Wt[i].copy(); y, z = Pv[i][1], Pv[i][2]
    side = 'Left' if y > 0 else 'Right'
    # legs never drive the tee; at the hem a soft, side-symmetric share goes to the thigh so sitting does not
    # leave the hem inside the legs, fading to pure hips at the centre line
    leg_total = sum(w[gi(nm)] for nm in LEGS if gi(nm) is not None)
    for nm in LEGS:
        if gi(nm) is not None: w[gi(nm)] = 0
    front = float(smoothstep(-.03, .02, Pv[i][0] - NECK.x))
    hem = float(smoothstep(-.04, -.10, z)) * .8 * float(smoothstep(0, .05, abs(y))) * front      # front hem lifts with its knee
    seat = float(smoothstep(-.05, -.10, z)) * .6 * (1 - front)                                    # back hem rides the seat: both thighs equally
    if gi('mixamorig:Hips') is not None:
        w[gi('mixamorig:Hips')] += leg_total * (1 - hem - seat)
    if gi(f'mixamorig:{side}UpLeg') is not None:
        w[gi(f'mixamorig:{side}UpLeg')] += leg_total * hem
    for sd in ('Left', 'Right'):
        if gi(f'mixamorig:{sd}UpLeg') is not None:
            w[gi(f'mixamorig:{sd}UpLeg')] += leg_total * seat * .5
    # sleeves: a tee vertex whose nearest body was the arm (transferred arm share) rides the upper arm alone past
    # the shoulder, blending from the torso over the first 4 cm; torso-side vertices keep no arm share at all
    if vert_garment[i] == 1:
        arm_total = sum(w[gi(nm)] for nm in ARMS if gi(nm) is not None)
        for nm in ARMS:
            if gi(nm) is not None: w[gi(nm)] = 0
        is_sleeve = arm_total > .3 or abs(y) > .16 or (abs(y) > .105 and z > .095)   # the whole sleeve cap above the armpit
        w_arm = float(smoothstep(.09, .14, abs(y))) if is_sleeve else 0.0
        torso_total = w.sum()
        if torso_total > 1e-9:
            w *= (1 - w_arm) / torso_total
        elif w_arm < 1:
            w[gi('mixamorig:Spine2')] += 1 - w_arm
        # when the long white sleeves belong to the same component, the arm share bends at the elbow (bone at
        # |y| .223) and hands the wrist to the hand bone (bone at .357)
        keep = float(smoothstep(.17, .22, abs(y)))     # past the elbow: the transferred forearm weights, as the
        if keep > 0 and arm_total > 1e-6:               # r07 white sleeve had, so the sleeve mouth moves with the wrist
            wt = Wt[i]
            trans = {nm: wt[gi(nm)] / arm_total for nm in ARMS if gi(nm) is not None}
            for nm, share in trans.items():
                w[gi(nm)] += w_arm * keep * share
        w[gi(f'mixamorig:{side}Arm')] += w_arm * (1 - keep)
    Wt[i] = w / max(w.sum(), 1e-9)
# layered hems: the tee hem and the white band lie on the trousers, so below the waist they take the weights of the
# nearest trouser vertex and move with it (any independent rule leaves the two surfaces crossing when the hips flex)
from mathutils.kdtree import KDTree
trouser_idx = np.where(vert_garment == 3)[0]
if len(trouser_idx):
    kd = KDTree(len(trouser_idx))
    for k, i in enumerate(trouser_idx):
        kd.insert(Vector(Pv[i]), k)
    kd.balance()
    copied = 0
    for i in np.where(((vert_garment == 1) | (vert_garment == 2)) & (Pv[:, 2] < -.04))[0]:
        co, k, dist = kd.find(Vector(Pv[i]))
        if dist is not None and dist < .04:
            Wt[i] = Wt[trouser_idx[k]]; copied += 1
    HEM_COPIED = copied
nbrs = [[] for _ in range(n)]
for e in me.edges:
    a, b = e.vertices; nbrs[a].append(b); nbrs[b].append(a)
for _ in range(3):
    new = Wt.copy()
    for i in range(n):
        if nbrs[i]:
            new[i] = .5 * Wt[i] + .5 * Wt[nbrs[i]].mean(axis=0)
    Wt = new
# prune to four influences and normalise
order = np.argsort(-Wt, axis=1)[:, :4]
mask = np.zeros_like(Wt, bool)
np.put_along_axis(mask, order, True, axis=1)
Wt = np.where(mask, Wt, 0); Wt /= np.maximum(Wt.sum(axis=1, keepdims=True), 1e-9)
for g in list(gen.vertex_groups):
    gen.vertex_groups.remove(g)
groups = [gen.vertex_groups.new(name=nm) for nm in names]
for j, g in enumerate(groups):
    idx = np.where(Wt[:, j] > 1e-6)[0]
    for i in idx:
        g.add([int(i)], float(Wt[i, j]), 'REPLACE')
for g in list(gen.vertex_groups):
    if not any(gr.group == g.index for v in me.vertices for gr in v.groups):
        gen.vertex_groups.remove(g)
# the white collar band (white faces inside the collar zone) sits 1.5 mm inward so it neither pokes through the tee at
# the shoulder corners nor z-fights with the tee front
band_verts = set()
for pl in me.polygons:
    c = pl.center
    if garment_face[pl.index] in (0, 1) and c.z > .13 and math.hypot(c.x - NECK.x, c.y - NECK.y) < .09 and classes_kept[pl.index] == 'white':
        band_verts.update(pl.vertices)
for vi in band_verts:
    v = me.vertices[vi]; v.co -= v.normal * .0015
me.update()
# 2 mm of cloth thickness inward so sleeve mouths, hem and collar have a lit inner surface instead of backfaces
sol = gen.modifiers.new('Cloth thickness', 'SOLIDIFY'); sol.thickness = .002; sol.offset = -1; sol.use_rim = True; sol.use_even_offset = False
bpy.ops.object.select_all(action='DESELECT'); gen.select_set(True); bpy.context.view_layer.objects.active = gen
bpy.ops.object.modifier_apply(modifier=sol.name)
mod = gen.modifiers.new('Skeleton', 'ARMATURE'); mod.object = arm; mod.use_deform_preserve_volume = True   # dual quaternions: no candy-wrapper collapse at the sleeve caps
# 5. matte material: keep the baked base colour, flatten roughness and metallic
bsdf = mat.node_tree.nodes.get('Principled BSDF')
if bsdf:
    for name, val in (('Roughness', .85), ('Metallic', 0.0), ('Specular IOR Level', .3)):
        if name in bsdf.inputs:
            for l in list(bsdf.inputs[name].links):
                mat.node_tree.links.remove(l)
            bsdf.inputs[name].default_value = val
mat.name = 'Outfit · Tripo skate r01'
gen['equipment_id'] = 'warm-body-swap-skate-r01'
gen['body_region'] = 'outfit_body'
base.hide_render = True; base.hide_set(True); base.hide_viewport = True
arm.data.pose_position = 'POSE'
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f'{STEM}.blend'))
report = {'classes': counts, 'components': COMPONENTS, 'hem_copied_from_trousers': globals().get('HEM_COPIED', 0), 'faces_with_thickness': len(me.polygons), 'wrist_cut': WRIST_CUT, 'cuff_edge_snapped': snapped, 'removed_faces': int(remove.sum()), 'faces_left': len(me.polygons), 'vertices': len(me.vertices),
          'removed_objects': removed_objects, 'kept_regions': sorted(keep_regions), 'groups': len(gen.vertex_groups),
          'bones': len(arm.data.bones), 'actions': len(bpy.data.actions)}
(OUT / 'assembly.json').write_text(json.dumps(report, indent=2) + '\n')
print('ASSEMBLED', json.dumps(report))
