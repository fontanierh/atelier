"""C3 foliage raw imports consume each fixed original LOD export Item only."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import foliage_build  # noqa: E402
import v2_foliage_units as foliage  # noqa: E402
from v2_texture_units import PLUGIN  # noqa: E402


@pytest.fixture(scope='module')
def rows():
    steps = foliage_build.world_steps(SimpleNamespace(out=ROOT / 'build/yorimichi'))
    return [row for row in extract(steps, checkout=ROOT, build_root=ROOT / 'build')
            if row['id'].startswith('world.foliage.export.')]


def test_roster_is_every_fixed_mesh_lod_and_crown_of_all_owners():
    roster = foliage.roster(ROOT)
    assert list(roster) == list(foliage_build.catalog.FOLIAGE) and len(roster) == 18
    for owner, chain in roster.items():
        spec = json.loads((GAME / 'assets/foliage' / (owner + '.json')).read_text())
        count = len(spec['screen_sizes']) + (spec.get('far_crown') is not None)
        expected = [owner] + [f'{owner}_LOD{level}' for level in range(1, count)]
        assert [key for key, _ in chain] == expected
        assert [level for _, level in chain] == list(range(len(chain)))
    assert len(roster['Tree_Broad_A']) == 6 and len(roster['Grass_A']) == 3


def test_each_key_becomes_one_store_only_raw_import_of_its_export_item(rows):
    result = foliage.foliage_units(rows, checkout=ROOT)
    roster = foliage.roster(ROOT)
    assert len(result['units']) == len(result['packages']) == sum(map(len, roster.values()))
    by_id = {unit['id']: unit for unit in result['units']}
    for package, ref in result['packages'].items():
        unit = by_id[ref['unit']]
        key = ref['key']
        assert package == f'/Game/_Raw/Foliage/{ref["owner"]}/{key}'
        assert unit['op'] == {'kind': 'unreal.raw_import', 'version': '1'}
        assert unit['params'] == {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': package,
                                  'input_roots': {'source': {'archive_member': 'products/0-0.tree.tar', 'name': key}}}
        assert unit['inputs'] == [{'role': 'content', 'name': 'source', 'source': {
            'kind': 'item', 'unit': 'world.foliage.export.' + key, 'item': 'product0'}}]
        output, = unit['outputs']
        assert output['class'] == 'RawStaticMesh' and output['destination'] == 'store'
        assert output['logical_path'] == package and output['id'] == ref['item'] == 'raw_static_mesh'
        assert output['files'][0] == {'path': 'content' + package + '.uasset', 'required': True}
        assert all('install_path' not in file for file in output['files'])
        assert result['staged'][unit['id']] == {'source': 'inputs/source'}
    assert not any(ref['key'].endswith('_Seed') for ref in result['packages'].values())
    assert 'unreal.foliage.raw.Tree_Broad_A_LOD5' in by_id


def test_final_packages_are_not_claimed_and_the_seam_is_named(rows):
    result = foliage.foliage_units(rows, checkout=ROOT)
    assert not any(package.startswith(('/Game/Japan/Assets/', '/Game/Japan/FoliageLODs/'))
                   for package in result['packages'])
    assert {unit['op']['kind'] for unit in result['units']} == {'unreal.raw_import'}
    assert 'set_lod_from_static_mesh' in result['finish_seam'] and 'unreal.author' in result['finish_seam']


@pytest.mark.parametrize('change', ['missing', 'product', 'optional', 'script', 'format', 'commands'])
def test_wrong_export_shape_refuses(rows, change):
    selected = deepcopy(rows)
    index = next(i for i, row in enumerate(selected) if row['id'] == 'world.foliage.export.Grass_A_LOD1')
    row = selected[index]
    if change == 'missing': del selected[index]
    elif change == 'product': row['products'][0]['paths'] = ['build/yorimichi/exports/other']
    elif change == 'optional': row['products'][0]['optional_paths'] = ['x.fbx']
    elif change == 'script': row['commands'][0]['script'] = {'path': 'other.py'}
    elif change == 'format': row['commands'][0]['args'][-1] = '.glb'
    elif change == 'commands': row['commands'].append(deepcopy(row['commands'][0]))
    with pytest.raises(foliage.Unsupported):
        foliage.foliage_units(selected, checkout=ROOT)


def test_construction_never_scans_generated_content_or_mutates_rows(rows, monkeypatch):
    before = deepcopy(rows)
    original = Path.rglob
    def scan(path, pattern):
        assert path == ROOT / PLUGIN / 'Source'
        return original(path, pattern)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('generated folder scan')
    monkeypatch.setattr(Path, 'rglob', scan)
    monkeypatch.setattr(Path, 'glob', forbidden)
    monkeypatch.setattr(Path, 'iterdir', forbidden)
    assert len(foliage.foliage_units(rows, checkout=ROOT)['units']) == 10 * 6 + 8 * 3
    assert rows == before
