"""Cold train source projection and native package bodies, without the legacy main/registry scans."""
import ast
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ORIGINAL = 'games/yorimichi/unreal/Scripts/import_belmonte_train.py'
ROOT = '/Game/BelmonteTrain'
ROSTER, REPORT = 'data/service.json', 'data/import-report.json'
ROLES = {'BaseColor': ('pbrMetallicRoughness', 'baseColorTexture'),
         'MetallicRoughness': ('pbrMetallicRoughness', 'metallicRoughnessTexture'),
         'Normal': (None, 'normalTexture'), 'Occlusion': (None, 'occlusionTexture'), 'Emissive': (None, 'emissiveTexture'),
         'ClearCoat': ('extensions.KHR_materials_clearcoat', 'clearcoatTexture'),
         'ClearCoatRoughness': ('extensions.KHR_materials_clearcoat', 'clearcoatRoughnessTexture'),
         'ClearCoatNormal': ('extensions.KHR_materials_clearcoat', 'clearcoatNormalTexture')}


def name(value):
    if not isinstance(value, str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]*', value):
        raise ValueError('Noncanonical train member name')
    return value


def source(root, relative):
    path = Path(root) / relative
    if (not isinstance(relative, str) or Path(relative).is_absolute() or '\\' in relative
            or any(p in ('', '.', '..') for p in relative.split('/')) or path.is_symlink()
            or path.resolve() != path.absolute() or not path.is_file()):
        raise ValueError('Missing or escaping train source')
    return path


