#!/usr/bin/env python3
"""Latest pinned whole Session and exact transfer/VertAssist owner comparison.

The accepted historical Session proof is unchanged. Original source is read
from immutable Git pin1536531; only the five changed compiled host prefixes are
replaced in a fresh historical staging tree, with complete latest bodies and
append-only observation/visibility adapters. Actual world, input, graphs,
animation, contacts, solve, trajectory, camera and scoring owners run together.
All stock assets and native packages remain supplied caller resources.

--preflight stages and hashes only. --run-under-root-guard compiles and executes
and MUST be invoked by the root render/memory guard. Outputs are streamed into
files and compared byte-for-byte before bounded mmap witness decoding. Raw
packets, triangle/rail resources, tuning and Session launch momentum are the
only producer inputs. The small footer calls the unchanged actual newest
vert_departure helper, including thresholds and exceptional float words. No
completed prediction/contact/physical/pose/clock record is injected. OS polling,
asynchronous thread timing and pipe JSON parsing remain external boundaries.
"""
import argparse
from collections import Counter
import copy
import hashlib
import io
import json
import math
import mmap
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile

import check_gameplay_session_parity as session
import historical_oracle

PLUGIN, CODE, TESTS = session.PLUGIN, session.CODE, session.TESTS
ROOT = historical_oracle.ROOT
OWNED = (Path(__file__), TESTS/'Native/latest_gameplay_session_probe.cpp',
         TESTS/'Reference/latest_gameplay_session_probe.rs',
         TESTS/'Reference/latest_gameplay_session_observer.rs')

PIN = '1536531c6e03c72d3c232614141500419059ca2e'
TREE = 'e68b1819e00bc8a5295938c4993d764077c41d98'
BASE_PIN = historical_oracle.REFERENCE_COMMIT
SOURCE = historical_oracle.SOURCE_GIT_PATH
HOST = 'crates/skate-host/src/'
COMPILED_CHANGES = tuple(HOST + rel for rel in (
    'physics.rs', 'physics/input_phase.rs', 'physics/air_trajectory/mod.rs',
    'physics/air_trajectory/vert_departure.rs', 'physics/bridge.rs'))
