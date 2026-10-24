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
    assert '(deny default)' in profile and '(deny file-read* network* (with send-signal SIGKILL))' in profile
    assert f'(literal "{source}")' in profile
    assert '(literal "/opt/homebrew/Cellar/node/1/lib/libnode.1.dylib")' in profile
    assert '(subpath "/opt/homebrew")' not in profile and '(subpath "/opt/homebrew/Cellar")' not in profile
    assert f'(subpath "{tmp_path / "snapshot/mesh"}")' in profile
    assert f'(allow process-exec (literal "{role}"))' in profile


def test_actual_tool_wrapper_checks_captured_provider_and_restores_on_error(tmp_path, monkeypatch):
    scratch = tmp_path / 'scratch'; directory = scratch / 'tmp/owned'; directory.mkdir(parents=True)
    snap = directory / 'snap'; snap.mkdir(); (snap / 'data').mkdir(); (snap / 'park.json').write_text('{}')
    output = directory / 'mesh'; output.mkdir()
    provider = tmp_path / 'frontend.py'
    raw = b'def compile_snapshot(argv, log):\n return subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False)\n'
    source = CapturedCode(str(provider), raw)
    scope = {'subprocess': subprocess, '__file__': str(provider)}
    exec(source.compiled(), scope)
    role = tmp_path / 'node'; role.write_bytes(b'image')
    files = [tmp_path / name for name in ('bridge.cjs', 'pieces.cjs', 'terrain.cjs', 'pin.json')]
    spec = {'provider': str(provider), 'libraries': []}
    monkeypatch.setattr(tools, '_verify', lambda value: (role, role, files))
    events = []
    observer = SimpleNamespace(local=SimpleNamespace(busy=False),
                               observe=lambda event, args: events.append(('denied', event)),
                               record=lambda event, **kw: events.append((event, kw)))
    original_observe = observer.observe
    calls = []
    def launched(command, **kwargs):
        assert command[:2] == ['/usr/bin/sandbox-exec', '-p']
        assert not observer.local.busy
        observer.observe('subprocess.Popen', (command[0], command, None, None))
        observer.observe('subprocess.Popen', (command[0], command, None, None))
        assert events[-1] == ('denied', 'subprocess.Popen')
        calls.append(command)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(tools.subprocess, 'run', launched)
    argv = [str(role), '--max-old-space-size=1024', str(files[0]),
            str(snap / 'park.json'), str(snap / 'data'), str(output)]
    with (output / 'node.log').open('w') as log:
        with tools.node_execution(spec, scratch=scratch, sources=[source], observer=observer):
            assert scope['compile_snapshot'](argv, log).returncode == 0
            with pytest.raises(ValueError, match='unqualified'):
                subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False)
            assert any(item[0] == 'subprocess' for item in events)
    assert len(calls) == 1 and any(item[0] == 'checked nested tool' for item in events)
    assert subprocess.run is launched and observer.observe is original_observe and not observer.local.busy


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
             'platform/studio/atelier/build_v2/protocol.py']
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