def module(path, label):
    spec = importlib.util.spec_from_file_location(label, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'


def blob(value):
    return {'bytes': base64.b64encode(value).decode('ascii'), 'sha256': hashlib.sha256(value).hexdigest()}


def pbr(record):
    """Finite metallic/roughness SDK mapping; unsupported shader models refuse rather than silently degrade."""
    extensions = record.get('extensions', {})
    if set(extensions) - {'KHR_materials_emissive_strength', 'KHR_materials_ior', 'KHR_materials_specular', 'KHR_materials_clearcoat'}:
        raise ValueError('Unsupported train glTF material extension')
    specular = extensions.get('KHR_materials_specular', {})
    if 'specularTexture' in specular or 'specularColorTexture' in specular:
        raise ValueError('Unsupported train textured specular extension')
    alpha = record.get('alphaMode', 'OPAQUE')
    if alpha not in ('OPAQUE', 'MASK', 'BLEND'):
        raise ValueError('Unsupported train alpha mode')
    return ('MI_ClearCoat_' if 'KHR_materials_clearcoat' in extensions else 'MI_Default_') + alpha.title() + ('_DS' if record.get('doubleSided', False) else '')


def members(train, bake):
    """Verify the original complete bake/service before exposing any native member."""
    from atelier.gltf import glb_parts
    train = Path(train)
    service = json.loads(source(train, 'service/service.json').read_bytes())
    module(bake, 'train_bake_projection').preflight_service(train, service)
    manifest = json.loads(source(train, 'manifest.json').read_bytes())
    result = {'meshes': {}, 'materials': {}, 'images': {}, 'record': {}}
    owners = []
    for vehicle in service['consist']['vehicles']:
        owners.append((vehicle['name'], vehicle['levels'], {'kind': 'vehicle', 'spec': vehicle,
                      'screen_sizes': service['render']['screen_sizes'], 'expected': manifest['coaches'].get(vehicle['id'], {})}))
        for door in vehicle['doors']:
            for leaf in door['leaves']:
                if leaf.get('glb'):
                    key = leaf['mesh'].rsplit('/', 1)[-1].split('.')[0]
                    owners.append((key, [leaf['glb']], {'kind': 'door', 'spec': leaf, 'vehicle': vehicle['name'], 'screen_sizes': [1.]}))
    for aid, spec in service['furniture'].items():
        key = spec['mesh'].rsplit('/', 1)[-1].split('.')[0]
        owners.append((key, ['furniture/' + r['glb'] for r in spec['levels']],
                       {'kind': 'furniture', 'asset': aid, 'spec': spec, 'screen_sizes': [r['screen_size'] for r in spec['levels']]}))
    for owner, paths, meta in owners:
        name(owner)
        if owner.casefold() in {k.casefold() for k in result['meshes']} or not 1 <= len(paths) <= 3:
            raise ValueError('Aliased train mesh or unsupported LOD count')
        payloads = [source(train, path).read_bytes() for path in paths]
        gltf, binary = glb_parts(payloads[0])
        if gltf.get('animations') or gltf.get('skins'):
            raise ValueError('Train sources must be static meshes')
        slots = {}
        # Doors reuse vehicle slots where present; the original importer retains unmatched leaf materials.
        material_owner = meta.get('vehicle', owner)
        for index, record in enumerate(gltf.get('materials', [])):
            slot = record.get('name') or f'material{index}'
            key = name(material_owner + '_' + re.sub('[^A-Za-z0-9_]', '_', slot))
            slots[slot] = key
            if meta['kind'] == 'door':
                if key in result['materials']:
                    continue
                key = name(owner + '_' + re.sub('[^A-Za-z0-9_]', '_', slot))
                slots[slot] = key
            if key.casefold() in {k.casefold() for k in result['materials']}:
                raise ValueError('Aliased train material member')
            parent = pbr(record)
            images = {}
            for role, (section, field) in ROLES.items():
                container = record
                for part in section.split('.') if section else (): container = container.get(part, {})
                reference = container.get(field)
                if reference is None:
                    continue
                texture = gltf['textures'][reference['index']]
                image = gltf['images'][texture['source']]
                if image.get('mimeType') not in ('image/png', 'image/jpeg') or 'bufferView' not in image:
                    raise ValueError('Train images must be embedded PNG/JPEG')
                view = gltf['bufferViews'][image['bufferView']]
                offset = view.get('byteOffset', 0); data = binary[offset:offset + view['byteLength']]
                if len(data) != view['byteLength']:
                    raise ValueError('Truncated train image')
                image_key = name(key + '_' + role)
                sampler = gltf.get('samplers', [])[texture['sampler']] if 'sampler' in texture else {}
                if set(reference.get('extensions', {})) - {'KHR_texture_transform'}:
                    raise ValueError('Unsupported train texture extension')
                images[role] = {'piece': image_key, 'reference': reference, 'sampler': sampler}
                result['images'][image_key] = {'name': image_key, 'role': role, 'mime': image['mimeType'], 'sampler': sampler, **blob(data)}
            result['materials'][key] = {'name': key, 'slot': slot, 'record': record, 'parent': parent,
                'ism': meta['kind'] == 'furniture', 'two_sided': meta['kind'] == 'furniture' and meta['spec'].get('two_sided', False),
                'images': images}
        result['meshes'][owner] = {'name': owner, **meta, 'levels': [blob(data) for data in payloads],
            'sources': {Path(path).name: hashlib.sha256(data).hexdigest() for path, data in zip(paths, payloads)}, 'materials': slots}
    result['record']['Record'] = {'name': 'Record', 'service': service, 'sources': {k: v['sources'] for k, v in result['meshes'].items()}}
    if not all(result[k] for k in result):
        raise ValueError('Train must expose meshes, materials, images and service')
    return result


def project(train=None, bake=None, output=None, kind=None):
    values = members(train, bake)
    for group, role, count in [('vehicles', 'vehicle', 3), ('doors', 'door', 1), ('furniture1', 'furniture', 1), ('furniture2', 'furniture', 2)]:
        values[group] = {k: v for k, v in values['meshes'].items() if v['kind'] == role and len(v['levels']) == count}
    if kind not in values or Path(output).exists():
        raise ValueError('Train projection needs a fresh supported group')
    Path(output).mkdir(parents=True)
    for key, value in sorted(values[kind].items()):
        (Path(output) / (key + '.json')).write_text(encode(value))


def select(selected=None, output=None, piece=None):
    root, output = Path(selected), Path(output)
    paths = list(root.iterdir())
    if len(paths) != 1 or paths[0].name != name(piece) + '.json' or paths[0].is_symlink() or output.exists():
        raise ValueError('Train selection must be exactly its declared member')
    value = json.loads(paths[0].read_bytes())
    if value['name'] != piece:
        raise ValueError('Train member identity mismatch')
    output.mkdir(parents=True)
    def unpack(record, path):
        data = base64.b64decode(record['bytes'], validate=True)
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Corrupt train member bytes')
        path.write_bytes(data)
    if 'levels' in value:
        for level in range(len(value['levels'])):
            folder = output / f'level{level}'; folder.mkdir()
            unpack(value['levels'][level], folder / 'source.glb')
    if 'bytes' in value:
        folder = output / 'image'; folder.mkdir()
        primary = 'source.png' if value['mime'] == 'image/png' else 'source.jpg'
        unpack(value, folder / primary)
        (folder / 'export.json').write_text(encode({'primary': primary, 'sha256': value['sha256']}))
    meta = {k: v for k, v in value.items() if k not in ('levels', 'bytes', 'sha256')}
    if 'levels' in value: meta['count'] = len(value['levels'])
    (output / 'meta.json').write_text(encode(meta))


def data(context, slot):
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Train data must be staged job-local input')
    return json.loads((root / 'meta.json').read_bytes())


def roster(value):
    rows = value.get('derived_items', {}).get('members') if isinstance(value, dict) else None
    if not isinstance(rows, list) or len({r['piece'] for r in rows}) != len(rows):
        raise ValueError('Unresolved or aliased train native roster')
    return {r['piece']: r['slot'] for r in rows}


def load(context, unreal, slot):
    values = context.packages.get(slot)
    values = [values] if isinstance(values, str) else values
    if not isinstance(values, (list, tuple)) or len(values) != 1:
        raise ValueError('Train input must select exactly one native package')
    asset = unreal.EditorAssetLibrary.load_asset(values[0])
    if asset is None or asset.get_path_name().split('.')[0] != values[0]:
        raise ValueError('Train native input failed to load')
    return asset


def save(unreal, asset, expected):
    if asset is None or asset.get_path_name().split('.')[0] != expected:
        raise ValueError('Train native output identity mismatch')
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, False):
        raise RuntimeError('Train native save failed: ' + expected)
    return asset


