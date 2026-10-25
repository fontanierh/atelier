"""Replace unreal.skate_clips (Scripts/skate_ride/import_clips.py and verify_clips.py) by native units per owner.

The source is skate.runtime's complete simulation package ROOT (the binding v2_skate_data_units uses); the committed
package-manifest.json names every clip. From that whole Item (world/skate_clip_members_v2.py):
- a fixed rig view: SK_SkateRider.glb by the original rider_mesh.write_glb, and the rig file;
- one FileSet per clip bank (Clips/B<bank>): each member is one clip's bytes, metadata and clips.json record, followed
  by its UAnimSequence (the original make_clip) and its every-frame compressed pose and curve measurement;
- fixed natives: SK_SkateRider/SKEL_SkateRider (raw glTF skeletal import, check_rider), ACL_SkateRideExact,
  CC_SkateRideExact, MDT_SkateRider, the four still pose documents, the compression control (a store-only private
  copy of the finished CONTROL clip under the default compression, with its measurement), and the
  complete Content/Data/SkateRide/clips.json and skate-ride/clips-verify.json.
"""
from copy import deepcopy
import json
from pathlib import Path, PurePosixPath

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import _modules, _output
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/skate_clip_v2.py'
BODY = GAME + '/world/skate_clip_members_v2.py'
SCRIPTS = GAME + '/unreal/Scripts/skate_ride'
ORIGINALS = tuple(f'{SCRIPTS}/{n}' for n in ('import_clips.py', 'verify_clips.py', 'simulation.py', 'rider_mesh.py'))
PACKAGER = 'platform/engine/Plugins/Activities/Skate/Tools/simulation_package.py'
MANIFEST = 'platform/engine/Plugins/Activities/Skate/Data/package-manifest.json'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
CLIPS_FILE = GAME + '/unreal/Content/Data/SkateRide/clips.json'
DEST = '/Game/SkateRide'
RAW = '/Game/_Raw/SkateRide/SK_SkateRider'
CONTROL_COPY = '/Game/_Raw/SkateRideVerify/ControlDefaultCompression'
RECIPE_OP = {'kind': 'recipe.python', 'version': '1'}
IMPORT_MARKER, VERIFY_MARKER = 'SKATE RIDE CLIPS BATCH COMPLETE', 'SKATE RIDE CLIPS VERIFY COMPLETE'


