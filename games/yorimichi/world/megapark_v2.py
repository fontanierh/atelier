"""Native bodies for Scripts/import_megapark.py, one declared MegaPark package per job.

``args.action`` selects
- ``parent``: one M_Retail* graph by the original material(alpha, defaults), compiled from the staged script;
- ``instance``: one MI_<key> exactly as the original materials() loop sets it, from build.json's material spec and
  textures.json's lightmap levels, refusing a spec that differs from the declared member;
- ``mesh``: one piece finished from its raw import: the original _finish_mesh LOD settings, complex-as-simple,
  double-sided UC_ collision unless one-sided, SM_ slots bound by name to their MeshIR slots, exact triangles and the
  original 0.05 cm bounds check;
- ``level``: SuperUltraMegaPark with every finished render and collision piece placed at its native origin, the
  rails, spawn, sun, sky and post-process volume.
"""
import ast
import hashlib
import json
from pathlib import Path
import re

import numpy as np

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')
ROOT = '/Game/MegaPark'
LEVEL = ROOT + '/Maps/SuperUltraMegaPark'
PARENTS = ('M_RetailOpaque', 'M_RetailMasked', 'M_RetailTranslucent')
SCRIPTS = 'games/yorimichi/unreal/Scripts/'
ALIASES = {'diffuse': 'Diffuse', 'decal': 'Decal', 'macrooverlay': 'Macro', 'lightmap': 'Lightmap',
           'normal': 'Normal', 'detail': 'Detail', 'specular': 'Specular', 'transparent': 'Transparent'}
DEFAULT_ROLES = {'Diffuse': 'T_DefaultWhite', 'Decal': 'T_DefaultWhite', 'Macro': 'T_DefaultWhite',
                 'Lightmap': 'T_DefaultLinear', 'Normal': 'T_DefaultNormal', 'Detail': 'T_DefaultNormal',
                 'Specular': 'T_DefaultBlack', 'Transparent': 'T_DefaultWhite'}


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared MegaPark input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('MegaPark native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls):
    package = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if not isinstance(asset, cls) or _path(asset) != package:
        raise ValueError('Declared MegaPark input did not load as expected: ' + package)
    return asset


def _data(context, slot, name=None, *, directory=False):
    if not isinstance(slot, str) or context.inputs.get(slot) is None or context.packages.get(slot) not in ([], ()):
        raise ValueError('MegaPark source must be a declared Data Item: ' + str(slot))
    path = Path(context.inputs[slot])
    if (not path.is_absolute() or path.is_symlink() or path.resolve() != path
            or not path.is_relative_to(Path(context.job_dir).resolve())
            or (not path.is_dir() if directory else (not path.is_file() or path.name != name))):
        raise ValueError('MegaPark source must be its exact job-local producer root: ' + str(name or slot))
    return path


def _fresh(unreal, package):
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        raise ValueError('MegaPark destination must be fresh: ' + package)


def _owned(context, package):
    if list(context.outputs) != [package]:
        raise ValueError('MegaPark job owns exactly its declared package: ' + package)


def original(context, unreal, names):
    """Named functions and constants of the staged import_megapark.py, bound to its editor globals; no top level."""
    path = Path(context.job_dir) / SCRIPTS / 'import_megapark.py'
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original MegaPark script is not staged keyed code')
    tree = ast.parse(path.read_bytes())
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
             or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))]
    found = {n.name if isinstance(n, ast.FunctionDef) else n.targets[0].id for n in nodes}
    if found != set(names):
        raise ValueError('import_megapark.py no longer defines ' + ', '.join(sorted(set(names) - found)))
    scope = {'unreal': unreal, 'E': unreal.EditorAssetLibrary, 'MEL': unreal.MaterialEditingLibrary,
             'AT': unreal.AssetToolsHelpers.get_asset_tools(), 'ROOT': ROOT}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'import_megapark.py', 'exec'), scope)
    return scope


