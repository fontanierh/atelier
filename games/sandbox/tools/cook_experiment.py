"""Sandbox-only receipt for explicit full/incremental cook experiments; no native parity claim."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time


def source_snapshot(ctx):
    from atelier.build import fingerprint, load_recipe
    from atelier.provenance import head, status
    step = next(step for step in load_recipe(ctx.game).steps(ctx) if step.name == 'unreal.cook')
    done = {name: json.loads((ctx.stamps / (name + '.json')).read_text())['fingerprint'] for name in step.needs}
    return dict(revision=head(), dirty=bool(status(untracked=False)), fingerprint=fingerprint(step, done),
                engine=json.loads((ctx.unreal_root / 'Engine/Build/Build.version').read_text()),
                mode=ctx.cook_mode.value)


def app(root):
    apps = sorted((root / 'archive').glob('*/*.app'))
    if len(apps) != 1:
        raise RuntimeError('Sandbox cook must archive exactly one app')
    result = apps[0]
    if not (result / 'Contents/MacOS' / result.stem).is_file():
        raise RuntimeError('Sandbox archive lacks its executable')
    if not any(result.rglob('*.utoc')) or not any(result.rglob('*.ucas')):
        raise RuntimeError('Sandbox modern experiment requires actual IoStore containers')
    return result


def inventory(root, log=None):
    entries, spoken = {}, time.monotonic()
    for path in sorted(root.rglob('*')):
        if len(entries) >= 100000:
            raise RuntimeError('Sandbox app inventory exceeds experiment bound')
        info = path.lstat()
        if path.is_symlink():
            record = dict(mode=info.st_mode & 0o777, link=os.readlink(path))
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for data in iter(lambda: source.read(1024**2), b''):
                    digest.update(data)
                    if log is not None and time.monotonic() - spoken >= 25:
                        line = f'sandbox cook certification: {len(entries)} files observed'
                        log.write(line + '\n'); log.flush(); print(line, flush=True)
                        spoken = time.monotonic()
            if path.stat().st_size != info.st_size:
                raise RuntimeError('Sandbox archive changed during certification')
            record = dict(mode=info.st_mode & 0o777, size=info.st_size, sha256=digest.hexdigest())
        elif path.is_dir():
            continue
        else:
            raise RuntimeError('Unsupported sandbox archive leaf')
        entries[path.relative_to(root).as_posix()] = record
    return entries


def prepare(ctx, log):
    from atelier.build_cook import CookMode
    if ctx.cook_mode is CookMode.DEFAULT:
        raise RuntimeError('Sandbox cook experiment requires --cook-mode modern-full or modern-incremental')
    root = ctx.out / 'package'
    root.mkdir(parents=True, exist_ok=True)
    (root / 'cook.json').unlink(missing_ok=True)
    ctx.cook_observation = None
    ctx.cook_source = source_snapshot(ctx)
    if (root / 'archive').exists():
        shutil.rmtree(root / 'archive')
    log.write(f'sandbox cook experiment: {ctx.cook_mode.value}; Saved/Zen state retained\n'); log.flush()


def finish(ctx, log):
    """@cc [owner:fontanierh,label:correctness] sandbox-modern-cook-receipt
    A receipt MUST require this invocation's completed modern observation, unchanged source and
    complete archived file inventory. It MUST NOT claim native load/cook parity or speedup.
    """
    root = ctx.out / 'package'
    report = json.loads((ctx.logs / 'unreal.cook.guard/cook-observation.json').read_text())
    if (report != getattr(ctx, 'cook_observation', None) or report.get('validated') is not True or report.get('requested') != ctx.cook_mode.value
            or report.get('modern_dependencies') is not True or report.get('cook_completed') is not True):
        raise RuntimeError('Sandbox cook lacks a completed modern observation')
    if source_snapshot(ctx) != ctx.cook_source:
        raise RuntimeError('Sandbox cook source changed; no receipt')
    cooked = app(root)
    files = inventory(cooked, log)
    if files != inventory(cooked, log) or source_snapshot(ctx) != ctx.cook_source:
        raise RuntimeError('Sandbox source/archive changed during certification; no receipt')
    receipt = dict(schema=1, experimental=True, native_parity=False, source=ctx.cook_source,
                   app=cooked.relative_to(root).as_posix(), files=files, cook=report)
    candidate = root / '.cook.json.tmp'
    candidate.write_text(json.dumps(receipt, indent=2) + '\n')
    # Retain each small result separately; the next archive is independently generated, never
    # seeded from these results. Native load/registry/container comparison remains a separate gate.
    results = ctx.out / 'cook-experiments'
    results.mkdir(exist_ok=True)
    retained = results / f'{time.time_ns()}-{ctx.cook_mode.value}.json'
    retained.write_text(json.dumps(receipt, indent=2) + '\n')
    candidate.replace(root / 'cook.json')
    log.write(f'sandbox cook certified experiment inventory: {len(files)} leaves; native parity unproven\n'); log.flush()


def present(root):
    try:
        receipt = json.loads((root / 'cook.json').read_text())
        return (receipt['schema'] == 1 and receipt['experimental'] is True and receipt['native_parity'] is False
                and receipt['cook']['validated'] is True and receipt['files'] == inventory(app(root)))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return False
