"""The build engine: named steps with inputs and dependencies, rerun only when something they read changed.

A game describes its build in `games/<game>/build.py`, a module with `steps()` returning a list of `Step`s. A step's
fingerprint is the hash of its inputs (files or folders, by content), its commands, and the fingerprints of the steps
it needs; `build/<game>/stamps/<step>.json` remembers the last good one. Logs go to `build/<game>/logs/<step>.log`.
A `cutoff` step gives its dependents the hash of its outputs instead of its fingerprint: when it reruns and makes the
same outputs, they stay current.

Commands are plain data (`Python`, `Blender`, `UnrealScript`, `UnrealCompile`, `UnrealPackage`, `Call`), so the fingerprint changes
when a command does.

A `heavy` step's commands run under `atelier.harness.safety.guarded`: a render slot and the memory guard, whose report is
`logs/<step>.guard/memory-health.json`. When two render slots are on (`atelier.harness.safety.render_lock`), a step whose last
completed run peaked at 3 GiB or less asks for the small slot; a compile, or a step with no completed run yet, takes the big
one. The step's log names the slot each command used, and the summary line names it too when two slots are on.
"""
import hashlib, importlib.util, json, math, os, subprocess, sys, time
import ast
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from functools import lru_cache
from pathlib import Path

from . import engine, paths
from . import build_inputs, build_products, build_source, source_imports
from .build_hashes import signature as _stat_signature
from .build_source import Python, Blender
from .build_products import Product
from .build_deferred import DeferredInputs
from .build_spatial import BBoxQuery
from .build_cook import CookMode
from .play_limits import GAME_GIB, GAME_MAX_GIB
from atelier.harness.safety import guarded
from atelier.harness.safety.render_lock import GiB, slot_count

SKIP_PARTS = build_inputs.SKIP_PARTS
SKIP_SUFFIXES = build_inputs.SKIP_SUFFIXES

_CLOSURE_CACHE = {}
_SOURCE_TOKEN_IMPORTS = {}


@lru_cache(maxsize=2048)
def _parse_imports_text(text):
    imports = []
    todo = [ast.parse(text)]
    while todo:
        node = todo.pop()
        for field_name in ('body', 'orelse', 'finalbody', 'handlers', 'cases'):
            value = getattr(node, field_name, ())
            if isinstance(value, list):
                todo.extend(value)
        if isinstance(node, ast.Import):
            imports.append((0, tuple(a.name for a in node.names)))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            names = (module, *(f'{module}.{a.name}'.lstrip('.') for a in node.names if a.name != '*'))
            imports.append((node.level, names))
    return tuple(imports)


def _fast_import_names(source, change_token):
    key = (source, change_token)
    cached = _SOURCE_TOKEN_IMPORTS.get(key)
    if cached is not None:
        return cached
    text = source.read_text()
    if _stat_signature(source.stat()) != change_token:
        raise ValueError(f'Imported source changed while reading: {source}')
    result = _parse_imports_text(text)
    if len(_SOURCE_TOKEN_IMPORTS) > 8192:
        _SOURCE_TOKEN_IMPORTS.clear()
    _SOURCE_TOKEN_IMPORTS[key] = result
    return result


class _FastImportScanner(source_imports.ImportScanner):
    def __init__(self):
        super().__init__()
        self._realpaths = {}
        self._tokens = {}
        self._direct = {}
        self._closures = {}
        self._call_cache = {}
        self._missed = {}
        self._checked_missed = set()

    def _realpath(self, path):
        path = Path(path)
        try:
            return self._realpaths[path]
        except KeyError:
            resolved = path.resolve()
            self._realpaths[path] = resolved
            self._realpaths[resolved] = resolved
            return resolved

    def _token(self, source):
        try:
            return self._tokens[source]
        except KeyError:
            token = _stat_signature(source.stat())
            self._tokens[source] = token
            return token

    def _missed_clear(self, candidates):
        checked = self._checked_missed
        for candidate in candidates:
            if candidate not in checked:
                if candidate.is_file():
                    return False
                checked.add(candidate)
        return True

    def _resolve_with_missed(self, root, parts):
        key = (root, tuple(parts))
        if key in self.resolved:
            return self.resolved[key], self._missed[key]
        namespace_parents = []
        if root == paths.STUDIO / 'atelier':
            root, parts = paths.STUDIO, ['atelier', *parts]
        if root == paths.STUDIO and parts and parts[0] == 'atelier':
            namespace_parents = [paths.STUDIO / 'atelier' / '__init__.py']
            if len(parts) > 1 and parts[1] == 'harness':
                root, parts = paths.HARNESS, parts[1:]
            elif len(parts) > 1 and (parts[1] in {'board', 'capacity', 'safety'}
                                    or parts[1].startswith(('board_', 'capacity_'))):
                root, parts = paths.HARNESS, ['harness', *parts[1:]]
        target = root.joinpath(*parts)
        candidates = [target / '__init__.py'] if not parts else [target.with_suffix('.py'), target / '__init__.py']
        missed = []
        found = None
        for candidate in candidates:
            if candidate.is_file():
                found = candidate
                break
            missed.append(candidate)
        if found:
            parents = [root.joinpath(*parts[:i], '__init__.py') for i in range(1, len(parts))]
            result = [found]
            for parent_init in [*parents, *namespace_parents]:
                if parent_init.is_file():
                    result.append(parent_init)
                else:
                    missed.append(parent_init)
        else:
            result = []
        self.resolved[key] = result
        self._missed[key] = tuple(missed)
        return result, self._missed[key]

    def resolve(self, root, parts):
        return self._resolve_with_missed(root, parts)[0]

    def local_imports(self, script, roots=()):
        repo = self._realpath(paths.REPO)
        studio = self._realpath(Path(source_imports.__file__).parent.parent)
        raw_key = (repo, studio, script, tuple(roots))
        if raw_key in self._call_cache:
            return list(self._call_cache[raw_key])
        script = self._realpath(script)
        ancestors = []
        for parent in script.parents:
            ancestors.append(parent)
            if parent == repo:
                break
        else:
            ancestors = [p for p in script.parents if p.is_relative_to(repo)]
        resolved_roots = tuple(self._realpath(r) for r in roots)
        search = tuple(dict.fromkeys([*ancestors, studio, *resolved_roots]))
        closure_key = (repo, studio, script, search)
        if closure_key in self._closures:
            self._call_cache[raw_key] = self._closures[closure_key]
            return list(self._closures[closure_key])
        cached = _CLOSURE_CACHE.get(closure_key)
        if cached is not None:
            cached_result, cached_tokens, cached_missed, cached_bindings = cached
            try:
                if (all(self._token(f) == tok for f, tok in cached_tokens)
                        and self._missed_clear(cached_missed)
                        and all(raw.resolve() == target for raw, target in cached_bindings)):
                    self._closures[closure_key] = cached_result
                    self._call_cache[raw_key] = cached_result
                    return list(cached_result)
            except OSError:
                pass
        seen, todo = set(), [script]
        all_missed = set()
        bindings = {}
        while todo:
            raw = todo.pop()
            source = self._realpath(raw)
            if raw != source:
                bindings[raw] = source
            if source in seen:
                continue
            seen.add(source)
            direct_key = (source, search)
            if direct_key in self._direct:
                found_all, direct_missed = self._direct[direct_key]
                todo.extend(found_all)
                all_missed.update(direct_missed)
                continue
            found_all = []
            direct_missed = []
            for level, names in _fast_import_names(source, self._token(source)):
                bases = (source.parent, *search)
                if level:
                    if level > len(source.parents):
                        raise ValueError(f'Invalid relative import in {source}')
                    bases = (source.parents[level - 1],)
                for name in names:
                    parts = name.split('.') if name else []
                    for base in bases:
                        found, missed = self._resolve_with_missed(base, parts)
                        direct_missed.extend(missed)
                        if found:
                            found_all.extend(found)
                            break
            self._direct[direct_key] = (tuple(found_all), tuple(dict.fromkeys(direct_missed)))
            todo.extend(found_all)
            all_missed.update(direct_missed)
        result = tuple(sorted(seen))
        self._closures[closure_key] = result
        self._call_cache[raw_key] = result
        _CLOSURE_CACHE[closure_key] = (
            result,
            tuple((f, self._token(f)) for f in result),
            tuple(sorted(all_missed)),
            tuple(sorted(bindings.items())),
        )
        return list(result)