def _defaults(unreal, context, slots):
    loaded = {name: _load(unreal, context, slot, unreal.Texture) for name, slot in slots.items()}
    if any(_path(t) != f'{ROOT}/Textures/{name}' for name, t in loaded.items()) or set(loaded) != set(DEFAULT_ROLES.values()):
        raise ValueError('MegaPark fallback pixels differ')
    return {role: loaded[name] for role, name in DEFAULT_ROLES.items()}


def parent(context, unreal, args):
    alpha = args['alpha']
    package = f'{ROOT}/Materials/{PARENTS[alpha]}'
    _owned(context, package); _fresh(unreal, package)
    material = original(context, unreal, ('material',))['material'](alpha, _defaults(unreal, context, args['defaults']))
    if _path(material) != package:
        raise ValueError('MegaPark parent material not authored at its package')
    return material


def instance(context, unreal, args):
    if 'spec' in args:
        selected=_data(context,args['spec'],args['piece']+'.json');spec=json.loads(selected.read_bytes(),object_pairs_hook=_pairs)
        if set(spec)!={'key','material','lightmap_norm'} or args['piece']!='MI_'+spec['key'][2:]:raise ValueError('MegaPark selected material spec differs')
        key=spec['key'];p=spec['material'];alpha=p.get('alpha_mode',0);channels=p.get('retail_texture_ids',{})
        if type(alpha) is not int or alpha not in (0,1,2) or set(channels)-set(ALIASES) or set(channels.values())-set(args['texture_inputs']):raise ValueError('Invalid actual MegaPark material spec')
        restyle={'lightmaps':{channels.get('lightmap'):spec['lightmap_norm']}}
        args={**args,'key':key,'alpha':alpha,'parent':args['parents'][str(alpha)],'textures':{role:args['texture_inputs'][tid] for role,tid in channels.items()}}
    else:
        key=args['key'];report=json.loads(_data(context,args['build'],'build.json').read_bytes())
        restyle_path=_data(context,args['restyle'],directory=True) if Path(context.inputs[args['restyle']]).is_dir() else None
        restyle=json.loads((restyle_path/'textures.json' if restyle_path else _data(context,args['restyle'],'textures.json')).read_bytes())
        p=report['materials'][key];channels=p.get('retail_texture_ids',{})
    package=f'{ROOT}/Materials/MI_{key[2:]}'
    _owned(context,package);_fresh(unreal,package)
    if p.get('alpha_mode',0)!=args['alpha'] or set(channels)!=set(args['textures']):raise ValueError(f'{key}: generated material spec differs from declared member')
    textures={role:_load(unreal,context,slot,unreal.Texture) for role,slot in args['textures'].items()}
    if any(_path(textures[role])!=f'{ROOT}/Textures/T_{tid[2:]}' for role,tid in channels.items()):raise ValueError('MegaPark declared texture differs')
    base = _load(unreal, context, args['parent'], unreal.Material)
    if _path(base) != f'{ROOT}/Materials/{PARENTS[args["alpha"]]}':
        raise ValueError(f'{key}: instance parent differs from its alpha mode')
    defaults = _defaults(unreal, context, args['defaults'])
    scope = original(context, unreal, ('MOSSY', 'NATURAL'))
    E, MEL = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
    mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'MI_' + key[2:], ROOT + '/Materials', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if not isinstance(mi, unreal.MaterialInstanceConstant) or _path(mi) != package:
        raise ValueError(f'{key}: instance not created')
    # import_megapark.materials, for this key.
    MEL.set_material_instance_parent(mi, base)
    for role, parameter in ALIASES.items():
        MEL.set_material_instance_texture_parameter_value(mi, parameter, textures[role] if role in channels else defaults[parameter])
    params = p.get('retail_parameters', {})
    def number(name, default):
        try: return float(params[name][0])
        except (KeyError, ValueError): return default
    scalars = {'MacroScale': number('macroOverlayUVScale', 1.), 'DetailScale': number('detailNormalUVScale', 1.),
               'MacroOpacity': number('macroOverlayOpacity', 0.) if 'macrooverlay' in channels else 0.,
               'UseDecal': float('decal' in channels), 'HasLightmap': float('lightmap' in channels),
               'HasTransparent': float('transparent' in channels),
               'LightmapNorm': restyle['lightmaps'].get(channels.get('lightmap'), 3.),
               'Moss': float(channels.get('diffuse') in scope['MOSSY'])}
    if p.get('seam'):
        scalars.update(SpecularScale=0., Gloss=0., LightmapOcclusion=.25)
    for k, v in scalars.items():
        MEL.set_material_instance_scalar_parameter_value(mi, k, v)
    natural = p.get('alpha_mode', 0) == 0 and channels.get('diffuse') in scope['NATURAL']
    overrides = mi.get_editor_property('base_property_overrides')
    overrides.set_editor_property('override_two_sided', natural); overrides.set_editor_property('two_sided', natural)
    mi.set_editor_property('base_property_overrides', overrides)
    MEL.update_material_instance(mi)
    if not E.save_loaded_asset(mi):
        raise ValueError(f'{key}: instance save failed')
    return mi


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('Duplicate MegaPark receipt key')
        result[key] = value
    return result


