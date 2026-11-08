"""Saved objects: each named runtime group becomes one actor with its own record, outside its region's actor record."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


objects = load('v2_migrate_objects', 'tools/migrate/objects.py')
ACTORS = 'unreal/Content/__ExternalActors__/V2/Maps/Slice'
MANIFEST = f'{ACTORS}/7/B7/MANIFEST.uasset'
WRECK = '/Game/__ExternalActors__/V2/Maps/Slice/2/AA/WRECK'


def write(path, data=b'x'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def region(game, name, bounds, files=()):
    folder = game / 'world/regions' / name
    write(folder / 'region.toml', (f'schema = 1\nid = "region/{name}"\nabout = "{name}"\nbounds_cm = {bounds}\n'
                                   'maps = ["/Game/V2/Maps/Slice"]\n').encode())
    for rel in files:
        write(game / rel, b'manifest')
    records.write_json(folder / 'actors.verified.json', {
        'schema': 1, 'kind': 'editor-saved', 'asset': f'region/{name}', 'engine': 'test',
        'files': {rel: records.sha256_file(game / rel) for rel in files}})
    return folder


@pytest.fixture
def game(tmp_path, monkeypatch):
    game = tmp_path / 'game'
    region(game, 'w00-island', [-1000, -1000, 1000, 1000], [MANIFEST])
    cove = region(game, 'w09-cove', [-1000, -1000, 0, 0])
    (cove / 'objects.toml').write_text(
        'schema = 1\ntag = "brinecove"\ndata = "brinecove/runtime.json"\n\n[[objects]]\nid = "object/cove/wreck"\n'
        'group = "SM_BC_Ships_2_2"\nmodel = "adopted/cove/wreck"\nabout = "the broken hull on the western rocks"\n')
    monkeypatch.setattr(objects.save_validate, 'engine_identity', lambda: 'test')
    monkeypatch.setattr(objects.save_validate, 'actor_info', lambda path: (None, None))
    monkeypatch.setenv('ATELIER_AGENT', objects.authority.BOOTSTRAP_WRITER)
    monkeypatch.delenv('ATELIER_CLAIMS_TASK', raising=False)
    return game


def editor(game, created=True):
    """The editor step: saves the wreck's actor (first run only) and the manifest, prints what the map holds."""
    def run(plan_file):
        plan = json.loads(plan_file.read_text())
        assert plan['groups'] == [{'region': 'region/w09-cove', 'tag': 'brinecove', 'data': 'brinecove/runtime.json',
                                   'meshes': ['SM_BC_Ships_2_2'], 'objects': ['wreck']}]
        if created:
            write(game / f'unreal/Content{WRECK[len("/Game"):]}.uasset', b'wreck')
            write(game / MANIFEST, b'manifest listing the wreck')
        return f'V2 OBJECT {WRECK} brinecove:wreck\nV2 OBJECTS DONE created={int(created)} kept={int(not created)}\n'
    return run


def test_an_object_gets_its_own_record_and_its_region_never_takes_its_actor(game):
    made = objects.migrate(game, ['region/w09-cove'], 'region/w00-island', None, editor=editor(game),
                           out=game / 'out', echo=lambda *_: None)
    assert made == {'object/cove/wreck': WRECK}
    wreck = records.load_asset(game / 'assets/object/cove/wreck/asset.toml')
    assert (wreck.kind, wreck.owner, wreck.references) == ('placement', 'region/w09-cove', ['adopted/cove/wreck'])
    assert [o.package for o in wreck.outputs] == [WRECK]
    rel = f'unreal/Content{WRECK[len("/Game"):]}.uasset'
    assert list(records.load_verified(wreck.verified)['files']) == [rel]
    island = records.load_verified(game / 'world/regions/w00-island/actors.verified.json')['files']
    assert rel not in island and island[MANIFEST] == records.sha256_file(game / MANIFEST)
    # The region's own save validation never takes the object's actor, labelled or inside its bounds.
    objects.save_validate.validate(game, 'region/w09-cove', add=[], echo=lambda *_: None)
    assert rel not in records.load_verified(game / 'world/regions/w09-cove/actors.verified.json')['files']
    with pytest.raises(objects.save_validate.ValidationError, match='belongs to object/cove/wreck'):
        objects.save_validate.validate(game, 'region/w09-cove', add=[rel], echo=lambda *_: None)
    # A rerun keeps the saved object as it is and writes nothing.
    record = (game / 'assets/object/cove/wreck/asset.toml').read_text()
    assert objects.migrate(game, ['region/w09-cove'], 'region/w00-island', None, editor=editor(game, created=False),
                           out=game / 'out', echo=lambda *_: None) == made
    assert (game / 'assets/object/cove/wreck/asset.toml').read_text() == record


