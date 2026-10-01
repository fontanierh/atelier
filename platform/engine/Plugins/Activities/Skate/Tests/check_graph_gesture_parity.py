#!/usr/bin/env python3
"""Exact original gesture catalog, trick priority and retained lifecycle parity.

Run compilation through atelier.safety. Original source modules stay unchanged;
the corpus reads their authored names only, and the Rust oracle computes outputs.
"""
import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import historical_oracle as historical
import random
import re
import struct
import subprocess
from reference_build import build_probe
from check_input_parity import Record, PLUGIN


def authored_rows():
    source = historical.source_text('crates/skate-host/src/input/gesture_mapping_data.rs')
    pattern = re.compile(r'\(\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*(\d+),?\s*\)')
    rows = [pattern.findall(chunk) for chunk in source.split('&[')[2:]]
    assert [len(group) for group in rows] == [30, 30, 30, 45, 45, 45, 45]
    return rows


def write_map(writer, values):
    writer.word(len(values))
    for name, bits in values:
        writer.raw(name)
        writer.word(bits)


def corpus():
    rng = random.Random(0x82BA07F0)
    rows = authored_rows()
    keys = sorted({row[0] for group in rows for row in group})
    groups = ('Square', 'Nose', 'Tail', '90Nose', '90Tail', 'N90Nose', 'N90Tail')
    parts, cases = [], []
    def add(operation, label, build):
        writer = Record()
        writer.word(operation)
        build(writer)
        cases.append(dict(command=len(cases), operation=operation, kind=label, input_bytes=len(writer.data)))
        parts.append(bytes(writer.data))
    for name in [variant for group in groups for variant in (group, group.lower(), group.upper(), group+'\0tail', ' '+group)] + ['', '90 Nose', 'é', 'Squaretail']:
        add(0, 'exact constructor and error spelling', lambda w, name=name: w.raw(name))
    for group in range(7):
        add(1, 'all 270 original authored mapping rows', lambda w, group=group: w.word(group))
    values = (0, 0x80000000, 0x3f800000, 0xbf800000, 0x7fc12345, 0xff800000)
    def selection(group, mirrored, action, label):
        def build(w):
            w.words((group, mirrored))
            write_map(w, action)
        add(2, label, build)
    for group, names in enumerate(rows):
        for row, modifier in itertools.product(names, range(8)):
            action = [(row[0], values[modifier % len(values)])]
            if modifier & 2:
                action.append(('DarkCatch', values[modifier % len(values)]))
            if modifier & 4:
                action.append(('DontMirrorTrick', 0))
            selection(group, modifier & 1, action, 'authored mappings, presence, mirrored/dark-catch/override flag')
        for first, second in itertools.combinations(names, 2):
            for mirrored in (False, True):
                selection(group, mirrored, [(first[0], 0), (second[0], 0x7fc12345)], '43-bucket priority and reverse insertion tie order')
    for group, key, alias in itertools.product(range(7), keys, range(4)):
        name = (key, key.upper(), key+'\0tail', key.lower())[alias]
        selection(group, alias % 2, [(name, values[alias])], 'catalog membership and canonical key aliases')
    for case in range(4096):
        action = [(rng.choice(keys+['DarkCatch', 'DontMirrorTrick', 'Underflip', 'unknown', 'a'*36+'tail']), rng.choice(values)) for _ in range(rng.randrange(20))]
        if case % 7 == 0:
            action += [('Kickflip', 0), ('KICKFLIP', 0x7fc12345), ('Kickflip\0tail', 0x80000000)]
        selection(case % 7, case % 2, action, 'generated multi-intent collision and duplicate maps')
    output_names = sorted({name for group in rows for row in group for name in row[:3]})
    output_names += ['KickflipHold', 'HeelflipHold', 'N_KickflipHold', 'N_HeelflipHold']
    output_names += ['U_'+name for name in output_names]
    overrides = ['', 'Shared', 'shared', 'shared\0tail', 'a'*36, 'a'*36+'tail', 'équipement']
    output_names += overrides+['U_'+name for name in overrides]+['DarkCatch', 'unrelated']
    for case in range(128):
        def build(w, case=case):
            write_map(w, [('DarkCatch', 0x7fc12345), ('unrelated', 0x80000000), ('KickflipHold', 0x3f800000)])
            w.word(len(output_names))
            for name in output_names:
                w.raw(name)
            w.word(128)
            for tick in range(128):
                phase = (0, 1, 1, 1, 2, 1, 3, 0)[tick % 8]
                w.word(phase)
                mutations = []
                if tick % 9 == 0:
                    mutations.append((True, rng.choice(output_names), rng.choice(values)))
                if tick % 13 == 0:
                    mutations.append((False, rng.choice(output_names), 0))
                w.word(len(mutations))
                for insert, name, bits in mutations:
                    w.word(insert)
                    w.raw(name)
                    if insert:
                        w.word(bits)
                if phase == 0:
                    w.words(((case+tick) % 7, (case+tick) % 2))
                    override = (None, '', 'Shared', 'Kickflip', 'N_Heelflip', 'a'*36+'tail', 'équipement')[(case+tick) % 7]
                    w.word(override is not None)
                    if override is not None:
                        w.raw(override)
                    action = [] if tick % 19 == 0 else [(rng.choice(keys), rng.choice(values)) for _ in range(1+case % 5)]
                    for index, name in enumerate(('Underflip', 'DontMirrorTrick', 'DarkCatch')):
                        if (case+tick) & (1 << index):
                            action.append((name, 0))
                    write_map(w, action)
        add(3, 'launch/first update/hold/exit/reallocation with shared retained map', build)
    offset = 4
    for case in cases:
        case['input_offset'] = offset
        offset += case['input_bytes']
    return struct.pack('<I', len(parts))+b''.join(parts), cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    reference = build_probe(output, 'graph-gesture-reference', PLUGIN/'Tests/Reference/graph_gesture_probe.rs', args.target_dir)
    native = PLUGIN/'Source/AtelierSkate/Private/Native'
    candidate = output/'graph-gesture-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror', '-I', str(native),
                    *(str(native/f'{name}.cpp') for name in ('AnimationName', 'Intents', 'GraphGestureOperations')),
                    str(PLUGIN/'Tests/Native/graph_gesture_probe.cpp'), '-o', str(candidate)], check=True)
    inputs, cases = corpus()
    (output/'input.bin').write_bytes(inputs)
    (output/'cases.json').write_text(json.dumps(cases, indent=2)+'\n')
    expected = subprocess.check_output([str(reference)], input=inputs)
    actual = subprocess.check_output([str(candidate)], input=inputs)
    if expected != actual:
        (output/'reference.bin').write_bytes(expected)
        (output/'candidate.bin').write_bytes(actual)
        low, high = 1, len(cases)
        while low < high:
            count = (low+high)//2
            end = cases[count-1]['input_offset']+cases[count-1]['input_bytes']
            prefix = struct.pack('<I', count)+inputs[4:end]
            if subprocess.check_output([str(reference)], input=prefix) == subprocess.check_output([str(candidate)], input=prefix):
                low = count+1
            else:
                high = count
        first = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
        report = dict(passed=False, case=cases[low-1], first_byte=first, reference_length=len(expected), candidate_length=len(actual),
                      reference_hex=expected[max(0, first-16):first+32].hex(), candidate_hex=actual[max(0, first-16):first+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    report = dict(passed=True, commands=len(cases), operations=dict(Counter(case['operation'] for case in cases)),
                  mapping_rows=270, lifecycle_frames=128*128, input_bytes=len(inputs), output_bytes=len(actual),
                  output_sha256=hashlib.sha256(actual).hexdigest(), comparison='exact catalog/row data, selected names and every retained map value; no tolerance',
                  limitations='Gesture operation host registration is a separate integration step. Full graph/session/controller sampling still requires integrated validation.',
                  reference_provenance='graph-gesture-reference-provenance.json')
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    historical.run_cli(main)
