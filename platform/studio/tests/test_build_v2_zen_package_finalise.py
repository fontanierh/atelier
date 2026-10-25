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
