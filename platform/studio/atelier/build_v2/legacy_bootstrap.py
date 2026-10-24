"""Isolated startup primitives for the private Rust-owned legacy scheduler child.

The absolute captured entry is launched with -I -S. Only standard-library startup runs
before restoring CLOEXEC; Python's built-in codec/runtime initialization is not suppressed.
Descriptor observations never create a build/content guard or authorize a task.
"""
import os
import stat

ROLES = ('command', 'reply', 'build', 'content', 'writer')


class BootstrapRefused(RuntimeError):
    """No project import, selection discovery or mutation is permitted after refusal."""


def restore_custody_fds(descriptors):
    """@cc [owner:fontanierh,label:safety] legacy-bootstrap-cloexec-before-project
    The isolated bootstrap MUST restore CLOEXEC on exactly the five inherited channel and
    custody descriptors before project/site import, thread creation or child launch. It MUST
    reject duplicate, standard, missing or wrongly shaped descriptors without probing flock,
    reopening a lock, unlocking, or interpreting descriptor metadata as epoch authority.
    Rust retains the original guards; these observations only bind Hello to that private child.
    See test_build_v2_legacy_bootstrap.py.
    """
    if (type(descriptors) is not dict or set(descriptors) != set(ROLES)
            or any(type(fd) is not int or fd < 3 for fd in descriptors.values())
            or len(set(descriptors.values())) != len(ROLES)):
        raise BootstrapRefused('invalid private bootstrap descriptor set')
    try:
        # Restore all five before any further startup action, including observation imports.
        for role in ROLES:
            os.set_inheritable(descriptors[role], False)
        observations = []
        for role in ROLES:
            info = os.fstat(descriptors[role])
            if role in ('command', 'reply'):
                if not stat.S_ISFIFO(info.st_mode):
                    raise BootstrapRefused('private bootstrap channel is not a pipe')
            elif not stat.S_ISREG(info.st_mode):
                raise BootstrapRefused('private bootstrap custody is not a regular file')
            if os.get_inheritable(descriptors[role]):
                raise BootstrapRefused('private bootstrap descriptor remains inheritable')
            observations.append((role, info.st_dev, info.st_ino))
        return tuple(observations)
    except OSError:
        raise BootstrapRefused('private bootstrap descriptor is unavailable') from None