PIPE_MAIN = 'atelier-host/src/main.rs'
CHANGES = (*COMPILED_CHANGES, PIPE_MAIN)
SECTIONS = (*session.SECTIONS, 'latest')
TRANSFER = 0x0800


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1',
               GIT_OPTIONAL_LOCKS='0')
    result = subprocess.run(['git', *args], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise historical_oracle.HistoricalOracleError(
            'Latest pinned oracle objects are unavailable: '+PIN+'. Obtain the '
            'commit/source objects explicitly from the configured remote; no '
            'automatic fetch or HEAD fallback is allowed. Git operation: '
            +' '.join(args)+'. '+historical_oracle.TOOLCHAIN_GUIDANCE)
    return result.stdout


def latest_originals():
    assert git('rev-parse', '--verify', PIN + '^{commit}').decode().strip() == PIN
    assert git('rev-parse', '--verify', PIN + ':' + SOURCE).decode().strip() == TREE
    changed = git('diff', '--name-only', BASE_PIN, PIN, '--', SOURCE).decode().splitlines()
    assert set(changed) == {SOURCE + '/' + rel for rel in CHANGES}, changed
    archive = git('archive', PIN + ':' + SOURCE)
    payload = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for entry in tar:
            path = Path(entry.name)
            assert not path.is_absolute() and '..' not in path.parts
            if entry.isfile():
                payload[entry.name] = tar.extractfile(entry).read()
            else:
                assert entry.isdir(), entry.name
    for rel in CHANGES:
        assert payload[rel] != historical_oracle.source_bytes(rel), rel
    return payload, dict(reference_commit=PIN, source_git_path=SOURCE,
                         source_tree=TREE, source_archive_sha256=sha(archive),
                         exact_changed_paths=list(CHANGES))


def destination(out, rel):
    if rel.startswith(HOST):
        return out / 'observed-source/atelier-host/src' / rel.removeprefix(HOST)
    return out / 'observed-source' / rel


def original_step(main):
    at = main.index('                elapsed = (elapsed + dt).min(0.1);')
    end = main.index('                // Also acknowledge sub-tick', at)
    step = main[at:end]
    publish = session.frame.function(main, 'fn publish(')
    at = publish.index('    if !p.root.is_finite()')
    end = publish.index('    let (score, reward, trick)', at)
    return step, publish[at:end]


def stage_reference(out, target, payload, identity):
    session.build_reference(out, target, compile=False)
    old_report = json.loads((out / 'reference-provenance.json').read_text())
    (out / 'baseline-reference-provenance.json').write_text(json.dumps(old_report, indent=2) + '\n')
    original = out / 'reference-source'
    if not original.is_dir():
        original = out / 'original-source'
    latest = out / 'latest-original-source'
    if latest.exists():
        shutil.rmtree(latest)
    latest.mkdir()
    for rel, data in payload.items():
        p = latest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    overlays = {}
    for rel in COMPILED_CHANGES:
        p = destination(out, rel)
        old = (original / rel).read_bytes()
        before = p.read_bytes()
        assert before.startswith(old), rel
        tail = before[len(old):]
        p.write_bytes(payload[rel] + tail)
        overlays[rel] = dict(base_original_sha256=sha(old), latest_original_sha256=sha(payload[rel]),
            latest_original_bytes=len(payload[rel]), observer_tail_before_sha256=sha(tail))

    # The latest Session snapshot additionally observes the retained trajectory
    # owner. Borrow the accepted Footplant data-only observer and its paired
    # private-stage getter after the complete original modules, never in place
    # of the latest host body or the unchanged core selector body.
    trajectory_observer = TESTS/'Reference/footplant_trajectory_observer.rs'
    footplant_builder = TESTS/'check_footplant_parity.py'
    selector_stage = b'\nimpl TrajectorySelector {pub fn migration_footplant_stage(&self)->[u32;2]{[u32::from(self.pass),u32::from(self.adjusted_on_vert)]}}\n'
    assert repr(selector_stage) in footplant_builder.read_text()
    trajectory_extensions = {}
    for rel, extra, method, origin in (
        (HOST+'physics/air_trajectory/mod.rs', b'\n'+trajectory_observer.read_bytes(),
         b'fn migration_footplant_trace(', trajectory_observer),
        ('crates/skate-core/src/air/trajectory/selector.rs', selector_stage,
         b'fn migration_footplant_stage(', footplant_builder),
    ):
        path = destination(out, rel)
        raw = path.read_bytes()
        assert raw.startswith(payload[rel]), rel
        assert method not in raw[len(payload[rel]):], rel
        path.write_bytes(raw+extra)
        trajectory_extensions[rel] = dict(
            original_prefix_sha256=sha(payload[rel]),
            observer_source=str(origin.relative_to(PLUGIN)),
            observer_source_sha256=session.digest(origin),
            appended_sha256=sha(extra))

    # Remove only the inherited unused frame-test entry. Its four-scalar Tune
    # transport is historical, and the actual latest Session has five scalars.
    # Keeping this unused method would still fail Rust type checking. The
    # complete original bridge prefix and all snapshot observers stay intact.
    bridge = destination(out, HOST+'physics/bridge.rs')
    prefix = payload[HOST+'physics/bridge.rs']
    text = bridge.read_text()
    unused = session.frame.function(text,'pub(crate)fn migration_gameplay_run(')
    at = text.index(unused)
    assert at >= len(prefix.decode()) and text.count(unused)==1
    bridge.write_text(text[:at]+text[at+len(unused):])
    removed = dict(file=HOST+'physics/bridge.rs', removed_sha256=sha(unused.encode()),
                   scope='Unused appended historical frame-test driver only; actual newest Session driver retained.')
    step,finite = original_step(payload[PIPE_MAIN].decode())
    base_step,base_finite = original_step(historical_oracle.source_text(PIPE_MAIN))
    assert step==base_step and finite==base_finite
    old = (TESTS/'Reference/gameplay_session_observer.rs').read_text()
    new = OWNED[3].read_text()
    declaration='if !dt.is_finite() || dt < 0. { return Err("Invalid frame interval".into()); }\n'
    for kind in ('old','new'):
        value=old if kind=='old' else new
        value=session.once(value,' // @ORIGINAL_HOST_STEP',declaration+step)
        value=session.once(value,' // @ORIGINAL_PUBLISH_FINITE_GATE',finite)
        if kind=='old':old=value
        else:new=value
    previous=session.sections(old)
    for rel,extra in session.sections(new).items():
        path=out/'observed-source/atelier-host/src'/rel
        raw=path.read_bytes()
        if rel in previous:
            old_tail=('\n'+previous[rel]).encode()
            assert raw.endswith(old_tail),rel
            raw=raw[:-len(old_tail)]
        path.write_bytes(raw+('\n'+extra).encode())
    template=OWNED[2].read_text()
    parent=(TESTS/'Reference/gameplay_runtime_probe.rs').read_text()
    helpers=parent[:parent.index('fn main()->Result<(),String>{')]
    template=session.once(template,
        '//! Actual newest pinned bridge Session and marker runtime; no completed producers.\n// @GAMEPLAY_PROBE_PREFIX',helpers)
    (out/'observed-source/atelier-host/src/migration_probe.rs').write_text(template)
    base_main = historical_oracle.source_text(PIPE_MAIN)
    step, finite = original_step(payload[PIPE_MAIN].decode())
    base_step, base_finite = original_step(base_main)
    assert step == base_step and finite == base_finite
    assert step in bridge.read_text() and finite in bridge.read_text()
    main = payload[PIPE_MAIN].decode()
    # This retained pipe source is not the Cargo probe entry point. Keep its
    # complete latest body for independent command/default and cadence audit.
    destination(out, PIPE_MAIN).write_bytes(payload[PIPE_MAIN])
    assert main.count('vert_assist: f32') == 2
    assert main.count('session.tune(pop, spin, push_speed, push_power, vert_assist)') == 2
    assert 'fn hosts_without_the_vert_assist_keep_the_original()' in main
    assert 'assert_eq!(vert_assist, 0.);' in main
    cargo = out / 'observed-source/atelier-host/Cargo.toml'
    cargo.write_text(session.once(cargo.read_text(), 'name="gameplay-session-reference"',
                                 'name="latest-gameplay-session-reference"'))

    prefixes = {}
    for rel in old_report['original_source_sha256']:
        raw = payload[rel]
        assert sha((latest / rel).read_bytes()) == sha(raw)
        if rel not in CHANGES:
            assert sha(raw) == old_report['original_source_sha256'][rel], rel
        if rel.startswith(HOST) and rel.endswith(('/lib.rs', '/main.rs')):
            continue
        p = destination(out, rel)
        assert p.read_bytes().startswith(raw), rel
        prefixes[rel] = dict(original_sha256=sha(raw), original_bytes=len(raw),
                            appended_sha256=sha(p.read_bytes()[len(raw):]),
                            generated_sha256=session.digest(p))
    report = dict(**identity, reference_revision=PIN, baseline_reference_commit=BASE_PIN,
        baseline_reference_provenance_sha256=session.digest(out / 'baseline-reference-provenance.json'),
        original_source_sha256={rel:sha(payload[rel]) for rel in old_report['original_source_sha256']},
        latest_original_prefixes=prefixes, compiled_body_overlays=overlays,
        pipe_main=dict(original_sha256=sha(payload[PIPE_MAIN]), cadence_sha256=sha(step.encode()),
                       pose_finite_gate_sha256=sha(finite.encode()),
                       scope='Latest command/default/tune source body retained whole; cadence and finite gate unchanged.'),
        removed_unused_appended_driver=removed,
        retained_trajectory_observer_extensions=trajectory_extensions,
        latest_bridge_append_sha256=sha(bridge.read_bytes()[len(prefix):]),
        proof_templates_sha256={str(q.relative_to(PLUGIN)):session.digest(q) for q in OWNED},
        generated_probe_sha256=session.digest(out / 'observed-source/atelier-host/src/migration_probe.rs'),
        scope=__doc__)
    (out / 'reference-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def stage_native(out, overlay):
    session.build_native(out, compile=False)
    base = json.loads((out / 'native-provenance.json').read_text())
    (out / 'baseline-native-provenance.json').write_text(json.dumps(base, indent=2) + '\n')
    snapshot = out / 'native-source'
    changes = {}
    if overlay is not None:
        manifest_path = overlay.parent / 'draft-manifest.json'
        manifest = json.loads(manifest_path.read_text())
        assert manifest['source_pin'] == PIN
        assert manifest['live_source_preserved'] is True
        rows = {row['basename']:row for row in manifest['files'] if row['overlay_path'] is not None}
        assert len(rows) == 8
        for name, row in rows.items():
            assert Path(name).name == name and Path(name).suffix in ('.h', '.cpp')
            p = snapshot / name
            assert session.digest(p) == row['base_sha256'], name
            replacement = overlay / name
            assert session.digest(replacement) == row['patched_sha256'], name
            p.write_bytes(replacement.read_bytes())
            changes[name] = dict(**row, staged_sha256=session.digest(p))
    if overlay is None:
        assert 'std::optional<bool> transfer' in (snapshot/'PhysicalSimulationRuntime.h').read_text(), 'Latest production is not applied; use an explicit ignored native overlay for staging.'
        assert 'float vert_assist' in (snapshot/'AirTrajectoryRuntime.h').read_text()
    shutil.copy2(OWNED[1],snapshot/OWNED[1].name)
    report = dict(reference_commit=PIN, baseline_reference_commit=BASE_PIN,
        baseline_native_provenance_sha256=session.digest(out / 'baseline-native-provenance.json'),
        latest_native_overlays=changes, latest_candidate_ready=True,
        ignored_overlay_manifest_sha256=session.digest(manifest_path) if overlay is not None else None,
        units=list(session.UNITS),
        snapshot_sources={p.name:session.digest(p) for p in sorted(snapshot.iterdir()) if p.is_file()},
        scope='Source-derived accepted Session snapshot plus explicit ignored latest production overlay; local data-only observer and tune transport changes.')
    (out / 'native-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def tune(assist, pop=1.5, spin=1., speed=1., power=1.):
    return [7, *session.fs([pop, spin, speed, power, assist])]


def slope_world(degrees, pipe=False):
    # Fixed authored world, source convention Y-up. Strip winding faces up and
    # inward. Quarter endpoints derive from this generator, never from outputs.
    radius, width = 5.5, 9.
    count = int(degrees / 5)
    curve = [(radius * math.sin(math.radians(degrees * k / count)),
              radius * (1. - math.cos(math.radians(degrees * k / count))))
             for k in range(count + 1)]
    if pipe:
        profile = [(-8. - z, y) for z, y in reversed(curve)] + [(8. + z, y) for z, y in curve]
    else:
        profile = [(-30., 0.), (0., 0.)] + curve[1:]
    triangles = []
    for (z0, y0), (z1, y1) in zip(profile, profile[1:]):
        a, b, c, d = [-width,y0,z0],[-width,y1,z1],[width,y1,z1],[width,y0,z0]
        triangles.extend(([a,b,c],[a,c,d]))
    # Actual authored coping is queried by the unchanged source provider.
    rails = [[[-8.,y,z],[8.,y,z]] for z,y in (profile[0],profile[-1]) if y > 0.]
    return dict(triangles=triangles, rails=rails)


def corpus():
    old = session.corpus()
    cases = copy.deepcopy(old)
    preserved = []
    for before, after in zip(old, cases):
        assert {k:v for k,v in before.items() if k!='rows'} == {
            k:v for k,v in after.items() if k!='rows'}
        for a, b in zip(before['rows'], after['rows']):
            if a[0] == 7:
                b.append(session.bits(0.))
                assert b[:-1] == a and b[-1] == 0
            else:
                assert b == a
        preserved.append(dict(index=before['index'], commands=len(before['rows']),
                              legacy_rows_sha256=sha(json.dumps(before['rows'],separators=(',',':')).encode())))
    # Scope first checks exact source lifetime and all tune rejection prefixes
    # on ordinary stock resources before adding the authored slope histories.
    rows = [session.collect(0,triggers=(255,255)),[3],[11],tune(0), [11], session.tick(buttons=TRANSFER), [11], session.tick(),
            session.tick(triggers=(255,255)), session.collect(1,buttons=TRANSFER),
            [3], session.collect(2,triggers=(255,255)), [3], [4], [11]]
    for assist in (0., -.0, .5, 1.):
        rows += [tune(assist),session.tick(buttons=TRANSFER),session.tick(),[11]]
    for assist in (-.0001,1.0001,float('inf'),float('-inf')):
        rows += [tune(assist),[11]]
    for word in (0x7fc12345,0xffc54321):
        rows += [[7,*session.fs([1.,1.,1.,1.]),word],[11]]
    rows += [tune(.5,pop=.49),tune(.5,spin=3.01),tune(.5,speed=.49),tune(.5,power=3.01),
             [5,session.bits(0.),*session.xbox(buttons=TRANSFER)],
             [5,0x7fc12345,*session.xbox(buttons=TRANSFER)],[11],session.activate(generation=99)]
    cases.append(dict(index=len(cases),scenario='latest-transfer-lifetime-and-five-scalar-tune',
                      world=session.world(),spawn=[0,0,0],heading=0,rows=rows))
    for degrees,assists in ((60,(0.,1.)),(70,(0.,.5,1.)),(80,(0.,1.)),(90,(0.,1.))):
        for assist in assists:
            goofy=len(cases)%2
            rows = [session.configure(goofy),tune(assist),session.activate(z=-4.,generation=1),
                    *[session.tick() for _ in range(40)],[8,*session.fs([0,0,15])]]
            for k in range(176):
                # Grab is a trigger producer. Transfer is an independent host
                # bit, alternated without changing the simultaneous grab.
                buttons = TRANSFER if (k//8)%2 and 16<=k<112 else 0
                triggers = (255,255) if 8<=k<96 else (0,0)
                right = (0,-32768) if 14<=k<20 else (0,32767) if 20<=k<24 else (0,0)
                left = (0,32767) if k<72 else (0,-32768) if k<112 else (0,0)
                rows.append(session.tick(buttons=buttons,triggers=triggers,left=left,right=right))
            rows += [[11],session.activate(z=-4.,generation=2),[8,*session.fs([0,0,10])],
                     *[session.tick(triggers=(255,0),buttons=TRANSFER if k%3==0 else 0)
                       for k in range(48)],[11]]
            cases.append(dict(index=len(cases),scenario='authored-quarter-'+str(degrees)+'-grab-pump-transfer',
                              degrees=degrees,assist=assist,goofy=goofy,world=slope_world(degrees),
                              spawn=[0,0,-4],heading=0,rows=rows))
    for assist in (0.,1.):
        goofy=len(cases)%2
        rows = [session.configure(goofy),tune(assist),*[session.tick() for _ in range(40)],
                [8,*session.fs([0,0,17])]]
        for k in range(240):
            rows.append(session.tick(buttons=TRANSFER if 24<=k<56 or 112<=k<152 else 0,
                triggers=(255,255) if k%48<32 else (0,0),
                left=(0,32767) if k%96<48 else (0,-32768),
                right=(0,-32768) if k%60<6 else (0,32767) if k%60<10 else (0,0)))
        rows += [[11],tune(0.),session.tick(),[11]]
        cases.append(dict(index=len(cases),scenario='authored-full-pipe-grab-pump-transfer',
                          degrees=90,assist=assist,goofy=goofy,world=slope_world(90,pipe=True),
                          spawn=[0,0,0],heading=0,rows=rows))
    for name,degrees,assist,velocity in (('carve',70,.5,[4,0,14]),('kicker',25,1.,[0,0,12])):
        goofy=len(cases)%2;world=slope_world(degrees)
        if name=='kicker':
            a,b,c,d=[-9,0,10],[-9,0,35],[9,0,35],[9,0,10]
            world['triangles'] += [[a,b,c],[a,c,d]]
        rows=[session.configure(goofy),tune(assist),session.activate(z=-4.,generation=1),
              *[session.tick() for _ in range(32)],[8,*session.fs(velocity)]]
        for k in range(144):
            rows.append(session.tick(buttons=TRANSFER if 28<=k<56 else 0,
                triggers=(255,0) if 12<=k<64 else (0,0),
                left=((16000 if k%48<24 else -16000) if name=='carve' else 0,32767 if k<80 else 0),
                right=(0,-32768) if 16<=k<22 else (0,32767) if 22<=k<26 else (0,0)))
        rows += [[11],*[session.tick() for _ in range(24)],[11]]
        cases.append(dict(index=len(cases),scenario='authored-'+name+'-grab-pump-transfer',
                          degrees=degrees,assist=assist,goofy=goofy,world=world,
                          spawn=[0,0,-4],heading=0,rows=rows))
    return cases, preserved


def leaf_corpus():
    leaves=[]
    def add(label,normal,velocity,direction,assist):
        if len(velocity)==3:velocity=[*velocity,0.]
        assert len(normal)==4 and len(velocity)==4
        leaves.append(dict(index=len(leaves),label=label,words=[*session.fs(normal),*session.fs(velocity),session.bits(direction),session.bits(assist)]))
    for normal in ([0,.4,-1,0],[.7,.3,-.7,.1],[0,0,-1,0],[0,1,0,1]):
        for velocity in ([0,15,10],[0,15,-10],[1,0,1]):
            for direction in (struct.unpack('<f',struct.pack('<I',0x3effffff))[0],.5,struct.unpack('<f',struct.pack('<I',0x3f000001))[0]):
                for assist in (0.,.5,1.):
                    add('source gate/direction/assist',normal,velocity,direction,assist)
    for field,value in (('horizontal',1e-6),('near_vertical_y',.25),('near_vertical_horizontal',.9),('reach_y',.45),('reach_y',.65)):
        word=session.bits(value)
        for adjacent in (word-1,word,word+1):
            v=struct.unpack('<f',struct.pack('<I',adjacent))[0]
            for assist in (0.,.5,1.):
                normal=[0,.4,-1,0]
                if field=='horizontal':normal=[0,.4,-v,0]
                elif field.endswith('_y'):normal[1]=v
                else:normal[2]=-v
                add(field+'/adjacent-f32',normal,[0,15,10],0.,assist)
    base=[*session.fs([0,.4,-1,0]),*session.fs([0,15,10,0]),session.bits(0.),session.bits(1.)]
    for slot in range(10):
        for word in (0,0x80000000,0x7f800000,0xff800000,0x7fc12345,0xffc54321,0x7f812345,0xff812345):
            values=list(base);values[slot]=word
            leaves.append(dict(index=len(leaves),label='exceptional word in source parameter '+str(slot),words=values))
    return leaves


def protocol_audit(raw, cases, ranges, leaves):
    words = struct.unpack('<'+'I'*(len(raw)//4),raw)
    at, counts = 0, Counter()
    def take(n):
        nonlocal at
        assert at+n <= len(words)
        result = words[at:at+n]
        at += n
        return result
    def word():
        return take(1)[0]
    def snapshot():
        take(word()*9)
        for _ in range(word()):
            take(word()*3)
    assert word() == len(cases)
    for case,(start,end) in zip(cases,ranges):
        assert at*4 == start
        snapshot();take(4)
        assert word() == len(case['rows'])
        for row in case['rows']:
            begin=at;op=word();counts[session.OPS[op]]+=1
            if op==0:take(5)
            elif op==1:take(7)
            elif op==2:
                take(1)
                for _ in range(4):
                    kind=word();take(9 if kind==0 else 1)
            elif op==5:take(8)
            elif op==6:take(word());take(2)
            elif op==7:take(5)
            elif op==8:take(3)
            elif op==9:take(1)
            elif op==10:snapshot()
            assert list(words[begin:at]) == row,(case['index'],op)
        assert at*4==end
    assert word()==len(leaves)
    for leaf in leaves:
        assert list(take(10))==leaf['words']
        counts['vert_departure_leaf']+=1
    assert at == len(words)
    return dict(counts)


class WireReader:
    """Byte offsets into a mapping; no whole-stream word list or pose copies."""
    def __init__(self, data, begin=0, end=None):
        self.data, self.at = data, begin
        self.end = len(data) if end is None else end
    def word(self):
        assert self.at + 4 <= self.end, (self.at, self.end)
        value = struct.unpack_from('<I', self.data, self.at)[0]
        self.at += 4
        return value
    def wide(self):
        return self.word() | (self.word() << 32)
    def take(self, n):
        assert n >= 0 and self.at + 4*n <= self.end
        result = struct.unpack_from('<'+'I'*n, self.data, self.at)
        self.at += 4*n
        return result
    def skip(self, n):
        assert n >= 0 and self.at + 4*n <= self.end
        self.at += 4*n
    def boolean(self):
        value = self.word()
        assert value in (0,1)
        return bool(value)
    def status(self):
        okay = self.boolean()
        return dict(okay=okay, error='' if okay else bytes(self.take(self.word())).decode())
    def sections(self, names):
        assert self.word() == len(names)
        spans = {}
        for name in names:
            n = self.word()*4
            assert self.at+n <= self.end
            spans[name] = (self.at,self.at+n)
            self.at += n
        return spans
    def finish(self):
        assert self.at == self.end, (self.at,self.end)


def trajectory_owner(r):
    names=('pending','valid','just_changed','all_predictions_missed',
           'grind_locked_to_middle','adjusted_on_vert')
    out={name:r.boolean() for name in names}
    out.update(pass_index=r.word(),selected_index=r.word())
    out['launch_info']=r.take(70) if r.boolean() else None
    requests=r.word()
    assert requests <= 7, requests
    out['requests']=[r.take(16) for _ in range(requests)]
    out['selection']=r.take(81) if r.boolean() else None
    out['pending_results']=None
    if r.boolean():
        n=r.word();assert n <= 7,n
        out['pending_results']=[r.take(32) for _ in range(n)]
    out['provider']=r.boolean()
    out['nearby']=r.take(r.word())
    return out


def latest_owner(data, span):
    r=WireReader(data,*span)
    out={'transfer':r.boolean() if r.boolean() else None,'assist_word':r.word(),
         'ticks':r.wide(),'state':r.word(),'processed_state':r.word(),
         'processed_previous_state':r.word(),'transition_word':r.word(),
         'ground_normal':r.take(4),'processed_velocity':r.take(4),
         'deck_velocity':r.take(3),'trajectory':trajectory_owner(r)}
    r.finish()
    return out


def float_word(word):
    return struct.unpack('<f',struct.pack('<I',word))[0]


def spans_equal(data, a, b):
    if a[1]-a[0] != b[1]-b[0]:
        return False
    for offset in range(0,a[1]-a[0],1<<20):
        n=min(1<<20,a[1]-a[0]-offset)
        if data[a[0]+offset:a[0]+offset+n] != data[b[0]+offset:b[0]+offset+n]:
            return False
    return True


def snapshots_equal(data, a, b):
    return all(spans_equal(data,a[name],b[name]) for name in SECTIONS)


def snapshot_states(data, spans):
    r=WireReader(data,*spans['gameplay'])
    inner=r.sections(session.frame.SECTIONS);r.finish()
    return inner,struct.unpack_from('<I',data,inner['state'][0])[0]


def source_locations(payload):
    selected={}
    for relative, needle in (
        (HOST+'physics/bridge.rs','pub fn tick('),
        (HOST+'physics/bridge.rs','pub fn tune('),
        (HOST+'physics/input_phase.rs','transition_action: physics.transfer'),
        (HOST+'physics/air_trajectory/mod.rs','(input.ground_normal, info.start_velocity)'),
        (HOST+'physics/air_trajectory/vert_departure.rs','fn vert_departure('),
        ('crates/skate-core/src/player/input_phase/runtime.rs','fn publish_transition'),
        ('crates/skate-core/src/air/trajectory/selector.rs','pub fn launch(')):
        text=payload[relative].decode();assert text.count(needle)==1,(relative,needle)
        selected[relative+'::'+needle]=dict(line=text[:text.index(needle)].count('\n')+1,
                                          source_sha256=sha(payload[relative]))
    return selected


def coverage(path, cases, leaves):
    """Only actual output records provide branch witnesses, never case labels.

    The complete selector trace proves requests, completions and vert-alignment
    retained by real full frames. The direct original helper footer establishes
    each departure arithmetic branch independently. End-of-frame observations
    do not intercept launch's transient input; an assisted sloped launch is
    reported as a retained selector witness, not a captured private call trace.
    """
    counts=Counter();states=set();assists=set();witnesses={};launches=[]
    def witness(name,case,row,owner,**extra):
        counts[name]+=1
        if name not in witnesses:
            witnesses[name]=dict(case=case['index'],row=row,tick=owner['ticks'],
                state=owner['state'],transfer=owner['transfer'],
                assist_word=owner['assist_word'],transition_word=owner['transition_word'],**extra)
    with path.open('rb') as handle, mmap.mmap(handle.fileno(),0,access=mmap.ACCESS_READ) as data:
        r=WireReader(data);assert r.word()==len(cases)
        for case in cases:
            assert r.word()==len(case['rows'])
            loaded=r.status();assert loaded['okay'],loaded
            prior=r.sections(SECTIONS);before=latest_owner(data,prior['latest'])
            assert before['transfer'] is None and before['assist_word']==0
            went_air=False
            for index,cmd in enumerate(case['rows']):
                op=r.word();assert op==cmd[0]
                status=r.status();after=r.sections(SECTIONS);owner=latest_owner(data,after['latest'])
                states.add(owner['state']);assists.add(owner['assist_word'])
                counts['commands']+=1;counts['successes' if status['okay'] else 'failures']+=1
                witness('transfer_absent' if owner['transfer'] is None else
                        'transfer_held' if owner['transfer'] else 'transfer_released',case,index,owner)
                inner,current=snapshot_states(data,after)
                assert current==owner['state']
                metadata=inner['metadata'];assert struct.unpack_from('<Q',data,metadata[0])[0]==owner['ticks']
                if op==1:
                    assert owner['transfer']==bool(cmd[1]&TRANSFER)
                    raw=struct.unpack_from('<I',data,after['controller'][0]+7*4)[0]
                    assert raw==(cmd[1]&~TRANSFER),('unmasked actual RawInput',case['index'],index,raw,cmd[1])
                    counts['tick_transfer_capture_and_raw_mask']+=1
                    if cmd[2] or cmd[3]:
                        witness('grab_with_transfer' if cmd[1]&TRANSFER else 'grab_without_transfer',case,index,owner)
                        if status['okay'] and not owner['transfer'] and owner['transition_word']==0:
                            witness('grab_without_transfer_transition_zero',case,index,owner)
                    if status['okay'] and owner['transfer'] and owner['transition_word']==session.bits(1.):
                        witness('held_transfer_transition_one',case,index,owner)
                if op==7:
                    if status['okay']:
                        assert owner['assist_word']==cmd[-1]
                        witness('tune_success',case,index,owner)
                    else:
                        assert status['error']=='Invalid skating tuning',status
                        assert snapshots_equal(data,prior,after),('rejected Tune changed an owner',case['index'],index)
                        witness('tune_rejected_all_owners_retained',case,index,owner)
                if op in (2,3,4,6,7,8,9,10,11):
                    assert owner['transfer'] is before['transfer'],('transfer lifetime',case['index'],index)
                    counts['non_tick_transfer_retention_checks']+=1
                if op in (2,3) and owner['transfer'] is None:
                    witness('collect_advance_without_tick_retains_none',case,index,owner)
                    if op==3 and status['okay'] and float_word(owner['transition_word'])>0:
                        witness('none_fallback_actual_positive_transition',case,index,owner)
                if op==5 and (not math.isfinite(float_word(cmd[1])) or float_word(cmd[1])<0):
                    assert status['error']=='Invalid frame interval' and snapshots_equal(data,prior,after)
                    counts['invalid_host_dt_all_owners_retained']+=1
                if op==0 and status['okay']:
                    assert owner['transfer'] is False
                    host=WireReader(data,*after['host']);assert host.take(2)==(0,cmd[-1]);host.finish()
                    if before['ticks']>0:
                        witness('same_owner_activation_reentry',case,index,owner,previous_ticks=before['ticks'])
                if op==8:
                    assert owner['deck_velocity']==tuple(cmd[1:4]),('actual body launch momentum',case['index'],index)
                    witness('launch_actual_deck_momentum',case,index,owner,velocity_words=list(owner['deck_velocity']))
                if owner['ticks']>before['ticks']:
                    counts['actual_physical_tick_advances']+=owner['ticks']-before['ticks']
                if owner['state'] in (200,201):
                    went_air=True
                    witness('actual_onboard_air',case,index,owner)
                elif went_air and owner['state'] in (100,103):
                    witness('actual_air_to_ground_return',case,index,owner)
                    went_air=False
                t=owner['trajectory'];b=before['trajectory']
                if t['requests']:
                    witness('actual_selector_query_requests',case,index,owner,requests=len(t['requests']))
                if t['pending_results']:
                    witness('actual_world_query_pending_results',case,index,owner,results=len(t['pending_results']))
                if t['valid'] and t['selection'] is not None:
                    witness('actual_completed_selector_selection',case,index,owner,selected_index=t['selected_index'])
                if t['pass_index'] in (1,2):
                    witness('actual_selector_second_pass',case,index,owner,pass_index=t['pass_index'])
                launch=t['launch_info']
                # GroundPhase and AirPhase both call Update after Launch in the
                # same frame. complete_batch advances pass0 to pass1 before the
                # observer runs; its second-pass path rewrites launch_info and
                # leaves pass2. A changed packet at a completed pass1 therefore
                # witnesses a new first-pass launch, excluding those rewrites.
                if (launch is not None and launch!=b['launch_info'] and t['pass_index']==1
                        and status['okay'] and owner['ticks']>before['ticks']
                        and t['requests'] and not t['pending'] and t['pending_results'] is None):
                    witness('actual_selector_launch_publication',case,index,owner,
                            start_velocity_words=list(launch[32:36]),requests=len(t['requests']),
                            previous_pass_index=b['pass_index'],completed_pass_index=t['pass_index'])
                    if len(launches)<96:
                        launches.append(dict(case=case['index'],row=index,tick=owner['ticks'],
                            assist_word=owner['assist_word'],transfer=owner['transfer'],
                            processed_ground_normal_words=list(owner['ground_normal']),
                            processed_velocity_words=list(owner['processed_velocity']),
                            start_velocity_words=list(launch[32:36]),adjusted_on_vert=t['adjusted_on_vert'],
                            request_count=len(t['requests'])))
                    if t['adjusted_on_vert']:
                        witness('actual_vert_aligned_selector_launch',case,index,owner,
                                start_velocity_words=list(launch[32:36]))
                        if float_word(owner['assist_word'])>0 and float_word(owner['ground_normal'][1])>0:
                            witness('assisted_sloped_retained_vert_launch',case,index,owner,
                                    ground_normal_words=list(owner['ground_normal']))
                    # adjust_velocity returns true only after assigning the
                    # retained start velocity. Require that source flag as well
                    # as distinct packets, so ordinary frame velocity drift
                    # cannot satisfy the launch-adjustment witness.
                    if (t['adjusted_on_vert'] and launch[32:36]!=before['processed_velocity']
                            and launch[32:36]!=owner['processed_velocity']):
                        witness('actual_launch_velocity_adjustment',case,index,owner,
                                before_velocity_words=list(before['processed_velocity']),
                                processed_velocity_words=list(owner['processed_velocity']),
                                retained_start_velocity_words=list(launch[32:36]))
                before,prior=owner,after
        assert r.word()==len(leaves)
        leaf_witnesses={}
        for leaf in leaves:
            result=r.take(8);initial=tuple(leaf['words'][:8])
            name='leaf_unchanged'
            if result[:4]!=initial[:4]:
                name='leaf_normal_only_changed' if result[4:]==initial[4:] else 'leaf_normal_and_velocity_changed'
            counts[name]+=1
            if name not in leaf_witnesses:
                leaf_witnesses[name]=dict(index=leaf['index'],input_words=leaf['words'],output_words=list(result))
            finite=all(math.isfinite(float_word(w)) for w in leaf['words'])
            if finite and name=='leaf_normal_only_changed' and leaf['words'][9]==0:
                counts['leaf_stock_near_vertical_band']+=1
            if finite and name=='leaf_normal_and_velocity_changed' and float_word(leaf['words'][9])>0:
                counts['leaf_assisted_outward_velocity_removed']+=1
            counts['leaf_finite_inputs' if finite else 'leaf_exceptional_inputs']+=1
            counts['leaf_exact_cases']+=1
        r.finish()
    mandatory=('transfer_absent','transfer_held','transfer_released',
        'tick_transfer_capture_and_raw_mask','non_tick_transfer_retention_checks',
        'grab_with_transfer','grab_without_transfer','grab_without_transfer_transition_zero',
        'held_transfer_transition_one','collect_advance_without_tick_retains_none',
        'none_fallback_actual_positive_transition','tune_success','tune_rejected_all_owners_retained',
        'invalid_host_dt_all_owners_retained','same_owner_activation_reentry',
        'launch_actual_deck_momentum','actual_physical_tick_advances','actual_onboard_air',
        'actual_air_to_ground_return','actual_selector_query_requests','actual_world_query_pending_results',
        'actual_completed_selector_selection','actual_selector_launch_publication',
        'actual_vert_aligned_selector_launch','assisted_sloped_retained_vert_launch',
        'actual_launch_velocity_adjustment','leaf_unchanged','leaf_stock_near_vertical_band',
        'leaf_assisted_outward_velocity_removed')
    missing=[name for name in mandatory if not counts[name]]
    report=dict(counts=dict(counts),required=list(mandatory),missing=missing,
        assists=sorted(assists),states=sorted(states),witnesses=witnesses,
        observed_launch_publications=launches,leaf_witnesses=leaf_witnesses,
        observation_scope=coverage.__doc__)
    assert {session.bits(v) for v in (0.,.5,1.)} <= assists,report
    return report


def first_difference(reference, native):
    """Hash and compare fixed chunks, retaining just the first differing offset."""
    sizes=(reference.stat().st_size,native.stat().st_size)
    digest_reference,digest_native=hashlib.sha256(),hashlib.sha256()
    first=None;offset=0
    with reference.open('rb') as a,native.open('rb') as b:
        while True:
            x,y=a.read(4<<20),b.read(4<<20)
            if not x and not y:
                break
            digest_reference.update(x);digest_native.update(y)
            if first is None and x!=y:
                first=offset+next((n for n,(u,v)in enumerate(zip(x,y))if u!=v),min(len(x),len(y)))
            offset+=max(len(x),len(y))
    return dict(equal=first is None,first_byte=first,reference_bytes=sizes[0],native_bytes=sizes[1],
                reference_sha256=digest_reference.hexdigest(),native_sha256=digest_native.hexdigest())


def locate_difference(path,offset,cases,leaves):
    """Read-only framing diagnostics even if a candidate's wire is malformed."""
    with path.open('rb') as handle,mmap.mmap(handle.fileno(),0,access=mmap.ACCESS_READ) as data:
        lo=max(0,offset-16);hi=min(len(data),offset+32)
        result=dict(hex=data[lo:hi].hex(),size=len(data))
        if offset+4<=len(data):
            result['word']=struct.unpack_from('<I',data,(offset//4)*4)[0]
        r=WireReader(data)
        try:
            assert r.word()==len(cases)
            for case in cases:
                result['case']=case['index'];result['scope']='case_header'
                assert r.word()==len(case['rows'])
                r.status()
                for index,op in [(-1,None),*((i,c[0])for i,c in enumerate(case['rows']))]:
                    result.update(row=index,operation=op,scope='status_or_opcode')
                    if index>=0:
                        assert r.word()==op;r.status()
                    start=r.at;spans=r.sections(SECTIONS)
                    if start<=offset<r.at:
                        result['scope']='snapshot_framing'
                        for name,span in spans.items():
                            if span[0]<=offset<span[1]:
                                result.update(scope='snapshot',section=name,section_word=(offset-span[0])//4)
                                if name=='gameplay':
                                    inner=WireReader(data,*span);nested=inner.sections(session.frame.SECTIONS)
                                    for key,block in nested.items():
                                        if block[0]<=offset<block[1]:
                                            result.update(gameplay_section=key,gameplay_section_word=(offset-block[0])//4)
                                            break
                                break
                        return result
                    if offset<start:
                        return result
            result.update(scope='vert_leaf_footer',leaf_index=max(0,(offset-r.at-4)//32))
            assert r.word()==len(leaves)
        except (AssertionError,IndexError,ValueError,struct.error) as error:
            result['decode_error']=str(error)
        return result


def resource_hashes(folder):
    assert folder.is_dir(),folder
    return {p.relative_to(folder).as_posix():session.digest(p)
            for p in sorted(folder.rglob('*')) if p.is_file()}


def dependency_hashes():
    return {Path(module.__file__).resolve().relative_to(PLUGIN).as_posix():
            session.digest(Path(module.__file__))
            for module in tuple(sys.modules.values()) if getattr(module,'__file__',None)
            and Path(module.__file__).resolve().is_relative_to(TESTS)
            and Path(module.__file__).suffix=='.py'}


def verify_snapshot(out,reference,native):
    for relative,row in reference['latest_original_prefixes'].items():
        p=destination(out,relative);raw=p.read_bytes()
        assert sha(raw[:row['original_bytes']])==row['original_sha256'],relative
        assert session.digest(p)==row['generated_sha256'],relative
    assert session.digest(out/'observed-source/atelier-host/src/migration_probe.rs')==reference['generated_probe_sha256']
    for name,expected in native['snapshot_sources'].items():
        assert session.digest(out/'native-source'/name)==expected,name


def build_plan(out,target):
    snapshot=out/'native-source';crate=out/'observed-source/atelier-host'
    return dict(reference=['cargo','+1.97.1','build','--release','--offline','--jobs','2',
            '--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target),
            '--bin','latest-gameplay-session-reference'],
        native=['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math',
            '-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),
            *[str(snapshot/(name+'.cpp'))for name in session.UNITS],
            str(snapshot/OWNED[1].name),'-o',str(out/'latest-gameplay-session-native')])


def execute(plan,out,target,assets,native_package,reference,native):
    # The explicit caller flag authorizes this path only from root's guard.
    # Independent agent execution and unguarded CI invocation are forbidden.
    verify_snapshot(out,reference,native)
    for name in ('reference','native'):
        print('Root guarded compile: '+name,flush=True)
        subprocess.run(plan[name],check=True)
    shutil.copy2(target/'release/latest-gameplay-session-reference',out/'latest-gameplay-session-reference')
    verify_snapshot(out,reference,native)
    for name,resource in (('reference',assets),('native',native_package)):
        print('Root guarded live Session comparison: '+name,flush=True)
        with (out/'input.bin').open('rb')as i,(out/(name+'.bin')).open('wb')as o:
            subprocess.run([str(out/('latest-gameplay-session-'+name)),str(resource)],
                           stdin=i,stdout=o,check=True)
    verify_snapshot(out,reference,native)
    return {name:session.digest(out/('latest-gameplay-session-'+name))for name in ('reference','native')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('output','target-dir','baseline-build','assets','native-package'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--native-overlay',type=Path,
                   help='Explicit ignored latest production draft; omit after root applies that port.')
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight',action='store_true')
    mode.add_argument('--run-under-root-guard',action='store_true')
    a=p.parse_args();out=historical_oracle._build_output(a.output).resolve()
    target=historical_oracle._build_output(a.target_dir).resolve()
    assert out!=target and out not in target.parents and target not in out.parents
    out.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','coverage.json'):
        (out/name).unlink(missing_ok=True)
    payload,identity=latest_originals()
    cases,preserved=corpus();leaves=leaf_corpus();session_raw,ranges=session.encode(cases)
    footer=[len(leaves),*[w for leaf in leaves for w in leaf['words']]]
    raw=session_raw+struct.pack('<'+'I'*len(footer),*footer)
    protocol=protocol_audit(raw,cases,ranges,leaves)
    baseline=a.baseline_build.resolve();stock=json.loads((baseline/'result.json').read_text())
    assert stock['passed']is True
    assert BASE_PIN.startswith(session.REFERENCE_REVISION)
    assert stock['reference_revision']in(BASE_PIN,session.REFERENCE_REVISION)
    old=session.corpus();old_raw,_=session.encode(old)
    assert old==json.loads((baseline/'cases.json').read_text())
    assert sha(old_raw)==stock['input_sha256']
    assets,native_package=a.assets.resolve(),a.native_package.resolve()
    for relative in ('private/stock/skater-collections.json',
                     'private/stock/data/script/camera/Default_cameragraph.stategraph'):
        assert (assets/relative).is_file(),('incomplete original asset root',relative)
    for relative in ('settings.skate','metadata/bank-0.skate','metadata/bank-1.skate',
                     'physics-skeletons.skate','animation/rig.skate','action.graph',
                     'motion.graph','camera.graph','camera.skate','gestures.skate'):
        assert (native_package/relative).is_file(),('incomplete native resource root',relative)
    assert any((native_package/'animation/clips').rglob('*.skate'))
    resources=dict(original_assets=resource_hashes(assets),native_package=resource_hashes(native_package))
    (out/'input.bin').write_bytes(raw)
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    (out/'leaf-cases.json').write_text(json.dumps(leaves,indent=2)+'\n')
    ref=stage_reference(out,target,payload,identity)
    native=stage_native(out,a.native_overlay.resolve()if a.native_overlay else None)
    verify_snapshot(out,ref,native)
    plan=build_plan(out,target)
    (out/'build-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    summary=dict(reference_commit=PIN,reference_revision=PIN,baseline_reference_commit=BASE_PIN,
        preflight=a.preflight,numeric_pass=False,root_guard_only=True,
        latest_native_overlay_ready=native['latest_candidate_ready'],
        histories=len(cases),commands=sum(len(c['rows'])for c in cases),
        legacy_histories=len(preserved),legacy_commands=sum(c['commands']for c in preserved),
        added_histories=len(cases)-len(preserved),leaf_cases=len(leaves),leaf_output_bytes=4+32*len(leaves),
        input_bytes=len(raw),input_sha256=sha(raw),
        units=len(session.UNITS),translation_units_with_probe=len(session.UNITS)+1,
        snapshot_sections=SECTIONS,protocol=protocol,ranges=ranges,
        legacy_preservation=preserved,legacy_input_sha256=sha(old_raw),
        accepted_baseline_result_sha256=session.digest(baseline/'result.json'),
        whole_latest_original_sha256={rel:sha(data)for rel,data in payload.items()},
        proof_sha256={str(q.relative_to(PLUGIN)):session.digest(q)for q in OWNED},
        dependency_sha256=dependency_hashes(),
        imported_session_proof_sha256={str(q.relative_to(ROOT)):session.digest(q)for q in session.OWNED},
        reference_provenance_sha256=session.digest(out/'reference-provenance.json'),
        native_provenance_sha256=session.digest(out/'native-provenance.json'),
        source_witness_locations=source_locations(payload),resources=resources,limitations=__doc__)
    (out/'owner-freeze.json').write_text(json.dumps(summary,indent=2)+'\n')
    if a.preflight:
        view={key:value for key,value in summary.items()if key not in (
            'whole_latest_original_sha256','ranges','legacy_preservation',
            'imported_session_proof_sha256','resources','source_witness_locations')}
        print(json.dumps(view,indent=2));return
    binaries=execute(plan,out,target,assets,native_package,ref,native)
    assert resources==dict(original_assets=resource_hashes(assets),native_package=resource_hashes(native_package))
    comparison=first_difference(out/'reference.bin',out/'native.bin')
    if not comparison['equal']:
        at=comparison['first_byte']
        report=dict(**comparison,first_word=at//4,
                    reference=locate_difference(out/'reference.bin',at,cases,leaves),
                    native=locate_difference(out/'native.bin',at,cases,leaves))
        (out/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n')
        raise AssertionError(report)
    print('Exact full streams match; decoding actual retained witnesses with mmap.',flush=True)
    covered=coverage(out/'reference.bin',cases,leaves)
    (out/'coverage.json').write_text(json.dumps(covered,indent=2)+'\n')
    assert not covered['missing'],('Unexercised actual owner witnesses',covered['missing'])
    result=dict(**{k:v for k,v in summary.items()if k not in ('preflight','numeric_pass')},
        preflight=False,numeric_pass=True,passed=True,exact_bytes=comparison['reference_bytes'],
        exact_words=comparison['reference_bytes']//4,output_sha256=comparison['reference_sha256'],
        binaries_sha256=binaries,coverage=covered,
        comparison='Every complete retained Session/frame owner byte plus actual latest helper footer; no float or error normalization.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key]for key in ('passed','reference_commit','histories','commands',
        'leaf_cases','exact_bytes','output_sha256','coverage')},indent=2))


if __name__=='__main__':
    main()
