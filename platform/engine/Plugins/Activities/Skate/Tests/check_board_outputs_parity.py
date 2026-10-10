#!/usr/bin/env python3
"""Compare persistent board ground/probe state and live output against frozen Rust.

The oracle runs unchanged skate-core source from 46513a6. This checks actual body
poses, four-lane toolkit data, query publication and completed-contact reports;
query generation/solver production and the gameplay owner are separate checks.
Run through the shared render lock and memory guard.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tarfile

PLUGIN = Path(__file__).resolve().parents[1]
REFERENCE_REVISION = '46513a6'
OPERATIONS = ('ground_stream', 'probe_stream', 'toolkit', 'live_board_outputs')
GROUND_WIDTH = 157
TOOLKIT_WIDTH = 83
LIVE_WIDTH = 128


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def scalar(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def f(values):
    return list(map(bits, values))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus():
    rng = random.Random(0x82c07d20)
    records, cases = [], []

    def add(op, payload, label, **meta):
        cases.append(dict(index=len(cases), operation=OPERATIONS[op], label=label, **meta))
        records.append(struct.pack('<' + 'I' * (len(payload) + 1), op, *payload))

    def numbers(n, scale=1.):
        return [rng.uniform(-scale, scale) for _ in range(n)]

    def normal():
        v = numbers(3)
        length = math.sqrt(sum(x * x for x in v))
        return [x / length for x in v]

    def transform(angle=0., pos=None):
        c, s = math.cos(angle), math.sin(angle)
        return f([c, 0., -s, 0., 1., 0., s, 0., c] + (numbers(3, 20.) if pos is None else list(pos)))

    def matrix(angle=0., carry=True):
        c, s = math.cos(angle), math.sin(angle)
        columns = ([c, 0., -s], [0., 1., 0.], [s, 0., c])
        return f([w for column in columns for w in (*column, rng.choice((0., -0., .25, -1.)) if carry else 0.)] + numbers(3, 20.) + [rng.choice((0., -0., 1.)) if carry else 1.])

    def report(part, n, tag=0, pos=None, velocity=None):
        return [part] + f(n + (numbers(3, 2.) if pos is None else list(pos)) + (numbers(3, 20.) if velocity is None else list(velocity))) + [tag]

    def update(reports, up=(0., 1., 0.), angle=75., wipe=False):
        return [1, len(reports)] + [w for r in reports for w in r] + f(up) + [bits(angle), int(wipe)]

    def publish(hits):
        return [0] + [w for hit in hits for w in ([0] if hit is None else [1, bits(hit[0]), *f(hit[1]), hit[2]])]

    for seed in range(128):
        seeded = bool(seed % 2)
        initial = [int(seeded)]
        if seeded:
            initial += f([w for _ in range(4) for w in normal()] + [rng.uniform(0., .2) for _ in range(4)])
            initial += [rng.randrange(32) for _ in range(4)] + f([.05] + numbers(21, 10.) + normal()) + [rng.getrandbits(32), bits(.25)]
        commands, meta = [], []

        def command(words, **extra):
            commands.append(words)
            meta.append(dict(command=words[0], **extra))

        hits = [(rng.uniform(.0, .35), [0., 1., 0.], (8 if i % 2 == 0 else 12) << 7) for i in range(4)]
        command(publish(hits), hit_mask=15)
        command([2] + f([w for _ in range(7) for w in (0., -2., 4.)]) + [bits(1 / 60)])
        command(update([report(i, [0., 1., 0.], 12 << 7) for i in range(4)]), reports=4)
        command([3, bits(1 / 60)])
        command(publish([None] * 4), hit_mask=0)
        command(update([]), reports=0)
        command([3, bits(1 / 60)])
        command(update([report(6, [0., -1., 0.], 12 << 7), report(6, [0., 1., 0.], 8 << 7), report(4, [1., 0., 0.]), report(5, [-1., 0., 0.])], wipe=True), reports=4)
        command(update([report(0, [0., 1., 0.]), report(0, [1., .1, 0.]), report(0, [0., 1., 0.]), report(1, [0., 1., 0.])], wipe=True), reports=4)
        for tick in range(24):
            if tick % 4 == 0:
                hits = [None if (tick + i + seed) % 3 == 0 else (rng.choice((0., -.0, .35, .35000005, 1., -1., 2.)), normal(), rng.getrandbits(16)) for i in range(4)]
                command(publish(hits), hit_mask=sum((1 << i) for i, h in enumerate(hits) if h is not None))
            velocities = f(numbers(21, 20.))
            command([2] + velocities + [bits((1 / 60, 1 / 120, 1 / 30)[tick % 3])])
            rs = [report(rng.randrange(7), normal(), rng.choice((0, 8, 12, 31)) << 7) for _ in range(tick % 13)]
            command(update(rs, up=normal() if tick % 5 == 0 else (0., 1., 0.), angle=(0., 30., 45., 60., 75., 90., 180.)[tick % 7], wipe=bool(tick % 2)), reports=len(rs))
            command([3, bits(1 / 60)])
        command([4])
        command(update([]), reports=0)
        command([3, bits(1 / 60)])
        add(0, initial + [len(commands)] + [w for c in commands for w in c], 'persistent misses, old-velocity closures, selected reports, contact/drag resets', commands=meta, seeded=seeded)

    # Explicit gates and exceptional query fractions, without repairing original values.
    fractions = (0, 0x80000000, 0x3eb33332, 0x3eb33333, 0x3eb33334, 0x3f800000, 0x7f800000, 0xff800000, 0x7fc00000)
    for fraction in fractions:
        commands = [[0] + [w for i in range(4) for w in (1, fraction, *f([0., 1., 0.]), (8 + i) << 7)], update([report(0, [0., 1., 0.])]), publish([None] * 4), update([])]
        add(0, [0, len(commands)] + [w for c in commands for w in c], 'wheel-distance ordered boundary/NaN publication', commands=[dict(command=0, hit_mask=15), dict(command=1, reports=1), dict(command=0, hit_mask=0), dict(command=1, reports=0)])
    for n in ([0., 0., 0.], [.0001, 0., 0.], [0., .001, 0.], [0., .01, 0.], [0., -1., 0.], [0., 1., 0.]):
        commands = [update([report(0, n), report(1, [-v for v in n]), report(6, n)], angle=180.), [3, bits(1 / 60)]]
        add(0, [0, len(commands)] + [w for c in commands for w in c], 'small-vector wheel sums and ordered deck/truck support', commands=[dict(command=1, reports=3), dict(command=3)])

    for seed in range(128):
        commands, meta = [], []
        for tick in range(32):
            op = (0, 1, 1, 0, 1, 2, 1, 0)[tick % 8]
            hit = op == 1 and tick % 4 != 2
            words = [op]
            if op == 0:
                words += f(numbers(3, 20.))
            elif op == 1:
                words += [int(hit)]
                if hit:
                    words += f(numbers(3, 20.) + normal()) + [rng.getrandbits(32)]
            # Deliberately cross each of the state, y, up-dot and elapsed gates.
            state = (100, 101, 99, 102)[(tick // 8 + seed) % 4]
            n = [1., (0., .49999997, .5, -.5)[tick % 4], 0.]
            up = [(1., .71, .71000004, .70999998)[(tick // 4) % 4], 0., 0.]
            time = (0., .01, .01000001, 1.)[(tick // 8) % 4]
            enabled = state in (100, 101) and abs(n[1]) < .5 and scalar(bits(up[0])) > scalar(0x3f35c28f) and scalar(bits(time)) > scalar(0x3c23d70a)
            words += f(numbers(3, 20.)) + [state] + f(n + up + numbers(3, 20.) + [time])
            commands.append(words)
            meta.append(dict(command=op, hit=hit, wall_expected=enabled))
        add(1, [len(commands)] + [w for c in commands for w in c], 'start/miss retain previous hit fields; disable resets; wall query gates', commands=meta)
    for seed in range(32):
        commands, meta = [], []
        for tick in range(12):
            n = [1., rng.uniform(-.49, .49), rng.uniform(-1., 1.)]
            words = [1, 1] + f(numbers(3, 10.) + normal()) + [rng.getrandbits(32)] + f(numbers(3, 10.)) + [100 + tick % 2] + f(n + n + numbers(3, 10.) + [1.])
            commands.append(words)
            meta.append(dict(command=1, hit=True, wall_expected=True))
        add(1, [len(commands)] + [w for c in commands for w in c], 'non-axis wall cross products and normalized down directions', commands=meta)

    for seed in range(1024):
        deck = matrix(rng.uniform(-math.pi, math.pi))
        if seed % 8 == 0:
            deck[8:12] = f([0., 1., 0., rng.choice((0., -.0, 1., -.5))])
        elif seed % 8 == 1:
            deck[8:12] = f([rng.choice((0., 1.e-4, .0031622774, .0031622777)), 1., 0., .5])
        if seed % 7 == 0:
            deck[4:8] = f([0., 0., 0., .5])
        count = (0, 1, 2, 3, 7, 16)[seed % 6]
        masses = [rng.choice((0., -.0, rng.uniform(.0001, 5.))) for _ in range(count)]
        flags = rng.getrandbits(32)
        speed = rng.choice((0., -.0, rng.uniform(-20., 20.)))
        n = normal() + [rng.choice((0., 1., -.5))]
        retained = n if seed % 3 == 0 else normal() + [rng.choice((0., 1., -.5))]
        if seed % 13 == 0:
            n, retained = [0.] * 4, [0.] * 4
        add(2, deck + [count] + f(masses) + [flags, bits(speed)] + f(n + retained), 'four-lane carries, travel sign, degenerate axes, normal filter and alternating mass sums', flags=flags, mass_count=count, speed=bits(speed), normal=f(n))
    for speed in (0, 0x80000000, 1, 0x80000001, 0x7f800000, 0xff800000, 0x7fc00000):
        for flag in (0, 0x00100000):
            deck = matrix(.4)
            add(2, deck + [7] + f([.5] * 7) + [flag, speed] + f([0., 1., 0., 0., 0., 1., 0., 0.]), 'ordered speed zero/subnormal/NaN branch', flags=flag, mass_count=7, speed=speed, normal=f([0., 1., 0., 0.]))

    for seed in range(64):
        ticks, flags = [], []
        for tick in range(24):
            flag = (0, 0x00100000, 0xffffffff)[tick % 3]
            flags.append(flag)
            ticks += transform(rng.uniform(-math.pi, math.pi)) + f(numbers(6, 20.) + normal()) + [flag, bits(rng.uniform(-20., 20.))] + f(normal() + [0.] + normal() + [0.])
        add(3, transform(.2) + [24] + ticks, 'actual seven-body poses drive probes, effective stance and live deck motion/toolkit', flags=flags, ticks=24)
    return struct.pack('<I', len(records)) + b''.join(records), cases


def build_probes(output):
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=PLUGIN, text=True).strip())
    relative = (PLUGIN / 'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision = subprocess.check_output(['git', 'rev-parse', REFERENCE_REVISION], cwd=root, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', f'{revision}:{relative}'], cwd=root)
    source = output / 'reference-source'
    if source.exists():
        shutil.rmtree(source)
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(source, filter='data')
    originals = {p.relative_to(source).as_posix(): digest(p) for p in sorted(source.rglob('*.rs'))}
    probe = PLUGIN / 'Tests/Reference/board_outputs_probe.rs'
    main = source / 'board-outputs-oracle.rs'
    main.write_text((source / 'lib.rs').read_text() + probe.read_text().replace('//!', '//'))
    reference = output / 'board-outputs-reference'
    subprocess.run(['rustc', '+1.97.1', '--edition=2024', '-O', '-A', 'dead_code', str(main), '-o', str(reference)], check=True)
    for name, expected in originals.items():
        if digest(source / name) != expected:
            raise AssertionError(f'Frozen original module changed: {name}')
    snapshot = output / 'simulation-source'
    if snapshot.exists():
        shutil.rmtree(snapshot)
    snapshot.mkdir()
    simulation = PLUGIN / 'Source/AtelierSkate/Private/Simulation'
    units = ('SimulationMath', 'RigidBody', 'BodyMass', 'AggregateMass', 'DeckGeometry', 'DriveFrames', 'ConstraintFrames', 'ConstraintSolver', 'JointBuild', 'DriveBuild', 'JointRecords', 'TruckDriveFrames', 'DrivePreparation', 'HookDrive', 'BoardAssembly', 'ContactBuild', 'ContactGeneration', 'BoardPose', 'ForceQueue', 'CollisionBody', 'BoardContactFeedback', 'BoardStep', 'BoardRuntime', 'BoardGroundAngle', 'BoardMotionOutput', 'BoardGround', 'BoardProbes', 'BoardToolkit')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h', 'cpp')] + ['GeometryTypes.h', 'BoardTypes.h', 'ContactRetention.h']:
        shutil.copy2(simulation / name, snapshot / name)
    shutil.copy2(PLUGIN / 'Tests/Simulation/board_outputs_probe.cpp', snapshot / 'board_outputs_probe.cpp')
    cpp = output / 'board-outputs-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot), *[str(snapshot / f'{unit}.cpp') for unit in units], str(snapshot / 'board_outputs_probe.cpp'), '-o', str(cpp)], check=True)
    provenance = dict(reference_revision=revision, source_archive_sha256=hashlib.sha256(archive).hexdigest(), original_source_sha256=originals, probe_sha256=digest(probe), reference_binary_sha256=digest(reference), cpp_binary_sha256=digest(cpp), simulation_source_sha256={p.name: digest(p) for p in sorted(snapshot.iterdir())}, rust_compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip(), cpp_compiler=subprocess.check_output(['clang++', '--version'], text=True).strip())
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return cpp, reference


def decode(data, cases):
    if len(data) % 4:
        raise AssertionError('Partial board output word')
    words = struct.unpack('<' + 'I' * (len(data) // 4), data)
    at, rows = 0, []
    for case in cases:
        index, op, count = words[at:at + 3]
        if index != case['index'] or OPERATIONS[op] != case['operation']:
            raise AssertionError('Board output identity changed')
        rows.append(words[at + 3:at + 3 + count])
        case.update(first_output_word=at, output_words=count + 3)
        at += count + 3
    if at != len(words):
        raise AssertionError('Trailing board output words')
    return rows


def coverage(rows, cases):
    counts = Counter()
    wheel_normals = set()
    for row, case in zip(rows, cases):
        op = case['operation']
        counts[op] += 1
        if op == 'ground_stream':
            if row[0] != len(case['commands']) or len(row) != 1 + (row[0] + 1) * GROUND_WIDTH:
                raise AssertionError('Ground stream framing changed')
            before = row[1:1 + GROUND_WIDTH]
            for tick, cmd in enumerate(case['commands']):
                after = row[1 + (tick + 1) * GROUND_WIDTH:1 + (tick + 2) * GROUND_WIDTH]
                counts[f'ground_command_{cmd["command"]}'] += 1
                if cmd['command'] == 0:
                    for wheel in range(4):
                        if not (cmd['hit_mask'] & (1 << wheel)):
                            if after[wheel * 3:wheel * 3 + 3] != before[wheel * 3:wheel * 3 + 3] or after[12 + wheel] != before[12 + wheel] or after[16 + wheel] != 0:
                                raise AssertionError('Miss discarded old wheel normal/distance or retained surface')
                            counts['retained_wheel_misses'] += 1
                    if after[21:] != before[21:]:
                        raise AssertionError('Wheel query publication mutated ground owner')
                elif cmd['command'] == 1:
                    counts['completed_contact_reports'] += cmd['reports']
                    counts['wheel_contact_frames' if after[151] else 'without_wheel_contact_frames'] += 1
                    if after[139] & (1 << 25):
                        counts['surface_twelve_frames'] += 1
                    if after[139] & (1 << 31):
                        counts['surface_eight_frames'] += 1
                    if after[91:133] != before[91:133]:
                        raise AssertionError('Contact selection mutated acceleration/velocity histories')
                    if after[151] == 0 and after[143:146] != before[143:146]:
                        raise AssertionError('Absent physical wheels changed retained wheel normal')
                    if scalar(after[136]) > 0.:
                        counts['closing_velocity_frames'] += 1
                    if scalar(after[137]) > 0.:
                        counts['opposing_deck_frames'] += 1
                    for wheel in range(4):
                        counts['valid_query_or_contact_normals' if after[146 + wheel] else 'invalid_wheel_normals'] += 1
                elif cmd['command'] == 2:
                    if after[:91] != before[:91] or after[133:] != before[133:]:
                        raise AssertionError('Acceleration sampling mutated contact owner')
                elif cmd['command'] == 3:
                    if after[:152] != before[:152] or after[153:] != before[153:]:
                        raise AssertionError('Elapsed-time sampling mutated contact state')
                    if after[151] and after[152] != 0:
                        raise AssertionError('Physical wheel contact did not reset elapsed time')
                elif cmd['command'] == 4:
                    if after[:21] != before[:21] or any(after[91:140]) or any(after[146:]):
                        raise AssertionError('Full ground reset retained histories/flags or changed wheel-query state')
                    if after[140:146] != tuple(f([0., 1., 0.] * 2)):
                        raise AssertionError('Full ground reset changed default normals')
                wheel_normals.add(after[143:146])
                before = after
        elif op == 'probe_stream':
            if row[0] != len(case['commands']):
                raise AssertionError('Probe command count changed')
            at, before = 12, row[1:12]
            for cmd in case['commands']:
                after = row[at:at + 11]
                at += 11
                if cmd['command'] == 0:
                    if after[3:10] != before[3:10] or after[10]:
                        raise AssertionError('Probe start changed previous point/normal/tag or retained hit')
                    counts['probe_starts'] += 1
                elif cmd['command'] == 1 and not cmd['hit']:
                    if after[:10] != before[:10] or after[10]:
                        raise AssertionError('Probe miss discarded retained fields')
                    counts['probe_retained_misses'] += 1
                elif cmd['command'] == 2:
                    if any(after):
                        raise AssertionError('Probe disable did not reset')
                    counts['probe_disables'] += 1
                else:
                    counts['probe_hits'] += 1
                at += 6
                present = row[at]
                at += 1
                if bool(present) != cmd['wall_expected']:
                    raise AssertionError('Authored wall-probe gate changed')
                if present:
                    at += 6
                counts['enabled_wall_probes' if present else 'disabled_wall_probes'] += 1
                before = after
            if at != len(row):
                raise AssertionError('Probe output framing changed')
        elif op == 'toolkit':
            if len(row) != TOOLKIT_WIDTH:
                raise AssertionError('Toolkit width changed')
            reversed_stance = bool(case['flags'] & 0x00100000)
            if row[81] != bits(-1. if reversed_stance else 1.):
                raise AssertionError('Toolkit effective stance changed')
            counts['reversed_toolkits' if reversed_stance else 'regular_toolkits'] += 1
            counts[f'mass_count_{case["mass_count"]}'] += 1
            counts['direct_filtered_normals' if row[76:80] == tuple(case['normal']) else 'blended_filtered_normals'] += 1
            if math.isnan(scalar(case['speed'])):
                counts['unordered_travel_speeds'] += 1
            if row[80] == 0:
                counts['negative_zero_absolute_speeds'] += 1
        elif op == 'live_board_outputs':
            if row[0] != case['ticks'] or len(row) != 1 + LIVE_WIDTH * row[0]:
                raise AssertionError('Live board output framing changed')
            counts['live_deck_ticks'] += row[0]
            for tick, flag in enumerate(case['flags']):
                state = row[1 + tick * LIVE_WIDTH:1 + (tick + 1) * LIVE_WIDTH]
                if state[45 + 81] != bits(-1. if flag & 0x00100000 else 1.):
                    raise AssertionError('Live toolkit used different stance flag')
                counts['live_reversed_stance' if flag & 0x00100000 else 'live_regular_stance'] += 1
    counts['distinct_retained_wheel_normals'] = len(wheel_normals)
    for key in ('retained_wheel_misses', 'completed_contact_reports', 'wheel_contact_frames', 'without_wheel_contact_frames', 'surface_twelve_frames', 'surface_eight_frames', 'closing_velocity_frames', 'opposing_deck_frames', 'invalid_wheel_normals', 'probe_starts', 'probe_retained_misses', 'probe_disables', 'enabled_wall_probes', 'disabled_wall_probes', 'direct_filtered_normals', 'blended_filtered_normals', 'unordered_travel_speeds', 'live_deck_ticks'):
        if not counts[key]:
            raise AssertionError(f'Uncovered board output branch: {key}')
    if counts['distinct_retained_wheel_normals'] < 16:
        raise AssertionError('Ground normals are insufficiently observable')
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'first-divergence.json', 'provenance.json'):
        (output / name).unlink(missing_ok=True)
    inputs, cases = corpus()
    (output / 'input.bin').write_bytes(inputs)
    cpp, reference = build_probes(output)
    expected = subprocess.check_output([str(reference)], input=inputs)
    actual = subprocess.check_output([str(cpp)], input=inputs)
    (output / 'reference.bin').write_bytes(expected)
    (output / 'cpp.bin').write_bytes(actual)
    rows = decode(expected, cases)
    (output / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    if expected != actual:
        first = next((i for i, (a, b) in enumerate(zip(expected, actual)) if a != b), min(len(expected), len(actual)))
        aligned = first // 4 * 4
        case = next((c for c in cases if c['first_output_word'] * 4 <= first < (c['first_output_word'] + c['output_words']) * 4), None)
        report = dict(passed=False, first_word=first // 4, case=case, reference_length=len(expected), cpp_length=len(actual), reference_hex=expected[max(0, aligned - 16):aligned + 32].hex(), cpp_hex=actual[max(0, aligned - 16):aligned + 32].hex())
        (output / 'first-divergence.json').write_text(json.dumps(report, indent=2) + '\n')
        raise AssertionError(report)
    counts = coverage(rows, cases)
    report = dict(passed=True, cases=len(cases), coverage=counts, exact_words=len(expected) // 4, input_sha256=hashlib.sha256(inputs).hexdigest(), output_sha256=hashlib.sha256(expected).hexdigest(), comparison='All live board output, ground history, completed report selection, probe retention and four-lane toolkit words exact; no tolerance; original numerical source unchanged; excludes connected gameplay owner')
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
