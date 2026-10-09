#!/usr/bin/env python3
"""Readable skating motion source <-> ATSKEL01/ATCLIP01/ATMETA01 files.

The committed source is JSON: the rig and its reference poses, two metadata banks and one file per clip. Floats are
binary32 values written as their shortest round-trip decimal (negative zero as -0.0), so `build` rewrites every binary
file byte for byte; callers check the result against the package manifest's SHA-256 digests. `export` is the
one-time conversion from the binary files.

    motion_text.py export --package <package> --source <motion source>
    motion_text.py build --source <motion source> --package <output folder>
"""
import argparse
import json
import math
from pathlib import Path
import struct

import numpy as np

RIG, CLIP, META = b'ATSKEL01', b'ATCLIP01', b'ATMETA01'
COMPONENTS = ('scale_x', 'scale_y', 'scale_z', 'rotation_x', 'rotation_y', 'rotation_z', 'rotation_w',
              'translation_x', 'translation_y', 'translation_z')
SAMPLE = (('scale', 3), ('rotation', 4), ('translation', 3))
ATTRIBUTE_KINDS = {0: 'scalar', 3: 'bone_contact'}
SOURCE_VERSION = 1


class Number(float):
    """A binary32 value that serializes as its shortest round-trip decimal."""

    def __new__(cls, word):
        value = np.uint32(word).view(np.float32)
        if not np.isfinite(value):
            raise ValueError(f'non-finite motion value {word:#010x}')
        self = super().__new__(cls, float(value))
        self.word = int(word)
        return self

    def __repr__(self):
        if self.word == 0x80000000:
            return '-0.0'
        value = np.uint32(self.word).view(np.float32)
        return min(np.format_float_positional(value, unique=True, trim='-'),
                   np.format_float_scientific(value, unique=True, trim='-'), key=len)


def words(values):
    """binary32 words of JSON numbers; ints and doubles round to the nearest binary32."""
    values = list(values)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError('motion values must be finite numbers')
    return [int(w) for w in np.array(values, dtype=np.float64).astype(np.float32).view(np.uint32)]


def word(value):
    return words([value])[0]


def encode_name(text):
    """EncodeAnimationName: six-character base-38 chunks of the first 30 bytes, wrapping u32 arithmetic."""
    raw, result, at = text.encode(), [0] * 5, 0
    while at < 30 and at < len(raw) and raw[at]:
        weight, chunk = 79235168, at // 6
        for _ in range(6):
            if at >= len(raw) or not raw[at]:
                break
            byte = raw[at] - 256 if raw[at] >= 128 else raw[at]
            digit = byte - 86 if byte >= 97 else byte - 58 if byte > 90 else byte - 54 if byte > 57 else byte - 47
            result[chunk] = (result[chunk] + digit * weight) & 0xFFFFFFFF
            weight //= 38
            at += 1
    return result


class Reader:
    def __init__(self, data, magic):
        if data[:8] != magic:
            raise ValueError(f'expected {magic.decode()}')
        self.data, self.at = data, 8

    def word(self):
        value = struct.unpack_from('<I', self.data, self.at)[0]
        self.at += 4
        return value

    def int(self):
        return struct.unpack('<i', struct.pack('<I', self.word()))[0]

    def wide(self):
        low = self.word()
        return low | (self.word() << 32)

    def string(self):
        size = self.word()
        text = self.data[self.at:self.at + size].decode()
        self.at += size
        return text

    def words(self, count=None):
        return [self.word() for _ in range(self.word() if count is None else count)]

    def strings(self):
        return [self.string() for _ in range(self.word())]

    def numbers(self, count=None):
        return [Number(w) for w in self.words(count)]

    def end(self):
        if self.at != len(self.data):
            raise ValueError('trailing binary bytes')


class Writer:
    def __init__(self, magic):
        self.data = bytearray(magic)

    def word(self, value):
        self.data += struct.pack('<I', value & 0xFFFFFFFF)

    def wide(self, value):
        self.data += struct.pack('<Q', value)

    def string(self, text):
        raw = text.encode()
        self.word(len(raw))
        self.data += raw

    def words(self, values, counted=True):
        if counted:
            self.word(len(values))
        for value in values:
            self.word(value)

    def strings(self, values):
        self.word(len(values))
        for value in values:
            self.string(value)

    def numbers(self, values, counted=True):
        self.words(words(values), counted)


