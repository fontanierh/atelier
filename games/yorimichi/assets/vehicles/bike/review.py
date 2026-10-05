"""Review renders of the built bike against the approved turnaround, view for view.

blender -b build/yorimichi/bike/Bike.blend --python games/yorimichi/assets/vehicles/bike/review.py -- OUT_DIR
The side, front and rear cameras are orthographic and matched to the turnaround's pixel scale, so each render
overlays its reference crop exactly; the three-quarter view is a perspective match by eye.
"""
import json, sys, math
from pathlib import Path
import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import PX, P   # noqa: E402

out = Path(sys.argv[sys.argv.index('--') + 1]); out.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.view_settings.view_transform = 'Standard'
sc.render.film_transparent = True   # composited over the turnaround's paper colour
sc.eevee.taa_render_samples = 64; sc.render.filter_size = 1.2   # thin far-side spokes stay continuous
for key, value in (('shadow_ray_count', 4), ('shadow_step_count', 16)):   # soft shadows without speckle on the fenders
    if hasattr(sc.eevee, key): setattr(sc.eevee, key, value)
world = bpy.data.worlds.new('Paper'); sc.world = world; world.use_nodes = True
# A soft studio gradient: bright above, warm and darker below, so chrome has something to reflect.
nt = world.node_tree; bg = nt.nodes['Background']; bg.inputs[1].default_value = .85
tc = nt.nodes.new('ShaderNodeTexCoord'); sep = nt.nodes.new('ShaderNodeSeparateXYZ'); ramp = nt.nodes.new('ShaderNodeValToRGB')
nt.links.new(tc.outputs['Generated'], sep.inputs[0]); nt.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
# A studio horizon: a dark floor band meeting a bright sky, so chrome shows a crisp dark-to-light reflection.
ramp.color_ramp.elements[0].position = .30; ramp.color_ramp.elements[0].color = (.20, .18, .16, 1)
ramp.color_ramp.elements[1].position = .80; ramp.color_ramp.elements[1].color = (1.0, .98, .95, 1)
for pos, col in ((.47, (.36, .33, .30, 1)), (.53, (.82, .80, .77, 1))):
    e = ramp.color_ramp.elements.new(pos); e.color = col
nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
sun = bpy.data.objects.new('Key', bpy.data.lights.new('Key', 'SUN')); sc.collection.objects.link(sun)
sun.data.energy = 3.6; sun.data.angle = math.radians(40); sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
fill = bpy.data.objects.new('Fill', bpy.data.lights.new('Fill', 'SUN')); sc.collection.objects.link(fill)
fill.data.energy = .6; fill.rotation_euler = (math.radians(70), 0, math.radians(150))
floor = bpy.data.objects.new('Floor', bpy.data.meshes.new('Floor')); sc.collection.objects.link(floor)
floor.data.from_pydata([(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)], [], [(0, 1, 2, 3)])
fm = bpy.data.materials.new('FloorMat'); fm.use_nodes = True
fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.86, .83, .76, 1)
floor.data.materials.append(fm)
# One-sided like the game material, so a flipped face shows up as a hole here rather than in Unreal.
bpy.data.materials['BikePalette'].use_backface_culling = True
board = bpy.data.objects.get('BK_RackBoard')
if board: board.hide_render = True   # the turnaround shows the board only in its three-quarter view and insets
cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); sc.collection.objects.link(cam); sc.camera = cam

def shoot(name, w, h, location, rotation, ortho=None, lens=None):
    sc.render.resolution_x, sc.render.resolution_y = w, h
    cam.location = location; cam.rotation_euler = [math.radians(a) for a in rotation]
    if ortho: cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else: cam.data.type = 'PERSP'; cam.data.lens = lens
    sc.render.filepath = str(out / f'{name}.png'); bpy.ops.render.render(write_still=True)

# Side: the turnaround crop (330,0)-(1160,530) at PX metres per pixel; P() takes that crop's pixel coordinates.
c = P(415, 265)
shoot('side', 830, 530, (c.x, -4, c.z), (90, 0, 0), ortho=830 * PX)
# Front and rear are drawn at .85 of the side's scale, ground at y=960 in the full sheet.
k = PX / .85
shoot('front', 300, 430, (4, (410 - 410) * k, (960 - 765) * k), (90, 0, 90), ortho=430 * k)
shoot('rear', 280, 430, (-4, -(760 - 750) * k, (960 - 765) * k), (90, 0, -90), ortho=430 * k)
# Three-quarter front view from the drive side, as in the turnaround: the board on the rack and Cairo's sword in the
# basket (a review stand-in at the manifest's socket; in the game the sword is Cairo's own prop).
if board: board.hide_render = False
floor.hide_render = True   # the perspective camera would see the floor and horizon; keep the film transparent
info = json.loads((Path(bpy.data.filepath).parent / 'manifest.json').read_text())['rider']['basket_bokken']
wood = bpy.data.materials.new('Bokken'); wood.use_nodes = True
wood.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.36, .17, .06, 1)
tilt = Matrix.Rotation(math.radians(info['pitch_degrees']), 4, 'Y')
def piece(name, size, offset, mat=wood, kind='CUBE'):
    if kind == 'CUBE': bpy.ops.mesh.primitive_cube_add(size=1)
    else: bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=.5, depth=1)
    ob = bpy.context.object; ob.name = name; ob.scale = size; ob.data.materials.append(mat)
    ob.matrix_world = Matrix.Translation(info['tsuba']) @ tilt @ Matrix.Translation(offset) @ Matrix.Diagonal((*size, 1))
piece('BokkenBlade', (.026, .018, .22), (0, 0, -.11))
piece('BokkenGrip', (.024, .020, .12), (0, 0, .06))
piece('BokkenTsuba', (.055, .055, .008), (0, 0, 0), kind='CYL')
# Fitted to ten landmarks on the turnaround's three-quarter drawing (saddle, grips, axles, crank, bell, lamp, basket;
# elevation held at 10 degrees so the rack and basket read from above as drawn): a long lens and the drawing's tilt.
az, el, dist, lens, roll = math.radians(41.51), math.radians(10.0), 3.995, 149.3, math.radians(4.95)
target = Vector((.140, -.035, .391)); eye = target + dist * Vector((math.cos(az) * math.cos(el), -math.sin(az) * math.cos(el), math.sin(el)))
cam.location = eye; cam.rotation_euler = ((target - eye).to_track_quat('-Z', 'Y') @ Quaternion((0, 0, 1), roll)).to_euler()
sc.render.resolution_x, sc.render.resolution_y = 450, 420; cam.data.type = 'PERSP'; cam.data.lens = lens
sc.render.filepath = str(out / 'q34.png'); bpy.ops.render.render(write_still=True)
print('BIKE REVIEW RENDERED', out)
