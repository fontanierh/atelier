"""Replace mutable Content identity scans with explicit frozen Native and runtime Data Item reads."""
from copy import deepcopy
import importlib.util
from pathlib import Path, PurePosixPath

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_cook_pipeline import NATIVE_CLASSES

GAME = 'games/yorimichi'
BODY = GAME + '/world/identity_v2.py'
ORIGINAL = GAME + '/network_identity.py'
POLICY = GAME + '/content_policy.py'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
CONTENT = GAME + '/unreal/Content/'
SESSION = CONTENT + 'Data/Network/session.json'
INVENTORY = 'build/yorimichi/runtime-content.json'


def _load(root, path, label):
    spec = importlib.util.spec_from_file_location(label, root / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or PurePosixPath(value).is_absolute()
            or PurePosixPath(value).as_posix() != value or any(p in ('', '.', '..') for p in value.split('/'))):
        raise ValueError('Identity declaration requires a canonical relative path')
    return value


def _native(item):
    return (item.get('class') in NATIVE_CLASSES and item.get('logical_path', '').startswith('/Game/')
            and not item['logical_path'].startswith(('/Game/_Raw/', '/Game/AtelierRaw/')))


def identity_units(rows, *, checkout, native_units, geometry, data):
    """@cc [owner:fontanierh,label:correctness] immutable-network-content-declarations
    Membership MUST derive only from actual supplied finished static Native owners,
    existing validated template/follower Items and explicit runtime Data ROOT refs.
    Every original native code/config source MUST be a keyed File input at its exact
    checkout-relative path. Network MUST exclude itself and Data/Network before
    adding dependencies. Unknown/overlapping ownership MUST refuse compilation.
    """
    root = Path(checkout).resolve(); by_id = {row['id']: row for row in rows}
    if not {'data.content', 'data.network'} <= set(by_id):
        raise ValueError('Identity requires the original data.content and data.network rows')
    for owner, source in (('data.content', POLICY), ('data.network', ORIGINAL)):
        row = by_id[owner]
        if len(row['commands']) != 1 or row['commands'][0].get('kind') != 'call' or source not in row['code']:
            raise ValueError('Original content/network identity body differs')
    script = _load(root, ORIGINAL, 'v2_original_network_identity')
    imports = (root / 'platform/studio', root / GAME, root / GAME / 'world')
    scanner = ImportScanner(); code = {BODY, RECIPE, ORIGINAL}
    for path in tuple(code): code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root / path, imports))
    static, known, keys = [], {}, set()
    for unit in native_units:
        if unit['id'] in ('data.network', 'data.content'): continue
        for item in unit['outputs']:
            if not _native(item): continue
            key = unit['id'], item['id']
            if key in keys: raise ValueError('Duplicate finished Native owner')
            keys.add(key); static.append(key)
            for file in item['files']:
                if file['path'].startswith('content/Game/'):
                    known[(unit['id'], item['id'], file['path'])] = CONTENT + file['path'][len('content/Game/'):]
    tokens, captured = [], set()
    for template in geometry.get('templates', []):
        owners = [(None, template)] if 'outputs' in template else []
        owners += [(i, f['unit']) for i, f in enumerate(template.get('followers', []))]
        for follower, unit in owners:
            for item in unit.get('outputs', []):
                if not _native(item): continue
                key = tuple(template[k] for k in ('producer', 'group', 'unit_prefix')) + (follower, item['id'])
                if key in captured: raise ValueError('Duplicate derived finished Native Item')
                captured.add(key)
                descriptor = {k: template[k] for k in ('producer', 'group', 'unit_prefix')}
                descriptor.update(item=item['id'])
                if follower is not None: descriptor['follower'] = follower
                tokens.append({'derived_items': {'root': 'build/v2-derived/identity/native' + str(len(tokens)), 'templates': [descriptor]}})
    if not static and not tokens: raise ValueError('Network identity has no selected finished Native Items')
    references, destinations = [], []
    for ref in data:
        if not isinstance(ref, dict) or set(ref) != {'unit', 'item', 'file', 'path'}:
            raise ValueError('Runtime Data identity requires exact produced ROOT references')
        for value in ref.values(): _relative(value)
        if not ref['path'].startswith(CONTENT + 'Data/'):
            raise ValueError('Runtime identity Data escapes Content/Data')
        if ref['unit'] == 'data.network' or ref['path'] == CONTENT + 'Data/Network' or ref['path'].startswith(CONTENT + 'Data/Network/'):
            continue
        key = ref['unit'], ref['item'], ref['file']
        if key in known:
            if known[key] != ref['path']: raise ValueError('Native Data file has conflicting destinations')
            continue
        if any(ref['path'] == p or ref['path'].startswith(p + '/') or p.startswith(ref['path'] + '/') for p in destinations):
            raise ValueError('Runtime identity Data destinations overlap')
        destinations.append(ref['path']); references.append(deepcopy(ref))
    sources = []
    for path in script.code_files(root):
        if path.resolve() != path or path.is_symlink(): raise ValueError('Native code identity source is aliased')
        sources.append(path.relative_to(root).as_posix())
    if len(sources) != len(set(sources)) or not sources: raise ValueError('Native code identity roster is empty or duplicated')
    def incoming(slot, owner, item):
        return {'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': owner, 'item': item}}
    common_inputs, paths, native_roots, data_roots = [], {}, [], []
    slots = {}
    def item_path(owner, item):
        key = owner, item
        if key not in slots:
            slot = 'item' + str(len(slots)); slots[key] = slot
            common_inputs.append(incoming(slot, owner, item))
        return 'inputs/' + slots[key]
    for i, (owner, item) in enumerate(static):
        logical = 'identity/native/' + str(i); paths[logical] = item_path(owner, item)
        native_roots.append(root / logical)
    for i, ref in enumerate(references):
        logical = 'identity/data/' + str(i); paths[logical] = item_path(ref['unit'], ref['item']) + '/' + ref['file']
        data_roots.append((ref['path'][len(CONTENT):], root / logical))
    units, staged, content_slots = [], {}, {}
    def call(name, defaults):
        function = getattr(_load(root, BODY, 'v2_identity_callback_' + name), name); function.__defaults__ = tuple(defaults)
        row = extract([Step('identity', [Call(name, function)])], checkout=root, build_root=root / 'build', import_roots=imports)[0]
        return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}
    for owner, filename, destination in (('data.content', 'inventory.tree.tar', INVENTORY), ('data.network', 'session.tree.tar', SESSION)):
        network = owner == 'data.network'; unit_paths = dict(paths); inputs = deepcopy(common_inputs)
        defaults = (tuple(native_roots), deepcopy(tokens), tuple(data_roots))
        if network:
            code_roots = []
            for i, path in enumerate(sources):
                slot = 'code' + str(i); inputs.append({'role': 'content', 'name': slot, 'source': {'kind': 'file', 'path': path}})
                unit_paths[path] = 'inputs/' + slot; code_roots.append((path, root / path))
            inputs.append(incoming('inventory', 'data.content', 'inventory'))
            unit_paths['identity/inventory.json'] = 'inputs/inventory/inventory.tree.tar'
            defaults += (tuple(code_roots), root / 'identity/inventory.json')
        defaults += (root / destination,)
        item_id = 'session' if network else 'inventory'
        unit = {'id': owner, 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': sorted(code), 'inputs': inputs,
            'params': {'recipe': {'version': 1, 'paths': unit_paths, 'verify': None,
                'commands': [call('network' if network else 'content', defaults)],
                'outputs': [{'kind': 'tree', 'path': destination, 'file': filename, 'required': True}]}},
            'outputs': [{'id': item_id, 'logical_path': '/Internal/Identity/' + item_id, 'class': 'Data', 'destination': 'store',
                         'files': [{'path': filename, 'required': True}]}]}
        units.append(unit); staged[owner] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        content_slots.update({i['name']: False for i in inputs})
    return {'units': units, 'staged_inputs': staged, 'content_slots': content_slots, 'packages': {},
            'aliases': {'data.content': ('data.content',), 'data.network': ('data.network',)},
            'session': {'unit': 'data.network', 'item': 'session', 'file': 'session.tree.tar', 'path': SESSION},
            'content': {'unit': 'data.content', 'item': 'inventory', 'file': 'inventory.tree.tar', 'path': INVENTORY}}
