"""Replace unreal.adventure (Scripts/import_adventure.py) by native units per /Game/Adventure package (world/reference_v2.py).

characters.adventure exports one rig, Reference (glb/Reference.glb with its clips), and the committed sword and glider
(glb/ReferenceSword.glb, glb/ReferenceGlider.glb), with export.json. From its complete export Product:
- FileSet groups (world/reference_members_v2.py): ``clips`` (one-animation Reference views), ``images`` (the glTF
  images), ``materials`` (the glTF materials), each member selected by one child with its followers: a clip's raw
  glTF animation on SKEL_Reference and its finish; an image's raw texture and finish; a material's instance;
- one views unit with the fixed owners' GLB views: the Reference body, the static sword, the glider and its clip;
- fixed units: the two masters (original master()), SK/SKEL_Reference, SM_ReferenceSword, SK/SKEL_ReferenceGlider
  with A_ReferenceGlider_<clip>, and Data/adventure/reference.json.
Raw glTF skeletal and animation imports are Root's SDK seam (GLTF in place of FBX bytes, Interchange pipelines as
import_adventure.pipelines). ``natives = {compression: {unit, item, package}}``. ``reference`` is the ABI the
move sets consume: {skeleton, glide, equipment, record, export}.
"""
from copy import deepcopy
from pathlib import Path
import re
import tomllib

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import _modules, _output
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/reference_v2.py'
BODY = GAME + '/world/reference_members_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_adventure.py'
COMPRESSION_SCRIPT = GAME + '/unreal/Scripts/animation_compression.py'
ADVENTURE = GAME + '/assets/characters/adventure'
BAKE = ADVENTURE + '/bake.py'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
OUT = 'build/yorimichi/adventure'
DEST = '/Game/Adventure'
FOLDER = DEST + '/Reference'
MATERIALS, TEXTURES = FOLDER + '/Materials', FOLDER + '/Textures'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
RECORD_FILE = GAME + '/unreal/Content/Data/adventure/reference.json'
MASTERS = {False: 'M_AdventureCharacter', True: 'M_AdventureCharacterMasked'}
OWNERS = ('Reference', 'ReferenceSword', 'ReferenceGlider')
RECIPE_OP = {'kind': 'recipe.python', 'version': '1'}


