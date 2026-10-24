"""Portable descriptor primitives only; no production exec/guard/cleanup claim."""
import os
import hashlib
from pathlib import Path
import sys

import pytest

from atelier.build_v2.legacy_bootstrap import BootstrapRefused, restore_custody_fds, startup_arguments


def test_startup_issuer_roster_accepts_512_and_refuses_513_duplicate_or_noncanonical_names():
    from atelier.build_v2.legacy_bootstrap import validate_issuer_files
    names = [f'games/example/provider_{index}.py' for index in range(513)]
    validate_issuer_files(names[:512])
    for invalid in (names, [*names[:511], names[0]], [], tuple(names[:512])):
        with pytest.raises(BootstrapRefused, match='issuer capture names'):
            validate_issuer_files(invalid)
    for invalid in (['../provider.py'], ['/provider.py'], ['games/./provider.py']):
        with pytest.raises(ValueError, match='normalized relative'):
            validate_issuer_files(invalid)


def test_bootstrap_restores_only_five_owned_descriptors_before_observations(tmp_path):
    command_r, command_w = os.pipe()
    reply_r, reply_w = os.pipe()
    locks = [os.open(tmp_path / role, os.O_CREAT | os.O_RDWR, 0o600)
             for role in ('build', 'content', 'writer')]
    descriptors = dict(zip(('command', 'reply', 'build', 'content', 'writer'),
                           (command_w, reply_r, *locks)))
    all_fds = (command_r, command_w, reply_r, reply_w, *locks)
    try:
        for fd in descriptors.values():
            os.set_inheritable(fd, True)  # Simulates only the host's child pre_exec exception.
        before = {role: os.fstat(fd) for role, fd in descriptors.items()}
        result = restore_custody_fds(descriptors)
        assert result == tuple((role, before[role].st_dev, before[role].st_ino)
                               for role in descriptors)
        assert all(not os.get_inheritable(fd) for fd in descriptors.values())
        os.write(command_w, b'original-pipe')
        assert os.read(command_r, 32) == b'original-pipe'
    finally:
        for fd in all_fds:
            os.close(fd)


def test_bootstrap_refuses_aliases_standard_missing_and_wrong_kind_before_discovery(tmp_path):
    descriptors = {'command': 1, 'reply': 2, 'build': 3, 'content': 4, 'writer': 5}
    with pytest.raises(BootstrapRefused, match='descriptor set'):
        restore_custody_fds(descriptors)
    with pytest.raises(BootstrapRefused, match='descriptor set'):
        restore_custody_fds({role: 9 for role in descriptors})
    fds = [os.open(tmp_path / str(i), os.O_CREAT | os.O_RDWR, 0o600) for i in range(5)]
    try:
        with pytest.raises(BootstrapRefused, match='not a pipe'):
            restore_custody_fds(dict(zip(descriptors, fds)))
        assert all(not os.get_inheritable(fd) for fd in fds)
        missing = dict(zip(descriptors, fds))
        os.close(fds.pop())
        with pytest.raises(BootstrapRefused, match='unavailable'):
            restore_custody_fds(missing)
    finally:
        for fd in fds:
            os.close(fd)


def test_exact_host_bootstrap_argv_has_no_module_site_or_ambient_option_fallback():
    arguments = ['--command-fd', '3', '--reply-fd', '4', '--build-fd', '5', '--content-fd', '6',
                 '--writer-fd', '7', '--startup-manifest', '/private/control/startup.json']
    fds, path = startup_arguments(arguments)
    assert fds == {'command': 3, 'reply': 4, 'build': 5, 'content': 6, 'writer': 7}
    assert path == '/private/control/startup.json'
    for changed in (arguments + ['--extra', 'permission'], arguments[2:],
                    ['--command-fd', 'NaN', *arguments[2:]],
                    [*arguments[:-1], 'relative/startup.json']):
        with pytest.raises(BootstrapRefused):
            startup_arguments(changed)


def test_legacy_bootstrap_original_interpreter_context_without_site_hooks(tmp_path, monkeypatch):
    from atelier.build_v2.legacy_bootstrap import restore_python_context
    from atelier.build_v2.legacy_client import AuthorityLost
    image = Path(sys.executable).resolve()
    library = tmp_path / 'venv/lib'
    library.mkdir(parents=True)
    forbidden = tmp_path / 'site-hook-ran'
    (library / 'hook.pth').write_text(f"import pathlib; pathlib.Path({str(forbidden)!r}).touch()\n")
    context = {'interpreter': str(image), 'interpreter_role': os.path.abspath(sys.executable),
               'interpreter_digest': hashlib.sha256(image.read_bytes()).hexdigest(),
               'python_context': {'platform_roots': [str(tmp_path)],
                                  'purelib': str(library), 'platlib': str(library)},
               'operational_environment': {'agent': 'test-owner', 'cache': None,
                                           'build_root': None, 'path': '/usr/bin:/bin'}}
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(os, 'environ', {'ATELIER_AGENT': 'test-owner', 'PATH': '/usr/bin:/bin'})
    executable = sys.executable
    assert restore_python_context(context) == (str(library),)
    assert sys.path.count(str(library)) == 1
    assert not forbidden.exists()
    assert sys.executable == executable
    monkeypatch.setitem(os.environ, 'LC_CTYPE', 'C.UTF-8')
    assert restore_python_context(context) == (str(library),)
    monkeypatch.setitem(os.environ, 'LC_CTYPE', 'unreviewed-locale')
    with pytest.raises(BootstrapRefused, match='locale coercion'):
        restore_python_context(context)
    monkeypatch.delitem(os.environ, 'LC_CTYPE')
    before = list(sys.path)
    for broken in ({**context, 'interpreter_digest': '0' * 64},
                   {**context, 'interpreter_role': str(tmp_path / 'missing-python')},
                   {**context, 'python_context': {**context['python_context'], 'purelib': '/'}},
                   {**context, 'python_context': {**context['python_context'], 'unknown': True}}):
        with pytest.raises((BootstrapRefused, AuthorityLost, ValueError, OSError)):
            restore_python_context(broken)
        assert sys.path == before
    monkeypatch.setitem(os.environ, 'PYTHONPATH', str(tmp_path))
    with pytest.raises(BootstrapRefused, match='environment differs'):
        restore_python_context(context)
