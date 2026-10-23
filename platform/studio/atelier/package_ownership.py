"""File-level ownership of steps that declare no output folder (Unreal imports, scripts, calls).

Such a step owns exactly the files it wrote in that run: every file it created or changed under
the generated root and the project Content (a metadata diff), the packages Unreal saved, and its
explicit outputs and the files written beside them. That result publishes as an ordinary action
entry whose roots are those files, so restoring it writes only them; a run that wrote nothing
publishes an empty result.

Ownership claims are kept beside the action entries, shared by every checkout using the store.
A step claims the files its latest run wrote, so a recipe that moves a package to one owner
clears the old claim when the old writer runs again. A path two steps claim stays unpublished
for both; a result kept local only for that reason publishes once the contest clears. A step
whose written set differs for an identical input/tool key is non-deterministic and stays local. A run is complete only when no
unclaimed file sits beside its packages and none of its earlier files was left in place: an
import that skips an unchanged package must never publish a partial result.
"""
import os
from pathlib import Path
import stat

from .checkpoint_store import CheckpointError, identity, read_json

CLAIMS = 'package-claims.json'
RUNS_KEPT = 8


def content(ctx):
    return ctx.uproject.parent / 'Content'


def observe(ctx):
    """Owned-root files -> (size, mtime_ns), by metadata only (about 0.2 s for 40k files).

    The generated root skips controller state, logs and stamps, as checkpoint capture does.
    """
    from .native_protocol import excluded
    seen = {}
    tops = [Path(ctx.out)] + ([content(ctx)] if getattr(ctx, 'uproject', None) else [])
    for top in tops:
        for base, directories, leaves in os.walk(top, followlinks=False):
            relative = Path(base).relative_to(top)
            directories[:] = [d for d in directories if not excluded(relative / d)]
            for name in leaves:
                if excluded(relative / name):
                    continue
                path = os.path.join(base, name)
                info = os.lstat(path)
                if stat.S_ISREG(info.st_mode):
                    seen[path] = (info.st_size, info.st_mtime_ns)
    return seen


def written(ctx, step, before, log_path, inventory):
    """(labels this run owns, reasons it cannot publish, labels it deleted), after the step ran."""
    from .build import UnrealScript
    from .checkpoint_actions import label
    from .unreal_saves import foreign, saved
    after = observe(ctx)
    reasons = []
    owned = {path for path, sig in after.items() if before.get(path) != sig}
    gone = []
    for path in sorted(path for path in before if path not in after):
        try:
            gone.append(label(ctx, Path(path)))
        except CheckpointError:
            reasons.append('deleted ' + Path(path).name)
    if getattr(ctx, 'uproject', None) and any(isinstance(c, UnrealScript) for c in step.commands):
        root = content(ctx)
        for name in saved(log_path, root):
            if (root / name).is_file():
                owned.add(str(root / name))
            else:
                reasons.append('saved package is missing after the run: ' + name)
        outside = foreign(log_path, root)
        if outside:
            reasons.append('saved outside the project Content: ' + outside[0].rpartition('/')[2])
    for output in map(Path, step.outputs):
        if output.is_file():
            owned.add(str(output.absolute()))
        else:
            reasons.append('explicit output is not a file: ' + output.name)
    labels = set(inventory or ())
    for path in owned:
        try:
            labels.add(label(ctx, Path(path)))
        except CheckpointError:
            reasons.append('wrote outside generated directories: ' + Path(path).name)
    return sorted(labels), reasons, gone


def load(store):
    """{steps: step -> member labels its latest run wrote, claims: label -> steps, runs, nondeterministic}."""
    path = store.directory / CLAIMS
    try:
        value = read_json(path) if path.is_file() else {}
    except (OSError, ValueError, CheckpointError):
        value = {}
    if value.get('schema') != 2:
        value = {}
    value = dict(schema=2, steps=value.get('steps', {}), runs=value.get('runs', {}),
                 nondeterministic=value.get('nondeterministic', {}))
    claims = {}
    for owner, names in value['steps'].items():
        for name in names:
            claims.setdefault(name, []).append(owner)
    value['claims'] = {name: sorted(owners) for name, owners in claims.items()}
    return value


def recipe_claims(ctx, steps):
    """Static claims of a plan: declared output roots (prefixes) and explicit outputs (exact)."""
    cached = ctx.__dict__.get('_package_recipe_claims')
    if cached is not None:
        return cached
    from .checkpoint_actions import declared, label
    roots, exact = [], {}
    for step in steps:
        for path in declared(ctx, step):
            try:
                roots.append((label(ctx, path), step.name))
            except CheckpointError:
                pass
        for path in map(Path, step.outputs):
            try:
                exact.setdefault(label(ctx, path.absolute()), set()).add(step.name)
            except CheckpointError:
                pass
    cached = ctx.__dict__['_package_recipe_claims'] = (roots, exact)
    return cached


