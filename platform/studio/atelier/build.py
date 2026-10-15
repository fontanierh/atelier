"""The build engine: named steps with inputs and dependencies, rerun only when something they read changed.

A game describes its build in `games/<game>/build.py`, a module with `steps()` returning a list of `Step`s. A step's
fingerprint is the hash of its inputs (files or folders, by content), its commands, and the fingerprints of the steps
it needs; `build/<game>/stamps/<step>.json` remembers the last good one. Logs go to `build/<game>/logs/<step>.log`.
A `cutoff` step gives its dependents the hash of its outputs instead of its fingerprint: when it reruns and makes the
same outputs, they stay current.

Commands are plain data (`Python`, `Blender`, `UnrealScript`, `UnrealCompile`, `UnrealPackage`, `Call`), so the fingerprint changes
when a command does.

A `heavy` step's commands run under `atelier.safety.guarded`: a render slot and the memory guard, whose report is
`logs/<step>.guard/memory-health.json`. When two render slots are on (`atelier.safety.render_lock`), a step whose last
guard reports peaked at 3 GiB or less asks for the small slot; a compile, or a step with no report yet, takes the big
one. The step's log names the slot each command used, and the summary line names it too when two slots are on.
"""
import hashlib, importlib.util, json, os, subprocess, sys, time
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from pathlib import Path

from . import engine, paths
from . import build_inputs, build_products
from .build_products import Product
from .build_deferred import DeferredInputs
from .build_spatial import BBoxQuery
from .safety import guarded
from .safety.render_lock import GiB, slot_count

SKIP_PARTS = build_inputs.SKIP_PARTS
SKIP_SUFFIXES = build_inputs.SKIP_SUFFIXES


# ---------------------------------------------------------------- commands
@dataclass
class Python:
    """A plain Python script, run with this interpreter (or $ATELIER_PYTHON)."""
    script: Path
    args: tuple = ()

    def argv(self, ctx):
        return [os.environ.get('ATELIER_PYTHON') or sys.executable, str(self.script), *map(str, self.args)]


@dataclass
class Blender:
    """A script run by headless Blender; everything after `args` reaches the script after `--`."""
    script: Path
    args: tuple = ()
    threads: int = 6
    factory_startup: bool = False
    env: tuple = ()

    def __repr__(self):
        shown = [f for f in fields(self) if f.name not in ('factory_startup', 'env') or getattr(self, f.name)]
        return f'Blender({", ".join(f"{f.name}={getattr(self, f.name)!r}" for f in shown)})'

    def argv(self, ctx):
        extra = ['--', *map(str, self.args)] if self.args else []
        return [ctx.blender, *(['--factory-startup'] if self.factory_startup else []), '-b', '--threads', str(self.threads), '--python-exit-code', '1',
                '--python', str(self.script), *extra]


GUARD = Path(__file__).with_name('unreal_script_guard.py')
# What decides an isolated script's editor (the descriptor, the closure) and checks it: inputs of every step it runs in
ISOLATION = (GUARD, Path(__file__).with_name('unreal_modules.py'))


@dataclass
class UnrealScript:
    """An editor Python script run by UnrealEditor-Cmd on the game's project; `marker` must appear in the log."""
    script: Path
    marker: str
    null_rhi: bool = False
    env: tuple = ()          # (("NAME", "value"), ...)
    args: tuple = ()         # additional editor arguments for this import
    # (module, ...): the game's compiled modules the script uses (atelier.unreal_modules). The step needs their module
    # steps, and the editor loads only those modules and what they need; unreal_script_guard stops it if any other
    # game or plugin library is loaded when the script ends.
    modules: tuple = ()

    def __repr__(self):
        # The fingerprint's view: declared modules count, and a script without them reads as before they existed.
        shown = [f for f in fields(self) if f.name != 'modules' or self.modules]
        return f'UnrealScript({", ".join(f"{f.name}={getattr(self, f.name)!r}" for f in shown)})'

    def runs(self):
        """Files the command runs besides the step's inputs: the isolation code, when it has modules."""
        return list(ISOLATION) if self.modules else []

    @contextmanager
    def prepared(self, ctx):
        """(argv, environment) for one run. With modules, the guard runs the script in an editor started on a
        descriptor that exists until the run ends (atelier.unreal_modules.descriptor)."""
        if not self.modules:
            yield self._argv(ctx, ctx.uproject, self.script), self.env
            return
        from .unreal_modules import descriptor
        with descriptor(ctx.uproject, self.modules) as (project, left_out):
            yield self._argv(ctx, project, GUARD), (*self.env, ('ATELIER_SCRIPT', str(self.script)),
                                                    ('ATELIER_LEFT_OUT', json.dumps(left_out)))

    def _argv(self, ctx, project, script):
        command = [str(ctx.unreal_cmd), str(project), '-run=pythonscript', f'-script={script}',
                   '-unattended', '-nop4', '-nosplash', '-stdout', '-AllowStdOutLogVerbosity']   # unreal.log lines reach stdout
        return command + (['-NullRHI'] if self.null_rhi else []) + list(self.args)


