"""Declare the original Slice map over finished native island pieces and world data."""
from copy import deepcopy
from pathlib import PurePosixPath

SCRIPT = 'games/yorimichi/world/map_v2.py'
CODE = (SCRIPT, 'games/yorimichi/unreal/Scripts/setup_project.py',
        'games/yorimichi/unreal/Scripts/material_assets.py')
PACKAGE = '/Game/Japan/Maps/Slice'
SIDECARS = ('.uexp', '.ubulk', '.uptnl', '.m.ubulk', '.upayload')


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or '\x00' in value
            or PurePosixPath(value).is_absolute()
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('map input file must be a canonical relative path')
    return value


def _reference(value):
    if (not isinstance(value, dict) or not isinstance(value.get('unit'), str) or not value['unit']
            or not isinstance(value.get('item'), str) or not value['item']):
        raise ValueError('map input requires an explicit completed item owner')
    return {'kind': 'item', 'unit': value['unit'], 'item': value['item']}


def author_units(*, world, terrain, painterly, dependencies=(), checkout=None):
    """@cc [owner:fontanierh,label:correctness] authored-slice-map-inputs
    Slice MUST consume caller-supplied finished native items and the actual keyed
    world JSON item. Dynamic pieces MUST use the normal before-key derived_items
    expansion, never generated Content discovery. The Sea parent MUST remain with
    JapanWorld and MUST NOT become a map dependency. Declaration MUST NOT import
    Unreal, run old main/purge/receiving/cache actions or manufacture native objects.
    """
    del checkout  # Every consumed source is an explicit code member, not a checkout scan.
    inputs = [{'role': 'content', 'name': 'world', 'source': _reference(world)}]
    selection = {'file': _relative(world['file'])}
    if 'member' in world:
        selection['member'] = _relative(world['member']) if world['member'] else ''
    native = {}
    def add(slot, reference):
        source = _reference(reference)
        package = reference.get('package')
        if (not isinstance(package, str) or not package.startswith('/Game/') or '.' in package
                or any(part in ('', '.', '..') for part in package[1:].split('/'))
                or package.startswith(('/Game/AtelierRaw/', '/Game/_Raw/')) or package == PACKAGE):
            raise ValueError('map input requires a finished canonical native package')
        if package in native.values():
            raise ValueError('duplicate map native dependency')
        native[slot] = package
        inputs.append({'role': 'content', 'name': slot, 'source': source})
    add('painterly', painterly)
    for index, reference in enumerate(dependencies):
        add(f'dependency_{index}', reference)
    selected = {}
    for parent, pieces in terrain.items():
        if parent == 'Sea':
            continue
        if not isinstance(parent, str) or not parent or any(c in parent for c in '/\\:\x00'):
            raise ValueError('invalid island terrain parent')
        if isinstance(pieces, dict) and set(pieces) == {'derived_items'}:
            descriptor = pieces['derived_items']
            if set(descriptor) != {'root', 'templates'} or not descriptor['templates']:
                raise ValueError('map requires unresolved native follower descriptors')
            _relative(descriptor['root'])
            for template in descriptor['templates']:
                if (set(template) - {'producer', 'group', 'unit_prefix', 'follower', 'item'}
                        or not {'producer', 'group', 'unit_prefix', 'follower'} <= set(template)
                        or any(not isinstance(template[k], str) or not template[k]
                               for k in ('producer', 'group', 'unit_prefix'))
                        or type(template['follower']) is not int or template['follower'] < 0
                        or ('item' in template and (not isinstance(template['item'], str) or not template['item']))):
                    raise ValueError('map requires exact finished native follower bindings')
            selected[parent] = deepcopy(pieces)
        elif isinstance(pieces, (list, tuple)) and pieces:
            rows = []
            for reference in pieces:
                piece = reference.get('piece')
                if not isinstance(piece, str) or not piece or any(c in piece for c in '/\\:\x00'):
                    raise ValueError('map requires explicit island piece identity')
                slot = f'terrain_{len(native)}'
                add(slot, reference)
                rows.append({'piece': piece, 'slot': slot})
            selected[parent] = rows
        else:
            raise ValueError('map terrain must name finished pieces or their native follower template')
    if not selected:
        raise ValueError('map requires an explicit terrain roster')
    files = [{'path': 'content/Game/Japan/Maps/Slice' + suffix,
              'install_path': 'games/yorimichi/unreal/Content/Japan/Maps/Slice' + suffix,
              'required': suffix == '.umap'} for suffix in ('.umap', *SIDECARS)]
    unit = {'id': 'unreal.island.map', 'op': {'kind': 'unreal.author', 'version': '1'},
            'script': SCRIPT, 'code': list(CODE), 'inputs': inputs,
            'params': {'args': {'package': PACKAGE, 'world': selection, 'native': native,
                                'terrain': selected}, 'settings': []},
            'outputs': [{'id': 'asset', 'logical_path': PACKAGE, 'class': 'Map',
                         'destination': 'checkout', 'files': files}]}
    return {'units': [unit], 'staged_inputs': {unit['id']: {row['name']: 'inputs/' + row['name'] for row in inputs}},
            'content_slots': {row['name']: False for row in inputs},
            'packages': {PACKAGE: {'unit': unit['id'], 'item': 'asset', 'package': PACKAGE}}}
