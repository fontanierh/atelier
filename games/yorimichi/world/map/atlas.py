"""Region definitions and coordinate-only atlas metadata, shared by art and runtime staging.

No image generation occurs in a normal build. Paintings are committed sources;
their declared frames are checked before they can replace the generated plans.
"""
from pathlib import Path
import json
import math
import hashlib


REGIONS = (
    dict(key='momiji_coast', name='Momiji Coast', bounds=[-650., -350., 400., 350.], label=[-900., -180.],
         polygon=[[-650., -340.], [330., -340.], [330., -35.], [-650., -35.]], color='#cda46a'),
    dict(key='momiji_woods', name='Momiji Woods', bounds=[-430., -50., 440., 530.], label=[-1000., 420.],
         polygon=[[-650., -35.], [330., -35.], [330., 430.], [-650., 430.]], color='#83975a'),
    dict(key='hidamari', name='Hidamari', bounds=[280., -310., 1435., 460.], label=[1850., 0.],
         polygon=[[330., -340.], [1500., -340.], [1500., 430.], [330., 430.]], color='#bc8d70'),
    dict(key='temple_island', name='Temple Island', bounds=[-510., -820., 270., -300.], label=[-200., -850.],
         polygon=[[-650., -1000.], [330., -1000.], [330., -340.], [-650., -340.]], color='#a39aaf'),
    dict(key='northern_foothills', name='Northern Foothills', bounds=[-850., 400., 1850., 2200.],
         polygon=[[-850., 430.], [3300., 430.], [3300., 1600.], [100., 1600.], [100., 1800.], [-850., 1800.]], color='#98a06c'),
    dict(key='volcanic_highlands', name='Volcanic Highlands', bounds=[-1000., 850., 3200., 3650.],
         polygon=[[100., 1600.], [3300., 1600.], [3300., 3600.], [-850., 3600.], [-850., 1800.], [100., 1800.]], color='#9baab2'),
    dict(key='haras_valley', name='Stud Valley', bounds=[-950., 3600., 2500., 5900.],
         polygon=[[-950., 3600.], [3300., 3600.], [3300., 7100.], [-950., 7100.]], color='#83a080'),
    # The western reach west of Momiji Coast (world/regions/brinecove/region.py), stepping round the foothills' corner.
    dict(key='brinecove', name='Brinecove Reach', bounds=[-2880., -1080., -360., 600.], label=[-1600., -1000.],
         polygon=[[-2560., -1080.], [-650., -1080.], [-650., 430.], [-850., 430.], [-850., 700.], [-2560., 700.]],
         color='#c99a5e'),
)
WORLD_BOUNDS = [-4200., -1200., 4200., 7200.]
ASSETS = Path(__file__).resolve().parent / 'atlas'
GAME = Path(__file__).resolve().parents[2]
GEOGRAPHY_SOURCES = (
    'world/gen_world.py', 'world/build_terrain.py',
    'world/farhills_surface.py', 'world/farhills_grid.py', 'world/terrain_product.py', 'world/north_mountain_surface.py',
    'world/city_terrain_surface.py', 'world/regions/hidamari/build.py',
    'world/regions/hidamari/layout.py', 'world/regions/hidamari_stable/layout.py', 'world/regions/hidamari/mountains.py',
    'world/regions/hidamari/natural_terrain.py', 'world/regions/craterpark/v2/v4_config.py',
    'world/regions/belmonte/layout.py', 'world/regions/belmonte/terrain.py', 'world/regions/belmonte/plan.py',
    'world/regions/southwest/island.py', 'world/train/route.py', 'world/train/corridor.py',
    'world/train/earthworks.py', 'world/train/station_site.py',
    'world/regions/skatepark/park.json', 'world/regions/craterpark/placement.py', 'world/regions/megapark/placement.py',
    'assets/belmonte/source.json', 'assets/vehicles/belmonte-train/line.json',
    'world/regions/brinecove/region.py', 'world/regions/brinecove/layout.py', 'world/regions/brinecove/ground.py',
    'world/regions/brinecove/plan.py',
    # The split moves consumed source expressions into these narrow modules.
    # They remain signed inputs; a later helper edit must invalidate the art.
    'world/regions/hidamari/arrival_placement.py', 'world/regions/hidamari/park_grounds_placement.py',
    'world/regions/hidamari/station_yard_placement.py', 'world/regions/hidamari/temple_precinct_placement.py',
    'world/regions/belmonte/query_arrays.py', 'world/regions/belmonte/query_surface.py',
    'world/regions/belmonte/source.py', 'world/map/build_map.py',
    'world/regions/belmonte/ground_names.py', 'world/regions/belmonte/terrain_bounds.py',
    'world/regions/brinecove/ground_sampling.py', 'world/regions/brinecove/boundary.py',
)
STABLE_NAMES = (
    ('home_stables', 'Home Stables'), ('alder_stables', 'Alder Stables'),
    ('clearbridge_stables', 'Clearbridge Stables'), ('three_meadows_estate', 'Three Meadows Estate'),
    ('low_dunes_stables', 'Low Dunes Stables'), ('longstone_estate', 'Longstone Estate'),
    ('amberhill_stables', 'Amberhill Stables'),
)