@dataclass
class UnrealCompile:
    """Compile the game's editor target (C++ module and any project plugins)."""
    target: str

    def argv(self, ctx):
        return [str(ctx.unreal_root / 'Engine/Build/BatchFiles/Mac/Build.sh'), self.target, 'Mac', 'Development',
                f'-project={ctx.uproject}', '-WaitMutex']


@dataclass
class UnrealPackage:
    """Build, cook, stage, package and archive the game with UAT BuildCookRun. The editor must already be compiled.
    Everything under Content is cooked, because the game loads many assets by path at run time. On a Mac, -package
    makes Xcode finalize a self-contained .app; without it the archive step copies the bare Binaries/Mac app, which has
    neither the paks nor the staged runtime data."""
    target: str
    archive: Path
    config: str = 'Development'
    workers: int = 3                    # UAT calls UnrealBuildTool directly, past the capped Build.sh wrapper
    marker: str = 'BUILD SUCCESSFUL'
    timeout: float = 4 * 3600           # the whole package: compile, cook, stage and archive
    # The heavy work happens in UAT's descendants: each gets its own memory guard in the same slot turn.
    watch: tuple = ('UnrealEditor-Cmd', 'UnrealEditor', 'ShaderCompileWorker', 'dotnet')
    progress: float = 25.               # quiet UAT phases still print at least every 30 s

    def argv(self, ctx):
        # UAT reads the build tool's XML config in-process and then runs UnrealBuildTool directly, both past the
        # patched Build.sh that exports the headless user directory. Without it the tool resolves ~/Documents and a
        # headless run waits forever on the macOS privacy check (the first package stalled exactly there).
        from .setup import headless_user_dir
        folder = None if os.environ.get('UE_HEADLESS_USER_DIR') else headless_user_dir(ctx.unreal_root)
        prefix = ['/usr/bin/env', f'UE_HEADLESS_USER_DIR={folder}'] if folder else []
        return prefix + [str(ctx.unreal_root / 'Engine/Build/BatchFiles/RunUAT.sh'), 'BuildCookRun', f'-project={ctx.uproject}',
                f'-target={self.target}', '-platform=Mac', f'-clientconfig={self.config}', '-build',
                f'-ubtargs=-MaxParallelActions={self.workers}', '-cook', '-cookall', '-stage', '-pak', '-package', '-archive',
                f'-archivedirectory={self.archive}', '-nocompileeditor', '-noP4', '-unattended', '-utf8output']


@dataclass
class Call:
    """A Python function `fn(ctx, log)` in the game's build module; `name` makes it part of the fingerprint."""
    name: str
    fn: object = field(compare=False, repr=False)


@dataclass(frozen=True)
class Batch:
    """Independent actions that may share a guarded process; yield at action boundaries."""
    group: str
    runtime_env: tuple[str, ...] = ()
    max_seconds: float = 240.


@dataclass
class Step:
    name: str
    commands: list
    inputs: list = field(default_factory=list)     # files or folders, hashed by content
    deferred_inputs: list[DeferredInputs] = field(default_factory=list, kw_only=True)  # explicit selected-only membership
    needs: list = field(default_factory=list)      # step names whose results this step uses (their fingerprints feed its own)
    after: list = field(default_factory=list)      # step names that only have to run first (a compiled editor): no rerun when they change
    outputs: list = field(default_factory=list)    # must exist after a run; a missing one forces a rerun
    heavy: bool = False                            # take a render slot and the memory guard (Unreal, Blender renders)
    about: str = ''
    pool_roots: list = field(default_factory=list)  # exclusively owned generated folders, opt-in portable pool
    explicit: bool = False                         # only when named exactly (a release package): never in a plain
                                                   # or prefix build
    verify: object = field(default=None, compare=False, repr=False)  # () -> bool: outputs whose names vary are present
    cutoff: bool = False                           # dependents see the hash of its outputs, not its fingerprint
    products: list[Product] = field(default_factory=list)  # independently consumed, exclusively owned outputs
    reads: list[str] = field(default_factory=list)         # product contents feed this step's fingerprint
    references: list[str] = field(default_factory=list)    # include products, without deriving data from them
    cache: bool = False                                   # explicitly portable products; automatic local reuse
    audit: bool = False                                   # observe one Python action's inputs and owned writes
    optional_inputs: list[Path] = field(default_factory=list)  # exact source files: absence is an input identity
    queries: list[BBoxQuery] = field(default_factory=list)     # graph-resolved spatial product reads
    _query_bindings: tuple | None = field(default=None, init=False, repr=False, compare=False)
    toolchain: bool = False                               # installed Python/Blender identity, without cache publication
    batch: Batch | None = None                            # opt-in scripts that reset their own transient process state


