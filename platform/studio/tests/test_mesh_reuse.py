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
        return SimpleNamespace(returncode=0, stdout=revision + '\n' if args[1] == 'log' else source.encode())
    monkeypatch.setattr(reuse.subprocess, 'run', git)
    raw = source.encode()
    old = hashlib.sha256(b'import_mesh.py' + raw).hexdigest()
    named = reuse.identity({'schema': 1, 'files': {'0/.': {
        'kind': 'file', 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}})
    assert reuse.saved_source(tmp_path, 'import_mesh.py', old) == source
    assert reuse.saved_source(tmp_path, 'import_mesh.py', named) == source
    assert reuse.saved_source(tmp_path, 'import_mesh.py', 'f' * 64) is None


def pending_fixture(tmp_path, monkeypatch):
    from atelier import native_protocol
    ctx = SimpleNamespace(out=tmp_path / 'build', uproject=tmp_path / 'game/unreal/Game.uproject')
    ctx.out.mkdir(); ctx.uproject.parent.mkdir(parents=True)
    source = ctx.out / 'source.glb'; source.write_bytes(b'original source')
    package = ctx.uproject.parent / 'Content/Region/Mesh.uasset'
    package.parent.mkdir(parents=True); package.write_bytes(b'geometry before finishing')
    current = {'engine': 'engine', 'sdk': 'sdk'}
    monkeypatch.setattr(native_protocol, 'context', lambda _: current)
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


@pytest.mark.parametrize('misses', [None, [], {'source': True}, {'source': -1}, {'path/to/source': 1}])
def test_parent_refuses_malformed_miss_diagnostics_before_receipt_publication(tmp_path, monkeypatch, misses):
    ctx, nonce, _, _, _ = pending_fixture(tmp_path, monkeypatch)
    path = reuse.pending_path(ctx, 'unreal.region', nonce)
    packet = json.loads(path.read_text())
    packet['miss_reasons'] = misses
    path.write_text(json.dumps(packet))
    with pytest.raises(ValueError, match='miss diagnostics'):
        reuse.finalize_pending(ctx, 'unreal.region', nonce)
    assert path.exists()
    assert not (ctx.out / 'native-imports/unreal.region/meshes.json').exists()
    assert not (ctx.out / 'native-imports/unreal.region/summary.json').exists()


@pytest.mark.parametrize('before,after', [
    ("T = {}; T.update({'b': 2})\ndef build(): return T\n", "T = {}; T.update({'b': 3})\ndef build(): return T\n"),
    ('N=100; N+=1\ndef build(): return N\n', 'N=100; N+=5\ndef build(): return N\n'),
    ('for K in [1]: pass\ndef build(): return K\n', 'for K in [2]: pass\ndef build(): return K\n')])
def test_policy_covers_global_mutation_and_control_bindings(before, after):
    assert reuse.policy(before, ('build',)) != reuse.policy(after, ('build',))


def test_native_policy_binds_local_helper_bytes(tmp_path, monkeypatch):
    from atelier import paths
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    script = tmp_path / 'importer.py'
    script.write_text('from kit import box\ndef build(): return box()\n')
    helper = tmp_path / 'kit.py'; helper.write_text('def box(): return 1\n')
    first = reuse.native_policy(script.read_text(), ('build',), script)
    helper.write_text('def box(): return 2\n')
    assert reuse.native_policy(script.read_text(), ('build',), script) != first
    with pytest.raises(ValueError, match='historical geometry support'):
        reuse.native_policy(script.read_text(), ('build',), script, inputs={})


def test_prior_stamp_is_bound_to_owner_nonce_root_and_type(tmp_path):
    ctx = SimpleNamespace(out=tmp_path)
    nonce = 'a' * 24
    path = tmp_path / '.state/mesh-import-prior/unreal.region' / (nonce + '.json')
    path.parent.mkdir(parents=True)
    packet = dict(schema=1, task='unreal.region', nonce=nonce, stamp={'fingerprint': 'b' * 64})
    path.write_text(json.dumps(packet))
    assert reuse.prior_stamp(ctx, 'unreal.region', nonce, str(path)) == packet['stamp']
    assert reuse.prior_stamp(ctx, 'unreal.region', 'c' * 24, str(path)) is None
    assert reuse.prior_stamp(ctx, 'unreal.other', nonce, str(path)) is None
    for bad in (None, [], dict(packet, stamp=[])):
        path.write_text(json.dumps(bad))
        assert reuse.prior_stamp(ctx, 'unreal.region', nonce, str(path)) is None


@pytest.mark.parametrize('bad', [None, [], {'meshes': []}, {'meshes': {'Mesh': []}}])
def test_malformed_optional_receipts_are_misses(tmp_path, bad):
    path = tmp_path / 'build/native-imports/task/meshes.json'; path.parent.mkdir(parents=True)
    path.write_text(json.dumps(bad))
    book = reuse.Receipts(tmp_path / 'build', 'task', {}, 'policy', tmp_path / 'Content')
    assert not book.matches('Mesh', 'key', ['/Game/Mesh'])


def test_preinventory_compatibility_refuses_package_saved_after_success(tmp_path):
    import os
    ctx = SimpleNamespace(uproject=tmp_path / 'game/unreal/Game.uproject')
    file = ctx.uproject.parent / 'Content/Region/Mesh.uasset'
    file.parent.mkdir(parents=True); file.write_bytes(b'old imported bytes')
    os.utime(file, (100, 100))
    finished = file.stat().st_ctime
    assert reuse.historical_packages_match(ctx, 'unreal.region', {'time': finished}, ['/Game/Region/Mesh'])
    file.write_bytes(b'later vertex edits retaining import-data MD5')
    os.utime(file, (100, 100))  # copying/restoring old mtimes cannot restore continuity
    assert not reuse.historical_packages_match(ctx, 'unreal.region', {'time': finished}, ['/Game/Region/Mesh'])


@pytest.fixture
def selected_without_inventory(tmp_path, monkeypatch):
    from atelier.native_protocol import ReadStore
    ctx = SimpleNamespace(game='fixture', uproject=tmp_path / 'game/unreal/Game.uproject')
    file = ctx.uproject.parent / 'Content/Region/Mesh.uasset'
    file.parent.mkdir(parents=True)
    file.write_bytes(b'current source/options already validated by native caller')
    store = ReadStore(ctx.game, tmp_path / 'store')
    monkeypatch.setattr(reuse, 'ReadStore', lambda game: store)
    # Ordinary build records the selected tool key even when the task has no
    # complete output scope and therefore cannot publish an action inventory.
    stamp = {'checkpoint_key': 'a' * 64, 'time': max(file.stat().st_ctime, file.stat().st_mtime),
             'fingerprint': 'b' * 64}
    return ctx, file, store, stamp


def test_tool_selection_key_does_not_disable_preinventory_continuity(selected_without_inventory):
    ctx, _, store, stamp = selected_without_inventory
    assert reuse.historical_packages_match(ctx, 'unreal.region', stamp, ['/Game/Region/Mesh'])
    assert not store.directory.exists()  # The native readback never initializes store metadata.


def test_selection_only_still_refuses_later_package_writes(selected_without_inventory):
    import os
    ctx, file, _, stamp = selected_without_inventory
    file.write_bytes(b'later geometry modification')
    os.utime(file, (100, 100))
    assert not reuse.historical_packages_match(ctx, 'unreal.region', stamp, ['/Game/Region/Mesh'])


def test_complete_stored_proof_still_matches_actual_bytes(selected_without_inventory):
    from atelier.native_protocol import inventory_identity
    ctx, file, store, old = selected_without_inventory
    member = 'content/Region/Mesh.uasset'
    info = file.stat()
    files = {member: dict(kind='file', mode=info.st_mode & 0o777, mtime_ns=info.st_mtime_ns,
                          size=info.st_size, sha256=reuse.digest(file))}
    roots = [dict(path=member, kind='file')]
    stamp = dict(old, checkpoint_inventory=inventory_identity(roots, files))
    value = dict(schema=1, game=ctx.game, key=stamp['checkpoint_key'], roots=roots, files=files,
                 stamp=stamp, fingerprint=stamp['fingerprint'], task='unreal.region')
    target = reuse.entry_path(store, stamp['checkpoint_key'])
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(value))
    assert reuse.historical_packages_match(ctx, 'unreal.region', stamp, ['/Game/Region/Mesh'])
    file.write_bytes(b'different geometry')
    assert not reuse.historical_packages_match(ctx, 'unreal.region', stamp, ['/Game/Region/Mesh'])


