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
