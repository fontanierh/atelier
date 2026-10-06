"""The build engine: named steps with inputs and dependencies, rerun only when something they read changed.

A game describes its build in `games/<game>/build.py`, a module with `steps()` returning a list of `Step`s. A step's
fingerprint is the hash of its inputs (files or folders, by content), its commands, and the fingerprints of the steps
it needs; `build/<game>/stamps/<step>.json` remembers the last good one. Logs go to `build/<game>/logs/<step>.log`.

Commands are plain data (`Python`, `Blender`, `UnrealScript`, `UnrealCompile`, `Call`), so the fingerprint changes
when a command does.

A `heavy` step's commands run under `atelier.safety.guarded`: a render slot and the memory guard, whose report is
`logs/<step>.guard/memory-health.json`. When two render slots are on (`atelier.safety.render_lock`), a step whose last
guard reports peaked at 3 GiB or less asks for the small slot; a compile, or a step with no report yet, takes the big
one. The step's log names the slot each command used, and the summary line names it too when two slots are on.
"""
import hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .safety import guarded
from .safety.render_lock import GiB, slot_count

SKIP_PARTS = {'__pycache__', '.DS_Store', 'Binaries', 'Intermediate', 'Saved', 'DerivedDataCache'}
SKIP_SUFFIXES = {'.md'}   # documentation next to sources never changes what a step makes


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

    def argv(self, ctx):
        extra = ['--', *map(str, self.args)] if self.args else []
        return [ctx.blender, '-b', '--threads', str(self.threads), '--python-exit-code', '1',
                '--python', str(self.script), *extra]


@dataclass
class UnrealScript:
    """An editor Python script run by UnrealEditor-Cmd on the game's project; `marker` must appear in the log."""
    script: Path
    marker: str
    null_rhi: bool = False
    env: tuple = ()          # (("NAME", "value"), ...)
    args: tuple = ()         # additional editor arguments for this import

    def argv(self, ctx):
        command = [str(ctx.unreal_cmd), str(ctx.uproject), '-run=pythonscript', f'-script={self.script}',
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
    """Build, cook, stage and archive the packaged game with UAT BuildCookRun. The editor must already be compiled.
    Everything under Content is cooked, because the game loads many assets by path at run time."""
    target: str
    archive: Path
    config: str = 'Development'
    workers: int = 3                    # UAT calls UnrealBuildTool directly, past the capped Build.sh wrapper
    marker: str = 'BUILD SUCCESSFUL'
    timeout: float = 4 * 3600           # the whole package: compile, cook, stage and archive
    # The heavy work happens in UAT's descendants: each gets its own memory guard in the same slot turn.
    watch: tuple = ('UnrealEditor-Cmd', 'UnrealEditor', 'ShaderCompileWorker', 'dotnet')
    progress: float = 60.

    def argv(self, ctx):
        return [str(ctx.unreal_root / 'Engine/Build/BatchFiles/RunUAT.sh'), 'BuildCookRun', f'-project={ctx.uproject}',
                f'-target={self.target}', '-platform=Mac', f'-clientconfig={self.config}', '-build',
                f'-ubtargs=-MaxParallelActions={self.workers}', '-cook', '-cookall', '-stage', '-pak', '-archive',
                f'-archivedirectory={self.archive}', '-nocompileeditor', '-noP4', '-unattended', '-utf8output']


@dataclass
class Call:
    """A Python function `fn(ctx, log)` in the game's build module; `name` makes it part of the fingerprint."""
    name: str
    fn: object = field(compare=False, repr=False)


@dataclass
class Step:
    name: str
    commands: list
    inputs: list = field(default_factory=list)     # files or folders, hashed by content
    needs: list = field(default_factory=list)      # step names whose results this step uses (their fingerprints feed its own)
    after: list = field(default_factory=list)      # step names that only have to run first (a compiled editor): no rerun when they change
    outputs: list = field(default_factory=list)    # must exist after a run; a missing one forces a rerun
    heavy: bool = False                            # take a render slot and the memory guard (Unreal, Blender renders)
    about: str = ''
    pool_roots: list = field(default_factory=list)  # exclusively owned generated folders, opt-in portable pool


# ---------------------------------------------------------------- context
class Context:
    def __init__(self, game):
        self.game = game
        self.game_dir = paths.game_dir(game)
        self.out = paths.build_dir(game)
        self.logs = self.out / 'logs'
        self.stamps = self.out / 'stamps'
        self.unreal_root = Path(os.environ.get('UE_ROOT') or '/Users/Shared/Epic Games/UE_5.8')
        self.unreal_cmd = self.unreal_root / 'Engine/Binaries/Mac/UnrealEditor-Cmd'
        self.unreal_app = self.unreal_root / 'Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor'
        # Resolved: Blender finds its bundled Python and data next to its real executable, not next to a PATH symlink.
        self.blender = os.path.realpath(os.environ.get('BLENDER') or shutil.which('blender') or '/Applications/Blender.app/Contents/MacOS/Blender')
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
def _hash_path(digest, path):
    path = Path(path)
    if path.is_file():
        digest.update(str(path.name).encode())
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b''):
                digest.update(chunk)
    elif path.is_dir():
        for child in sorted(path.rglob('*')):
            if child.is_file() and not SKIP_PARTS & set(child.parts) and child.suffix not in SKIP_SUFFIXES:
                digest.update(str(child.relative_to(path)).encode())
                _hash_path(digest, child)
    else:
        digest.update(b'missing:' + str(path).encode())


