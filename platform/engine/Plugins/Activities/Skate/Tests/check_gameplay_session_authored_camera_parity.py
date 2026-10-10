#!/usr/bin/env python3
"""Authored camera RESOURCE scope, using already accepted whole Session binaries.

This is separate from stock Session coverage. The active stock host always
publishes camera type 1, whose stock graph has no SlowMotionController. Here only
the original camera graph resource and its lossless simulation conversion change.
All settings, shots, physics, input, animation, world, clock, Session methods and
observers remain the existing complete owners. Raw launch/tick/landing histories
produce the camera condition and real Begin/Update/End requests. No completed
packet, camera frame, request, physical state or clock record is supplied.

--preflight performs file/hash/protocol work only. Execution must be invoked by
the parent render guard after the referenced stock Session comparison passes;
this script has no compiler or build path. Every output byte is compared before
the read-only request-delivery and cadence assertions are evaluated.
"""
import argparse
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import shutil
import struct
import subprocess

import camera_probe_schema as camera_schema
import historical_oracle
import check_camera_runtime_parity as camera
import check_gameplay_session_parity as session
from check_gesture_parity import converter
from check_graph_parity import attribute, element, original_graph
from session_parity import REFERENCE_REVISION, digest

PLUGIN, CODE, TESTS = session.PLUGIN, session.CODE, session.TESTS
SOURCE_GRAPH = Path('private/stock/data/script/camera/Default_cameragraph.stategraph')
SIMULATION_GRAPH = Path('camera.graph')
NORMAL_TIMESTEP = 0x3c888889
NORMAL_PERIOD_NS = 16666600
DEPENDENCIES = (Path(session.__file__), Path(session.frame.__file__),
                Path(camera.__file__), Path(camera_schema.__file__),
                Path(converter.__file__), TESTS / 'check_graph_parity.py',
                TESTS / 'session_parity.py', Path(historical_oracle.__file__),
                TESTS / 'check_gameplay_world_input_parity.py')


def authored_graph():
    return element('state', 'root', [attribute('policy', 'Priority')], [
        element('state', 'Air', [attribute('interruptable', 'root')], [
            element('expression', children=[element('condition', 'IsInOnBoardAir',
                                                    [attribute('mask', 'always')])]),
            element('behaviour', 'SlowMotionController'),
            element('behaviour', 'CameraChooseShot', [attribute('shot1', 'bl_air')]),
        ]),
        element('state', 'Default', [attribute('interruptable', 'root')], [
            element('behaviour', 'CameraChooseShot', [attribute('shot1', 'bl_chase')]),
        ]),
    ])


def corpus():
    # Fixed independently of execution. The large flat authored world has no
    # rails: rail admission is unrelated to this camera-resource boundary.
    cases = []
    for goofy in (0, 1):
        for name, velocity, flight_ticks in (
                ('vertical-launch-land', [0, 8, 0], 200),
                ('travelling-launch-land', [0, 10, 4], 240)):
            rows = [session.configure(goofy), *[session.tick() for _ in range(64)],
                    [8, *session.fs(velocity)], *[session.tick() for _ in range(flight_ticks)],
                    [11], *[session.tick() for _ in range(32)]]
            cases.append(dict(index=len(cases), scenario='authored-camera-' + name,
                              goofy=goofy, world=dict(triangles=session.world_input.floor(size=100),
                                                     rails=[]),
                              spawn=[0, 0, 0], heading=(0, .317)[goofy], rows=rows))
    return cases


def tree_hashes(root):
    return {p.relative_to(root).as_posix(): digest(p)
            for p in sorted(root.rglob('*')) if p.is_file()}


def clone_tree(source, destination):
    # Existing resources are immutable. Hard links avoid copying animation banks;
    # changed graph files are replaced atomically, never opened through a link.
    assert destination != source and source not in destination.parents and destination not in source.parents
    if destination.exists():
        shutil.rmtree(destination)
    def copy_file(a, b):
        try:
            os.link(a, b)
        except OSError:
            shutil.copy2(a, b)
        return b
    shutil.copytree(source, destination, copy_function=copy_file, symlinks=True)