def source_facts(context, args, piece):
    """import_megapark's entry for one piece, from its own export receipt, MeshIR payload and parent metadata."""
    from atelier import mesh_ir
    from atelier.export_manifest import validate as validate_export
    root = _data(context, args['source_export'], directory=True)
    receipt = validate_export(root, key=piece)
    if receipt['primary'] != piece + '.fbx' or {p.name for p in root.iterdir()} != {'export.json', piece + '.fbx'}:
        raise ValueError(f'{piece}: export Item differs from its exact selected source')
    payload = _data(context, args['payload'], directory=True)
    members = list(payload.iterdir())
    if len(members) != 1 or members[0].name != piece + '.npz' or members[0].is_symlink() or not members[0].is_file():
        raise ValueError(f'{piece}: requires exactly its selected MeshIR payload')
    raw = members[0].read_bytes()
    if receipt['metadata']['geometry_sha256'] != hashlib.sha256(raw).hexdigest():
        raise ValueError(f'{piece}: export differs from its MeshIR payload')
    meta, decoded = mesh_ir.decode(raw)
    if not np.array_equal(meta['matrix'], np.eye(4)):
        raise ValueError('Unexpected park local-frame transform')
    info = json.loads(_data(context, args['metadata'], args['parent'] + '.json').read_bytes(), object_pairs_hook=_pairs)
    if info.get('schema') != 1 or info['entry']['name'] != args['parent']:
        raise ValueError('Foreign logical park metadata')
    origin = info['entry']['native_origin']
    vertices = decoded['positions'][:, [0, 2, 1]].astype('f8')
    vertices[:, 2] *= -1
    vertices += np.asarray(origin)
    used = set(int(i) for i in decoded['materials'])
    return dict(triangles=receipt['triangles'], origin=origin, one_sided=info['entry'].get('one_sided', True),
                materials=[slot for i, slot in enumerate(meta['slots']) if i in used],
                minimum=vertices.min(0).tolist(), maximum=vertices.max(0).tolist())


def _ue(point):
    return (point[0] * 100., point[2] * 100., point[1] * 100.)


