#!/usr/bin/env python3
"""Readable skating runtime source <-> the session's settings, graph, camera, gesture and physics files.

The committed source is one JSON file per runtime file. Floats are binary32 values written as their shortest
round-trip decimal (negative zero as -0.0), as in motion_text.py; a word that is not a finite float is written as the
string "0x" plus 8 hex digits. `build` rewrites every runtime file byte for byte; callers check the result against
the package manifest's SHA-256 digests. `export` is the conversion from the runtime files.

    runtime_text.py export --package <package> --source <runtime source>
    runtime_text.py build --source <runtime source> --package <output folder>
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motion_text import Number, Reader, Writer, word  # noqa: E402

SETTINGS, GRAPH, CAMERA, GESTURES, PHYSICS = b'ATATTR01', b'ATGRPH01', b'ATCAM001', b'ATGEST01', b'ATPHYS01'
# Source file -> runtime file.
FILES = {
    'settings.json': 'settings.skate',
    'action-graph.json': 'action.graph',
    'motion-graph.json': 'motion.graph',
    'camera-graph.json': 'camera.graph',
    'camera.json': 'camera.skate',
    'gestures.json': 'gestures.skate',
    'physics-skeletons.json': 'physics-skeletons.skate',
}
RAW = re.compile(r'^0x[0-9a-f]{8}$')


def finite(value):
    return (value & 0x7f800000) != 0x7f800000


def number(value):
    """A float word: its shortest decimal when finite, otherwise the raw word."""
    return Number(value) if finite(value) else f'0x{value:08x}'


def raw(value):
    return f'0x{value:08x}'


def bits(value):
    """Inverse of number and raw."""
    if isinstance(value, str):
        if not RAW.match(value):
            raise ValueError(f'invalid raw word {value!r}')
        return int(value, 16)
    return word(value)


def integer(value, low=0, high=0xFFFFFFFF):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'expected an integer in [{low}, {high}], found {value!r}')
    return value


# ------------------------------------------------------------------ settings (ATATTR01)
# Each record holds named fields of a reflected type; a field's bytes are packed big-endian into words.
PREFIX = 'EA::Reflection::'
SIGNED = {'Int8': 8, 'Int16': 16, 'Int32': 32, 'Int64': 64}
UNSIGNED = {'UInt8': 8, 'UInt16': 16, 'UInt32': 32, 'UInt64': 64}
SCALARS = {'Float', 'Bool', 'Text', *SIGNED, *UNSIGNED}
FLOATS = re.compile(r'^(Math::Vector[234]|Attrib::Types::(Vector[234]|FloatColour|Matrix)|Sk8::Point(Neg)?GraphData\d+)$')


def short_type(name):
    if name in SCALARS:
        raise ValueError(f'type {name} collides with a scalar abbreviation')
    return name[len(PREFIX):] if name.startswith(PREFIX) and name[len(PREFIX):] in SCALARS else name


def long_type(name):
    return PREFIX + name if name in SCALARS else name


def unpack(values, size):
    """A field's bytes: whole words are big-endian; a last partial word holds its bytes in its low-order bits."""
    data = b''.join(v.to_bytes(4, 'big') for v in values)
    return data[:size // 4 * 4] + data[len(data) - size % 4:] if size % 4 else data


def pack(data):
    padded = b'\0' * (-len(data) % 4) + data[len(data) // 4 * 4:] if len(data) % 4 else b''
    data = data[:len(data) // 4 * 4] + padded
    return [int.from_bytes(data[i:i + 4], 'big') for i in range(0, len(data), 4)]


def field_text(name, size, encoding, value):
    """[type, value] or, for a Bool wider than one byte, [type, value, bytes]."""
    kind = short_type(name)
    if encoding == 1:
        if kind != 'Text':
            raise ValueError(f'text in a {kind} field')
        return [kind, value]
    if kind == 'Text':
        raise ValueError('Text field without text encoding')
    if pack(unpack(value, size)) != value:
        raise ValueError(f'{kind} field words do not hold {size} bytes')
    data = unpack(value, size)
    width = SIGNED.get(kind) or UNSIGNED.get(kind)
    if kind == 'Float' and size == 4 and finite(value[0]):
        return [kind, Number(value[0])]
    if kind == 'Bool' and size and data[0] < 2 and not any(data[1:]):
        return [kind, bool(data[0])] if size == 1 else [kind, bool(data[0]), size]
    if width and size * 8 == width:
        return [kind, int.from_bytes(data, 'big', signed=kind in SIGNED)]
    if size % 4 == 0:
        return [kind, [number(v) if FLOATS.match(kind) else raw(v) for v in value]]
    return [kind, {'words': [raw(v) for v in value], 'bytes': size}]


def field_binary(kind, value, size=None):
    """(type, text encoding, byte count, words or text) of a field's source value."""
    if size is not None and not (kind == 'Bool' and isinstance(value, bool) and integer(size, 2)):
        raise ValueError('only a Bool names its byte count')
    if kind == 'Text':
        if not isinstance(value, str):
            raise ValueError('Text field without a string')
        return long_type(kind), 1, len(value.encode()), value
    if isinstance(value, dict):
        if set(value) != {'words', 'bytes'}:
            raise ValueError('a packed field holds words and bytes')
        values, size = [bits(v) for v in value['words']], integer(value['bytes'])
        if size % 4 == 0 or len(values) != (size + 3) // 4:
            raise ValueError('packed field word count differs from its byte count')
        return long_type(kind), 0, size, values
    if isinstance(value, list):
        return long_type(kind), 0, 4 * len(value), [bits(v) for v in value]
    if isinstance(value, bool):
        if kind != 'Bool':
            raise ValueError(f'boolean in a {kind} field')
        size = size or 1
        return long_type(kind), 0, size, pack(bytes([value]) + b'\0' * (size - 1))
    width = SIGNED.get(kind) or UNSIGNED.get(kind)
    if width and isinstance(value, int):
        size = width // 8
        return long_type(kind), 0, size, pack(value.to_bytes(size, 'big', signed=kind in SIGNED))
    if kind == 'Float':
        return long_type(kind), 0, 4, [bits(value)]
    raise ValueError(f'value does not fit type {kind}')


def settings_text(data):
    r = Reader(data, SETTINGS)
    strings, records = r.word(), r.word()
    strings = [r.string() for _ in range(strings)]
    if strings != sorted(set(strings)):
        raise ValueError('settings strings must be sorted and unique')
    categories = []
    for _ in range(records):
        category, key, parent = (strings[r.word()] for _ in range(3))
        fields = {}
        for _ in range(r.word()):
            name, kind, encoding, size = strings[r.word()], strings[r.word()], r.word(), r.word()
            if name in fields or encoding > 1:
                raise ValueError(f'invalid settings field {name}')
            value = r.data[r.at:r.at + size].decode() if encoding else [r.word() for _ in range((size + 3) // 4)]
            if encoding:
                r.at += size
            fields[name] = field_text(kind, size, encoding, value)
        if not categories or categories[-1]['category'] != category:
            categories.append({'category': category, 'records': []})
        row = {'key': key}
        if parent:
            row['parent'] = parent
        row['fields'] = fields
        categories[-1]['records'].append(row)
    r.end()
    return categories


def settings_binary(categories):
    records = []
    for category in categories:
        for row in category['records']:
            fields = [(name, *field_binary(*value)) for name, value in row['fields'].items()]
            records.append((category['category'], row['key'], row.get('parent', ''), fields))
    strings = sorted({s for c, k, p, fields in records for s in (c, k, p, *(n for f in fields for n in f[:2]))})
    index = {s: i for i, s in enumerate(strings)}
    w = Writer(SETTINGS)
    w.word(len(strings))
    w.word(len(records))
    for s in strings:
        w.string(s)
    for category, key, parent, fields in records:
        for s in (category, key, parent):
            w.word(index[s])
        w.word(len(fields))
        for name, kind, encoding, size, value in fields:
            for v in (index[name], index[kind], encoding, size):
                w.word(v)
            if encoding:
                w.data += value.encode()
            else:
                w.words(value, False)
    return bytes(w.data)


# ------------------------------------------------------------------ graphs (ATGRPH01)
# A tree of tagged elements with ordered text attributes. Each attribute's float word and boolean byte, and each
# element's source offset, follow from the text and are written as the session reads them.
DECIMAL = re.compile(r'^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$')


def attribute_float(text):
    return word(float(text)) if DECIMAL.match(text) else 0


def element_size(tag, attributes):
    return (len(tag.encode()) + 1 + 4 + sum(len(n.encode()) + len(t.encode()) + 7 for n, t in attributes.items())
            + 4)


def graph_text(data):
    r = Reader(data, GRAPH)
    strings, count = r.word(), r.word()
    strings = [r.string() for _ in range(strings)]
    elements = []
    for _ in range(count):
        offset, tag, attributes, children = r.word(), strings[r.word()], r.word(), r.word()
        attributes = [(strings[r.word()], strings[r.word()], r.word(), r.word()) for _ in range(attributes)]
        elements.append((offset, tag, attributes, [r.word() for _ in range(children)]))
    r.end()

    def node(index):
        offset, tag, attributes, children = elements[index]
        if tag == 'children' or len({a[0] for a in attributes}) != len(attributes):
            raise ValueError(f'graph element {index} cannot be written as JSON')
        out = {tag: {name: text for name, text, _, _ in attributes}}
        if children:
            out['children'] = [node(c) for c in children]
        return out
    return node(0)


def graph_binary(root):
    elements = []
    offset = 0

    def visit(node):
        nonlocal offset
        tags = [k for k in node if k != 'children']
        if len(tags) != 1 or not isinstance(node[tags[0]], dict):
            raise ValueError('a graph element is one tag with its attributes, and optional children')
        tag, attributes = tags[0], node[tags[0]]
        if not all(isinstance(t, str) for t in attributes.values()):
            raise ValueError(f'{tag}: attribute values are text')
        element = (offset, tag, attributes, [])
        elements.append(element)
        offset += element_size(tag, attributes)
        for child in node.get('children', []):
            element[3].append(len(elements))
            visit(child)
    visit(root)
    strings = sorted({e[1] for e in elements} | {s for e in elements for a in e[2].items() for s in a})
    index = {s: i for i, s in enumerate(strings)}
    w = Writer(GRAPH)
    w.word(len(strings))
    w.word(len(elements))
    for s in strings:
        w.string(s)
    for offset, tag, attributes, children in elements:
        for v in (offset, index[tag], len(attributes), len(children)):
            w.word(v)
        for name, text in attributes.items():
            for v in (index[name], index[text], attribute_float(text), int(text == 'true')):
                w.word(v)
        w.words(children, False)
    return bytes(w.data)


# ------------------------------------------------------------------ camera (ATCAM001)
# (name, words); integer fields are written as integers, every other word as a float.
SHOT = (('distance', 1), ('lens_length', 1), ('smoothing', 4), ('reference_weights', 10), ('board_offset', 1),
        ('position_heading', 1), ('position_elevation', 1), ('framing', 3), ('follow_subject_in_air', 1),
        ('mirror_for_stance', 1), ('snap_to_reference_point', 1), ('use_previous_shot', 1), ('use_drop_predictor', 1),
        ('use_free_camera_stick', 1), ('avoidance_override', 1), ('blur', 1), ('transition_blur', 1),
        ('subject_opacity', 1), ('collision_hint', 1), ('anchor', 1), ('compass_north', 1), ('world_heading', 1),
        ('arm_orientation', 4), ('camera_orientation', 4))
SHOT_INTEGERS = {'follow_subject_in_air', 'mirror_for_stance', 'snap_to_reference_point', 'use_previous_shot',
                 'use_drop_predictor', 'use_free_camera_stick', 'avoidance_override', 'collision_hint', 'anchor',
                 'compass_north'}


def camera_text(data):
    r = Reader(data, CAMERA)
    identity, shots = r.string(), []
    for _ in range(r.word()):
        shot = {'name': r.string(), 'shot_type': r.word()}
        for name, size in SHOT:
            values = [r.word() for _ in range(size)]
            if name not in SHOT_INTEGERS:
                values = [number(v) for v in values]
            shot[name] = values[0] if size == 1 else values
        shot['transition_time'], shot['transition_units'] = number(r.word()), r.word()
        children = []
        for _ in range(3):
            present = r.word()
            if present > 1:
                raise ValueError('invalid camera child slot')
            children.append(r.string() if present else None)
        shot['children'] = children
        shot['blend_points'] = [number(r.word()) for _ in range(3)]
        shot['blend_value'], shot['blend_type'], shot['blend_smoothing'] = number(r.word()), r.word(), number(r.word())
        shots.append(shot)
    shakes = []
    for _ in range(2):
        samples = [[number(r.word()) for _ in range(8)] for _ in range(r.word())]
        shakes.append({'rotations': [s[:4] for s in samples], 'translations': [s[4:] for s in samples]})
    r.end()
    return {'source_identity': identity, 'shots': shots, 'shakes': shakes}


def camera_binary(value):
    w = Writer(CAMERA)
    w.string(value['source_identity'])
    w.word(len(value['shots']))
    for shot in value['shots']:
        expected = ['name', 'shot_type', *(n for n, _ in SHOT), 'transition_time', 'transition_units', 'children',
                    'blend_points', 'blend_value', 'blend_type', 'blend_smoothing']
        if list(shot) != expected:
            raise ValueError(f'camera shot {shot.get("name")}: fields must be {expected}')
        w.string(shot['name'])
        w.word(integer(shot['shot_type']))
        for name, size in SHOT:
            values = [shot[name]] if size == 1 else shot[name]
            if len(values) != size:
                raise ValueError(f'camera shot {shot["name"]}: {name} has {size} values')
            w.words([integer(v) if name in SHOT_INTEGERS else bits(v) for v in values], False)
        w.word(bits(shot['transition_time']))
        w.word(integer(shot['transition_units']))
        if len(shot['children']) != 3:
            raise ValueError('a camera shot has three child slots')
        for child in shot['children']:
            w.word(child is not None)
            if child is not None:
                w.string(child)
        if len(shot['blend_points']) != 3:
            raise ValueError('a camera shot has three blend points')
        w.words([bits(v) for v in shot['blend_points']], False)
        w.word(bits(shot['blend_value']))
        w.word(integer(shot['blend_type']))
        w.word(bits(shot['blend_smoothing']))
    if len(value['shakes']) != 2:
        raise ValueError('camera data has two shakes')
    for shake in value['shakes']:
        if len(shake['rotations']) != len(shake['translations']):
            raise ValueError('a shake has one translation per rotation')
        w.word(len(shake['rotations']))
        for rotation, translation in zip(shake['rotations'], shake['translations']):
            if len(rotation) != 4 or len(translation) != 4:
                raise ValueError('shake samples have four rotation and four translation values')
            w.words([bits(v) for v in rotation + translation], False)
    return bytes(w.data)


# ------------------------------------------------------------------ gestures (ATGEST01)
def gestures_text(data):
    r = Reader(data, GESTURES)
    sets = []
    for _ in range(r.word()):
        gesture = {'name': r.string(), 'stick': r.word(), 'patterns': []}
        for _ in range(r.word()):
            pattern = {'name': r.string(), 'tolerance_squared': number(r.word())}
            pattern['points'] = [[number(r.word()), number(r.word())] for _ in range(r.word())]
            gesture['patterns'].append(pattern)
        sets.append(gesture)
    r.end()
    return sets


def gestures_binary(sets):
    w = Writer(GESTURES)
    w.word(len(sets))
    for gesture in sets:
        w.string(gesture['name'])
        w.word(integer(gesture['stick']))
        w.word(len(gesture['patterns']))
        for pattern in gesture['patterns']:
            w.string(pattern['name'])
            w.word(bits(pattern['tolerance_squared']))
            w.word(len(pattern['points']))
            for point in pattern['points']:
                if len(point) != 2:
                    raise ValueError(f'gesture {pattern["name"]}: points are [x, y]')
                w.words([bits(v) for v in point], False)
    return bytes(w.data)


# ------------------------------------------------------------------ physical skeletons (ATPHYS01)
BONE_WORDS = 28


def physics_text(data):
    r = Reader(data, PHYSICS)
    value = {'source_sha256': r.string(), 'skeletons': []}
    for _ in range(r.word()):
        skeleton = {'name': r.string(), 'source_offset': r.wide(), 'bones': []}
        for _ in range(r.word()):
            skeleton['bones'].append({'name': r.string(), 'source_offset': r.wide(),
                                      'words': [number(v) for v in (r.word() for _ in range(BONE_WORDS))]})
        value['skeletons'].append(skeleton)
    r.end()
    return value


def physics_binary(value):
    w = Writer(PHYSICS)
    w.string(value['source_sha256'])
    w.word(len(value['skeletons']))
    for skeleton in value['skeletons']:
        w.string(skeleton['name'])
        w.wide(integer(skeleton['source_offset'], high=(1 << 64) - 1))
        w.word(len(skeleton['bones']))
        for bone in skeleton['bones']:
            if len(bone['words']) != BONE_WORDS:
                raise ValueError(f'physical bone {bone["name"]} has {BONE_WORDS} words')
            w.string(bone['name'])
            w.wide(integer(bone['source_offset'], high=(1 << 64) - 1))
            w.words([bits(v) for v in bone['words']], False)
    return bytes(w.data)


FORMATS = {
    'settings.skate': (settings_text, settings_binary),
    'action.graph': (graph_text, graph_binary),
    'motion.graph': (graph_text, graph_binary),
    'camera.graph': (graph_text, graph_binary),
    'camera.skate': (camera_text, camera_binary),
    'gestures.skate': (gestures_text, gestures_binary),
    'physics-skeletons.skate': (physics_text, physics_binary),
}


# ------------------------------------------------------------------ files

def dumps(value, indent=0, width=118):
    """JSON with a container on one line when it fits in width, otherwise one item per line."""
    def line(v):
        if isinstance(v, Number):
            return repr(v)
        if isinstance(v, dict):
            return '{' + ', '.join(json.dumps(k) + ': ' + line(x) for k, x in v.items()) + '}'
        if isinstance(v, list):
            return '[' + ', '.join(line(x) for x in v) + ']'
        return json.dumps(v, ensure_ascii=False)
    one = line(value)
    if not isinstance(value, (dict, list)) or not value or indent + len(one) <= width:
        return one
    pad, inner = ' ' * indent, ' ' * (indent + 2)
    if isinstance(value, dict):
        rows = [f'{inner}{json.dumps(k, ensure_ascii=False)}: {dumps(v, indent + 2, width).lstrip()}'
                for k, v in value.items()]
        return '{\n' + ',\n'.join(rows) + f'\n{pad}}}'
    return '[\n' + ',\n'.join(inner + dumps(v, indent + 2, width) for v in value) + f'\n{pad}]'


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key {key}')
        result[key] = value
    return result


def export(package, source):
    """Runtime files -> readable source. Returns the written relative paths."""
    package, source = Path(package), Path(source)
    source.mkdir(parents=True, exist_ok=True)
    for text, binary in FILES.items():
        (source / text).write_text(dumps(FORMATS[binary][0]((package / binary).read_bytes())) + '\n')
    return sorted(FILES)


def build(source):
    """Readable source -> {runtime file name: bytes}."""
    source = Path(source)
    found = sorted(p.name for p in source.iterdir())
    if found != sorted(FILES):
        raise ValueError(f'the runtime source holds exactly {sorted(FILES)}, found {found}')
    return {binary: FORMATS[binary][1](json.loads((source / text).read_text(), object_pairs_hook=unique))
            for text, binary in FILES.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('export', 'build'))
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'export':
        print(f'{len(export(args.package, args.source))} source files')
        return
    files = build(args.source)
    args.package.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (args.package / name).write_bytes(data)
    print(f'{len(files)} runtime files')


if __name__ == '__main__':
    main()
