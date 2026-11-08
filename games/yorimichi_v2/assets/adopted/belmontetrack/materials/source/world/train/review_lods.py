"""Before/after renders of the furniture levels of detail (Blender, headless, Eevee): `atelier build yorimichi world.belmonte_train_furniture_review`.

For each asset: the fitted Tripo mesh (before), LOD0 and LOD1 from the same close camera, under the same light. Then the
second-class saloon and the restaurant furnished from their placements, once with the fitted meshes and once with LOD0.
Raw frames go to build/yorimichi/belmonte-train/review-perf/frames/; review_sheets.py lays them out side by side.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import json
import math
import sys

import bpy
from mathutils import Matrix, Vector

from train import budgets as B
from train import layout as L
from train import render as R

OUT = yori.OUT / 'belmonte-train'
FURN = OUT / 'furniture'
FRAMES = OUT / 'review-perf' / 'frames'
SCENES = None


def load(path, prefix):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        o.name = prefix + o.name
    return [o for o in new if o.type == 'MESH']


def bounds(objs):
    pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    return Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)])


def asset_frames(asset):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    coll = R.setup(scene)
    R.light(coll, 'Key', 'AREA', (2, -3, 3), 300, size=3, rot=(math.radians(50), 0, math.radians(30)), color=(1, .97, .92))
    R.light(coll, 'Sun', 'SUN', (0, 0, 10), 2.4, rot=(math.radians(45), math.radians(8), math.radians(25)), color=(1, 1, 1))
    sets = {'before': load(FURN / f'{asset}.glb', 'A_')}
    for k in (0, 1):
        p = FURN / 'lod' / f'{asset}_LOD{k}.glb'
        if p.exists():
            sets[f'lod{k}'] = load(p, f'L{k}_')
    lo, hi = bounds(sets['before'])
    c = (lo + hi) / 2; size = (hi - lo).length
    front = Vector((.55, -1.0, .45)).normalized()
    if asset == 'wall-sconce':
        front = Vector((.6, -1.0, .1)).normalized()
    cam, res = R.camera(scene, 'C', c + front * size * 1.15, c, lens=40, res=(1200, 1000))
    close, _ = R.camera(scene, 'C_close', c + front * size * .55 + Vector((0, 0, size * .05)), c + Vector((0, 0, (hi.z - lo.z) * .15)), lens=40, res=(1200, 1000))
    for label, objs in sets.items():
        for other, os_ in sets.items():
            for o in os_:
                o.hide_render = other != label
        R.shoot(scene, cam, res, FRAMES / f'{asset}-{label}.png')
        if label != 'lod1':
            R.shoot(scene, close, res, FRAMES / f'{asset}-{label}-close.png')


def furnish(coach, which):
    """Instances of every placement's asset: which = 'before' (fitted meshes) or 'lod0'."""
    p = json.loads((OUT / coach / f'{coach}-placements.json').read_text())
    protos = {}
    made = []
    for pl in p['placements']:
        a = pl['asset']
        if a not in protos:
            path = FURN / f'{a}.glb' if which == 'before' else FURN / 'lod' / f'{a}_LOD0.glb'
            if not path.exists():
                continue
            protos[a] = load(path, f'P{which}_')
            for o in protos[a]:
                o.hide_render = True
        for o in protos[a]:
            inst = o.copy(); bpy.context.scene.collection.objects.link(inst)
            inst.parent = None
            inst.matrix_world = (Matrix.Translation((pl['x'], pl['y'], pl['z'])) @ Matrix.Rotation(math.radians(pl['yaw']), 4, 'Z')
                                 @ o.matrix_world)
            inst.hide_render = False
            made.append(inst)
    return made


def coach_frames(coach, views):
    for which in ('before', 'lod0'):
        bpy.ops.wm.open_mainfile(filepath=str(SCENES / coach / f'{coach}.blend'))
        scene = bpy.context.scene
        coll = R.setup(scene)
        c = next(v for v in L.vehicles() if v.name == coach)
        R.interior_lights(coll, c)
        R.light(coll, 'Sun', 'SUN', (0, 0, 10), 2.2, rot=(math.radians(48), math.radians(8), math.radians(35)), color=(1, 1, 1))
        for o in [o for o in scene.objects if o.name.startswith('FURN_')]:
            o.hide_render = True
        furnish(coach, which)
        for name, loc, look, lens in views:
            cam, res = R.camera(scene, f'C_{name}', loc, look, lens=lens, res=(1600, 900))
            R.shoot(scene, cam, res, FRAMES / f'{coach}-{name}-{which}.png', ('_Reservations', '_Collision', '_LOD2'))


def main(argv=None):
    import argparse
    global SCENES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenes', type=_Path, required=True, help='isolated legacy authoring scenes')
    parser.add_argument('assets', nargs='*')
    args = parser.parse_args(argv)
    SCENES = args.scenes.resolve()
    if SCENES == OUT.resolve():
        raise ValueError('Furniture diagnostics require isolated authoring scenes')
    FRAMES.mkdir(parents=True, exist_ok=True)
    assets = [a for a in (args.assets or B.FURNITURE) if a in B.FURNITURE and (FURN / 'lod' / f'{a}_LOD0.glb').exists()]
    for k, a in enumerate(assets):
        print(f'REVIEW [{k + 1}/{len(assets)}] {a}', flush=True)
        asset_frames(a)
    if not args.assets:
        eye = L.FLOOR_Z + 1.55
        coach_frames('second-class', [('saloon', (9.0, 0, eye), (-7.0, 0, eye - .3), 17),
                                      ('benches-close', (4.2, -.35, eye - .1), (1.6, -.9, L.FLOOR_Z + .5), 24),
                                      ('canteen', (-6.9, .2, eye), (-9.8, 1.2, eye - .35), 16)])
        coach_frames('restaurant', [('towards-bar', (-8.1, 0, eye), (6.0, 0, eye - .25), 17),
                                    ('table-close', (-3.2, -.2, eye - .15), (-4.6, -.9, L.FLOOR_Z + .7), 24)])
    print('BELMONTE TRAIN FURNITURE REVIEW COMPLETE', flush=True)


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