def mesh(context, unreal, args):
    params = context.params
    destination = params['destination']
    piece = destination.rsplit('/', 1)[-1]
    source = _selected(context, 'raw')
    if (not PACKAGE.fullmatch(destination) or destination != f'{ROOT}/Meshes/{piece}' or source != f'/Game/_Raw/MegaPark/Meshes/{piece}'
            or params.get('source') != 'raw' or args['collision'] != args['parent'].startswith('UC_')
            or not (piece == args['parent'] or piece.startswith(args['parent'] + '_'))):
        raise ValueError('MegaPark mesh finish must own exactly its original piece package')
    _owned(context, destination)
    entry = source_facts(context, args, piece)
    material_slots=args['materials']
    if isinstance(material_slots,dict) and 'derived_items' in material_slots:
        members=_derived(material_slots);material_slots={('0x'+row['piece'][3:]):row['slot'] for row in members}
        if any(not row['piece'].startswith('MI_') for row in members) or len(material_slots)!=len(members):raise ValueError('MegaPark actual MI roster differs')
    mis={key:_load(unreal,context,slot,unreal.MaterialInterface) for key,slot in material_slots.items()}
    if set(args['native_inputs']) != {slot for slot in context.inputs if slot.startswith('native')}:
        raise ValueError('MegaPark finish input membership differs from its declared native closure')
    for slot, package in args['native_inputs'].items():
        if _selected(context, slot) != package:
            raise ValueError('MegaPark native dependency differs')
    if any(_path(m) != f'{ROOT}/Materials/MI_{key[2:]}' for key, m in mis.items()):
        raise ValueError('MegaPark slot materials must be the declared MI_ instances')
    library = unreal.EditorAssetLibrary
    _fresh(unreal, destination)
    asset = library.duplicate_asset(source, destination)
    if not isinstance(asset, unreal.StaticMesh) or _path(asset) != destination:
        raise ValueError('MegaPark raw duplicate failed: ' + destination)
    unreal.load_module('StaticMeshEditor')
    original(context, unreal, ('_finish_mesh',))['_finish_mesh'](asset)
    collision = args['collision']
    body = asset.get_editor_property('body_setup')
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    body.set_editor_property('double_sided_geometry', collision and not entry['one_sided'])
    if not collision:
        found = set()
        slots = list(asset.get_editor_property('static_materials'))
        for slot in slots:
            key = str(slot.get_editor_property('imported_material_slot_name'))
            if key not in mis:
                raise ValueError(f'{piece}: unknown material {key}')
            slot.set_editor_property('material_interface', mis[key]); found.add(key)
        if found != set(entry['materials']):
            raise ValueError(f'{piece}: imported slots differ from its MeshIR slots')
        asset.set_editor_property('static_materials', slots)
    def validate():
        if asset.get_num_triangles(0) != entry['triangles']:
            raise ValueError(f'{piece}: triangle count differs')
        box = asset.get_bounding_box()
        lo = [a - b for a, b in zip(_ue(entry['minimum']), _ue(entry['origin']))]
        hi = [a - b for a, b in zip(_ue(entry['maximum']), _ue(entry['origin']))]
        error = max(sum((getattr(box.min, k) - v) ** 2 for k, v in zip('xyz', lo)) ** .5,
                    sum((getattr(box.max, k) - v) ** 2 for k, v in zip('xyz', hi)) ** .5)
        if not error < .05:
            raise ValueError(f'{piece}: bounds differ by {error} cm')
        return error
    validate()
    if not library.save_loaded_asset(asset):
        raise ValueError('Could not save current park mesh ' + piece)
    primary = Path(context.content_dir) / (destination.removeprefix('/Game/') + '.uasset')
    if any(part.is_symlink() for part in (primary, *primary.parents)) or not primary.is_file():
        raise ValueError('MegaPark native save did not leave its actual regular primary package')
    error=validate()
    if args.get('audit'):
        binary='data/imported-geometry/'+piece+'.bin';report_path='data/imported-reports/'+piece+'.json'
        if set(getattr(context,'data_outputs',()))!={binary,report_path} or len(context.data_outputs)!=2:raise ValueError('MegaPark finish requires its exact declared native audit outputs')
        observer=getattr(getattr(unreal,'MeshImportAudit',None),'dump_mesh_triangles',None)
        if not callable(observer):raise ValueError('Produced YorimichiImport MeshImportAudit unavailable')
        origin=original(context,unreal,('ue',))['ue'](entry['origin'])
        if not observer(asset,origin,str(Path(context.job_dir)/'output'/binary)):raise ValueError('Actual MegaPark triangle dump failed')
        editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        return {report_path:{'name':piece,'triangles':asset.get_num_triangles(0),'bounds_error_cm':error,'uv_channels':editor.get_num_uv_channels(asset,0),'collision':collision,'placed':args['parent'] not in ('SM_MP_Seam','UC_MP_Seam')}}
    return asset


