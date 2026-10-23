"""Control renders of the Belmonte railway track (Blender, headless, Eevee): `atelier build yorimichi world.belmonte_track_review`.

Reads the assembled separate track LOD0 GLBs and linked instances, and renders the viaduct,
a portal of the spiral tunnel, the passing loop from above, a turnout, the Belmonte buffer stop and a plan of the
whole line, on a white background without terrain. Output: build/yorimichi/belmonte-track/review/.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import argparse
import math
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Vector

from train import track as T
from train.track_review_source import Library, origins, instances

REVIEW = T.OUT / 'review'


def scene_setup():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 16
    scene.view_settings.view_transform = 'Standard'
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    world = bpy.data.worlds.new('White')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (1, 1, 1, 1)
    bg.inputs['Strength'].default_value = .7
    sun = bpy.data.lights.new('Sun', 'SUN')
    sun.energy = 3.5
    sun.angle = math.radians(3)
    o = bpy.data.objects.new('Sun', sun)
    o.rotation_euler = (math.radians(50), 0, math.radians(35))
    scene.collection.objects.link(o)
    cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
    cam.data.clip_end = 20000
    scene.collection.objects.link(cam)
    scene.camera = cam
    return scene, cam


def shoot(scene, cam, name, eye, target, lens=35., ortho=None):
    cam.location = Vector(eye)
    cam.rotation_euler = (Vector(target) - Vector(eye)).to_track_quat('-Z', 'Y').to_euler()
    if ortho:
        cam.data.type, cam.data.ortho_scale = 'ORTHO', ortho
    else:
        cam.data.type, cam.data.lens = 'PERSP', lens
    scene.render.filepath = str(REVIEW / f'{name}.png')
    bpy.ops.render.render(write_still=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=T.OUT / 'atomic/track.json')
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    REVIEW.mkdir(parents=True, exist_ok=True)
    line = T.Line()
    library = Library(args.source); doc = library.doc
    placed = origins(doc)
    for parent in doc['meshes']:
        if parent in doc['instances']:
            if parent not in doc['editor_only']: library.place(parent, instances(doc, parent))
        else:
            if parent not in placed: raise ValueError('Missing published railway placement: ' + parent)
            library.place(parent, [[*placed[parent], 0., 1.]])
    scene, cam = scene_setup()

    def at(s, u=0., v=0.):
        return tuple(float(c) for c in line.place(s, u, v))

    via = doc['viaducts'][0]
    mid = (via['start'] + via['end']) / 2
    ground = float(line.ground_at(mid))
    eye = at(mid - 60., -110., 0.)
    shoot(scene, cam, 'viaduct', (eye[0], eye[1], ground + 8.), at(mid, 0., -10.), lens=30.)
    spiral = next(t for t in doc['tunnels'] if t['name'] == 'Spiral')
    s = spiral['start']
    shoot(scene, cam, 'portal-spiral-south', at(s - 45., 9., 4.), at(s, 0., 3.), lens=35.)
    a, b = line.loop
    shoot(scene, cam, 'loop', at((a + b) / 2 - 40., -90., 70.), at((a + b) / 2, 0., 0.), lens=35.)
    shoot(scene, cam, 'turnout', at(a - 18., -4., 3.), at(a + 25., 0., 0.), lens=35.)
    end = line.length
    shoot(scene, cam, 'buffer-stop-belmonte', at(end - 22., 3.5, 2.2), at(end - T.BUFFER_OFFSET, 0., 1.), lens=40.)
    xy = np.asarray([line.frame(s)[0] for s in np.linspace(0, end, 50)])
    lo, hi = xy.min(0), xy.max(0)
    centre = (lo + hi) / 2
    shoot(scene, cam, 'plan', (centre[0], centre[1], hi[2] + 2000.), (centre[0], centre[1] + .01, 0.),
          ortho=float(max(hi[0] - lo[0], (hi[1] - lo[1]) * 16 / 9)) * 1.1)
    print('belmonte-track review:', sorted(p.name for p in REVIEW.glob('*.png')))


if __name__ == '__main__':
    main()
