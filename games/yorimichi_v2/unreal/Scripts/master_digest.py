"""Wiring digest of a material master, and the rule that accepts a rebuilt master only when it equals the saved original.

The digest records what a graph is, not how Unreal happens to list it: each expression's class and its own settings
(parameter name, default, texture, sampler, constants), each input connection (source expression and output, destination
expression and input), each material property connection, and the blend mode, shading model and two-sided flag.
Expression indices and object names are not recorded, since a rebuild in another package has other names. The three
lists are compared as multisets for diagnostics. Version 3 fingerprints the graph rooted at each material property,
including each node's ordered input pins and upstream structure, plus each root's native output index and component masks.
Older reports must be read again; lossy connection labels or roots without their masks cannot establish equivalence.
Customized UV roots are hidden from Unreal's Python enum. This reader refuses enabled customized UV inputs, and reports
must record a disabled count explicitly; an older report without that count cannot establish equivalence either.

The graph is what the master renders: the expressions reachable from its property pins. An expression wired to nothing
compiles into no shader, so it is listed apart as `unwired` and not compared with historical originals. The importer clears
old expressions before rebuilding and separately requires the saved graph's unwired nodes to equal the fresh build's.
Parameters still count, since a material instance can see every parameter of its parent: `parameters` lists each distinct
parameter expression of the whole graph, wired or not, and is compared.

The pure functions (canonical, accept) run without the Unreal editor, and the tests use them. read() needs the editor and
is the only part that touches it. A part that cannot be read makes the whole digest an error, which refuses the master:
a partial digest never matches.
"""
import collections
import hashlib
import json
import re

try:
    import unreal as U
except ImportError:   # outside the editor only the pure functions are usable
    U = None

# Every material-level property a builder writes, plus the domain: a cutoff or a usage flag that differs refuses.
SETTINGS = ('blend_mode', 'shading_model', 'two_sided', 'material_domain', 'opacity_mask_clip_value',
            'used_with_instanced_static_meshes', 'used_with_skeletal_mesh', 'used_with_static_lighting',
            'translucency_lighting_mode', 'is_sky', 'blendable_location', 'dithered_lod_transition',
            'tangent_space_normal', 'compute_fog_per_pixel', 'num_customized_u_vs',
            'max_world_position_offset_displacement', 'use_translucency_vertex_fog', 'output_translucent_velocity')
PROPERTY_PINS = ('MP_BASE_COLOR', 'MP_NORMAL', 'MP_ROUGHNESS', 'MP_METALLIC', 'MP_SPECULAR', 'MP_EMISSIVE_COLOR',
                 'MP_OPACITY', 'MP_OPACITY_MASK', 'MP_AMBIENT_OCCLUSION', 'MP_WORLD_POSITION_OFFSET', 'MP_REFRACTION',
                 'MP_PIXEL_DEPTH_OFFSET', 'MP_SUBSURFACE_COLOR', 'MP_CUSTOM_DATA0', 'MP_CUSTOM_DATA1', 'MP_TANGENT',
                 'MP_ANISOTROPY', 'MP_SHADING_MODEL')   # a pin this engine does not have is skipped on both sides alike
CUSTOM_OUTPUT_CLASSES = ('MaterialExpressionSingleLayerWaterMaterialOutput',)
EXPRESSION_PROPERTIES = ('parameter_name', 'default_value', 'r', 'constant', 'const_a', 'const_b', 'texture',
                         'sampler_type', 'code', 'coordinate_index', 'u_tiling', 'v_tiling', 'un_mirror_u', 'un_mirror_v',
                         'output_type', 'data_index', 'const_default_value',
                         'inputs', 'scene_texture_id', 'filtered', 'collection', 'g', 'b', 'a', 'material_function',
                         'use_custom_primitive_data', 'primitive_data_index',
                         'transform_source_type', 'transform_type', 'world_position_shader_offset',
                         'ignore_pause', 'override_period', 'period', 'input_mode', 'const_input', 'fallback_depth',
                         # Defaults matter too: these are the remaining rendering fields of the used UE 5.8 node classes.
                         'sampler_source', 'const_coordinate', 'mip_value_mode', 'const_mip_value',
                         'automatic_view_mip_bias', 'gather_mode', 'const_alpha', 'included_offsets', 'local_origin',
                         'const_periodic_world_tile_size', 'const_first_person_interpolation_alpha',
                         'additional_outputs', 'additional_defines', 'include_file_paths', 'contains_clip_instruction')
