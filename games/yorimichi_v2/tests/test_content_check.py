"""The read-only content check fails on every kind of missing, stale or unexplained content, and fixes nothing."""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools' / 'content'
sys.path.insert(0, str(TOOLS))
import records  # noqa: E402

spec = importlib.util.spec_from_file_location('v2_content_check', TOOLS / 'check.py')
check = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check
spec.loader.exec_module(check)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data: bytes | str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def generated_asset(game, *, mesh=b'mesh v1', package=b'uasset v1'):
    folder = game / 'assets/props/bench'
    write(folder / 'src/bench.glb', mesh)
    write(folder / 'asset.toml', f'''schema = 1
id = "prop/bench"
kind = "static-mesh"
authority = "generated"
owner = "region/w04-skatepark"
license = "original"
[[sources]]
path = "src/bench.glb"
sha256 = "{sha(mesh)}"
[recipe]
importer = "static-mesh"
version = 1
settings = {{ collision = "convex" }}
[[outputs]]
package = "/Game/Props/SM_Bench"
''')
    write(game / 'unreal/Content/Props/SM_Bench.uasset', package)
    asset = records.load_asset(folder / 'asset.toml')
    records.write_json(folder / 'verified.json', {
        'schema': 1, 'kind': 'imported', 'asset': asset.id, 'engine': '5.8.0-test', 'tool': 'static-mesh@1',
        'input_fingerprint': records.input_fingerprint(asset, {}),
        'files': {'unreal/Content/Props/SM_Bench.uasset': sha(package)}})
    return folder


def editor_asset(game, *, package=b'material v1'):
    folder = game / 'assets/materials/painted'
    write(folder / 'asset.toml', '''schema = 1
id = "material/painted"
kind = "material"
authority = "editor"
owner = "shared/material/painted"
[[outputs]]
package = "/Game/Materials/M_Painted"
''')
    write(game / 'unreal/Content/Materials/M_Painted.uasset', package)
    records.write_json(folder / 'verified.json', {
        'schema': 1, 'kind': 'editor-saved', 'asset': 'material/painted', 'engine': '5.8.0-test',
        'files': {'unreal/Content/Materials/M_Painted.uasset': sha(package)}})
    return folder


def region(game, actors=None):
    folder = game / 'world/regions/w04-skatepark'
    write(folder / 'region.toml', '''schema = 1
id = "region/w04-skatepark"
bounds_cm = [0, 0, 10000, 10000]
neighbours = ["region/w01-start"]
maps = ["/Game/Maps/Island"]
''')
    files = {}
    for name, data in (actors or {}).items():
        rel = f'unreal/Content/__ExternalActors__/Maps/Island/0/AB/{name}.uasset'
        write(game / rel, data)
        files[rel] = sha(data)
    records.write_json(folder / 'actors.verified.json', {
        'schema': 1, 'kind': 'editor-saved', 'asset': 'region/w04-skatepark', 'engine': '5.8.0-test', 'files': files})
    return folder


def codes(game, **kw):
    problems, _ = check.check(game, **kw)
    return sorted({p.code for p in problems}), problems


@pytest.fixture
def game(tmp_path):
    generated_asset(tmp_path)
    editor_asset(tmp_path)
    region(tmp_path, {'BENCH01': b'actor v1'})
    return tmp_path


def tracked_snapshot(root: Path):
    return {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in root.rglob('*')
            if p.is_file() and 'Saved' not in p.parts}


def test_clean_content_passes_and_a_rerun_writes_nothing_tracked(game):
    assert codes(game) == ([], [])
    before = tracked_snapshot(game)
    assert codes(game) == ([], [])
    assert tracked_snapshot(game) == before


def test_quick_mode_reuses_unchanged_hashes(game):
    check.check(game)
    _, stats = check.check(game)
    assert stats['hashed'] == 0
    _, stats = check.check(game, full=True)
    assert stats['hashed'] == stats['files'] + 1        # every package plus the one source


def test_a_changed_source_asks_for_its_targeted_import(game):
    write(game / 'assets/props/bench/src/bench.glb', b'mesh v2')
    found, problems = codes(game)
    assert found == ['SOURCE_CHANGED']
    assert 'tools/import/run.py prop/bench' in problems[0].action


def test_same_size_same_mtime_edit_is_still_detected(game):
    check.check(game)                                   # warm the index
    path = game / 'unreal/Content/Props/SM_Bench.uasset'
    st = path.stat()
    path.write_bytes(b'uasset v2')                      # same length
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert codes(game)[0] == ['OUTPUT_CHANGED']