def outputs_present(step):
    return all(Path(o).exists() for o in step.outputs) and (step.verify is None or bool(step.verify()))


def module_step(module):
    """The step that records a compiled Unreal module's code digest (atelier.unreal_modules)."""
    return f'unreal.module.{module}'


def check_modules(steps):
    """A script that declares game modules must need their module steps, so their digests feed its fingerprint."""
    for step in steps:
        for command in step.commands:
            missing = [module_step(m) for m in getattr(command, 'modules', ()) if module_step(m) not in step.needs]
            if missing:
                raise SystemExit(f'{step.name}: its script uses {missing} but the step does not need them')


# ---------------------------------------------------------------- context
class Context:
    def __init__(self, game, *, create=True):
        self.game = game
        self.game_dir = paths.game_dir(game)
        self.out = paths.build_dir(game) if create else paths.build_root() / game
        self.logs = self.out / 'logs'
        self.stamps = self.out / 'stamps'
        self.unreal_root = engine.unreal_root()
        self.unreal_cmd = engine.unreal_cmd(self.unreal_root)
        self.unreal_app = engine.unreal_app(self.unreal_root)
        self.blender = engine.blender()
        try:
            self.uproject = paths.uproject(game)
        except FileNotFoundError:
            self.uproject = None

    def env(self, extra=()):
        env = dict(os.environ)
        env['ATELIER_BUILD_ROOT'] = str(paths.build_root())
        env.update(dict(extra))
        return env


def load_recipe(game):
    """games/<game>/build.py as a module."""
    path = paths.game_dir(game) / 'build.py'
    spec = importlib.util.spec_from_file_location(f'atelier_recipe_{game}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- fingerprints
class RecordingDigest:
    """Feed a legacy fingerprint and its explanatory input digest in one streaming pass."""

    def __init__(self, aggregate):
        self.aggregate = aggregate
        self.local = hashlib.sha256()

    def update(self, data):
        self.aggregate.update(data)
        self.local.update(data)


def _hash_path(digest, path, skip=True):
    """Hash a file, or a folder's files; `skip` leaves out what never changes a step's source (SKIP_PARTS)."""
    path = Path(path)
    if path.is_file():
        digest.update(str(path.name).encode())
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b''):
                digest.update(chunk)
    elif path.is_dir():
        depth = len(path.parts)
        for child in sorted(path.rglob('*')):
            if child.is_file() and not (skip and (SKIP_PARTS & set(child.parts) or child.suffix in SKIP_SUFFIXES)):
                # rglob preserves this lexical prefix; avoid searching all parent paths per file.
                digest.update(str(Path(*child.parts[depth:])).encode())
                _hash_path(digest, child, skip)
    else:
        digest.update(b'missing:' + str(path).encode())


def required_inputs(step, *, observation=None):
    named = step.products or step.reads or step.references
    from .build_audit import SUPPORT
    from . import build_spatial
    batch_code = [Path(__file__).with_name(name) for name in ('build_batches.py', 'build_batch_worker.py')] if step.batch else []
    if step.deferred_inputs and observation is None:
        raise ValueError(f'{step.name}: deferred inputs require an explicit input observation')
    inputs = step.inputs if observation is None else observation.paths
    return [*inputs, *batch_code, *(c.script for c in step.commands if named and hasattr(c, 'script')),
            *(p for c in step.commands for p in getattr(c, 'runs', list)()),
            *(SUPPORT if step.audit else ()), *([Path(build_spatial.__file__)] if step.queries else ())]


def declared_inputs(step):
    return [*required_inputs(step), *step.optional_inputs]


def missing_product_inputs(step):
    """Named-product actions require all declared sources; legacy optional inputs stay compatible."""
    if not (step.products or step.reads or step.references):
        return []
    return [str(path) for path in required_inputs(step) if not Path(path).exists()]


def fingerprint(step, done, *, index=None, tool_cache=None, observation=None):
    """@cc [owner:fontanierh,label:correctness] legacy-fingerprint-compatibility
    Legacy steps without deferred inputs MUST retain their existing fingerprint algorithm. Read edges
    MUST include the consumed product's content identity; references and ordering MUST NOT.
    """
    return fingerprint_state(step, done, capture=False, index=index, tool_cache=tool_cache,
                             observation=observation)[0]


