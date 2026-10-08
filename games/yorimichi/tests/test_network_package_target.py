import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import types

import pytest

spec = importlib.util.spec_from_file_location('package_target', Path(__file__).resolve().parents[1] / 'tools/network_package_target.py')
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(target.Path, 'home', lambda: tmp_path)
    root = tmp_path / 'Yorimichi.app'
    exe = root / 'Contents/MacOS/Yorimichi'; exe.parent.mkdir(parents=True)
    exe.write_bytes(b'actual executable'); exe.chmod(0o755)
    (root / 'Contents/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleExecutable='Yorimichi', CFBundleIdentifier='test.yorimichi')))
    data = root / 'Contents/UE/Yorimichi/Content/Data/Network'; data.mkdir(parents=True)
    (data / 'session.json').write_text(json.dumps(dict(protocol=1, code='code', signature='signature')))
    pak = root / 'Contents/UE/Yorimichi/Content/Paks/data.pak'; pak.parent.mkdir();pak.write_bytes(b'cooked collision')
    monkeypatch.setattr(target.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a[0], 0))
    monkeypatch.setattr(target.subprocess, 'check_output', lambda *a, **kw: plistlib.dumps({}))
    monkeypatch.setitem(sys.modules, 'verify_network_package', types.SimpleNamespace(check_data=lambda *a: {'verified': True}))
    return root


def test_hashes_actual_binary_and_cooked_content(app):
    initial = target.package_fingerprint(app, '1:code:signature')
    (app / 'Contents/UE/Yorimichi/Content/Paks/data.pak').write_bytes(b'changed collision')
    changed = target.package_fingerprint(app, '1:code:signature')
    assert initial['app_sha256'] != changed['app_sha256']
    assert initial['executable_sha256'] == changed['executable_sha256']
    (app / 'Contents/MacOS/Yorimichi').write_bytes(b'changed executable')
    assert changed['executable_sha256'] != target.package_fingerprint(app, '1:code:signature')['executable_sha256']


@pytest.mark.parametrize('kind', ['executable', 'data', 'external', 'broken', 'missing-pak', 'identity'])
def test_refuse_invalid_targets(app, tmp_path, kind):
    if kind == 'executable':
        p=app/'Contents/MacOS/Yorimichi';p.rename(p.with_name('real'));p.symlink_to('real')
    elif kind == 'data':
        p=app/'Contents/UE/Yorimichi/Content/Data';p.rename(p.with_name('real'));p.symlink_to('real')
    elif kind in ('external', 'broken'):
        p=tmp_path/'outside';p.write_text('outside')
        (app/'redirect').symlink_to(p if kind=='external' else tmp_path/'missing')
    elif kind == 'missing-pak':
        (app/'Contents/UE/Yorimichi/Content/Paks/data.pak').unlink()
    with pytest.raises(RuntimeError):
        target.package_fingerprint(app, 'wrong' if kind=='identity' else '1:code:signature')


def test_signature_failure_fails(app, monkeypatch):
    def fail(*args, **kwargs): raise subprocess.CalledProcessError(1, args[0])
    monkeypatch.setattr(target.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError): target.package_fingerprint(app, '1:code:signature')


def test_internal_framework_link_recorded(app):
    (app/'internal-link').symlink_to('Contents/MacOS/Yorimichi')
    result=target.package_fingerprint(app, '1:code:signature')
    assert result['files'] == 4


def test_sandbox_local_unique_runtime(app):
    folder=target.runtime_directory(app, 'run-1')
    command=target.packaged_command(app, '/Game/Japan/Maps/Slice?listen', 'server', folder, ['-game', '-nullrhi'])
    assert command[0].endswith('/Yorimichi.app/Contents/MacOS/Yorimichi')
    assert not any('.uproject' in x or 'UnrealEditor' in x for x in command)
    assert str(folder) in command[-1] and str(folder) in command[-2]
    with pytest.raises(FileExistsError): target.runtime_directory(app, 'run-1')
    with pytest.raises(RuntimeError): target.runtime_directory(app, '../escape')
    with pytest.raises(RuntimeError): target.packaged_command(app, 'map', 'client', app.parent, [])


def test_redirected_runtime_parent_refused(app, tmp_path):
    base=tmp_path/'Library/Containers/test.yorimichi/Data';base.parent.mkdir(parents=True)
    base.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RuntimeError): target.runtime_directory(app, 'run-2')


