"""Cold railway members and single-package native bodies for the original track importer."""
import ast
import json
from pathlib import Path

from train_v2 import blob, data, encode, load, name, roster, save, select, source

ORIGINAL = 'games/yorimichi/unreal/Scripts/import_belmonte_track.py'
ROOT = '/Game/BelmonteTrack'
PARENT = '/Game/Belmonte/Materials/M_Belmonte'
GLOW = ROOT + '/Materials/M_TK_Glow'
RUNTIME, REPORT = 'data/track.json', 'data/import-report.json'


def members(track, material_view):
    """The original sorted first-use material rule, collision policy and exact runtime-referenced GLBs."""
    from atelier.gltf import glb_parts
    track = Path(track)
    runtime = json.loads(source(track, 'runtime/track.json').read_bytes())
    report = json.loads(Path(material_view).read_bytes())
    belmonte = {key.rsplit('/', 1)[-1].split('.')[0]: '/Game/Belmonte/Materials/' + name(entry['name'])
                for key, entry in report['materials'].items()}
    collision = {p['name']: p['collision'] for p in runtime['pieces']}
    for group in runtime['instances']:
        if group['collision']:
            key = group['mesh'].rsplit('/', 1)[-1].split('.')[0]
            collision[key] = len(runtime['meshes'][key]['lods']) - 1
    result = {'materials': {}, 'mesh1': {}, 'mesh2': {}, 'mesh3': {}, 'record': {}}
    seen = set()
    for key, spec in sorted(runtime['meshes'].items()):
        name(key)
        if key.casefold() in seen or len(spec['lods']) not in (1, 2, 3):
            raise ValueError('Aliased track mesh or unsupported LOD chain')
        seen.add(key.casefold())
        if spec['asset'].split('.')[0] != ROOT + '/' + key:
            raise ValueError('Track runtime mesh path differs from its owned package')
        payloads = [source(track, relative).read_bytes() for relative in spec['lods']]
        gltf, _ = glb_parts(payloads[0])
        if gltf.get('skins') or gltf.get('animations'):
            raise ValueError('Track GLBs must be static')
        records = {m.get('name'): m for m in gltf.get('materials', [])}
        for material in spec['materials']:
            name(material)
            if material.startswith('MI_B_'):
                if material not in belmonte:
                    raise ValueError('Track slot lacks its original Belmonte material: ' + material)
            elif material not in result['materials']:
                result['materials'][material] = {'name': material, 'record': records.get(material),
                    'bias': runtime.get('exposure', {}).get('bias', 0.)}
        value = {'name': key, 'spec': spec, 'collision': collision.get(key, -1),
                 'belmonte': {m: belmonte[m] for m in spec['materials'] if m.startswith('MI_B_')},
                 'levels': [blob(raw) for raw in payloads]}
        result['mesh' + str(len(payloads))][key] = value
    result['record']['Record'] = {'name': 'Record', 'runtime': runtime, 'belmonte': belmonte,
                                 'collision': collision}
    return result


def project(track=None, material_view=None, output=None, kind=None):
    values = members(track, material_view)
    values['glow_materials'] = {k: v for k, v in values['materials'].items() if k == 'MI_TK_LampGlow'}
    values['materials'] = {k: v for k, v in values['materials'].items() if k != 'MI_TK_LampGlow'}
    if kind not in values or Path(output).exists():
        raise ValueError('Track projection requires a fresh supported group')
    Path(output).mkdir(parents=True)
    for key, value in sorted(values[kind].items()):
        (Path(output) / (key + '.json')).write_text(encode(value))


def original(context, unreal, names, *, bias=0.):
    path = Path(context.job_dir) / ORIGINAL
    nodes = [n for n in ast.parse(path.read_bytes()).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in nodes} != set(names):
        raise ValueError('Original track material functions drifted')
    scope = {'ROOT': ROOT, 'BIAS': bias, 'unreal': unreal, 'E': unreal.EditorAssetLibrary,
             'MEL': unreal.MaterialEditingLibrary, 'AT': unreal.AssetToolsHelpers.get_asset_tools()}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), ORIGINAL, 'exec'), scope)
    return scope


def external(context, unreal, slots):
    result = {}
    for slot in slots:
        asset = load(context, unreal, slot)
        package = asset.get_path_name().split('.')[0]
        if package in result: raise ValueError('Aliased supplied Belmonte material')
        result[package] = asset
    return result


def material(context, unreal, args):
    meta = data(context, args['meta']); key = name(args['name'])
    destination = ROOT + '/Materials/' + key
    if meta['name'] != key or set(context.outputs) != {destination} or key.startswith('MI_B_'):
        raise ValueError('Track instance must own exactly its selected non-Belmonte package')
    parent = load(context, unreal, args['parent'])
    expected = GLOW if key == 'MI_TK_LampGlow' else PARENT
    if parent.get_path_name().split('.')[0] != expected:
        raise ValueError('Track instance parent differs from original')
    scope = original(context, unreal, ('track_material',), bias=meta['bias'])
    asset = scope['track_material'](key, meta['record'], parent if expected == GLOW else None)
    return save(unreal, asset, destination)


