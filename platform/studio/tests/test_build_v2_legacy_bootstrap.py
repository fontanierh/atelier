"""Portable descriptor primitives only; no production exec/guard/cleanup claim."""
import os

import pytest

from atelier.build_v2.legacy_bootstrap import BootstrapRefused, restore_custody_fds, startup_arguments


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