def test_new_sidecar_is_not_continuous_preinventory_state(selected_without_inventory):
    ctx, file, _, stamp = selected_without_inventory
    file.with_suffix('.ubulk').write_bytes(b'new sidecar')
    assert not reuse.historical_packages_match(ctx, 'unreal.region', stamp, ['/Game/Region/Mesh'])


@pytest.mark.parametrize('inventory', [None, '', 'c' * 64, {}])
def test_explicit_output_proof_never_downgrades_to_timestamp_compatibility(selected_without_inventory, inventory):
    ctx, _, _, stamp = selected_without_inventory
    assert not reuse.historical_packages_match(ctx, 'unreal.region', dict(stamp, checkpoint_inventory=inventory),
                                               ['/Game/Region/Mesh'])


@pytest.mark.parametrize('evidence', ['action', 'conflict', 'linked-action', 'linked-conflict'])
def test_existing_or_conflicted_action_never_downgrades_to_timestamps(selected_without_inventory, evidence):
    ctx, _, store, stamp = selected_without_inventory
    target = reuse.entry_path(store, stamp['checkpoint_key'])
    if 'conflict' in evidence:
        target = target.with_suffix('.conflict')
    target.parent.mkdir(parents=True)
    if evidence.startswith('linked-'):
        target.symlink_to(target.parent / 'absent')
    else:
        target.write_text('{}')
    assert not reuse.historical_packages_match(ctx, 'unreal.region', stamp, ['/Game/Region/Mesh'])