def _body(root):
    import importlib.util
    spec = importlib.util.spec_from_file_location('skate_clip_members_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _call(root, name, defaults):
    function = getattr(_body(root), name); function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / GAME / 'world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def token(bank, follower, item, piece=None):
    """Bank <bank>'s clip children: follower 0 the UAnimSequence, 1 the measurement, None the selected member."""
    template = {'producer': f'skate_clips.members.b{bank}', 'group': 'members', 'unit_prefix': f'unreal.skate_clips.b{bank}',
                'follower': follower, 'item': item}
    if piece is not None:
        template['piece'] = piece
    return {'derived_items': {'root': f'build/v2-derived/skate_clips/b{bank}/{follower}' + (f'/{piece}' if piece else ''),
                              'templates': [template]}}


def roster(checkout):
    """{bank: [clip]} of the committed package manifest, and its clip count."""
    manifest = json.loads((Path(checkout) / MANIFEST).read_bytes())
    banks = {}
    for name in manifest['files']:
        parts = name.split('/')
        if name.startswith('animation/clips/'):
            if len(parts) != 4 or not parts[3].endswith('.skate') or parts[2] not in ('0', '1'):
                raise Unsupported('noncanonical committed skate clip file: ' + name)
            banks.setdefault(int(parts[2]), []).append(parts[3].removesuffix('.skate'))
    if manifest.get('version') != 1 or sum(map(len, banks.values())) != manifest.get('clips'):
        raise Unsupported('committed skate clip roster is incomplete')
    return {bank: sorted(names, key=lambda n: n + '.skate') for bank, names in sorted(banks.items())}, manifest['clips']


def _check(by_id):
    row, producer = by_id.get('unreal.skate_clips'), by_id.get('skate.runtime')
    if not row or not producer or row['needs'] != ['skate.runtime'] or row.get('products'):
        raise Unsupported('unreal.skate_clips requires its unique skate.runtime source')
    commands = row['commands']
    imports = [c for c in commands if c.get('script') == {'path': ORIGINALS[0]}]
    verifies = [c for c in commands if c.get('script') == {'path': ORIGINALS[1]}]
    if (not imports or not verifies or commands != imports + verifies
            or any(c.get('kind') != 'UnrealScript' or c.get('null_rhi') is not True or c.get('args') or c.get('modules')
                   for c in commands)
            or [c.get('marker') for c in commands] != [IMPORT_MARKER] * len(imports) + [VERIFY_MARKER] * len(verifies)
            or [c.get('env') for c in imports] != [[['SKATE_RIDE_BATCH', f'{i}/{len(imports)}']] for i in range(1, len(imports) + 1)]
            or [c.get('env') for c in verifies] != [[['SKATE_RIDE_VERIFY_BATCH', f'{i}/{len(verifies)}']]
                                                    for i in range(1, len(verifies) + 1)]):
        raise Unsupported('unreal.skate_clips differs from its batched import_clips.py and verify_clips.py')
    outputs = [str(o) for o in row['outputs']]
    if len(outputs) != 2 or outputs[0] != CLIPS_FILE or not outputs[1].endswith('/skate-ride/clips-verify.json'):
        raise Unsupported('unreal.skate_clips outputs differ from clips.json and clips-verify.json')
    source = producer['commands']
    arguments = source[0].get('args') if len(source) == 1 else None
    if (len(source) != 1 or source[0].get('script') != {'path': PACKAGER} or not isinstance(arguments, list)
            or len(arguments) != 4 or arguments[0] != '--assemble' or not isinstance(arguments[1], dict)):
        raise Unsupported('skate runtime must retain its actual package constructor')
    package = arguments[1]['path']
    if producer['products'] or package not in producer['outputs'] or PurePosixPath(package).name != 'package':
        raise Unsupported('skate runtime complete package must be its exact ungrouped output ROOT')
    index = producer['outputs'].index(package)
    return producer['id'], f'output{index}', f'outputs/{index}.tree.tar', package, outputs[1]


def skate_clip_units(rows, *, checkout):
    """@cc [owner:fontanierh,label:correctness] skate-clip-native-units
    unreal.skate_clips MUST become one unit per /Game/SkateRide owner and per JSON
    document from the actual skate.runtime package ROOT and the committed manifest
    roster: per-bank clip FileSets whose clip and measurement followers consume only
    their own member, the fixed rider/compression/mirror owners, stills, the
    transient control, and the complete manifest and report over every derived clip.
    Consumers MUST bind actual derived Items; the originals' main, setup, state,
    batching and directory deletes never run.
    """
    root = Path(checkout).resolve()
    by_id = {row['id']: row for row in rows}
    producer_id, package_item, package_archive, package, verify_file = _check(by_id)
    banks, count = roster(root)
    scanner = ImportScanner()
    recipe_code = {BODY, *ORIGINALS}
    for source in (BODY, RECIPE, EMITTER):
        recipe_code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(
            root / source, (root / 'platform/studio', root / GAME / 'world')))
    recipe_code = sorted(recipe_code)
    ops_code = list(_code(root))
    code = sorted({*ops_code, SCRIPT, BODY, *ORIGINALS})
    editor = _modules(root, [])[0]
    units, staged, packages, requirements, templates, groups = [], {}, {}, {}, [], {}

    def add(unit, inputs, roots=None):
        unit['inputs'] = inputs
        if roots:
            unit['params']['input_roots'] = roots
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if unit['op']['kind'] != 'recipe.python':
            requirements[unit['id']] = editor
    def author(unit_id, args, outputs, inputs, roots=None):
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': args, 'settings': []}, 'outputs': outputs}, inputs, roots)
    def data(item, logical, store=True, install=None):
        files = [{'path': 'data/' + (PurePosixPath(install).name if install else 'verify.json'), 'required': True}]
        if install:
            files[0]['install_path'] = install
        return {'id': item, 'logical_path': logical, 'class': 'JsonData', 'destination': 'store' if store else 'checkout',
                'files': files}

    whole = _item('package', producer_id, package_item)
    whole['whole'] = 'The complete simulation package checks the committed clip roster before any clip is selected.'
    paths = {package: 'inputs/package/' + package_archive, MANIFEST: 'inputs/manifest'}
    add({'id': 'skate_clips.rig', 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
         'params': {'recipe': {'version': 1, 'paths': {package: paths[package]}, 'verify': None,
             'commands': [_call(root, 'rig', (root / package, root / SCRIPTS, root / 'generated/skate_clips/mesh',
                                              root / 'generated/skate_clips/bundle'))],
             'outputs': [{'path': f'generated/skate_clips/{f}', 'kind': 'tree', 'file': f + '.tree.tar', 'required': True}
                         for f in ('mesh', 'bundle')]}},
         'outputs': [{'id': 'rig', 'logical_path': '/Internal/SkateRide/Rig', 'class': 'Data', 'destination': 'store',
                      'files': [{'path': f + '.tree.tar', 'required': True} for f in ('mesh', 'bundle')]}]},
        [deepcopy(whole)])
    bundle_input, bundle_root = _item('bundle', 'skate_clips.rig', 'rig'), {'archive_member': 'bundle.tree.tar', 'name': 'bundle'}
    for bank in banks:
        generated, unit_id = f'generated/skate_clips/b{bank}', f'skate_clips.members.b{bank}'
        contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                    'adapter_version': 'd2.file-set/1', 'parent': f'SkateRide_B{bank}', 'encoding': 'file_set',
                    'class': 'Data', 'logical_namespace': f'/Internal/SkateRide/B{bank}', **LIMITS}
        add({'id': unit_id, 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
             'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': dict(paths), 'verify': None,
                 'commands': [_call(root, 'project', (root / package, root / MANIFEST, root / SCRIPTS, root / generated, bank))],
                 'outputs': [{'path': generated, 'kind': 'tree', 'file': 'members.tree.tar', 'required': True}],
                 'file_group': {'source': generated, 'parent': f'SkateRide_B{bank}', 'extensions': ['.json']}}},
             'outputs': [{'id': 'members', 'logical_path': f'/Internal/SkateRide/B{bank}', 'class': 'Data',
                          'destination': 'store', 'files': [{'path': 'members.tree.tar', 'required': True}]}],
             'output_groups': [contract]}, [deepcopy(whole), {'role': 'content', 'name': 'manifest',
                                                              'source': {'kind': 'file', 'path': MANIFEST}}])
        groups[unit_id] = {'contract': contract, 'source': generated}
    # The rider: the raw glTF skeletal import of the rig view's GLB, then SK_SkateRider and SKEL_SkateRider.
    add({'id': 'unreal.skate_clips.rider.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS,
         'code': ops_code, 'params': {'op': 'raw_import', 'kind': 'skeletal_mesh', 'source': 'source', 'destination': RAW,
                                      'create_physics_asset': False},
         'outputs': [_output('raw_mesh', RAW, 'RawSkeletalMesh', store=True),
                     _output('raw_skeleton', RAW + '_Skeleton', 'Skeleton', store=True)]},
        [_item('source', 'skate_clips.rig', 'rig')], {'source': {'archive_member': 'mesh.tree.tar', 'name': 'mesh'}})
    mesh, skeleton = DEST + '/SK_SkateRider', DEST + '/SKEL_SkateRider'
    rider_id = 'unreal.skate_clips.rider'
    add({'id': rider_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': mesh,
                    'partners': {'skeleton': skeleton}, 'args': {'action': 'rider', 'bundle': 'bundle'}},
         'outputs': [_output('mesh', mesh, 'SkeletalMesh'), _output('skeleton', skeleton, 'Skeleton')]},
        [_item('raw', 'unreal.skate_clips.rider.raw', 'raw_mesh'), _item('raw_skeleton', 'unreal.skate_clips.rider.raw', 'raw_skeleton'),
         deepcopy(bundle_input)], {'bundle': dict(bundle_root)})
    packages[mesh] = {'unit': rider_id, 'item': 'mesh', 'package': mesh,
                      'dependencies': [{'unit': rider_id, 'item': 'skeleton', 'package': skeleton}]}
    packages[skeleton] = {'unit': rider_id, 'item': 'skeleton', 'package': skeleton}
    owners = {'bone': ('ACL_SkateRideExact', 'AnimBoneCompressionSettings'), 'curve': ('CC_SkateRideExact', 'AnimCurveCompressionSettings')}
    for action, (name, cls) in owners.items():
        author(f'unreal.skate_clips.{name}', {'action': action}, [_output('asset', f'{DEST}/{name}', cls)], [])
        packages[f'{DEST}/{name}'] = {'unit': f'unreal.skate_clips.{name}', 'item': 'asset', 'package': f'{DEST}/{name}'}
    author('unreal.skate_clips.MDT_SkateRider', {'action': 'mirror', 'skeleton': 'skeleton', 'bundle': 'bundle'},
           [_output('asset', DEST + '/MDT_SkateRider', 'MirrorDataTable')],
           [_item('skeleton', rider_id, 'skeleton'), deepcopy(bundle_input)], {'bundle': dict(bundle_root)})
    packages[DEST + '/MDT_SkateRider'] = {'unit': 'unreal.skate_clips.MDT_SkateRider', 'item': 'asset', 'package': DEST + '/MDT_SkateRider',
                                          'dependencies': [dict(packages[skeleton])]}
    shared = [_item('skeleton', rider_id, 'skeleton'), _item('mesh', rider_id, 'mesh'),
              _item('bone', 'unreal.skate_clips.ACL_SkateRideExact', 'asset'), _item('curve', 'unreal.skate_clips.CC_SkateRideExact', 'asset')]
    shared_args = {'skeleton': 'skeleton', 'mesh': 'mesh', 'bone': 'bone', 'curve': 'curve', 'bundle': 'bundle'}
    member_root = {'archive_member': 'member.tree.tar', 'name': 'member'}
    for bank in banks:
        folder = f'{DEST}/Clips/B{bank}'
        clip_unit = {'id': '$export.clip', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
                     'inputs': [_item('member', '$export', 'asset'), deepcopy(bundle_input), *deepcopy(shared)],
                     'params': {'args': {'action': 'clip', 'name': '$piece', 'bank': bank, 'member': 'member', **shared_args},
                                'settings': [], 'input_roots': {'member': dict(member_root), 'bundle': dict(bundle_root)}},
                     'outputs': [_output('asset', f'{folder}/$piece', 'Animation')]}
        verify_unit = {'id': '$export.verify', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
                       'inputs': [_item('sequence', '$previous', 'asset'), _item('member', '$export', 'asset'), deepcopy(bundle_input)],
                       'params': {'args': {'action': 'verify', 'sequence': 'sequence', 'member': 'member', 'bundle': 'bundle'},
                                  'settings': [], 'input_roots': {'member': dict(member_root), 'bundle': dict(bundle_root)}},
                       'outputs': [data('data', f'/Internal/SkateRide/Verify/B{bank}/$piece')]}
        templates.append({'producer': f'skate_clips.members.b{bank}', 'group': 'members', 'unit_prefix': f'unreal.skate_clips.b{bank}',
            'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code, 'derive_payload': False, 'payload_slot': 'payload',
            'staged_path': 'inputs/payload', 'output_class': 'Data', 'logical_namespace': f'/Internal/SkateRide/Selected/B{bank}',
            'files': [{'path': 'member.tree.tar', 'required': True}],
            'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
                'commands': [_call(root, 'select', (root / 'selected', root / 'member', '$piece'))],
                'outputs': [{'path': 'member', 'kind': 'tree', 'file': 'member.tree.tar', 'required': True}]}},
            'followers': [{'unit': u, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in u['inputs']}}
                          for u in (clip_unit, verify_unit)]})
    members_inputs = {bank: _item(f'members_b{bank}', f'skate_clips.members.b{bank}', 'members') for bank in banks}
    members_roots = {f'members_b{bank}': {'archive_member': 'members.tree.tar', 'name': f'members_b{bank}'} for bank in banks}
    import_constants = _body(root).constants(root / ORIGINALS[0], ('STILLS', 'CONTROL'))
    where = {name: bank for bank, names in banks.items() for name in names}
    for name in (*import_constants['STILLS'], import_constants['CONTROL']):
        if name not in where:
            raise Unsupported(f'{name} is not a committed clip')
    for name in import_constants['STILLS']:
        bank = where[name]
        author(f'unreal.skate_clips.still.{name}',
               {'action': 'still', 'name': name, 'members': f'members_b{bank}', 'bundle': 'bundle', 'sequence': token(bank, 0, 'asset', name)},
               [data('data', f'/Internal/SkateRide/Stills/{name}')],
               [deepcopy(members_inputs[bank]), deepcopy(bundle_input)],
               {f'members_b{bank}': dict(members_roots[f'members_b{bank}']), 'bundle': dict(bundle_root)})
    control = import_constants['CONTROL']
    # verify_clips.control's copy, as its own store-only private package: the finished CONTROL clip (exact piece join)
    # duplicated under the engine's default compression, with its measurement as the finish's Data report.
    add({'id': 'unreal.skate_clips.control', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'op': 'finish', 'kind': 'animation', 'source': token(where[control], 0, 'asset', control),
                    'destination': CONTROL_COPY, 'args': {'action': 'control', 'members': f'members_b{where[control]}', 'bundle': 'bundle'}},
         'outputs': [_output('asset', CONTROL_COPY, 'Animation', store=True),
                     {'id': 'report', 'logical_path': '/Internal/SkateRide/Control', 'class': 'Data', 'destination': 'store',
                      'files': [{'path': 'data/control.json', 'required': True}]}]},
        [deepcopy(members_inputs[where[control]]), deepcopy(bundle_input)],
        {f'members_b{where[control]}': dict(members_roots[f'members_b{where[control]}']), 'bundle': dict(bundle_root)})
    author('unreal.skate_clips.manifest',
           {'action': 'manifest', **shared_args, 'mirror': 'mirror', 'members': [f'members_b{b}' for b in banks],
            'clips': [token(b, 0, 'asset') for b in banks]},
           [data('manifest', '/Game/_Data/SkateRide/clips', store=False, install=CLIPS_FILE)],
           [*deepcopy(shared), _item('mirror', 'unreal.skate_clips.MDT_SkateRider', 'asset'), deepcopy(bundle_input),
            *deepcopy(list(members_inputs.values()))], {**deepcopy(members_roots), 'bundle': dict(bundle_root)})
    author('unreal.skate_clips.report', {'action': 'report', 'bundle': 'bundle', 'control': 'control', 'count': count,
                                         'verify': [token(b, 1, 'data') for b in banks]},
           [{'id': 'report', 'logical_path': '/Internal/SkateRide/Verify', 'class': 'JsonData', 'destination': 'store',
             'files': [{'path': 'data/clips-verify.json', 'required': True}]}],
           [deepcopy(bundle_input), _item('control', 'unreal.skate_clips.control', 'report')], {'bundle': dict(bundle_root)})
    packages[CLIPS_FILE] = {'unit': 'unreal.skate_clips.manifest', 'item': 'manifest'}
    packages[verify_file] = {'unit': 'unreal.skate_clips.report', 'item': 'report'}
    slots = {i['name']: False for u in [*units, *(f['unit'] for t in templates for f in t['followers'])] for i in u['inputs']}
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots, 'packages': packages,
            'aliases': {'unreal.skate_clips': tuple(u['id'] for u in units)}, 'module_requirements': requirements,
            'templates': templates, 'groups': groups,
            'tokens': {f'b{b}': {'clips': token(b, 0, 'asset'), 'verify': token(b, 1, 'data')} for b in banks}}