def sample(values):
    """Ten sample components as named scale/rotation/translation vectors."""
    out, at = {}, 0
    for key, size in SAMPLE:
        out[key] = values[at:at + size]
        at += size
    return out


def sample_numbers(value):
    if set(value) != {key for key, _ in SAMPLE} or any(len(value[k]) != n for k, n in SAMPLE):
        raise ValueError('a sample has scale[3], rotation[4] and translation[3]')
    return [v for key, _ in SAMPLE for v in value[key]]


# ------------------------------------------------------------------ rig

def rig_text(data):
    r = Reader(data, RIG)
    count, trajectory = r.word(), r.word()
    bones = []
    for _ in range(count):
        bones.append(dict(name=r.string(), parent=r.int(), mirror=r.int()))
    names = [b['name'] for b in bones]
    poses = []
    for _ in range(r.word()):
        bank, name, record = r.word(), r.string(), r.wide()
        if r.word() != count:
            raise ValueError('reference pose sample count differs from the rig')
        poses.append(dict(bank=bank, name=name, record=record,
                          bones={names[b]: sample(r.numbers(10)) for b in range(count)}))
    r.end()
    named = lambda i: None if i < 0 else names[i]
    return dict(version=SOURCE_VERSION, trajectory=bool(trajectory),
                bones=[dict(name=b['name'], parent=named(b['parent']), mirror=named(b['mirror'])) for b in bones],
                reference_poses=poses)


def rig_binary(value):
    if value.get('version') != SOURCE_VERSION:
        raise ValueError('unsupported motion rig version')
    names = [b['name'] for b in value['bones']]
    index = {name: i for i, name in enumerate(names)}
    if len(index) != len(names):
        raise ValueError('duplicate rig bone')
    w = Writer(RIG)
    w.word(len(names))
    w.word(int(value['trajectory']))
    for bone in value['bones']:
        w.string(bone['name'])
        for key in ('parent', 'mirror'):
            w.word(-1 if bone[key] is None else index[bone[key]])
    w.word(len(value['reference_poses']))
    for pose in value['reference_poses']:
        w.word(pose['bank'])
        w.string(pose['name'])
        w.wide(pose['record'])
        if list(pose['bones']) != names:
            raise ValueError(f'reference pose {pose["name"]} must list every rig bone in rig order')
        w.word(len(names))
        for name in names:
            w.numbers(sample_numbers(pose['bones'][name]), counted=False)
    return bytes(w.data)


# ------------------------------------------------------------------ clips

def clip_text(data, names):
    r = Reader(data, CLIP)
    name, bank, record, fps = r.string(), r.word(), r.wide(), Number(r.word())
    loop_t, loop_r = r.numbers(3), r.numbers(4)
    channel = r.word()
    weights = r.numbers()
    frames, count = r.word(), r.word()
    if count != len(names) or count != len(weights):
        raise ValueError(f'clip {name} bone count differs from the rig')
    bones = {}
    for b in range(count):
        tracks = {'weight': weights[b]}
        for component in COMPONENTS:
            track = r.numbers()
            if len(track) not in (1, frames):
                raise ValueError(f'clip {name} track length')
            tracks[component] = track[0] if len(track) == 1 else track
        bones[names[b]] = tracks
    r.end()
    return dict(version=SOURCE_VERSION, name=name, bank=bank, record=record, frame_rate=fps, frames=frames,
                channel_animation=bool(channel), loop=dict(translation=loop_t, rotation=loop_r), bones=bones)


def clip_binary(value, names):
    if value.get('version') != SOURCE_VERSION:
        raise ValueError('unsupported motion clip version')
    if list(value['bones']) != names:
        raise ValueError(f'clip {value["name"]} must list every rig bone in rig order')
    w = Writer(CLIP)
    w.string(value['name'])
    w.word(value['bank'])
    w.wide(value['record'])
    w.word(word(value['frame_rate']))
    w.numbers(value['loop']['translation'], counted=False)
    w.numbers(value['loop']['rotation'], counted=False)
    w.word(int(value['channel_animation']))
    w.numbers([value['bones'][n]['weight'] for n in names])
    frames = value['frames']
    w.word(frames)
    w.word(len(names))
    for name in names:
        for component in COMPONENTS:
            track = value['bones'][name][component]
            track = track if isinstance(track, list) else [track]
            if len(track) not in (1, frames):
                raise ValueError(f'clip {value["name"]} {name}.{component}: one value or one per frame')
            w.numbers(track)
    return bytes(w.data)


