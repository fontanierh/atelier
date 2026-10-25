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


@pytest.mark.parametrize('broken', ['inputs', 'cleanup', 'link'])
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
    (fresh / 'new.cpp').write_bytes(b'new declared source')
    (fresh / 'shared.py').write_bytes(b'same bytes')
    (old / 'shared.py').write_bytes(b'same bytes'); (old / 'shared.py').chmod(0o444)
    request = {'code': [], 'params': {'recipe': {'paths': {'new.cpp':'inputs/new','shared.py':'inputs/shared'}}}}
    view, protected = tool.compile_candidate(request, fresh, [str(fresh / 'new.cpp')], old)
    assert view == old and protected == [str(old / 'new.cpp')]
    assert (old / 'new.cpp').read_bytes() == b'new declared source'
