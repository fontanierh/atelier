"""Independent original Zeppelin materials and ten independent native followers."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

FINISH = 'games/yorimichi/world/zeppelin_finish_v2.py'
FABRIC = '/Game/Japan/Materials/M_ZeppelinFabric'
MATERIAL_SOURCE = 'games/yorimichi/unreal/Scripts/import_zeppelin.py'
MATERIAL = '/Game/Japan/Materials/M_Village'


def _load(root, path, name):
    spec = importlib.util.spec_from_file_location(name, root / path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def attach_followers(geometry, natives, *, checkout):
    """@cc [owner:fontanierh,label:correctness] zeppelin-current-native-followers
    All ten actual Zeppelin D2 parents MUST have independent selected export and
    payload owners. Fabric MUST execute only the keyed original fabric_material
    definition; importer top-level, cache and namespace operations MUST NOT run.
    Airship fabric slots MUST bind M_ZeppelinFabric, others supplied M_Village.
    Original complex collision policy and native save checks MUST remain required.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    factory = _load(root, 'games/yorimichi/world/regions/zeppelin/atomic.py', 'zeppelin_original_factory')
    texture = _load(root, 'games/yorimichi/v2_texture_units.py', 'zeppelin_texture_policy')
    island = _load(root, 'games/yorimichi/v2_island_units.py', 'zeppelin_item_policy')
    parents = tuple(name for name, _ in factory.LOGICAL)
    material = natives.get(MATERIAL)
    if not isinstance(material, dict) or material.get('package') != MATERIAL:
        raise ValueError('Missing exact supplied Zeppelin native material: ' + MATERIAL)
    dependencies = {}
    def add(ref):
        if (not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ('unit', 'item', 'package'))
                or not ref['package'].startswith('/Game/')):
            raise ValueError('Zeppelin native dependencies require actual finished Item refs')
        key = ref['unit'], ref['item']
        if key in dependencies:
            if dependencies[key][1]['package'] != ref['package']: raise ValueError('Zeppelin native Item aliases packages')
            return dependencies[key][0]
        slot = 'native' + str(len(dependencies)); dependencies[key] = slot, ref
        for child in ref.get('dependencies', ()):
            if isinstance(child, str):
                if child not in natives: raise ValueError('Missing Zeppelin transitive native material input: ' + child)
                child = natives[child]
            add(child)
        return slot
    material_slot = add(material)
    code = set(texture._code(root))
    code.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(root / FINISH,
        (root / 'platform/studio', root / 'games/yorimichi', root / 'games/yorimichi/world')))
    for relative in code:
        if (root / relative).is_symlink() or not (root / relative).is_file():
            raise ValueError('Zeppelin keyed source is missing or linked: ' + relative)
    descriptor = json.loads((root / 'games/yorimichi/unreal/Yorimichi.uproject').read_text())
    modules = [{'name': m['Name'], 'kind': m['Type'], 'loading_phase': m.get('LoadingPhase', 'Default')} for m in descriptor['Modules']]
    result = deepcopy(geometry); requirements = dict(result.get('module_requirements', {})); seen = set()
    unit_id = 'unreal.zeppelin.material.M_ZeppelinFabric'
    output = island._item(FABRIC, raw=False); output['class'] = 'Material'
    unit = {'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': FINISH,
        'code': sorted(code | {MATERIAL_SOURCE}), 'inputs': [],
        'params': {'args': {'op': 'fabric'}, 'settings': []}, 'outputs': [output]}
    result.setdefault('units', []).append(unit); result.setdefault('staged_inputs', {})[unit_id] = {}
    fabric_ref = {'unit': unit_id, 'item': 'asset', 'package': FABRIC}
    result.setdefault('packages', {})[FABRIC] = fabric_ref
    result.setdefault('content_slots', {})
    for template in result['templates']:
        if not template['unit_prefix'].startswith('world.zeppelin.export.'): continue
        parent = template['unit_prefix'].removeprefix('world.zeppelin.export.')
        if (parent not in parents or parent in seen or template['producer'] != 'world.zeppelin.geometry.' + parent
                or template['group'] != 'geometry' or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                or template['params'].get('format') != 'fbx' or template.get('followers')):
            raise ValueError('Zeppelin followers require each original FBX D2 parent exactly once')
        seen.add(parent); raw_package = '/Game/_Raw/Zeppelin/$piece'; destination = '/Game/Japan/Assets/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': texture.OPS,
               'code': texture._code(root), 'inputs': [{'role': 'content', 'name': 'source',
                   'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
               'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                          'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']},
               'outputs': [island._item(raw_package, raw=True)]}
        selected_dependencies = {slot: ref for slot, ref in dependencies.values()}
        fabric_slot = None
        if parent == 'ZP_Airship':
            fabric_slot = 'fabric'; selected_dependencies[fabric_slot] = fabric_ref
        inputs = [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': '$previous', 'item': 'raw'}},
                  {'role': 'content', 'name': 'source_export', 'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}},
                  {'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member', 'unit': template['producer'], 'group': 'geometry', 'piece': '$piece'}},
                  *({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}}
                    for slot, ref in selected_dependencies.items())]
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH,
                  'code': sorted(code), 'inputs': inputs,
                  'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': destination,
                      'package_sources': {'raw': raw_package}, 'args': {'parent': parent, 'source_export': 'source_export', 'payload': 'payload',
                          'material': material_slot, 'fabric': fabric_slot, 'native_inputs': {slot: ref['package'] for slot, ref in selected_dependencies.items()}},
                      'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
                  'outputs': [island._item(destination, raw=False)]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
                                 {'unit': finish, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in inputs}}]
        requirements[template['unit_prefix']] = modules
    if seen != set(parents): raise ValueError('Zeppelin native followers require the complete ten-parent family')
    result['module_requirements'] = requirements
    return result
