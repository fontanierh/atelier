"""Launch barrier for whole-worktree artifact installation."""
from pathlib import Path
import os

from . import paths


JOURNAL = '.reuse-in-progress.json'
COMPLETE = '.reuse-complete.json'


def require_complete(out, *, game=None, repo=None):
    """@cc [owner:fontanierh,label:correctness] default-snapshot-launch-barrier
    An output-root override MUST NOT hide the checkout's default reuse journal: copied native
    Content and Binaries remain shared by that project. Foreign checkout checks MUST use that
    checkout's root rather than the controller's. Both default and selected roots MUST be checked.

    A crashed copy may contain a mixture of snapshots, even when some stamps exist.
    """
    out = Path(out)
    game = game or out.name
    default = Path(paths.REPO if repo is None else repo) / 'build' / game
    if any((root / JOURNAL).exists() for root in (default, out)):
        raise SystemExit(f'Artifact reuse was interrupted. Run `atelier reuse {game} --abandon` '
                         'to remove the partial generated copy, then reuse again or build. '
                         'Build, play and package cannot use a partial snapshot.')


def require_launch(command, *, cwd=None, env=None):
    """Catch direct native launchers too, including UAT's -project= argument."""
    env = os.environ if env is None else env
    child_cwd = Path(cwd or os.getcwd()).resolve()
    for argument in command:
        value = str(argument).partition('=')[2] if str(argument).lower().startswith('-project=') else str(argument)
        if not value.lower().endswith('.uproject'):
            continue
        project = Path(value)
        if not project.is_absolute():
            project = child_cwd / project
        for directory in project.resolve().parents:
            if directory.parent.name == 'games':
                root = Path(env.get('ATELIER_BUILD_ROOT') or directory.parent.parent / 'build')
                if not root.is_absolute():
                    root = child_cwd / root
                require_complete(root / directory.name, game=directory.name, repo=directory.parent.parent)
                break
