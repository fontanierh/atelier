"""Village per-piece native followers over actual D2 plans and the assembled manifest Item."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

FINISH = 'games/yorimichi/world/village_finish_v2.py'
MATERIAL = '/Game/Japan/Materials/M_Village'
DESTINATION = '/Game/Experiments/VillageAtomic/v1_atomic'


def _load(root, relative, name):
    spec = importlib.util.spec_from_file_location(name, root / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def attach_followers(geometry, natives, *, checkout):
    """@cc [owner:fontanierh,label:correctness] original-village-native-followers
    All twelve original Village D2 parents MUST receive independent per-piece raw
    and finish owners. Finish MUST consume the actual assembled manifest Item,
    selected source payload/export and supplied M_Village including its declared
    native dependency closure. Neither generated membership nor fallback materials
    MAY be discovered. Ground/native hull policies MUST remain original.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    catalogue = _load(root, 'games/yorimichi/world/regions/village/catalogue.py', 'v2_village_catalogue')
    factory = _load(root, 'games/yorimichi/village_atomic_build.py', 'v2_village_original_build')
    texture = _load(root, 'games/yorimichi/v2_texture_units.py', 'v2_village_texture')
    island = _load(root, 'games/yorimichi/v2_island_units.py', 'v2_village_items')
    declared = [step for step in factory.steps(SimpleNamespace(out=root / 'build/yorimichi')) if step.name == 'world.village']
    if len(declared) != 1:
        raise ValueError('Village assembled manifest owner is ambiguous')
    products = [(i, p) for i, p in enumerate(declared[0].products) if p.name == 'village.meshes']
    if len(products) != 1 or len(products[0][1].paths) != 1 or products[0][1].optional_paths:
        raise ValueError('Village manifest must be its actual singleton required product')
    index, product = products[0]
    if product.paths[0].name != 'atomic-manifest.json':
        raise ValueError('Village manifest source declaration differs')
    manifest = {'unit': declared[0].name, 'item': 'product' + str(index)}
    binding = {'archive_member': f'products/{index}-0.tree.tar', 'name': product.paths[0].name}
    if MATERIAL not in natives:
        raise ValueError('Missing exact supplied Village native material: ' + MATERIAL)
    dependencies = {}
    def dependency(ref):
        if (not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ('unit', 'item', 'package'))
                or not ref['package'].startswith('/Game/')):
            raise ValueError('Village material dependency must name its actual finished native Item')
        key = ref['unit'], ref['item']
        if key in dependencies:
            if dependencies[key][1]['package'] != ref['package']:
                raise ValueError('Village material Item aliases distinct native packages')
            return dependencies[key][0]
        slot = 'native' + str(len(dependencies)); dependencies[key] = slot, ref
        for child in ref.get('dependencies', ()):
            if isinstance(child, str):
                if child not in natives: raise ValueError('Missing supplied Village transitive material input: ' + child)
                child = natives[child]
            dependency(child)
        return slot
    material = natives[MATERIAL]
    if not isinstance(material, dict) or material.get('package') != MATERIAL:
        raise ValueError('Village material ref must match its exact original package')
    material_slot = dependency(material)
    code = set(texture._code(root))
    scanner = ImportScanner()
    for source in (FINISH, 'games/yorimichi/village_atomic_products.py', 'games/yorimichi/city_tile_products.py'):
        code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root / source,
            (root / 'platform/studio', root / 'games/yorimichi', root / 'games/yorimichi/world', root / 'games/yorimichi/world/regions')))
    descriptor = json.loads((root / 'games/yorimichi/unreal/Yorimichi.uproject').read_text())
    modules = [{'name': m['Name'], 'kind': m['Type'], 'loading_phase': m.get('LoadingPhase', 'Default')} for m in descriptor['Modules']]
    result = deepcopy(geometry); seen = set(); requirements = dict(result.get('module_requirements', {}))
    for template in result['templates']:
        if not template['unit_prefix'].startswith('world.village.export.'):
            continue
        parent = template['unit_prefix'].removeprefix('world.village.export.')
        if (parent not in catalogue.ASSETS or parent in seen or template['producer'] != 'world.village.geometry.' + parent
                or template['group'] != 'geometry' or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                or template['params'].get('format') != 'fbx' or template.get('followers')):
            raise ValueError('Village native followers require every original FBX D2 parent exactly once')
        seen.add(parent)
        raw_package = '/Game/_Raw/Village/$piece'
        destination = DESTINATION + '/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': texture.OPS,
               'code': texture._code(root), 'inputs': [{'role': 'content', 'name': 'source',
                   'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
               'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                   'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']},
               'outputs': [island._item(raw_package, raw=True)]}
        inputs = [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': '$previous', 'item': 'raw'}},
                  {'role': 'content', 'name': 'source_export', 'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}},
                  {'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member', 'unit': template['producer'], 'group': 'geometry', 'piece': '$piece'}},
                  {'role': 'content', 'name': 'manifest', 'source': {'kind': 'item', **manifest}},
                  *({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}}
                    for slot, ref in dependencies.values())]
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH,
                  'code': sorted(code), 'inputs': inputs,
                  'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': destination,
                    'package_sources': {'raw': raw_package}, 'input_roots': {'manifest': binding},
                    'args': {'parent': parent, 'payload': 'payload', 'source_export': 'source_export', 'manifest': 'manifest',
                             'material': material_slot, 'native_inputs': {slot: ref['package'] for slot, ref in dependencies.values()}},
                    'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
                  'outputs': [island._item(destination, raw=False)]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
                                 {'unit': finish, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in inputs}}]
        requirements[template['unit_prefix']] = modules
    if seen != set(catalogue.ASSETS):
        raise ValueError('Village native followers require the complete twelve-parent family')
    result['module_requirements'] = requirements
    return result
