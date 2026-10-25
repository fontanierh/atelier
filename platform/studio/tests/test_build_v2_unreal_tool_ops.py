"""Guarded-tool argv/receipt adapters, without launching any native work."""
import hashlib
import json

import pytest

from atelier.build_v2 import unreal_tool_ops as ops


def setup_compile(tmp_path, *, kind='editor'):
    engine = tmp_path / 'engine'
    project = tmp_path / 'project/Game.uproject'
    project.parent.mkdir()
    project.write_text('{}')
    binary = project.parent / 'Binaries/Mac/libUnrealEditor-Game.dylib'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'compiled')
    receipt = binary.parent / 'GameEditor.target'
    value = {'TargetName': 'GameEditor', 'Platform': 'Mac', 'Configuration': 'Development',
             'BuildProducts': [{'Path': '$(ProjectDir)/Binaries/Mac/' + binary.name}],
             'RuntimeDependencies': []}
    receipt.write_text(json.dumps(value))
    modules = binary.parent / 'UnrealEditor.modules'
    modules.write_text(json.dumps({'BuildId': 'test', 'Modules': {'Game': binary.name}}))
    return engine, project, binary, receipt, value


def test_compile_uses_existing_build_tool_with_explicit_worker_cap(tmp_path):
    engine, project, *_ = setup_compile(tmp_path)
    argv = ops.compile_argv(engine, project, 'GameEditor')
    assert argv[0] == str(engine / 'Engine/Build/BatchFiles/Mac/Build.sh')
    assert argv[1:4] == ['GameEditor', 'Mac', 'Development']
    assert argv[-1] == '-MaxParallelActions=3'
    assert ops.compile_argv(engine, project, 'Game', kind='game', configuration='Shipping')[3] == 'Shipping'
    with pytest.raises(ValueError):
        ops.compile_argv(engine, project, '../Other')


def test_receipt_inventory_covers_binary_receipt_module_map_and_dependencies(tmp_path):
    engine, project, binary, receipt, value = setup_compile(tmp_path)
    dependency = project.parent / 'runtime.json'
    dependency.write_text('{}')
    value['RuntimeDependencies'] = [{'Path': '$(ProjectDir)/runtime.json'}]
    receipt.write_text(json.dumps(value))
    result = ops.compile_products(engine, project, 'GameEditor', owned_roots=[project.parent])
    assert set(result['files']) == {binary, receipt, binary.parent / 'UnrealEditor.modules'}
    assert result['runtime_dependencies'] == (dependency,)
    dependency.unlink()
    with pytest.raises(FileNotFoundError):
        ops.compile_products(engine, project, 'GameEditor', owned_roots=[project.parent])


@pytest.mark.parametrize('defect', ['outside', 'missing', 'unlisted_module', 'wrong_target', 'unknown_variable', 'symlink'])
def test_incomplete_or_unowned_receipts_refuse(tmp_path, defect):
    engine, project, binary, receipt, value = setup_compile(tmp_path)
    if defect == 'outside':
        other = tmp_path / 'outside'
        other.write_bytes(b'other')
        value['BuildProducts'][0]['Path'] = str(other)
    elif defect == 'missing':
        binary.unlink()
    elif defect == 'unlisted_module':
        value['BuildProducts'] = [{'Path': str(receipt)}]
    elif defect == 'wrong_target':
        value['TargetName'] = 'Other'
    elif defect == 'unknown_variable':
        value['BuildProducts'][0]['Path'] = '$(OtherDir)/binary'
    elif defect == 'symlink':
        binary.unlink()
        binary.symlink_to(receipt)
    receipt.write_text(json.dumps(value))
    with pytest.raises((ValueError, FileNotFoundError)):
        ops.compile_products(engine, project, 'GameEditor', owned_roots=[project.parent])


def test_package_requires_exact_completed_upstream_bytes_and_never_cooks(tmp_path):
    engine, project, *_ = setup_compile(tmp_path)
    cooked = project.parent / 'Saved/Cooked/Mac'
    cooked.mkdir(parents=True)
    (cooked / 'global.bin').write_bytes(b'globals')
    inventory = {'global.bin': hashlib.sha256(b'globals').hexdigest()}
    argv = ops.package_argv(engine, project, 'Game', tmp_path / 'archive', cooked_root=cooked, cooked_files=inventory)
    assert '-skipbuild' in argv and '-skipcook' in argv
    assert '-cook' not in argv and '-cookall' not in argv and '-build' not in argv
    assert '-ubtargs=-MaxParallelActions=3' in argv
    (cooked / 'extra').write_bytes(b'undeclared')
    with pytest.raises(ValueError, match='complete upstream inventory'):
        ops.package_argv(engine, project, 'Game', tmp_path / 'archive', cooked_root=cooked, cooked_files=inventory)
    (cooked / 'extra').unlink()
    (cooked / 'global.bin').write_bytes(b'changed')
    with pytest.raises(ValueError, match='upstream identity'):
        ops.package_argv(engine, project, 'Game', tmp_path / 'archive', cooked_root=cooked, cooked_files=inventory)


def test_uat_environment_uses_existing_headless_repair_and_preserves_explicit_setting(tmp_path, monkeypatch):
    from atelier import setup
    monkeypatch.setattr(setup, 'headless_user_dir', lambda engine: tmp_path / 'tool-user')
    original = {'LC_ALL': 'C'}
    actual = ops.package_environment(tmp_path, original)
    assert original == {'LC_ALL': 'C'}
    assert actual['UE_HEADLESS_USER_DIR'] == str(tmp_path / 'tool-user')
    assert ops.package_environment(tmp_path, {'UE_HEADLESS_USER_DIR': '/explicit'})['UE_HEADLESS_USER_DIR'] == '/explicit'


def test_cooked_census_accepts_empty_sdk_directories_but_not_links(tmp_path):
    cooked = tmp_path / 'Cooked'
    empty = cooked / 'Game/Metadata/PipelineCaches'
    empty.mkdir(parents=True)
    payload = cooked / 'global.bin'
    payload.write_bytes(b'globals')
    inventory = {'global.bin': hashlib.sha256(b'globals').hexdigest()}
    assert ops.verify_cooked_files(cooked, inventory) == (payload,)
    with pytest.raises(ValueError, match='empty'):
        ops._regular_files(empty)  # UBT product requirements remain strict.
    (cooked / 'alias').symlink_to(empty, target_is_directory=True)
    with pytest.raises(ValueError, match='link'):
        ops.verify_cooked_files(cooked, inventory)