@pytest.mark.parametrize('bad', ['identity', 'code', 'target', 'digest', 'missing'])
def test_runtime_identity_checks_actual_compiled_fields(tmp_path, bad):
    import hashlib
    identity, source = '1:' + 'a'*40 + ':' + 'b'*40, 'a'*40
    receipt = dict(identity=identity, compiled_source_revision=source, compiled_code_digest='a'*40,
                   compiled_target='Mac/Game/Development',
                   compiled_input_digest=hashlib.sha256(('a'*40+'\nMac/Game/Development\n').encode()).hexdigest())
    for role in ('server', 'client'):
        (tmp_path/(role+'-connected.json')).write_text(json.dumps(receipt))
    assert all(target.runtime_identity_checks(tmp_path, identity, source).values())
    if bad == 'missing': receipt.clear()
    else:
        key = dict(identity='identity', source='compiled_source_revision', code='compiled_code_digest',
                   target='compiled_target', digest='compiled_input_digest')[bad]
        receipt[key] = 'unprepared'
    for role in ('server', 'client'):
        (tmp_path/(role+'-connected.json')).write_text(json.dumps(receipt))
    assert not any(target.runtime_identity_checks(tmp_path, identity, source).values())


def test_matching_unprepared_values_are_not_build_identity(tmp_path):
    receipt=dict(identity='1:unprepared:signature', compiled_source_revision='unversioned',
                 compiled_code_digest='unprepared', compiled_target='Mac/Game/Development')
    for role in ('server', 'client'):
        (tmp_path/(role+'-connected.json')).write_text(json.dumps(receipt))
    assert not any(target.runtime_identity_checks(tmp_path, receipt['identity'], 'unversioned').values())


@pytest.mark.parametrize('mutation', ['ready', 'deadline', 'flags', 'reaction', 'missing_reaction', 'code', 'receipt', 'reaction_receipt'])
def test_plain_launch_requires_positive_inactive_evidence(tmp_path, mutation):
    import hashlib
    code='a'*40; digest=hashlib.sha256((code+'\nMac/Game/Development\n').encode()).hexdigest()
    text=f'Character ready: Cairo\nNETWORK diagnostics session=0 gameplay=0 combat=0 enemy=0 vehicles=0 reaction=0 code={code} target=Mac/Game/Development input={digest}\nFEngineLoop::Tick.Benchmarking'
    assert all(target.plain_launch_checks(tmp_path, text, 0, code).values())
    if mutation=='ready': text=text.replace('Character ready:', 'not initialized')
    elif mutation=='deadline': text=text.replace('FEngineLoop::Tick.Benchmarking','crashed')
    elif mutation=='flags': text=text.replace('enemy=0','enemy=1')
    elif mutation=='reaction': text=text.replace('reaction=0','reaction=1')
    elif mutation=='missing_reaction': text=text.replace(' reaction=0','')
    elif mutation=='code': text=text.replace('code='+code,'code=unprepared')
    elif mutation=='reaction_receipt': (tmp_path/'reaction-client.json').write_text('{}')
    else: (tmp_path/'vehicle-result.json').write_text('{}')
    assert not all(target.plain_launch_checks(tmp_path, text, 0, code).values())


@pytest.mark.parametrize('mutation', ['sha', 'size', 'missing', 'extra', 'source', 'identity'])
def test_package_cannot_use_an_unrelated_cook_receipt(mutation):
    name='Contents/UE/Yorimichi/Content/Paks/content.pak'
    cook=dict(files={name:dict(bytes=42, sha256='a'*64)})
    source=dict(code_digest='b'*40)
    identity='1:'+'b'*40+':'+'c'*40
    binary=dict(identity=identity,cooked_containers=[('file',name,0o644,42,'a'*64)])
    assert all(target.cook_binding_checks(cook,binary,source,identity).values())
    if mutation=='sha': cook['files'][name]['sha256']='d'*64
    elif mutation=='size': cook['files'][name]['bytes']=43
    elif mutation=='missing': cook['files'].clear()
    elif mutation=='extra': binary['cooked_containers'].append(('file',name+'2.pak',0o644,42,'a'*64))
    elif mutation=='source': source['code_digest']='e'*40
    else: binary['identity']='1:'+'f'*40+':'+'c'*40
    assert not all(target.cook_binding_checks(cook,binary,source,identity).values())
