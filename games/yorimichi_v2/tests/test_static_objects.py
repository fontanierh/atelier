"""Static leftovers: the mini Mega ramp (W03) and the Ronin camp's props (W13) saved as objects of their own. The meshes the
runtime skips are the ones the saved objects list; the placements sit inside their regions; the plan the editor step gets
names exactly those meshes; and the C++ builder and the Python table agree on the names."""
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

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


objects = load('v2_migrate_objects_static', 'tools/migrate/objects.py')
SRC = ROOT / 'unreal/Source/Yorimichi'
RAMP_REGION, CAMP_REGION = 'region/w03-mega', 'region/w13-swordcamp'
RAMP_MESHES = ['Mega_Ramp', 'Mega_Trim']
CAMP_MESHES = ['SM_CampFirePit', 'SM_CampJinmaku', 'SM_CampWeaponRack', 'SM_CampBales']


@pytest.fixture(scope='module')
def discovered():
    _, regions = records.discover(ROOT)
    return {r.id: r for r in regions}


def static_objects(discovered, rid):
    return [item for item in objects.load_objects(discovered[rid])['objects'] if 'static' in item]


def test_ramp_is_one_object_of_both_meshes(discovered):
    items = static_objects(discovered, RAMP_REGION)
    assert [(i['id'], i['static']) for i in items] == [('object/megaramp/ramp', RAMP_MESHES)]
    assert objects.load_objects(discovered[RAMP_REGION])['tag'] == 'mega'


def test_camp_has_one_object_per_prop_in_its_own_region(discovered):
    items = static_objects(discovered, CAMP_REGION)
    assert [i['static'] for i in items] == [[m] for m in CAMP_MESHES]
    assert [i['id'] for i in items] == ['object/swordcamp/fire-pit', 'object/swordcamp/jinmaku',
                                        'object/swordcamp/weapon-rack', 'object/swordcamp/bales']
    assert objects.load_objects(discovered[CAMP_REGION])['tag'] == 'swordcamp'


def test_models_are_records_that_own_the_meshes(discovered):
    """Every static object's model is one record, or several, whose outputs together include the object's packages."""
    owned = {}
    for path in (ROOT / 'assets').rglob('asset.toml'):
        data = tomllib.loads(path.read_text())
        owned[data.get('id')] = {o['package'] for o in data.get('outputs', [])}
    for rid in (RAMP_REGION, CAMP_REGION):
        for item in static_objects(discovered, rid):
            missing = [m for m in objects.models(item) if m not in owned]
            assert not missing, f'{item["id"]}: no record {missing}'
            packages = set().union(*(owned[m] for m in objects.models(item)))
            root = '/Game/Japan/Assets' if item['static'][0].startswith('Mega_') else '/Game/SwordCamp/Assets'
            for mesh in item['static']:
                assert f'{root}/{mesh}' in packages, f'{item["id"]}: {mesh} is not an output of {item["model"]}'


def test_static_names_match_the_builder_and_the_table():
    """STATIC_MESHES lists the ramp's two meshes and the camp table's four props, and the C++ table and builder use the same."""
    camp = re.findall(r'TEXT\("(SM_Camp\w+)"\)', (SRC / 'Combat/SwordTrainer.cpp').read_text())
    assert set(camp) == set(CAMP_MESHES)   # the table and the call sites name each prop
    assert sorted(objects.STATIC_MESHES) == sorted(RAMP_MESHES + CAMP_MESHES)
    builder = (SRC / 'World/V2MigrationMisc.cpp').read_text()
    assert 'Mega_Trim' in builder and 'MakePiece' in builder and 'FindRoninCampProp' in builder


def test_runtime_skips_match_the_saved_tags_and_meshes():
    """The runtime checks the same tag and meshes the objects save under (V2StaticSaved with the tag)."""
    world = (SRC / 'World/JapanWorld.cpp').read_text()
    assert 'V2StaticSaved(Manifest, TEXT("mega"), TEXT("Mega_Ramp")' in world
    assert 'V2StaticSaved(Manifest, TEXT("mega"), TEXT("Mega_Trim")' in world
    camp = (SRC / 'Combat/SwordTrainer.cpp').read_text()
    assert 'V2StaticSaved(Manifest, TEXT("swordcamp"), Mesh' in camp