def test_an_object_the_map_does_not_hold_fails(game):
    def nothing(plan_file):
        return 'V2 OBJECTS DONE created=0 kept=0\n'
    with pytest.raises(objects.ObjectError, match='holds no object'):
        objects.migrate(game, ['region/w09-cove'], 'region/w00-island', None, editor=nothing, out=game / 'out',
                        echo=lambda *_: None)


def test_objects_toml_is_checked(game):
    path = game / 'world/regions/w09-cove/objects.toml'
    path.write_text(path.read_text().replace('id = "object/cove/wreck"', 'id = "adopted/cove/wreck"'))
    with pytest.raises(objects.ObjectError, match='object/'):
        objects.migrate(game, ['region/w09-cove'], 'region/w00-island', None, editor=editor(game), out=game / 'out',
                        echo=lambda *_: None)


def test_only_names_a_subset_and_refuses_an_unknown_object(game):
    path = game / 'world/regions/w09-cove/objects.toml'
    path.write_text(path.read_text() + '\n[[objects]]\nid = "object/cove/fort"\ngroup = "SM_BC_Landmarks_3_5"\n'
                    'model = "adopted/cove/fort"\nabout = "the fort"\n')
    made = objects.migrate(game, ['region/w09-cove'], 'region/w00-island', None, only=['object/cove/wreck'],
                           editor=editor(game), out=game / 'out', echo=lambda *_: None)
    assert made == {'object/cove/wreck': WRECK} and not (game / 'assets/object/cove/fort').exists()
    with pytest.raises(objects.ObjectError, match='not all are objects'):
        objects.migrate(game, ['region/w09-cove'], 'region/w00-island', None, only=['object/cove/mast'],
                        editor=editor(game), out=game / 'out', echo=lambda *_: None)


def test_a_patch_object_takes_its_saved_patch_and_the_region_lets_it_go(game):
    """A patch holding one object alone becomes that object's record; the region's verification drops it, and the
    content check's roster accepts the patch as held by the region's object."""
    patch_rel = 'unreal/Content/__ExternalActors__/V2/Maps/Slice/A/4O/STOREHOUSE.uasset'
    write(game / patch_rel, b'storehouse patch')
    village = region(game, 'w02-village', [0, 0, 1000, 1000], [patch_rel])
    (village / 'patches.json').write_text(json.dumps({'schema': 1, 'region': 'region/w02-village', 'patches': {
        '05ed3a01c13d434b': {'key': 'Village_Storehouse', 'package': patch_rel}}}))
    (village / 'objects.toml').write_text(
        'schema = 1\ntag = "village"\ndata = ""\n\n[[objects]]\nid = "object/village/storehouse"\n'
        'patch = "05ed3a01c13d434b"\nmodel = "adopted/japan/assets"\nabout = "the storehouse"\n')
    objects.save_validate.validate(game, 'region/w02-village', add=[patch_rel], echo=lambda *_: None)
    assert patch_rel in records.load_verified(village / 'actors.verified.json')['files']
    made = objects.promote(game, ['region/w02-village'], None, echo=lambda *_: None)
    package = '/Game/__ExternalActors__/V2/Maps/Slice/A/4O/STOREHOUSE'
    assert made == {'object/village/storehouse': package}
    record = records.load_asset(game / 'assets/object/village/storehouse/asset.toml')
    assert (record.kind, record.owner, [o.package for o in record.outputs]) == ('placement', 'region/w02-village', [package])
    assert list(records.load_verified(record.verified)['files']) == [patch_rel]
    assert patch_rel not in records.load_verified(village / 'actors.verified.json')['files']
    assert objects.promote(game, ['region/w02-village'], None, echo=lambda *_: None) == made   # a rerun writes nothing
    # A runtime-group migration of the same region skips its patch objects.
    with pytest.raises(objects.ObjectError, match='not all are objects'):
        objects.migrate(game, ['region/w02-village'], 'region/w00-island', None, only=['object/village/storehouse'],
                        editor=editor(game), out=game / 'out', echo=lambda *_: None)


