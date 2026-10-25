"""Five Lake D2 native families and the original independent water material author."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

FINISH = 'games/yorimichi/world/lake_finish_v2.py'
CALL = 'games/yorimichi/world/native_author_call_v2.py'
WATER_SOURCE = 'games/yorimichi/unreal/Scripts/forest_lake_material.py'
WATER = '/Game/Japan/Materials/M_ForestLakeWater'
VILLAGE = '/Game/Japan/Materials/M_Village'
WATER_UNIT = 'unreal.lake.material.M_ForestLakeWater'


def _load(root, path, name):
    spec = importlib.util.spec_from_file_location(name, root / path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def attach_followers(geometry, natives, *, checkout):
    """@cc [owner:fontanierh,label:correctness] original-lake-piece-owners
    All five original Lake FBX D2 parents MUST receive independent raw and finish
    followers over their exact selected payload and export Items. Only Lake_Water
    MUST bind the original create() water material; other parents MUST consume the
    supplied M_Village with its native dependency closure. No generated membership,
    namespace inventory, original importer main or retirement MAY execute.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    factory = _load(root, 'games/yorimichi/lake_atomic_build.py', 'lake_original_factory')
    texture = _load(root, 'games/yorimichi/v2_texture_units.py', 'lake_texture_policy')
    island = _load(root, 'games/yorimichi/v2_island_units.py', 'lake_item_policy')
    if VILLAGE not in natives or not isinstance(natives[VILLAGE], dict) or natives[VILLAGE].get('package') != VILLAGE:
        raise ValueError('Missing exact supplied Lake native material: ' + VILLAGE)
    scanner = ImportScanner()
    def code_for(path):
        return set(texture._code(root)) | {p.relative_to(root).as_posix() for p in scanner.local_imports(root / path,
            (root / 'platform/studio', root / 'games/yorimichi', root / 'games/yorimichi/world', root / 'games/yorimichi/unreal/Scripts'))}
    water_code = sorted(code_for(CALL) | code_for(WATER_SOURCE))
    output = island._item(WATER, raw=False); output['class'] = 'Material'
    water = {'id': WATER_UNIT, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': CALL,
             'code': water_code, 'inputs': [], 'params': {'args': {'module': WATER_SOURCE, 'function': 'create',
                 'arguments': [], 'keyword_arguments': {}, 'expected_package': WATER}, 'settings': []}, 'outputs': [output]}
    result = deepcopy(geometry)
    result.setdefault('units', []).append(water)
    result.setdefault('staged_inputs', {})[WATER_UNIT] = {}
    result.setdefault('content_slots', {})
    water_ref = {'unit': WATER_UNIT, 'item': 'asset', 'package': WATER}
    result.setdefault('packages', {})[WATER] = water_ref
    requirements = dict(result.get('module_requirements', {}))
    descriptor = json.loads((root / 'games/yorimichi/unreal/Yorimichi.uproject').read_text())
    modules = [{'name': m['Name'], 'kind': m['Type'], 'loading_phase': m.get('LoadingPhase', 'Default')} for m in descriptor['Modules']]
    finish_code = sorted(code_for(FINISH)); seen = set()
    for template in result['templates']:
        if not template['unit_prefix'].startswith('world.lake.export.'):
            continue
        parent = template['unit_prefix'].removeprefix('world.lake.export.')
        if (parent not in factory.OWNERS or parent in seen or template['producer'] != 'world.lake.geometry.' + parent
                or template['group'] != 'geometry' or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                or template['params'].get('format') != 'fbx' or template.get('followers')):
            raise ValueError('Lake followers require every original FBX D2 parent exactly once')
        seen.add(parent); dependencies = {}
        def add(ref):
            if (not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ('unit', 'item', 'package'))
                    or not ref['package'].startswith('/Game/')):
                raise ValueError('Lake material dependencies require actual finished native Item refs')
            key = ref['unit'], ref['item']
            if key in dependencies:
                if dependencies[key][1]['package'] != ref['package']:
                    raise ValueError('Lake native Item aliases distinct packages')
                return dependencies[key][0]
            slot = 'native' + str(len(dependencies)); dependencies[key] = slot, ref
            for child in ref.get('dependencies', ()):
                if isinstance(child, str):
                    if child not in natives: raise ValueError('Missing Lake transitive material dependency: ' + child)
                    child = natives[child]
                add(child)
            return slot
        material_slot = add(water_ref if parent == 'Lake_Water' else natives[VILLAGE])
        raw_package = '/Game/_Raw/Lake/$piece'; destination = '/Game/Japan/Lake/Pieces/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': texture.OPS,
               'code': texture._code(root), 'inputs': [{'role': 'content', 'name': 'source',
                   'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
               'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                          'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=0,Editor.AsyncStaticMeshCompilation=0']},
               'outputs': [island._item(raw_package, raw=True)]}
        inputs = [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': '$previous', 'item': 'raw'}},
                  {'role': 'content', 'name': 'source_export', 'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}},
                  {'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member', 'unit': template['producer'], 'group': 'geometry', 'piece': '$piece'}},
                  *({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}}
                    for slot, ref in dependencies.values())]
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH,
                  'code': finish_code, 'inputs': inputs,
                  'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': destination,
                      'package_sources': {'raw': raw_package}, 'args': {'parent': parent, 'source_export': 'source_export', 'payload': 'payload',
                          'material': material_slot, 'native_inputs': {slot: ref['package'] for slot, ref in dependencies.values()}},
                      'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
                  'outputs': [island._item(destination, raw=False)]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
                                 {'unit': finish, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in inputs}}]
        requirements[template['unit_prefix']] = modules
    if seen != set(factory.OWNERS):
        raise ValueError('Lake native followers require the complete five-parent family')
    result['module_requirements'] = requirements
    return result
