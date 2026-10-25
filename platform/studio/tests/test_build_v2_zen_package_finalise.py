"""Native package finalization requires actual SDK restores and complete globals."""
import hashlib
from pathlib import Path

import pytest

from atelier.build_v2.zen_package_finalise import finalise, Refused


def setup(tmp_path):
    values = {}
    for name in ('project.uproject', 'ue.projectstore', 'runtime.uproject', 'record.cb', 'ScriptObjects.bin'):
        path = tmp_path / name
        path.write_bytes(name.encode())
        values[name] = path
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    args = dict(destination={'project': 'AtelierV2_Global', 'oplog': 'Mac',
        'project_file': str(values['project.uproject']), 'lifetime_marker': str(values['ue.projectstore'])},
        packages=[{'record_sha256': sha(values['record.cb']), 'locator': {'package': '/Game/Test',
            'dependency_key': 'a' * 40, 'entry_hash': 'b' * 40, 'record_path': str(values['record.cb']),
            'record_sha256': sha(values['record.cb'])}}], histories=[{'declared': 'history'}],
        global_histories=[{'declared': 'global-history'}], global_files=[{'clientpath': '/{project}/ScriptObjects.bin',
            'path': str(values['ScriptObjects.bin']), 'sha256': sha(values['ScriptObjects.bin'])}],
        output_dir=str(tmp_path / 'final'), library='Game', formats=['SF_METAL_SM5'],
        runtime_project=str(values['runtime.uproject']), input_key='d' * 64)
    calls = []
    def call(method, request):
        calls.append((method, request))
        if method == 'zen_package_request':
            return {**request, 'status': 'restored', 'root_hash': 'b' * 40, 'native_stored_key': 'a' * 40,
                    'installed_root_hash': 'c' * 40}
        if method == 'zen_finalise_request':
            root = Path(request['output_dir']); root.mkdir()
            filename = 'Global.metallib' if request['global_library'] else 'AssetRegistry.bin'
            path = root / filename; path.write_bytes(filename.encode())
            return {'version': 1, 'status': 'composed', 'packages': 0 if request['global_library'] else 1,
                    'global_library': request['global_library'], 'native_libraries': True,
                    'files': [{'path': filename, 'sha256': sha(path)}]}
        return {'version': 1, 'status': 'finalized'}
    return args, call, calls, values


def test_restore_then_native_shader_composition_then_exact_endcook(tmp_path):
    args, call, calls, _ = setup(tmp_path)
    result = finalise(**args, call=call)
    assert [method for method, _ in calls] == ['zen_package_request', 'zen_finalise_request',
                                              'zen_finalise_request', 'zen_end_cook_request']
    end = calls[-1][1]
    assert end['packages'] == [{'name': '/Game/Test', 'installed_root_hash': 'c' * 40}]
    assert {row['clientpath'] for row in end['globals']} == {'/{project}/ScriptObjects.bin',
        '/{project}/AssetRegistry.bin', '/{project}/Global.metallib'}
    assert result['endcook']['status'] == 'finalized'


@pytest.mark.parametrize('cause', ['record', 'stored', 'root', 'refused', 'libraries', 'roster', 'global'])
def test_changed_source_or_incomplete_native_finalization_refuses(tmp_path, cause):
    args, original, calls, values = setup(tmp_path)
    if cause == 'record': values['record.cb'].write_bytes(b'changed')
    if cause == 'global': values['ScriptObjects.bin'].write_bytes(b'changed')
    def call(method, request):
        result = original(method, request)
        if method == 'zen_package_request':
            if cause == 'stored': result['native_stored_key'] = 'e' * 40
            if cause == 'root': result['root_hash'] = 'f' * 40
            if cause == 'refused': result['status'] = 'refused'
        if method == 'zen_finalise_request':
            if cause == 'libraries': result['native_libraries'] = False
            if cause == 'roster' and not request['global_library']: result['packages'] = 2
        return result
    with pytest.raises(Refused):
        finalise(**args, call=call)
    assert all(method != 'zen_end_cook_request' for method, _ in calls)


def test_histories_use_frozen_archives_and_selected_package_rosters(tmp_path):
    from atelier.build_v2 import recipe_job
    from atelier.build_v2.zen_package_finalise import prepare_histories
    def shaders(root, library):
        root.mkdir(parents=True)
        for stem, suffix in (('ShaderAssetInfo', '.assetinfo.json'), ('ShaderArchive', '.ushaderbytecode'),
                             ('ShaderTypeInfo', '.stinfo')):
            (root / (stem + '-' + library + '-SF_METAL_SM5' + suffix)).write_bytes(stem.encode())
    cooked = tmp_path / 'cooked'
    shaders(cooked / 'FixtureGame/Content', 'FixtureGame')
    metadata = cooked / 'FixtureGame/Metadata'; metadata.mkdir()
    (metadata / 'DevelopmentAssetRegistry.bin').write_bytes(b'registry')
    (metadata / 'CookMetadata.ucookmeta').write_bytes(b'metadata')
    # Private transport bytes are retained in the archive but never shader inputs.
    (cooked / 'ue.projectstore').write_bytes(b'private locator')
    archive = tmp_path / 'metadata.tree.tar'; recipe_job.pack_root(cooked, archive)
    global_root = tmp_path / 'global'; shaders(global_root / 'Content', 'Global')
    carrier = {'version': 1, 'packages': [
        {'locator': {'package': name}, 'metadata_archive': str(archive),
         'metadata_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
        for name in ('/Game/A', '/Game/B')]}
    result = prepare_histories(carrier=carrier, global_root=global_root, folder=tmp_path / 'projection',
                              project_name='FixtureGame', library='FixtureGame', unpack=recipe_job.unpack_root)
    assert result['formats'] == ['SF_METAL_SM5']
    assert len(result['histories']) == 1
    assert result['histories'][0]['packages'] == ['/Game/A', '/Game/B']
    assert len(result['histories'][0]['files']) == 3
    assert result['global_histories'][0]['packages'] == []
    assert all('ue.projectstore' not in str(row) for row in result['histories'])


def test_missing_global_shader_triple_refuses_before_package_archive_use(tmp_path):
    from atelier.build_v2.zen_package_finalise import prepare_histories
    content = tmp_path / 'global/Content'; content.mkdir(parents=True)
    (content / 'ShaderArchive-Global-SF_METAL_SM5.ushaderbytecode').write_bytes(b'shaders')
    with pytest.raises((Refused, FileNotFoundError)):
        prepare_histories(carrier={'version': 1, 'packages': [{'locator': {'package': '/Game/A'}}]},
                          global_root=content.parent, folder=tmp_path / 'projection',
                          project_name='FixtureGame', library='FixtureGame',
                          unpack=lambda *_: pytest.fail('incomplete globals precede package archive reads'))
