"""Source and package evidence for incremental native mesh imports.

These receipts describe geometry reuse inside a normal importer. They are not
task/action certificates, and never replace the importer's current validation.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .native_protocol import (atomic_json, CheckpointError, canonical, read_json, relative, safe_destination,
                              ReadStore, entry_path, validate_action, context)


def digest(path, algorithm='sha256'):
    value = hashlib.new(algorithm)
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def policy(source, functions, resolve_import=None):
    """Hash geometry functions and their local function/global-binding closure.

    Comments, formatting, and unrelated finishing/validation code do not change
    a geometry policy. Missing or ambiguous declarations cannot establish it.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            raise ValueError('Class initialization cannot establish a geometry policy')
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            annotations = ([node.returns] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns else [])
            annotations += [arg.annotation for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                                                        *([node.args.vararg] if node.args.vararg else []),
                                                        *([node.args.kwarg] if node.args.kwarg else []))
                            if arg.annotation]
            evaluated = [*node.args.defaults, *(value for value in node.args.kw_defaults if value), *annotations]
            if (getattr(node, 'decorator_list', ()) or
                    any(isinstance(part, ast.Call) for value in evaluated for part in ast.walk(value))):
                raise ValueError('Dynamic definition expressions cannot establish a geometry policy')
    if any(isinstance(node, ast.ImportFrom) and any(alias.name == '*' for alias in node.names)
           for node in ast.walk(tree)):
        raise ValueError('Wildcard imports cannot establish a geometry policy')
    declarations = {}
    def register(node, owner=None):
        owner = owner or node
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [part.id for target in targets for part in ast.walk(target) if isinstance(part, ast.Name)]
        elif isinstance(node, ast.AugAssign):
            names = [part.id for part in ast.walk(node.target) if isinstance(part, ast.Name)]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [item.asname or item.name.split('.')[0] for item in node.names]
        else:
            # Conditional module bindings belong to their complete control-flow
            # statement. Never silently omit a referenced global's assignment.
            for field in ('body', 'orelse', 'finalbody', 'handlers', 'cases'):
                for child in getattr(node, field, ()):
                    register(child, owner)
            targets = ([node.target] if isinstance(node, (ast.For, ast.AsyncFor)) else
                       [item.optional_vars for item in node.items if item.optional_vars]
                       if isinstance(node, (ast.With, ast.AsyncWith)) else [])
            names = [part.id for target in targets for part in ast.walk(target) if isinstance(part, ast.Name)]
        for name in names:
            if name in declarations and declarations[name] is not owner and not isinstance(node, ast.AugAssign):
                raise ValueError('Ambiguous geometry policy declaration: ' + name)
            declarations[name] = owner
    for node in tree.body:
        register(node)
    # Dynamic module initialization can change configuration without mentioning
    # it at the call site. Refuse this uncommon policy rather than infer purity.
    def mutates_globals(function, seen):
        if function.name in seen:
            return False
        seen.add(function.name)
        local = {arg.arg for arg in (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)}
        local.update(node.id for node in ast.walk(function) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store))
        mutators = {'update', 'append', 'extend', 'clear', 'add', 'remove', 'pop', 'setdefault', '__setitem__'}
        for part in ast.walk(function):
            if isinstance(part, ast.Global):
                return True
            base = (part.value if isinstance(part, (ast.Subscript, ast.Attribute)) and isinstance(part.ctx, ast.Store)
                    else part.func.value if isinstance(part, ast.Call) and isinstance(part.func, ast.Attribute)
                    and part.func.attr in mutators else None)
            if isinstance(base, ast.Name) and base.id in declarations and base.id not in local:
                return True
            if isinstance(part, ast.Call) and isinstance(part.func, ast.Name):
                called = declarations.get(part.func.id)
                if isinstance(called, (ast.FunctionDef, ast.AsyncFunctionDef)) and mutates_globals(called, seen):
                    return True
        return False
    def module_execution(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            return
        yield node
        for child in ast.iter_child_nodes(node):
            yield from module_execution(child)
    for node in module_execution(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called = declarations.get(node.func.id)
            if isinstance(called, (ast.FunctionDef, ast.AsyncFunctionDef)) and mutates_globals(called, set()):
                raise ValueError('Dynamic module initialization cannot establish a geometry policy')
    if not functions or any(name not in declarations for name in functions):
        raise ValueError('Geometry policy function is missing')
    pending, selected = list(functions), {}
    effects = [node for node in tree.body if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    imports = {}
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        node = declarations[name]
        related = [node, *(effect for effect in effects
                          if any(isinstance(part, ast.Name) and part.id == name for part in ast.walk(effect)))]
        selected[name] = [ast.dump(item, include_attributes=False) for item in related]
        if resolve_import:
            for item in related:
                for part in ast.walk(item):
                    if isinstance(part, (ast.Import, ast.ImportFrom)):
                        imports.update(resolve_import(part))
        pending.extend(part.id for item in related for part in ast.walk(item)
                       if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Load)
                       and part.id in declarations and part.id not in selected)
    return identity(dict(declarations=selected, support=imports))


def native_policy(source, functions, script, *, revision=None, inputs=None):
    """Bind selected repository imports without executing historical Python."""
    from . import source_imports, paths
    scanner = source_imports.ImportScanner()
    repo, script = paths.REPO.resolve(), Path(script).resolve()
    search = list(dict.fromkeys([script.parent, *(p for p in script.parents if p.is_relative_to(repo)), paths.STUDIO]))
    search = [p for p in search if p.is_relative_to(repo)]
    def resolve(node):
        if isinstance(node, ast.Import):
            names, bases = [alias.name for alias in node.names], search
        else:
            names = [node.module or '']
            bases = [script.parents[node.level - 1]] if node.level else search
        result = {}
        for name in names:
            found = next((files for base in bases if (files := scanner.resolve(base, name.split('.') if name else []))), [])
            for file in sorted({p for file in found for p in scanner.local_imports(file, search)}):
                relative_name = file.relative_to(repo).as_posix()
                text = (revision_source(repo, revision, relative_name) if revision else
                        saved_source(repo, relative_name, inputs.get('<repo>/' + relative_name)) if inputs is not None else
                        file.read_bytes().decode())
                if text is None:
                    raise ValueError('Missing historical geometry support: ' + relative_name)
                result[relative_name] = hashlib.sha256(text.encode()).hexdigest()
        return result
    return policy(source, functions, resolve)


def revision_source(repo, revision, filename):
    """Read a captured clean revision without executing donor code or fetching."""
    if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{40}', revision):
        return None
    name = relative(filename).as_posix()
    try:
        result = subprocess.run(['git', 'show', revision + ':' + name], cwd=repo,
                                capture_output=True, timeout=10)
        return result.stdout.decode() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None


def saved_source(repo, filename, recorded):
    """Resolve a saved per-file input identity to existing immutable Git bytes.

    Recognizes the published legacy basename+bytes and single-file Merkle
    algorithms. This recovers evidence without rewriting a successful stamp.
    """
    if not isinstance(recorded, str) or not re.fullmatch('[0-9a-f]{64}', recorded):
        return None
    name = relative(filename).as_posix()
    try:
        revisions = subprocess.run(['git', 'log', '-n', '64', '--format=%H', '--', name],
                                   cwd=repo, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    if revisions.returncode:
        return None
    for revision in revisions.stdout.splitlines():
        source = revision_source(repo, revision, name)
        if source is not None:
            raw = source.encode()
            old = hashlib.sha256(Path(name).name.encode() + raw).hexdigest()
            merkle = identity({'schema': 1, 'files': {'0/.': {
                'kind': 'file', 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}})
            if recorded in (old, merkle):
                return source
    return None


def recorded_source_matches(tag, source):
    """Check Unreal's stored import hash; absent/multiple/unknown sources miss."""
    try:
        records = json.loads(tag)
        if not isinstance(records, list) or len(records) != 1:
            return False
        expected = records[0]['FileMD5'].lower()
        return (bool(re.fullmatch('[0-9a-f]{32}', expected)) and expected != '0' * 32
                and digest(source, 'md5') == expected)
    except (ValueError, TypeError, KeyError, OSError, AttributeError):
        return False


def package_members(package):
    if not package.startswith('/Game/'):
        raise ValueError('Native mesh reuse only owns game packages')
    stem = relative(package.removeprefix('/Game/')).as_posix()
    return ['content/' + stem + suffix for suffix in ('.uasset', '.uexp', '.ubulk', '.uptnl', '.m.ubulk', '.upayload')]


def package_inventory(content, packages):
    if not isinstance(packages, (list, tuple)) or not packages or len(set(packages)) != len(packages):
        raise ValueError('Native mesh package inventory must be nonempty and unique')
    result = {}
    for package in packages:
        present = False
        for member in package_members(package):
            path = safe_destination(Path(content), member.removeprefix('content/'))
            if path.is_symlink():
                raise ValueError('Linked native mesh package')
            if path.exists():
                result[member] = dict(sha256=digest(path), size=path.stat().st_size)
                present |= member.endswith('.uasset')
        if not present:
            raise ValueError('Native mesh package is incomplete: ' + package)
    return result


def pending_path(ctx, task, nonce):
    if (not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', task) or '..' in task
            or not re.fullmatch('[0-9a-f]{24}', nonce)):
        raise ValueError('Invalid native mesh receipt owner or invocation')
    result = safe_destination(ctx.out, '.state/mesh-import-pending/' + task + '/' + nonce + '.json')
    if result.is_symlink():
        raise ValueError('Linked pending native mesh evidence')
    return result


def prior_stamp(ctx, task, nonce, pointer):
    """Historical non-success evidence must belong to this exact invocation."""
    try:
        pending_path(ctx, task, nonce)  # shared task/nonce validation
        target = safe_destination(ctx.out, '.state/mesh-import-prior/' + task + '/' + nonce + '.json')
        if not pointer or Path(pointer) != target or target.is_symlink():
            return None
        packet = read_json(target)
        if (not isinstance(packet, dict) or packet.get('schema') != 1 or packet.get('task') != task or packet.get('nonce') != nonce
                or not isinstance(packet.get('stamp'), dict)):
            return None
        known = packet['stamp'].get('checkpoint_incremental_context')
        if known is not None and known != packet.get('observed_context'):
            return None
        return packet['stamp']
    except (OSError, ValueError, TypeError, CheckpointError):
        return None


def historical_packages_match(ctx, task, stamp, packages):
    """@cc [owner:fontanierh,label:correctness] distinguish-selection-from-output-proof
    A selected checkpoint tool key without an inventory or stored action MUST NOT be
    treated as a produced byte certificate. It MAY use the existing compatibility-only
    pre-inventory continuity checks. An explicit inventory, stored action or conflict
    MUST validate or refuse; failed proof MUST NOT fall back to timestamps.
    Native source/options/owner/context validation remains mandatory outside this helper.
    """
    try:
        current = package_inventory(ctx.uproject.parent / 'Content', packages)
        key = stamp.get('checkpoint_key')
        target = None
        if key is not None:
            store = ReadStore(ctx.game)
            target = entry_path(store, key)
            if os.path.lexists(target.with_suffix('.conflict')):
                return False
        if 'checkpoint_inventory' in stamp or target is not None and os.path.lexists(target):
            if target is None:
                return False
            entry = validate_action(read_json(target), store, key)
            if (entry['task'] != task or entry['fingerprint'] != stamp['fingerprint']
                    or entry['stamp']['checkpoint_inventory'] != stamp['checkpoint_inventory']):
                return False
            expected = {member: {k: value[k] for k in ('sha256', 'size')}
                        for package in packages for member in package_members(package)
                        if (value := entry['files'].get(member)) and value.get('kind') == 'file'}
            return expected == current
        # The old incremental format has no byte proof. Never admit packages
        # saved after its successful task; native source/options checks remain mandatory.
        finished = stamp['time']
        if type(finished) not in (float, int) or finished <= 0:
            return False
        observations = [safe_destination(ctx.uproject.parent / 'Content', member.removeprefix('content/')).stat()
                        for member in current]
        return all(info.st_mtime <= finished and info.st_ctime <= finished for info in observations)
    except (OSError, ValueError, KeyError, TypeError, CheckpointError):
        return False


def source_member(ctx, source):
    from . import paths
    source = Path(source).resolve()
    for label, root in [('generated', ctx.out), ('game', ctx.uproject.parent.parent), ('repo', paths.REPO)]:
        root = root.resolve()
        if source.is_relative_to(root):
            return label + '/' + source.relative_to(root).as_posix()
    raise ValueError('Native mesh source is outside its owning game/build')


def resolve_source(ctx, member):
    label, _, name = relative(member).as_posix().partition('/')
    from . import paths
    roots = {'generated': ctx.out, 'game': ctx.uproject.parent.parent, 'repo': paths.REPO}
    if label not in roots:
        raise ValueError('Unknown native mesh source root')
    path = safe_destination(roots[label], name)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Native mesh source is missing or linked')
    return path


def queue_pending(ctx, task, nonce, import_policy, current_context, name, record, counts, *, miss_reasons=None):
    """Native child evidence; only the successful parent can finalize package receipts."""
    target = pending_path(ctx, task, nonce)
    header = dict(schema=1, task=task, nonce=nonce, policy=import_policy, context=current_context)
    packet = read_json(target) if target.exists() else dict(**header, entries={})
    if any(packet.get(k) != v for k, v in header.items()) or not isinstance(packet.get('entries'), dict):
        raise ValueError('Pending native mesh evidence differs from this invocation')
    if record is not None:
        packet['entries'][name] = record
    packet['counts'] = counts
    if miss_reasons is not None:
        packet['miss_reasons'] = miss_reasons
    atomic_json(target, packet)


def finalize_pending(ctx, task, nonce):
    """@cc [owner:fontanierh,label:correctness] finalize-mesh-receipts-after-native-success
    Only a host that verified the owned native command's marker and positive guard
    cleanup MAY call this function. It MUST bind the exact invocation, current engine
    context and unchanged source bytes, then inventory every final saved package.
    Pending child evidence alone MUST NOT publish receipts or receiving task stamps.
    """
    for owner in (task, task + '.assets'):
        evidence = _finalize_pending(ctx, owner, nonce)
        if evidence is not None:
            ctx.__dict__.setdefault('native_candidate_observations', {}).setdefault(task, []).append(evidence)


def _finalize_pending(ctx, task, nonce):
    target = pending_path(ctx, task, nonce)
    if not target.exists():
        return
    from .native_protocol import context
    packet = read_json(target)
    if (not isinstance(packet, dict) or packet.get('schema') != 1 or packet.get('task') != task or packet.get('nonce') != nonce
            or packet.get('context') != context(ctx) or not isinstance(packet.get('entries'), dict)
            or not isinstance(packet.get('counts'), dict)
            or any(type(value) is not int or value < 0 for value in packet['counts'].values())
            or not re.fullmatch('[0-9a-f]{64}', packet.get('policy', ''))):
        raise ValueError('Malformed pending native mesh evidence')
    content = ctx.uproject.parent / 'Content'
    misses = packet.get('miss_reasons', {})
    if (not isinstance(misses, dict) or len(misses) > 64
            or any(not isinstance(key, str) or not re.fullmatch('[a-z_]{1,80}', key)
                   or type(value) is not int or value < 0 for key, value in misses.items())):
        raise ValueError('Malformed native reuse miss diagnostics')
    receipts = Receipts(ctx.out, task, packet['context'], packet['policy'], content)
    prepared = {}
    for name, entry in packet['entries'].items():
        asset_group = isinstance(entry, dict) and entry.get('kind') == 'asset-group'
        if (not isinstance(entry, dict) or
                (entry.get('native_assets_validated') if asset_group else entry.get('native_source_validated')) is not True
                or not entry.get('sources')
                or not re.fullmatch('[0-9a-f]{64}', entry.get('key', ''))):
            raise ValueError('Missing native mesh source validation')
        if (not isinstance(entry.get('packages'), list) or not entry['packages']
                or (not asset_group and sorted(entry['packages']) != sorted(item.get('package') for item in entry['sources']))
                or not isinstance(entry.get('provenance'), dict)):
            raise ValueError('Incomplete native mesh package/source group')
        for item in entry['sources']:
            if digest(resolve_source(ctx, item['member'])) != item['sha256']:
                raise ValueError('Native mesh source changed after validation')
        prepared[name] = dict(identity=entry['key'], packages=package_inventory(content, entry['packages']),
                              provenance=entry['provenance'])
    if prepared:
        receipts.records.update(prepared)
        atomic_json(receipts.path, dict(**receipts.header, meshes=receipts.records))
    atomic_json(receipts.path.with_name('summary.json'), dict(schema=1, task=task,
                invocation=nonce, counts=packet['counts'], miss_reasons=misses, finalized_after_native_success=True))
    target.unlink()
    return dict(context=packet['context'], entries=packet['entries'], records=prepared)


class Receipts:
    """@cc [owner:fontanierh,label:correctness] mesh-reuse-receipts
    A geometry receipt MUST bind current inputs, engine context, import policy and
    every saved package sidecar. It MUST be recorded only after the current native
    validator succeeds, and MUST NOT be promoted to a whole-task success stamp.
    A changed, missing or newly appearing sidecar MUST refuse local reuse.
    """
    def __init__(self, output, task, context, import_policy, content):
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', task):
            raise ValueError('Invalid native import owner')
        self.path = safe_destination(Path(output), 'native-imports/' + task + '/meshes.json')
        self.content = Path(content)
        self.header = dict(schema=1, context=context, policy=import_policy)
        self.records = {}
        self.previous = None
        if self.path.exists():
            try:
                saved = read_json(self.path)
                if (isinstance(saved, dict) and isinstance(saved.get('meshes'), dict)
                        and saved.get('schema') == self.header['schema'] and saved.get('context') == context):
                    self.previous = saved
                    if saved.get('policy') == import_policy:
                        self.records = saved['meshes']
            except (OSError, ValueError, CheckpointError):
                pass

    def matches(self, name, key, packages):
        return self._matches(self.records.get(name), key, packages)

    def matches_previous(self, name, key, packages, policies):
        """@cc [owner:fontanierh,label:correctness] unchanged-production-before-revalidation
        A previous receipt MAY supply saved byte proof only under its exact reproduced
        historical policy and unchanged engine context. The caller MUST separately prove
        current raw-geometry/owner compatibility and run current native validation. Every
        source identity and saved package sidecar MUST still match; this MUST NOT publish
        a current receipt or treat a validator-only change as a geometry change.
        """
        if (self.previous is None or not isinstance(self.previous.get('policy'), str)
                or self.previous['policy'] not in policies):
            return False
        return self._matches(self.previous['meshes'].get(name), key, packages)

    def _matches(self, old, key, packages):
        if not isinstance(old, dict) or old.get('identity') != key:
            return False
        try:
            return old['packages'] == package_inventory(self.content, packages)
        except (OSError, ValueError, KeyError):
            return False

    def record(self, name, key, packages, *, evidence, provenance=None):
        if evidence != 'current-native-validation':
            raise ValueError('A captured candidate cannot certify native geometry')
        self.records[name] = dict(identity=key, packages=package_inventory(self.content, packages),
                                  provenance=provenance or {'kind': 'current-native-import'})
        atomic_json(self.path, dict(**self.header, meshes=self.records))