def test_placements_lie_inside_their_regions(discovered):
    """The ramp's origin (world.json, 65 m, 242 m source: 6500, -24200 cm) and the camp centre (-54, -94 m: -5400, 9400 cm)."""
    def inside(rid, point):
        min_x, min_y, max_x, max_y = discovered[rid].bounds_cm
        return min_x <= point[0] < max_x and min_y <= point[1] < max_y
    assert inside(RAMP_REGION, (6500.0, -24200.0))
    assert inside(CAMP_REGION, (-5400.0, 9400.0))


def test_plan_carries_the_statics_to_the_editor(monkeypatch, tmp_path):
    """migrate() writes a plan naming the ramp unit and each camp prop before the editor runs, and nothing else."""
    monkeypatch.setattr(objects.authority, 'authorize', lambda *a, **k: None)
    monkeypatch.setattr(objects.authority, 'content_snapshot', lambda game: {})
    seen = {}

    def editor(plan_file):
        seen.update(json.loads(plan_file.read_text()))
        return ''   # no completion marker: the migration stops after the plan
    with pytest.raises(objects.ObjectError, match='did not report completion'):
        objects.migrate(ROOT, [RAMP_REGION, CAMP_REGION], 'region/w00-island', None, editor=editor, out=tmp_path)
    assert seen['statics'] == [
        {'region': RAMP_REGION, 'tag': 'mega', 'meshes': RAMP_MESHES, 'units': ['ramp', 'ramp']},
        {'region': CAMP_REGION, 'tag': 'swordcamp', 'meshes': CAMP_MESHES, 'units': ['fire-pit', 'jinmaku', 'weapon-rack', 'bales']},
    ]
    assert seen['groups'] == [] and seen['parks'] == [] and seen['hippodromes'] == []
    assert seen['environment'] == 'region/w00-island'


def write_region(tmp_path, body):
    folder = tmp_path / 'region'
    folder.mkdir(parents=True)
    (folder / 'objects.toml').write_text('schema = 1\ntag = "x"\ndata = ""\n' + body)
    return SimpleNamespace(id='region/x', folder=folder)


def test_static_meshes_are_refused_when_unknown_or_repeated(tmp_path):
    unknown = write_region(tmp_path / 'a', '[[objects]]\nid = "object/x/a"\nstatic = ["SM_Nope"]\n'
                                           'model = "adopted/x/m"\nabout = "a"\n')
    with pytest.raises(objects.ObjectError, match='static needs'):
        objects.load_objects(unknown)
    repeated = write_region(tmp_path / 'b', '[[objects]]\nid = "object/x/a"\nstatic = ["Mega_Ramp"]\n'
                                            'model = "adopted/x/m"\nabout = "a"\n[[objects]]\nid = "object/x/b"\n'
                                            'static = ["Mega_Ramp"]\nmodel = "adopted/x/m"\nabout = "b"\n')
    with pytest.raises(objects.ObjectError, match='listed twice'):
        objects.load_objects(repeated)


def test_a_unit_is_the_ramp_or_one_camp_prop():
    mixed = {'id': 'object/x/a', 'static': ['Mega_Ramp', 'SM_CampBales']}
    with pytest.raises(objects.ObjectError, match='a unit is'):
        objects.static_plan('region/x', 'x', [mixed])
    camp_pair = {'id': 'object/x/a', 'static': ['SM_CampBales', 'SM_CampJinmaku']}
    with pytest.raises(objects.ObjectError, match='a unit is'):
        objects.static_plan('region/x', 'x', [camp_pair])
    ramp = {'id': 'object/x/ramp', 'static': ['Mega_Ramp', 'Mega_Trim']}
    assert objects.static_plan('region/x', 'x', [ramp]) == {
        'region': 'region/x', 'tag': 'x', 'meshes': ['Mega_Ramp', 'Mega_Trim'], 'units': ['ramp', 'ramp']}