# Descriptions/UI/generated editor state are excluded. ExternalCodeIdentifiers is engine class configuration from
# MaterialExpressions.ini; GetExternalCodeReferencesHash reads it from class default objects, not authored node settings.
LISTS = ('expressions', 'connections', 'property_connections')
SETS = ('parameters',)
TOPOLOGY_VERSION = 3


def _norm(value):
    """A canonical JSON value: floats to six places, lists element by element, anything else as text."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    return str(value)


def canonical(digest):
    """Pure: the digest with its settings normalised and each list sorted, so no order Unreal chose matters."""
    return {'settings': {k: _norm(v) for k, v in sorted(digest['settings'].items())},
            'expressions': sorted(digest['expressions']),
            'connections': sorted(digest['connections']),
            'property_connections': sorted(digest['property_connections']),
            'parameters': sorted(set(digest.get('parameters', ()))),
            'unwired': sorted(digest.get('unwired', ())),
            'topology': digest['topology']}


def accept(saved, rebuilt):
    """@cc [owner:fontanierh,label:correctness] master-digest-equals-saved
    A rebuilt master is accepted only when its wiring digest equals the saved original's, with nothing missing on either side:
    the settings, rooted topology with ordered input pins, the rendered graph and every parameter. An unwired expression
    is not compared, unless it carries a parameter. An unreadable or legacy digest without version 3 topology refuses;
    lossy local-node labels MUST NOT be used to invent that topology. Both reports MUST explicitly record a disabled
    customized-UV count; those hidden roots are not supported. Returns differences; empty means accepted."""
    for label, digest in (('saved original', saved), ('rebuilt master', rebuilt)):
        if 'error' in digest:
            return [f'{label} could not be read: {digest["error"]}']
        topology = digest.get('topology')
        if not isinstance(topology, dict) or topology.get('version') != TOPOLOGY_VERSION \
                or not isinstance(topology.get('roots'), dict):
            return [f'{label} lacks version {TOPOLOGY_VERSION} rooted topology; collect a new read-only report']
        if digest.get('settings', {}).get('num_customized_u_vs') != '0':
            return [f'{label} lacks a supported customized-UV count of 0; collect a new read-only report']
    a, b = canonical(saved), canonical(rebuilt)
    problems = []
    for key in sorted(set(a['settings']) | set(b['settings'])):
        if a['settings'].get(key) != b['settings'].get(key):
            problems.append(f'{key}: saved {a["settings"].get(key)!r}, rebuilt {b["settings"].get(key)!r}')
    for key in LISTS:
        left, right = collections.Counter(a[key]), collections.Counter(b[key])
        for text in sorted((left - right).elements()):
            problems.append(f'{key} only in the saved original: {text}')
        for text in sorted((right - left).elements()):
            problems.append(f'{key} only in the rebuilt master: {text}')
    for key in SETS:
        left, right = set(a[key]), set(b[key])
        problems += [f'{key} only in the saved original: {text}' for text in sorted(left - right)]
        problems += [f'{key} only in the rebuilt master: {text}' for text in sorted(right - left)]
    left, right = a['topology']['roots'], b['topology']['roots']
    for pin in sorted(set(left) | set(right)):
        if left.get(pin) != right.get(pin):
            problems.append(f'rendered topology differs at {pin}')
    return problems


def _rooted_topology(nodes, roots):
    """@cc [owner:fontanierh,label:correctness] master-digest-rooted-inputs
    Each root MUST identify its expression properties and complete upstream structure, retaining input order, pin names
    and source output names. Engine node names and enumeration order MUST NOT affect this identity. Cycles refuse.
    `nodes` maps temporary engine identities to (local expression text, ordered inputs); roots name material properties.
    Each input is (pin name, source output name, source identity), or None for an unconnected pin."""
    complete, visiting = {}, set()

    def identity(key):
        if key in complete:
            return complete[key]
        if key in visiting:
            raise ValueError('a material expression graph contains a cycle')
        visiting.add(key)
        local, inputs = nodes[key]
        ordered = [None if edge is None else [edge[0], edge[1], identity(edge[2])] for edge in inputs]
        payload = json.dumps([local, ordered], separators=(',', ':'), ensure_ascii=True).encode()
        complete[key] = hashlib.sha256(payload).hexdigest()
        visiting.remove(key)
        return complete[key]

    return {'version': TOPOLOGY_VERSION,
            'roots': {pin: [output, identity(key)] for pin, (output, key) in sorted(roots.items())}}


def _custom_input_name(value):
    """The name of a Custom node input (a CustomInput struct exposes it only through get_editor_property), else None."""
    if type(value).__name__ != 'CustomInput':
        return None
    return str(value.get_editor_property('input_name'))


def _value(value):
    if isinstance(value, (list, tuple)) or type(value).__name__ == 'Array':   # an engine Array is not a list
        return [_value(v) for v in value]
    name = _custom_input_name(value)
    if name is not None:   # a Custom node input: its name, never the struct's text
        return name
    fields = {'CustomOutput': ('output_name', 'output_type'), 'CustomDefine': ('define_name', 'define_value')}
    if type(value).__name__ in fields:
        return [str(value.get_editor_property(field)) for field in fields[type(value).__name__]]
    if hasattr(value, 'get_path_name'):
        return value.get_path_name().split('.')[0]
    if hasattr(value, 'r') and hasattr(value, 'a'):
        return [float(value.r), float(value.g), float(value.b), float(value.a)]
    if hasattr(value, 'x') and hasattr(value, 'y') and not hasattr(value, 'z'):
        return [float(value.x), float(value.y)]
    return value


def _expression_text(expression):
    """The class and its settings, as canonical JSON. Only UE's explicit absent-property result may be skipped."""
    kind = type(expression).__name__
    props = {}
    for prop in EXPRESSION_PROPERTIES:
        # These exact fields are FExpressionInput connections in the installed headers, read by the native input audit.
        # ComponentMask A/B and scalar/vector DefaultValue are real settings and must still be read (or refuse).
        if (prop in ('a', 'b') and kind in {'MaterialExpressionAdd', 'MaterialExpressionAppendVector',
                                          'MaterialExpressionLinearInterpolate', 'MaterialExpressionMultiply',
                                          'MaterialExpressionDotProduct', 'MaterialExpressionSubtract',
                                          'MaterialExpressionDivide'}) \
                or (prop == 'default_value' and kind == 'MaterialExpressionPerInstanceCustomData'):
            continue
        try:
            value = expression.get_editor_property(prop)
        except Exception as error:
            # PyWrapperObject::FindEditorPropertyImpl + PyUtil::SetPythonError in UE 5.8. Protected/read/conversion
            # failures of present properties have different messages and must make the whole digest unreadable.
            missing = rf"[^\n]+: Failed to find property '[^'\n]+' for attribute '{re.escape(prop)}' on '[^'\n]+'"
            if re.fullmatch(missing, str(error)):
                continue
            raise
        props[prop] = _norm(_value(value))
    return json.dumps({'class': kind, 'props': props}, sort_keys=True)


