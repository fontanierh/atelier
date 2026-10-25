"""Fixed nested Node launch validation, independent of an installed SDK."""
import subprocess
import threading
from types import SimpleNamespace

import pytest

from atelier.build_v2 import recipe_node


@pytest.fixture
def launch(tmp_path, monkeypatch):
    sdk = {'version': 1, 'executable': '/installed/node', 'image': '/installed/node', 'read_literals': []}
    monkeypatch.setattr(recipe_node, 'permissions', lambda value: {})
    view = tmp_path / 'view'; view.mkdir()
    entry = view / 'entry.cjs'; entry.write_text('')
    scratch = tmp_path / 'tmp'; scratch.mkdir()
    work = scratch / 'generated'; (work / 'snap/data').mkdir(parents=True)
    (work / 'snap/park.json').write_text('{}')
    (work / 'mesh').mkdir()
    context = recipe_node.NodeExecution(sdk, view=view, scratch=scratch, entry=entry, sources=[entry])
    with (work / 'mesh/node.log').open('w') as log:
        argv = [sdk['executable'], '--max-old-space-size=1024', str(entry),
                str(work / 'snap/park.json'), str(work / 'snap/data'), str(work / 'mesh')]
        kwargs = {'stdout': log, 'stderr': subprocess.STDOUT, 'check': False, 'timeout': 600}
        yield context, argv, kwargs


def test_fixed_command_and_environment_are_the_only_one_shot_audit_grant(launch, monkeypatch):
    context, argv, kwargs = launch
    def run(command, **actual):
        assert command[0] == context.sdk['image'] and '--permission' in command
        assert '--allow-child-process' not in command and '--allow-addons' not in command
        assert actual['env'] == context.environment and actual['close_fds'] is True
        event = (command[0], command, actual['cwd'], actual['env'])
        wrong = (*event[:3], dict(actual['env'], NODE_OPTIONS='--inspect'))
        assert not context.allow_subprocess(wrong)
        assert context.allow_subprocess(event)
        assert not context.allow_subprocess(event)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess, 'run', run)
    with context.install():
        assert subprocess.run(argv, **kwargs).returncode == 0
    assert not context.allow_subprocess(('/bin/sh', [], None, None))


@pytest.mark.parametrize('change', ['executable', 'entry', 'shell', 'environment', 'cwd', 'pass_fds', 'timeout', 'check', 'relative', 'output'])
def test_unknown_launch_or_role_refuses_before_spawn(launch, change):
    context, argv, kwargs = launch
    argv = list(argv); kwargs = dict(kwargs)
    if change == 'executable': argv[0] = '/bin/sh'
    elif change == 'entry': argv[2] += '.other'
    elif change == 'shell': kwargs['shell'] = True
    elif change == 'environment': kwargs['env'] = {'NODE_OPTIONS': '--inspect'}
    elif change == 'cwd': kwargs['cwd'] = '/'
    elif change == 'pass_fds': kwargs['pass_fds'] = (1,)
    elif change == 'timeout': kwargs['timeout'] = 601
    elif change == 'check': kwargs['check'] = True
    elif change == 'relative': argv[3] = 'snap/park.json'
    elif change == 'output': argv[5] = '/tmp/foreign'
    with pytest.raises(ValueError): context.validate(argv, (), kwargs)


def test_log_descriptor_must_name_the_exact_output_log(launch, tmp_path):
    context, argv, kwargs = launch
    with (tmp_path / 'other.log').open('w') as foreign:
        with pytest.raises(ValueError, match='stdout'):
            context.validate(argv, (), dict(kwargs, stdout=foreign))


def test_audit_grant_does_not_cross_threads(launch):
    context, argv, kwargs = launch
    command, cwd = context.validate(argv, (), kwargs)
    context._grant = (command, cwd, threading.get_ident())
    observed = []
    thread = threading.Thread(target=lambda: observed.append(context.allow_subprocess((command[0], command, cwd, context.environment))))
    thread.start(); thread.join()
    assert observed == [False]
    assert context.allow_subprocess((command[0], command, cwd, context.environment))


def test_installed_library_links_include_rewritten_intermediate_roles(tmp_path):
    keg = tmp_path / 'keg'; keg.mkdir()
    (keg / 'lib.1.2').write_bytes(b'library')
    (keg / 'lib.1').symlink_to('lib.1.2')
    (tmp_path / 'opt').symlink_to('keg', target_is_directory=True)
    assert recipe_node._links(tmp_path / 'opt/lib.1') == {str(tmp_path / 'opt'), str(keg / 'lib.1')}
