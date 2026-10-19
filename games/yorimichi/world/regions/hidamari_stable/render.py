"""Control renders of the Hidamari stable (Blender, headless, Eevee): `atelier build yorimichi world.hidamari_stable_review`.

Opens build/yorimichi/hidamari-stable/hidamari-stable.blend and sets it in its surroundings for review only: the
island's ground round the stable and the course (hidamari.layout.north_height), the hippodrome's own meshes
(build/yorimichi/hippodrome/region), and a scatter of simple autumn trees outside the clearance polygons. Warm late
afternoon sun, as Hidamari's concepts paint it.

Output in build/yorimichi/hidamari-stable/review/: road.png (from the street's end up the road), front.png (the gate
and the barn from the road), three_quarter.png, aerial.png (with the city's streets), aisle.png (inside, from the west door), plan.png (top view), lod1.png and lod2.png
(the three-quarter view of LOD1 and LOD2).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json
import math
import random

import bpy
import numpy as np
from mathutils import Vector

from hidamari import layout as H
from hidamari_stable import layout as L

OUT = yori.OUT / 'hidamari-stable'
REVIEW = OUT / 'review'
HIPPODROME = yori.OUT / 'hippodrome' / 'region'


def inside(poly, x, y):
    n = len(poly); hit = False
    for i in range(n):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            hit = not hit
    return hit


def vertex_material(name):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    nodes = mat.node_tree.nodes; bsdf = nodes['Principled BSDF']
    col = nodes.new('ShaderNodeVertexColor'); col.layer_name = 'Color'
    mat.node_tree.links.new(col.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = .9
    return mat


def mesh_object(name, verts, faces, colors, mat, coll):
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    attr = me.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
    for poly in me.polygons:
        for li in poly.loop_indices:
            attr.data[li].color = (*colors[poly.index], 1.)
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me); coll.objects.link(o)
    return o


def terrain(coll, pad_z, mat):
    """The island's ground round the stable and the course, in the stable's frame, 4 m cells."""
    sx, sy = L.SITE
    xs = np.arange(430., 1060.1, 4.); ys = np.arange(290., 760.1, 4.)
    gx, gy = np.meshgrid(xs, ys)
    z = H.north_height(gx, gy) - pad_z - .05
    ny, nx = z.shape
    verts = [(float(gx[j, i] - sx), float(gy[j, i] - sy), float(z[j, i])) for j in range(ny) for i in range(nx)]
    faces, colors = [], []
    rr = random.Random(3)
    grass = np.array(H.ISLAND_LAWN)
    for j in range(ny - 1):
        for i in range(nx - 1):
            faces.append((j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i))
            slope = abs(z[j, i + 1] - z[j, i]) + abs(z[j + 1, i] - z[j, i])
            c = grass * rr.uniform(.85, 1.12)
            if slope > 2.4:
                c = c * .5 + np.array((.16, .12, .07)) * .5
            colors.append(tuple(float(v) for v in c))
    return mesh_object('Review_Terrain', verts, faces, colors, mat, coll)


def hippodrome(coll, pad_z):
    """The course's own meshes at their place (world.hippodrome), recoloured by surface."""
    data = json.loads((HIPPODROME / 'hippodrome.json').read_text())
    ox, oy, oz = data['origin']
    for m in data['meshes']:
        path = HIPPODROME / 'glb' / f'{m["name"]}.glb'
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(path))
        for o in set(bpy.data.objects) - before:
            for c in o.users_collection:
                c.objects.unlink(o)
            coll.objects.link(o)
            if o.parent is None:
                o.location = (ox - L.SITE[0] + m['at'][0], oy - L.SITE[1] + m['at'][1], oz - pad_z + m['at'][2])
                o.rotation_euler.z += math.radians(m['yaw'])
            if o.type == 'MESH':
                for slot in o.material_slots:
                    if slot.material and slot.material.node_tree:
                        bsdf = slot.material.node_tree.nodes.get('Principled BSDF')
                        colour = {'HD_Grass': (.16, .19, .05), 'HD_Dirt': (.36, .24, .13), 'HD_Stone': (.32, .30, .26),
                                  'HD_Rail': (.85, .84, .8)}.get(slot.material.name.split('.')[0])
                        if bsdf and colour:
                            bsdf.inputs['Base Color'].default_value = (*colour, 1)
    return data['clearance']