def original(context, unreal, names):
    path = Path(context.job_dir) / ORIGINAL
    nodes = [n for n in ast.parse(path.read_bytes()).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in nodes} != set(names):
        raise ValueError('Original train importer function drift')
    scope = {'unreal': unreal, 'ROOT': ROOT, 'E': unreal.EditorAssetLibrary,
             'AT': unreal.AssetToolsHelpers.get_asset_tools(), 'hashlib': hashlib, 'Path': Path}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), ORIGINAL, 'exec'), scope)
    return scope


def material(context, unreal, args):
    meta = data(context, args['meta']); key = name(args['name'])
    if meta['name'] != key or pbr(meta['record']) != meta['parent']:
        raise ValueError('Train material differs from its selected source')
    E, M = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
    package, parent_path = f'{ROOT}/Materials/MI_{key}', f'{ROOT}/Materials/M_{key}'
    if set(context.outputs) != {package, parent_path}:
        raise ValueError('Train material owns exactly its instance and private master')
    default = E.load_asset('/InterchangeAssets/gltf/MaterialInstances/' + meta['parent'])
    if default is None:
        raise ValueError('SDK glTF material parent missing')
    parent = E.duplicate_asset(default.get_base_material().get_path_name(), parent_path)
    if meta['ism']:
        parent.set_editor_property('used_with_instanced_static_meshes', True)
    M.recompile_material(parent); save(unreal, parent, parent_path)
    instance = E.duplicate_asset(default.get_path_name(), package)
    M.set_material_instance_parent(instance, parent)
    r = meta['record']; p = r.get('pbrMetallicRoughness', {}); extensions = r.get('extensions', {})
    scalars = {'MetallicFactor': p.get('metallicFactor', 1.), 'RoughnessFactor': p.get('roughnessFactor', 1.),
               'NormalScale': r.get('normalTexture', {}).get('scale', 1.),
               'OcclusionStrength': r.get('occlusionTexture', {}).get('strength', 1.), 'AlphaCutoff': r.get('alphaCutoff', .5),
               'EmissiveStrength': extensions.get('KHR_materials_emissive_strength', {}).get('emissiveStrength', 1.),
               'IOR': extensions.get('KHR_materials_ior', {}).get('ior', 1.5),
               'SpecularFactor': extensions.get('KHR_materials_specular', {}).get('specularFactor', 1.)}
    coat = extensions.get('KHR_materials_clearcoat', {})
    if coat:
        scalars.update({'ClearCoatFactor': coat.get('clearcoatFactor', 0.),
                        'ClearCoatRoughnessFactor': coat.get('clearcoatRoughnessFactor', 0.),
                        'ClearCoatNormalScale': coat.get('clearcoatNormalTexture', {}).get('scale', 1.)})
    vectors = {'BaseColorFactor': p.get('baseColorFactor', [1., 1., 1., 1.]),
               'EmissiveFactor': [*r.get('emissiveFactor', [0., 0., 0.]), 1.],
               'SpecularColorFactor': [*extensions.get('KHR_materials_specular', {}).get('specularColorFactor', [1., 1., 1.]), 1.]}
    images = roster(args['images'])
    for absent in ('Specular', 'SpecularColor'):
        M.set_material_instance_static_switch_parameter_value(instance, 'bHas' + absent + 'Texture', False)
    for role in ROLES:
        entry = meta['images'].get(role)
        # The selected SDK default uses true static switches; explicitly disable absent maps.
        if not role.startswith('ClearCoat'):
            M.set_material_instance_static_switch_parameter_value(instance, 'bHas' + role + 'Texture', entry is not None)
            if M.get_material_instance_static_switch_parameter_value(instance, 'bHas' + role + 'Texture') != (entry is not None):
                raise ValueError('SDK glTF texture switch missing: ' + role)
        if entry is None: continue
        if entry['piece'] not in images: raise ValueError('Missing train texture owner')
        parameter = role + 'Texture'
        M.set_material_instance_texture_parameter_value(instance, parameter, load(context, unreal, images[entry['piece']]))
        ref, sampler = entry['reference'], entry['sampler']
        transform = ref.get('extensions', {}).get('KHR_texture_transform', {})
        scalars[parameter + '_TexCoord'] = transform.get('texCoord', ref.get('texCoord', 0))
        rotation = transform.get('rotation', 0.)
        scalars[parameter + '_Rotation'] = 6.283185307179586 - rotation if rotation < 0 else rotation
        vectors[parameter + '_OffsetScale'] = [*transform.get('offset', [0., 0.]), *transform.get('scale', [1., 1.])]
        tiling = {10497: 0., 33071: 1., 33648: 2.}
        vectors[parameter + '_TilingMethod'] = [tiling[sampler.get('wrapS', 10497)], tiling[sampler.get('wrapT', 10497)], 0., 0.]
    if 'KHR_materials_clearcoat' in extensions:
        enabled = any(role.startswith('ClearCoat') for role in meta['images'])
        M.set_material_instance_static_switch_parameter_value(instance, 'bHasClearCoatTexture', enabled)
        if M.get_material_instance_static_switch_parameter_value(instance, 'bHasClearCoatTexture') != enabled:
            raise ValueError('SDK clearcoat texture switch differs')
    for key_, value in scalars.items(): M.set_material_instance_scalar_parameter_value(instance, key_, float(value))
    for key_, value in vectors.items(): M.set_material_instance_vector_parameter_value(instance, key_, unreal.LinearColor(*value))
    if meta['two_sided']:
        overrides = instance.get_editor_property('base_property_overrides')
        overrides.set_editor_property('override_two_sided', True); overrides.set_editor_property('two_sided', True)
        instance.set_editor_property('base_property_overrides', overrides)
    M.update_material_instance(instance)
    return save(unreal, instance, package)