def fingerprint_state(step, done, *, capture=True, index=None, tool_cache=None, observation=None):
    """Hash once, optionally retaining per-input identities for build explanations."""
    digest = hashlib.sha256()
    named = bool(step.products or step.reads or step.references)
    hasher = (index.digest if index is not None else build_products.file_digest) if named else None
    if named:
        digest.update(b'product-fingerprint-v2\0')
    # Checkout locations and generated Unreal outputs do not change a step's source. Keeping the command paths
    # relative to their roots also lets a verified build seed another checkout of the same source revision.
    commands = repr([c for c in step.commands])
    commands = commands.replace(str(paths.build_root()), '<build>').replace(str(paths.REPO), '<repo>')
    digest.update(commands.encode())
    state = {'commands': hashlib.sha256(commands.encode()).hexdigest(), 'inputs': {},
             'needs': {name: done.get(name, 'unbuilt') for name in step.needs}}
    from .build_deferred import observe, validate
    validate(step)
    observation = observation if observation is not None else observe(step)
    inputs = required_inputs(step, observation=observation)
    if observation.metadata is not None:
        def portable(value):
            if isinstance(value, str):
                return value.replace(str(paths.build_root()), '<build>').replace(str(paths.REPO), '<repo>')
            if isinstance(value, list):
                return [portable(item) for item in value]
            if isinstance(value, dict):
                return {key: portable(item) for key, item in value.items()}
            return value
        metadata = json.dumps(portable({'providers': json.loads(observation.metadata),
                                        'members': [str(p) for p in observation.members]}), sort_keys=True)
        digest.update(b'deferred-inputs-v1\0' + metadata.encode())
        state['deferred_inputs'] = json.loads(metadata)
    if step.cache or step.audit:
        build_inputs.validate_imports(step, declared_inputs(step))
    for item in inputs:
        if named:
            # Named actions hash a Merkle inventory, not the legacy byte stream. This permits
            # file memoization and includes directory membership and every explicitly selected input.
            options = {'complete': True} if step.audit else {}
            manifest = build_inputs.inventory(item, hasher=hasher, **options) if Path(item).exists() else None
            value = build_products.identity(manifest)
            label = str(item).replace(str(paths.build_root()), '<build>').replace(str(paths.REPO), '<repo>')
            digest.update(json.dumps([label, value]).encode())
            state['inputs'][label] = value
            continue
        if capture:
            recording = RecordingDigest(digest)
            _hash_path(recording, item)
            label = str(item).replace(str(paths.build_root()), '<build>').replace(str(paths.REPO), '<repo>')
            state['inputs'][label] = recording.local.hexdigest()
        else:
            _hash_path(digest, item)
    if step.optional_inputs:
        state['optional_inputs'] = {}
        for item in step.optional_inputs:
            manifest = build_inputs.optional_file(item, hasher=hasher)
            label = str(item).replace(str(paths.build_root()), '<build>').replace(str(paths.REPO), '<repo>')
            value = {'present': manifest['kind'] == 'file', 'identity': build_products.identity(manifest)}
            digest.update(b'optional-file-v1\0' + json.dumps([label, value], sort_keys=True).encode())
            state['optional_inputs'][label] = value
    for need in step.needs:
        digest.update(done.get(need, 'unbuilt').encode())
    if step.products or step.reads or step.references:
        declarations = repr((step.products, step.reads, step.references))
        declarations = declarations.replace(str(paths.build_root()), '<build>').replace(str(paths.REPO), '<repo>')
        consumed = {name: done.get(f'product:{name}', 'unbuilt') for name in step.reads}
        digest.update(json.dumps({'products': declarations, 'reads': consumed}, sort_keys=True).encode())
        state['products'] = declarations
        state['reads'] = consumed
    if step.audit:
        state['audit'] = 1
        digest.update(b'python-input-audit-v1\0')
    if step.queries:
        from .build_spatial import manifest
        declarations = json.dumps(manifest(step), sort_keys=True)
        declarations = declarations.replace(str(paths.build_root()), '<build>').replace(str(paths.REPO), '<repo>')
        state['queries'] = json.loads(declarations)['queries']
        digest.update(b'spatial-inputs-v1\0' + declarations.encode())
    spatial_outputs = {p.name: [p.collection, p.bounds] for p in step.products if p.collection is not None}
    if spatial_outputs:
        state['spatial_outputs'] = spatial_outputs
        digest.update(json.dumps(spatial_outputs, sort_keys=True).encode())
    if step.cache or step.audit or step.toolchain:
        if step.audit:
            from .build_audit import tool_context
        else:
            from .build_cache import tool_context
        state['tools'] = build_products.identity(tool_context(step, hasher, cache=tool_cache))
        digest.update(state['tools'].encode())
    if step.batch:
        state['batch'] = repr(step.batch)
        digest.update(state['batch'].encode())
    return digest.hexdigest(), state


