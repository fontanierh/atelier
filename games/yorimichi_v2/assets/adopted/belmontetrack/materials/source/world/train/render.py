"""Control renders of the Belmonte train shells (Blender, headless, Eevee): `atelier build yorimichi world.belmonte_train_review`.

For each coach: exterior profile and three-quarter views showing the empty interior through the glazing, the
interior views of the references (restaurant towards the bar and back; a first-class cabin towards its window and
towards the corridor), the roof-off top view and the same top view with the furniture reservations. White
backgrounds and even light, as technical references. Output: build/yorimichi/belmonte-train-authoring/review/.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import math

import bpy
from mathutils import Vector

from train import layout as L

OUT = yori.OUT / 'belmonte-train'
REVIEW = OUT / 'review'


def setup(scene):
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 24
    try:
        scene.eevee.use_raytracing = True
        scene.eevee.ray_tracing_options.resolution_scale = '1'
    except AttributeError:
        pass
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.render.film_transparent = True          # composited over white after the render (white_background)
    w = bpy.data.worlds.new('White'); scene.world = w
    bg = w.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (1, 1, 1, 1); bg.inputs['Strength'].default_value = .55
    coll = bpy.data.collections.new('Review_Lights'); scene.collection.children.link(coll)
    return coll


def light(coll, name, kind, loc, energy, size=1., rot=(0, 0, 0), color=(1, .93, .82)):
    ld = bpy.data.lights.new(name, kind); ld.energy = energy; ld.color = color
    if kind == 'AREA':
        ld.size = size
    elif kind == 'POINT':
        ld.shadow_soft_size = size
    o = bpy.data.objects.new(name, ld); o.location = loc; o.rotation_euler = rot
    coll.objects.link(o)
    return o


def interior_lights(coll, c, dx=0.):
    """Warm area lights under the ceiling of every room, standing in for the future lamps."""
    for r in c.rooms:
        length = r.x1 - r.x0
        n = max(1, round(length / 2.2))
        for k in range(n):
            x = r.x0 + length * (k + .5) / n
            y = (r.y0 + r.y1) / 2
            area = min(length / n, 2.2) * (r.y1 - r.y0)
            light(coll, f'L_{c.name}_{r.name}_{k}', 'AREA', (x + dx, y, L.ceiling_z(y) - .08), 28 * area, size=min(length / n, r.y1 - r.y0) * .8)


def camera(scene, name, loc, look, lens=24, ortho=None, res=(1600, 900)):
    cd = bpy.data.cameras.new(name)
    if ortho:
        cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else:
        cd.lens = lens
    cd.clip_start = .05; cd.clip_end = 200
    o = bpy.data.objects.new(name, cd); scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return o, res


def white_background(path):
    """Put the transparent render over plain white, so the background is white without lighting the scene white."""
    import numpy as np
    img = bpy.data.images.load(str(path))
    px = np.empty(len(img.pixels), np.float32); img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    px[:, :3] = px[:, :3] * px[:, 3:4] + (1 - px[:, 3:4])
    px[:, 3] = 1
    img.pixels.foreach_set(px.ravel()); img.filepath_raw = str(path); img.file_format = 'PNG'; img.save()
    bpy.data.images.remove(img)


def shoot(scene, cam, res, path, hide=(), show=()):
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    for c in bpy.data.collections:
        if c.name.endswith(tuple(hide)):
            c.hide_render = True
        if c.name.endswith(tuple(show)):
            c.hide_render = False
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    white_background(path)
    print(f'BELMONTE TRAIN REVIEW saved {path.name}', flush=True)


def coach_views(c):
    title = ''.join(p.title() for p in c.name.split('-'))
    bpy.ops.wm.open_mainfile(filepath=str(OUT / c.name / f'{c.name}.blend'))
    scene = bpy.context.scene
    coll = setup(scene)
    interior_lights(coll, c)
    light(coll, 'Sun', 'SUN', (0, 0, 10), 2.2, rot=(math.radians(48), math.radians(8), math.radians(35)), color=(1, 1, 1))
    base_hide = ('_Reservations', '_Collision', '_LOD2')
    views = []
    mid_z = 2.2
    b = c.body
    cx, span = (b.buffer_a + b.buffer_b) / 2, b.length
    k = span / 24
    views.append(('exterior-profile', camera(scene, 'C_profile', (cx, 40, mid_z), (cx, 0, mid_z), ortho=span + 1.5, res=(2400, int(2400 * 5.6 / (span + 1.5)))), base_hide, ()))
    views.append(('exterior-three-quarter', camera(scene, 'C_three', (cx + 21.0 * k + 3, 17.0 * k + 3, 4.2), (cx - .8 * k, 0, 2.0), lens=30, res=(2000, 1000)), base_hide, ()))
    views.append(('exterior-profile-other-side', camera(scene, 'C_profile_r', (cx, -40, mid_z), (cx, 0, mid_z), ortho=span + 1.5, res=(2400, int(2400 * 5.6 / (span + 1.5)))), base_hide, ()))
    if b.end_a == 'balcony':
        views.append(('exterior-balcony', camera(scene, 'C_balcony', (b.buffer_a - 5.5, 4.5, 3.4), (b.x_a, 0, 2.0), lens=28, res=(1600, 1000)), base_hide, ()))
    eye = L.FLOOR_Z + 1.55
    if c.name == 'restaurant':
        views.append(('interior-towards-bar', camera(scene, 'C_bar', (-8.1, 0, eye), (6.0, 0, eye - .25), lens=17), base_hide, ()))
        views.append(('interior-towards-vestibule', camera(scene, 'C_back', (3.9, 0, eye), (-9.0, 0, eye - .25), lens=17), base_hide, ()))
        views.append(('interior-towards-bar-blockout', camera(scene, 'C_bar_b', (-8.1, 0, eye), (6.0, 0, eye - .25), lens=17), ('_Collision', '_LOD2'), ('_Reservations',)))
    elif c.name == 'second-class':
        views.append(('saloon-towards-canteen', camera(scene, 'C_saloon', (9.0, 0, eye), (-7.0, 0, eye - .3), lens=17), base_hide, ()))
        views.append(('canteen', camera(scene, 'C_canteen', (-6.9, .2, eye), (-9.8, 1.2, eye - .35), lens=16), base_hide, ()))
        views.append(('saloon-blockout', camera(scene, 'C_saloon_b', (9.0, 0, eye), (-7.0, 0, eye - .3), lens=17), ('_Collision', '_LOD2'), ('_Reservations',)))
    elif c.name == 'baggage-van':
        views.append(('hold', camera(scene, 'C_hold', (10.6, .3, eye), (-7.0, 0, eye - .35), lens=17), base_hide, ()))
        views.append(('guard-room', camera(scene, 'C_bguard', (-7.9, -.6, eye), (-11.4, .6, eye - .35), lens=16), base_hide, ()))
    elif c.name == 'brake-van':
        views.append(('guard-room', camera(scene, 'C_guard', (.3, -.6, eye), (5.4, .4, eye - .35), lens=16), base_hide, ()))
        views.append(('luggage-towards-balcony', camera(scene, 'C_lug', (.6, .3, eye), (-5.0, 0, eye - .3), lens=16), base_hide, ()))
        views.append(('guard-room-blockout', camera(scene, 'C_guard_b', (.3, -.6, eye), (5.4, .4, eye - .35), lens=16), ('_Collision', '_LOD2'), ('_Reservations',)))
    else:
        cab = c.room('cabin-2'); xc = (cab.x0 + cab.x1) / 2
        views.append(('cabin-towards-window', camera(scene, 'C_window', (xc, L.ROOM_Y + .12, eye - .05), (xc, L.IN, eye - .30), lens=14), base_hide, ()))
        views.append(('cabin-towards-corridor', camera(scene, 'C_corridor', (xc + .05, L.IN - .22, eye - .05), (xc, -L.IN, eye - .30), lens=16), base_hide, ()))
        yc = -L.IN + L.CORRIDOR / 2
        views.append(('corridor', camera(scene, 'C_corr', (-9.4, yc, eye), (9.0, yc, eye - .2), lens=20), base_hide, ()))
        views.append(('cabin-towards-window-blockout', camera(scene, 'C_window_b', (xc, L.ROOM_Y + .12, eye - .05), (xc, L.IN, eye - .30), lens=14), ('_Collision', '_LOD2'), ('_Reservations',)))
    top_res = (2600, int(2600 * 4.4 / (span + 1)))
    views.append(('top-roof-off', camera(scene, 'C_top', (cx, 0, 30), (cx, 0, 0), ortho=span + 1, res=top_res), base_hide + ('_Roof',), ()))
    views.append(('top-roof-off-blockout', camera(scene, 'C_top_b', (cx, 0, 30), (cx, 0, 0), ortho=span + 1, res=top_res), ('_Collision', '_LOD2', '_Roof'), ('_Reservations',)))
    for name, (cam, res), hide, show in views:
        for col in bpy.data.collections:
            if col.name.startswith(title):
                col.hide_render = False
        shoot(scene, cam, res, REVIEW / f'{c.name}-{name}.png', hide, show)


def consist():
    """The two coaches coupled (first class at end A of the restaurant, one coupling pitch away): profile and a
    close look at the coupling, buffers and gangway faces touching."""
    bpy.ops.wm.open_mainfile(filepath=str(OUT / 'restaurant' / 'restaurant.blend'))
    scene = bpy.context.scene
    with bpy.data.libraries.load(str(OUT / 'first-class' / 'first-class.blend'), link=False) as (src, dst):
        dst.collections = [n for n in src.collections if n.startswith('FirstClass_')]
    for col in dst.collections:
        scene.collection.children.link(col)
    bpy.data.objects['BT_FirstClass'].location.x = -L.coupling()['pitch_m']
    coll = setup(scene)
    interior_lights(coll, L.restaurant())
    interior_lights(coll, L.first_class(), -L.coupling()['pitch_m'])
    light(coll, 'Sun', 'SUN', (0, 0, 10), 2.2, rot=(math.radians(48), math.radians(8), math.radians(35)), color=(1, 1, 1))
    hide = ('_Reservations', '_Collision', '_LOD2')
    cam, res = camera(scene, 'C_consist', (-12, 60, 2.2), (-12, 0, 2.2), ortho=50, res=(2800, 520))
    shoot(scene, cam, res, REVIEW / 'consist-profile.png', hide)
    cam, res = camera(scene, 'C_coupling', (-9.0, 6.5, 2.6), (-12, 0, 1.6), lens=28, res=(1600, 1000))
    shoot(scene, cam, res, REVIEW / 'consist-coupling.png', hide)
    cam, res = camera(scene, 'C_through', (-8.6, 0, L.FLOOR_Z + 1.55), (-20, 0, L.FLOOR_Z + 1.3), lens=20, res=(1600, 900))
    shoot(scene, cam, res, REVIEW / 'consist-through-gangway.png', hide)


def main(argv=None):
    import argparse
    global OUT, REVIEW
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=_Path, required=True, help='isolated legacy authoring scenes')
    args = parser.parse_args(argv)
    OUT = args.source.resolve()
    if OUT == (yori.OUT / 'belmonte-train').resolve():
        raise ValueError('Coach diagnostics require isolated authoring scenes')
    REVIEW = OUT / 'review'
    REVIEW.mkdir(parents=True, exist_ok=True)
    for c in L.coaches():
        coach_views(c)
    consist()
    print('BELMONTE TRAIN REVIEW COMPLETE', flush=True)


if __name__ == '__main__':
    main(_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
