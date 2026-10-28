"""Controller distribution/control proof without compiling or starting any worker."""
import hashlib
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier.build_v2 import controller_client as client


def source(root):
    names = {
        'platform/build-v2/Cargo.toml': b'[package]\nname="controller"\nversion="0.1.0"\n',
        'platform/build-v2/Cargo.lock': b'version = 4\n',
        'platform/build-v2/.cargo/config.toml': b'[build]\njobs=3\n',
        'platform/build-v2/src/lib.rs': b'pub fn fixture() {}\n',
        'platform/build-v2/src/bin/atelier-build-v2.rs': b'fn main() {}\n',
    }
    for name, raw in names.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (root / client.SOURCE_MANIFEST).write_text(json.dumps({'version': 1, 'files': sorted(names)}))
    return names


def test_controller_sources_are_named_frozen_and_location_independent(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    original = source(first)
    source(second)
    frozen = client.capture_controller(first)
    assert frozen.digest == client.capture_controller(second).digest
    script = first / 'platform/build-v2/src/lib.rs'
    script.write_bytes(b'pub fn changed() {}\n')
    assert frozen.digest != client.capture_controller(first).digest
    assert dict(frozen.files)['platform/build-v2/src/lib.rs'] == original['platform/build-v2/src/lib.rs']
    destination = tmp_path / 'frozen'
    frozen.materialize(destination)
    assert client.capture_controller(destination).digest == frozen.digest
    assert (destination / 'platform/build-v2/src/lib.rs').stat().st_mode & 0o222 == 0
    with pytest.raises(FileExistsError):
        frozen.materialize(destination)


def test_controller_distribution_keeps_256_file_limit_separate_from_named_issuer(tmp_path):
    names = source(tmp_path)
    folder = tmp_path / 'platform/studio/atelier'
    folder.mkdir(parents=True)
    for index in range(252):
        name = f'platform/studio/atelier/distribution_fixture_{index}.py'
        (tmp_path / name).write_bytes(b'VALUE = 1\n')
        names[name] = b'VALUE = 1\n'
    manifest = tmp_path / client.SOURCE_MANIFEST
    manifest.write_text(json.dumps({'version': 1, 'files': sorted(names)[:256]}))
    captured = client.capture_controller(tmp_path)
    assert len(captured.files) == 257  # 256 listed files plus the separately captured manifest.
    assert client.SOURCE_MANIFEST in dict(captured.files)
    manifest.write_text(json.dumps({'version': 1, 'files': sorted(names)}))
    with pytest.raises(ValueError):
        client.capture_controller(tmp_path)


@pytest.mark.parametrize('change', ['link', 'parent_link', 'path_dependency', 'build_script', 'workspace', 'duplicate'])
def test_controller_source_capture_refuses_links_and_undeclared_build_dependencies(tmp_path, change):
    names = source(tmp_path)
    cargo = tmp_path / 'platform/build-v2/Cargo.toml'
    if change == 'link':
        other = tmp_path / 'other'
        other.write_bytes(cargo.read_bytes())
        cargo.unlink()
        cargo.symlink_to(other)
    elif change == 'parent_link':
        folder = tmp_path / 'platform/build-v2/src'
        folder.rename(tmp_path / 'moved')
        folder.symlink_to(tmp_path / 'moved', target_is_directory=True)
    elif change == 'path_dependency':
        cargo.write_text('[package]\nname="controller"\nversion="0.1.0"\n[dependencies]\nother={path="../other"}\n')
    elif change == 'build_script':
        cargo.write_text('[package]\nname="controller"\nversion="0.1.0"\nbuild="build.rs"\n')
    elif change == 'workspace':
        cargo.write_text('[workspace]\nmembers=[]\n')
    elif change == 'duplicate':
        (tmp_path / client.SOURCE_MANIFEST).write_text(json.dumps({'version': 1, 'files': [*names, *names]}))
    with pytest.raises((ValueError, OSError)):
        client.capture_controller(tmp_path)


def test_control_files_are_bounded_private_exclusive_and_nofollow(tmp_path, monkeypatch):
    private = tmp_path / 'control'
    private.mkdir(mode=0o700)
    record = {'version': 1, 'targets': ['existing.target']}
    client.write_control(private, 'request.json', record)
    assert client.read_control(private, 'request.json') == record
    assert (private / 'request.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        client.write_control(private, 'request.json', record)
    (private / 'link').symlink_to(private / 'request.json')
    with pytest.raises(OSError):
        client.read_control(private, 'link')
    (private / 'duplicate.json').write_text('{"x":1,"x":2}')
    (private / 'duplicate.json').chmod(0o600)
    with pytest.raises(ValueError, match='duplicate'):
        client.read_control(private, 'duplicate.json')
    monkeypatch.setattr(client, 'MAX_CONTROL_BYTES', 8)
    with pytest.raises(ValueError, match='bound'):
        client.write_control(private, 'too-large.json', record)
    assert not (private / 'too-large.json').exists()
    private.chmod(0o755)
    with pytest.raises(ValueError, match='private'):
        client.read_control(private, 'request.json')


def test_inspection_never_bootstraps_or_creates_state_and_refuses_stale_bytes(tmp_path):
    checkout = tmp_path / 'checkout'
    source(checkout)
    cache = tmp_path / 'not-created'
    assert client.inspect_controller(checkout, cache) == {
        'state': 'bootstrap_needed', 'reason': 'missing_controller'}
    assert not cache.exists()
    cache.mkdir(mode=0o700)
    binary = cache / 'atelier-build-v2'
    binary.write_bytes(b'fixture executable bytes, never launched')
    binary.chmod(0o500)
    client.write_control(cache, 'controller.json', {
        'version': 1, 'source': client.capture_controller(checkout).digest,
        'binary': hashlib.sha256(binary.read_bytes()).hexdigest()})
    before = sorted(p.name for p in cache.iterdir())
    assert client.inspect_controller(checkout, cache)['state'] == 'current'
    assert sorted(p.name for p in cache.iterdir()) == before
    binary.chmod(0o700)
    binary.write_bytes(b'substituted')
    assert client.inspect_controller(checkout, cache)['reason'] == 'binary_mismatch'
    (checkout / 'platform/build-v2/src/lib.rs').write_bytes(b'new controller implementation')
    assert client.inspect_controller(checkout, cache)['reason'] == 'source_or_receipt_mismatch'


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'a//b', 'a/./b', 'a\\b', ''])
def test_control_names_cannot_escape_private_namespace(tmp_path, name):
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError):
        client.write_control(tmp_path, name, {})


