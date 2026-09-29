"""Review Tripo's auto-rig on the fox hunter: diagnostic poses, still renders, a reel, and a web preview.

blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/review_fox_rig.py -- \
    --input output/imagegen/yorimichi-fox-hunter-2026-09-13/tripo-rig-r01/raw/output_model_url.glb \
    --output output/imagegen/yorimichi-fox-hunter-2026-09-13/tripo-rig-r01/blender --name FoxHunter-Rig-r01 [--no-reel]

The raw provider GLB is not modified. The rigged mesh and skeleton are used as delivered (one material, so no
transfer back to the native mesh is needed, unlike the player character). Six movement tests of 60 frames each
at 24 fps form one 360-frame diagnostic action. Rotations are authored in armature space (character faces +X,
its left is +Y, up is +Z) and converted into each bone's local frame, so the tests do not depend on bone rolls.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, base64, json, math, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

ap = argparse.ArgumentParser()
ap.add_argument('--input', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
ap.add_argument('--name', required=True)
ap.add_argument('--no-reel', action='store_true')
ap.add_argument('--texture-size', type=int, default=2048)
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = a.output.resolve(); out.mkdir(parents=True, exist_ok=True)
FPS, SEG = 24, 60

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(a.input.resolve()))
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
body = max(meshes, key=lambda m: len(m.data.vertices))
removed_names = [m.name for m in meshes if m is not body]
for m in meshes:
    if m is not body:
        bpy.data.objects.remove(m, do_unlink=True)  # Tripo's stray placeholder sphere
scene = bpy.context.scene
scene.render.fps = FPS

# --- inspection -------------------------------------------------------------------------------------------
bones = [dict(name=b.name, parent=b.parent.name if b.parent else None, head=[round(c, 4) for c in b.head_local],
              length=round(b.length, 4)) for b in arm.data.bones]
verts = body.data.vertices
unweighted = sum(1 for v in verts if not v.groups)
max_inf = max(len(v.groups) for v in verts)
sums = [sum(g.weight for g in v.groups) for v in verts]
inspection = dict(source=str(a.input), armature=arm.name, bone_count=len(bones), bones=bones, mesh=body.name,
                  vertices=len(verts), polygons=len(body.data.polygons), unweighted_vertices=unweighted,
                  max_influences=max_inf, weight_sum_min=round(min(sums), 5), weight_sum_max=round(max(sums), 5),
                  materials=[m.name for m in body.data.materials], dimensions=[round(d, 4) for d in body.dimensions],
                  removed_objects=removed_names, fps=FPS, frames=6 * SEG)

# --- diagnostic action ------------------------------------------------------------------------------------
def B(n):
    return arm.pose.bones['mixamorig:' + n]

rest_rot = {pb.name: pb.bone.matrix_local.to_3x3() for pb in arm.pose.bones}

def world_rot(pb, axis, deg):
    """Rotate a bone about an armature-space axis by deg; returns the local quaternion."""
    R = Matrix.Rotation(math.radians(deg), 3, axis)
    M = rest_rot[pb.name]
    if pb.parent:
        # local pose rotation is expressed in the bone's rest frame; parent chain handled by Blender
        pass
    return (M.inverted() @ R @ M).to_quaternion()

for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'
arm.animation_data_create()
action = bpy.data.actions.new(a.name + '-diagnostic')
arm.animation_data.action = action

def key_all(frame, pose):
    """pose: {bone short name: list of (axis, deg)} ; unnamed bones get identity."""
    for pb in arm.pose.bones:
        q = Matrix.Identity(3).to_quaternion()
        short = pb.name.replace('mixamorig:', '')
        for axis, deg in pose.get(short, []):
            q = q @ world_rot(pb, axis, deg)
        pb.rotation_quaternion = q
        pb.keyframe_insert('rotation_quaternion', frame=frame)

def mirror(pose):
    """Swap Left/Right and flip the sign of Y and Z rotations so the mirrored side moves the same way."""
    out = {}
    for k, rots in pose.items():
        mk = k.replace('Left', 'TMP').replace('Right', 'Left').replace('TMP', 'Right')
        out[mk] = [(ax, -deg if ax in ('X', 'Z') else deg) for ax, deg in rots]
    return out

TESTS = [
    ('rest', 'Rest pose', {}, {}),
    ('shoulders', 'Shoulders', {'LeftArm': [('X', -70)], 'RightArm': [('X', 70)]},
     {'LeftArm': [('Z', -70)], 'RightArm': [('Z', 70)]}),
    ('elbows', 'Elbows and wrists', {'LeftForeArm': [('Z', -90)], 'RightForeArm': [('Z', 90)]},
     {'LeftForeArm': [('Z', -60)], 'RightForeArm': [('Z', 60)], 'LeftHand': [('X', -35)], 'RightHand': [('X', 35)]}),
    ('knees', 'Hips, knees and ankles', {'LeftUpLeg': [('Y', -60)], 'LeftLeg': [('Y', 80)], 'LeftFoot': [('Y', -25)]},
     {'RightUpLeg': [('Y', -60)], 'RightLeg': [('Y', 80)], 'RightFoot': [('Y', 25)]}),
    ('head', 'Head and torso', {'Head': [('Z', 40)], 'Neck': [('Z', 10)]},
     {'Head': [('Z', -30)], 'Spine': [('Y', 20)], 'Spine1': [('Y', 15), ('Z', -20)], 'Spine2': [('Z', -15)]}),
    ('stride', 'Alternating legs',
     {'LeftUpLeg': [('Y', -35)], 'RightUpLeg': [('Y', 25)], 'RightLeg': [('Y', 45)], 'LeftFoot': [('Y', 15)],
      'LeftArm': [('X', -70), ('Z', 25)], 'RightArm': [('X', 70), ('Z', 25)], 'Spine1': [('Z', 8)]},
     None),  # None = mirror of pose A
]
stills = {}
for i, (slug, label, pa, pb_) in enumerate(TESTS):
    base = i * SEG
    if pb_ is None:
        pb_ = mirror(pa)
    key_all(base, {}); key_all(base + 15, pa); key_all(base + 30, {}); key_all(base + 45, pb_); key_all(base + SEG - 1, {})
    stills[slug] = base + 15
scene.frame_start, scene.frame_end = 0, 6 * SEG - 1
inspection['tests'] = [dict(slug=s, label=l, start=i * SEG, peak_a=i * SEG + 15, peak_b=i * SEG + 45) for i, (s, l, _, _) in enumerate(TESTS)]

# --- review scene: camera, light, materials ----------------------------------------------------------------
h = body.dimensions.z
cam_data = bpy.data.cameras.new('ReviewCam'); cam = bpy.data.objects.new('ReviewCam', cam_data); scene.collection.objects.link(cam)
cam_data.lens = 60
target = Vector((0, 0, h * 0.5))
cam.location = Vector((h * 1.75, -h * 1.3, h * 0.62))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam
sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN')); scene.collection.objects.link(sun)
sun.data.energy = 3.0; sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
fill = bpy.data.objects.new('Fill', bpy.data.lights.new('Fill', 'SUN')); scene.collection.objects.link(fill)
fill.data.energy = 1.2; fill.rotation_euler = (math.radians(60), 0, math.radians(-140))
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (0.6, 0.62, 0.65, 1)
world.node_tree.nodes['Background'].inputs[1].default_value = 0.8
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = scene.render.resolution_y = 900
scene.render.image_settings.file_format = 'PNG'
for mat in body.data.materials:
    if mat.use_nodes:
        n = mat.node_tree.nodes.get('Principled BSDF')
        if n:
            n.inputs['Roughness'].default_value = 0.85
            n.inputs['Metallic'].default_value = 0.0

for slug, frame in stills.items():
    scene.frame_set(frame)
    scene.render.filepath = str(out / f'{slug}.png')
    bpy.ops.render.render(write_still=True)
if not a.no_reel:
    scene.render.filepath = str(out / 'deformation-frames') + '/'
    bpy.ops.render.render(animation=True)

# --- exports ------------------------------------------------------------------------------------------------
bpy.ops.wm.save_as_mainfile(filepath=str(out / f'{a.name}.blend'))
for o in bpy.data.objects:
    o.select_set(o in (arm, body))
bpy.ops.export_scene.gltf(filepath=str(out / f'{a.name}.glb'), export_format='GLB', use_selection=True,
                          export_animations=True, export_skins=True, export_force_sampling=True, export_yup=True)
# web preview: JSON glTF + geometry as a script + JPEG textures, same contract as export_preview_gltf.py
for im in bpy.data.images:
    if im.size[0] > a.texture_size:
        im.scale(a.texture_size, a.texture_size)
prev = out.parent / 'preview'; prev.mkdir(exist_ok=True)
gltf = prev / f'{a.name}.gltf'
bpy.ops.export_scene.gltf(filepath=str(gltf), export_format='GLTF_SEPARATE', use_selection=True,
                          export_image_format='JPEG', export_jpeg_quality=85, export_texture_dir='tex',
                          export_animations=True, export_skins=True, export_force_sampling=True, export_yup=True)
doc = json.loads(gltf.read_text())
assert len(doc['buffers']) == 1
b = doc['buffers'][0]; blob = (gltf.parent / b['uri']).read_bytes(); (gltf.parent / b['uri']).unlink()
del b['uri']; b['byteLength'] = len(blob); gltf.write_text(json.dumps(doc))
(prev / f'{a.name}.buffer.js').write_text('window.GLTF_BUFFER_B64="' + base64.b64encode(blob).decode() + '";\n')
inspection['exports'] = dict(blend=f'{a.name}.blend', glb=f'{a.name}.glb', preview_gltf=str(gltf.relative_to(out.parent)),
                             preview_buffer_bytes=len(blob), animations=[x['name'] for x in doc.get('animations', [])])
(out / 'inspection.json').write_text(json.dumps(inspection, indent=2) + '\n')
print('RIG REVIEW OK', json.dumps({k: inspection[k] for k in ('bone_count', 'vertices', 'unweighted_vertices', 'max_influences', 'weight_sum_min', 'weight_sum_max', 'removed_objects', 'exports')}))
