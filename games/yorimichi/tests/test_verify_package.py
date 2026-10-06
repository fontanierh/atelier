"""Release checks must reject stale proofs, corrupt parts and build-host dependencies."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    spec = importlib.util.spec_from_file_location('yorimichi_verify_package', TOOLS / 'verify_package.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def release(tmp_path, *, split=False):
    root = tmp_path / 'package'; root.mkdir()
    names = ['release.zip.part-aa', 'release.zip.part-ab'] if split else ['release.zip']
    entries = []
    for name in names:
        data = name.encode()
        (root / name).write_bytes(data)
        entries.append(dict(file=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    manifest = dict(app='Yorimichi.app', launcher='Play Yorimichi.command', zip='release.zip', split=split,
                    revision='a1b2c3d4', cook={'revision': 'a1b2c3d4' * 5}, files=entries)
    (root / 'manifest.json').write_text(json.dumps(manifest))
    (root / 'SHA256SUMS').write_text(''.join(f"{e['sha256']}  {e['file']}\n" for e in entries))
    return root, manifest


def test_release_checks_both_checksum_sources_and_the_actual_file(tmp_path, monkeypatch):
    tool = verifier(monkeypatch)
    root, manifest = release(tmp_path)
    assert tool.release_inputs(root, 'a1b2c3d4' * 5)[1] == 'a1b2c3d4' * 5
    with pytest.raises(RuntimeError, match='revision differs'):
        tool.release_inputs(root, 'other source')
    (root / 'release.zip').write_bytes(b'wrong bytes')
    with pytest.raises(RuntimeError, match='checksum mismatch'):
        tool.release_inputs(root)
    (root / 'SHA256SUMS').write_text('forged')
    with pytest.raises(RuntimeError, match='differs from the manifest'):
        tool.release_inputs(root)


def test_parts_must_be_complete_ordered_and_confined_to_the_release_directory(tmp_path, monkeypatch):
    tool = verifier(monkeypatch)
    root, manifest = release(tmp_path, split=True)
    assert len(tool.release_inputs(root)[2]) == 2
    manifest['files'].reverse()
    (root / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match='out of order'):
        tool.release_inputs(root)
    manifest['files'][0]['file'] = '../outside'
    (root / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match='single path'):
        tool.release_inputs(root)


def test_new_verification_refuses_an_old_extraction_or_old_report(tmp_path, monkeypatch):
    tool = verifier(monkeypatch)
    root, _ = release(tmp_path)
    old = tmp_path / 'old'; old.mkdir()
    with pytest.raises(RuntimeError, match='new extraction'):
        tool.verify(root, old, tmp_path / 'report.json')
    report = tmp_path / 'report.json'; report.write_text('old pass')
    with pytest.raises(RuntimeError, match='new report'):
        tool.verify(root, tmp_path / 'new', report)
    assert report.read_text() == 'old pass'


def load_commands(kind, library):
    return f'Load command 1\n      cmd {kind}\n     name {library} (offset 24)\n'


def test_dependency_checks_resolve_bundled_rpaths_and_distinguish_weak_links(tmp_path, monkeypatch):
    tool = verifier(monkeypatch)
    app = tmp_path / 'Yorimichi.app'
    binary = app / 'Contents/MacOS/Yorimichi'
    library = app / 'Contents/Frameworks/libAtelier.dylib'
    for path in (binary, library):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'\xcf\xfa\xed\xfe')
    commands = {binary: ('Load command 0\n      cmd LC_RPATH\n     path @executable_path/../Frameworks (offset 12)\n'
                         + load_commands('LC_LOAD_DYLIB', '@rpath/libAtelier.dylib')),
                library: load_commands('LC_LOAD_WEAK_DYLIB', '@loader_path/optional.dylib')}
    monkeypatch.setattr(tool.subprocess, 'check_output', lambda args, **kwargs: commands[Path(args[-1])])
    result = tool.native_dependencies(app, binary)
    assert result['resolved'] == [dict(loader='Contents/MacOS/Yorimichi', library='@rpath/libAtelier.dylib',
                                      resolved='Contents/Frameworks/libAtelier.dylib')]
    assert result['optional_weak_links'][0]['library'] == '@loader_path/optional.dylib'
    commands[library] = load_commands('LC_LOAD_DYLIB', '@loader_path/optional.dylib')
    with pytest.raises(RuntimeError, match='unresolved required library'):
        tool.native_dependencies(app, binary)
    commands[library] = load_commands('LC_LOAD_DYLIB', '/opt/local/build/libAtelier.dylib')
    with pytest.raises(RuntimeError, match='local installation'):
        tool.native_dependencies(app, binary)
    assert tool.expand_dyld('@loader_path', library.parent, binary) == library.parent


def test_no_success_report_when_the_guarded_extraction_fails(tmp_path, monkeypatch):
    tool = verifier(monkeypatch)
    root, _ = release(tmp_path)
    calls = []
    monkeypatch.setattr(tool.guarded, 'run', lambda *args, **kwargs: calls.append((args, kwargs)) or 1)
    report = tmp_path / 'report.json'
    with pytest.raises(RuntimeError, match='extraction failed'):
        tool.verify(root, tmp_path / 'new', report)
    assert not report.exists() and calls[0][1]['small_gib'] == 3 and calls[0][1]['watch'] == ('ditto',)
