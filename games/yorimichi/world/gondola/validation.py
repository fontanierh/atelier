"""Fail-closed fitted ropeway input validation before service/import mutation."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

GAME=Path(__file__).resolve().parents[2]
REPO=GAME.parents[1]
KIT=GAME/'assets/vehicles/gondola'
_spec=importlib.util.spec_from_file_location('gondola_canonical_parameters',KIT/'params.py')
PARAMETERS=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(PARAMETERS)
SITE_CODE=tuple(GAME/name for name in (
    'world/regions/gondola/site.py','world/regions/gondola/layout.py',
    'world/regions/hidamari/gondola.py','world/regions/belmonte/gondola.py',
    'world/gondola/line.py','world/gondola/support.py','world/gondola/products.py',
    'world/gondola/terrain.py','world/gondola/clearance.py','world/gondola/validation.py',
    'world/terrain_product.py','world/terrain_query.py','world/regions/belmonte/layout.py',
    'world/regions/craterpark/placement.py','world/regions/craterpark/v2/v4_placement.py',
    'world/regions/craterpark/v2/v4_config.py',
))
SITE_CODE += tuple(GAME/name for name in (
    'export_digest.py','world/gondola/__init__.py',
    'world/regions/belmonte/__init__.py','world/regions/craterpark/__init__.py',
    'world/regions/craterpark/v2/__init__.py','world/regions/craterpark/v2/curves.py',
    'world/regions/craterpark/v2/dsl.py','world/regions/craterpark/v2/profile.py',
    'world/regions/gondola/__init__.py','world/regions/hidamari/__init__.py',
    'world/regions/megapark/__init__.py','world/regions/megapark/placement.py',
))
SITE_CODE += tuple(REPO/name for name in ('platform/studio/atelier/__init__.py','platform/studio/atelier/paths.py'))


def network_layout():
    import sys
    old=list(sys.path)
    try:
        sys.path.insert(0,str(GAME/'world'))
        from regions.gondola import layout
        return layout
    finally:
        sys.path[:]=old


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def kit_snapshot(build):
    folder=build/'gondola'
    data=json.loads((folder/'manifest.json').read_text())
    if (data.get('failures')!=[] or data.get('soft_fail') is not False or
            data.get('source_hash')!=PARAMETERS.source_hash() or data.get('parameters')!=PARAMETERS.DEFAULTS or
            data.get('walk',{}).get('all_pass') is not True):
        raise ValueError('Gondola kit is missing, stale, noncanonical or failed')
    report=json.loads((folder/'review/walk_report.json').read_text())
    expected={'checker_sha256':sha(KIT/'walk.py'),
              'layouts':{name:sha(folder/f'layout_{name}.json') for name in ('cabin','valley','rim','crater')}}
    if (report.get('all_pass') is not True or report.get('failures')!=[] or report.get('inputs')!=expected or
            set(report.get('pieces',{}))!={'cabin','valley','rim','crater'}):
        raise ValueError('Gondola kit walking audit is stale, incomplete or failed')
    return {name:sha(folder/name) for name in PARAMETERS.product_files()}


def site_inputs(build):
    return {'code':{str(path.relative_to(REPO)):sha(path) for path in SITE_CODE},
            'kit':kit_snapshot(build),
            'world':{name:sha(build/name) for name in (
                'gondola/world/ground.npz','gondola/world/ground.json','craterpark/v2/geometry.npz')}}


def validate_site(build):
    folder=build/'gondola/world'
    data=json.loads((folder/'site.json').read_text())
    if data.get('failures')!=[] or data.get('inputs')!=site_inputs(build):
        raise ValueError('Gondola site is stale or failed')
    layout=network_layout()
    if (set(data['stations'])!=set(layout.STATIONS) or
            len(data['lines'])!=len(layout.LINES) or
            {row['id'] for row in data['lines']}!={row['id'] for row in layout.LINES} or
            {row['name'] for row in data['exports']}!=set(layout.mesh_names())):
        raise ValueError('Gondola site is missing network members or fitted meshes')
    tower_counts={line['id']:len(line['towers']) for line in layout.LINES}
    for line in data['lines']:
        if len(line['towers'])!=tower_counts[line['id']]:
            raise ValueError('Gondola fitted tower roster is incomplete')
        audit=line['span_audit']
        if (audit.get('pass') is not True or audit['poses']<=0 or
                not all(math.isfinite(audit[key]) for key in ('groove_max_mm','hardware_min_m')) or
                audit['groove_max_mm']>2. or audit['hardware_min_m']<.095):
            raise ValueError('Gondola fitted-span contact proof is incomplete or failed')
        if line['ground'].get('pass') is not True or not math.isfinite(line['ground']['minimum_sampled_m']) or line['ground']['minimum_sampled_m']<6.:
            raise ValueError('Gondola cabin-to-ground proof is missing or failed')
        if not math.isfinite(line['ground']['minimum_approach_m']) or line['ground']['minimum_approach_m']<.03:
            raise ValueError('Gondola approach terrain clearance failed')
        for tower in line['towers']:
            if len(tower['contact_audit'])!=2:
                raise ValueError('Gondola tower pass proof is incomplete')
            for proof in tower['contact_audit']:
                if (proof['poses']<=0 or proof['contacts']!=[] or proof['body_envelope']!=[] or
                        any(proof['rope'][key].get('ok') is not True for key in ('intentional','clearance'))):
                    raise ValueError('Gondola fitted tower pass failed')
        value=line['riding']['minimum_m']
        if (value is None and line['riding']['triangles_tested']!=0) or (value is not None and (not math.isfinite(value) or value<15.)):
            raise ValueError('Gondola riding/jump clearance failed')
    for station in data['stations'].values():
        if station.get('static_riding_clear') is not True:
            raise ValueError('Gondola station overlaps riding structure or has no static proof')
        jump=station['jump']
        if jump.get('pass') is not True or jump['poses']<=0 or (jump['minimum_m'] is not None and (not math.isfinite(jump['minimum_m']) or jump['minimum_m']<15.)):
            raise ValueError('Gondola station-loop jump proof is missing or failed')
    for row in data['exports']:
        proof=row['closed']
        if any(proof[key]!=0 for key in ('open_edges','misoriented_edges','degenerate_faces')) or row['triangles']<=0:
            raise ValueError('Gondola fitted mesh closure proof failed')
        if '_Rope_LOD' not in row['name']:
            carried=row['carried']
            if (row.get('riding_plan_clear') is not True or row['coplanar']['count']!=0 or
                    any(seat['status']!='ok' for seat in row['seating']) or carried['failures']!=[] or
                    carried['uncarried_groups']!=0 or carried['uncarried_islands']!=0 or carried['groups']<=0):
                raise ValueError('Gondola fitted support/access proof is missing or failed')
        if sha(folder/'assets'/f"{row['name']}.fbx")!=row['sha256']:
            raise ValueError('Gondola fitted mesh changed: '+row['name'])
    # Revalidate extraction identities too: a receipt bound only to old world
    # bytes cannot authorize an old interpretation of unchanged exports.
    from gondola.inputs import snapshot
    ground=json.loads((folder/'ground.json').read_text())
    if ground['inputs']!=snapshot(build) or ground['output_sha256']!=sha(folder/'ground.npz'):
        raise ValueError('Gondola final ground interpretation is stale')
    return data
