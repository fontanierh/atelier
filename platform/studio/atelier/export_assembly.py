"""Assemble validated independent export files; never construct or join geometry."""
from dataclasses import dataclass
from pathlib import Path
import tempfile

from .atomic_files import atomic_json
from .build_cache import copy_file
from .export_tasks import name, real_directory, sha, validate
from .model_files import regular_files, retain_files


@dataclass(frozen=True)
class Item:
    key: str
    root: Path


def assemble(items, destination):
    """@cc [owner:fontanierh,label:correctness;performance] assembled-atomic-export-inventory
    Validate ALL independently owned products and the exclusive destination tree before writes.
    Assembly MUST copy complete unchanged primary bytes, never export or join geometry. Names
    MUST be case-fold unique; missing, corrupt, foreign or linked members MUST refuse. Publish
    complete membership before retiring superseded destination files, and preserve unchanged
    primary bytes and mtimes. Assembly MUST NOT manufacture child success stamps.
    """
    items = tuple(items)
    if not items or len({name(item.key).casefold() for item in items}) != len(items):
        raise ValueError('Assembly requires a nonempty unique logical export inventory')
    rows = [(item, validate(item.root, key=item.key)) for item in items]
    destination = real_directory(destination)
    if destination.exists():
        regular_files(destination)
    # No destination write precedes the complete source and destination preflight.
    destination.mkdir(parents=True, exist_ok=True)
    manifest = dict(schema=1, complete=True, exports=[])
    for item, receipt in rows:
        primary = receipt['primary']
        source, target = item.root / primary, destination / primary
        if not target.is_file() or sha(target) != receipt['sha256']:
            with tempfile.NamedTemporaryFile(prefix='.assemble-', dir=destination, delete=False) as temporary:
                staging = Path(temporary.name)
            try:
                staging.unlink()
                copy_file(source, staging)
                if sha(staging) != receipt['sha256'] or sha(source) != receipt['sha256']:
                    raise ValueError('Atomic source changed during assembly')
                staging.replace(target)
            finally:
                staging.unlink(missing_ok=True)
        manifest['exports'].append(receipt)
    # Recheck even unchanged sources: a concurrent change must not publish a stale manifest.
    for item, receipt in rows:
        if validate(item.root, key=item.key) != receipt:
            raise ValueError('Atomic export changed before assembly publication')
    atomic_json(destination / 'manifest.json', manifest)
    retain_files(destination, ['manifest.json', *(r['primary'] for _, r in rows)])
    return manifest
