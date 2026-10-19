"""Control renders of the Belmonte station (Blender, headless, Eevee): `atelier build yorimichi world.belmonte_station_review`.

Builds the station's LOD0 meshes (station.py) with the last 320 m of track and the road's overbridge, and
renders the views Paul's elevations show (assets/belmonte/concepts/station/): front, back, both sides and the roof,
orthographic on a white background, then a three-quarter view, a platform and the stair hall. Output:
build/yorimichi/belmonte-track/review/station-*.png.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import math

import bpy
import numpy as np
from mathutils import Vector

from train import station as ST
from train import station_site as S
from train import track as T
from train import track_build as B
from train import track_render as TR

REVIEW = T.OUT / 'review'


def main():
    B.clear()
    REVIEW.mkdir(parents=True, exist_ok=True)
    line = T.Line()
    meshes, doc = T.layout(line)
    mats = B.materials()
    st = doc['station']
    for row in [*st['pieces'], *([doc['overbridge']] if doc.get('overbridge') else [])]:
        o = B.to_object(row['name'], meshes[row['name']][0], mats)
        o.location = row['origin']
    for chunk in doc['chunks']:
        if chunk['end'] > line.length - 320.:
            B.to_object(chunk['name'], meshes[chunk['name']][0], mats).location = chunk['origin']
    stop = [r for r in doc['instances']['SM_TK_BufferStop'] if np.hypot(r[0] - st['frame']['origin'][0], r[1] - st['frame']['origin'][1]) < 20]
    B.to_object('buffer', TR.merged(meshes['SM_TK_BufferStop'][0], stop), mats)
    scene, cam = TR.scene_setup()
    scene.render.resolution_x, scene.render.resolution_y = 1800, 1000
    origin = np.array(st['frame']['origin'], float)
    t = np.array([*st['frame']['along'], 0.])
    n = np.array([*st['frame']['left'], 0.])
    z = np.array([0., 0., 1.])

    def at(a, u, h):
        return tuple(float(c) for c in origin + a * t + u * n + h * z)

    mid_a, mid_u = (S.HEADHOUSE[1] - S.SHED_LENGTH) / 2, S.AXIS_U
    far = 600.
    views = [
        ('station-front', at(S.FORECOURT[1] + far, S.AXIS_U, 20.), at(0., S.AXIS_U, 20.), 105.),
        ('station-back', at(-S.SHED_LENGTH - far, S.AXIS_U, 20.), at(0., S.AXIS_U, 20.), 105.),
        ('station-side-sw', at(mid_a, far, 20.), at(mid_a, S.AXIS_U, 20.), 230.),
        ('station-side-ne', at(mid_a, -far, 20.), at(mid_a, S.AXIS_U, 20.), 230.),
        ('station-roof', at(mid_a, S.AXIS_U + .01, far), at(mid_a, S.AXIS_U, 0.), 240.),
    ]
    for name, eye, target, scale in views:
        TR.shoot(scene, cam, name, eye, target, ortho=scale)
    TR.shoot(scene, cam, 'station-three-quarter', at(130., 120., 70.), at(-40., S.AXIS_U, 12.), lens=30.)
    TR.shoot(scene, cam, 'station-platform', at(-S.SHED_LENGTH + 30., 6., 2.6), at(0., -4., 9.), lens=24.)
    TR.shoot(scene, cam, 'station-stair-hall', at(-6., -2., 2.4), at(20., -2., 12.), lens=20.)
    TR.shoot(scene, cam, 'station-overbridge', at(-229. - 60., 3., 4.), at(-229., 0., 6.), lens=35.)
    print('belmonte-station review:', sorted(p.name for p in REVIEW.glob('station-*.png')))


if __name__ == '__main__':
    main()