def _selected_output(selected, source):
    """Validate and label the native source/output/masks of either an expression input or a material-property root."""
    if selected.error:
        raise ValueError(f'material input audit: {selected.error}')
    if selected.source_path != source.get_path_name():
        raise ValueError('native input differs from the material input enumeration')
    output = int(selected.output_index)
    names = U.MaterialEditingLibrary.get_material_expression_output_names(source)
    if not 0 <= output < len(names):
        raise ValueError('native input has an unreadable output index')
    mask = [int(value) for value in selected.masks]
    if len(mask) != 5:
        raise ValueError('native input audit has an incomplete component mask')
    return json.dumps({'index': output, 'name': str(names[output]), 'mask': mask}, sort_keys=True)


def _input_output(expression, index, source):
    """Use the native read-only accessor: protected FExpressionInput members cannot be read through Python reflection.
    The source-node lookup returns only the first matching connection, so every connected input is read by index."""
    return _selected_output(U.MaterialInputAudit.read_input(expression, index), source)


def _digest(material):
    MEL = U.MaterialEditingLibrary
    settings = {}
    for key in SETTINGS:
        value = material.get_editor_property(key)
        settings[key] = value if isinstance(value, (bool, float)) else str(value)
    if settings['num_customized_u_vs'] != '0':
        raise ValueError('customized UV inputs are not supported by the master digest')
    every = list(MEL.get_material_expressions(material) or [])
    text = {}
    for expression in every:
        text[expression.get_path_name()] = _expression_text(expression)

    def named(expression):
        return text.get(expression.get_path_name()) or _expression_text(expression)

    pins = {}
    for pin in PROPERTY_PINS:
        if not hasattr(U.MaterialProperty, pin):
            continue
        node = MEL.get_material_property_input_node(material, getattr(U.MaterialProperty, pin))
        if node is not None:
            pins[pin] = node
    custom_outputs = sorted([e for e in every if type(e).__name__ in CUSTOM_OUTPUT_CLASSES],
                            key=lambda e: (type(e).__name__, named(e), e.get_path_name()))
    reached, todo = {}, list(pins.values()) + custom_outputs
    while todo:   # the rendered graph: everything an output pin or custom output reaches through input connections
        node = todo.pop()
        if node.get_path_name() in reached:
            continue
        reached[node.get_path_name()] = node
        todo += [s for s in (MEL.get_inputs_for_material_expression(material, node) or []) if s is not None]
    expressions = list(reached.values())
    unwired = [text[e.get_path_name()] for e in every if e.get_path_name() not in reached]
    parameters = [text[e.get_path_name()] for e in every if json.loads(text[e.get_path_name()])['props'].get('parameter_name')]

    connections, nodes = [], {}
    for expression in expressions:
        # One entry per input pin, unwired pins as None; the names list walks the same pins in the same order.
        sources = list(MEL.get_inputs_for_material_expression(material, expression) or [])
        names = [str(name) for name in (MEL.get_material_expression_input_names(expression) or [])]
        inputs = []
        for index, source in enumerate(sources):
            if source is None:
                inputs.append(None)
                continue
            out = _input_output(expression, index, source)
            pin = (names[index] if index < len(names) else '') or f'#{index}'
            connections.append(f'{named(source)}.{out} -> {named(expression)}.{pin}')
            inputs.append((pin, out, source.get_path_name()))
        nodes[expression.get_path_name()] = (named(expression), inputs)
    property_connections, roots = [], {}
    for pin, node in pins.items():
        out = _selected_output(U.MaterialInputAudit.read_property_input(material, getattr(U.MaterialProperty, pin)), node)
        property_connections.append(f'{pin} <- {named(node)}.{out}')
        roots[pin] = (out, node.get_path_name())
    for index, node in enumerate(custom_outputs):
        pin = f'CUSTOM_OUTPUT:{type(node).__name__}:{index}'
        property_connections.append(f'{pin} <- {named(node)}')
        roots[pin] = ('', node.get_path_name())
    return {'settings': settings, 'expressions': [named(e) for e in expressions], 'connections': connections,
            'property_connections': property_connections, 'parameters': parameters, 'unwired': unwired,
            'topology': _rooted_topology(nodes, roots)}