def streets(coll, pad_z, mat):
    """Hidamari's main street (y = 335) and the north-running street the road continues, as grey ribbons on the ground."""
    sx, sy = L.SITE
    ex, ey = L.STREET_END
    pieces = [[(x, L.MAIN_STREET_Y) for x in np.arange(830., 1040.1, 4.)], [(ex, y) for y in np.arange(L.MAIN_STREET_Y, ey + .1, 3.)]]
    verts, faces, colors = [], [], []
    for pts, half in zip(pieces, (3.8, L.STREET_HALF)):
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            n = math.hypot(xb - xa, yb - ya); nx, ny = -(yb - ya) / n * half, (xb - xa) / n * half
            quad = [(xa - nx, ya - ny), (xb - nx, yb - ny), (xb + nx, yb + ny), (xa + nx, ya + ny)]
            base = len(verts)
            for x, y in quad:
                verts.append((float(x - sx), float(y - sy), float(H.north_height(np.array([x]), np.array([y]))[0]) - pad_z + .03))
            faces.append(tuple(range(base, base + 4))); colors.append((.16, .16, .17))
    return mesh_object('Review_Streets', verts, faces, colors, mat, coll)


def trees(coll, pad_z, clear, keep_out=()):
    """Autumn maples, ginkgos and pines on a jittered 10 m grid outside the clearance polygons."""
    protos = {}
    bark = bpy.data.materials.new('Tree_bark'); bark.use_nodes = True
    bark.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.12, .07, .04, 1)
    for kind, colour in (('maple', (.62, .16, .03)), ('maple_b', (.78, .36, .04)), ('ginkgo', (.80, .58, .08)), ('pine', (.05, .09, .04))):
        mat = bpy.data.materials.new(f'Tree_{kind}'); mat.use_nodes = True
        mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*colour, 1)
        mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1.
        if kind == 'pine':
            bpy.ops.mesh.primitive_cone_add(vertices=7, radius1=2.6, depth=9., location=(0, 0, 6.))
        else:
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=3.2, location=(0, 0, 6.))
        crown = bpy.context.object; crown.data.materials.append(mat)
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=.3, depth=5., location=(0, 0, 2.5))
        stem = bpy.context.object; stem.data.materials.append(bark)
        bpy.ops.object.select_all(action='DESELECT'); crown.select_set(True); stem.select_set(True)
        bpy.context.view_layer.objects.active = crown; bpy.ops.object.join()
        protos[kind] = crown.data
        bpy.data.objects.remove(crown, do_unlink=True)
    rr = random.Random(11)
    sx, sy = L.SITE
    kinds = list(protos)
    for x in np.arange(440., 1050., 10.):
        for y in np.arange(300., 750., 10.):
            px, py = x + rr.uniform(-4, 4), y + rr.uniform(-4, 4)
            if any(inside(p, px, py) for p in clear) or rr.random() < .25 or \
                    any(math.hypot(px - L.SITE[0] - cx, py - L.SITE[1] - cy) < 14. for cx, cy in keep_out):
                continue
            z = float(H.north_height(np.array([px]), np.array([py]))[0]) - pad_z
            o = bpy.data.objects.new('Tree', protos[kinds[rr.randrange(len(kinds))]]); coll.objects.link(o)
            o.location = (px - sx, py - sy, z); s = rr.uniform(.8, 1.3); o.scale = (s, s, s * rr.uniform(.9, 1.15))
            o.rotation_euler.z = rr.uniform(0, math.tau)


def setup(scene):
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 32
    scene.view_settings.view_transform = 'AgX'
    try:
        scene.view_settings.look = 'AgX - Medium High Contrast'
    except TypeError:
        pass
    scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
    w = bpy.data.worlds.new('Sky'); scene.world = w; w.use_nodes = True
    nt = w.node_tree; bg = nt.nodes['Background']
    # a warm horizon under a blue sky: the view direction's height drives the ramp
    coord = nt.nodes.new('ShaderNodeTexCoord'); sep = nt.nodes.new('ShaderNodeSeparateXYZ'); ramp = nt.nodes.new('ShaderNodeValToRGB')
    nt.links.new(coord.outputs['Generated'], sep.inputs[0])
    nt.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    ramp.color_ramp.elements[0].position = 0.; ramp.color_ramp.elements[0].color = (.80, .66, .48, 1)
    ramp.color_ramp.elements[1].position = .25; ramp.color_ramp.elements[1].color = (.22, .42, .80, 1)
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color']); bg.inputs['Strength'].default_value = 1.1
    sun = bpy.data.lights.new('Sun', 'SUN'); sun.energy = 4.2; sun.color = (1., .86, .68); sun.angle = math.radians(2.)
    o = bpy.data.objects.new('Sun', sun); scene.collection.objects.link(o)
    o.rotation_euler = (math.radians(58), 0, math.radians(-140))     # from the south-west, late afternoon


