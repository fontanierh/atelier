"""Per-cue ordinary WAV groups and native owners over committed audio declarations."""
import ast
from pathlib import Path

from v2_audio_units import GAPS, ROSTER, Unsupported, _check, _output
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, _code

RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'


def _data(node, env):
    """Evaluate finite source data only; never import or execute a generator."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_data(value, env) for value in node.elts]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _data(node.left, env) + _data(node.right, env)
    if isinstance(node, ast.ListComp) and len(node.generators) == 1:
        generator = node.generators[0]
        if isinstance(generator.target, ast.Name) and not generator.ifs and not generator.is_async:
            return [_data(node.elt, {**env, generator.target.id: value})
                    for value in _data(generator.iter, env)]
    raise Unsupported('audio cue declaration is not finite literal source data')


def _assignment(tree, name):
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(values) != 1:
        raise Unsupported('missing or ambiguous audio source declaration: ' + name)
    return values[0]


def cue_settings(producer, *, checkout):
    """Read committed cue/loop declarations without loading their side-effectful modules."""
    script = ROSTER[producer][1]
    tree = ast.parse((Path(checkout) / script).read_bytes(), filename=script)
    if producer == 'audio.footsteps':
        fetch = script.rsplit('/', 1)[0] + '/fetch.py'
        picks = ast.literal_eval(_assignment(ast.parse((Path(checkout) / fetch).read_bytes()), 'PICKS'))
        cues = {pick[0]: False for pick in picks}
    elif producer in ('audio.combat', 'audio.transport', 'audio.kart'):
        mapping = _assignment(tree, 'SPEC' if producer == 'audio.combat' else 'CUES')
        if not isinstance(mapping, ast.Dict):
            raise Unsupported('audio cue table must be a literal mapping')
        cues = {}
        for key, value in zip(mapping.keys, mapping.values):
            name = ast.literal_eval(key)
            if producer == 'audio.kart':
                looping = ast.literal_eval(value)[1]
            elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'dict':
                fields = {field.arg: field.value for field in value.keywords}
                looping = ('loop' in fields if producer == 'audio.combat'
                           else ast.literal_eval(fields['loop']))
            else:
                raise Unsupported('audio cue settings differ from original dict declarations')
            if name in cues or type(looping) is not bool:
                raise Unsupported('duplicate cue or nonboolean audio loop policy')
            cues[name] = looping
    else:
        env = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                try:
                    value = _data(node.value, env)
                except Unsupported:
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        env[target.id] = value
        names = set()
        main = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main']
        if len(main) != 1:
            raise Unsupported('audio generator requires its original main body')
        def collect(node, bindings):
            if isinstance(node, ast.For):
                try:
                    values = _data(node.iter, bindings)
                except Unsupported:
                    values = [None]
                if not isinstance(values, list) or len(values) > 128:
                    raise Unsupported('audio cue loop exceeds its finite source bound')
                for value in values:
                    nested = dict(bindings)
                    if isinstance(node.target, ast.Name) and value is not None:
                        nested[node.target.id] = value
                    for child in (*node.body, *node.orelse):
                        collect(child, nested)
                return
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == 'report':
                names.add(_data(node.slice, bindings))
            for child in ast.iter_child_nodes(node):
                collect(child, bindings)
        collect(main[0], env)
        if producer == 'audio.bike':
            loops = _data(_assignment(tree, 'LOOPS'), env)
        else:
            loops_nodes = [value for node in ast.walk(main[0]) if isinstance(node, ast.Dict)
                           for key, value in zip(node.keys, node.values)
                           if isinstance(key, ast.Constant) and key.value == 'loops']
            if len(loops_nodes) != 1:
                raise Unsupported('skate manifest loop declaration is ambiguous')
            loops = _data(loops_nodes[0], env)
        if set(loops) - names or len(set(loops)) != len(loops):
            raise Unsupported('loop cue does not name exactly one authored cue')
        cues = {name: name in loops for name in names}
    if not cues or any(not isinstance(name, str) or not name.isascii()
                       or not name.replace('_', '').isalnum() or not name[0].isalpha() for name in cues):
        raise Unsupported('audio source has unsupported cue names')
    return dict(sorted(cues.items()))


def audio_templates(rows, *, checkout):
    """@cc [owner:fontanierh,label:correctness] finite-audio-native-templates
    Cue roles and loop policy MUST derive from committed original source declarations,
    never generated manifests or native assets. Each projection MUST consume the actual
    complete producer ROOT and publish a strict per-cue FileSet. Native templates MUST
    consume only the selected member, preserving its filename, original destination and
    loop/stream policy. Attenuation and FootstepSet ownership MUST remain explicit gaps;
    this constructor MUST NOT certify the whole unreal.sounds target complete.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout)
    selected = [row for row in rows if row['id'] in ROSTER]
    if len({row['id'] for row in selected}) != len(selected):
        raise Unsupported('duplicate audio producer')
    scanner = ImportScanner()
    projection_code = sorted({path.relative_to(root).as_posix() for script in (RECIPE, EMITTER)
                              for path in scanner.local_imports(root / script, (root / 'platform/studio',))})
    native_code = _code(root) if selected else []
    units, templates, groups, staged, slots, packages = [], [], {}, {}, {}, {}
    for row in selected:
        _check(row)
        family, generator, folder, surfaces, _, fixed = ROSTER[row['id']]
        product_index = next(index for index, product in enumerate(row['products']) if product['id'] == row['id'])
        archive = f'products/{product_index}-0.tree.tar'
        source_code = [generator]
        if surfaces:
            source_code.append(generator.rsplit('/', 1)[0] + '/fetch.py')
        for cue, looping in cue_settings(row['id'], checkout=root).items():
            producer = row['id'] + '.files.' + cue
            prefix = 'unreal.sound.raw.' + family + '.' + cue
            destination = folder + ('/' + cue if surfaces else '')
            raw_folder = '/Game/_Raw/' + destination.removeprefix('/Game/')
            parent = 'Audio_' + family + '_' + cue
            contract = {'id': 'waves', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                        'adapter_version': 'd2.file-set/1', 'parent': parent, 'encoding': 'file_set',
                        'class': 'Data', 'logical_namespace': '/Internal/Audio/' + family + '/' + cue, **LIMITS}
            units.append({'id': producer, 'op': {'kind': 'recipe.python', 'version': '1'},
                'script': RECIPE, 'code': sorted(set(projection_code + source_code)),
                'inputs': [{'role': 'content', 'name': 'source',
                            'source': {'kind': 'item', 'unit': row['id'], 'item': 'product' + str(product_index)},
                            'whole': 'projection validates the complete owned source ROOT before selecting this cue'}],
                'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'commands': [], 'outputs': [],
                    'paths': {'source': 'inputs/source/' + archive}, 'verify': None,
                    'file_group': {'source': 'source/' + cue, 'parent': parent, 'extensions': ['.wav']}}},
                'outputs': [], 'output_groups': [contract]})
            staged[producer] = {'source': 'inputs/source'}
            raw_output = _output(raw_folder + '/$piece', raw=True)
            finish_output = _output(destination + '/$piece', raw=False)
            finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'},
                'script': OPS, 'code': native_code,
                'inputs': [{'role': 'content', 'name': 'raw',
                            'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
                'params': {'op': 'finish', 'kind': 'sound', 'source': 'raw',
                    'destination': destination + '/$piece', 'package_sources': {'raw': raw_folder + '/$piece'},
                    'properties': dict(fixed) if fixed else {'looping': looping}}, 'outputs': [finish_output]}
            templates.append({'producer': producer, 'group': 'waves', 'unit_prefix': prefix,
                'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': native_code,
                'derive_payload': False, 'params': {'op': 'raw_import', 'kind': 'sound', 'source': 'source',
                    'destination': raw_folder + '/$piece'}, 'payload_slot': 'source', 'staged_path': 'inputs/source',
                'output_class': raw_output['class'], 'logical_namespace': raw_folder,
                'files': raw_output['files'],
                'followers': [{'unit': finish, 'staged_inputs': {'raw': 'inputs/raw'}}]})
            groups[producer] = {'contract': contract, 'source': 'source/' + cue}
            packages[producer] = {'derived_items': {'templates': [{'producer': producer, 'group': 'waves',
                'unit_prefix': prefix, 'follower': 0, 'item': 'sound'}],
                'root': 'build/v2-derived/audio/' + family + '/' + cue}}
    slots['source'] = False
    return {'units': units, 'templates': templates, 'groups': groups, 'staged_inputs': staged,
            'content_slots': slots, 'packages': packages, 'gaps': list(GAPS), 'aliases': {}}
