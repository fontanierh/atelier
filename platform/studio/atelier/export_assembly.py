"""Assemble validated independent export files; never construct or join geometry."""
from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

from .atomic_files import atomic_json
from .build_cache import copy_file
from .export_manifest import name, real_directory, sha, validate
from .model_files import regular_files, retain_files


def runtime_inputs():
    """Only executed file assembly/clone helpers, excluding unused build-controller imports."""
    return [Path(__file__), *(Path(__file__).with_name(name) for name in
            ('atomic_files.py', 'build_cache.py', 'export_manifest.py', 'model_files.py'))]


@dataclass(frozen=True)
class Item:
    key: str
    root: Path


def destination_members(destination, current):
    """Retire only names owned by the prior complete flat assembly inventory."""
    if not destination.exists():
        return
    actual = regular_files(destination)
    if any(path.is_dir() for path in destination.iterdir()):
        raise ValueError('Atomic assembly destination must be flat')
    owned = set(current)
    previous = destination / 'manifest.json'
    if previous.exists():
        try:
            manifest = json.loads(previous.read_text())
            if (not isinstance(manifest, dict) or manifest.get('schema') != 1
                    or manifest.get('complete') is not True
                    or not isinstance(manifest.get('exports'), list) or not manifest['exports']):
                raise ValueError('Invalid previous assembly inventory')
            names = set()
            for row in manifest['exports']:
                asset = name(row['asset'])
                primary = row['primary']
                if (asset.casefold() in names or not isinstance(primary, str)
                        or primary not in (asset + '.fbx', asset + '.glb')):
                    raise ValueError('Invalid previous assembly member')
                names.add(asset.casefold())
                owned.add(primary)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('Invalid previous assembly inventory') from error
    if actual - owned - {'manifest.json'}:
        raise ValueError('Foreign atomic assembly members')


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
    destination_members(destination, {receipt['primary'] for _, receipt in rows})
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
