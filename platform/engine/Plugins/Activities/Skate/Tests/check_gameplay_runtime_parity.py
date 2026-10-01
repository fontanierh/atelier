#!/usr/bin/env python3
"""Whole original fixed gameplay frame versus the sole native owning runtime.

Only the root coordinator compiles or executes through the render guard.
--preflight stages immutable sources, read-only observers and fixed inputs.
The only input boundary is published action18/controller availability plus
actual Session tuning, launch, travel and customization APIs. No completed
physical, graph, contact, pose, state or scoring publication is transported.
"""
import argparse
from collections import Counter, OrderedDict, defaultdict
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_render_pose_runtime_parity as render
import camera_probe_schema as camera_schema
import player_input_protocol as player_schema
import check_scoring_runtime_parity as scoring
from session_parity import REFERENCE_REVISION, digest
from check_animation_trees_parity import source_at_reference

PLUGIN, CODE, TESTS = render.PLUGIN, render.CODE, render.TESTS
DEPENDENCIES = (
    'animation_phase_runtime', 'biped_runtime', 'landing_on_deck_runtime',
    'grind_runtime', 'wipeout_physical_runtime', 'player_teleport_runtime',
    'player_state_publication', 'state_conditioning_runtime', 'boneless_runtime',
    'climbing_runtime', 'ground_phase', 'air_phase_runtime', 'slide_phase_runtime',
    'camera_output', 'player_input_host_phase', 'scoring_runtime',
)
OWN_UNITS = ('GameplayRuntime', 'GameplayResources', 'GameplayFrameRuntime',
             'PlayerPostPhysicsPhase', 'PlayerStateCoordinator',
             'PlayerStatePreState', 'PlayerStatePhases', 'PlayerPostInput',
             'PlayerStatePostInputRuntime', 'PlayerInputHostPhase',
             'SimulationClock', 'PlayerControls', 'GestureInputPublication',
             'Gestures', 'RespawnRuntime', 'RespawnHistory', 'PlayerSceneProbe')


def units():
    out = list(render.UNITS)
    for name in DEPENDENCIES:
        module = importlib.import_module('check_' + name + '_parity')
        out.extend(module.UNITS)
    out.extend(OWN_UNITS)
    out = tuple(dict.fromkeys(out))
    for name in out:
        assert (CODE / (name + '.cpp')).is_file(), name
    return out


UNITS = units()
SECTIONS = ('physical', 'player', 'publication', 'processed', 'state',
            'controls', 'metadata', 'camera', 'scoring')
LENGTHS = {0: 22, 1: 17, 2: 4, 3: 5, 4: 3, 5: 2}


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def fs(values):
    return [bits(value) for value in values]


def flatten(rows):
    return [word for row in rows for word in row]


def function(text, marker):
    """Balanced exact extraction; never regex-copy numerical implementation."""
    start = text.index(marker)
    opening = text.index('{', start)
    depth = 0
    for at in range(opening, len(text)):
        if text[at] == '{':
            depth += 1
        elif text[at] == '}':
            depth -= 1
            if depth == 0:
                return text[start:at + 1]
    raise AssertionError(marker)


def extraction(path, marker, *, end=False):
    raw = path.read_bytes()
    position = raw.index(marker.encode())
    selected = raw[position:] if end else raw[:position]
    begin, finish = (position, len(raw)) if end else (0, position)
    assert raw[begin:finish] == selected
    return selected, dict(file=path.relative_to(PLUGIN).as_posix(),
        full_sha256=digest(path), begin_byte=begin, end_byte=finish,
        extracted_sha256=hashlib.sha256(selected).hexdigest())


