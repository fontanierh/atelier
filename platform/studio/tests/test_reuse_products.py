"""Whole-snapshot reuse through real inspector subprocesses, with tiny stand-in native files."""
import contextlib
import json
from pathlib import Path
import shutil

import pytest

from atelier import build, build_snapshot, cli, paths, reuse


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    source, target, engine = (tmp_path / name for name in ('source', 'target', 'engine'))
    shutil.copytree(paths.STUDIO / 'atelier', source / 'platform/studio/atelier',
                    ignore=shutil.ignore_patterns('__pycache__'))
    game = source / 'games/standin'
    write(game / 'game.toml', 'editor_target = "StandinEditor"\n')
    write(game / 'source.txt', 'source')
    write(game / 'unreal/Standin.uproject', '{}')
    write(game / 'build.py', '''from pathlib import Path
from atelier.build import Product, Step
from atelier import paths
def steps(ctx):
    native = ctx.uproject.parent / 'Content/Leaf.uasset'
    return [Step('export', [], inputs=[Path(__file__).with_name('source.txt')],
                 products=[Product('mesh', (ctx.out / 'mesh.json',))]),
            Step('import', [], inputs=[ctx.out / 'mesh.json'], reads=['mesh'],
                 products=[Product('native', (native,), optional_paths=(native.with_suffix('.ubulk'),))]),
            Step('map', [], references=['native'], products=[Product('map', (ctx.out / 'map.json',))],
                 optional_inputs=[ctx.out / 'optional.json', Path(__file__).with_name('optional-source.json')]),
            Step('plugin', [], inputs=[paths.REPO / 'platform/engine/Plugins/Fixture/Source'],
                 products=[Product('plugin', (paths.REPO / 'platform/engine/Plugins/Fixture/Binaries',))])]
''')
    write(source / 'platform/engine/Plugins/Fixture/Source/Type.h', 'declared source')
    shutil.copytree(source, target)
    write(engine / 'Engine/Build/Build.version', '{}')
    write(engine / 'Engine/Binaries/Mac/UnrealEditor.modules', '{"BuildId":"same"}')
    monkeypatch.setenv('UE_ROOT', str(engine))
    monkeypatch.delenv('ATELIER_BUILD_ROOT', raising=False)
    monkeypatch.setattr(reuse, 'render_lock', lambda *args: contextlib.nullcontext())
    monkeypatch.setattr(reuse, 'git', lambda repo, *args: 'revision' if args[0] == 'rev-parse' else '')
    monkeypatch.setattr(reuse, 'occupied', lambda *args: [])
    for name, content in [('libUnrealEditor-Standin.dylib', 'module'), ('StandinEditor.target', '{"Version":{}}'),
                          ('UnrealEditor.modules', '{"BuildId":"same"}')]:
        write(game / 'unreal/Binaries/Mac' / name, content)
    write(game / 'unreal/Content/Leaf.uasset', 'native leaf')
    write(source / 'build/standin/mesh.json', 'exported geometry')
    write(source / 'build/standin/map.json', 'path-only reference')
    write(source / 'build/standin/optional.json', 'copied optional input')
    write(source / 'platform/engine/Plugins/Fixture/Binaries/Mac/library.dylib', 'compiled plugin')
    for step in reuse.inspect(source, 'standin')['steps']:
        write(source / 'build/standin/stamps' / (step['name'] + '.json'),
              json.dumps({'fingerprint': step['fingerprint'], 'products': step['products']}))
    return source, target


def test_named_snapshot_clones_reads_references_and_optional_sidecars(snapshot):
    source, target = snapshot
    original = reuse.inspect(source, 'standin')
    assert reuse.differing_sources(original, reuse.inspect(target, 'standin')) == []
    assert reuse.main('standin', source, target) == 0
    verified = reuse.inspect(target, 'standin')
    assert reuse._inputs(verified) == reuse._inputs(original)
    assert reuse._products(verified) == reuse._products(original)
    assert all(s['stamp']['products'] == s['products'] for s in verified['steps'])
    out = target / 'build/standin'
    assert (out / build_snapshot.COMPLETE).is_file()
    assert not (out / build_snapshot.JOURNAL).exists()
    assert (target / 'platform/engine/Plugins/Fixture/Binaries/Mac/library.dylib').read_text() == 'compiled plugin'
    leaf = Path('games/standin/unreal/Content/Leaf.uasset')
    (target / leaf).write_text('changed copy')
    assert (source / leaf).read_text() == 'native leaf'


def test_reuse_source_identity_filters_only_copied_optional_inputs(snapshot):
    source, target = snapshot
    before, empty = reuse.inspect(source, 'standin'), reuse.inspect(target, 'standin')
    assert reuse.differing_sources(before, empty) == []
    source_map = next(step for step in before['steps'] if step['name'] == 'map')
    target_map = next(step for step in empty['steps'] if step['name'] == 'map')
    assert source_map['fingerprint'] != target_map['fingerprint']
    write(target / 'games/standin/optional-source.json', 'different source outside the copy')
    assert reuse.differing_sources(before, reuse.inspect(target, 'standin')) == ['map']
    with pytest.raises(ValueError, match='Source inputs differ'):
        reuse.main('standin', source, target)