def test_a_split_object_leaves_its_area_patch_for_an_actor_of_its_own(game):
    """A placed thing of an area patch (key and source point) becomes its own actor and record; the area patch, which
    gave up its instance, is re-verified by its region, and the claim locks every patch of the key."""
    area_rel = f'{ACTORS}/C/3D/HOUSES.uasset'
    other_rel = f'{ACTORS}/C/3E/HOUSES2.uasset'
    house_rel = f'{ACTORS}/C/3D/HOUSE7.uasset'
    for rel in (area_rel, other_rel):
        write(game / rel, b'four houses')
    harbour = region(game, 'w07-harbour', [0, -100000, 100000, 0], [area_rel, other_rel])
    (harbour / 'patches.json').write_text(json.dumps({'schema': 1, 'region': 'region/w07-harbour', 'patches': {
        'aaaa000000000001': {'key': 'HD_House_02', 'package': area_rel},
        'aaaa000000000002': {'key': 'HD_House_02', 'package': other_rel},
        'aaaa000000000003': {'key': 'HD_Lamp', 'package': f'{ACTORS}/C/3F/LAMPS.uasset'}}}))
    (harbour / 'objects.toml').write_text(
        'schema = 1\ntag = "harbour"\ndata = ""\n\n[[objects]]\nid = "object/harbour/house-02-7"\n'
        'split = {key = "HD_House_02", at = [455.5, -71]}\nmodel = "adopted/japan/hidamari"\nabout = "a harbour house"\n')

    def run(plan_file):
        plan = json.loads(plan_file.read_text())
        assert plan['groups'] == []
        assert plan['splits'] == [{'region': 'region/w07-harbour', 'tag': 'harbour', 'keys': ['HD_House_02'],
                                   'objects': ['house-02-7'], 'points_cm': [[45550.0, 7100.0]], 'tolerance_cm': 50.0}]
        write(game / house_rel, b'one house')
        write(game / area_rel, b'three houses')
        return (f'V2 SPLIT FROM /Game/{area_rel[len("unreal/Content/"):-len(".uasset")]}\n'
                f'V2 OBJECT /Game/{house_rel[len("unreal/Content/"):-len(".uasset")]} harbour:house-02-7\n'
                'V2 OBJECTS DONE created=1 kept=0\n')

    assert objects.claim_paths(game, ['region/w07-harbour'])['lock'] == [f'games/yorimichi_v2/{area_rel}',
                                                                         f'games/yorimichi_v2/{other_rel}']
    made = objects.migrate(game, ['region/w07-harbour'], 'region/w00-island', None, editor=run, out=game / 'out',
                           echo=lambda *_: None)
    package = f'/Game/{house_rel[len("unreal/Content/"):-len(".uasset")]}'
    assert made == {'object/harbour/house-02-7': package}
    record = records.load_asset(game / 'assets/object/harbour/house-02-7/asset.toml')
    assert list(records.load_verified(record.verified)['files']) == [house_rel]
    files = records.load_verified(harbour / 'actors.verified.json')['files']
    assert house_rel not in files and files[area_rel] == records.sha256_file(game / area_rel)