def player_observers():
    all_defs, sources = player_schema.declarations()
    defs = OrderedDict()

    def keep(name):
        if name in defs:
            return
        for _, kind in all_defs[name]:
            while player_schema.array(kind) or player_schema.option(kind):
                kind = (player_schema.array(kind)[0] if player_schema.array(kind)
                        else player_schema.option(kind))
            if kind in all_defs:
                keep(kind)
        defs[name] = all_defs[name]

    for name in ('PlayerInputState', 'PhysicalPlayerInput', 'ProcessedPhysicsInput'):
        keep(name)
    cpp, rust = [], [
        'use skate_core::player::input_phase::*;',
        'use skate_core::animation::output::actor_packet::*;',
        'use skate_core::animation::output::attributes::AttributeName;']
    for name in defs:
        cpp.append(f'void Observe(Output&,const {name}&);')
    for name, fields in defs.items():
        cpp.append(f'void Observe(Output& o,const {name}& s){{' + ''.join(
            player_schema.observe_expr(kind, 's.' + field, 'cpp')
            for field, kind in fields) + '}')
        rust.append(f'fn observe_{name}(o:&mut Output,s:&{player_schema.rust_kind(name)}){{' + ''.join(
            player_schema.observe_expr(kind, 's.' + field, 'rust')
            for field, kind in fields) + '}')
    return '\n'.join(cpp), '\n'.join(rust), dict(
        declaration_source_sha256={name: hashlib.sha256(raw.encode()).hexdigest()
                                   for name, raw in sources.items()},
        declarations=defs,
        boundary='Observation-only declaration traversal; no generated readers or producer methods.')


def sections():
    path = TESTS / 'Reference/gameplay_runtime_observer.rs'
    raw = path.read_text()
    parts = re.split(r'^// @SECTION (.+)$', raw, flags=re.M)
    assert len(parts) % 2 == 1 and len(parts) > 1
    out = dict(zip(parts[1::2], parts[2::2]))
    assert len(out) == len(parts[1::2])
    return out


