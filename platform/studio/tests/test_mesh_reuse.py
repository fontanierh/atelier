import hashlib
import json
from types import SimpleNamespace

import pytest

from atelier import mesh_reuse as reuse
from atelier.checkpoint_store import CheckpointError


def test_geometry_policy_tracks_options_helpers_and_global_values_without_finishing_code():
    source = '''
SCALE = 100
def helper(x): return x * SCALE
def import_mesh(x): return helper(x)
def finish(x): return x
'''
    expected = reuse.policy(source, ('import_mesh',))
    assert reuse.policy(source.replace('return x\n', 'return x + 1\n'), ('import_mesh',)) == expected
    assert reuse.policy(source + '\n# authoring comment\n', ('import_mesh',)) == expected
    assert reuse.policy(source.replace('SCALE = 100', 'SCALE = 1'), ('import_mesh',)) != expected
    assert reuse.policy(source.replace('x * SCALE', 'x / SCALE'), ('import_mesh',)) != expected
    with pytest.raises(ValueError, match='missing'):
        reuse.policy(source, ('unknown',))
    with pytest.raises(ValueError, match='Ambiguous'):
        reuse.policy(source + '\nSCALE = 2\n', ('import_mesh',))


def test_geometry_policy_covers_conditional_global_bindings():
    source = 'if enabled:\n SCALE = 100\nelse:\n SCALE = 1\ndef build(x): return x * SCALE\n'
    assert reuse.policy(source, ('build',)) != reuse.policy(source.replace('100', '200'), ('build',))


def test_source_hash_is_actual_imported_file_not_just_matching_report(tmp_path):
    source = tmp_path / 'mesh.glb'
    source.write_bytes(b'original geometry')
    tag = json.dumps([{'FileMD5': hashlib.md5(source.read_bytes()).hexdigest()}])
    assert reuse.recorded_source_matches(tag, source)
    source.write_bytes(b'changed geometry!')
    assert not reuse.recorded_source_matches(tag, source)


@pytest.mark.parametrize('tag', [None, '', '{}', '[]', '[{}]',
    '[{"FileMD5":"00000000000000000000000000000000"}]',
    '[{"FileMD5":"wrong"}]', '[{},{}]'])
def test_missing_unknown_or_multiple_import_sources_are_misses(tmp_path, tag):
    source = tmp_path / 'mesh.glb'; source.write_bytes(b'geometry')
    assert not reuse.recorded_source_matches(tag, source)


def test_receipt_binds_complete_sidecars_context_policy_and_validation(tmp_path):
    content = tmp_path / 'Content'; package = content / 'Region/Mesh'
    package.parent.mkdir(parents=True)
    package.with_suffix('.uasset').write_bytes(b'mesh')
    package.with_suffix('.ubulk').write_bytes(b'bulk')
    context = {'engine': 'same installed engine', 'sdk': 'same sdk'}
    book = reuse.Receipts(tmp_path / 'build', 'unreal.region', context, 'geometry-policy', content)
    key = reuse.identity({'source': 'source-sha256', 'collision': 'hull-sha256'})
    with pytest.raises(ValueError, match='captured candidate'):
        book.record('Mesh', key, ['/Game/Region/Mesh'], evidence='compatibility-only')
    book.record('Mesh', key, ['/Game/Region/Mesh'], evidence='current-native-validation')
    assert book.matches('Mesh', key, ['/Game/Region/Mesh'])
    assert not reuse.Receipts(tmp_path / 'build', 'unreal.region', {'engine': 'changed'},
                              'geometry-policy', content).matches('Mesh', key, ['/Game/Region/Mesh'])
    assert not reuse.Receipts(tmp_path / 'build', 'unreal.region', context,
                              'changed-policy', content).matches('Mesh', key, ['/Game/Region/Mesh'])
    package.with_suffix('.uexp').write_bytes(b'new sidecar')
    assert not book.matches('Mesh', key, ['/Game/Region/Mesh'])
    package.with_suffix('.uexp').unlink()
    package.with_suffix('.ubulk').write_bytes(b'other bulk')
    assert not book.matches('Mesh', key, ['/Game/Region/Mesh'])
    package.with_suffix('.ubulk').unlink()
    assert not book.matches('Mesh', key, ['/Game/Region/Mesh'])


