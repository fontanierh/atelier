"""Host-only append-only Folia receipt finalization; never executes native work.

Run only after both native phases stopped. Old receipts remain immutable. A fresh
output directory receives exact stdout snapshots and a new, explicitly scoped
receipt after the original comparator and all old input/native gates pass again.
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
APPROVED_TAIL_SHA256 = '90aa320285072b3f06d6ec40ec318300c42a96cbbff32daa392a8d8a46b969f8'
SOURCE_HEAD = 'b59638ab175e14df1288f2cb7b6f41b6c2a90a08'
RECEIVING_HEAD = 'e1a700a24b95f83254379eb2d30a4f7551b76f05'


def trace_tail(tail):
    """Admit exactly the reviewed 825-byte TraceServer tail, never a log grammar."""
    require(len(tail) == APPROVED_TAIL_BYTES and digest(tail) == APPROVED_TAIL_SHA256,
            'Unknown stdout append; only the exact reviewed TraceServer shutdown tail is admitted')


def prefix_proof(payload, expected):
    """@cc [owner:fontanierh,label:correctness] folia-retained-stdout-prefix
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


def physical_cleanup(spec, cleanup):
    """Read-only check of this Folia fixture only, never other Content or assets."""
    package = spec['package']
    require(re.fullmatch('/Game/AtelierValidation/Foliage_[0-9a-f]{12}', package) is not None, 'Foreign Folia namespace')
    folder = Path(spec['content']) / package.removeprefix('/Game/')
    require(cleanup['root'] == str(folder) and cleanup['remaining'] == {} and cleanup['allowed_packages']
            and len(set(cleanup['allowed_packages'])) == len(cleanup['allowed_packages'])
            and all(p.startswith(package + '/') and '..' not in p.split('/') for p in cleanup['allowed_packages']),
            'Incomplete or foreign Folia cleanup record')
    for parent in folder.parents:
        require(not parent.is_symlink(), 'Linked fixture ancestor')
    require(not os.path.lexists(folder), 'Original Folia fixture is not physically absent')


def original_api(source, spec):
    """Import the retained comparator from the old source, never the new tool tree."""
    game = source / 'games/yorimichi'; native = game / 'tests/native'; tools = game / 'tools'
    for name in ('foliage_native_equivalence', 'track_native_equivalence', 'atomic_equivalence',
                 'atomic_equivalence_io', 'run_track_native_equivalence', 'network_review_common'):
        require(name not in sys.modules, 'Comparator modules already loaded; start a fresh host process')
    sys.path[:0] = [str(native), str(tools), str(game / 'world')]
    modules = {name: importlib.import_module(name) for name in
               ('foliage_native_equivalence', 'atomic_equivalence', 'track_native_equivalence', 'network_review_common')}
    for module in modules.values():
        path = str(Path(module.__file__).absolute())
        require(path in spec['inputs'] and digest(Path(path).read_bytes()) == spec['inputs'][path],
                'Comparator is not the original source-bound module')
    return modules


