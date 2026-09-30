#!/usr/bin/env python3
"""One-time conversion into the project's native skating data formats.

Development migration tool. The C++ runtime never reads the original formats.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

GESTURE_SETS = (
    ('main', 1, 'skater.pat'),
    ('rotated90', 1, 'skater90.pat'),
    ('rotated_minus90', 1, 'skaterN90.pat'),
    ('air', 1, 'skater_air.pat'),
    ('fingerflip', 1, 'skater_fingerflip.pat'),
    ('left', 0, 'skaterls.pat'),
    ('step', 0, 'skaterstep.pat'),
)

GRAPH_FILES = (
    ('action', 'data/state/ActionGraph_OnBoard.stategraph'),
    ('motion', 'data/state/MotionGraph_OnBoard.stategraph'),
    ('camera', 'data/script/camera/Default_cameragraph.stategraph'),
)


def name_hash(text):
    if not text:
        return 0
    mask = (1 << 64)-1
    def mix(a, b, c):
        for x, y, z in ((43,9,8), (38,23,5), (35,49,11), (12,18,22)):
            a = ((a-b-c) & mask) ^ (c >> x)
            b = ((b-c-a) & mask) ^ ((a << y) & mask)
            c = ((c-a-b) & mask) ^ (b >> z)
        return a, b, c
    a = b = 0xabcdef0011223344
    c = 0x9e3779b97f4a7c13
    raw = text.encode('utf-8')
    at = 0
    while len(raw)-at >= 24:
        x, y, z = struct.unpack_from('<QQQ',raw,at)
        a, b, c = mix((a+x)&mask, (b+y)&mask, (c+z)&mask)
        at += 24
    c = (c+len(raw)) & mask
    for i, byte in enumerate(raw[at:]):
        if i < 8:
            a = (a+(byte << (i*8))) & mask
        elif i < 16:
            b = (b+(byte << ((i-8)*8))) & mask
        else:
            c = (c+(byte << ((i-15)*8))) & mask
    return mix(a,b,c)[2]


def name_id(text):
    hex_value = text[5:] if text.startswith('Hash_') else text[2:] if text.startswith('0x') else None
    if hex_value is not None:
        digits = hex_value[1:] if hex_value.startswith('+') else hex_value
        if digits and all(c in '0123456789abcdefABCDEF' for c in digits):
            value = int(digits,16)
            if value < 1 << 64:
                return value
    return name_hash(text)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def read_patterns(path):
    patterns = []
    tolerance = None
    for line, source in enumerate(path.read_text().splitlines(), 1):
        words = source.split('//', 1)[0].split()
        if not words:
            continue
        def number(index):
            result = f32(float(words[index]))
            if not math.isfinite(result):
                raise ValueError(f'{path.name}:{line}: nonfinite value')
            return result
        key = words[0]
        if key == 'global_tolerance_dist' and len(words) == 2:
            value = number(1)
            tolerance = f32(value * value)
        elif key in ('global_tolerance_time', 'global_tolerance_speed', 'global_anticipation_delay', 'tolerance_time') and len(words) == 2:
            number(1)  # The reference loader validates but does not store these fields.
        elif key == 'pattern' and len(words) == 2 and tolerance is not None:
            patterns.append(dict(name=words[1], tolerance_squared=tolerance, points=[]))
        elif key == 'tolerance_dist' and len(words) == 2 and patterns:
            value = number(1)
            patterns[-1]['tolerance_squared'] = f32(value * value)
        elif key == 'coord' and len(words) == 3 and patterns:
            patterns[-1]['points'].append([number(1), number(2)])
        else:
            raise ValueError(f'{path.name}:{line}: unsupported directive: {source}')
    for pattern in patterns:
        if not 2 <= len(pattern['points']) <= 15:
            raise ValueError(f'{path.name}: invalid point count for {pattern["name"]}')
    return patterns


def gesture_sets(source):
    return [dict(name=name, stick=stick, patterns=read_patterns(source / filename))
            for name, stick, filename in GESTURE_SETS]


def encode_gestures(sets):
    data = bytearray(b'ATGEST01')
    def word(value):
        data.extend(struct.pack('<I', value))
    def string(value):
        encoded = value.encode('utf-8')
        word(len(encoded))
        data.extend(encoded)
    word(len(sets))
    for group in sets:
        string(group['name'])
        word(group['stick'])
        word(len(group['patterns']))
        for pattern in group['patterns']:
            string(pattern['name'])
            data.extend(struct.pack('<f', pattern['tolerance_squared']))
            word(len(pattern['points']))
            for point in pattern['points']:
                data.extend(struct.pack('<ff', *point))
    return bytes(data)


def encode_settings(source):
    """Intern names and materialize numeric words once, keeping every record and field."""
    records = json.loads(source.read_text())['collections']
    strings = set()
    identities = set()
    for record in records:
        identity = (name_id(record['class']),name_id(record['key']))
        if identity in identities:
            raise ValueError('Duplicate normalized settings record')
        identities.add(identity)
        strings.update((record['class'],record['key'],record['parent']))
        strings.update(record['fields'])
        strings.update(field['type'] for field in record['fields'].values())
    strings = sorted(strings)
    ids = {value:index for index,value in enumerate(strings)}
    data = bytearray(b'ATATTR01')
    def word(value):
        data.extend(struct.pack('<I',value))
    word(len(strings)); word(len(records))
    for text in strings:
        raw = text.encode('utf-8'); word(len(raw)); data.extend(raw)
    for record in records:
        for key in ('class','key','parent'):
            word(ids[record[key]])
        word(len(record['fields']))
        for name, field in sorted(record['fields'].items()):
            word(ids[name]); word(ids[field['type']])
            text = field['type'] == 'EA::Reflection::Text'
            word(int(text))
            raw = field['data'].encode('utf-8') if text else bytes.fromhex(field['data'])
            word(len(raw))
            if text:
                data.extend(raw)
            else:
                for at in range(0,len(raw),4):
                    word(int.from_bytes(raw[at:at+4],'big'))
    return bytes(data)


def read_graph(source):
    """Materialize a preorder arena; keep duplicate attributes and all typed bits."""
    raw = source.read_bytes()
    at = 0
    def take(count):
        nonlocal at
        if count > len(raw)-at:
            raise ValueError(f'{source.name}: truncated graph at {at}')
        value = raw[at:at+count]; at += count
        return value
    def word():
        return struct.unpack('>I', take(4))[0]
    def string():
        end = raw.find(b'\0', at)
        if end < 0:
            raise ValueError(f'{source.name}: unterminated graph string')
        return take(end-at+1)[:-1].decode('utf-8')
    def element():
        offset = at
        tag = string()
        count = word()
        if count > (len(raw)-at)//7:
            raise ValueError('Graph attribute count exceeds remaining data')
        attributes = [dict(name=string(), text=string(), float_bits=word(), boolean_byte=take(1)[0]) for _ in range(count)]
        children = word()
        if children > (len(raw)-at)//9:
            raise ValueError('Graph child count exceeds remaining data')
        return dict(source_offset=offset, tag=tag, attributes=attributes, children=[]), children
    root, children = element()
    result = [root]; pending = [[0, children]]
    while pending:
        parent, remaining = pending[-1]
        if remaining == 0:
            pending.pop(); continue
        pending[-1][1] -= 1
        child, children = element()
        index = len(result)
        result[parent]['children'].append(index); result.append(child)
        pending.append([index, children])
    if at != len(raw):
        raise ValueError('Trailing graph bytes')
    return result


def encode_graph(elements):
    strings = sorted({e['tag'] for e in elements} |
                     {a[key] for e in elements for a in e['attributes'] for key in ('name', 'text')})
    indices = {name:index for index,name in enumerate(strings)}
    data = bytearray(b'ATGRPH01')
    def word(value):
        data.extend(struct.pack('<I',value))
    word(len(strings)); word(len(elements))
    for value in strings:
        raw=value.encode('utf-8'); word(len(raw)); data.extend(raw)
    for element in elements:
        word(element['source_offset']); word(indices[element['tag']])
        word(len(element['attributes'])); word(len(element['children']))
        for attribute in element['attributes']:
            word(indices[attribute['name']]); word(indices[attribute['text']])
            word(attribute['float_bits']); word(attribute['boolean_byte'])
        for child in element['children']:
            word(child)
    return bytes(data)


def encode_clip_samples(raw):
    """Lossless per-component tracks; constant tracks store one original bit word."""
    if raw[:8]!=b'ATCLRAW1': raise ValueError('Invalid decoded clip export')
    at=8
    def word():
        nonlocal at
        value=struct.unpack_from('<I',raw,at)[0];at+=4;return value
    length=word();at+=length
    at+=4+8+4+7*4+4  # bank, record, fps, loop transforms, channel flag
    weights=word();at+=weights*4
    frames,bones=word(),word()
    if frames==0 or bones==0 or bones!=weights or len(raw)-at!=frames*bones*40:
        raise ValueError('Decoded clip frame layout mismatch')
    words=struct.unpack_from(f'<{frames*bones*10}I',raw,at)
    result=bytearray(b'ATCLIP01'+raw[8:at]);constant=0
    for lane in range(bones*10):
        track=words[lane::bones*10]
        if all(value==track[0] for value in track):
            track=track[:1];constant+=1
        result.extend(struct.pack('<I',len(track)))
        result.extend(struct.pack(f'<{len(track)}I',*track))
    return bytes(result),dict(frames=frames,bones=bones,constant_tracks=constant,tracks=bones*10)


def convert_animation_samples(source,output):
    output.mkdir(parents=True,exist_ok=True)
    rig=(source/'rig.raw').read_bytes()
    if rig[:8]!=b'ATSKEL01': raise ValueError('Invalid decoded rig export')
    (output/'rig.skate').write_bytes(rig)
    entries=[]
    for name in (source/'clips.txt').read_text().splitlines():
        parts=name.split('/')
        if len(parts)!=2 or parts[0] not in ('0','1') or not parts[1] or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in parts[1]):
            raise ValueError('Invalid exported clip name')
        raw=(source/'clips'/f'{name}.raw').read_bytes()
        native,counts=encode_clip_samples(raw)
        path=output/'clips'/f'{name}.skate';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(native)
        entries.append(dict(name=name,**counts,source_bytes=len(raw),native_bytes=len(native),
                            decoded_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(native).hexdigest()))
    manifest=dict(format='ATCLIP01',rig_sha256=hashlib.sha256(rig).hexdigest(),clips=entries)
    (output/'samples-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest



def encode_physics_skeletons(source):
    """Keep every physical bone word and record identity; no original JSON at runtime."""
    value=json.loads(source.read_text())
    if value['version']!=1:raise ValueError('Unknown physics skeleton version')
    data=bytearray(b'ATPHYS01')
    def word(v):data.extend(struct.pack('<I',v))
    def string(v):
        raw=v.encode('utf-8');word(len(raw));data.extend(raw)
    string(value['source_sha256']);word(len(value['skeletons']))
    for skeleton in value['skeletons']:
        string(skeleton['name']);data.extend(struct.pack('<Q',skeleton['source_offset']));word(len(skeleton['bones']))
        for bone in skeleton['bones']:
            if len(bone['words'])!=28:raise ValueError('Invalid physics bone word count')
            string(bone['name']);data.extend(struct.pack('<Q',bone['source_offset']))
            for v in bone['words']:word(v)
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='reference assets root containing private/')
    parser.add_argument('--output', type=Path, required=True, help='generated migration output directory')
    parser.add_argument('--animation-samples', type=Path, help='decoded sample export from the reference reader')
    args = parser.parse_args()
    source = args.source / 'private/stock/data/joystick'
    sets = gesture_sets(source)
    encoded = encode_gestures(sets)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'gestures.skate').write_bytes(encoded)
    (args.output / 'settings.skate').write_bytes(encode_settings(args.source/'private/stock/skater-collections.json'))
    (args.output / 'physics-skeletons.skate').write_bytes(encode_physics_skeletons(args.source/'private/stock/physics-skeletons.json'))
    for name, relative in GRAPH_FILES:
        (args.output / f'{name}.graph').write_bytes(encode_graph(read_graph(args.source/'private/stock'/relative)))
    if args.animation_samples:
        convert_animation_samples(args.animation_samples,args.output/'animation')
    report = dict(format='ATGEST01', patterns=sum(len(group['patterns']) for group in sets),
                  sha256=hashlib.sha256(encoded).hexdigest(),
                  source_sha256={name: hashlib.sha256((source/name).read_bytes()).hexdigest()
                                 for _, _, name in GESTURE_SETS})
    (args.output / 'gestures-conversion.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
