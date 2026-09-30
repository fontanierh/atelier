#!/usr/bin/env python3
"""Record and replay complete fixed-step skating sessions against an independent reference.

This is an offline verification tool. A C++ test executable will implement the same
small stdin/stdout test protocol; the shipping C++ session is called in-process.
Use the shared render lock and memory guard when recording or replaying sessions.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import selectors
import struct
import subprocess

REFERENCE_REVISION = '46513a6'
PLUGIN = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def float_bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def first_difference(expected, actual, path='$'):
    """No dropped fields, tolerances or rounding of integer identities/ticks."""
    if isinstance(expected, float):
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            return dict(path=path, reason='type', expected=expected, actual=actual)
        if not math.isfinite(expected) or not math.isfinite(actual):
            return dict(path=path, reason='nonfinite', expected=str(expected), actual=str(actual))
        try:
            a, b = float_bits(expected), float_bits(actual)
        except OverflowError:
            return dict(path=path, reason='f32 overflow', expected=expected, actual=actual)
        if a != b:
            return dict(path=path, reason='float bits', expected=expected, actual=actual,
                        expected_bits=f'{a:08x}', actual_bits=f'{b:08x}')
        return None
    if type(expected) is not type(actual):
        return dict(path=path, reason='type', expected_type=type(expected).__name__, actual_type=type(actual).__name__)
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            return dict(path=path, reason='fields', missing=sorted(set(expected)-set(actual)),
                        unexpected=sorted(set(actual)-set(expected)))
        for key in sorted(expected):
            difference = first_difference(expected[key], actual[key], f'{path}.{key}')
            if difference:
                return difference
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            return dict(path=path, reason='length', expected=len(expected), actual=len(actual))
        for index, (a, b) in enumerate(zip(expected, actual)):
            difference = first_difference(a, b, f'{path}[{index}]')
            if difference:
                return difference
    elif expected != actual:
        return dict(path=path, reason='value', expected=expected, actual=actual)
    return None


class Worker:
    def __init__(self, binary, assets, world, log):
        self.log = Path(log).open('w')
        try:
            self.process = subprocess.Popen([str(binary), str(assets), str(world)], stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1)
        except BaseException:
            self.log.close()
            raise
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def receive(self):
        if not self.selector.select(90):
            raise TimeoutError('No session output within 90 seconds')
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f'Session exited with code {self.process.poll()}; see worker log')
        value = json.loads(line)
        if value.get('type') == 'error':
            raise RuntimeError(value)
        if value.get('type') not in ('ready', 'pose'):
            raise RuntimeError(f'Unexpected session response: {value}')
        if len(value['bones']) != 36 or len(value['root']) != 16 or any(len(b) != 16 for b in value['bones']):
            raise RuntimeError('Unexpected session pose layout')
        for values in [value['root'], value['velocity'], *value['bones']]:
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
                raise RuntimeError('Nonfinite or invalid pose output')
        return value

    def send(self, command):
        self.process.stdin.write(json.dumps(command, separators=(',', ':'))+'\n')
        self.process.stdin.flush()

    def close(self, require_clean=False):
        forced = False
        try:
            if self.process.poll() is None:
                try:
                    self.send(dict(op='quit'))
                    self.process.wait(timeout=10)
                except (BrokenPipeError, subprocess.TimeoutExpired):
                    forced = True
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
        finally:
            self.selector.close()
            self.process.stdin.close()
            self.process.stdout.close()
            self.log.close()
        if require_clean and (forced or self.process.returncode != 0):
            raise RuntimeError(f'Session did not shut down cleanly: {self.process.returncode=}, {forced=}')


def flat_world():
    return dict(triangles=[[[-100, 0, -100], [-100, 0, 100], [100, 0, 100]],
                           [[-100, 0, -100], [100, 0, 100], [100, 0, -100]]],
                rails=[], spawn=[0, 0, 0], heading=0)


def scenarios():
    """Explicit commands, replayed verbatim without adapting to candidate output."""
    cases = []
    generation = 0
    def add(name, controls, goofy=False, spin=1.6, velocity=(0, 0, 0), spawn=(0, 0, 0)):
        nonlocal generation
        generation += 1
        activate = dict(op='activate', spawn=list(spawn), heading=0, goofy=goofy, difficulty='normal',
                        trucks=.5, generation=generation, velocity=list(velocity),
                        pop=1.15, spin=spin, push_power=1.45, push_speed=1.15)
        commands = [activate]
        for overrides in controls:
            commands.append(dict(dict(op='step', dt=1/60, buttons=0, left=[0, 0], right=[0, 0], triggers=[0, 0]), **overrides))
        cases.append(dict(name=name, commands=commands))
    for goofy in (False, True):
        stance = 'goofy' if goofy else 'regular'
        add(f'{stance}/push-ollie-land', [dict(buttons=0x1000 if 60<=i<240 else 0,
            right=[0,-32767] if 245<=i<263 else [0,32767] if i==263 else [0,0]) for i in range(420)], goofy)
        for direction in (-1, 1):
            for spin in (1.6, 2.15):
                add(f'{stance}/spin/{direction}/{spin}', [dict(
                    left=[direction*32767,0] if 160<=i<270 else [0,0],
                    right=[0,-32767] if 150<=i<168 else [0,32767] if 168<=i<170 else [0,0])
                    for i in range(330)], goofy, spin, velocity=(0,0,5))
            add(f'{stance}/powerslide/{direction}', [dict(left=[direction*19660,-26214] if 150<=i<210 else [0,0])
                for i in range(330)], goofy, velocity=(0,0,5))
            add(f'{stance}/flip/{direction}', [dict(right=[0,-32767] if 120<=i<138 else
                [direction*32767,20000] if 138<=i<141 else [0,0]) for i in range(300)], goofy, velocity=(0,0,5))
        add(f'{stance}/manual', [dict(right=[0,-16000] if 90<=i<240 else [0,0]) for i in range(330)],
            goofy, velocity=(0,0,5))
        add(f'{stance}/bail-recover', [dict(buttons=0xc0 if 60<=i<90 else 0x1000 if 230<=i<240 else 0,
            triggers=[255,255] if 60<=i<90 else [0,0]) for i in range(480)], goofy)
        add(f'{stance}/run-mount', [{} for _ in range(120)], goofy, velocity=(0,0,4.2), spawn=(12,0,-8))
    add('packet-periods', [dict(dt=dt) for dt in (.001,1/120,1/60,1/30,.099)*80], velocity=(0,0,5))
    return cases


def rows(path):
    with gzip.open(path, 'rt') as source:
        for line in source:
            yield json.loads(line)


def write_row(target, value):
    target.write(json.dumps(value, separators=(',', ':'), allow_nan=False)+'\n')


def record(args):
    reference = Path(args.reference).resolve()
    provenance = json.loads(args.reference_provenance.read_text())
    revision = subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=PLUGIN,text=True).strip()
    if provenance['reference_revision'] != revision or provenance['binary_sha256'] != digest(reference):
        raise ValueError('Reference executable does not match the pinned build provenance')
    output = args.recording.resolve()
    if output.exists():
        raise ValueError('Recording already exists; use a new directory to preserve the reference')
    output.mkdir(parents=True)
    world = output/'world.json'
    world.write_text(json.dumps(flat_world(), separators=(',', ':'))+'\n')
    plan = scenarios()
    (output/'inputs.json').write_text(json.dumps(plan, separators=(',', ':'))+'\n')
    (output/'reference-build.json').write_text(json.dumps(provenance,indent=2)+'\n')
    worker = Worker(reference, args.assets.resolve(), world, output/'reference.log')
    count = 0
    states = set()
    completed = False
    try:
        with gzip.open(output/'reference.jsonl.gz', 'wt', compresslevel=3) as target:
            write_row(target, dict(case='startup', command=None, output=worker.receive()))
            for case in plan:
                for index, command in enumerate(case['commands']):
                    worker.send(command)
                    value = worker.receive()
                    write_row(target, dict(case=case['name'], command=index, output=value))
                    states.add(value['state'])
                    count += 1
                print(f'Recorded {case["name"]}', flush=True)
        completed = True
    finally:
        worker.close(require_clean=completed)
    manifest = dict(format=1, reference_revision=revision, reference_binary_sha256=digest(reference),
                    architecture=platform.machine(), cases=len(plan), responses=count+1, states=sorted(states),
                    comparison='all response fields; exact f32 bits; integer/string/bool values and structure exact',
                    files={name:digest(output/name) for name in ('world.json','inputs.json','reference.jsonl.gz','reference-build.json')},
                    assets={p.relative_to(args.assets).as_posix():digest(p) for p in sorted(args.assets.rglob('*')) if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2), flush=True)


def compare(args):
    recording = args.recording.resolve()
    manifest = json.loads((recording/'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        if digest(recording/name) != expected:
            raise ValueError(f'Reference recording changed: {name}')
    candidate = args.candidate.resolve()
    binary_digest = digest(candidate)
    if args.mode == 'repeat-reference':
        if binary_digest != manifest['reference_binary_sha256']:
            raise ValueError('Repeatability requires the same reference binary')
    elif binary_digest == manifest['reference_binary_sha256']:
        raise ValueError('Candidate is the reference binary; use repeat-reference to test reference determinism')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    worker = Worker(candidate, args.assets.resolve(), recording/'world.json', args.report.with_suffix('.log'))
    expected_rows = iter(rows(recording/'reference.jsonl.gz'))
    count = 0
    difference = None
    completed = False
    try:
        expected = next(expected_rows)
        actual = worker.receive()
        difference = first_difference(expected['output'], actual)
        if difference:
            difference.update(case='startup', command=None)
        count += 1
        for case in json.loads((recording/'inputs.json').read_text()):
            if difference:
                break
            for index, command in enumerate(case['commands']):
                expected = next(expected_rows)
                if (expected['case'],expected['command']) != (case['name'],index):
                    raise ValueError('Reference outputs do not correspond to recorded inputs')
                worker.send(command)
                actual = worker.receive()
                difference = first_difference(expected['output'], actual)
                count += 1
                if difference:
                    difference.update(case=case['name'], command=index, input=command,
                                      expected_tick=expected['output']['tick'], actual_tick=actual['tick'])
                    break
            print(f'Compared {case["name"]}', flush=True)
        if not difference and (next(expected_rows, None) is not None or count != manifest['responses']):
            raise ValueError('Reference output count mismatch')
        completed = True
    finally:
        worker.close(require_clean=completed)
    report = dict(passed=difference is None,
                  kind='reference-repeatability' if args.mode=='repeat-reference' else 'candidate-parity',
                  compared_responses=count, candidate_sha256=binary_digest,
                  reference_sha256=manifest['reference_binary_sha256'], first_divergence=difference)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    capture = commands.add_parser('record')
    capture.add_argument('--reference', type=Path, required=True)
    capture.add_argument('--reference-provenance', type=Path, required=True)
    for name in ('compare','repeat-reference'):
        replay = commands.add_parser(name)
        replay.add_argument('--candidate', type=Path, required=True)
        replay.add_argument('--report', type=Path, required=True)
    for command in (capture,*[commands.choices[name] for name in ('compare','repeat-reference')]):
        command.add_argument('--assets', type=Path, required=True)
        command.add_argument('--recording', type=Path, required=True)
    args = parser.parse_args()
    return record(args) if args.mode=='record' else compare(args)


if __name__ == '__main__':
    raise SystemExit(main())
