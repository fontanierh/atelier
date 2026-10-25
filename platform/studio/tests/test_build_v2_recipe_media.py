"""Fixed media SDK/argv boundaries, with fake installed images and no native jobs."""
from copy import deepcopy
from pathlib import Path
import subprocess
import threading

import pytest

from atelier.build_v2 import recipe_media as media
from atelier.build_v2 import recipe_node


@pytest.fixture
def setup(tmp_path, monkeypatch):
    platform = tmp_path / 'platform'
    binaries = platform / 'audio/bin'
    binaries.mkdir(parents=True)
    for name in ('ffmpeg', 'ffprobe'):
        (binaries / name).write_bytes(b'fake installed SDK image')
    monkeypatch.setattr(media, 'INSTALL_ROOT', platform)
    for name in ('OPENSSL_CONF', 'OPENSSL_CONF_INCLUDE', 'OPENSSL_MODULES'):
        monkeypatch.delenv(name, raising=False)
    sdk = {'version': 1, **{name: {'version': 1, 'image': str(binaries / name),
        'executable': str(binaries / name), 'read_literals': [str(binaries / name)],
        'openssl_config': None} for name in ('ffmpeg', 'ffprobe')}}
    view, scratch = tmp_path / 'view', tmp_path / 'scratch'
    view.mkdir(); scratch.mkdir()
    source = view / 'inputs/master.wav'
    source.parent.mkdir()
    source.write_bytes(b'RIFF\0\0\0\0WAVE source fixture')
    output = view / 'out/mono.wav'
    output.parent.mkdir()
    execution = media.MediaExecution(sdk, view, scratch, inputs=[source.parent], writes=[output.parent])
    return sdk, execution, source, output


def mono(source, output):
    return ['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-ac', '1', '-ar', '48000', '-sample_fmt', 's16', str(output)]


def probe(source):
    return ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=channels', '-of', 'csv=p=0', str(source)]


def floating(source):
    return ['ffmpeg', '-v', 'error', '-i', str(source), '-map', '0:a:0', '-ar', '48000', '-f', 'f32le', '-']


def test_discovery_reuses_complete_installed_metadata_and_explicit_paths_avoid_path_lookup(setup, monkeypatch):
    sdk, _, _, _ = setup
    calls = []
    def discover(role):
        calls.append(role)
        return deepcopy(next(tool for name, tool in sdk.items() if name != 'version' and tool['executable'] == role))
    monkeypatch.setattr(recipe_node, 'discover_node', discover)
    monkeypatch.setattr(media.shutil, 'which', lambda name: pytest.fail('explicit SDK lookup must not use PATH'))
    assert media.discover_media(sdk['ffmpeg']['executable'], sdk['ffprobe']['executable']) == sdk
    assert calls == [sdk['ffmpeg']['executable'], sdk['ffprobe']['executable']]
    assert not any('hash' in key or 'digest' in key for tool in (sdk['ffmpeg'], sdk['ffprobe']) for key in tool)


def test_platform_permissions_do_not_grant_project_or_network_access(setup):
    sdk, execution, _, _ = setup
    permissions = media.permissions(sdk)
    assert permissions['executables'] == [sdk[name]['image'] for name in ('ffmpeg', 'ffprobe')]
    assert str(execution.view) not in permissions['read_subpaths']
    assert not any('network' in rule for rule in permissions['extra_rules'])
    bad = deepcopy(sdk)
    bad['ffmpeg']['read_literals'].append(str(execution.view / 'secret'))
    with pytest.raises(ValueError, match='installed platform'):
        media.permissions(bad)