def test_missing_generated_output_fails(game):
    (game / 'unreal/Content/Props/SM_Bench.uasset').unlink()
    found, problems = codes(game)
    assert found == ['MISSING']
    assert 'targeted import' in problems[0].action


def test_lfs_pointer_is_reported_as_not_hydrated(game):
    write(game / 'unreal/Content/Props/SM_Bench.uasset',
          'version https://git-lfs.github.com/spec/v1\noid sha256:' + '0' * 64 + '\nsize 9\n')
    found, problems = codes(game)
    assert found == ['NOT_HYDRATED']
    assert problems[0].action.startswith('git lfs pull')


def test_editor_owned_change_asks_for_save_validation_never_reimport(game):
    write(game / 'unreal/Content/Materials/M_Painted.uasset', b'material v2 edited')
    found, problems = codes(game)
    assert found == ['OUTPUT_CHANGED']
    assert problems[0].action.startswith('save validation') and 'import' not in problems[0].action


def test_recipe_change_makes_the_import_stale(game):
    record = game / 'assets/props/bench/asset.toml'
    record.write_text(record.read_text().replace('collision = "convex"', 'collision = "complex"'))
    assert codes(game)[0] == ['STALE_IMPORT']


def test_input_dependency_change_makes_dependents_stale(game):
    record = game / 'assets/props/bench/asset.toml'
    record.write_text(record.read_text().replace('[[sources]]', 'input_dependencies = ["material/painted"]\n[[sources]]'))
    asset = records.load_asset(record)
    material = records.load_verified(game / 'assets/materials/painted/verified.json')
    verified = json.loads((game / 'assets/props/bench/verified.json').read_text())
    verified['input_fingerprint'] = records.input_fingerprint(
        asset, {'material/painted': records.state_fingerprint(material)})
    records.write_json(game / 'assets/props/bench/verified.json', verified)
    assert codes(game) == ([], [])
    # A genuine material save updates its record; the mesh built against the old one is now stale.
    write(game / 'unreal/Content/Materials/M_Painted.uasset', b'material v2')
    material['files']['unreal/Content/Materials/M_Painted.uasset'] = sha(b'material v2')
    records.write_json(game / 'assets/materials/painted/verified.json', material)
    assert codes(game)[0] == ['STALE_IMPORT']


def test_unowned_package_fails(game):
    write(game / 'unreal/Content/Stray/SM_Stray.uasset', b'stray')
    found, problems = codes(game)
    assert found == ['UNOWNED']
    assert problems[0].subject == 'unreal/Content/Stray/SM_Stray.uasset'


def test_new_actor_without_region_record_fails_and_edits_are_caught(game):
    write(game / 'unreal/Content/__ExternalActors__/Maps/Island/1/CD/NEWACTOR.uasset', b'new actor')
    assert codes(game)[0] == ['UNOWNED']
    (game / 'unreal/Content/__ExternalActors__/Maps/Island/1/CD/NEWACTOR.uasset').unlink()
    write(game / 'unreal/Content/__ExternalActors__/Maps/Island/0/AB/BENCH01.uasset', b'actor moved')
    found, problems = codes(game)
    assert found == ['OUTPUT_CHANGED'] and problems[0].subject == 'region/w04-skatepark'


def test_two_records_owning_one_package_fail(game):
    folder = game / 'assets/props/bench2'
    write(folder / 'asset.toml', (game / 'assets/props/bench/asset.toml').read_text()
          .replace('prop/bench', 'prop/bench-two').replace('src/bench.glb', '../bench/src/bench.glb'))
    found, _ = codes(game)
    assert 'OWNERSHIP' in found or 'SCHEMA' in found


def test_records_reject_unknown_keys(tmp_path):
    folder = generated_asset(tmp_path)
    record = folder / 'asset.toml'
    record.write_text(record.read_text().replace('[[sources]]', '[[sources]]\ninput_dependencies = ["x/y"]'))
    with pytest.raises(records.RecordError, match='unknown'):
        records.load_asset(record)


def test_records_reject_personal_paths(tmp_path):
    folder = tmp_path / 'assets/x'
    write(folder / 'asset.toml', '''schema = 1
id = "prop/x"
kind = "static-mesh"
authority = "generated"
owner = "region/a"
[[sources]]
path = "''' + '/' + 'Users/someone/x.glb' + '''"
sha256 = "''' + '0' * 64 + '''"
[recipe]
importer = "static-mesh"
version = 1
[[outputs]]
package = "/Game/X"
''')
    with pytest.raises(records.RecordError, match='portable'):
        records.load_asset(folder / 'asset.toml')