def mesh(context, unreal, args):
    meta = data(context, args['meta']); key = name(args['name'])
    if meta['name'] != key: raise ValueError('Train mesh identity mismatch')
    destination = ROOT + ('/Furniture/' if meta['kind'] == 'furniture' else '/Doors/' if meta['kind'] == 'door' else '/') + key
    if set(context.outputs) != {destination}: raise ValueError('Train mesh must own exactly its final package')
    E = unreal.EditorAssetLibrary
    asset = E.duplicate_asset(load(context, unreal, args['levels'][0]).get_path_name(), destination)
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    editor.remove_collisions(asset)
    for level in range(1, meta['count']):
        raw = load(context, unreal, args['levels'][level])
        if editor.set_lod_from_static_mesh(asset, level, raw, 0, True) != level:
            raise ValueError('Train LOD copy failed')
    if asset.get_num_lods() != meta['count']: raise ValueError('Train LOD count differs from source')
    if meta['count'] > 1 and not editor.set_lod_screen_sizes(asset, meta['screen_sizes'][:meta['count']]):
        raise ValueError('Train LOD screen size failure')
    materials = roster(args['materials'])
    for index, slot in enumerate(asset.get_editor_property('static_materials')):
        imported = str(slot.get_editor_property('imported_material_slot_name'))
        material_key = meta['materials'].get(imported)
        if material_key not in materials: raise ValueError('Missing original train material slot: ' + imported)
        asset.set_material(index, load(context, unreal, materials[material_key]))
    if meta['kind'] == 'vehicle':
        boxes = meta['spec']['collision']
        fn = original(context, unreal, ('box',))['box']
        count = unreal.BelmonteTrainImportLibrary.set_simple_boxes(asset, [fn(b) for b in boxes])
        if count != len(boxes): raise ValueError('Train collision box count mismatch')
        asset.set_editor_property('lod_for_collision', 0)
        expected = meta['expected'].get('triangles', {}).get('LOD0')
        if expected and abs(asset.get_num_triangles(0) - expected) > expected * .02:
            unreal.log_warning('BELMONTE TRAIN ' + key + ' triangle count differs from build')
    elif meta['kind'] == 'door':
        body = asset.get_editor_property('body_setup')
        if body: body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    return save(unreal, asset, destination)


