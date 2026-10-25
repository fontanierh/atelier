"""Replace each import_character.py target by one unit per native asset bundle (world/character_v2.py).

Per character: a raw import and a finish per texture, a Material author per body material, one raw skeletal
import (mesh, skeleton, physics asset), one skeletal finish owning SK_<Name> with its Skeleton, PhysicsAsset (when
[unreal] physics_asset) and cloth colliders, a raw import and a finish per own clip, and DA_<Name>Base.

The material, texture, clip and cloth roster comes from the generated build/<output>/export.json, so it MUST
arrive as keyed ``members``: {id: {body: InputSource, cloth: bool,
materials: {name: {texture?: {file, source: InputSource}}}, clips: {name: {sample_rate, source: InputSource}}}};
without it a character refuses with DynamicMembership. ``natives`` supplies the shared compression owner
({compression: {unit, item, package}}) and each export Data Item ({<id>: {export: {unit, item, root?}}}).
"""
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re

from v2_texture_units import OPS, SIDECARS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/character_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_character.py'
SCRIPTS = GAME + '/unreal/Scripts/'
CONTENT = GAME + '/unreal/Content'
PIPELINE = GAME + '/assets/characters/pipeline'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
_NAME = re.compile(r'[A-Za-z0-9_]+\Z')
# raw_import's FBX import data exactly as import_character.fbx sets it (enums as Root's unreal_enum tokens).
MESH_FBX = {'normal_import_method': {'unreal_enum': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS'},
            'use_t0_as_ref_pose': False, 'update_skeleton_reference_pose': True, 'import_meshes_in_bone_hierarchy': True,
            'convert_scene': True}
VERTEX_COLORS = {'vertex_color_import_option': {'unreal_enum': 'VertexColorImportOption.REPLACE'}}
CLIP_FBX = {'animation_length': {'unreal_enum': 'FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME'},
            'use_default_sample_rate': False, 'import_bone_tracks': True, 'convert_scene': True}


# Importing a clip with morph curves may register curve metadata on its target Skeleton, which the original
# saved last. Here that Skeleton is the mesh finish's Item and only an input: the worker's dirty-input check
# refuses such a job by name until an actual run proves the effect absent; no write is granted.
SKELETON_MUTATION = 'morph-curve clip import dirtied its input Skeleton'


class DynamicMembership(Unsupported):
    """A character's generated export roster was not supplied as keyed members."""


def _definition(checkout):
    spec = importlib.util.spec_from_file_location('v2_character_definition', Path(checkout) / PIPELINE / 'definition.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _code_closure(checkout):
    from atelier.source_imports import ImportScanner
    root = Path(checkout)
    found = set()
    for helper in ('animation_compression.py', 'skin_morph_contacts.py'):
        found |= {p.relative_to(root).as_posix() for p in ImportScanner().local_imports(
            root / SCRIPTS / helper, (root / GAME / 'world', root / GAME / 'unreal/Scripts', root / 'platform/studio'))}
    return sorted({*_code(checkout), SCRIPT, *found})


def _modules(checkout, names):
    """(project modules, platform plugins) a native job loads: [unreal] modules = [] is the whole editor."""
    root = Path(checkout)
    project = json.loads((root / GAME / 'unreal/Yorimichi.uproject').read_text())
    modules = {m['Name']: {'name': m['Name'], 'kind': m['Type'], 'loading_phase': m['LoadingPhase']} for m in project['Modules']}
    if not names:
        return [dict(m) for m in modules.values()], []
    plugins = [name for name in names if name not in modules]
    if any(not (root / 'platform/engine/Plugins' / name / f'{name}.uplugin').is_file() for name in plugins):
        raise Unsupported('a character module is neither a project module nor a platform plugin')
    return [dict(modules[name]) for name in names if name in modules], plugins


def _files(package, *, store=False):
    relative = package.removeprefix('/Game/')
    files = []
    for suffix in SIDECARS:
        row = {'path': 'content/Game/' + relative + suffix, 'required': suffix == '.uasset'}
        if not store:
            row['install_path'] = CONTENT + '/' + relative + suffix
        files.append(row)
    return files


def _output(item, package, cls, *, store=False):
    return {'id': item, 'logical_path': package, 'class': cls, 'destination': 'store' if store else 'checkout',
            'files': _files(package, store=store)}


def _source(value, label):
    if not isinstance(value, dict) or value.get('kind') not in ('item', 'group_member'):
        raise Unsupported(f'{label}: member source must be an exact item or group_member InputSource')
    return dict(value)


def _check(row, character):
    commands = row['commands']
    expected = f"{CONTENT}{character.unreal_path.removeprefix('/Game')}/SK_{character.name}.uasset"
    if (len(commands) != 1 or commands[0].get('kind') != 'UnrealScript' or commands[0].get('script') != {'path': ORIGINAL}
            or commands[0].get('env') != [['CHARACTER', character.id]] or commands[0].get('args')
            or list(commands[0].get('modules', [])) != list(character.unreal['modules'])
            or row['products'] or row['outputs'] != [expected]):
        raise Unsupported(f'{row["id"]}: row differs from the original import_character.py target')


def character_units(rows, *, checkout, natives, members=None):
    """@cc [owner:fontanierh,label:correctness] authored-c3-character-bodies
    Each original import_character.py target MUST become one unit per native asset
    bundle consuming exact keyed source members and finished producer Items: textures,
    materials, the raw skeletal import, one skeletal finish owning SK/Skeleton/
    PhysicsAsset/cloth colliders, own clips on the finished Skeleton with the shared
    compression owner, and DA_<Name>Base. Generated membership MUST be passed or
    refused; generated content is never scanned and the original never runs.
    """
    checkout = Path(checkout)
    definition = _definition(checkout)
    members = members or {}
    targets = {row['id']: row for row in rows if any(c.get('script') == {'path': ORIGINAL} for c in row['commands'])}
    characters = [c for c in definition.movers() if f"unreal.{c.id.replace('-', '_')}" in targets]
    if len(characters) != len(targets):
        raise Unsupported('character targets without a definition: ' + ', '.join(sorted(
            set(targets) - {f"unreal.{c.id.replace('-', '_')}" for c in characters})))
    for character in characters:
        _check(targets[f"unreal.{character.id.replace('-', '_')}"], character)
    missing = sorted(c.id for c in characters if c.id not in members)
    if missing:
        raise DynamicMembership('generated character export rosters need keyed members: ' + ', '.join(missing))
    if set(members) - {c.id for c in characters}:
        raise Unsupported('character members name an unselected character')
    compression = natives.get('compression')
    if (not isinstance(compression, dict) or not {'unit', 'item', 'package'} <= set(compression)
            or compression['package'] != COMPRESSION):
        raise Unsupported('missing the shared CharacterCompression owner Item')
    code, ops_code = _code_closure(checkout), list(_code(checkout))
    units, staged, slots, packages, aliases, requirements, effects, plugins = [], {}, {}, {}, {}, {}, [], {}
    def add(unit, inputs, roots=None, modules=None):
        unit['inputs'] = inputs
        if roots:
            unit['params']['input_roots'] = roots
        units.append(unit)
        staged[unit['id']] = {item['name']: 'inputs/' + item['name'] for item in inputs}
        slots.update({item['name']: False for item in inputs})
        if modules:
            requirements[unit['id']], needed = modules
            if needed:
                plugins[unit['id']] = needed
    def item(name, unit, item_id):
        return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}
    def _native(dependency):
        return item('native_' + dependency['package'].removeprefix('/Game/').replace('/', '_'),
                    dependency['unit'], dependency['item'])
    for character in characters:
        k, name, dest = character.id.replace('-', '_'), character.name, character.unreal_path
        settings, entry = character.unreal, members[character.id]
        if not isinstance(entry, dict) or set(entry) != {'body', 'cloth', 'materials', 'clips'} or type(entry['cloth']) is not bool:
            raise Unsupported(f'{character.id}: members must be {{body, cloth, materials, clips}}')
        if not entry['materials'] or not isinstance(entry['materials'], dict) or not isinstance(entry['clips'], dict):
            raise Unsupported(f'{character.id}: empty material roster')
        export_ref = (natives.get(character.id) or {}).get('export')
        if (not isinstance(export_ref, dict) or not {'unit', 'item'} <= set(export_ref) <= {'unit', 'item', 'root'}):
            raise Unsupported(f'missing exact data Item for {character.id} export.json')
        def export(inputs, roots):
            inputs.append(item('export', export_ref['unit'], export_ref['item']))
            if 'root' in export_ref:
                roots['export'] = dict(export_ref['root'])
            return 'export'
        morphs = bool(settings['morph_targets'])
        requirement = _modules(checkout, list(settings['modules']))
        mesh_package = f'{dest}/SK_{name}'
        dependencies = []
        material_units = {}
        for material, spec in entry['materials'].items():
            if not _NAME.fullmatch(str(material)) or not isinstance(spec, dict) or set(spec) - {'texture'}:
                raise Unsupported(f'{character.id}: noncanonical material member {material!r}')
            inputs, roots = [], {}
            args = {'action': 'material', 'name': material, 'dest': dest, 'morphs': morphs, 'export': export(inputs, roots)}
            if 'texture' in spec:
                texture = spec['texture']
                if not isinstance(texture, dict) or set(texture) != {'file', 'source'}:
                    raise Unsupported(f'{character.id}: texture member is {{file, source}}')
                stem = PurePosixPath(texture['file']).stem
                if not _NAME.fullmatch(stem) or PurePosixPath(texture['file']).name != texture['file'].rsplit('/', 1)[-1]:
                    raise Unsupported(f'{character.id}: noncanonical texture {texture["file"]!r}')
                raw_package, package = f'/Game/_Raw/Characters/{k}/Textures/{stem}', f'{dest}/Textures/{stem}'
                raw_id, finish_id = f'unreal.character.{k}.texture.raw.{stem}', f'unreal.character.{k}.texture.{stem}'
                if finish_id not in {u['id'] for u in units}:
                    add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
                         'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_package},
                         'outputs': [_output('raw_texture', raw_package, 'RawTexture', store=True)]},
                        [{'role': 'content', 'name': 'source', 'source': _source(texture['source'], stem)}])
                    add({'id': finish_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': ops_code,
                         'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                                    'package_sources': {'raw': raw_package}, 'properties': {}},
                         'outputs': [_output('texture', package, 'Texture')]}, [item('raw', raw_id, 'raw_texture')])
                    packages[package] = {'unit': finish_id, 'item': 'texture', 'package': package}
                inputs.append(item('texture', finish_id, 'texture'))
                args['texture'] = 'texture'
                texture_ref = packages[package]
            else:
                texture_ref = None
            unit_id = f'unreal.character.{k}.material.{material}'
            package = f'{dest}/{material}'
            add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
                 'params': {'args': args, 'settings': []}, 'outputs': [_output('asset', package, 'Material')]}, inputs, roots)
            packages[package] = {'unit': unit_id, 'item': 'asset', 'package': package,
                                 'dependencies': [dict(texture_ref)] if texture_ref else []}
            material_units[material] = unit_id
            dependencies.extend(d for d in [packages[package], *([texture_ref] if texture_ref else [])] if d not in dependencies)
        raw_id = f'unreal.character.{k}.raw'
        raw_mesh = f'/Game/_Raw/Characters/{k}/SK_{name}'
        fbx = dict(MESH_FBX)
        if morphs:
            fbx['import_morph_targets'] = True
        if settings['vertex_colors']:
            fbx.update(VERTEX_COLORS)
        physics = bool(settings['physics_asset'])
        raw_outputs = [_output('raw_mesh', raw_mesh, 'RawSkeletalMesh', store=True),
                       _output('raw_skeleton', raw_mesh + '_Skeleton', 'Skeleton', store=True)]
        if physics:
            raw_outputs.append(_output('raw_physics_asset', raw_mesh + '_PhysicsAsset', 'PhysicsAsset', store=True))
        add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': {'op': 'raw_import', 'kind': 'skeletal_mesh', 'source': 'source', 'destination': raw_mesh,
                        'create_physics_asset': physics, 'fbx': fbx},
             'outputs': raw_outputs},
            [{'role': 'content', 'name': 'source', 'source': _source(entry['body'], f'{character.id} body')}])
        inputs, roots = [item('raw', raw_id, 'raw_mesh'), item('raw_skeleton', raw_id, 'raw_skeleton')], {}
        if physics:
            inputs.append(item('raw_physics_asset', raw_id, 'raw_physics_asset'))
        materials = {material: inputs.append(item('material_' + material, unit_id, 'asset')) or 'material_' + material
                     for material, unit_id in material_units.items()}
        for dependency in dependencies:
            if dependency['unit'] not in material_units.values():
                inputs.append(_native(dependency))
        partners = {'skeleton': f'{mesh_package}_Skeleton'}
        outputs = [_output('mesh', mesh_package, 'SkeletalMesh'), _output('skeleton', partners['skeleton'], 'Skeleton')]
        if physics:
            partners['physics_asset'] = f'{mesh_package}_PhysicsAsset'
            outputs.append(_output('physics_asset', partners['physics_asset'], 'PhysicsAsset'))
        args = {'action': 'mesh', 'name': name, 'dest': dest, 'export': export(inputs, roots), 'materials': materials,
                'cpu_access': bool(settings['cpu_access']), 'morphs': morphs,
                'contact_morphs': list(settings['contact_morphs'])}
        if entry['cloth']:
            args['cloth_package'] = f'{dest}/PA_{name}_Cloth'
            outputs.append(_output('cloth', args['cloth_package'], 'PhysicsAsset'))
        mesh_id = f'unreal.character.{k}.mesh'
        add({'id': mesh_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': mesh_package,
                        'partners': partners, 'args': args}, 'outputs': outputs}, inputs, roots, requirement)
        for output in outputs[1:]:
            packages[output['logical_path']] = {'unit': mesh_id, 'item': output['id'], 'package': output['logical_path']}
            dependencies.append(packages[output['logical_path']])
        packages[mesh_package] = {'unit': mesh_id, 'item': 'mesh', 'package': mesh_package,
                                  'dependencies': [dict(d) for d in dependencies]}
        mesh_ref = packages[mesh_package]
        clip_slots = {}
        for clip, spec in entry['clips'].items():
            if (not _NAME.fullmatch(str(clip)) or not isinstance(spec, dict) or set(spec) != {'sample_rate', 'source'}
                    or type(spec['sample_rate']) is not int or spec['sample_rate'] <= 0):
                raise Unsupported(f'{character.id}: noncanonical clip member {clip!r}')
            raw_clip, package = f'/Game/_Raw/Characters/{k}/A_{clip}', f'{dest}/A_{clip}'
            clip_raw_id, clip_id = f'unreal.character.{k}.clip.raw.{clip}', f'unreal.character.{k}.clip.{clip}'
            fbx = {**CLIP_FBX, 'custom_sample_rate': spec['sample_rate']}
            if morphs:
                fbx.update(delete_existing_morph_target_curves=True, do_not_import_curve_with_zero=False)
            add({'id': clip_raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
                 'params': {'op': 'raw_import', 'kind': 'animation', 'source': 'source', 'destination': raw_clip,
                            'skeleton': 'skeleton', 'fbx': fbx},
                 'outputs': [_output('raw_animation', raw_clip, 'RawAnimation', store=True)]},
                [{'role': 'content', 'name': 'source', 'source': _source(spec['source'], clip)},
                 item('skeleton', mesh_id, 'skeleton')])
            inputs, roots = [item('raw', clip_raw_id, 'raw_animation'), item('skeleton', mesh_id, 'skeleton'),
                             item('mesh', mesh_id, 'mesh'), item('compression', compression['unit'], compression['item'])], {}
            inputs.extend(_native(d) for d in mesh_ref['dependencies'] if d['unit'] != mesh_id)
            add({'id': clip_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
                 'params': {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': package,
                            'args': {'action': 'clip', 'name': clip, 'export': export(inputs, roots), 'skeleton': 'skeleton',
                                     'mesh': 'mesh', 'compression': 'compression'}},
                 'outputs': [_output('animation', package, 'Animation')]}, inputs, roots)
            packages[package] = {'unit': clip_id, 'item': 'animation', 'package': package}
            clip_slots[clip] = clip_id
            if morphs:
                effects.append({'unit': clip_raw_id, 'input': partners['skeleton'], 'refusal': SKELETON_MUTATION})
        inputs, roots = [item('mesh', mesh_id, 'mesh')], {}
        inputs.extend(_native(d) for d in mesh_ref['dependencies'])
        clip_args = {clip: inputs.append(item('clip_' + clip, unit_id, 'animation')) or 'clip_' + clip
                     for clip, unit_id in clip_slots.items()}
        base_package = f'{dest}/DA_{name}Base'
        base_id = f'unreal.character.{k}.base'
        add({'id': base_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': 'base', 'name': f'DA_{name}Base', 'dest': dest, 'export': export(inputs, roots),
                                 'mesh': 'mesh', 'clips': clip_args, 'camera_height': float(settings['camera_height'])},
                        'settings': []},
             'outputs': [_output('asset', base_package, 'WandererDefinition')]}, inputs, roots, _modules(checkout, ['Yorimichi']))
        packages[base_package] = {'unit': base_id, 'item': 'asset', 'package': base_package,
                                  'dependencies': [dict(mesh_ref), *(dict(packages[f'{dest}/A_{c}']) for c in clip_slots)]}
        aliases[f"unreal.{k}"] = tuple(u['id'] for u in units if u['id'].startswith(f'unreal.character.{k}.'))
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots, 'packages': packages,
            'aliases': aliases, 'module_requirements': requirements, 'plugin_requirements': plugins,
            'runtime_refusals': effects}
