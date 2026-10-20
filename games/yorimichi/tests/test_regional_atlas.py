"""A region is a view of the destination registry, never a replacement for it."""
import copy
import importlib.util
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('yorimichi_atlas', GAME / 'world/map/atlas.py')
atlas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(atlas)


def source():
    return json.loads((GAME / 'assets/belmonte/source.json').read_text())


def test_extracted_terrain_sources_are_signed_and_declared_inputs(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from atelier import build
    sources = {'world/build_terrain.py', 'world/farhills_surface.py', 'world/farhills_grid.py', 'world/terrain_product.py',
               'world/north_mountain_surface.py', 'world/city_terrain_surface.py', 'world/regions/hidamari/build.py'}
    assert sources <= set(atlas.GEOGRAPHY_SOURCES)
    recipe = build.load_recipe('yorimichi')
    step = next(s for s in recipe.steps(SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None))
                if s.name == 'world.map')
    assert {GAME / rel for rel in sources} <= set(step.inputs)
    monkeypatch.setattr(atlas, 'GAME', tmp_path)
    for rel in atlas.GEOGRAPHY_SOURCES:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel)
    before = atlas.geography_signature()
    for rel in sorted(sources):
        path = tmp_path / rel
        path.write_text(rel + ' changed')
        after = atlas.geography_signature()
        assert {key for key in before if before[key] != after[key]} == {rel}
        path.write_text(rel)


def test_all_current_destination_families_keep_their_travel_identity():
    positions = {
        'spawn': (-255, -99), 'hamlet': (113, 91), 'mega': (60, 234),
        'fishing': (-262, -124), 'cove': (-216, -169), 'landing': (-198, -427), 'temple': (-155, -511),
        'arrival': (450, 140), 'arcade': (599, 75), 'plaza': (712, 150), 'harbor': (570, -116),
        'hillside': (690, 335), 'park': (984, 230), 'station': (1184, 335), 'foothills': (1060, 1130),
        'forest_lake': (-54, 223), 'megapark': (-149, 1474), 'craterpark': (1285, 2497),
        'skatepier': (-104, -174), 'hippodrome': (563, 459), 'ronin_camp': (-55, -74),
        'zeppelin_forest': (-199, 221), 'zeppelin_city': (1279, 299), 'zeppelin_megapark': (-194, 1475),
        'zeppelin_belmonte': (416, 4651), 'belmonte': (550, 4482), 'belmonte_course': (385, 4855),
        'belmonte_training': (230, 5160), 'hidamari_station': (1184, 335), 'belmonte_station': (900, 4625),
        'belmonte_salon': (617.8, 4806.8), 'brinecove_quay': (-1500, -45),
        'marker_custom': (5000, 8000),
    }
    zones = [dict(key=k, name=k, x=x, y=y, z=21.5, yaw=92., hint='same resolver') for k, (x, y) in positions.items()]
    before = copy.deepcopy(zones)
    result = atlas.metadata(zones, source())
    keys = {r['key'] for r in result['regions']}
    assert len(keys) == 8
    assert len(zones) == len(before)
    for old, new in zip(before, zones):
        assert old == {k: v for k, v in new.items() if k != 'region'}
        assert new['region'] in keys | {'world'}
        if new['key'] != 'marker_custom':
            assert new['region'] != 'world', new['key']
            b = next(r['bounds'] for r in result['regions'] if r['key'] == new['region'])
            assert b[0] <= new['x'] <= b[2] and b[1] <= new['y'] <= b[3]
    assert zones[-1]['region'] == 'world'


def test_indoor_salon_keeps_its_landing_trace_when_added_to_haras_valley(monkeypatch):
    import importlib
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    importlib.import_module('yori')
    from belmonte.build import map_zones
    zones = map_zones(241.)
    before = copy.deepcopy(zones)
    atlas.metadata(zones, source())
    salon = next(z for z in zones if z['key'] == 'belmonte_salon')
    assert salon['region'] == 'haras_valley'
    assert salon['above_m'] == 1.5
    assert [{k: v for k, v in z.items() if k != 'region'} for z in zones] == before