def outputs_digest(step):
    """Every file a step made, whatever its folder or suffix."""
    digest = hashlib.sha256()
    for output in step.outputs:
        _hash_path(digest, output, skip=False)
    return 'outputs:' + digest.hexdigest()


def result(step, current, stamp):
    """What a step's dependents see: its fingerprint, or for a current cutoff step the outputs digest it recorded."""
    if step.cutoff and stamp.get('fingerprint') == current and stamp.get('result'):
        return stamp['result']
    return current


# ---------------------------------------------------------------- running
def order(steps, wanted):
    """Select a dependency-complete, stable topological plan and reject invalid declarations."""
    try:
        return build_products.Graph(steps).select(wanted)
    except ValueError as error:
        raise SystemExit(str(error)) from error


def report_peak(path):
    """The peak footprint in bytes recorded in a guard report, or None."""
    try:
        value = json.loads(Path(path).read_text()).get('peak_bytes')
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, (int, float)) and value > 0 else None


def expected_peak_gib(folder):
    """A heavy step's expected peak in GiB, from its last guard reports: memory-health.json (the last command run) and
    step-peak.json (every command of the last complete run), whichever is higher. None before any report."""
    peaks = [p for p in (report_peak(folder / 'memory-health.json'), report_peak(folder / 'step-peak.json')) if p]
    return max(peaks) / GiB if peaks else None


def slot_request(ctx, step):
    """How a heavy step asks for a render slot: (kind, expected peak in GiB). A compile always takes the big slot (and
    holds the small one); a step with no guard report has no expected peak and takes the big one. render_lock decides
    the rest (the 3 GiB bound, the switch, free memory)."""
    if any(isinstance(c, (UnrealCompile, UnrealPackage)) for c in step.commands):
        return 'compile', None
    return 'job', expected_peak_gib(ctx.logs / f'{step.name}.guard')


def run_command(ctx, step, command, log, request=None, slots=None, *, products=None, audit_receipt=None):
    """Run one command of a step. A heavy step's command runs under guarded.run, in a render slot asked for with
    `request` (slot_request's answer, computed now when absent); the slot is written to the log and added to `slots`."""
    if isinstance(command, Call):
        return command.fn(ctx, log)
    if step.audit:
        from . import build_audit
        with build_audit.prepared(ctx, step, products, receipt=audit_receipt) as (argv, env, descriptors):
            return run_argv(ctx, step, command, argv, env, log, request, slots, pass_fds=descriptors)
    if isinstance(command, UnrealScript):
        with command.prepared(ctx) as (argv, env):
            return run_argv(ctx, step, command, argv, env, log, request, slots)
    return run_argv(ctx, step, command, command.argv(ctx), getattr(command, 'env', ()), log, request, slots)


