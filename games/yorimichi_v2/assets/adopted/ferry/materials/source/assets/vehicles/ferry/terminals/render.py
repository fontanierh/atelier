"""Review renders of the ferry terminals with ship C alongside, framed like the v2 concepts, plus plan views.

blender --background --factory-startup --threads 3 --python-exit-code 1 -P games/yorimichi/assets/vehicles/ferry/terminals/render.py
Opens build/yorimichi/ferry/terminals/terminals.blend (build.py), links ship C's meshes from ferry.blend at each
berth pose (site.json), adds plain stand-ins for the existing quay, promenade and pier (not part of the kit) and
writes PNGs to build/yorimichi/ferry/terminals/review/. compare.py puts them beside the concepts.
"""
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build as F  # noqa: E402
import render as R  # noqa: E402

OUT = F.OUT / 'terminals'
REVIEW = OUT / 'review'
SITE = json.loads((OUT / 'site.json').read_text())
SHIP = ('FY_Hull', 'FY_Superstructure', 'FY_Funnel', 'FY_Lifeboats', 'FY_Rails', 'FY_Masts', 'FY_Fittings')


def material(name, rgb, rough=0.85):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*R.srgb(rgb), 1); b.inputs['Roughness'].default_value = rough
    return m


def box(name, lo, hi, mat):
    me = bpy.data.meshes.new(name)
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    me.from_pydata(v, [], [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob


def ship_at(centre, heading, tag):
    with bpy.data.libraries.load(str(F.OUT / 'ferry.blend'), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in SHIP]
    for ob in dst.objects:
        ob.name = f'{ob.name}_{tag}'
        bpy.context.scene.collection.objects.link(ob)
        ob.matrix_world = Matrix.Translation((centre[0], centre[1], 0.0)) @ Matrix.Rotation(math.radians(heading), 4, 'Z')


def context(stone, paving, timber, grass):
    """Plain stand-ins for what already stands at each berth (simplified from the regions' builds)."""
    h = SITE['hidamari']['berth']; gx = h['gate'][0]
    box('HD_QuayWall', (gx - 90, -127.5, -6.0), (gx + 70, -124.5, 2.3), stone)
    box('HD_Coping', (gx - 90, -127.7, 2.225), (gx + 70, -124.3, 2.475), paving)
    box('HD_Promenade', (gx - 90, -124.3, -1.0), (gx + 70, -92.0, 2.62), paving)
    box('HD_Road', (gx - 90, -94.0, -1.0), (gx + 70, -60.0, 3.2), stone)
    box('HD_Bank', (gx - 90, -60.0, -1.0), (gx + 70, 40.0, 6.5), grass)
    for x in range(int(gx) - 90, int(gx) + 70, 3):    # the quay's timber rail, cut at the jetty root
        if gx - 8.2 < x < gx + 8.2:
            continue
        box(f'HD_RailPost{x}', (x - 0.065, -126.065, 2.45), (x + 0.065, -125.935, 3.55), timber)
    b = SITE['brinecove']['berth']; PW = b['face'] + 0.5
    box('BC_Pier', (PW, -112.0, -6.0), (PW + 13.0, 60.0, 5.25), stone)
    box('BC_Quay', (PW - 120, 60.0, -6.0), (PW + 120, 120.0, 4.5), paving)


def look(cam, pos, target, lens=24.0):
    cam.location = pos
    d = Vector(target) - Vector(pos)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens


def main():
    REVIEW.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(OUT / 'terminals.blend'))
    scene = bpy.context.scene
    for ob in list(scene.objects):
        if ob.name.startswith('ctx_'):
            bpy.data.objects.remove(ob)
    R.setup(scene)
    stone = material('ctx_stone', (150, 146, 138)); paving = material('ctx_paving', (178, 170, 156))
    timber = material('ctx_timber', (96, 66, 44)); grass = material('ctx_grass', (110, 140, 80))
    context(stone, paving, timber, grass)
    h = SITE['hidamari']['berth']; b = SITE['brinecove']['berth']
    ship_at(h['centre'], h['heading_deg'], 'hd'); ship_at(b['centre'], b['heading_deg'], 'bc')
    cam = R.camera(scene, 'Cam', size=(1536, 1024))
    gx, gy, sill = h['gate']
    views = {
        # As in the concept: from the land north-west of the jetty, the quay running away to the left, the stage on
        # its jetty in front of the ship, whose bow points right.
        'hidamari_concept': ((gx - 24.0, -108.0, 15.0), (gx + 4.0, -137.0, 5.0), 24.0),
        # Pulled back west over the promenade so the waiting house roof does not fill the foreground.
        'hidamari_concept_far': ((gx - 42.0, -110.0, 14.0), (gx + 3.0, -137.0, 5.0), 26.0),
        'hidamari_water': ((gx - 30.0, -150.0, 17.0), (gx + 6.0, -132.0, 5.0), 22.0),
        'hidamari_stage': ((gx - 14.0, -126.0, 4.2), (gx, -136.0, 6.0), 24.0),
        'hidamari_promenade': ((gx - 4.0, -108.0, 4.3), (gx + 1.0, -130.0, 5.0), 22.0),
        # The waiting house door (open sliding door, steps down to the quay), where the terminal walk starts.
        'hidamari_door': ((gx - 16.5, -126.0, h['promenade_z'] + 1.6), (gx - 19.3, -122.0, h['promenade_z'] + 1.0), 24.0),
    }
    bx, by, _ = b['gate']; PW = b['face'] + 0.5
    views.update({
        # Brinecove concept: from the pier north of the landing, looking south-west at the pavilion, landing and ship.
        'brinecove_concept': ((PW + 14.5, by + 21.0, 8.0), (PW - 2.0, by - 3.0, 6.0), 22.0),
        # From the walkway between landing and pavilion, south of both, looking north along the berth.
        'brinecove_concept_pier': ((PW + 4.5, by - 18.0, 7.2), (PW - 2.0, by + 4.0, 6.5), 24.0),
        'brinecove_landing': ((PW + 4.6, by - 7.0, 6.9), (PW + 0.5, by + 1.0, 6.4), 22.0),
        # Close-up of what carries the pavilion roof (its eave beams and king posts), seen from under it.
        'brinecove_pavilion': ((PW + 7.0, by - 8.0, 6.6), (PW + 10.5, by + 1.0, 8.6), 18.0),
    })
    # The stage lanterns on their iron arms from the middle truss's tie beam.
    views['hidamari_lanterns'] = ((gx - 4.0, gy + 8.0, sill + 1.5), (gx + 0.5, gy + 5.0, sill + 2.3), 20.0)
    only = set(filter(None, os.environ.get('TERMINAL_VIEWS', '').split(',')))  # optional subset of views
    for name, (pos, tgt, lens) in views.items():
        if only and name not in only:
            continue
        look(cam, pos, tgt, lens)
        scene.camera = cam
        scene.render.filepath = str(REVIEW / f'{name}.png')
        bpy.ops.render.render(write_still=True)
        print('rendered', scene.render.filepath)
    if only:
        return
    # Plan views straight down, 60 m across.
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = 60.0; cam.rotation_euler = (0, 0, 0)
    for name, (x, y) in (('hidamari_plan', (gx, -132.0)), ('brinecove_plan', (PW + 4.0, by + 2.0))):
        cam.location = (x, y, 120.0)
        scene.render.filepath = str(REVIEW / f'{name}.png')
        bpy.ops.render.render(write_still=True)
        print('rendered', scene.render.filepath)


if __name__ == '__main__':
    main()
