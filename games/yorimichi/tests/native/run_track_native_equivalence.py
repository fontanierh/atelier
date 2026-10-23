"""Parent-invoked guarded Track phase/finalizer. Never launch on import.

Run from the parent's stopped receiving checkout after source review. Preparation
is separate; the runner does not update source, compile, restore packages or stamp
tasks. Each selected phase requires a fresh guard and physical fixture absence.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from atelier import build
from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

GAME = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(GAME / 'tools'), str(Path(__file__).parent)]
from atomic_equivalence import artifact, guard_binding, require  # noqa: E402
from track_native_equivalence import bound_inputs, check_private_launch, compare, fixture_files, sha, startup_ddc  # noqa: E402


def head(root):
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root), 'Receiving/source checkout must stay clean')
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()


def binding(path):
    path = Path(path).absolute()
    row = dict(path=str(path), sha256=sha(path)); artifact(row)
    return row


def strict_cleanup(spec, record):
    """Remove only SHA-exact fixture remnants after positive whole/empty evidence."""
    folder = Path(spec['content']) / spec['package'].removeprefix('/Game/')
    require(Path(record['root']) == folder, 'Track cleanup root escaped fixture')
    packages = record['allowed_packages']
    require(packages and len(set(packages)) == len(packages) and all(
            path.startswith(spec['package'] + '/') and '..' not in path.split('/') for path in packages),
            'Track cleanup package authority is incomplete')
    observed = fixture_files(folder, packages, spec['package'])
    require(observed == record['remaining'], 'Track residual bytes/membership differ')
    directories = {folder}
    for package in packages:
        parent = folder / Path(package.removeprefix(spec['package'] + '/')).parent
        while parent != folder:
            directories.add(parent); parent = parent.parent
    # Complete no-link/type/directory preflight precedes the first unlink.
    if folder.exists():
        for path in folder.rglob('*'):
            mode = path.lstat().st_mode
            require(stat.S_ISREG(mode) or (stat.S_ISDIR(mode) and path in directories),
                    'Foreign/special Track fixture directory entry')
        for relative in observed:
            (folder / relative).unlink()
        for path in sorted((p for p in directories if p.exists()), key=lambda p: len(p.parts), reverse=True):
            path.rmdir()
    require(not os.path.lexists(folder), 'Track fixture directory survived cleanup')


def run(workspace, phase):
    root = real_directory(Path(workspace).absolute()); output = root / phase
    spec_path = output / 'spec.json'; spec_binding = binding(spec_path)
    payload = artifact(spec_binding); spec = json.loads(payload)
    require(spec['phase'] == phase, 'Wrong Track phase')
    receiver, source = Path(spec['receiving']), Path(spec['source'])
    require(Path.cwd().resolve() == receiver.resolve(), 'Run through the receiving checkout uv environment')
    require(head(receiver) == spec['receiving_head'] and head(source) == spec['source_head'], 'Track source changed')
    bound_inputs(spec)
    launch = check_private_launch(spec)
    require(not os.path.lexists(launch['startup_log']), 'Fresh bound Track engine log required')
    guard = output / 'guard'
    require(not os.path.lexists(guard) and not os.path.lexists(output / 'whole-result.json'), 'Fresh Track phase guard required')
    fixture = Path(spec['content']) / spec['package'].removeprefix('/Game/')
    real_directory(fixture)
    require(not os.path.lexists(fixture), 'Previous Track fixture remains physically present')
    if phase == 'current':
        previous = json.loads((root / 'original/host-result.json').read_bytes())
        require(previous['whole_exit'] == 0 and previous['guard_empty'] and previous['fixture_absent']
                and previous['spec_sha256'] == sha(root / 'original/spec.json'), 'Original phase not independently finalized')
        guard_binding(previous['guard'])
    ctx = build.Context('yorimichi')
    require(ctx.game_dir == receiver / 'games/yorimichi', 'Wrong actual receiving project')
    sys.path.insert(0, str(receiver / 'games/yorimichi/tools'))
    from network_review_common import current_native_build
    native = current_native_build(ctx)
    script = Path(__file__).with_name('track_native_equivalence.py')
    require(str(script.absolute()) in spec['inputs'] and sha(script) == spec['inputs'][str(script.absolute())],
            'Unbound Track native driver')
    marker = 'TRACK ACTUAL ORIGINAL/CURRENT137/362 NATIVE FIXTURE COMPLETE ' + phase + ' ' + spec_binding['sha256']
    command = build.UnrealScript(script, marker, modules=('Yorimichi',), null_rhi=True,
                                args=('-nosound', '-noshaderworker', *launch['args']))
    with command.prepared(ctx) as (argv, overrides):
        require([value for value in argv if value in launch['args']] == launch['args'], 'Prepared private args changed')
        env = dict(ctx.env(), **dict(overrides), ATELIER_TRACK_NATIVE_SPEC=str(spec_path),
                   ATELIER_TRACK_NATIVE_SHA256=spec_binding['sha256'])
        code = guarded.run(argv, guard, timeout=2400, queue_seconds=1200, limit_gib=10,
            kind='job', purpose='Track137 whole meshes/all362 authored LOD actual receiving ' + phase,
            env=env, progress=15., track_tree=True)
    atomic_json(output / 'whole-result.json', dict(exit_code=code, native=native, phase=phase,
        source_head=spec['source_head'], receiving_head=spec['receiving_head'], spec_sha256=spec_binding['sha256'],
        work_seconds=2400, queue_seconds=1200, launch=launch, argv=argv))
    if code: raise SystemExit(code)
    evidence = dict(receipt=binding(guard / 'memory-health-tree.json'), stdout=binding(guard / 'stdout.log'),
                    marker=marker, whole_result=binding(output / 'whole-result.json'))
    guard_binding(evidence)
    require(current_native_build(ctx) == native and head(receiver) == spec['receiving_head']
            and head(source) == spec['source_head'], 'Actual native/source identity changed')
    bound_inputs(spec); require(artifact(spec_binding) == payload, 'Track phase spec changed')
    engine_log = binding(launch['startup_log'])
    observed_ddc = startup_ddc(launch, artifact(engine_log).decode(errors='replace'))
    native_startup = json.loads((output / 'startup-ddc.json').read_bytes())
    require(native_startup['launch'] == launch and all(native_startup[key] == value for key, value in observed_ddc.items()),
            'Startup/native private DDC evidence differs')
    records = json.loads((output / 'native.json').read_bytes())
    require(set(records) == {phase}, 'Unexpected Track phase records')
    strict_cleanup(spec, json.loads((output / 'cleanup.json').read_bytes()))
    result = dict(schema=1, complete=False, native_complete=False, whole_exit=0, guard_empty=True,
        fixture_absent=True, phase=phase, spec_sha256=spec_binding['sha256'], native=native, guard=evidence,
        source_head=spec['source_head'], receiving_head=spec['receiving_head'], launch=launch, startup_ddc=observed_ddc,
        engine_log=engine_log)
    atomic_json(output / 'host-result.json', result)
    if phase == 'current':
        original = json.loads((root / 'original/native.json').read_bytes())
        original.update(records)
        runtime = json.loads((Path(spec['current_track']) / 'runtime/track.json').read_bytes())
        compared = compare(original, runtime)
        original_host = json.loads((root / 'original/host-result.json').read_bytes())
        require(original_host['native'] == native, 'Original/current actual native modules differ')
        atomic_json(root / 'host-result.json', dict(**compared, whole_exit=0, guards_empty=True,
            fixture_absent=True, source_head=spec['source_head'], receiving_head=spec['receiving_head'], native=native,
            original_guard=original_host['guard'], current_guard=evidence))
    print('TRACK GUARDED PHASE FINALIZED ' + phase + '; fixture scope only', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--phase', choices=('original', 'current'), required=True)
    args = parser.parse_args(); run(args.workspace, args.phase)


if __name__ == '__main__': main()