def run_argv(ctx, step, command, argv, env, log, request, slots, *, pass_fds=()):
    env = ctx.env(env)
    log.write(f'$ {" ".join(argv)}\n'); log.flush()
    if step.heavy:
        folder = ctx.logs / f'{step.name}.guard'
        kind, small_gib = request or slot_request(ctx, step)
        used = []

        def note(slot, why):
            used.append(slot)
            if slots is not None:
                slots.append(slot)
            why = why or ('no guard report yet' if kind == 'job' and small_gib is None else '')
            log.write(f'render slot: {slot}' + (f' ({why})' if why else '') + '\n'); log.flush()
        inherited = {'pass_fds': pass_fds} if pass_fds else {}
        code = guarded.run(argv, folder, purpose=f'atelier build {ctx.game} {step.name}', env=env,
                           small_gib=small_gib, kind=kind, on_slot=note, timeout=getattr(command, 'timeout', 0.),
                           watch=getattr(command, 'watch', ()), progress=getattr(command, 'progress', 0.),
                           **inherited, **({'on_poll': command.on_poll} if hasattr(command, 'on_poll') else {}))
        text = (folder / 'stdout.log').read_text(errors='ignore')
        log.write(text)
        if code and used == ['small']:
            try:
                stopped = json.loads((folder / 'memory-health.json').read_text()).get('state') == 'memory_limit'
            except (OSError, ValueError, AttributeError):
                stopped = False
            if stopped:
                raise RuntimeError(f'{step.name}: stopped at the small render slot\'s memory limit; '
                                   f'its report now sends it to the big slot, run it again')
    else:
        from .safety.process import policy_command
        result = subprocess.run(policy_command(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                text=True, errors='ignore', **({'pass_fds': pass_fds, 'stdin': subprocess.DEVNULL} if pass_fds else {}))
        code, text = result.returncode, result.stdout
        log.write(text)
    if code:
        raise RuntimeError(f'{step.name}: command exited {code}')
    marker = getattr(command, 'marker', None)
    if marker and marker not in text:
        raise RuntimeError(f'{step.name}: "{marker}" missing from the log')
    from .build_timings import parse_phases
    return parse_phases(text, allow_echo=isinstance(command, UnrealScript))


def slot_summary(slots):
    """', small slot' for the summary line when two render slots are on (or a step used the small one)."""
    if not slots or (slot_count() != 2 and 'small' not in slots):
        return ''
    if len(set(slots)) == 1:
        return f', {slots[0]} slot'
    return f', slots {" then ".join(slots)}'


def build(game, wanted=(), force=False, dry=False, touch=False, echo=print, verify=False):
    from .build_snapshot import require_complete
    require_complete(paths.build_root() / game, game=game)
    if dry:
        from .build_plan import show
        return show(game, wanted, force=force, echo=echo, verify=verify)
    ctx = Context(game)
    from .build_hashes import HashIndex
    with HashIndex(ctx.out / '.state' / 'file-hashes.sqlite3', verify=verify) as index:
        return _build(ctx, wanted, force=force, touch=touch, echo=echo, index=index)


def _build(ctx, wanted, *, force, touch, echo, index, steps=None, produced=None):
    checkpoint = {}
    try:
        code = _execute_build(ctx, wanted, force=force, touch=touch, echo=echo, index=index,
                              steps=steps, produced=produced, checkpoint=checkpoint)
    finally:
        # Failure and yield paths must also discard earlier certificates with changed reads.
        invalid = _discard_changed_certificates(ctx, checkpoint, index=index)
    if invalid:
        echo('FAILED: products changed after their owner completed: ' + ', '.join(invalid))
        return 1
    return code


def _discard_changed_certificates(ctx, checkpoint, *, index):
    """@cc [owner:fontanierh,label:correctness] completed-product-checkpoint
    Every build exit MUST discard selected completed/current certificates whose owned products
    or consumed products changed, including legacy-output consumers and failed/yielded builds.
    Producer inventories MUST be fresh for this checkpoint; reference bytes MUST NOT invalidate
    a consumer. Reuse each observed producer inventory only within this checkpoint.
    """
    from .build_plan import read_stamp
    done, plan = checkpoint.get('done', {}), checkpoint.get('plan', ())
    observed, fresh = {}, {}
    for step in plan:
        if step.name not in done:
            continue
        try:
            observed[step.name] = build_products.records(step, hasher=index.digest)
        except (OSError, ValueError):
            observed[step.name] = None
        build_products.feed_results(fresh, observed[step.name])
    invalid = []
    for step in plan:
        if step.name not in done:
            continue
        stamp = ctx.stamps / (step.name + '.json')
        outputs_changed = step.products and observed[step.name] != read_stamp(stamp).get('products', {})
        reads_changed = any(fresh.get('product:' + name) != done.get('product:' + name) for name in step.reads)
        if outputs_changed or reads_changed:
            stamp.unlink(missing_ok=True)
            invalid.append(step.name)
    return invalid


def _execute_build(ctx, wanted, *, force, touch, echo, index, steps, produced, checkpoint):
    # A trusted producer can supply the exact singleton declarations it already vetted, avoiding
    # a second recipe import that could choose a different action or introduce native prerequisites.
    from . import build_batches, build_cache
    from .build_snapshot import require_complete
    require_complete(ctx.out, game=ctx.game)
    game = ctx.game
    if steps is None:
        steps = load_recipe(game).steps(ctx)
    check_modules(steps)
    plan = order(steps, list(wanted))
    declared_products = {p.name: p for s in steps for p in s.products}
    for step in plan:
        if step.toolchain and not step.products:
            raise SystemExit(f'{step.name}: an explicit toolchain identity requires named products')
        try:
            build_batches.validate(step)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        if step.cache or step.audit:
            try:
                if step.audit:
                    from .build_audit import roots
                    roots(ctx, step)
                else:
                    build_cache.roots(ctx, step)
            except ValueError as error:
                raise SystemExit(str(error)) from error
    if touch and any(step.products for step in plan):
        raise SystemExit('Named products require a successful build; --touch cannot certify them')
    remote = None
    if not force and not touch and any(step.cache for step in plan):
        from . import artifact_remote
        try:
            remote = artifact_remote.configured()
        except artifact_remote.RemoteError as error:
            echo(f'Remote cache unavailable ({error}); continuing locally')
    ctx.logs.mkdir(parents=True, exist_ok=True)
    ctx.stamps.mkdir(parents=True, exist_ok=True)
    done, ran, restored = {}, 0, 0
    checkpoint.update(plan=plan, done=done)
    tool_cache = {}
    def verify_spatial(step, expected):
        if step.queries:
            from .build_spatial import verify_current
            fresh = verify_current(ctx, step, done, hasher=index.digest)
            if fingerprint(fresh, done, index=index, tool_cache=tool_cache) != expected:
                raise ValueError(f'{step.name}: spatial action changed; rerun the build to replan')

    # The graph includes every prerequisite. Unrelated stamps cannot affect this selected build.
    started = time.monotonic()
    completed_batches = set()
    for position, step in enumerate(plan):
        if step.name in completed_batches:
            continue
        print_ = f'{step.name:34s}'
        stamp = ctx.stamps / f'{step.name}.json'
        journal = ctx.stamps / f'{step.name}.restore.json'
        if step.cache:
            build_cache.recover(ctx, step)
        if journal.exists():
            # An interrupted replacement is never certified by an old stamp.
            stamp.unlink(missing_ok=True)
        missing = missing_product_inputs(step)
        if missing:
            echo(f'{print_} FAILED: required inputs missing: {missing[:3]}')
            return 1
        try:
            current, input_state = fingerprint_state(step, done, index=index, tool_cache=tool_cache)
        except (OSError, ValueError, SyntaxError) as error:
            if step.queries:
                stamp.unlink(missing_ok=True)
            echo(f'{print_} FAILED: {error}')
            return 1
        from .build_plan import read_stamp
        previous = read_stamp(stamp)
        outputs_ok = outputs_present(step)
        if step.products:
            outputs_ok = outputs_ok and build_products.valid_records(step, previous.get('products', {}), hasher=index.digest)
        try:
            verify_spatial(step, current)
        except (OSError, ValueError, SyntaxError) as error:
            stamp.unlink(missing_ok=True)
            echo(f'{print_} FAILED: {error}')
            return 1
        if not force and previous.get('fingerprint') == current and outputs_ok:
            done[step.name] = result(step, current, previous)
            build_products.feed_results(done, previous.get('products', {}))
            echo(f'{print_} up to date')
            continue
        if touch:   # the outputs are known to be current (a refactor of the recipe): record them without running
            if not outputs_ok:
                echo(f'{print_} not touched: outputs missing')
                continue
            touched = {'fingerprint': current, 'seconds': previous.get('seconds'), 'time': time.time(), 'touched': True}
            if step.cutoff:
                touched['result'] = outputs_digest(step)
            stamp.write_text(json.dumps(touched) + '\n')
            done[step.name] = result(step, current, touched)
            echo(f'{print_} touched')
            continue
        try:
            batch = build_batches.select(ctx, plan, position, done, force=force, index=index, tool_cache=tool_cache)
        except (OSError, ValueError, SyntaxError) as error:
            echo(f'{print_} FAILED: {error}')
            return 1
        if batch:
            completed, code = build_batches.run(ctx, batch, done, index=index, tool_cache=tool_cache,
                                                echo=echo, products=declared_products, wanted=wanted)
            completed_batches.update(completed)
            ran += len(completed)
            if code:
                return code
            continue
        pool_key = None
        if step.pool_roots:
            from . import artifact_pool
            pool_key = artifact_pool.key(ctx, step, current)
        t0 = time.monotonic()
        log_path = ctx.logs / f'{step.name}.log'
        slots, peaks, command_times = [], [], []
        audit_receipt = {}
        products = None
        restore_source = None
        store = build_cache.Store() if step.cache else None
        try:
            verify_spatial(step, current)
        except (OSError, ValueError, SyntaxError) as error:
            stamp.unlink(missing_ok=True)
            echo(f'{print_} FAILED: {error}')
            return 1
        if store is not None and not force:
            try:
                # Source change metadata is local; all transferred output bytes are verified below.
                if fingerprint(step, done, index=index, tool_cache=tool_cache) != current:
                    raise RuntimeError('Inputs changed before cache lookup')
                products = store.restore(ctx, step, current)
                if products is not None:
                    restore_source = 'local'
                if products is None and remote is not None and remote.fetch(current, store, echo):
                    products = store.restore(ctx, step, current)
                    if products is not None:
                        restore_source = 'https'
                if products is not None and (fingerprint(step, done, index=index, tool_cache=tool_cache) != current or not outputs_present(step)):
                    raise RuntimeError('Restored action inputs or required outputs differ')
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
                echo(f'{print_} cache unavailable ({error}); building')
                products = None
        from_cache = products is not None
        with open(log_path, 'w') as log:
            try:
                stamp.unlink(missing_ok=True)
                # Also covers a restored hit. A changed catalogue is not a cache miss: continuing
                # would execute an obsolete plan whose newly selected producers have not run.
                verify_spatial(step, current)
                request = slot_request(ctx, step) if step.heavy else None   # from the reports of the previous run
                for command in (() if from_cache else step.commands):
                    from .build_timings import clear_launch_report, launch_receipt
                    launch_folder = ctx.logs / f'{step.name}.guard'
                    fresh_launch = (step.heavy and not isinstance(command, Call)
                                    and clear_launch_report(launch_folder))
                    command_started = time.monotonic()
                    audited = {'products': declared_products, 'audit_receipt': audit_receipt} if step.audit else {}
                    phases = run_command(ctx, step, command, log, request, slots, **audited)
                    timing = {'kind': type(command).__name__, 'seconds': round(time.monotonic() - command_started, 3),
                              'scope': 'command invocation'}
                    if not isinstance(command, Call) and phases is not None:
                        timing['phases'] = phases
                    if fresh_launch:
                        launch = launch_receipt(launch_folder)
                        if launch is not None:
                            timing['launcher'] = launch
                    command_times.append(timing)
                    if step.heavy and not isinstance(command, Call):
                        peaks.append(report_peak(ctx.logs / f'{step.name}.guard' / 'memory-health.json'))
                missing = [str(o) for o in step.outputs if not Path(o).exists()]
                if step.verify is not None and not step.verify():
                    missing.append(f'{step.name} verification')
                if missing:
                    raise RuntimeError(f'{step.name}: outputs missing after the run: {missing[:3]}')
                products = build_products.records(step)
                build_products.verify_reads(step, declared_products, done)
                if (step.products or step.deferred_inputs) and fingerprint(step, done, index=index, tool_cache=tool_cache) != current:
                    raise RuntimeError(f'{step.name}: inputs changed during build; outputs not certified')
                verify_spatial(step, current)
            except Exception as error:
                log.flush()
                tail = log_path.read_text(errors='ignore').splitlines()[-25:]
                echo(f'{print_} FAILED ({error})\n  log: {log_path}\n    ' + '\n    '.join(tail))
                stamp.unlink(missing_ok=True)
                return 1
        seconds = time.monotonic() - t0
        if peaks and None not in peaks:   # a step with several commands: its report keeps only the last one's peak
            (ctx.logs / f'{step.name}.guard' / 'step-peak.json').write_text(
                json.dumps({'peak_bytes': max(peaks), 'commands': peaks, 'time': time.time()}) + '\n')
        record = {'fingerprint': current, 'seconds': round(seconds, 3), 'time': time.time(),
                  'input_state': input_state, 'commands': command_times}
        if audit_receipt and not from_cache:
            record['audit_receipt'] = audit_receipt
        if step.products or 'product_roots' in previous:
            from . import build_changes
            record['products'] = products
            record['product_roots'] = build_changes.root_labels(ctx, step)
            optional = build_changes.optional_roots(step)
            if optional:
                record['product_optional_roots'] = optional
            record['output_changes'] = build_changes.compare(previous, products, record['product_roots'],
                                                             restored=from_cache, optional=optional)
        if from_cache:
            record['restored_from'] = current
            record['restore_source'] = restore_source
            if previous.get('fingerprint') == current:
                from .build_timings import producer_receipt
                producer = producer_receipt(previous)
                if producer is not None:
                    record['producer_receipt'] = producer
        if step.cutoff:
            record['result'] = outputs_digest(step)
        if pool_key is not None:
            if fingerprint(step, done) != current or artifact_pool.key(ctx, step, current) != pool_key:
                stamp.unlink(missing_ok=True)
                raise RuntimeError('Pool tool context changed during build; outputs not certified')
            record['pool_key'] = pool_key
        temporary = stamp.with_suffix('.tmp')
        temporary.write_text(json.dumps(record) + '\n')
        temporary.replace(stamp)
        journal.unlink(missing_ok=True)
        if store is not None and not from_cache:
            try:
                store.publish(ctx, step, current, products)
            except (OSError, ValueError, KeyError, TypeError) as error:
                echo(f'{print_} cache publication skipped ({error})')
        done[step.name] = result(step, current, record)
        build_products.feed_results(done, products)
        restored += int(from_cache)
        ran += int(not from_cache)
        if produced is not None and not from_cache:
            produced.append((step.name, record))
        echo(f'{print_} {"restored" if from_cache else "done"} in {seconds:.1f} s{slot_summary(slots)}')
    echo(f'{len(plan)} steps, {ran} ran, {restored} restored, {time.monotonic() - started:.0f} s')
    return 0


def list_steps(game, echo=print):
    ctx = Context(game, create=False)
    for s in load_recipe(game).steps(ctx):
        needs = f'  (needs {", ".join(s.needs)})' if s.needs else ''
        needs += f'  (after {", ".join(s.after)})' if s.after else ''
        needs += f'  (products {", ".join(p.name for p in s.products)})' if s.products else ''
        needs += f'  (reads {", ".join(s.reads)})' if s.reads else ''
        needs += f'  (references {", ".join(s.references)})' if s.references else ''
        echo(f'{s.name:34s} {s.about}{needs}')
