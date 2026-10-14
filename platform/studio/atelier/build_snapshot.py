"""Launch barrier for whole-worktree artifact installation."""
from pathlib import Path
import os


JOURNAL = '.reuse-in-progress.json'
COMPLETE = '.reuse-complete.json'


def require_complete(out):
    """A crashed copy may contain a mixture of snapshots, even when some stamps exist."""
    if (Path(out) / JOURNAL).exists():
        raise SystemExit(f'Artifact reuse was interrupted. Run `atelier reuse {Path(out).name} --abandon` '
                         'to remove the partial generated copy, then reuse again or build. '
                         'Build, play and package cannot use a partial snapshot.')


def require_launch(command, *, cwd=None, env=None):
    """Catch direct native launchers too, including UAT's -project= argument."""
    env = os.environ if env is None else env
    for argument in command:
        value = str(argument).partition('=')[2] if str(argument).lower().startswith('-project=') else str(argument)
        if not value.lower().endswith('.uproject'):
            continue
        project = Path(value)
        if not project.is_absolute():
            project = Path(cwd or os.getcwd()) / project
        for directory in project.resolve().parents:
            if directory.parent.name == 'games':
                root = Path(env.get('ATELIER_BUILD_ROOT') or directory.parent.parent / 'build')
                require_complete(root / directory.name)
                break