def test_package_scope_cannot_escape_content_or_follow_linked_outputs(tmp_path):
    with pytest.raises(ValueError):
        reuse.package_members('/Engine/Mesh')
    with pytest.raises(CheckpointError):
        reuse.package_members('/Game/../source')
    target = tmp_path / 'outside'; target.write_bytes(b'outside')
    content = tmp_path / 'Content'; content.mkdir()
    (content / 'Mesh.uasset').symlink_to(target)
    with pytest.raises(ValueError, match='Linked'):
        reuse.package_inventory(content, ['/Game/Mesh'])


def test_saved_input_identity_recovers_named_and_legacy_history_without_execution(monkeypatch, tmp_path):
    source = 'raise RuntimeError("donor code must never execute")\n'
    revision = 'a' * 40
    def git(args, **kwargs):
        assert not kwargs.get('shell')
        return SimpleNamespace(returncode=0, stdout=revision + '\n' if args[1] == 'log' else source)
    monkeypatch.setattr(reuse.subprocess, 'run', git)
    raw = source.encode()
    old = hashlib.sha256(b'import_mesh.py' + raw).hexdigest()
    named = reuse.identity({'schema': 1, 'files': {'0/.': {
        'kind': 'file', 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}})
    assert reuse.saved_source(tmp_path, 'import_mesh.py', old) == source
    assert reuse.saved_source(tmp_path, 'import_mesh.py', named) == source
    assert reuse.saved_source(tmp_path, 'import_mesh.py', 'f' * 64) is None


def pending_fixture(tmp_path, monkeypatch):
    from atelier import checkpoint_store
    ctx = SimpleNamespace(out=tmp_path / 'build', uproject=tmp_path / 'game/unreal/Game.uproject')
    ctx.out.mkdir(); ctx.uproject.parent.mkdir(parents=True)
    source = ctx.out / 'source.glb'; source.write_bytes(b'original source')
    package = ctx.uproject.parent / 'Content/Region/Mesh.uasset'
    package.parent.mkdir(parents=True); package.write_bytes(b'geometry before finishing')
    current = {'engine': 'engine', 'sdk': 'sdk'}
    monkeypatch.setattr(checkpoint_store, 'context', lambda _: current)
    nonce = 'a' * 24
    record = dict(key='b' * 64, packages=['/Game/Region/Mesh'], native_source_validated=True,
                  provenance={'kind': 'compatibility-only', 'historical_task': 'c' * 64},
                  sources=[dict(package='/Game/Region/Mesh', member='generated/source.glb', sha256=reuse.digest(source))])
    reuse.queue_pending(ctx, 'unreal.region', nonce, 'd' * 64, current, 'Mesh', record,
                        dict(reused_local=1, reused_candidate=0, imported=0))
    return ctx, nonce, current, source, package


def test_successful_parent_finalizes_final_bytes_not_early_native_geometry(tmp_path, monkeypatch):
    ctx, nonce, current, source, package = pending_fixture(tmp_path, monkeypatch)
    receipt = ctx.out / 'native-imports/unreal.region/meshes.json'
    assert not receipt.exists()
    package.write_bytes(b'after material/role/collision finishing and saves')
    reuse.finalize_pending(ctx, 'unreal.region', 'e' * 24)  # another child cannot finalize it
    assert not receipt.exists()
    reuse.finalize_pending(ctx, 'unreal.region', nonce)
    saved = json.loads(receipt.read_text())
    row = saved['meshes']['Mesh']
    assert row['packages']['content/Region/Mesh.uasset']['sha256'] == reuse.digest(package)
    assert row['provenance']['kind'] == 'compatibility-only'
    assert not reuse.pending_path(ctx, 'unreal.region', nonce).exists()
    assert not (ctx.out / 'stamps/unreal.region.json').exists()


@pytest.mark.parametrize('change', ['source', 'engine', 'nonce', 'proof'])
def test_parent_refuses_changed_or_unproved_pending_geometry(tmp_path, monkeypatch, change):
    ctx, nonce, current, source, package = pending_fixture(tmp_path, monkeypatch)
    if change == 'source': source.write_bytes(b'changed')
    if change == 'engine': current['sdk'] = 'changed sdk'
    if change in ('nonce', 'proof'):
        path = reuse.pending_path(ctx, 'unreal.region', nonce); packet = json.loads(path.read_text())
        if change == 'nonce': packet['nonce'] = 'e' * 24
        else: packet['entries']['Mesh']['native_source_validated'] = False
        path.write_text(json.dumps(packet))
    with pytest.raises(ValueError):
        reuse.finalize_pending(ctx, 'unreal.region', nonce)
    assert not (ctx.out / 'native-imports/unreal.region/meshes.json').exists()