def test_bootstrap_compiles_frozen_bytes_under_guard_and_reuses_verified_helper(tmp_path, monkeypatch):
    from atelier.harness.safety import guarded
    checkout = tmp_path / 'checkout'
    names = source(checkout)
    state = tmp_path / 'helpers'
    expected = client.capture_controller(checkout).digest
    calls = []

    def compile_frozen(argv, report, **options):
        assert options['kind'] == 'compile'
        assert options['aggregate_tree'] is True
        assert options['timeout'] == options['queue_seconds'] == 1800
        assert argv[:5] == ['cargo', 'build', '--locked', '--jobs', '3']
        assert Path.cwd() != checkout / 'platform/build-v2'
        assert (Path.cwd() / 'src/lib.rs').read_bytes() == names['platform/build-v2/src/lib.rs']
        assert options['env']['ATELIER_CONTROLLER_SOURCE_SHA256'] == expected
        assert options['env']['CARGO_ENCODED_RUSTFLAGS'] == ''
        assert 'CARGO_BUILD_RUSTC_WRAPPER' not in options['env']
        target = Path(argv[argv.index('--target-dir') + 1])
        (target / 'debug').mkdir()
        (target / 'debug/atelier-build-v2').write_bytes(b'compiled fixture bytes')
        calls.append(report)
        return 0

    def identity(argv, **kwargs):
        assert Path(argv[0]).read_bytes() == b'compiled fixture bytes'
        assert argv[1:] == ['--identity']
        return SimpleNamespace(returncode=0, stdout=(expected + '\n').encode())

    monkeypatch.setenv('CARGO_BUILD_RUSTC_WRAPPER', 'must-not-reach-compile')
    monkeypatch.setattr(guarded, 'run', compile_frozen)
    monkeypatch.setattr(client.subprocess, 'run', identity)
    before = Path.cwd()
    helper = client.ensure_controller(checkout, state, echo=lambda _: None)
    assert Path.cwd() == before
    assert len(calls) == 1
    assert helper.source == expected
    assert helper.path.read_bytes() == b'compiled fixture bytes'
    assert helper.path.stat().st_mode & 0o777 == 0o500
    assert client.ensure_controller(checkout, state, echo=lambda _: None) == helper
    assert len(calls) == 1
    assert (state / 'controller.json').exists() is False  # distribution is source-versioned


