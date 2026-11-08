"""Write tools/parity/island_poses.json: whole-island parity viewpoints (plan P5) from the committed world data.

    uv run python games/yorimichi_v2/tools/parity/make_island_poses.py

Every pose looks at one landmark of one world row (W00-W20), from outside and above it. Each target's coordinates come
from a committed file, named in the pose's `source`: unreal/Content/Data/*.json rows, world/regions/*/region.toml bounds,
or the terrain. Island metres (x east, y north, z up) map to Unreal cm as (100x, -100y, 100z), the same frame as
poses.json, and the pose rotation is the one the slice poses use: yaw = atan2(dy, dx) of the look direction in Unreal
axes, pitch = atan2(dz, horizontal distance), so the camera aims at the target.

Ground. The committed heightfield (unreal/Content/Data/heightmap.bin, 301 x 301 samples, 2 m apart over +-300 m, row =
+Y north) gives the ground inside its square. Outside it there is no committed heightfield, so the ground is the nearest
committed scenery sample (a tree, bush, rock or house origin from world.json or hidamari/city.json) within 150 m of the
camera, and a target's height is its own committed z or, where a region has none, the nearest sample within 400 m. A
camera is placed `height` metres above the higher of its target and that ground, so it always clears the landmark's
own level. Walls, canopies and other scenery between camera and target are not checked: a capture that shows a blocked
view is evidence of that, not a fault in the pose.
"""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
V2 = HERE.parents[1]
DATA = V2 / 'unreal' / 'Content' / 'Data'
REGIONS = V2 / 'world' / 'regions'
OUT = HERE / 'island_poses.json'
MAPS = {'donor': '/Game/Japan/Maps/Slice', 'v2': '/Game/V2/Maps/Slice'}
FOV = 60.0
NEAR_RADIUS_M = 150.0      # camera ground: nearest committed sample within this distance, else sea level
TARGET_RADIUS_M = 400.0    # target ground where a region has no committed height of its own


def load_json(relative):
    return json.loads((DATA / relative).read_text())


WORLD = load_json('world.json')
CITY = load_json('hidamari/city.json')
GONDOLA = load_json('gondola/runtime.json')
FERRY = load_json('ferry/service/service.json')
TRAIN = load_json('belmonte_train/service.json')
BELMONTE = load_json('belmonte/runtime.json')
BRINECOVE = load_json('brinecove/runtime.json')
HIPPO = load_json('hippodrome/hippodrome.json')
HEIGHTS = np.fromfile(DATA / 'heightmap.bin', dtype='<f4')
N = int(WORLD['n'])
SIZE = float(WORLD['size'])
assert HEIGHTS.size == N * N, 'heightmap.bin is not n x n float32'
HEIGHTS = HEIGHTS.reshape(N, N)      # HEIGHTS[j, i] at (xs[i], ys[j]), as gen_world.py writes it
STEP = SIZE / (N - 1)


def _scenery_samples():
    """Every non-placeholder scenery row of world.json and city.json: [x, y, z] in island metres."""
    rows = []
    for source in (WORLD['instances'], CITY['instances']):
        for values in source.values():
            for row in values:
                if isinstance(row, list) and len(row) >= 3 and all(isinstance(v, (int, float)) for v in row[:3]):
                    if row[0] or row[1] or row[2]:
                        rows.append(row[:3])
    return np.asarray(rows, dtype=np.float64)


SAMPLES = _scenery_samples()


def heightfield(x, y):
    """Bilinear height inside the committed square, or None outside it."""
    fi, fj = (x + SIZE / 2) / STEP, (y + SIZE / 2) / STEP
    if not (0 <= fi <= N - 1 and 0 <= fj <= N - 1):
        return None
    i0, j0 = min(int(fi), N - 2), min(int(fj), N - 2)
    u, v = fi - i0, fj - j0
    h = HEIGHTS
    return float((h[j0, i0] * (1 - u) + h[j0, i0 + 1] * u) * (1 - v) + (h[j0 + 1, i0] * (1 - u) + h[j0 + 1, i0 + 1] * u) * v)


