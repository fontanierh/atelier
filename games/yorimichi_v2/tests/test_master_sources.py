"""Declared helper sources remain pinned and isolated across imports in the same Python process; no Unreal is run."""
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import py_compile
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/content'))
sys.path.insert(0, str(ROOT / 'tools/migrate'))
import master_records as planner  # noqa: E402
import records  # noqa: E402

SPEC = importlib.util.spec_from_file_location('v2_master_sources_test', ROOT / 'unreal/Scripts/master_sources.py')
loader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loader)
SWORD = planner.load_families()['swordcamp']


def sources(folder, value):
    folder.mkdir(parents=True)
    entry, helper = folder / 'entry.py', folder / 'haze.py'
    entry.write_text('from . import haze\ndef build():\n    return haze.VALUE\n')
    helper.write_text(f'VALUE = {value!r}\n')
    return entry, helper


def namespaces():
    return {name for name in sys.modules if name.startswith('_v2_master_')}


def test_warm_imports_never_reuse_another_records_helper(tmp_path, monkeypatch):
    """@cc [owner:fontanierh,label:correctness] warm-master-helper-isolation
    Identically named helpers from distinct records retain their own values; neither a prior job nor an unrelated global
    module supplies the next builder's helper. Both private namespaces are removed without modifying sys.path.
    """
    global_helper = ModuleType('haze')
    global_helper.VALUE = 'unrelated'
    monkeypatch.setitem(sys.modules, 'haze', global_helper)
    first, second = sources(tmp_path / 'first', 'first'), sources(tmp_path / 'second', 'second')
    before, path_before = namespaces(), list(sys.path)
    with loader.builder(first, 'build') as build_first:
        first_module = build_first.__module__
        assert build_first() == 'first'
    assert namespaces() == before
    with loader.builder(second, 'build') as build_second:
        assert build_second() == 'second'
        assert build_second.__module__ != first_module
    assert namespaces() == before
    assert sys.modules['haze'] is global_helper
    assert sys.path == path_before


def test_an_unlisted_sibling_helper_is_not_imported(tmp_path):
    entry, _ = sources(tmp_path / 'record', 'unlisted')
    before = namespaces()
    with pytest.raises(ImportError):
        with loader.builder([entry], 'build'):
            pytest.fail('the unlisted helper was loaded')
    assert namespaces() == before


@pytest.mark.parametrize('failure', ['helper', 'build'])
def test_failed_imports_and_builds_remove_their_private_modules(tmp_path, failure):
    entry, helper = sources(tmp_path / 'record', 'test')
    if failure == 'helper':
        helper.write_text('raise RuntimeError("helper refused")\n')
    else:
        entry.write_text('from . import haze\ndef build():\n    raise RuntimeError("build refused")\n')
    before = namespaces()
    with pytest.raises(RuntimeError, match=f'{failure} refused'):
        with loader.builder([entry, helper], 'build') as build:
            build()
    assert namespaces() == before