@pytest.mark.parametrize('shape', ['mono', 'probe', 'float'])
def test_exact_original_audio_shapes_select_absolute_images_and_fixed_worker_policy(setup, shape):
    sdk, execution, source, output = setup
    argv, kwargs = {'mono': (mono(source, output), {}), 'probe': (probe(source), {
        'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'text': True}), 'float': (floating(source), {
        'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE})}[shape]
    actual = execution.validate(argv, (), kwargs)
    assert actual[0] == sdk['ffprobe' if shape == 'probe' else 'ffmpeg']['image']
    if shape != 'probe':
        assert actual[1:8] == ['-threads', '3', '-filter_threads', '3', '-nostdin', '-protocol_whitelist', 'file,pipe']
        assert actual[8:] == argv[1:]


@pytest.mark.parametrize('defect', ['rate', 'format', 'network', 'extra_arg', 'shell', 'environment', 'descriptors', 'cwd'])
def test_arbitrary_subprocess_shapes_refuse(setup, defect):
    _, execution, source, output = setup
    argv, kwargs = mono(source, output), {}
    if defect == 'rate':
        argv[9] = '44100'
    elif defect == 'format':
        argv[11] = 'flt'
    elif defect == 'network':
        argv[5] = 'https://example.test/source.wav'
    elif defect == 'extra_arg':
        argv.insert(1, '-filter_complex')
    elif defect == 'shell':
        kwargs['shell'] = True
    elif defect == 'environment':
        kwargs['env'] = {'PATH': '/foreign'}
    elif defect == 'descriptors':
        kwargs['pass_fds'] = (7,)
    else:
        kwargs['cwd'] = str(execution.view)
    with pytest.raises(ValueError):
        execution.validate(argv, (), kwargs)


def test_only_initial_keyed_inputs_and_declared_owned_writes_are_eligible(setup):
    _, execution, source, output = setup
    unkeyed = source.with_name('later.wav')
    unkeyed.write_bytes(b'producer-created data')
    with pytest.raises(ValueError, match='unchanged declared'):
        execution.validate(mono(unkeyed, output), (), {})
    with pytest.raises(ValueError, match='write role'):
        execution.validate(mono(source, execution.view / 'unowned.wav'), (), {})
    linked = execution.scratch / 'linked.wav'
    linked.symlink_to(source)
    with pytest.raises(ValueError):
        execution.validate(mono(source, linked), (), {})
    source.write_bytes(b'mutated declared input')
    with pytest.raises(ValueError, match='unchanged declared'):
        execution.validate(mono(source, output), (), {})


def test_popen_rewrite_preserves_original_run_capture_check_and_one_use_audit_grants(setup, monkeypatch):
    _, execution, source, output = setup
    launched = []
    class Process:
        def __init__(self, argv, **kwargs):
            self.args, self.returncode = argv, 0
            launched.append((argv, kwargs))
            audit = (argv[0], argv, kwargs['cwd'], kwargs['env'])
            assert not execution.allow_subprocess((argv[0], argv, '/foreign', kwargs['env']))
            assert execution.allow_subprocess(audit)
            assert not execution.allow_subprocess(audit)
            self.text = kwargs.get('text', False)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def communicate(self, *args, **kwargs):
            return ('2\n', '') if self.text else (b'decoded', b'')
        def poll(self):
            return self.returncode
    monkeypatch.setattr(subprocess, 'Popen', Process)
    with execution.install():
        assert subprocess.run(probe(source), capture_output=True, text=True, check=True).stdout == '2\n'
        assert subprocess.run(floating(source), capture_output=True, check=True).stdout == b'decoded'
        subprocess.run(mono(source, output), check=True)
    assert subprocess.Popen is Process
    assert execution._grant is None
    for argv, kwargs in launched:
        assert kwargs['close_fds'] is True and kwargs['cwd'] == str(execution.view)
        assert kwargs['env']['PATH'] == '' and 'shell' not in kwargs and 'pass_fds' not in kwargs


def test_caught_refusal_stays_failed_and_popen_is_restored(setup):
    _, execution, source, output = setup
    original = subprocess.Popen
    with pytest.raises(ValueError, match='refused audio subprocess'):
        with execution.install():
            try:
                subprocess.Popen(mono(source, output), shell=True)
            except ValueError:
                pass
    assert subprocess.Popen is original and execution._grant is None


def test_audit_grant_is_thread_bound_and_does_not_allow_other_process_events(setup):
    _, execution, source, output = setup
    command = execution.validate(mono(source, output), (), {})
    execution._grant = (command, threading.get_ident() + 1)
    assert not execution.allow_subprocess((command[0], command, str(execution.view), execution.environment))
    execution._grant = None
    assert not execution.allow_subprocess((command[0], command, str(execution.view), execution.environment))


def test_runtime_bootstrap_is_self_contained_stdlib_source(setup):
    sdk, execution, source, output = setup
    namespace = {'__name__': 'fixed_media_bootstrap'}
    exec(compile(Path(media.__file__).read_text(), '<fixed media bootstrap>', 'exec'), namespace)
    namespace['INSTALL_ROOT'] = media.INSTALL_ROOT
    runtime = namespace['MediaExecution'](sdk, execution.view, execution.scratch, inputs=[source], writes=[output.parent])
    assert runtime.validate(mono(source, output), (), {})[0] == sdk['ffmpeg']['image']


def test_existing_output_hardlink_refuses_before_native_overwrite(setup):
    import os
    _, execution, source, output = setup
    target = execution.scratch / 'other.wav'
    target.write_bytes(b'preserve')
    os.link(target, output)
    with pytest.raises(ValueError, match='independent canonical'):
        execution.validate(mono(source, output), (), {})
    assert target.read_bytes() == b'preserve'
