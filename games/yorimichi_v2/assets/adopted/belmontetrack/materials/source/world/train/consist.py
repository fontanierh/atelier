"""The Belmonte train's consist: which vehicles, in which order, and where each sits once coupled (plain Python).

The head of the train (the locomotive's front buffers) is at the most positive x; every vehicle's own frame keeps
x along the train, so its origin is simply shifted along X. Two coupled vehicles touch buffer to buffer: the distance
between their origins is the sum of their half-lengths over buffers. Vehicles not built yet are listed as `planned`
with their target length so the train's order and total length are already right.

`assembly()` writes build/yorimichi/belmonte-train/assembly/: consist.json (engine-agnostic: vehicles, offsets,
placements, doors, seats, collision boxes, fitted furniture) and copies of the GLBs it names. Unreal reads the same
consist.json and GLBs later.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401

from train import bake_manifest as BM
from train import layout as L  # noqa: E402

OUT = yori.OUT / 'belmonte-train'
ASSEMBLY = OUT / 'assembly'

# front to back; length over buffers in metres
VEHICLES = [
    dict(id='locomotive', title='Locomotive 4-6-2', length=L.LOCO_LENGTH, status='built', concept='locomotive/locomotive-tender--locomotive-profile.png'),
    dict(id='tender', title='Tender', length=L.TENDER_LENGTH, status='built', concept='locomotive/locomotive-tender--tender-profile-v2.png'),
    dict(id='baggage-van', title='Baggage van', length=L.LENGTH_OVER_BUFFERS, status='built'),
    dict(id='restaurant', title='Dining car', length=L.LENGTH_OVER_BUFFERS, status='built'),
    dict(id='first-class', title='First class', length=L.LENGTH_OVER_BUFFERS, status='built'),
    dict(id='second-class', title='Second class and canteen', length=L.LENGTH_OVER_BUFFERS, status='built'),
    dict(id='brake-van', title='Rear brake van', length=L.BRAKE_LENGTH, status='built'),
]


def copy_glb(glb, out_dir):
    """Copy a GLB next to consist.json."""
    shutil.copy2(glb, out_dir / glb.name)


BUILDERS = {'locomotive': L.locomotive, 'tender': L.tender, 'baggage-van': L.baggage_van, 'restaurant': L.restaurant, 'first-class': L.first_class, 'second-class': L.second_class, 'brake-van': L.brake_van}


def offsets():
    """Origin x of each vehicle, the locomotive's front buffer at x = 0."""
    x, out = 0., {}
    for v in VEHICLES:
        out[v['id']] = x - v['length'] / 2
        x -= v['length']
    return out


def assembly():
    """@cc [owner:fontanierh,label:correctness] production-furniture-assembly
    Assembly MUST validate the complete furniture bake before writing outputs, select baked LOD0
    for assembly geometry and record the summary checksum consumed by service generation.
    """
    baked = BM.read(OUT / 'furniture')
    ASSEMBLY.mkdir(parents=True, exist_ok=True)
    xs = offsets()
    contract = L.contract()
    furniture = {}
    for a in contract['assets']:
        aid = a['id']
        record = baked[aid]
        fitted = OUT / 'furniture' / f'{aid}.json'
        entry = dict(dimensions_m=a['dimensions_m'], pivot=a['pivot'], name_fr=a['name_fr'],
                     fit=json.loads(fitted.read_text())['fitted_m'])
        lod0 = OUT / 'furniture' / 'lod' / record['levels'][0]['glb']
        entry['glb'] = lod0.name
        copy_glb(lod0, ASSEMBLY)
        entry['lods'] = [dict(r, glb=f'lod/{r["glb"]}') for r in record['levels']]
        entry['cull_screen_size'] = record['cull_screen_size']
        furniture[a['id']] = entry
    vehicles, door_rules = [], None
    for v in VEHICLES:
        rec = dict(v, x=round(xs[v['id']], 4))
        if v['status'] == 'built':
            title = ''.join(p.title() for p in v['id'].split('-'))
            glb = OUT / v['id'] / f'SM_BT_{title}_LOD0.glb'
            copy_glb(glb, ASSEMBLY)
            p = json.loads((OUT / v['id'] / f'{v["id"]}-placements.json').read_text())
            door_rules = p['door_rules']
            body = BUILDERS[v['id']]().body
            rec.update(walk=list(body.walk_limits()), walk_y=body.walk_y, ends=[body.end_a, body.end_b], body_faces=[body.x_a, body.x_b],
                       railings=[list(r) for r in L.railings(body)])
            rec.update(glb=glb.name, placements=p['placements'], seats=p['seats'], doors=p['doors_runtime'],
                       door_interactions=p['doors'], interior_volumes=p['interior_volumes'],
                       exterior_volumes=p['exterior_volumes'], boarding=p['boarding'],
                       collision=[b['box'] for b in p['collision_boxes'] if b['group'] == 'fixed'],
                       collision_boxes=p['collision_boxes'],
                       rooms=[dict(name=r['name'], kind=r['kind'], box=[r['x0'], r['x1'], r['y0'], r['y1']]) for r in p['rooms']],
                       mounts=p['mounts'], reservations=p['reservations'])
        vehicles.append(rec)
    doc = dict(
        version=1, name='Belmonte train',
        furniture_bake_sha256=BM.sha(OUT / 'furniture' / 'lod' / 'summary.json'),
        frame='metres; x along the train (head at +x), y across (+Y compartment/galley side), z up from the top of the rail; '
              'each vehicle at its own origin shifted by x. Unreal: atelier.conventions.to_unreal. glTF/three.js: (x, z, -y).',
        floor_z=L.FLOOR_Z, interior_half_width=L.IN, interior_half_length=L.IN_X, body_half_length=L.BODY_X,
        gangway=dict(width=L.GANGWAY_W, height=L.GANGWAY_H), coupling=L.coupling(),
        human=dict(adult=L.HUMAN, cairo=L.CAIRO), furniture=furniture, vehicles=vehicles, door_rules=door_rules,
        notes=dict(
            collision="per vehicle, 'collision_boxes' is the full simple collision (name, part, group, box): build game "
                      "collision from it (or from the _Collision.glb). 'collision' is only the fixed boxes' extents, the "
                      "simple obstacle boxes; it has no switchable door or gangway-lock boxes",
            door_interactions="one per door: Interact opens it alone, under door_rules",
            interior_volumes="tags ['interior', 'no_sprint', 'no_climb']: inside any of them a player walks (no sprint) "
                             "and cannot climb",
            boarding="per passenger door and balcony gate: outside start (ground, z 0), the two treads upper first, the "
                     "inside end on the floor, board and alight yaws (0 faces -Y); Interact boards or alights, at a "
                     "station only",
            exterior_volumes="one 'train_exterior' box per vehicle over its body and roof, tags ['no_climb']: nobody "
                             "climbs onto the train"),
        length_m=sum(v['length'] for v in VEHICLES),
    )
    (ASSEMBLY / 'consist.json').write_text(json.dumps(doc, indent=1))
    print(f'BELMONTE TRAIN ASSEMBLY: {len(vehicles)} vehicles, {doc["length_m"]:.1f} m', flush=True)


if __name__ == '__main__':
    assembly()