def level(context, unreal, args):
    _owned(context, LEVEL); _fresh(unreal, LEVEL)
    report = json.loads(_data(context, args['build'], 'build.json').read_bytes())
    piece_members=_derived(args['pieces']);placed={row['piece']:row['slot'] for row in piece_members}
    if 'materials' in args:
        for row in _derived(args['materials']):
            asset=_load(unreal,context,row['slot'],unreal.MaterialInterface)
            if _path(asset)!=ROOT+'/Materials/'+row['piece']:raise ValueError('MegaPark level actual MI differs')
    entries = [(e, False) for e in report['render']] + [(e, True) for e in report['collision']]
    if len(placed) != len(piece_members) or set(placed) != {e['name'] for e, _ in entries}:
        raise ValueError('MegaPark level pieces differ from the assembled render/collision roster')
    meshes = {name: _load(unreal, context, slot, unreal.StaticMesh) for name, slot in placed.items()}
    if any(_path(m) != f'{ROOT}/Meshes/{name}' for name, m in meshes.items()):
        raise ValueError('MegaPark level pieces must be the finished /Game/MegaPark/Meshes packages')
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    if not world:
        raise ValueError('Could not create park level')
    ue = original(context, unreal, ('ue',))['ue']
    for entry, collision in entries:
        actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, ue(entry['native_origin']))
        actor.set_actor_label(entry['name']); actor.set_folder_path('OriginalCollision' if collision else 'OriginalGeometry')
        actor.set_mobility(unreal.ComponentMobility.STATIC)
        component = actor.static_mesh_component
        component.set_static_mesh(meshes[entry['name']])
        component.set_collision_profile_name('BlockAll' if collision else 'NoCollision')
        if collision:
            actor.set_actor_hidden_in_game(True); component.set_visibility(False)
            component.set_editor_property('cast_shadow', False)
    rails = []
    for source in report['rails']:
        rail = unreal.MegaParkRail()
        rail.set_editor_property('source_id', source['id']); rail.set_editor_property('closed', source['closed'])
        rail.set_editor_property('points', [ue(p) for p in source['points']])
        rail.set_editor_property('original_segments', source['original_segments']); rails.append(rail)
    ground = ue(report['spawn']['position']); yaw = report['spawn']['heading_degrees']
    layout = unreal.MegaParkLayoutData()
    for k, v in dict(source_manifest_hash=report['source_sha256'], rails=rails, spawn_ground=ground, spawn_yaw=yaw).items():
        layout.set_editor_property(k, v)
    park = actors.spawn_actor_from_class(unreal.MegaParkLayout, unreal.Vector())
    park.set_actor_label('ParkLayout'); park.set_editor_property('layout', layout)
    start = actors.spawn_actor_from_class(unreal.PlayerStart, ground + unreal.Vector(0, 0, 80), unreal.Rotator(yaw=yaw))
    start.set_actor_label('UpperDeckStart')
    sun = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(33000, -71000, 25000), unreal.Rotator(pitch=-35, yaw=-40))
    sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.light_component.set_editor_property('intensity', 3.)
    sun.light_component.set_editor_property('atmosphere_sun_light', True)
    actors.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector())
    sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector())
    sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property('real_time_capture', True)
    volume = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector())
    volume.set_editor_property('unbound', True)
    settings = volume.get_editor_property('settings')
    for k, v in dict(override_auto_exposure_method=True, auto_exposure_method=unreal.AutoExposureMethod.AEM_MANUAL,
                     override_auto_exposure_bias=True, auto_exposure_bias=0.,
                     override_auto_exposure_apply_physical_camera_exposure=True, auto_exposure_apply_physical_camera_exposure=False,
                     override_motion_blur_amount=True, motion_blur_amount=0.).items():
        settings.set_editor_property(k, v)
    volume.set_editor_property('settings', settings)
    if not unreal.EditorLoadingAndSavingUtils.save_map(world, LEVEL):
        raise ValueError('Failed to save native map')
    return world


