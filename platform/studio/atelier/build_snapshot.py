"""Launch barriers for artifact installation."""
from pathlib import Path
import os

from . import paths


JOURNAL = '.reuse-in-progress.json'
COMPLETE = '.reuse-complete.json'
PORTABLE_JOURNAL = '.portable-snapshot-in-progress.json'
PACKAGE_JOURNAL = '.package-install-in-progress.json'


def require_complete(out, *, game=None, repo=None, portable_resume=None, pool_resume=None, checkpoint_resume=None):
    """@cc [owner:fontanierh,label:correctness] default-snapshot-launch-barrier
    An output-root override MUST NOT hide the checkout's default installation journals: copied native
    Content and Binaries remain shared by that project. Foreign checkout checks MUST use that
    checkout's root rather than the controller's. Both default and selected roots MUST be checked.
    Only the dedicated portable restorer MAY pass portable_resume, after validating its original
    key/nonce/scope. That receipt MAY bypass only an identical durable portable journal. A package-install journal
    MUST remain an unconditional blocker, including with a valid portable-resume receipt.

    Only the pool transfer controller/worker MAY pass pool_resume, after validating its original scope. It
    MUST bypass only an identical durable pool journal; other installation barriers still apply.

    A crashed copy may contain a mixture of snapshots, even when some stamps exist.
    Only the checkpoint worker MAY resume an identical checkpoint journal. All other entry
    points MUST refuse that journal, including when an output-root override is selected.
    """
    out = Path(out)
    game = game or out.name
    default = Path(paths.REPO if repo is None else repo) / 'build' / game
    from .checkpoint_store import JOURNAL as checkpoint_journal, read_json
    for root in dict.fromkeys((default, out)):
        marker = root / checkpoint_journal
        if os.path.lexists(marker):
            if checkpoint_resume is not None and not marker.is_symlink() and read_json(marker) == checkpoint_resume:
                continue
            raise SystemExit(f'Build checkpoint restoration is incomplete. Rerun `atelier build {game}` '
                             'to resume it. Build, play and package cannot use a partial checkpoint.')
    if any(os.path.lexists(root / PACKAGE_JOURNAL) for root in (default, out)):
        raise SystemExit('Package installation or registry readiness is incomplete. Recover the exact '
                         'journaled transaction before build, play, package or direct native launch.')
    if any((root / JOURNAL).exists() for root in (default, out)):
        raise SystemExit(f'Artifact reuse was interrupted. Run `atelier cache abandon-transfer {game}` '
                         'to remove the partial generated copy, then build normally. '
                         'Build, play and package cannot use a partial snapshot.')
    from . import artifact_pool_state as pool_state
    for root in dict.fromkeys((default, out)):
        marker = root / pool_state.JOURNAL
        if os.path.lexists(marker):
            if pool_resume is not None:
                try:
                    if pool_state.read(marker) == pool_resume:
                        continue
                except (OSError, ValueError, TypeError, RecursionError):
                    pass
            raise SystemExit(f'Portable pool transfer is incomplete. Resume its original `atelier pool` command, '
                             f'or use `atelier pool abandon {game} <step>` to discard only its partial transfer. '
                             'Build, play and package cannot use an incomplete pool transfer.')
    for marker in portable_journals(out, game=game, repo=repo):
        if marker.exists() or marker.is_symlink():
            if portable_resume is not None:
                from contextlib import ExitStack
                from . import artifact_bundle as bundle
                try:
                    with ExitStack() as stack:
                        actual = bundle._read_json(stack, marker, bundle.MAX_MANIFEST)
                    if bundle._canonical(actual) == bundle._canonical(portable_resume):
                        continue
                except (OSError, ValueError, TypeError, RecursionError):
                    pass
            raise SystemExit('Portable snapshot restoration is incomplete. Resume the same '
                             '`atelier cache snapshot-restore <snapshot-key> <game>` in its original output root. '
                             'Build, play, package and direct native launch cannot use a partial snapshot.')


def portable_journals(out, *, game, repo=None):
    """Both roots share one installation scope, including when the output root is overridden."""
    default = Path(paths.REPO if repo is None else repo) / 'build' / game
    return tuple(root / PORTABLE_JOURNAL for root in dict.fromkeys((default.resolve(), Path(out).resolve())))


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
