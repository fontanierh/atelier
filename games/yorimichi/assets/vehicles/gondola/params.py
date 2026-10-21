"""Shared parameters of the gondola ropeway pieces (plain Python, read by build.py, walk.py and render.py).

Metres. The route-dependent values (tower height, rope gauge, hanger length) are parameters here, recorded with the
attachment points they move in manifest.json. Override any of them with a JSON file named by $GONDOLA_PARAMS, for
example {"gauge": 6.4, "tower_heights": [12, 18]}; the build records the values it used.
"""
import json
import os

BUILD_SOURCES = ('build.py', 'cabin.py', 'checks.py', 'params.py', 'rope.py',
                 'solid.py', 'stations.py', 'textures.py', 'tower.py', 'walk.py')

DEFAULTS = {
    # Ropeway
    'gauge': 6.0,               # distance between the two haul ropes (up and down track) = bullwheel rope-line diameter
    'rope_radius': 0.045,       # 90 mm haul rope (six strands; stylised thick, as in the concept)
    'hanger_length': 1.45,      # rope axis down to the cabin roof top
    # Cabin (x along the rope, door on the -y face, which faces away from the line centre)
    'cabin_length': 2.30,       # exterior, along the rope
    'cabin_width': 2.10,        # exterior, across the rope
    'cabin_floor_to_roof': 2.30,  # interior floor top to the roof deck top
    'cabin_floor_depth': 0.20,  # interior floor top down to the underside of the skirt
    'door_clear_width': 1.00,
    'door_clear_height': 2.05,
    # Towers: rope saddle height above the foundation datum, one exported model per height
    'tower_heights': [10.0, 13.0, 16.0, 20.0, 24.0, 28.0],
    'review_tower_height': 16.0,
    # Stations: platform top is z = 0; the cabin floor stands this much above it in the berth
    'berth_floor_step': 0.02,
    'berth_x': 3.4,             # cabin centre in the berth, along the line (+x leaves the station)
    'pit_depth': 0.28,          # the cabin's channel beside the platform edge
}


def load():
    p = dict(DEFAULTS)
    path = os.environ.get('GONDOLA_PARAMS')
    if path:
        p.update(json.loads(open(path).read()))
    return p


def derived(p):
    """Values that follow from the parameters (shared by every piece)."""
    d = {}
    d['rope_height_above_platform'] = p['berth_floor_step'] + p['cabin_floor_to_roof'] + p['hanger_length']
    d['grip_to_floor'] = p['cabin_floor_to_roof'] + p['hanger_length']          # rope axis down to the cabin floor top
    half_l, half_w = p['cabin_length'] / 2, p['cabin_width'] / 2
    r = p['gauge'] / 2
    d['bullwheel_rope_radius'] = r
    d['cabin_inner_face_offset'] = r - half_w                                    # from the line centre, on a straight
    d['cabin_outer_face_offset'] = r + half_w
    d['turn_sweep_outer_radius'] = ((r + half_w) ** 2 + half_l ** 2) ** 0.5
    d['turn_sweep_inner_radius'] = r - half_w
    return d


def asset_names():
    """Canonical runtime mesh/collision closure, shared by preparation and import."""
    cabin=['GD_Cabin'+suffix for suffix in ('','Hanger','Grip','DoorLeft','DoorRight','_Collision')]
    towers=[f'GD_Tower_{height:g}m{suffix}' for height in DEFAULTS['tower_heights'] for suffix in ('','_Collision')]
    stations=[f'GD_Station{kind}_{part}' for kind in ('Valley','Rim','Crater')
              for part in ('Platform','Machinery','Fittings','Building','Collision')]
    return cabin+towers+stations


def product_files():
    return ['manifest.json','review/walk_report.json',
            *(f'layout_{kind}.json' for kind in ('cabin','valley','rim','crater')),
            *(f'assets/{name}.fbx' for name in asset_names()),
            *(f'textures/GD_{name}_{kind}.png' for name in
              ('wood_panel','wood_grain','wood_grain_light','wood_grain_dark','deck_planks','shingle')
              for kind in ('color','rough'))]


def source_hash():
    """The exact normal kit preparation identity; no Blender import is needed."""
    import hashlib
    from pathlib import Path
    here=Path(__file__).resolve().parent
    digest=hashlib.sha256()
    files=[(name,here/name) for name in sorted(BUILD_SOURCES)]
    files.append(('world/solid_mesh.py',here.parents[2]/'world/solid_mesh.py'))
    for name,path in files:
        digest.update(name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()[:16]
