"""Fixed native TOOL routes; no native execution in these focused tests."""
import io
import json

import pytest

from atelier.build_v2 import native_tool_worker as tool
from atelier.build_v2 import protocol


def job(tmp_path, kind='unreal.compile'):
    (tmp_path / 'output').mkdir()
    (tmp_path / '.recipe-runtime').mkdir()
    project = tmp_path / 'Game.uproject'
    project.write_text('{}')
    return {'job_id': 'j', 'unit': 'u', 'op': {'kind': kind, 'version': '1'}, 'job_dir': str(tmp_path),
            'script': '', 'code': ['Game.uproject'], 'inputs': [],
            'params': {'project': 'Game.uproject', 'target': 'GameEditor',
                       'recipe': {'version': 1, 'paths': {}, 'commands': [], 'verify': None,
                                  'outputs': [{'path': 'Binaries/Mac', 'file': 'binaries.tree.tar'}]}},
            'outputs': [{'path': 'binaries.tree.tar'}]}


def test_compile_runs_private_frozen_project_and_exports_complete_receipt(tmp_path):
    original = job(tmp_path)
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        view = kwargs['cwd']
        root = view / 'Binaries/Mac'
        root.mkdir(parents=True)
        (root / 'Game.dylib').write_bytes(b'compiled')
        (root / 'UnrealEditor.modules').write_text(json.dumps({'BuildId': 'real-receipt-test', 'Modules': {'Game': 'Game.dylib'}}))
        (root / 'GameEditor.target').write_text(json.dumps({'TargetName': 'GameEditor', 'Platform': 'Mac',
            'Configuration': 'Development', 'BuildProducts': [{'Path': '$(ProjectDir)/Binaries/Mac/Game.dylib'}]}))
    result = tool.dispatch(original, tmp_path, tmp_path / 'engine', run)
    assert result == ['binaries.tree.tar']
    assert calls[0][0][-1] == '-MaxParallelActions=3'
    assert str(tmp_path / '.recipe-runtime/view/Game.uproject') in calls[0][0][-3]
    restored = tmp_path / 'restored'
    tool.recipe_job.unpack_root(tmp_path / 'output/binaries.tree.tar', restored)
    assert {p.name for p in restored.iterdir()} == {'Game.dylib', 'GameEditor.target', 'UnrealEditor.modules'}


def test_missing_receipt_never_completes(tmp_path):
    with pytest.raises(FileNotFoundError):
        tool.dispatch(job(tmp_path), tmp_path, tmp_path / 'engine', lambda *a, **kw: None)
    assert not list((tmp_path / 'output').iterdir())


def test_cook_production_without_fixed_export_hook_refuses(tmp_path):
    with pytest.raises(tool.Refused, match='source-cook'):
        tool.dispatch(job(tmp_path, 'unreal.cook.produce'), tmp_path, tmp_path / 'engine', lambda *a, **kw: None)


def test_archive_inventory_preserves_internal_link_and_refuses_escape(tmp_path):
    root = tmp_path / 'Game.app'
    root.mkdir()
    (root / 'binary').write_bytes(b'game')
    (root / 'linked').symlink_to('binary')
    assert ('linked', 'link', 'binary') in tool._tree(root)
    (root / 'linked').unlink()
    (root / 'linked').symlink_to('/etc/passwd')
    with pytest.raises(tool.Refused, match='escapes'):
        tool._tree(root)


def test_worker_protocol_hello_started_failed_then_shutdown(tmp_path):
    requests, responses = io.BytesIO(), io.BytesIO()
    request = job(tmp_path, 'unknown')
    for value in ({'type': 'run', 'job': request}, {'type': 'shutdown'}):
        protocol.write_frame(requests, protocol.REQUEST, value)
    requests.seek(0)
    tool.Worker(requests, responses, tmp_path / 'engine').serve()
    responses.seek(0)
    frames = []
    while (frame := protocol.read_frame(responses, protocol.RESPONSE)) is not None:
        frames.append(frame)
    assert [f['type'] for f in frames] == ['hello', 'started', 'failed', 'stopped']
    assert frames[0]['worker_version'] == tool.WORKER_VERSION


def test_package_refuses_missing_upstream_inventory_before_launch(tmp_path):
    request = job(tmp_path, 'unreal.package')
    request['params']['archive'] = 'archive'
    calls = []
    with pytest.raises(ValueError, match='independently completed'):
        tool.dispatch(request, tmp_path, tmp_path / 'engine', lambda *a, **kw: calls.append(a))
    assert calls == []


def test_unknown_version_and_arbitrary_archive_script_refuse(tmp_path):
    request = job(tmp_path, 'package.archive')
    request['op']['version'] = '2'
    with pytest.raises(ValueError, match='unsupported native'):
        tool.dispatch(request, tmp_path, tmp_path / 'engine', lambda *a, **kw: None)
    request['op']['version'] = '1'
    request['params']['recipe']['commands'] = [{'kind': 'python', 'script': 'arbitrary.py', 'env': [], 'args': []}]
    with pytest.raises(ValueError, match='unknown package archive'):
        tool.dispatch(request, tmp_path, tmp_path / 'engine', lambda *a, **kw: None)


def test_game_archives_receipt_listed_bundle_with_internal_links(tmp_path):
    request = job(tmp_path, 'unreal.game')
    request['params']['target'] = 'Game'
    request['params']['recipe']['outputs'][0]['encoding'] = 'mac-zip'
    request['params']['recipe']['outputs'][0]['file'] = 'binaries.zip'
    commands = []
    def run(argv, **kwargs):
        commands.append(argv)
        if argv[0] == '/usr/bin/ditto':
            Path(argv[-1]).write_bytes(b'zip tool output')
            return
        binaries = kwargs['cwd'] / 'Binaries/Mac'
        app = binaries / 'Game.app'
        app.mkdir(parents=True)
        (app / 'game').write_bytes(b'executable')
        (app / 'linked').symlink_to('game')
        (binaries / 'Game.target').write_text(json.dumps({'TargetName': 'Game', 'Platform': 'Mac',
            'Configuration': 'Development', 'BuildProducts': [{'Path': '$(ProjectDir)/Binaries/Mac/Game.app'}]}))
    from pathlib import Path
    assert tool.dispatch(request, tmp_path, tmp_path / 'engine', run) == ['binaries.zip']
    assert commands[0][-1] == '-MaxParallelActions=3'
    assert commands[1][:5] == ['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent']
