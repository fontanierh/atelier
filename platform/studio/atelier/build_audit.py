"""Prepare and validate an opt-in Python input audit, separately from the action's outputs."""
from contextlib import contextmanager, ExitStack
from dataclasses import replace, dataclass, field
import json
import os
from pathlib import Path
import secrets
import select
import sysconfig
import tempfile
import threading

from . import paths

WORKER = Path(__file__).with_name('build_audit_worker.py')
NATIVE = Path(__file__).with_name('build_audit_native.py')
SUPPORT = (Path(__file__), WORKER, NATIVE)
_CAPTURED_ORIGIN = object()
_CAPTURED_WORKER = (
    'platform/studio/atelier/__init__.py',
    'platform/studio/atelier/build_audit_worker.py',
    'platform/studio/atelier/atomic_files.py',
    'platform/studio/atelier/build_v2/__init__.py',
    'platform/studio/atelier/build_v2/legacy_action.py',
    'platform/studio/atelier/build_v2/legacy_bootstrap.py',
    'platform/studio/atelier/build_v2/legacy_client.py',
    'platform/studio/atelier/build_v2/legacy_qualification.py',
    'platform/studio/atelier/build_v2/controller_client.py',
)


@dataclass(frozen=True)
class _CapturedRuntime:
    root: Path
    files: tuple[str, ...]
    _origin: object = field(repr=False, compare=False)
    nested_tool: object = None
    legacy_outputs: tuple[Path, ...] = ()


def captured_runtime_inputs(step):
    runtime = getattr(step, '_captured_audit_runtime', None)
    if runtime is None:
        return ()
    if type(runtime) is not _CapturedRuntime or runtime._origin is not _CAPTURED_ORIGIN:
        raise ValueError('unqualified captured audit runtime descriptor')
    return tuple(runtime.root / name for name in runtime.files)


def enabled(step):
    """@cc [owner:fontanierh,label:correctness;safety] fixed-issuer-observed-python
    Only original audit opt-in or the private fixed-issuer runtime MAY enable this
    existing observer. Original recipe flags MUST remain unchanged; runtime/support
    identities and observation mode MUST enter the original fingerprint. Unknown
    descriptors MUST refuse. Observer completeness and normal guarded lifecycle MUST
    remain required before certification; this predicate grants no mutation authority.
    See test_build_v2_legacy_action.py and test_build_audit.py.
    """
    runtime = captured_runtime_inputs(step)
    return step.audit or bool(runtime)


def _bind_captured_runtime(step, *, checkout, issuer_files, code_inputs=(), nested_tool=None, legacy_outputs=()):
    """Fixed issuer semantic descriptor only; never a mutation/launch capability.

    Use the existing step inputs and named worker helpers/initializers. This private
    mode is not a recipe flag and cannot execute without the real bound authority.
    """
    from .build import required_inputs
    root = Path(checkout)
    names = {path.relative_to(root).as_posix() for path in map(Path, required_inputs(step))
             if path.suffix == '.py' and path not in SUPPORT}
    names.update(Path(path).relative_to(root).as_posix() for path in code_inputs)
    names.update(_CAPTURED_WORKER)
    if nested_tool is not None:
        from .build_v2.legacy_tool_action import checked_node
        checked_node(nested_tool)
        names.add('platform/studio/atelier/build_v2/legacy_tool_action.py')
        names.add('platform/studio/atelier/build_v2/python_worker.py')
        names.add('platform/studio/atelier/build_v2/protocol.py')
        names.add('platform/studio/atelier/build_products.py')
    if nested_tool is not None or legacy_outputs:
        from .build import Python
        if (not legacy_outputs or tuple(legacy_outputs) != tuple(step.outputs)
                or step.products or not step.cutoff or step.cache
                or len(step.commands) != 1 or type(step.commands[0]) is not Python):
            raise ValueError('captured legacy Python action differs from its original cutoff/output role')
    for name in list(names):
        parent = (root / name).parent
        while parent != root:
            initializer = parent / '__init__.py'
            if initializer.is_symlink():
                raise ValueError('linked captured worker package initializer')
            if initializer.is_file():
                names.add(initializer.relative_to(root).as_posix())
            parent = parent.parent
    if not names <= set(issuer_files):
        raise ValueError('selected worker code is outside the original named issuer capture')
    runtime = _CapturedRuntime(root, tuple(sorted(names)), _CAPTURED_ORIGIN, nested_tool, tuple(legacy_outputs))
    step._captured_audit_runtime = runtime
    return runtime


