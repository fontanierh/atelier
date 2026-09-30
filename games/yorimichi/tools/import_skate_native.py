#!/usr/bin/env python3
"""Import original Skate controller data from an owned disc using SK8-ENGINE's converters.

--engine is a checkout of SK8-ENGINE/skate-3-rust-engine (its tools directory is required).
--game contains default.xex and data/. Output stays in ignored Content/Data and build/.
No game model, animation, audio, or executable is copied into Yorimichi.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
CLASSES = {'physics_steering', 'physics_push', 'physics_pumping', 'physics_manual',
           'physics_mode', 'physics_animation', 'physics_friction', 'physics_speed_conservation',
           'anim_motion', 'physics_surfaces', 'physics_jump', 'physics_trajectory', 'physics_grinds_air'}


def parameters(document):
    """Resolve inheritance and convert big-endian floats / point-graph layouts."""
    rows = {(r['class'], r['key']): r for r in document['collections']}
    def fields(key, seen):
        if key in seen:
            raise ValueError(f'Collection inheritance cycle: {key}')
        row = rows[key]
        result = fields((key[0], row['parent']), seen | {key}) if row['parent'] else {}
        result.update(row['fields'])
        return result
    result = {}
    for key in rows:
        if key[0] not in CLASSES:
            continue
        for name, field in fields(key, set()).items():
            raw = field['data']
            value = None
            if field['type'] == 'EA::Reflection::Float':
                value = struct.unpack('>f', bytes.fromhex(raw))[0]
            elif field['type'] in ('Sk8::PointGraphData4', 'Sk8::PointGraphData16', 'Sk8::PointGraphData8', 'Sk8::PointNegGraphData8'):
                words = struct.unpack('>' + 'f' * (len(raw) // 8), bytes.fromhex(raw))
                # Graph8 has either just eight X/eight Y, or four editor bounds first.
                if len(words) == 20:
                    words = words[4:]
                if len(words) in (8, 16, 32):
                    count = len(words) // 2
                    value = [list(words[:count]), list(words[count:])]
            if value is not None:
                values = [value] if isinstance(value, float) else value[0] + value[1]
                if not all(math.isfinite(v) for v in values):
                    raise ValueError(f'Nonfinite value in {key}/{name}')
                result['/'.join((*key, name))] = value
    return result


def patterns(text):
    result, current, tolerance = [], None, .4
    for line in text.splitlines():
        parts = line.split('//', 1)[0].split()
        if not parts:
            continue
        if parts[0] == 'global_tolerance_dist':
            tolerance = float(parts[1])
        elif parts[0] == 'pattern':
            current = {'name': parts[1], 'tolerance': tolerance, 'points': []}
            result.append(current)
        elif parts[0] == 'tolerance_dist' and current is not None:
            current['tolerance'] = float(parts[1])
        elif parts[0] == 'coord' and current is not None:
            current['points'].append([float(parts[1]), float(parts[2])])
    for p in result:
        if not 2 <= len(p['points']) <= 15 or p['tolerance'] < 0:
            raise ValueError(f'Invalid gesture {p["name"]}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--mode', choices=('easy', 'normal', 'hardcore'), default='normal')
    parser.add_argument('--output', type=Path, default=ROOT/'games/yorimichi/unreal/Content/Data/skate-native.json')
    args = parser.parse_args()
    if not (args.game/'default.xex').is_file():
        parser.error('--game must contain default.xex and data/')
    sys.path.insert(0, str(args.engine.resolve()))
    from tools.asset_pipeline.install import extract
    from tools.asset_pipeline.vlt import convert
    from tools.owned_game.refpack import decompress
    staging = ROOT/'build/yorimichi/skate-native'
    staging.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='import-', dir=staging))
    stems = ('skaterschema', 'skatercollections')
    extract(args.game/'data/big/db.big', work,
            lambda entry: Path(entry.path).name in {s + e for s in stems for e in ('.vlt', '.bin')})
    base = work/'data/db'
    for stem in stems:
        for ext in ('.vlt', '.bin'):
            path = base/(stem + ext)
            raw = path.read_bytes()
            if raw[:2] in (b'\x10\xfb', b'\x90\xfb'):
                path.write_bytes(decompress(raw))
    names = (args.engine/'tools/asset_pipeline/names.txt').read_text().splitlines()
    document = convert(base/stems[0], base/stems[1], names)
    extract(args.game/'data/big/miscload.big', work,
            lambda entry: entry.path.lower() == 'data/joystick/skater.pat')
    pat = work/'data/joystick/skater.pat'
    output = {'version': 1, 'mode': args.mode, 'parameters': parameters(document),
              'patterns': patterns(pat.read_text()),
              'source_sha256': hashlib.sha256((base/'skatercollections.vlt').read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print(f'Imported {len(output["parameters"])} parameters and {len(output["patterns"])} gestures ({args.mode}).')


if __name__ == '__main__':
    main()