@pytest.mark.parametrize('key', ['', 0, 'not-a-key'])
def test_invalid_selection_key_is_not_preinventory_evidence(selected_without_inventory, key):
    ctx, _, _, stamp = selected_without_inventory
    assert not reuse.historical_packages_match(ctx, 'unreal.region', dict(stamp, checkpoint_key=key),
                                               ['/Game/Region/Mesh'])


@pytest.mark.parametrize('call', ['s()', 'if True:\n s()', 'for _ in range(1):\n s()', 'result=s()'])
def test_policy_refuses_dynamic_module_initialization_through_function(call):
    with pytest.raises(ValueError, match='Dynamic module initialization'):
        reuse.policy("T={}\ndef s(): T['a']=1\n" + call + "\ndef build(): return T\n", ('build',))


def test_known_prior_environment_cannot_become_unknown(tmp_path):
    ctx = SimpleNamespace(out=tmp_path); nonce = 'f' * 24
    target = tmp_path / '.state/mesh-import-prior/task' / (nonce + '.json')
    target.parent.mkdir(parents=True)
    packet = dict(schema=1, task='task', nonce=nonce,
                  stamp={'checkpoint_incremental_context': 'a' * 64})
    for observed in (None, 'b' * 64, 'a' * 64):
        packet['observed_context'] = observed; target.write_text(json.dumps(packet))
        assert (reuse.prior_stamp(ctx, 'task', nonce, str(target)) is not None) == (observed == 'a' * 64)


@pytest.mark.parametrize('definition', [
    "class Setup:\n T.update({'a':1})",
    'def other(x=s()): pass',
    'def other(x:s()): pass',
    '@s()\ndef other(): pass'])
def test_policy_refuses_definition_time_execution(definition):
    with pytest.raises(ValueError, match='initialization|definition expressions'):
        reuse.policy("T={}\ndef s(): T['a']=1\n" + definition + '\ndef build(): return T\n', ('build',))