def _derived(value):
    if isinstance(value,dict) and set(value)=={'derived_items'}:value=value['derived_items']
    if not isinstance(value,dict) or set(value)!={'root','members'} or not isinstance(value['members'],list):raise ValueError('MegaPark requires actual expanded derived members')
    rows=value['members']
    if any(not isinstance(row,dict) or set(row)!={'piece','root','slot'} for row in rows) or len({r['piece'] for r in rows})!=len(rows) or len({r['slot'] for r in rows})!=len(rows):raise ValueError('Duplicate MegaPark derived member')
    return rows


def texture(context,unreal,args):
    tid=args['tid'];name='T_'+tid[2:];package=ROOT+'/Textures/'+name
    _owned(context,package);_fresh(unreal,package)
    source=_selected(context,'raw')
    if source!='/Game/_Raw/MegaPark/Textures/'+name:raise ValueError('MegaPark texture raw owner differs')
    folder=_data(context,args['roles'],directory=True);path=folder/(name+'.json')
    if {p.name for p in folder.iterdir()}!={name+'.json'} or path.is_symlink():raise ValueError('MegaPark selected texture role member differs')
    spec=json.loads(path.read_bytes(),object_pairs_hook=_pairs)
    if set(spec)!={'tid','roles'} or spec['tid']!=tid or not isinstance(spec['roles'],list) or len(set(spec['roles']))!=len(spec['roles']) or set(spec['roles'])-set(ALIASES):raise ValueError('Invalid MegaPark actual texture roles')
    roles=set(spec['roles']);normal=bool(roles&{'normal','detail'});linear=bool(roles&{'lightmap','normal','detail','specular'})
    raw=_load(unreal,context,'raw',unreal.Texture);asset=unreal.EditorAssetLibrary.duplicate_asset(source,package)
    if not isinstance(asset,unreal.Texture) or asset is raw or _path(asset)!=package:raise ValueError('MegaPark texture duplicate failed')
    asset.set_editor_property('srgb',not linear and not normal)
    asset.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP if normal else unreal.TextureCompressionSettings.TC_DEFAULT)
    if 'lightmap' in roles:
        asset.set_editor_property('address_x',unreal.TextureAddress.TA_CLAMP);asset.set_editor_property('address_y',unreal.TextureAddress.TA_CLAMP)
    from atelier import native_packages
    native_packages.save(asset,unreal.EditorAssetLibrary,context.content_dir)
    return asset


ACTIONS = {'parent': parent, 'instance': instance, 'mesh': mesh, 'level': level, 'texture':texture}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-megapark-bodies
    Each job MUST author or finish exactly its declared MegaPark package from
    declared inputs with import_megapark.py's own parent graph, instance
    parameters, mesh finishing and level layout: a spec equal to its declared
    member, a fresh duplicate of each raw piece with exact triangles, slots and
    bounds, and only finished pieces placed. It MUST NOT run the original top
    level, cache, retirement or receiving reports. Declared audit outputs MUST
    come from the native triangle dumper and actual checked mesh properties.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported MegaPark action')
    if args['action'] in ('mesh','texture'):
        if params.get('op') != 'finish' or params.get('kind') != ('static_mesh' if args['action']=='mesh' else 'texture'):
            raise ValueError('MegaPark pieces are finished by unreal.finish(static_mesh)')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected MegaPark author parameters')
    return ACTIONS[args['action']](context, unreal, args)