def seed(ctx, steps, store):
    """Record the saves in this checkout's existing logs of plan steps, once per build."""
    if ctx.__dict__.get('_package_seeded'):
        return
    ctx._package_seeded = True
    from .build import UnrealScript
    from .unreal_saves import saved
    found = {}
    for step in steps:
        log = ctx.logs / (step.name + '.log')
        if any(isinstance(c, UnrealScript) for c in step.commands) and log.is_file():
            names = saved(log, content(ctx))
            if names:
                found[step.name] = ['content/' + name for name in names]
    if found:
        # Only steps with no recorded run: a recorded latest run is authoritative for its step.
        update(store, lambda value: [value['steps'].setdefault(owner, names) for owner, names in found.items()])


def update(store, change):
    from .build_cache import atomic_json
    with store.locked():
        value = load(store)
        change(value)
        atomic_json(store.directory / CLAIMS, {k: v for k, v in value.items() if k != 'claims'})
    return load(store)


def others(ctx, steps, step, name, value):
    """Steps other than step that ever wrote, declare or explicitly output this member."""
    roots, exact = recipe_claims(ctx, steps)
    result = {owner for owner in value['claims'].get(name, ()) if owner != step.name}
    result |= {owner for owner in exact.get(name, ()) if owner != step.name}
    result |= {owner for root, owner in roots if owner != step.name and (name == root or name.startswith(root + '/'))}
    return sorted(result)


def contested(ctx, steps, step, labels, value):
    """Members of labels some other step ever wrote or owns -> those steps."""
    return {name: owners for name in labels for owners in [others(ctx, steps, step, name, value)] if owners}


def leftovers(ctx, steps, step, labels, value):
    """Files that may belong to this run but were not written by it.

    Imports save only dirty packages, so an unchanged package keeps its old bytes and leaves no
    trace in the run. Any unclaimed file beside the written ones, or any file this step wrote in
    an earlier run that is still present, makes the run's written set possibly partial.
    """
    from .checkpoint_actions import destination
    owned = set(labels)
    result = []
    folders = {name.rpartition('/')[0] for name in owned if '/' in name}
    for folder in sorted(folders):
        directory = destination(ctx, folder)
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except FileNotFoundError:
            continue
        for entry in entries:
            name = folder + '/' + entry.name
            if entry.name.startswith('.') or name in owned or not stat.S_ISREG(entry.stat(follow_symlinks=False).st_mode):
                continue
            if not others(ctx, steps, step, name, value):
                result.append(name)
    for name in value['steps'].get(step.name, ()):
        # A file another step now writes moved to that owner; it is not this run's leftover.
        if (name not in owned and name not in result and destination(ctx, name).is_file()
                and not others(ctx, steps, step, name, value)):
            result.append(name)
    return result


def decide(ctx, steps, step, certificate, labels, reasons, store, gone=()):
    """Record this run's claims; return (reasons it stays local, whether only a contest blocks it).

    Deleting a file its own latest run wrote is a step replacing its output (a renamed release
    zip); deleting any other file cannot be represented by a result that only writes files.
    """
    signature = identity(sorted(labels))
    reasons = list(reasons)
    def change(value):
        value['steps'][step.name] = sorted(labels)
        if certificate is None:
            return
        runs = value['runs'].setdefault(step.name, {})
        if runs.get(certificate, signature) != signature:
            value['nondeterministic'][step.name] = certificate
        runs.pop(certificate, None)
        runs[certificate] = signature
        for old in list(runs)[:-RUNS_KEPT]:
            runs.pop(old)
    before = load(store)
    own = set(before['steps'].get(step.name, ()))
    foreign = [name for name in gone if name not in own or others(ctx, steps, step, name, before)]
    if foreign:
        reasons.insert(0, 'deleted ' + foreign[0])
    reasons += [f'{name} present but not rewritten' for name in leftovers(ctx, steps, step, labels, before)]
    value = update(store, change)
    if step.name in value['nondeterministic']:
        reasons.insert(0, 'written set changed for identical inputs (non-deterministic)')
    retry = not reasons
    contests = contested(ctx, steps, step, labels, value)
    reasons += [f'{name} also written by {", ".join(owners)}' for name, owners in contests.items()]
    return reasons, retry and bool(contests)


def blocked(ctx, steps, step, labels, store):
    """Why an existing package-owned result must not be published or restored now."""
    value = load(store)
    if step.name in value['nondeterministic']:
        return ['written set changed for identical inputs (non-deterministic)']
    return [f'{name} also written by {", ".join(owners)}' for name, owners in contested(ctx, steps, step, labels, value).items()]


def report(store):
    """Contested members and non-deterministic steps, for listing."""
    value = load(store)
    contested = {name: owners for name, owners in value['claims'].items() if len(owners) > 1}
    return dict(contested=contested, nondeterministic=sorted(value['nondeterministic']))
