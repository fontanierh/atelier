"""Execute one declared producer in its private project view and encode complete roots.

The controller keys this implementation and all declared project code. Archives never
follow links, represent optional absence explicitly, and restore only their named root.
"""
import ast
from collections.abc import Mapping
import hashlib
from dataclasses import dataclass, is_dataclass
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import shutil
import stat
import sys
import tarfile
import types

RUNTIME = '.recipe-runtime'
MANIFEST = 'atelier-root.json'


def relative(value):
    if (not isinstance(value, str) or not value or '\\' in value
            or PurePosixPath(value).is_absolute() or str(PurePosixPath(value)) != value
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('noncanonical recipe path')
    return value


def inventory(root, *, check_cancelled=None):
    """Complete, sorted nofollow membership, with stable regular bytes and modes."""
    root = Path(root)
    if not os.path.lexists(root):
        return []
    rows = []
    def visit(path, name):
        if check_cancelled is not None:check_cancelled()
        before = path.lstat()
        if stat.S_ISDIR(before.st_mode):
            rows.append((name, 'directory', 0, 0o755, None))
            for child in sorted(path.iterdir(), key=lambda p: p.name):
                visit(child, name + '/' + child.name if name else child.name)
        elif stat.S_ISREG(before.st_mode):
            if before.st_nlink != 1:
                raise ValueError('root contains a hard link')
            digest = hashlib.sha256()
            count = 0
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise ValueError('root changed while opening')
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    if check_cancelled is not None:check_cancelled()
                    digest.update(chunk)
                    count += len(chunk)
                after = os.fstat(stream.fileno())
            named = path.lstat()
            fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if fields(before) != fields(after) or fields(after) != fields(named) or count != before.st_size:
                raise ValueError('root changed while reading')
            rows.append((name, 'file', count, 0o755 if before.st_mode & 0o111 else 0o644, digest.hexdigest()))
        else:
            raise ValueError('root contains a link or special file')
    visit(root, '')
    return rows


def pack_root(root, destination, *, required=True):
    rows = inventory(root)
    if not rows and required:
        raise ValueError('required recipe output is absent')
    manifest = {'version': 1, 'kind': rows[0][1] if rows else 'absent',
                'entries': [list(row) for row in rows]}
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode('ascii')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as output, tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        entry = tarfile.TarInfo(MANIFEST)
        entry.size, entry.mode = len(encoded), 0o644
        archive.addfile(entry, io.BytesIO(encoded))
        for name, kind, size, mode, digest in rows:
            entry = tarfile.TarInfo('root' + ('/' + name if name else ''))
            entry.mode, entry.size = mode, size
            if kind == 'directory':
                entry.type = tarfile.DIRTYPE
                archive.addfile(entry)
            else:
                fd = os.open(Path(root) / name if name else root, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as stream:
                    archive.addfile(entry, stream)
    if inventory(root) != rows:
        raise ValueError('recipe output changed while archiving')
    return manifest


def unpack_root(source, destination, *, check_cancelled=None):
    """Validate the complete archive before creating its independently copied root."""
    destination = Path(destination)
    if check_cancelled is not None:check_cancelled()
    if os.path.lexists(destination):
        raise ValueError('archive destination already exists')
    with tarfile.open(source, 'r:') as archive:
        members = []
        for member in archive:
            if check_cancelled is not None:check_cancelled()
            members.append(member)
        if not members or members[0].name != MANIFEST or not members[0].isreg() or members[0].size > 16 * 1024 * 1024:
            raise ValueError('missing bounded root manifest')
        manifest = json.loads(archive.extractfile(members[0]).read())
        if set(manifest) != {'version', 'kind', 'entries'} or manifest['version'] != 1:
            raise ValueError('invalid root manifest')
        rows = manifest['entries']
        if not isinstance(rows, list) or len(rows) > 1_000_000 or len(members) != len(rows) + 1:
            raise ValueError('incomplete root membership')
        expected_kind = rows[0][1] if rows else 'absent'
        if manifest['kind'] != expected_kind or expected_kind not in ('absent', 'file', 'directory'):
            raise ValueError('invalid root kind')
        seen = set()
        for member, row in zip(members[1:], rows):
            if check_cancelled is not None:check_cancelled()
            if not isinstance(row, list) or len(row) != 5:
                raise ValueError('invalid root member')
            name, kind, size, mode, digest = row
            if name:
                relative(name)
            if name in seen or (not seen and name != ''):
                raise ValueError('duplicate or missing archive root')
            if name and name.rpartition('/')[0] not in seen:
                raise ValueError('archive parent is missing')
            seen.add(name)
            if (member.name != 'root' + ('/' + name if name else '') or member.linkname
                    or member.mode != mode or member.size != size or mode not in (0o644, 0o755)
                    or not ((kind == 'file' and member.isreg() and isinstance(digest, str) and len(digest) == 64)
                            or (kind == 'directory' and member.isdir() and size == 0 and digest is None))):
                raise ValueError('archive member differs from manifest')
        destination.parent.mkdir(parents=True, exist_ok=True)
        for member, row in zip(members[1:], rows):
            if check_cancelled is not None:check_cancelled()
            name, kind, size, mode, digest = row
            path = destination / name if name else destination
            if kind == 'directory':
                path.mkdir(mode=0o755)
            else:
                actual = hashlib.sha256()
                with archive.extractfile(member) as incoming, path.open('xb') as outgoing:
                    for chunk in iter(lambda: incoming.read(1024 * 1024), b''):
                        if check_cancelled is not None:check_cancelled()
                        actual.update(chunk)
                        outgoing.write(chunk)
                if actual.hexdigest() != digest:
                    raise ValueError('archive payload digest mismatch')
                path.chmod(mode)
    return manifest


def prepare_view(job, job_dir, *, reserved=(), materializer=None, check_cancelled=None):
    """@cc [owner:fontanierh,label:correctness;safety] trusted-root-materialization
    Only the fixed trusted outer worker MAY provide a materializer callback. It MUST restore the complete
    root from the actual frozen archive with the same bytes, membership and modes as the ordinary codec;
    it MUST NOT infer permissions or omit any declared mapping. Default callers use the unchanged codec.
    A supplied cancellation check MUST run during preparation traversals and bounded file reads, and its
    refusal MUST propagate before the producer body runs. Reserved names remain bootstrap-only roles.
    """
    def check():
        if check_cancelled is not None:check_cancelled()
    def copy_file(source, destination):
        check()
        if check_cancelled is None:return shutil.copyfile(source, destination)
        with open(source,'rb') as incoming, open(destination,'wb') as outgoing:
            for chunk in iter(lambda:incoming.read(1024*1024),b''):
                check();outgoing.write(chunk)
        return destination
    def same_file(source, destination):
        if check_cancelled is None:return source.read_bytes()==destination.read_bytes()
        with source.open('rb') as incoming, destination.open('rb') as existing:
            while True:
                check();first=incoming.read(1024*1024);second=existing.read(1024*1024)
                if first!=second:return False
                if not first:return True
    check()
    root = Path(job_dir) / RUNTIME
    if (not root.is_dir() or root.is_symlink()
            or any(not isinstance(name, str) or relative(name) != name or '/' in name for name in reserved)
            or {path.name for path in root.iterdir()} != set(reserved)):
        raise ValueError('recipe runtime is not a fresh reserved directory')
    view = root / 'view'
    view.mkdir()
    (root / 'tmp').mkdir()
    recipe = job['params']['recipe']
    protected = []
    def target(name):
        check()
        result = view / relative(name)
        result.parent.mkdir(parents=True, exist_ok=True)
        return result
    for name in job['code']:
        check()
        source = Path(job_dir) / relative(name)
        if not stat.S_ISREG(source.lstat().st_mode):
            raise ValueError('code is not a regular staged file')
        result = target(name)
        copy_file(source, result)
        result.chmod(0o444)
        protected.append(str(result))
    declared = {item['path']: item for item in job['inputs']}
    for logical, staged in recipe['paths'].items():
        check()
        relative(staged)
        if not any(staged == path or staged.startswith(path + '/') for path in declared):
            raise ValueError('recipe mapping is outside declared inputs')
        source = Path(job_dir) / staged
        result = target(logical)
        if not os.path.lexists(source):
            continue
        if staged.endswith('.tree.tar'):
            if materializer is not None:materializer(source,result)
            elif check_cancelled is not None:unpack_root(source,result,check_cancelled=check_cancelled)
            else:unpack_root(source,result)
            check()
        elif stat.S_ISDIR(source.lstat().st_mode):
            inventory(source,check_cancelled=check_cancelled)  # Reject links/special members before copying.
            if check_cancelled is None:shutil.copytree(source,result)
            else:
                def copy_member(source,destination):
                    copy_file(source,destination);shutil.copystat(source,destination)
                    return destination
                def visit_directory(source,names):
                    check();return []
                shutil.copytree(source,result,copy_function=copy_member,ignore=visit_directory)
        else:
            if not stat.S_ISREG(source.lstat().st_mode):
                raise ValueError('raw mapped input is not a regular file')
            if result.exists():
                if not same_file(source,result):
                    raise ValueError('code/input mapping collision')
            else:
                copy_file(source, result)
        protected.append(str(result))
    writes = []
    for row in recipe['outputs']:
        check()
        path = target(row['path'])
        if any(path == Path(p) or path.is_relative_to(p) or Path(p).is_relative_to(path) for p in protected):
            raise ValueError('output overlaps frozen inputs/code')
        writes.append(str(path))
    return view, protected, writes


@dataclass(frozen=True)
class RecipePaths:
    """Declarative paths only; permissions still come from the existing job guard."""
    game: str
    out: Path
    game_dir: Path
    uproject: Path | None
    unreal_root: None = None


class RecipeStdout:
    """Write-only progress output, without access to the worker's stream object."""
    __slots__ = ()

    def write(self, value):
        if not isinstance(value, str):
            raise TypeError('recipe progress must be text')
        return sys.stdout.write(value)

    def flush(self):
        sys.stdout.flush()


def _value(value, view, namespace=None):
    if isinstance(value, (list, tuple)):
        return [_value(v, view, namespace) for v in value]
    if not isinstance(value, Mapping):
        return value
    if set(value) == {'recipe_context'}:
        fields = value['recipe_context']
        if set(fields) != {'game', 'out', 'game_dir', 'uproject', 'unreal_root'} or fields['unreal_root'] is not None:
            raise ValueError('unsupported recipe path context')
        if (not isinstance(fields['game'], str) or '/' in fields['game']
                or relative(fields['game']) != fields['game']
                or any(not isinstance(fields[k], Mapping) or set(fields[k]) != {'path'}
                       for k in ('out', 'game_dir'))
                or (fields['uproject'] is not None and (not isinstance(fields['uproject'], Mapping)
                    or set(fields['uproject']) != {'path'}))):
            raise ValueError('invalid recipe path context fields')
        return RecipePaths(**{k: _value(v, view, namespace) for k, v in fields.items()})
    if set(value) == {'recipe_stdout'}:
        if value['recipe_stdout'] is not True:
            raise ValueError('invalid recipe stdout descriptor')
        return RecipeStdout()
    if set(value) == {'path'}:
        return view / relative(value['path'])
    if set(value) == {'text'}:
        return value['text'].replace('<checkout>', str(view))
    if 'module' in value:
        module = importlib.import_module(value['module'])
        if 'source' in value and 'root' not in value and Path(module.__file__) != view / relative(value['source']):
            raise ValueError('callback module differs from declared source')
        return module
    if set(value) == {'derived_items'}:
        descriptor = value['derived_items']
        if set(descriptor) != {'root', 'members'}:
            raise ValueError('unresolved derived item roster')
        return [(types.SimpleNamespace(products=[types.SimpleNamespace(paths=(view / relative(row['root']),))]), row['piece'])
                for row in descriptor['members']]
    if set(value) == {'set'}:
        return set(_value(value['set'], view, namespace))
    if set(value) == {'callable'}:
        return bind(value['callable'], view)
    if set(value) == {'type'}:
        module, _, name = value['type'].rpartition('.')
        return getattr(importlib.import_module(module), name)
    if set(value) == {'record', 'fields'}:
        classes = [candidate for candidate in (namespace or {}).values()
                   if isinstance(candidate, type) and candidate.__name__ == value['record'] and is_dataclass(candidate)]
        if len(set(classes)) != 1:
            raise ValueError('callback record has no unique captured class binding')
        return classes[0](**{key: _value(item, view, namespace) for key, item in value['fields'].items()})
    return {k: _value(v, view, namespace) for k, v in value.items()}


def bind(binding, view):
    source = view / relative(binding['source'])
    sys.path.insert(0, str(source.parent))
    namespace = runpy.run_path(str(source), run_name='atelier_recipe_callback_source')
    tree = ast.parse(source.read_text(), filename=str(source))
    if binding.get('bound') is not None:
        raise ValueError('bound callable requires an explicit receiver role')
    captures = binding.get('captures', binding.get('closure'))
    freevars = []
    # Recompile the actual nested body inside a factory to retain Python's freevar semantics.
    matches = [code for code in _codes(compile(tree, str(source), 'exec'))
               if code.co_firstlineno == binding['line'] and code.co_qualname == binding['qualname']]
    original = matches[0] if len(matches) == 1 else None
    if original is None or len(original.co_freevars) != len(captures):
        raise ValueError('callback closure does not match current source')
    for value in captures:
        cell = (lambda x: lambda: x)(_value(value, view, namespace)).__closure__[0]
        freevars.append(cell)
    result = types.FunctionType(original, namespace, original.co_name,
                                tuple(_value(binding['defaults'], view, namespace)), tuple(freevars) or None)
    result.__kwdefaults__ = _value(binding['kwdefaults'], view, namespace)
    return result


def _codes(code):
    yield code
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            yield from _codes(value)


def verify_encoded_plan(root, *, parent, limits):
    """Reuse the original encoded decoder for every complete planned packet."""
    from atelier import encoded_glb
    if root.is_symlink() or not root.is_dir() or any(p.is_symlink() or not p.is_file() or p.stat().st_nlink != 1 for p in root.iterdir()):
        raise ValueError('encoded plan contains a link or unsupported member')
    raw = (root / 'plan.json').read_bytes()
    if len(raw) > limits['max_manifest_bytes']:
        raise ValueError('encoded manifest exceeds declared bound')
    value = json.loads(raw)
    if (value.get('parent') != parent or value.get('kind') != 'encoded_glb'
            or value.get('schema') != 1 or value.get('complete') is not True
            or value.get('triangle_limit') != 32768
            or not 0 < len(value.get('pieces', ())) <= limits['max_pieces']):
        raise ValueError('incomplete encoded plan')
    expected = {'plan.json'}
    totals = {'render': 0, 'collision': 0}
    total_bytes = len(raw)
    for row in value['pieces']:
        name = relative(row['name'])
        if '/' in name or row['payload'] != name + '.mesh' or row['payload'] in expected:
            raise ValueError('aliased encoded plan member')
        expected.add(row['payload'])
        path = root / row['payload']
        if path.stat().st_size > limits['max_member_bytes']:
            raise ValueError('encoded member exceeds declared bound')
        packet = path.read_bytes()
        identity, _ = encoded_glb.decode(packet, key=name)
        if (hashlib.sha256(packet).hexdigest() != row['sha256']
                or any(identity[field] != row[field] for field in ('triangles', 'role', 'bounds'))):
            raise ValueError('encoded member differs from complete plan')
        totals[identity['role']] += identity['triangles']
        total_bytes += len(packet)
    if (total_bytes > limits['max_total_bytes'] or not totals['render']
            or value['source_triangles'] != sum(totals.values())
            or value['source_render_triangles'] != totals['render']
            or value['source_collision_triangles'] != totals['collision']
            or {p.name for p in root.iterdir()} != expected
            or any(p.is_symlink() or not p.is_file() for p in root.iterdir())):
        raise ValueError('incomplete encoded plan conservation or membership')
    return value


def run(context):
    recipe = context.params['recipe']
    geometry = recipe.get('geometry')
    if geometry is not None:
        if (geometry.get('format') not in ('fbx', 'glb')
                or geometry.get('encoding') not in ('mesh_ir', 'mesh_set', 'encoded_glb')
                or (geometry['encoding'] == 'encoded_glb' and geometry['format'] != 'glb')):
            raise ValueError('Recipe geometry requires its declared encoding and exact export format')
    view = Path.cwd()
    output = context.output_dir.absolute()
    game_roots = sorted({view / '/'.join(path.split('/')[:2]) for path in recipe['paths']
                         if path.startswith('games/')})
    sys.path[:0] = [str(view / 'platform/studio'), *map(str, game_roots), str(view)]
    old = list(sys.argv), dict(os.environ)
    atomic = None
    token = None
    held = getattr(context, '_atomic_temporary', None)
    if held is not None and (view / 'platform/studio/atelier/atomic_files.py').is_file():
        # The fixed bootstrap already opened/validated this exact reserved directory,
        # before PathGuard. Reuse the shared helper's held-fd scope, never reopen '/'.
        from atelier import atomic_files as atomic
        token = atomic._MANAGED_TEMPORARY.set(held)
    try:
        for command in recipe['commands']:
            if command['kind'] == 'call':
                bind(command['call'], view)()
                continue
            if command['kind'] not in ('python', 'blender'):
                raise ValueError('unregistered recipe command')
            if command['kind'] == 'blender' and 'bpy' not in sys.modules:
                raise ValueError('Blender command requires the Blender worker')
            script = view / relative(command['script'])
            sys.path.insert(0, str(script.parent))
            sys.argv[:] = [str(script), *(['--'] if command['kind'] == 'blender' else []), *map(str, _value(command['args'], view))]
            for key, value in command['env']:
                os.environ[key] = str(_value(value, view))
            try:
                runpy.run_path(str(script), run_name='__main__')
            except SystemExit as error:
                if error.code not in (None, 0):
                    raise
        if recipe['verify'] is not None and not bind(recipe['verify'], view)():
            raise ValueError('original producer verification refused outputs')
        for row in recipe['outputs']:
            pack_root(view / relative(row['path']), output / relative(row['file']),
                      required=row.get('required', True))
        if recipe.get('file_group'):
            from atelier.build_v2.file_groups import emit
            group = recipe['file_group']
            if context.params.get('file_root') != 'output/files':
                raise ValueError('File group requires its exact declared output root')
            emit(view / relative(group['source']), output / 'files',
                 parent=group['parent'], extensions=group['extensions'])
        if recipe.get('geometry'):
            geometry = recipe['geometry']
            root = view / relative(geometry['source'])
            if geometry['encoding'] == 'encoded_glb':
                verify_encoded_plan(root, parent=geometry['parent'], limits=context.params['plan_limits'])
            elif geometry['encoding'] in ('mesh_ir', 'mesh_set'):
                from atelier.build_v2.blender_ops import verify_plan
                verify_plan(root, parent=geometry['parent'], limits=context.params['plan_limits'],
                            output_format=geometry['format'], plan_encoding=geometry['encoding'])
            else:
                raise ValueError('unsupported geometry encoding')
            shutil.copytree(root, output / 'geometry')
    finally:
        if token is not None:
            atomic._MANAGED_TEMPORARY.reset(token)
        sys.argv[:] = old[0]
        os.environ.clear()
        os.environ.update(old[1])