def nearest_sample(x, y, radius):
    """(z, distance) of the nearest committed scenery sample within `radius` metres, or None."""
    d = np.hypot(SAMPLES[:, 0] - x, SAMPLES[:, 1] - y)
    k = int(np.argmin(d))
    if d[k] > radius:
        return None
    return float(SAMPLES[k, 2]), float(d[k])


def ground_at_camera(x, y):
    h = heightfield(x, y)
    if h is not None:
        return h
    near = nearest_sample(x, y, NEAR_RADIUS_M)
    return near[0] if near else 0.0    # sea level where no scenery is near


def terrain_target(x, y):
    """Height and how it was found, for a target with no committed z of its own."""
    h = heightfield(x, y)
    if h is not None:
        return h, 'heightmap.bin'
    near = nearest_sample(x, y, TARGET_RADIUS_M)
    if near is None:
        raise ValueError(f'no committed height within {TARGET_RADIUS_M:.0f} m of ({x}, {y})')
    return near[0], f'nearest committed scenery sample {near[1]:.0f} m away'


def region_centre(folder):
    """Centre (island metres) and the bounds' source of a region.toml bounds_cm = [x0, y0, x1, y1] in Unreal cm."""
    text = (REGIONS / folder / 'region.toml').read_text()
    x0, y0, x1, y1 = (float(v) for v in re.search(r'bounds_cm\s*=\s*\[([^\]]+)\]', text).group(1).split(','))
    return ((x0 + x1) / 200.0, -(y0 + y1) / 200.0), f'world/regions/{folder}/region.toml bounds_cm'


@dataclass(frozen=True)
class Target:
    x: float
    y: float
    z: float
    cite: str


def world_row(section, key, index=0, source=WORLD, path='unreal/Content/Data/world.json'):
    row = source[section][key][index]
    return Target(row[0], row[1], row[2], f'{path} {section}.{key}[{index}]')


def at_ground(x, y, cite):
    z, how = terrain_target(x, y)
    return Target(x, y, z, f'{cite}; z from {how}')


def region_target(folder):
    (x, y), cite = region_centre(folder)
    return at_ground(x, y, cite)


def cm_target(location, cite):
    """A point given in Unreal cm (gondola, ferry and train data): island metres, z in metres."""
    return Target(location[0] / 100.0, -location[1] / 100.0, location[2] / 100.0, cite)


def look_at(camera, target, aim_up=3.0):
    """Unreal location (cm) and rotation (degrees) of a camera at island point `camera` (m, x, y, z) that aims at
    `target` (m), `aim_up` metres above it. Yaw is atan2 of the look direction in Unreal axes (x east, y south), pitch
    is atan2 of its height over its horizontal length, as the slice poses in poses.json are made."""
    cx, cy, cz = camera
    ax, ay, az = target.x, target.y, target.z + aim_up
    dx, dy, dz = 100 * (ax - cx), -100 * (ay - cy), 100 * (az - cz)
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    location = [round(100 * cx, 2), round(-100 * cy, 2), round(100 * cz, 2)]
    return location, {'pitch': round(pitch, 2), 'yaw': round(yaw, 2), 'roll': 0.0}


def pose_from(target, bearing, distance, height):
    """Camera `distance` m out at `bearing` (degrees, island frame: 0 east, 90 north) from the target and `height` m
    above the higher of the target and the ground under it, aimed at the target. Returns the camera in island metres."""
    cx = target.x + distance * math.cos(math.radians(bearing))
    cy = target.y + distance * math.sin(math.radians(bearing))
    cz = max(target.z, ground_at_camera(cx, cy)) + height
    location, rotation = look_at((cx, cy, cz), target)
    return {'camera': (cx, cy, cz), 'location': location, 'rotation': rotation}


def village_centroid():
    buildings = WORLD['village']['buildings']
    pts = np.array([b['position'] for b in buildings], dtype=float)
    cx, cy, cz = pts.mean(axis=0)
    return Target(float(cx), float(cy), float(cz), 'unreal/Content/Data/world.json village.buildings (mean of the 5 positions)')