def test_platform_support_source_resolves_read_only_and_detects_changed_bytes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from atelier import paths
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    ctx = SimpleNamespace(out=tmp_path / 'build/game', uproject=tmp_path / 'games/game/unreal/Game.uproject')
    support = tmp_path / 'platform/support.py'; support.parent.mkdir(); support.write_text('SETTING=1\n')
    member = reuse.source_member(ctx, support)
    assert member == 'repo/platform/support.py'
    assert reuse.resolve_source(ctx, member) == support
    support.unlink(); support.symlink_to(tmp_path / 'missing')
    with pytest.raises(ValueError):
        reuse.resolve_source(ctx, member)


@pytest.mark.parametrize('algorithm', ['legacy', 'merkle'])
def test_saved_source_can_recover_exact_producing_bytes_from_another_local_branch(tmp_path, algorithm):
    import subprocess
    def git(*args):
        return subprocess.check_output(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',*args],
                                       cwd=tmp_path,text=True).strip()
    git('init','-q')
    file = tmp_path/'owner.py'
    file.write_text('BASE = True\n')
    git('add','owner.py'); git('commit','-qm','base')
    base = git('rev-parse','HEAD')
    original = 'raise RuntimeError("Historical bytes must never execute")\n'
    raw = original.encode()
    key = hashlib.sha256(b'owner.py'+raw).hexdigest() if algorithm == 'legacy' else reuse.identity(
        {'schema':1,'files':{'0/.':{'kind':'file','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}})
    assert reuse.saved_source(tmp_path,'owner.py',key) is None
    git('checkout','-qb','producing-evidence')
    file.write_text(original)
    git('commit','-qam','original producer source')
    producing = git('rev-parse','HEAD')
    git('checkout','-qb','receiving',base)
    file.write_text('CURRENT = True\n'); git('commit','-qam','current source')
    assert subprocess.run(['git','merge-base','--is-ancestor',producing,'HEAD'],cwd=tmp_path).returncode == 1
    assert reuse.saved_source(tmp_path,'owner.py',key) == original
    assert reuse.saved_source(tmp_path,'owner.py','f'*64) is None
    assert file.read_text() == 'CURRENT = True\n'


def test_local_ref_fallback_deduplicates_and_limits_additional_source_reads(monkeypatch, tmp_path):
    heads = [f'{n:040x}' for n in range(2)]
    extras = [f'{n:040x}' for n in range(2,130)]
    reads = []
    def git(args, **kwargs):
        assert args[1] == 'log' and kwargs['timeout'] <= 10
        rows = [*heads,heads[0],'invalid',*extras] if '--all' in args else heads
        return SimpleNamespace(returncode=0,stdout='\n'.join(rows))
    monkeypatch.setattr(reuse.subprocess,'run',git)
    monkeypatch.setattr(reuse.time,'monotonic',lambda:0.)
    monkeypatch.setattr(reuse,'revision_source',lambda repo,revision,name,**kwargs: reads.append(revision) or 'different')
    assert reuse.saved_source(tmp_path,'owner.py','f'*64) is None
    assert reads[:2] == heads and len(reads) == 66 and len(set(reads)) == 66


def test_local_ref_fallback_has_one_total_time_budget(monkeypatch, tmp_path):
    clock = iter([0.,0.,0.,11.])
    monkeypatch.setattr(reuse.time,'monotonic',lambda:next(clock))
    monkeypatch.setattr(reuse.subprocess,'run',lambda args,**kwargs: SimpleNamespace(returncode=0,
        stdout='\n'.join(f'{i:040x}' for i in range(100)) if '--all' in args else ''))
    reads = []
    def read(repo,revision,name,**kwargs):
        assert 0 < kwargs['timeout'] <= 10
        reads.append(revision)
        return 'different'
    monkeypatch.setattr(reuse,'revision_source',read)
    assert reuse.saved_source(tmp_path,'owner.py','f'*64) is None
    assert len(reads) == 2