source_imports.ImportScanner = _FastImportScanner
build_inputs.ImportScanner = _FastImportScanner


# ---------------------------------------------------------------- commands
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
    memory_gib: float = 10.  # explicit per-command ceiling; full-capacity reservation grows with it

    def __post_init__(self):
        self.memory_limit()

    def memory_limit(self):
        """@cc [owner:fontanierh,label:safety] explicit-script-memory-envelope
        Script ceilings MUST be finite 10–24 GiB numbers. A nondefault ceiling MUST use one
        aggregate heavy guard and matching full-capacity reservation; the default command
        representation MUST remain unchanged. Warm batches MUST refuse nondefault ceilings.
        """
        if (type(self.memory_gib) not in (int, float) or not math.isfinite(self.memory_gib)
                or not 10 <= self.memory_gib <= 24):
            raise ValueError('UnrealScript memory_gib must be a finite number from 10 to 24 GiB')
        return self.memory_gib

    def validate_step(self, step):
        if self.memory_limit() != 10 and (not step.heavy or step.batch is not None or 'ATELIER_BATCH' in dict(self.env)):
            raise ValueError('An explicit script ceiling requires a separate guarded heavy command, without batching')

    def __repr__(self):
        # The fingerprint's view: declared modules count, and a script without them reads as before they existed.
        shown = [f for f in fields(self) if (f.name != 'modules' or self.modules)
                 and (f.name != 'memory_gib' or self.memory_limit() != 10)]
        return f'UnrealScript({", ".join(f"{f.name}={getattr(self, f.name)!r}" for f in shown)})'

    def runs(self):
        """Files the command runs besides the step's inputs: the isolation code, when it has modules."""
        inputs = list(ISOLATION) if self.modules else []
        preflight = dict(self.env).get('ATELIER_UNREAL_PREFLIGHT')
        if preflight is not None:
            inputs.extend([Path(__file__).with_name('unreal_preflight.py'),
                           *build_inputs.local_imports(Path(preflight))])
        return inputs

    def prepared_argv(self, argv):
        overrides = dict(self.env)
        script = overrides.get('ATELIER_UNREAL_PREFLIGHT')
        if script is None:
            return argv
        from .unreal_preflight import wrap
        return wrap(argv, script, overrides.get('ATELIER_BATCH'))

    @contextmanager
    def prepared(self, ctx):
        """(argv, environment) for one run. With modules, the guard runs the script in an editor started on a
        descriptor that exists until the run ends (atelier.unreal_modules.descriptor)."""
        if not self.modules:
            yield self.prepared_argv(self._argv(ctx, ctx.uproject, self.script)), self.env
            return
        from .unreal_modules import descriptor
        with descriptor(ctx.uproject, self.modules) as (project, left_out):
            yield self.prepared_argv(self._argv(ctx, project, GUARD)), (*self.env, ('ATELIER_SCRIPT', str(self.script)),
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
    cook_mode: CookMode = CookMode.DEFAULT

    def __post_init__(self):
        self.cook_mode = CookMode(self.cook_mode)

    def __repr__(self):
        """@cc [owner:fontanierh,label:correctness] explicit-cook-mode-identity
        Default package representation and argv MUST retain their preexisting shape. Package
        lifecycle implementation MUST enter the action inputs without invalidating unrelated commands.
        Nondefault cook mode MUST enter command identity on every recipe and receipt reload.
        """
        shown = [f for f in fields(self) if f.name != 'cook_mode' or self.cook_mode != CookMode.DEFAULT]
        return f'UnrealPackage({", ".join(f"{f.name}={getattr(self, f.name)!r}" for f in shown)})'

    def runs(self):
        return [Path(__file__).with_name(name) for name in ('build_cook.py', 'build_zen.py')]

    def argv(self, ctx):
        from .build_cook import options
        extra = options(self.cook_mode, ctx.unreal_root)
        # UAT reads the build tool's XML config in-process and then runs UnrealBuildTool directly, both past the
        # patched Build.sh that exports the headless user directory. Without it the tool resolves ~/Documents and a
        # headless run waits forever on the macOS privacy check (the first package stalled exactly there).
        from .setup import headless_user_dir
        folder = None if os.environ.get('UE_HEADLESS_USER_DIR') else headless_user_dir(ctx.unreal_root)
        prefix = ['/usr/bin/env', f'UE_HEADLESS_USER_DIR={folder}'] if folder else []
        return prefix + [str(ctx.unreal_root / 'Engine/Build/BatchFiles/RunUAT.sh'), 'BuildCookRun', f'-project={ctx.uproject}',
                f'-target={self.target}', '-platform=Mac', f'-clientconfig={self.config}', '-build',
                f'-ubtargs=-MaxParallelActions={self.workers}', '-cook', '-cookall', '-stage', '-pak', '-package', '-archive',
                f'-archivedirectory={self.archive}', '-nocompileeditor', '-noP4', '-unattended', '-utf8output', *extra]


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
    cook_recovery: object = field(default=None, repr=False, compare=False)  # narrowly opted-in cook certification policy
    checkpoint_previous_needs: tuple | None = field(default=None, repr=False)  # equivalent dependency-boundary migration only
    checkpoint_restore: object = field(default=None, repr=False)  # optional non-destructive recertification callback
    checkpoint_outputs: tuple = field(default=(), repr=False)  # complete additional output roots, never representative samples
    candidate_scope: object = field(default=None, repr=False, compare=False)  # generic compatibility candidates; native validation still required
    replan: bool = field(default=False, kw_only=True)  # reload recipe after a completed source planner


def outputs_present(step):
    return all(Path(o).exists() for o in step.outputs) and (step.verify is None or bool(step.verify()))


def module_step(module):
    """The step that records a compiled Unreal module's code digest (atelier.unreal_modules)."""
    return f'unreal.module.{module}'


def check_source_launch(steps):
    """@cc [owner:fontanierh,label:correctness] recipe-launch-preflight
    Cached Blender actions MUST declare factory startup. Invalid declarations
    MUST refuse before checkpoint restoration, prerequisite execution or installed
    tool-context inventory. This declaration check MUST NOT add fingerprint
    fields or change command representations.
    """
    for step in steps:
        if type(getattr(step, 'replan', False)) is not bool or (getattr(step, 'replan', False) and (not step.products or not step.commands
                or any(not isinstance(c, (Call, Python, Blender)) for c in step.commands))):
            raise ValueError(f'{step.name}: recipe planners require complete source products')
        for command in step.commands:
            if step.cache and isinstance(command, Blender) and not command.factory_startup:
                raise ValueError(f'{step.name}: cached Blender commands require factory_startup=True')


def check_modules(steps):
    """A script that declares game modules must need their module steps, so their digests feed its fingerprint."""
    check_source_launch(steps)
    from .mesh_export_contract import check_steps
    check_steps(steps, Blender)
    for step in steps:
        for command in step.commands:
            if isinstance(command, UnrealScript):
                command.validate_step(step)
            missing = [module_step(m) for m in getattr(command, 'modules', ()) if module_step(m) not in step.needs]
            if missing:
                raise SystemExit(f'{step.name}: its script uses {missing} but the step does not need them')


def cook_memory_limit(value, wanted=None):
    """@cc [owner:fontanierh,label:safety] invocation-cook-memory
    An explicitly selected cook ceiling MUST be finite and within 10–24 GiB, validated before
    creating a build context. It MUST select exactly unreal.cook or unreal.package and MUST
    affect only typed UnrealPackage execution, not command argv, representation or action keys.
    The default MUST retain the existing guard/reservation path. The selected ceiling MUST
    reach the child/tree guards and the matching full-capacity compile reservation together.
    """
    if value is not None:
        if type(value) not in (int, float) or not math.isfinite(value) or not GAME_GIB <= value <= GAME_MAX_GIB:
            raise ValueError(f'Cook memory ceiling must be {GAME_GIB:g} to {GAME_MAX_GIB:g} GiB')
        if wanted is not None and list(wanted) not in (['unreal.cook'], ['unreal.package']):
            raise ValueError('--cook-memory-gib requires exactly unreal.cook or unreal.package')
    return value


# ---------------------------------------------------------------- context
class Context:
    def __init__(self, game, *, create=True, cook_mode=None, cook_reason=None, recover_cook=None, record_cook_recovery=False, cook_memory_gib=None):
        self.cook_memory_gib = cook_memory_limit(cook_memory_gib)
        from .build_cook import measurement_reason
        self.cook_reason = measurement_reason(cook_reason)
        self.cook_mode = CookMode.DEFAULT if cook_mode is None else CookMode(cook_mode)
        self.recover_cook = recover_cook
        self.record_cook_recovery = record_cook_recovery
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
        """Compatibility environment for native callers; source actions use the keyed adapter directly."""
        return build_source.environment(extra)


def load_recipe(game):
    """games/<game>/build.py as a module."""
    path = paths.game_dir(game) / 'build.py'
    spec = importlib.util.spec_from_file_location(f'atelier_recipe_{game}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_steps = module.steps
    def steps(ctx):
        from .build_cook import apply
        return apply(ctx, original_steps(ctx))
    module.steps = steps
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


def _hash_path(digest, path, skip=True, shadow=False):
    """Hash a file, or a folder's files; `skip` leaves out what never changes a step's source (SKIP_PARTS).

    With shadow, each file contributes its stat identity instead of its bytes (a memo key only).
    """
    path = Path(path)
    if path.is_file():
        digest.update(str(path.name).encode())
        if shadow:
            info = path.stat()
            digest.update(f'{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}:{info.st_ino}:{info.st_mode}\0'.encode())
            return
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b''):
                digest.update(chunk)
    elif path.is_dir():
        depth = len(path.parts)
        for child in sorted(path.rglob('*')):
            if child.is_file() and not (skip and (SKIP_PARTS & set(child.parts) or child.suffix in SKIP_SUFFIXES)):
                # rglob preserves this lexical prefix; avoid searching all parent paths per file.
                digest.update(str(Path(*child.parts[depth:])).encode())
                _hash_path(digest, child, skip, shadow)
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


def fingerprint(step, done, *, index=None, tool_cache=None, observation=None, _input_bytes=None, _tool_identity=None):
    """@cc [owner:fontanierh,label:correctness] legacy-fingerprint-compatibility
    Legacy steps without deferred inputs MUST retain their existing fingerprint algorithm. Read edges
    MUST include the consumed product's content identity; references and ordering MUST NOT.
    """
    return fingerprint_state(step, done, capture=False, index=index, tool_cache=tool_cache,
                             observation=observation, _input_bytes=_input_bytes, _tool_identity=_tool_identity)[0]


def fingerprint_state(step, done, *, capture=True, index=None, tool_cache=None, observation=None, _input_bytes=None, _tool_identity=None):
    """@cc [owner:fontanierh,label:correctness;performance] legacy-fingerprint-memo
    A legacy byte-stream fingerprint MAY be reused from the build's hash index only under a key
    that covers everything the fingerprint covers, with each input file's bytes replaced by its
    identity, size, mode and nanosecond modification/change times. Verification mode, replaced
    input bytes and named (Merkle) fingerprints MUST compute directly. The value MUST be exactly
    what the direct computation returned.
    """
    named = bool(step.products or step.reads or step.references)
    if index is None or named or _input_bytes or getattr(index, 'verify', False):
        return _fingerprint_state(step, done, capture=capture, index=index, tool_cache=tool_cache,
                                  observation=observation, _input_bytes=_input_bytes, _tool_identity=_tool_identity)
    from .build_deferred import observe, validate
    validate(step)
    observation = observation if observation is not None else observe(step)
    shadow, _ = _fingerprint_state(step, done, capture=False, index=index, tool_cache=tool_cache,
                                   observation=observation, _tool_identity=_tool_identity, shadow=True)
    key = ('legacy-fingerprint-v1:' + ('state:' if capture else 'key:') + shadow)
    hit = index.remembered(key)
    if isinstance(hit, list) and len(hit) == 2:
        return hit[0], hit[1]
    value = _fingerprint_state(step, done, capture=capture, index=index, tool_cache=tool_cache,
                               observation=observation, _tool_identity=_tool_identity)
    index.remember(key, [value[0], value[1]])
    return value


def _fingerprint_state(step, done, *, capture=True, index=None, tool_cache=None, observation=None, _input_bytes=None,
                       _tool_identity=None, shadow=False):
    """Hash once, optionally retaining per-input identities for build explanations.

    _input_bytes and _tool_identity only reproduce historical evidence in bounded migration. Ordinary
    task/cache identities always read actual current inputs; replacements never certify work.
    """
    digest = hashlib.sha256()
    named = bool(step.products or step.reads or step.references)
    hasher = (index.digest if index is not None else build_products.file_digest) if named else None
    if named:
        digest.update(b'product-fingerprint-v2\0')
    # Checkout locations and generated Unreal outputs do not change a step's source. Keeping the command paths
    # relative to their roots also lets a verified build seed another checkout while each receiving input is revalidated.
    build_root_str = str(paths.build_root())
    repo_str = str(paths.REPO)
    commands = repr([c for c in step.commands])
    commands = commands.replace(build_root_str, '<build>').replace(repo_str, '<repo>')
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
                return value.replace(build_root_str, '<build>').replace(repo_str, '<repo>')
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
        build_inputs.validate_imports(step, [*inputs, *step.optional_inputs])
    for item in inputs:
        replacement = _input_bytes.get(Path(item)) if _input_bytes else None
        if named:
            # Named actions hash a Merkle inventory, not the legacy byte stream. This permits
            # file memoization and includes directory membership and every explicitly selected input.
            options = {'complete': True} if step.audit else {}
            manifest = (dict(schema=1, files={'0/.': dict(kind='file', size=len(replacement), sha256=hashlib.sha256(replacement).hexdigest())})
                        if replacement is not None else build_inputs.inventory(item, hasher=hasher, **options) if Path(item).exists() else None)
            value = build_products.identity(manifest)
            label = str(item).replace(build_root_str, '<build>').replace(repo_str, '<repo>')
            digest.update(json.dumps([label, value]).encode())
            state['inputs'][label] = value
            continue
        if capture:
            recording = RecordingDigest(digest)
            if replacement is not None:
                recording.update(Path(item).name.encode()); recording.update(replacement)
            else:
                _hash_path(recording, item, shadow=shadow)
            label = str(item).replace(build_root_str, '<build>').replace(repo_str, '<repo>')
            state['inputs'][label] = recording.local.hexdigest()
        else:
            if replacement is not None:
                digest.update(Path(item).name.encode()); digest.update(replacement)
            else:
                _hash_path(digest, item, shadow=shadow)
    if step.optional_inputs:
        state['optional_inputs'] = {}
        for item in step.optional_inputs:
            manifest = build_inputs.optional_file(item, hasher=hasher)
            label = str(item).replace(build_root_str, '<build>').replace(repo_str, '<repo>')
            value = {'present': manifest['kind'] == 'file', 'identity': build_products.identity(manifest)}
            digest.update(b'optional-file-v1\0' + json.dumps([label, value], sort_keys=True).encode())
            state['optional_inputs'][label] = value
    for need in step.needs:
        digest.update(done.get(need, 'unbuilt').encode())
    if step.products or step.reads or step.references:
        declarations = repr((step.products, step.reads, step.references))
        declarations = declarations.replace(build_root_str, '<build>').replace(repo_str, '<repo>')
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
        declarations = declarations.replace(build_root_str, '<build>').replace(repo_str, '<repo>')
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
        state['tools'] = (_tool_identity if _tool_identity is not None else
                          build_products.identity(tool_context(step, hasher, cache=tool_cache)))
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
    if stamp.get('fingerprint') == current:
        if stamp.get('checkpoint_migration_result'):
            return stamp['checkpoint_migration_result']
        if step.cutoff and stamp.get('result'):
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
    """@cc [owner:fontanierh,label:safety] completed-peak-before-small-admission
    Only a completed step's peak record MAY establish small-job eligibility. A raw guard report,
    including a pre-GO launcher or interrupted command, MUST NOT establish it by itself. A later
    guard peak MUST still raise the estimate above the completed run's peak when it is higher.
    """
    completed = report_peak(folder / 'step-peak.json')
    if completed is None:
        return None
    latest = report_peak(folder / 'memory-health.json')
    return max(completed, latest or 0) / GiB


def slot_request(ctx, step):
    """How a heavy step asks for a render slot: (kind, expected peak in GiB). A compile always takes the big slot (and
    holds the small one); a step with no completed peak has no expected peak and takes the big one. render_lock decides
    the rest (the 3 GiB bound, the switch, free memory)."""
    if any(isinstance(c, (UnrealCompile, UnrealPackage)) for c in step.commands):
        return 'compile', None
    return 'job', expected_peak_gib(ctx.logs / f'{step.name}.guard')


def run_command(ctx, step, command, log, request=None, slots=None, *, products=None, audit_receipt=None):
    """Run one command of a step. A heavy step's command runs under guarded.run, in a render slot asked for with
    `request` (slot_request's answer, computed now when absent); the slot is written to the log and added to `slots`."""
    if isinstance(command, UnrealScript):
        command.validate_step(step)
    if isinstance(command, Call):
        return command.fn(ctx, log)
    if isinstance(command, (Python, Blender)):
        source_request = request or (slot_request(ctx, step) if step.heavy else None)
        return build_source.run(ctx, step, command, log, source_request, slots,
                                products=products, audit_receipt=audit_receipt)
    if step.audit:
        from . import build_audit
        with build_audit.prepared(ctx, step, products, receipt=audit_receipt) as (argv, env, descriptors):
            return run_argv(ctx, step, command, argv, env, log, request, slots, pass_fds=descriptors)
    if isinstance(command, UnrealScript):
        with command.prepared(ctx) as (argv, env):
            return run_argv(ctx, step, command, argv, env, log, request, slots)
    return run_argv(ctx, step, command, command.argv(ctx), getattr(command, 'env', ()), log, request, slots)


def run_argv(ctx, step, command, argv, env, log, request, slots, *, pass_fds=()):
    if isinstance(command, (Python, Blender)):
        source_request = request or (slot_request(ctx, step) if step.heavy else None)
        return build_source.run_argv(ctx, step, command, argv, env, log, source_request, slots, pass_fds=pass_fds)
    script_memory = command.memory_limit() if isinstance(command, UnrealScript) else 10
    if script_memory != 10 and (not step.heavy or step.batch is not None or 'ATELIER_BATCH' in dict(env)):
        raise ValueError('An explicit script ceiling requires a separate guarded heavy command, without batching')
    selected_cook_memory = cook_memory_limit(getattr(ctx, 'cook_memory_gib', None)) if isinstance(command, UnrealPackage) else None
    if selected_cook_memory is not None and not step.heavy:
        raise ValueError('An explicit cook ceiling requires the normal heavy compile guard lifecycle')
    if isinstance(command, UnrealPackage) and command.cook_mode is not CookMode.DEFAULT and not step.heavy:
        raise ValueError('Experimental cooking requires the normal heavy compile guard lifecycle')
    preflight = isinstance(command, UnrealScript) and 'ATELIER_UNREAL_PREFLIGHT' in dict(command.env)
    if preflight and not step.heavy:
        raise ValueError('Unreal preflight requires the normal guarded heavy lifecycle')
    env = ctx.env(env)
    if isinstance(command, UnrealScript):
        env.update(ATELIER_BUILD_TASK=step.name, ATELIER_BUILD_GAME=ctx.game,
                   ATELIER_BUILD_SCRIPT=str(command.script), ATELIER_MESH_REUSE_NONCE=os.urandom(12).hex())
        env.pop('ATELIER_BUILD_PRIOR_STAMP', None)
        from .checkpoint_candidates import save_prior
        prior = save_prior(ctx, step.name, env['ATELIER_MESH_REUSE_NONCE'],
                           getattr(ctx, 'native_previous_stamps', {}).get(step.name))
        if prior is not None:
            env['ATELIER_BUILD_PRIOR_STAMP'] = str(prior)
    log.write(f'$ {" ".join(argv)}\n'); log.flush()
    if step.heavy:
        folder = ctx.logs / f'{step.name}.guard'
        kind, small_gib = request or slot_request(ctx, step)
        if script_memory != 10:
            kind, small_gib = 'job', None
        used = []

        def note(slot, why):
            used.append(slot)
            if slots is not None:
                slots.append(slot)
            why = why or ('no guard report yet' if kind == 'job' and small_gib is None else '')
            log.write(f'render slot: {slot}' + (f' ({why})' if why else '') + '\n'); log.flush()
        inherited = {'pass_fds': pass_fds} if pass_fds else {}
        if selected_cook_memory is not None:
            inherited.update(limit_gib=selected_cook_memory, compile_memory_gib=selected_cook_memory)
        if script_memory != 10:
            inherited.update(limit_gib=script_memory, script_memory_gib=script_memory, aggregate_tree=True)
        if preflight:
            inherited['aggregate_tree'] = True
        cook = None
        zen = None
        callback = getattr(command, 'on_poll', None)
        if isinstance(command, UnrealPackage):
            from .build_cook import Observer
            from .build_zen import Lifecycle
            zen = Lifecycle(folder, ctx.unreal_root, env)
            cook = Observer(folder, command.cook_mode, on_line=zen.line)
            cook.reason = getattr(ctx, 'cook_reason', None)
            original_callback = callback
            def callback(pid):
                if original_callback is not None:
                    original_callback(pid)
                cook.poll(pid)
                zen.poll(pid)
        attempt = None
        if isinstance(command, UnrealPackage) and step.cook_recovery is not None and getattr(ctx, 'record_cook_recovery', False):
            from . import build_cook_recovery
            from atelier.harness.safety.launch_ownership import prepare
            launch_context = prepare(env)
            env = dict(launch_context.environment)
            inherited['launch_context'] = launch_context
            attempt = build_cook_recovery.begin(ctx, step, command, argv, env)
            argv = attempt[1]
            inherited.update(invocation_id=attempt[0].name, completion_path=attempt[0] / 'guarded-success.json')
        try:
            code = guarded.run(argv, folder, purpose=f'atelier build {ctx.game} {step.name}', env=env,
                               small_gib=small_gib, kind=kind, on_slot=note, timeout=getattr(command, 'timeout', 0.),
                               watch=getattr(command, 'watch', ()), progress=getattr(command, 'progress', 0.),
                               **inherited, **({'on_poll': callback} if callback is not None else {}))
        except BaseException:
            if cook is not None:
                cook.finish(success=False)
            raise
        finally:
            if zen is not None:
                zen.close()
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
        from atelier.harness.safety.process import policy_command
        code, text = run_light(policy_command(argv), env,
                               {'pass_fds': pass_fds, 'stdin': subprocess.DEVNULL} if pass_fds else {})
        log.write(text)
    if code:
        if step.heavy and cook is not None:
            cook.finish(success=False)
        raise RuntimeError(f'{step.name}: command exited {code}')
    marker = getattr(command, 'marker', None)
    if marker and marker not in text:
        if step.heavy and cook is not None:
            cook.finish(success=False)
        raise RuntimeError(f'{step.name}: "{marker}" missing from the log')
    if isinstance(command, UnrealScript) and 'ATELIER_BATCH' not in dict(command.env):
        from .mesh_reuse import finalize_pending
        finalize_pending(ctx, step.name, env['ATELIER_MESH_REUSE_NONCE'])
    from .build_timings import parse_phases
    phases = parse_phases(text, allow_echo=isinstance(command, UnrealScript))
    if step.heavy and cook is not None:
        if phases is None:
            phases = dict(schema=1, status='not-recorded', phases=[], diagnostics=[])
        phases['cook'] = cook.finish(success=True)
        ctx.cook_observation = phases['cook']
        if attempt is not None:
            build_cook_recovery.complete(ctx, step, attempt, phases['cook'])
    return phases


def slot_summary(slots):
    """', small slot' for the summary line when two render slots are on (or a step used the small one)."""
    if not slots or (slot_count() != 2 and 'small' not in slots):
        return ''
    if len(set(slots)) == 1:
        return f', {slots[0]} slot'
    return f', slots {" then ".join(slots)}'


def build(game, wanted=(), force=False, dry=False, touch=False, echo=print, verify=False, cook_mode=None, cook_reason=None,
          max_heavy_commands=None, recover_cook=None, record_cook_recovery=False, rebuild_touched=False, cook_memory_gib=None,
          rebuild_reason=None):
    """@cc [owner:fontanierh,label:correctness] rebuild-touched-certificates
    An explicit touched-only rebuild MUST replace only explicitly named touched certificates through normal
    execution or verified product restoration, without changing action keys or skipping guards.
    Current proven certificates MUST remain current. Planning MUST explain the same rebuild rule.
    The repair MUST NOT combine with force, touch or cook recording/recovery.
    """
    cook_memory_limit(cook_memory_gib, wanted)
    if cook_memory_gib is not None and (touch or recover_cook is not None):
        raise ValueError('--cook-memory-gib cannot combine with touch or certification-only recovery')
    if rebuild_touched and (force or touch or recover_cook is not None or record_cook_recovery):
        raise ValueError('Rebuilding touched prerequisites is a separate build, without force/touch/cook recovery')
    if recover_cook is not None and (force or dry or touch or cook_mode is not None or max_heavy_commands is not None):
        raise ValueError('Cook recovery requires ordinary execution without force/touch/experimental/budget flags')
    if recover_cook is not None and list(wanted) not in (['unreal.cook'], ['unreal.package']):
        raise ValueError('Cook recovery selects exactly unreal.cook or unreal.package')
    if record_cook_recovery and (recover_cook is not None or list(wanted) not in (['unreal.cook'], ['unreal.package'])):
        raise ValueError('Record cook recovery selects unreal.cook or unreal.package, without --recover-cook')
    if max_heavy_commands is not None and (type(max_heavy_commands) is not int or max_heavy_commands < 1):
        raise ValueError('max_heavy_commands must be a positive integer')
    from .build_snapshot import require_complete
    if dry:
        require_complete(paths.build_root() / game, game=game)
        from .build_plan import show
        return show(game, wanted, force=force, echo=echo, verify=verify,
                    **({'rebuild_touched': True} if rebuild_touched else {}),
                    **({'cook_mode': cook_mode, 'cook_reason': cook_reason} if cook_mode is not None else {}),
                    **({'cook_memory_gib': cook_memory_gib} if cook_memory_gib is not None else {}))
    ctx = Context(game, **({'cook_mode': cook_mode, 'cook_reason': cook_reason} if cook_mode is not None else {}),
                  **({'recover_cook': recover_cook} if recover_cook is not None else {}),
                  **({'cook_memory_gib': cook_memory_gib} if cook_memory_gib is not None else {}))
    # TERM/HUP unwind the build, so running children are stopped and completed results stay published.
    from atelier.harness.safety.cancellation import termination_cleanup
    with termination_cleanup():
        return _prepared_build(ctx, wanted, force=force, touch=touch, echo=echo, verify=verify,
                               rebuild_reason=rebuild_reason, rebuild_touched=rebuild_touched,
                               record_cook_recovery=record_cook_recovery, max_heavy_commands=max_heavy_commands)


def _prepared_build(ctx, wanted, *, force, touch, echo, verify, rebuild_reason, rebuild_touched,
                    record_cook_recovery, max_heavy_commands):
    from .build_snapshot import require_complete
    game = ctx.game
    ctx.record_cook_recovery = record_cook_recovery
    ctx.rebuild_touched = rebuild_touched
    from . import build_checkpoints
    try:
        ctx.rebuild_reasons, ctx.rebuild_reason = build_checkpoints.reasons(rebuild_reason)
    except build_checkpoints.CheckpointError as error:
        raise SystemExit(str(error)) from error
    ctx.checkpoint_settings = build_checkpoints.configured(ctx)
    checkpoint_steps = None
    if ctx.checkpoint_settings is not None:
        if touch:
            raise SystemExit('--touch cannot certify checkpoint builds. Use the normal build command.')
        if force and not (ctx.rebuild_reason or ctx.rebuild_reasons):
            raise SystemExit('--force requires --rebuild-reason for checkpoint builds; normal builds restore matching results.')
        checkpoint_steps = load_recipe(game).steps(ctx)
        check_source_launch(checkpoint_steps)
        unknown = sorted(set(ctx.rebuild_reasons) - {s.name for s in checkpoint_steps})
        if unknown:
            raise SystemExit(f'--rebuild-reason names unknown tasks: {", ".join(unknown)}')
        # A bare reason covers the tasks named on the command line and those with no result at
        # launch; any other task the budget stops needs its own STEP=REASON.
        ctx.cold_at_launch = {s.name for s in checkpoint_steps if not (ctx.stamps / (s.name + '.json')).exists()} | set(wanted)
        try:  # Read and need edges carry invalidation; planning reports an invalid graph itself.
            graph = build_products.Graph(checkpoint_steps)
            ctx.rebuild_upstream = {s.name: {*s.needs, *(graph.owners[n] for n in s.reads)} for s in graph.steps}
        except (ValueError, KeyError):
            ctx.rebuild_upstream = {s.name: set(s.needs) for s in checkpoint_steps}
        ctx.rebuild_reran, ctx.rebuild_covered = set(), []
        if force and (len(wanted) != 1 or wanted[0] not in {s.name for s in checkpoint_steps}):
            raise SystemExit('--force requires one exact task and --rebuild-reason; broad forced rebuilds are retired.')
        ctx.checkpoint_force_task = wanted[0] if force else None
        if force:  # The one forced task is named on the command line, so any given reason covers it.
            forced_reason = ctx.rebuild_reasons.get(wanted[0]) or ctx.rebuild_reason
            if not forced_reason:
                raise SystemExit(f'--force needs a rebuild reason for {wanted[0]}')
            ctx.rebuild_reasons[wanted[0]] = forced_reason
        if getattr(ctx, 'cook_mode', CookMode.DEFAULT) is CookMode.FULL and not (ctx.rebuild_reason or ctx.rebuild_reasons):
            raise SystemExit('A diagnostic full cook requires --rebuild-reason; normal builds cook incrementally.')
    # Pure refusal checks precede metadata creation. Unconfigured games keep their
    # existing lifecycle and never acquire a checkpoint-only output lock.
    require_complete(paths.build_root() / game, game=game)
    from contextlib import nullcontext
    from .checkpoint_manifest import writer
    with writer(ctx.out) if ctx.checkpoint_settings is not None else nullcontext():
        if checkpoint_steps is not None:
            try:
                build_checkpoints.prepare(ctx, checkpoint_steps, echo=echo)
            except (OSError, ValueError, RuntimeError) as error:
                raise SystemExit(str(error)) from None
        from .build_hashes import HashIndex
        from .build_expansion import execute
        with HashIndex(ctx.out / '.state' / 'file-hashes.sqlite3', verify=verify) as index:
            return execute(ctx, wanted, force=force, touch=touch, echo=echo, index=index,
                           steps=checkpoint_steps, max_heavy_commands=max_heavy_commands)


def run_light(argv, env, extra):
    """@cc [owner:fontanierh,label:safety] light-command-process-group
    A light command MUST run in its own process group, and any interruption of the build,
    including TERM/HUP unwinding, MUST terminate that whole group before propagating.
    """
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True,
                               errors='ignore', start_new_session=True, **extra)
    try:
        text, _ = process.communicate()
    except BaseException:
        stop_group(process)
        raise
    return process.returncode, text