def hippodrome_grandstand():
    origin = HIPPO['origin']
    mesh = next(m for m in HIPPO['meshes'] if m['name'] == 'SM_HD_Grandstand')
    x, y = origin[0] + mesh['at'][0], origin[1] + mesh['at'][1]
    return Target(x, y, origin[2], 'unreal/Content/Data/hippodrome/hippodrome.json origin + SM_HD_Grandstand.at')


def city(key, index=0):
    row = CITY['instances'][key][index]
    return Target(row[0], row[1], row[2], f'unreal/Content/Data/hidamari/city.json instances.{key}[{index}]')


def gondola(station_id):
    s = next(s for s in GONDOLA['stations'] if s['id'] == station_id)
    return cm_target(s['location_cm'], f'unreal/Content/Data/gondola/runtime.json stations[{station_id}].location_cm')


def zone(file, key):
    z = next(z for z in file['zones'] if z['key'] == key)
    return Target(z['x'], z['y'], z['z'], f'{file["_path"]} zones[{key}]')


def zeppelin(key):
    s = next(s for s in WORLD['zeppelin']['stations'] if s['key'] == key)
    x, y, z = s['origin']
    return Target(x, y, z, f'unreal/Content/Data/world.json zeppelin.stations[{key}].origin')


BELMONTE = {**BELMONTE, '_path': 'unreal/Content/Data/belmonte/runtime.json'}
BRINECOVE = {**BRINECOVE, '_path': 'unreal/Content/Data/brinecove/runtime.json'}