def test_source_bytes_override_an_old_timestamp_bytecode_cache(tmp_path):
    entry, helper = sources(tmp_path / 'record', 'old')
    stat = helper.stat()
    py_compile.compile(str(helper), doraise=True)
    helper.write_text("VALUE = 'new'\n")  # the old cache's size and timestamp still match
    os.utime(helper, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with loader.builder([entry, helper], 'build') as build:
        assert build() == 'new'


def test_a_single_source_builder_still_loads(tmp_path):
    entry = tmp_path / 'entry.py'
    entry.write_text('def build():\n    return 42\n')
    with loader.builder([entry], 'build') as build:
        assert build() == 42


@pytest.fixture
def prepared_master(tmp_path):
    game = tmp_path / 'game'
    folder = game / 'assets/master/test/surface'
    entry, helper = sources(folder / 'src', 42)
    source_rows = ''.join(f'[[sources]]\npath = "src/{path.name}"\n'
                          f'sha256 = "{hashlib.sha256(path.read_bytes()).hexdigest()}"\n' for path in (entry, helper))
    record = folder / 'asset.toml'
    record.write_text('schema = 1\nid = "master/test/surface"\nkind = "material-master"\nauthority = "generated"\n'
                      'owner = "shared/test/surface"\n' + source_rows +
                      '[recipe]\nimporter = "material-master"\nversion = 1\n[recipe.settings]\n'
                      'builder = "build"\nreads = []\n[[outputs]]\npackage = "/Game/Test/M_Surface"\n')
    asset = records.load_asset(record)
    plan = dict(asset=asset.id, kind=asset.kind, importer='material-master', version=1, settings=asset.recipe['settings'],
                sources=[str(path.resolve()) for path in (entry, helper)],
                portable_sources=['games/yorimichi_v2/' + path.relative_to(game).as_posix() for path in (entry, helper)],
                packages=['/Game/Test/M_Surface'])
    return game, asset, plan


def test_verified_snapshots_are_the_bytes_executed(prepared_master):
    game, asset, plan = prepared_master
    contents = loader.checked_sources(game, asset, plan)
    # This swap happens after verification. The loader must retain the accepted bytes, without reopening the files.
    for path in plan['sources']:
        Path(path).write_text('raise RuntimeError("changed after verification")\n')
    before = namespaces()
    with loader.builder(plan['sources'], 'build', source_bytes=contents) as build:
        assert build() == 42
    assert namespaces() == before


@pytest.mark.parametrize('route', ['direct-build', 'editor'])
@pytest.mark.parametrize('changed', ['entry', 'helper', 'source-path', 'portable-path', 'settings'])
def test_master_write_boundaries_refuse_changed_sources_before_execution(prepared_master, monkeypatch, route, changed):
    """Prepared plans are replayable only while their recipe and every declared source still match the canonical record."""
    game, asset, plan = prepared_master
    if changed in ('entry', 'helper'):
        path = Path(plan['sources'][changed == 'helper'])
        path.write_text(path.read_text() + '\n# changed after preparation\n')
        error = 'pinned sha256'
    elif changed == 'source-path':
        other = game / 'unlisted.py'
        other.write_bytes(Path(plan['sources'][0]).read_bytes())   # even identical bytes do not authorize another path
        plan['sources'][0] = str(other)
        error = 'sources does not match'
    elif changed == 'portable-path':
        plan['portable_sources'][0] = 'games/yorimichi_v2/assets/unlisted.py'
        error = 'portable_sources does not match'
    else:
        plan['settings'] = dict(plan['settings'], builder='other')
        error = 'settings does not match'
    authority = SimpleNamespace(discovered=lambda _: SimpleNamespace(by_id={asset.id: asset}))
    monkeypatch.setitem(sys.modules, 'authority', authority)
    touched = []
    if route == 'direct-build':
        spec = importlib.util.spec_from_file_location('v2_master_source_boundary_recipe', ROOT / 'build.py')
        recipe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(recipe)
        recipe.GAME = game
        plan_file = game / 'plan.json'
        plan_file.write_text(json.dumps(plan))
        monkeypatch.setenv('V2_IMPORT_PLAN', str(plan_file))
        authority.authorize = lambda *args, **kwargs: touched.append('authorize')
        action = lambda: recipe._authorize_import(None, io.StringIO())
    else:
        # Execute the actual editor entry function without importing or starting Unreal.
        tree = ast.parse((ROOT / 'unreal/Scripts/import_asset.py').read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_material_master')
        namespace = dict(Path=Path, sys=sys, __file__=str(game / 'unreal/Scripts/import_asset.py'),
                         _checked_master_sources=loader.checked_sources,
                         _master_builder=lambda *args, **kwargs: touched.append('builder'))
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'import_asset.py', 'exec'), namespace)
        action = lambda: namespace['_material_master'](plan)
    before = namespaces()
    with pytest.raises(RuntimeError, match=error):
        action()
    assert not touched and namespaces() == before


def test_source_snapshots_must_cover_every_declared_file(prepared_master):
    game, asset, plan = prepared_master
    contents = loader.checked_sources(game, asset, plan)
    with pytest.raises(RuntimeError, match='one source snapshot'):
        with loader.builder(plan['sources'], 'build', source_bytes=contents[:1]):
            pytest.fail('a missing helper snapshot was accepted')


