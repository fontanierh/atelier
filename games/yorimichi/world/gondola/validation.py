"""Fail-closed fitted ropeway input validation before service/import mutation."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

GAME=Path(__file__).resolve().parents[2]
REPO=GAME.parents[1]
KIT=GAME/'assets/vehicles/gondola'
RASTER=GAME/'world/walk_raster.py'
_spec=importlib.util.spec_from_file_location('gondola_canonical_parameters',KIT/'params.py')
PARAMETERS=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(PARAMETERS)
SITE_CODE=tuple(GAME/name for name in (
    'world/regions/gondola/site.py','world/regions/gondola/layout.py',
    'world/regions/hidamari/gondola.py','world/regions/belmonte/gondola.py',
    'world/walk_raster.py','world/gondola/line.py','world/gondola/support.py','world/gondola/products.py',
    'world/gondola/terrain.py','world/gondola/clearance.py','world/gondola/structures.py','world/gondola/validation.py',
    'unreal/Scripts/mesh_import.py','unreal/Scripts/import_gondola.py',
    'world/terrain_product.py','world/terrain_query.py','world/regions/belmonte/layout.py',
    'world/gondola/interactions.py','world/regions/zeppelin/layout.py','world/regions/village/layout.py',
    'world/regions/zeppelin/build.py','unreal/Source/Yorimichi/ZeppelinService.cpp',
    'unreal/Source/Yorimichi/ZeppelinNetwork.cpp',
    'world/regions/craterpark/placement.py','world/regions/craterpark/v2/v4_placement.py',
    'world/regions/craterpark/v2/v4_config.py',
))
SITE_CODE += tuple(GAME/name for name in (
    'export_digest.py','world/gondola/__init__.py',
    'world/regions/belmonte/__init__.py','world/regions/craterpark/__init__.py',
    'world/regions/craterpark/v2/__init__.py','world/regions/craterpark/v2/curves.py',
    'world/regions/craterpark/v2/dsl.py','world/regions/craterpark/v2/profile.py',
    'world/regions/gondola/__init__.py','world/regions/hidamari/__init__.py',
    'world/regions/zeppelin/__init__.py','world/regions/village/__init__.py',
    'world/regions/megapark/__init__.py','world/regions/megapark/placement.py',
))
SITE_CODE += tuple(REPO/name for name in ('platform/studio/atelier/__init__.py','platform/studio/atelier/paths.py',
                                        'platform/studio/atelier/gltf.py'))


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
    expected={'checker_sha256':sha(KIT/'walk.py'),'raster_sha256':sha(RASTER),
              'layouts':{name:sha(folder/f'layout_{name}.json') for name in ('cabin','valley','rim','crater')}}
    if (report.get('all_pass') is not True or report.get('failures')!=[] or report.get('inputs')!=expected or
            set(report.get('pieces',{}))!={'cabin','valley','rim','crater'}):
        raise ValueError('Gondola kit walking audit is stale, incomplete or failed')
    return {name:sha(folder/name) for name in PARAMETERS.product_files()}


def site_inputs(build):
    return {'code':{str(path.relative_to(REPO)):sha(path) for path in SITE_CODE},
            'kit':kit_snapshot(build),
            'world':{name:sha(build/name) for name in (
                'gondola/world/ground.npz','gondola/world/ground.json',
                'gondola/world/structures.npz','gondola/world/structures.json','craterpark/v2/geometry.npz',
                'zeppelin/manifest.json')}}


def validate_access_ground(access):
    proof=access.get('ground_proof',{})
    value=proof.get('maximum_intrusion_m')
    if (proof.get('pass') is not True or proof.get('complete_coverage') is not True or
            not access.get('surfaces') or proof.get('surfaces')!=len(access['surfaces']) or
            proof.get('allowance_m')!=.03 or not isinstance(value,(int,float)) or
            not math.isfinite(value) or value>.03):
        raise ValueError('Gondola complete access-floor proof is missing or failed')



def validate_stored_contact(row,poses,hardware_min):
    proof=row.get('stored_contact',{})
    if (proof.get('pass') is not True or proof.get('representation')!='fbx-float32-cm-ring-axis' or
            proof.get('control_point_frame')!='mesh-local' or proof.get('world_transform_applied') is not True or
            proof.get('directions')!=[-1,1] or proof.get('poses')!=poses or poses<=0 or
            proof.get('points_per_pose')!=114 or type(proof.get('matched_vertices')) is not int or proof['matched_vertices']<48 or
            not all(type(proof.get(key)) in (int,float) and math.isfinite(proof[key])
                    for key in ('max_error_mm','bound_mm','control_point_error_m','control_point_allowance_m',
                                'axis_extra_m','axis_bound_m','hardware_bound_m','world_displacement_m')) or
            proof['max_error_mm']<0 or proof['bound_mm']>2. or
            abs(proof['bound_mm']-proof['max_error_mm']-.005)>1e-9 or
            not 0<=proof['control_point_error_m']<=proof['control_point_allowance_m']<=.001 or
            proof['world_displacement_m']<0 or proof['axis_extra_m']<0 or proof['hardware_bound_m']<.095 or
            abs(proof['axis_bound_m']-row.get('axis_deviation_m',-1)-proof['axis_extra_m'])>1e-12 or
            abs(proof['hardware_bound_m']-hardware_min+proof['axis_bound_m'])>1e-12):
        raise ValueError('Incomplete or failed stored rope contact proof')


def validate_structure_envelope(envelope, kit):
    expected={name for name in PARAMETERS.asset_names()[:6] if not name.endswith('_Collision')}
    parts=envelope.get('parts',{})
    pivot=kit['pieces']['cabin']['grip']['pivot']['point']
    shift=2*math.sqrt(math.fsum(v*v for v in pivot))
    offsets=kit['pieces']['cabin']['door_frame']['leaves']['open_offsets']
    if (set(parts)!=expected or envelope.get('margin_m')!=.3 or
            type(envelope.get('pivot_shift_m')) not in (int,float) or
            not math.isfinite(envelope['pivot_shift_m']) or
            abs(envelope['pivot_shift_m']-shift)>1e-12):
        raise ValueError('Incomplete actual-kit moving structure envelope')
    for name,row in parts.items():
        offset=offsets.get(name,[0.,0.,0.])
        if (row.get('mode')!=('grip' if name=='GD_CabinGrip' else 'plumb') or
                not all(type(row.get(k)) in (int,float) and math.isfinite(row[k]) and row[k]>=0
                        for k in ('radius_m','drop_m','door_motion_m','door_vertical_m')) or
                abs(row['door_motion_m']-math.hypot(*offset[:2]))>1e-12 or
                row['door_vertical_m']!=abs(offset[2])):
            raise ValueError('Invalid actual-kit part motion envelope')
    if (envelope.get('radius_m')!=max(p['radius_m'] for p in parts.values())+.3 or
            envelope.get('drop_m')!=max(p['drop_m'] for p in parts.values())):
        raise ValueError('Actual-kit structure envelope total does not match its parts')
    return envelope


def validate_structure_proof(proof, *, static=False, envelope=None):
    if proof.get('pass') is not True or proof.get('margin_m')!=.05:
        raise ValueError('Missing final structure clearance proof')
    if static:
        if (proof.get('representation')!='complete-expanded-static-box' or
                set(proof.get('candidates',{}))!={'visual','collision'} or
                any(type(v) is not int or v<0 for v in proof['candidates'].values()) or
                len(proof.get('bounds_m',[]))!=2 or any(len(v)!=3 for v in proof['bounds_m']) or
                not all(math.isfinite(v) for row in proof['bounds_m'] for v in row)):
            raise ValueError('Incomplete static structure refusal proof')
    else:
        if (not envelope or proof.get('representation')!='complete-segment-envelope' or
                type(proof.get('segments')) is not int or proof['segments']<=0 or
                proof.get('radius_m')!=envelope['radius_m'] or proof.get('drop_m')!=envelope['drop_m'] or
                set(proof.get('results',{}))!={'visual','collision'}):
            raise ValueError('Incomplete moving structure clearance proof')
        for row in proof['results'].values():
            count=row.get('triangles_tested');value=row.get('minimum_m')
            if (type(count) is not int or count<0 or (count==0 and value is not None) or
                    (count>0 and (type(value) not in (int,float) or not math.isfinite(value) or value<.05))):
                raise ValueError('Failed moving structure clearance proof')

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
    envelope=validate_structure_envelope(data.get('structure_envelope',{}),
                                        json.loads((build/'gondola/manifest.json').read_text()))
    for line in data['lines']:
        if line['id']=='L2':
            validate_structure_proof(line.get('structures',{}),envelope=envelope)
            if (line['structures'].get('required_clearance_m')!=6. or
                    any(row['minimum_m'] is not None and row['minimum_m']<6.
                        for row in line['structures']['results'].values())):
                raise ValueError('Ropeway does not clear final town structures by6m')
        if len(line['towers'])!=tower_counts[line['id']]:
            raise ValueError('Gondola fitted tower roster is incomplete')
        ropes=line['rope_meshes']
        if len(ropes)!=3 or ropes[0]['groove_bound_mm']>2. or not math.isfinite(ropes[0]['groove_bound_mm']):
            raise ValueError('Near rope mesh exceeds the unchanged contact budget')
        if [row['minimum_view_distance_m'] for row in ropes]!=[0.,1000.,2000.]:
            raise ValueError('Far rope detail has no explicit distance/contact policy')
        audit=line['span_audit']
        validate_stored_contact(ropes[0],audit.get('poses',0),audit.get('hardware_min_m',0))
        if (audit.get('pass') is not True or audit['poses']<=0 or
                not all(math.isfinite(audit[key]) for key in ('groove_max_mm','hardware_min_m')) or
                audit['groove_max_mm']>2. or audit['hardware_min_m']<.095):
            raise ValueError('Gondola fitted-span contact proof is incomplete or failed')
        if line['ground'].get('complete_coverage') is not True or line['ground'].get('triangles_tested',0)<=0 or line['ground'].get('pass') is not True or not math.isfinite(line['ground']['minimum_sampled_m']) or line['ground']['minimum_sampled_m']<6.:
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
        if station['id']=='belmonte':
            link=station.get('walking_link',{})
            if (link.get('pass') is not True or link.get('complete_coverage') is not True or
                    link.get('width_m')!=.7 or link.get('height_m')!=1.7 or
                    not isinstance(link.get('triangles'),int) or link['triangles']<=0 or
                    not 0<=link.get('maximum_slope',math.inf)<=math.tan(math.radians(40.)) or
                    type(link.get('stone_path_gap_m')) not in (int,float) or
                    not math.isfinite(link['stone_path_gap_m']) or link['stone_path_gap_m']<.35):
                raise ValueError('Missing complete stone-path connection proof')
        if station['id'] in ('belmonte','northwest'):
            prefix='GD_Station'+station['kind'].title()+'_'
            expected={prefix+part for part in ('Platform','Machinery','Fittings','Building')}
            if set(station.get('structure_static',{}))!=expected:
                raise ValueError('Incomplete station/world structure proof')
            for proof in station['structure_static'].values():
                validate_structure_proof(proof,static=True)
            validate_structure_proof(station.get('structure_collision',{}),static=True)
            validate_structure_proof(station.get('structure_loop',{}),envelope=envelope)
        validate_access_ground(station['access'])
        if station.get('static_riding_clear') is not True:
            raise ValueError('Gondola station overlaps riding structure or has no static proof')
        jump=station['jump']
        if jump.get('pass') is not True or jump['poses']<=0 or (jump['minimum_m'] is not None and (not math.isfinite(jump['minimum_m']) or jump['minimum_m']<15.)):
            raise ValueError('Gondola station-loop jump proof is missing or failed')
    for row in data['exports']:
        if row['name'].startswith(('GD_belmonte_','GD_northwest_','GD_L2_')) and '_Rope_LOD' not in row['name']:
            validate_structure_proof(row.get('world_structure') or {},static=True)
            if row['name']=='GD_L2_0_Tower' and row['world_structure'].get('plan_clear') is not True:
                raise ValueError('Tower footing/guy footprint obstructs final town walking space')
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
    from gondola.structures import validate as validate_structures
    validate_structures(build)
    flight=data.get('zeppelin_flight',{})
    if (flight.get('pass') is not True or
            not all(type(flight.get(key)) in (int,float) and math.isfinite(flight[key])
                    for key in ('climb_plan_gap_m','rotating_radius_m','ropeway_ceiling_m')) or
            flight['climb_plan_gap_m']<.3 or flight['rotating_radius_m']<=0 or
            {tuple(row['stops']) for row in flight.get('legs',[])}!={(0,3),(1,3),(2,3)} or
            any(type(row.get('overlapping_boxes')) is not int or row['overlapping_boxes']<0 or
                (row['overlapping_boxes']==0 and row.get('minimum_vertical_m') is not None) or
                (row['overlapping_boxes']>0 and (type(row.get('minimum_vertical_m')) not in (int,float) or
                 not math.isfinite(row['minimum_vertical_m']) or row['minimum_vertical_m']<6.))
                for row in flight['legs'])):
        raise ValueError('Missing complete zeppelin flight clearance proof')
    return data
