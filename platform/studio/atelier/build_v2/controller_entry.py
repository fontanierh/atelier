"""Narrow normal-build dispatch. Rust remains the only v2 build/cache decision maker."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from atelier import paths
from .controller_client import ensure_controller, invoke_controller
from .controller_recipe import ControllerTarget, ControllerSelection


def discover(game, *, checkout=None, wanted=()):
    """Load the game's pure controller declarations without a runtime build Context."""
    if checkout is None:
        try:
            directory = paths.game_dir(game)
        except FileNotFoundError:
            return {}
    else:
        directory = Path(checkout) / 'games' / game
    file = directory / 'build_v2.py'
    if not file.is_file():
        return {}
    spec = importlib.util.spec_from_file_location('atelier_controller_recipe_' + game, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    targets = module.targets()
    missing = [name for name in wanted if name not in targets]
    if missing and hasattr(module, 'compile_target'):
        for name in missing:
            targets[name] = module.compile_target(name)
    if not isinstance(targets, dict) or any(
            not isinstance(marker, ControllerTarget) or name != marker.unit for name, marker in targets.items()):
        raise ValueError('invalid game controller target declarations')
    return targets


def declaration_context(game):
    """Source-only recipe discovery; no native tool lookup or generated-directory creation."""
    try:
        project = paths.uproject(game)
    except FileNotFoundError:
        project = None
    return SimpleNamespace(game=game, game_dir=paths.game_dir(game), out=paths.build_root() / game,
                           uproject=project)


def exact_selection(game, wanted):
    """@cc [owner:fontanierh,label:correctness] direct-v2-default-selection
    Normal builds MUST select only real v2 units and invoke the existing Rust engine.
    Missing full/default selectors MUST refuse explicitly, never call an older scheduler
    or substitute a partial selection. Discovery MUST NOT construct a runtime Context.
    """
    names = tuple(wanted) if wanted else ('unreal.package',)
    candidates = discover(game, wanted=names)
    if not candidates:
        raise ValueError(f'{game}: no v2 build declaration')
    missing = [name for name in names if name not in candidates]
    if missing:
        raise ValueError(f'{game}: v2 target is not implemented: ' + ', '.join(missing))
    selection = ControllerSelection(tuple(candidates[name] for name in names), names)
    selection.request(paths.REPO)  # Strict finite control assembly; Rust still owns graph validation.
    return selection



def provenance(checkout):
    def git(*args):
        try:
            return subprocess.run(['git', '-C', str(checkout), *args], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            return SimpleNamespace(returncode=1, stdout=b'')  # Provenance is not a build prerequisite.
    commit = git('rev-parse', 'HEAD')
    branch = git('rev-parse', '--abbrev-ref', 'HEAD')
    status = git('status', '--porcelain', '--untracked-files=normal')
    return {
        'checkout': str(checkout),
        'commit': commit.stdout.decode().strip() if commit.returncode == 0 else 'unknown',
        'branch': branch.stdout.decode().strip() if branch.returncode == 0 else 'unknown',
        'dirty': status.returncode != 0 or bool(status.stdout),
        'built_at': datetime.now(timezone.utc).isoformat(),
    }


def execute(selection, *, echo=print):
    """Execute a direct selection through the existing Rust scheduler/store/executor/install."""
    if not isinstance(selection, (ControllerTarget, ControllerSelection)):
        raise ValueError('normal build requires a typed v2 selection')
    return _result_code(_invoke_marker(selection, echo=echo), echo=echo)



def _native_memory_gib(request):
    """Individual textures/shaders use the normal guard; maps and tool jobs keep 16 GiB."""
    light = {'RawTexture', 'Texture', 'Material', 'MaterialInstance', 'MaterialParameterCollection'}
    native = [unit for unit in request['declaration']['units'] if unit['op']['kind'].startswith('unreal.')]
    if native and all(unit['op']['kind'] in {'unreal.raw_import', 'unreal.finish', 'unreal.author'}
                      and unit['outputs'] and all(item['class'] in light for item in unit['outputs'])
                      for unit in native):
        return 10
    return 16


def _invoke_marker(marker, *, echo):
    checkout = paths.REPO
    state = paths.build_root() / 'build-v2' / 'controller'
    helper = ensure_controller(checkout, state / 'helpers', echo=echo)
    request = marker.request(checkout)
    kinds = {unit['op']['kind'] for unit in request['declaration']['units']}
    blender = any(kind.startswith('blender') or kind == 'recipe.blender' for kind in kinds)
    unreal = any(kind.startswith('unreal') or kind in ('cook', 'package', 'compile') for kind in kinds)
    options = {
        'cache_root': str(paths.cache_dir('build-v2', create=False).absolute()),
        'interpreter': str(Path(sys.executable).absolute()), 'provenance': provenance(checkout),
        # Retention namespace only, explicitly excluded from A3 item identities.
        'worktree_id': hashlib.sha256(str(checkout).encode()).hexdigest(),
        'memory_gib': 8,
        'blender_memory_gib': 10,
        'unreal_memory_gib': _native_memory_gib(request),
        'unreal_job_seconds': 7200,
        'job_seconds': 900,
        'cleanup_seconds': 60 if (unreal or blender) else 30,
        'overall_seconds': 28800 if (unreal or blender) else 1800,
    }
    for tool in ('ffmpeg', 'ffprobe'):
        executable = shutil.which(tool)
        if executable:
            options[tool] = str(Path(executable).absolute())
    node = shutil.which('node')
    if node:
        options['node'] = str(Path(node).absolute())
    if blender or unreal:
        from atelier import engine
        if blender:
            options['blender'] = str(Path(engine.blender()).absolute())
        if unreal:
            root = engine.unreal_root().absolute()
            modules = json.loads((root / 'Engine/Binaries/Mac/UnrealEditor.modules').read_text())
            from .native_bootstrap import ensure_native_worker
            plugin = ensure_native_worker(checkout, Path(options['cache_root']) / 'native-worker-bootstrap', root, echo=echo)
            options['unreal'] = {'engine_root': str(root), 'build_id': modules['BuildId'],
                                 'plugins': {'AtelierBuildWorker': str(plugin)}}
            if 'unreal.cook.produce' in kinds:
                options['native_export_project'] = str(plugin.parent.parent / 'AtelierWorkerHost.uproject')
    return invoke_controller(checkout, helper, marker, state / 'runs', options, echo=echo)


def _result_code(result, *, echo):
    report = result['report']
    if report is not None:
        observation = report['observation']
        if observation['summary'] is not None:
            echo(json.dumps(observation['summary'], sort_keys=True))
        if result['cancelled'] or observation['cancellation_requested']:
            return 130
        if result['state'] == 'observed' and observation['final_requirements_satisfied']:
            if 'incomplete' in (observation['source_finalization'], observation['root_finalization']):
                echo('Target requirements fulfilled; retention finalization is incomplete and claims remain protected')
            return 0
    echo('Build controller did not certify target fulfillment; retained report/logs describe the incomplete boundary')
    echo(f"Private failure diagnostic locator: {result.get('diagnostic_log', 'none retained')}")
    return 130 if result['cancelled'] else 1