def test_stable_identity_and_coordinates_do_not_depend_on_display_names():
    original = source()
    changed = copy.deepcopy(original)
    for sign in changed['signs']:
        sign['text'] = 'A completely different name'
    a = atlas.metadata([], original)['landmarks']
    b = atlas.metadata([], changed)['landmarks']
    assert a == b
    assert len({p['key'] for p in a}) == 7
    assert all(p['editable'] and p['category'] == 'stable' and p['region'] == 'haras_valley' for p in a)
    assert {p['name'] for p in a} == {'Home Stables', 'Alder Stables', 'Clearbridge Stables', 'Three Meadows Estate',
                                     'Low Dunes Stables', 'Longstone Estate', 'Amberhill Stables'}


def test_production_painting_must_match_its_frame_and_have_no_baked_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas, 'ASSETS', tmp_path / 'sources')
    atlas.ASSETS.mkdir()
    frame = dict(key='world', image='atlas/world.png', bounds=atlas.WORLD_BOUNDS)
    Image.new('RGB', (1024, 1024)).save(atlas.ASSETS / 'world.png')
    record = atlas.ASSETS / 'world.json'
    record.write_text(json.dumps(dict(bounds=frame['bounds'], labels_baked=False, geography=atlas.geography_signature(),
                                     output_sha256=hashlib.sha256((atlas.ASSETS / 'world.png').read_bytes()).hexdigest())))
    masks = atlas.ASSETS / 'coasts'
    masks.mkdir()
    Image.new('L', (1024, 1024), 255).save(masks / 'world.png')
    (masks / 'source.json').write_text(json.dumps(dict(geography=atlas.geography_signature(), frames=dict(world=dict(
        bounds=frame['bounds'], sha256=hashlib.sha256((masks / 'world.png').read_bytes()).hexdigest())))))
    atlas.stage(tmp_path / 'out', dict(world=frame, regions=[]))
    assert (tmp_path / 'out/atlas/world.png').read_bytes() == (atlas.ASSETS / 'world.png').read_bytes()
    record.write_text(json.dumps(dict(bounds=[0, 0, 1, 1], labels_baked=False)))
    with pytest.raises(ValueError, match='frame/label'):
        atlas.stage(tmp_path / 'bad-frame', dict(world=frame, regions=[]))
    record.write_text(json.dumps(dict(bounds=frame['bounds'], labels_baked=True)))
    with pytest.raises(ValueError, match='frame/label'):
        atlas.stage(tmp_path / 'baked-names', dict(world=frame, regions=[]))
    painting_sha = hashlib.sha256((atlas.ASSETS / 'world.png').read_bytes()).hexdigest()
    old = dict(bounds=frame['bounds'], labels_baked=False, geography={}, output_sha256=painting_sha)
    record.write_text(json.dumps(old))
    with pytest.raises(ValueError, match='geography'):
        atlas.stage(tmp_path / 'old-coastline', dict(world=frame, regions=[]))
    witness = dict(kind='terrain-reference-revalidation', geography=atlas.geography_signature(),
                   painting_sha256=painting_sha, coast_sha256=hashlib.sha256((masks / 'world.png').read_bytes()).hexdigest(),
                   reference_sha256=None)
    old['verified_geography'] = witness
    record.write_text(json.dumps(old))
    atlas.stage(tmp_path / 'revalidated', dict(world=frame, regions=[]))
    assert json.loads(record.read_text())['geography'] == {}
    witness['painting_sha256'] = 'an obsolete painting'
    record.write_text(json.dumps(old))
    with pytest.raises(ValueError, match='geography'):
        atlas.stage(tmp_path / 'stale-witness', dict(world=frame, regions=[]))