def validate(step):
    from .build import Blender, Python, UnrealScript
    if type(step.audit) is not bool:
        raise ValueError(f'{step.name}: audit must be a boolean')
    if not enabled(step):
        return
    runtime = getattr(step, '_captured_audit_runtime', None)
    legacy = bool(captured_runtime_inputs(step) and runtime.legacy_outputs
                  and len(step.commands) == 1 and type(step.commands[0]) is Python
                  and runtime.legacy_outputs == tuple(step.outputs) and not step.products
                  and step.cutoff and not step.cache)
    if runtime is not None and runtime.legacy_outputs and not legacy:
        raise ValueError('captured legacy Python output/command role changed')
    if ((not step.products and not legacy) or len(step.commands) != 1
            or type(step.commands[0]) not in (Python, Blender, UnrealScript)):
        raise ValueError(f'{step.name}: audit requires named products and exactly one Python, Blender or UnrealScript command')
    if type(step.commands[0]) is not Python:
        if not step.heavy or step.cache:
            raise ValueError(f'{step.name}: native Python audits require heavy=True and cache=False')
        if isinstance(step.commands[0], Blender) and not step.commands[0].factory_startup:
            raise ValueError(f'{step.name}: audited Blender commands require factory_startup=True')


def installation(command):
    """Recognized native tool roots; never infer trust from an action's sys.path."""
    from . import engine
    from .build import Blender
    if isinstance(command, Blender):
        binary = Path(engine.blender()).resolve()
        bundle = binary.parent.parent
        if binary.parent.name != 'MacOS' or bundle.name != 'Contents':
            raise ValueError('Native Blender audits require a complete macOS app bundle')
        return [bundle]
    root = engine.unreal_root().resolve()
    version = json.loads((root / 'Engine/Build/Build.version').read_text())
    if (version.get('MajorVersion'), version.get('MinorVersion')) != (5, 8):
        raise ValueError('Native Unreal Python audit tool layout is verified only for UE 5.8')
    return [root / 'Engine/Binaries/ThirdParty/Python3/Mac',
            root / 'Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python']


def tool_context(step, hasher, *, cache=None):
    """Fingerprint the native Python installation without granting portable cache eligibility."""
    from . import build, build_cache, build_inputs, build_products, engine
    hasher = hasher or build_products.file_digest
    if type(step.commands[0]) is not build.UnrealScript:
        context = build_cache.tool_context(step, hasher, cache=cache)
        runtime = getattr(step, '_captured_audit_runtime', None)
        if runtime is not None:
            inputs = captured_runtime_inputs(step)
            if runtime.nested_tool is not None:
                from .build_v2.legacy_tool_action import node_identity
                context = {**context, 'nested_tool': node_identity(runtime.nested_tool, hasher)}
            context = {**context, 'captured_python_runtime': {
                'version': 'captured-audited-python/1', 'flags': ['-I', '-S', '-B'],
                'files': [(name, hasher(path)) for name, path in zip(runtime.files, inputs)]}}
        if type(step.commands[0]) is build.Blender:
            # A native host may have executed bytecode before the bootstrap. Unlike the
            # portable source-cache identity, this observation context includes __pycache__.
            context = {**context, 'audit_installation': [build_inputs.inventory(root, hasher=hasher, complete=True)
                                                       for root in installation(step.commands[0])]}
        return context
    command = step.commands[0]
    runtime, wrappers = installation(command)
    binary = engine.unreal_cmd().resolve()
    root = engine.unreal_root()
    version = root / 'Engine/Build/Build.version'
    plugin = root / 'Engine/Plugins/Experimental/PythonScriptPlugin/Binaries/Mac'
    # Revalidate every file through the invocation's hasher. No private runtime or ambient
    # import directory is inferred from the parent interpreter's package paths.
    return {'schema': 1, 'host': 'UnrealScript', 'binary': hasher(binary), 'version': hasher(version),
            'python': build_inputs.inventory(runtime, hasher=hasher, complete=True),
            'wrappers': build_inputs.inventory(wrappers, hasher=hasher, complete=True),
            'plugin': {name: hasher(plugin / name) for name in
                       ('libUnrealEditor-PythonScriptPlugin.dylib',
                        'libUnrealEditor-PythonScriptPluginPreload.dylib', 'UnrealEditor.modules')}}


