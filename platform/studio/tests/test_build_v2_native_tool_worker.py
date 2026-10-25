"""Fixed native TOOL routes; no native execution in these focused tests."""
import io
import json
import hashlib

import pytest

from atelier.build_v2 import native_tool_worker as tool
from atelier.build_v2 import protocol


def package_carrier(tmp_path):
    request = job(tmp_path, 'unreal.package')
    request['params']['native_global'] = 'global'
    root = tmp_path / '.recipe-runtime'
    histories = root / 'native-histories'; histories.mkdir()
    global_archive = root / 'global-metadata.tree.tar'
    history = histories / 'texture.tree.tar'
    source = histories / 'texture.source'
    for path in (global_archive, history, source):
        path.write_bytes(b'certified immutable archive bytes')
        path.chmod(0o444)
    digest = hashlib.sha256(global_archive.read_bytes()).hexdigest()
    carrier = {'version': 1, 'global_metadata_archive': str(global_archive),
               'global_metadata_sha256': digest, 'packages': [{'slot': 'texture',
               'metadata_archive': str(history), 'metadata_sha256': digest,
               'source': {'path': str(source), 'sha256': digest}}]}
    path = root / 'native-packages.json'
    path.write_text(json.dumps(carrier)); path.chmod(0o400)
    return request, root, carrier


def test_package_private_carrier_survives_actual_view_bootstrap(tmp_path):
    request, root, _ = package_carrier(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='fresh reserved'):
        tool.recipe_job.prepare_view(request, tmp_path)
    reserved = tool.package_runtime(tmp_path)
    view, _, _ = tool.recipe_job.prepare_view(request, tmp_path, reserved=reserved)
    assert (view / 'Game.uproject').read_bytes() == b'{}'
    assert (root / 'tmp').is_dir()
    assert all(path.read_bytes() == raw for path, raw in before.items())
    with pytest.raises(ValueError, match='fresh reserved'):
        tool.recipe_job.prepare_view(request, tmp_path, reserved=reserved)


def test_actual_package_dispatch_reaches_finalization_with_private_carrier(tmp_path, monkeypatch):
    request, root, _ = package_carrier(tmp_path)
    request['params']['archive'] = 'archive'
    class Reached(Exception):
        pass
    def finalise(*args):
        assert (root / 'view/Game.uproject').read_bytes() == b'{}'
        assert (root / 'native-packages.json').is_file()
        raise Reached
    monkeypatch.setattr(tool, 'finalise_package', finalise)
    with pytest.raises(Reached):
        tool.dispatch(request, tmp_path, tmp_path / 'engine', lambda *a, **kw: None)


@pytest.mark.parametrize('mutation', ['extra', 'history_extra', 'changed', 'writable', 'link', 'escape', 'source_changed', 'source_escape'])
def test_package_bootstrap_rejects_unknown_changed_or_aliased_roles(tmp_path, mutation):
    request, root, carrier = package_carrier(tmp_path)
    archive = root / 'native-histories/texture.tree.tar'
    if mutation == 'extra':
        (root / 'unknown').write_bytes(b'unknown')
    elif mutation == 'history_extra':
        (archive.parent / 'unknown').write_bytes(b'unknown')
    elif mutation == 'changed':
        archive.chmod(0o644); archive.write_bytes(b'changed'); archive.chmod(0o444)
    elif mutation == 'writable':
        archive.chmod(0o644)
    elif mutation == 'link':
        archive.unlink(); archive.symlink_to(root / 'global-metadata.tree.tar')
    elif mutation == 'escape':
        carrier['packages'][0]['metadata_archive'] = str(tmp_path / 'outside.tree.tar')
        path = root / 'native-packages.json'; path.chmod(0o600)
        path.write_text(json.dumps(carrier)); path.chmod(0o400)
    elif mutation == 'source_changed':
        source = root / 'native-histories/texture.source'
        source.chmod(0o644); source.write_bytes(b'changed'); source.chmod(0o444)
    elif mutation == 'source_escape':
        carrier['packages'][0]['source']['path'] = str(tmp_path / 'outside.source')
        path = root / 'native-packages.json'; path.chmod(0o600)
        path.write_text(json.dumps(carrier)); path.chmod(0o400)
    with pytest.raises((ValueError, OSError)):
        reserved = tool.package_runtime(tmp_path)
        tool.recipe_job.prepare_view(request, tmp_path, reserved=reserved)
    assert not (root / 'view').exists()


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


def test_stock_cook_argv_is_explicit_package_no_refs_and_zen_source_namespace(tmp_path):
    args = tool.cook_argv(tmp_path / 'engine', tmp_path / 'Game.uproject', ['/Game/Asset'], 'a' * 64)
    assert '-package=/Game/Asset' in args
    assert '-cooksinglepackagenorefs' in args
    assert '-ZenStoreProject=AtelierV2_' + 'a' * 64 in args
    assert '-cookall' not in args and '-build' not in args
    with pytest.raises(ValueError, match='canonical package'):
        tool.cook_argv(tmp_path, tmp_path / 'Game.uproject', ['/Game/A+-run=other'], 'a' * 64)


def test_persistent_source_view_never_adopts_existing_key_scope(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'Game.uproject').write_text('{}')
    state = tmp_path / 'zen'
    view, protected = tool.persistent_cook_view(source, [str(source / 'Game.uproject')], 'a' * 64, state)
    assert view == state / 'projects' / ('a' * 64) / 'view'
    assert protected == [str(view / 'Game.uproject')]
    other = tmp_path / 'other'
    other.mkdir()
    with pytest.raises(FileExistsError):
        tool.persistent_cook_view(other, [], 'a' * 64, state)
    assert other.exists() and (view / 'Game.uproject').read_text() == '{}'


def test_mac_zip_validation_refuses_external_links_before_extract(tmp_path):
    import stat
    import zipfile
    archive = tmp_path / 'input.mac.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        info = zipfile.ZipInfo('Game.app/evil')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        stream.writestr(info, '../../outside')
    calls = []
    with pytest.raises(ValueError, match='escapes'):
        tool.restore_mac_zip(archive, tmp_path / 'Game.app', lambda *a, **kw: calls.append(a))
    assert not calls


def test_stock_cook_runs_before_fixed_native_capture_and_raw_record_publication(tmp_path, monkeypatch):
    from pathlib import Path
    request = job(tmp_path, 'unreal.cook.produce')
    data = tmp_path / 'inputs/data'; data.mkdir(parents=True)
    (data / 'runtime.json').write_text('{"actual":17}')
    request['inputs'] = [{'name': 'data', 'path': 'inputs/data'}]
    request['params']['recipe']['paths'] = {'Content/Data': 'inputs/data'}
    original_source_cook = tool.source_cook
    def source_with_declared_inputs(*args, **kwargs):
        view, project = args[1:3]
        assert str(project) in kwargs['protected']
        assert str(view / 'Content/Data') in kwargs['protected']
        assert (view / 'Content/Data/runtime.json').read_text() == '{"actual":17}'
        assert 'zen/projects' in str(view)
        return original_source_cook(*args, **kwargs)
    monkeypatch.setattr(tool, 'source_cook', source_with_declared_inputs)
    checkout = Path(__file__).resolve().parents[3]
    for source in sorted((checkout / tool.NATIVE_SOURCE_PREFIX).rglob('*')):
        if source.is_file() and (source.name == 'AtelierBuildWorker.uplugin' or source.suffix in ('.cs', '.cpp', '.h')):
            name = source.relative_to(checkout).as_posix()
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            request['code'].append(name)
    request['params'].update(packages=['/Game/Asset'], record_outputs={'/Game/Asset': 'build/record.cb'},
                             cook_root='build/cook-metadata')
    request['params']['recipe']['outputs'] = [{'path': 'build/record.cb', 'file': 'record.cb'},
                                            {'path': 'build/cook-metadata', 'file': 'metadata.tree.tar'}]
    class Callbacks:
        def __init__(self, *args):
            pass
        def close(self, success):
            assert success
    monkeypatch.setattr(tool, 'CookCallbacks', Callbacks)
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        if '-run=cook' in argv:
            cooked = Path(argv[1]).parent / 'Saved/Cooked/Mac'
            cooked.mkdir(parents=True)
            (cooked / 'ue.projectstore').write_bytes(b'stock marker')
            return
        assert '-run=pythonscript' in argv
        export = json.loads(Path(kwargs['env']['ATELIER_NATIVE_COOK_EXPORT']).read_bytes())
        assert export['native_source_digest'] == tool.native_source_digest(request, tmp_path)
        assert Path(kwargs['env']['ATELIER_NATIVE_COOK_EXPORT']).is_relative_to(tmp_path / '.recipe-runtime')
        reports = []
        for native in export['requests']:
            Path(native['record_path']).write_bytes(b'native retained CB')
            reports.append({key: native[key] for key in ('mode', 'project', 'oplog', 'source_package', 'input_key', 'runtime_project_file')})
            reports[-1].update(version=1, status='verified', source_dependency_evaluation='recorded_only',
                native_stored_key='a' * 40, root_hash='b' * 40, installed_root_hash='', attachments=1,
                record_io_hash='c' * 40, request_io_hash='d' * 40)
        Path(export['report']).write_text(json.dumps(reports))
    state = tmp_path / 'zen'
    (tmp_path / 'C3.uproject').write_text('{}')
    result = tool.dispatch(request, tmp_path, tmp_path / 'engine', run, source_key='a' * 64, zen_state_root=state, export_project=tmp_path / 'C3.uproject')
    assert result == ['metadata.tree.tar', 'record.cb']
    assert (tmp_path / 'output/record.cb').read_bytes() == b'native retained CB'
    assert '-run=cook' in calls[0] and '-run=pythonscript' in calls[1]
    assert (state / 'records' / ('a' * 64 + '.cb')).stat().st_mode & 0o777 == 0o444


