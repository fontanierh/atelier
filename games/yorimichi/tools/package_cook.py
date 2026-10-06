"""Certify a completed cook and retain its app as the input to download assembly."""
import hashlib
import json
import os
import shutil
import subprocess
import time


def archived_app(root):
    apps = sorted((root / 'archive').glob('*/*.app'))
    if len(apps) != 1:
        raise RuntimeError(f'expected one cooked app, found {len(apps)}')
    app = apps[0]
    data = list(app.glob('Contents/UE/*/Content/Data'))
    if not data or any(not (data[0] / rel).is_file() for rel in ('world.json', 'heightmap.bin', 'map/map.json')):
        raise RuntimeError('the cooked app lacks staged runtime data')
    if not (app / 'Contents/MacOS' / app.stem).is_file():
        raise RuntimeError('the cooked app lacks its executable')
    return app


def inventory(app, *, hashes=False, log=None):
    """File identity for quick freshness checks; content hashes for the cook and independent copy proof."""
    result, spoken = {}, time.monotonic()
    for path in sorted(app.rglob('*')):
        stat = path.lstat()
        entry = dict(mode=stat.st_mode & 0o777, mtime_ns=stat.st_mtime_ns)
        if path.is_symlink():
            entry['link'] = os.readlink(path)
        elif path.is_file():
            entry['bytes'] = stat.st_size
            if hashes:
                digest = hashlib.sha256()
                with path.open('rb') as source:
                    for chunk in iter(lambda: source.read(1 << 20), b''):
                        digest.update(chunk)
                        if log is not None and time.monotonic() - spoken >= 25:
                            line = f'cook inventory: hashing {path.relative_to(app)}, {len(result)} files complete'
                            log.write(line + '\n'); log.flush(); print(line, flush=True)
                            spoken = time.monotonic()
                entry['sha256'] = digest.hexdigest()
        else:
            continue
        result[str(path.relative_to(app))] = entry
    return result


def read_receipt(root):
    receipt = json.loads((root / 'cook.json').read_text())
    if (receipt['schema'] != 1 or not receipt['files'] or not isinstance(receipt['revision'], str)
            or len(receipt['revision']) != 40 or not isinstance(receipt['engine'], dict)
            or not isinstance(receipt['fingerprint'], str) or not isinstance(receipt['source_dirty'], bool)):
        raise ValueError('invalid cook receipt')
    app = archived_app(root)
    expected = {name: {k: v for k, v in entry.items() if k != 'sha256'} for name, entry in receipt['files'].items()}
    if receipt['app'] != str(app.relative_to(root)) or inventory(app) != expected:
        raise ValueError('cooked app changed or is incomplete')
    return receipt


def cook_present(root):
    try:
        read_receipt(root)
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError):
        return False


def source_snapshot(ctx):
    from atelier import paths
    from atelier.build import fingerprint, load_recipe
    cook = next(step for step in load_recipe(ctx.game).steps(ctx) if step.name == 'unreal.cook')
    done = {name: json.loads((ctx.stamps / (name + '.json')).read_text())['fingerprint'] for name in cook.needs}
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=paths.REPO, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=paths.REPO))
    engine = json.loads((ctx.unreal_root / 'Engine/Build/Build.version').read_text())
    return dict(revision=revision, source_dirty=dirty, fingerprint=fingerprint(cook, done), engine=engine)


def prepare(ctx, log):
    root = ctx.out / 'package'
    root.mkdir(parents=True, exist_ok=True)
    (root / 'cook.json').unlink(missing_ok=True)
    ctx.cook_source = source_snapshot(ctx)
    shutil.rmtree(root / 'archive', ignore_errors=True)
    log.write(f'cook source {ctx.cook_source["revision"]}\n'); log.flush()


def finish(ctx, log):
    if ctx.cook_source != source_snapshot(ctx):
        raise RuntimeError('source or prerequisite stamps changed during the cook; no receipt written')
    root = ctx.out / 'package'
    app = archived_app(root)
    files = inventory(app, hashes=True, log=log)
    if files != inventory(app, hashes=True, log=log):
        raise RuntimeError('cooked app changed during certification; no receipt written')
    if ctx.cook_source != source_snapshot(ctx):
        raise RuntimeError('cook inputs changed during certification; no receipt written')
    receipt = dict(schema=1, app=str(app.relative_to(root)), files=files, **ctx.cook_source)
    candidate = root / '.cook.json.tmp'
    candidate.write_text(json.dumps(receipt, indent=2) + '\n')
    candidate.replace(root / 'cook.json')
    log.write(f'cook certified: {len(files)} files\n'); log.flush()


def verify_copy(app, receipt, log):
    # ditto may recreate a symlink's timestamp. Its target, permissions and all file contents must match.
    identity = lambda entries: {name: {k: v for k, v in entry.items() if k != 'mtime_ns'} for name, entry in entries.items()}
    if identity(inventory(app, hashes=True, log=log)) != identity(receipt['files']):
        raise RuntimeError('download app differs from the certified cook')