# ------------------------------------------------------------------ metadata

def metadata_text(data, names):
    r = Reader(data, META)
    encoded = {tuple(encode_name(n)): n for n in reversed(names)}  # the first rig bone wins, as in the importer
    out = dict(version=SOURCE_VERSION, source_bank=r.string(), source_sha256=r.string(), source_bytes=r.wide())
    identity = lambda: dict(name=r.string(), source_offset=r.wide())
    clips = []
    for _ in range(r.word()):
        clip = identity()
        clip.update(frame_rate=Number(r.word()), frames=Number(r.word()), base_speed=Number(r.word()), flags=r.word())
        attributes = []
        for _ in range(r.word()):
            a = dict(name=r.string())
            kind = r.word()
            a.update(kind=ATTRIBUTE_KINDS.get(kind, kind), begin=Number(r.word()), end=Number(r.word()), source_offset=r.wide())
            payload = r.words()
            if kind == 0 and len(payload) == 4 and not any(payload[1:]):
                a['value'] = Number(payload[0])
            elif kind == 3 and len(payload) == 8 and not any(payload[6:]) and tuple(payload[:5]) in encoded:
                a.update(target_bone=encoded[tuple(payload[:5])], value=Number(payload[5]))
            else:
                raise ValueError(f'unsupported attribute {a["name"]} kind {kind} payload {len(payload)}')
            attributes.append(a)
        clip['attributes'] = attributes
        clips.append(clip)
    out['clips'] = clips
    out['phase_blends'] = []
    for _ in range(r.word()):
        tree = identity()
        tree.update(parameter=r.string(), children=r.strings())
        out['phase_blends'].append(tree)
    out['blend_spaces'] = []
    for _ in range(r.word()):
        tree = identity()
        tree.update(parameters=r.strings(), children=r.strings(), simplexes=[])
        for _ in range(r.word()):
            tree['simplexes'].append(dict(children=r.words(), vertices=[r.numbers() for _ in range(r.word())],
                                          normals=[r.numbers() for _ in range(r.word())], scales=r.numbers()))
        out['blend_spaces'].append(tree)
    out['selectors'] = []
    for _ in range(r.word()):
        tree = identity()
        tree.update(parameter=r.string(), default=r.string(), children=r.strings(), values=r.strings())
        out['selectors'].append(tree)
    out['selection_spaces'] = []
    for _ in range(r.word()):
        tree = identity()
        tree['parameters'] = [dict(name=r.string(), mode=r.word(), weight=Number(r.word()), minimum=Number(r.word()),
                                   maximum=Number(r.word())) for _ in range(r.word())]
        tree['candidates'] = [dict(child=r.string(), values=r.numbers()) for _ in range(r.word())]
        out['selection_spaces'].append(tree)
    out['unsupported_trees'] = []
    for _ in range(r.word()):
        tree = identity()
        tree['kind'] = r.word()
        out['unsupported_trees'].append(tree)
    r.end()
    return out