def contains(polygon, x, y):
    """Boundary-inclusive polygon membership; first matching region owns shared edges."""
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if abs((x-a[0])*dy - (y-a[1])*dx) < 1e-7 and min(a[0], b[0])-1e-7 <= x <= max(a[0], b[0])+1e-7 and min(a[1], b[1])-1e-7 <= y <= max(a[1], b[1])+1e-7:
            return True
        if (a[1] > y) != (b[1] > y) and x < a[0] + (y-a[1])*dx/dy:
            inside = not inside
    return inside


def geography_signature():
    """Pin the geometry used by paintings, including changes that preserve their outer bounds."""
    # A future coastline update can introduce its shared helper without silently
    # keeping paintings signed only against the old import sites.
    optional = ('world/shorelines.py',) if (GAME / 'world/shorelines.py').exists() else ()
    return {rel: hashlib.sha256((GAME / rel).read_bytes()).hexdigest() for rel in (*GEOGRAPHY_SOURCES, *optional)}


def region_at(x, y):
    for region in REGIONS:
        if contains(region['polygon'], x, y):
            return region['key']
    return 'world'


def region_for_zone(zone):
    """@cc [owner:fontanierh,label:correctness] atlas-destination-completeness
    Every existing teleport MUST retain its key, position, yaw and travel resolver.
    Region membership MUST NOT remove a destination. A destination outside the
    named regional frames remains reachable from the world overview.
    """
    key = zone['key']
    if key in ('megapark', 'zeppelin_megapark', 'hippodrome', 'foothills'):
        return 'northern_foothills'
    if key == 'craterpark':
        return 'volcanic_highlands'
    return region_at(zone['x'], zone['y'])


def air_metadata(zones, zeppelin):
    """Ordered shuttle stops and legs from the zeppelin layout, never from painted text."""
    if not zeppelin:
        return None
    stations = zeppelin.get('stations') or []
    legs = zeppelin.get('legs') or []
    if len(stations) < 2:
        return None
    by_key = {z['key']: z for z in zones}
    stops = []
    for station in stations:
        zone = by_key.get(station.get('key'))
        if zone is None:
            raise ValueError('Atlas zeppelin station is not in the travel registry: ' + str(station.get('key')))
        stops.append(dict(key=zone['key'], name=station.get('name', zone.get('name', zone['key'])),
                          x=zone['x'], y=zone['y'], z=zone.get('z', 0.)))
    line = [stop['key'] for stop in stops]
    def find_leg(a, b):
        for leg in legs:
            if sorted(leg.get('stops', [])) == [a, b]:
                return leg
        raise ValueError('Atlas zeppelin line has no leg between stops ' + str(a) + ' and ' + str(b))
    sequential = []
    for index in range(len(line) - 1):
        leg = find_leg(index, index + 1)
        sequential.append(dict(**{key: value for key, value in leg.items() if key != 'stops'},
                               **{'from': line[index], 'to': line[index + 1]}))
    connections = []
    for leg in legs:
        indices = leg.get('stops', [])
        if len(indices) != 2 or not all(0 <= i < len(line) for i in indices):
            continue
        connections.append(dict(**{key: value for key, value in leg.items() if key != 'stops'},
                                **{'from': line[indices[0]], 'to': line[indices[1]]}))
    return dict(line=line, stops=stops, legs=sequential, connections=connections,
                note='Airship shuttle; any docked stop can choose another destination.')


def metadata(zones, source_manifest, zeppelin=None):
    """Build label-free image frames plus semantic, editable landmark identities."""
    regions = [dict(r, image=f"atlas/{r['key']}.png") for r in REGIONS]
    landmarks = []
    for sign, (key, name) in zip(source_manifest['signs'][:7], STABLE_NAMES):
        x, y, z = sign['transform']['translation_cm']
        landmarks.append(dict(key=key, name=name, category='stable', editable=True,
                              region='haras_valley', x=x/100.+550., y=-y/100.+4500., z=z/100.+210.))
    # Frame membership is separate from geographic ownership. Expand a region's
    # frame rather than silently dropping an outlying registered destination.
    for zone in zones:
        zone['region'] = region_for_zone(zone)
    for region in regions:
        points = [z for z in zones if z['region'] == region['key']]
        b = region['bounds'][:]
        for p in points:
            b = [min(b[0], p['x']-35), min(b[1], p['y']-35), max(b[2], p['x']+35), max(b[3], p['y']+35)]
        region['bounds'] = b
        assert all(math.isfinite(v) for v in b) and b[0] < b[2] and b[1] < b[3]
    result = dict(version=1, world=dict(key='world', name='The World', bounds=WORLD_BOUNDS, image='atlas/world.png'),
                  regions=regions, landmarks=landmarks)
    air = air_metadata(zones, zeppelin)
    if air:
        result['air'] = air
    return result


