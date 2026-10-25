"""Author C3 foliage RawImport units for every fixed source LOD export of the 18 owners.

The static LOD roster comes from each owner's committed spec through the original
``foliage_source_products.definition_rows`` (mesh levels and the far crown; the seed
export is only an import slot template). Each raw import consumes its exact
``world.foliage.export.<key>`` Item (one FBX plus its public export receipt) and stays
store-only. The original raw FBX options equal ``Scripts/mesh_import.py``.

Finishing is not authored here: see ``FINISH_SEAM``.
"""
import importlib.util
import json
from pathlib import Path

from v2_texture_units import OPS, SIDECARS, Unsupported, _code

EXPORTS = 'build/yorimichi/exports/world.foliage.export'
FINISH_SEAM = (
    'The final /Game/Japan/Assets/<owner> mesh assembles its LOD chain from the finished '
    '/Game/Japan/FoliageLODs/<owner>/<owner>_LODn sources (set_lod_from_static_mesh, '
    'set_lod_screen_sizes), sets body_setup collision_trace_flag, clears or keeps UCX hulls '
    'and validates triangles/bounds (import_foliage.py, import_foliage_lods.apply_lods). '
    'unreal.finish(static_mesh) supports only duplicate + mesh properties, ordered '
    'materials and lod_build_settings; unreal.author admits only Material, '
    'MaterialInstance, MaterialParameterCollection and Map, one package each. A C3 '
    'StaticMesh LOD-assembly finish (or StaticMesh in unreal.author with LOD-source and '
    'material native inputs) is required before any final foliage package is runnable.')


def _module(name, path):
    spec = importlib.util.spec_from_file_location('v2_foliage_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def roster(checkout):
    """{owner: [(key, level)]}: every fixed mesh LOD and far crown from committed specs."""
    import sys
    world = str(Path(checkout) / 'games/yorimichi/world')
    sys.path.insert(0, world)
    try:
        catalog = _module('catalog', Path(world) / 'asset_catalog.py')
        materials = _module('materials', Path(world) / 'material_specs.py')
        products = _module('products', Path(checkout) / 'games/yorimichi/foliage_source_products.py')
    finally:
        sys.path.remove(world)
    result = {}
    for owner in catalog.FOLIAGE:
        spec = json.loads((catalog.SPEC_ROOT / (owner + '.json')).read_text())
        rows, policy = products.definition_rows(owner, spec, materials.MATERIALS)
        chain = policy['levels']
        if (len(chain) != len(policy['screen_sizes']) or policy['keys'] != chain + [owner + '_Seed']
                or [rows[key]['mode'] for key in chain] != ['mesh'] * len(spec['screen_sizes'])
                + ['crown'] * policy['crown']):
            raise Unsupported(f'{owner}: unexpected foliage source rows')
        result[owner] = [(key, level) for level, key in enumerate(chain)]
    return result


def _output(package):
    stem = package.removeprefix('/Game/')
    return {'id': 'raw_static_mesh', 'logical_path': package, 'class': 'RawStaticMesh', 'destination': 'store',
            'files': [{'path': 'content/Game/' + stem + suffix, 'required': suffix == '.uasset'} for suffix in SIDECARS]}


def foliage_units(rows, *, checkout):
    """@cc [owner:fontanierh,label:correctness] authored-c3-foliage-raw-units
    Every fixed mesh LOD and far crown of every foliage owner MUST become one
    independent store-only RawImport consuming its exact export Item, with the
    original FBX options and no finish properties. The roster MUST come from committed
    source specs, never a generated-folder scan; a missing or reshaped export row
    refuses. Final packages are not claimed: FINISH_SEAM names the missing operation.
    """
    exports = {row['id']: row for row in rows if row['id'].startswith('world.foliage.export.')}
    owners = roster(checkout)
    code = _code(checkout)
    units, staged, slots, packages = [], {}, {}, {}
    for owner, chain in owners.items():
        for key, level in chain:
            row = exports.get('world.foliage.export.' + key)
            if row is None:
                raise Unsupported(f'{owner}: missing export row for {key}')
            products = row['products']
            if (len(products) != 1 or products[0]['id'] != row['id'] or products[0]['optional_paths']
                    or products[0]['paths'] != [f'{EXPORTS}/{key}']):
                raise Unsupported(f'{key}: export must own exactly its single folder ROOT')
            commands = row['commands']
            if (len(commands) != 1 or commands[0].get('kind') != 'blender'
                    or commands[0].get('script') != {'path': 'games/yorimichi/world/export_foliage_piece.py'}
                    or commands[0].get('args', [])[-2:] != ['--format', '.fbx']):
                raise Unsupported(f'{key}: export command differs from the original declared body')
            unit_id = 'unreal.foliage.raw.' + key
            package = f'/Game/_Raw/Foliage/{owner}/{key}'
            units.append({'id': unit_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS,
                          'code': list(code),
                          'inputs': [{'role': 'content', 'name': 'source',
                                      'source': {'kind': 'item', 'unit': row['id'], 'item': 'product0'}}],
                          'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source',
                                     'destination': package,
                                     'input_roots': {'source': {'archive_member': 'products/0-0.tree.tar',
                                                                'name': key}}},
                          'outputs': [_output(package)]})
            staged[unit_id] = {'source': 'inputs/source'}
            slots['source'] = False
            packages[package] = {'unit': unit_id, 'item': 'raw_static_mesh', 'owner': owner, 'key': key,
                                 'level': level}
    return {'units': units, 'staged': staged, 'slots': slots, 'packages': packages, 'finish_seam': FINISH_SEAM}
