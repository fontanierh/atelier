"""Targeted import: unchanged inputs start nothing; a failure restores exactly the asset's own files."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402

spec = importlib.util.spec_from_file_location('v2_import_run', ROOT / 'tools' / 'import' / 'run.py')
run = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run
spec.loader.exec_module(run)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def mesh_asset(game, name, package, source=b'glb v1', deps=()):
    folder = game / 'assets/props' / name
    write(folder / 'src/model.glb', source)
    dep_line = f'input_dependencies = {json.dumps(list(deps))}\n' if deps else ''
    write(folder / 'asset.toml', f'''schema = 1
id = "prop/{name}"
kind = "static-mesh"
authority = "generated"
owner = "region/w04-skatepark"
{dep_line}[[sources]]
path = "src/model.glb"
sha256 = "{sha(source)}"
[recipe]
importer = "static-mesh"
version = 1
[[outputs]]
package = "{package}"
''')
    return folder


class FakeEditor:
    """Writes the planned packages like the editor would; can misbehave on request."""

    def __init__(self, *, stray=None, crash_after_first=False):
        self.calls, self.stray, self.crash = [], stray, crash_after_first

    def __call__(self, game, asset, plan_file):
        plan = json.loads(plan_file.read_text())
        self.calls.append(asset.id)
        for i, package in enumerate(plan['packages']):
            target = records.package_files(game, package)[0]
            write(target, f'imported {asset.id} from {plan["portable_sources"][0]}'.encode())
            if self.crash:
                raise RuntimeError('editor crashed')
        if self.stray:
            write(game / self.stray, b'unexpected')


@pytest.fixture
def game(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_AGENT', run.BOOTSTRAP_WRITER)
    mesh_asset(tmp_path, 'bench', '/Game/Props/SM_Bench')
    write(tmp_path / 'unreal/Content/Other/SM_Other.uasset', b'someone else')
    return tmp_path


def do(game, ids, editor):
    ordered, by_id = run.plan(game, ids)
    done = []
    for asset in ordered:
        by_id = {a.id: a for a in records.discover(game)[0]}
        done.append(run.import_one(game, by_id[asset.id], by_id, engine='5.8.2-1', claim=None, importer=editor,
                                   echo=lambda *_: None))
    return done


def test_import_writes_its_packages_and_record_then_an_unchanged_rerun_starts_nothing(game):
    editor = FakeEditor()
    assert do(game, ['prop/bench'], editor) == [True]
    record = records.load_verified(game / 'assets/props/bench/verified.json')
    assert list(record['files']) == ['unreal/Content/Props/SM_Bench.uasset']
    stamp = (game / 'assets/props/bench/verified.json').stat().st_mtime_ns
    assert do(game, ['prop/bench'], editor) == [False]
    assert editor.calls == ['prop/bench']
    assert (game / 'assets/props/bench/verified.json').stat().st_mtime_ns == stamp
    check_spec = importlib.util.spec_from_file_location('v2_import_check', ROOT / 'tools' / 'content' / 'check.py')
    check = importlib.util.module_from_spec(check_spec)
    sys.modules[check_spec.name] = check
    check_spec.loader.exec_module(check)
    problems, _ = check.check(game)
    assert [(p.code, p.subject) for p in problems] == [('UNOWNED', 'unreal/Content/Other/SM_Other.uasset')]


def test_a_source_edit_reimports_and_records_the_new_hash(game):
    do(game, ['prop/bench'], FakeEditor())
    write(game / 'assets/props/bench/src/model.glb', b'glb v2')
    editor = FakeEditor()
    assert do(game, ['prop/bench'], editor) == [True]
    assert sha(b'glb v2') in (game / 'assets/props/bench/asset.toml').read_text()


def test_dependents_are_planned_after_their_dependency(game):
    mesh_asset(game, 'bench-lod', '/Game/Props/SM_BenchLod', deps=['prop/bench'])
    ordered, _ = run.plan(game, ['prop/bench'])
    assert [a.id for a in ordered] == ['prop/bench', 'prop/bench-lod']


def test_a_write_outside_the_declared_packages_fails_and_restores_everything(game):
    before = (game / 'unreal/Content/Other/SM_Other.uasset').read_bytes()
    with pytest.raises(run.ImportError_, match='outside its declared packages'):
        do(game, ['prop/bench'], FakeEditor(stray='unreal/Content/Other/SM_Stray.uasset'))
    assert not (game / 'unreal/Content/Props/SM_Bench.uasset').exists()
    assert not (game / 'assets/props/bench/verified.json').exists()
    assert (game / 'unreal/Content/Other/SM_Other.uasset').read_bytes() == before


def test_a_crash_restores_the_previous_import_exactly(game):
    do(game, ['prop/bench'], FakeEditor())
    good = (game / 'unreal/Content/Props/SM_Bench.uasset').read_bytes()
    record = (game / 'assets/props/bench/verified.json').read_text()
    write(game / 'assets/props/bench/src/model.glb', b'glb v3')
    with pytest.raises(RuntimeError, match='editor crashed'):
        do(game, ['prop/bench'], FakeEditor(crash_after_first=True))
    assert (game / 'unreal/Content/Props/SM_Bench.uasset').read_bytes() == good
    assert (game / 'assets/props/bench/verified.json').read_text() == record


def test_a_journal_left_by_a_killed_run_is_restored_before_the_next_import(game):
    do(game, ['prop/bench'], FakeEditor())
    asset = records.load_asset(game / 'assets/props/bench/asset.toml')
    journal = run.Journal(game, asset)
    journal.begin(run.generated_files(game, asset))
    write(game / 'unreal/Content/Props/SM_Bench.uasset', b'half written')     # the process died here
    assert journal.restore() == ['unreal/Content/Props/SM_Bench.uasset']
    assert b'imported prop/bench' in (game / 'unreal/Content/Props/SM_Bench.uasset').read_bytes()


def test_an_unauthorized_writer_is_refused_before_any_write(game, monkeypatch):
    monkeypatch.setenv('ATELIER_AGENT', 'someone-else')
    editor = FakeEditor()
    with pytest.raises(run.ImportError_, match='bootstrap writer'):
        do(game, ['prop/bench'], editor)
    assert editor.calls == [] and not (game / 'unreal/Content/Props').exists()


def test_editor_owned_assets_are_never_imported(game):
    write(game / 'assets/materials/m/asset.toml', '''schema = 1
id = "material/m"
kind = "material"
authority = "editor"
owner = "shared/material/m"
[[outputs]]
package = "/Game/M"
''')
    with pytest.raises(run.ImportError_, match='editor-owned'):
        run.plan(game, ['material/m'])


def test_a_split_reimport_drops_a_generated_companion_it_no_longer_wrote(game):
    folder = game / 'assets/props/split'
    write(folder / 'src/model.glb', b'glb v1')
    write(folder / 'asset.toml', f'''schema = 1
id = "prop/split"
kind = "static-mesh"
authority = "split"
owner = "region/w04-skatepark"
[[sources]]
path = "src/model.glb"
sha256 = "{sha(b'glb v1')}"
[recipe]
importer = "static-mesh"
version = 1
[[outputs]]
package = "/Game/Props/SM_Split"
writer = "generated"
[[outputs]]
package = "/Game/Props/MI_Split"
writer = "editor"
''')
    do(game, ['prop/split'], FakeEditor())
    verified = folder / 'verified.json'
    record = records.load_verified(verified)
    # As if the previous import also wrote a .ubulk, and the editor saved the material instance.
    record['files']['unreal/Content/Props/SM_Split.ubulk'] = sha(b'old bulk')
    record['files']['unreal/Content/Props/MI_Split.uasset'] = sha(b'editor saved')
    verified.write_text(json.dumps(record))
    write(folder / 'src/model.glb', b'glb v2')
    assert do(game, ['prop/split'], FakeEditor()) == [True]
    files = records.load_verified(verified)['files']
    assert 'unreal/Content/Props/SM_Split.ubulk' not in files
    assert files['unreal/Content/Props/MI_Split.uasset'] == sha(b'editor saved')


def test_recovery_restores_only_files_the_current_import_may_write(game):
    asset = records.discover(game)[0][0]
    journal = run.Journal(game, asset)
    journal.begin([game / 'unreal/Content/Other/SM_Other.uasset'])   # left by an older record's import
    write(game / 'unreal/Content/Other/SM_Other.uasset', b'half written')
    write(game / 'assets/props/bench/src/model.glb', b'glb v2')
    with pytest.raises(run.ImportError_, match='outside its current outputs'):
        do(game, ['prop/bench'], FakeEditor())
    assert (game / 'unreal/Content/Other/SM_Other.uasset').read_bytes() == b'half written'   # untouched


def test_an_editor_owned_change_in_a_split_asset_does_not_reimport(game):
    test_a_split_reimport_drops_a_generated_companion_it_no_longer_wrote(game)
    write(game / 'unreal/Content/Props/MI_Split.uasset', b'edited again in the editor')
    editor = FakeEditor()
    assert do(game, ['prop/split'], editor) == [False] and editor.calls == []


def test_the_import_step_of_an_asset_id_is_a_valid_build_step_name():
    import re
    name = records.import_step('prop/lantern')
    assert name == 'import.prop.lantern'
    assert re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', name)   # atelier.build_products' step name rule
