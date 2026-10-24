"""Private normal-build entry for the Rust-owned legacy authority parent.

The entry captures control/source bytes and starts the existing host. It does not
compute action keys, qualify tasks, recover checkpoints or run a second scheduler.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import uuid

from .controller_client import (
    MAX_BINARY_BYTES, ControllerSource, _private_root, _read_at, capture_controller, capture_named_sources,
    ensure_controller, verified_controller, write_control,
)
from .legacy_client import CLOCK_ID, host_budgets, scheduler_request


def managed(game, wanted):
    """Classify globally declared/persisted management without creating state.

    Exact controller-only requests retain their existing transactional route. A legacy
    selector cannot erase management or an old epoch, and never dispatches a course.
    """
    from atelier import paths
    from .controller_entry import discover
    declarations = discover(game)
    if wanted and declarations and all(name in declarations for name in wanted):
        return False
    # Cargo/test listings or a helper distribution alone are not saved checkout
    # ownership. The authoritative B3 metadata root includes lock-only management.
    state = paths.REPO / 'build/build-v2/install'
    return bool(declarations) or state.exists() or state.is_symlink()


def prepare_discovery(game, wanted, *, verify=False, max_heavy_commands=None, fail_fast=False):
    """Captured source-only global declaration preflight, before helper/control writes."""
    from atelier import paths
    from .legacy_qualification import CapturedCode, captured_spec
    checkout = paths.REPO.resolve(strict=True)
    name = f'games/{game}/legacy_qualification.py'
    initial = capture_named_sources(checkout, (name,))
    spec = captured_spec('_atelier_original_discovery_profile',
                         CapturedCode(str(checkout / name), dict(initial.files)[name]))
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    names = profile.source_names(checkout)
    captured = capture_named_sources(checkout, names)
    if dict(captured.files).get(name) != dict(initial.files)[name]:
        raise ValueError('game discovery profile changed during capture')
    request = scheduler_request(game, wanted, verify=verify,
                                max_heavy_commands=max_heavy_commands, fail_fast=fail_fast)
    manifest = {'checkout': str(checkout), 'issuer_digest': captured.digest,
                'python_context': original_python_context()}
    profile.discover(manifest, request, captured_files=captured.files)
    return captured


def original_python_context():
    """Observe the original interpreter before -S changes venv sysconfig behavior."""
    from .python_worker import interpreter_roots
    scheme = sysconfig.get_paths()
    return {'platform_roots': interpreter_roots(), 'purelib': scheme['purelib'],
            'platlib': scheme['platlib']}


def operational_environment(environment):
    """Only the reviewed operational context crosses isolated scheduler startup."""
    forbidden = ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'LD_PRELOAD', 'LD_LIBRARY_PATH')
    allowed = {'ATELIER_AGENT', 'ATELIER_CACHE', 'ATELIER_BUILD_ROOT'}
    if (any(key in environment for key in forbidden)
            or any(key.startswith('DYLD_') or (key.startswith('ATELIER_') and key not in allowed)
                   for key in environment)):
        raise ValueError('unsupported injected interpreter environment')
    path = environment.get('PATH', '')
    if not path or any(not part or not os.path.isabs(part) for part in path.split(os.pathsep)):
        raise ValueError('managed scheduler requires an explicit absolute PATH')
    result = {'agent': environment.get('ATELIER_AGENT'), 'cache': environment.get('ATELIER_CACHE'),
              'build_root': environment.get('ATELIER_BUILD_ROOT'), 'path': path}
    for key in ('cache', 'build_root'):
        if result[key] is not None and not os.path.isabs(result[key]):
            raise ValueError('managed scheduler requires absolute operational roots')
    return result


def execute(game, wanted, *, discovery_source, verify=False, max_heavy_commands=None,
            fail_fast=False, echo=print, enclosing_deadline_ns=None):
    """@cc [owner:fontanierh,label:safety] original-managed-host-entry
    The normal managed entry MUST start only a verified immutable controller image over
    the original bounded request and captured named provider bytes. It MUST preserve the
    original lexical interpreter role, installed C2c context and closed operational
    environment. Host failure/uncertainty MUST NOT fall back to the legacy scheduler or
    manufacture Finish. No controller-owned task is implicitly dispatched here.
    See test_build_v2_legacy_entry.py.
    """
    from atelier import paths
    from atelier.harness.capacity_protocol import boot_id
    from atelier.harness.safety.cancellation import termination_cleanup
    checkout = paths.REPO.resolve(strict=True)
    request = scheduler_request(game, wanted, verify=verify,
                                max_heavy_commands=max_heavy_commands, fail_fast=fail_fast)
    operational = operational_environment(os.environ)
    context = original_python_context()
    interpreter_role = Path(os.path.abspath(sys.executable))
    interpreter = interpreter_role.resolve(strict=True)
    image = _read_at(interpreter.parent, interpreter.name, MAX_BINARY_BYTES)
    captured = capture_controller(checkout)
    if not isinstance(discovery_source, ControllerSource):
        raise ValueError('managed startup requires the original captured discovery source')
    issuer = discovery_source
    source_names = tuple(name for name, _ in issuer.files)
    if capture_named_sources(checkout, source_names).digest != issuer.digest:
        raise ValueError('game discovery source changed after original global preflight')
    if f'games/{game}/legacy_qualification.py' not in dict(issuer.files):
        raise ValueError('managed entry has no captured fixed game issuer')
    budgets = host_budgets(enclosing_deadline_ns=enclosing_deadline_ns)
    helper = ensure_controller(checkout, paths.build_root() / 'build-v2/controller/helpers', echo=echo)
    if helper.source != captured.digest or capture_controller(checkout).digest != captured.digest:
        raise ValueError('controller source changed during managed startup')
    if capture_named_sources(checkout, source_names).digest != issuer.digest:
        raise ValueError('game issuer source changed during managed startup')
    nonce = uuid.uuid4().hex
    control = _private_root(checkout / 'build/build-v2/legacy-host' / nonce)
    captured.materialize(control / 'distribution')
    issuer.materialize(control / 'issuer')
    write_control(control, 'request.json', request)
    os.chmod(control / 'request.json', 0o400)
    request_bytes = _read_at(control, 'request.json', 64 * 1024, owned=True)
    config = {
        'version': 2, 'nonce': nonce, 'selection': nonce, 'checkout': str(checkout),
        'output': str(paths.build_root() / game), 'distribution': str(control / 'distribution'),
        'source_identity': captured.digest, 'interpreter': str(interpreter),
        'interpreter_digest': hashlib.sha256(image).hexdigest(),
        'interpreter_role': str(interpreter_role), 'python_context': context,
        'operational_environment': operational,
        'game_issuer': {'project': game, 'root': str(control / 'issuer'),
                        'files': [name for name, _ in issuer.files], 'digest': issuer.digest,
                        'profile': f'games/{game}/legacy_qualification.py'},
        'control_directory': f'build/build-v2/legacy-host/{nonce}',
        'boot': boot_id(), 'clock_domain': CLOCK_ID,
        **budgets,
        'scheduler_request': {'path': f'build/build-v2/legacy-host/{nonce}/request.json',
                              'size': len(request_bytes),
                              'digest': hashlib.sha256(request_bytes).hexdigest()},
    }
    write_control(control, 'config.json', config)
    os.chmod(control / 'config.json', 0o400)
    echo(f'Managed legacy authority control: {control}')
    sys.stdout.flush()
    # Only the bounded control descriptor is inherited by the Rust parent. It owns
    # B3 acquisition and the five-descriptor child handoff; no Python flock/adoption.
    descriptor = os.open(control / 'config.json', os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with verified_controller(helper) as binary, termination_cleanup():
            process = subprocess.Popen([str(binary), '--legacy-config-fd', str(descriptor)],
                                       pass_fds=(descriptor,), cwd=checkout)
            try:
                code = process.wait()
            except BaseException:
                try:
                    if process.poll() is None:
                        process.terminate()
                    process.wait()  # Rust retains guards through its bounded child drain.
                except OSError:
                    echo('Managed authority shutdown observation unavailable; completion remains uncertified')
                raise
    finally:
        os.close(descriptor)
    if code:
        echo('Managed legacy build held/refused; no fallback or final completion was certified')
        sys.stdout.flush()
    return code
