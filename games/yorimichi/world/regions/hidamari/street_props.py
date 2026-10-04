"""Where the Tripo street props stand (tools/hidamari_props.py, fitted by props.py as HD_P_<slug>).

A prop's front faces -y before its yaw, which turns it anticlockwise seen from above (the shops' convention: yaw 90
faces +x). Along the shop streets the props stand in the two-metre seams between neighbouring 27 m lots, set back
from the shop fronts, so they never reach the riding lanes or the shops' awnings and displays; the seams take turns
in a fixed sequence. The shrine, the temples, the station square and the market get their own groups. A placement
that would overlap a building's footprint or another small object (lamp, planter, bench, bollard, another prop) is
dropped (a group's members are not checked against each other), and so is a prop without a Tripo model yet.
"""
import math

# One prop per lot seam, in this order (None: an empty seam), facing the street: a bicycle or a scooter then stands
# lengthwise in the seam, nose out.
SEAMS = ['vending_machine', 'potted_plants', 'bicycle', None, 'garbage_station', 'potted_plants', 'scooter',
         'sake_barrels', None, 'vending_machine', 'bicycle', 'potted_plants', 'postbox', None]
# half extents (m) used for the overlap checks: (along x, along y) before yaw
HALF = {'vending_machine': (.6, .45), 'potted_plants': (.65, .5), 'bicycle': (.35, .9), 'scooter': (.4, .95),
        'garbage_station': (.85, .6), 'sake_barrels': (.85, .5), 'postbox': (.4, .4), 'kei_truck': (.8, 1.75),
        'phone_booth': (.55, .55), 'bus_stop': (1.7, .8), 'stone_lantern': (.5, .5), 'komainu': (.55, .45),
        'jizo': (.4, .35), 'water_basin': (1.1, .8), 'produce_stand': (1.05, .7)}
# Fixed groups: (slug, x, y, yaw) in city metres.
GROUPS = [
    # the shrine (600, 280): guardians and lanterns along the approach from the street, the basin beside it
    ('komainu', 595.2, 262.0, 0), ('komainu', 604.8, 262.0, 0), ('stone_lantern', 594.5, 252.5, 0),
    ('stone_lantern', 605.5, 252.5, 0), ('water_basin', 612.5, 265.0, -90), ('jizo', 587.0, 266.0, 0),
    ('jizo', 588.2, 266.0, 0),
    # the temples (690, 300) and (790, 305, turned 25 degrees): lanterns before them
    ('stone_lantern', 683.0, 281.5, 0), ('stone_lantern', 697.0, 281.5, 0), ('jizo', 706.0, 283.0, 0),
    ('stone_lantern', 777.0, 288.0, 25), ('stone_lantern', 790.0, 282.0, 25),
    # the station square (station 1185, 290, 51 x 23)
    ('bus_stop', 1162.0, 244.0, 0), ('phone_booth', 1216.0, 262.0, 0), ('vending_machine', 1206.0, 276.0, 0),
    ('vending_machine', 1207.3, 276.0, 0), ('postbox', 1222.0, 250.0, 0), ('bicycle', 1148.0, 270.0, 90),
    ('bicycle', 1148.0, 271.1, 90), ('bicycle', 1148.0, 272.2, 90), ('scooter', 1148.0, 274.0, 90),
    ('kei_truck', 1228.0, 266.0, 0),
    # the market (600 and 730, -113, facing the harbour street): stalls before it, a truck between the halls
    ('produce_stand', 590.0, -103.5, 180), ('produce_stand', 611.0, -103.5, 180), ('produce_stand', 721.0, -103.5, 180),
    ('produce_stand', 741.0, -103.5, 180), ('sake_barrels', 625.0, -104.5, 180), ('kei_truck', 662.0, -106.0, 90),
    ('kei_truck', 520.0, -108.0, -90), ('garbage_station', 690.0, -105.0, 180),
]


def corners(x, y, yaw, hx, hy):
    a = math.radians(yaw); c, s = math.cos(a), math.sin(a)
    return [(x+dx*c-dy*s, y+dx*s+dy*c) for dx, dy in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]


def inside(px, py, b, margin):
    a = math.radians(b['yaw']); dx = px-b['position'][0]; dy = py-b['position'][1]
    lx = dx*math.cos(a)+dy*math.sin(a); ly = -dx*math.sin(a)+dy*math.cos(a)
    return abs(lx) < b['width']/2+margin and abs(ly) < b['depth']/2+margin


def place(put, inst, buildings, sites):
    """Add the props through put(); returns {slug: count} of those kept."""
    import yori
    modelled = {s for s in HALF if (yori.ASSETS/'hidamari'/'props'/s/f'{s}.glb').exists()}
    small = [(p[0], p[1]) for name in ('HD_Lamp', 'HD_Planter', 'HD_Bench', 'HD_Bollard') for p in inst.get(name, [])]
    trunks = [(p[0], p[1]) for name in ('Tree_Ginkgo', 'Tree_Maple_A') for p in inst.get(name, [])]
    kept = {}

    def free(slug, x, y, yaw, seam=False):
        hx, hy = HALF[slug]
        pts = corners(x, y, yaw, hx, hy)+[(x, y)]
        # In a seam the prop sits between two lots by design: only the lot footprints themselves are checked.
        if any(inside(px, py, b, -.05 if seam else .3) for b in buildings for px, py in pts): return False
        r = max(hx, hy)+.6
        return not any(math.hypot(x-sx, y-sy) < r for sx, sy in small) and not any(math.hypot(x-sx, y-sy) < r+.6 for sx, sy in trunks)

    def add(slug, x, y, yaw, seam=False, group=None):
        if slug not in modelled or not free(slug, x, y, yaw, seam): return
        put(f'HD_P_{slug}', x, y, yaw=yaw)
        (group if group is not None else small).append((x, y)); kept[slug] = kept.get(slug, 0)+1

    lots = {(round(x, 2), round(y, 2)) for _, x, y, *_ in sites}
    k = 0
    for _, x, y, yaw, cy, col, side in sorted(sites, key=lambda s: (s[4], s[6], s[1])):
        right = [(lx, ly) for lx, ly in lots if abs(ly-y) < .01 and 26 < lx-x < 28.5]
        if not right: continue
        slug = SEAMS[k % len(SEAMS)]; k += 1
        if slug is None: continue
        sx = (x+right[0][0])/2; sy = cy+side*10.6
        add(slug, sx, sy, 0 if side > 0 else 180, seam=True)
    # a group's own members stand as close as it puts them (the station's bicycle rack)
    grouped = []
    for slug, x, y, yaw in GROUPS:
        add(slug, x, y, yaw, group=grouped)
    return kept
