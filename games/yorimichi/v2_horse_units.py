"""Replace unreal.horses (Scripts/import_horses.py) by native units per /Game/Horses package (world/horse_v2.py).

world.horses writes each breed's body with its turn clips (turns/<slug>.glb) and its manifest (contacts, fps); the
library (assets/horses) commits the tack GLBs, coat masks and variants. Per breed, from those actual sources:
- FileSet groups (world/horse_members_v2.py): ``clips`` (one-animation upright body views), ``images`` (the body's
  and tack's glTF images), ``materials`` (their glTF materials), each member selected by one child with its
  followers: a clip's raw glTF animation on SKEL_Horse_<Breed> and its finish; an image's raw texture and finish; a
  material's instance;
- one views unit with the fixed owners' GLB views: the body and each committed tack set's saddle and reins;
- fixed units: SK/SKEL_Horse_<Breed> and every SK_Horse_<Breed>_<Part>_<sid> on that skeleton.
Shared: the four masters (the original make_*_master), the coat masks and variants, and the record writing
Content/Data/horses/roster.json and horses/unreal_import.json. ``natives = {compression: {unit, item, package}}``.
"""
from copy import deepcopy
import json
from pathlib import Path

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import _modules, _output
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/horse_v2.py'
BODY = GAME + '/world/horse_members_v2.py'
REFERENCE_BODY = GAME + '/world/reference_members_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_horses.py'
HORSE_DATA = GAME + '/unreal/Scripts/horse_data.py'
COMPRESSION_SCRIPT = GAME + '/unreal/Scripts/animation_compression.py'
ASSETS = GAME + '/assets/horses'
LIBRARY = ASSETS + '/manifest.json'
VARIANTS = ASSETS + '/coats/variants/manifest.json'
BUILDER = ASSETS + '/build.py'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
OUT = 'build/yorimichi/horses'
DEST = '/Game/Horses'
ROSTER_FILE = GAME + '/unreal/Content/Data/horses/roster.json'
REPORT_FILE = OUT + '/unreal_import.json'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
MASTERS = {'coat': 'M_HorseCoat', 'hair': 'M_HorseHair', 'tack': 'M_HorseTack', 'tack_masked': 'M_HorseTackMasked'}
PARTS = ('Saddle', 'Reins')
RECIPE_OP = {'kind': 'recipe.python', 'version': '1'}


def _body(root):
    import importlib.util
    spec = importlib.util.spec_from_file_location('horse_members_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _call(root, name, defaults):
    function = getattr(_body(root), name); function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / GAME / 'world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def _file(name, path):
    return {'role': 'content', 'name': name, 'source': {'kind': 'file', 'path': path}}


def token(slug, kind, follower, item):
    return {'derived_items': {'root': f'build/v2-derived/horses/{slug}/{kind}', 'templates': [
        {'producer': f'horses.{slug}.members.{kind}', 'group': 'members', 'unit_prefix': f'unreal.horses.{slug}.{kind}',
         'follower': follower, 'item': item}]}}


def variant_name(variant):
    """import_horses' coat variant texture name."""
    return 'T_CoatVariant_' + variant['id'].replace('-', '_')


def _check(by_id, library):
    importer, producer = by_id.get('unreal.horses'), by_id.get('world.horses')
    commands = (importer or {}).get('commands') or [{}]
    if (not importer or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL} or commands[0].get('marker') != 'HORSES IMPORT COMPLETE'
            or commands[0].get('args') or commands[0].get('env') or importer.get('products')
            or [str(o) for o in importer['outputs']] != [REPORT_FILE, ROSTER_FILE]):
        raise Unsupported('unreal.horses differs from the original import_horses.py target')
    if not producer or producer['commands'][0].get('script') != {'path': BUILDER}:
        raise Unsupported('world.horses differs from the original assets/horses/build.py')
    outputs = [str(o) for o in producer['outputs']]
    expected = [f'{OUT}/manifest.json', *(f'{OUT}/turns/{slug}.glb' for slug in library['breeds'])]
    if outputs != expected:
        raise Unsupported('world.horses outputs differ from its manifest and one turns GLB per committed breed')
    return producer['id'], {path: (f'output{i}', f'outputs/{i}.tree.tar') for i, path in enumerate(outputs)}