def build_poses():
    """(name, target, bearing, distance, height, what) for every pose, in the order of the rows W00-W20."""
    skate = load_json('skatepark/park.json')
    belmonte_train = TRAIN
    hd_station_key = next(s for s in belmonte_train['stations'] if s['key'] == 'hidamari_station')
    bm_station_key = next(s for s in belmonte_train['stations'] if s['key'] == 'belmonte_station')
    ferry = {t['key']: cm_target(t['anchor_cm'], f'unreal/Content/Data/ferry/service/service.json terminals[{t["key"]}].anchor_cm')
             for t in FERRY['terminals']}
    sea_island = Target(0.0, 0.0, heightfield(0.0, 0.0), 'unreal/Content/Data/heightmap.bin at the island origin')
    sw_summit = Target(*WORLD['southwest']['island']['summit'], 'unreal/Content/Data/world.json southwest.island.summit')
    crater_floor = gondola('floor')
    crater_rim = gondola('floor_rim')
    craterpark_c = Target(850.0, 2400.0, crater_floor.z,
                          'docs/inventory/world.md W12: caldera centre (850, 2400) (craterpark/placement.py:26-31); '
                          'z is the caldera floor station')
    rim_a = sample_row('HD_NorthRockA', 0)
    trail_city = Target(*CITY['north_trail'][0], 'unreal/Content/Data/hidamari/city.json north_trail[0]')
    corridor = BELMONTE['railway_corridor'][3]
    corridor_t = at_ground(corridor[0], corridor[1],
                           'unreal/Content/Data/belmonte/runtime.json railway_corridor[3]')
    buffer_bm = cm_target(bm_station_key['buffer']['centre'],
                          'unreal/Content/Data/belmonte_train/service.json stations[belmonte_station].buffer.centre')
    platform_hd = cm_target(hd_station_key['platform']['centre'],
                            'unreal/Content/Data/belmonte_train/service.json stations[hidamari_station].platform.centre')
    lake_c = WORLD['forest_lake']['center']
    lake = Target(lake_c[0], lake_c[1], WORLD['forest_lake']['water_height'],
                  'unreal/Content/Data/world.json forest_lake.center, z = water_height')
    cabin = Target(*WORLD['forest_lake']['cabin'], 'unreal/Content/Data/world.json forest_lake.cabin')
    entry = WORLD['treehouse']['places']['entry']
    tree_entry = Target(entry['xy'][0], entry['xy'][1], entry['ground'],
                        'unreal/Content/Data/world.json treehouse.places.entry (xy, ground)')
    tree_grade = Target(*WORLD['treehouse']['grade']['center'], 'unreal/Content/Data/world.json treehouse.grade.center')
    mega_origin = Target(*WORLD['mega']['origin'], 'unreal/Content/Data/world.json mega.origin')
    mega_trail = Target(*WORLD['mega']['trail'][0], 'unreal/Content/Data/world.json mega.trail[0]')
    deck_origin = Target(*skate['origin'], 'unreal/Content/Data/skatepark/park.json origin (the deck top)')
    bowl_local = skate['spawns']['bowl']['pos']
    bowl = Target(skate['origin'][0] + bowl_local[0], skate['origin'][1] + bowl_local[1], skate['origin'][2] + bowl_local[2],
                  'unreal/Content/Data/skatepark/park.json origin + spawns.bowl.pos (park-local)')
    trail0 = WORLD['park_trail'][0]
    trail_t = Target(*trail0, 'unreal/Content/Data/world.json park_trail[0]')
    house_a = world_row('instances', 'House_A')
    house_c = world_row('instances', 'House_C')
    dock = world_row('instances', 'SW_Dock')
    gate = at_ground(-160.0, 1520.0,
                     'world/regions/w11-megapark/region.toml HD_NorthGate x -260..-60, y 1440..1600 (centre)')
    park_c = Target(-150.0, 1300.0, 127.4,
                    'docs/inventory/world.md W11: CENTRE (-150, 1300) (megapark/placement.py:18-21); z is the middle of '
                    'placement bounds z 49.3..205.46')
    w05_w = region_target('w05-forest-west')
    w05_ne = region_target('w05-forest-far-northeast')
    w05_e = region_target('w05-forest-far-east')
    w12_w = region_target('w12-volcano-west')
    hd_stable = at_ground(955.0, 447.0, 'docs/inventory/world.md W14: SITE (955, 447) (hidamari_stable/layout.py:21)')
    camp = at_ground(-54.0, -94.0, 'docs/inventory/world.md W13: Ronin camp at (-54, -94) (SwordTrainer.cpp:427)')
    camp_road = at_ground(-55.0, -71.0, 'docs/inventory/world.md W13: the road the camp faces, (-55, -71)')
    quay = zone(BRINECOVE, 'brinecove_quay')
    sea_w = at_ground(-290.0, -40.0, 'the west coast, a point on the committed heightfield')
    hd_station = city('HD_Station')
    hd_clock = city('HD_ClockHall')
    hd_temple = city('HD_Temple')
    harbour = Target(*CITY['harbor_pier_route'][0], 'unreal/Content/Data/hidamari/city.json harbor_pier_route[0]')
    gondola_hd = gondola('hidamari')
    gondola_bm = gondola('belmonte')
    zep = {k: zeppelin(k) for k in ('zeppelin_forest', 'zeppelin_city', 'zeppelin_megapark', 'zeppelin_belmonte')}
    hippo = Target(*HIPPO['origin'], 'unreal/Content/Data/hippodrome/hippodrome.json origin')
    grandstand = hippodrome_grandstand()
    town = zone(BELMONTE, 'belmonte')
    course = zone(BELMONTE, 'belmonte_course')
    poses = []

    def add(name, target, bearing, distance, height, what):
        poses.append((name, target, bearing, distance, height, what))

    # W00 island foundation: the whole island from above, and the sea views of its coast
    add('w00_island_overview', sea_island, 225, 650, 260,
        'the whole island from the south-west, over the sea')
    add('w00_sea_south_islet', sw_summit, 270, 380, 70, 'the south-west island summit from the sea to the south')
    add('w00_sea_west_coast', sea_w, 270, 260, 40, 'the west coast from the sea, looking east at the shoreline')
    # W01 start, road and houses
    add('w01_spawn_houses', house_a, 250, 55, 22, 'House A and its lot from the road, seen from the south-west')
    add('w01_road_houses_bc', house_c, 15, 60, 25, 'House C beside the road bend, seen from the east')
    # W02 Momiji Hamlet
    add('w02_hamlet_overview', village_centroid(), 300, 110, 55, 'the hamlet cluster from the west over its roofs')
    add('w02_hamlet_teahouse', Target(*WORLD['village']['buildings'][0]['position'],
                                      'unreal/Content/Data/world.json village.buildings[0] (Village_TeaHouse)'),
        200, 35, 12, 'the tea house and the lane in front of it')
    # W03 mini Mega ramp
    add('w03_mini_ramp_overview', mega_origin, 250, 90, 40, 'the mini Mega ramp from the south-west')
    add('w03_mega_trail_foot', mega_trail, 60, 55, 18, 'the foot of the ramp trail where it leaves the hamlet')
    # W04 Sunset Pier skate plaza
    add('w04_pier_deck_south', deck_origin, 270, 170, 60, 'the pier deck from the sea, south of its edge')
    add('w04_pier_bowl', bowl, 60, 45, 18, 'the bowl, looking north over the deck from the bowl spawn')
    # W05 forest
    add('w05_north_park_trail', trail_t, 225, 90, 35, 'the park trail from the south-west into the north woods')
    add('w05_west_woods', w05_w, 270, 150, 60, 'the west coast woods, from offshore to the west')
    add('w05_far_northeast', w05_ne, 270, 300, 120, 'the far north-east backdrop forest beside Belmonte')
    add('w05_far_east', w05_e, 200, 350, 150, 'the far east backdrop forest from the south-west')
    # W06 forest lake and cabin
    add('w06_lake_overview', lake, 135, 110, 55, 'the forest lake from the north-west')
    add('w06_lake_cabin', cabin, 300, 35, 12, 'the lake cabin and its shore')
    # W07 Hidamari
    add('w07_harbour_pier', harbour, 240, 110, 40, 'the harbour jetty and the fishing harbour from the south-west')
    add('w07_clock_hall', hd_clock, 200, 110, 45, 'the clock hall on the arcade side of the city')
    add('w07_temple_hillside', hd_temple, 270, 90, 35, 'the temple hillside from the south')
    add('w07_station_yard', hd_station, 250, 120, 45, 'the Hidamari station and its yard')
    # W08 southwest
    add('w08_fishing_dock', dock, 200, 60, 25, 'the fishing dock and the boat shed from the south-west')
    add('w08_temple_islet', sw_summit, 0, 240, 80, 'the south-west island with its temple, from the east over the sea')
    # W09 Brinecove
    add('w09_brinecove_quay', quay, 0, 260, 70, 'the Brinecove quay from the sea to the east')
    add('w09_brinecove_ferry', ferry['brinecove'], 150, 150, 55, 'the Brinecove ferry terminal from the south-east')
    # W10 tree house
    add('w10_treehouse_hut', tree_entry, 270, 32, 10, 'the little hut and its south porch, the tree house reveal')
    add('w10_treehouse_canopy', tree_grade, 60, 55, 25, 'the tree house canopy and rooms from the north-east')
    # W11 Super Ultra Mega Park
    add('w11_megapark_overview', park_c, 240, 300, 110, 'Super Ultra Mega Park from the south-west')
    add('w11_megapark_north_gate', gate, 270, 120, 30, 'the north gate from the south')
    # W12 volcano and Crater Park
    add('w12_crater_overview', craterpark_c, 225, 700, 350, 'the caldera and Crater Park from the south-west rim')
    add('w12_crater_rim_station', crater_rim, 120, 150, 40, 'the rim gondola station above the caldera')
    add('w12_volcano_north_flank', rim_a, 180, 260, 120, 'the volcano north flank, the rock cluster above Belmonte')
    add('w12_volcano_south_trail', trail_city, 200, 180, 60, 'the north trail from Hidamari up the volcano south flank')
    add('w12_volcano_west_flank', w12_w, 270, 300, 150, 'the volcano west flank above Mega Park')
    # W13 sword camp
    add('w13_ronin_camp', camp, 200, 45, 15, 'the Ronin camp clearing')
    add('w13_ronin_road', camp_road, 330, 60, 20, 'the road bend beside the camp')
    # W14 Hidamari stable (disabled at baseline: the site must render empty of a stable)
    add('w14_stable_site', hd_stable, 200, 90, 30, 'the disabled stable site, which must render without a stable')
    add('w14_stable_gondola', gondola_hd, 250, 70, 30, 'the Hidamari gondola station above the stable slope')
    # W15 hippodrome
    add('w15_hippodrome_overview', hippo, 150, 260, 110, 'the hippodrome track and infield from the south-east')
    add('w15_hippodrome_grandstand', grandstand, 270, 90, 30, 'the grandstand from the south')
    # W16 Belmonte
    add('w16_belmonte_town', town, 200, 150, 60, 'the Belmonte town square and its piazza')
    add('w16_belmonte_racecourse', course, 270, 220, 90, 'the Belmonte racecourse and its grandstands')
    # W17 ferry
    add('w17_ferry_hidamari_pier', ferry['hidamari'], 0, 130, 45, 'the Hidamari ferry jetty from the sea to the east')
    add('w17_ferry_brinecove_pier', ferry['brinecove'], 180, 130, 45, 'the Brinecove ferry pier from the sea to the west')
    # W18 gondola
    add('w18_gondola_hidamari_station', gondola_hd, 300, 80, 35, 'the Hidamari gondola station from the south-west')
    add('w18_gondola_crater_floor', crater_floor, 200, 140, 50, 'the caldera floor gondola station from the south-west')
    add('w18_gondola_belmonte_station', gondola_bm, 90, 110, 40, 'the Belmonte gondola station from the east')
    # W19 zeppelin (four stations)
    add('w19_zeppelin_woodland', zep['zeppelin_forest'], 180, 60, 25, 'the Woodland air station by the lake')
    add('w19_zeppelin_hidamari', zep['zeppelin_city'], 240, 90, 35, 'the Hidamari air station')
    add('w19_zeppelin_megapark', zep['zeppelin_megapark'], 270, 90, 35, 'the Mega Park air station')
    add('w19_zeppelin_belmonte', zep['zeppelin_belmonte'], 270, 120, 40, 'the Belmonte air station')
    # W20 train and cross-region routes
    add('w20_train_hidamari_platform', platform_hd, 200, 120, 40, 'the Hidamari train platform and its canopy')
    add('w20_train_corridor_viaduct', corridor_t, 270, 200, 70, 'the railway corridor below the volcano, east of Hidamari')
    add('w20_train_belmonte_buffer', buffer_bm, 0, 110, 40, 'the Belmonte train buffer and station approach')
    return poses


