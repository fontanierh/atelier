#!/usr/bin/env python3
"""Original full MotionHost score, tweak, height, RNG and registry phase parity.

Parent exclusively runs this under atelier.safety. Generated authored trees make
parameter effects visible through real cached animation output, not test sinks.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
from check_gesture_parity import converter
from check_graph_parity import attribute, element, original_graph
from check_input_parity import Record, fbits, from_bits
from check_animation_trees_parity import converter as metadata_converter, name as attribute_name
from check_motion_animation_parity import validate_fixture_attributes
from motion_reference_build import build_probes


def fixture():
    configs = []
    groups = {}
    def add(name, values=()):
        groups.setdefault(name, []).append(len(configs))
        configs.append(element('behaviour', name, values))
        return len(configs)-1
    add('ScoringTrick', [attribute('trick', 'Kickflip')])
    add(' ScoringTrick ', [attribute('trick', 'LongTrickNameWithMoreThanThirtySixBytes_alias')])
    for name, base_field in (('ScoringHandPlants', 'handplantname'), ('ScoringGrabs', 'grabName')):
        for mask in range(16):
            values = [attribute(base_field, 'base'), attribute('intentX', 'X'), attribute('intentY', 'Y'), attribute('invertY', boolean=1)]
            values += [attribute(direction, direction) for i, direction in enumerate(('up', 'left', 'down', 'right')) if mask & (1 << i)]
            add(name, values)
    for invert in (0, 1):
        add('ScoringGrabs', [attribute('grabName', 'polar'), attribute('angle', 'Angle'), attribute('magnitude', 'Magnitude'), attribute('invertY', boolean=invert),
            *[attribute(d, d) for d in ('up', 'left', 'down', 'right')]])
    augmentations = ('FSPowerslide', 'BSPowerslide', 'FSRevert', 'BSRevert', 'NoseManual', 'TailManual', 'Wipeout', 'Landing', 'RideIdle', 'Switching')
    for name in augmentations:
        add('SetScoreAugmentation', [attribute('augment', name)])
    add('SetScoreAugmentation', [attribute('augment', 'TailManual'), attribute('mirrorAugment', 'NoseManual')])
    for extra in ((), (attribute('setToValue', bits=fbits(.35)),), (attribute('trickFromManual', boolean=0),), (attribute('trickFromGrind', boolean=0),)):
        add('SetTrickHeight', [attribute('from', 'HEIGHT_SOURCE'), attribute('rename', 'HEIGHT_OUT'), *extra])
    add('SetTrickHeight', [attribute('from', 'missing'), attribute('rename', 'HEIGHT_OUT')])
    add('SetTrickAttr', [attribute('trick', 'Heelflip')])
    add('TweakProject')
    for count in (1., 3.9, 0., -2., from_bits(0x7fc12345), float('inf')):
        add('ChooseRandomLanding', [attribute('numlandings', bits=fbits(count))])
    for seconds in (.15, 0.):
        add('EndShimmy', [attribute('blendtime', bits=fbits(seconds))])
    add('InitMovingObjects', [attribute('path', 'WORLD/train')])
    add('InitMovingObjects', [attribute('object', 'WORLD/car')])
    add('InitMovingObjects', [attribute('nameToFind', 'WORLD/étram')])
    add('MovingObject', [attribute('path', 'WORLD\\train')])
    add('MovingObject', [attribute('object', 'WORLD/car')])
    add('MovingObject', [attribute('nameToFind', 'WORLD/étram')])
    add('MovingObject', [attribute('path', 'unregistered')])
    graph = element('state', 'root', children=configs)
    return graph, configs, groups


def fixture_metadata():
    data = dict(version=1, source_bank='ScoreFixture.abin', source_sha256='b'*64, source_bytes=1000000,
        clips=[], phase_blends=[], blend_spaces=[], selectors=[], selection_spaces=[], unsupported_trees=[])
    def clip(name, pairs):
        offset = 48 + len(data['clips'])*4096
        # Original PhaseBlend intersection scans forward by encoded name.
        # Authored attribute order is part of the format; an unsorted TWEAK
        # child drops PROOF_X/Y even though the parameter reaches the tree.
        pairs = sorted(pairs, key=lambda item: tuple(attribute_name(item[0])))
        attrs = [dict(name=n, type_id=0, begin_bits=fbits(-1), end_bits=fbits(-1), payload_words=[fbits(v)], source_offset=offset+128+i*128) for i, (n, v) in enumerate(pairs)]
        data['clips'].append(dict(name=name, source_offset=offset, fps_bits=fbits(30), frames_bits=fbits(61), base_speed_bits=fbits(1), flags_word=0x10000000, attributes=attrs))
    clip('PROBE_EMPTY', [('HEIGHT_SOURCE', .8)])
    for param, proof, tree, low, high in (('HEIGHT_OUT', 'PROOF_HEIGHT', 'PROBE_HEIGHT', 0., 1.),
            ('TWEAK_X', 'PROOF_X', 'PROBE_TWEAK_X', -1., 1.), ('TWEAK_Y', 'PROOF_Y', 'PROBE_TWEAK_Y', -1., 1.)):
        children = []
        for i, value in enumerate((low, high)):
            child = f'{tree}_{i}'
            children.append(child)
            attrs = [(param, value), (proof, value)]
            if param == 'HEIGHT_OUT':
                attrs += [('HEIGHT_SOURCE', .8), ('DEFAULTCYC', 1.)]
            clip(child, attrs)
        data['phase_blends'].append(dict(name=tree, source_offset=100000+len(data['phase_blends'])*4096, parameter=param, children=children))
    validate_fixture_attributes(data)
    return data


def corpus(configs, groups):
    rows = []
    def add(index, phase, *, clip=0, mirror=1, reset=0, channels=0, dt=0., motion=None, filtered=None):
        rows.append(dict(index=index, phase=phase, clip=clip, mirror=mirror, reset=reset, channels=channels, dt=dt, motion=motion or {}, filtered=filtered or {}))
    # Real source allocation and all three phases for every authored factory.
    for i, config in enumerate(configs):
        for phase in range(3):
            add(i, phase, clip=2 if phase == 0 else 0, channels=3 if config['attributes'][0]['text'] == 'EndShimmy' else 0,
                filtered={'X': .75, 'Y': .5, 'TweakX': .7, 'TweakY': -.6}, motion={'GestureSpeed': .6})
    degrees = (0, 1, 44, 46, 89, 91, 134, 179, 181, 224, 226, 269, 271, 314, 316, 359)
    vectors = [(0., 0.), (.5, 0.), (from_bits(fbits(.5)+1), 0.), (-.5, 0.), (-0., -.5)]
    for angle in degrees:
        x, y = from_bits(fbits(math.cos(math.radians(angle)))), from_bits(fbits(math.sin(math.radians(angle))))
        for delta in (-1, 0, 1):
            xb = fbits(x)
            vectors.append((from_bits(xb+delta) if x != 0 else x, y))
    for name in ('ScoringHandPlants', 'ScoringGrabs'):
        for index in groups[name][:16]:
            for x, y in vectors:
                add(index, 1, filtered={'X': x, 'Y': y})
    for index in groups['ScoringGrabs'][16:]:
        for angle in degrees:
            radians = from_bits(fbits(math.radians(angle)))
            for delta in (-1, 0, 1):
                for magnitude in (.5, 1.):
                    add(index, 1, filtered={'Angle': from_bits(fbits(radians)+delta) if radians else radians, 'Magnitude': magnitude})
    for index in groups['SetScoreAugmentation']:
        for mirror in (0, 1, 2):
            add(index, 1, mirror=mirror, reset=1)
    for index in groups['SetTrickHeight']:
        for clip in (1, 2):
            for motion in ({}, {'GestureSpeed': -.2}, {'GestureSpeed': .2}, {'GestureSpeed': 1.2}, {'GestureSpeed': .6, 'TrickHeight': .9}, {'GestureSpeed': from_bits(0x7fc12345)}):
                add(index, 0, clip=clip, motion=motion)
    trick = groups['SetTrickAttr'][0]
    for clip in (1, 2):
        for phase in (0, 1, 2):
            add(trick, phase, clip=clip)
    tweak = groups['TweakProject'][0]
    for filtered in ({}, {'TweakX': .25}, {'TweakY': -.5}, {'TweakX': .75, 'TweakY': -.5}, {'TweakX': -.5, 'TweakY': .5}, {'TweakX': -0., 'TweakY': 0.}, {'TweakX': float('inf'), 'TweakY': 1.}):
        add(tweak, 1, filtered=filtered)
    for index in groups['ChooseRandomLanding']:
        for _ in range(16):
            add(index, 0)
            add(index, 1)
        add(index, 2)
    idle = groups['ScoringTrick'][0]
    for index in groups['EndShimmy']:
        # Real fading channels remain present until the subsequent retire pass.
        add(index, 0, channels=3)
        for _ in range(8):
            add(idle, 0, dt=.05)
    train, car, tram, unknown = groups['MovingObject']
    for index, phase in ((train, 1), (train, 0), (train, 1), (car, 1), (car, 0), (train, 1), (car, 1), (unknown, 0), (car, 1), (unknown, 1), (tram, 0), (tram, 1), (tram, 2), (tram, 1), (train, 2)):
        add(index, phase)
    w = Record()
    w.word(len(rows))
    for row in rows:
        w.words((row['index'], row['phase'], row['clip'], row['mirror'], row['reset'], row['channels']))
        w.scalar(row['dt'])
        for name in ('motion', 'filtered'):
            w.word(len(row[name]))
            for key, value in row[name].items():
                w.raw(key)
                w.scalar(value)
    return bytes(w.data), rows


def coverage(data, rows, groups, trace_path=None):
    at = 0
    def word():
        nonlocal at
        v, = struct.unpack_from('<I', data, at)
        at += 4
        return v
    def string():
        nonlocal at
        n = word()
        s = data[at:at+n].decode()
        at += n
        return s
    def name():
        return tuple(word() for _ in range(5))
    def optional_name():
        return name() if word() else None
    def vector():
        return dict(name=name(), xy=[word(), word()]) if word() else None
    def scalar():
        ok = word()
        return dict(ok=ok, value=word() if ok else string())
    assert word() == len(rows)
    traces, selected, effects, phases = [], {'ScoringHandPlants': set(), 'ScoringGrabs': set()}, Counter(), {}
    previous_random = None
    for tick, row in enumerate(rows):
        error = string()
        statuses = [(word(), string()) for _ in range(3)]
        assert statuses == [(1, ''), (1, ''), (1, '')], (tick, row, statuses)
        handplant, grab = vector(), vector()
        trick = [optional_name(), optional_name()]
        score_name = word() if word() else None
        flags, moving = word(), word()
        construction = [(name(), name()) for _ in range(word())]
        packets = [(name(), word()) for _ in range(word())]
        attributes = []
        for _ in range(word()):
            n = name()
            kind, status, sequence, begin, end = [word() for _ in range(5)]
            payload = [word() if word() else None for _ in range(6)]
            attributes.append(dict(name=n, kind=kind, status=status, sequence=sequence, begin=begin, end=end, payload=payload))
        channels = [[word(), word(), word(), word()] for _ in range(4)]
        clock = [scalar(), scalar()]
        op = next(n for n, ids in groups.items() if row['index'] in ids)
        phases.setdefault(op, set()).add(row['phase'])
        if op in selected and row['phase'] == 1:
            selected[op].add(tuple((handplant if op == 'ScoringHandPlants' else grab)['name']))
        if packets:
            effects['height_packets'] += 1
        if trick[0] and trick[0] == trick[1] and flags & 0x01000000:
            effects['scoring_trick'] += 1
        if score_name is not None:
            effects['score_name'] += 1
        if error:
            effects['diagnostics'] += 1
        if moving:
            effects['moving_active'] += 1
        random = next((v for n, v in construction if n == tuple(attribute_name('Random'))), None)
        if random and random != previous_random:
            effects['random_values_changed'] += 1
        previous_random = random
        for proof in ('PROOF_HEIGHT', 'PROOF_X', 'PROOF_Y'):
            values = [a['payload'][0] for a in attributes if a['name'] == tuple(attribute_name(proof))]
            if values:
                effects[proof] += 1
        traces.append(dict(tick=tick, operation=op, phase=row['phase'], error=error, handplant=handplant, grab=grab, trick_names=trick, score_name=score_name, flags=flags, moving_active=moving, construction=construction, packets=packets, tree_attributes=attributes, channels=channels, clock=clock))
    assert at == len(data)
    if trace_path is not None:
        trace_path.write_text(json.dumps(traces, indent=2)+'\n')
    assert all(v == {0, 1, 2} for v in phases.values()), phases
    assert all(len(v) >= 5 for v in selected.values()), selected
    assert all(effects[n] > 0 for n in ('height_packets', 'scoring_trick', 'score_name', 'diagnostics', 'moving_active', 'random_values_changed', 'PROOF_HEIGHT', 'PROOF_X', 'PROOF_Y')), effects
    for proof in ('PROOF_HEIGHT', 'PROOF_X', 'PROOF_Y'):
        values = {a['payload'][0] for t in traces for a in t['tree_attributes'] if a['name'] == tuple(attribute_name(proof))}
        assert len(values) >= 3, (proof, values)
    assert any(t['channels'][2][0] and t['channels'][3][0] for t in traces)
    assert any(not t['channels'][2][0] and not t['channels'][3][0] for t in traces)
    assert any('MovingObject is not active:' in t['error'] for t in traces)
    assert any('MovingObject resource is not registered:' in t['error'] for t in traces)
    assert any('MovingObject update references unknown resource:' in t['error'] for t in traces)
    assert any('Score augmentation requires animation stance' in t['error'] for t in traces)
    assert any('ChooseRandomLanding requires numlandings > 0' in t['error'] for t in traces)
    return dict(commands=len(rows), operation_names=len(phases), phases={n: sorted(v) for n, v in phases.items()}, distinct_score_names={n: len(v) for n, v in selected.items()}, observable_effects=dict(effects)), traces


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, required=True)
    p.add_argument('--metadata', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--target-dir', type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for marker in ('result.json', 'first-divergence.json'):
        (output/marker).unlink(missing_ok=True)
    sources = ('NativeMath', 'AnimationName', 'Intents', 'Input', 'InputIntentions', 'NameId', 'Settings', 'Graph', 'GraphController', 'GraphConditions', 'GraphGestureOperations',
        'AnimationSamples', 'AnimationMetadata', 'AnimationPlayback', 'AnimationPlaybackParameters', 'AnimationTrees', 'AnimationChannels', 'MotionAnimation',
        'MotionFrame', 'GraphMotionName', 'GraphMotionConditions', 'GraphMotionScoreOperations')
    cpp, rust = build_probes(output, args.target_dir, 'motion_score_operations', sources)
    graph, configs, groups = fixture()
    reference, native = output/'operations.reference-graph', output/'operations.graph'
    reference.write_bytes(original_graph(graph))
    native.write_bytes(converter.encode_graph(converter.read_graph(reference)))
    metadata = fixture_metadata()
    metadata_json, metadata_native = output/'fixture.json', output/'fixture.skate'
    metadata_json.write_text(json.dumps(metadata))
    metadata_native.write_bytes(metadata_converter.pack_metadata(metadata))
    inputs, rows = corpus(configs, groups)
    (output/'input.bin').write_bytes(inputs)
    (output/'authored-commands.json').write_text(json.dumps(rows, indent=2)+'\n')
    expected = subprocess.check_output([str(rust), str(args.assets), str(reference), str(metadata_json)], input=inputs)
    actual = subprocess.check_output([str(cpp), str(args.metadata/'bank-0.skate'), str(args.metadata/'bank-1.skate'), str(metadata_native), str(native)], input=inputs)
    # Save both complete outputs before any coverage assertion, including
    # equal-byte runs whose authored observer coverage is insufficient.
    (output/'reference.bin').write_bytes(expected)
    (output/'cpp.bin').write_bytes(actual)
    if actual != expected:
        first = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
        report = dict(passed=False, first_byte=first, reference_length=len(expected), cpp_length=len(actual), reference_hex=expected[max(0, first-16):first+32].hex(), cpp_hex=actual[max(0, first-16):first+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    result, trace = coverage(expected, rows, groups, output/'original-trace.json')
    (output/'original-trace.json').write_text(json.dumps(trace, indent=2)+'\n')
    report = dict(passed=True, authored_configs=len(configs), output_bytes=len(expected), output_sha256=hashlib.sha256(expected).hexdigest(), coverage=result,
        comparison='exact full pinned MotionHost factories/phase dispatch; standard f32 trig at sector boundaries, all direction masks, real applied height/tweak trees, score flags/names, shared RNG, fading shimmy channels, UTF8/path aliases, registry errors and retained state',
        limitations='Host registration and full physical producers are separate. Current original host fixes trick-height settings to (true,true); other setting combinations and exhaustive malformed parser diagnostics are not covered.', reference_provenance='reference-provenance.json')
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
