"""Hidamari's final harbour source: the audited rail opening, with its source identity checked before import."""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify(base, records):
    if not records:
        raise ValueError('Hidamari ferry access proof is missing source identities')
    for relative, wanted in records.items():
        path = base / relative
        if not path.is_file() or sha(path) != wanted:
            raise ValueError(f'Hidamari ferry access source changed: {relative}')


def validated_harbor(build, repo):
    """@cc [owner:fontanierh,label:correctness] hidamari-ferry-package-source
    Refuse missing/failed cuts or changed cut code, base mesh, sweep proof and final bytes.

    The bounded city owner MUST select this same validated opening for every Harbor piece.
    Reimporting the world MUST NOT recreate the retired parent; a later transport import
    MUST NOT patch the parent or piece packages.
    """
    build, repo = Path(build), Path(repo)
    target = build / 'hidamari/ferry/HD_Harbor.fbx'
    cut = json.loads((target.parent / 'cut.json').read_text())
    site_path = build / 'ferry/terminals/site.json'
    site = json.loads(site_path.read_text())
    if (cut.get('failures') != [] or not cut.get('cuts') or
            not all(c.get('cap_normals_pass') is True for c in cut['cuts']) or site.get('pass') is not True):
        raise ValueError('Hidamari ferry access cut or sweep failed')
    if cut.get('source') != 'hidamari/assets/HD_Harbor.fbx' or cut.get('site') != 'ferry/terminals/site.json':
        raise ValueError('Hidamari ferry access proof names a different source')
    paths = (repo / 'games/yorimichi/world/regions/hidamari/ferry_cut.py',
             build / cut['source'], site_path)
    expected = {str(p.relative_to(repo)) if p.is_relative_to(repo) else p.name: sha(p) for p in paths}
    if cut.get('inputs') != expected or not target.is_file() or sha(target) != cut.get('output_sha256'):
        raise ValueError('Hidamari ferry access cut inputs or final mesh changed')
    _verify(repo, site['inputs']['code'])
    probes = site['inputs'].get('world_probes')
    if not probes or set(probes) != {'hidamari', 'brinecove', 'crossing'}:
        raise ValueError('Hidamari ferry sweep is missing world probe identities')
    _verify(build / 'ferry/terminals', {f'world_{name}.npz': value for name, value in probes.items()})
    for records in site['inputs']['exports'].values():
        _verify(build, records)
    return target


def validated_atomic_harbor(build, repo):
    """@cc [owner:fontanierh,label:correctness] independently-exported-ferry-opening
    The production ferry MUST validate the full sweep proof, projected cut fields,
    original raw source membership, final geometry plan and final query bytes.
    Every cut MUST succeed with capped normals before any final receiving or
    service publication. No monolithic Harbor FBX is required or reconstructed.
    """
    from atelier.export_manifest import real_directory
    from regions.ferry import site_inputs
    from region_plan_files import files
    build,repo = real_directory(build),real_directory(repo)
    site_inputs.validate(build,repo)
    cut_path = site_inputs.path(build,'hidamari/final-source-data/harbor-cut.json')
    cut = json.loads(cut_path.read_text())
    projection = site_inputs.path(build,'hidamari/final-source-data/harbor-cut-data.json')
    if json.loads(projection.read_text())!=site_inputs.projection(build,repo):
        raise ValueError('Final Harbor parameters differ from current ferry sweep')
    if (cut.get('schema')!=1 or cut.get('complete') is not True or cut.get('failures')!=[]
            or not cut.get('cuts') or not all(row.get('cap_normals_pass') is True for row in cut['cuts'])
            or cut.get('cut_data_sha256')!=sha(projection)):
        raise ValueError('Final Harbor source cut is incomplete or stale')
    raw = build/'hidamari/source-data/HD_Harbor'
    inputs = {relative:sha(raw/relative) for relative in files(raw)}
    if inputs!=cut.get('raw_source'): raise ValueError('Harbor raw geometry changed after the cut')
    plan = site_inputs.path(build,'planned_exports/hidamari/HD_Harbor/plan.json')
    query = site_inputs.path(build,'hidamari/query-data/HD_Harbor.npz')
    if sha(plan)!=cut.get('plan_sha256') or sha(query)!=cut.get('query_sha256'):
        raise ValueError('Final Harbor plan/query differs from cut proof')
    value = json.loads(plan.read_text())
    if (value.get('complete') is not True or value.get('parent')!='HD_Harbor'
            or value.get('source_triangles')!=cut['triangles']['after']):
        raise ValueError('Incomplete final Harbor geometry')
    from region_plan_files import payloads
    expected = payloads('HD_Harbor',[row['payload'] for row in value['pieces']])
    if files(plan.parent)!=expected|{'plan.json'}:
        raise ValueError('Incomplete or foreign final Harbor payloads')
    for row in value['pieces']:
        if sha(plan.parent/row['payload'])!=row['sha256']:
            raise ValueError('Final Harbor payload changed after cut')
    # Exact files are returned for service evidence; this never imports old FBX.
    records = [cut_path,projection,plan,query,*(raw/relative for relative in inputs),
               *(plan.parent/relative for relative in expected)]
    records.extend(site_inputs.paths(build,repo))
    return {str(path.relative_to(build)):sha(path) for path in records if path.is_relative_to(build)}