def roots(ctx, step):
    """Audit ownership permits native products, but never permits restoring native cache entries."""
    from .build import Python, UnrealScript
    runtime = getattr(step, '_captured_audit_runtime', None)
    if captured_runtime_inputs(step) and runtime.legacy_outputs:
        if (not runtime.legacy_outputs or runtime.legacy_outputs != tuple(step.outputs)
                or step.products or not step.cutoff or step.cache):
            raise ValueError('nested legacy output declaration changed')
        for path in runtime.legacy_outputs:
            path = Path(path)
            if not path.is_absolute() or not path.is_relative_to(ctx.out) or path == ctx.out:
                raise ValueError('nested legacy output is outside the owned build root')
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise ValueError('linked nested legacy output')
        return
    if type(step.commands[0]) is Python:
        from .build_cache import roots as portable_roots
        return portable_roots(ctx, step)
    if step.pool_roots or step.cutoff or any(p.optional_paths for p in step.products):
        raise ValueError('Native audits require complete owned products without pool/cutoff/optional roots')
    bases = [Path(os.path.abspath(ctx.out))]
    if isinstance(step.commands[0], UnrealScript):
        bases.append(Path(os.path.abspath(ctx.uproject)).parent / 'Content')
    for product in step.products:
        for root in product.paths:
            root = Path(os.path.abspath(root))
            base = next((b for b in bases if root != b and root.is_relative_to(b)), None)
            if base is None or root.relative_to(base).parts[0] in ('logs', 'stamps', '.state'):
                raise ValueError('Audited products require an owned generated subpath')
            if any(p.is_symlink() for p in (root, *root.parents)):
                raise ValueError('Linked audit destination')
    declared = [Path(os.path.abspath(p)) for product in step.products for p in product.paths]
    if any(not any(Path(os.path.abspath(p)).is_relative_to(r) for r in declared) for p in step.outputs):
        raise ValueError('Audited required output has no product owner')


def valid_record(record, nonce):
    if not isinstance(record, dict) or record.get('nonce') != nonce:
        return False
    kind = record.get('kind')
    if kind == 'start':
        return set(record) == {'kind', 'nonce'}
    if kind == 'complete':
        return set(record) == {'kind', 'nonce', 'success'} and type(record['success']) is bool
    return (kind == 'access' and set(record) == {'kind', 'nonce', 'operation', 'path', 'violation'}
            and isinstance(record['operation'], str) and bool(record['operation'])
            and (record['path'] is None or isinstance(record['path'], str))
            and (record['violation'] is None or isinstance(record['violation'], str) and bool(record['violation'])))