def test_editor_owned_record_cannot_have_a_recipe(tmp_path):
    folder = tmp_path / 'assets/m'
    write(folder / 'asset.toml', '''schema = 1
id = "material/m"
kind = "material"
authority = "editor"
owner = "shared/material/m"
[recipe]
importer = "x"
version = 1
[[outputs]]
package = "/Game/M"
''')
    with pytest.raises(records.RecordError, match='no \\[recipe\\]'):
        records.load_asset(folder / 'asset.toml')


def test_published_schemas_match_the_validator():
    schemas = Path(__file__).resolve().parents[1] / 'schemas'
    asset = json.loads((schemas / 'asset.schema.json').read_text())
    region_schema = json.loads((schemas / 'region.schema.json').read_text())
    assert set(asset['properties']) == records.ASSET_KEYS
    assert set(region_schema['properties']) == records.REGION_KEYS
    assert asset['properties']['kind']['enum'] == list(records.KINDS)
    assert asset['properties']['authority']['enum'] == list(records.AUTHORITIES)


def test_reordering_sources_against_their_packages_changes_the_fingerprint(tmp_path):
    """The importer pairs sources with generated packages in record order, so swapping them is a stale import."""
    def fingerprint(order):
        folder = tmp_path / '-'.join(order)
        rows = ''.join(f'[[sources]]\npath = "{n}.glb"\nsha256 = "{sha(n.encode())}"\n' for n in order)
        write(folder / 'asset.toml', 'schema = 1\nid = "prop/pair"\nkind = "static-mesh"\nauthority = "generated"\n'
              'owner = "region/w04-skatepark"\nlicense = "original"\n' + rows +
              '[recipe]\nimporter = "static-mesh"\nversion = 1\n'
              '[[outputs]]\npackage = "/Game/V2/A"\n[[outputs]]\npackage = "/Game/V2/B"\n')
        return records.input_fingerprint(records.load_asset(folder / 'asset.toml'), {})
    assert fingerprint(['a', 'b']) != fingerprint(['b', 'a'])


def test_a_scene_patch_deleted_outright_fails_against_its_region_roster(game):
    folder = game / 'world/regions/w04-skatepark'
    kept = 'unreal/Content/__ExternalActors__/Maps/Island/0/AB/BENCH01.uasset'
    gone = 'unreal/Content/__ExternalActors__/Maps/Island/0/AB/TREES07.uasset'
    records.write_json(folder / 'patches.json', {'schema': 1, 'region': 'region/w04-skatepark', 'patches': {
        'a1': {'key': 'HD_Bench', 'package': kept}, 'b2': {'key': 'TH_Dressing', 'package': gone}}})
    found, problems = codes(game)
    assert found == ['PATCH_MISSING']
    assert 'b2 (TH_Dressing)' in problems[0].detail


def runtime_data(game, files=None):
    for rel, data in (files or {'Data/world.json': b'{"size": 600}', 'Data/skatepark/park.json': b'{}'}).items():
        write(game / 'unreal/Content' / rel, data)
    records.write_data_lock(game)


def test_pinned_runtime_data_passes(game):
    runtime_data(game)
    assert codes(game)[0] == []


def test_deleted_or_unhydrated_runtime_data_fails_with_its_restore_route(game):
    runtime_data(game)
    (game / 'unreal/Content/Data/world.json').unlink()
    found, problems = codes(game)
    assert found == ['MISSING'] and 'git checkout -- "games/yorimichi_v2/unreal/Content/Data/world.json"' in problems[0].action
    write(game / 'unreal/Content/Data/world.json',
          'version https://git-lfs.github.com/spec/v1\noid sha256:' + '0' * 64 + '\nsize 9\n')
    found, problems = codes(game)
    assert found == ['NOT_HYDRATED'] and problems[0].action.startswith('git lfs pull')


def test_changed_or_unpinned_runtime_data_fails(game):
    runtime_data(game)
    write(game / 'unreal/Content/Data/world.json', b'{"size": 601}')
    write(game / 'unreal/Content/Data/extra.json', b'{}')
    found, problems = codes(game)
    assert found == ['DATA_CHANGED', 'DATA_UNPINNED']
    assert all('--pin-data' in p.action for p in problems)


def test_runtime_data_without_a_lock_fails(game):
    write(game / 'unreal/Content/Data/world.json', b'{}')
    assert codes(game)[0] == ['DATA_UNPINNED']
