"""Replace each import_adventure_moveset.py target by one unit per native asset and one move-record unit.

Per character (adventure.toml): a store-only raw import and a finish per clip (A_<Clip>), three 1D speed blends
(BS_<Name>Adventure*), the merged UAdventureMoveSet and the JsonData move record (Content/Data/<id>/adventure.json),
all run by world/moveset_v2.py. One shared unit owns /Game/Japan/Animation/CharacterCompression.

The clip roster is generated (build/yorimichi/adventure/export.json, from the local adventure library, plus the
donor's own clips retargeted for the others), so it MUST arrive as keyed ``members``:
{id: [{name, kind: clip|own, fps, frames, source: InputSource}]}; without it a character refuses with
DynamicMembership. Finished producers arrive as ``natives``:
{'reference': {skeleton, glide, equipment: [ref], record, export},
 '<id>': {skeleton, base, export}, 'donor': {package: ref}}, where a native ref is
{unit, item, package, dependencies?: [ref]} and a data ref {unit, item, root?}.
"""
import importlib.util
import json
from pathlib import Path
import re
import sys

from v2_texture_units import SIDECARS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/moveset_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_adventure_moveset.py'
COMPRESSION_SCRIPT = GAME + '/unreal/Scripts/animation_compression.py'
CONTENT = GAME + '/unreal/Content'
PIPELINE = GAME + '/assets/characters/pipeline'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
COMPRESSION_UNIT = 'unreal.animation.compression'
BLENDS = (('locomotion', 'Locomotion'), ('crouching', 'Crouching'), ('armed', 'ArmedLocomotion'))
# raw_import(animation)'s FbxAnimSequenceImportData, as import_adventure_moveset.fbx sets it; animation_length
# (FBXALIT_EXPORTED_TIME) is an enum the raw op's property ABI cannot spell and is left at its default.
FBX = {'use_default_sample_rate': False, 'import_bone_tracks': True, 'delete_existing_morph_target_curves': True,
       'do_not_import_curve_with_zero': False, 'convert_scene': True}
_NAME = re.compile(r'[A-Za-z0-9_]+\Z')


class DynamicMembership(Unsupported):
    """A character's generated clip roster was not supplied as keyed members."""


