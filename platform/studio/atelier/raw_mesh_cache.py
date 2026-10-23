"""Save the raw mesh items a successful import captured into the shared cache, as APFS clones.

The editor side (unreal_mesh_reuse.RawMeshes) captures each fresh import's saved package before
finishing; finalize_pending marks the capture ready only after the owning task's native success.
This host step then stores every file under its digest and writes the item under its exact key.
"""
from pathlib import Path
import shutil
import stat

from .build_hashes import signature
from .checkpoint_store import CheckpointError, Store, atomic_json, read_json

SCHEMA = 1


def entry_path(store, key):
    return store.directory / 'raw-meshes' / key[:2] / (key + '.json')


def publish(ctx, task, *, store=None, echo=print):
    """Store every ready capture of this task. Returns the number of new items."""
    root = Path(ctx.out) / '.state/raw-mesh-ready' / task
    if not root.is_dir():
        return 0
    store = store or Store(ctx.game)
    added = 0
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            manifest = read_json(folder / 'manifest.json')
            if manifest.get('schema') != SCHEMA or manifest.get('task') != task:
                raise CheckpointError('Raw mesh capture belongs to another task')
            for key, item in sorted(manifest['items'].items()):
                target = entry_path(store, key)
                if target.exists():
                    continue  # The first saved result for this exact key stays the cached item.
                files = {}
                for member, entry in sorted(item['files'].items()):
                    path = folder / 'files' / key / member
                    info = path.lstat()
                    if not stat.S_ISREG(info.st_mode) or info.st_size != entry['size']:
                        raise CheckpointError('Raw mesh capture changed before publication')
                    store.put(path, entry['sha256'], proved=signature(info))
                    files[member] = dict(sha256=entry['sha256'], size=entry['size'], mode=entry['mode'])
                target.parent.mkdir(parents=True, exist_ok=True)
                atomic_json(target, dict(schema=SCHEMA, key=key, task=task, package=item['package'], files=files))
                added += 1
        except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
            echo(f'{task}: raw mesh items not cached ({error})')
        shutil.rmtree(folder, ignore_errors=True)
    if added:
        echo(f'{task}: cached {added} raw mesh items')
    return added
