"""Mini-mega per-piece native followers over the actual mega D2 export children.

Scripts/import_mega.py imports mega_build's three exports (Mega_Ramp, Mega_Trim, Mega_Trail) into
/Game/Japan/Assets with M_Village on slot 0. The ramp and trail collide with their render mesh (complex as
simple); the trim is look only (simple as complex, no physics shapes). Each original parent's existing export
template gains a raw import and a finish that consumes its own export and MeshIR payload plus the supplied
M_Village closure.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

FINISH = 'games/yorimichi/world/mega_finish_v2.py'
PARENTS = ('Mega_Ramp', 'Mega_Trim', 'Mega_Trail')
DESTINATION = '/Game/Japan/Assets'
RAW = '/Game/_Raw/Mega'
MATERIAL = '/Game/Japan/Materials/M_Village'
# mesh_import.import_mesh's legacy FBX static-mesh options, which import_mega.py uses through import_village.
FBX = {'combine_meshes': True, 'generate_lightmap_u_vs': False, 'auto_generate_collision': False,
       'convert_scene': True, 'convert_scene_unit': True, 'import_uniform_scale': 1.0, 'build_nanite': False,
       'one_convex_hull_per_ucx': True,
       'vertex_color_import_option': {'unreal_enum': 'VertexColorImportOption.REPLACE'},
       'normal_import_method': {'unreal_enum': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS'}}


def _load(root, relative, name):
    spec = importlib.util.spec_from_file_location(name, root / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def attach_followers(geometry, natives, *, checkout):
    """@cc [owner:fontanierh,label:correctness] original-mega-native-followers
    All three original mega D2 parents MUST receive independent per-piece raw and
    finish owners at their original /Game/Japan/Assets packages. Finish MUST consume
    its own export and MeshIR payload and the supplied sole M_Village with its
    declared native closure; nothing is discovered or duplicated. Mega_Trim MUST
    stay look-only simple-as-complex, Mega_Ramp and Mega_Trail complex-as-simple.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    texture = _load(root, 'games/yorimichi/v2_texture_units.py', 'v2_mega_texture')
    island = _load(root, 'games/yorimichi/v2_island_units.py', 'v2_mega_items')
    if not isinstance(natives, dict):
        raise ValueError('Mega requires the supplied native material roster')
    dependencies = {}
    def dependency(ref):
        if (not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ('unit', 'item', 'package'))
                or not ref['package'].startswith('/Game/') or set(ref) - {'unit', 'item', 'package', 'dependencies'}):
            raise ValueError('Mega material dependency must name its actual finished native Item')
        key = ref['unit'], ref['item']
        if key in dependencies:
            if dependencies[key][1]['package'] != ref['package']:
                raise ValueError('Mega material Item aliases distinct native packages')
            return dependencies[key][0]
        slot = 'native' + str(len(dependencies)); dependencies[key] = slot, ref
        for child in ref.get('dependencies', ()):
            if isinstance(child, str):
                if child not in natives:
                    raise ValueError('Missing supplied Mega transitive material input: ' + child)
                child = natives[child]
            dependency(child)
        return slot
    material = natives.get(MATERIAL)
    if not isinstance(material, dict) or material.get('package') != MATERIAL:
        raise ValueError('Missing exact supplied Mega native material: ' + MATERIAL)
    material_slot = dependency(material)
    code = set(texture._code(root))
    scanner = ImportScanner()
    for source in (FINISH, 'games/yorimichi/city_tile_products.py'):
        code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root / source,
            (root / 'platform/studio', root / 'games/yorimichi', root / 'games/yorimichi/world', root / 'games/yorimichi/world/regions')))
    descriptor = json.loads((root / 'games/yorimichi/unreal/Yorimichi.uproject').read_text())
    modules = [{'name': m['Name'], 'kind': m['Type'], 'loading_phase': m.get('LoadingPhase', 'Default')} for m in descriptor['Modules']]
    result = deepcopy(geometry); seen = set(); requirements = dict(result.get('module_requirements', {}))
    for template in result['templates']:
        if not template['unit_prefix'].startswith('world.mega.export.'):
            continue
        parent = template['unit_prefix'].removeprefix('world.mega.export.')
        if (parent not in PARENTS or parent in seen or template['producer'] != 'world.mega.geometry.' + parent
                or template['group'] != 'geometry' or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                or template['params'].get('format') != 'fbx'
                or template['files'] != [{'path': '$piece.fbx'}, {'path': 'export.json'}] or template.get('followers')):
            raise ValueError('Mega native followers require every original FBX D2 parent exactly once')
        seen.add(parent)
        raw_package, destination = RAW + '/$piece', DESTINATION + '/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': texture.OPS,
               'code': texture._code(root), 'inputs': [{'role': 'content', 'name': 'source',
                   'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
               'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                   'fbx': dict(FBX),
                   'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=0,Editor.AsyncStaticMeshCompilation=0']},
               'outputs': [island._item(raw_package, raw=True)]}
        inputs = [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': '$previous', 'item': 'raw'}},
                  {'role': 'content', 'name': 'source_export', 'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}},
                  {'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member', 'unit': template['producer'],
                                                                    'group': 'geometry', 'piece': '$piece'}},
                  *({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}}
                    for slot, ref in dependencies.values())]
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH,
                  'code': sorted(code), 'inputs': inputs,
                  'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': destination,
                    'package_sources': {'raw': raw_package},
                    'args': {'parent': parent, 'collision': 'look_only' if parent == 'Mega_Trim' else 'complex_as_simple',
                             'payload': 'payload', 'source_export': 'source_export', 'material': material_slot,
                             'native_inputs': {slot: ref['package'] for slot, ref in dependencies.values()}},
                    'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
                  'outputs': [island._item(destination, raw=False)]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
                                 {'unit': finish, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in inputs}}]
        requirements[template['unit_prefix']] = modules
    if seen != set(PARENTS):
        raise ValueError('Mega native followers require the complete three-parent family')
    result['module_requirements'] = requirements
    return result
