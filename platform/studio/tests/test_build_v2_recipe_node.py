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


@pytest.fixture
def crypto(tmp_path):
    config = tmp_path / 'openssl.cnf'; config.write_text('openssl_conf = defaults\n[defaults]\n')
    image = tmp_path / 'libcrypto.3.dylib'
    image.write_bytes(b'prefix\0OPENSSLDIR: "' + str(tmp_path).encode() + b'"\0suffix')
    return image, config


def test_selected_openssl_default_is_retained_and_used_in_fixed_environment(crypto, launch):
    image, config = crypto
    assert recipe_node._openssl_configuration([str(image)]) == str(config)
    context, _, _ = launch
    sdk = dict(context.sdk, openssl_config=str(config))
    selected = recipe_node.NodeExecution(sdk, view=context.view, scratch=context.scratch,
                                        entry=context.entry, sources=context.sources)
    assert selected.environment['OPENSSL_CONF'] == str(config)


@pytest.mark.parametrize('name', ['OPENSSL_CONF', 'OPENSSL_CONF_INCLUDE', 'OPENSSL_MODULES'])
def test_inherited_openssl_overrides_refuse(crypto, monkeypatch, name):
    monkeypatch.setenv(name, '/foreign/config')
    with pytest.raises(ValueError, match='environment override'):
        recipe_node._openssl_configuration([str(crypto[0])])


@pytest.mark.parametrize('directive', ['.include other.cnf', 'module = external.dylib',
                                        'dynamic_path = external.dylib', 'engines = engines',
                                        'value = $ENV::HOME'])
def test_openssl_follow_on_configuration_refuses(crypto, directive):
    image, config = crypto; config.write_text(directive + '\n')
    with pytest.raises(ValueError, match='include or external provider'):
        recipe_node._openssl_configuration([str(image)])


def test_openssl_unknown_compiled_default_refuses(crypto):
    image, _ = crypto; image.write_bytes(b'unknown selected library metadata')
    with pytest.raises(ValueError, match='default directory is not exact'):
        recipe_node._openssl_configuration([str(image)])


def test_explicit_absolute_node_role_works_without_path(monkeypatch):
    role = '/opt/homebrew/Cellar/node/25.6.1/bin/node'
    monkeypatch.delenv('PATH', raising=False)
    monkeypatch.setattr(recipe_node.shutil, 'which', lambda _: pytest.fail('explicit SDK must not search PATH'))
    monkeypatch.setattr(recipe_node.Path, 'resolve', lambda self, **_: self)
    monkeypatch.setattr(recipe_node.Path, 'is_file', lambda _: True)
    monkeypatch.setattr(recipe_node, '_links', lambda _: set())
    monkeypatch.setattr(recipe_node, '_openssl_configuration', lambda _: None)
    monkeypatch.setattr(recipe_node.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=role + ':\n'))
    sdk = recipe_node.discover_node(role)
    assert sdk['executable'] == sdk['image'] == role
    with pytest.raises(ValueError, match='installed Node'):
        recipe_node.discover_node('relative/node')
