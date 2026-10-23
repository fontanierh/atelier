"""Private one-off host revalidation of retained Carriage67/81 captures. No native launch.

The original f375 driver and87ae orchestration remain frozen. Only the reviewed
public material identity policy changes, and every other comparator AST node and
retained native/input/archive gate stays unchanged. All reports are new files.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess

# Preserve the receiver environment before any old/new source yori path adaptation.
from atelier import build

OLD_HOST_HEAD = '87ae89eee99950e30ebae14a6d726255aee5acb8'
OLD_HOST_SHA = '43c9afb7688755ad01de4bcfe332e9d60414bc9a17115abe98bdd71bed6714f8'
NEW_COMPARATOR_HEAD = 'ca3859d41abfd2d4ce707f2df0a7dbc619bcfe1f'
NEW_COMPARATOR_SHA = 'eb6f93a1823f45f1058d2395aa5ec32c33c9037a40334fd020f52740ff8287af'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def clean_head(root):
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root), 'Source checkout is not clean')
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()


def load_host(path):
    path = Path(path).absolute()
    payload = path.read_bytes()
    require(clean_head(path.parents[4]) == OLD_HOST_HEAD and digest(payload) == OLD_HOST_SHA,
            'Original host tool identity changed')
    loading = importlib.util.spec_from_file_location('retained_carriage_host', path)
    module = importlib.util.module_from_spec(loading)
    exec(compile(payload, str(path), 'exec'), module.__dict__)
    return module


def comparator_boundary(old_payload, new_payload):
    """Every module AST node except material_text must match the retained driver."""
    def outside(payload):
        tree = ast.parse(payload)
        found = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'material_text']
        require(len(found) == 1, 'Exactly one material_text policy required')
        tree.body.remove(found[0]); return ast.dump(tree)
    require(outside(old_payload) == outside(new_payload), 'Comparator changed outside reviewed material_text policy')


def load_comparator(session, source):
    source = Path(source).absolute(); path = source / 'games/yorimichi/tests/native/carriage_native_equivalence.py'
    require(clean_head(source) == NEW_COMPARATOR_HEAD, 'Wrong reviewed public comparator revision')
    payload, observed = session.host.stable_read(path)
    require(digest(payload) == NEW_COMPARATOR_SHA, 'Public comparator SHA differs')
    old_path = Path(session.proof.__file__).absolute()
    old_payload = session.generic.artifact(dict(path=str(old_path), sha256=session.specs['current']['inputs'][str(old_path)]))
    comparator_boundary(old_payload, payload)
    # Session already loaded all old source-bound dependencies. The new module's
    # imports therefore retain those exact f375 validators, not new helper forks.
    loading = importlib.util.spec_from_file_location('reviewed_carriage_material_policy', path)
    module = importlib.util.module_from_spec(loading)
    exec(compile(payload, str(path), 'exec'), module.__dict__)
    require(module.native_raw_set is session.proof.native_raw_set and module.artifact is session.proof.artifact,
            'Retained raw geometry/artifact validators were replaced')
    return module, dict(path=str(path), head=NEW_COMPARATOR_HEAD, sha256=digest(payload)), observed


def bind_file(session, path):
    path = Path(path).absolute(); payload, observed = session.host.stable_read(path)
    require(str(path) not in session.retained.rows or session.retained.rows[str(path)] == observed, 'Mixed retained file identity')
    session.retained.rows[str(path)] = observed
    return dict(path=str(path), sha256=digest(payload))


def prior_rejection(proof, records, vehicles, materials, poses, package):
    expected = 'Actual material/texture differs: ' + package + '/Source/SM_BT_BaggageVan/LOD0/M_BT_Brass/text'
    try:
        proof.compare(records, vehicles, materials, poses)
    except ValueError as error:
        require(str(error) == expected, 'Old comparator failed for a different reason: ' + str(error))
        return dict(accepted=False, reproduced_from_retained_data=True, exception_class=type(error).__name__, message=str(error))
    raise ValueError('Old comparison unexpectedly accepted; original failed comparison not reproduced')


def revalidate(workspace, output, sealed_original, current_host, host_tool, comparator_source):
    """@cc [owner:fontanierh,label:correctness] retained-carriage-new-policy-lineage
    Revalidation MUST execute no native work and preserve all old captures,
    receipts and failed comparison. Only the separately pinned public
    material_text policy MAY differ; old native/source/input/archive, whole0,
    frozen stdout, physical absence, geometry/material/query/pose gates MUST
    revalidate before a new finite-scope report. Source/native/input identities
    MUST remain current before and after comparison. Failure MUST never publish
    an accepted paired report or overwrite an existing report.
    """
    host = load_host(host_tool)
    tool = Path(__file__).absolute(); tool_payload, tool_observed = host.stable_read(tool)
    own_head = clean_head(tool.parents[4]); own = dict(path=str(tool), head=own_head, sha256=digest(tool_payload))
    print('CARRIAGE REVALIDATION: checking retained source/receiver/native identities; no native execution', flush=True)
    session = host.Session(workspace, output); session.host = host
    require(Path(build.__file__).absolute().is_relative_to(session.receiver / 'platform/studio'), 'Wrong receiver build environment')
    original = host.validate_sealed_original(session, sealed_original)
    base = session.root / 'current'; current_host = Path(current_host).absolute()
    require(current_host == session.root / 'current-host-01', 'Wrong retained current host attempt')
    whole_path = current_host / 'whole-result.json'; whole = session.retained.load(whole_path)
    spec = session.specs['current']; driver = session.source / 'games/yorimichi/tests/native/carriage_native_equivalence.py'
    driver_binding = dict(path=str(driver), sha256=spec['inputs'][str(driver)])
    require(whole['exit_code'] == 0 and whole['phase'] == 'current' and whole['native'] == session.native
            and whole['source_head'] == host.SOURCE_HEAD and whole['receiving_head'] == host.RECEIVING_HEAD
            and whole['spec_sha256'] == session.retained.rows[str(base / 'spec.json')]['sha256']
            and whole['native_driver'] == driver_binding and whole['host_tool'] == session.tool_binding()
            and whole['work_seconds'] == 2400 and whole['queue_seconds'] == 1200
            and whole['launch'] == spec['launch'], 'Retained current whole/source/native/host identity differs')
    session.generic.artifact(driver_binding)
    require([arg for arg in whole['argv'] if arg in spec['launch']['args']] == spec['launch']['args'], 'Old launch argument binding differs')
    tree = base / 'guard/memory-health-tree.json'; host.empty_owned_tree(tree)
    marker = 'CARRIAGE ACTUAL67/81 VEHICLE FIXTURE COMPLETE current ' + whole['spec_sha256']
    snapshot = current_host / 'current-stdout.log'
    require(stat.S_IMODE(host.regular(snapshot).st_mode) == 0o444, 'Retained current stdout snapshot is not read-only')
    guard = dict(receipt=bind_file(session, tree), stdout=bind_file(session, snapshot), marker=marker,
                 whole_result=bind_file(session, whole_path))
    session.generic.guard_binding(guard)
    launch = session.proof.check_private_launch(spec); engine = bind_file(session, launch['startup_log'])
    ddc = session.proof.startup_ddc(launch, session.generic.artifact(engine).decode(errors='replace'))
    session.startup('current', dict(launch=launch, engine_log=engine, startup_ddc=ddc))
    cleanup = {p: session.retained.load(session.root / p / 'cleanup.json') for p in ('original', 'current')}
    for phase in cleanup:
        host.physical_absence(session.specs[phase], cleanup[phase])
    records, vehicles, current_materials, current_poses = session.metadata('current')
    old_records, _, old_materials, old_poses = session.metadata('original'); records.update(old_records)
    materials = dict(original=old_materials, current=current_materials); poses = dict(original=old_poses, current=current_poses)
    new, comparator, comparator_observed = load_comparator(session, comparator_source)
    old_comparator = dict(path=str(Path(session.proof.__file__).absolute()), head=host.SOURCE_HEAD,
                          sha256=spec['inputs'][str(Path(session.proof.__file__).absolute())])
    session.output.mkdir()
    lineage = dict(host_tool=own, retained_host_tool=session.tool_binding(), native_driver=driver_binding,
                   native_source_head=host.SOURCE_HEAD, comparator=comparator, old_comparator=old_comparator,
                   sealed_original=bind_file(session, sealed_original), current_whole=bind_file(session, whole_path),
                   original_guard=original['guard'], current_guard=guard, no_new_native_execution=True,
                   prior_host_pair_not_accepted=True)
    try:
        print('CARRIAGE REVALIDATION: reproducing old strict material rejection; prior failure remains retained', flush=True)
        rejected = prior_rejection(session.proof, records, vehicles, materials, poses, spec['package'])
        lineage['old_comparison_observation'] = host.write_new(session.output / 'old-comparison-observation.json',
            dict(**rejected, comparator=old_comparator))
        print('CARRIAGE REVALIDATION: full retained67/81 source/GPU/cooked/archive/material/PNG/query/pose comparison', flush=True)
        compared = new.compare(records, vehicles, materials, poses)
        session.finish(); host.empty_owned_tree(tree)
        session.generic.guard_binding(original['guard']); session.generic.guard_binding(guard)
        for phase in cleanup:
            host.physical_absence(session.specs[phase], cleanup[phase])
        public_payload, public_observed = host.stable_read(comparator['path'])
        require(public_observed == comparator_observed and digest(public_payload) == comparator['sha256']
                and clean_head(Path(comparator_source).absolute()) == comparator['head'], 'New public comparator changed across comparison')
        own_payload, own_observed = host.stable_read(tool)
        require(own_payload == tool_payload and own_observed == tool_observed and clean_head(tool.parents[4]) == own_head,
                'Independent revalidation tool changed')
        result = dict(**compared, whole_exit=0, guards_empty=True, fixture_absent=True, native=session.native,
            source_head=host.SOURCE_HEAD, receiving_head=host.RECEIVING_HEAD,
            original_guard=original['guard'], current_guard=guard,
            revalidation=dict(**lineage, old_comparison=rejected, retained_metadata=session.retained.rows,
                material_scope='Only exact class/depth MIC ParameterStateId/LightingGuid and existing Texture2D LightingGuid identities; static-lighting/texture-streaming build identity and production runtime excluded'))
        target = session.output / 'paired-revalidation-result.json'; host.write_new(target, result)
    except Exception as error:
        host.write_new(session.output / 'revalidation-failure.json', dict(accepted=False, lineage=lineage,
            exception_class=type(error).__name__, message=str(error)))
        raise
    print('CARRIAGE RETAINED REVALIDATION COMPLETE: ' + str(target) + '; finite fixture scope only', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'output', 'sealed-original', 'current-host', 'host-tool', 'comparator-source'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    revalidate(args.workspace, args.output, args.sealed_original, args.current_host, args.host_tool, args.comparator_source)


if __name__ == '__main__':
    main()
