"""Save validation records exactly the saved editor-owned packages, never imports, and no change writes nothing."""
import importlib.util
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


sv = load('v2_save_validate', 'tools/content/save_validate.py')
check = load('v2_save_check', 'tools/content/check.py')


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def region(game, name, bounds='[0, 0, 100, 100]'):
    write(game / f'world/regions/{name}/region.toml', f'''schema = 1
id = "region/{name}"
bounds_cm = {bounds}
maps = ["/Game/V2/Maps/Slice"]
''')


ACTORS = 'unreal/Content/__ExternalActors__/V2/Maps/Slice'


@pytest.fixture
def game(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_AGENT', sv.BOOTSTRAP_WRITER)
    monkeypatch.setattr(sv, 'engine_identity', lambda: '5.8.2-56702186')
    write(tmp_path / 'assets/materials/painted/asset.toml', '''schema = 1
id = "material/painted"
kind = "material"
authority = "editor"
owner = "shared/material/painted"
[[outputs]]
package = "/Game/Japan/Materials/M_Painted"
''')
    write(tmp_path / 'unreal/Content/Japan/Materials/M_Painted.uasset', b'material')
    write(tmp_path / 'unreal/Content/V2/Maps/Slice.umap', b'map')
    write(tmp_path / 'assets/maps/slice/asset.toml', '''schema = 1
id = "map/slice"
kind = "map"
authority = "editor"
owner = "shared/map/slice"
[[outputs]]
package = "/Game/V2/Maps/Slice"
''')
    region(tmp_path, 'a')
    region(tmp_path, 'b')
    write(tmp_path / f'{ACTORS}/0/AA/BENCH.uasset', b'bench')
    write(tmp_path / f'{ACTORS}/0/BB/HOUSE.uasset', b'house')
    return tmp_path


def quiet(*_):
    pass


def test_an_editor_asset_is_recorded_once_and_an_unchanged_rerun_writes_nothing(game):
    assert sv.validate(game, 'material/painted', echo=quiet) is True
    stamp = (game / 'assets/materials/painted/verified.json').stat().st_mtime_ns
    assert sv.validate(game, 'material/painted', echo=quiet) is False
    assert (game / 'assets/materials/painted/verified.json').stat().st_mtime_ns == stamp


def test_regions_own_their_actors_and_the_whole_tree_then_checks_clean(game):
    sv.validate(game, 'material/painted', echo=quiet)
    sv.validate(game, 'map/slice', echo=quiet)
    sv.validate(game, 'region/a', add=[f'{ACTORS}/0/AA/BENCH.uasset'], echo=quiet)
    sv.validate(game, 'region/b', add=[f'{ACTORS}/0/BB/HOUSE.uasset'], echo=quiet)
    assert check.check(game)[0] == []
    # an edit to one actor is caught, and its save validation touches only its region's record
    write(game / f'{ACTORS}/0/AA/BENCH.uasset', b'bench moved')
    assert [p.code for p in check.check(game)[0]] == ['OUTPUT_CHANGED']
    before = (game / 'world/regions/b/actors.verified.json').read_text()
    sv.validate(game, 'region/a', echo=quiet)
    assert check.check(game)[0] == []
    assert (game / 'world/regions/b/actors.verified.json').read_text() == before


def test_an_actor_owned_by_another_region_must_be_moved_explicitly(game):
    sv.validate(game, 'region/a', add=[f'{ACTORS}/0/AA/BENCH.uasset'], echo=quiet)
    with pytest.raises(sv.ValidationError, match='belongs to region/a'):
        sv.validate(game, 'region/b', add=[f'{ACTORS}/0/AA/BENCH.uasset'], echo=quiet)


def test_a_deleted_actor_drops_out_of_its_region(game):
    sv.validate(game, 'region/a', add=[f'{ACTORS}/0/AA/BENCH.uasset', f'{ACTORS}/0/BB/HOUSE.uasset'], echo=quiet)
    (game / f'{ACTORS}/0/BB/HOUSE.uasset').unlink()
    sv.validate(game, 'region/a', echo=quiet)
    assert list(records.load_verified(game / 'world/regions/a/actors.verified.json')['files']) == [
        f'{ACTORS}/0/AA/BENCH.uasset']


def test_labels_assign_new_actors_when_the_header_reader_knows_them(game, monkeypatch):
    monkeypatch.setattr(sv, 'actor_info', lambda path: ('region/b:House_C:root', None) if path.name == 'HOUSE.uasset'
                        else (None, None))
    sv.validate(game, 'region/b', echo=quiet)
    assert list(records.load_verified(game / 'world/regions/b/actors.verified.json')['files']) == [
        f'{ACTORS}/0/BB/HOUSE.uasset']


def test_generated_assets_and_unauthorized_writers_are_refused(game, monkeypatch):
    write(game / 'assets/props/x/src/x.glb', b'x')
    write(game / 'assets/props/x/asset.toml', '''schema = 1
id = "prop/x"
kind = "static-mesh"
authority = "generated"
owner = "region/a"
[[sources]]
path = "src/x.glb"
sha256 = "''' + records.sha256_file(game / 'assets/props/x/src/x.glb') + '''"
[recipe]
importer = "static-mesh"
version = 1
[[outputs]]
package = "/Game/X"
''')
    with pytest.raises(sv.ValidationError, match='generated'):
        sv.validate(game, 'prop/x', echo=quiet)
    monkeypatch.setenv('ATELIER_AGENT', 'someone-else')
    with pytest.raises(sv.ValidationError, match='bootstrap writer'):
        sv.validate(game, 'material/painted', echo=quiet)
    assert not (game / 'assets/materials/painted/verified.json').exists()


def test_an_unlabelled_actor_joins_the_region_its_location_falls_in(game, monkeypatch):
    monkeypatch.setattr(sv, 'actor_info', lambda path: ('Bench', (50.0, 50.0, 0.0)) if path.name == 'BENCH.uasset'
                        else ('House', (150.0, 50.0, 0.0)))
    sv.validate(game, 'region/a', echo=quiet)
    assert list(records.load_verified(game / 'world/regions/a/actors.verified.json')['files']) == [
        f'{ACTORS}/0/AA/BENCH.uasset']


def test_a_region_whose_last_actor_was_deleted_records_an_empty_set(game):
    sv.validate(game, 'region/a', add=[f'{ACTORS}/0/AA/BENCH.uasset'], echo=quiet)
    (game / f'{ACTORS}/0/AA/BENCH.uasset').unlink()
    sv.validate(game, 'region/a', echo=quiet)
    assert records.load_verified(game / 'world/regions/a/actors.verified.json')['files'] == {}