def test_atlas_code_and_nested_painting_metadata_invalidate_the_map_step(tmp_path):
    from dataclasses import replace
    from types import SimpleNamespace
    from atelier import build
    recipe = build.load_recipe('yorimichi')
    step = next(s for s in recipe.steps(SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)) if s.name == 'world.map')
    assert recipe.WORLD / 'map' in step.inputs
    inputs = tmp_path / 'map-source'
    (inputs / 'atlas').mkdir(parents=True)
    (inputs / 'atlas.py').write_text('version = 1\n')
    (inputs / 'atlas/world.json').write_text('{"labels_baked": false}')
    (inputs / 'atlas/world.png').write_bytes(b'painting revision 1')
    contract = replace(step, inputs=[inputs])
    done = {name: name for name in step.needs}
    initial = build.fingerprint(contract, done)
    (inputs / 'atlas/world.json').write_text('{"labels_baked": false, "bounds": [0,0,1,1]}')
    metadata_changed = build.fingerprint(contract, done)
    assert initial != metadata_changed
    (inputs / 'atlas/world.png').write_bytes(b'painting revision 2')
    painting_changed = build.fingerprint(contract, done)
    assert painting_changed != metadata_changed
    (inputs / 'atlas.py').write_text('version = 2\n')
    assert build.fingerprint(contract, done) != painting_changed


def test_committed_paintings_cover_all_regions_with_current_geometry_and_provenance(tmp_path):
    data = atlas.metadata([], source())
    atlas.stage(tmp_path, data)
    assert {p.stem for p in (tmp_path / 'atlas').glob('*.png')} == {'world', *(r['key'] for r in atlas.REGIONS)}


def test_world_coast_preserves_restored_spawn_ground_finite_edges_and_country_join():
    # The repaired fine/backdrop join restores dry ground west of the spawn road.
    # FarHills still ends at +/-3200 and the country GLB starts at3200; its lower
    # strip must not turn into a fictitious channel at SOUTH_JOIN.
    b = atlas.WORLD_BOUNDS
    with Image.open(atlas.ASSETS / 'coasts/world.png') as mask, Image.open(atlas.ASSETS / 'world.png') as painting:
        for x, y, water in [(-350., -99.51, False), (4000., 2500., True), (-2000., 3400., False), (0., 7190., True)]:
            ix = int((x-b[0])/(b[2]-b[0])*mask.width)
            iy = int((b[3]-y)/(b[3]-b[1])*mask.height)
            assert (mask.getpixel((ix, iy)) < 128) == water, (x, y)
            assert bool(atlas.water_pixels(painting.crop((ix, iy, ix+1, iy+1)))[0, 0]) == water, (x, y)


@pytest.mark.parametrize('key,x,y,water', [
    ('momiji_coast', -400., -75., False),
    ('momiji_coast', -400., -300., True),
    ('momiji_woods', -410., -25., False),
    ('momiji_woods', -350., 0., False),
])
def test_western_regional_paintings_preserve_restored_ground(key, x, y, water):
    # The Woods frame no longer has ocean on its lower-left edge, so an ocean
    # flood seeded only from known reference-water edges cannot find that old
    # painted corner. Check the actual restored terrain coordinates directly.
    bounds = next(r['bounds'] for r in atlas.REGIONS if r['key'] == key)
    with Image.open(atlas.ASSETS / 'coasts' / f'{key}.png') as mask, Image.open(atlas.ASSETS / f'{key}.png') as painting:
        ix = int((x-bounds[0])/(bounds[2]-bounds[0])*mask.width)
        iy = int((bounds[3]-y)/(bounds[3]-bounds[1])*mask.height)
        assert (mask.getpixel((ix, iy)) < 128) == water, (key, x, y)
        assert bool(atlas.water_pixels(painting.crop((ix, iy, ix+1, iy+1)))[0, 0]) == water, (key, x, y)


