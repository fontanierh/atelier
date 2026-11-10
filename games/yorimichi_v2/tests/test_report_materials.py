"""The read-only material report job (unreal/Scripts/report_materials.py): its pure-Python part, and the 43 package
paths it is run on. The Unreal calls are not imported here; the module loads against a stub `unreal`."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'unreal' / 'Scripts' / 'report_materials.py'
PACKAGES = ROOT / 'docs' / 'inventory' / 'japan-materials-packages.txt'
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402


@pytest.fixture
def job(monkeypatch):
    stub = types.ModuleType('unreal')
    stub.EditorAssetLibrary = stub.MaterialEditingLibrary = stub
    stub.MaterialInstanceConstant = type('MaterialInstanceConstant', (), {})
    stub.log = lambda message: None
    monkeypatch.setitem(sys.modules, 'unreal', stub)
    spec = importlib.util.spec_from_file_location('report_materials_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)   # main() runs only as __main__, so this loads no editor state
    return module


def test_split_packages_takes_any_whitespace(job):
    assert job.split_packages('/Game/Japan/Materials/MI_Bark\n /Game/Japan/Materials/MI_Sky  ') == [
        '/Game/Japan/Materials/MI_Bark', '/Game/Japan/Materials/MI_Sky']


def test_check_coverage_names_missing_and_failed_rows_and_nothing_else(job):
    expected = ['/Game/A/MI_1', '/Game/A/MI_2', '/Game/A/MI_3']
    report = {'/Game/A/MI_1': {'parent': 'x'}, '/Game/A/MI_3': {'error': 'boom'}, '/Game/A/MI_extra': {}}
    assert job.check_coverage(report, expected) == (['/Game/A/MI_2'], ['/Game/A/MI_3'])


def test_round_value_is_fixed_precision_and_plain_float(job):
    assert job.round_value(0.1234567891) == 0.123457
    assert type(job.round_value(1)) is float


def test_the_package_list_is_the_43_records_packages_in_order():
    listed = PACKAGES.read_text().split()
    assert len(listed) == len(set(listed)) == 43
    assert all(p.startswith('/Game/Japan/Materials/MI_') for p in listed)
    family = ROOT / 'assets' / 'material' / 'japan' / 'materials'   # the JAPANMI records (were adopted/japan/materials/<name>)
    names = ['bark', 'buildings', 'foliage', 'ground', 'rock-concrete', 'sky-wind', 'water']
    recorded = [o.package for n in names for o in records.load_asset(family / f'{n}-instances' / 'asset.toml').outputs]
    recorded += [o.package for n in ('leaf-amber', 'leaf-crimson')
                 for o in records.load_asset(ROOT / 'assets' / 'material' / 'japan' / n / 'asset.toml').outputs]
    assert sorted(listed) == sorted(recorded)


def test_the_report_is_refused_inside_the_game_tree_even_through_a_link(job, tmp_path):
    game = tmp_path / 'game'
    (game / 'unreal' / 'Content').mkdir(parents=True)
    outside = tmp_path / 'reports' / 'japan.json'
    assert job.report_target(str(outside), str(game)) == str(outside.resolve())
    for inside in (game / 'unreal' / 'Content' / 'MI_Bark.uasset', game):
        with pytest.raises(ValueError, match='inside'):
            job.report_target(str(inside), str(game))
    link = tmp_path / 'link'
    link.symlink_to(game / 'unreal' / 'Content')
    with pytest.raises(ValueError, match='inside'):
        job.report_target(str(link / 'new.uasset'), str(game))
    assert job.GAME == str(Path(job.__file__).resolve().parents[2])