def _body(root):
    import importlib.util
    spec = importlib.util.spec_from_file_location('reference_members_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _call(root, name, defaults):
    function = getattr(_body(root), name); function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / GAME / 'world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def glide(root):
    """moves.toml's Glide clip, the reference pose the move records fit the glider in (export.unreal_name)."""
    spec = tomllib.loads((root / ADVENTURE / 'moves.toml').read_text())
    return re.sub(r'[^A-Za-z0-9_]+', '_', spec['action']['Glide']['clip']).strip('_')


def token(kind, follower, item):
    return {'derived_items': {'root': f'build/v2-derived/reference/{kind}', 'templates': [
        {'producer': f'characters.adventure.members.{kind}', 'group': 'members', 'unit_prefix': f'unreal.adventure.{kind}',
         'follower': follower, 'item': item}]}}


def _export(row):
    paths = [f'{OUT}/export.json', f'{OUT}/glb']
    found = [i for i, p in enumerate(row['products']) if p['id'] == 'characters.adventure.export']
    if len(found) != 1 or [str(p) for p in row['products'][found[0]]['paths']] != paths or row['products'][found[0]]['optional_paths']:
        raise Unsupported('characters.adventure must own its complete export Product (export.json, glb)')
    index = found[0]
    return f'product{index}', {'export.json': f'products/{index}-0.tree.tar', 'glb': f'products/{index}-1.tree.tar'}


def reference_units(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] cold-reference-native-units
    unreal.adventure MUST become one unit per /Game/Adventure package and its record,
    from the actual complete characters.adventure export Product: generated clips,
    images and materials as FileSet members, each owner consuming only its own
    narrow member view; the masters by the original master(); the committed sword
    and glider as fixed owners. Consumers MUST bind actual derived Items, never
    invented IDs; the original top level, its delete and registry scans never run.
    """
    root = Path(checkout).resolve()
    by_id = {row['id']: row for row in rows}
    importer, producer = by_id.get('unreal.adventure'), by_id.get('characters.adventure')
    if (not importer or len(importer['commands']) != 1 or importer['commands'][0].get('kind') != 'UnrealScript'
            or importer['commands'][0].get('script') != {'path': ORIGINAL}):
        raise Unsupported('unreal.adventure differs from the original import_adventure.py target')
    if not producer or producer['commands'][0].get('script') != {'path': ADVENTURE + '/export.py'}:
        raise Unsupported('characters.adventure differs from the original adventure/export.py')
    compression = (natives or {}).get('compression')
    if not isinstance(compression, dict) or not {'unit', 'item', 'package'} <= set(compression) or compression['package'] != COMPRESSION:
        raise Unsupported('missing the shared CharacterCompression owner Item')
    export_item, archives = _export(producer)
    export_root = {'archive_member': archives['export.json'], 'name': 'export.json'}
    recipe_code = set()
    for source in (BODY, RECIPE, EMITTER):
        recipe_code.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(
            root / source, (root / 'platform/studio', root / GAME / 'world')))
    recipe_code = sorted(recipe_code | {BODY, BAKE})
    code = sorted({*_code(root), SCRIPT, ORIGINAL, *(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(
        root / COMPRESSION_SCRIPT, (root / GAME / 'unreal/Scripts', root / 'platform/studio'))), COMPRESSION_SCRIPT})
    ops_code = list(_code(root))
    units, staged, packages, requirements, templates, groups = [], {}, {}, {}, [], {}

    def add(unit, inputs, roots=None):
        unit['inputs'] = inputs
        if roots:
            unit['params']['input_roots'] = roots
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        # These bodies use Engine/editor classes only, never project C++ classes.

    def whole():
        value = _item('export', producer['id'], export_item)
        value['whole'] = 'The complete adventure export validates its one rig, clips and committed equipment.'
        return value
    paths = {f'{OUT}/export.json': 'inputs/export/' + archives['export.json'], f'{OUT}/glb': 'inputs/export/' + archives['glb']}
    args = (root / OUT / 'export.json', root / OUT / 'glb', root / BAKE)
    for kind in ('clips', 'images', 'materials'):
        folder, producer_id = f'generated/reference/{kind}', f'characters.adventure.members.{kind}'
        contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                    'adapter_version': 'd2.file-set/1', 'parent': f'Reference_{kind}', 'encoding': 'file_set', 'class': 'Data',
                    'logical_namespace': f'/Internal/Reference/{kind}', **LIMITS}
        add({'id': producer_id, 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
             'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': dict(paths), 'verify': None,
                 'commands': [_call(root, 'project', (*args, root / folder, kind))],
                 'outputs': [{'kind': 'tree', 'path': folder, 'file': 'members.tree.tar', 'required': True}],
                 'file_group': {'source': folder, 'parent': f'Reference_{kind}', 'extensions': ['.json']}}},
             'outputs': [{'id': 'archive', 'logical_path': f'/Internal/Reference/{kind}', 'class': 'Data',
                          'destination': 'store', 'files': [{'path': 'members.tree.tar', 'required': True}]}],
             'output_groups': [contract]}, [whole()])
        groups[producer_id] = {'contract': contract, 'source': folder}
    clip_name = tomllib.loads((root / ADVENTURE / 'moves.toml').read_text())['equipment']['glider']['clip']
    views_id = 'characters.adventure.views'
    add({'id': views_id, 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
         'params': {'recipe': {'version': 1, 'paths': dict(paths), 'verify': None,
             'commands': [_call(root, 'views', (*args, root / 'generated/reference/views', clip_name))],
             'outputs': [{'kind': 'tree', 'path': 'generated/reference/views', 'file': 'views.tree.tar', 'required': True}]}},
         'outputs': [{'id': 'views', 'logical_path': '/Internal/Reference/Views', 'class': 'Data', 'destination': 'store',
                      'files': [{'path': 'views.tree.tar', 'required': True}]}]}, [whole()])
    views_root = {'archive_member': 'views.tree.tar', 'name': 'views'}
    images, materials, clips = token('images', 1, 'texture'), token('materials', 0, 'asset'), token('clips', 1, 'animation')
    for masked, name in MASTERS.items():
        unit_id, package = f'unreal.adventure.master.{name}', f'{DEST}/{name}'
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': 'master', 'masked': masked}, 'settings': []},
             'outputs': [_output('asset', package, 'Material')]}, [])
        packages[package] = {'unit': unit_id, 'item': 'asset', 'package': package}
    master_inputs = [_item('master_' + str(m).lower(), f'unreal.adventure.master.{n}', 'asset') for m, n in MASTERS.items()]
    reference_mesh, reference_skeleton = f'{FOLDER}/SK_Reference', f'{FOLDER}/SKEL_Reference'
    mesh_id = 'unreal.adventure.mesh.Reference'

    def template(kind, followers, files=('member', 'meta')):
        templates.append({'producer': f'characters.adventure.members.{kind}', 'group': 'members',
            'unit_prefix': f'unreal.adventure.{kind}', 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
            'derive_payload': False, 'payload_slot': 'payload', 'staged_path': 'inputs/payload', 'output_class': 'Data',
            'logical_namespace': f'/Internal/Reference/Selected/{kind}',
            'files': [{'path': f + '.tree.tar', 'required': True} for f in files],
            'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
                'commands': [_call(root, 'select', (root / 'selected', root / 'member', root / 'meta', '$piece'))],
                'outputs': [{'kind': 'tree', 'path': f, 'file': f + '.tree.tar', 'required': True} for f in files]}},
            'followers': [{'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}}
                          for unit in followers]})
    member_root = {'archive_member': 'member.tree.tar', 'name': 'member'}
    meta_root = {'archive_member': 'meta.tree.tar', 'name': 'meta'}
    raw_texture = '/Game/_Raw/Adventure/Textures/T_$piece'
    template('images', [
        {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
         'inputs': [_item('source', '$export', 'asset')],
         'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_texture,
                    'input_roots': {'source': dict(member_root)}},
         'outputs': [_output('raw_texture', raw_texture, 'RawTexture', store=True)]},
        {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': ops_code,
         'inputs': [_item('raw', '$previous', 'raw_texture')],
         'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': f'{TEXTURES}/T_$piece',
                    'package_sources': {'raw': raw_texture}, 'properties': {}},
         'outputs': [_output('texture', f'{TEXTURES}/T_$piece', 'Texture')]}])
    template('materials', [
        {'id': '$export.author', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'inputs': [_item('meta', '$export', 'asset'), *deepcopy(master_inputs)],
         'params': {'input_roots': {'meta': dict(meta_root)}, 'settings': [],
                    'args': {'action': 'instance', 'name': '$piece', 'meta': 'meta', 'folder': MATERIALS,
                             'masters': {'false': 'master_false', 'true': 'master_true'}, 'images': deepcopy(images)}},
         'outputs': [_output('asset', f'{MATERIALS}/MI_$piece', 'MaterialInstanceConstant')]}], files=('meta',))
    raw_clip = '/Game/_Raw/Adventure/Reference/$piece'   # raw glTF: the destination names the one animation
    template('clips', [
        {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
         'inputs': [_item('source', '$export', 'asset'), _item('skeleton', mesh_id, 'skeleton')],
         'params': {'op': 'raw_import', 'kind': 'animation', 'source': 'source', 'destination': raw_clip,
                    'skeleton': 'skeleton', 'input_roots': {'source': dict(member_root)}},
         'outputs': [_output('raw_animation', raw_clip, 'RawAnimation', store=True)]},
        {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'inputs': [_item('raw', '$previous', 'raw_animation'), _item('skeleton', mesh_id, 'skeleton'),
                    _item('compression', compression['unit'], compression['item']), _item('meta', '$export', 'asset')],
         'params': {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': f'{FOLDER}/A_Reference_$piece',
                    'input_roots': {'meta': dict(meta_root)},
                    'args': {'action': 'clip', 'meta': 'meta', 'skeleton': 'skeleton', 'compression': 'compression'}},
         'outputs': [_output('animation', f'{FOLDER}/A_Reference_$piece', 'Animation')]}])

    def skeletal(owner, folder):
        raw_id, finish_id = f'unreal.adventure.raw.{owner}', f'unreal.adventure.mesh.{owner}'
        raw = f'/Game/_Raw/Adventure/{owner}/SK_{owner}'
        mesh, skeleton = f'{folder}/SK_{owner}', f'{folder}/SKEL_{owner}'
        add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': {'op': 'raw_import', 'kind': 'skeletal_mesh', 'source': 'source', 'destination': raw,
                        'create_physics_asset': False, 'source_member': owner},
             'outputs': [_output('raw_mesh', raw, 'RawSkeletalMesh', store=True),
                         _output('raw_skeleton', raw + '_Skeleton', 'Skeleton', store=True)]},
            [_item('source', views_id, 'views')], {'source': dict(views_root)})
        add({'id': finish_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': mesh,
                        'partners': {'skeleton': skeleton},
                        'args': {'action': 'mesh', 'owner': owner, 'material_folder': MATERIALS, 'materials': deepcopy(materials)}},
             'outputs': [_output('mesh', mesh, 'SkeletalMesh'), _output('skeleton', skeleton, 'Skeleton')]},
            [_item('raw', raw_id, 'raw_mesh'), _item('raw_skeleton', raw_id, 'raw_skeleton')])
        packages[mesh] = {'unit': finish_id, 'item': 'mesh', 'package': mesh,
                          'dependencies': [{'unit': finish_id, 'item': 'skeleton', 'package': skeleton}],
                          'derived_dependencies': {'materials': deepcopy(materials), 'images': deepcopy(images)}}
        packages[skeleton] = {'unit': finish_id, 'item': 'skeleton', 'package': skeleton}
        return finish_id, mesh, skeleton
    skeletal('Reference', FOLDER)
    glider_id, glider_mesh, glider_skeleton = skeletal('ReferenceGlider', FOLDER + '/Glider')
    raw_sword, sword = '/Game/_Raw/Adventure/ReferenceSword/SM_ReferenceSword', f'{FOLDER}/Sword/SM_ReferenceSword'
    add({'id': 'unreal.adventure.raw.ReferenceSword', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS,
         'code': ops_code, 'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_sword,
                                      'source_member': 'ReferenceSword'},
         'outputs': [_output('raw_mesh', raw_sword, 'RawStaticMesh', store=True)]},
        [_item('source', views_id, 'views')], {'source': dict(views_root)})
    add({'id': 'unreal.adventure.mesh.ReferenceSword', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT,
         'code': code, 'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': sword,
                                  'args': {'action': 'prop', 'owner': 'ReferenceSword', 'material_folder': MATERIALS,
                                           'materials': deepcopy(materials)}},
         'outputs': [_output('mesh', sword, 'StaticMesh')]},
        [_item('raw', 'unreal.adventure.raw.ReferenceSword', 'raw_mesh')])
    packages[sword] = {'unit': 'unreal.adventure.mesh.ReferenceSword', 'item': 'mesh', 'package': sword,
                       'derived_dependencies': {'materials': deepcopy(materials), 'images': deepcopy(images)}}
    # The glider's one clip: committed in moves.toml's [equipment]; its name is the export's.
    raw_glider_clip = f'/Game/_Raw/Adventure/ReferenceGlider/{clip_name}'
    glider_clip = f'{FOLDER}/Glider/A_ReferenceGlider_{clip_name}'
    add({'id': 'unreal.adventure.clip.raw.ReferenceGlider', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS,
         'code': ops_code, 'params': {'op': 'raw_import', 'kind': 'animation', 'source': 'source', 'skeleton': 'skeleton',
                                      'destination': raw_glider_clip, 'source_member': f'ReferenceGlider_{clip_name}'},
         'outputs': [_output('raw_animation', raw_glider_clip, 'RawAnimation', store=True)]},
        [_item('source', views_id, 'views'), _item('skeleton', glider_id, 'skeleton')], {'source': dict(views_root)})
    add({'id': 'unreal.adventure.clip.ReferenceGlider', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT,
         'code': code, 'params': {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': glider_clip,
                                  'args': {'action': 'clip', 'skeleton': 'skeleton', 'compression': 'compression',
                                           'compress': False}},
         'outputs': [_output('animation', glider_clip, 'Animation')]},
        [_item('raw', 'unreal.adventure.clip.raw.ReferenceGlider', 'raw_animation'), _item('skeleton', glider_id, 'skeleton'),
         _item('compression', compression['unit'], compression['item'])])
    packages[glider_clip] = {'unit': 'unreal.adventure.clip.ReferenceGlider', 'item': 'animation', 'package': glider_clip}
    record_id = 'unreal.adventure.record'
    add({'id': record_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'record', 'export': 'export', 'mesh': 'mesh', 'skeleton': 'skeleton',
                             'clips': deepcopy(clips), 'materials': deepcopy(materials), 'owners': list(OWNERS),
                             'equipment': {'sword': {'mesh': 'sword'}, 'glider': {'mesh': 'glider', 'clip': 'glider_clip'}}},
                    'settings': []},
         'outputs': [{'id': 'record', 'logical_path': '/Game/_Data/adventure/reference', 'class': 'JsonData',
                      'destination': 'checkout', 'files': [{'path': 'data/reference.json', 'install_path': RECORD_FILE,
                                                            'required': True}]}]},
        [_item('export', producer['id'], export_item), _item('mesh', mesh_id, 'mesh'), _item('skeleton', mesh_id, 'skeleton'),
         _item('sword', 'unreal.adventure.mesh.ReferenceSword', 'mesh'), _item('glider', glider_id, 'mesh'),
         _item('glider_clip', 'unreal.adventure.clip.ReferenceGlider', 'animation')], {'export': dict(export_root)})
    packages[RECORD_FILE] = {'unit': record_id, 'item': 'record'}
    reference = {'skeleton': {'unit': mesh_id, 'item': 'skeleton', 'package': reference_skeleton},
                 'glide': {'derived': deepcopy(clips), 'piece': glide(root), 'package': f'{FOLDER}/A_Reference_{glide(root)}'},
                 'equipment': [dict(packages[sword]), dict(packages[glider_mesh])],
                 'record': {'unit': record_id, 'item': 'record'},
                 'export': {'unit': producer['id'], 'item': export_item, 'root': dict(export_root)}}
    return {'units': units, 'staged_inputs': staged, 'content_slots': {i['name']: False for u in units for i in u['inputs']},
            'packages': packages, 'aliases': {'unreal.adventure': tuple(u['id'] for u in units)},
            'module_requirements': requirements, 'templates': templates, 'groups': groups,
            'tokens': {'clips': clips, 'images': images, 'materials': materials}, 'reference': reference}
