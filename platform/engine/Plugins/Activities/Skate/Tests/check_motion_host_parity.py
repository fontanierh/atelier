#!/usr/bin/env python3
"""Bounded real MotionHost/controller lifecycle comparison.

Compile only through atelier.safety. Simulation metadata/settings/graphs and the
unchanged pinned host consume the same explicit completed physical inputs.
"""
import argparse
from collections import Counter, defaultdict
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
from check_input_parity import Record, fbits
from check_animation_trees_parity import name as attribute_name
from session_parity import REFERENCE_REVISION, digest

QUERIES = ('A', 'X', 'Y', 'TweakX', 'TweakY', 'DarkCatch', 'U_Kickflip', 'Turn', 'RawTurn', 'HardTurn')
TICKS = 128


def behavior(name, values=(), children=()):
    return element('behaviour', name, values, children)


def condition(name, values=()):
    return element('condition', name, [attribute('mask', 'always'), *values])


def fixture(case):
    numeric = [attribute('greater', bits=fbits(.2))]
    conditions = [condition('IsPushOffEnabled'), condition('CurrentGrabType', [attribute('grab', 'FS')]),
        condition('HasTweak', numeric), condition('ManualOutTimerIsActive'),
        condition('HasGestureIntent', [attribute('group', 'Square')]), condition('ExpireInTime', [attribute('less', bits=fbits(.2))]),
        condition('WillExpire', [attribute('InTimeTag', 'probe'), attribute('InTime', bits=fbits(.2))]),
        condition('InTimeWindow', [attribute('StartTime', bits=0), attribute('WindowFrameLength', bits=fbits(.5))]),
        condition('IsProSkater', [attribute('skater', 'Loose' if case % 2 == 0 else 'Other')]),
        condition('BreakOutOfPush'), condition('ShouldLeaveSlide', [attribute('right', boolean=case % 2)]),
        condition('IsRidingSwitch'), condition('MongoPushFootToFar'), condition('LastState', [attribute('state', 'active')]),
        condition('IsDark'), condition('IsUnderflipRequested'), condition('IsDarkCatchRequested'),
        condition('CanEnterSlide', [attribute('right', boolean=case % 2)]), condition('IsDroppingSkateboard'),
        condition('AllowedToTrick'), condition('IsInDebugAnimationsMode'), condition('RandomCond')]
    clip = 'R_STAND_IDLE2_N_0_CYC' if case < 4 else 'R_PUSHHSP_HSTR_MONGO_LEFT_CYC1'
    play = behavior('PlayAnimation' if case % 2 == 0 else '\u2003PlayAnimation\u2003', [attribute('anim', clip),
        attribute('transType', 'play'), attribute('applyPosture', boolean=0), attribute('playBackSpeed', bits=fbits(1.+case*.125))],
        [element('param', attributes=[attribute('from', 'intent'), attribute('intent', 'A'), attribute('rename', 'probe'), attribute('defaultValue', bits=fbits(.1))])])
    root_operations = [play, behavior('CreateAttribute', [attribute('attName', 'Marker'), attribute('always', bits=fbits((case+1)*.125))]),
        behavior('AttachIntent', [attribute('intent', 'A'), attribute('attr', 'probe'), attribute('set', boolean=1)]),
        behavior('FilterMotionGraphIntent', [attribute('intent', 'X'), attribute('filteredIntent', 'TweakX'),
            attribute('blend', bits=fbits(.5)), attribute('scale', bits=fbits(1.+case*.125))]),
        behavior('FilterMotionGraphIntent', [attribute('intent', 'Y'), attribute('filteredIntent', 'TweakY'), attribute('filter', 'abs')]),
        behavior('UpdateManualOutTimer'), behavior('UpdateTimeSinceTeleport'), behavior('UpdateTimeSinceKickturn'),
        behavior('ApplyingBodyTilt'), behavior('PrintText2D'), behavior('UpdateStandingOnCar')]
    active_operations = [behavior('SetDark'), behavior('SetGrabType', [attribute('grab', 'FS')]), behavior('MonitorUnderflip'),
        behavior('IsDoingTrick'), behavior('IsManualing'), behavior('IsAnticipating'), behavior('IsLanding'),
        behavior('DisableTricks', [attribute('length', bits=fbits(.035+case*.005))]),
        behavior('SetManualOutTimer', [attribute('length', bits=fbits(.125+case*.03125))]),
        behavior('HandBusy', [attribute('hand', 'bs' if case % 2 == 0 else 'BS')]), behavior('MaintainShove'),
        behavior('UpdateIsWeightOnNose'), behavior('IsPowerSliding'), behavior('InCandidateSlidingState')]
    if case == 7:
        # Source-defined producer gap and unsupported condition stay diagnostic,
        # distinct from the two source-defined no-op operations above.
        active_operations.append(behavior('AirDismounting'))
        conditions.append(condition('IsArmChannelPlaying'))
    active = element('state', 'active', children=[element('expression', attributes=[attribute('op', 'and')],
        children=[condition('HasAGIntent', [attribute('intent', 'enable')])]), *active_operations,
        element('transition', attributes=[attribute('target', 'idle'), attribute('priority', 'urgent')], children=[
            element('expression', children=[condition('HasAGIntent', [attribute('intent', 'exit')])]),
            element('hook', 'GrabSlide', [attribute('right', boolean=case % 2)])])])
    idle = element('state', 'idle', children=[behavior('SetGrabType', [attribute('grab', 'BS')]), behavior('ResetTimeSinceKickturn')])
    return element('state', 'root', children=[element('expression', attributes=[attribute('op', 'or')], children=conditions), *root_operations, active, idle])