def metadata_binary(value, names):
    if value.get('version') != SOURCE_VERSION:
        raise ValueError('unsupported motion metadata version')
    kinds = {v: k for k, v in ATTRIBUTE_KINDS.items()}
    w = Writer(META)
    w.string(value['source_bank'])
    w.string(value['source_sha256'])
    w.wide(value['source_bytes'])

    def identity(tree):
        w.string(tree['name'])
        w.wide(tree['source_offset'])
    w.word(len(value['clips']))
    for clip in value['clips']:
        identity(clip)
        for key in ('frame_rate', 'frames', 'base_speed'):
            w.word(word(clip[key]))
        w.word(clip['flags'])
        w.word(len(clip['attributes']))
        for a in clip['attributes']:
            kind = kinds[a['kind']]
            w.string(a['name'])
            w.word(kind)
            w.word(word(a['begin']))
            w.word(word(a['end']))
            w.wide(a['source_offset'])
            if kind == 3:
                if a['target_bone'] not in names:
                    raise ValueError(f'attribute {a["name"]} targets an unknown bone')
                w.words(encode_name(a['target_bone']) + [word(a['value']), 0, 0])
            else:
                w.words([word(a['value']), 0, 0, 0])
    w.word(len(value['phase_blends']))
    for tree in value['phase_blends']:
        identity(tree)
        w.string(tree['parameter'])
        w.strings(tree['children'])
    w.word(len(value['blend_spaces']))
    for tree in value['blend_spaces']:
        identity(tree)
        w.strings(tree['parameters'])
        w.strings(tree['children'])
        w.word(len(tree['simplexes']))
        for simplex in tree['simplexes']:
            w.words(simplex['children'])
            for key in ('vertices', 'normals'):
                w.word(len(simplex[key]))
                for row in simplex[key]:
                    w.numbers(row)
            w.numbers(simplex['scales'])
    w.word(len(value['selectors']))
    for tree in value['selectors']:
        identity(tree)
        w.string(tree['parameter'])
        w.string(tree['default'])
        w.strings(tree['children'])
        w.strings(tree['values'])
    w.word(len(value['selection_spaces']))
    for tree in value['selection_spaces']:
        identity(tree)
        w.word(len(tree['parameters']))
        for p in tree['parameters']:
            w.string(p['name'])
            w.word(p['mode'])
            w.numbers([p['weight'], p['minimum'], p['maximum']], counted=False)
        w.word(len(tree['candidates']))
        for c in tree['candidates']:
            w.string(c['child'])
            w.numbers(c['values'])
    w.word(len(value['unsupported_trees']))
    for tree in value['unsupported_trees']:
        identity(tree)
        w.word(tree['kind'])
    return bytes(w.data)


# ------------------------------------------------------------------ files

def dumps(value, indent=0):
    """JSON with one line per scalar field and number lists kept on one line."""
    pad, inner = ' ' * indent, ' ' * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return '{}'
        rows = [f'{inner}{json.dumps(k)}: {dumps(v, indent + 1)}' for k, v in value.items()]
        return '{\n' + ',\n'.join(rows) + f'\n{pad}}}'
    if isinstance(value, list):
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            return '[' + ', '.join(repr(v) if isinstance(v, Number) else json.dumps(v) for v in value) + ']'
        if all(isinstance(v, str) for v in value):
            return json.dumps(value)
        if not value:
            return '[]'
        return '[\n' + ',\n'.join(inner + dumps(v, indent + 1) for v in value) + f'\n{pad}]'
    if isinstance(value, Number):
        return repr(value)
    return json.dumps(value)


def export(package, source):
    """Binary bundle -> readable source. Returns the written relative paths."""
    package, source = Path(package), Path(source)
    rig = rig_text((package / 'animation/rig.skate').read_bytes())
    names = [b['name'] for b in rig['bones']]
    written = {'rig.json': rig}
    for bank in (0, 1):
        written[f'metadata/bank-{bank}.json'] = metadata_text((package / f'metadata/bank-{bank}.skate').read_bytes(), names)
    for path in sorted((package / 'animation/clips').rglob('*.skate')):
        clip = clip_text(path.read_bytes(), names)
        written[f'clips/{clip["bank"]}/{clip["name"]}.json'] = clip
    for rel, value in written.items():
        target = source / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dumps(value) + '\n')
    return sorted(written)


def build(source):
    """Readable source -> {binary relative path: bytes}."""
    source = Path(source)
    rig = json.loads((source / 'rig.json').read_text())
    names = [b['name'] for b in rig['bones']]
    out = {'animation/rig.skate': rig_binary(rig)}
    for bank in (0, 1):
        out[f'metadata/bank-{bank}.skate'] = metadata_binary(
            json.loads((source / f'metadata/bank-{bank}.json').read_text()), names)
    for path in sorted((source / 'clips').glob('*/*.json')):
        clip = json.loads(path.read_text())
        if path.stem != clip['name'] or path.parent.name != str(clip['bank']):
            raise ValueError(f'{path.relative_to(source)} must be clips/<bank>/<name>.json')
        out[f'animation/clips/{clip["bank"]}/{clip["name"]}.skate'] = clip_binary(clip, names)
    return out


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
    for rel, data in files.items():
        target = args.package / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print(f'{len(files)} binary files')


if __name__ == '__main__':
    main()