def test_source_cook_rejects_partial_native_implementation_before_sdk_launch(tmp_path):
    request = job(tmp_path, 'unreal.cook.produce')
    with pytest.raises(ValueError, match='complete exporter implementation'):
        tool.native_source_digest(request, tmp_path)


def test_native_capture_checks_actual_compiled_source_before_invoking_native_api(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    configuration = tmp_path / 'request.json'
    configuration.write_text(json.dumps({'native_source_digest': 'a' * 64, 'requests': [],
                                        'report': str(tmp_path / 'report.json')}))
    monkeypatch.setenv('ATELIER_NATIVE_COOK_EXPORT', str(configuration))
    calls = []
    library = SimpleNamespace(native_context=lambda: json.dumps({'worker_source_digest': 'b' * 64}),
                              zen_package_request=lambda raw: calls.append(raw))
    monkeypatch.setitem(sys.modules, 'unreal', SimpleNamespace(AtelierBuildWorkerLibrary=library))
    with pytest.raises(RuntimeError, match='keyed implementation source'):
        exec(compile(tool.EXPORT_SOURCE, '<fixed-native-capture>', 'exec'), {})
    assert calls == []
    assert not (tmp_path / 'report.json').exists()


@pytest.mark.skipif(__import__('sys').platform != 'darwin', reason='macOS ditto transport')
def test_actual_ditto_roundtrip_keeps_framework_links_and_executable_mode(tmp_path):
    import subprocess
    root = tmp_path / 'source/Game.app'
    version = root / 'Contents/Frameworks/Test.framework/Versions/A'
    version.mkdir(parents=True)
    executable = version / 'Test'
    executable.write_bytes(b'not an executable; archive fixture')
    executable.chmod(0o755)
    (version.parent / 'Current').symlink_to('A')
    (version.parent.parent / 'Test').symlink_to('Versions/Current/Test')
    before = tool._tree(root)
    archive = tmp_path / 'Game.mac.zip'
    def run(argv, **kwargs):
        subprocess.run(argv, cwd=kwargs['cwd'], check=True, timeout=10)
    run(tool.zip_argv(root, archive), cwd=tmp_path)
    destination = tmp_path / 'restored/Game.app'
    destination.parent.mkdir()
    tool.restore_mac_zip(archive, destination, run)
    assert tool._tree(destination) == before


def test_global_cook_keeps_global_shader_saving_and_explicit_shader_archive_policy():
    from pathlib import Path
    engine, project, key = Path('/engine'), Path('/view/Game.uproject'), 'a' * 64
    normal = tool.cook_argv(engine, project, ['/Game/Asset'], key)
    global_args = tool.cook_argv(engine, project, ['/Engine/EngineResources/DefaultTexture'], key, global_data=True)
    assert '-cooksinglepackagenorefs' in normal and '-cooksinglepackagenorefs' not in global_args
    assert {'-NoDefaultMaps', '-NoGameAlwaysCook', '-SkipHardReferences', '-SkipSoftReferences'} <= set(global_args)
    for args in (normal, global_args):
        assert '-ini:Game:[/Script/UnrealEd.ProjectPackagingSettings]:bShareMaterialShaderCode=True' in args
        assert '-ini:Game:[/Script/UnrealEd.ProjectPackagingSettings]:bSharedMaterialNativeLibraries=True' in args


def test_semantic_global_projection_keeps_complete_shader_bytes_excludes_transport(tmp_path):
    from atelier.build_v2.native_tool_worker import semantic_global_data, Refused
    import pytest
    source = tmp_path / 'cooked'
    content = source / 'Game/Metadata/ShaderLibrarySource'
    content.mkdir(parents=True)
    roles = {'ShaderAssetInfo':'.assetinfo.json','ShaderArchive':'.ushaderbytecode','ShaderTypeInfo':'.stinfo'}
    expected = {}
    for format_ in ('SF_METAL_SM5-METAL_SM5','SF_METAL_SM6-METAL_SM6'):
        for prefix, suffix in roles.items():
            name = prefix + '-Global-' + format_ + suffix
            expected[name] = name.encode()
            (content / name).write_bytes(expected[name])
    (source/'Engine').mkdir()
    for platform in ('METAL_SM5','METAL_SM6'):
        (source/'Engine'/('GlobalShaderCache-'+platform+'.bin')).write_bytes(platform.encode())
    (source / 'ue.projectstore').write_text('namespace A')
    (source / 'atelier-native-cook.json').write_text('transport only')
    (source / 'CookStats.txt').write_text('statistics')
    staging=source/'Game/Content';staging.mkdir()
    for name in expected: (staging/name).write_bytes(b'not the canonical source archive')
    first = tmp_path / 'first'
    assert semantic_global_data(source, first, 'Game') == ['SF_METAL_SM5-METAL_SM5','SF_METAL_SM6-METAL_SM6']
    assert {p.name:p.read_bytes() for p in (first/'Content').iterdir()} == expected
    assert {p.name for p in first.iterdir()} == {'Content','Engine'}
    (source/'ue.projectstore').write_text('namespace B')
    second=tmp_path/'second';semantic_global_data(source,second,'Game')
    assert {p.name:p.read_bytes() for p in (second/'Content').iterdir()} == expected
    engine = tmp_path / 'engine'; project = tmp_path / 'project'
    runtime = engine / 'Engine/Content/Internationalization/English/data.bin'
    runtime.parent.mkdir(parents=True); runtime.write_bytes(b'actual selected culture')
    project.mkdir(); descriptor = project / 'Game.uproject'; descriptor.write_text('{}')
    data = project / 'Content/Data/runtime.json'; data.parent.mkdir(parents=True); data.write_text('{"value":17}')
    data.chmod(0o444)
    plugin = tmp_path / 'declared-plugin/Content/font.bin'
    plugin.parent.mkdir(parents=True); plugin.write_bytes(b'produced keyed plugin bytes')
    sibling = project / 'Content/undeclared.bin'; sibling.write_bytes(b'not in the declared input')
    generated = source / 'Game/Runtime/generated.bin'; generated.parent.mkdir(); generated.write_bytes(b'complete producer output')
    scopes = {'engine_root': engine, 'project_root': project,
              'protected': [descriptor, data.parent, plugin.parent.parent]}
    ledger = content.parent / 'zenfs.manifest'
    rows = ['1' * 24 + ', Engine/Content/Internationalization/English/data.bin, /{engine}/Content/Internationalization/data.bin',
            '2' * 24 + ', ../project/Game.uproject, /{project}/Game.uproject',
            '3' * 24 + ', ignored-private-statistics, /{project}/Metadata/CookedSettings.txt',
            '4' * 24 + ', ../project/Content/Data/runtime.json, /{project}/Content/Data/runtime.json',
            '5' * 24 + ', ../declared-plugin/Content/font.bin, /{project}/Plugins/Declared/Content/font.bin',
            '6' * 24 + ', ../cooked/Game/Runtime/generated.bin, /{project}/Runtime/generated.bin']
    header = ';ServerRoot=private transport, Platform=Mac, CookDirectory=private transport\nFileId, ServerPath, ClientPath\n'
    ledger.write_text(header + '\n'.join(rows) + '\n')
    closed = tmp_path / 'closed'
    semantic_global_data(source, closed, 'Game', **scopes)
    assert (closed/'RuntimeFiles/Engine/Content/Internationalization/data.bin').read_bytes() == b'actual selected culture'
    assert (closed/'RuntimeFiles/Project/Game.uproject').read_text() == '{}'
    assert (closed/'RuntimeFiles/Project/Content/Data/runtime.json').read_bytes() == data.read_bytes()
    assert (closed/'RuntimeFiles/Project/Content/Data/runtime.json').stat().st_mode & 0o777 == 0o444
    assert (closed/'RuntimeFiles/Project/Plugins/Declared/Content/font.bin').read_bytes() == plugin.read_bytes()
    assert (closed/'RuntimeFiles/Project/Runtime/generated.bin').read_bytes() == generated.read_bytes()
    assert not any(p.name == 'zenfs.manifest' for p in closed.rglob('*'))
    runtime.write_bytes(b'ordinary changed runtime bytes')
    changed = tmp_path / 'changed-runtime'
    semantic_global_data(source, changed, 'Game', **scopes)
    assert (changed/'RuntimeFiles/Engine/Content/Internationalization/data.bin').read_bytes() != (closed/'RuntimeFiles/Engine/Content/Internationalization/data.bin').read_bytes()
    for suffix, invalid in [('escape', rows[0].replace('Engine/Content/Internationalization/English/data.bin', '../outside')),
                            ('duplicate', rows[0] + '\n' + rows[0]),
                            ('unknown-project', rows[2].replace('Metadata/CookedSettings.txt', 'unknown.bin')),
                            ('sibling', '6' * 24 + ', ../project/Content/undeclared.bin, /{project}/Content/undeclared.bin')]:
        ledger.write_text(header + invalid + '\n')
        with pytest.raises(ValueError):
            semantic_global_data(source, tmp_path/suffix, 'Game', **scopes)
    ledger.write_text(header + '\n'.join(rows) + '\n')
    with pytest.raises(ValueError, match='anchored declared'):
        semantic_global_data(source, tmp_path/'unbound-descriptor', 'Game', engine_root=engine, project_root=project)
    (content/'ShaderArchive-Global-SF_METAL_SM5-METAL_SM5.ushaderbytecode').unlink()
    with pytest.raises(Refused, match='complete Global'):
        semantic_global_data(source,tmp_path/'missing','Game')
    assert not (tmp_path/'missing').exists()
    (content/'ShaderArchive-Global-SF_METAL_SM5-METAL_SM5.ushaderbytecode').symlink_to(content/'ShaderArchive-Global-SF_METAL_SM6-METAL_SM6.ushaderbytecode')
    with pytest.raises(Refused, match='alias'):
        semantic_global_data(source,tmp_path/'alias','Game')


def test_package_composes_verified_inputs_before_uat_without_reading_source_namespace(tmp_path, monkeypatch):
    import hashlib
    from pathlib import Path
    from atelier.build_v2 import zen_package_finalise as finaliser
    runtime = tmp_path / '.recipe-runtime'; runtime.mkdir()
    view = tmp_path / 'view'; view.mkdir()
    project = view / 'Fixture.uproject'; project.write_text('{}')
    bootstrap = tmp_path / 'bootstrap/Worker.uproject'; bootstrap.parent.mkdir(); bootstrap.write_text('{}')
    plugin = bootstrap.parent / 'Plugins/AtelierBuildWorker/AtelierBuildWorker.uplugin'
    plugin.parent.mkdir(parents=True); plugin.write_text('{}')
    def shaders(content, name):
        content.mkdir(parents=True)
        for stem, suffix in (('ShaderAssetInfo', '.assetinfo.json'), ('ShaderArchive', '.ushaderbytecode'),
                             ('ShaderTypeInfo', '.stinfo')):
            (content / (stem + '-' + name + '-SF_METAL_SM5-METAL_SM5' + suffix)).write_bytes(stem.encode())
    source = tmp_path / 'transport'; shaders(source / 'Fixture/Metadata/ShaderLibrarySource', 'Fixture')
    metadata = source / 'Fixture/Metadata'
    for name in ('DevelopmentAssetRegistry.bin', 'CookMetadata.ucookmeta'):
        (metadata / name).write_bytes(name.encode())
    (metadata / 'zenfs.manifest').write_text(';ServerRoot=fixture, Platform=Mac, CookDirectory=fixture\n'
        'FileId, ServerPath, ClientPath\n' + '1' * 24 + ', Engine/Config/Base.ini, /{engine}/Config/Base.ini\n')
    (source / 'ue.projectstore').write_bytes(b'actual namespace marker')
    archive = runtime / 'global-metadata.tree.tar'; tool.recipe_job.pack_root(source, archive)
    globals_root = tmp_path / 'semantic'; shaders(globals_root / 'Content', 'Global')
    (globals_root / 'Engine').mkdir()
    (globals_root / 'Engine/GlobalShaderCache-METAL_SM5.bin').write_bytes(b'engine shaders')
    staged = tmp_path / 'inputs/global'; staged.mkdir(parents=True)
    tool.recipe_job.pack_root(globals_root, staged / 'global-data.tree.tar')
    record = tmp_path / 'package.cb'; record.write_bytes(b'CB')
    primary = tmp_path / 'uncooked.uasset'; primary.write_bytes(b'uncooked source fixture; no native SDK in this test')
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    destination = {'project': 'AtelierV2_Global', 'oplog': 'Mac', 'project_file': str(bootstrap),
                   'lifetime_marker': str(source / 'ue.projectstore')}
    carrier = {'version': 1, 'destination': destination, 'globals': ['global'], 'export_project': str(bootstrap),
        'global_metadata_archive': str(archive), 'global_metadata_sha256': sha(archive),
        'packages': [{'metadata_archive': str(archive), 'metadata_sha256': sha(archive),
            'source': {'path': str(primary), 'sha256': sha(primary)},
            'record_sha256': sha(record), 'locator': {'package': '/Game/A', 'dependency_key': 'a' * 40,
                'entry_hash': 'b' * 40, 'record_path': str(record), 'record_sha256': sha(record)}}]}
    carrier_file = runtime / 'native-packages.json'; carrier_file.write_text(json.dumps(carrier)); carrier_file.chmod(0o400)
    monkeypatch.setattr(tool, 'native_source_digest', lambda *_: 'c' * 64)
    monkeypatch.setattr(tool, '_sibling', lambda name: finaliser if name == 'zen_package_finalise' else pytest.fail(name))
    calls = []
    def run(argv, **kwargs):
        control = json.loads(Path(kwargs['env']['ATELIER_NATIVE_PACKAGE_FINALISE']).read_bytes())
        assert Path(argv[1]).name == 'AtelierV2Finalise.uproject'
        assert json.loads(Path(argv[1]).read_bytes())['Plugins'] == [{'Name': 'AtelierBuildWorker', 'Enabled': True}]
        def native(method, request):
            calls.append(method)
            if method == 'zen_package_request':
                return {**request, 'status': 'restored', 'native_stored_key': 'a' * 40,
                        'root_hash': 'b' * 40, 'installed_root_hash': 'd' * 40}
            if method == 'zen_finalise_request':
                output = Path(request['output_dir']); output.mkdir()
                filename = 'Global.metallib' if request['global_library'] else 'AssetRegistry.bin'
                (output / filename).write_bytes(filename.encode())
                return {'version': 1, 'status': 'composed', 'packages': 0 if request['global_library'] else 1,
                        'global_library': request['global_library'], 'native_libraries': True,
                        'files': [{'path': filename, 'sha256': sha(output / filename)}]}
            return {'version': 1, 'status': 'finalized', 'project': destination['project'], 'oplog': 'Mac',
                    'input_key': 'e' * 64, 'packages': 1}
        result = finaliser.finalise(**control['arguments'], call=native)
        Path(control['report']).write_text(json.dumps(result))
    (tmp_path / 'engine').mkdir()
    inventory = tool.finalise_package({'inputs': [{'name': 'global', 'path': 'inputs/global'}]},
        {'native_global': 'global'}, view, project, tmp_path / 'engine', tmp_path, run, {}, 'e' * 64)
    assert calls == ['zen_package_request', 'zen_finalise_request', 'zen_finalise_request', 'zen_end_cook_request']
    assert (view / 'Saved/Cooked/Mac/Fixture/AssetRegistry.bin').read_bytes() == b'AssetRegistry.bin'
    tool.ops.verify_cooked_files(view / 'Saved/Cooked/Mac', inventory)
    assert (view / 'Saved/Cooked/Mac/Engine/GlobalShaderCache-METAL_SM5.bin').read_bytes() == b'engine shaders'
    assert project.read_text() == '{}'


def test_uat_game_view_keeps_the_editor_input_unchanged(tmp_path, monkeypatch):
    view = tmp_path / 'view'; (view / 'Binaries/Mac').mkdir(parents=True)
    (tmp_path / '.recipe-runtime').mkdir()
    project = view / 'Fixture.uproject'; project.write_text('{}')
    editor = view / 'Binaries/Mac/libUnrealEditor-Fixture.dylib'; editor.write_bytes(b'editor')
    game = tmp_path / 'inputs/game'; game.mkdir(parents=True)
    archive = game / 'binary.mac.zip'; archive.write_bytes(b'archive')
    def restore(source, destination, run):
        assert source == archive
        destination.mkdir()
        (destination / 'Fixture.app').write_bytes(b'game')
    monkeypatch.setattr(tool, 'restore_mac_zip', restore)
    before = tool._tree(view)
    package_view, package_project = tool.package_project_view(
        {'inputs': [{'name': 'game', 'path': 'inputs/game'}]}, tmp_path, view, project, None)
    assert package_project == package_view / 'Fixture.uproject'
    assert tool._tree(view) == before
    assert (package_view / 'Binaries/Mac/Fixture.app').read_bytes() == b'game'
    assert not (package_view / 'Binaries/Mac/libUnrealEditor-Fixture.dylib').exists()


def test_archive_consumes_the_produced_app_and_controller_key(tmp_path, monkeypatch):
    from pathlib import Path
    request = job(tmp_path, 'package.archive')
    script = tmp_path / 'tools/package_archive.py'; script.parent.mkdir(); script.write_text('# keyed package body')
    request['code'].append('tools/package_archive.py')
    archive = tmp_path / 'inputs/archive/archive.mac.zip'; archive.parent.mkdir(parents=True); archive.write_bytes(b'produced app')
    request['inputs'] = [{'name': 'archive', 'path': 'inputs/archive'}]
    request['params']['recipe'].update(commands=[{'kind': 'python', 'script': 'tools/package_archive.py',
        'args': ['--out', {'path': 'download'}], 'env': {}}],
        outputs=[{'path': 'download', 'file': 'download.tree.tar', 'required': True}])
    request['outputs'] = [{'path': 'download.tree.tar'}]
    def restore(source, destination, run):
        assert source == archive
        destination.mkdir(); (destination / 'app').write_bytes(b'owned app')
    monkeypatch.setattr(tool, 'restore_mac_zip', restore)
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        assert (kwargs['cwd'] / 'download/archive/app').read_bytes() == b'owned app'
        (kwargs['cwd'] / 'download/manifest.json').write_text('{}')
    assert tool.dispatch(request, tmp_path, tmp_path / 'engine', run, source_key='f' * 64) == ['download.tree.tar']
    assert calls[0][-2:] == ['--revision', 'v2-' + 'f' * 64]
    assert '--cook-receipt' not in calls[0]
    assert archive.read_bytes() == b'produced app'


def test_compile_candidate_revalidates_inputs_and_runs_current_ubt(tmp_path, monkeypatch):
    from pathlib import Path
    old_job = tmp_path / 'old/job'; old_job.mkdir(parents=True)
    old = job(old_job)
    old_view, _, _ = tool.recipe_job.prepare_view(old, old_job)
    source = old_view / 'Source.cpp'; source.write_bytes(b'current source')
    retained = old_view / 'Intermediate'; retained.mkdir(); (retained / 'compiled.pch').write_bytes(b'preserved')
    cleanup = old_job.parent / 'guard/attempt-1/cleanup.json'; cleanup.parent.mkdir(parents=True)
    cleanup.write_text('{"confirmed":true}')
    fresh_job = tmp_path / 'fresh/job'; fresh_job.mkdir(parents=True)
    current = job(fresh_job)
    incoming = fresh_job / 'inputs/source'; incoming.parent.mkdir(); incoming.write_bytes(b'current source')
    current['inputs'] = [{'name': 'source', 'path': 'inputs/source'}]
    current['params']['recipe']['paths'] = {'Source.cpp': 'inputs/source'}
    monkeypatch.setenv('ATELIER_V2_COMPILE_VIEW', str(old_view))
    calls = []
    def run(argv, *, cwd, **kwargs):
        calls.append(cwd)
        assert cwd == old_view and (cwd / 'Intermediate/compiled.pch').read_bytes() == b'preserved'
        binaries = cwd / 'Binaries/Mac'; binaries.mkdir(parents=True)
        (binaries / 'Game.dylib').write_bytes(b'current compiled bytes')
        (binaries / 'UnrealEditor.modules').write_text(json.dumps({'BuildId': 'sdk', 'Modules': {'Game': 'Game.dylib'}}))
        (binaries / 'GameEditor.target').write_text(json.dumps({'TargetName': 'GameEditor', 'Platform': 'Mac',
            'Configuration': 'Development', 'BuildProducts': [{'Path': '$(ProjectDir)/Binaries/Mac/Game.dylib'}]}))
    assert tool.dispatch(current, fresh_job, tmp_path / 'engine', run) == ['binaries.tree.tar']
    assert calls == [old_view]
    assert (old_job / 'Game.uproject').read_bytes() == b'{}'
    assert (fresh_job / 'output/binaries.tree.tar').is_file()


@pytest.mark.parametrize('broken', ['cleanup', 'link'])
def test_compile_candidate_refuses_changed_inputs_and_unconfirmed_cleanup(tmp_path, broken):
    candidate = tmp_path / 'previous/job/.recipe-runtime/view'; candidate.mkdir(parents=True)
    cleanup = candidate.parents[2] / 'guard/attempt-1/cleanup.json'; cleanup.parent.mkdir(parents=True)
    cleanup.write_text('{"confirmed":true}')
    fresh = tmp_path / 'fresh'; fresh.mkdir()
    (fresh / 'Source.cpp').write_bytes(b'new')
    (candidate / 'Source.cpp').write_bytes(b'new' if broken != 'inputs' else b'old')
    request = {'code': [], 'params': {'recipe': {'paths': {'Source.cpp': 'inputs/source'}}}}
    if broken == 'cleanup': cleanup.write_text('{"confirmed":false}')
    if broken == 'link':
        alias = tmp_path / 'alias'; alias.symlink_to(candidate); candidate = alias
    with pytest.raises(tool.Refused):
        tool.compile_candidate(request, fresh, [str(fresh / 'Source.cpp')], candidate)


def test_game_receipt_keeps_owned_runtime_dependencies_portable(tmp_path):
    project = tmp_path / 'view/Game.uproject'; project.parent.mkdir(); project.write_text('{}')
    binaries = project.parent / 'Binaries/Mac'; binaries.mkdir(parents=True)
    (binaries / 'Game').write_bytes(b'actual compiled binary')
    descriptor = project.parent / 'Plugins/Owned/Owned.uplugin'
    descriptor.parent.mkdir(parents=True); descriptor.write_text('{}')
    receipt = binaries / 'Game.target'
    receipt.write_text(json.dumps({'TargetName': 'Game', 'Platform': 'Mac', 'Configuration': 'Development',
        'BuildProducts': [{'Path': str(binaries / 'Game')}],
        'RuntimeDependencies': [{'Path': str(descriptor)}]}))
    actual = tool.receipt_files(tmp_path / 'engine', project, 'Game', 'Development', 'game', owned_root=project.parent)
    assert set(actual) == {receipt, binaries / 'Game'}
    portable = json.loads(receipt.read_bytes())
    assert portable['BuildProducts'][0]['Path'] == '$(ProjectDir)/Binaries/Mac/Game'
    assert portable['RuntimeDependencies'][0]['Path'] == '$(ProjectDir)/Plugins/Owned/Owned.uplugin'
    assert str(project.parent) not in receipt.read_text()


def test_compile_candidate_clones_new_declared_input_and_accepts_code_readonly_mode(tmp_path):
    old = tmp_path / 'old/job/.recipe-runtime/view'; old.mkdir(parents=True)
    cleanup = old.parents[2] / 'guard/attempt-1/cleanup.json'; cleanup.parent.mkdir(parents=True)
    cleanup.write_text('{"confirmed":true}')
    fresh = tmp_path / 'fresh/job/.recipe-runtime/view'; fresh.mkdir(parents=True)
    (fresh / 'new.cpp').write_bytes(b'new declared source'); (fresh / 'new.cpp').chmod(0o444)
    (fresh / 'shared.py').write_bytes(b'same bytes')
    (old / 'shared.py').write_bytes(b'same bytes'); (old / 'shared.py').chmod(0o444)
    (old / 'new.cpp').write_bytes(b'prior source')
    (fresh / 'tools').mkdir(); (fresh / 'tools/check.py').write_bytes(b'# frozen verifier')
    request = {'code': ['tools/check.py'], 'params': {'recipe': {'paths': {'new.cpp':'inputs/new','shared.py':'inputs/shared'}}}}
    view, protected = tool.compile_candidate(request, fresh, [str(fresh / 'new.cpp')], old)
    assert view == old and protected == [str(old / 'new.cpp')]
    assert (old / 'new.cpp').read_bytes() == b'new declared source'
    assert (old / 'tools/check.py').read_bytes() == b'# frozen verifier'


@pytest.fixture
def relocated_modules(tmp_path, monkeypatch):
    from types import SimpleNamespace
    view, engine = tmp_path / 'view', tmp_path / 'sdk'
    project = view / 'game/Game.uproject'; project.parent.mkdir(parents=True)
    project.write_text(json.dumps({'AdditionalPluginDirectories': ['../platform/plugins']}))
    binaries = project.parent / 'Binaries/Mac'; binaries.mkdir(parents=True)
    images = [binaries / ('libUnrealEditor-' + name + '.dylib') for name in ('Game', 'Skate')]
    for image in images: image.write_bytes(b'certified produced module')
    def sdk(name, folder):
        directory = engine / 'Engine' / folder; directory.mkdir(parents=True)
        library = directory / ('libUnrealEditor-' + name + '.dylib'); library.write_bytes(b'installed SDK module')
        manifest = directory / 'UnrealEditor.modules'
        manifest.write_text(json.dumps({'BuildId': 'selected', 'Modules': {name: library.name}}))
        return library, manifest
    core, _ = sdk('Core', 'Binaries/Mac')
    physics, physics_manifest = sdk('PhysicsControl', 'Plugins/Animation/PhysicsControl/Binaries/Mac')
    unused, _ = sdk('Unused', 'Plugins/Unused/Binaries/Mac')
    calls = []
    def inspect(command, **options):
        calls.append((command, options))
        image = images[0] if command[-1] == str(images[0]) else images[1]
        dependencies = [image.name, 'libUnrealEditor-Core.dylib', 'libUnrealEditor-PhysicsControl.dylib']
        return SimpleNamespace(stdout=str(image) + ':\n' + ''.join(
            '\t@rpath/' + name + ' (compatibility version 5.8.0)\n' for name in dependencies))
    monkeypatch.setattr(tool.subprocess, 'run', inspect)
    return dict(view=view, engine=engine, project=project, images=images, core=core, physics=physics,
                manifest=physics_manifest, unused=unused, calls=calls, inspect=inspect)


def test_relocated_declared_module_dependencies_select_only_exact_sdk_directories(relocated_modules):
    r = relocated_modules; original = {'PATH': '/usr/bin:/bin'}
    before = {image: image.read_bytes() for image in r['images']}
    environment = tool.native_module_environment(r['engine'], r['view'], r['project'], original)
    assert environment == original | {'DYLD_LIBRARY_PATH': ':'.join(sorted({str(r['core'].parent), str(r['physics'].parent)}))}
    assert original == {'PATH': '/usr/bin:/bin'}
    assert str(r['unused'].parent) not in environment['DYLD_LIBRARY_PATH']
    assert len(r['calls']) == len(r['images'])
    assert all(command[:4] == ['/usr/bin/otool', '-arch', tool.os.uname().machine, '-L'] and options['timeout'] == 5 and options['check']
               for command, options in r['calls'])
    assert before == {image: image.read_bytes() for image in r['images']}


@pytest.mark.parametrize('change', ['missing', 'ambiguous', 'other_build', 'external_alias', 'manifest_alias'])
def test_unknown_ambiguous_or_escaping_sdk_roles_refuse_before_native_launch(relocated_modules, change):
    r = relocated_modules
    if change == 'missing': r['physics'].unlink()
    elif change == 'ambiguous':
        folder = r['engine'] / 'Engine/Plugins/Copy/Binaries/Mac'; folder.mkdir(parents=True)
        (folder / r['physics'].name).write_bytes(b'different image')
        (folder / 'UnrealEditor.modules').write_bytes(r['manifest'].read_bytes())
    elif change == 'other_build':
        value = json.loads(r['manifest'].read_bytes()); value['BuildId'] = 'other'; r['manifest'].write_text(json.dumps(value))
    elif change == 'external_alias':
        external = r['engine'].parent / 'foreign.dylib'; external.write_bytes(b'foreign')
        r['physics'].unlink(); r['physics'].symlink_to(external)
    else:
        external = r['engine'].parent / 'foreign.modules'; external.write_bytes(r['manifest'].read_bytes())
        r['manifest'].unlink(); r['manifest'].symlink_to(external)
    with pytest.raises(tool.Refused, match='SDK module'):
        tool.native_module_environment(r['engine'], r['view'], r['project'], {})


def test_native_loader_overrides_and_produced_aliases_never_become_search_paths(relocated_modules):
    r = relocated_modules
    with pytest.raises(tool.Refused, match='override'):
        tool.native_module_environment(r['engine'], r['view'], r['project'], {'DYLD_LIBRARY_PATH': '/foreign'})
    r['images'][0].unlink(); r['images'][0].symlink_to(r['physics'])
    with pytest.raises(tool.Refused, match='regular file'):
        tool.native_module_environment(r['engine'], r['view'], r['project'], {})


def test_project_plugin_roots_cannot_escape_declared_view(relocated_modules):
    r = relocated_modules; r['project'].write_text(json.dumps({'AdditionalPluginDirectories': ['../../../foreign']}))
    with pytest.raises(tool.Refused, match='escapes'):
        tool.native_module_environment(r['engine'], r['view'], r['project'], {})


def test_unknown_module_and_failed_metadata_inspection_remain_attributable(relocated_modules, monkeypatch):
    from types import SimpleNamespace
    r = relocated_modules
    monkeypatch.setattr(tool.subprocess, 'run', lambda command, **kw: SimpleNamespace(
        stdout=command[-1]+':\n\t@rpath/libUnrealEditor-Unknown.dylib (version 1)\n'))
    with pytest.raises(tool.Refused, match='unknown or ambiguous'):
        tool.native_module_environment(r['engine'], r['view'], r['project'], {})
    def failed(*a, **kw): raise tool.subprocess.TimeoutExpired('otool', 5)
    monkeypatch.setattr(tool.subprocess, 'run', failed)
    with pytest.raises(tool.Refused, match='inspection failed'):
        tool.native_module_environment(r['engine'], r['view'], r['project'], {})


def test_universal_metadata_header_binds_only_the_selected_native_architecture(relocated_modules, monkeypatch):
    from types import SimpleNamespace
    r = relocated_modules
    def universal(command, **options):
        assert command[1:4] == ['-arch', tool.os.uname().machine, '-L']
        return SimpleNamespace(stdout=command[-1]+' (architecture '+tool.os.uname().machine+'):\n'
            +'\t@rpath/libUnrealEditor-PhysicsControl.dylib (version 1)\n')
    monkeypatch.setattr(tool.subprocess, 'run', universal)
    x=tool.native_module_environment(r['engine'], r['view'], r['project'], {})
    assert x['DYLD_LIBRARY_PATH'] == str(r['physics'].parent)


@pytest.fixture
def additional_plugin_view(tmp_path):
    view = tmp_path / 'view'; project = view / 'games/game/unreal/Game.uproject'
    project.parent.mkdir(parents=True)
    project.write_text(json.dumps({'Modules': [{'Name': 'Game'}], 'AdditionalPluginDirectories': ['../../../platform/plugins']}))
    plugin = view / 'platform/plugins/Activities/Move/Move.uplugin'; plugin.parent.mkdir(parents=True)
    plugin.write_text(json.dumps({'CanContainContent': False, 'Modules': [{'Name': 'Move', 'Type': 'Runtime'}]}))
    binary = plugin.parent / 'Binaries/Mac/libUnrealEditor-Move.dylib'; binary.parent.mkdir(parents=True); binary.write_bytes(b'actual produced module')
    protected = list(map(str, (project, plugin, binary)))
    return view, project, plugin, binary, protected


def test_canonical_additional_plugins_copy_only_verified_bytes_and_keep_originals(additional_plugin_view):
    view, project, plugin, binary, protected = additional_plugin_view
    before = {path: path.read_bytes() for path in (plugin, binary)}
    relocations = {}
    result = tool.canonical_project_plugins(view, project, protected, relocations=relocations)
    assert relocations == {plugin.parent.relative_to(view).as_posix():
                           (project.parent / "Plugins/Move").relative_to(view).as_posix()}
    destination = project.parent / 'Plugins/Move'
    assert json.loads(project.read_bytes()) == {'Modules': [{'Name': 'Game'}], 'AdditionalPluginDirectories': []}
    assert (destination/'Move.uplugin').read_bytes() == before[plugin]
    assert (destination/'Binaries/Mac'/binary.name).read_bytes() == before[binary]
    assert before == {path: path.read_bytes() for path in before}
    assert str(destination/'Move.uplugin') in result
    assert str(destination/'Binaries/Mac'/binary.name) in result
    assert str(destination) not in result  # no future subtree grant
    assert tool.canonical_project_plugins(view, project, result) == result


@pytest.mark.parametrize('change', ['outside', 'descriptor_alias', 'extra_file', 'hardlink', 'content', 'collision'])
def test_canonical_plugin_projection_refuses_unearned_roles_before_descriptor_change(additional_plugin_view, change):
    view, project, plugin, binary, protected = additional_plugin_view
    original = project.read_bytes()
    if change == 'outside':
        project.write_text(json.dumps({'AdditionalPluginDirectories': ['../../../../foreign']})); original = project.read_bytes()
    elif change == 'descriptor_alias':
        import os
        real = plugin.with_suffix('.real'); plugin.rename(real); plugin.symlink_to(real)
    elif change == 'extra_file': (plugin.parent/'unlisted.bin').write_bytes(b'unbound')
    elif change == 'hardlink':
        import os
        os.link(binary, plugin.parent/'linked.bin')
    elif change == 'content': plugin.write_text(json.dumps({'CanContainContent': True}))
    else: (project.parent/'Plugins/Move').mkdir(parents=True)
    with pytest.raises(tool.Refused):
        tool.canonical_project_plugins(view, project, protected)
    assert project.read_bytes() == original


def test_uat_logs_and_actual_lifecycle_close_use_owned_runtime_with_readonly_job(tmp_path, monkeypatch):
    runtime = tmp_path / tool.recipe_job.RUNTIME
    runtime.mkdir()
    monkeypatch.setattr(tool.ops, 'package_environment', lambda engine, env: dict(env))
    tmp_path.chmod(0o555)
    original = {'uebp_LogFolder': '/Library/Logs/ambient'}
    def run(argv, **kwargs):
        assert argv == ['RunUAT']
        assert kwargs['env']['uebp_LogFolder'] == str(runtime / 'uat/logs')
        (runtime / 'uat/logs/Log.txt').write_text('actual UAT role')
    try:
        tool.run_package(['RunUAT'], job_dir=tmp_path, engine=tmp_path / 'engine',
                         cwd=runtime, environment=original, run=run)
        assert json.loads((runtime / 'uat/zen-lifecycle.json').read_bytes())['schema'] == 1
        assert not (tmp_path / 'zen-lifecycle.json').exists()
        assert original == {'uebp_LogFolder': '/Library/Logs/ambient'}
    finally:
        tmp_path.chmod(0o755)


def test_uat_first_failure_survives_secondary_lifecycle_close_error(tmp_path, monkeypatch):
    (tmp_path / tool.recipe_job.RUNTIME).mkdir()
    monkeypatch.setattr(tool.ops, 'package_environment', lambda engine, env: dict(env))
    class Lifecycle:
        def close(self):
            raise PermissionError('secondary scratch failure')
    monkeypatch.setattr(tool.ops, 'package_lifecycle', lambda *args: Lifecycle())
    first = RuntimeError('first UAT setup failure')
    def run(*args, **kwargs):
        raise first
    with pytest.raises(RuntimeError, match='first UAT setup failure') as caught:
        tool.run_package(['RunUAT'], job_dir=tmp_path, engine=tmp_path / 'engine',
                         cwd=tmp_path, environment={}, run=run)
    assert caught.value is first
    assert caught.value.__notes__ == ['UAT lifecycle close also failed: PermissionError']


@pytest.mark.parametrize('defect', [None, 'changed', 'alias', 'unknown'])
def test_game_receipt_relocates_all_verified_plugin_paths_only(tmp_path, defect):
    view = tmp_path / 'view'
    project = view / 'games/game/Game.uproject'
    project.parent.mkdir(parents=True); project.write_text('{}')
    mappings, entries = {}, []
    for name in ('Driving', 'Skate', 'Core', 'FX', 'Animation', 'Stream', 'Bridge'):
        old = view / 'platform/plugins' / name
        new = project.parent / 'Plugins' / name
        for root in (old, new):
            root.mkdir(parents=True); (root / (name + '.uplugin')).write_text('{}')
        mappings[old.relative_to(view).as_posix()] = new.relative_to(view).as_posix()
        entries.append({'Path': '$(ProjectDir)/../../platform/plugins/' + name + '/' + name + '.uplugin', 'Type': 'UFS'})
    receipt = project.parent / 'Binaries/Mac/Game.target'
    receipt.parent.mkdir(parents=True)
    value = {'TargetName': 'Game', 'TargetType': 'Game', 'BuildProducts': [], 'RuntimeDependencies': entries}
    receipt.write_text(json.dumps(value)); before = receipt.read_bytes()
    canonical = project.parent / 'Plugins/Driving/Driving.uplugin'
    if defect == 'changed': canonical.write_text('changed')
    elif defect == 'alias':
        canonical.unlink(); canonical.symlink_to(view / 'platform/plugins/Driving/Driving.uplugin')
    elif defect == 'unknown': del mappings['platform/plugins/Driving']
    if defect:
        with pytest.raises(tool.Refused): tool.canonical_package_receipt(view, project, 'Game', mappings)
        assert receipt.read_bytes() == before
    else:
        assert tool.canonical_package_receipt(view, project, 'Game', mappings) == 7
        for row in value['RuntimeDependencies']:
            name = row['Path'].split('/')[-1]
            row['Path'] = '$(ProjectDir)/Plugins/' + name[:-8] + '/' + name
        assert json.loads(receipt.read_bytes()) == value


def test_uat_game_view_binds_actual_verified_plugin_copy_map(additional_plugin_view, monkeypatch):
    view, project, plugin, binary, protected = additional_plugin_view
    runtime = view.parent / '.recipe-runtime'; runtime.mkdir()
    relocations = {}
    tool.canonical_project_plugins(view, project, protected, relocations=relocations)
    staged = view.parent / 'inputs/game'; staged.mkdir(parents=True)
    archive = staged / 'binary.mac.zip'; archive.write_bytes(b'frozen game input')
    original_receipt = {'TargetName': 'Game', 'TargetType': 'Game', 'BuildProducts': [],
                        'RuntimeDependencies': [{'Path': '$(ProjectDir)/../../../platform/plugins/Activities/Move/Move.uplugin', 'Type': 'UFS'}]}
    def restore(source, destination, run):
        destination.mkdir(parents=True)
        (destination / 'Game.target').write_text(json.dumps(original_receipt))
    monkeypatch.setattr(tool, 'restore_mac_zip', restore)
    package_view, package_project = tool.package_project_view(
        {'inputs': [{'name': 'game', 'path': 'inputs/game'}]}, view.parent, view, project, None,
        relocations=relocations, target='Game')
    result = json.loads((package_project.parent / 'Binaries/Mac/Game.target').read_bytes())
    assert result['RuntimeDependencies'] == [{'Path': '$(ProjectDir)/Plugins/Move/Move.uplugin', 'Type': 'UFS'}]
    assert archive.read_bytes() == b'frozen game input'
    assert plugin.read_bytes() == (package_project.parent / 'Plugins/Move/Move.uplugin').read_bytes()


@pytest.mark.parametrize('failure', [None, 'second', 'close', 'second+close'])
def test_source_frontier_preserves_keys_and_waits_for_sdk_close(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    jobs=[]
    for index in range(2):
        folder=tmp_path / str(index);folder.mkdir()
        request=job(folder,'unreal.cook.produce');request['job_id']=str(index);request['unit']='source.'+str(index)
        jobs.append({'job':request,'key':str(index+1)*64,'seconds':120.0})
    scope=tmp_path / 'frontier';scope.mkdir();control=scope/'control.json'
    control.write_text(json.dumps({'version':1,'jobs':jobs}));control.chmod(0o400)
    calls=[]
    class Sdk:
        def __init__(self,owner,folder):self.child=SimpleNamespace(pid=123);self.owner=owner
        def close(self):
            assert not (scope/'result.json').exists()
            calls.append('closed')
            if failure in ('close','second+close'):raise RuntimeError('uncertain native close')
    monkeypatch.setattr(tool,'CookSdkSession',Sdk)
    def dispatch(request,directory,engine,run,**kwargs):
        index=int(request['job_id']);assert kwargs['source_key']==jobs[index]['key']
        assert kwargs['cook_session'].owner.source_deadline>tool.time.monotonic()
        assert not (scope/'result.json').exists()
        calls.append(index)
        if index==1 and failure in ('second','second+close'):raise tool.Refused('second key failed')
        return ['records/'+str(index)+'.cb','cook-root.tree.tar']
    monkeypatch.setattr(tool,'dispatch',dispatch)
    worker=tool.Worker(io.BytesIO(),io.BytesIO(),tmp_path/'engine',source_batch=control)
    assert worker.source_frontier(jobs[0]['job'])==[]
    result=json.loads((scope/'result.json').read_bytes())
    assert [row['key'] for row in result['members']]==[row['key'] for row in jobs]
    assert calls==[0,1,'closed']
    assert result['sdk_processes']==1
    assert [row['status'] for row in result['members']]==(['failed','failed'] if failure in ('close','second+close') else ['completed','failed'] if failure=='second' else ['completed','completed'])
    if failure=='second+close':
        assert result['members'][1]['error'].startswith('second key failed; source SDK close:')


def test_source_frontier_duplicate_actual_key_refuses_before_effect(tmp_path,monkeypatch):
    request=job(tmp_path,'unreal.cook.produce');scope=tmp_path/'control';scope.mkdir()
    rows=[{'job':dict(request,job_id=str(index)),'key':'a'*64,'seconds':120} for index in range(2)]
    path=scope/'control.json';path.write_text(json.dumps({'version':1,'jobs':rows}));path.chmod(0o400)
    monkeypatch.setattr(tool,'CookSdkSession',lambda *args:pytest.fail('SDK must not start'))
    with pytest.raises(tool.Refused,match='roster differs'):
        tool.Worker(io.BytesIO(),io.BytesIO(),tmp_path/'engine',source_batch=path).source_frontier(rows[0]['job'])


def test_source_sdk_context_separates_native_payloads_but_binds_module_and_config(tmp_path):
    from types import SimpleNamespace
    project=tmp_path/'Game.uproject';project.write_text('{}')
    (tmp_path/'Content').mkdir();asset=tmp_path/'Content/A.uasset';asset.write_bytes(b'first')
    config=tmp_path/'Config';config.mkdir();ini=config/'DefaultEngine.ini';ini.write_bytes(b'keyed config')
    sdk=tool.CookSdkSession(SimpleNamespace(),tmp_path/'session')
    before=sdk.context(project)
    asset.write_bytes(b'second own package')
    assert sdk.context(project)==before
    loose=tmp_path/'Content/runtime.json';loose.write_bytes(b'common runtime data')
    assert sdk.context(project)!=before
    loose.unlink()
    ini.write_bytes(b'different keyed config')
    assert sdk.context(project)!=before


def test_source_sdk_host_injects_worker_only_in_independent_readonly_descriptor_copy(tmp_path,monkeypatch):
    from types import SimpleNamespace
    project=tmp_path/'source/Game.uproject';project.parent.mkdir();project.write_text('{}');project.chmod(0o444)
    folder=tmp_path/'session';folder.mkdir()
    owner=SimpleNamespace(engine=tmp_path/'engine')
    def popen(command,**kwargs):
        host=folder/'sdk-host/Game.uproject'
        assert host.read_bytes()!=project.read_bytes() and project.read_bytes()==b'{}'
        assert json.loads(host.read_bytes())['Plugins']==[{'Name':'AtelierBuildWorker','Enabled':True}]
        assert len(kwargs['pass_fds'])==2
        assert '-RunAsCookCommandlet' in command
        return SimpleNamespace(poll=lambda:0,returncode=0)
    monkeypatch.setattr(tool.subprocess,'Popen',popen)
    sdk=tool.CookSdkSession(owner,folder)
    monkeypatch.setattr(sdk,'exchange',lambda *args,**kwargs:{'status':'ready'})
    sdk.start(project,{},'a'*64,tmp_path/'bootstrap/Host.uproject')
    sdk.close()


def test_fixed_source_sdk_program_compiles_before_native_launch():
    compile(tool.SOURCE_COOK_SESSION,'fixed-source-sdk-session.py','exec')


@pytest.mark.parametrize("mutate", [False, True])
def test_source_sdk_cook_checks_exact_retained_overlay_inputs(tmp_path, monkeypatch, mutate):
    from types import SimpleNamespace
    project=tmp_path/'own/Game.uproject';project.parent.mkdir();project.write_text('{}')
    content=project.parent/'Content';content.mkdir();asset=content/'A.uasset';asset.write_bytes(b'keyed native input')
    host=tmp_path/'host';host.mkdir();(host/'Content').mkdir()
    sdk=tool.CookSdkSession(SimpleNamespace(),tmp_path/'session')
    sdk.project=host/'Game.uproject'
    monkeypatch.setattr(sdk,'start',lambda *args,**kwargs:None)
    def exchange(mode,**kwargs):
        assert mode=='cook' and kwargs['request']['project_file']==str(project)
        assert not list((host/'Content').iterdir())
        if mutate:asset.write_bytes(b'unexpected mutation')
        return dict(status='cooked',game_unloaded=True,source_key='a'*64,project_file=str(project),
                    package='/Game/A',project='AtelierV2_'+'a'*64)
    monkeypatch.setattr(sdk,'exchange',exchange)
    if mutate:
        with pytest.raises(tool.Refused,match='retained native inputs'):
            sdk.cook(project,{},'b'*64,tmp_path/'Bootstrap.uproject','a'*64,'/Game/A',None,tmp_path/'log')
    else:
        sdk.cook(project,{},'b'*64,tmp_path/'Bootstrap.uproject','a'*64,'/Game/A',None,tmp_path/'log')
        assert asset.read_bytes()==b'keyed native input'


def test_source_sdk_close_reaps_own_process_without_waiting_for_inherited_pipe_eof(tmp_path,monkeypatch,capsys):
    import os
    from types import SimpleNamespace
    read,held_service_write=os.pipe();request,response=os.pipe()
    stream=os.fdopen(read,'rb',buffering=0);os.write(held_service_write,b'owned SDK exiting\n')
    child=SimpleNamespace(stdout=stream,returncode=None)
    polls=[]
    def poll():
        polls.append(1)
        if len(polls)>=3:child.returncode=0
        return child.returncode
    child.poll=poll
    child.communicate=lambda **kwargs:pytest.fail('shared-service EOF is not owned-process exit')
    sdk=tool.CookSdkSession(SimpleNamespace(),tmp_path);sdk.child=child
    sdk.request,sdk.response=request,response
    monkeypatch.setattr(sdk,'exchange',lambda *args,**kwargs:{'status':'stopped'})
    try:
        sdk.close()
        assert stream.closed and child.returncode==0
        assert 'owned SDK exiting' in capsys.readouterr().err
        # This write end remains held by the simulated shared service throughout.
        os.fstat(held_service_write)
    finally:
        os.close(held_service_write)


def test_source_group_common_roots_use_validated_copies_and_clone_sdk_host(tmp_path,monkeypatch):
    import shutil
    from pathlib import Path
    from types import SimpleNamespace
    from atelier.build_v2.recipe_root_clones import CommonRootClones
    source=tmp_path/'editor';source.mkdir();(source/'Game.dylib').write_bytes(b'compiled immutable module')
    session=tmp_path/'session';session.mkdir()
    sdk=tool.CookSdkSession(SimpleNamespace(engine=tmp_path/'engine'),session)
    cloned=[]
    def clone(source,target):
        cloned.append(Path(target));shutil.copyfile(source,target)
    sdk.root_clones=CommonRootClones(session/'common-roots',clone=clone)
    clone_codec=CommonRootClones.materialize.__globals__['recipe_job']
    ordinary_unpack=clone_codec.unpack_root
    unpack_calls=[]
    def unpack(*args,**kwargs):
        unpack_calls.append(True)
        assert len(unpack_calls)==1,'repeated common ROOT must not unpack again'
        return ordinary_unpack(*args,**kwargs)
    monkeypatch.setattr(clone_codec,'unpack_root',unpack)
    copies=[]
    for name in ('first','second'):
        directory=tmp_path/name;directory.mkdir();request=job(directory,'unreal.cook.produce')
        request['params']['recipe']['outputs']=[{'path':'record.cb','file':'record.cb'}]
        archive=directory/'inputs/editor/outputs/0.tree.tar';archive.parent.mkdir(parents=True)
        tool.recipe_job.pack_root(source,archive)
        request['inputs']=[{'name':'editor','path':'inputs/editor'}]
        request['params']['recipe']['paths']={'Binaries/Mac':'inputs/editor/outputs/0.tree.tar'}
        view,_,_=tool.recipe_job.prepare_view(request,directory,materializer=sdk.materialize_root)
        sdk.share_prepared_roots(request,view);copies.append(view/'Binaries/Mac/Game.dylib')
    assert len(sdk.root_clones.snapshots)==1
    assert len(unpack_calls)==1
    assert copies[0].stat().st_ino!=copies[1].stat().st_ino
    def popen(command,**kwargs):
        host=session/'sdk-host/Binaries/Mac/Game.dylib'
        assert host.read_bytes()==source.joinpath('Game.dylib').read_bytes()
        assert host.stat().st_ino not in [p.stat().st_ino for p in copies]
        return SimpleNamespace(poll=lambda:0,returncode=0)
    monkeypatch.setattr(tool.subprocess,'Popen',popen)
    monkeypatch.setattr(sdk,'exchange',lambda *args,**kwargs:{'status':'ready'})
    sdk.start(view/'Game.uproject',{},'a'*64,tmp_path/'bootstrap/Host.uproject');sdk.close()
    assert session/'sdk-host/Binaries/Mac/Game.dylib' in cloned
    copies[1].write_bytes(b'independent later write')
    assert copies[0].read_bytes()==b'compiled immutable module'
    assert source.joinpath('Game.dylib').read_bytes()==b'compiled immutable module'


def test_source_group_missing_directory_is_not_a_cache_fallback(tmp_path):
    import shutil
    from types import SimpleNamespace
    request=job(tmp_path,'unreal.cook.produce')
    request['params']['recipe']['outputs']=[{'path':'record.cb','file':'record.cb'}]
    source=tmp_path/'source';source.mkdir();(source/'module').write_bytes(b'keyed')
    archive=tmp_path/'inputs/editor/root.tree.tar';archive.parent.mkdir(parents=True)
    tool.recipe_job.pack_root(source,archive)
    request['inputs']=[{'name':'editor','path':'inputs/editor'}]
    request['params']['recipe']['paths']={'Binaries/Mac':'inputs/editor/root.tree.tar'}
    view,_,_=tool.recipe_job.prepare_view(request,tmp_path)
    shutil.rmtree(view/'Binaries/Mac')
    session=tmp_path/'session';session.mkdir();sdk=tool.CookSdkSession(SimpleNamespace(),session)
    with pytest.raises(tool.Refused,match='disappeared'):
        sdk.share_prepared_roots(request,view)
    assert sdk.child is None and sdk.root_clones is None


def test_source_dispatch_clone_refusal_precedes_persistent_namespace(tmp_path,monkeypatch):
    from types import SimpleNamespace
    request=job(tmp_path,'unreal.cook.produce')
    def refuse(job,view):
        assert (view/'Game.uproject').is_file()
        raise ValueError('verified clone failed')
    monkeypatch.setattr(tool,'persistent_cook_view',lambda *a,**kw:pytest.fail('must not create namespace'))
    with pytest.raises(ValueError,match='verified clone failed'):
        tool.dispatch(request,tmp_path,tmp_path/'engine',lambda *a,**kw:None,
                      cook_session=SimpleNamespace(share_prepared_roots=refuse,materialize_root=lambda *a,**kw:None))


def test_request_pipe_cancellation_refuses_before_view_preparation(tmp_path):
    import os
    import io
    read,write=os.pipe()
    try:
        with os.fdopen(read,'rb',buffering=0)as requests,os.fdopen(write,'wb',buffering=0)as sender:
            worker=tool.Worker(requests,io.BytesIO(),tmp_path/'engine');worker.active='active'
            protocol.write_frame(sender,protocol.REQUEST,{'type':'cancel','job_id':'old'})
            protocol.write_frame(sender,protocol.REQUEST,{'type':'cancel','job_id':'active'})
            request=job(tmp_path,'unreal.cook.produce')
            with pytest.raises(tool.Refused,match='cancelled by controller'):
                tool.dispatch(request,tmp_path,tmp_path/'engine',lambda *a,**kw:pytest.fail('producer ran'),
                              check_cancelled=worker.check_cancelled)
            assert worker.stop and not (tmp_path/'.recipe-runtime/view').exists()
    except BaseException:
        for fd in(read,write):
            try:os.close(fd)
            except OSError:pass
        raise
