"""Complete written-output inventories for steps that declare only representative outputs.

A representative output samples what its step writes. Observing the step's output directories
before and after it runs gives the files it actually wrote; their size, mtime and digest, with
the explicit outputs, make a complete record that later builds check by metadata alone.
"""
import os
from pathlib import Path
import stat

from .checkpoint_store import roots


def allowed(ctx):
    """Allowed roots by label, once per build: discovering plugin roots walks the engine tree."""
    cached = ctx.__dict__.get('_inventory_roots')
    if cached is None:
        cached = ctx.__dict__['_inventory_roots'] = {name: str(root) for name, (root, _) in roots(ctx).items()}
    return cached


def bases(ctx):
    """Allowed roots as (path text, label), deepest first, matching checkpoint labels."""
    return sorted(((root, name) for name, root in allowed(ctx).items()), key=lambda b: -len(b[0]))


def member(path, allowed):
    text = str(Path(path).absolute())
    for base, name in allowed:
        if text == base:
            return name
        if text.startswith(base + '/'):
            return name + '/' + text[len(base) + 1:]
    return None


def scope(ctx, step):
    """Directories a step's representative outputs live in; never a whole generated root."""
    tops = {base for base, _ in bases(ctx)}
    result = []
    for output in map(Path, step.outputs):
        output = output.absolute()
        target = output if output.is_dir() else output.parent
        result.append(target if str(target) not in tops else output)
    result = list(dict.fromkeys(result))
    return [p for p in result if not any(q in p.parents for q in result)]


def observe(paths):
    """Regular files under paths -> (size, mtime_ns), by metadata only."""
    seen = {}
    for top in paths:
        top = Path(top)
        try:
            info = top.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(info.st_mode):
            seen[str(top)] = (info.st_size, info.st_mtime_ns)
            continue
        if not stat.S_ISDIR(info.st_mode):
            continue
        for base, directories, leaves in os.walk(top, followlinks=False):
            for name in leaves:
                path = os.path.join(base, name)
                info = os.lstat(path)
                if stat.S_ISREG(info.st_mode):
                    seen[path] = (info.st_size, info.st_mtime_ns)
    return seen


class Tracker:
    """Rolling baseline: each step is credited only with changes since the previous step."""

    def __init__(self, ctx, steps):
        self.ctx, self.allowed = ctx, bases(ctx)
        self.scopes = {step.name: scope(ctx, step) for step in steps}
        self.baseline = observe([p for paths in self.scopes.values() for p in paths])

    def inventory(self, step, digest):
        """@cc [owner:fontanierh,label:correctness] written-output-inventory
        A representative-output step's inventory MUST list every explicit output and every file
        created or changed in its output directories while it ran, with size, mtime and digest.
        Files outside allowed generated roots MUST NOT be listed. Digests MUST come from the
        build's hash index, so recording adds no second read of a file it already hashed.
        """
        after = observe(self.scopes[step.name])
        written = {p for p, sig in after.items() if self.baseline.get(p) != sig}
        self.baseline.update(after)
        return self._record(step, written, digest)

    def batch(self, finished, digest):
        """Inventories for batch actions that ran in order; finished is [(step, certify time)].

        A changed file belongs to the earliest action, in its scope, certified at or after the
        file's mtime; later writes go to the last such action.
        """
        finished = sorted(finished, key=lambda item: item[1])
        after = observe([p for step, _ in finished for p in self.scopes[step.name]])
        credited = {step.name: set() for step, _ in finished}
        for path, sig in after.items():
            if self.baseline.get(path) == sig:
                continue
            owners = [(step, when) for step, when in finished
                      if any(path == str(top) or path.startswith(str(top) + '/') for top in self.scopes[step.name])]
            if owners:
                chosen = next((step for step, when in owners if sig[1] <= when * 1e9), owners[-1][0])
                credited[chosen.name].add(path)
        self.baseline.update(after)
        return {step.name: self._record(step, credited[step.name], digest) for step, _ in finished}

    def _record(self, step, written, digest):
        written = set(written)
        for output in step.outputs:
            if Path(output).is_file():
                written.add(str(Path(output).absolute()))
        result = {}
        for path in sorted(written):
            name = member(path, self.allowed)
            if name is None:
                continue
            info = os.lstat(path)
            result[name] = [info.st_size, info.st_mtime_ns, digest(Path(path))]
        return result


def changed(ctx, inventory):
    """Members whose current size/mtime differ from the inventory (or that vanished)."""
    labels = allowed(ctx)
    result = []
    for name, (size, mtime_ns, _) in inventory.items():
        label, _, tail = name.partition('/')
        base = labels.get(label)
        if base is None:
            result.append(name)
            continue
        try:
            info = os.lstat(base + '/' + tail if tail else base)
        except FileNotFoundError:
            result.append(name)
            continue
        if not stat.S_ISREG(info.st_mode) or (info.st_size, info.st_mtime_ns) != (size, mtime_ns):
            result.append(name)
    return result


def claims(ctx):
    """Inventory member -> newest stamp time claiming it, from this workspace's stamps."""
    import json
    owners = {}
    for path in ctx.stamps.glob('*.json') if ctx.stamps.is_dir() else ():
        try:
            stamp = json.loads(path.read_bytes())
        except (OSError, ValueError):
            continue
        for name in (stamp.get('output_inventory') or {}):
            owners.setdefault(name, []).append((stamp.get('time', 0), path.stem))
    return owners


def stale(ctx, step, stamp):
    """@cc [owner:fontanierh,label:correctness] outputs-match-their-stamp
    A step whose stamp records an output inventory MUST NOT be up to date when any listed
    file's size or mtime differs, unless a newer stamp of another step claims that file (it was
    rewritten later in the build order). The check MUST read metadata only.
    """
    inventory = stamp.get('output_inventory')
    if not inventory:
        return []
    differing = changed(ctx, inventory)
    if not differing:
        return []
    if not hasattr(ctx, 'output_claims'):
        ctx.output_claims = claims(ctx)
    when = stamp.get('time', 0)
    return [name for name in differing
            if not any(t > when and owner != step.name for t, owner in ctx.output_claims.get(name, ()))]