def record(context, unreal, args):
    field = args.get('field')
    output = {'service': ROSTER, 'report': REPORT}.get(field)
    if output is None or context.outputs or tuple(context.data_outputs) != (output,):
        raise ValueError('Train data author owns exactly its one service or report JSON')
    metadata = data(context, args['meta'])
    service = metadata['service']; meshes = roster(args['meshes'])
    report = {'vehicles': {}, 'furniture': {}}
    for vehicle in service['consist']['vehicles']:
        asset = load(context, unreal, meshes[vehicle['name']]); bounds = asset.get_bounding_box()
        editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        report['vehicles'][vehicle['name']] = {'asset': asset.get_path_name(),
            'triangles': [asset.get_num_triangles(i) for i in range(asset.get_num_lods())],
            'boxes': len(vehicle['collision']), 'switchable': len(vehicle['switchable']),
            'screen_sizes': list(editor.get_lod_screen_sizes(asset)),
            'bounds': [[bounds.min.x, bounds.min.y, bounds.min.z], [bounds.max.x, bounds.max.y, bounds.max.z]],
            'sources': metadata['sources'][vehicle['name']], 'door_leaves': sum(bool(leaf.get('glb')) for d in vehicle['doors'] for leaf in d['leaves'])}
    for aid, spec in service['furniture'].items():
        key = spec['mesh'].rsplit('/', 1)[-1].split('.')[0]; asset = load(context, unreal, meshes[key])
        report['furniture'][aid] = {'asset': asset.get_path_name(),
            'triangles': [asset.get_num_triangles(i) for i in range(asset.get_num_lods())],
            'cull_cm': spec['cull_cm'], 'shadow': spec['shadow'], 'two_sided': spec.get('two_sided', False)}
    return {output: service if field == 'service' else report}


def run(context):
    """@cc [owner:fontanierh,label:correctness] finite-train-native-owners
    Native jobs MUST consume declared source/native Items, preserve original LOD,
    collision, door-slot and furniture PBR/ISM rules, and own every saved package.
    SDK materials MUST remain immutable; no legacy main, Content scan or deletion.
    """
    import unreal
    args = context.params['args']
    if args['action'] == 'texture':
        meta = data(context, args['meta']); destination = context.params['destination']
        if list(context.outputs) != [destination] or destination != ROOT + '/Textures/T_' + meta['name']:
            raise ValueError('Train texture owner mismatch')
        asset = unreal.EditorAssetLibrary.duplicate_asset(load(context, unreal, context.params['source']).get_path_name(), destination)
        asset.set_editor_property('srgb', meta['role'] in ('BaseColor', 'Emissive'))
        compression = 'TC_NORMALMAP' if meta['role'] in ('Normal', 'ClearCoatNormal') else 'TC_DEFAULT'
        asset.set_editor_property('compression_settings', getattr(unreal.TextureCompressionSettings, compression))
        asset.set_editor_property('flip_green_channel', meta['role'] in ('Normal', 'ClearCoatNormal'))
        sampler = meta.get('sampler', {})
        filter_name = {9728: 'TF_NEAREST', 9985: 'TF_BILINEAR', 9987: 'TF_TRILINEAR'}.get(sampler.get('minFilter'), 'TF_DEFAULT')
        asset.set_editor_property('filter', getattr(unreal.TextureFilter, filter_name))
        for axis, field in [('x', 'wrapS'), ('y', 'wrapT')]:
            address = {10497: 'TA_WRAP', 33071: 'TA_CLAMP', 33648: 'TA_MIRROR'}[sampler.get(field, 10497)]
            asset.set_editor_property('address_' + axis, getattr(unreal.TextureAddress, address))
        return save(unreal, asset, destination)
    if args['action'] == 'material': return material(context, unreal, args)
    if args['action'] == 'mesh': return mesh(context, unreal, args)
    if args['action'] == 'record': return record(context, unreal, args)
    if args['action'] == 'board':
        if list(context.outputs) != [ROOT + '/Materials/M_BT_BoardText']: raise ValueError('Board owns its one material')
        asset = original(context, unreal, ('board_text_material',))['board_text_material']()
        return save(unreal, asset, context.outputs[0])
    raise ValueError('Unsupported train native action')
