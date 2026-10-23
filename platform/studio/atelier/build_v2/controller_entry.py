"""Narrow normal-build dispatch. Rust remains the only v2 build/cache decision maker."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from atelier import paths
from .controller_client import ensure_controller, invoke_controller
from .controller_recipe import ControllerTarget


def discover(game, *, checkout=None):
    """Load the game's pure controller declarations without a runtime build Context."""
    if checkout is None:
        try:
            directory = paths.game_dir(game)
        except FileNotFoundError:
            return {}  # No controller declaration; legacy callers retain their own discovery.
    else:
        directory = Path(checkout) / 'games' / game
    file = directory / 'build_v2.py'
    if not file.is_file():
        return {}
    spec = importlib.util.spec_from_file_location('atelier_controller_recipe_' + game, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    targets = module.targets()
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
    """@cc [owner:fontanierh,label:correctness] normal-controller-global-preflight
    Early exact-target dispatch MUST validate the complete normal recipe graph and
    cross-owner declarations before invoking a helper, without creating a legacy Context,
    checkpoints, stamps or tool identities. Its selected typed marker MUST match the pure
    game declaration. Unsupported mixed predecessors MUST NOT fall back or be skipped.
    See test_controller_exact_selection_validates_unselected_owners_before_invocation.
    """
    if not wanted:
        return None
    candidates = discover(game)
    if not candidates or any(name not in candidates for name in wanted):
        return None
    from atelier import build, build_products
    steps = build.load_recipe(game).steps(declaration_context(game))
    build.check_declarations(steps)
    selected = build_products.Graph(steps).select(wanted)
    if len(selected) != 1 or selected[0].controller is None:
        raise ValueError('controller exact dispatch requires one independent declared leaf')
    build.check_modules(selected)
    marker = selected[0].controller
    if marker.request(paths.REPO) != candidates[marker.unit].request(paths.REPO):
        raise ValueError('normal recipe and controller declarations disagree')
    return selected[0]


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


def execute(step, *, echo=print):
    """Execute the existing normal target through the sole Rust controller; never v1 fallback."""
    marker = step.controller
    if not isinstance(marker, ControllerTarget):
        raise ValueError('normal controller dispatch requires its typed marker')
    checkout = paths.REPO
    state = paths.build_root() / 'build-v2' / 'controller'
    helper = ensure_controller(checkout, state / 'helpers', echo=echo)
    result = invoke_controller(checkout, helper, marker, state / 'runs', {
        'cache_root': str(paths.cache_dir('build-v2', create=False).absolute()),
        'interpreter': str(Path(sys.executable).absolute()), 'provenance': provenance(checkout),
        # Retention namespace only, explicitly excluded from A3 item identities.
        'worktree_id': hashlib.sha256(str(checkout).encode()).hexdigest(),
        'memory_gib': 2, 'job_seconds': 120, 'cleanup_seconds': 30, 'overall_seconds': 1800,
    }, echo=echo)
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
    return 130 if result['cancelled'] else 1
