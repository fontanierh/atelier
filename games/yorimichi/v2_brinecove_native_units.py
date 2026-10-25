"""Per-piece Brinecove native owners over the actual declared export family."""
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import re

FINISH = 'games/yorimichi/world/brinecove_finish_v2.py'
MATERIALS = '/Game/Brinecove/Materials/'


def _load(root, path, name):
    spec = importlib.util.spec_from_file_location(name, root / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def material_packages(checkout):
    """Only the original committed palette table, never generated report discovery."""
    source = Path(checkout) / 'games/yorimichi/world/regions/brinecove/layout.py'
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == 'COLORS' for n in node.targets):
            colors = ast.literal_eval(node.value)
            if not isinstance(colors, dict) or any(not isinstance(name, str) or not re.fullmatch('[A-Za-z0-9_]+', name) for name in colors):
                raise ValueError('Invalid original Brinecove material catalogue')
            return sorted(MATERIALS + 'MI_BC_' + name for name in {*colors, 'terrain'})
    raise ValueError('Missing original Brinecove material catalogue')


def attach_followers(geometry, packages, native_units, *, checkout):
    """@cc [owner:fontanierh,label:correctness] brinecove-selected-native-followers
    Every Brinecove child MUST consume its actual export/raw Items and exact selected
    payload. Material owners MUST be explicit, including transitive native inputs.
    Missing palette/hero/policy roles MUST refuse or remain explicit; no default
    material, generated Content scan, old main/cache/report or native receipt reuse.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    island = _load(root, 'games/yorimichi/v2_island_units.py', 'brinecove_item_policy')
    texture = _load(root, 'games/yorimichi/v2_texture_units.py', 'brinecove_raw_policy')
    raw_code = texture._code(root)
    finish_code = set(raw_code)
    for helper in (FINISH, 'games/yorimichi/unreal/Scripts/import_brinecove.py'):
        if helper.endswith('/import_brinecove.py'):
            # Its function AST is read, never execute/import its unguarded main.
            finish_code.add(helper)
        else:
            finish_code.update(path.relative_to(root).as_posix() for path in ImportScanner().local_imports(
                root / helper, (root / 'platform/studio', root / 'games/yorimichi/world', root / 'games/yorimichi/unreal/Scripts')))
    by_id = {unit['id']: unit for unit in native_units}
    required = set(material_packages(root))
    required.update(package for package in packages if package.startswith(MATERIALS + 'MI_BC_'))
    missing = sorted(required - set(packages))
    result = deepcopy(geometry)
    for template in result['templates']:
        if not template['unit_prefix'].startswith('world.brinecove.export.'):
            continue
        if (template['producer'] != 'world.brinecove' and not template['producer'].startswith('world.brinecove.geometry.')):
            raise ValueError('Foreign Brinecove source producer')
        op = template['op']
        if op not in ({'kind': 'blender_export_piece', 'version': '1'}, {'kind': 'encoded_export_piece', 'version': '1'}):
            raise ValueError('Unsupported Brinecove selected export body')
        if op['kind'] == 'blender_export_piece' and template['params'].get('format') != 'glb':
            raise ValueError('Brinecove raw import requires original geometry-only GLB')
        if missing:
            continue
        dependencies = {}
        def add(package):
            ref = packages.get(package)
            if not ref or ref.get('unit') not in by_id:
                raise ValueError('Missing declared Brinecove native owner: ' + package)
            key = ref['unit'], ref['item']
            if key in dependencies:
                return dependencies[key]
            owner = by_id[key[0]]
            if not any(item['id'] == key[1] and item['logical_path'] == package and item['class'] in island.NATIVE_CLASSES for item in owner['outputs']):
                raise ValueError('Brinecove native reference differs from actual Item')
            slot = 'native' + str(len(dependencies)); dependencies[key] = slot
            for incoming in owner['inputs']:
                source = incoming.get('source', {})
                if source.get('kind') == 'item' and source.get('unit') in by_id:
                    for item in by_id[source['unit']]['outputs']:
                        if item['id'] == source['item'] and item['class'] in island.NATIVE_CLASSES:
                            add(item['logical_path'])
            return slot
        mapping = {package.removeprefix(MATERIALS + 'MI_BC_'): add(package) for package in sorted(required)}
        raw_package, destination = '/Game/_Raw/Brinecove/$piece', '/Game/Brinecove/Meshes/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'},
            'script': texture.OPS, 'code': raw_code,
            'inputs': [{'role': 'content', 'name': 'source', 'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
            'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package},
            'outputs': [island._item(raw_package, raw=True)]}
        inputs = [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': '$previous', 'item': 'raw'}},
                  {'role': 'content', 'name': 'source_export', 'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}},
                  {'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member', 'unit': template['producer'], 'group': template['group'], 'piece': '$piece'}},
                  *({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': owner, 'item': item}}
                    for (owner, item), slot in dependencies.items())]
        args = {'materials': mapping, 'source_export': 'source_export', 'payload': 'payload'}
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH,
            'code': sorted(finish_code), 'inputs': inputs,
            'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': destination,
                       'package_sources': {'raw': raw_package}, 'args': args},
            'outputs': [island._item(destination, raw=False)]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
            {'unit': finish, 'staged_inputs': {row['name']: 'inputs/' + row['name'] for row in inputs}}]
    return {'geometry': result, 'units': [], 'staged_inputs': {}, 'content_slots': {}, 'packages': {},
            'aliases': {}, 'missing_material_packages': missing}
