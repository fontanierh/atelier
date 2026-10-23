"""City placement dependencies are shared data, independent from mesh construction bodies."""
import ast
import hashlib
import importlib
import json
from copy import deepcopy
from pathlib import Path

from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parents[1]
REGIONS = GAME / 'world/regions'
ROOT = REGIONS / 'hidamari'


def test_moved_placement_declarations_match_the_original_complete_source_ast():
    witness = json.loads((GAME / 'tests/fixtures/hidamari-placement-source.json').read_text())
    for module, record in witness['sources'].items():
        nodes = {}
        for n in ast.parse((ROOT / (module + '_placement.py')).read_text()).body:
            if isinstance(n, ast.FunctionDef): nodes[n.name] = n
            elif isinstance(n, ast.Assign):
                for target in n.targets:
                    for item in ast.walk(target):
                        if isinstance(item, ast.Name): nodes[item.id] = n
        assert set(nodes) == set(record['declarations'])
        for name, expected in record['declarations'].items():
            assert hashlib.sha256(ast.dump(nodes[name], include_attributes=False).encode()).hexdigest() == expected


def test_geometry_and_layout_share_one_authoritative_parameter_and_placement_definition(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    import yori  # noqa: F401
    witness = json.loads((GAME / 'tests/fixtures/hidamari-placement-source.json').read_text())
    for module, record in witness['sources'].items():
        geometry = importlib.import_module('hidamari.' + module)
        data = importlib.import_module('hidamari.' + module + '_placement')
        for name in record['declarations']:
            assert getattr(geometry, name) is getattr(data, name), (module, name)


def test_city_layout_source_key_excludes_independent_shop_and_surface_constructors():
    sources = set(local_imports(ROOT / 'layout.py', (REGIONS, REGIONS.parent)))
    assert ROOT / 'build.py' not in sources
    assert not any(p.is_relative_to(ROOT / 'kit') or p.is_relative_to(ROOT / 'logical') for p in sources)
    for module in ('arrival', 'park_grounds', 'station_yard', 'temple_precinct'):
        assert ROOT / (module + '.py') not in sources
        assert ROOT / (module + '_placement.py') in sources


def test_constructor_city_projection_stops_unread_city_and_sibling_fields(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    import yori  # noqa: F401
    from hidamari.city_data import project, read
    city = dict(roads=[[[0, 0, 0], [1, 0, 0]]], road_widths=[[8, 3.8]],
                buildings=[dict(asset='House', position=[1, 2, 3])], poles=[[2, 3, 4]], unused='first')
    value = deepcopy(project(city, 'HD_Streets'))
    assert read(value, 'HD_Streets') == dict(roads=city['roads'], road_widths=city['road_widths'])
    city['unused'] = 'second'; city['buildings'][0]['position'] = [9, 8, 7]
    assert project(city, 'HD_Streets') == value
    city['roads'][0][0][2] = 1
    assert project(city, 'HD_Streets') != value
