"""Replace Scripts/import_wanderer.py by one unit per native Wanderer V2 asset bundle (world/wanderer_v2.py).

The original runs inside unreal.world and imports characters.wanderer's export into its own compact skeleton:
M_Wanderer (flat vertex-colour graph, two sided), SK_Wanderer with SK_Wanderer_Skeleton and
SK_Wanderer_PhysicsAsset, one A_<Clip> per clip at 60 Hz on that skeleton with the shared CharacterCompression,
BS_Locomotion and BS_Crouching, and the public selection asset /Game/Wanderer/DA_Wanderer.

The clip roster is the committed animate.ACTIONS key set that wanderer_motion.py tunes; the blend spaces are the
original's literal blendspace() calls. Every FBX, model_manifest.json and animation_manifest.json value is read
from the supplied characters.wanderer Item (``natives['wanderer'] = {unit, item, root?}``); the shared
compression owner comes from v2_moveset_units.compression_unit (``natives['compression']``).
"""
import ast
from pathlib import Path

from v2_character_units import _modules, _output
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/wanderer_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_wanderer.py'
SOURCE = GAME + '/assets/characters/wanderer'
PRODUCER = 'characters.wanderer'
DEST = '/Game/Wanderer/V2'
RAW = '/Game/_Raw/Wanderer'
DEFINITION = '/Game/Wanderer/DA_Wanderer'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
# import_wanderer.fbx's skeletal and animation import data (enums as unreal_enum tokens).
MESH_FBX = {'normal_import_method': {'unreal_enum': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS'},
            'vertex_color_import_option': {'unreal_enum': 'VertexColorImportOption.REPLACE'},
            'use_t0_as_ref_pose': False, 'update_skeleton_reference_pose': True, 'import_meshes_in_bone_hierarchy': True,
            'convert_scene': True}
CLIP_FBX = {'animation_length': {'unreal_enum': 'FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME'},
            'use_default_sample_rate': False, 'custom_sample_rate': 60, 'import_bone_tracks': True, 'convert_scene': True}


def roster(checkout):
    """The committed clip names: animate.ACTIONS, which wanderer_motion only deep-copies and tunes."""
    root = Path(checkout)
    kit = ast.parse((root / SOURCE / 'kit/animate.py').read_bytes())
    actions = [n.value for n in kit.body if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ['ACTIONS']]
    if len(actions) != 1 or not isinstance(actions[0], ast.Dict) or not all(isinstance(k, ast.Constant) for k in actions[0].keys):
        raise Unsupported('animate.ACTIONS is no longer a literal clip table')
    names = [k.value for k in actions[0].keys]
    motion = ast.parse((root / SOURCE / 'wanderer_motion.py').read_bytes())
    for node in motion.body:
        text = ast.unparse(node)
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)) or text == 'ACTIONS = deepcopy(compact.ACTIONS)':
            continue
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and ast.unparse(node.value.func).endswith('].update')
                and isinstance(node.value.func.value, ast.Subscript) and ast.unparse(node.value.func.value.value) == 'ACTIONS'
                and isinstance(node.value.func.value.slice, ast.Constant) and node.value.func.value.slice.value in names):
            continue
        if isinstance(node, ast.For) and ast.unparse(node.iter) == 'ACTIONS.values()' and 'ACTIONS[' not in ast.unparse(node.body):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        raise Unsupported('wanderer_motion.py changes the clip roster beyond tuning: ' + text.splitlines()[0])
    if len(set(names)) != len(names) or not names:
        raise Unsupported('duplicate or empty Wanderer clip roster')
    return names


def blendspaces(checkout):
    """The original's literal blendspace(name, [clips]) calls, in order."""
    tree = ast.parse((Path(checkout) / ORIGINAL).read_bytes())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) == 'blendspace']
    result = {}
    for call in calls:
        name, clips = (ast.literal_eval(a) for a in call.args)
        result[name] = list(clips)
    if sorted(result) != ['BS_Crouching', 'BS_Locomotion']:
        raise Unsupported('import_wanderer.py blend spaces changed')
    return result


def _check(row):
    commands = row['commands']
    if (row['id'] != PRODUCER or len(commands) != 1 or commands[0].get('kind') != 'blender'
            or commands[0].get('script') != {'path': SOURCE + '/build.py'}
            or list(commands[0].get('args', [])) != ['--animations', '--export', '--no-render']):
        raise Unsupported('characters.wanderer differs from the original Blender export')