def fingerprint(step, done):
    digest = hashlib.sha256()
    # Checkout locations and generated Unreal outputs do not change a step's source. Keeping the command paths
    # relative to their roots also lets a verified build seed another checkout of the same source revision.
    commands = repr([c for c in step.commands])
    commands = commands.replace(str(paths.build_root()), '<build>').replace(str(paths.REPO), '<repo>')
    digest.update(commands.encode())
    for item in step.inputs:
        _hash_path(digest, item)
    for need in step.needs:
        digest.update(done.get(need, 'unbuilt').encode())
    return digest.hexdigest()


# ---------------------------------------------------------------- running
def order(steps, wanted):
    """Wanted steps plus everything they need, in declaration order."""
    by_name = {s.name: s for s in steps}
    unknown = [w for w in wanted if w not in by_name and not any(s.name.startswith(w + '.') for s in steps)]
    if unknown:
        raise SystemExit(f'unknown steps: {unknown}; `atelier build <game> --list` shows them')
    chosen = set()

    def add(name):
        if name in chosen:
            return
        chosen.add(name)
        for need in by_name[name].needs + by_name[name].after:
            add(need)
    for w in wanted or [s.name for s in steps]:
        for s in steps:
            if s.name == w or s.name.startswith(w + '.'):
                add(s.name)
    return [s for s in steps if s.name in chosen]


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


def run_command(ctx, step, command, log, request=None, slots=None):
    """Run one command of a step. A heavy step's command runs under guarded.run, in a render slot asked for with
    `request` (slot_request's answer, computed now when absent); the slot is written to the log and added to `slots`."""
    if isinstance(command, Call):
        return command.fn(ctx, log)
    env = ctx.env(getattr(command, 'env', ()))
    argv = command.argv(ctx)
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
        code = guarded.run(argv, folder, purpose=f'atelier build {ctx.game} {step.name}', env=env,
                           small_gib=small_gib, kind=kind, on_slot=note, timeout=getattr(command, 'timeout', 0.),
                           watch=getattr(command, 'watch', ()), progress=getattr(command, 'progress', 0.))
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
                                text=True, errors='ignore')
        code, text = result.returncode, result.stdout
        log.write(text)
    if code:
        raise RuntimeError(f'{step.name}: command exited {code}')
    marker = getattr(command, 'marker', None)
    if marker and marker not in text:
        raise RuntimeError(f'{step.name}: "{marker}" missing from the log')