def read(material):
    """The wiring digest of a loaded material master, or {'error': ...} when any part of it cannot be read."""
    try:
        return _digest(material)
    except Exception as error:   # an unreadable part makes the digest unusable; a partial digest never matches
        return {'error': repr(error)}


def compare_reports(saved, rebuilt):
    """Pure: two report_masters.py outputs ({package: row}) compared per package by accept(). A package in only one report,
    or a row without a wiring digest, is a problem. Returns {package: [problems]}; accepted when the list is empty."""
    missing = {'error': 'no wiring digest in the row'}
    out = {}
    for package in sorted(set(saved) | set(rebuilt)):
        if package not in saved or package not in rebuilt:
            side = 'rebuilt' if package not in rebuilt else 'saved'
            out[package] = [f'missing from the {side} report']
            continue
        out[package] = accept(saved[package].get('wiring', missing), rebuilt[package].get('wiring', missing))
    return out


def main(argv=None):
    """Compare two report files: `master_digest.py SAVED_REPORT.json REBUILT_REPORT.json`. Exit 0 only when every package is accepted."""
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print('usage: master_digest.py SAVED_REPORT.json REBUILT_REPORT.json', file=sys.stderr)
        return 2
    with open(argv[0]) as f:
        saved = json.load(f)
    with open(argv[1]) as f:
        rebuilt = json.load(f)
    result = compare_reports(saved, rebuilt)
    for package, problems in result.items():
        print(('accepted ' if not problems else 'DIFFERS  ') + package)
        dropped = len(saved.get(package, {}).get('wiring', {}).get('unwired', ()))
        if dropped:
            print(f'    the saved original has {dropped} unwired expression(s), not compared')
        for problem in problems:
            print('    ' + problem)
    return 0 if all(not problems for problems in result.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