def condition_names(graph):
    names = []
    def visit(node):
        if node['tag'] == 'condition':
            names.append(next(v['text'] for v in node['attributes'] if v['name'] == 'name'))
        for child in node['children']:
            visit(child)
    visit(graph)
    return names


def corpus(case):
    w = Record()
    w.word(len(QUERIES))
    for name in QUERIES:
        w.raw(name)
    w.word(TICKS)
    for tick in range(TICKS):
        # EndAll deliberately keeps current/state-times; a later Update does
        # not restart root behaviors. Exercise shutdown after all live frames.
        w.word(tick == 127)
        # This authored Mongo clip has five frames at 60fps and does not loop.
        # Resolve its short clock with actual sub-frame increments.
        w.scalar((0., 1/60, .05, .1)[tick % 4] if case < 4 else (0., .0005, .001, .002)[tick % 4])
        action = []
        if tick % 20 < 12:
            action.append(('enable', 0.))
        if tick % 20 == 8:
            action.append(('exit', 1.))
        if tick % 7 < 4:
            action.append(('Kickflip' if tick % 2 else 'KICKFLIP', 0.))
        motion = [('A', ((tick+case) % 11-5)*.125), ('X', ((tick+case*3) % 13-6)*.125),
            ('Y', ((tick+case) % 5-2)*.25), ('Turn', case*.125), ('RawTurn', tick*.03125), ('HardTurn', -.25)]
        if tick % 20 in (3, 4, 5):
            motion.append(('U_Kickflip', 0.))
        if tick % 20 in (6, 7):
            motion.append(('DarkCatch', 0.))
        for values in (action, motion):
            w.word(len(values))
            for name, value in values:
                w.raw(name)
                w.scalar(value)
        w.words((0x08020000 | (((tick+case) % 4) << 29), (tick//9+case) % 2, (tick//7+case) % 2,
                 5 if tick % 29 == 0 else 1))
        w.words((not(case == 7 and tick % 19 == 0), 102 if tick % 11 == 0 else 100, tick % 13 < 6))
        foot_z = -1. if (tick//5+case) % 2 else 1.
        for vector in ((0., 0., foot_z, 0.), (0., 0., foot_z, 0.), (0., 0., 0., 1.),
                       (0., 1., 0., 0.), (0., 0., 1., 0.)):
            w.scalars(vector)
        w.word((tick//17+case) % 2)
        w.words((fbits(.1), (0x80000000 if tick % 3 else 0) | (0x40000000 if tick % 5 else 0) | case,
                 fbits(.2), (0x80000000 if tick % 5 else 0) | (0x40000000 if tick % 3 else 0) | case,
                 (0x80000000 if tick % 2 else 0) | case))
        w.word(tick % 7 == 0)
        w.scalar(0. if tick % 2 else .9)
        w.word(tick % 9 == 0)
        w.scalar((0., .2, 2., -.1)[tick % 4])
    return bytes(w.data)


def build_probes(output, target_dir):
    simulation = PLUGIN/'Source/AtelierSkate/Private/Simulation'
    cpp = output/'motion-host-cpp'
    sources = ('SimulationMath', 'AnimationName', 'Intents', 'Input', 'InputIntentions', 'NameId', 'Settings',
        'Graph', 'CompiledGraph', 'GraphController', 'GraphConditions', 'GraphGestureOperations', 'GraphIntentOperations',
        'GraphMotionSliding', 'AnimationSamples', 'AnimationMetadata', 'AnimationPlayback', 'AnimationPlaybackParameters',
        'AnimationTrees', 'AnimationChannels', 'MotionAnimation', 'MotionAnimationOperations', 'MotionFrame',
        'GraphMotionName', 'GraphMotionConditions', 'GraphMotionPhysicalConditions', 'GraphMotionSpecialConditions',
        'RidingAnimation', 'RidingAnimationSettings', 'GraphMotionFeedbackOperations', 'GraphMotionScoreOperations', 'GraphMotionPushOperations', 'GraphMotionGestureOperations', 'MotionGraphHost')
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-fno-rtti',
        '-Wall', '-Wextra', '-Werror', '-I', str(simulation), *(str(simulation/f'{n}.cpp') for n in sources),
        str(PLUGIN/'Tests/Simulation/motion_host_probe.cpp'), '-o', str(cpp)], check=True)
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
        assert digest(destination) == expected, f'Staged module changed: {relative}'
        staged[relative.as_posix()] = expected
    cargo = crate/'Cargo.toml'
    cargo.write_text(cargo.read_text()+'\nskate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\nskate-net={path="../crates/skate-net"}\nhalf="2.7.1"\nbevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n\n[[bin]]\nname="motion-host-reference"\npath="src/migration_probe.rs"\n')
    probe = PLUGIN/'Tests/Reference/motion_host_probe.rs'
    shutil.copyfile(probe, crate/'src/migration_probe.rs')
    subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2', '--manifest-path', str(cargo),
        '--target-dir', str(target_dir.resolve()), '--bin', 'motion-host-reference'], check=True)
    for relative, expected in originals.items():
        assert digest(source/relative) == expected, f'Reference implementation changed: {relative}'
    for relative, expected in staged.items():
        assert digest(crate/'src'/relative) == expected, f'Staged reference implementation changed: {relative}'
    rust = output/'motion-host-reference'
    shutil.copy2(target_dir.resolve()/'release/motion-host-reference', rust)
    provenance = dict(reference_revision=revision, source_archive_sha256=hashlib.sha256(archive).hexdigest(), original_source_sha256=originals,
        staged_host_modules_sha256=staged, probe_sha256=digest(probe), binary_sha256=digest(rust), cargo_lock_sha256=digest(crate/'Cargo.lock'),
        compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip())
    (output/'reference-provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    return cpp, rust


class Reader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def word(self):
        value, = struct.unpack_from('<I', self.data, self.at)
        self.at += 4
        return value

    def words(self, count):
        return [self.word() for _ in range(count)]

    def string(self):
        count = self.word()
        value = self.data[self.at:self.at+count].decode()
        self.at += count
        return value

    def optional(self):
        return self.word() if self.word() else None

    def mapping(self):
        return dict(size=self.word(), values=dict(zip(QUERIES, (self.optional() for _ in QUERIES))))

    def scalar(self):
        return dict(ok=True, value=self.word()) if self.word() else dict(ok=False, error=self.string())


def trace(data, names, case):
    r, frames = Reader(data), []
    for tick in range(r.word()):
        count = r.word()
        assert count == len(names)
        conditions = dict(zip(names, r.words(count)))
        error = r.string()
        statuses = [dict(ok=bool(r.word()), error=r.string()) for _ in range(3)]
        dt, current, last = r.words(3)
        times = [r.optional() for _ in range(r.word())]
        active = [r.words(2) for _ in range(r.word())]
        motion, filtered = r.mapping(), r.mapping()
        flags, timers, hands, latch = r.words(9), r.words(4), r.words(2), r.words(5)
        grab = r.optional()
        animation_flags, relative, reset = r.words(3)
        packet = [dict(name=r.words(5), value=r.word()) for _ in range(r.word())]
        cached = []
        for _ in range(r.word()):
            cached.append(dict(name=r.words(5), kind=r.word(), status=r.word(), sequence=r.word(), times=r.words(2),
                payload=[r.optional() for _ in range(6)]))
        property_words = r.words(3)
        clock, length, transitioning = r.scalar(), r.scalar(), r.word()
        frames.append(dict(tick=tick, conditions=conditions, error=error, statuses=statuses, dt=dt, current=current, last=last,
            times=times, active=active, motion=motion, filtered=filtered, flags=flags, timers=timers, hands=hands,
            latch=latch, grab=grab, animation_flags=animation_flags, relative=relative, reset=reset, packet=packet,
            cached=cached, property=property_words, clock=clock, length=length, transitioning=transitioning))
    assert r.at == len(data)
    assert len(frames) == TICKS
    states = {f['current'] for f in frames}
    instances = {a[1] for f in frames for a in f['active']}
    assert {1, 2} <= states and len(instances) > 25, (case, states, len(instances))
    assert all(s['ok'] for f in frames for s in f['statuses'])
    assert all(f['clock']['ok'] and f['length']['ok'] for f in frames)
    assert all(f['packet'] for f in frames) and any(f['cached'] for f in frames)
    # Fixture identities/configured values only. Expected tick output still
    # comes exclusively from the unchanged original MotionHost above.
    probe_name, marker_name = attribute_name('probe'), attribute_name('Marker')
    for f in frames:
        ending = f['tick'] == 127
        marker = [a['value'] for a in f['packet'] if a['name'] == marker_name]
        attached = [a['value'] for a in f['packet'] if a['name'] == probe_name]
        assert marker and all(v == fbits(0. if ending else (case+1)*.125) for v in marker), (case, f['tick'], 'authored marker')
        expected_a = fbits(((f['tick']+case) % 11-5)*.125)
        assert attached == ([] if ending else [expected_a]), (case, f['tick'], 'actual AttachIntent emission', attached)
    assert len({f['motion']['values']['A'] for f in frames}) > 8
    assert len({f['filtered']['values']['TweakX'] for f in frames}) > 8
    assert len({f['clock']['value'] for f in frames}) > 16
    for flag in (0, 1, 2, 3, 4, 5, 6, 8):
        assert {0, 1} <= {f['flags'][flag] for f in frames}, (case, 'flag', flag)
    assert any(any(f['hands']) for f in frames) and any(not any(f['hands']) for f in frames)
    assert any(f['timers'][2] for f in frames), (case, 'manual timer never started')
    assert all(f['conditions']['IsPushOffEnabled'] == 1 and f['conditions']['IsInDebugAnimationsMode'] == 0 for f in frames)
    for tick in (127,):
        assert not frames[tick]['active'] and not any(frames[tick]['hands']), (case, 'end-all cleanup', tick)
    if case < 7:
        assert not any(f['error'] for f in frames), (case, next(f['error'] for f in frames if f['error']))
    else:
        assert any('stock gameplay producer AirDismounting is not implemented' in f['error'] for f in frames)
        assert all('Unsupported MotionGraph condition' in f['error'] for f in frames)
        assert any('requires the actual physical condition publication' in f['error'] for f in frames)
    truth = {name: sorted({f['conditions'][name] for f in frames}) for name in names}
    return dict(states=sorted(states), instances=len(instances), cached_frames=sum(bool(f['cached']) for f in frames),
        packet_frames=sum(bool(f['packet']) for f in frames), truth_values=truth), frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for marker in ('result.json', 'first-divergence.json'):
        (output/marker).unlink(missing_ok=True)
    cpp, rust = build_probes(output, args.target_dir)
    settings = output/'settings.simulation'
    settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    results, combined_truth, raw_cases = [], defaultdict(set), []
    for case in range(8):
        graph = fixture(case)
        reference, simulation = output/f'host-{case}.reference-graph', output/f'host-{case}.graph'
        reference.write_bytes(original_graph(graph))
        simulation.write_bytes(converter.encode_graph(converter.read_graph(reference)))
        inputs = corpus(case)
        (output/f'host-{case}-input.bin').write_bytes(inputs)
        expected = subprocess.check_output([str(rust), str(args.assets), str(reference)], input=inputs)
        actual = subprocess.check_output([str(cpp), str(args.metadata/'bank-0.skate'), str(args.metadata/'bank-1.skate'), str(simulation), str(settings)], input=inputs)
        # Retain exact oracle evidence even if a subsequent coverage assertion
        # rejects the fixture after byte comparison succeeds.
        (output/f'host-{case}-reference.bin').write_bytes(expected)
        (output/f'host-{case}-cpp.bin').write_bytes(actual)
        if actual != expected:
            first = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
            report = dict(passed=False, case=case, first_byte=first, reference_length=len(expected), cpp_length=len(actual),
                reference_hex=expected[max(0, first-16):first+32].hex(), cpp_hex=actual[max(0, first-16):first+32].hex())
            (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
            raise AssertionError(report)
        raw_cases.append((case, graph, expected))
    # Save every original trace before enforcing coverage so a later rejected
    # fixture can be audited completely without another runtime invocation.
    for case, graph, expected in raw_cases:
        coverage, frames = trace(expected, condition_names(graph), case)
        (output/f'host-{case}-original-trace.json').write_text(json.dumps(frames, indent=2)+'\n')
        for name, values in coverage['truth_values'].items():
            combined_truth[name].update(values)
        results.append(dict(case=case, output_bytes=len(expected), output_sha256=hashlib.sha256(expected).hexdigest(), coverage=coverage))
    for name, values in combined_truth.items():
        if name not in ('IsPushOffEnabled', 'IsInDebugAnimationsMode', 'IsArmChannelPlaying'):
            assert {0, 1} <= values, f'Original condition {name} did not execute both branches: {values}'
    assert len({r['output_sha256'] for r in results}) == 8, 'Numeric fixture inputs did not produce distinct live host traces'
    report = dict(passed=True, fixtures=8, ticks=8*TICKS, results=results, output_bytes=sum(r['output_bytes'] for r in results),
        comparison='exact original MotionHost/controller allocation/lifecycle, explicit gameplay/feet, typed AG handoff, clip parameter/advance/cache ordering, lazy and queried conditions; no tolerance',
        limitations='First MotionHost dispatch slice. Unported C++ physical/stock operation owners retain diagnostics; full actor schedule, physical producers and complete graph coverage remain pending.',
        reference_provenance='reference-provenance.json')
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
