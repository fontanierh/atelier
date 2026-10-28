"""Compatibility identity from declared frozen Native/Data Items and staged code only."""
import hashlib
import runpy
from types import SimpleNamespace
import json
from pathlib import Path, PurePosixPath

from atelier.build_v2.recipe_job import inventory
identity = SimpleNamespace(**runpy.run_path(str(Path(__file__).parents[1] / 'network_identity.py'),
                                          run_name='atelier_network_identity_body'))


def _relative(value, *, empty=False):
    if (not isinstance(value, str) or (not value and not empty) or '\\' in value
            or PurePosixPath(value).is_absolute() or (value and PurePosixPath(value).as_posix() != value)
            or any(part in ('.', '..') for part in value.split('/') if part)):
        raise ValueError('Identity requires a canonical declared content path')
    return value


def _root(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path or path.is_symlink() or not path.exists():
        raise ValueError('Identity input is absent or aliased')
    return path


def _excluded(name):
    relative = PurePosixPath(name)
    return (bool(set(relative.parts) & identity.IGNORED) or relative.name.casefold() in identity.DESKTOP_METADATA
            or relative == PurePosixPath('Data/Network') or relative.is_relative_to('Data/Network'))


def _inputs(native_roots, derived, data):
    files = {}
    def add(name, path):
        _relative(name)
        if _excluded(name): return
        if name in files:
            raise ValueError('Identity content has duplicate actual output ownership: ' + name)
        files[name] = path
    for root in [*native_roots, *(child.products[0].paths[0] for group in derived for child, _piece in group)]:
        root = _root(root)
        if not root.is_dir(): raise ValueError('Finished Native Item must be a directory')
        rows = inventory(root)
        count = 0
        for name, kind, _size, _mode, _sha256 in rows:
            if kind != 'file': continue
            if not name.startswith('content/Game/'):
                raise ValueError('Finished Native Item contains a non-Content member')
            relative = name.removeprefix('content/Game/')
            if not relative.endswith(('.uasset', '.umap', '.uexp', '.ubulk', '.uptnl', '.upayload')):
                raise ValueError('Finished Native Item contains an unknown package member')
            add(relative, root / name); count += 1
        if not count: raise ValueError('Finished Native Item contains no actual package files')
    for destination, root in data:
        destination = _relative(destination)
        if destination != 'Data' and not destination.startswith('Data/'):
            raise ValueError('Runtime Data input escapes Content/Data')
        root = _root(root)
        for name, kind, _size, _mode, _sha256 in inventory(root):
            if kind != 'file': continue
            add(destination + ('/' + name if name else ''), root / name if name else root)
    records = []
    for index, (name, path) in enumerate(sorted(files.items())):
        records.append({'path': name, 'sha1': identity.sha1_file(path)})
        if index % 250 == 0: print(f'identity: checked {index + 1}/{len(files)} selected content files', flush=True)
    return records


def content(native_roots=(), derived=(), data=(), output=None):
    """@cc [owner:fontanierh,label:correctness] selected-item-content-inventory
    Inventory MUST read only supplied finished Native Items and decoded runtime Data
    roots. Reject links, foreign members and duplicate ownership. Report exact SHA1
    bytes without scanning or archiving the checkout Content namespace; v2 installation
    owns stale-output retirement. Network output MUST remain excluded.
    """
    records = _inputs(native_roots, derived, data)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists(): raise ValueError('Content inventory output must be fresh')
    output.write_text(json.dumps({'mode': 'selected_items', 'files': records}, indent=2, sort_keys=True) + '\n')


def network(native_roots=(), derived=(), data=(), code=(), content_report=None, output=None):
    """@cc [owner:fontanierh,label:correctness] declared-network-compatibility-identity
    Session identity MUST preserve the original protocol, canonical SHA1 record and
    signature rules, source-only CRLF normalization and Data/Network exclusion. The
    exact supplied frozen content MUST include Data/world.json and an imported map.
    Code membership MUST be explicit original code_files inputs, never a runtime scan.
    No identity may depend on itself or mutable checkout Content.
    """
    records = _inputs(native_roots, derived, data)
    report = json.loads(_root(content_report).read_bytes())
    if report != {'mode': 'selected_items', 'files': records}:
        raise ValueError('Network frozen inventory differs from data.content')
    if not any(row['path'] == 'Data/world.json' for row in records) or not any(row['path'].endswith('.umap') for row in records):
        raise ValueError('Cannot certify multiplayer content before world data and the imported map exist')
    native, files = [], []
    for row in records:
        if row['path'].startswith('Data/'):
            files.append({'path': row['path'][5:], 'sha1': row['sha1']})
        elif Path(row['path']).suffix in {'.uasset', '.umap', '.uexp', '.ubulk'}:
            native.append(row)
    names, code_records = set(), []
    for name, source in code:
        _relative(name)
        if name in names: raise ValueError('Duplicate declared network code source')
        names.add(name); source = _root(source)
        if not source.is_file(): raise ValueError('Declared network code is not a file')
        code_records.append({'path': name, 'sha1': hashlib.sha1(source.read_bytes().replace(b'\r\n', b'\n')).hexdigest()})
    if not code_records: raise ValueError('Network identity requires its actual native code/config sources')
    code_hash, assets = identity.records_digest(code_records), identity.records_digest(native)
    result = {'protocol': identity.PROTOCOL, 'code': code_hash, 'assets': assets,
              'signature': identity.signature(code_hash, assets, files), 'files': files}
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists(): raise ValueError('Network session output must be fresh')
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(f'NETWORK IDENTITY {result["signature"]}: {len(files)} data files, {len(native)} imported assets', flush=True)
