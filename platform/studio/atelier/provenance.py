"""The source a record was made from: the checked-out commit and whether the tree had changes. `root` is the
repository by default."""
import subprocess

from . import paths


def git(*args, root=None, timeout=None):
    return subprocess.check_output(['git', *args], cwd=root or paths.REPO, text=True, timeout=timeout)


def head(root=None, short=None, timeout=None):
    """The checked-out commit, abbreviated to `short` characters when given."""
    return git('rev-parse', *([f'--short={short}'] if short else []), 'HEAD', root=root, timeout=timeout).strip()


def status(root=None, untracked=True, timeout=None):
    """`git status --porcelain`, empty for a clean tree; `untracked=False` looks at tracked files only."""
    return git('status', '--porcelain', *([] if untracked else ['--untracked-files=no']), root=root, timeout=timeout)


def source_revision(root=None, untracked=True, timeout=5):
    return dict(head_sha=head(root, timeout=timeout), dirty=bool(status(root, untracked, timeout).strip()))


def require_clean_source(message='Commit the source before recording evidence from it', **kwargs):
    revision = source_revision(**kwargs)
    if revision['dirty']:
        raise RuntimeError(message)
    return revision