class Receiver:
    """Drain a private pipe while the normal launcher owns the child and its guard."""
    def __init__(self, fd, nonce):
        self.fd, self.nonce = fd, nonce
        self.records = []
        self.error = None
        self.eof = False
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.read, daemon=True, name='atelier-input-audit')

    def read(self):
        buffer = b''
        try:
            while True:
                # Read the stop flag before polling: the host closes its writer before stopping,
                # so only a poll that started after the stop can show a pipe another process holds.
                stopping = self.stopped.is_set()
                ready, _, _ = select.select([self.fd], [], [], .1)
                if not ready:
                    if stopping:
                        break
                    continue
                data = os.read(self.fd, 65536)
                if not data:
                    self.eof = True
                    break
                if self.error:
                    continue  # Keep draining: a bad report must not fill the pipe and hang its child.
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    try:
                        if len(line) > 32768 or len(self.records) >= 20002:
                            raise ValueError('audit report exceeds its limit')
                        record = json.loads(line)
                        if not valid_record(record, self.nonce):
                            raise ValueError('invalid audit record')
                        self.records.append(record)
                    except (ValueError, TypeError) as error:
                        self.error = type(error).__name__
                        buffer = b''
                        break
                if len(buffer) > 32768:
                    self.error, buffer = 'oversized audit record', b''
            if buffer:
                raise ValueError('truncated audit record')
        except (OSError, ValueError, TypeError) as error:
            # Do not copy untrusted record contents or exception text into the report.
            self.error = type(error).__name__

    def finish(self, step):
        self.stopped.set()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            self.error = 'audit reader did not stop'
        if not self.error and not self.eof:
            self.error = 'audit pipe did not close'
        kinds = [r.get('kind') for r in self.records]
        complete = (not self.error and len(kinds) >= 2 and kinds[0] == 'start' and kinds[-1] == 'complete'
                    and all(kind == 'access' for kind in kinds[1:-1]))
        accesses = [r for r in self.records if r.get('kind') == 'access']
        violations = [r for r in accesses if r.get('violation')]
        passed = complete and self.records[-1].get('success') is True and not violations
        return {'schema': 1, 'step': step.name, 'complete': bool(complete), 'passed': bool(passed),
                'error': self.error, 'accesses': accesses, 'violations': violations}


