"""Separate original complete kit audit, textures and selected authored collision."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

WORLD = Path(__file__).resolve().parents[2]
KIT = WORLD.parent / 'assets/vehicles/gondola'
sys.path[:0] = [str(KIT), str(WORLD)]
import yori  # noqa: E402,F401
import bpy  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from regions.gondola.kit_sources import recording, RENDER, COLLISION  # noqa: E402
from regions.gondola.plan_kit import FIELDS, source  # noqa: E402
import params as P  # noqa: E402
import solid  # noqa: E402
import cabin  # noqa: E402
import stations  # noqa: E402
import tower  # noqa: E402


def query_mesh(root, key):
    value = source(root / (key + '.json'), key)
    if set(value['mesh']) != set(FIELDS): raise ValueError('Incomplete Gondola pre-export mesh queries')
    m = solid.Mesh(key)
    for field in FIELDS: setattr(m, field, value['mesh'][field])
    m.parts = [tuple(row) for row in m.parts]
    return m


def audit(queries, output):
    spec = importlib.util.spec_from_file_location('gondola_original_audit', KIT / 'build.py')
    K = importlib.util.module_from_spec(spec); spec.loader.exec_module(K)
    K.OUT = output
    output.mkdir(parents=True, exist_ok=True)
    p = dict(P.DEFAULTS); d = P.derived(p)
    # This evaluates metadata/queries only: recording refuses unrecognized operations
    # and never calls a primitive. Actual geometry comes exclusively from queries.
    with recording(cabin, stations, tower):
        c = cabin.Cabin(p,d); recorded, doors = c.build()
        cab_prepared = c, {key: query_mesh(queries,key) for key in recorded}, doors
        towers = {}
        for height in p['tower_heights']:
            t = tower.Tower(p,height); recorded = t.build()
            towers[height] = t, query_mesh(queries, recorded.name)
        station_data = {}
        for key in ('valley','rim','crater'):
            st = stations.STATIONS[key](key,p,d); recorded = st.make()
            station_data[key] = st, {name: query_mesh(queries,name) for name in recorded}
    manifest = dict(units='metres, z up', source_hash=K.source_hash(), parameters=p,
                    derived={key: round(value,4) for key,value in d.items()}, budgets=K.BUDGET, pieces={})
    failures = []
    entry, bad, cab = K.build_cabin(p,d,prepared=cab_prepared,export=False)
    manifest['pieces']['cabin'] = entry; failures.extend('cabin: '+item for item in bad)
    entry, bad = K.build_towers(p,d,cab,prepared=towers,export=False)
    manifest['pieces']['towers'] = entry; failures.extend('towers: '+item for item in bad)
    for key in ('valley','rim','crater'):
        ctx = dict(audit=K.audit_meshes, movers=K.cabin_movers, groove=K.groove_check,
            rope_check=K.rope_check, jaw_contact=K.jaw_contact, static_rope=K.static_rope_check,
            budget=K.BUDGET, bounds=K.bounds, envelope=lambda mg: K.envelope(p,d,mg,top=True),
            failures=K.failures_of, out=output, export=lambda piece,meshes,proxies: len(proxies))
        entry, bad = stations.build(key,p,d,cab,ctx,prepared=station_data[key])
        manifest['pieces']['station_'+key] = entry
        failures.extend('station '+key+': '+item for item in bad)
        print('GONDOLA ORIGINAL AUDIT', key, len(bad), 'failures', flush=True)
    summary = K.rope_summary(manifest['pieces'])
    if any(not row['ok'] for row in summary): failures.append('Original rope audit failed')
    manifest.update(rope_clearance=summary, materials=solid.MATERIALS,
                    textured_materials=solid.TEXTURED, failures=failures, soft_fail=False)
    if failures: raise ValueError('Gondola original complete audit failed: '+repr(failures))
    import walk
    walk.OUT = output; walk.REVIEW = output / 'review'
    report, bad = walk.audit(quiet=True)
    if bad: raise ValueError('Original Gondola walking gates failed: '+repr(bad))
    manifest['walk'] = dict(all_pass=report['all_pass'], report='review/walk_report.json', rules=report['rules'])
    atomic_json(output / 'kit-audit.json', manifest)
    print('GONDOLA ORIGINAL KIT AUDIT COMPLETE', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('audit',))
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    audit(args.input,args.output)


if __name__ == '__main__': main()
