"""Focused fixed-tool composition tests; no native child or sandbox execution."""
import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from atelier.build_v2 import legacy_tool_action as tools
from atelier.build_v2.legacy_qualification import CapturedCode


def test_selected_tool_identity_tracks_actual_image_library_and_source_bytes(tmp_path, monkeypatch):
    image = tmp_path / 'bin/node'; image.parent.mkdir(); image.write_bytes(b'image')
    library = tmp_path / 'lib/libnode.1.dylib'; library.parent.mkdir(); library.write_bytes(b'library')
    source = tmp_path / 'bridge.cjs'; source.write_bytes(b'source')
    files = [source]
    for name in ('pieces.cjs', 'terrain.cjs', 'pin.json'):
        p = tmp_path / name; p.write_bytes(b'data'); files.append(p)
    monkeypatch.setattr(tools.shutil, 'which', lambda name: str(image))
    monkeypatch.setattr(tools, 'node_libraries', lambda path: (library,))
    tool = tools.bind_node(files, tmp_path / 'frontend.py')
    # Installed path labels are fixed platform context, not generated private paths.
    hasher = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    before = tools.node_spec(tool, hasher)
    identity = tools.node_identity(tool, hasher)
    image.write_bytes(b'changed image')
    assert tools.node_spec(tool, hasher)['digest'] != before['digest']
    assert tools.node_identity(tool, hasher) != identity
    with pytest.raises(ValueError, match='image changed'):
        tools._verify(before)
    image.write_bytes(b'image'); library.write_bytes(b'changed library')
    assert tools.node_spec(tool, hasher)['libraries'] != before['libraries']
    source.write_bytes(b'changed source')
    assert tools.node_spec(tool, hasher)['sources'] != before['sources']
    with pytest.raises(ValueError, match='descriptor'):
        tools.checked_node(SimpleNamespace(**vars(tool)))


def test_native_profile_has_only_exact_tool_sources_libraries_and_mesh_writes(tmp_path):
    role = tmp_path / 'node'; role.write_bytes(b'node')
    source = tmp_path / 'bridge.cjs'; source.write_bytes(b'code')
    profile = tools._profile(tmp_path / 'snapshot', tmp_path / 'snapshot/mesh', role, role,
                             [source], ['/opt/homebrew/Cellar/node/1/lib/libnode.1.dylib'])
    assert '(debug deny)' in profile
    assert '(deny default)' in profile and '(deny file-read* network* (with send-signal SIGKILL) (with telemetry)' in profile
    assert f'(literal "{source}")' in profile
    assert '(literal "/opt/homebrew/Cellar/node/1/lib/libnode.1.dylib")' in profile
    assert '(subpath "/opt/homebrew")' not in profile and '(subpath "/opt/homebrew/Cellar")' not in profile
    assert f'(subpath "{tmp_path / "snapshot/mesh"}")' in profile
    assert f'(subpath "{tmp_path / "snapshot/output"}")' not in profile
    assert f'(allow process-exec (literal "{role}"))' in profile


def test_actual_tool_wrapper_checks_captured_provider_and_restores_on_error(tmp_path, monkeypatch):
    scratch = tmp_path / 'scratch'; directory = scratch / 'tmp/owned'; directory.mkdir(parents=True)
    snap = directory / 'snap'; snap.mkdir(); (snap / 'data').mkdir(); (snap / 'park.json').write_text('{}')
    output = directory / 'mesh'; output.mkdir()
    provider = tmp_path / 'frontend.py'
    raw = b'def compile_snapshot(argv, log):\n assert shutil.which("node") == argv[0]\n return subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False)\n'
    source = CapturedCode(str(provider), raw)
    scope = {'subprocess': subprocess, 'shutil': tools.shutil, '__file__': str(provider)}
    exec(source.compiled(), scope)
    image = tmp_path / 'installed/bin/node'; image.parent.mkdir(parents=True); image.write_bytes(b'image')
    role = tmp_path / 'node-role'; role.symlink_to(image)
    files = [tmp_path / name for name in ('bridge.cjs', 'pieces.cjs', 'terrain.cjs', 'pin.json')]
    spec = {'provider': str(provider), 'libraries': []}
    monkeypatch.setattr(tools, '_verify', lambda value: (role, image, files))
    events = []
    from atelier.build_audit_worker import Observer
    observer = Observer({'inputs': [], 'outputs': [], 'runtime': [], 'scratch': str(scratch)})
    observer.record = lambda event, *args, **kw: events.append((event, kw))
    original_observe = observer.observe.__func__
    calls = []
    def launched(command, **kwargs):
        assert command[:2] == ['/usr/bin/sandbox-exec', '-p']
        assert command[3] == str(image) and command[3] != str(role)
        assert not observer.local.busy
        observer.observe('subprocess.Popen', (command[0], command, kwargs['cwd'], None))
        observer.observe('subprocess.Popen', (command[0], command, kwargs['cwd'], None))
        assert events[-1][0] == 'subprocess.Popen' and events[-1][1]['reason']
        calls.append(command)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(tools.subprocess, 'run', launched)
    argv = [str(role), '--max-old-space-size=1024', str(files[0]),
            str(snap / 'park.json'), str(snap / 'data'), str(output)]
    with (output / 'node.log').open('w') as log:
        with tools.node_execution(spec, scratch=scratch, sources=[source], observer=observer):
            assert observer.observe.__func__ is original_observe  # Import resolver stack stays exact.
            assert scope['compile_snapshot'](argv, log).returncode == 0
            with pytest.raises(ValueError, match='unqualified'):
                subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False)
            assert any(item[0] == 'subprocess' for item in events)
    assert len(calls) == 1 and any(item[0] == 'checked nested tool' for item in events)
    assert subprocess.run is launched and observer.observe.__func__ is original_observe and observer._nested_process is None and not observer.local.busy


