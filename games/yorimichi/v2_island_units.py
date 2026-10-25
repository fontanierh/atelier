"""Author per-piece island raw-import/finish chains over validated export templates."""
from copy import deepcopy
from pathlib import Path

NATIVE_CLASSES = {'Texture', 'StaticMesh',
                  'Material', 'MaterialInstance', 'MaterialParameterCollection'}
SIDECARS = ('.uasset', '.uexp', '.m.ubulk', '.ubulk', '.uptnl', '.upayload')
FINISH = 'games/yorimichi/world/island_finish_v2.py'


def _item(package, *, raw):
    stem = package.removeprefix('/Game/')
    files = [{'path': 'content/Game/' + stem + suffix, 'required': suffix == '.uasset',
              **({} if raw else {'install_path': 'games/yorimichi/unreal/Content/' + stem + suffix})}
             for suffix in SIDECARS]
    return {'id': 'raw' if raw else 'asset', 'logical_path': package,
            'class': 'RawStaticMesh' if raw else 'StaticMesh',
            'destination': 'store' if raw else 'checkout', 'files': files}


def attach_followers(geometry, packages, native_units, *, checkout):
    """@cc [owner:fontanierh,label:correctness] island-native-piece-chains
    Followers MUST consume their actual expanded export and raw Item identities.
    Finish MUST own only its one original native package and declare every material
    package it loads, including parent/texture dependencies. Generated plan scans,
    old native receipts and source-key guesses MUST NOT author these units.
    """
    import importlib.util
    from atelier.source_imports import ImportScanner
    root = Path(checkout)
    def module(path, name):
        spec = importlib.util.spec_from_file_location(name, root / path)
        result = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(result)
        return result
    policy = module('games/yorimichi/island_atomic_products.py', 'v2_island_products')
    texture = module('games/yorimichi/v2_texture_units.py', 'v2_island_texture_code')
    code = texture._code(root)
    finish_code = sorted(set(code) | {path.relative_to(root).as_posix() for path in
        ImportScanner().local_imports(root / FINISH, (root / 'platform/studio',))})
    by_id = {unit['id']: unit for unit in native_units}
    result = deepcopy(geometry)
    count = 0
    for template in result['templates']:
        if not template['unit_prefix'].startswith('world.island.export.'):
            continue
        parent = template['producer'].rsplit('.', 1)[-1]
        if parent not in policy.PARENTS or template['op']['kind'] != 'blender_export_piece':
            raise ValueError('Island export differs from its authored bounded source family')
        material_paths = policy.material_paths(parent, list(policy.MATERIALS[parent]))
        dependencies = {}
        def add(package):
            reference = packages.get(package)
            if not reference or reference['unit'] not in by_id:
                raise ValueError('Missing authored island native dependency: ' + package)
            key = reference['unit'], reference['item']
            if key in dependencies:
                return dependencies[key]
            slot = 'native' + str(len(dependencies))
            dependencies[key] = slot
            unit = by_id[reference['unit']]
            for incoming in unit['inputs']:
                source = incoming.get('source', {})
                source_unit = by_id.get(source.get('unit'))
                if source.get('kind') != 'item' or source_unit is None:
                    continue
                for output in source_unit['outputs']:
                    if output['id'] == source['item'] and output['class'] in NATIVE_CLASSES:
                        add(output['logical_path'])
            return slot
        mapping = {name: add(package) for name, package in material_paths.items()}
        raw_package = '/Game/_Raw/Island/$piece'
        destination = policy.DESTINATION + '/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'},
            'script': texture.OPS, 'code': code,
            'inputs': [{'role': 'content', 'name': 'source',
                        'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
            'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source',
                       'destination': raw_package,
                       'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=0,Editor.AsyncStaticMeshCompilation=0']},
            'outputs': [_item(raw_package, raw=True)]}
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'},
            'script': FINISH, 'code': finish_code,
            'inputs': [{'role': 'content', 'name': 'raw',
                        'source': {'kind': 'item', 'unit': '$previous', 'item': 'raw'}},
                       {'role': 'content', 'name': 'source_export',
                        'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}},
                       *({'role': 'content', 'name': slot,
                          'source': {'kind': 'item', 'unit': owner, 'item': item}}
                         for (owner, item), slot in dependencies.items())],
            'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw',
                       'destination': destination, 'package_sources': {'raw': raw_package},
                       'args': {'source_export': 'source_export', 'materials': mapping},
                       'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
            'outputs': [_item(destination, raw=False)]}
        template['followers'] = [
            {'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
            {'unit': finish, 'staged_inputs': {item['name']: 'inputs/' + item['name']
                                              for item in finish['inputs']}}]
        count += 1
    if count != len(policy.PARENTS):
        raise ValueError('Island source family lacks one of its seven authored parents')
    return result