def stop_group(process):
    import signal
    for number, wait in ((signal.SIGTERM, 5.), (signal.SIGKILL, 2.)):
        try:
            os.killpg(process.pid, number)
        except (ProcessLookupError, PermissionError):
            return
        try:
            process.wait(wait)
            return
        except subprocess.TimeoutExpired:
            continue


def touched_targets(ctx, steps, wanted):
    if not getattr(ctx, 'rebuild_touched', False):
        return set()
    names = set(wanted)
    if not names or names - {step.name for step in steps}:
        raise SystemExit('--rebuild-touched requires explicit exact step names, not prefixes or the default build')
    return names


def _build(ctx, wanted, *, force, touch, echo, index, steps=None, produced=None, max_heavy_commands=None):
    from .build_cook import validate_force
    validate_force(ctx, force)
    ctx.build_hash_index = index  # Publication reuses the digests this build already computed.
    def output_tracker(steps):
        from .checkpoint_actions import verifiable
        from .output_inventory import Tracker
        return Tracker(ctx, [s for s in steps if s.outputs and not verifiable(ctx, s)])
    ctx.output_tracker = output_tracker
    checkpoint = {}
    completed = False
    try:
        code = _execute_build(ctx, wanted, force=force, touch=touch, echo=echo, index=index,
                              steps=steps, produced=produced, checkpoint=checkpoint,
                              max_heavy_commands=max_heavy_commands)
        completed = True
    finally:
        # Failure and yield paths must also discard earlier certificates with changed reads.
        invalid = _discard_changed_certificates(ctx, checkpoint, index=index)
        if completed and code != 76 and checkpoint.get('steps') is not None:
            from .checkpoint_manifest import finish
            finish(ctx, checkpoint['steps'])
    if completed and code != 76 and getattr(ctx, 'checkpoint_settings', None) is not None:
        from . import store_retention
        from .checkpoint_store import Store
        store_retention.maybe_collect(Store(ctx.game), echo=echo)
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


