#!/usr/bin/env python3
"""Pack frozen-reader camera exports as ATCAM001, preserving every float bit.

Original collections, shot references and shake files are conversion inputs only.
The shipping runtime loads the project package produced here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


class Writer:
    def __init__(self):
        self.data = bytearray(b'ATCAM001')

    def word(self, value):
        if not isinstance(value, int) or not 0 <= value <= 0xffffffff:
            raise ValueError('Camera export contains an invalid raw word')
        self.data.extend(struct.pack('<I', value))

    def string(self, value):
        raw = value.encode('utf-8')
        self.word(len(raw))
        self.data.extend(raw)

    def words(self, values, count):
        if len(values) != count:
            raise ValueError(f'Camera export requires {count} words, found {len(values)}')
        for value in values:
            self.word(value)


def pack_camera(value):
    if value['version'] != 1:
        raise ValueError('Unsupported decoded camera version')
    writer = Writer()
    writer.string(value['source_identity'])
    shots = value['shots']
    names = [shot['name'] for shot in shots]
    if names != sorted(set(names)):
        raise ValueError('Camera shots must retain the original sorted unique names')
    writer.word(len(shots))
    for definition in shots:
        writer.string(definition['name'])
        writer.word(definition['shot_type'])
        shot = definition['shot']
        writer.word(shot['distance'])
        writer.word(shot['lens_length'])
        writer.words(shot['smoothing'], 4)
        writer.words(shot['reference_weights'], 10)
        for key in ('board_offset', 'position_heading', 'position_elevation'):
            writer.word(shot[key])
        writer.words(shot['framing'], 3)
        for key in ('follow_subject_in_air', 'mirror_for_stance', 'snap_to_reference_point',
                    'use_previous_shot', 'use_drop_predictor', 'use_free_camera_stick',
                    'avoidance_override'):
            flag = shot[key]
            if not 0 <= flag <= 255:
                raise ValueError('Invalid decoded camera byte')
            writer.word(flag)
        for key in ('blur', 'transition_blur', 'subject_opacity', 'collision_hint',
                    'anchor', 'compass_north', 'world_heading'):
            writer.word(shot[key])
        writer.words(shot['arm_orientation'], 4)
        writer.words(shot['camera_orientation'], 4)
        writer.word(definition['transition_time'])
        writer.word(definition['transition_units'])
        if len(definition['children']) != 3:
            raise ValueError('Camera definition requires three child slots')
        for child in definition['children']:
            writer.word(int(child is not None))
            if child is not None:
                if child not in names:
                    raise ValueError(f'Missing decoded camera child {child}')
                writer.string(child)
        writer.words(definition['blend_points'], 3)
        for key in ('blend_value', 'blend_type', 'blend_smoothing'):
            writer.word(definition[key])
    if len(value['shakes']) != 2:
        raise ValueError('Camera package requires both original shake sequences')
    for sample in value['shakes']:
        rotations, translations = sample['rotations'], sample['translations']
        if not rotations or len(rotations) != len(translations):
            raise ValueError('Invalid decoded camera shake sequence')
        writer.word(len(rotations))
        for rotation, translation in zip(rotations, translations):
            writer.words(rotation, 4)
            writer.words(translation, 4)
    return bytes(writer.data)


def convert_camera(source, destination):
    source, destination = Path(source), Path(destination)
    value = json.loads(source.read_text())
    raw = pack_camera(value)
    expected = source.with_suffix('.raw')
    if expected.exists() and expected.read_bytes() != raw:
        raise AssertionError('Camera package differs from independent original-reader export')
    destination.mkdir(parents=True, exist_ok=True)
    package = destination / 'camera.skate'
    package.write_bytes(raw)
    report = dict(format='ATCAM001', source_identity=value['source_identity'],
                  decoded_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  file=package.name, shots=len(value['shots']),
                  shake_samples=[len(sample['rotations']) for sample in value['shakes']],
                  bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (destination / 'camera-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decoded', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(convert_camera(args.decoded, args.output), indent=2))


if __name__ == '__main__':
    main()