def _code_closure(checkout):
    from atelier.source_imports import ImportScanner
    root = Path(checkout)
    found = {p.relative_to(root).as_posix() for p in ImportScanner().local_imports(
        root / GAME / 'unreal/Scripts/animation_compression.py',
        (root / GAME / 'world', root / GAME / 'unreal/Scripts', root / 'platform/studio'))}
    return sorted({*_code(checkout), SCRIPT, *found})


def wanderer_units(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] authored-c3-wanderer-v2
    import_wanderer.py MUST become one unit per native asset bundle: M_Wanderer, a
    raw skeletal import and one finish owning SK_Wanderer with its compact Skeleton
    and PhysicsAsset, a raw import and finish per committed clip on that Skeleton
    with the supplied shared compression, both blend spaces and DA_Wanderer. Every
    FBX and manifest value MUST come from the supplied characters.wanderer Item;
    generated content is never scanned and the original never runs.
    """
    checkout = Path(checkout)
    selected = [row for row in rows if row['id'] == PRODUCER]
    if len(selected) != 1:
        raise Unsupported('Wanderer V2 needs exactly the actual characters.wanderer row')
    _check(selected[0])
    source = natives.get('wanderer')
    if (not isinstance(source, dict) or source.get('unit') != PRODUCER or not isinstance(source.get('item'), str)
            or not {'unit', 'item'} <= set(source) <= {'unit', 'item', 'root'}):
        raise Unsupported('missing the exact characters.wanderer export Item')
    compression = natives.get('compression')
    if (not isinstance(compression, dict) or set(compression) != {'unit', 'item', 'package'}
            or compression['package'] != COMPRESSION):
        raise Unsupported('missing the shared CharacterCompression owner Item')
    clips, spaces = roster(checkout), blendspaces(checkout)
    if any(clip not in clips for names in spaces.values() for clip in names) or not {'Walk', 'Jog', 'Run', 'CrouchWalk'} <= set(clips):
        raise Unsupported('blend space or definition clips are outside the committed roster')
    code, ops_code = _code_closure(checkout), list(_code(checkout))
    editor = _modules(checkout, [])
    units, staged, packages = [], {}, {}

    def item(name, unit, item_id):
        return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}

    def add(unit, inputs, *, wanderer=True, member=None):
        roots = {}
        if wanderer:
            inputs.append(item('wanderer', source['unit'], source['item']))
            if 'root' in source:
                roots['wanderer'] = dict(source['root'])
        if member is not None:
            unit['params']['source_member'] = member
        if roots:
            unit['params']['input_roots'] = roots
        unit['inputs'] = inputs
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}

    def native(package):
        ref = packages[package]
        return item('native_' + package.removeprefix('/Game/').replace('/', '_'), ref['unit'], ref['item'])

    material = DEST + '/M_Wanderer'
    add({'id': 'unreal.wanderer.material', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'material'}, 'settings': []}, 'outputs': [_output('asset', material, 'Material')]},
        [], wanderer=False)
    packages[material] = {'unit': 'unreal.wanderer.material', 'item': 'asset', 'package': material}

    raw_mesh = RAW + '/SK_Wanderer'
    add({'id': 'unreal.wanderer.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
         'params': {'op': 'raw_import', 'kind': 'skeletal_mesh', 'source': 'wanderer', 'destination': raw_mesh,
                    'create_physics_asset': True, 'fbx': dict(MESH_FBX)},
         'outputs': [_output('raw_mesh', raw_mesh, 'RawSkeletalMesh', store=True),
                     _output('raw_skeleton', raw_mesh + '_Skeleton', 'Skeleton', store=True),
                     _output('raw_physics_asset', raw_mesh + '_PhysicsAsset', 'PhysicsAsset', store=True)]},
        [], member='fbx/Wanderer.fbx')
    mesh = DEST + '/SK_Wanderer'
    partners = {'skeleton': mesh + '_Skeleton', 'physics_asset': mesh + '_PhysicsAsset'}
    add({'id': 'unreal.wanderer.mesh', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': mesh, 'partners': partners,
                    'args': {'action': 'mesh', 'material': 'material', 'wanderer': 'wanderer'}},
         'outputs': [_output('mesh', mesh, 'SkeletalMesh'), _output('skeleton', partners['skeleton'], 'Skeleton'),
                     _output('physics_asset', partners['physics_asset'], 'PhysicsAsset')]},
        [item('raw', 'unreal.wanderer.raw', 'raw_mesh'), item('raw_skeleton', 'unreal.wanderer.raw', 'raw_skeleton'),
         item('raw_physics_asset', 'unreal.wanderer.raw', 'raw_physics_asset'), item('material', 'unreal.wanderer.material', 'asset')])
    for key, package in (('mesh', mesh), ('skeleton', partners['skeleton']), ('physics_asset', partners['physics_asset'])):
        packages[package] = {'unit': 'unreal.wanderer.mesh', 'item': key, 'package': package}
    bundle = [material, partners['skeleton'], partners['physics_asset']]
    packages[mesh]['dependencies'] = [dict(packages[p]) for p in bundle]
    closure = [mesh, *bundle]

    for clip in clips:
        raw_clip, package = f'{RAW}/A_{clip}', f'{DEST}/A_{clip}'
        raw_id, clip_id = f'unreal.wanderer.clip.raw.{clip}', f'unreal.wanderer.clip.{clip}'
        add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': {'op': 'raw_import', 'kind': 'animation', 'source': 'wanderer', 'destination': raw_clip,
                        'skeleton': 'skeleton', 'fbx': dict(CLIP_FBX)},
             'outputs': [_output('raw_animation', raw_clip, 'RawAnimation', store=True)]},
            [item('skeleton', 'unreal.wanderer.mesh', 'skeleton')], member=f'fbx/{clip}.fbx')
        add({'id': clip_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': package,
                        'args': {'action': 'clip', 'name': clip, 'skeleton': native(partners['skeleton'])['name'],
                                 'compression': 'compression', 'wanderer': 'wanderer'}},
             'outputs': [_output('animation', package, 'Animation')]},
            [item('raw', raw_id, 'raw_animation'), item('compression', compression['unit'], compression['item']),
             *(native(p) for p in closure)])
        packages[package] = {'unit': clip_id, 'item': 'animation', 'package': package,
                             'dependencies': [dict(packages[p]) for p in closure] + [dict(compression)]}

    for name, names in spaces.items():
        package = f'{DEST}/{name}'
        unit_id = f'unreal.wanderer.blendspace.{name}'
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': 'blendspace', 'name': name, 'skeleton': native(partners['skeleton'])['name'],
                                 'clips': {c: native(f'{DEST}/A_{c}')['name'] for c in names}, 'wanderer': 'wanderer'},
                        'settings': []},
             'outputs': [_output('asset', package, 'BlendSpace1D')]},
            [*(native(p) for p in closure), item('compression', compression['unit'], compression['item']),
             *(native(f'{DEST}/A_{c}') for c in names)])
        packages[package] = {'unit': unit_id, 'item': 'asset', 'package': package,
                             'dependencies': [dict(packages[f'{DEST}/A_{c}']) for c in names]}

    clip_slots = {c: native(f'{DEST}/A_{c}')['name'] for c in clips}
    add({'id': 'unreal.wanderer.definition', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'definition', 'mesh': native(mesh)['name'], 'clips': clip_slots,
                             'locomotion': native(f'{DEST}/BS_Locomotion')['name'],
                             'crouching': native(f'{DEST}/BS_Crouching')['name'], 'camera_height': 35., 'wanderer': 'wanderer'},
                    'settings': []},
         'outputs': [_output('asset', DEFINITION, 'WandererDefinition')]},
        [*(native(p) for p in closure), item('compression', compression['unit'], compression['item']),
         *(native(f'{DEST}/A_{c}') for c in clips), native(f'{DEST}/BS_Locomotion'), native(f'{DEST}/BS_Crouching')])
    packages[DEFINITION] = {'unit': 'unreal.wanderer.definition', 'item': 'asset', 'package': DEFINITION,
                            'dependencies': [dict(packages[p]) for p in (*closure, *(f'{DEST}/A_{c}' for c in clips),
                                                                         f'{DEST}/BS_Locomotion', f'{DEST}/BS_Crouching')]}
    requirements = {u['id']: editor[0] for u in units if u['op']['kind'] != 'unreal.raw_import'}
    return {'units': units, 'staged_inputs': staged, 'packages': packages, 'module_requirements': requirements,
            'clips': clips, 'blendspaces': spaces}
