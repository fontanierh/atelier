#!/usr/bin/env python3
"""Whole original Handplant/PlantSkeleton/SkeletonAir composition proof.

Only the root render guard builds and executes. The reference retains every
original host/core byte prefix. No callback, trajectory hit, pose or IK result
is replaced. Explicit processed inputs, authored rails and engine triangles are
caller boundaries; stock hierarchy and all downstream owners are produced live.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import check_handplant_parity as numeric
import check_air_reckoning_parity as air
import check_skeleton_input_runtime_parity as skeleton
import check_air_trajectory_query_parity as query
from camera_reference_build import frozen_sources
from check_gesture_parity import PLUGIN, converter
from check_graph_parity import element, original_graph
from session_parity import REFERENCE_REVISION, digest

CODE = PLUGIN / 'Source/AtelierSkate/Private/Native'
UNITS = tuple(dict.fromkeys((*skeleton.UNITS, *air.UNITS, *query.UNITS,
    'NameId','Settings','StockSettingsReader','NativeMath','AnimationName','Input','InputIntentions','WipeoutOrientation','SkeletonPhysicalRecord','PlayerInputTypes','PlayerInputPhase',
    'PlayerGrindSurface', 'PlayerGrindInputWorld', 'BoardAnimation',
    'SkeletonAirFrames', 'SkeletonAirRuntime', 'HandplantSettings',
    'HandplantContact', 'HandplantRotation', 'HandplantTrajectory',
    'Handplant', 'PlantSkeleton')))
OPS = ('publish', 'authored_pose', 'ground_query', 'ground_update', 'enter',
       'update', 'advance_plant', 'hold_foot', 'capture_error', 'reset_board',
       'animated_air', 'known_air', 'continuation', 'reset', 'launch', 'pending_trajectory')
SECTIONS = ('handplant', 'reckoning', 'roots', 'pose_drives', 'ik', 'bodies_blend',
            'physical_record', 'drive_owner', 'publication', 'adjustment')
fs = numeric.fs
bits = numeric.bits

def publish(n):
    return [0, 0x2000 | ((1 << 20) if n % 2 else 0), 0,
            (1 << 22) | (4 if n % 3 == 0 else 0),
            (1 << 28) | ((1 << 29) if n % 17 == 0 else 0), 0, 600, 600] + fs([
                (1 / 60, 1 / 120, 1 / 30)[n % 3], 9.81,
                0, .731, 0, 0, (1 if n % 2 == 0 else -1) * (1.137 + (n % 5) * .137),
                4.731 + (n % 7) * .137, .0317, 0,
                0, .6, (-1 if n % 2 == 0 else 1) * .8, 0,
                1, 0, 0, 0, .731, 4.73, .137, 0, 1, 0, 0, 0])

def launch(n):
    point = (.731 + (n % 5) * .0317, 1.7 + (n % 3) * .137, -.317, 0)
    owner = 0x1234567800000001 + n
    c = fs([*point, -2, point[1], point[2], 0, 2, point[1], point[2], 0]) + [owner & 0xffffffff, owner >> 32, 1 + n % 2]
    # Candidate construction is an explicit caller-domain case. Launch itself
    # generates every trajectory/rotation/curve; no completed query hit enters.
    return [14] + c + fs([0, .731, 0, 0, 1.137, 4.731, .137, 0,
                         0, .6, .8, 0, 1, 0, 0, 0, 1, 0, 0, 0])

def pending(n):
    return [15] + fs([1,0,0,0, 0,1,0,0, 0,0,1,0, .13+n*.0173,.17,-.317,0])

def corpus():
    cases = []; records = []
    def add(label, commands, n, domain, metadata=False):
        edges = numeric.edges(n)
        for index in range(edges[0]):
            edges[1 + index * 10 + 3] = edges[1 + index * 10 + 7] = 0
        world = ([0xffffffff] + numeric.authored_query_world(n % 2, pool=n % 3)[1:]) if metadata else numeric.world(n % 3)
        raw = world + edges + [len(commands)] + numeric.flatten(commands)
        cases.append(dict(index=len(cases), label=label, domain=domain,
                          commands=commands, operations=[c[0] for c in commands], metadata=metadata))
        records.append(struct.pack('<' + 'I' * len(raw), *raw))
    for n in range(6):
        commands = [publish(n), [1, n % 4], [2], [3], [4]]
        # This caller consumes the real coping returned by GroundQuery. Empty
        # scenes can still produce the source's thin-rail investigation result.
        for k in range(72):
            commands += [publish(n + k), [1, (n + k // 9) % 4], [5]]
            if k % 13 == 0: commands += [[8]]
            if k % 19 == 0: commands += [[12, (k // 19) % 2]]
            if k % 23 == 0: commands += [[7, k % 2] + fs([.517, .137, -.317, 0]) + [2 + k % 5]]
        commands += [[13, n % 2]]
        add('real authored coping selection, surface investigation, entry and retained plant update', commands, n, 'ground')
    for n in range(6):
        commands = [publish(n), [1, n % 4], launch(n), [4]]
        for k in range(96):
            commands += [publish(n + k), [1, (n + k // 13) % 4], [5]]
            if k % 17 == 0: commands += [[8], [10, (k // 17) % 2]]
            if k % 29 == 0: commands += [[9]]
        add('explicit caller coping, complete source launch and concrete outgoing query/plant owners', commands, n, 'caller')
    for n in range(6):
        commands = [publish(n), [1, n % 4], launch(n), [4], [5], [8]]
        for k in range(16):
            commands += [publish(n + k), [1, (n + k) % 4],
                [6] + fs([.317 + k * .0173, .731, -.137, 0]) +
                    [0xffffffff if k % 2 else (3, 7, 15, 19)[(k // 2) % 4]],
                pending(k), [10, k % 2], pending(k + 1),
                [11] + fs([.13 + k * .0173, .731, -.317, 0]) +
                    [(1 << 28) if k % 3 else 0, (0, 1, 7, 31, 360, 0x80000000, 0xffffffff)[k % 7]]]
            if k % 7 == 0: commands += [[8], [9]]
        add('anchored feet versus COM, actual AnimatedAir/KnownAir, unsigned revert and persistent board blend', commands, n, 'air')
    for n in range(4):
        commands = [publish(n), [1, n % 4], launch(n), [4], [5], [8]]
        for missing in (4, 5):
            commands += [[1, missing], [5], [6] + fs([.517, .731, -.317, 0]) + [0xffffffff],
                         [10, n % 2], [11] + fs([.317, .731, -.137, 0]) + [1 << 28, 7],
                         [1, n % 4], [5]]
        commands += [[13, 1], [4]]
        add('missing hierarchy preserves original mutations before GeneralUpdate/IK rejection; missing coping entry', commands, n, 'failure')
    for scene in range(3):
        commands = [publish(0), [1, 0], launch(0), [4]] + [[5] for _ in range(8)]
        add('identical coping/launch isolated across floor, ledge and empty real trajectory-query worlds', commands, scene, 'query_world')
    # All 25 original streams above remain byte-identical. These additive
    # scenes provide genuine packed surfaces/mesh ownership to the actual
    # source investigation before entry and its concrete outgoing query.
    for n in range(4):
        commands=[]
        for k in range(8):
            j=n*72+k
            commands += [publish(j),[1,j%4],[2],[3],[4]]
            for t in range(24):
                commands += [publish(j+t),[1,(j+t//9)%4],[5]]
                if t%13==0:commands += [[8]]
            commands += [[9],[13,k%2]]
        add('genuine metadata investigation then source entry/outgoing query and full retained plant update',commands,n,'ground',True)
    raw=struct.pack('<I',len(records))+b''.join(records)
    assert len(cases[:25])==25 and sum(len(c['commands'])for c in cases[:25])==4132
    baseline=struct.pack('<I',25)+b''.join(records[:25])
    assert hashlib.sha256(baseline).hexdigest()==BASELINE_INPUT_SHA256
    return raw,cases

BASELINE_INPUT_SHA256='d2b20ee30db3e6c5d46d67cff68fc5e375e531583d763a5f62d7493c82f67d67'

def extraction(path, boundary):
    raw = path.read_bytes(); marker = boundary.encode()
    assert raw.count(marker) == 1, (path, boundary)
    end = raw.index(marker); prefix = raw[:end]
    assert prefix.endswith(b'\n'), (path, end)
    return prefix, dict(source=path.relative_to(PLUGIN).as_posix(),
                        original_sha256=digest(path), start=0, end=end,
                        boundary=boundary, prefix_sha256=hashlib.sha256(prefix).hexdigest())

def build_reference(output, target, *, compile=True):
    source, report = frozen_sources(output); observed = output / 'observed-source'
    if observed.exists(): shutil.rmtree(observed)
    shutil.copytree(source, observed); crate = observed / 'atelier-host'
    host = source / 'crates/skate-host/src'
    helper = PLUGIN / 'Tests/Reference/handplant_lifecycle_observer.rs'
    prefix, h_extract = extraction(PLUGIN / 'Tests/Reference/handplant_observer.rs', 'pub(super) fn run(')
    aprefix, a_extract = extraction(PLUGIN / 'Tests/Reference/air_reckoning_observer.rs', 'fn core_input(')
    # Only read-only original-owner observers are reused. Their containing
    # migration module is closed below; no old numeric probe entry executes.
    air_view = b'''\npub(super) fn observe(o:&mut Output,a:&AirReckoning,r:&RidingOutputs){out_state(o,&a.state);for w in *r.body_spin.words(){o.word(w)}for w in r.reckoning.migration_air_reckoning_words(){o.word(w)}out_frames(o,&r.reckoning_frames);}\n}\npub(crate) fn migration_lifecycle_observe(o:&mut crate::Output,a:&AirReckoning,r:&RidingOutputs){migration::observe(o,a,r)}\n'''
    extensions = {'physics/handplant.rs': b'\n' + prefix + helper.read_bytes(),
        'physics/air_reckoning.rs': b'\n' + aprefix + air_view,
        'physics.rs': b'\npub(crate) fn migration_handplant_lifecycle_run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{handplant::migration_handplant_lifecycle_run(assets,fixtures,i,o)}\n',
        'grind_world/provider.rs': b'\npub(super) fn migration_handplant_primitives(primitives:Vec<Primitive>)->StaticProvider{let mut value=StaticProvider::new(None).unwrap();value.primitives=primitives;value}\n',
        'grind_world.rs': b'\npub(crate) fn migration_handplant_primitives(primitives:Vec<skate_core::physics::grind_contact::Primitive>)->StaticProvider{provider::migration_handplant_primitives(primitives)}\n'}
    staged = {}
    for original in sorted(host.rglob('*.rs')):
        rel = original.relative_to(host).as_posix()
        if rel in ('lib.rs', 'main.rs'): continue
        raw = original.read_bytes(); extra = extensions.get(rel, b'')
        p = crate / 'src' / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw + extra)
        assert p.read_bytes()[:len(raw)] == raw
        staged[rel] = dict(original_prefix_bytes=len(raw), original_prefix_sha256=digest(original),
                          append_sha256=hashlib.sha256(extra).hexdigest(), generated_sha256=digest(p))
    core = {'crates/skate-core/src/riding/ground_orientation.rs': air.CORE_OBSERVER.encode(),
            'crates/skate-core/src/physics/skeleton_motion.rs': b'\nimpl SkeletonMotion {pub fn migration_lifecycle_previous(&self)->f32{self.previous_board_at_y}}\n'}
    for rel, extra in core.items():
        original = source / rel; p = observed / rel; p.write_bytes(original.read_bytes() + extra)
        assert p.read_bytes()[:original.stat().st_size] == original.read_bytes()
    template = PLUGIN / 'Tests/Reference/handplant_lifecycle_probe.rs'
    shutil.copy2(template, crate / 'src/migration_probe.rs')
    cargo = crate / 'Cargo.toml'; cargo.write_text(cargo.read_text() + '''
skate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="handplant-lifecycle-reference"
path="src/migration_probe.rs"
''')
    if compile:
        subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2',
            '--manifest-path', str(cargo), '--target-dir', str(target.resolve()), '--bin', 'handplant-lifecycle-reference'], check=True)
    for rel, sha in report['original_source_sha256'].items():
        assert digest(source / rel) == sha
        assert (observed / rel).read_bytes()[:len((source / rel).read_bytes())] == (source / rel).read_bytes(), rel
    for rel, row in staged.items(): assert digest(crate / 'src' / rel) == row['generated_sha256'], rel
    binary = output / 'handplant-lifecycle-reference'
    if compile:shutil.copy2(target.resolve() / 'release/handplant-lifecycle-reference', binary)
    report.update(staged_host_original_prefixes=staged,
        extracted_observer_prefixes=[h_extract, a_extract],
        appended_core_observers={rel: dict(original_prefix_sha256=digest(source / rel),
            generated_sha256=digest(observed / rel), observer_sha256=hashlib.sha256(extra).hexdigest()) for rel, extra in core.items()},
        probe_sha256=digest(template), helper_sha256=digest(helper), binary_sha256=digest(binary)if compile else None,
        scope='Every production host/core body remains byte-for-byte original. Only explicit caller input setters, authored primitive transport and read-only owner observers append. No geometry/hit/pose/IK/callback substitute is present.')
    (output / 'reference-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    return binary

def build_native(output, *, compile=True):
    snapshot = output / 'native-source'
    if snapshot.exists(): shutil.rmtree(snapshot)
    snapshot.mkdir(); hashes = {}
    for p in [*sorted(CODE.glob('*.h')), *[CODE / (u + '.cpp') for u in UNITS]]:
        shutil.copy2(p, snapshot / p.name); hashes[p.name] = digest(snapshot / p.name)
    for name in ('handplant_probe.cpp', 'handplant_lifecycle_probe.cpp'):
        p = PLUGIN / 'Tests/Native' / name; shutil.copy2(p, snapshot / name); hashes[name] = digest(snapshot / name)
    binary = output / 'handplant-lifecycle-native'
    if compile:
        subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math',
            '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot),
            *[str(snapshot / (u + '.cpp')) for u in UNITS],
            str(snapshot / 'handplant_lifecycle_probe.cpp'), '-o', str(binary)], check=True)
    (output / 'native-provenance.json').write_text(json.dumps(dict(immutable_native_sources=hashes,
        units=UNITS, reused_probe='The complete unchanged numeric probe is included with its entry renamed solely to reuse wire/observation helpers. Its entry is never invoked.'), indent=2) + '\n')
    return binary

class Reader(numeric.Reader):
    def snapshot(self):
        assert self.word() == len(SECTIONS)
        result = {}; self.spans = {}
        for name in SECTIONS:
            size = self.word(); start = self.at; result[name] = self.take(size)
            self.spans[name] = [start, self.at]
        return result

def decode(raw, cases):
    r = Reader(raw); assert r.word() == len(cases); frames = []
    for c in cases:
        c['first_output_word'] = r.at
        assert r.word() == len(c['commands']); prior = r.snapshot(); c['initial_spans'] = r.spans.copy(); rows = []
        for command in c['commands']:
            at = r.at; op = r.word(); assert op == command[0]
            error = r.status(); target = r.take(16) if r.word() else None
            state = r.snapshot(); rows.append(dict(operation=op, error=error, target=target,
                state=state, prior=prior, first_word=at, last_word=r.at, spans=r.spans.copy())); prior = state
        c['last_output_word'] = r.at; frames.append(rows)
    assert r.at == len(r.words), (r.at, len(r.words))
    return frames

def handplant(raw):
    r = numeric.Reader(struct.pack('<' + 'I' * len(raw), *raw)); s = r.owner()
    assert r.at == len(raw); return s

def coverage(frames, cases):
    counts = Counter(); phases = set(); roots = set(); drives = set(); hands = set()
    known_retained_pending = 0
    identity = fs([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,0])
    ground_candidates = ground_launches = ground_enters = caller_enters = update_ok = failures = 0
    some = none = known = animated = captures = resets = anchor_errors = anchor_calls = 0; blends = set(); partial = 0; query_worlds = set(); velocities = set()
    genuine_launches=genuine_enters=genuine_updates=0
    for rows, case in zip(frames, cases):
        genuine=False;pose_kind=None
        for row, command in zip(rows, case['commands']):
            op = row['operation']; counts[OPS[op]] += 1
            s = row['state']; before = row['prior']; h = handplant(s['handplant']); old = handplant(before['handplant'])
            if op==1:pose_kind=command[1]
            if op == 2 and h['candidate']: ground_candidates += 1
            if op == 2:genuine=bool(case.get('metadata')and h['pending']and row['error']is None)
            if op == 3 and h['flags'] & 0x80000000:
                ground_launches += 1
                if genuine:
                    assert old['pending']and h['pending']is None and row['error']is None
                    genuine_launches+=1
            if op == 3:genuine=genuine and bool(h['flags']&0x80000000)and row['error']is None
            if op == 13:genuine=False
            if op == 4 and row['error'] is None:
                assert h['candidate'] and h['times'][1:3] == [0, 0]
                assert s['handplant'][-1] == 1
                if case['domain'] == 'ground':
                    ground_enters += 1
                    if genuine:genuine_enters+=1
                else: caller_enters += 1
                if case['domain'] == 'query_world': query_worlds.add(tuple(h['trajectories'][26:52]))
            if op == 5 and row['error'] is None:
                update_ok += 1
                if genuine:genuine_updates+=1
                phases.add(h['phase']); roots.add(tuple(s['roots']))
                drives.add(tuple(s['pose_drives'][-384:])); hands.add(tuple(s['ik']))
                assert s['publication'][0] & (1 << 19)
                assert s['publication'][7] == s['publication'][0]
                # Original collision_mode.rs visits [7,3,8,4,1], including
                # the head. GeneralUpdate does not retire these timers.
                assert h['effects'][24] == 1
                for part in (7, 3, 8, 4, 1):
                    assert h['effects'][25 + part] == 2
                    assert h['effects'][49 + part] == 0
            if row['error'] is not None:
                failures += 1
                if op in (5, 6, 10, 11):
                    assert s['roots'] != before['roots'] or s['bodies_blend'] != before['bodies_blend'] or s['publication'] != before['publication']
                    partial += 1
            if op == 6:
                anchor_calls+=1
                if row['error']is not None:
                    assert command[-1]==0xffffffff and pose_kind in(4,5)
                    assert row['error']=='IK original joint is absent from the current pose'
                    for section in('roots','bodies_blend','publication'):assert s[section]!=before[section]
                    for section in('ik','physical_record','drive_owner','adjustment'):assert s[section]==before[section]
                    assert s['pose_drives']==before['pose_drives']
                    anchor_errors+=1
                elif command[-1] == 0xffffffff:none+=1
                else:
                    some += 1
                    # An anchored limb must retain all seven dynamic board
                    # bodies; only the distinct animation hook changes.
                    start = 5 + 16 + 8 + 40
                    assert s['bodies_blend'][start:start + 7 * 40] == before['bodies_blend'][start:start + 7 * 40]
            if op == 11 or (op == 6 and command[-1] == 0xffffffff):
                start = 5 + 16 + 8 + 40
                board = s['bodies_blend'][start:start + 7 * 40]
                previous_board = before['bodies_blend'][start:start + 7 * 40]
                live = [tuple(board[index * 40 + 26:index * 40 + 29]) for index in range(7)]
                assert len(set(live)) == 1, 'all seven dynamic bodies receive the source target velocity'
                velocities.add(live[0])
                for index in range(7):
                    base = index * 40
                    assert board[base:base + 26] == previous_board[base:base + 26]
                    assert board[base + 29:base + 40] == previous_board[base + 29:base + 40]
            if op == 10:
                animated += 1
                if row['error'] is None: assert s['pose_drives'][545:561] == identity
                else: assert s['pose_drives'][545:561] == before['pose_drives'][545:561]
            if op == 11:
                known += 1
                assert s['pose_drives'][545:561] == before['pose_drives'][545:561]
                if s['pose_drives'][545:561] != identity: known_retained_pending += 1
            if op in (5,6) and row['error'] is None:
                assert s['pose_drives'][545:561] == identity
            if op == 8: captures += 1
            if op == 9:
                assert s['bodies_blend'][:4] == fs([0, 0, 0, 1])
                assert s['bodies_blend'][4] == before['bodies_blend'][4]
                resets += 1
            blends.add(tuple(s['bodies_blend'][:5]))
    assert ground_candidates >= 4 and ground_launches >= 4 and ground_enters >= 4
    assert genuine_launches>=4 and genuine_enters>=4 and genuine_updates>128,(genuine_launches,genuine_enters,genuine_updates)
    assert len(query_worlds) >= 2, 'real world query must distinguish floor admission from empty-world fallback'
    assert caller_enters >= 16 and update_ok > 1000
    assert len(phases) > 64 and len(roots) > 128 and len(drives) > 128 and len(hands) > 128
    assert len(velocities) > 64
    assert known_retained_pending >= 96
    assert some == none == 48 and anchor_errors==8 and anchor_calls==104
    assert known >= 96 and animated >= 128
    assert failures >= 40 and partial >= 24 and captures > 64 and resets > 32 and len(blends) > 32
    return dict(operations=dict(counts),ground_candidates=ground_candidates,ground_launches=ground_launches,
        ground_enters=ground_enters,genuine_metadata_launches=genuine_launches,genuine_metadata_enters=genuine_enters,genuine_metadata_updates=genuine_updates,distinct_real_query_world_outgoing=len(query_worlds),caller_domain_enters=caller_enters,successful_updates=update_ok,
        distinct_phases=len(phases),distinct_roots=len(roots),distinct_drives=len(drives),distinct_ik=len(hands),
        anchored_bone=some,anchored_com=none,failed_com_anchors=anchor_errors,total_anchor_calls=anchor_calls,animated_air=animated,known_air=known,known_air_retained_pending=known_retained_pending,distinct_dynamic_board_target_velocities=len(velocities),
        failures=failures,partial_write_failures=partial,captured_errors=captures,selective_blend_resets=resets,blend_histories=len(blends))

def validate_probe_extensions():
    # Reconstruct the exact old lifecycle adapters by removing only the
    # additive sentinel dispatch; old bodies, opcodes and observations persist.
    native=PLUGIN/'Tests/Native/handplant_lifecycle_probe.cpp'
    first=native.read_text().index('    // Additive metadata-world sentinel.')
    last=native.read_text().index('    std::vector<PlayerGrindPrimitive> edges;',first)
    segment=native.read_text()[first:last]
    restored=native.read_text()[:first]+'    auto world = World(i);\n'+native.read_text()[last:]
    assert hashlib.sha256(restored.encode()).hexdigest()=='c56a3d6701b482a247f4763cc3483f2a6b45fca701fe0e3a7f83dbc16cbc65a8'
    reference=PLUGIN/'Tests/Reference/handplant_lifecycle_observer.rs'
    branch='let world_header=i.word();i.at-=4;physics.world=if world_header==u32::MAX{i.word();authored_query_world(i)}else{world(i)};'
    assert reference.read_text().count(branch)==1
    restored=reference.read_text().replace(branch,'physics.world=world(i);')
    assert hashlib.sha256(restored.encode()).hexdigest()=='6de4471fb51a44a39f88749074eba0000b1b5314aaa47e4c63506f0e652df9cf'
    return dict(old_native_sha256='c56a3d6701b482a247f4763cc3483f2a6b45fca701fe0e3a7f83dbc16cbc65a8',
        old_reference_helper_sha256='6de4471fb51a44a39f88749074eba0000b1b5314aaa47e4c63506f0e652df9cf',
        native_append_sha256=hashlib.sha256(segment.encode()).hexdigest(),reference_append_sha256=hashlib.sha256(branch.encode()).hexdigest(),
        reused_metadata_transport=numeric.validate_probe_extensions())

def preflight(raw, cases):
    words = struct.unpack('<' + 'I' * (len(raw) // 4), raw); at = 1; ranges = []
    for c in cases:
        start = at * 4
        metadata=words[at]==0xffffffff
        if metadata:at+=1
        n = words[at]; at += 1 + 18 * n
        if metadata:
            surfaces=words[at];at+=1+surfaces
            meshes=words[at];at+=1+12*meshes
            at+=1
        assert metadata==c.get('metadata',False)
        n = words[at]; at += 1 + 10 * n
        assert words[at] == len(c['commands']); at += 1
        lengths = (34,2,1,1,1,1,6,7,1,1,2,7,2,2,36,17)
        for command in c['commands']:
            assert len(command) == lengths[command[0]], (c['index'],command)
            assert list(words[at:at + len(command)]) == command; at += len(command)
        ranges.append((start, at * 4))
    assert at == len(words), (at, len(words))
    for unit in UNITS: assert (CODE / (unit + '.cpp')).is_file(), unit
    assert len(UNITS) == len(set(UNITS))
    return ranges

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('assets', 'samples', 'output', 'target-dir'): p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--preflight', action='store_true')
    p.add_argument('--reference-case-runner', action='store_true', help='Run unchanged independent original cases under their own identified 2 GiB guards')
    p.add_argument('--reference-workers', type=int, choices=(1,2,3,4), default=1, help='Root-selected measured capacity; used only with --reference-case-runner')
    a = p.parse_args()
    if not a.reference_case_runner and a.reference_workers != 1:
        p.error('--reference-workers requires --reference-case-runner')
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=True); inputs, cases = corpus(); ranges = preflight(inputs, cases); wire_audit=validate_probe_extensions()
    (out / 'input.bin').write_bytes(inputs); (out / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    if a.preflight:
        build_reference(out/'reference',a.target_dir,compile=False);build_native(out,compile=False)
        paths=[PLUGIN/'Tests/check_handplant_lifecycle_parity.py',PLUGIN/'Tests/Native/handplant_lifecycle_probe.cpp',PLUGIN/'Tests/Reference/handplant_lifecycle_probe.rs',PLUGIN/'Tests/Reference/handplant_lifecycle_observer.rs']
        report=dict(cases=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(inputs),units=len(UNITS),input_sha256=hashlib.sha256(inputs).hexdigest(),preserved_baseline_sha256=BASELINE_INPUT_SHA256,preserved_baseline_streams=25,preserved_baseline_commands=4132,authored_metadata_worlds=sum(bool(c.get('metadata'))for c in cases),wire_audit=wire_audit,frozen_proof={p.relative_to(PLUGIN).as_posix():digest(p)for p in paths})
        (out/'frozen-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return
    fixtures = out / 'fixtures'; fixtures.mkdir(exist_ok=True); stock = a.assets.resolve() / 'private/stock'
    (fixtures / 'settings.native').write_bytes(converter.encode_settings(stock / 'skater-collections.json'))
    (fixtures / 'physics.native').write_bytes(converter.encode_physics_skeletons(stock / 'physics-skeletons.json'))
    for kind in ('action', 'motion'): (fixtures / f'actor.{kind}.reference').write_bytes(original_graph(element('state', 'idle')))
    identity = json.loads((stock / 'physics-skeletons.json').read_text())['source_sha256']
    reference = build_reference(out / 'reference', a.target_dir); native = build_native(out)
    if a.reference_case_runner:
        from copy import deepcopy
        from reference_case_runner import run_reference_cases
        expected = run_reference_cases(reference, [a.assets.resolve(),fixtures], inputs, ranges,
            out / 'reference-cases', workers=a.reference_workers,
            validate_output=lambda index, raw: decode(raw, [deepcopy(cases[index])]))
    else:
        expected = subprocess.check_output([str(reference),str(a.assets.resolve()),str(fixtures)],input=inputs)
    actual = subprocess.check_output([str(native),str(fixtures / 'settings.native'),str(fixtures / 'physics.native'),str(a.samples.resolve() / 'native/rig.skate'),identity,str(a.assets.resolve())],input=inputs)
    (out / 'reference.bin').write_bytes(expected); (out / 'native.bin').write_bytes(actual)
    frames = decode(expected,cases)
    if expected != actual:
        at = next((i for i,(x,y) in enumerate(zip(expected,actual)) if x != y),min(len(expected),len(actual)))
        word = at // 4
        case = next((c for c in cases if c['first_output_word'] <= word < c['last_output_word']),None)
        row = next((r for rows in frames for r in rows if r['first_word'] <= word < r['last_word']),None)
        spans = row['spans'] if row else (case['initial_spans'] if case else {})
        section = next(((name, word - span[0]) for name,span in spans.items() if span[0] <= word < span[1]),None)
        owner = dict(case=case['index'] if case else None,operation=row['operation'] if row else 'initial',section=section)
        failure = dict(byte=at,word=at//4,reference_bytes=len(expected),native_bytes=len(actual),nearby_row=owner,
            reference_hex=expected[max(0,at-16):at+32].hex(),native_hex=actual[max(0,at-16):at+32].hex())
        (out / 'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n'); raise AssertionError(failure)
    result = dict(passed=True,reference_revision=REFERENCE_REVISION,cases=len(cases),commands=sum(len(c['commands']) for c in cases),
        bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(inputs).hexdigest(),coverage=coverage(frames,cases),
        scope='Complete Handplant Enter/Update and PlantSkeleton scheduling with actual outgoing WorldGeometry/SAT trajectory query, AirReckoning, adjusted stock hierarchy, FootIK, GeneralUpdate, board/skeleton/hook/drive owners and full SkeletonAir capture/reset/animated/known methods. Exact retained fields, flags, order and partial-write failures.',
        preserved_baseline=dict(streams=25,commands=4132,input_sha256=BASELINE_INPUT_SHA256),wire_audit=wire_audit,
        boundaries='Authored primitive transport fills the actual StaticProvider primitive vector in source order; Handplant does not read its octree or metadata. Processed physical/player state fields, pending trajectory requests, world triangles and explicit caller coping cases are upstream inputs. Pose hierarchy, surface investigations, trajectory hits, reckoning, skeleton/IK and board effects are live original/native producers. The global frame/state selector, actual trajectory admission batch and shared solve scheduling remain separate. Info-only filtered logging is not asserted.')
    if a.reference_case_runner:
        result['reference_execution'] = dict(strategy='exact independent outer cases, original constructors per case',
            workers=a.reference_workers,worker_limit_bytes=2*1024**3,report='reference-cases/result.json')
    (out / 'result.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2))

if __name__ == '__main__': main()
