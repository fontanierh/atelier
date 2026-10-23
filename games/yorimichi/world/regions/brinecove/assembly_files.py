"""Flat coastal staging ownership: validate all destinations before changing any bytes."""
from pathlib import Path

from atelier.file_copy import copy_file
from atelier.export_manifest import real_directory, sha
from atelier.model_files import member, regular_files


def preflight(root, sources, previous):
    root = real_directory(root)
    for filename, source in sources.items():
        if member(filename) != Path(filename).name: raise ValueError('Nonflat coastal staged member')
        real_directory(source.parent)
        if source.is_symlink() or not source.is_file(): raise ValueError('Missing coastal source member')
    for filename in previous:
        if member(filename) != Path(filename).name: raise ValueError('Nonflat previous coastal member')
    if root.exists():
        actual = regular_files(root)
        if actual - set(sources) - set(previous) or any(p.is_dir() for p in root.iterdir()):
            raise ValueError('Foreign coastal assembly members')
    return root


def stage(root, sources, identities):
    root.mkdir(parents=True, exist_ok=True)
    for filename, source in sources.items():
        digest = identities[filename]
        if sha(source) != digest: raise ValueError('Coastal source changed before staging')
        target = root / filename
        if not target.exists() or sha(target) != digest:
            temporary = root / ('.stage-' + filename)
            if temporary.exists() or temporary.is_symlink(): raise ValueError('Unresolved coastal staging file')
            try:
                copy_file(source, temporary)
                if sha(temporary) != digest or sha(source) != digest:
                    raise ValueError('Coastal source changed while staging')
                temporary.replace(target)
            finally: temporary.unlink(missing_ok=True)


def retire(root, expected):
    """Only after complete publication, remove preflighted former owned flat files."""
    for path in root.iterdir():
        if path.name not in expected: path.unlink()