@pytest.mark.parametrize('failure', ['compile', 'live_source', 'frozen_source', 'wrong_binary'])
def test_bootstrap_source_change_or_failure_never_publishes_helper(tmp_path, monkeypatch, failure):
    from atelier.harness.safety import guarded
    checkout = tmp_path / 'checkout'
    source(checkout)
    state = tmp_path / 'helpers'
    expected = client.capture_controller(checkout).digest

    def compile_frozen(argv, report, **options):
        if failure == 'compile':
            return 1
        if failure == 'live_source':
            (checkout / 'platform/build-v2/src/lib.rs').write_bytes(b'changed live code')
        if failure == 'frozen_source':
            path = Path.cwd() / 'src/lib.rs'
            path.chmod(0o600)
            path.write_bytes(b'changed private code')
        target = Path(argv[argv.index('--target-dir') + 1])
        (target / 'debug').mkdir()
        (target / 'debug/atelier-build-v2').write_bytes(b'fixture bytes')
        return 0

    monkeypatch.setattr(guarded, 'run', compile_frozen)
    monkeypatch.setattr(client.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'wrong\n'))
    before = Path.cwd()
    with pytest.raises((ValueError, RuntimeError)):
        client.ensure_controller(checkout, state, echo=lambda _: None)
    assert Path.cwd() == before
    assert not (state / expected).exists()
    assert not list(state.glob('*/controller.json'))


def test_busy_bootstrap_refuses_without_unbounded_wait_or_guard_submission(tmp_path, monkeypatch):
    from atelier.harness.safety import guarded
    checkout = tmp_path / 'checkout'
    source(checkout)
    state = tmp_path / 'helpers'
    state.mkdir(mode=0o700)
    lock = state / '.bootstrap.lock'
    lock.touch(mode=0o600)
    with lock.open('r+b') as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        def forbidden(*args, **kwargs):
            raise AssertionError('busy bootstrap submitted another guard')
        monkeypatch.setattr(guarded, 'run', forbidden)
        with pytest.raises(RuntimeError, match='already active'):
            client.ensure_controller(checkout, state, echo=lambda _: None)
    assert sorted(p.name for p in state.iterdir()) == ['.bootstrap.lock']


def test_real_controller_manifest_contains_transitive_literal_rust_includes():
    import re
    root = Path(__file__).resolve().parents[3]
    manifest = json.loads((root / client.SOURCE_MANIFEST).read_text())
    named = set(manifest['files'])
    pending, seen = list(named), set()
    include = re.compile(r'include_(?:str|bytes)!\s*\(\s*("(?:[^"\\]|\\.)*")\s*\)')
    while pending:
        name = pending.pop()
        if name in seen or not name.endswith('.rs'):
            continue
        seen.add(name)
        for match in include.finditer((root / name).read_text()):
            target = ((root / name).parent / json.loads(match[1])).resolve(strict=True)
            relative = target.relative_to(root).as_posix()
            assert relative in named, f'{name} embeds source omitted by controller manifest: {relative}'
            pending.append(relative)