def finalize(workspace, output):
    """@cc [owner:fontanierh,label:correctness] folia-host-only-finalization-lineage
    New receipts MUST preserve old phase/paired receipts with exact SHA lineage,
    use the original input/native/comparison gates and physically absent Folia
    namespace, and bind stable full stdout snapshots across comparison. No native
    execution, cleanup mutation, task reuse or production-runtime claim is allowed.
    """
    root, output = Path(workspace).absolute(), Path(output).absolute()
    require(root.is_dir() and not root.is_symlink() and output.parent == root
            and re.fullmatch('finalized-[A-Za-z0-9_-]+', output.name) is not None
            and not os.path.lexists(output), 'Fresh direct finalized-* output directory required')
    retained = {}
    def load(path):
        payload, observed = stable_read(path)
        retained[str(path)] = observed
        return json.loads(payload)
    old = load(root / 'host-result.json')
    phases = {phase: load(root / phase / 'host-result.json') for phase in ('original', 'current')}
    specs = {phase: load(root / phase / 'spec.json') for phase in phases}
    source = Path(specs['original']['source']); receiver = Path(specs['original']['receiving'])
    require(all(s['source_head'] == SOURCE_HEAD and s['receiving_head'] == RECEIVING_HEAD for s in specs.values()),
            'This recovery only admits the reviewed source and receiving heads')
    tool = Path(__file__).absolute(); tool_bytes, tool_identity = stable_read(tool)
    tool_head = clean_head(tool.parents[4])
    # Refuse dirty/changed executable source before importing any of its code.
    for spec in specs.values():
        for key in ('source', 'receiving', 'producer'):
            require(clean_head(Path(spec[key])) == spec[key + '_head'], 'Original executable source head changed')
    api = original_api(source, specs['original']); proof = api['foliage_native_equivalence']
    generic = api['atomic_equivalence']; track = api['track_native_equivalence']
    from atelier import build
    require(Path.cwd().resolve() == receiver.resolve(), 'Run in the stopped receiving checkout')
    ctx = build.Context('yorimichi')
    require(ctx.game_dir == receiver / 'games/yorimichi', 'Wrong receiving project')
    native_identity = lambda: api['network_review_common'].current_native_build(ctx)
    def inputs():
        for phase, spec in specs.items():
            require(spec['phase'] == phase and spec['source'] == str(source) and spec['receiving'] == str(receiver), 'Mixed phase source/receiver')
            for key in ('source', 'receiving', 'producer'):
                require(clean_head(Path(spec[key])) == spec[key + '_head'], 'Original source/receiver/producer head changed')
            proof.bound_inputs(spec)
    print('FOLIA HOST FINALIZER: validating retained inputs and native identities; no native execution', flush=True)
    inputs(); native = native_identity()
    require(native == old['native'] and all(p['native'] == native for p in phases.values()), 'Original compiled native identity changed')
    guards = {}; cleanup_records = {}; records = {}
    for phase, phase_host in phases.items():
        spec = specs[phase]; whole = load(root / phase / 'whole-result.json')
        require(whole['phase'] == phase and whole['exit_code'] == 0 and whole['native'] == native
                and whole['spec_sha256'] == retained[str(root / phase / 'spec.json')]['sha256'] == phase_host['spec_sha256'], 'Original whole/spec binding differs')
        for key in ('source_head', 'receiving_head', 'producer_head'):
            require(whole[key] == spec[key], 'Original whole head differs')
        require(phase_host['whole_exit'] == 0 and phase_host['guard_empty'] is True and phase_host['fixture_absent'] is True,
                'Original phase did not finish empty and successful')
        guard = phase_host['guard']; require(guard == old[phase + '_guard'], 'Paired guard differs from original phase')
        require(guard['stdout']['path'] == str(root / phase / 'guard/stdout.log')
                and guard['receipt']['path'] == str(root / phase / 'guard/memory-health-tree.json')
                and guard['whole_result']['path'] == str(root / phase / 'whole-result.json'), 'Foreign phase guard evidence')
        marker = 'FOLIAGE ACTUAL18/84/150 NATIVE FIXTURE COMPLETE ' + phase + ' ' + phase_host['spec_sha256']
        require(guard['marker'] == marker, 'Original phase marker differs')
        launch = track.check_private_launch(spec)
        require(whole['launch'] == phase_host['launch'] == old['launches'][phase] == launch
                and '-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0' in whole['argv'], 'Original private launch/DPCVars differ')
        engine_log = generic.artifact(phase_host['engine_log']).decode(errors='replace')
        require(track.startup_ddc(launch, engine_log) == phase_host['startup_ddc'], 'Original startup DDC differs')
        cleanup_records[phase] = load(root / phase / 'cleanup.json'); physical_cleanup(spec, cleanup_records[phase])
        phase_records = load(root / phase / 'native.json')
        require(set(phase_records) == {phase}, 'Foreign phase native records'); records.update(phase_records)
    output.mkdir()
    for phase, phase_host in phases.items():
        snapshot = snapshot_stdout(phase_host['guard']['stdout'], output / (phase + '-stdout.log'))
        require(snapshot['classifier'] == ('unchanged' if phase == 'original' else 'reviewed-traceserver-tail-825-sha256-v1'),
                'This recovery requires the unchanged original log and exact reviewed current append')
        guards[phase] = dict(phase_host['guard'], stdout=snapshot['snapshot'])
        generic.guard_binding(guards[phase])
        phases[phase] = dict(original_receipt=phases[phase], stdout_finalization=snapshot)
    print('FOLIA HOST FINALIZER: rerunning original exact paired geometry comparator', flush=True)
    compared = proof.compare(records, specs['current']['manifests'])
    expected = dict(**compared, whole_exit=0, guards_empty=True, fixture_absent=True, native=native,
                    source_head=specs['current']['source_head'], receiving_head=specs['current']['receiving_head'],
                    original_guard=phases['original']['original_receipt']['guard'],
                    current_guard=phases['current']['original_receipt']['guard'], launches=old['launches'])
    require(old == expected, 'Retained paired receipt differs from rerun original comparison')
    inputs(); require(native_identity() == native, 'Compiled native identity changed across comparison')
    for phase in phases:
        physical_cleanup(specs[phase], cleanup_records[phase])
        phases[phase]['stdout_finalization']['after_comparison'] = unchanged_snapshot(phases[phase]['stdout_finalization'])
        generic.guard_binding(guards[phase])
    for path, before in retained.items():
        _, after = stable_read(path); require(after == before, 'Retained evidence changed across comparison')
    current_tool, after_tool = stable_read(tool)
    require(current_tool == tool_bytes and after_tool == tool_identity and clean_head(tool.parents[4]) == tool_head,
            'Independent finalizer source changed')
    result = dict(expected, original_guard=guards['original'], current_guard=guards['current'],
                  finalization=dict(schema=1, no_new_native_execution=True, original_receipts={
                      str(root / name): dict(path=str(root / name), sha256=retained[str(root / name)]['sha256'])
                      for name in ('host-result.json', 'original/host-result.json', 'current/host-result.json')},
                      tool=dict(path=str(tool), sha256=digest(tool_bytes), head=tool_head), phases=phases,
                      retained_metadata=retained))
    target = output / 'finalized-host-result.json'
    payload = json.dumps(result, sort_keys=True).encode() + b'\n'
    with target.open('xb') as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.chmod(target, 0o444)
    print('FOLIA HOST FINALIZER: wrote ' + str(target) + '; fixture geometry scope only', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); finalize(args.workspace, args.output)


if __name__ == '__main__':
    main()