def test_private_legacy_runtime_retains_cutoff_and_exact_original_output_roots(tmp_path, monkeypatch):
    from atelier import build, build_audit
    root = tmp_path / 'checkout'; root.mkdir()
    script = root / 'producer.py'; script.write_text('pass\n')
    output = root / 'build/game'; output.mkdir(parents=True)
    step = build.Step('actual.geometry', [build.Python(script)], inputs=[script],
                      outputs=[output / 'geometry.npz', output / 'lines'], heavy=True, cutoff=True)
    image = tmp_path / 'bin/node'; image.parent.mkdir(); image.write_bytes(b'image')
    libraries = tmp_path / 'libnode.1.dylib'; libraries.write_bytes(b'library')
    sources = []
    for name in ('bridge.cjs', 'pieces.cjs', 'terrain.cjs', 'pin.json'):
        p = tmp_path / name; p.write_bytes(b'code'); sources.append(p)
    monkeypatch.setattr(tools.shutil, 'which', lambda name: str(image))
    monkeypatch.setattr(tools, 'node_libraries', lambda path: (libraries,))
    tool = tools.bind_node(sources, script)
    names = [*build_audit._CAPTURED_WORKER, 'producer.py',
             'platform/studio/atelier/build_v2/legacy_tool_action.py',
             'platform/studio/atelier/build_v2/python_worker.py',
             'platform/studio/atelier/build_v2/protocol.py', 'platform/studio/atelier/build_products.py']
    runtime = build_audit._bind_captured_runtime(step, checkout=root, issuer_files=names,
                      nested_tool=tool, legacy_outputs=tuple(step.outputs))
    build_audit.validate(step)
    build_audit.roots(SimpleNamespace(out=output), step)
    assert step.products == [] and step.cutoff and step.heavy and not step.cache
    assert runtime.legacy_outputs == tuple(step.outputs)
    step.outputs.append(output / 'foreign')
    with pytest.raises(ValueError):
        build_audit.validate(step)
    step.outputs.pop()
    step.cutoff = False
    with pytest.raises(ValueError):
        build_audit.validate(step)


def test_original_legacy_fingerprint_and_current_include_nested_tool_bytes(tmp_path, monkeypatch):
    from atelier import build, build_audit, build_cache, build_plan, paths
    script = tmp_path / 'producer.py'; script.write_text('pass\n')
    product = tmp_path / 'geometry.npz'; product.write_bytes(b'output')
    image = tmp_path / 'installed/bin/node'; image.parent.mkdir(parents=True); image.write_bytes(b'image')
    library = tmp_path / 'installed/libnode.1.dylib'; library.write_bytes(b'library')
    sources = []
    for name in ('bridge.cjs', 'pieces.cjs', 'terrain.cjs', 'pin.json'):
        p = tmp_path / name; p.write_bytes(b'code'); sources.append(p)
    monkeypatch.setattr(tools.shutil, 'which', lambda name: str(image))
    configuration = tmp_path / 'openssl/openssl.cnf'
    configuration.parent.mkdir(); configuration.write_bytes(b'openssl_conf = openssl_init\n')
    crypto = tmp_path / 'installed/libcrypto.3.dylib'
    crypto.write_bytes(b'OPENSSLDIR: "' + str(configuration.parent).encode() + b'"\0')
    monkeypatch.setattr(tools, 'node_libraries', lambda path: (library, crypto))
    tool = tools.bind_node(sources, script)
    step = build.Step('actual.geometry', [build.Python(script)], inputs=[script], outputs=[product],
                      heavy=True, cutoff=True)
    # This unit fixture supplies the existing private descriptor without issuing any
    # task/epoch authority. Production constructs it only after the pure fixed role.
    step._captured_audit_runtime = build_audit._CapturedRuntime(
        paths.REPO, build_audit._CAPTURED_WORKER, build_audit._CAPTURED_ORIGIN, tool, (product,))
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **kw: {'fixed': 'original Python installation'})
    key = build.fingerprint(step, {})
    stamps = tmp_path / 'stamps'; stamps.mkdir()
    import json
    (stamps / 'actual.geometry.json').write_text(json.dumps({'fingerprint': key}))
    ctx = SimpleNamespace(out=tmp_path, stamps=stamps, game='fixture')
    assert build_plan.inspect(ctx, [step], [step.name])['steps'][0]['status'] == 'current'
    for path in (image, library, sources[0], configuration):
        old = path.read_bytes(); path.write_bytes(old + b'changed')
        assert build.fingerprint(step, {}) != key
        assert build_plan.inspect(ctx, [step], [step.name])['steps'][0]['status'] == 'run'
        path.write_bytes(old)
    metadata = image.parent.parent / 'Contents'
    metadata.mkdir()
    (metadata / 'Info.plist').write_bytes(b'new installed metadata')
    assert build.fingerprint(step, {}) != key
    assert build_plan.inspect(ctx, [step], [step.name])['steps'][0]['status'] == 'run'
    (metadata / 'Info.plist').unlink(); metadata.rmdir()
    assert build.fingerprint(step, {}) == key and not step.cache and not step.products


