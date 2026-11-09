"""Hidamari shops as saved objects: every donor placement is one object whose model is its type's existing mesh record(s)."""
import importlib.util
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import shop_objects as shops  # noqa: E402

CELLS = {'0': 0, 'm1': -1}


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def placed():
    return shops.placements()


@pytest.fixture(scope='module')
def committed():
    result = {}
    for rid in shops.REGION_IDS:
        data = tomllib.loads((shops.REGIONS / rid / 'objects.toml').read_text())
        result[rid] = [o for o in data['objects'] if 'split' in o and o['split']['key'].startswith('HD_Shop_')]
    return result


def test_committed_objects_toml_is_the_generated_shop_split():
    for rid, text in shops.plan().items():
        assert (shops.REGIONS / rid / 'objects.toml').read_text() == text, f'{rid}: run shop_objects.py --write'


def test_every_donor_placement_is_exactly_one_object(placed, committed):
    assert len(placed) == 191
    wanted = Counter((shops.region_of(x, y), key, round(x, 2), round(y, 2)) for key, x, y in placed)
    assert all(count == 1 for count in wanted.values())
    have = Counter()
    for rid, objects in committed.items():
        for item in objects:
            key, x, y = item['split']['key'], *item['split']['at']
            have[(rid, key, round(float(x), 2), round(float(y), 2))] += 1
    assert have == wanted


def test_object_ids_and_names_are_unique_per_region(committed):
    for rid, objects in committed.items():
        ids = [o['id'] for o in objects]
        assert len(ids) == len(set(ids)), rid
        assert all(o['id'].startswith('object/' + shops.TAGS[rid] + '/hd-shop-') for o in objects), rid
        tails = [o['id'].rsplit('/', 1)[1] for o in objects]
        assert len(tails) == len(set(tails)), rid


def test_placements_of_one_type_never_share_a_point(placed):
    by_key = defaultdict(list)
    for key, x, y in placed:
        by_key[key].append((x, y))
    for key, points in by_key.items():
        for i, (ax, ay) in enumerate(points):
            for bx, by in points[i + 1:]:
                assert max(abs(ax - bx), abs(ay - by)) > 5, (key, ax, ay, bx, by)


def test_each_model_record_exists_and_packages_its_type(committed):
    for rid, objects in committed.items():
        for item in objects:
            key = item['split']['key']
            models = item['model'] if isinstance(item['model'], list) else [item['model']]
            assert all(m.startswith(shops.MODEL_PREFIX) for m in models), item['id']
            packages = []
            for model in models:
                record = tomllib.loads((shops.RECORDS / model.rsplit('/', 1)[1] / 'asset.toml').read_text())
                assert record['id'] == model, item['id']
                packages += [output['package'] for output in record['outputs']]
            assert len(packages) == len(models), item['id']
            assert all(p.rsplit('/', 1)[1].startswith(key + '_cell_') or p.rsplit('/', 1)[1] == key for p in packages), item['id']


def test_a_quadrant_type_takes_all_four_of_its_cells_and_a_whole_type_one_record(committed):
    seen = defaultdict(set)
    for rid, objects in committed.items():
        for item in objects:
            key = item['split']['key']
            models = item['model'] if isinstance(item['model'], list) else [item['model']]
            if len(models) == 1:
                assert isinstance(item['model'], str), item['id']
                assert models[0].endswith('/shop-' + key[-2:]), item['id']
                continue
            assert len(models) == 4, item['id']
            seen[key].add(tuple(sorted(models)))
    for key, sets in seen.items():
        assert len(sets) == 1, f'{key} takes different cell sets'
        cells = set()
        for model in next(iter(sets)):
            number = key[-2:]
            tail = model.rsplit('/', 1)[1].removeprefix(f'shop-{number}-cell-').split('-')
            cells.add((CELLS[tail[0]], CELLS[tail[1]]))
        assert cells == {(0, 0), (0, -1), (-1, 0), (-1, -1)}, key


def test_objects_py_takes_one_model_or_a_list_and_records_each(tmp_path, monkeypatch):
    objects = load('v2_migrate_objects_shops', 'tools/migrate/objects.py')
    region = tmp_path / 'region'
    region.mkdir()
    (region / 'objects.toml').write_text(
        'schema = 1\ntag = "harbour"\ndata = ""\n\n[[objects]]\nid = "object/harbour/hd-shop-00-01"\n'
        'split = {key = "HD_Shop_00", at = [455, -71]}\n'
        'model = ["adopted/experiments/citysurfaces/v1-128m/shop-00-0-0", "adopted/experiments/citysurfaces/v1-128m/shop-00-m1-m1"]\n'
        'about = "one shop"\n\n[[objects]]\nid = "object/harbour/hd-shop-03-01"\n'
        'split = {key = "HD_Shop_03", at = [455, 56]}\nmodel = "adopted/experiments/citysurfaces/v1-128m/shop-03"\n'
        'about = "one whole shop"\n')
    listed = objects.load_objects(SimpleNamespace(id='region/w07-hidamari-harbour', folder=region))
    first, second = listed['objects']
    assert first['models'] == ['adopted/experiments/citysurfaces/v1-128m/shop-00-0-0',
                               'adopted/experiments/citysurfaces/v1-128m/shop-00-m1-m1']
    assert second['models'] == ['adopted/experiments/citysurfaces/v1-128m/shop-03']
    text = objects.record_text(first, 'region/w07-hidamari-harbour', '/Game/Shop')
    assert 'references = ["adopted/experiments/citysurfaces/v1-128m/shop-00-0-0", ' \
           '"adopted/experiments/citysurfaces/v1-128m/shop-00-m1-m1"]' in text
    single = objects.record_text(second, 'region/w07-hidamari-harbour', '/Game/Shop')
    assert 'references = ["adopted/experiments/citysurfaces/v1-128m/shop-03"]' in single


def test_objects_py_refuses_an_empty_or_repeated_model_list(tmp_path):
    objects = load('v2_migrate_objects_refuse', 'tools/migrate/objects.py')
    region = tmp_path / 'region'
    region.mkdir()
    for model in ('[]', '["adopted/x/shop-03", "adopted/x/shop-03"]', '[1]'):
        (region / 'objects.toml').write_text(
            'schema = 1\ntag = "harbour"\ndata = ""\n\n[[objects]]\nid = "object/harbour/hd-shop-03-01"\n'
            f'split = {{key = "HD_Shop_03", at = [455, 56]}}\nmodel = {model}\nabout = "x"\n')
        with pytest.raises(objects.ObjectError):
            objects.load_objects(SimpleNamespace(id='region/w07-hidamari-harbour', folder=region))