def horse_units(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] cold-horse-native-units
    unreal.horses MUST become one unit per /Game/Horses package and its record,
    from the actual world.horses outputs and the committed library: each breed's
    generated clips, images and materials as FileSet members whose owners consume
    only their own narrow member view; the body and every committed tack set as
    fixed owners on the breed skeleton; the masters by the original functions.
    Consumers MUST bind actual derived Items, never invented IDs; the original top
    level, its directory delete and registry scans never run.
    """
    root = Path(checkout).resolve()
    by_id = {row['id']: row for row in rows}
    library = json.loads((root / LIBRARY).read_bytes())
    variants = json.loads((root / VARIANTS).read_bytes())['variants']
    producer_id, produced = _check(by_id, library)
    compression = (natives or {}).get('compression')
    if not isinstance(compression, dict) or not {'unit', 'item', 'package'} <= set(compression) or compression['package'] != COMPRESSION:
        raise Unsupported('missing the shared CharacterCompression owner Item')
    scanner = ImportScanner()
    recipe_code = set()
    for source in (BODY, REFERENCE_BODY, HORSE_DATA, RECIPE, EMITTER):
        recipe_code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(
            root / source, (root / 'platform/studio', root / GAME / 'world', root / GAME / 'unreal/Scripts')))
    recipe_code = sorted(recipe_code | {BODY, REFERENCE_BODY, HORSE_DATA})
    code = {*_code(root), SCRIPT, ORIGINAL, HORSE_DATA, COMPRESSION_SCRIPT}
    for source in (HORSE_DATA, COMPRESSION_SCRIPT):
        code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(
            root / source, (root / GAME / 'unreal/Scripts', root / 'platform/studio')))
    code = sorted(code)
    ops_code, editor = list(_code(root)), _modules(root, [])[0]
    units, staged, packages, requirements, templates, groups = [], {}, {}, {}, [], {}

    def add(unit, inputs, roots=None):
        unit['inputs'] = inputs
        if roots:
            unit['params']['input_roots'] = roots
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if unit['op']['kind'] != 'recipe.python':
            requirements[unit['id']] = editor

    def texture(unit_id, package, source, raw_package):
        add({'id': unit_id + '.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_package},
             'outputs': [_output('raw_texture', raw_package, 'RawTexture', store=True)]}, [_file('source', source)])
        add({'id': unit_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                        'package_sources': {'raw': raw_package}, 'properties': {}},
             'outputs': [_output('texture', package, 'Texture')]}, [_item('raw', unit_id + '.raw', 'raw_texture')])
        packages[package] = {'unit': unit_id, 'item': 'texture', 'package': package}
        return unit_id

    masks = {mask: texture(f'unreal.horses.mask.{mask}', f'{DEST}/Coats/Masks/T_Coat_{mask}_Mask',
                           f'{ASSETS}/coats/T_Coat_{mask}_Mask.png', f'/Game/_Raw/Horses/Coats/Masks/T_Coat_{mask}_Mask')
             for mask in library['coat_masks']}
    if 'Solid' not in masks:
        raise Unsupported('The coat master needs the committed Solid coat mask')
    coat_variants = {v['id']: texture(f'unreal.horses.variant.{v["id"]}', f'{DEST}/Coats/Variants/{variant_name(v)}',
                                      f'{ASSETS}/coats/variants/{v["file"]}', f'/Game/_Raw/Horses/Coats/Variants/{variant_name(v)}')
                     for v in variants}
    for key, name in MASTERS.items():
        unit_id, package = f'unreal.horses.master.{name}', f'{DEST}/{name}'
        mask = [_item('mask', masks['Solid'], 'texture')] if key == 'coat' else []
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': 'master', 'key': key, **({'mask': 'mask'} if mask else {})}, 'settings': []},
             'outputs': [_output('asset', package, 'Material')]}, mask)
        packages[package] = {'unit': unit_id, 'item': 'asset', 'package': package}
    master_inputs = [_item('master_' + key, f'unreal.horses.master.{name}', 'asset') for key, name in MASTERS.items()]
    member_root = {'archive_member': 'member.tree.tar', 'name': 'member'}
    meta_root = {'archive_member': 'meta.tree.tar', 'name': 'meta'}
    views_root = {'archive_member': 'views.tree.tar', 'name': 'views'}
    breeds = {}
    for slug, breed in library['breeds'].items():
        name = breed['name']
        folder, materials_folder = f'{DEST}/{name}', f'{DEST}/{name}/Materials'
        body_path = f'{OUT}/turns/{slug}.glb'
        body_item, body_archive = produced[body_path]
        tack = [(part, sid) for sid in library['tack_sets'] for part in PARTS]
        sources = [_item('body', producer_id, body_item), _file('library', LIBRARY),
                   *(_file(f'tack_{part}_{sid}', f'{ASSETS}/{slug}/tack/{part}_{sid}.glb') for part, sid in tack)]
        sources[0]['whole'] = "The breed's complete body and committed tack check before any member is selected."
        paths = {body_path: 'inputs/body/' + body_archive, LIBRARY: 'inputs/library',
                 **{f'{ASSETS}/{slug}/tack/{part}_{sid}.glb': f'inputs/tack_{part}_{sid}' for part, sid in tack}}
        args = (root / LIBRARY, slug, root / body_path, root / ASSETS / slug, root / HORSE_DATA)
        for kind in ('clips', 'images', 'materials'):
            generated, unit_id = f'generated/horses/{slug}/{kind}', f'horses.{slug}.members.{kind}'
            contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                        'adapter_version': 'd2.file-set/1', 'parent': f'Horse_{name}_{kind}', 'encoding': 'file_set',
                        'class': 'Data', 'logical_namespace': f'/Internal/Horses/{name}/{kind}', **LIMITS}
            add({'id': unit_id, 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
                 'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': dict(paths), 'verify': None,
                     'commands': [_call(root, 'project', (*args, root / generated, kind))],
                     'outputs': [{'path': generated, 'kind': 'tree', 'file': 'members.tree.tar', 'required': True}],
                     'file_group': {'source': generated, 'parent': f'Horse_{name}_{kind}', 'extensions': ['.json']}}},
                 'outputs': [{'id': 'archive', 'logical_path': f'/Internal/Horses/{name}/{kind}', 'class': 'Data',
                              'destination': 'store', 'files': [{'path': 'members.tree.tar', 'required': True}]}],
                 'output_groups': [contract]}, deepcopy(sources))
            groups[unit_id] = {'contract': contract, 'source': generated}
        views_id = f'horses.{slug}.views'
        add({'id': views_id, 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
             'params': {'recipe': {'version': 1, 'paths': dict(paths), 'verify': None,
                 'commands': [_call(root, 'views', (*args, root / f'generated/horses/{slug}/views'))],
                 'outputs': [{'path': f'generated/horses/{slug}/views', 'kind': 'tree', 'file': 'views.tree.tar', 'required': True}]}},
             'outputs': [{'id': 'views', 'logical_path': f'/Internal/Horses/{name}/Views', 'class': 'Data',
                          'destination': 'store', 'files': [{'path': 'views.tree.tar', 'required': True}]}]}, deepcopy(sources))
        images, materials, clips = (token(slug, 'images', 1, 'texture'), token(slug, 'materials', 0, 'asset'),
                                    token(slug, 'clips', 1, 'animation'))
        mesh_id = f'unreal.horses.{slug}.mesh'

        def template(kind, followers, files=('member', 'meta')):
            templates.append({'producer': f'horses.{slug}.members.{kind}', 'group': 'members',
                'unit_prefix': f'unreal.horses.{slug}.{kind}', 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
                'derive_payload': False, 'payload_slot': 'payload', 'staged_path': 'inputs/payload', 'output_class': 'Data',
                'logical_namespace': f'/Internal/Horses/{name}/Selected/{kind}',
                'files': [{'path': f + '.tree.tar', 'required': True} for f in files],
                'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
                    'commands': [_call(root, 'select', (root / 'selected', root / 'member', root / 'meta', '$piece'))],
                    'outputs': [{'path': f, 'kind': 'tree', 'file': f + '.tree.tar', 'required': True} for f in files]}},
                'followers': [{'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}}
                              for unit in followers]})
        raw_texture = f'/Game/_Raw/Horses/{name}/Textures/T_$piece'
        template('images', [
            {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'inputs': [_item('source', '$export', 'asset')],
             'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_texture,
                        'input_roots': {'source': dict(member_root)}},
             'outputs': [_output('raw_texture', raw_texture, 'RawTexture', store=True)]},
            {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'inputs': [_item('raw', '$previous', 'raw_texture')],
             'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': f'{folder}/Textures/T_$piece',
                        'package_sources': {'raw': raw_texture}, 'properties': {}},
             'outputs': [_output('texture', f'{folder}/Textures/T_$piece', 'Texture')]}])
        template('materials', [
            {'id': '$export.author', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'inputs': [_item('meta', '$export', 'asset'), *deepcopy(master_inputs)],
             'params': {'input_roots': {'meta': dict(meta_root)}, 'settings': [],
                        'args': {'action': 'instance', 'name': '$piece', 'meta': 'meta', 'folder': materials_folder,
                                 'hair_colour': list(breed['hair_colour']),
                                 'masters': {key: 'master_' + key for key in MASTERS}, 'images': deepcopy(images)}},
             'outputs': [_output('asset', f'{materials_folder}/MI_$piece', 'MaterialInstance')]}], files=('meta',))
        raw_clip = f'/Game/_Raw/Horses/{name}/Clips/$piece'   # raw glTF: the destination names the one animation
        template('clips', [
            {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'inputs': [_item('source', '$export', 'asset'), _item('skeleton', mesh_id, 'skeleton')],
             'params': {'op': 'raw_import', 'kind': 'animation', 'source': 'source', 'destination': raw_clip,
                        'skeleton': 'skeleton', 'input_roots': {'source': dict(member_root)}},
             'outputs': [_output('raw_animation', raw_clip, 'RawAnimation', store=True)]},
            {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'inputs': [_item('raw', '$previous', 'raw_animation'), _item('skeleton', mesh_id, 'skeleton'),
                        _item('compression', compression['unit'], compression['item']), _item('meta', '$export', 'asset')],
             'params': {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': f'{folder}/A_Horse_{name}_$piece',
                        'input_roots': {'meta': dict(meta_root)},
                        'args': {'action': 'clip', 'name': '$piece', 'meta': 'meta', 'skeleton': 'skeleton',
                                 'compression': 'compression'}},
             'outputs': [_output('animation', f'{folder}/A_Horse_{name}_$piece', 'Animation')]}])
        owner = f'SK_Horse_{name}'
        raw_body = f'/Game/_Raw/Horses/{name}/{owner}'
        mesh, skeleton = f'{folder}/{owner}', f'{folder}/SKEL_Horse_{name}'
        add({'id': f'unreal.horses.{slug}.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS,
             'code': ops_code, 'params': {'op': 'raw_import', 'kind': 'skeletal_mesh', 'source': 'source', 'destination': raw_body,
                                          'create_physics_asset': False, 'source_member': owner},
             'outputs': [_output('raw_mesh', raw_body, 'RawSkeletalMesh', store=True),
                         _output('raw_skeleton', raw_body + '_Skeleton', 'Skeleton', store=True)]},
            [_item('source', views_id, 'views')], {'source': dict(views_root)})
        add({'id': mesh_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': mesh,
                        'partners': {'skeleton': skeleton},
                        'args': {'action': 'mesh', 'owner': owner, 'material_folder': materials_folder,
                                 'materials': deepcopy(materials)}},
             'outputs': [_output('mesh', mesh, 'SkeletalMesh'), _output('skeleton', skeleton, 'Skeleton')]},
            [_item('raw', f'unreal.horses.{slug}.raw', 'raw_mesh'), _item('raw_skeleton', f'unreal.horses.{slug}.raw', 'raw_skeleton')])
        derived = {'materials': deepcopy(materials), 'images': deepcopy(images)}
        packages[mesh] = {'unit': mesh_id, 'item': 'mesh', 'package': mesh,
                          'dependencies': [{'unit': mesh_id, 'item': 'skeleton', 'package': skeleton}], 'derived_dependencies': derived}
        packages[skeleton] = {'unit': mesh_id, 'item': 'skeleton', 'package': skeleton}
        entry = {'mesh': 'mesh_' + slug, 'skeleton': 'skeleton_' + slug, 'clips': deepcopy(clips), 'saddles': {}, 'reins': {}}
        record_inputs = [_item('mesh_' + slug, mesh_id, 'mesh'), _item('skeleton_' + slug, mesh_id, 'skeleton')]
        for part, sid in tack:
            tack_owner = f'{part}_{sid}'
            raw_tack, package = f'/Game/_Raw/Horses/{name}/Tack/{tack_owner}', f'{folder}/Tack/{tack_owner}/SK_Horse_{name}_{tack_owner}'
            raw_id, finish_id = f'unreal.horses.{slug}.tack.raw.{tack_owner}', f'unreal.horses.{slug}.tack.{tack_owner}'
            add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
                 'params': {'op': 'raw_import', 'kind': 'skeletal_mesh', 'source': 'source', 'destination': raw_tack,
                            'create_physics_asset': False, 'skeleton': 'skeleton', 'source_member': tack_owner},
                 'outputs': [_output('raw_mesh', raw_tack, 'RawSkeletalMesh', store=True)]},
                [_item('source', views_id, 'views'), _item('skeleton', mesh_id, 'skeleton')], {'source': dict(views_root)})
            add({'id': finish_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
                 'params': {'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': package,
                            'args': {'action': 'tack', 'owner': tack_owner, 'skeleton': 'skeleton',
                                     'material_folder': materials_folder, 'materials': deepcopy(materials)}},
                 'outputs': [_output('mesh', package, 'SkeletalMesh')]},
                [_item('raw', raw_id, 'raw_mesh'), _item('skeleton', mesh_id, 'skeleton')])
            packages[package] = {'unit': finish_id, 'item': 'mesh', 'package': package,
                                 'dependencies': [{'unit': mesh_id, 'item': 'skeleton', 'package': skeleton}],
                                 'derived_dependencies': deepcopy(derived)}
            slot = f'tack_{slug}_{tack_owner}'
            entry['saddles' if part == 'Saddle' else 'reins'][sid] = slot
            record_inputs.append(_item(slot, finish_id, 'mesh'))
        breeds[slug] = (entry, record_inputs)
    record_inputs = [_file('library', LIBRARY), _file('variants', VARIANTS), _item('built', producer_id, produced[f'{OUT}/manifest.json'][0]),
                     *(_item('master_' + key, f'unreal.horses.master.{name}', 'asset') for key, name in MASTERS.items()),
                     *(_item('mask_' + mask, unit_id, 'texture') for mask, unit_id in masks.items()),
                     *(_item('variant_' + vid, unit_id, 'texture') for vid, unit_id in coat_variants.items()),
                     *(i for _, inputs in breeds.values() for i in inputs)]
    record_args = {'library': 'library', 'variants': 'variants', 'built': 'built',
                   'masters': {key: 'master_' + key for key in MASTERS},
                   'masks': {mask: 'mask_' + mask for mask in masks},
                   'coat_variants': {vid: 'variant_' + vid for vid in coat_variants},
                   'breeds': {slug: entry for slug, (entry, _) in breeds.items()}}
    # The data author serializes one JSON per job, so the installed roster and the stored report are two owners
    # over the same read closure.
    for item, logical, destination, file, installed in (
            ('roster', '/Game/_Data/horses/roster', 'checkout', {'path': 'data/roster.json', 'install_path': ROSTER_FILE}, ROSTER_FILE),
            ('report', '/Internal/Horses/Report', 'store', {'path': 'data/unreal_import.json'}, REPORT_FILE)):
        unit_id = 'unreal.horses.' + item
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': item, **deepcopy(record_args)}, 'settings': []},
             'outputs': [{'id': item, 'logical_path': logical, 'class': 'JsonData', 'destination': destination,
                          'files': [{**file, 'required': True}]}]},
            deepcopy(record_inputs), {'built': {'archive_member': produced[f'{OUT}/manifest.json'][1], 'name': 'manifest.json'}})
        packages[installed] = {'unit': unit_id, 'item': item}
    return {'units': units, 'staged_inputs': staged, 'content_slots': {i['name']: False for u in units for i in u['inputs']},
            'packages': packages, 'aliases': {'unreal.horses': tuple(u['id'] for u in units)},
            'module_requirements': requirements, 'templates': templates, 'groups': groups,
            'tokens': {slug: {kind: token(slug, kind, follower, item) for kind, follower, item in
                              (('clips', 1, 'animation'), ('images', 1, 'texture'), ('materials', 0, 'asset'))}
                       for slug in library['breeds']}}
