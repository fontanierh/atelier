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


def startup_arguments(arguments):
    flags = ('--command-fd', '--reply-fd', '--build-fd', '--content-fd', '--writer-fd',
             '--startup-manifest')
    if (type(arguments) not in (list, tuple) or len(arguments) != 12
            or tuple(arguments[::2]) != flags):
        raise BootstrapRefused('invalid private bootstrap arguments')
    descriptors = {}
    for role, value in zip(ROLES, arguments[1:10:2]):
        if type(value) is not str or not value.isascii() or not value.isdecimal() or len(value) > 10:
            raise BootstrapRefused('invalid private bootstrap descriptor')
        descriptors[role] = int(value)
    manifest = arguments[-1]
    if type(manifest) is not str or not os.path.isabs(manifest) or '\0' in manifest:
        raise BootstrapRefused('invalid private bootstrap manifest path')
    return descriptors, manifest


def main(arguments=None):
    # No project/site import, thread or subprocess precedes this restoration. The host's
    # -I -S invocation is mandatory; ordinary imports of this module are test primitives.
    import sys
    if not sys.flags.isolated or not sys.flags.no_site:
        raise BootstrapRefused('legacy bootstrap requires isolated nonsite startup')
    descriptors, startup_path = startup_arguments(sys.argv[1:] if arguments is None else arguments)
    lock_observations = restore_custody_fds(descriptors)
    sys.dont_write_bytecode = True
    channel = None
    try:
        import hashlib
        import importlib.util
        from pathlib import Path
        # Only this exact host-verified captured distribution can supply startup providers.
        distribution = Path(__file__).resolve(strict=True).parents[4]
        sys.path.insert(0, str(distribution / 'platform/studio'))
        from atelier.build_v2.controller_client import _json, _open_root, _read_at, MAX_CONTROL_BYTES
        from atelier.build_v2.legacy_client import (
            AuthorityLost, LegacyChannel, LegacyClient, _fields, _identity, _integer,
            CLOCK_ID, authority_now_ns, validate_scheduler_request,
        )
        from atelier.build_v2.legacy_qualification import CapturedCode, captured_spec
        from atelier.harness.capacity_protocol import boot_id, process_start

        manifest_path = Path(startup_path)
        manifest = _json(_read_at(manifest_path.parent, manifest_path.name, MAX_CONTROL_BYTES, owned=True))
        _fields(manifest, ('version', 'nonce', 'selection', 'checkout', 'output', 'distribution',
                          'source_digest', 'issuer_digest', 'issuer_root', 'issuer_profile',
                          'host', 'root', 'locks', 'deadline_ns', 'work_deadline_ns', 'clock_domain', 'scheduler_request'))
        if (type(manifest['version']) is not int or manifest['version'] != 2
                or manifest['clock_domain'] != CLOCK_ID):
            raise BootstrapRefused('unsupported private startup version')
        for field in ('checkout', 'output', 'distribution', 'issuer_root'):
            value = manifest[field]
            if type(value) is not str or not Path(value).is_absolute() or str(Path(value).resolve(strict=True)) != value:
                raise BootstrapRefused('private startup root is not canonical')
        checkout = Path(manifest['checkout'])
        if Path(manifest['distribution']) != distribution:
            raise BootstrapRefused('private startup distribution differs from executed bootstrap')
        nonce = manifest['nonce']
        if type(nonce) is not str or len(nonce) != 32 or any(c not in '0123456789abcdef' for c in nonce):
            raise BootstrapRefused('private startup nonce is invalid')
        control = checkout / 'build/build-v2/legacy-host' / nonce
        if manifest_path != control / 'startup.json':
            raise BootstrapRefused('private startup manifest has a different invocation scope')
        _fields(manifest['root'], ('device', 'inode'))
        for value in manifest['root'].values():
            _integer(value, 2**64 - 1)
        root_fd = _open_root(checkout)
        try:
            root = os.fstat(root_fd)
        finally:
            os.close(root_fd)
        if manifest['root'] != {'device': root.st_dev, 'inode': root.st_ino}:
            raise BootstrapRefused('private startup checkout identity changed')
        expected_locks = [{'role': role, 'device': device, 'inode': inode}
                          for role, device, inode in lock_observations if role in ROLES[2:]]
        if type(manifest['locks']) is not list or len(manifest['locks']) != 3:
            raise BootstrapRefused('private startup custody shape differs')
        for binding in manifest['locks']:
            _fields(binding, ('role', 'device', 'inode'))
            _integer(binding['device'], 2**64 - 1)
            _integer(binding['inode'], 2**64 - 1)
        if manifest['locks'] != expected_locks:
            raise BootstrapRefused('private startup custody observations differ')
        request_binding = manifest['scheduler_request']
        _fields(request_binding, ('path', 'digest', 'size'))
        if (request_binding['path'] != f'build/build-v2/legacy-host/{nonce}/request.json'
                or type(request_binding['size']) is not int
                or not 0 < request_binding['size'] <= MAX_CONTROL_BYTES):
            raise BootstrapRefused('original scheduler request has a different invocation scope')
        raw_request = _read_at(control, 'request.json', MAX_CONTROL_BYTES, owned=True)
        if (len(raw_request) != request_binding['size']
                or hashlib.sha256(raw_request).hexdigest() != request_binding['digest']):
            raise BootstrapRefused('original scheduler request changed')
        request = validate_scheduler_request(_json(raw_request))
        _identity(manifest['host'])
        boot = boot_id()
        def identity(pid):
            return {'pid': pid, 'boot': boot, 'started': str(process_start(pid))}
        actual_parent = identity(os.getppid())
        if actual_parent != manifest['host']:
            raise BootstrapRefused('original authority parent identity changed')
        deadline = manifest['deadline_ns']
        work_deadline = manifest['work_deadline_ns']
        if (type(deadline) is not int or type(work_deadline) is not int
                or not authority_now_ns() < work_deadline < deadline):
            raise BootstrapRefused('private authority deadline expired')
        hello = {'version': 2, 'type': 'hello', 'nonce': nonce, 'process': identity(os.getpid()),
                 'clock_domain': CLOCK_ID,
                 'parent': actual_parent, 'source_digest': manifest['source_digest'],
                 'issuer_digest': manifest['issuer_digest'], 'root': manifest['root'],
                 'locks': expected_locks}
        channel = LegacyChannel(descriptors['command'], descriptors['reply'], deadline_ns=work_deadline,
                                clock_domain=manifest['clock_domain'])
        client = LegacyClient.handshake(channel, hello, expected_host=actual_parent,
                                       deadline_ns=deadline, work_deadline_ns=work_deadline)

        # This one captured, game-owned provider is the reviewed semantic issuer. It must
        # prepare DiscoveryControl BEFORE importing the recipe or constructing Context.
        profile = manifest['issuer_profile']
        expected_profile = f"games/{request['game']}/legacy_qualification.py"
        if profile != expected_profile:
            raise BootstrapRefused('game semantic issuer has a different logical path')
        raw_profile = _read_at(manifest['issuer_root'], profile, 8 * 1024 * 1024)
        source = CapturedCode(str(checkout / profile), raw_profile)
        spec = captured_spec('_atelier_fixed_legacy_issuer', source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        result = module.run(manifest=manifest, request=request, client=client,
                            custody={role: descriptors[role] for role in ('build', 'content', 'writer')})
        if type(result) is not int or result != 0 or not client.finished:
            raise AuthorityLost('legacy scheduler did not verify terminal finalization')
        return 0
    finally:
        if channel is not None:
            channel.close()
        for role in (('build', 'content', 'writer') if channel is not None else ROLES):
            try:
                os.close(descriptors[role])  # Close-only; Rust owns all original guards.
            except OSError:
                pass


if __name__ == '__main__':
    import sys
    try:
        raise SystemExit(main())
    except Exception as error:
        # No arbitrary request, environment, source line or input value is dumped.
        detail = str(error) if isinstance(error, BootstrapRefused) else type(error).__name__
        print(f'legacy authority bootstrap failed ({detail})', file=sys.stderr)
        raise SystemExit(1)
