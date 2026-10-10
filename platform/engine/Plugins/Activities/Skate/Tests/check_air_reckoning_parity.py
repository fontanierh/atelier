#!/usr/bin/env python3
"""Whole original AirReckoning, physical BodySpin/BodyFlip and retained owners.

Only the root render guard compiles/executes. Original host/core prefixes remain
byte-for-byte intact; explicit fixture inputs and private field observers append.
Runtime consumes simulation settings and borrows the canonical physical/input owners.
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
import check_physical_simulation_runtime_parity as physics
from camera_reference_build import frozen_sources
from check_gesture_parity import PLUGIN, converter
from session_parity import REFERENCE_REVISION, digest

CODE = PLUGIN / 'Source/AtelierSkate/Private/Simulation'
UNITS = tuple(dict.fromkeys((*physics.UNITS, 'StockSettingsReader',
                            'PlayerInputTypes', 'WipeoutOrientation',
                            'BodySpin', 'BodyFlip', 'AirReckoning')))
OPS = ('seed', 'host_update', 'plant', 'scale', 'reset_spin', 'spin_update', 'spin_ground',
       'spin_words', 'flip', 'limiter', 'spin_settings', 'core_update', 'flip_settings', 'fields')

def bits(v): return struct.unpack('<I', struct.pack('<f', v))[0]
def fs(v): return [bits(x) for x in v]
def flat(rows): return [x for row in rows for x in row]
def matrix(n):
    c, s = math.cos(n * .137), math.sin(n * .137)
    return [[c, .0317, -s, .137], [.0173, 1, .071, -.317], [s, .0137, c, .731], [.13 + n * .0317, .17, -.731, .137]]
def spin_words(n):
    words = fs([(.731 if k % 4 == n % 4 else -.317) * (1 + (k % 5) * .137) for k in range(30)])
    words += fs([.137, -.317, .731, -.517]) + [0xa5f7318c] + fs([(-.731, .01, .731, 1.73)[n % 4], .317, -.731, 0, -.137, .317, .517])
    return words + [n % 30, 0xa3aaccee]
def seed(n, flip=None):
    state = fs([.1731 * n, -.317, .731, .137 if n % 3 == 0 else 0, -.1731, .317])
    state += fs(flat(matrix(n))) + fs([1, .0317, .137, .317]) + [int(n % 3 == 0 if flip is None else flip), n % 2]
    orientation = fs([0, 1, 0, .071, .983, .137, 0, 1, 0, .0317, -.0173, .071, .137, .983, .071, .317])
    for f in range(3):
        orientation += fs([.137 + f * .0173, .071, .0137, .317])
        orientation += fs([.137, .983, .071, .1731, .137, .983, .071, -.317])
        orientation += fs([(.00173 * ((n + j) % 7 - 3)) for j in range(12)])
    frames = []
    for f in range(5): frames += fs(flat(matrix(n + f)))
    frames += fs([1, .0317, .137, .317, .731, .137, -.317, .731, -.1731])
    return [0] + state + spin_words(n) + orientation + frames
def host(n, mode, *, invalid=False):
    return [1, (1 << 20) if n % 2 else 0, (1 << 28) if n % 3 == 1 else 0,
            (1 << 15) if n % 5 == 2 else 0, (5 if n % 2 else 0xffffffff) if invalid else mode] + fs([
                (.00831, .016666668, .0317)[n % 3], -.731 + (n % 11) * .1731,
                .137 + (n % 7) * .317, .731, -.317, .137,
                math.sin(n * .317) * 1.317, .1731 * math.sin(n * .137), .8731, .317 * math.cos(n * .1731), .1731,
                (.0317, .317, .731, 1.137)[n % 4], (-2.317, -.731, 0, .731, 2.317)[n % 5], math.sin(n * .137) * 7.31])
def core(n):
    return [11] + fs([.1731 * math.sin(n * .137), .8731, .317 * math.cos(n * .1731), .1731,
                    (.0317, .317, .731, 1.137)[n % 4], (-.731, 0, .731, 2.317)[n % 4], math.sin(n * .137) * 7.31,
                    .137 + (n % 7) * .317, .731, -.317, .137, (.00831, .016666668, .0317)[n % 3],
                    math.sin(n * .317) * 1.317, -.731 + (n % 11) * .1731]) + [int(n % 5 == 2), int(n % 3 == 1), n % 2, (n // 2) % 2, (n // 3) % 2]
def flip_settings(n):
    values = []
    for j, v in enumerate((.137, 7.31, 1.137)):
        present = bool(n & (1 << j)); values += [int(present)] + ([bits(v)] if present else [])
    return values + [bits(.731)]
def spin_settings(n):
    values = [10] + fs([.317, .731])
    for j in range(7):
        x = [-1, -.517, -.137, 0, .137, .517, 1.137, 2.317]
        y = [(.0317 + j * .0173 + k * .0137) if j < 3 else (-.1731 + j * .317 + k * .137) for k in range(8)]
        if j in (3, 4) and n % 3 == 0: y[:4] = [.731] * 4  # strict equal-peak history ties
        values += fs(x + y)
    thresholds = [.137] * 4
    if n % 3 == 1: thresholds[2] = 0  # one false lane must prevent input fade
    if n % 3 == 2: thresholds = [.00001] * 4
    return values + fs(thresholds)
def corpus():
    cases = []
    def add(name, commands, mutation=None): cases.append(dict(name=name, commands=commands, mutation=mutation))
    for n in range(12):
        commands = [seed(n)]
        for k in range(144):
            if k % 23 == 0: commands += [[3, bits((1.6, .731, 1.6, 1)[(k // 23) % 4])]]
            commands += [host(n * 144 + k, n % 5)]
            if k % 7 == 0:
                commands += [[2, (1 << 20) if k % 2 else 0] + fs([.137 + k * .00173, .983, .071, .1731, 1, .0317, .137, .317])]
            if k % 11 == 0: commands += [[6, bits(math.sin(k * .137) * .731)]]
            if k % 17 == 0: commands += [[4], [13]]
            if k % 43 == 0: commands += [host(k, 0, invalid=True)]
            if k % 19 == 0: commands += [core(k)]
        add('live host modes, stock-scale cache, additive/direct priority, flips, normal histories and plant', commands)
    for n in range(8):
        commands = [seed(n), spin_settings(n)]
        for k in range(160):
            if k % 40 == 0: commands += [[7] + spin_words(k + n)]
            commands += [[5] + fs([(-.731, 0, .000001, .137, .731)[(k + n) % 5], (-2.317, -.731, 0, .731, 2.317)[k % 5]]) + [int(k % 9 != 0), (0, 1, 5, 255)[n % 4]]]
            if k % 13 == 0: commands += [[6, bits(.731)]]
        bad = spin_words(n); bad[42] = 30; commands += [[7] + bad]
        add('complete spin derivative ring, strict peak ties, four-lane fade, acceleration gates and byte padding', commands)
    for n in range(8):
        commands = []
        for k in range(96):
            angle = (0, math.tau, -math.tau, math.tau + .01, -math.tau - .01, .731, -.731)[k % 7]
            speed = 0 if k % 7 == 0 else (-.731 if k % 2 else .731)
            commands += [[8] + fs([angle, speed, .317]) + fs(flat(matrix(k))) + fs(flat(matrix(k + 3))) + flip_settings(n)
                         + fs([0 if k % 7 == 0 else (-7.31 if k % 2 else 7.31), .1731 * k, .137, .983, .071, .317, 1, .071, .137, .731,
                               (.00831, .016666668, .0317)[k % 3]]) + [k % 2]]
        add('all optional flip attribute branches, perfect-turn clamp, the simulation W columns and untouched zero-angle matrix', commands)
    for n in range(4):
        commands = []
        for k in range(128):
            a = [math.sin(k * .137) * 2.317, .731, math.cos(k * .1731) * 1.317, .137]
            b = [.317, .731, -.137, .731]
            if k % 5 == 0: a, b = [0, 2, 0, .317], [0, -3, 0, .137]
            if k % 7 == 0: a, b = [0, 0, 0, .317], [0, 0, 0, -.137]
            commands += [[9] + fs(a + b + [(-.137, 0, .0317, .317, .731, 3.17)[(k + n) % 6]])]
        add('full simulation limiter endpoint magnitude, parallel/zero gates and fourth-lane rotation', commands)
    for category, key, name, replacement in (
            ('physics_reckoning', 'default', 'GroundNormalSmoothing', ''),
            ('physics_mode', 'easy', 'EasyBodySpins', 'missing'),
            ('physics_mode', 'test', 'PerfectBodyFlips', 'type'),
            ('physics_reckoning', 'default', 'Air_MaxUpVectAngleDelta', ''),
            ('physics_reckoning', 'default', 'TiltVsRotAir', ''),
            ('physics_bodyspin', 'default', 'MinDerivativeScalar', 'nan'),
            ('physics_bodyspin', 'default', 'MaxDeltaOppositeDirection', 'missing'),
            ('physics_bodyspin', 'default', 'Hash_BEA30B5DC6AFF26A', ''),
            ('physics_reckoning', 'default', 'FlipSpeedSmoothingFactor', 'type'),
            ('physics_reckoning', 'default', 'FlipBodySpinScalar', 'missing')):
        add('exact settings failure ' + name, [], (category, key, name, replacement))
    add('missing inherited EasyBodySpins rejection', [],
        ('physics_mode', 'easy', 'EasyBodySpins', 'missing_chain'))
    inherited = next(c for c in cases if c['mutation'] == ('physics_mode', 'easy', 'EasyBodySpins', 'missing'))
    inherited['name'] = 'removed easy EasyBodySpins inherits default false'
    raw = [len(cases)]
    for case in cases: raw += [len(case['commands'])] + flat(case['commands'])
    return struct.pack('<' + 'I' * len(raw), *raw), cases

CORE_OBSERVER = '''
impl GroundOrientation {
 pub fn migration_air_reckoning_set(&mut self,w:[u32;88]) {
  let vector=|at:usize|Vector3::new(f32::from_bits(w[at]),f32::from_bits(w[at+1]),f32::from_bits(w[at+2]));
  self.dynamic_up=vector(0);self.up=vector(3);self.target=vector(6);self.up_velocity=vector(9);self.ground_normal=vector(12);self.ground_blend=f32::from_bits(w[15]);
  self.ground_filter=GroundNormalFilter::from_words(w[16..40].try_into().unwrap());
  self.slow_filter=GroundNormalFilter::from_words(w[40..64].try_into().unwrap());
  self.fast_filter=GroundNormalFilter::from_words(w[64..88].try_into().unwrap());
 }
 pub fn migration_air_reckoning_words(&self)->[u32;88] {
  let mut w=[0;88];for (i,v) in [self.dynamic_up,self.up,self.target,self.up_velocity,self.ground_normal].into_iter().enumerate(){w[i*3..i*3+3].copy_from_slice(&[v.x.to_bits(),v.y.to_bits(),v.z.to_bits()]);}w[15]=self.ground_blend.to_bits();w[16..40].copy_from_slice(self.ground_filter.words());w[40..64].copy_from_slice(self.slow_filter.words());w[64..88].copy_from_slice(self.fast_filter.words());w
 }
}
'''
def build_reference(output, target):
    source, report = frozen_sources(output); observed = output / 'observed-source'
    if observed.exists(): shutil.rmtree(observed)
    shutil.copytree(source, observed)
    core_path = Path('crates/skate-core/src/riding/ground_orientation.rs')
    original = source / core_path; extended = observed / core_path
    extended.write_bytes(original.read_bytes() + CORE_OBSERVER.encode())
    crate = observed / 'atelier-host'; host = source / 'crates/skate-host/src'
    helper = PLUGIN / 'Tests/Reference/air_reckoning_observer.rs'
    additions = {'physics/air_reckoning.rs': '\n' + helper.read_text(), 'physics.rs': '''
pub(crate) fn migration_air_reckoning_run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{air_reckoning::migration_air_reckoning_run(assets,fixtures,i,o)}
'''}
    staged = {}
    for path in sorted(host.rglob('*.rs')):
        relative = path.relative_to(host).as_posix()
        if relative in ('lib.rs', 'main.rs'): continue
        raw = path.read_bytes(); append = additions.get(relative, '').encode(); destination = crate / 'src' / relative
        destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(raw + append)
        assert destination.read_bytes()[:len(raw)] == raw
        staged[relative] = dict(original_prefix_bytes=len(raw), original_prefix_sha256=digest(path), append_sha256=hashlib.sha256(append).hexdigest(), generated_sha256=digest(destination))
    template = PLUGIN / 'Tests/Reference/air_reckoning_probe.rs'; shutil.copy2(template, crate / 'src/migration_probe.rs')
    cargo = crate / 'Cargo.toml'; cargo.write_text(cargo.read_text() + '''
skate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="air-reckoning-reference"
path="src/migration_probe.rs"
''')
    subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2', '--manifest-path', str(cargo), '--target-dir', str(target.resolve()), '--bin', 'air-reckoning-reference'], check=True)
    for relative, sha in report['original_source_sha256'].items():
        assert digest(source / relative) == sha
        raw = (source / relative).read_bytes(); assert (observed / relative).read_bytes()[:len(raw)] == raw
    for relative, row in staged.items(): assert digest(crate / 'src' / relative) == row['generated_sha256']
    binary = output / 'air-reckoning-reference'; shutil.copy2(target.resolve() / 'release/air-reckoning-reference', binary)
    report.update(staged_host_prefixes=staged, appended_core_observer=dict(source=core_path.as_posix(), original_prefix_sha256=digest(original), generated_sha256=digest(extended), observer_sha256=hashlib.sha256(CORE_OBSERVER.encode()).hexdigest()), probe_sha256=digest(template), helper_sha256=digest(helper), binary_sha256=digest(binary), cargo_lock_sha256=digest(crate / 'Cargo.lock'), boundary='Whole original host/core production prefixes remain unchanged. Appended fixture setters target actual shared state; observers read private filter/control/history words. All loaded host settings/update/plant/scale/fields and complete original core spin/flip/limiter/update/reset bodies execute. No numerical body or callback is replaced. Invalid BodySpin from_words panic is caught solely to compare rejection and retained existing-owner semantics.')
    (output / 'reference-provenance.json').write_text(json.dumps(report, indent=2) + '\n'); return binary

def build_simulation(output):
    snapshot = output / 'simulation-source'; snapshot.mkdir(exist_ok=True); hashes = {}
    for path in sorted(CODE.glob('*.h')): shutil.copy2(path, snapshot / path.name); hashes[path.name] = digest(snapshot / path.name)
    for unit in UNITS:
        path = CODE / (unit + '.cpp'); shutil.copy2(path, snapshot / path.name); hashes[path.name] = digest(snapshot / path.name)
    probe = PLUGIN / 'Tests/Simulation/air_reckoning_probe.cpp'; shutil.copy2(probe, snapshot / probe.name); hashes[probe.name] = digest(snapshot / probe.name)
    binary = output / 'air-reckoning-simulation'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot), *[str(snapshot / (u + '.cpp')) for u in UNITS], str(snapshot / probe.name), '-o', str(binary)], check=True)
    (output / 'simulation-provenance.json').write_text(json.dumps(dict(immutable_sources=hashes, units=UNITS), indent=2) + '\n'); return binary

class Reader:
    def __init__(self, data): self.words = struct.unpack('<' + 'I' * (len(data) // 4), data); self.at = 0
    def take(self, n): values = list(self.words[self.at:self.at+n]); assert len(values) == n; self.at += n; return values
    def word(self): return self.take(1)[0]
    def optional(self):
        present = self.word(); assert present in (0, 1)
        return self.word() if present else None
    def status(self): return None if self.word() else bytes(self.take(self.word())).decode()
    def runtime(self):
        owner = dict(state=self.take(28), spin=self.take(44), orientation=self.take(88), frames=self.take(89))
        owner['settings'] = dict(control=self.take(4), graphs=self.take(48), spin=self.take(118), flip=[self.optional() for _ in range(3)], fallback=self.word())
        owner['modes'] = self.take(10); owner['cache'] = self.take(112); owner['acceleration'] = self.word(); return owner
def decode(data, cases):
    r = Reader(data); assert r.word() == len(cases); decoded = []
    for case in cases:
        assert r.word() == len(case['commands']); error = r.status(); item = dict(error=error, rows=[])
        if error is not None: assert not case['commands']; decoded.append(item); continue
        prior = r.runtime(); item['initial'] = prior
        for cmd in case['commands']:
            op = r.word(); assert op == cmd[0]; error = None; result = None
            if op in (1, 7): error = r.status()
            if op == 1 and error is None: result = r.take(10)
            if op == 8: result = r.take(35)
            if op == 9: result = r.take(4)
            if op == 13: result = r.take(10)
            state = r.runtime(); item['rows'].append(dict(op=op, error=error, result=result, state=state, prior=prior)); prior = state
        decoded.append(item)
    assert r.at == len(r.words), (r.at, len(r.words)); return decoded
def coverage(decoded, cases):
    counts = Counter(); speeds = set(); matrices = set(); histories = set(); fourth = set(); modes = set(); scale_changes = zero_flip = invalid_mode = invalid_spin = reset = 0
    spin_branches = Counter(); flip_fallbacks = set(); spin_modes = set(); inherited_modes = 0
    for item, case in zip(decoded, cases):
        inherits = case['mutation'] == ('physics_mode', 'easy', 'EasyBodySpins', 'missing')
        assert bool(item['error']) == (bool(case['mutation']) and not inherits), (case['name'], item['error'])
        if inherits:
            assert item['initial']['modes'][0] == 0
            assert item['initial']['modes'][1:] == decoded[0]['initial']['modes'][1:]
            inherited_modes += 1
        if case['mutation'] == ('physics_mode', 'easy', 'EasyBodySpins', 'missing_chain'):
            assert item['error'] == 'Missing stock field physics_mode/easy/EasyBodySpins'
        for row, cmd in zip(item['rows'], case['commands']):
            op, s, prior = row['op'], row['state'], row['prior']; counts[OPS[op]] += 1
            speeds.add(s['spin'][35]); matrices.add(tuple(s['frames'])); histories.add(tuple(s['spin'])); fourth.add(tuple(s['orientation'][19::4]))
            if op == 1 and row['error'] is not None:
                assert row['error'] == f'Undefined physics mode {cmd[4]}' and s == prior; invalid_mode += 1
            elif op == 1:
                modes.add(cmd[4])
                if cmd[3] & (1 << 15):
                    expected = bits(struct.unpack('<f', struct.pack('<I', cmd[6]))[0] + struct.unpack('<f', struct.pack('<I', cmd[17]))[0])
                    spin_branches['additive_over_direct' if cmd[2] & (1 << 28) else 'additive'] += 1
                elif cmd[2] & (1 << 28): expected = cmd[17]; spin_branches['direct'] += 1
                else: expected = s['spin'][35]; spin_branches['filtered'] += 1
                assert s['state'][1] == expected
            if op in (1, 11, 2) and row['error'] is None:
                assert s['frames'][12:16] == prior['frames'][12:16], 'ground translation must remain retained'
                # The persistent orientation stores Vector3; the two filters
                # publish the original chosen Vec4, including its retained W.
                up = s['orientation'][44:48]
                assert up[:3] == s['orientation'][3:6] and s['orientation'][68:72] == up
                assert s['orientation'][40:44] == prior['orientation'][40:44] and s['orientation'][64:68] == prior['orientation'][64:68], 'slow/fast retained controls'
            if op in (1, 13) and row['error'] is None:
                assert row['result'] == s['orientation'][3:6] + [0] + s['orientation'][12:15] + [0] + s['state'][:2]
            if op == 3:
                assert s['cache'] == prior['cache'] and s['acceleration'] == prior['acceleration']
                assert s['settings']['spin'][:1] == prior['settings']['spin'][:1]
                scale = struct.unpack('<f', struct.pack('<I', cmd[1]))[0]
                assert s['settings']['spin'][1] == bits(struct.unpack('<f', struct.pack('<I', s['acceleration']))[0] * scale)
                for curve in range(7):
                    at = 2 + curve * 16
                    assert s['settings']['spin'][at:at+8] == prior['settings']['spin'][at:at+8]
                    if curve in (0, 1, 5, 6):
                        assert s['settings']['spin'][at+8:at+16] == [bits(struct.unpack('<f', struct.pack('<I', word))[0] * scale) for word in s['cache'][curve*16+8:curve*16+16]]
                    else: assert s['settings']['spin'][at+8:at+16] == prior['settings']['spin'][at+8:at+16]
                scale_changes += 1
            if op == 4:
                assert s['state'][:2] == [0, 0] and s['state'][2:] == prior['state'][2:]
                for key in ('spin', 'orientation', 'frames', 'settings', 'cache'): assert s[key] == prior[key]
                reset += 1
            if op == 6:
                assert s['spin'][35] == s['spin'][36] == s['spin'][38] == 0 and s['spin'][43] == prior['spin'][43] & 0x00ffffff
                assert s['spin'][42] == (prior['spin'][42] + 1) % 30
            if op in (5, 6):
                assert s['spin'][34] == prior['spin'][34] and s['spin'][43] & 0x00ffffff == prior['spin'][43] & 0x00ffffff
            if op == 5:
                spin_modes.add(cmd[4]); assert s['spin'][43] >> 24 == cmd[4]
            if op == 7 and row['error']:
                assert row['error'] == 'native derivative history index must be 0..30' and s == prior; invalid_spin += 1
            if op == 8:
                at = 36; present = []
                for _ in range(3): present.append(cmd[at]); at += 1 + cmd[at]
                flip_fallbacks.add(tuple(present))
                if row['result'][0] & 0x7fffffff == 0:
                    assert row['result'][19:35] == cmd[20:36]; zero_flip += 1
    assert modes == {0, 1, 2, 3, 4}, modes
    assert len(speeds) > 64 and len(matrices) > 256 and len(histories) > 512 and len(fourth) > 128
    assert scale_changes == 84 and zero_flip > 64 and invalid_mode == 48 and invalid_spin == 8 and reset == 108
    assert spin_modes == {0, 1, 5, 255} and len(flip_fallbacks) == 8
    assert set(spin_branches) == {'additive', 'additive_over_direct', 'direct', 'filtered'} and min(spin_branches.values()) > 64
    assert inherited_modes == 1
    return dict(operations=dict(counts),speed_variants=len(speeds),frame_variants=len(matrices),spin_histories=len(histories),fourth_lane_filter_variants=len(fourth),physics_modes=sorted(modes),spin_branch_priority=dict(spin_branches),spin_mode_bytes=sorted(spin_modes),optional_flip_attribute_combinations=len(flip_fallbacks),stock_cache_scale_changes=scale_changes,zero_flip_matrix_retention=zero_flip,invalid_modes_unchanged=invalid_mode,invalid_spin_rejections=invalid_spin,selective_spin_resets=reset,inherited_mode_loads=inherited_modes,settings_errors=[item['error'] for item in decoded if item['error']])

def prepare(assets, output, cases):
    fixtures = output / 'fixtures'; fixtures.mkdir(exist_ok=True)
    source = assets / 'private/stock/skater-collections.json'; stock = json.loads(source.read_text())
    (fixtures / 'stock.settings').write_bytes(converter.encode_settings(source))
    skeletons = assets / 'private/stock/physics-skeletons.json'; (fixtures / 'physics.simulation').write_bytes(converter.encode_physics_skeletons(skeletons))
    for index, case in enumerate(cases):
        data = copy.deepcopy(stock)
        if case['mutation']:
            category, key, name, replacement = case['mutation']; record = next(r for r in data['collections'] if r['class'] == category and r['key'] == key)
            # Match the source's normalized hash aliases when a recovered name
            # is represented by Hash_<id> in the original collection.
            target = next((n for n in record['fields'] if n == name), None)
            if target is None: target = next(n for n in record['fields'] if converter.name_hash(n) == converter.name_hash(name))
            if replacement == 'missing_chain':
                current = record
                while True:
                    names = [n for n in current['fields'] if converter.name_hash(n) == converter.name_hash(name)]
                    for n in names: current['fields'].pop(n)
                    if not current.get('parent'): break
                    current = next(r for r in data['collections'] if r['class'] == category and r['key'] == current['parent'])
            elif replacement == 'missing': record['fields'].pop(target)
            elif replacement == 'type': record['fields'][target]['type'] = 'EA::Reflection::String'
            elif replacement == 'nan': record['fields'][target]['data'] = '7fc00000'
            else: record['fields'][target]['data'] = replacement
        folder = fixtures / f'case-{index}'; original = folder / 'private/stock/skater-collections.json'; original.parent.mkdir(parents=True, exist_ok=True); original.write_text(json.dumps(data)); (folder / 'settings.simulation').write_bytes(converter.encode_settings(original))
    return fixtures, json.loads(skeletons.read_text())['source_sha256']
def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--assets', type=Path, required=True); p.add_argument('--samples', type=Path, required=True); p.add_argument('--output', type=Path, required=True); p.add_argument('--target-dir', type=Path, required=True); p.add_argument('--preflight', action='store_true'); a = p.parse_args()
    output = a.output.resolve(); output.mkdir(parents=True, exist_ok=True); corpus_bytes, cases = corpus(); (output / 'input.bin').write_bytes(corpus_bytes)
    fixtures, identity = prepare(a.assets.resolve(), output, cases)
    for unit in UNITS: assert (CODE / (unit + '.cpp')).is_file(), unit
    if a.preflight:
        print(json.dumps(dict(cases=len(cases),commands=sum(len(c['commands']) for c in cases),input_bytes=len(corpus_bytes),units=len(UNITS)), indent=2)); return
    reference = build_reference(output / 'reference', a.target_dir); simulation = build_simulation(output)
    expected = subprocess.check_output([str(reference), str(a.assets.resolve()), str(fixtures)], input=corpus_bytes)
    actual = subprocess.check_output([str(simulation), str(fixtures), str(fixtures / 'stock.settings'), str(fixtures / 'physics.simulation'), str(a.samples.resolve() / 'simulation/rig.skate'), identity, str(a.assets.resolve())], input=corpus_bytes)
    (output / 'reference.bin').write_bytes(expected); (output / 'simulation.bin').write_bytes(actual)
    if actual != expected:
        at = next((i for i, (a,b) in enumerate(zip(expected,actual)) if a != b), min(len(expected),len(actual)))
        report = dict(byte=at,word=at//4,reference_bytes=len(expected),simulation_bytes=len(actual),reference_hex=expected[max(0,at-16):at+32].hex(),simulation_hex=actual[max(0,at-16):at+32].hex()); (output / 'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n'); raise AssertionError(report)
    proof = coverage(decode(expected,cases),cases)
    result = dict(passed=True, reference_revision=REFERENCE_REVISION, cases=len(cases), commands=sum(len(c['commands']) for c in cases), bytes=len(expected), sha256=hashlib.sha256(expected).hexdigest(), input_sha256=hashlib.sha256(corpus_bytes).hexdigest(), coverage=proof, boundary='Complete unchanged original core air/reckoning/{mod,data,math}, physical body_spin/body_flip and host air_reckoning/settings bodies; actual canonical RidingOutputs/filter/frame/body-spin owners. Runtime simulation settings only. Explicit completed processed/trajectory/animation fields remain upstream producer inputs. Root frame/state/air scheduling and trajectory producers are not claimed. Optional BodyFlip fallbacks are covered directly as core call inputs; production host loader requires all three attributes. Invalid BodySpin from_words panics are caught in oracle and explicitly rejected in C++; other invalid-owner mutation/panic domains are excluded. No neutral callback or replacement numeric method executes.')
    (output / 'result.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2))
if __name__ == '__main__': main()