def replace_file(path, data):
    temporary = path.with_name(path.name + '.authored-camera-new')
    temporary.write_bytes(data)
    temporary.replace(path)


def source_destination(build, relative):
    if relative == 'atelier-host/src/main.rs':
        return build / 'reference-source' / relative
    if relative.startswith('crates/skate-host/src/'):
        return build / 'observed-source/atelier-host/src' / relative.removeprefix('crates/skate-host/src/')
    return build / 'observed-source' / relative


def verify_session_build(build):
    result_path = build / 'result.json'
    result = json.loads(result_path.read_text())
    assert result['passed'], 'The stock whole Session comparison must pass first'
    pinned = historical_oracle.REFERENCE_COMMIT
    assert pinned.startswith(REFERENCE_REVISION)
    assert result['reference_revision'] in (REFERENCE_REVISION, pinned)
    simulation_path, reference_path = build / 'simulation-provenance.json', build / 'reference-provenance.json'
    simulation, reference = json.loads(simulation_path.read_text()), json.loads(reference_path.read_text())
    assert reference['reference_revision'] == pinned
    snapshot = build / 'simulation-source'
    for name, expected in simulation['session_snapshot_sources'].items():
        assert digest(snapshot / name) == expected, ('changed simulation build snapshot', name)
    for name, expected in simulation['immutable_simulation_sources'].items():
        current = CODE / name if (CODE / name).is_file() else TESTS / 'Simulation' / name
        assert digest(current) == expected, ('source changed since accepted build', name)
    for name, expected in simulation['session_production'].items():
        assert digest(CODE / name) == expected, ('Session production changed', name)
    for relative, row in reference['session_original_prefixes'].items():
        original = build / 'reference-source' / relative
        assert digest(original) == row['original_sha256'], relative
        generated = source_destination(build, relative)
        assert generated.read_bytes()[:row['original_bytes']] == original.read_bytes(), relative
        assert digest(generated) == row['generated_sha256'], ('changed original observer staging', relative)
    for path in session.OWNED:
        assert digest(path) == reference['session_proof'][path.name], ('changed Session proof', path.name)
    assert digest(build / 'observed-source/atelier-host/src/migration_probe.rs') == reference['session_generated_sha256']
    binaries = {name: dict(path=str(build / name), sha256=digest(build / name))
                for name in ('gameplay-session-reference', 'gameplay-session-simulation')}
    return dict(stock_result_sha256=digest(result_path),
                stock_exact_bytes=result['exact_bytes'], stock_output_sha256=result['output_sha256'],
                simulation_provenance_sha256=digest(simulation_path),
                reference_provenance_sha256=digest(reference_path), binaries=binaries,
                production_sha256=simulation['immutable_simulation_sources'],
                session_production_sha256=simulation['session_production'],
                reference_prefixes=len(reference['session_original_prefixes']),
                snapshot_files=len(simulation['session_snapshot_sources']),
                units=len(simulation['units']),
                schema_root=str(build / 'reference-source'))