def interior_lights(scene):
    cy = L.BARN_CENTRE[1]
    for k in range(L.STALLS_PER_SIDE):
        x = L.bay_x(k)[1] + L.PART / 2
        ld = bpy.data.lights.new(f'Lantern_{k}', 'POINT'); ld.energy = 120; ld.color = (1., .72, .42); ld.shadow_soft_size = .3
        o = bpy.data.objects.new(ld.name, ld); o.location = (x, cy, L.EAVE_Z - 1.0); scene.collection.objects.link(o)
    for name in ('office', 'tack'):
        x0, y0, x1, y1, z = L.rooms()[name]['box']
        ld = bpy.data.lights.new(f'Room_{name}', 'POINT'); ld.energy = 60; ld.color = (1., .74, .45)
        o = bpy.data.objects.new(ld.name, ld); o.location = ((x0 + x1) / 2, (y0 + y1) / 2, L.ROOM_CEIL - .5); scene.collection.objects.link(o)


def camera(scene, name, at, target, lens=35, ortho=None):
    cam = bpy.data.cameras.new(name); cam.lens = lens; cam.clip_end = 3000
    if ortho:
        cam.type = 'ORTHO'; cam.ortho_scale = ortho
    o = bpy.data.objects.new(name, cam); scene.collection.objects.link(o)
    o.location = at
    o.rotation_euler = (Vector(target) - Vector(at)).to_track_quat('-Z', 'Y').to_euler()
    return o


def show_lod(lod):
    for k in (0, 1, 2):
        c = bpy.data.collections[f'LOD{k}']
        c.hide_render = k != lod; c.hide_viewport = k != lod


def main():
    bpy.ops.wm.open_mainfile(filepath=str(OUT / 'hidamari-stable.blend'))
    REVIEW.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    data = json.loads((OUT / 'placements.json').read_text())
    pad_z = data['site']['origin'][2]
    setup(scene); interior_lights(scene)
    for mat in bpy.data.materials:              # Hidamari's surfaces (HDS_<slug>) are matt earth and gravel, as in Unreal
        if mat.name.startswith('HDS_') and mat.node_tree:
            bsdf = mat.node_tree.nodes.get('Principled BSDF')
            bsdf.inputs['Roughness'].default_value = .95; bsdf.inputs['Specular IOR Level'].default_value = .1
    ctx = bpy.data.collections.new('Review_Context'); scene.collection.children.link(ctx)
    terrain(ctx, pad_z, vertex_material('Review_Ground'))
    clear = list(data['clearance']) + hippodrome(ctx, pad_z)
    cy = L.BARN_CENTRE[1]
    gx, gy = L.GATE['at']
    streets(ctx, pad_z, vertex_material('Review_Street'))
    ex, ey = L.STREET_END[0] - L.SITE[0], L.STREET_END[1] - L.SITE[1]
    rz = float(H.north_height(np.array([L.STREET_END[0] + 1.]), np.array([L.STREET_END[1] - 10.]))[0]) - pad_z
    trees(ctx, pad_z, clear, keep_out=[(gx - 21., gy - 7.), (gx - 9., gy - 2.), (-40., -26.), (ex + 1., ey - 10.)])
    shots = {
        'road': camera(scene, 'Cam_road', (ex + 1., ey - 10., rz + 1.8), (ex - 8., ey + 70., rz + 6.), 30),
        'front': camera(scene, 'Cam_front', (gx - 21., gy - 7., 2.3), (gx + 8., gy + 1., 2.6), 32),
        'three_quarter': camera(scene, 'Cam_tq', (-40., -26., 15.), (2., 9., 1.5), 30),
        'aerial': camera(scene, 'Cam_aerial', (110., -185., 95.), (-20., -45., -6.), 30),
        'gate': camera(scene, 'Cam_gate', (gx - 9., gy - 2., 2.0), (gx, gy, 2.7), 40),
        'aisle': camera(scene, 'Cam_aisle', (L.BARN_X0 - .8, cy - .6, 1.65), (L.BARN_X1, cy + .2, 1.6), 20),
        'plan': camera(scene, 'Cam_plan', (0., -2., 120.), (0., -1.99, 0.), 50, ortho=86.),
    }
    show_lod(0)
    for name, cam in shots.items():
        scene.camera = cam
        scene.render.filepath = str(REVIEW / f'{name}.png')
        bpy.ops.render.render(write_still=True)
        print(f'HIDAMARI STABLE REVIEW {name}', flush=True)
    scene.camera = shots['three_quarter']
    for lod in (1, 2):
        show_lod(lod)
        scene.render.filepath = str(REVIEW / f'lod{lod}.png')
        bpy.ops.render.render(write_still=True)
        print(f'HIDAMARI STABLE REVIEW lod{lod}', flush=True)
    print('HIDAMARI STABLE REVIEW COMPLETE', flush=True)


if __name__ == '__main__':
    main()