def _definition(checkout):
    spec = importlib.util.spec_from_file_location('v2_moveset_definition', Path(checkout) / PIPELINE / 'definition.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _code_closure(checkout):
    from atelier.source_imports import ImportScanner
    root = Path(checkout)
    found = ImportScanner().local_imports(root / COMPRESSION_SCRIPT, (root / GAME / 'world', root / GAME / 'unreal/Scripts',
                                                                     root / 'platform/studio'))
    return sorted({*_code(checkout), SCRIPT, ORIGINAL, *(p.relative_to(root).as_posix() for p in found)})


def _modules(checkout):
    project = json.loads((Path(checkout) / GAME / 'unreal/Yorimichi.uproject').read_text())
    return {m['Name']: {'name': m['Name'], 'kind': m['Type'], 'loading_phase': m['LoadingPhase']} for m in project['Modules']}


def _files(package, *, store=False, json_file=None):
    if json_file:
        return [{'path': 'data/' + json_file.rsplit('/', 1)[1], 'install_path': json_file, 'required': True}]
    relative = package.removeprefix('/Game/')
    files = []
    for suffix in SIDECARS:
        row = {'path': 'content/Game/' + relative + suffix, 'required': suffix == '.uasset'}
        if not store:
            row['install_path'] = CONTENT + '/' + relative + suffix
        files.append(row)
    return files


def _native(ref, label, package=None):
    if isinstance(ref, dict) and set(ref) == {'derived', 'piece', 'package'}:
        binding = ref['derived'].get('derived_items') if isinstance(ref['derived'], dict) else None
        if (not isinstance(binding, dict) or len(binding.get('templates', ())) != 1
                or not isinstance(ref['piece'], str) or not _NAME.fullmatch(ref['piece'])
                or not isinstance(ref['package'], str) or not ref['package'].startswith('/Game/')
                or (package is not None and ref['package'] != package)):
            raise Unsupported(f'missing exact derived native Item for {label}')
        return ref
    if (not isinstance(ref, dict) or not {'unit', 'item', 'package'} <= set(ref) <= {'unit', 'item', 'package', 'dependencies'}
            or not all(isinstance(ref[k], str) and ref[k] for k in ('unit', 'item', 'package'))
            or (package is not None and ref['package'] != package)):
        raise Unsupported(f'missing exact native Item for {label}' + (f' ({package})' if package else ''))
    return ref


def _data_ref(ref, label):
    if (not isinstance(ref, dict) or not {'unit', 'item'} <= set(ref) <= {'unit', 'item', 'root'}
            or not all(isinstance(ref[k], str) and ref[k] for k in ('unit', 'item'))):
        raise Unsupported(f'missing exact data Item for {label}')
    if 'root' in ref and (not isinstance(ref['root'], dict) or set(ref['root']) != {'archive_member', 'name'}):
        raise Unsupported(f'{label}: invalid ROOT binding')
    return ref


class _Inputs:
    """One unit's content inputs, each slot named once, with its native dependencies staged beside it."""

    def __init__(self):
        self.items, self.roots, self.packages = [], {}, set()

    def native(self, slot, ref):
        if 'derived' in ref:
            from copy import deepcopy
            binding = deepcopy(ref['derived'])
            binding['derived_items']['templates'][0]['piece'] = ref['piece']
            self.packages.add(ref['package'])
            return {'derived_native': {'items': binding, 'package': ref['package']}}
        self.items.append({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}})
        self.packages.add(ref['package'])
        for dependency in ref.get('dependencies', []):
            dependency = _native(dependency, f'dependency of {ref["package"]}')
            if dependency['package'] not in self.packages:
                self.native('native_' + dependency['package'].removeprefix('/Game/').replace('/', '_'), dependency)
        return slot

    def data(self, slot, ref):
        self.items.append({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}})
        if 'root' in ref:
            self.roots[slot] = dict(ref['root'])
        return slot

    def item(self, slot, unit, item):
        self.items.append({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': unit, 'item': item}})
        return slot


def compression_unit(*, checkout, code=None):
    """The single shared owner of CharacterCompression: every finished clip consumes this Item."""
    return {'id': COMPRESSION_UNIT, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
            'code': list(code or _code_closure(checkout)), 'inputs': [],
            'params': {'args': {'action': 'compression'}, 'settings': []},
            'outputs': [{'id': 'asset', 'logical_path': COMPRESSION, 'class': 'AnimBoneCompressionSettings',
                         'destination': 'checkout', 'files': _files(COMPRESSION)}]}


def _check(row, character):
    commands = row['commands']
    if (len(commands) != 1 or commands[0].get('kind') != 'UnrealScript' or commands[0].get('script') != {'path': ORIGINAL}
            or commands[0].get('env') != [['ADVENTURE_CHARACTER', character.id]] or commands[0].get('args')
            or row['products'] or row['outputs'] != [f'{CONTENT}/Data/{character.id}/adventure.json']):
        raise Unsupported(f'{row["id"]}: row differs from the original import_adventure_moveset.py target')


def _members(character, entries, donor):
    if not isinstance(entries, list) or not entries:
        raise Unsupported(f'{character.id}: empty clip roster')
    clips, own = {}, {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'name', 'kind', 'fps', 'frames', 'source'}:
            raise Unsupported(f'{character.id}: each member is {{name, kind, fps, frames, source}}')
        name, kind, source = entry['name'], entry['kind'], entry['source']
        if (not isinstance(name, str) or not _NAME.fullmatch(name) or kind not in ('clip', 'own')
                or type(entry['fps']) is not int or entry['fps'] <= 0 or type(entry['frames']) is not int or entry['frames'] <= 0
                or not isinstance(source, dict) or source.get('kind') not in ('item', 'group_member')):
            raise Unsupported(f'{character.id}: noncanonical clip member {entry!r}')
        if kind == 'own' and donor:
            raise Unsupported(f'{character.id}: the donor plays its own imported clips, not retargeted copies')
        target = clips if kind == 'clip' else own
        if name in target:
            raise Unsupported(f'{character.id}: duplicate clip member {name}')
        target[name] = entry
    if set(clips) & set(own):
        raise Unsupported(f'{character.id}: a clip and an own clip share A_ names')
    return clips, own


def moveset_units(rows, *, checkout, natives, members=None):
    """@cc [owner:fontanierh,label:correctness] authored-c3-adventure-movesets
    Each original import_adventure_moveset.py target MUST become one unit per native
    asset (raw/finish per keyed clip member, three blends, the merged definition) and
    one JsonData move-record unit, consuming exact finished producer Items and the
    single shared compression owner. The generated clip roster MUST arrive as keyed
    members; a missing roster refuses. Generated content is never scanned and the
    original top-level script never runs.
    """
    checkout = Path(checkout)
    definition = _definition(checkout)
    members = members or {}
    targets = {row['id']: row for row in rows
               if any(command.get('script') == {'path': ORIGINAL} for command in row['commands'])}
    characters = [c for c in definition.movers() if f'unreal.{c.id.replace("-", "_")}_adventure' in targets]
    if len(characters) != len(targets):
        raise Unsupported('move-set targets without an adventure definition: ' + ', '.join(sorted(
            set(targets) - {f'unreal.{c.id.replace("-", "_")}_adventure' for c in characters})))
    for character in characters:
        _check(targets[f'unreal.{character.id.replace("-", "_")}_adventure'], character)
    missing = sorted(c.id for c in characters if c.id not in members)
    if missing:
        raise DynamicMembership('generated clip rosters need keyed members: ' + ', '.join(missing))
    if set(members) - {c.id for c in characters}:
        raise Unsupported('clip members name an unselected character')
    code = _code_closure(checkout)
    modules = _modules(checkout)
    donor_id = definition.movers()[0].id
    donor_spec = definition.movers()[0].donor
    reference = natives.get('reference') or {}
    units, staged, slots, packages, aliases, requirements = [compression_unit(checkout=checkout, code=code)], {}, {}, {}, {}, {}
    packages[COMPRESSION] = {'unit': COMPRESSION_UNIT, 'item': 'asset', 'package': COMPRESSION}
    def add(unit, inputs, module=None):
        unit['inputs'] = inputs.items
        if inputs.roots:
            unit['params']['input_roots'] = dict(inputs.roots)
        units.append(unit)
        staged[unit['id']] = {item['name']: 'inputs/' + item['name'] for item in inputs.items}
        slots.update({item['name']: False for item in inputs.items})
        if module:
            requirements[unit['id']] = [dict(modules[module])]
    def author(unit_id, args, cls, package, inputs, module=None, json_file=None):
        output = {'id': 'record' if json_file else 'asset', 'logical_path': package, 'class': cls, 'destination': 'checkout',
                  'files': _files(package, json_file=json_file)}
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': args, 'settings': []}, 'outputs': [output]}, inputs, module)
    for character in characters:
        k, spec = character.id.replace('-', '_'), character.adventure
        own = natives.get(character.id) or {}
        is_donor = character.id == donor_id
        clips, own_clips = _members(character, members[character.id], is_donor)
        name = spec['mesh'].rsplit('/SK_', 1)[1]
        dest = spec['dest']
        skeleton = _native(own.get('skeleton'), f'{character.id} skeleton')
        base = _native(own.get('base'), f'{character.id} base definition', spec['base'])
        export = _data_ref(own.get('export'), f'{character.id} adventure export.json')
        reference_export = _data_ref(reference.get('export'), 'adventure/export.json')
        roster = _data_ref(reference.get('record'), 'Data/adventure/reference.json')
        donor = {}
        if is_donor:
            needed = {donor_spec['double_jump'], *(t['clip'] for t in donor_spec['actions'].values())}
            for clip_name in sorted(needed):
                package = f"{donor_spec['folder']}/A_{clip_name}"
                donor[clip_name] = _native((natives.get('donor') or {}).get(package), 'donor clip', package)
        finished = {}
        for kind, table in (('clip', clips), ('own', own_clips)):
            for clip_name, entry in table.items():
                raw_id, clip_id = f'unreal.moveset.{k}.raw.{clip_name}', f'unreal.moveset.{k}.clip.{clip_name}'
                raw_package = f'/Game/_Raw/Moveset/{k}/A_{clip_name}'
                package = f'{dest}/A_{clip_name}'
                inputs = _Inputs()
                inputs.items.append({'role': 'content', 'name': 'source', 'source': dict(entry['source'])})
                inputs.native('skeleton', skeleton)
                add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script':
                     'platform/studio/atelier/build_v2/unreal_ops.py', 'code': list(_code(checkout)),
                     'params': {'op': 'raw_import', 'kind': 'animation', 'source': 'source', 'destination': raw_package,
                                'skeleton': 'skeleton', 'fbx': {**FBX, 'custom_sample_rate': entry['fps']}},
                     'outputs': [{'id': 'raw_animation', 'logical_path': raw_package, 'class': 'RawAnimation',
                                  'destination': 'store', 'files': _files(raw_package, store=True)}]}, inputs)
                inputs = _Inputs()
                inputs.item('raw', raw_id, 'raw_animation')
                inputs.native('skeleton', skeleton)
                inputs.item('compression', COMPRESSION_UNIT, 'asset')
                add({'id': clip_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
                     'params': {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': package,
                                'args': {'action': 'clip', 'name': clip_name, 'frames': entry['frames'], 'fps': entry['fps'],
                                         'skeleton': 'skeleton', 'compression': 'compression'}},
                     'outputs': [{'id': 'animation', 'logical_path': package, 'class': 'Animation',
                                  'destination': 'checkout', 'files': _files(package)}]}, inputs)
                packages[package] = {'unit': clip_id, 'item': 'animation', 'package': package}
                finished[(kind, clip_name)] = (clip_id, package)
        def clip_inputs(inputs):
            refs = {'clips': {}, 'own': {}}
            for (kind, clip_name), (unit_id, _) in finished.items():
                slot = ('clip_' if kind == 'clip' else 'own_') + clip_name
                inputs.item(slot, unit_id, 'animation')
                refs['clips' if kind == 'clip' else 'own'][clip_name] = slot
            return refs
        def common(inputs):
            return {'export': inputs.data('export', export), 'reference_export': inputs.data('reference_export', reference_export)}
        blends = {}
        for kind, title in BLENDS:
            blend_name = f'BS_{name}Adventure{title}'
            package = f'{dest}/{blend_name}'
            inputs = _Inputs()
            args = {'action': 'blend', 'kind': kind, 'name': blend_name, 'dest': dest,
                    'skeleton': inputs.native('skeleton', skeleton), **common(inputs),
                    'clips': clip_inputs(inputs)['clips']}
            unit_id = f'unreal.moveset.{k}.blend.{title}'
            author(unit_id, args, 'BlendSpace1D', package, inputs, 'YorimichiImport')
            packages[package] = {'unit': unit_id, 'item': 'asset', 'package': package}
            blends[kind] = unit_id
        def donor_inputs(inputs):
            return {clip_name: inputs.native('donor_' + clip_name, ref) for clip_name, ref in donor.items()}
        timing = {'donor_spec': {'double_jump': donor_spec['double_jump'], 'gestures': list(donor_spec['gestures']),
                                 'actions': {a: dict(t) for a, t in donor_spec['actions'].items()}}, 'is_donor': is_donor}
        inputs = _Inputs()
        refs = clip_inputs(inputs)
        args = {'action': 'moveset', 'target': spec['definition'], 'base_package': spec['base'],
                'base': inputs.native('base', base), 'keep_base_actions': bool(spec['keep_base_actions']),
                'blends': {kind: inputs.item('blend_' + kind, unit_id, 'asset') for kind, unit_id in blends.items()},
                **common(inputs), 'roster': inputs.data('roster', roster), **refs, 'donor': donor_inputs(inputs), **timing}
        moveset_id = f'unreal.moveset.{k}.definition'
        author(moveset_id, args, 'AdventureMoveSet', spec['definition'], inputs, 'Yorimichi')
        packages[spec['definition']] = {'unit': moveset_id, 'item': 'asset', 'package': spec['definition']}
        inputs = _Inputs()
        refs = clip_inputs(inputs)
        equipment = [inputs.native(f'equipment_{index}', _native(ref, 'reference equipment mesh'))
                     for index, ref in enumerate(reference.get('equipment') or ())]
        if not equipment:
            raise Unsupported('missing exact native Items for the reference equipment meshes')
        args = {'action': 'record', 'character': character.id, **common(inputs), 'roster': inputs.data('roster', roster),
                'skeleton': inputs.native('skeleton', skeleton),
                'reference_skeleton': inputs.native('reference_skeleton', _native(reference.get('skeleton'), 'reference skeleton')),
                'reference_glide': inputs.native('reference_glide', _native(reference.get('glide'), 'reference glide clip')),
                'equipment': equipment, **refs, 'donor': donor_inputs(inputs), 'fit': json.loads(json.dumps(spec.get('fit', {}))),
                **timing}
        record_file = f'{CONTENT}/Data/{character.id}/adventure.json'
        record_id = f'unreal.moveset.{k}.record'
        author(record_id, args, 'JsonData', f'/Game/_Data/{character.id}/adventure', inputs, json_file=record_file)
        packages[record_file] = {'unit': record_id, 'item': 'record'}
        aliases[f'unreal.{k}_adventure'] = tuple(unit['id'] for unit in units if unit['id'].startswith(f'unreal.moveset.{k}.'))
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots, 'packages': packages,
            'aliases': aliases, 'module_requirements': requirements}