def slot_summary(slots):
    """', small slot' for the summary line when two render slots are on (or a step used the small one)."""
    if not slots or (slot_count() != 2 and 'small' not in slots):
        return ''
    if len(set(slots)) == 1:
        return f', {slots[0]} slot'
    return f', slots {" then ".join(slots)}'


def build(game, wanted=(), force=False, dry=False, touch=False, echo=print):
    ctx = Context(game)
    recipe = load_recipe(game)
    steps = recipe.steps(ctx)
    plan = order(steps, list(wanted))
    ctx.logs.mkdir(parents=True, exist_ok=True)
    ctx.stamps.mkdir(parents=True, exist_ok=True)
    done, ran = {}, 0
    for s in steps:   # fingerprints of steps not in the plan still feed their dependents
        stamp = ctx.stamps / f'{s.name}.json'
        if stamp.exists() and s not in plan:
            done[s.name] = json.loads(stamp.read_text())['fingerprint']
    started = time.monotonic()
    for step in plan:
        print_ = f'{step.name:34s}'
        stamp = ctx.stamps / f'{step.name}.json'
        current = fingerprint(step, done)
        previous = json.loads(stamp.read_text()) if stamp.exists() else {}
        outputs_ok = all(Path(o).exists() for o in step.outputs)
        if not force and previous.get('fingerprint') == current and outputs_ok:
            done[step.name] = current
            echo(f'{print_} up to date')
            continue
        if dry:
            done[step.name] = current
            echo(f'{print_} would run')
            continue
        if touch:   # the outputs are known to be current (a refactor of the recipe): record them without running
            if not outputs_ok:
                echo(f'{print_} not touched: outputs missing')
                continue
            stamp.write_text(json.dumps({'fingerprint': current, 'seconds': previous.get('seconds'), 'time': time.time(), 'touched': True}) + '\n')
            done[step.name] = current
            echo(f'{print_} touched')
            continue
        pool_key = None
        if step.pool_roots:
            from . import artifact_pool
            pool_key = artifact_pool.key(ctx, step, current)
        t0 = time.monotonic()
        log_path = ctx.logs / f'{step.name}.log'
        slots, peaks = [], []
        with open(log_path, 'w') as log:
            try:
                request = slot_request(ctx, step) if step.heavy else None   # from the reports of the previous run
                for command in step.commands:
                    run_command(ctx, step, command, log, request, slots)
                    if step.heavy and not isinstance(command, Call):
                        peaks.append(report_peak(ctx.logs / f'{step.name}.guard' / 'memory-health.json'))
                missing = [str(o) for o in step.outputs if not Path(o).exists()]
                if missing:
                    raise RuntimeError(f'{step.name}: outputs missing after the run: {missing[:3]}')
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
        result = {'fingerprint': current, 'seconds': round(seconds, 1), 'time': time.time()}
        if pool_key is not None:
            if fingerprint(step, done) != current or artifact_pool.key(ctx, step, current) != pool_key:
                stamp.unlink(missing_ok=True)
                raise RuntimeError('Pool tool context changed during build; outputs not certified')
            result['pool_key'] = pool_key
        stamp.write_text(json.dumps(result) + '\n')
        done[step.name] = current
        ran += 1
        echo(f'{print_} done in {seconds:.1f} s{slot_summary(slots)}')
    echo(f'{len(plan)} steps, {ran} ran, {time.monotonic() - started:.0f} s')
    return 0


def list_steps(game, echo=print):
    ctx = Context(game)
    for s in load_recipe(game).steps(ctx):
        needs = f'  (needs {", ".join(s.needs)})' if s.needs else ''
        needs += f'  (after {", ".join(s.after)})' if s.after else ''
        echo(f'{s.name:34s} {s.about}{needs}')