@pytest.mark.parametrize('changed', ['leaf', 'sidecar', 'missing_source', 'source_difference'])
def test_bad_donor_or_different_source_cannot_start_copy(snapshot, changed):
    source, target = snapshot
    if changed == 'leaf':
        write(source / 'games/standin/unreal/Content/Leaf.uasset', 'corrupted')
    elif changed == 'sidecar':
        write(source / 'games/standin/unreal/Content/Leaf.ubulk', 'unexpected sidecar')
    elif changed == 'missing_source':
        (source / 'games/standin/source.txt').unlink()
    else:
        write(target / 'games/standin/source.txt', 'different untracked source')
    with pytest.raises(ValueError, match='not complete/current|Source inputs differ'):
        reuse.main('standin', source, target)
    assert not (target / 'games/standin/unreal/Content').exists()
    assert not (target / 'build/standin/stamps').exists()


@pytest.mark.parametrize('change', ['target_leaf', 'donor_leaf', 'interrupt'])
def test_interrupted_or_corrupt_copy_blocks_build_and_play(snapshot, monkeypatch, change):
    source, target = snapshot
    original = reuse.copy_tree

    def copy(src, dst, *args):
        original(src, dst, *args)
        if src.name == 'Leaf.uasset':
            if change == 'interrupt':
                raise OSError('interrupted')
            (src if change == 'donor_leaf' else dst).write_text('changed during copy')

    monkeypatch.setattr(reuse, 'copy_tree', copy)
    with pytest.raises((ValueError, OSError), match='Products changed|interrupted'):
        reuse.main('standin', source, target)
    out = target / 'build/standin'
    assert (out / build_snapshot.JOURNAL).exists()
    assert not (out / 'stamps').exists()
    monkeypatch.setattr(paths, 'build_root', lambda: target / 'build')
    monkeypatch.setattr(cli, 'Context', lambda game: type('Context', (), {'out': out})())
    with pytest.raises(SystemExit, match='--abandon'):
        build.build('standin')
    with pytest.raises(SystemExit, match='--abandon'):
        cli.play('standin', 'default', None, [])


def test_registry_cache_in_target_requires_a_fresh_checkout(snapshot):
    source, target = snapshot
    write(target / 'games/standin/unreal/Intermediate/CachedAssetRegistry.bin', 'stale registry')
    with pytest.raises(ValueError, match='registry discovery'):
        reuse.main('standin', source, target)
    assert not (target / 'games/standin/unreal/Content').exists()


def test_supported_abandon_keeps_tracked_assets_logs_and_unrelated_files(snapshot, monkeypatch):
    import subprocess
    source, target = snapshot
    original = reuse.copy_tree

    def interrupt(src, dst, *args):
        original(src, dst, *args)
        if src.name == 'Content':
            raise OSError('interrupted')

    monkeypatch.setattr(reuse, 'copy_tree', interrupt)
    with pytest.raises(OSError, match='interrupted'):
        reuse.main('standin', source, target)
    kept = target / 'games/standin/unreal/Content/Kept.uasset'
    write(kept, 'authored tracked asset')
    subprocess.run(['git', '-C', str(target), 'init', '-q'], check=True)
    subprocess.run(['git', '-C', str(target), 'add', str(kept)], check=True)
    write(target / 'build/standin/logs/copy.log', 'diagnostic evidence')
    write(target / 'notes.txt', 'unrelated work')
    assert reuse.abandon('standin', target) == 0
    assert kept.read_text() == 'authored tracked asset'
    assert (target / 'build/standin/logs/copy.log').is_file()
    assert (target / 'notes.txt').read_text() == 'unrelated work'
    assert not (target / 'games/standin/unreal/Content/Leaf.uasset').exists()
    assert not (target / 'build/standin/mesh.json').exists()
    assert not (target / 'build/standin' / build_snapshot.JOURNAL).exists()


@pytest.mark.parametrize('relative', ['../outside', 'build/standin/../../outside', 'games/standin/source.txt',
                                    'build/standin/.reuse-in-progress.json', 'build/standin/logs'])
def test_abandon_refuses_unsafe_scope_before_removing_anything(tmp_path, monkeypatch, relative):
    journal = tmp_path / 'build/standin' / build_snapshot.JOURNAL
    write(journal, json.dumps({'schema': 1, 'copies': ['build/standin/mesh.json', relative]}))
    write(tmp_path / 'build/standin/mesh.json', 'keep on refused cleanup')
    monkeypatch.setattr(reuse, 'render_lock', lambda *args: contextlib.nullcontext())
    with pytest.raises(SystemExit, match='Unsafe path'):
        reuse.abandon('standin', tmp_path)
    assert journal.exists()
    assert (tmp_path / 'build/standin/mesh.json').exists()


def test_direct_native_launcher_refuses_partial_snapshot_before_spawning(tmp_path, monkeypatch):
    from atelier.safety import process
    project = tmp_path / 'games/standin/unreal/Standin.uproject'
    write(project, '{}')
    write(tmp_path / 'build/standin' / build_snapshot.JOURNAL, '{}')
    monkeypatch.setattr(process.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not launch'))
    for argv in (['editor', str(project)], ['uat', '-project=' + str(project)]):
        with pytest.raises(SystemExit, match='--abandon'):
            process.spawn(argv, env={})
