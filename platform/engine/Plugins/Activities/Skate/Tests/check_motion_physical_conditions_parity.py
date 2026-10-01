#!/usr/bin/env python3
"""Bounded source-faithful physical predicates and explicit absence semantics.

Run under atelier.safety. Original factories/conditions execute through the full
unchanged pinned MotionHost; the candidate reads only completed input records.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
from check_gesture_parity import converter, PLUGIN
from check_graph_parity import attribute, element, original_graph
from check_input_parity import Record, fbits, from_bits
from session_parity import REFERENCE_REVISION, digest


def fixture():
    configs = []
    def add(name, values=()):
        configs.append(element('condition', name, [attribute('mask', 'always'), *values]))
    for name in ('IsRetrievingSkateboard', 'IsInBipedAir', 'IsHippyHurdling', 'PhysicsWantsRunout', 'IsPhysicsWiping',
                 'IsBodyFlipping', 'PhysicsWantsWipeOut', 'IsBumped', 'IsGrabbingObject', 'OkToDoTrickOnStairs',
                 'IsEnteringSkitch', 'IsSkitching', 'IsFootPlanting', 'ShouldPrepareOneFootAirForFootplant',
                 'HasNewHandPlantPos', 'IsMovingObject'):
        add(name)
    for phase in ('antic', 'into', 'out'):
        add('ShouldPlayHandPlantAnim', [attribute('anim', phase)])
    for state in ('air', 'ground'):
        for direction in ('FS', 'BS', 'any'):
            add('IsHandPlanting', [attribute('state', state), attribute('dir', direction)])
    numeric = [attribute('greater', bits=fbits(.25))]
    for name in ('TimeToLand', 'OBTimeToLand', 'OBTrajTime'):
        add(name, numeric)
    for loco in ('Stand', 'Walk', 'Run', 'Sprint'):
        add('LocoState', [attribute('locostate', loco)])
    for slope in ('Flat', 'StairUpShallow', 'StairUpSteep', 'StairDnShallow', 'StairDnSteep', 'RampUpShallow', 'RampUpSteep', 'RampDnShallow', 'RampDnSteep'):
        add('GroundSlopeType', [attribute('slopetype', slope)])
    for name in ('IsRidingGoofy', 'IsBipedGroundThin', 'IsHoldingSkateboard', 'IsStandingOnMovingObject',
                 'CanLandOnBoard', 'IsDeckFree', 'IsBipedCommittedToMotion', 'CanBipedLand',
                 'IsCrouchedEnoughForBlendToGrabCycle', 'TrucksOrDeckInContact', 'PhysicsWantsManualExit', 'ApexReached'):
        add(name)
    add('DistToEdge', numeric)
    for db, animation in (('OffBoard', 'HIPPYOUT_FWD_HI_TO_BIG_FWD_25'), ('missing', 'HIPPYOUT_FWD_HI_TO_BIG_FWD_25'), ('OffBoard', 'missing')):
        add('EnoughDistToObstacle', [attribute('db', db), attribute('anim', animation)])
    for axis in ('Xsuffix', 'y', 'Z', ''):
        add('ComVelCompare', [attribute('axis', axis), *numeric])
    for name in ('SkateSlope', 'SurfaceSlope'):
        add(name, [attribute('greater', bits=fbits(45.))])
    add('DisableDismount')
    return element('state', 'root', children=[element('expression', attributes=[attribute('op', 'or')], children=configs)]), configs


def corpus():
    w = Record()
    frames = 160
    w.word(frames)
    nan = from_bits(0x7fc12345)
    levels = (0., .1, .25, from_bits(0x3e800001), .5, -.1, nan, float('inf'), float('-inf'))
    for tick in range(frames):
        mask = 0 if tick == 0 else 1023 ^ (1 << (tick-2)) if 2 <= tick < 12 else 1023
        w.word(mask)
        w.word((100, 104, 600, 500)[tick % 4])
        w.words(((tick+i) % 2 for i in range(10)))
        w.word(((tick//3) % 8) << 29)
        w.scalar((-.6, -.15, 0., .15, .4, .8)[tick % 6])
        w.scalars((.1, .25, .5))
        w.word(tick % 2)
        w.scalar((-1., -0., 0., .1, nan)[tick % 5])
        w.scalar((.099, .1, .3, .5, .501, nan)[tick % 6])
        w.scalar((-.1, -0., 0., .1, .2, nan)[tick % 6])
        w.scalar(.1)
        w.scalar(levels[tick % len(levels)])
        w.word(tick % 3 != 0)
        w.scalar(levels[(tick+1) % len(levels)])
        w.scalar(.5)
        w.scalars((0., 0., 0., 1.))
        w.scalars((0., (.8, .85, from_bits(fbits(.85)+1), 1., nan)[tick % 5], 0., 0.))
        w.word(tick % 2)
        w.scalar((.2, .3, 1., 1.4, 2., nan)[tick % 6])
        w.scalar(levels[(tick+2) % len(levels)])
        w.scalar(levels[(tick+3) % len(levels)])
        w.words((tick % 3 != 1, *((tick+i) % 2 for i in range(8))))
        w.words((tick % 2, (tick//2) % 2, tick % 5, tick % 10, tick % 2, (tick//2) % 2, (tick//3) % 2, (tick//5) % 2))
        w.scalar((.5, .6, .7, nan)[tick % 4])
        speed = (0., -1., 1., .125, .5, nan)[tick % 6]
        w.scalars((speed, speed*.5, speed*-.5, from_bits(0x7fc54321)))
        w.scalars((1., 0., 0., from_bits(0xffc43210)))
        w.scalars((0., 0., 1., from_bits(0x7fc98765)))
        w.scalars(((0., 1., -.5, .5, 1.1, nan)[tick % 6], (1., 0., .5, -.5, -1.1, nan)[tick % 6]))
        w.scalar((.63, .64, .65, nan)[tick % 4])
        w.word((tick//4) % 2)
        w.scalar(45.)
    return bytes(w.data), frames


def build_probes(output, target_dir):
    native, cpp = PLUGIN/'Source/AtelierSkate/Private/Native', output/'motion-physical-cpp'
    sources = ('NativeMath', 'AnimationName', 'Intents', 'NameId', 'Settings', 'Graph', 'GraphController', 'GraphConditions', 'GraphGestureOperations',
        'AnimationSamples', 'AnimationMetadata', 'AnimationPlayback', 'AnimationPlaybackParameters', 'AnimationTrees', 'AnimationChannels', 'MotionAnimation',
        'MotionFrame', 'GraphMotionName', 'GraphMotionPhysicalConditions')
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror',
        '-I', str(native), *(str(native/f'{n}.cpp') for n in sources), str(PLUGIN/'Tests/Native/motion_physical_conditions_probe.cpp'), '-o', str(cpp)], check=True)
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=PLUGIN, text=True).strip())
    relative = (PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix()
    revision = subprocess.check_output(['git', 'rev-parse', REFERENCE_REVISION], cwd=root, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', f'{revision}:{relative}'], cwd=root)
    source = output/'reference-source'
    source.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(source, filter='data')
    originals = {p.relative_to(source).as_posix(): digest(p) for p in sorted(source.rglob('*.rs')) if p.name != 'migration_probe.rs'}
    crate, host_source = source/'atelier-host', source/'crates/skate-host/src'
    staged = {}
    for original in sorted(host_source.rglob('*.rs')):
        relative = original.relative_to(host_source)
        if relative.as_posix() in ('lib.rs', 'main.rs'):
            continue
        destination = crate/'src'/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
        expected = digest(original)
        assert digest(destination) == expected
        staged[relative.as_posix()] = expected
    cargo = crate/'Cargo.toml'
    cargo.write_text(cargo.read_text()+'\nskate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\nskate-net={path="../crates/skate-net"}\nhalf="2.7.1"\nbevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n\n[[bin]]\nname="motion-physical-reference"\npath="src/migration_probe.rs"\n')
    probe = PLUGIN/'Tests/Reference/motion_physical_conditions_probe.rs'
    shutil.copyfile(probe, crate/'src/migration_probe.rs')
    subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2', '--manifest-path', str(cargo), '--target-dir', str(target_dir.resolve()), '--bin', 'motion-physical-reference'], check=True)
    for relative, expected in originals.items():
        assert digest(source/relative) == expected
    for relative, expected in staged.items():
        assert digest(crate/'src'/relative) == expected
    rust = output/'motion-physical-reference'
    shutil.copy2(target_dir.resolve()/'release/motion-physical-reference', rust)
    (output/'reference-provenance.json').write_text(json.dumps(dict(reference_revision=revision, source_archive_sha256=hashlib.sha256(archive).hexdigest(),
        original_source_sha256=originals, staged_host_modules_sha256=staged, probe_sha256=digest(probe), binary_sha256=digest(rust),
        cargo_lock_sha256=digest(crate/'Cargo.lock'), compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip()), indent=2)+'\n')
    return cpp, rust


def coverage(data, configs, frames):
    at = 0
    def word():
        nonlocal at
        value, = struct.unpack_from('<I', data, at)
        at += 4
        return value
    def string():
        nonlocal at
        length = word()
        value = data[at:at+length].decode()
        at += length
        return value
    assert word() == frames and word() == len(configs)
    truth, errors = [set() for _ in configs], [set() for _ in configs]
    trace = []
    for tick in range(frames):
        row = []
        for i in range(len(configs)):
            value, error = word(), string()
            if not error:
                truth[i].add(value)
            else:
                errors[i].add(error)
            row.append(dict(value=value, error=error))
        trace.append(dict(tick=tick, results=row))
    assert at == len(data)
    for i, config in enumerate(configs):
        assert truth[i] == {0, 1}, (i, config, truth[i])
        name = config['attributes'][0]['text']
        if name == 'IsHoldingSkateboard':
            assert not errors[i], 'Original absent board-toggle publication must evaluate false'
        else:
            assert errors[i], (i, config, 'missing-publication error not exercised')
    return dict(condition_configs=len(configs), condition_names=len({c['attributes'][0]['text'] for c in configs}), evaluations=len(configs)*frames,
        conditions=[dict(config=config, truth_values=sorted(values), missing_publication_errors=sorted(error)) for config, values, error in zip(configs, truth, errors)]), trace


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
    cpp, rust = build_probes(output, args.target_dir)
    graph, configs = fixture()
    reference, native = output/'conditions.reference-graph', output/'conditions.graph'
    reference.write_bytes(original_graph(graph))
    native.write_bytes(converter.encode_graph(converter.read_graph(reference)))
    inputs, frames = corpus()
    (output/'input.bin').write_bytes(inputs)
    expected = subprocess.check_output([str(rust), str(args.assets), str(reference)], input=inputs)
    actual = subprocess.check_output([str(cpp), str(args.metadata/'bank-0.skate'), str(args.metadata/'bank-1.skate'), str(native)], input=inputs)
    if actual != expected:
        (output/'reference.bin').write_bytes(expected)
        (output/'cpp.bin').write_bytes(actual)
        first = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
        report = dict(passed=False, first_byte=first, reference_length=len(expected), cpp_length=len(actual), reference_hex=expected[max(0, first-16):first+32].hex(), cpp_hex=actual[max(0, first-16):first+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    result, frames = coverage(expected, configs, frames)
    (output/'original-trace.json').write_text(json.dumps(frames, indent=2)+'\n')
    report = dict(passed=True, output_bytes=len(expected), output_sha256=hashlib.sha256(expected).hexdigest(), coverage=result,
        comparison='exact actual original MotionHost physical condition factories/evaluation; authored configs, finite boundaries, NaNs, inactive validity flags, independent optional publication absence',
        limitations='Complete physical producer and controller registration are separate. Invalid raw-name mismatch panic translation and exhaustive malformed parser diagnostics remain unverified.', reference_provenance='reference-provenance.json')
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