def water_pixels(image):
    """Semantic plan blue, also recognizing the paintings' turquoise ocean."""
    import numpy as np
    pixels = np.asarray(image.convert('RGB'), dtype=np.int16)
    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    return (b > r + 12) & (g > r + 10) & (b > .85 * g)


def verify_coast(image, mask, key):
    """Reject invented land outside the signed terrain/water reference.

    Three source pixels allow ink, surf and edge antialiasing. A small total
    allowance covers boats/foam; it cannot cover an enlarged island or bay.
    This colour check complements source registration and visual inspection;
    blue roofs and shaded snow are not treated as missing inland terrain.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    if image.size != mask.size:
        raise ValueError(f'Atlas coast mask dimensions differ: {key}')
    near_land = np.asarray(mask.convert('L').filter(ImageFilter.MaxFilter(7))) > 127
    invented = ~water_pixels(image) & ~near_land
    fraction = float(invented.mean())
    if fraction > .0035:
        raise ValueError(f'Atlas coastline differs for {key}: {fraction:.2%} painted land in reference water')
    # Only ocean connected to a known water edge counts as missing coastline.
    # Blue roof plans and shaded inland snow must not become water errors.
    source_water = np.asarray(mask.convert('L')) < 128
    # fromarray may expose a read-only buffer; floodfill silently ignores its
    # write failure. Own a writable raster before traversing the ocean.
    ocean = Image.fromarray(water_pixels(image).astype('uint8')).copy()
    pixels = ocean.load()
    edges = [(x, y) for x in range(image.width) for y in (0, image.height - 1)]
    edges += [(x, y) for y in range(image.height) for x in (0, image.width - 1)]
    for x, y in edges:
        if source_water[y, x] and pixels[x, y] == 1:
            ImageDraw.floodfill(ocean, (x, y), 2)
    dry_interior = np.asarray(mask.convert('L').filter(ImageFilter.MinFilter(7))) > 127
    missing = (np.asarray(ocean) == 2) & dry_interior
    missing_fraction = float(missing.mean())
    if missing_fraction > .0035:
        raise ValueError(f'Atlas coastline differs for {key}: {missing_fraction:.2%} reference land flooded by painted ocean')
    return max(fraction, missing_fraction)


def stage(out, atlas):
    """Require matching source frames: old paintings must never stretch onto a changed map."""
    import shutil
    from PIL import Image
    geography = geography_signature()
    coast_record = json.loads((ASSETS / 'coasts/source.json').read_text())
    for frame in [atlas['world'], *atlas['regions']]:
        key = frame['key']
        source = ASSETS / f'{key}.png'
        record = json.loads((ASSETS / f'{key}.json').read_text())
        if record['bounds'] != frame['bounds'] or record.get('labels_baked', True):
            raise ValueError(f'Atlas painting frame/label contract differs for {key}; prepare matching artwork')
        painting_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        if record.get('output_sha256') != painting_sha:
            raise ValueError(f'Atlas painting bytes differ from their provenance: {key}')
        coast = coast_record['frames'][key]
        if record.get('geography') != geography:
            # Keep original generation inputs and hashes intact when an existing
            # painting has been explicitly checked against a newer terrain plan.
            expected = dict(kind='terrain-reference-revalidation', geography=geography,
                            painting_sha256=painting_sha, coast_sha256=coast['sha256'],
                            reference_sha256=coast.get('reference_sha256'))
            if record.get('verified_geography') != expected:
                raise ValueError(f'Atlas painting geography differs for {key}; verify artwork against the current terrain')
        with Image.open(source) as image:
            if image.width < 1024 or image.height < 1024:
                raise ValueError(f'Atlas painting is too small: {key}')
            b = frame['bounds']
            if abs(image.width/image.height - (b[2]-b[0])/(b[3]-b[1])) > .001:
                raise ValueError(f'Atlas painting aspect differs from its world frame: {key}')
            mask = ASSETS / 'coasts' / f'{key}.png'
            if coast_record['geography'] != geography or coast['bounds'] != frame['bounds']:
                raise ValueError(f'Atlas coast reference geography differs: {key}')
            if hashlib.sha256(mask.read_bytes()).hexdigest() != coast['sha256']:
                raise ValueError(f'Atlas coast reference bytes differ: {key}')
            with Image.open(mask) as reference:
                verify_coast(image, reference, key)
        target = Path(out) / frame['image']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