def slot_key(slot, spec):
    slot_name = str(slot.get_editor_property('material_slot_name'))
    imported = str(slot.get_editor_property('imported_material_slot_name')) or slot_name
    return next((m for m in spec['materials'] if imported.startswith(m)), imported.split('_LOD')[0])


def mesh(context, unreal, args):
    meta = data(context, args['meta']); key = name(args['name']); destination = ROOT + '/' + key
    if meta['name'] != key or set(context.outputs) != {destination} or len(args['levels']) != meta['count']:
        raise ValueError('Track finish differs from its selected package/LOD chain')
    E = unreal.EditorAssetLibrary
    asset = E.duplicate_asset(load(context, unreal, args['levels'][0]).get_path_name(), destination)
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    editor.remove_collisions(asset)
    for level in range(1, meta['count']):
        if editor.set_lod_from_static_mesh(asset, level, load(context, unreal, args['levels'][level]), 0, True) != level:
            raise ValueError('Track LOD copy failed')
    if asset.get_num_lods() != meta['count']:
        raise ValueError('Track LOD count differs from actual source')
    if meta['count'] > 1 and not editor.set_lod_screen_sizes(asset, meta['spec']['screen_sizes']):
        raise ValueError('Track screen sizes failed')
    local = {k: load(context, unreal, v) for k, v in roster(args['materials']).items()}
    belmonte = external(context, unreal, args['belmonte'])
    for index, slot in enumerate(asset.get_editor_property('static_materials')):
        key_ = slot_key(slot, meta['spec'])
        material = belmonte.get(meta['belmonte'].get(key_)) if key_.startswith('MI_B_') else local.get(key_)
        expected = meta['belmonte'].get(key_) if key_.startswith('MI_B_') else ROOT + '/Materials/' + key_
        if material is None or material.get_path_name().split('.')[0] != expected:
            raise ValueError('Track slot has no declared finished material: ' + key_)
        asset.set_material(index, material)
    lod = meta['collision']; body = asset.get_editor_property('body_setup')
    if lod >= 0 and body:
        asset.set_editor_property('lod_for_collision', min(lod, asset.get_num_lods() - 1))
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        body.set_editor_property('double_sided_geometry', True)
    return save(unreal, asset, destination)


def record(context, unreal, args):
    output = {'runtime': RUNTIME, 'report': REPORT}.get(args.get('field'))
    if not output or context.outputs or tuple(context.data_outputs) != (output,):
        raise ValueError('Track data author owns exactly one JSON')
    meta = data(context, args['meta']); runtime = meta['runtime']
    meshes = roster(args['meshes']); local = {k: load(context, unreal, s) for k, s in roster(args['materials']).items()}
    belmonte = external(context, unreal, args['belmonte'])
    if set(meshes) != set(runtime['meshes']): raise ValueError('Track record lacks its complete current mesh inventory')
    report = {'meshes': {}, 'materials': {}}
    for key, spec in sorted(runtime['meshes'].items()):
        asset = load(context, unreal, meshes[key])
        if asset.get_path_name().split('.')[0] != ROOT + '/' + key: raise ValueError('Track record foreign mesh')
        report['meshes'][key] = {'lods': asset.get_num_lods(),
            'triangles': [asset.get_num_triangles(i) for i in range(asset.get_num_lods())],
            'collision_lod': meta['collision'].get(key, -1)}
        for slot in asset.get_editor_property('static_materials'):
            material = slot_key(slot, spec)
            value = belmonte.get(meta['belmonte'].get(material)) if material.startswith('MI_B_') else local.get(material)
            if value is None: raise ValueError('Track report material is missing')
            report['materials'].setdefault(material, value.get_path_name())
    return {output: runtime if args['field'] == 'runtime' else report}


def run(context):
    """@cc [owner:fontanierh,label:correctness] track-native-package-owners
    Each track native body MUST own exactly one package or JSON. Track materials
    MUST preserve the original glow/exposure and flat-colour rules; mesh finishing
    MUST bind declared Belmonte/track owners and retain authored LOD/collision rules.
    No original main, registry scan, ambient Content or namespace deletion may run.
    """
    import unreal
    args = context.params['args']
    if args['action'] == 'glow':
        if set(context.outputs) != {GLOW}: raise ValueError('Track glow must own its single material')
        return save(unreal, original(context, unreal, ('glow_parent',))['glow_parent'](), GLOW)
    if args['action'] == 'material': return material(context, unreal, args)
    if args['action'] == 'mesh': return mesh(context, unreal, args)
    if args['action'] == 'record': return record(context, unreal, args)
    raise ValueError('Unsupported track native action')
