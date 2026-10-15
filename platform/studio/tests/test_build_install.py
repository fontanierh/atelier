"""Offline transaction foundation: temporary typed packages, never native packages or caches."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from atelier import build_install as install, build_snapshot


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / 'repo'
    unreal = repo / 'games' / 'fixture' / 'unreal'
    unreal.mkdir(parents=True)
    (unreal / 'Fixture.uproject').write_text(json.dumps(dict(schema=1, backend=install.BACKEND)))
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    return install.Scope(repo, 'fixture')


def source(tmp_path, packages, *, label='source'):
    root = tmp_path / label
    root.mkdir()
    records = []
    for name, refs, sidecars in packages:
        relative = name.removeprefix('/Game/')
        primary = root / (relative + '.uasset')
        primary.parent.mkdir(parents=True, exist_ok=True)
        primary.write_text(json.dumps(dict(schema=1, backend=install.BACKEND, package=name, references=refs)))
        leaves = [primary]
        for suffix, data in sidecars.items():
            path = root / (relative + suffix)
            path.write_bytes(data)
            leaves.append(path)
        records.append(dict(name=name, owner='fixture.action', references=refs,
            files=[dict(path=path.relative_to(root).as_posix(), size=path.stat().st_size,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in leaves]))
    names = {item['name'] for item in records}
    plan = dict(schema=1, backend=install.BACKEND, packages=records,
                external_references=sorted({ref for _, refs, _ in packages for ref in refs if ref not in names}))
    return root, plan


def run(scope, root, plan):
    return install._execute(scope, plan, root)


def test_fresh_complete_install_uses_bound_registry_and_durable_owner_manifest(project, tmp_path):
    root, plan = source(tmp_path, [('/Game/Mesh/One', [], {'.uexp': b'payload'})])
    result = run(project, root, plan)
    assert result['snapshot'] == plan
    assert not project.journal.exists()
    assert (project.content / 'Mesh/One.uexp').read_bytes() == b'payload'
    receipt = install._read(project.receipt)
    assert receipt['registry']['nonce'] == result['transaction']
    assert '/Game/Mesh/One' in receipt['registry']['packages']
    assert receipt['registry']['child'][0] != receipt['registry']['parent'][0]


def test_update_keeps_unchanged_leaf_identity_and_retires_exact_sidecars(project, tmp_path):
    root, first = source(tmp_path, [('/Game/One', [], {'.uexp': b'old', '.ubulk': b'bulk'}),
                                    ('/Game/Retired', [], {})])
    run(project, root, first)
    unchanged = (project.content / 'One.uasset').stat().st_ino
    root, second = source(tmp_path, [('/Game/One', [], {'.uexp': b'new'})], label='second')
    run(project, root, second)
    assert (project.content / 'One.uasset').stat().st_ino == unchanged
    assert (project.content / 'One.uexp').read_bytes() == b'new'
    assert not (project.content / 'One.ubulk').exists()
    assert not (project.content / 'Retired.uasset').exists()


def test_initial_empty_ownership_cannot_adopt_existing_files(project, tmp_path):
    root, plan = source(tmp_path, [('/Game/One', [], {})])
    project.content.mkdir()
    original = root / 'One.uasset'
    target = project.content / 'One.uasset'
    target.write_bytes(original.read_bytes())
    with pytest.raises(install.InstallError, match='unowned'):
        run(project, root, plan)
    assert target.read_bytes() == original.read_bytes() and not project.journal.exists()


def test_authored_unrelated_files_stay_untouched(project, tmp_path):
    project.content.mkdir()
    authored = project.content / 'notes.txt'
    authored.write_text('authored')
    before = authored.stat().st_ino
    root, plan = source(tmp_path, [('/Game/One', [], {})])
    run(project, root, plan)
    assert authored.read_text() == 'authored' and authored.stat().st_ino == before


def test_git_tracked_content_is_never_replaced(project, tmp_path):
    root, plan = source(tmp_path, [('/Game/One', [], {})])
    project.content.mkdir()
    target = project.content / 'One.uasset'
    target.write_bytes((root / 'One.uasset').read_bytes())
    subprocess.run(['git', '-C', str(project.repo), 'add', 'games'], check=True)
    with pytest.raises(install.InstallError, match='Git-tracked'):
        run(project, root, plan)


@pytest.mark.parametrize('change', ['size', 'hash', 'missing', 'extra', 'symlink', 'hardlink'])
def test_invalid_sources_never_mutate_content(project, tmp_path, change):
    root, plan = source(tmp_path, [('/Game/One', [], {})])
    leaf = root / 'One.uasset'
    if change == 'size':
        plan['packages'][0]['files'][0]['size'] += 1
    elif change == 'hash':
        plan['packages'][0]['files'][0]['sha256'] = '0' * 64
    elif change == 'missing':
        leaf.unlink()
    elif change == 'extra':
        (root / 'extra').write_text('unlisted')
    elif change == 'symlink':
        moved = tmp_path / 'original'
        leaf.rename(moved)
        leaf.symlink_to(moved)
    else:
        import os
        os.link(leaf, tmp_path / 'linked')
    with pytest.raises((install.InstallError, OSError)):
        run(project, root, plan)
    assert not project.content.exists() and not project.journal.exists()


def test_native_backend_and_native_project_refuse_before_mutation(project, tmp_path):
    root, plan = source(tmp_path, [('/Game/One', [], {})])
    native = copy.deepcopy(plan)
    native['backend'] = 'unreal'
    with pytest.raises(install.InstallError, match='no validated backend'):
        run(project, root, native)
    (project.project / 'Fixture.uproject').write_text('{"FileVersion":3,"EngineAssociation":"5.8"}')
    with pytest.raises(install.InstallError, match='native hydration is disabled'):
        run(project, root, plan)
    assert not project.content.exists()


def test_reference_to_retired_generated_package_cannot_be_called_external(project, tmp_path):
    root, plan = source(tmp_path, [('/Game/One', [], {}), ('/Game/Two', ['/Game/One'], {})])
    run(project, root, plan)
    root, plan = source(tmp_path, [('/Game/Two', ['/Game/One'], {})], label='second')
    with pytest.raises(install.InstallError, match='retired generated'):
        run(project, root, plan)
    assert (project.content / 'One.uasset').exists()


def test_package_journal_blocks_default_even_with_override(project, tmp_path):
    project.journal.write_text('{}')
    with pytest.raises(SystemExit, match='registry readiness'):
        build_snapshot.require_complete(tmp_path / 'alternate' / 'fixture', game='fixture', repo=project.repo)
    with pytest.raises(SystemExit, match='registry readiness'):
        build_snapshot.require_launch(['launcher', str(project.project / 'Fixture.uproject')], env={})


class Interrupted(RuntimeError):
    pass


def interrupt_after_content_mutation(monkeypatch, scope, at):
    count = [0]
    def record(path):
        if path == scope.content or path.is_relative_to(scope.content):
            count[0] += 1
            if count[0] == at:
                raise Interrupted('simulated interruption after destination mutation')
    move, retire = install._move_prepared, install._retire_owned
    def moved(scope, candidate, relative, *args, **kwargs):
        result = move(scope, candidate, relative, *args, **kwargs)
        record(scope.content / relative)
        return result
    def retired(scope, relative, *args, **kwargs):
        result = retire(scope, relative, *args, **kwargs)
        record(scope.content / relative)
        return result
    monkeypatch.setattr(install, '_move_prepared', moved)
    monkeypatch.setattr(install, '_retire_owned', retired)


@pytest.mark.parametrize('at', range(1, 6))
def test_recover_forward_after_each_initial_directory_or_leaf_mutation(project, tmp_path, monkeypatch, at):
    root, plan = source(tmp_path, [('/Game/Mesh/Sub/One', [], {'.uexp': b'bytes'})])
    with monkeypatch.context() as edits:
        interrupt_after_content_mutation(edits, project, at)
        with pytest.raises(Interrupted):
            run(project, root, plan)
    assert project.journal.exists()
    (root / 'Mesh/Sub/One.uasset').unlink()
    (root / 'Mesh/Sub/One.uexp').unlink()
    result = install._execute(install.Scope(project.repo, project.game), resume=True)
    assert result['snapshot'] == plan and not project.journal.exists()
    assert (project.content / 'Mesh/Sub/One.uexp').read_bytes() == b'bytes'


@pytest.mark.parametrize('at', range(1, 4))
def test_recover_forward_after_each_replacement_or_retirement(project, tmp_path, monkeypatch, at):
    root, plan = source(tmp_path, [('/Game/One', [], {'.uexp': b'old', '.ubulk': b'old'}),
                                  ('/Game/Retired', [], {})])
    run(project, root, plan)
    identity = (project.content / 'One.uasset').stat().st_ino
    root, plan = source(tmp_path, [('/Game/One', [], {'.uexp': b'new'})], label='second')
    with monkeypatch.context() as edits:
        interrupt_after_content_mutation(edits, project, at)
        with pytest.raises(Interrupted):
            run(project, root, plan)
    assert project.journal.exists()
    install._execute(install.Scope(project.repo, project.game), resume=True)
    assert not project.journal.exists()
    assert (project.content / 'One.uasset').stat().st_ino == identity
    assert (project.content / 'One.uexp').read_bytes() == b'new'
    assert not (project.content / 'One.ubulk').exists() and not (project.content / 'Retired.uasset').exists()


@pytest.mark.parametrize('failure', ['false', 'nonce', 'inventory', 'retired', 'stale'])
def test_registry_failure_keeps_launch_barrier_and_durable_stage(project, tmp_path, monkeypatch, failure):
    root, plan = source(tmp_path, [('/Game/One', [], {})])
    original = install._query_registry
    def query(scope, value):
        result = original(scope, value)
        if failure == 'false':
            return True
        if failure == 'nonce':
            result['nonce'] = '0' * 32
        elif failure == 'inventory':
            result['packages']['/Game/One']['files'] = {}
        elif failure == 'retired':
            result['packages'] = {}
        else:
            result['observed_monotonic'] -= 60
        return result
    with monkeypatch.context() as edits:
        edits.setattr(install, '_query_registry', query)
        with pytest.raises(install.InstallError):
            run(project, root, plan)
    assert project.journal.exists() and not project.current.exists() and not project.receipt.exists()
    journal = install._read(project.journal)
    assert journal['phase'] == 'registry-pending'
    assert (project.stages / journal['nonce'] / 'payload/0').exists()
    with pytest.raises(SystemExit, match='registry readiness'):
        build_snapshot.require_complete(project.out, repo=project.repo)
    install._execute(project, resume=True)
    assert not project.journal.exists()


def test_staged_or_destination_tampering_refuses_recovery(project, tmp_path, monkeypatch):
    root, plan = source(tmp_path, [('/Game/One', [], {'.uexp': b'bytes'})])
    with monkeypatch.context() as edits:
        interrupt_after_content_mutation(edits, project, 2)
        with pytest.raises(Interrupted):
            run(project, root, plan)
    journal = install._read(project.journal)
    payload = project.stages / journal['nonce'] / journal['staged']['One.uasset']['path']
    payload.chmod(0o600)
    payload.write_bytes(b'corrupt')
    with pytest.raises(install.InstallError, match='staging'):
        install._execute(project, resume=True)
    assert project.journal.exists() and not project.receipt.exists()


@pytest.mark.parametrize('case', ['external', 'generated_external', 'reference'])
def test_logical_case_aliases_are_rejected(tmp_path, case):
    _, plan = source(tmp_path, [('/Game/One', [], {})])
    if case == 'external':
        plan['external_references'] = ['/Game/Other', '/Game/other']
    elif case == 'generated_external':
        plan['external_references'] = ['/Game/one']
    else:
        plan['packages'][0]['references'] = ['/Game/one']
    with pytest.raises(install.InstallError):
        install.snapshot(plan)


def test_case_alias_cannot_hide_a_reference_to_a_retired_package(project, tmp_path):
    root, first = source(tmp_path, [('/Game/One', [], {})])
    run(project, root, first)
    root, second = source(tmp_path, [('/Game/Other', ['/Game/one'], {})], label='second')
    with pytest.raises(install.InstallError, match='retired'):
        run(project, root, second)
    assert not project.journal.exists() and (project.content / 'One.uasset').exists()


@pytest.mark.parametrize('change', ['journal_prior', 'current_replaced', 'current_removed'])
def test_recovery_binds_prior_ownership_to_durable_current(project, tmp_path, change):
    root, first = source(tmp_path, [('/Game/One', [], {'.uexp': b'old'})])
    run(project, root, first)
    root, second = source(tmp_path, [('/Game/One', [], {'.uexp': b'new'})], label='second')
    journal = install._prepare(project, second, root)
    if change == 'journal_prior':
        journal['old_files']['One.uexp']['pin']['inode'] += 1
        for operation in journal['operations']:
            if operation['path'] == 'One.uexp':
                operation['before'] = journal['old_files']['One.uexp']
        install._save(project.journal, journal)
    elif change == 'current_replaced':
        install._save(project.current, install._read(project.current))
    else:
        project.current.unlink()
    with pytest.raises((install.InstallError, FileNotFoundError)):
        install._execute(project, resume=True)
    assert project.journal.exists() and (project.content / 'One.uexp').read_bytes() == b'old'


@pytest.mark.parametrize('after', ['current', 'receipt', 'complete'])
def test_recovery_after_completion_metadata_fsync(project, tmp_path, monkeypatch, after):
    root, plan = source(tmp_path, [('/Game/One', [], {})])
    original = install._save
    def save(path, value):
        original(path, value)
        if ((after == 'current' and path == project.current)
                or (after == 'receipt' and path == project.receipt)
                or (after == 'complete' and path == project.journal and value['phase'] == 'complete')):
            raise Interrupted()
    with monkeypatch.context() as edits:
        edits.setattr(install, '_save', save)
        with pytest.raises(Interrupted):
            run(project, root, plan)
    assert project.journal.exists()
    assert install._execute(project, resume=True)['snapshot'] == plan
    assert not project.journal.exists()


def test_parent_symlink_swap_cannot_redirect_content_mutation(project, tmp_path, monkeypatch):
    root, plan = source(tmp_path, [('/Game/Sub/One', [], {})])
    project.content.mkdir()
    (project.content / 'Sub').mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    original = install._move_prepared
    def move(scope, candidate, relative, directories, *args, **kwargs):
        (scope.content / 'Sub').rename(scope.content / 'Original')
        (scope.content / 'Sub').symlink_to(outside, target_is_directory=True)
        return original(scope, candidate, relative, directories, *args, **kwargs)
    monkeypatch.setattr(install, '_move_prepared', move)
    with pytest.raises((install.InstallError, OSError)):
        run(project, root, plan)
    assert list(outside.iterdir()) == [] and project.journal.exists()


def test_public_install_uses_actual_guarded_worker_and_registry(project, tmp_path):
    import os
    import shutil
    import sys
    import atelier
    root, plan = source(tmp_path, [('/Game/One', [], {'.uexp': b'bytes'})])
    module_root = project.repo / 'platform' / 'studio'
    shutil.copytree(Path(atelier.__file__).parent, module_root / 'atelier',
                    ignore=shutil.ignore_patterns('__pycache__'))
    manifest = tmp_path / 'snapshot.json'
    manifest.write_text(json.dumps(plan))
    script = '''
import sys
from pathlib import Path
from atelier import build_install, capacity_runtime
capacity_runtime.DEFAULT_CONFIG = Path(sys.argv[3]) / 'absent-client.json'
try:
    from atelier import capacity_compat
    capacity_compat.DEFAULT_RECORD = Path(sys.argv[3]) / 'absent-cutover.json'
except ImportError:
    pass
result = build_install.install('fixture', sys.argv[1], sys.argv[2], timeout=30)
print('INSTALL_COMPLETE', result['transaction'], flush=True)
'''
    environment = dict(os.environ, PYTHONPATH=str(module_root), ATELIER_RENDER_LOCK=str(tmp_path / 'private-render.lock'),
                       ATELIER_RENDER_LOCK_SCAN='0')
    environment.pop('ATELIER_CAPACITY_CLIENT', None)
    environment.pop('ATELIER_BUILD_ROOT', None)
    result = subprocess.run([sys.executable, '-c', script, str(manifest), str(root), str(tmp_path)],
                            cwd=project.repo, env=environment, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'INSTALL_COMPLETE' in result.stdout and not project.journal.exists()
    assert (project.content / 'One.uexp').read_bytes() == b'bytes'
    assert install._read(project.receipt)['registry']['child'][0] > 0
    report = install._read(project.out / 'package-install.guard' / 'memory-health-tree.json')
    assert report['state'] == 'child_exited' and report['cleanup_complete'] is True


@pytest.mark.parametrize('mode', ['install', 'recover', 'nonzero', 'incomplete', 'stale'])
def test_public_guarded_request_and_completion_binding(project, tmp_path, monkeypatch, mode):
    import fcntl
    import os
    import stat
    from atelier import capacity_runtime, paths
    from atelier.safety import guarded
    root, plan = source(tmp_path, [('/Game/One', [], {})])
    manifest = tmp_path / 'snapshot.json'
    manifest.write_text(json.dumps(plan))
    monkeypatch.setattr(paths, 'REPO', project.repo)
    monkeypatch.setattr(capacity_runtime, 'configured_session', lambda **kwargs: None)
    if mode == 'recover':
        pending = install._prepare(project, plan, root)
    calls = []
    def run_guard(command, folder, **kwargs):
        calls.append((command, folder, kwargs))
        assert kwargs['aggregate_tree'] is True and kwargs['performance'] is True
        assert kwargs['limit_gib'] == 1 and kwargs['admission'] is None
        assert kwargs.get('lock', True) is True
        assert command[-3:-1] == ['atelier.build_install_worker', 'install']
        descriptor, = kwargs['pass_fds']
        assert command[-1] == str(descriptor)
        info = os.fstat(descriptor)
        assert stat.S_ISREG(info.st_mode) and info.st_nlink == 0 and stat.S_IMODE(info.st_mode) == 0o400
        assert fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
        spec = install._decode(os.pread(descriptor, install.MAX_JSON + 1, 0))
        assert spec['repo'] == str(project.repo) and spec['snapshot_sha256'] == install._digest(plan)
        assert spec['parent'][0] == os.getpid()
        assert spec['operation'] == ('recover' if mode == 'recover' else 'install')
        if mode == 'nonzero':
            return 7
        if mode == 'incomplete':
            install._prepare(project, plan, root, nonce=spec['nonce'])
            return 0
        if mode == 'recover':
            assert spec['transaction'] == pending['nonce']
            install._execute(project, resume=True)
        else:
            assert spec['transaction'] == spec['nonce']
            install._execute(project, plan, root, nonce=spec['nonce'])
        if mode == 'stale':
            receipt = install._read(project.receipt)
            receipt['nonce'] = '0' * 32
            install._save(project.receipt, receipt)
        return 0
    monkeypatch.setattr(guarded, 'run', run_guard)
    if mode in ('nonzero', 'incomplete', 'stale'):
        with pytest.raises(install.InstallError):
            install.install(project.game, manifest, root)
    else:
        result = install.recover(project.game) if mode == 'recover' else install.install(project.game, manifest, root)
        assert result['snapshot'] == plan
    assert len(calls) == 1


def test_recovery_refuses_newly_git_tracked_retirement(project, tmp_path):
    root, first = source(tmp_path, [('/Game/One', [], {}), ('/Game/Retired', [], {})])
    run(project, root, first)
    root, second = source(tmp_path, [('/Game/One', [], {})], label='second')
    install._prepare(project, second, root)
    subprocess.run(['git', '-C', str(project.repo), 'add', 'games/fixture/unreal/Content/Retired.uasset'], check=True)
    with pytest.raises(install.InstallError, match='tracked'):
        install._execute(project, resume=True)
    assert (project.content / 'Retired.uasset').exists() and project.journal.exists()


def test_git_index_change_after_scan_refuses_mutation(project, tmp_path, monkeypatch):
    root, plan = source(tmp_path, [('/Game/One', [], {})])
    project.content.mkdir()
    original = install._move_prepared
    def move(scope, *args, **kwargs):
        note = scope.repo / 'newly-tracked.txt'
        note.write_text('changed ownership index')
        subprocess.run(['git', '-C', str(scope.repo), 'add', note.name], check=True)
        return original(scope, *args, **kwargs)
    monkeypatch.setattr(install, '_move_prepared', move)
    with pytest.raises(install.InstallError, match='Git ownership'):
        run(project, root, plan)
    assert not (project.content / 'One.uasset').exists() and project.journal.exists()


@pytest.mark.parametrize('marker', [build_snapshot.JOURNAL, build_snapshot.PORTABLE_JOURNAL, build_snapshot.PACKAGE_JOURNAL])
def test_selected_root_transaction_blocks_package_worker(project, tmp_path, monkeypatch, marker):
    selected = tmp_path / 'selected'
    folder = selected / project.game
    folder.mkdir(parents=True)
    (folder / marker).write_text('{}')
    monkeypatch.setenv('ATELIER_BUILD_ROOT', str(selected))
    root, plan = source(tmp_path, [('/Game/One', [], {})])
    with pytest.raises(install.InstallError, match='transaction blocks'):
        run(project, root, plan)
    assert not project.content.exists()


def test_portable_resume_cannot_bypass_package_barrier(project, tmp_path):
    portable = {'scope': 'fixture'}
    install._save(project.out / build_snapshot.PORTABLE_JOURNAL, portable)
    project.journal.write_text('{}')
    with pytest.raises(SystemExit, match='Package installation'):
        build_snapshot.require_complete(project.out, repo=project.repo, portable_resume=portable)
