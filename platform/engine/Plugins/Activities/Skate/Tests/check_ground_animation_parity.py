#!/usr/bin/env python3
"""Complete original GroundAnimation/GroundJump over actual physical owners.

Only the root runs the compiler/executables under its render lock. --preflight
validates the exact transport, source boundaries, units and original fixtures.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import check_footplant_parity as foot
import check_ground_runtime_parity as ground
from camera_reference_build import frozen_sources
from check_gesture_parity import PLUGIN, converter
from check_graph_parity import element, original_graph
from session_parity import REFERENCE_REVISION, digest
CODE = foot.CODE
UNITS = tuple(dict.fromkeys((*foot.UNITS, *ground.UNITS,
    'GroundJump', 'GroundAnimationSettings', 'GroundAnimationRuntime',
    'GroundAnimationBoard', 'GroundAnimationSkeleton')))
OPS = ('publish', 'authored_pose', 'toolkit', 'enter', 'advance', 'exit', 'fill',
       'clear_forces', 'append_force', 'retained_jump', 'set_drag', 'core_jump',
       'select_profile', 'reload_trajectory', 'bind_provider', 'load_settings',
       'capture_air_error', 'retained_ground')
SECTIONS = ('owner', 'settings', 'lifecycle', 'board', 'queue', 'collision')
fs, bits = foot.fs, foot.bits

def publish(n, *, jump=None, mode=None, collision=None):
    active = n % 4 >= 2 if jump is None else jump
    hippy = n % 9 == 3 if jump is None else False
    flags = ((1 << 22) if active else 0) | ((1 << 20) if n % 2 else 0)
    flags |= (1 << 13) if n % 5 == 2 else 0
    hit = n % 4 == 0 if collision is None else collision
    flags2 = ((1 << 17) if hit else 0) | ((1 << 26) if n % 3 else 0) | ((1 << 27) if n % 7 < 3 else 0)
    normal = [math.sin(n * .137) * .13, .97 + (n % 3) * .01, math.cos(n * .1731) * .071, .137]
    speed = (1.137, 2.317, 4.731, 7.31, 10.137)[n % 5]
    velocity = [.317 * math.sin(n * .137), -.137, speed, .1731]
    prepared = [0, 0, 0, .137] if n % 2 else velocity.copy()
    values = [(.00831, .016666668, .0317)[n % 3], -9.8,
              (-.731, .137, 2.317, 7.31)[n % 4], speed, speed, speed,
              (.0317, .137, .731, 2.317)[n % 4], (.1731, .731, 2.317)[n % 3],
              math.sin(n * .317) * .731, (.137, .317, .731)[n % 3],
              (-1, -.317, -0.0, 0, .317, 1)[n % 6], (.0317, .317, .731)[n % 3],
              math.sin(n * .137) * .317, (.137, .731, 1)[n % 3],
              math.sin(n * .1731) * .731, math.cos(n * .137) * .317,
              (.731, 1, 1.317)[n % 3]]
    vectors = [velocity, [2.731, 0, .317, .137], normal,
               [.137, -.035, -.317, .137], [0, -.035, 0, .317], [0, 0, 1, .1731], [0, 1, 0, .137],
               [0, 1, 0, .317], [0, 0, 1, .137], [.137, .317 + (n % 7) * .0173, -.317, .137],
               [0, 0, speed, .1731], prepared, [.137, .731, -.317, .137],
               [-.317, .0173, .071, .137] if hit else [0, 0, 0, 0]]
    raw = [0, flags, flags2, (1 << 30) if n % 4 == 1 else 0,
           0x1000 if hippy else 0, 0x800 if n % 3 == 0 else 0,
           0x10000000 if n % 7 == 4 else 0, n % 5 if mode is None else mode,
           200, 100, 100, (0, 0x10)[n % 2], (0, 1, 2, 4)[n % 4]]
    return raw + fs(values) + fs([v for vector in vectors for v in vector])

def core(n):
    flags = (1 << 22) if n % 8 else 0
    normal = [math.sin(n * .137) * .317, (-1, -.317, 0, .317, .731, 1)[n % 6], math.cos(n * .1731) * .137, .317]
    velocity = [math.sin(n * .137) * 7.31, -.731, math.cos(n * .1731) * 4.731, .137]
    prepared = [0, 0, .137, .731] if n % 2 else velocity
    vectors = [[.137, .0317, 1, .317], [0, 0, 1, .731], velocity,
               [.137, -.731, -.317, .137], [0, 1, 0, .317], normal,
               [.137, (-1, -.317, 0, .317, 1.731)[n % 5], -.317, .731], prepared]
    return [11, n % 5, flags, 0x1000 if n % 7 == 3 else 0,
            0x800 if n % 3 == 0 else 0, 0x10000000 if n % 9 == 4 else 0] + fs([
                *[v for vector in vectors for v in vector],
                (0, .137, .731, 1)[n % 4], math.sin(n * .137), math.cos(n * .1731),
                (-3.17, -9.8, -17.31)[n % 3], (0, .317, 1.137, 3.17, 7.31, 17.31)[n % 6]])

def retained_ground(n, mode=None):
    return [17] + fs([math.sin(n * .137) * .731, .317, -.137,
                     (0, .0317, .1731, .731)[n % 4], .071]) + [n % 4 if mode is None else mode] + fs([.731]) + [n % 2, (0, 1, 255)[n % 3]]

def fill(n): return [6] + [0x3e000000 + n + k for k in range(8)] + [0x71]
def mutations():
    specs = [('physics_jump', 'default', 'VerticalResponse', 'short'),
             ('physics_jump', 'default', 'VerticalResponse', 'type'),
             ('physics_jump', 'default', 'VerticalResponse', 'long')]
    for key in ('easy', 'normal', 'hardcore', 'motorized', 'test'):
        specs += [('physics_mode', key, 'Hash_BE3F74F978D777E5', 'missing_chain'),
                  ('physics_mode', key, 'JumpMinHeight', 'type'),
                  ('physics_mode', key, 'JumpMaxHeight', 'nan')]
    for name in ('JumpYScalarVsGroundNormalY', 'JumpSpeedScalarVsAngle', 'MinHeightVsSpeed', 'MaxHeightVsSpeed'):
        specs += [('physics_jump', 'default', name, 'short'), ('physics_jump', 'default', name, 'type'),
                  ('physics_jump', 'default', name, 'long')]
    for name in ('SpeedResponseMaxSpeed', 'MinScalar', 'JumpYBonusMax', 'JumpAdjustZFactor',
                 'JumpAdjustXFactor', 'AbsoluteMinHeight', 'HippyJumpMinHeight', 'HippyJumpMaxHeight'):
        specs += [('physics_jump', 'default', name, 'missing_chain'), ('physics_jump', 'default', name, 'nan')]
    return [None] + specs

def corpus():
    cases = []; records = []
    for n in range(4):
        world = foot.lifecycle.numeric.world(0 if n != 3 else 2)
        if n != 3:
            for k in range(world[0]):
                for v in range(3): world[1 + k * 18 + v * 3 + 1] = bits((-1, 0, .5)[n])
        commands = [publish(n), [1, n], [2, 1], retained_ground(n, 0), [3]]
        for k in range(96):
            index = n * 96 + k
            commands += [publish(index), [1, (n + k // 12) % 4], [2, 1], [12, index % 5, k % 5 + 1]]
            if k % 12 == 0: commands += [retained_ground(index), [3], [16]]
            commands += [[7], [10, bits(.317 + (k % 5) * .137)], [4], fill(index)]
            if k % 7 == 0: commands += [[5], fill(index + 1000)]
        # Full force-capacity domain: the source still runs every calculation
        # and retains its queue prefix when new records cannot be appended.
        commands += [publish(n, jump=False, collision=False), [1, n], [2, 1], [7]]
        commands += [[8, 0x100 + k] + fs([.137 * k, -.317, .731, .137, -.317, .731]) for k in range(24)]
        commands += [[4], [7], publish(n, jump=False, collision=True), [1, n], [2, 1], [10, bits(.731)], [4]]
        # Real absent-toolkit and invalid-mode paths occur after Skeleton writes.
        commands += [publish(n + 2), [1, n], [2, 0], [4], [2, 1], publish(n + 2, mode=9), [12, n % 5, n % 4 + 2], retained_ground(n + 100), [4]]
        for kind in (4, 5): commands += [publish(n + 1, jump=False), [1, kind], [2, 1], [4], [1, n]]
        # Actual trajectory load clears its provider. Launch/Update executes
        # unchanged and consumes real query results before the missing-owner error.
        commands += [publish(n + 2, jump=True), [1, n], [2, 1], [13], [4], [14], [4], [5]]
        # Caller-owned retained initial states cover exact Enter and selective Fill.
        for flags, active, launched in ((0, 0, 0), (1 << 22, 1, 0), (0, 1, 1), (1 << 22, 1, 1)):
            pub = publish(n, jump=False); pub[1] = flags; pub[4] = 0
            commands += [pub, [9] + fs([.137, 2.317, -.731, .1731, .731]) + [active, launched] + fs([.317, 1.731, .137, .731]), fill(2000 + n), [5], fill(3000 + n)]
        for wipeout_mode in (0, 1, 2): commands += [retained_ground(n, wipeout_mode), [3]]
        commands += [core(n * 160 + k) for k in range(160)]
        if n == 0:
            for fixture in range(len(mutations())): commands += [[15, fixture]]
            commands += [[15, 0]]
        raw = world + [len(commands)] + [v for cmd in commands for v in cmd]
        cases.append(dict(index=n, world=n, commands=commands,
                          label='real floor/empty world, stock pose, ordered forces, jump/trajectory, retained prefixes and settings'))
        records.append(struct.pack('<' + 'I' * len(raw), *raw))
    return struct.pack('<I', len(records)) + b''.join(records), cases

def extract(path, boundary): return foot.extraction(path, boundary)

def build_reference(output, target, *, compile=True):
    original, report = frozen_sources(output); observed = output / 'observed-source'
    if observed.exists(): shutil.rmtree(observed)
    shutil.copytree(original, observed); crate = observed / 'atelier-host'; host = original / 'crates/skate-host/src'
    hprefix, hmeta = extract(PLUGIN / 'Tests/Reference/handplant_observer.rs', 'pub(super) fn run(')
    lprefix, lmeta = extract(PLUGIN / 'Tests/Reference/handplant_lifecycle_observer.rs', 'pub(super) fn run(')
    aprefix, ameta = extract(PLUGIN / 'Tests/Reference/air_reckoning_observer.rs', 'fn core_input(')
    fprefix, fmeta = extract(PLUGIN / 'Tests/Reference/footplant_observer.rs', 'pub(super) fn run(')
    htail = b'\npub(super) fn shared(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime){snapshot(o,p,s)}\n}\npub(crate) fn migration_footplant_shared_snapshot(o:&mut crate::Output,p:&super::GamePhysics,s:&super::SkaterRuntime){migration::shared(o,p,s)}\n'
    atail = b'\npub(super) fn observe(o:&mut Output,a:&AirReckoning,r:&RidingOutputs){out_state(o,&a.state);for w in *r.body_spin.words(){o.word(w)}for w in r.reckoning.migration_air_reckoning_words(){o.word(w)}out_frames(o,&r.reckoning_frames);}\n}\npub(crate) fn migration_lifecycle_observe(o:&mut crate::Output,a:&AirReckoning,r:&RidingOutputs){migration::observe(o,a,r)}\n'
    ftail = b'\npub(super) fn observe(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime,f:&skate_core::player::input_phase::AirOutputFields){snapshot(o,p,s,f)}\n}\npub(crate) fn migration_ground_snapshot(o:&mut crate::Output,p:&super::GamePhysics,s:&super::SkaterRuntime,f:&skate_core::player::input_phase::AirOutputFields){migration::observe(o,p,s,f)}\n'
    observer = PLUGIN / 'Tests/Reference/ground_animation_observer.rs'
    additions = {'physics/handplant.rs': b'\n' + hprefix + lprefix + htail,
                 'physics/air_reckoning.rs': b'\n' + aprefix + atail,
                 'physics/footplant.rs': b'\n' + fprefix + ftail,
                 'physics/ground_animation.rs': b'\n' + observer.read_bytes(),
                 'physics/air_trajectory/mod.rs': b'\n' + (PLUGIN / 'Tests/Reference/footplant_trajectory_observer.rs').read_bytes(),
                 'physics.rs': b'\npub(crate) fn migration_ground_animation_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{ground_animation::migration_ground_animation_run(a,f,i,o)}\n'}
    staged = {}
    for path in sorted(host.rglob('*.rs')):
        relative = path.relative_to(host).as_posix()
        if relative in ('lib.rs', 'main.rs'): continue
        raw = path.read_bytes(); extra = additions.get(relative, b''); destination = crate / 'src' / relative
        destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(raw + extra)
        assert destination.read_bytes()[:len(raw)] == raw
        staged[relative] = dict(original_prefix_bytes=len(raw), original_prefix_sha256=digest(path),
                                append_sha256=hashlib.sha256(extra).hexdigest(), generated_sha256=digest(destination))
    core = {'crates/skate-core/src/riding/ground_orientation.rs': foot.lifecycle.air.CORE_OBSERVER.encode(),
            'crates/skate-core/src/physics/skeleton_motion.rs': b'\nimpl SkeletonMotion {pub fn migration_lifecycle_previous(&self)->f32{self.previous_board_at_y}}\n',
            'crates/skate-core/src/air/trajectory/selector.rs': b'\nimpl TrajectorySelector {pub fn migration_footplant_stage(&self)->[u32;2]{[u32::from(self.pass),u32::from(self.adjusted_on_vert)]}}\n'}
    for relative, extra in core.items():
        raw = (original / relative).read_bytes(); (observed / relative).write_bytes(raw + extra)
        assert (observed / relative).read_bytes()[:len(raw)] == raw
    template = PLUGIN / 'Tests/Reference/ground_animation_probe.rs'; shutil.copy2(template, crate / 'src/migration_probe.rs')
    cargo = crate / 'Cargo.toml'; cargo.write_text(cargo.read_text() + '''
skate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="ground-animation-reference"
path="src/migration_probe.rs"
''')
    binary = output / 'ground-animation-reference'
    if compile:
        subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2', '--manifest-path', str(cargo), '--target-dir', str(target.resolve()), '--bin', 'ground-animation-reference'], check=True)
        shutil.copy2(target.resolve() / 'release/ground-animation-reference', binary)
        report['binary_sha256'] = digest(binary)
    for relative, sha in report['original_source_sha256'].items():
        assert digest(original / relative) == sha
        raw = (original / relative).read_bytes(); assert (observed / relative).read_bytes()[:len(raw)] == raw
    for relative, row in staged.items(): assert digest(crate / 'src' / relative) == row['generated_sha256']
    report.update(staged_host_original_prefixes=staged, extracted_observer_prefixes=[hmeta, lmeta, ameta, fmeta],
        appended_core_observers={relative: dict(original_prefix_sha256=digest(original / relative), generated_sha256=digest(observed / relative), observer_sha256=hashlib.sha256(extra).hexdigest()) for relative, extra in core.items()},
        probe_sha256=digest(template), observer_sha256=digest(observer), scope='Whole original host/core prefixes remain byte-for-byte unchanged. Appended methods only supply explicit upstream caller fields and observe private owners. Complete GroundAnimation Enter/Advance/Exit/Fill and GroundJump calculate execute with original skeleton, board, world, trajectory, settings and native helpers. No numerical method or callback is replaced.')
    (output / 'reference-provenance.json').write_text(json.dumps(report, indent=2) + '\n'); return binary

def build_native(output, *, compile=True):
    snapshot = output / 'native-source'
    if snapshot.exists(): shutil.rmtree(snapshot)
    snapshot.mkdir(); hashes = {}
    for path in [*sorted(CODE.glob('*.h')), *[CODE / (u + '.cpp') for u in UNITS]]:
        shutil.copy2(path, snapshot / path.name); hashes[path.name] = digest(snapshot / path.name)
    for name in ('handplant_probe.cpp', 'ground_animation_probe.cpp'):
        path = PLUGIN / 'Tests/Native' / name; shutil.copy2(path, snapshot / name); hashes[name] = digest(snapshot / name)
    hprefix, hmeta = extract(PLUGIN / 'Tests/Native/handplant_lifecycle_probe.cpp', 'int main(')
    fprefix, fmeta = extract(PLUGIN / 'Tests/Native/footplant_probe.cpp', 'KnownAirFootplantInput Packet(')
    (snapshot / 'handplant_lifecycle_helpers.inc').write_bytes(hprefix)
    (snapshot / 'ground_animation_helpers.inc').write_bytes(fprefix + b'\n} // namespace\n')
    binary = output / 'ground-animation-native'
    if compile:
        subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot), *[str(snapshot / (u + '.cpp')) for u in UNITS], str(snapshot / 'ground_animation_probe.cpp'), '-o', str(binary)], check=True)
    for name, sha in hashes.items(): assert digest(snapshot / name) == sha
    (output / 'native-provenance.json').write_text(json.dumps(dict(immutable_native_sources=hashes, extracted_helper_prefixes=[hmeta, fmeta], units=UNITS), indent=2) + '\n'); return binary

class Reader(foot.Reader):
    def ground(self):
        assert self.word() == len(SECTIONS); result = {}; self.ground_spans = {}
        for name in SECTIONS:
            size = self.word(); at = self.at; result[name] = self.take(size); self.ground_spans[name] = [at, self.at]
        assert len(result['owner']) == 11 and len(result['settings']) == 119
        assert len(result['lifecycle']) == 11 and len(result['board']) == 34
        assert len(result['queue']) == 1 + 7 * result['queue'][0] and result['queue'][0] <= 21
        assert len(result['collision']) == (13 if result['collision'][0] else 1)
        return result

def decode(raw, cases):
    r = Reader(raw); assert r.word() == len(cases); frames = []
    for case in cases:
        case['first_output_word'] = r.at; assert r.word() == len(case['commands']); g = r.ground(); f = r.foot(); s = r.snapshot(); rows = []
        for cmd in case['commands']:
            at = r.at; assert r.word() == cmd[0]; error = r.status(); extra = r.take(r.word()); ng = r.ground(); gs = r.ground_spans.copy(); nf = r.foot(); fs_ = r.foot_spans.copy(); ns = r.snapshot()
            rows.append(dict(operation=cmd[0], error=error, extra=extra, ground=ng, prior=g, foot=nf, shared=ns, shared_prior=s, first_word=at, last_word=r.at, spans={**{'ground.' + n: span for n, span in gs.items()}, **{'foot.' + n: span for n, span in fs_.items()}, **r.spans})); g, f, s = ng, nf, ns
        case['last_output_word'] = r.at; frames.append(rows)
    assert r.at == len(r.words); return frames

def queue(raw): return [raw[1 + 7 * k:8 + 7 * k] for k in range(raw[0])]
def float_(word): return struct.unpack('<f', struct.pack('<I', word))[0]

def coverage(frames, cases):
    counts = Counter(); paths = Counter(); pure = set(); jumps = set(); roots = set(); steering = set(); launch_packets = set(); board_velocities = set(); physics_modes = set(); body_fourth = set(); selected_hits = set(); selections = Counter(); short_poses = Counter(); misses = 0; partial = 0; settings_failures = []
    specs = mutations()
    for rows, case in zip(frames, cases):
        processed = None; pose_kind = None
        for row, cmd in zip(rows, case['commands']):
            op = cmd[0]; counts[OPS[op]] += 1; g = row['ground']; old = row['prior']; owner = g['owner']; before = old['owner']; life = g['lifecycle']; board = g['board']; q = queue(g['queue']); prior_queue = queue(old['queue'])
            if op == 0: processed = cmd
            if op == 1: pose_kind = cmd[1]
            if op == 3:
                assert row['error'] is None and owner[:6] == before[:6]
                assert owner[6:] == [0] * 5 and life[5:7] == [1, 1]
                assert life[8] == 1 and life[9] == (old['lifecycle'][9] if old['lifecycle'][8] == 1 else 0)
                paths['enter_retains_jump_and_resets_launch'] += 1
            if op == 4:
                roots.add(tuple(row['shared']['roots'])); steering.add(tuple(life[:5])); physics_modes.add(processed[7])
                if row['error']:
                    assert owner[6] == (1 if row['error'] == 'Trajectory static grind provider was not registered' else 0)
                    assert q == prior_queue
                    partial += row['shared']['reckoning'] != row['shared_prior']['reckoning'] or row['shared']['pose_drives'] != row['shared_prior']['pose_drives']
                    if row['error'] == 'GroundAnimation requires current BoardToolkit':
                        assert owner[:6] == before[:6] and life[:5] == old['lifecycle'][:5] and board[:3] == old['board'][:3]; paths['missing_toolkit'] += 1
                    elif row['error'] == 'Invalid GroundAnimation physics mode 9':
                        assert owner[:6] == before[:6] and life[:5] != old['lifecycle'][:5]; assert life[10] == 1; paths['invalid_mode'] += 1
                    elif row['error'] == 'Trajectory static grind provider was not registered':
                        assert owner[5:7] == [1, 1] and owner[7:] == before[7:] and board[6:13] == [0] * 7
                        a = foot.trajectory_observation(row['foot']['trajectory']); assert a['provider'] == 0 and a['launch'] is not None; paths['real_launch_missing_provider'] += 1
                    else:
                        assert row['error'] == 'IK original joint is absent from the current pose' and pose_kind in (4, 5)
                        assert {name for name in row['shared'] if row['shared'][name] != row['shared_prior'][name]} == {'reckoning', 'roots', 'bodies_blend', 'physical_record', 'publication'}
                        assert q == prior_queue
                        short_poses[pose_kind] += 1; paths['short_hierarchy'] += 1
                elif owner[5]:
                    assert owner[6] == 1 and q == prior_queue and board[6:13] == [0] * 7
                    assert all(board[13 + k * 3:16 + k * 3] == owner[:3] for k in range(7))
                    a = foot.trajectory_observation(row['foot']['trajectory']); assert a['launch'] is not None
                    assert a['launch'][67] == 1 and owner[7:11] == a['launch'][32:36]
                    if a['selection'] is not None:
                        selection = a['selection']
                        if a['flags'][3]:
                            # complete_batch retains Some(selection) even for
                            # QueryResult::miss(), then publishes valid=false.
                            assert selection[13] == bits(-1.0) and selection[30] == 0xffffffff and a['flags'][1] == 0
                            selections['completed_miss'] += 1
                        else:
                            assert selection[30] != 0xffffffff and float_(selection[13]) >= 0
                            selections['admitted_contact'] += 1
                            selected_hits.add(tuple(selection))
                    else:
                        assert a['flags'][0] == 1 and a['flags'][1] == 0 and a['flags'][3] == 0 and a['flags'][7] == 0xffffffff
                        selections['pending'] += 1
                    misses += int(a['flags'][3])
                    if case['world'] == 3:
                        if a['selection'] is not None:
                            assert a['flags'][3] == 1 and a['selection'][13] == bits(-1.0)
                    launch_packets.add(tuple(a['launch'])); board_velocities.add(tuple(board[13:])); jumps.add(tuple(owner[:4])); body_fourth.add(owner[3]); paths['real_launch_update'] += 1
                else:
                    assert owner[:6] == [0] * 6 and owner[6] == 0
                    if len(prior_queue) == 21:
                        assert q == prior_queue; paths['queue_capacity_retained'] += 1
                    else:
                        tags = [v[0] for v in q[len(prior_queue):]]
                        if tags == [15]:
                            assert board[6:13] == old['board'][6:13]; paths['collision_preserves_drag'] += 1
                        else:
                            assert tags == [4, 5, 1, 2], tags
                            assert len(set(board[6:13])) == 1; paths['ordered_nonjump_forces'] += 1
            if op == 5:
                assert row['error'] is None and owner[:6] == [0] * 6 and owner[6:] == before[6:]
                assert board[:3] == board[3:6] and board[6:13] == [0] * 7
                assert q == prior_queue; paths['exit_retains_launch'] += 1
            if op == 6:
                assert row['error'] is None and len(row['extra']) == 9
                expected = cmd[1:]
                flags = row['shared']['publication'][0]
                if flags & (1 << 22):
                    expected[:4] = [bits(float_(owner[k]) - float_(processed[30 + k])) for k in range(4)]
                    paths['fill_jump_delta'] += 1
                else: paths['fill_preserves_delta'] += 1
                if owner[6]: expected[4:8] = owner[7:11]; expected[8] = 1; paths['fill_launch'] += 1
                else: paths['fill_preserves_launch'] += 1
                assert row['extra'] == expected
            if op == 8:
                assert q == (prior_queue + [cmd[1:]] if len(prior_queue) < 21 else prior_queue)
            if op == 10:
                drag = bits(float_(cmd[1]) * float_(0x426fffff)); assert board[6:13] == [drag] * 7
            if op == 11:
                assert row['error'] is None and len(row['extra']) == 6
                active = bool(cmd[2] & (1 << 22) or cmd[3] & 0x1000)
                assert row['extra'][5] == int(active) and row['extra'][4] == 0
                if not active: assert row['extra'] == [0] * 6; paths['core_inactive_gate'] += 1
                else: pure.add(tuple(row['extra'])); paths['core_active'] += 1
                assert g == old, 'pure calculate must not change live GroundAnimation state'
            if op == 15:
                category, key, name, replacement = specs[cmd[1]] or ('', '', '', '')
                failure = bool(replacement) and not (replacement == 'type' and category == 'physics_jump')
                assert bool(row['error']) == failure, (cmd[1], specs[cmd[1]], row['error'])
                if failure:
                    assert g['settings'] == old['settings']; settings_failures.append(row['error'])
                else: paths['settings_success_ignores_graph_type'] += 1
    assert paths['real_launch_update'] > 80 and paths['ordered_nonjump_forces'] > 80
    assert paths['collision_preserves_drag'] > 16 and paths['queue_capacity_retained'] == 4
    assert paths['missing_toolkit'] == paths['invalid_mode'] == paths['real_launch_missing_provider'] == 4
    assert paths['short_hierarchy'] == 8 and partial >= 12
    assert short_poses == {4: 4, 5: 4}
    assert selections == {'admitted_contact': 131, 'completed_miss': 83, 'pending': 4}
    assert paths['fill_jump_delta'] > 80 and paths['fill_preserves_delta'] > 80
    assert paths['fill_launch'] > 80 and paths['fill_preserves_launch'] > 80
    assert len(pure) > 128 and len(jumps) > 64 and len(roots) > 128 and len(steering) > 32
    assert len(launch_packets) > 64 and len(board_velocities) > 64 and len(body_fourth) > 8
    assert len(selected_hits) > 8 and misses > 16
    assert physics_modes == {0, 1, 2, 3, 4, 9}
    assert len(settings_failures) == sum(s is not None and not (s[3] == 'type' and s[0] == 'physics_jump') for s in specs)
    return dict(operations=dict(counts),source_paths=dict(paths),partial_failures=partial,
                pure_jump_variants=len(pure),live_jump_variants=len(jumps),root_variants=len(roots),
                steering_variants=len(steering),launch_packet_variants=len(launch_packets),
                board_velocity_variants=len(board_velocities),jump_fourth_variants=len(body_fourth),
                physics_modes=sorted(physics_modes),trajectory_selections=dict(selections),
                short_pose_failures=dict(short_poses),settings_failures=settings_failures)

def prepare(assets, output):
    fixtures = output / 'fixtures'; fixtures.mkdir(exist_ok=True)
    source = assets / 'private/stock/skater-collections.json'; stock = json.loads(source.read_text())
    (fixtures / 'settings.native').write_bytes(converter.encode_settings(source))
    skeletons = assets / 'private/stock/physics-skeletons.json'
    (fixtures / 'physics.native').write_bytes(converter.encode_physics_skeletons(skeletons))
    for kind in ('action', 'motion'): (fixtures / f'actor.{kind}.reference').write_bytes(original_graph(element('state', 'idle')))
    fixture_proof = []
    for index, spec in enumerate(mutations()):
        data = copy.deepcopy(stock)
        if spec is not None:
            category, key, name, replacement = spec
            record = next(r for r in data['collections'] if r['class'] == category and r['key'] == key)
            current = record; inherited = None; target = None
            while True:
                target = next((n for n in current['fields'] if converter.name_id(n) == converter.name_id(name)), None)
                if target is not None: inherited = copy.deepcopy(current['fields'][target]); break
                assert current.get('parent'), (spec, 'stock field absent in inheritance chain')
                current = next(r for r in data['collections'] if r['class'] == category and r['key'] == current['parent'])
            if replacement == 'missing_chain':
                current = record
                while True:
                    for field in list(current['fields']):
                        if converter.name_id(field) == converter.name_id(name): current['fields'].pop(field)
                    if not current.get('parent'): break
                    current = next(r for r in data['collections'] if r['class'] == category and r['key'] == current['parent'])
            else:
                record['fields'][target] = inherited
                if replacement == 'type': record['fields'][target]['type'] = 'EA::Reflection::String'
                elif replacement == 'nan': record['fields'][target]['data'] = '7fc00000'
                elif replacement == 'long': record['fields'][target]['data'] += '00000000'
                elif replacement == 'short':
                    raw = record['fields'][target]['data']; assert len(raw) >= 8 and len(raw) % 8 == 0
                    record['fields'][target]['data'] = raw[:-8]
                else: raise AssertionError(spec)
        folder = fixtures / f'load-{index}'; original = folder / 'private/stock/skater-collections.json'
        original.parent.mkdir(parents=True, exist_ok=True); original.write_text(json.dumps(data))
        native = folder / 'settings.native'; native.write_bytes(converter.encode_settings(original))
        fixture_proof.append(dict(index=index, mutation=spec, original_sha256=digest(original), native_sha256=digest(native)))
    (fixtures / 'fixture-provenance.json').write_text(json.dumps(fixture_proof, indent=2) + '\n')
    return fixtures, json.loads(skeletons.read_text())['source_sha256']

def preflight(raw, cases):
    words = struct.unpack('<' + 'I' * (len(raw) // 4), raw); at = 1; ranges = []
    assert words[0] == len(cases)
    lengths = (86, 2, 2, 1, 1, 1, 10, 1, 8, 12, 2, 43, 3, 1, 1, 2, 1, 10)
    for case in cases:
        start = at * 4; triangles = words[at]; at += 1 + 18 * triangles
        assert words[at] == len(case['commands']); at += 1
        for cmd in case['commands']:
            assert len(cmd) == lengths[cmd[0]], (case['index'], cmd[0], len(cmd), lengths[cmd[0]])
            assert list(words[at:at + len(cmd)]) == cmd; at += len(cmd)
        ranges.append((start, at * 4))
    assert at == len(words)
    for unit in UNITS: assert (CODE / (unit + '.cpp')).is_file(), unit
    for path, boundary in (('Tests/Reference/handplant_observer.rs', 'pub(super) fn run('),
        ('Tests/Reference/handplant_lifecycle_observer.rs', 'pub(super) fn run('),
        ('Tests/Reference/air_reckoning_observer.rs', 'fn core_input('),
        ('Tests/Reference/footplant_observer.rs', 'pub(super) fn run('),
        ('Tests/Native/handplant_lifecycle_probe.cpp', 'int main('),
        ('Tests/Native/footplant_probe.cpp', 'KnownAirFootplantInput Packet(')):
        extract(PLUGIN / path, boundary)
    return ranges

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('assets', 'samples', 'output', 'target-dir'): p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--preflight', action='store_true')
    p.add_argument('--reference-case-runner', action='store_true')
    p.add_argument('--reference-workers', type=int, choices=(1, 2, 3, 4), default=1)
    a = p.parse_args()
    if not a.reference_case_runner and a.reference_workers != 1: p.error('--reference-workers requires --reference-case-runner')
    output = a.output.resolve(); output.mkdir(parents=True, exist_ok=True); inputs, cases = corpus(); ranges = preflight(inputs, cases)
    (output / 'input.bin').write_bytes(inputs); (output / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    fixtures, identity = prepare(a.assets.resolve(), output)
    if a.preflight:
        build_reference(output / 'reference', a.target_dir, compile=False); build_native(output, compile=False)
        print(json.dumps(dict(cases=len(cases), commands=sum(len(c['commands']) for c in cases), input_bytes=len(inputs), settings_fixtures=len(mutations()), units=len(UNITS), input_sha256=hashlib.sha256(inputs).hexdigest()), indent=2)); return
    reference = build_reference(output / 'reference', a.target_dir); native = build_native(output)
    if a.reference_case_runner:
        from reference_case_runner import run_reference_cases
        expected = run_reference_cases(reference, [a.assets.resolve(), fixtures], inputs, ranges,
            output / 'reference-cases', workers=a.reference_workers,
            validate_output=lambda index, raw: decode(raw, [copy.deepcopy(cases[index])]))
    else: expected = subprocess.check_output([str(reference), str(a.assets.resolve()), str(fixtures)], input=inputs)
    actual = subprocess.check_output([str(native), str(fixtures / 'settings.native'), str(fixtures / 'physics.native'), str(a.samples.resolve() / 'native/rig.skate'), identity, str(a.assets.resolve()), str(fixtures)], input=inputs)
    (output / 'reference.bin').write_bytes(expected); (output / 'native.bin').write_bytes(actual); frames = decode(expected, cases)
    if expected != actual:
        at = next((k for k, (x, y) in enumerate(zip(expected, actual)) if x != y), min(len(expected), len(actual))); word = at // 4
        case = next((c for c in cases if c['first_output_word'] <= word < c['last_output_word']), None)
        row = next((r for rows in frames for r in rows if r['first_word'] <= word < r['last_word']), None)
        section = next(((name, word - span[0]) for name, span in (row['spans'].items() if row else []) if span[0] <= word < span[1]), None)
        failure = dict(byte=at, reference_bytes=len(expected), native_bytes=len(actual), case=case['index'] if case else None,
                       operation=row['operation'] if row else 'initial', section=section, reference_hex=expected[max(0, at - 16):at + 32].hex(), native_hex=actual[max(0, at - 16):at + 32].hex())
        (output / 'first-divergence.json').write_text(json.dumps(failure, indent=2) + '\n'); raise AssertionError(failure)
    result = dict(passed=True, reference_revision=REFERENCE_REVISION, cases=len(cases), commands=sum(len(c['commands']) for c in cases), bytes=len(expected), sha256=hashlib.sha256(expected).hexdigest(), input_sha256=hashlib.sha256(inputs).hexdigest(), settings_fixtures=len(mutations()), coverage=coverage(frames, cases),
        scope='Complete GroundJump and GroundAnimation settings, Fill/Enter/Advance/Exit, actual retained Ground steering/force collision, all seven board velocities/drag, animated Skeleton/FootIK/SkeletonAir updates and real trajectory Launch/Update.',
        boundaries='Processed physical fields, animation attributes, authored engine triangles, initial retained owner values and stock physics-mode/surface selections are explicit caller inputs. The real GamePhysics and SkaterRuntime constructors run separately for every original case; no constructors or completed outputs are reused. Terrain queries and selector results are computed by actual original/native producers with a genuine empty StaticProvider on both sides. Full stock grind admission and global phase/session scheduling remain separate. No callback, completed hit/trajectory/up, pose or numerical helper is replaced. Info logging is not asserted.')
    if a.reference_case_runner: result['reference_execution'] = dict(strategy='exact independent outer cases, original constructors per case', workers=a.reference_workers, worker_limit_bytes=2 * 1024**3, report='reference-cases/result.json')
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n'); print(json.dumps(result, indent=2))
if __name__ == '__main__': main()