def test_a_split_needs_a_key_and_a_point(game):
    (game / 'world/regions/w09-cove/objects.toml').write_text(
        'schema = 1\ntag = "brinecove"\ndata = ""\n\n[[objects]]\nid = "object/cove/rock"\n'
        'split = {key = "SW_Rock"}\nmodel = "adopted/cove/rock"\nabout = "a rock"\n')
    with pytest.raises(objects.ObjectError, match='split needs key'):
        objects.migrate(game, ['region/w09-cove'], 'region/w00-island', None, editor=editor(game), out=game / 'out',
                        echo=lambda *_: None)


def test_a_batch_of_objects_takes_one_claims_check_for_its_records_and_one_for_its_packages(game, monkeypatch):
    calls = []
    real = objects.authority.authorize
    monkeypatch.setattr(objects.authority, 'authorize', lambda paths, *a, **k: (calls.append(paths), real(paths, *a, **k)))
    entries = []
    for n in range(5):
        rel = f'{ACTORS}/D/{n}0/HOUSE{n}.uasset'
        write(game / rel, f'house {n}'.encode())
        entries.append(('region/w09-cove', {'id': f'object/cove/house-{n}', 'model': 'adopted/cove/wreck',
                                            'about': f'house {n}'}, f'/Game/{rel[len("unreal/Content/"):-7]}'))
    made = objects.record_objects(game, entries, None, echo=lambda *_: None)
    assert sorted(made) == [f'object/cove/house-{n}' for n in range(5)]
    assert [len(paths) for paths in calls] == [5, 5]   # the five records, then the five package files
    for n in range(5):
        record = records.load_asset(game / f'assets/object/cove/house-{n}/asset.toml')
        assert list(records.load_verified(record.verified)['files']) == [f'{ACTORS}/D/{n}0/HOUSE{n}.uasset']
    calls.clear()
    assert objects.record_objects(game, entries, None, echo=lambda *_: None) == made and calls == []   # unchanged


def test_a_building_cut_into_cells_takes_all_its_cell_patches(game):
    """`patch` as a list: the cell patches each holding a piece of one building alone become that one object, with an
    output per cell; the region lets them all go, and the same V2Id cannot be listed by two objects."""
    cells = [f'unreal/Content/__ExternalActors__/V2/Maps/Slice/B/{n}C/STATIONCELL{n}.uasset' for n in range(4)]
    for rel in cells:
        write(game / rel, rel.encode())
    harbour = region(game, 'w07-harbour', [0, 0, 1000, 1000], cells)
    ids = [f'cccc00000000000{n}' for n in range(4)]
    (harbour / 'patches.json').write_text(json.dumps({'schema': 1, 'region': 'region/w07-harbour', 'patches': {
        v: {'key': 'HD_Station', 'package': rel} for v, rel in zip(ids, cells)}}))
    entry = ('schema = 1\ntag = "harbour"\ndata = ""\n\n[[objects]]\nid = "object/harbour/station-building"\n'
             f'patch = {json.dumps(ids)}\nmodel = "adopted/experiments/citysurfaces/v1-128m"\nabout = "the station"\n')
    (harbour / 'objects.toml').write_text(entry)
    made = objects.promote(game, ['region/w07-harbour'], None, echo=lambda *_: None)
    packages = [f'/Game/{rel[len("unreal/Content/"):-len(".uasset")]}' for rel in cells]
    assert made == {'object/harbour/station-building': packages}
    record = records.load_asset(game / 'assets/object/harbour/station-building/asset.toml')
    assert [o.package for o in record.outputs] == packages
    assert sorted(records.load_verified(record.verified)['files']) == sorted(cells)
    assert not set(cells) & set(records.load_verified(harbour / 'actors.verified.json')['files'])
    assert objects.promote(game, ['region/w07-harbour'], None, echo=lambda *_: None) == made   # a rerun writes nothing
    (harbour / 'objects.toml').write_text(entry + entry.split('\n\n', 1)[1].replace('station-building', 'station-again'))
    with pytest.raises(objects.ObjectError, match='listed twice'):
        objects.load_objects(records.discover(game)[1][[r.id for r in records.discover(game)[1]].index('region/w07-harbour')])
