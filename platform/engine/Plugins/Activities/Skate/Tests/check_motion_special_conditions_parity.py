#!/usr/bin/env python3
"""Exact remaining grind, landing and wipeout predicates against original host.

Compile only through atelier.safety. Inputs are explicit completed owner records.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from check_gesture_parity import converter
from check_graph_parity import attribute, element, original_graph
from check_input_parity import Record, fbits, from_bits
from check_motion_physical_conditions_parity import coverage
from motion_reference_build import build_probes


def fixture():
    configs = []
    def add(name, values=()):
        configs.append(element('condition', name, [attribute('mask', 'always'), *values]))
    add('IsGrindBluntingBackslash')
    for facing in ('F', 'B', 'f'):
        add('IsGrindApproach', [attribute('Facing', facing)])
    for kind in ('normal', 'left', 'right'):
        add('GrindTrickOutTypeAllowed', [attribute('type', kind)])
    add('IsLandingIntoGrind')
    add('IsDroppingIn')
    for kind in ('straight', 'spin', 'sketchy', 'unknown'):
        add('HasLandingType', [attribute('landingType', kind)])
    add('HasTiltToLargeForPreland')
    add('IsDoneWipingOut')
    for name in ('WipeoutTimeToLand', 'WipeoutTimeSinceContact'):
        for field in ('greater', 'less', 'equal'):
            add(name, [attribute(field, bits=fbits(.2))])
    for gesture in ('Freefall', 'CannonBall', 'JudoKick', 'SwanDive', 'Torpedo'):
        add('GestureType', [attribute('gesture', gesture)])
    for orientation in ('onback', 'onfront', 'either'):
        add('IsInWater', [attribute('orientation', orientation)])
    return element('state', 'root', children=[element('expression', attributes=[attribute('op', 'or')], children=configs)]), configs


def corpus():
    w = Record()
    frames = 160
    w.word(frames)
    nan = from_bits(0x7fc12345)
    times = (0., .1, from_bits(fbits(.2)-1), .2, from_bits(fbits(.2)+1), -.1, nan, float('inf'), float('-inf'))
    # Authored stock settings are override_x=.3 and override_velocity_y=-2.
    tilts = (0., from_bits(fbits(.3)-1), .3, from_bits(fbits(.3)+1), -.31, nan, float('inf'))
    velocities = (-3., -2., from_bits(fbits(-2.)-1), 0., nan)
    for tick in range(frames):
        mask = 0 if tick == 0 else 15 ^ (1 << (tick-2)) if 2 <= tick < 6 else 15
        w.word(mask)
        w.words((tick % 3 != 0, tick % 6, tick % 2, tick % 4, tick % 2))
        w.scalar(times[tick % len(times)])
        w.word((tick//2) % 2)
        w.scalars((.5, -.25))
        w.word(tick % 4)
        w.scalar(.75)
        w.word(tick % 2)
        w.scalars((times[(tick+1) % len(times)], times[(tick+2) % len(times)]))
        w.word(tick % 6)
        w.words((tick % 3 != 0, tick % 7 != 0))
        w.scalars(((-1., -0., 0., 1., nan)[tick % 5], .2, -.3))
        w.word(tick % 13 == 0)
        w.scalars(((.49, .5, from_bits(fbits(.5)+1), nan)[tick % 4], tilts[tick % len(tilts)], velocities[(tick//4) % len(velocities)]))
        w.words((tick % 2, (tick//2) % 2))
        w.scalar(times[(tick+3) % len(times)])
        w.word(tick % 3 == 0)
        w.scalars((.5, times[(tick+4) % len(times)], .5))
    return bytes(w.data), frames


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--target-dir', type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for marker in ('result.json', 'first-divergence.json'):
        (output/marker).unlink(missing_ok=True)
    sources = ('SimulationMath', 'AnimationName', 'Intents', 'NameId', 'Settings', 'Graph', 'GraphController', 'GraphConditions', 'GraphGestureOperations', 'GraphMotionSpecialConditions')
    cpp, rust = build_probes(output, args.target_dir, 'motion_special_conditions', sources)
    graph, configs = fixture()
    reference, simulation = output/'conditions.reference-graph', output/'conditions.graph'
    reference.write_bytes(original_graph(graph))
    simulation.write_bytes(converter.encode_graph(converter.read_graph(reference)))
    settings = output/'settings.simulation'
    settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    inputs, frames = corpus()
    (output/'input.bin').write_bytes(inputs)
    expected = subprocess.check_output([str(rust), str(args.assets), str(reference)], input=inputs)
    actual = subprocess.check_output([str(cpp), str(simulation), str(settings)], input=inputs)
    if actual != expected:
        (output/'reference.bin').write_bytes(expected)
        (output/'cpp.bin').write_bytes(actual)
        first = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
        report = dict(passed=False, first_byte=first, reference_length=len(expected), cpp_length=len(actual), reference_hex=expected[max(0, first-16):first+32].hex(), cpp_hex=actual[max(0, first-16):first+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    result, trace = coverage(expected, configs, frames)
    (output/'original-trace.json').write_text(json.dumps(trace, indent=2)+'\n')
    report = dict(passed=True, output_bytes=len(expected), output_sha256=hashlib.sha256(expected).hexdigest(), coverage=result,
        comparison='exact actual original MotionHost special condition factories/evaluation; all 12 names, boundaries, NaNs, inactive gates and independent optional owner absence',
        limitations='Production completed-input publishers and full MotionHost registration are separate. Exhaustive malformed parser diagnostics remain unverified.', reference_provenance='reference-provenance.json')
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