@contextmanager
def prepared(ctx, step, products, *, receipt=None):
    """@cc [owner:fontanierh,label:correctness] observed-inputs-before-certification
    An audited action MUST provide a fresh, complete successful report without violations before
    certification. Reference products MUST NOT grant read access. Reports MUST stay outside products;
    failed actions and incomplete reports MUST NOT create stamps or publish cache entries.
    An execution receipt MUST bind its fresh run nonce and exact successful report digest before certification.
    Preparing an invocation MUST NOT remove owned outputs: an admitted child MUST clear them before
    installing the observer and running the action, so refused admission preserves existing products.
    """
    from .build import Blender, Python, required_inputs
    from .build_cache import atomic_json
    validate(step)
    roots(ctx, step)
    command = step.commands[0]
    inputs = [*required_inputs(step), *(p for name in step.reads for p in products[name].roots())]
    runtime = getattr(step, '_captured_audit_runtime', None)
    output_roots = ([Path(p).resolve() for p in runtime.legacy_outputs]
                    if runtime is not None and runtime.legacy_outputs else
                    [Path(p).resolve() for product in step.products for p in product.paths])
    report_path = ctx.logs / f'{step.name}.audit.json'
    authority = getattr(ctx, 'legacy_authority', None)
    runtime = getattr(step, '_captured_audit_runtime', None)
    if runtime is not None and (authority is None or getattr(authority, 'runtime', None) is not runtime):
        raise ValueError('captured audit runtime requires its original fixed issuer authority')
    temporary_scope = (authority.audit_directory() if authority is not None else
                       tempfile.TemporaryDirectory(dir=ctx.logs, prefix='.audit-'))
    with temporary_scope as temporary, ExitStack() as cleanup:
        control = Path(temporary).resolve()
        from .build_spatial import manifest
        action_inputs = control / 'action-inputs.json'
        action_inputs.write_text(json.dumps(manifest(step)))
        inputs.append(action_inputs)
        scratch = control / 'scratch'
        for name in ('home', 'tmp', 'cache', 'bytecode'):
            (scratch / name).mkdir(parents=True)
        read_fd, write_fd = os.pipe()
        reader = cleanup.enter_context(os.fdopen(read_fd, 'rb', buffering=0))
        writer = cleanup.enter_context(os.fdopen(write_fd, 'wb', buffering=0))
        nonce = secrets.token_hex(16)
        receiver = Receiver(read_fd, nonce)
        config = {
            'nonce': nonce, 'fd': write_fd, 'script': str(command.script.resolve()), 'args': list(map(str, command.args)),
            'inputs': [*((str(Path(p).resolve()), Path(p).is_dir()) for p in inputs),
                       *((str(Path(p).resolve()), False) for p in step.optional_inputs)],
            'outputs': list(map(str, output_roots)), 'scratch': str(scratch),
            'runtime': (authority.runtime_roots() if authority is not None else
                        sorted({str(Path(sysconfig.get_path(name)).resolve())
                                for name in ('stdlib', 'platstdlib', 'purelib', 'platlib')})),
            'labels': [(str(scratch), 'scratch'), (str(ctx.out.resolve()), 'build'),
                       (str(paths.REPO.resolve()), 'repo')],
        }
        config['labels'].extend((p, 'runtime') for p in config['runtime'])
        spec = control / 'request.json'
        spec.write_text(json.dumps(config))
        native = type(command) is not Python
        if native:
            config.update(host=type(command).__name__, installation=list(map(str, installation(command))),
                          module_guard=bool(getattr(command, 'modules', ())))
            # An editor's args are host launch flags, not Python script arguments.
            if not isinstance(command, Blender):
                config['args'] = []
            spec.write_text(json.dumps(config))
            if isinstance(command, Blender):
                argv, command_env = replace(command, script=NATIVE, args=()).argv(ctx), command.env
            else:
                # Keep descriptor ownership alive, but the bootstrap performs the same module
                # checks before/after the observed recipe instead of nesting an outer guard.
                argv, command_env = cleanup.enter_context(replace(command, script=NATIVE).prepared(ctx))
                argv = [f'-script={NATIVE}' if arg.startswith('-script=') else arg for arg in argv]
        else:
            argv, command_env = [command.argv(ctx)[0], str(WORKER), str(spec)], ()
        env = (('HOME', str(scratch / 'home')), ('TMPDIR', str(scratch / 'tmp')),
               ('TMP', str(scratch / 'tmp')), ('TEMP', str(scratch / 'tmp')),
               ('XDG_CACHE_HOME', str(scratch / 'cache')), ('PYTHONPYCACHEPREFIX', str(scratch / 'bytecode')),
               ('PYTHONDONTWRITEBYTECODE', '1'), ('ATELIER_ACTION_INPUTS', str(action_inputs)))
        env = (*command_env, *env, *((('ATELIER_AUDIT_SPEC', str(spec)),) if native else ()))
        if authority is not None:
            if native:
                raise ValueError('managed captured audit supports the qualified Python family only')
            argv = authority.audit_argv(spec)
            config['legacy_environment'] = dict(authority.action_environment(env))
            config['legacy_code_files'] = list(runtime.files)
            if runtime.nested_tool is not None:
                from .build_v2.legacy_tool_action import node_spec
                config['legacy_nested_tool'] = node_spec(runtime.nested_tool, ctx.build_hash_index.digest)
                config['inputs'].extend((str(path), False) for path in
                                       (runtime.nested_tool.image, *runtime.nested_tool.libraries))
            env = tuple(config['legacy_environment'].items())
            spec.write_text(json.dumps(config))
            spec.chmod(0o600)
        receiver.thread.start()
        try:
            yield argv, env, (write_fd,)
        finally:
            writer.close()
            report = receiver.finish(step)
            reader.close()
            atomic_json(report_path, report)
        if not report['passed']:
            # Name what was refused: the report is outside the log a failing action shows, and
            # "see the report" alone sends every reader to the artifacts.
            detail = '; '.join(f"{v['operation']} {v.get('path') or ''}: {v['violation']}".strip()
                               for v in report['violations'][:3])
            raise RuntimeError(f'{step.name}: input audit incomplete or failed; see {report_path}'
                               f" ({detail or report['error'] or 'no complete report'})")
        if receipt is not None:
            from .build_products import identity
            receipt.update(schema=1, execution='audited-native-python-v1' if native else 'audited-python-v1', run_id=nonce,
                           report_sha256=identity(report))