def prepare(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    integration = verify_session_build(args.session_build.resolve())
    stock_assets, stock_simulation = tree_hashes(args.assets.resolve()), tree_hashes(args.simulation_package.resolve())
    assets, package = output / 'authored-assets', output / 'authored-simulation-package'
    clone_tree(args.assets.resolve(), assets)
    clone_tree(args.simulation_package.resolve(), package)
    graph = authored_graph()
    replace_file(assets / SOURCE_GRAPH, original_graph(graph))
    arena = converter.read_graph(assets / SOURCE_GRAPH)
    replace_file(package / SIMULATION_GRAPH, converter.encode_graph(arena))
    authored_assets, authored_simulation = tree_hashes(assets), tree_hashes(package)
    changed_assets = sorted(k for k in stock_assets if stock_assets[k] != authored_assets[k])
    changed_simulation = sorted(k for k in stock_simulation if stock_simulation[k] != authored_simulation[k])
    assert stock_assets.keys() == authored_assets.keys() and changed_assets == [SOURCE_GRAPH.as_posix()]
    assert stock_simulation.keys() == authored_simulation.keys() and changed_simulation == [SIMULATION_GRAPH.as_posix()]
    cases = corpus()
    raw, ranges = session.encode(cases)
    protocol = session.protocol_audit(raw, cases, ranges)
    (output / 'input.bin').write_bytes(raw)
    (output / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    (output / 'authored-graph.json').write_text(json.dumps(graph, indent=2) + '\n')
    freeze = dict(scope=__doc__, reference_revision=REFERENCE_REVISION,
                  helper_sha256=digest(Path(__file__)), integration=integration,
                  borrowed_proof_sources={p.relative_to(PLUGIN).as_posix(): digest(p) for p in DEPENDENCIES},
                  source_assets=str(args.assets.resolve()), source_simulation_package=str(args.simulation_package.resolve()),
                  session_build=str(args.session_build.resolve()),
                  stock_assets_sha256=stock_assets, stock_simulation_sha256=stock_simulation,
                  authored_assets_sha256=authored_assets, authored_simulation_sha256=authored_simulation,
                  changes=dict(original_camera_graph=SOURCE_GRAPH.as_posix(), simulation_camera_graph=SIMULATION_GRAPH.as_posix()),
                  graph_elements=len(arena), histories=len(cases), commands=sum(len(c['rows']) for c in cases),
                  input_bytes=len(raw), input_sha256=hashlib.sha256(raw).hexdigest(),
                  cases_sha256=digest(output / 'cases.json'), protocol=protocol, ranges=ranges)
    (output / 'owner-freeze.json').write_text(json.dumps(freeze, indent=2) + '\n')
    return freeze


class WireReader:
    def __init__(self, data): self.data, self.at = data, 0
    def word(self):
        assert self.at + 4 <= len(self.data)
        value = struct.unpack_from('<I', self.data, self.at)[0]
        self.at += 4
        return value
    def wide(self): return self.word() | (self.word() << 32)
    def status(self):
        okay = self.word()
        assert okay in (0, 1)
        if okay: return dict(okay=True, error='')
        return dict(okay=False, error=bytes(self.word() for _ in range(self.word())).decode())
    def sections(self, names):
        assert self.word() == len(names)
        out = {}
        for name in names:
            size = self.word() * 4
            assert self.at + size <= len(self.data)
            out[name] = (self.at, self.at + size)
            self.at += size
        return out


class GameplayCameraReader(camera.Reader):
    # The whole Session's existing observer omits no state; its graph controller
    # is serialized with Frame's original field order (dt,current,last,times).
    def value(self, kind, path):
        if kind in ('StateId', 'BehaviorId', 'HookId'):
            kind = 'usize'
        return super().value(kind, path)

    def runtime(self, path):
        result = {'manager': self.value('CameraMan', path + '.manager'),
                  'subject': self.value('SubjectPublisher', path + '.subject'),
                  'controller': self.value('Controller', path + '.controller')}
        for key, kind in [('slow', 'Vec<Option<SlowMotionController>>'),
                          ('trajectories', '[TrajectoryResult;3]'),
                          ('frame', 'Option<CameraFrame>'), ('latest', 'Option<CameraSubjectSnapshot>'),
                          ('rates', 'Vec<SimulationRateRequest>'), ('messages', 'Vec<String>')]:
            result[key] = self.value(kind, path + '.' + key)
        return result


def read_snapshot(reader, schema):
    outer = reader.sections(session.SECTIONS)
    begin, end = outer['gameplay']
    nested_reader = WireReader(reader.data[begin:end])
    inner = nested_reader.sections(session.frame.SECTIONS)
    assert nested_reader.at == len(nested_reader.data)
    state_at = begin + inner['state'][0]
    state = struct.unpack_from('<I', reader.data, state_at)[0]
    metadata_at = begin + inner['metadata'][0]
    ticks = struct.unpack_from('<Q', reader.data, metadata_at)[0]
    # Exact existing complete metadata observer: 7 prefix words, 12 trainer,
    # 17 retained COM conditioner, 12 COM output, then clock u32/u64.
    reset, period_ns = struct.unpack_from('<IQ', reader.data, metadata_at + 48 * 4)
    camera_at, camera_end = inner['camera']
    camera_reader = WireReader(nested_reader.data[camera_at:camera_end])
    size = camera_reader.word()
    raw_camera = bytes(camera_reader.word() for _ in range(size))
    assert camera_reader.at == len(camera_reader.data)
    typed = GameplayCameraReader(raw_camera, schema)
    runtime = typed.runtime('camera')
    assert typed.at == len(raw_camera)
    pose_end = outer['pose'][1]
    period_word = struct.unpack_from('<I', reader.data, pose_end - 4)[0]
    return dict(state=state, ticks=ticks, reset=reset, period_ns=period_ns,
                period_word=period_word, camera=runtime)


def f32(value): return struct.unpack('<f', struct.pack('<f', value))[0]
def from_bits(value): return struct.unpack('<f', struct.pack('<I', value))[0]


def delivered_clock(previous):
    reset, period = previous['reset'], previous['period_ns']
    for request in previous['camera']['rates']:
        timestep = from_bits(request['timestep'])
        frequency = math.trunc(f32(f32(1.0 / timestep) + .5))
        assert 1 <= frequency <= 0x7fffffff
        period = (10000000 // frequency) * 100
        reset = (0 if request['timestep'] == NORMAL_TIMESTEP else
                 (request['ticks'] + 1) & 0xffffffff if 0 < request['ticks'] < 0x80000000 else 180)
    reset = (reset - 1) & 0xffffffff
    if reset == 0: period = NORMAL_PERIOD_NS
    return reset, period


def coverage(path, cases, schema):
    counts = dict(ticks=0, begin=0, update=0, end=0, changed_period=0,
                  return_to_stock=0, ordered_begin_update=0, next_tick_delivery=0)
    witnesses, periods, per_case = [], set(), []
    with path.open('rb') as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as raw:
        reader = WireReader(raw)
        assert reader.word() == len(cases)
        for case in cases:
            assert reader.word() == len(case['rows'])
            assert reader.status()['okay']
            prior = read_snapshot(reader, schema)
            starts, ends, returns = 0, 0, 0
            for row, command in enumerate(case['rows']):
                assert reader.word() == command[0]
                status = reader.status()
                current = read_snapshot(reader, schema)
                assert status['okay'], (case['index'], row, status)
                periods.add(current['period_word'])
                if command[0] == 1:
                    counts['ticks'] += 1
                    assert current['ticks'] == prior['ticks'] + 1
                    assert (current['reset'], current['period_ns']) == delivered_clock(prior), (case['index'], row, 'request delivery order')
                    counts['next_tick_delivery'] += 1
                    before = any(v is not None for v in prior['camera']['slow'])
                    active = any(v is not None for v in current['camera']['slow'])
                    latest = current['camera']['latest']
                    assert latest is not None and bool(latest['graph']['onboard_air']) == active
                    rates = current['camera']['rates']
                    if active and not before:
                        assert len(rates) == 2 and rates[0] == dict(timestep=NORMAL_TIMESTEP, ticks=1)
                        assert rates[1]['ticks'] == 1
                        counts['begin'] += 1; counts['ordered_begin_update'] += 1; starts += 1
                        witnesses.append(dict(case=case['index'], row=row, event='Begin then Update', rates=rates, state=current['state']))
                    elif before and not active:
                        assert rates == [dict(timestep=NORMAL_TIMESTEP, ticks=0)]
                        counts['end'] += 1; ends += 1
                        witnesses.append(dict(case=case['index'], row=row, event='End', rates=rates, state=current['state']))
                    elif active:
                        assert len(rates) == 1 and rates[0]['ticks'] == 1
                        counts['update'] += 1
                    else:
                        assert not rates
                    if current['period_ns'] != NORMAL_PERIOD_NS: counts['changed_period'] += 1
                    if prior['period_ns'] != NORMAL_PERIOD_NS and current['period_ns'] == NORMAL_PERIOD_NS:
                        counts['return_to_stock'] += 1; returns += 1
                        witnesses.append(dict(case=case['index'], row=row, event='clock returns to stock', pending_prior_requests=prior['camera']['rates']))
                prior = current
            assert starts > 0 and ends > 0 and returns > 0, (case['index'], starts, ends, returns)
            assert prior['period_ns'] == NORMAL_PERIOD_NS and not any(v is not None for v in prior['camera']['slow'])
            per_case.append(dict(case=case['index'], begins=starts, ends=ends, returns_to_stock=returns))
        assert reader.at == len(raw)
    assert len(periods) > 1 and counts['changed_period'] > 0
    return dict(counts=counts, periods=sorted(periods), witnesses=witnesses, per_case=per_case)


def execute(args):
    output = args.output.resolve()
    for name in ('result.json', 'first-divergence.json'):
        (output / name).unlink(missing_ok=True)
    frozen = json.loads((output / 'owner-freeze.json').read_text())
    assert frozen['helper_sha256'] == digest(Path(__file__))
    assert {p.relative_to(PLUGIN).as_posix(): digest(p) for p in DEPENDENCIES} == frozen['borrowed_proof_sources']
    assert verify_session_build(args.session_build.resolve()) == frozen['integration']
    assert tree_hashes(args.assets.resolve()) == frozen['stock_assets_sha256']
    assert tree_hashes(args.simulation_package.resolve()) == frozen['stock_simulation_sha256']
    assert tree_hashes(output / 'authored-assets') == frozen['authored_assets_sha256']
    assert tree_hashes(output / 'authored-simulation-package') == frozen['authored_simulation_sha256']
    assert digest(output / 'input.bin') == frozen['input_sha256']
    assert digest(output / 'cases.json') == frozen['cases_sha256']
    cases = json.loads((output / 'cases.json').read_text())
    binaries = frozen['integration']['binaries']
    for side, binary, resource in (
            ('reference', 'gameplay-session-reference', 'authored-assets'),
            ('simulation', 'gameplay-session-simulation', 'authored-simulation-package')):
        with (output / 'input.bin').open('rb') as stdin, (output / (side + '.bin')).open('wb') as stdout, (output / (side + '.stderr')).open('wb') as stderr:
            subprocess.run([binaries[binary]['path'], str(output / resource)], stdin=stdin, stdout=stdout, stderr=stderr, check=True)
        assert digest(Path(binaries[binary]['path'])) == binaries[binary]['sha256']
    expected, actual = output / 'reference.bin', output / 'simulation.bin'
    with expected.open('rb') as reference_file, actual.open('rb') as simulation_file:
        at = 0
        while True:
            a, b = reference_file.read(1024 * 1024), simulation_file.read(1024 * 1024)
            if a != b:
                first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                failure = dict(first_byte=at + first, first_word=(at + first) // 4,
                               reference_bytes=expected.stat().st_size, simulation_bytes=actual.stat().st_size)
                (output / 'first-divergence.json').write_text(json.dumps(failure, indent=2) + '\n')
                raise AssertionError(failure)
            if not a: break
            at += len(a)
    source = Path(frozen['integration']['schema_root'])
    schema = camera_schema.schemas(lambda relative: (source / relative).read_text())
    for name in ('Frame', 'ActiveBehavior', 'Controller'):
        schema[name] = camera_schema.declaration((source / 'crates/skate-core/src/graph/controller.rs').read_text(), name)
    covered = coverage(expected, cases, schema)
    result = dict(passed=True, scope=__doc__, reference_revision=REFERENCE_REVISION,
                  stock_session_build=frozen['integration'], helper_sha256=frozen['helper_sha256'],
                  input_sha256=frozen['input_sha256'], exact_bytes=expected.stat().st_size,
                  output_sha256=digest(expected), coverage=covered,
                  resource_changes=frozen['changes'])
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('session-build', 'assets', 'simulation-package', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    result = prepare(args) if args.preflight else execute(args)
    # The full file manifest is recorded under build; keep terminal output small.
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('stock_assets_sha256', 'stock_simulation_sha256',
                                     'authored_assets_sha256', 'authored_simulation_sha256')}, indent=2))


if __name__ == '__main__':
    main()
