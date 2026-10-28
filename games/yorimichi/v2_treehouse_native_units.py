"""Finite Treehouse raw/finish chains over authored, selected MeshIR exports."""
import ast
from copy import deepcopy
from pathlib import Path

FINISH = 'games/yorimichi/world/treehouse_finish_v2.py'
TREES = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')
PROPS = tuple('TH_P_' + slug for slug in ('backpack', 'barrel', 'basket', 'bell', 'bookshelf',
    'crate_desk', 'futon', 'globe', 'kamado', 'log_table', 'planter', 'stump_kettle', 'telescope'))
SURFACES = ('TH_Structure', 'TH_Frame', 'TH_Trunks', 'TH_Dressing')
MATERIALS = '/Game/Japan/Treehouse/Materials/'


def _load(root, path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, root / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _palette(root):
    """Read only the original finite source tables, without importing its paid tool."""
    tree = ast.parse((root / 'games/yorimichi/tools/treehouse_textures.py').read_text())
    tables = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in ('SURFACES', 'PICTURES'):
                tables[key] = ast.literal_eval(node.value)
    if set(tables) != {'SURFACES', 'PICTURES'}:
        raise ValueError('Treehouse original palette tables are missing')
    return sorted(set(tables['SURFACES']) | set(tables['PICTURES']) | {'rope', 'pane'})


def attach_followers(geometry, packages, native_units, *, checkout):
    """@cc [owner:fontanierh,label:correctness] treehouse-current-native-followers
    Every Treehouse piece MUST use its own selected export, MeshIR member and raw
    native Item. Preserve original destinations/material roles/UV/collision policy.
    Missing original palette owners MUST be explicit unresolved roles, never fake
    IDs, generic materials, ambient native assets or old receiving/cache actions.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    island = _load(root, 'games/yorimichi/v2_island_units.py', 'treehouse_island_item')
    texture = _load(root, 'games/yorimichi/v2_texture_units.py', 'treehouse_raw_code')
    raw_code = texture._code(root)
    scanner = ImportScanner()
    finish_code = set(raw_code)
    for script in (FINISH, 'games/yorimichi/unreal/Scripts/forest_native.py'):
        finish_code.update(path.relative_to(root).as_posix() for path in scanner.local_imports(
            root / script, (root / 'platform/studio', root / 'games/yorimichi/world',
                            root / 'games/yorimichi/unreal/Scripts')))
    by_id = {unit['id']: unit for unit in native_units}
    result = deepcopy(geometry)
    missing, selected = set(), set()
    roles = {}
    for template in result['templates']:
        prefix = template['unit_prefix']
        if not prefix.startswith(('world.treehouse_trees.export.', 'world.treehouse_props.export.',
                                  'world.treehouse_surfaces.export.')):
            continue
        parent = prefix.rsplit('.', 1)[-1]
        family = 'trees' if parent in TREES else 'props' if parent in PROPS else 'surfaces' if parent in SURFACES else None
        if (family is None or prefix != f'world.treehouse_{family}.export.{parent}'
                or template['producer'] != f'world.treehouse_{family}.geometry.{parent}'
                or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                or template['params']['format'] != 'fbx' or parent in selected):
            raise ValueError('Treehouse template differs from its finite original source family')
        selected.add(parent)
        if family == 'trees':
            leaf = parent.removeprefix('Tree_Canopy_')
            material_paths = {'Bark': '/Game/Japan/Materials/MI_Bark',
                              'Leaf' + leaf: '/Game/Japan/Materials/MI_Leaf' + leaf}
        elif family == 'props':
            material_paths = {'__prop__': MATERIALS + 'MI_' + parent}
        else:
            material_paths = {'TH_' + slot: MATERIALS + 'MI_TH_' + slot for slot in _palette(root)}
            if parent == 'TH_Trunks':
                material_paths['TH_bark'] = MATERIALS + 'MI_TH_trunk'
        required_missing = {package for package in material_paths.values() if package not in packages}
        missing.update(required_missing)
        roles[parent] = dict(material_paths)
        if required_missing:
            continue
        dependencies = {}
        def add(package):
            reference = packages.get(package)
            if not reference or reference.get('unit') not in by_id:
                raise ValueError('Treehouse dependency lacks its declared native owner: ' + package)
            key = reference['unit'], reference['item']
            if key in dependencies:
                return dependencies[key]
            owner = by_id[key[0]]
            if not any(item['id'] == key[1] and item['logical_path'] == package
                       and item['class'] in island.NATIVE_CLASSES for item in owner['outputs']):
                raise ValueError('Treehouse material reference differs from its actual native Item')
            slot = 'native' + str(len(dependencies))
            dependencies[key] = slot
            for incoming in owner['inputs']:
                source = incoming.get('source', {})
                source_unit = by_id.get(source.get('unit'))
                if source.get('kind') == 'item' and source_unit:
                    for output in source_unit['outputs']:
                        if output['id'] == source['item'] and output['class'] in island.NATIVE_CLASSES:
                            add(output['logical_path'])
            return slot
        mapping = {slot: add(package) for slot, package in material_paths.items()}
        folder = ('/Game/Japan/Treehouse/StructurePieces' if parent == 'TH_Structure' else
                  '/Game/Japan/Treehouse/Pieces' if parent == 'TH_Dressing' else '/Game/Japan/Assets')
        raw_package = '/Game/_Raw/Treehouse/$piece'
        destination = folder + '/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'},
            'script': texture.OPS, 'code': raw_code,
            'inputs': [{'role': 'content', 'name': 'source', 'source': {
                'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
            'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source',
                       'destination': raw_package,
                       'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']},
            'outputs': [island._item(raw_package, raw=True)]}
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'},
            'script': FINISH, 'code': sorted(finish_code),
            'inputs': [{'role': 'content', 'name': 'raw', 'source': {
                'kind': 'item', 'unit': '$previous', 'item': 'raw'}},
                {'role': 'content', 'name': 'source_export', 'source': {
                    'kind': 'item', 'unit': '$export', 'item': 'asset'}},
                {'role': 'content', 'name': 'payload', 'source': {
                    'kind': 'group_member', 'unit': template['producer'], 'group': template['group'], 'piece': '$piece'}},
                *({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': owner, 'item': item}}
                  for (owner, item), slot in dependencies.items())],
            'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': destination,
                       'package_sources': {'raw': raw_package},
                       'args': {'parent': parent, 'source_export': 'source_export', 'payload': 'payload',
                                'materials': mapping}, 'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
            'outputs': [island._item(destination, raw=False)]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
            {'unit': finish, 'staged_inputs': {row['name']: 'inputs/' + row['name'] for row in finish['inputs']}}]
    return {'geometry': result, 'units': [], 'staged_inputs': {}, 'content_slots': {},
            'packages': {}, 'aliases': {}, 'missing_material_packages': sorted(missing),
            'material_roles': roles, 'unrepresented_parents': sorted(set((*TREES, *PROPS, *SURFACES)) - selected)}