def _execute_build(ctx, wanted, *, force, touch, echo, index, steps, produced, checkpoint, max_heavy_commands=None):
    """@cc [owner:fontanierh,label:correctness] bounded-heavy-commands
    A bounded build MUST yield with exit 75 before preparing or admitting the next heavy
    command after its budget is spent. Calls, current actions and cache hits MUST NOT spend
    the budget; a warm batch spends one command for its whole process. Yield MUST preserve
    completed certificates and leave the next unstarted action's outputs and stamp intact,
    subject to the completed-product checkpoint.
    """
    # A trusted producer can supply the exact singleton declarations it already vetted, avoiding
    # a second recipe import that could choose a different action or introduce native prerequisites.
    from . import build_batches, build_cache
    from .build_snapshot import require_complete
    require_complete(ctx.out, game=ctx.game)
    game = ctx.game
    if steps is None:
        steps = load_recipe(game).steps(ctx)
    rebuild_names = touched_targets(ctx, steps, wanted)
    check_modules(steps)
    plan = order(steps, list(wanted))
    from .build_cook import validate_selection
    validate_selection(ctx, plan, touch=touch)
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
    if (not force or getattr(ctx, 'cook_mode', CookMode.DEFAULT) is not CookMode.DEFAULT) and not touch and any(step.cache for step in plan):
        from . import artifact_remote
        try:
            remote = artifact_remote.configured()
        except artifact_remote.RemoteError as error:
            echo(f'Remote cache unavailable ({error}); continuing locally')
    ctx.logs.mkdir(parents=True, exist_ok=True)
    ctx.stamps.mkdir(parents=True, exist_ok=True)
    from . import checkpoint_actions as task_cache
    settings = getattr(ctx, 'checkpoint_settings', None)
    actions = task_cache.Actions(ctx, settings, echo) if settings is not None else None
    if actions is not None:
        from .checkpoint_actions import validate_ownership
        validate_ownership(ctx, steps)
    done, ran, restored, saved_seconds = {}, 0, 0, 0.
    heavy_commands = 0
    def budget_spent():
        return max_heavy_commands is not None and heavy_commands + getattr(ctx, 'expansion_heavy_commands', 0) >= max_heavy_commands

    def yield_build(step):
        echo(f'BUILD YIELDED: {heavy_commands} heavy commands completed; next: {step.name}. '
             'Completed results are saved. Recheck Waiting, then resume the same build command.')
        return 75
    checkpoint.update(plan=plan, done=done, steps=steps)
    tool_cache = {}
    ctx.build_tool_cache = tool_cache
    ctx.support_migration_tools = tool_cache
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
        if actions is not None and not force and not touch:
            previous = task_cache.migrate_boundary(ctx, step, current, input_state, previous, done, echo=echo)
            from .build_support_migration import migrate as migrate_support
            previous = migrate_support(ctx, step, current, input_state, previous, done, echo=echo)
            from .build_batch_migration import migrate as migrate_batch
            previous = migrate_batch(ctx, step, current, input_state, previous, done, echo=echo)
        ctx.__dict__.setdefault('native_previous_stamps', {})[step.name] = previous
        adopted = None
        if actions is not None and not force and previous.get('fingerprint') != current:
            # A hydrated checkpoint certificate counts only for the build's own fingerprint.
            from .build_checkpoints import adopt_staged
            staged = adopt_staged(ctx, step, current, index.digest)
            if staged is not None:
                adopted, previous = 'checkpoint ' + str(staged[0])[:12], staged[1]
            elif (step.heavy or step.products) and task_cache.key(ctx, step, current) is not None and \
                    task_cache.load(actions.store, task_cache.key(ctx, step, current)) is None:
                # Without a saved action, any retained store checkpoint certifying this fingerprint serves.
                from . import store_reuse
                if not hasattr(ctx, 'store_catalogue'):
                    ctx.store_catalogue = store_reuse.Catalogue(ctx.game)
                reused = store_reuse.restore_checkpoint(ctx, step, current, ctx.store_catalogue, echo=echo)
                if reused is not None:
                    adopted, previous = 'checkpoint ' + reused[0][:12], reused[1]
        outputs_ok = outputs_present(step) and task_cache.compile_present(ctx, step)
        if actions is not None:
            outputs_ok = outputs_ok and (task_cache.certified(ctx, step, current, previous)
                                         or task_cache.local_incremental(ctx, step, current, previous))
        saved_action = None
        if actions is not None:
            identity = task_cache.key(ctx, step, current)
            saved_action = task_cache.load(actions.store, identity) if identity else None
            if saved_action is not None:
                outputs_ok = outputs_ok and task_cache.valid_outputs(ctx, step, saved_action)
        if step.products:
            outputs_ok = outputs_ok and build_products.valid_records(step, previous.get('products', {}), hasher=index.digest)
        if outputs_ok and previous.get('output_inventory') and previous.get('fingerprint') == current:
            from .output_inventory import stale
            drift = stale(ctx, step, previous)
            if drift:
                outputs_ok = False
                echo(f'{print_} outputs changed since its stamp ({drift[0]}' + (f' and {len(drift) - 1} more' if len(drift) > 1 else '') + '); rebuilding')
        try:
            verify_spatial(step, current)
        except (OSError, ValueError, SyntaxError) as error:
            stamp.unlink(missing_ok=True)
            echo(f'{print_} FAILED: {error}')
            return 1
        from .build_cook import forced
        force_step = forced(ctx, step, force) and getattr(ctx, 'expansion_completed', {}).get(step.name) != current
        recovering = getattr(ctx, 'recover_cook', None) is not None and step.name == 'unreal.cook'
        if (recovering or (step.name == 'unreal.cook' and getattr(ctx, 'record_cook_recovery', False))) and step.cook_recovery is None:
            echo(f'{print_} FAILED: this recipe does not support cook recovery')
            return 1
        rebuilding_touched = step.name in rebuild_names and previous.get('touched')
        if not recovering and not force_step and not rebuilding_touched and previous.get('fingerprint') == current and outputs_ok:
            if adopted is not None:
                stamp.write_text(json.dumps(previous) + '\n')
                from .build_checkpoints import estimate
                restored += 1
                saved_seconds += estimate(previous) or 0.
                echo(f'{print_} certificate adopted from {adopted}')
            done[step.name] = result(step, current, previous)
            build_products.feed_results(done, previous.get('products', {}))
            if actions is not None and saved_action is None and task_cache.certified(ctx, step, current, previous):
                task_cache.publish(ctx, step, current, previous, store=actions.store, done=done)
            if actions is not None:
                from .checkpoint_manifest import record as retain_record
                retain_record(ctx, step, previous, store=actions.store)
            echo(f'{print_} up to date')
            continue
        if getattr(ctx, 'recover_cook', None) is not None and not recovering and step.name != 'unreal.package':
            echo(f'{print_} FAILED: recovery requires every prerequisite already current and complete')
            return 1
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
        local_portable = step.cache and build_cache.Store().action(current).exists()
        from .build_support_migration import cached_key as previous_cache_key
        compatible_portable = (previous_cache_key(ctx, step, current, input_state, done)
                               if not force_step and not local_portable else None)
        action_hit = (actions.get(step, current, local_only=local_portable or compatible_portable is not None)
                      if actions is not None and not force_step and not recovering else None)
        try:
            # The batch selector skips current certificates; this explicitly requested repair
            # must execute or restore normally before handing later actions to a batch.
            batch = [] if rebuilding_touched or action_hit is not None or compatible_portable is not None or (actions is not None and force_step) else build_batches.select(
                ctx, plan, position, done, force=force_step, index=index, tool_cache=tool_cache)
        except (OSError, ValueError, SyntaxError) as error:
            echo(f'{print_} FAILED: {error}')
            return 1
        if batch and not force_step:
            from .build_support_migration import migrate as migrate_support
            from .build_batch_migration import migrate as migrate_batch
            # Saved or equivalently preserved results never enter a native batch.
            for offset, (candidate, candidate_key, candidate_state) in enumerate(batch):
                if candidate.cache and build_cache.Store().action(candidate_key).is_file():
                    # Presence is only a reason to defer to ordinary verified restore,
                    # never cache authority or permission to skip its checks.
                    batch = batch[:offset]
                    break
                if actions is None:
                    continue
                prior = read_stamp(ctx.stamps / (candidate.name + '.json'))
                prior = migrate_support(ctx, candidate, candidate_key, candidate_state, prior, done, echo=echo)
                prior = migrate_batch(ctx, candidate, candidate_key, candidate_state, prior, done, echo=echo)
                if prior.get('fingerprint') == candidate_key and task_cache.local_incremental(ctx, candidate, candidate_key, prior):
                    batch = batch[:offset]
                    break
                if (previous_cache_key(ctx, candidate, candidate_key, candidate_state, done) is not None
                        or actions.get(candidate, candidate_key) is not None):
                    batch = batch[:offset]
                    break
        if batch:
            if budget_spent():
                return yield_build(step)
            from .build_checkpoints import protect, estimate
            try:
                for item in batch:
                    candidate = item.step if hasattr(item, 'step') else item[0]
                    from .checkpoint_candidates import prepare as prepare_candidates
                    prepare_candidates(ctx, candidate, fingerprint=fingerprint(candidate, done, index=index, tool_cache=tool_cache), echo=echo)
                    protect(ctx, candidate, estimate=estimate(read_stamp(ctx.stamps / (candidate.name + '.json'))), echo=echo)
            except RuntimeError as error:
                echo(str(error))
                return 1
            heavy_commands += 1
            batch_tracker = ctx.output_tracker([s for s, _, _ in batch])
            completed, code = build_batches.run(ctx, batch, done, index=index, tool_cache=tool_cache,
                                                echo=echo, products=declared_products, wanted=wanted)
            finished = [(s, read_stamp(ctx.stamps / (s.name + '.json')).get('time', 0))
                        for s, _, _ in batch if s.name in completed and s.name in batch_tracker.scopes]
            if finished:
                from .build_cache import atomic_json
                for name, inventory in batch_tracker.batch(finished, index.digest).items():
                    saved = read_stamp(ctx.stamps / (name + '.json'))
                    if saved:
                        atomic_json(ctx.stamps / (name + '.json'), dict(saved, output_inventory=inventory))
            if actions is not None:
                for completed_step in plan:
                    if completed_step.name in completed:
                        saved = read_stamp(ctx.stamps / (completed_step.name + ".json"))
                        from .build_cache import atomic_json
                        path = ctx.stamps / (completed_step.name + '.json')
                        try:
                            saved['checkpoint_key'] = task_cache.certificate_key(ctx, completed_step, saved['fingerprint'])
                            saved['checkpoint_incremental_context'] = getattr(ctx, 'checkpoint_observed_context', None)
                            task_cache.publish(ctx, completed_step, saved['fingerprint'], saved, store=actions.store, done=done, produced=True)
                            atomic_json(path, saved)
                        except (OSError, ValueError, RuntimeError):
                            path.unlink(missing_ok=True)
                            raise
            if code in (0, 75):
                # The guarded process has closed positively. Failed/uncertain sessions
                # do not publish portable source-cache authority.
                for completed_step in plan:
                    if completed_step.name in completed and completed_step.cache:
                        saved = read_stamp(ctx.stamps / (completed_step.name + '.json'))
                        try:
                            build_cache.Store().publish(ctx, completed_step, saved['fingerprint'], saved['products'])
                        except (OSError, ValueError, KeyError, TypeError) as error:
                            echo(f'{completed_step.name}: cache publication skipped ({error})')
            from .checkpoint_native_capture import publish as retain_candidates
            for completed_step in plan:
                if completed_step.name in completed:
                    saved = read_stamp(ctx.stamps / (completed_step.name + '.json'))
                    retain_candidates(ctx, completed_step, saved,
                                      fresh=lambda item=completed_step: fingerprint(item, done), echo=echo)
            if actions is not None:
                from .checkpoint_manifest import record as retain_record
                for completed_step in plan:
                    if completed_step.name in completed:
                        retain_record(ctx, completed_step, read_stamp(ctx.stamps / (completed_step.name + '.json')), store=actions.store)
            completed_batches.update(completed)
            ctx.checkpoint_changed = True
            ran += len(completed)
            for completed_step in plan:
                if completed_step.name in completed:
                    from .build_checkpoints import note_rerun
                    note_rerun(ctx, completed_step)
            if code:
                return code
            for completed_step in plan:
                if completed_step.name in completed:
                    saved = read_stamp(ctx.stamps / (completed_step.name + '.json'))
                    if hasattr(ctx, 'expansion_completed'):
                        ctx.expansion_completed[completed_step.name] = saved['fingerprint']
            planners = [s for s in plan if s.name in completed and s.replan]
            if planners:
                planner = planners[-1]
                saved = read_stamp(ctx.stamps / (planner.name + '.json'))
                ctx.recipe_expansion = (planner.name, saved['fingerprint'])
                ctx.expansion_heavy_commands = getattr(ctx, 'expansion_heavy_commands', 0) + heavy_commands
                return 76
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
        if action_hit is not None:
            actions.restore(step, current, action_hit, done, index=index, tool_cache=tool_cache)
            products = build_products.records(step, hasher=index.digest)
            restore_source = "checkpoint"
        if products is None and store is not None and not force_step:
            try:
                # Source change metadata is local; all transferred output bytes are verified below.
                if fingerprint(step, done, index=index, tool_cache=tool_cache) != current:
                    raise RuntimeError('Inputs changed before cache lookup')
                products = store.restore(ctx, step, current)
                if products is not None:
                    restore_source = 'local'
                if products is None and compatible_portable is not None:
                    products = store.restore(ctx, step, compatible_portable)
                    if products is not None:
                        restore_source = 'compatible-local'
                if products is None and remote is not None and remote.fetch(current, store, echo):
                    products = store.restore(ctx, step, current)
                    if products is not None:
                        restore_source = 'https'
                if products is not None and (fingerprint(step, done, index=index, tool_cache=tool_cache) != current or not outputs_present(step)):
                    raise RuntimeError('Restored action inputs or required outputs differ')
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
                echo(f'{print_} cache unavailable ({error}); building')
                products = None
        if products is None and actions is not None and local_portable and not force_step:
            action_hit = actions.get(step, current)
            if action_hit is not None:
                actions.restore(step, current, action_hit, done, index=index, tool_cache=tool_cache)
                products = build_products.records(step, hasher=index.digest)
                restore_source = 'checkpoint'
        from_cache = products is not None
        if not from_cache and step.heavy and any(not isinstance(c, Call) for c in step.commands) and budget_spent():
            return yield_build(step)
        if not from_cache:
            from .checkpoint_candidates import prepare as prepare_candidates
            prepare_candidates(ctx, step, fingerprint=current, echo=echo)
        if not from_cache and not recovering:
            from .build_checkpoints import protect, estimate
            try:
                protect(ctx, step, estimate=estimate(previous), echo=echo)
            except RuntimeError as error:
                echo(str(error))
                return 1
        tracker = ctx.output_tracker([step]) if not from_cache else None  # Credits this step with its writes.
        if tracker is not None and step.name not in tracker.scopes:
            tracker = None
        with open(log_path, 'w') as log:
            try:
                stamp.unlink(missing_ok=True)
                # Also covers a restored hit. A changed catalogue is not a cache miss: continuing
                # would execute an obsolete plan whose newly selected producers have not run.
                verify_spatial(step, current)
                request = slot_request(ctx, step) if step.heavy else None   # from the reports of the previous run
                if recovering:
                    from .build_cook_recovery import recover
                    recovery = recover(ctx, step, ctx.recover_cook, log)
                    command_times.append(dict(kind='CookCertificationRecovery', **recovery))
                commands = (() if from_cache or recovering else step.commands)
                if action_hit is not None and step.checkpoint_restore is not None:
                    commands = [Call('certify_restored_checkpoint', step.checkpoint_restore)]
                for command in commands:
                    if step.heavy and not isinstance(command, Call):
                        if budget_spent():
                            return yield_build(step)
                        heavy_commands += 1
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
                            try:
                                from . import build_tree_observations
                                observation = build_tree_observations.read(launch_folder, launch['invocation_id'], current)
                            except Exception:
                                observation = None  # Optional history cannot fail a build.
                            if observation is not None:
                                timing['whole_tree'] = observation
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
                observed_key = (fingerprint(step, done) if actions is not None else
                                fingerprint(step, done, index=index, tool_cache=tool_cache))
                if (actions is not None or step.products or step.deferred_inputs) and observed_key != current:
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
        if tracker is not None:
            record['output_inventory'] = tracker.inventory(step, index.digest)
        if step.products or 'product_roots' in previous:
            from . import build_changes
            record['products'] = products
            record['product_roots'] = build_changes.root_labels(ctx, step)
            optional = build_changes.optional_roots(step)
            if optional:
                record['product_optional_roots'] = optional
            record['output_changes'] = build_changes.compare(previous, products, record['product_roots'],
                                                             restored=from_cache, optional=optional)
        if actions is not None:
            from .build_checkpoints import estimate
            record['checkpoint_key'] = task_cache.certificate_key(ctx, step, current)
            record['checkpoint_incremental_context'] = getattr(ctx, 'checkpoint_observed_context', None)
            record['checkpoint_build_seconds'] = estimate(action_hit['stamp']) if action_hit is not None else (None if from_cache else round(seconds, 3))
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
        if restore_source == 'compatible-local':
            record.pop('checkpoint_key', None)
            record['checkpoint_migrated_from'] = compatible_portable
            record['checkpoint_migration_result'] = record.get('result', compatible_portable)
            record['restored_from'] = compatible_portable
        if actions is not None and restore_source != 'compatible-local':
            try:
                task_cache.publish(ctx, step, current, record, store=actions.store, done=done, produced=True)
            except (OSError, ValueError, RuntimeError) as error:
                stamp.unlink(missing_ok=True)
                echo(f'{print_} FAILED: checkpoint publication refused ({error})')
                return 1
        temporary = stamp.with_suffix('.tmp')
        temporary.write_text(json.dumps(record) + '\n')
        temporary.replace(stamp)
        ctx.checkpoint_changed = True
        if hasattr(ctx, 'expansion_completed'):
            ctx.expansion_completed[step.name] = current
        journal.unlink(missing_ok=True)
        if store is not None and not from_cache:
            try:
                store.publish(ctx, step, current, products)
            except (OSError, ValueError, KeyError, TypeError) as error:
                echo(f'{print_} cache publication skipped ({error})')
        done[step.name] = result(step, current, record)
        build_products.feed_results(done, products)
        from .checkpoint_native_capture import publish as retain_candidates
        retain_candidates(ctx, step, record, fresh=lambda: fingerprint(step, done), echo=echo)
        if actions is not None:
            from .checkpoint_manifest import record as retain_record
            retain_record(ctx, step, record, store=actions.store)
        restored += int(from_cache)
        ran += int(not from_cache)
        if not from_cache:
            from .build_checkpoints import note_rerun
            note_rerun(ctx, step)
        if from_cache:
            saved_seconds += record.get('checkpoint_build_seconds') or 0.
        if produced is not None and not from_cache:
            produced.append((step.name, record))
        if from_cache:
            source = {'checkpoint': 'checkpoint action ' + action_hit['key'][:12] if action_hit else 'checkpoint action',
                      'local': 'local artifact cache', 'compatible-local': 'compatible local artifact cache',
                      'https': 'remote artifact cache'}.get(restore_source, restore_source or 'cache')
            echo(f'{print_} restored in {seconds:.1f} s from {source}{slot_summary(slots)}')
        else:
            echo(f'{print_} done in {seconds:.1f} s{slot_summary(slots)}')
        if step.replan:
            ctx.recipe_expansion = (step.name, current)
            ctx.expansion_heavy_commands = getattr(ctx, 'expansion_heavy_commands', 0) + heavy_commands
            return 76
    covered = getattr(ctx, 'rebuild_covered', [])
    if covered:
        echo(f'rebuild reason covered {len(covered)} tasks: ' + ', '.join(covered))
    echo(f'{len(plan)} steps, {ran} ran, {restored} restored, {len(plan) - ran - restored} up to date, '
         f'~{saved_seconds:.0f} s of building saved by reuse, {time.monotonic() - started:.0f} s')
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
