"""World props per-piece native followers over the actual props D2 export children.

Scripts/setup_project.py imports each of world_props' fourteen rigid props (prop_sources.BUILDERS) into
/Game/Japan/Assets with its own static FBX options, binds every slot by name through
asset_catalog.material_bindings (plus MI_FarForest and MI_Coast), and gives only Pole, Pole_Lamp, Guardrail,
Lantern and Torii complex-as-simple collision; the rest keep their raw import policy. Each prop's consumed
palette comes from the pure prop_sources.project packets (no Blender), and each export template gains a raw
import and a finish over its own export and MeshIR plus the supplied MI_<slot> closure.
"""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

FINISH = 'games/yorimichi/world/props_finish_v2.py'
SOURCES = 'games/yorimichi/world/prop_sources.py'
CATALOGUE = 'games/yorimichi/world/asset_catalog.py'
ORIGINAL = 'games/yorimichi/unreal/Scripts/setup_project.py'
DESTINATION = '/Game/Japan/Assets'
RAW = '/Game/_Raw/Props'
COMPLEX = ('Guardrail', 'Lantern', 'Pole', 'Pole_Lamp', 'Torii')
# setup_project.import_fbx's static options. It leaves convert_scene_unit at the engine default (False), which
# the raw op would otherwise turn on; import_uniform_scale and one_convex_hull_per_ucx keep their defaults.
FBX = {'combine_meshes': True, 'generate_lightmap_u_vs': False, 'auto_generate_collision': False,
       'convert_scene': True, 'convert_scene_unit': False, 'import_uniform_scale': 1.0, 'build_nanite': False,
       'one_convex_hull_per_ucx': True,
       'vertex_color_import_option': {'unreal_enum': 'VertexColorImportOption.REPLACE'},
       'normal_import_method': {'unreal_enum': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS'}}


def _load(root, relative, name):
    spec = importlib.util.spec_from_file_location(name, root / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def bindings(root):
    """Each prop's consumed palette keys and setup_project's MI_<key> package for each, from original sources only."""
    world = str(root / 'games/yorimichi/world')
    sys.path.insert(0, world)
    try:
        sources = _load(root, SOURCES, 'v2_props_sources')
        catalogue = _load(root, CATALOGUE, 'v2_props_catalogue')
        packets = sources.project((root / 'games/yorimichi/world/build_assets.py').read_text())
    finally:
        sys.path.remove(world)
    tree = ast.parse((root / ORIGINAL).read_bytes(), filename=ORIGINAL)
    loops = [node for node in ast.walk(tree) if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple)
             and 'CTF_USE_COMPLEX_AS_SIMPLE' in ast.unparse(node)]
    extra = [node for node in ast.walk(tree) if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple)
             and "'/Game/Japan/Materials/MI_' + name" in ast.unparse(node)]
    if (len(loops) != 1 or tuple(sorted(ast.literal_eval(loops[0].iter))) != COMPLEX or len(extra) != 1
            or set(packets) != set(sources.BUILDERS)):
        raise ValueError('World prop collision/material policy differs from setup_project')
    mapping = {**catalogue.material_bindings(),
               **{name: '/Game/Japan/Materials/MI_' + name for name in ast.literal_eval(extra[0].iter)}}
    result = {}
    for prop, packet in packets.items():
        missing = sorted(set(packet['materials']) - set(mapping))
        if missing or not packet['materials']:
            raise ValueError(f'{prop}: palette keys have no original material binding: {missing}')
        result[prop] = {key: mapping[key] for key in sorted(packet['materials'])}
    return result


def attach_followers(geometry, natives, *, checkout):
    """@cc [owner:fontanierh,label:correctness] original-world-prop-native-followers
    All fourteen original prop_sources.BUILDERS D2 parents MUST receive independent
    per-piece raw and finish owners at their original /Game/Japan/Assets packages.
    Finish MUST consume its own export and MeshIR payload and exactly the supplied
    MI_<key> Items its projected palette binds, with their declared native closure;
    nothing is discovered or duplicated. Only Pole, Pole_Lamp, Guardrail, Lantern and
    Torii become complex-as-simple; every other prop keeps its raw import policy.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    texture = _load(root, 'games/yorimichi/v2_texture_units.py', 'v2_props_texture')
    island = _load(root, 'games/yorimichi/v2_island_units.py', 'v2_props_items')
    if not isinstance(natives, dict):
        raise ValueError('World props require the supplied native material roster')
    palette = bindings(root)
    code = set(texture._code(root))
    scanner = ImportScanner()
    for source in (FINISH, 'games/yorimichi/city_tile_products.py'):
        code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root / source,
            (root / 'platform/studio', root / 'games/yorimichi', root / 'games/yorimichi/world', root / 'games/yorimichi/world/regions')))
    descriptor = json.loads((root / 'games/yorimichi/unreal/Yorimichi.uproject').read_text())
    modules = [{'name': m['Name'], 'kind': m['Type'], 'loading_phase': m.get('LoadingPhase', 'Default')} for m in descriptor['Modules']]
    result = deepcopy(geometry); seen = set(); requirements = dict(result.get('module_requirements', {}))
    for template in result['templates']:
        if not template['unit_prefix'].startswith('world.props.export.'):
            continue
        parent = template['unit_prefix'].removeprefix('world.props.export.')
        if (parent not in palette or parent in seen or template['producer'] != 'world.props.geometry.' + parent
                or template['group'] != 'geometry' or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                or template['params'].get('format') != 'fbx'
                or template['files'] != [{'path': '$piece.fbx'}, {'path': 'export.json'}] or template.get('followers')):
            raise ValueError('World prop native followers require every original FBX D2 parent exactly once')
        seen.add(parent)
        dependencies = {}
        def dependency(ref):
            if (not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ('unit', 'item', 'package'))
                    or not ref['package'].startswith('/Game/') or set(ref) - {'unit', 'item', 'package', 'dependencies'}):
                raise ValueError('World prop material dependency must name its actual finished native Item')
            key = ref['unit'], ref['item']
            if key in dependencies:
                if dependencies[key][1]['package'] != ref['package']:
                    raise ValueError('World prop material Item aliases distinct native packages')
                return dependencies[key][0]
            slot = 'native' + str(len(dependencies)); dependencies[key] = slot, ref
            for child in ref.get('dependencies', ()):
                if isinstance(child, str):
                    if child not in natives:
                        raise ValueError('Missing supplied world prop transitive material input: ' + child)
                    child = natives[child]
                dependency(child)
            return slot
        materials = {}
        for key, package in palette[parent].items():
            ref = natives.get(package)
            if not isinstance(ref, dict) or ref.get('package') != package:
                raise ValueError(f'{parent}: missing exact supplied material for palette key {key}: {package}')
            materials[key] = dependency(ref)
        if len({ref['package'] for _slot, ref in dependencies.values()}) != len(dependencies):
            raise ValueError('World prop native closure aliases one package across Items')
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
                    'args': {'parent': parent, 'collision': 'complex_as_simple' if parent in COMPLEX else 'original',
                             'payload': 'payload', 'source_export': 'source_export', 'materials': materials,
                             'native_inputs': {slot: ref['package'] for slot, ref in dependencies.values()}},
                    'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
                  'outputs': [island._item(destination, raw=False)]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
                                 {'unit': finish, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in inputs}}]
        requirements[template['unit_prefix']] = modules
    if seen != set(palette):
        raise ValueError('World prop native followers require the complete fourteen-prop family')
    result['module_requirements'] = requirements
    return result
