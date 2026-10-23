"""Source-bound station/cabin data consumed by the native ropeway service."""
import hashlib
import json
import math
import sys
from pathlib import Path

WORLD=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(WORLD))
from gondola import clock
from gondola.validation import validate_site, site_inputs, PARAMETERS, KIT
import yori

HERE=Path(__file__).resolve().parent
CODE=(HERE/'service.py',HERE/'clock.py',HERE/'validation.py',KIT/'rope.py',KIT/'params.py')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def ue(point):return [round(x*f,5) for x,f in zip(point,(100.,-100.,100.))]


def asset(name,world=False):
    return f'/Game/Gondola/{"World" if world else "Kit"}/{name}.{name}'


def transform(row):
    return {'location_cm':ue([*row['origin'],row['platform_z']]),'yaw':-row['heading']}


def records(build):
    return {'code':{str(path.relative_to(yori.GAME.parents[1])):sha(path) for path in CODE},
            'site_sha256':sha(build/'gondola/world/site.json'),'site_inputs':site_inputs(build)}


def build_data(site,build):
    if site.get('atomic') is not True:raise ValueError('Gondola runtime requires complete bounded site membership')
    p=PARAMETERS.DEFAULTS;d=PARAMETERS.derived(p)
    kit=json.loads((build/'gondola/manifest.json').read_text())
    cabin=kit['pieces']['cabin']
    stations=[];static=[]
    for key,row in site['stations'].items():
        placement=transform(row)
        names=[f'GD_Station{row["kind"].title()}_{part}' for part in ('Platform','Machinery','Fittings','Building','Collision')]
        for name in names:
            static.append({'name':key+'_'+name,'mesh':asset(name),'collision':name.endswith('_Collision'),**placement})
        for part in ('foundation','access_mesh'):
            for piece in row[part]['pieces']:
                name=piece['name']
                static.append({'name':name,'mesh':asset(name,True),'collision':True,**placement})
        angle=math.radians(row['heading']);along=[math.cos(angle),math.sin(angle)];lateral=[-along[1],along[0]]
        origin=row['origin'];z=row['platform_z'];rope_z=z+d['rope_height_above_platform']
        walk=row['access']['route']
        world_walk=[[origin[0]+q[0]*along[0]+q[1]*lateral[0],origin[1]+q[0]*along[1]+q[1]*lateral[1],z+q[2]] for q in walk]
        boarding={}
        for side,points in row['boarding_routes'].items():
            route=list(reversed(world_walk))
            route += [[origin[0]+q[0]*along[0]+q[1]*lateral[0],origin[1]+q[0]*along[1]+q[1]*lateral[1],z+q[2]] for q in points]
            boarding[side]=[ue(q) for q in route]
        stations.append({'boarding_cm':boarding,'id':key,'name':row['name'],**placement,'walk_cm':[ue(q) for q in world_walk],
                         'origin':origin,'along':along,'lateral':lateral,'rope_z':rope_z,
                         'mouth_grip':[row['mouth'][0],row['mouth'][1],rope_z],
                         'berth_x':p['berth_x'],'gauge':p['gauge'],'mouth_x':7.6})
    by_name={row['id']:row for row in stations};lines=[]
    for line in site['lines']:
        print('GONDOLA SERVICE clock',line['id'],flush=True)
        towers=[]
        for tower in line['towers']:
            location=tower['origin'];angle=math.radians(tower['heading']);lateral=[-math.sin(angle),math.cos(angle)]
            tracks={str(side):[location[0]+side*p['gauge']/2*lateral[0],location[1]+side*p['gauge']/2*lateral[1],location[2]+tower['height']] for side in (-1,1)}
            towers.append({'tracks':tracks})
            for piece in tower['mesh']['pieces']:
                static.append({'name':piece['name'],'mesh':asset(piece['name'],True),
                               'location_cm':ue(location),'yaw':-tower['heading'],'collision':True})
        table=clock.prepare(line['circuit'],[by_name[key] for key in line['stations']],towers)
        # The geometry remains exact; only world coordinate units change here.
        count=4 if line['id']=='L3' else 12
        separation=clock.spacing(table,count,math.dist(*cabin['bounds'])+2*math.sqrt(math.fsum(v*v for v in cabin['grip']['pivot']['point'])))
        table['points']=[ue(q) for q in table['points']]
        lines.append({'id':line['id'],'stations':line['stations'],'clock':table,
                      'cabins':count,'spacing':separation,
                      'ropes':[asset(name,True) for name in site['rope_groups'][line['id']]],
                      'rope_lod_minimum_m':[row['minimum_view_distance_m'] for row in line['rope_meshes']]})
    clear=[]
    for line in site['lines']:
        a,b=(site['stations'][key]['mouth'] for key in line['stations'])
        clear.append([*a,*b,8.])
    for station in stations:
        for a,b in zip(station['walk_cm'],station['walk_cm'][1:]):
            clear.append([a[0]/100.,-a[1]/100.,b[0]/100.,-b[1]/100.,3.])
        origin=station['origin'];along=station['along']
        clear.append([origin[0]-14*along[0],origin[1]-14*along[1],origin[0]+18*along[0],origin[1]+18*along[1],14.])
    return {'clear_prefixes':['HD_NorthTree','HD_ArcadeTree','HD_PlazaTree'],
            'clearance_segments_m':clear,'sources':records(build),'stations':stations,'static':static,'lines':lines,
            'cabin':{'parts':[asset(name) for name in PARAMETERS.asset_names()[:6] if not name.endswith('_Collision')],
                     'body':asset('GD_Cabin_Collision'),'grip_pivot_cm':ue(cabin['grip']['pivot']['point']),
                     'floor_z_cm':cabin['floor_top_z']*100.,'size_cm':[p['cabin_length']*100,p['cabin_width']*100],
                     'door_centre_cm':ue(cabin['door_frame']['centre']),
                     'door_width_cm':p['door_clear_width']*100,'door_height_cm':p['door_clear_height']*100,
                     'door_offsets_cm':{key:ue(value) for key,value in cabin['door_frame']['leaves']['open_offsets'].items()},
                     'cull_cm':40000.}}


def validate_service(data,build):
    """@cc [owner:fontanierh,label:correctness] fitted-ropeway-runtime-source
    Runtime generation and import MUST refuse stale/incomplete site, kit and
    final world proof before asset mutation. Cabin clocks MUST refine the same
    audited circuit without moving it, stop at the kit's platform berths, keep
    physical doors shut outside dwell, and prove cabin headway clearance.
    """
    site=validate_site(build)
    if data!=build_data(site,build):raise ValueError('Gondola runtime differs from its current audited fitted circuit')
    return data


def main():
    site=validate_site(yori.OUT)
    data=build_data(site,yori.OUT)
    folder=yori.OUT/'gondola';folder.mkdir(parents=True,exist_ok=True)
    (folder/'runtime.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
    print('GONDOLA SERVICE COMPLETE',len(data['lines']),'lines',sum(line['cabins'] for line in data['lines']),'cabins',flush=True)


if __name__=='__main__':main()
