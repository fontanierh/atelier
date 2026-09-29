"""The build engine: named steps with inputs and dependencies, rerun only when something they read changed.

A game describes its build in `games/<game>/build.py`, a module with `steps()` returning a list of `Step`s. A step's
fingerprint is the hash of its inputs (files or folders, by content), its commands, and the fingerprints of the steps
it needs; `build/<game>/stamps/<step>.json` remembers the last good one. Logs go to `build/<game>/logs/<step>.log`.

Commands are plain data (`Python`, `Blender`, `UnrealScript`, `UnrealCompile`, `Call`), so the fingerprint changes
when a command does.
"""
import hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .safety import guarded

SKIP_PARTS = {'__pycache__', '.DS_Store'}


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

    def argv(self, ctx):
        command = [str(ctx.unreal_cmd), str(ctx.uproject), '-run=pythonscript', f'-script={self.script}',
                   '-unattended', '-nop4', '-nosplash', '-stdout']
        return command + (['-NullRHI'] if self.null_rhi else [])


@dataclass
class UnrealCompile:
    """Compile the game's editor target (C++ module and any project plugins)."""
    target: str

    def argv(self, ctx):
        return [str(ctx.unreal_root / 'Engine/Build/BatchFiles/Mac/Build.sh'), self.target, 'Mac', 'Development',
                f'-project={ctx.uproject}', '-WaitMutex']


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
    needs: list = field(default_factory=list)      # step names
    outputs: list = field(default_factory=list)    # must exist after a run; a missing one forces a rerun
    heavy: bool = False                            # take the machine's render lock (Unreal, Blender renders)
    about: str = ''


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
        self.blender = os.environ.get('BLENDER') or shutil.which('blender') or '/Applications/Blender.app/Contents/MacOS/Blender'
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
            if child.is_file() and not SKIP_PARTS & set(child.parts):
                digest.update(str(child.relative_to(path)).encode())
                _hash_path(digest, child)
    else:
        digest.update(b'missing:' + str(path).encode())


def fingerprint(step, done):
    digest = hashlib.sha256()
    digest.update(repr([c for c in step.commands]).encode())
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
        for need in by_name[name].needs:
            add(need)
    for w in wanted or [s.name for s in steps]:
        for s in steps:
            if s.name == w or s.name.startswith(w + '.'):
                add(s.name)
    return [s for s in steps if s.name in chosen]


def run_command(ctx, step, command, log):
    if isinstance(command, Call):
        return command.fn(ctx, log)
    env = ctx.env(getattr(command, 'env', ()))
    argv = command.argv(ctx)
    log.write(f'$ {" ".join(argv)}\n'); log.flush()
    if step.heavy:
        folder = ctx.logs / f'{step.name}.guard'
        code = guarded.run(argv, folder, purpose=f'atelier build {ctx.game} {step.name}', env=env)
        text = (folder / 'stdout.log').read_text(errors='ignore')
        log.write(text)
    else:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True, errors='ignore')
        code, text = result.returncode, result.stdout
        log.write(text)
    if code:
        raise RuntimeError(f'{step.name}: command exited {code}')
    marker = getattr(command, 'marker', None)
    if marker and marker not in text:
        raise RuntimeError(f'{step.name}: "{marker}" missing from the log')


def build(game, wanted=(), force=False, dry=False, echo=print):
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
        t0 = time.monotonic()
        log_path = ctx.logs / f'{step.name}.log'
        with open(log_path, 'w') as log:
            try:
                for command in step.commands:
                    run_command(ctx, step, command, log)
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
        stamp.write_text(json.dumps({'fingerprint': current, 'seconds': round(seconds, 1), 'time': time.time()}) + '\n')
        done[step.name] = current
        ran += 1
        echo(f'{print_} done in {seconds:.1f} s')
    echo(f'{len(plan)} steps, {ran} ran, {time.monotonic() - started:.0f} s')
    return 0


def list_steps(game, echo=print):
    ctx = Context(game)
    for s in load_recipe(game).steps(ctx):
        needs = f'  (needs {", ".join(s.needs)})' if s.needs else ''
        echo(f'{s.name:34s} {s.about}{needs}')