def sample_row(key, index):
    row = CITY['instances'][key][index]
    return Target(row[0], row[1], row[2], f'unreal/Content/Data/hidamari/city.json instances.{key}[{index}]')


def generate():
    poses = []
    for name, target, bearing, distance, height, what in build_poses():
        placed = pose_from(target, bearing, distance, height)
        cx, cy, cz = placed['camera']
        source = (f'{what}. Target at ({target.x:.2f}, {target.y:.2f}, {target.z:.2f}) m from {target.cite}. Camera at '
                  f'({cx:.2f}, {cy:.2f}, {cz:.2f}) m: {distance} m out at bearing {bearing} deg, {height} m above the '
                  f'higher of the target and the ground under it.')
        poses.append({'name': name, 'location': placed['location'], 'rotation': placed['rotation'], 'fov': FOV,
                      'source': source})
    return poses


def main(argv=None):
    poses = generate()
    names = [p['name'] for p in poses]
    if len(names) != len(set(names)):
        raise SystemExit('duplicate pose names')
    data = {'schema': 1,
            'doc': ('Whole-island visual parity viewpoints (plan P5), one or more per world row W00-W20 plus the sea views of '
                    'W00. Generated by tools/parity/make_island_poses.py from committed world data: rerun it, do not edit. '
                    'Unreal units as poses.json: location in cm (x east, y south, z up), rotation in degrees, fov horizontal. '
                    'Pose names are <wrow>_<what>; capture with --only to select a row (fnmatch globs, e.g. w07_*).'),
            'maps': MAPS, 'poses': poses}
    text = json.dumps(data, indent=2) + '\n'
    if '--check' in (argv or sys.argv[1:]):
        return 0 if OUT.read_text() == text else 1
    OUT.write_text(text)
    print(f'{len(poses)} poses in {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