def test_coast_check_rejects_an_enlarged_island_or_filled_bay():
    from PIL import ImageDraw
    mask = Image.new('L', (1024, 1024), 0)
    ImageDraw.Draw(mask).ellipse((350, 350, 650, 650), fill=255)
    painting = Image.new('RGB', mask.size, (30, 100, 160))
    ImageDraw.Draw(painting).ellipse((350, 350, 650, 650), fill=(120, 150, 65))
    assert atlas.verify_coast(painting, mask, 'island') < .0035
    ImageDraw.Draw(painting).ellipse((280, 280, 720, 720), fill=(120, 150, 65))
    with pytest.raises(ValueError, match='coastline differs'):
        atlas.verify_coast(painting, mask, 'island')
    painting = Image.new('RGB', mask.size, (30, 100, 160))
    ImageDraw.Draw(painting).ellipse((430, 430, 570, 570), fill=(120, 150, 65))
    with pytest.raises(ValueError, match='flooded by painted ocean'):
        atlas.verify_coast(painting, mask, 'island')


def zeppelin_layout():
    stations = [
        dict(key='zeppelin_forest', name='Woodland air station'),
        dict(key='zeppelin_city', name='Hidamari air station'),
        dict(key='zeppelin_megapark', name='Mega Park air station'),
        dict(key='zeppelin_belmonte', name='Belmonte air station'),
    ]
    legs = [
        dict(stops=[0, 1], height=155., seconds=28.),
        dict(stops=[0, 2], height=185., seconds=23.7),
        dict(stops=[0, 3], height=600., seconds=84.6),
        dict(stops=[1, 2], height=240., seconds=35.5),
        dict(stops=[1, 3], height=910., seconds=83.7),
        dict(stops=[2, 3], height=520., seconds=61.2),
    ]
    return dict(stations=stations, legs=legs)


def test_zeppelin_itinerary_uses_the_line_order_and_real_leg_times():
    positions = {
        'zeppelin_forest': (-199., 221.3), 'zeppelin_city': (1279., 312.3),
        'zeppelin_megapark': (-194., 1475.3), 'zeppelin_belmonte': (416., 4651.3),
    }
    zones = [dict(key=key, name=key, x=x, y=y, z=70., yaw=90., hint='') for key, (x, y) in positions.items()]
    air = atlas.metadata(zones, source(), zeppelin_layout())['air']
    assert air['line'] == ['zeppelin_forest', 'zeppelin_city', 'zeppelin_megapark', 'zeppelin_belmonte']
    assert [(leg['from'], leg['to'], leg['seconds']) for leg in air['legs']] == [
        ('zeppelin_forest', 'zeppelin_city', 28.),
        ('zeppelin_city', 'zeppelin_megapark', 35.5),
        ('zeppelin_megapark', 'zeppelin_belmonte', 61.2),
    ]
    assert [stop['x'] for stop in air['stops']] == [-199., 1279., -194., 416.]
    assert len(air['connections']) == 6
    bad = zeppelin_layout()
    bad['stations'][0]['key'] = 'missing_air_station'
    with pytest.raises(ValueError, match='travel registry'):
        atlas.metadata(zones, source(), bad)


def test_native_float32_route_time_is_compared_with_tolerance():
    spec = importlib.util.spec_from_file_location('regional_atlas_scenario', GAME / 'scenarios/regional_atlas.py')
    scenario = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scenario)
    actual = [('zeppelin_forest', 'zeppelin_city', 28.),
              ('zeppelin_city', 'zeppelin_megapark', 35.5),
              ('zeppelin_megapark', 'zeppelin_belmonte', 61.20000076293945)]
    expected = [('zeppelin_forest', 'zeppelin_city', 28.),
                ('zeppelin_city', 'zeppelin_megapark', 35.5),
                ('zeppelin_megapark', 'zeppelin_belmonte', 61.2)]
    assert scenario.same_leg_times(actual, expected)
    assert not scenario.same_leg_times([actual[0], actual[1], ('zeppelin_megapark', 'wrong', 61.2)], expected)
