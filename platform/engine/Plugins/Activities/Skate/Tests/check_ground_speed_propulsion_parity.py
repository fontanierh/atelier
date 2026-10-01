#!/usr/bin/env python3
"""Compare physical push/brake/drag, speed-model state and phased propulsion.

Frozen original core source is unmodified. Run through the render lock and
memory guard; actual gameplay producer and state scheduling remain separate.
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
OPERATIONS = ('push','brake','linear_drag','speed_model','propulsion','enqueue_push','manual_angle','manual')


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def scalar(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def f(values):
    return list(map(bits, values))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus():
    rng=random.Random(0x82c04f68);records=[];cases=[]
    def add(op,words,label,**meta):
        cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**meta));records.append(struct.pack('<'+'I'*(len(words)+1),op,*words))
    def values(n,scale=10.):return [rng.uniform(-scale,scale) for _ in range(n)]
    def push(seed):
        flags=(0,0x02000000,0x02000000,0x02000000)[seed%4]
        return [flags,(0,0x200,0,0)[seed%4]]+f([rng.uniform(-3.,20.),rng.uniform(-3.,18.),rng.uniform(0.,22.),rng.uniform(.1,100.),(1/60,1/120,1/30)[seed%3]]+values(3,1.))
    limits=f([20.,.08,.12])
    for seed in range(2048):
        add(0,push(seed)+limits,'push flag/suppression, signed gaps, speed blending and force units')
        add(1,[(0,0x20000000,0x40000000,0x60000000)[seed%4]]+f([rng.uniform(0.,1.),rng.uniform(-20.,20.),rng.uniform(0.,4.),rng.uniform(0.,2.)]+values(3,1.)+[30.,50.,.2]),'brake override and actual unnormalized axis')
        add(2,[(0,0x20000000,0x40000000,0x60000000)[seed%4]]+f([rng.uniform(0.,5.),(0.,1.,-1.)[seed%3],(0.,-1.,1.)[seed%3],rng.uniform(-1.,2.),1.,3.,.5,.1]),'low-speed brake/balance drag branch ordering')
    for speed in (-0.,0.,.19999999,.2,.20000002,20.):
        for flags in (0,0x20000000,0x40000000,0x60000000):
            add(1,[flags]+f([1.,speed,abs(speed),1.,1.,-.0,.5,30.,50.,.2]),'signed zero brake sign and exact minimum boundary')
    curve=f([0.,.1,.25,.5,1.,2.,5.,20.]+[.001,.01,.02,.05,.1,.15,.2,.3])
    for seed in range(256):
        settings=f([.5,9.81,9.81,.7,.1,.6])+curve+f([.1,.25,.5,.2])+curve+curve+[seed%2]+f([20.]+[1e-6,1e-6,1e-6,(0.,.1)[seed%2]]+[.01,.02,.03,.04])
        assert len(settings)==68
        steps=[]
        for tick in range(32):
            flags=(0,0,0x02000000,0x00010000,0x20000000,0x40000000)[tick%6]
            f2=(0,0x00400000,0x40000000,0x08000000)[(seed+tick)%4]
            forward=[0.,rng.uniform(-.5,.5),1.,rng.choice((0.,.25,-.5))]
            normal=[rng.uniform(-.1,.1),(0.,.65,.65000004,1.)[tick%4],rng.uniform(-.1,.1),rng.choice((0.,.25,-.5))]
            scalars=[(1/60,1/120,1/30)[tick%3],rng.uniform(-10.,10.),(.25,.5,.50000006)[tick%3],rng.uniform(0.,2.),rng.uniform(-1.,1.),(0.,1.,-1.)[tick%3],(.2,.20000002,1.)[tick%3],(0.,1.)[tick%2]]
            vectors=values(4,1.)+values(4,1.)+values(4,10.)+normal+forward
            payload=[flags,f2,(1,2,3)[tick%3],(29,30,31)[tick%3]]+f(scalars+vectors+[rng.uniform(.1,100.)]);assert len(payload)==33
            steps.append([0x80000000 if tick%8==0 else 0]+payload)
        initial=f([rng.uniform(0.,20.)])+[rng.getrandbits(31)|(0x80000000 if seed%2 else 0)]
        add(3,settings+initial+[len(steps)]+[w for step in steps for w in step],
            'persistent target/reset flag, enabled/disabled forces, manual/gravity/coffin/override friction',steps=len(steps),initial_flags=initial[1])
    for seed in range(96):
        fill=(0,20,21)[seed%3];initial=[]
        for n in range(fill):initial+=[100+n]+f(values(6,1.))
        steps=[]
        for tick in range(24):
            g=push(seed+tick);ground=g[:2]+g[2:7]+f([rng.uniform(0.,1.)])+g[7:]+f(values(3,1.)+[1.])
            assert len(ground)==15
            settings=f([30.,50.,.2,20.,.08,.12]);manual=(seed+tick)%3==0
            steps.append([int(tick==12)]+ground+settings+[255,int(manual)]+f(values(4,100.)+values(4,1.)))
        add(4,[fill]+initial+[len(steps)]+[w for step in steps for w in step],
            'retained stack results submitted after manual selection, both zero tags, capacity drops and explicit clears',steps=len(steps))
    for seed in range(32):
        masses=f([rng.uniform(.1,10.) for _ in range(seed%9)])
        add(5,push(seed)+limits+[len(masses)]+masses,'explicit fresh mass convenience and actual queue append')
    for word in (0,0x80000000,0x40490fda,0x40490fdb,0xc0490fdb,0x40c90fdb,0x7f800000,0xff800000,0x7fc12345,0x7f7fffff,0xff7fffff):
        add(6,[word],'angle signed boundaries and explicit unavailable integer conversion')
    for _ in range(1024):add(6,f([rng.uniform(-1.e10,1.e10)]),'finite scalar fctiwz-style normalization without widening arithmetic')
    for seed in range(192):
        settings=f([0.,.1,.25,.5,1.,2.,5.,20.]+[.01,.02,.03,.04,.05,.06,.07,.08]+[.4,.95,.2,.03,.7]+[.01,.001,.02,.02,.002,.04]+[20.,.3,.1,15.,.1]);assert len(settings)==32
        commands=[]
        for tick in range(32):
            if tick%11==0:commands.append([1,(100,1,2)[tick//11],bits(.8)]);continue
            if tick%13==0:commands.append([0]);continue
            balance=(0.,1.,-1.,.5,-.5)[(seed+tick)%5]
            braking=(seed+tick)%3==0;flipped=(1.,-1.)[seed%2]
            target_degrees=15.*(.75*abs(balance*flipped)+.25)*(1 if balance*flipped>0 else -1)
            angle=math.radians(target_degrees if braking else rng.uniform(-30.,30.))
            arrays=[1.,0.,0.,.25]+[0.,0.,1.,-.5]+[0.,math.sin(angle),math.cos(angle),.25]+[0.,0.,1.,0.]+[rng.uniform(-1.,1.),0.,-2.*(1 if balance>=0 else -1),.25]+[.1,.2,.3,.4]+[-.1,-.2,-.3,-.4]
            flags=[int(seed%2==0),int(braking),int(tick%4<2),int(tick%4 in (0,2)),int(seed%2)]
            input=f([balance,flipped,tick/60,rng.uniform(0.,20.),rng.uniform(-1.,1.),(1/60,1/120)[tick%2]])+flags+f(arrays);assert len(input)==39
            mode=1 if tick==15 else 2 if tick in (16,17) else 0
            supplied=0x7fc12345 if tick==16 else bits(.1)
            commands.append([2,mode,supplied]+input)
        initial=f([.1,.2,-.1,.3,0. if seed%2 else .5])
        add(7,settings+f([.1])+[seed%2]+initial+[len(commands)]+[w for c in commands for w in c],
            'real angle measurement, contact/entry/reset, procedural PID histories, alternate forces and partial error writes',steps=len(commands))
    return struct.pack('<I',len(records))+b''.join(records),cases


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
    probe = PLUGIN / 'Tests/Reference/ground_speed_propulsion_probe.rs'
    main = source / 'ground-speed-propulsion-oracle.rs'
    main.write_text((source / 'lib.rs').read_text() + probe.read_text().replace('//!', '//'))
    reference = output / 'ground-speed-propulsion-reference'
    subprocess.run(['rustc', '+1.97.1', '--edition=2024', '-O', '-A', 'dead_code', str(main), '-o', str(reference)], check=True)
    for name, expected in originals.items():
        if digest(source / name) != expected:
            raise AssertionError(f'Frozen original module changed: {name}')
    snapshot = output / 'native-source'
    if snapshot.exists():
        shutil.rmtree(snapshot)
    snapshot.mkdir()
    native = PLUGIN / 'Source/AtelierSkate/Private/Native'
    units = ('NativeMath', 'RigidBody', 'ForceQueue', 'Braking', 'Push', 'GroundPropulsion', 'SpeedModel', 'Manual', 'BoardGroundAngle', 'RidingAngles')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h', 'cpp')]:
        shutil.copy2(native / name, snapshot / name)
    # Snapshot transitive headers as well as compiled numerical units.
    import re
    pending=list(snapshot.glob('*'));seen=set()
    while pending:
        path=pending.pop()
        if path.name in seen:continue
        seen.add(path.name)
        for name in re.findall(r'^#include "([^"\n]+)"',path.read_text(),re.M):
            target=snapshot/name
            if not target.exists():shutil.copy2(native/name,target)
            pending.append(target)
    shutil.copy2(PLUGIN / 'Tests/Native/ground_speed_propulsion_probe.cpp', snapshot / 'ground_speed_propulsion_probe.cpp')
    cpp = output / 'ground-speed-propulsion-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot), *[str(snapshot / f'{unit}.cpp') for unit in units], str(snapshot / 'ground_speed_propulsion_probe.cpp'), '-o', str(cpp)], check=True)
    provenance = dict(reference_revision=revision, source_archive_sha256=hashlib.sha256(archive).hexdigest(), original_source_sha256=originals, probe_sha256=digest(probe), reference_binary_sha256=digest(reference), cpp_binary_sha256=digest(cpp), native_source_sha256={p.name: digest(p) for p in sorted(snapshot.iterdir())}, rust_compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip(), cpp_compiler=subprocess.check_output(['clang++', '--version'], text=True).strip())
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return cpp, reference


def decode(data, cases):
    if len(data) % 4:
        raise AssertionError('Partial ground output word')
    words = struct.unpack('<' + 'I' * (len(data) // 4), data)
    at, rows = 0, []
    for case in cases:
        index, op, count = words[at:at + 3]
        if index != case['index'] or OPERATIONS[op] != case['operation']:
            raise AssertionError('Ground output identity changed')
        rows.append(words[at + 3:at + 3 + count])
        case.update(first_output_word=at, output_words=count + 3)
        at += count + 3
    if at != len(words):
        raise AssertionError('Trailing ground output words')
    return rows


def coverage(rows,cases):
    counts=Counter();targets=set();forces=set()
    def queue(row,at):
        n=row[at];at+=1
        if n>21:raise AssertionError('Force queue exceeded source capacity')
        counts['full_queues']+=n==21
        for index in range(n):counts[f'queue_tag_{row[at+index*7]}']+=1
        return at+n*7
    for row,c in zip(rows,cases):
        op=c['operation'];counts[op]+=1
        if op=='push':
            if len(row)!=7 or any(row[3:6]):raise AssertionError('Push record changed')
            counts['suppressed_pushes']+=bool(row[6]);counts['nonzero_pushes']+=any(w&0x7fffffff for w in row[:3])
        elif op=='brake':
            if len(row)!=7 or row[0]!=2 or any(row[4:]):raise AssertionError('Brake tag/point changed')
            counts['nonzero_brakes']+=any(w&0x7fffffff for w in row[1:4])
        elif op=='linear_drag':
            if len(row)!=1:raise AssertionError('Drag framing changed')
            counts['drag_override']+=scalar(row[0])==1.;counts['drag_balance']+=0.<scalar(row[0])<1.
        elif op=='speed_model':
            if row[2]!=c['steps'] or len(row)!=3+c['steps']*10:raise AssertionError('Speed program changed')
            for tick in range(c['steps']):
                r=row[3+tick*10:3+(tick+1)*10]
                if any(r[4:8]) or r[9]&0x80000000:raise AssertionError('Speed force point/reset-bit behavior changed')
                if r[9]!=c['initial_flags']&0x7fffffff:raise AssertionError('Speed model cleared unrelated flags')
                targets.add(r[8]);forces.add(r[:4]);counts['speed_updates']+=1
                counts['speed_force_enabled' if any(w&0x7fffffff for w in r[:4]) else 'speed_force_disabled']+=1
        elif op=='propulsion':
            at=queue(row,0);n=row[at];at+=1
            if n!=c['steps']:raise AssertionError('Propulsion step count changed')
            for _ in range(n):
                suppressed=row[at];at+=1;counts['ground_push_suppressed']+=bool(suppressed)
                if row[at]!=2:raise AssertionError('Ground braking tag changed')
                at+=7
                if row[at+6]!=suppressed:raise AssertionError('Suppression output not copied/reset')
                at+=7;manual=row[at];at+=1;first=row[at];at+=1
                if manual:counts['manual_submissions']+=1;counts['dropped_manual']+=not first
                else:
                    second=row[at];at+=1;counts['ordinary_submissions']+=1;counts['dropped_brake']+=not first;counts['dropped_push']+=not second
                at=queue(row,at)
            if at!=len(row):raise AssertionError('Trailing propulsion output')
        elif op=='enqueue_push':
            if len(row)!=15 or row[7]!=1 or row[8]!=3:raise AssertionError('Fresh mass enqueue changed')
        elif op=='manual_angle':
            if len(row)!=2:raise AssertionError('Manual angle framing changed')
            counts['manual_angle_success' if row[0] else 'manual_angle_error']+=1
            if not row[0] and row[1]!=bits(12.75):raise AssertionError('Unavailable conversion overwrote output')
        elif op=='manual':
            n=row[18];at=19
            if n!=c['steps']:raise AssertionError('Manual step count changed')
            previous_calls=0
            for _ in range(n):
                cmd=row[at];at+=1
                if cmd==1:counts['manual_entry_continue' if row[at]==0 else 'manual_entry_remove_velocity']+=1;at+=1
                elif cmd==2:
                    ok=row[at];at+=1
                    if ok:
                        e=row[at:at+22];at+=22
                        if any(e[4:12]):raise AssertionError('Manual emitted nonzero regular force/point')
                        counts['manual_correction_forces']+=bool(e[20]);counts['manual_opposition']+=bool(e[21]);counts['manual_success']+=1
                    else:counts['manual_measurement_error' if row[at] else 'manual_controller_angle_error']+=1;at+=1
                elif cmd==0:counts['manual_resets']+=1
                else:raise AssertionError('Manual command changed')
                state=row[at:at+5];at+=5;calls=row[at];at+=13
                if calls<previous_calls or calls>previous_calls+1:raise AssertionError('Manual measurement call ordering changed')
                previous_calls=calls;counts['manual_steps']+=1
                if cmd==0 and any(state):raise AssertionError('Manual reset did not clear five fields')
            if at!=len(row):raise AssertionError('Trailing manual output')
    for key in ('suppressed_pushes','nonzero_pushes','nonzero_brakes','drag_override','drag_balance','speed_force_enabled','speed_force_disabled','ground_push_suppressed','manual_submissions','ordinary_submissions','dropped_manual','dropped_brake','dropped_push','queue_tag_2','queue_tag_3','queue_tag_7','manual_angle_success','manual_angle_error','manual_entry_continue','manual_entry_remove_velocity','manual_correction_forces','manual_opposition','manual_success','manual_measurement_error','manual_controller_angle_error','manual_resets'):
        if not counts[key]:raise AssertionError(f'Uncovered ground speed/propulsion branch: {key}')
    if min(len(targets),len(forces))<64:raise AssertionError('Persistent speed model not sufficiently observable')
    counts.update(distinct_speed_targets=len(targets),distinct_speed_forces=len(forces))
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
    report = dict(passed=True, cases=len(cases), coverage=counts, exact_words=len(expected) // 4, input_sha256=hashlib.sha256(inputs).hexdigest(), output_sha256=hashlib.sha256(expected).hexdigest(), comparison='All push/braking/drag, persistent speed-model/manual state, actual measurements, partial errors and phased propulsion submission records exact; no tolerance; original numerical source unchanged; live producer/state scheduling separate')
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
