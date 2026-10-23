"""One-off Carriage host orchestration; native execution only via run-current.

seal-original preserves the already completed original invocation and its old
receipts. run-current executes only the exact independently bound old native
driver through normal admission, then compares the retained67/81 finite slice.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

# Bind the receiver-installed package before source yori prepends its own studio.
# This is the original native runner import order; Context must remain receiving.
from atelier import build

MAX_LOG_BYTES = 8 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def regular(path):
    path = Path(path)
    require(path.is_absolute(), 'Absolute evidence path required')
    for parent in [path, *path.parents]:
        require(not parent.is_symlink(), 'Linked evidence path refused')
    value = path.lstat()
    require(stat.S_ISREG(value.st_mode), 'Regular evidence file required')
    return value


def stable_read(path, maximum=MAX_LOG_BYTES):
    """Read one unlinked file with matching descriptor/path identities before/after."""
    path = Path(path); before = regular(path)
    require(0 < before.st_size <= maximum, 'Empty or oversized metadata/log file')
    with path.open('rb') as stream:
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Evidence replaced before read')
        payload = stream.read(maximum + 1)
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Evidence changed during read')
    require(identity(regular(path)) == identity(before) and len(payload) == before.st_size,
            'Evidence changed after read')
    return payload, dict(identity=identity(before), sha256=digest(payload))


APPROVED_TAIL_BYTES = 825
APPROVED_TAIL_SHA256 = '5c9b23a4bb46bc66c3c6da8c05079eb04f9d9c222f5d014a540034313b7c881f'
SOURCE_HEAD = 'f3750223ce7c8e5d2587f7f7fd1d1c8193bcc0c6'
RECEIVING_HEAD = 'e1a700a24b95f83254379eb2d30a4f7551b76f05'


def trace_tail(tail):
    """Admit exactly the reviewed 825-byte TraceServer tail, never a log grammar."""
    require(len(tail) == APPROVED_TAIL_BYTES and digest(tail) == APPROVED_TAIL_SHA256,
            'Unknown stdout append; only the exact reviewed TraceServer shutdown tail is admitted')


def prefix_proof(payload, expected):
    """@cc [owner:fontanierh,label:correctness] carriage-retained-stdout-prefix
    Finalization MUST retain the exact old bound stdout prefix. Only the complete
    explicitly classified TraceServer tail MAY follow it; changed prefixes,
    unknown appends and unstable files MUST refuse without rewriting old evidence.
    """
    require(re.fullmatch('[0-9a-f]{64}', expected) is not None, 'Invalid original stdout SHA')
    if digest(payload) == expected:
        return dict(prefix_bytes=len(payload), prefix_sha256=expected, appended_bytes=0, tail_sha256=digest(b''), classifier='unchanged')
    current = hashlib.sha256(); offset = 0
    for line in payload.splitlines(keepends=True):
        current.update(line); offset += len(line)
        if current.hexdigest() == expected:
            tail = payload[offset:]; trace_tail(tail)
            return dict(prefix_bytes=offset, prefix_sha256=expected, appended_bytes=len(tail),
                        tail_sha256=digest(tail), classifier='reviewed-traceserver-tail-825-sha256-v1')
    raise ValueError('Original bound stdout prefix changed or is absent')


def snapshot_stdout(old_binding, destination):
    source = Path(old_binding['path']); payload, before = stable_read(source)
    proof = prefix_proof(payload, old_binding['sha256'])
    # Independent second full read catches an append/replacement around snapshot publication.
    repeated, after = stable_read(source)
    require(payload == repeated and before == after, 'Stdout raced before snapshot publication')
    with Path(destination).open('xb') as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.chmod(destination, 0o444)
    frozen, frozen_identity = stable_read(destination)
    require(frozen == payload, 'Frozen stdout differs from stable full log')
    return dict(source=old_binding, before=before, after=after, snapshot=dict(path=str(destination), sha256=digest(frozen)),
                snapshot_identity=frozen_identity, **proof)


def unchanged_snapshot(record):
    payload, current = stable_read(record['source']['path'])
    require(current == record['before'] == record['after'], 'Live stdout changed across comparison')
    frozen, frozen_identity = stable_read(record['snapshot']['path'])
    require(frozen_identity == record['snapshot_identity'] and frozen == payload
            and digest(frozen) == record['snapshot']['sha256'], 'Stdout snapshot changed across comparison')
    return current


def clean_head(root):
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root), 'Bound source checkout is dirty')
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()


def write_new(path, value):
    payload = json.dumps(value, sort_keys=True).encode() + b'\n'
    with path.open('xb') as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.chmod(path, 0o444)
    return dict(path=str(path), sha256=digest(payload))


class Retained:
    def __init__(self):
        self.rows = {}

    def load(self, path):
        payload, observed = stable_read(path); self.rows[str(path)] = observed
        return json.loads(payload)

    def check(self):
        for path, before in self.rows.items():
            _, after = stable_read(path)
            require(before == after, 'Retained metadata changed across host validation')


def original_api(source, spec):
    for name in ('carriage_native_equivalence', 'atomic_equivalence', 'track_native_equivalence',
                 'run_track_native_equivalence', 'network_review_common', 'yori'):
        require(name not in sys.modules, 'Start a fresh host process with no preloaded proof modules')
    game = source / 'games/yorimichi'
    sys.path[:0] = [str(game / 'tests/native'), str(game / 'tools'), str(game / 'world')]
    names = ('carriage_native_equivalence', 'atomic_equivalence', 'track_native_equivalence',
             'run_track_native_equivalence', 'network_review_common')
    modules = {name: importlib.import_module(name) for name in names}
    for module in modules.values():
        path = str(Path(module.__file__).absolute())
        require(path in spec['inputs'] and digest(Path(path).read_bytes()) == spec['inputs'][path],
                'Host dependency is not the retained source-bound module')
    return modules


def physical_absence(spec, cleanup):
    package = spec['package']; content = Path(spec['receiving']) / 'games/yorimichi/unreal/Content'
    require(re.fullmatch('/Game/AtelierValidation/Carriage_[0-9a-f]{12}', package) is not None
            and Path(spec['content']) == content, 'Foreign Carriage fixture root')
    folder = content / package.removeprefix('/Game/')
    require(cleanup['root'] == str(folder) and cleanup['remaining'] == {} and cleanup['allowed_packages']
            and len(set(cleanup['allowed_packages'])) == len(cleanup['allowed_packages'])
            and all(p.startswith(package + '/') and '..' not in p.split('/') for p in cleanup['allowed_packages']),
            'Incomplete or foreign Carriage cleanup record')
    for parent in folder.parents:
        require(not parent.is_symlink(), 'Linked fixture ancestor')
    require(not os.path.lexists(folder), 'Carriage fixture remains physically present')


def empty_owned_tree(path):
    value = json.loads(stable_read(path)[0]); late = value.get('late_reporters', {})
    require(value['state'] == 'child_exited' and value['cleanup_complete'] is True
            and value['processes'] == [] and value['footprint_bytes'] == 0
            and not late.get('unresolved') and not late.get('unresolved_pids') and not late.get('scan_failed', False),
            'Owned tree cleanup is not positively empty')
    from atelier.harness.safety.process_tree import started
    require(type(value['owner']) is int and type(value['owner_started']) is int
            and started(value['owner']) != value['owner_started'], 'Exact owned native root is still alive')
    return value


def frozen_current_stdout(source, destination, marker):
    """Freeze full bytes immediately after whole return; later service appends are irrelevant."""
    payload, before = stable_read(source)
    require(marker.encode() in payload, 'Current completion marker absent')
    repeated, after = stable_read(source)
    require(payload == repeated and before == after, 'Current stdout raced while freezing')
    with destination.open('xb') as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.chmod(destination, 0o444)
    frozen, observed = stable_read(destination)
    require(frozen == payload, 'Current stdout snapshot differs')
    return dict(source=str(source), before=before, after=after,
                snapshot=dict(path=str(destination), sha256=digest(frozen)), snapshot_identity=observed,
                boundary='whole return, positive empty owned root/tree, complete native marker; no service wait')


class Session:
    def __init__(self, workspace, output):
        print('CARRIAGE HOST: checking old source/receiver specs and independent host source', flush=True)
        self.root, self.output = Path(workspace).absolute(), Path(output).absolute()
        require(self.root.is_dir() and not self.root.is_symlink() and self.output.parent == self.root
                and re.fullmatch('(sealed-original|current-host)-[A-Za-z0-9_-]+', self.output.name) is not None
                and not os.path.lexists(self.output), 'Fresh direct owned host output directory required')
        self.retained = Retained()
        self.specs = {p: self.retained.load(self.root / p / 'spec.json') for p in ('original', 'current')}
        self.source = Path(self.specs['original']['source']); self.receiver = Path(self.specs['original']['receiving'])
        self.tool = Path(__file__).absolute(); self.tool_data, self.tool_identity = stable_read(self.tool)
        self.tool_head = clean_head(self.tool.parents[4])
        for phase, spec in self.specs.items():
            require(spec['phase'] == phase and spec['source'] == str(self.source) and spec['receiving'] == str(self.receiver)
                    and spec['source_head'] == SOURCE_HEAD and spec['receiving_head'] == RECEIVING_HEAD
                    and spec['output'] == str(self.root / phase), 'Wrong reviewed phase/source/receiver/output')
            require(clean_head(self.source) == SOURCE_HEAD and clean_head(self.receiver) == RECEIVING_HEAD,
                    'Original source or receiver changed before proof imports')
        require(Path.cwd().resolve() == self.receiver.resolve(), 'Run through the receiving checkout environment')
        self.api = original_api(self.source, self.specs['original'])
        self.proof = self.api['carriage_native_equivalence']; self.generic = self.api['atomic_equivalence']
        self.ctx = build.Context('yorimichi')
        require(self.ctx.game_dir == self.receiver / 'games/yorimichi', 'Wrong receiving Context')
        self.inputs()
        print('CARRIAGE HOST: checking actual receiver compile/native signatures; no native launch yet', flush=True)
        self.native = self.native_identity()

    def native_identity(self):
        return self.api['network_review_common'].current_native_build(self.ctx)

    def inputs(self):
        require(clean_head(self.source) == SOURCE_HEAD and clean_head(self.receiver) == RECEIVING_HEAD, 'Old source/receiver changed')
        for phase, spec in self.specs.items():
            print('CARRIAGE HOST: checking ' + phase + ' retained input identities (' + str(len(spec['inputs'])) + ' files)', flush=True)
            self.proof.bound_inputs(spec)

    def finish(self):
        self.inputs(); require(self.native_identity() == self.native, 'Actual compiled native identity changed')
        self.retained.check()
        payload, observed = stable_read(self.tool)
        require(payload == self.tool_data and observed == self.tool_identity
                and clean_head(self.tool.parents[4]) == self.tool_head, 'Independent host tool changed')

    def tool_binding(self):
        return dict(path=str(self.tool), sha256=digest(self.tool_data), head=self.tool_head)

    def metadata(self, phase):
        records = self.retained.load(self.root / phase / 'native.json')
        require(set(records) == {phase}, 'Wrong retained native phase')
        vehicles = self.retained.load(Path(self.specs[phase]['document']))['vehicles']
        expected = self.proof.inventory(vehicles)
        require(len(expected) == 67 and sum(expected.values()) == 81 and set(records[phase]) == set(expected)
                and all(row['policy_scope'] == 'fixture' for row in records[phase].values()), 'Missing67/81 retained native census')
        materials = self.retained.load(self.root / phase / 'materials.json')
        poses = self.retained.load(self.root / phase / 'poses.json')
        return records, vehicles, materials, poses

    def startup(self, phase, host):
        spec = self.specs[phase]; launch = self.proof.check_private_launch(spec)
        text = self.generic.artifact(host['engine_log']).decode(errors='replace')
        ddc = self.proof.startup_ddc(launch, text)
        observed = self.retained.load(self.root / phase / 'startup-ddc.json')
        require(host['launch'] == launch and host['startup_ddc'] == ddc and observed['launch'] == launch
                and all(observed[k] == v for k, v in ddc.items()), 'Actual private startup evidence differs')


def seal_original(workspace, output):
    """@cc [owner:fontanierh,label:correctness] carriage-original-receipt-recovery
    Recovery MUST preserve the old original invocation/receipts and admit only
    its exact bound prefix plus the reviewed825-byte TraceServer tail. Whole0,
    empty owned root/tree, source/native/inputs and physical fixture absence MUST
    revalidate. This new host tool MUST NOT claim it executed the old native job.
    """
    print('CARRIAGE HOST: sealing retained original only; no new native execution', flush=True)
    session = Session(workspace, output); load = session.retained.load
    old_path = session.root / 'original/host-result.json'; old = load(old_path)
    spec = session.specs['original']; whole = load(session.root / 'original/whole-result.json')
    require(old['phase'] == whole['phase'] == 'original' and old['whole_exit'] == whole['exit_code'] == 0
            and old['guard_empty'] is True and old['fixture_absent'] is True
            and old['native'] == whole['native'] == session.native
            and old['spec_sha256'] == whole['spec_sha256'] == session.retained.rows[str(session.root / 'original/spec.json')]['sha256']
            and whole['work_seconds'] == 2400 and whole['queue_seconds'] == 1200, 'Old original invocation binding differs')
    for key in ('source_head', 'receiving_head'):
        require(old[key] == whole[key] == spec[key], 'Old original head differs')
    guard = old['guard']; base = session.root / 'original'
    require(guard['stdout']['path'] == str(base / 'guard/stdout.log')
            and guard['receipt']['path'] == str(base / 'guard/memory-health-tree.json')
            and guard['whole_result']['path'] == str(base / 'whole-result.json'), 'Foreign original guard paths')
    require(guard['marker'] == 'CARRIAGE ACTUAL67/81 VEHICLE FIXTURE COMPLETE original ' + old['spec_sha256'], 'Old marker differs')
    empty_owned_tree(Path(guard['receipt']['path'])); session.startup('original', old)
    cleanup = load(base / 'cleanup.json'); physical_absence(spec, cleanup)
    session.metadata('original')  # Original phase only; paired exact comparison remains a current-phase obligation.
    session.output.mkdir()
    snapshot = snapshot_stdout(guard['stdout'], session.output / 'original-stdout.log')
    require(snapshot['classifier'] == 'reviewed-traceserver-tail-825-sha256-v1'
            and snapshot['prefix_bytes'] == 2493961, 'Not the reviewed original append incident')
    sealed_guard = dict(guard, stdout=snapshot['snapshot']); session.generic.guard_binding(sealed_guard)
    session.finish(); physical_absence(spec, cleanup)
    snapshot['after_validation'] = unchanged_snapshot(snapshot)
    result = dict(old, guard=sealed_guard, finalization=dict(schema=1, no_new_native_execution=True,
        original_phase_only=True, original_receipt=dict(path=str(old_path), sha256=session.retained.rows[str(old_path)]['sha256']),
        retained_metadata=session.retained.rows, stdout_finalization=snapshot, tool=session.tool_binding()))
    target = session.output / 'sealed-original-host-result.json'; write_new(target, result)
    print('CARRIAGE ORIGINAL SEALED: ' + str(target) + '; old native invocation preserved', flush=True)
    return result


def validate_sealed_original(session, path):
    sealed = session.retained.load(Path(path).absolute()); final = sealed['finalization']
    require(final['no_new_native_execution'] is True and final['original_phase_only'] is True
            and final['tool'] == session.tool_binding(), 'Original recovery host lineage differs')
    old = session.generic.artifact(final['original_receipt'])
    original = dict(sealed); original.pop('finalization'); original['guard'] = dict(sealed['guard'], stdout=final['stdout_finalization']['source'])
    require(json.loads(old) == original and sealed['native'] == session.native
            and sealed['spec_sha256'] == session.retained.rows[str(session.root / 'original/spec.json')]['sha256'], 'Sealed original receipt/spec/native differs')
    # Check retained immutable metadata; the old mutable stdout is deliberately not a new guard input.
    for path, row in final['retained_metadata'].items():
        _, current = stable_read(path); require(current == row, 'Sealed original metadata changed')
        require(path not in session.retained.rows or session.retained.rows[path] == row, 'Mixed original metadata identity')
        session.retained.rows[path] = row
    session.generic.guard_binding(sealed['guard'])
    return sealed


def run_current(workspace, output, sealed_original):
    """@cc [owner:fontanierh,label:safety;correctness] carriage-old-driver-host-only-repair
    Current MUST execute only the retained exact source driver under the ordinary
    2400s work/1200s queue/10GiB guard. Every returned exit status MUST be retained
    in new whole metadata before success, cleanup or snapshot gates. A stable full stdout snapshot MUST publish
    immediately after successful whole return and empty owned root/tree. The old
    exact67/81 material/pose comparator and strict cleanup MUST remain unchanged;
    host-tool identity MUST stay separate from native source identity.
    """
    session = Session(workspace, output); original = validate_sealed_original(session, sealed_original)
    spec = session.specs['current']; base = session.root / 'current'; guard_dir = base / 'guard'
    require(not os.environ.get('ATELIER_BUILD_TASK') and not os.environ.get('ATELIER_MESH_REUSE_NONCE'), 'No normal task context allowed')
    for path in (guard_dir, base / 'whole-result.json', base / 'host-result.json', Path(spec['launch']['startup_log'])):
        require(not os.path.lexists(path), 'Fresh current guard/host/startup required')
    fixture = Path(spec['content']) / spec['package'].removeprefix('/Game/')
    require(not os.path.lexists(fixture), 'Previous Carriage fixture remains')
    launch = session.proof.check_private_launch(spec)
    script = session.source / 'games/yorimichi/tests/native/carriage_native_equivalence.py'
    script_row = dict(path=str(script), sha256=spec['inputs'].get(str(script)))
    session.generic.artifact(script_row)
    marker = 'CARRIAGE ACTUAL67/81 VEHICLE FIXTURE COMPLETE current ' + session.retained.rows[str(base / 'spec.json')]['sha256']
    command = build.UnrealScript(script, marker, modules=('Yorimichi',), null_rhi=True,
                                args=('-nosound', '-noshaderworker', *launch['args']))
    session.output.mkdir()
    from atelier.harness.safety import guarded
    with command.prepared(session.ctx) as (argv, overrides):
        require([v for v in argv if v in launch['args']] == launch['args'], 'Old private launch arguments changed')
        env = dict(session.ctx.env(), **dict(overrides), ATELIER_CARRIAGE_NATIVE_SPEC=str(base / 'spec.json'),
                   ATELIER_CARRIAGE_NATIVE_SHA256=session.retained.rows[str(base / 'spec.json')]['sha256'])
        print('CARRIAGE HOST: submitting exact old current driver with 2400s work/1200s queue/10GiB guard', flush=True)
        code = guarded.run(argv, guard_dir, timeout=2400, queue_seconds=1200, limit_gib=10,
            kind='job', purpose='Carriage67 final meshes/all81 authored LOD actual receiving current',
            env=env, progress=15., track_tree=True)
        # Always preserve the actual whole outcome before any success/cleanup/snapshot gate.
        # New metadata identifies the old native driver and separate new host source.
        whole = dict(exit_code=code, native=session.native, phase='current', source_head=SOURCE_HEAD,
            receiving_head=RECEIVING_HEAD, spec_sha256=env['ATELIER_CARRIAGE_NATIVE_SHA256'], work_seconds=2400,
            queue_seconds=1200, launch=launch, argv=argv, native_driver=script_row, host_tool=session.tool_binding())
        whole_row = write_new(session.output / 'whole-result.json', whole)
    require(code == 0, 'Whole current native invocation failed; actual whole outcome retained; original remains sealed')
    empty_owned_tree(guard_dir / 'memory-health-tree.json')
    snapshot = frozen_current_stdout(guard_dir / 'stdout.log', session.output / 'current-stdout.log', marker)
    print('CARRIAGE HOST: froze full current stdout after whole0/empty owned root/tree; validating retained inputs and startup', flush=True)
    receipt = dict(path=str(guard_dir / 'memory-health-tree.json'), sha256=digest(stable_read(guard_dir / 'memory-health-tree.json')[0]))
    evidence = dict(receipt=receipt, stdout=snapshot['snapshot'], marker=marker, whole_result=whole_row)
    session.generic.guard_binding(evidence)
    session.inputs()
    engine = Path(launch['startup_log']); engine_row = dict(path=str(engine), sha256=digest(stable_read(engine)[0]))
    ddc = session.proof.startup_ddc(launch, session.generic.artifact(engine_row).decode(errors='replace'))
    current_host = dict(schema=1, complete=False, native_complete=False, whole_exit=0, guard_empty=True,
        fixture_absent=True, phase='current', spec_sha256=whole['spec_sha256'], native=session.native, guard=evidence,
        source_head=SOURCE_HEAD, receiving_head=RECEIVING_HEAD, launch=launch, startup_ddc=ddc, engine_log=engine_row,
        host_tool=session.tool_binding(), native_driver=script_row, stdout_finalization=snapshot)
    session.startup('current', current_host)
    cleanup = session.retained.load(base / 'cleanup.json')
    session.api['run_track_native_equivalence'].strict_cleanup(spec, cleanup)
    require(not os.path.lexists(fixture), 'Current Carriage fixture survived strict cleanup')
    records, vehicles, current_materials, current_poses = session.metadata('current')
    old_records, _, old_materials, old_poses = session.metadata('original'); records.update(old_records)
    print('CARRIAGE HOST: exact old67/81 geometry/material/pose comparison; original capture retained', flush=True)
    compared = session.proof.compare(records, vehicles,
        dict(original=old_materials, current=current_materials), dict(original=old_poses, current=current_poses))
    session.finish(); session.generic.guard_binding(original['guard']); session.generic.guard_binding(evidence)
    physical_absence(session.specs['original'], session.retained.load(session.root / 'original/cleanup.json'))
    require(not os.path.lexists(fixture), 'Current Carriage fixture reappeared')
    _, frozen = stable_read(snapshot['snapshot']['path']); require(frozen == snapshot['snapshot_identity'], 'Current frozen stdout changed')
    write_new(session.output / 'current-host-result.json', current_host)
    paired = dict(**compared, whole_exit=0, guards_empty=True, fixture_absent=True, source_head=SOURCE_HEAD,
        receiving_head=RECEIVING_HEAD, native=session.native, original_guard=original['guard'], current_guard=evidence,
        host_orchestration=dict(tool=session.tool_binding(), native_driver=script_row,
            sealed_original=dict(path=str(Path(sealed_original).absolute()), sha256=session.retained.rows[str(Path(sealed_original).absolute())]['sha256']),
            retained_metadata=session.retained.rows, current_stdout=snapshot))
    target = session.output / 'paired-host-result.json'; write_new(target, paired)
    print('CARRIAGE PAIRED HOST COMPLETE: ' + str(target) + '; finite fixture scope only', flush=True)
    return paired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('seal-original', 'run-current'))
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sealed-original', type=Path)
    args = parser.parse_args()
    if args.action == 'seal-original':
        require(args.sealed_original is None, 'Original recovery does not consume a prior recovery')
        seal_original(args.workspace, args.output)
    else:
        require(args.sealed_original is not None, 'Current requires the independently sealed original receipt')
        run_current(args.workspace, args.output, args.sealed_original)


if __name__ == '__main__':
    main()