@pytest.mark.parametrize('mode', ['base-only', 'with-glow', 'glow-only'])
def test_shared_haze_preserves_the_complete_donor_branches(mode):
    """The shared implementation retains the donor's optional emission and named output pins for future consumers."""
    from test_master_skatepark import World, Token, fake_unreal

    original_dir = ROOT / 'assets/adopted/japan/materials/base-materials/source/unreal/Scripts'
    sea = (original_dir / 'sea_look.py').read_bytes()
    atmosphere = (original_dir / 'atmosphere.py').read_bytes()
    assert hashlib.sha256(sea).hexdigest() == 'ffae53cded2bb461534c88c100bc75d3f93ec3bf396eb303e5d4ec3ad4dbb4fa'
    assert hashlib.sha256(atmosphere).hexdigest() == 'b59478df43df83b8c7386e7ff7c097f32faf647716fdacb804f3cf0c99336ebf'
    sea_namespace = {}
    exec(compile(sea, 'donor sea_look.py', 'exec'), sea_namespace)
    tree = ast.parse(atmosphere)
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    donor_world, actual_world = World(), World()
    donor_unreal, actual_unreal = fake_unreal(donor_world), fake_unreal(actual_world)
    donor_namespace = {'unreal': donor_unreal, 'S': SimpleNamespace(**sea_namespace)}
    exec(compile(tree, 'donor atmosphere.py', 'exec'), donor_namespace)
    helper_path = planner.BUILDERS / 'master_haze.py'
    with loader.builder([helper_path], 'apply' if mode != 'glow-only' else 'glow') as function:
        args = [Token(actual_world, 'material')]
        donor_args = [Token(donor_world, 'material')]
        kwargs = {'x': 123, 'y': 45}
        if mode != 'glow-only':
            args.append(Token(actual_world, 'base'))
            donor_args.append(Token(donor_world, 'base'))
            kwargs['base_out'] = 'RGB'
            if mode == 'with-glow':
                args.append(Token(actual_world, 'emission'))
                donor_args.append(Token(donor_world, 'emission'))
                kwargs['glow_out'] = 'R'
        function(actual_unreal, *args, **kwargs)
        donor_namespace['apply' if mode != 'glow-only' else 'glow'](*donor_args, **kwargs)
    assert actual_world.log == donor_world.log


def test_duplicate_helper_module_names_refuse_before_loading(tmp_path):
    entry, first = sources(tmp_path / 'first', 'first')
    _, second = sources(tmp_path / 'second', 'second')
    before = namespaces()
    with pytest.raises(RuntimeError, match='distinct helper module names'):
        with loader.builder([entry, first, second], 'build'):
            pytest.fail('duplicate names were accepted')
    assert namespaces() == before


def test_the_planner_copies_every_declared_helper_with_its_pin(tmp_path):
    family = dict(SWORD, adopted='adopted/test/materials', masters=SWORD['masters'][:1])
    adopted = tmp_path / 'assets/adopted/test/materials/asset.toml'
    adopted.parent.mkdir(parents=True)
    adopted.write_text('schema = 1\nid = "adopted/test/materials"\nkind = "adopted"\nauthority = "editor"\n'
                       'owner = "shared/test/materials"\n[[outputs]]\npackage = "/Game/SwordCamp/Materials/M_SwordCamp"\n')
    writes = planner.claim_ops(tmp_path, family)['writes']
    record_rel = 'assets/master/swordcamp/camp/asset.toml'
    destination = tmp_path / record_rel
    destination.parent.mkdir(parents=True)
    destination.write_bytes(writes[record_rel])
    record = records.load_asset(destination)
    assert [source.path for source in record.sources] == ['src/swordcamp_masters.py', 'src/master_haze.py']
    for source in record.sources:
        data = writes[f'assets/master/swordcamp/camp/{source.path}']
        assert hashlib.sha256(data).hexdigest() == source.sha256
        assert data == (planner.BUILDERS / Path(source.path).name).read_bytes()


def test_a_changed_helper_changes_the_input_fingerprint(tmp_path, monkeypatch):
    family = dict(SWORD)
    builder_dir = tmp_path / 'builders'
    builder_dir.mkdir()
    for path in planner.builder_sources(family):
        (builder_dir / path.name).write_bytes(path.read_bytes())
    monkeypatch.setattr(planner, 'BUILDERS', builder_dir)
    record_path = tmp_path / 'asset.toml'

    def fingerprint():
        record_path.write_text(planner.record_text(family, family['masters'][0], planner.builder_sha(family)))
        return records.input_fingerprint(records.load_asset(record_path), {'texture/swordcamp/atlas': 'unchanged'})

    before = fingerprint()
    helper = builder_dir / 'master_haze.py'
    helper.write_text(helper.read_text().replace('900000.0', '800000.0'))
    assert fingerprint() != before


@pytest.mark.parametrize('helpers', [['swordcamp_masters.py'], ['../master_haze.py'], ['missing.py'], 'master_haze.py'])
def test_family_helpers_must_be_distinct_local_source_files(tmp_path, helpers):
    family = dict(SWORD, name='sample', helpers=helpers)
    (tmp_path / 'sample.py').write_text(f'FAMILY = {family!r}\n')
    with pytest.raises(planner.PlanError):
        planner.load_families(tmp_path)