def test_intermediate_image_link_metadata_is_exact_and_never_a_data_grant(tmp_path):
    role = tmp_path / 'node'; role.write_bytes(b'node')
    link = '/opt/homebrew/Cellar/llhttp/9.3.0/lib/libllhttp.9.3.dylib'
    profile = tools._profile(tmp_path / 'owned', tmp_path / 'owned/mesh', role, role, [], [], [link])
    clause = next(line for line in profile.splitlines() if 'regex-quote' in line)
    assert clause == ('(allow file-read-metadata (regex (string-append "^" (regex-quote "'
                      + link + '") "$")))')
    assert profile.count(link) == 1
    assert '(allow file-read* (regex' not in profile


def test_relative_native_profile_scope_refuses_without_ambient_resolution(tmp_path):
    with pytest.raises(ValueError, match='absolute'):
        tools._profile(Path('relative/snapshot'), tmp_path / 'mesh', tmp_path / 'node',
                       tmp_path / 'node', [], [])


def test_complete_installed_context_tracks_membership_and_internal_links_without_escape(tmp_path):
    root = tmp_path / 'installation'; root.mkdir()
    source = root / 'library'; source.write_bytes(b'image')
    (root / 'alias').symlink_to('library')
    before = tools.installation_inventory(root)
    assert before['links'] == {'alias': 'library'}
    assert before['inventory']['files']['0/library']['kind'] == 'file'
    (root / 'unused.md').write_bytes(b'installed metadata participates too')
    assert tools.installation_inventory(root) != before  # No source-style exclusions.
    foreign = tmp_path / 'foreign'; foreign.write_bytes(b'must not read')
    (root / 'outside').symlink_to(foreign)
    seen = []
    def hasher(path):
        seen.append(Path(path))
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    observed = tools.installation_inventory(root, hasher)
    assert observed['links']['outside'] == str(foreign)
    assert not any(str(foreign) in name for name in observed['inventory']['files'])
    assert foreign not in seen and foreign.read_bytes() == b'must not read'


def test_compiled_default_openssl_configuration_is_exact_and_refuses_expansion(tmp_path, monkeypatch):
    library = tmp_path / 'libcrypto.3.dylib'
    directory = tmp_path / 'openssl'; directory.mkdir()
    config = directory / 'openssl.cnf'; config.write_text('openssl_conf = openssl_init\n')
    library.write_bytes(b'OPENSSLDIR: "' + str(directory).encode() + b'"\0')
    assert tools.openssl_configurations([library, library]) == (config,)
    original = config.read_bytes()
    for content in (b'.include foreign.cnf\n', b'module = /foreign/provider.dylib\n',
                    b'dynamic_path = /foreign/engine.dylib\n', b'oid_file = $ENV::HOME/foreign\n'):
        config.write_bytes(content)
        with pytest.raises(ValueError, match='unsupported OpenSSL'):
            tools.openssl_configurations([library])
    config.write_bytes(original)
    for name in ('OPENSSL_CONF', 'OPENSSL_CONF_INCLUDE', 'OPENSSL_MODULES'):
        with monkeypatch.context() as patch:
            patch.setenv(name, '')
            with pytest.raises(ValueError, match='environment override'):
                tools.openssl_configurations([library])
    config.unlink(); config.symlink_to(library)
    with pytest.raises((ValueError, OSError)):
        tools.openssl_configurations([library])


def test_profile_grants_only_keyed_node_installation_and_exact_default_config(tmp_path):
    image = tmp_path / 'installed/bin/node'
    config = tmp_path / 'config/openssl.cnf'
    profile = tools._profile(tmp_path / 'scratch', tmp_path / 'scratch/mesh', image, image,
                            [], [], configurations=[config])
    assert f'(subpath "{image.parent.parent}")' in profile
    assert f'(literal "{config}")' in profile
    assert f'(subpath "{config.parent}")' not in profile
    assert '(allow file-read-metadata (with report))' not in profile
    assert '(deny file-read* network* (with send-signal SIGKILL)' in profile