def build_reference(output, target, *, compile=True):
    # The bounded render builder already stages the entire original host and
    # core, including only immutable read accessors for physical histories.
    render.build_reference(output, target, compile=False)
    source = output / 'reference-source'
    if not source.is_dir():
        source = output / 'original-source'
    observed = output / 'observed-source'
    crate = observed / 'atelier-host'
    report = json.loads((output / 'reference-provenance.json').read_text())
    extracts = []
    additions = defaultdict(str)
    for rel, extra in sections().items():
        additions['crates/skate-host/src/' + rel] += extra

    hp, item = extraction(TESTS / 'Reference/handplant_observer.rs', 'pub(super) fn run(')
    extracts.append(item)
    lp, item = extraction(TESTS / 'Reference/handplant_lifecycle_observer.rs', 'pub(super) fn run(')
    extracts.append(item)
    rp, item = extraction(TESTS / 'Reference/render_pose_runtime_observer.rs', 'pub(super)fn run(')
    extracts.append(item)
    # Preserve complete physical observation bodies. The old operation driver
    # is not used; this wrapper reads the actual whole-session owners.
    hp_path = crate / 'src/physics/handplant.rs'
    original = source / 'crates/skate-host/src/physics/handplant.rs'
    hp_extra = b'\n' + hp + lp + rp + b'''
pub(super)fn gameplay_physical(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime){render_snapshot(o,p,s)}
}
pub(crate)fn migration_gameplay_physical(o:&mut crate::Output,p:&GamePhysics,s:&SkaterRuntime){migration::gameplay_physical(o,p,s)}
'''
    hp_path.write_bytes(original.read_bytes() + hp_extra)

    # Restaging only the renderer's read-only Handplant prefix drops its old
    # driver. Remove that driver's unused appended entry from the parent too;
    # the complete original physics.rs prefix remains byte-for-byte intact.
    physics_path = crate / 'src/physics.rs'
    physics_raw = physics_path.read_bytes()
    old_driver = function(physics_raw.decode(), 'pub(crate)fn migration_render_pose_run(').encode()
    driver_at = physics_raw.index(old_driver)
    assert driver_at >= (source / 'crates/skate-host/src/physics.rs').stat().st_size
    assert physics_raw.count(old_driver) == 1
    physics_path.write_bytes(physics_raw[:driver_at] + physics_raw[driver_at + len(old_driver):])
    removed_driver = dict(file='crates/skate-host/src/physics.rs', begin_byte=driver_at,
        end_byte=driver_at + len(old_driver), removed_sha256=hashlib.sha256(old_driver).hexdigest(),
        scope='Unused prior renderer test entry only; complete original prefix and all read-only observers preserved.')

    values = camera_schema.schemas(lambda rel: (source / rel).read_text())
    for value in values.values():
        additions[value['source']] += camera_schema.rust_observe(
            value, host=value['source'].startswith('crates/skate-host/'))
    for name in ('Frame', 'ActiveBehavior', 'Controller'):
        rel = 'crates/skate-core/src/graph/controller.rs'
        value = camera_schema.declaration((source / rel).read_text(), name)
        additions[rel] += camera_schema.rust_observe(value)
    additions['crates/skate-core/src/lib.rs'] += '\npub mod migration_camera_observer;\n'
    (observed / 'crates/skate-core/src/migration_camera_observer.rs').write_text(camera_schema.RUST_OBSERVER)
    additions['crates/skate-host/src/camera/graph.rs'] += '''
impl CameraGraph{pub(super)fn migration_observe(&self,o:&mut Vec<u8>){use skate_core::migration_camera_observer::Observe;self.controller.observe(o);self.slow_motion.observe(o);}}
'''
    additions['crates/skate-host/src/camera/shot_data.rs'] += '''
impl skate_core::migration_camera_observer::Observe for StockShots{fn observe(&self,o:&mut Vec<u8>){skate_core::migration_camera_observer::Observe::observe(&self.0,o)}}
'''
    camera_path = TESTS / 'Reference/camera_runtime_observer.rs'
    camera_method = function(camera_path.read_text(), 'fn observe_runtime(')
    extracts.append(dict(file=camera_path.relative_to(PLUGIN).as_posix(),
        full_sha256=digest(camera_path), method_sha256=hashlib.sha256(camera_method.encode()).hexdigest(),
        exact_boundary='balanced fn observe_runtime'))
    additions['crates/skate-host/src/camera/runtime.rs'] += '''
use skate_core::migration_camera_observer::Observe;
''' + camera_method + '''
impl CameraRuntime{pub(crate)fn migration_gameplay_observe(&self,o:&mut Vec<u8>,log:&crate::LogSink){observe_runtime(self,o,log)}}
'''
    additions['crates/skate-core/src/graph/intents.rs'] += '''
impl IntentMap{pub fn migration_gameplay_observe(&self,o:&mut Vec<u32>){o.push(self.values.len()as u32);for (key,value)in &self.values{o.extend(key);o.push(value.to_bits())}}}
'''
    additions['crates/skate-core/src/physics/centre_of_mass_filter.rs'] += '''
impl CentreOfMassFilter{pub fn migration_gameplay_words(&self)->[u32;17]{let mut o=[0;17];for (i,v)in[self.velocity,self.position,self.position_velocity,self.accumulated_error].into_iter().enumerate(){o[i*4..i*4+4].copy_from_slice(&v.map(f32::to_bits))}o[16]=self.position_valid as u32;o}}
'''
    additions['crates/skate-core/src/physics/filtered_state.rs'] += '''
fn migration_gameplay_grind(v:GrindState,o:&mut Vec<u32>){o.extend([v.kind as u32,v.scorable_id as u32]);o.extend(v.name.0);o.extend(v.scoring_name.0);o.extend([v.on_front as u32,v.crouch.to_bits(),v.pathed_guid as u32,(v.pathed_guid>>32)as u32,v.local_guid as u32,(v.local_guid>>32)as u32]);}
impl FilteredState{pub fn migration_gameplay_observe(&self,o:&mut Vec<u32>){o.extend([self.category as u32,self.previous_category as u32,self.previous_physics_state as u32,self.air_count as u32,self.nonspecific_count as u32,self.nonspecific_collision_free_count as u32,self.nonspecific_collision_count as u32,self.frames_since_ground_stairs as u32,self.must_change as u32]);migration_gameplay_grind(self.cached_grind,o)}}
impl FilteredStateOutput{pub fn migration_gameplay_observe(&self,o:&mut Vec<u32>){o.extend([self.category as u32,self.previous_category as u32,self.grinding as u32]);migration_gameplay_grind(self.grind,o);o.push(self.last_grind_distance.to_bits());}}
'''
    additions[scoring.CORE] += scoring.OBSERVER.decode()
    score_path = TESTS / 'Reference/scoring_runtime_probe.rs'
    score_method = function(score_path.read_text(), ' pub(super) fn observe(')
    additions[scoring.HOST] += '\n' + score_method + '\n'
    extracts.append(dict(file=score_path.relative_to(PLUGIN).as_posix(),full_sha256=digest(score_path),
        method_sha256=hashlib.sha256(score_method.encode()).hexdigest(),exact_boundary='balanced pub(super) fn observe'))

    for rel, extra in additions.items():
        path = (crate / 'src' / rel.removeprefix('crates/skate-host/src/')
                if rel.startswith('crates/skate-host/src/') else observed / rel)
        path.write_bytes(path.read_bytes() + extra.encode())
    _, protocol, protocol_report = player_observers()
    (crate / 'src/gameplay_player_observers.inc').write_text(protocol)
    template = TESTS / 'Reference/gameplay_runtime_probe.rs'
    shutil.copy2(template, crate / 'src/migration_probe.rs')
    cargo = crate / 'Cargo.toml'
    text = cargo.read_text().replace('name="render-pose-runtime-reference"', 'name="gameplay-runtime-reference"')
    assert text.count('name="gameplay-runtime-reference"') == 1
    # The observation sink is the same one proven by the original camera test.
    text = text.replace('[dependencies]', '[dependencies]\ntracing-subscriber={version="0.3",features=["fmt"]}')
    cargo.write_text(text)

    prefix_rows = {}
    for rel, sha in report['original_source_sha256'].items():
        original = source / rel
        assert digest(original) == sha
        path = (crate / 'src' / rel.removeprefix('crates/skate-host/src/')
                if rel.startswith('crates/skate-host/src/') else observed / rel)
        if rel.startswith('crates/skate-host/src/') and rel.endswith(('/lib.rs', '/main.rs')):
            continue
        assert path.read_bytes()[:original.stat().st_size] == original.read_bytes(), rel
        if digest(path) != sha:
            prefix_rows[rel] = dict(original_prefix_bytes=original.stat().st_size,
                original_sha256=sha, appended_sha256=hashlib.sha256(path.read_bytes()[original.stat().st_size:]).hexdigest(),
                generated_sha256=digest(path))
    binary = output / 'gameplay-runtime-reference'
    if compile:
        subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2',
            '--manifest-path', str(cargo), '--target-dir', str(target.resolve()),
            '--bin', 'gameplay-runtime-reference'], check=True)
        shutil.copy2(target.resolve() / 'release/gameplay-runtime-reference', binary)
    report.update(whole_gameplay_appended_observers=prefix_rows, extracted_observer_bodies=extracts,
        removed_unused_test_driver=removed_driver,
        player_protocol=protocol_report, camera_declarations=values,
        whole_gameplay_probe_sha256=digest(template),
        whole_gameplay_observer_sha256=digest(TESTS / 'Reference/gameplay_runtime_observer.rs'),
        binary_sha256=digest(binary) if compile else None,
        scope='Complete unchanged GameAssets, StockGraphs, Flat GamePhysics, easy SkaterRuntime/controls/camera constructors and frame::advance. Same live Session owners for unchanged tune/launch. Appends only packet transport/read-only accessors; no original prefix or numerical method is edited.')
    (output / 'reference-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    return binary


def build_native(output, *, compile=True):
    snapshot = output / 'native-source'
    if snapshot.exists():
        shutil.rmtree(snapshot)
    snapshot.mkdir(parents=True)
    hashes = {}
    files = [*sorted(CODE.glob('*.h')), *[CODE / (n + '.cpp') for n in UNITS],
             TESTS / 'Native/handplant_probe.cpp', TESTS / 'Native/gameplay_runtime_probe.cpp']
    for path in files:
        shutil.copy2(path, snapshot / path.name)
        hashes[path.name] = digest(snapshot / path.name)
    extracts = []
    prefix, item = extraction(TESTS / 'Native/handplant_lifecycle_probe.cpp', 'int main(')
    (snapshot / 'render_pose_owner_helpers.inc').write_bytes(prefix)
    extracts.append(item)
    prefix, item = extraction(TESTS / 'Native/render_pose_runtime_probe.cpp', 'int main(')
    (snapshot / 'gameplay_render_helpers.inc').write_bytes(prefix)
    extracts.append(item)
    cpp, _, player_report = player_observers()
    (snapshot / 'gameplay_player_observers.inc').write_text(cpp)
    camera_prefix, item = extraction(TESTS / 'Native/camera_runtime_probe.cpp', 'struct MovingPublication')
    extracts.append(item)
    values = camera_schema.schemas(source_at_reference)
    raw = camera_prefix.decode()
    includes = '\n'.join(line for line in raw.splitlines() if line.startswith('#include'))
    body = '\n'.join(line for line in raw.splitlines() if not line.startswith('#include'))
    # Same generic declarations/templates as the proven camera probe. They
    # must precede generated field observers for array/optional overload lookup.
    camera_observers = camera_schema.cpp_observers(values).replace(
        '// @CPP_GENERIC_WRITERS@', camera_schema.CPP_GENERIC_WRITERS)
    assert '// @CPP_GENERIC_WRITERS@' not in camera_observers
    body = body.replace('// @CPP_OBSERVERS@', camera_observers)
    (snapshot / 'gameplay_camera_helpers.inc').write_text(includes + '\nnamespace gameplay_camera_wire {\n' + body + '\n}\n')
    score_path = TESTS / 'Native/scoring_runtime_probe.cpp'
    score_body = function(score_path.read_text(), 'struct Output {') + ';'
    (snapshot / 'gameplay_scoring_helpers.inc').write_text('namespace gameplay_score_wire {\n' + score_body + '\n}\n')
    extracts.append(dict(file=score_path.relative_to(PLUGIN).as_posix(),full_sha256=digest(score_path),
        method_sha256=hashlib.sha256(score_body.encode()).hexdigest(),exact_boundary='balanced complete observation-only Output struct'))
    binary = output / 'gameplay-runtime-native'
    if compile:
        subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math',
            '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot),
            *[str(snapshot / (n + '.cpp')) for n in UNITS],
            str(snapshot / 'gameplay_runtime_probe.cpp'), '-o', str(binary)], check=True)
    for name, sha in hashes.items():
        assert digest(snapshot / name) == sha, name
    report = dict(immutable_native_sources=hashes, reused_observer_extractions=extracts,
                  player_protocol=player_report, units=UNITS,
                  binary_sha256=digest(binary) if compile else None)
    (output / 'native-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    return binary


def packet(tick, **values):
    actions = [0.] * 18
    for slot, value in values.items():
        actions[int(slot.removeprefix('a'))] = value
    return [0, tick & 0xffffffff, tick >> 32, 1, *fs(actions)]


def travel(x=0., y=1., z=0., heading=0.):
    c, s = math.cos(heading), math.sin(heading)
    # Native affine column lanes, same explicit valid TravelTo caller domain.
    return [1, *fs([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, x, y, z, 0])]


def corpus():
    cases = []
    for stance in (0, 1):
        for scenario in ('neutral', 'push-brake', 'pop-flip-spin', 'slide-manual',
                         'offboard-run-mount', 'teleport-launch-tune'):
            rows = []
            tick = 0

            def frames(count, **values):
                nonlocal tick
                for _ in range(count):
                    rows.append(packet(tick, **values)); tick += 1

            frames(12)
            if scenario == 'neutral':
                frames(120)
                for available in (0, 1, 0, 1):
                    row = packet(tick); row[3] = available; rows.append(row); tick += 1
                rows += [[5, bits(4 / 3)], [5, bits(16 / 9)], [5, bits(0)], [5, 0x7fc01234]]
                frames(24)
            elif scenario == 'push-brake':
                for _ in range(4):
                    frames(8, a16=1); frames(22); frames(8, a14=1); frames(22)
                frames(40, a17=1); frames(36)
            elif scenario == 'pop-flip-spin':
                frames(40, a16=1)
                for side in (-1, 1):
                    for horizontal in (0, side):
                        frames(18, a4=-1); frames(2, a3=horizontal, a4=1)
                        frames(18, a0=side, a3=horizontal); frames(48)
                frames(40)
            elif scenario == 'slide-manual':
                rows += [[2, *fs([0, 0, 5.731])]]
                frames(24)
                for side in (-1, 1):
                    frames(30, a0=side, a1=-.731, a6=1); frames(18)
                    frames(24, a4=-.517); frames(18)
                    frames(24, a4=.517); frames(18)
                frames(40, a17=1)
            elif scenario == 'offboard-run-mount':
                frames(2, a15=1); frames(36)
                frames(64, a0=.317, a1=-1, a16=1); frames(24, a0=-.731, a1=-.731)
                frames(2, a14=1); frames(48)
                frames(2, a15=1); frames(64)
            else:
                for k in range(3):
                    rows += [[3, *fs([1 + k * .137, 1 + k * .317, 1 + k * .173, 1 + k * .231])],
                             travel(k * .317, 1.317, -k * .731, k * .317),
                             travel(-.731, 1.731, .317, -.137)]
                    frames(8)
                    rows += [[2, *fs([.317 * k, 2.731 + k, 3.731 + k])]]
                    frames(36, a0=.137 * (k - 1)); frames(48)
                for value in (.49, 2.01, float('nan')):
                    rows += [[3, *fs([value, 1, 1, 1])]]
                    frames(1)
                rows += [[3, *fs([1, 1, 1, 1])], [4, 1 - stance, 2], [4, stance, 0], travel(.731, 1.137, -.317, -.731)]
                frames(32)
            cases.append(dict(index=len(cases),natural_stance=stance,scenario=scenario,rows=rows))
    words = [len(cases)]
    for case in cases:
        words += [case['natural_stance'], len(case['rows']), *flatten(case['rows'])]
    return struct.pack('<' + 'I' * len(words), *words), cases


def preflight(raw, cases):
    words = struct.unpack('<' + 'I' * (len(raw) // 4), raw)
    assert words[0] == len(cases)
    at = 1
    ranges = []
    for case in cases:
        start = at
        assert words[at:at + 2] == (case['natural_stance'], len(case['rows']))
        at += 2
        for row in case['rows']:
            assert len(row) == LENGTHS[row[0]], (row[0], len(row))
            assert list(words[at:at + len(row)]) == row
            at += len(row)
        ranges.append([start * 4, at * 4])
    assert at == len(words)
    assert len(cases) == 12 and {case['natural_stance'] for case in cases} == {0, 1}
    return ranges


class Reader:
    def __init__(self, data): self.data, self.at = data, 0
    def word(self):
        value = struct.unpack_from('<I', self.data, self.at)[0]; self.at += 4; return value
    def take(self, n): return [self.word() for _ in range(n)]
    def status(self):
        okay = self.word(); assert okay in (0, 1)
        return dict(okay=bool(okay), error='' if okay else bytes(self.take(self.word())).decode())
    def snapshot(self):
        assert self.word() == len(SECTIONS)
        result = {}; spans = {}
        for name in SECTIONS:
            count = self.word(); start = self.at
            result[name] = self.take(count); spans[name] = [start, self.at]
        return result, spans


def decode(raw, cases):
    r = Reader(raw); assert r.word() == len(cases); out = []
    for case in cases:
        assert r.word() == len(case['rows'])
        loaded = r.status(); assert loaded['okay'], loaded
        initial, span = r.snapshot(); frames = []
        for row in case['rows']:
            assert r.word() == row[0]
            status = r.status(); frame, spans = r.snapshot()
            frames.append(dict(op=row[0],status=status,sections=frame,spans=spans))
        out.append(dict(initial=initial,frames=frames))
    assert r.at == len(raw), (r.at, len(raw))
    return out


def coverage(decoded, cases):
    stats = Counter(); states = set(); poses = set(); controls = set(); camera = set(); scoring_states = set()
    for case, trace in zip(cases, decoded):
        before = trace['initial']
        last_tick = before['metadata'][0] | (before['metadata'][1] << 32)
        assert last_tick == 0
        for row, frame in zip(case['rows'], trace['frames']):
            after = frame['sections']; status = frame['status']; tick = after['metadata'][0] | (after['metadata'][1] << 32)
            stats['operations'] += 1; stats['successes' if status['okay'] else 'failures'] += 1
            states.add(after['state'][0]); controls.add(tuple(after['controls'][:26])); poses.add(hashlib.sha256(struct.pack('<'+'I'*len(after['physical']),*after['physical'])).hexdigest())
            camera.add(tuple(after['camera'])); scoring_states.add(tuple(after['scoring']))
            if row[0] == 0:
                stats['frames'] += 1
                if status['okay']:
                    assert tick == last_tick + 1, (case['scenario'], tick, last_tick)
                    stats['completed_frames'] += 1
                else:
                    # Failure can occur before or after FinishSkater increments
                    # the authoritative tick; compare that exact retained prefix.
                    assert tick in (last_tick, last_tick + 1)
                    assert status['error']
                    stats['failed_frames'] += 1
            elif row[0] == 3 and not status['okay']:
                assert status['error'] == 'Invalid skating tuning'
                assert after == before, 'Invalid tune must retain every observed live owner'
                stats['invalid_tunes_retained'] += 1
            elif row[0] == 1 and not status['okay']:
                assert status['error'] == 'A pending teleport must complete before replacement'
                assert after == before, 'Pending replacement must retain the actual first request and all owners'
                stats['pending_teleports_retained'] += 1
            else:
                assert tick == last_tick
            before = after; last_tick = tick
    assert stats['completed_frames'] > 256, stats
    assert stats['invalid_tunes_retained'] == 6, stats
    assert stats['pending_teleports_retained'] == 6, stats
    assert len(states) >= 3, states
    assert len(poses) > 128 and len(controls) > 32 and len(camera) > 32
    assert len(scoring_states) > 16
    return dict(stats, selected_states=sorted(states), physical_pose_variants=len(poses),
                control_variants=len(controls), camera_variants=len(camera), scoring_variants=len(scoring_states),
                note='Coverage witnesses are actual original outputs, not expected fabricated state transitions. Histories may expose original explicit errors; every retained prefix is compared exactly.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--native-package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-dir', type=Path, required=True)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    raw, cases = corpus(); ranges = preflight(raw, cases)
    (out / 'input.bin').write_bytes(raw); (out / 'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    manifest = dict(cases=len(cases), commands=sum(len(case['rows']) for case in cases),
        frames=sum(row[0] == 0 for case in cases for row in case['rows']), input_bytes=len(raw),
        input_sha256=hashlib.sha256(raw).hexdigest(), units=len(UNITS), input_ranges=ranges,
        assets_sha256={p.relative_to(args.assets).as_posix():digest(p)for p in sorted(args.assets.rglob('*'))if p.is_file()},
        native_package_sha256={p.relative_to(args.native_package).as_posix():digest(p)for p in sorted(args.native_package.rglob('*'))if p.is_file()})
    reference = build_reference(out / 'reference', args.target_dir, compile=not args.preflight)
    native = build_native(out, compile=not args.preflight)
    if args.preflight:
        (out / 'preflight.json').write_text(json.dumps(manifest,indent=2)+'\n'); print(json.dumps({k:v for k,v in manifest.items()if not k.endswith('_sha256')},indent=2)); return
    expected = subprocess.run([str(reference),str(args.assets.resolve())],input=raw,stdout=subprocess.PIPE,check=True).stdout
    actual = subprocess.run([str(native),str(args.native_package.resolve())],input=raw,stdout=subprocess.PIPE,check=True).stdout
    (out / 'reference.bin').write_bytes(expected); (out / 'native.bin').write_bytes(actual)
    if expected != actual:
        index = next((i for i,(a,b)in enumerate(zip(expected,actual))if a!=b), min(len(expected),len(actual)))
        report = dict(first_byte=index, first_word=index//4, expected_bytes=len(expected), actual_bytes=len(actual))
        try:
            traces = decode(expected,cases)
            for case, trace in zip(cases,traces):
                for row, frame in enumerate(trace['frames']):
                    for name,(begin,end)in frame['spans'].items():
                        if begin <= index < end: report.update(case=case['index'],row=row,opcode=case['rows'][row][0],section=name,section_word=(index-begin)//4)
        finally:
            (out / 'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n')
        raise AssertionError(report)
    result = dict(passed=True,reference_revision=REFERENCE_REVISION,**manifest,bytes=len(expected),
        sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage(decode(expected,cases),cases),
        scope='Complete stock fixed-frame runtime on exact authored Flat world and empty original grind provider. All controls/gestures, animation graphs, processed-input/state selection, contacts/shared solve, physical/render/COM/camera/scoring publications execute from actual owners. Initialization and every operation/failure prefix are bitwise compared.',
        limitations='Published action18 values/controller availability are the external input boundary. Flat world intentionally contains no authored grind rails, movable actors, climb clips or network peer. Histories exercise source-reachable paths; full stock non-flat gameplay and Unreal frame/world/event transport remain separate integrations. Original sampling panic context is retained as its exact returned test-transport diagnostic, with original update_for_physics body unchanged.')
    (out / 'result.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps({k:v for k,v in result.items()if not k.endswith('_sha256')},indent=2))


if __name__ == '__main__':
    main()
