"""Project one station/trail's exact original final-surface calls."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import argparse
import json
import numpy as np
import yori
from atelier.atomic_files import atomic_json
from zeppelin.query_data import key
from zeppelin.layout import STATIONS,MESHES,belmonte_path,city_path,PARK_BRIDGE,PARK_WALK


def project(asset,destination):
    from village.layout import upper_surface
    from hidamari.layout import height,north_height
    values={}
    def record(x,y,reader):
        value=float(reader(x,y));name=key(x,y)
        if name in values and values[name]!=value:raise ValueError('Inconsistent original final terrain owner')
        values[name]=value
        return value
    if asset=='ZP_Trail':
        from zeppelin.ground_query import city_ground
        h=np.load(yori.OUT/'heightmap.npy')
        world=json.loads((yori.OUT/'world.json').read_text());path=np.array(world['zeppelin']['trail'])
        paths=[]
        for path,width,reader,lift,skirts in [(path,1.25,lambda x,y:upper_surface(h,x,y),.04,False),
                                              (city_path(),.8,city_ground,.04,True)]:
            d=np.gradient(path[:,:2],axis=0);d/=np.linalg.norm(d,axis=1)[:,None];n=np.column_stack([-d[:,1],d[:,0]])
            polygons=[]
            for i in range(len(path)-1):
                p=[]
                for k,side in [(i,-1),(i+1,-1),(i+1,1),(i,1)]:
                    q=path[k,:2]+n[k]*width*side;p.append((float(q[0]),float(q[1]),record(*q,reader)+lift))
                polygons.append(p)
            paths.append(dict(polygons=polygons,skirts=skirts))
        atomic_json(destination,dict(schema=1,ground=values,paths=paths));return
    index=MESHES.index(asset);ox,oy,oz=STATIONS[index]['origin']
    if index==0:
        h=np.load(yori.OUT/'heightmap.npy');reader=lambda x,y:upper_surface(h,x,y)
    elif index==1:reader=height
    elif index==2:reader=north_height
    else:
        from belmonte import layout as layout,source
        surf=source.terrain();reader=lambda x,y:surf.height(x-layout.ORIGIN[0],y-layout.ORIGIN[1])+layout.ORIGIN[2]
    points=[]
    points.extend((float(x),float(y)) for x in np.arange(-10,11,1.) for y in np.arange(-8.8,-5.1,1.))
    points.extend((6,-7.9+k*.49) for k in range(10))
    points.extend((x,-7.9+k*.49) for x in (4.55,7.45) for k in (0,4,9))
    points.extend((x,y) for x in (2.25,6,9.75) for y in (-2.8,.8))
    points.extend((x,y) for x,y in [(-10,-3.2),(-1.7,-5.4),(10,-6.5)])
    for x,y in points:record(x+ox,y+oy,reader)
    if index==2:
        (_,y),_=PARK_WALK;(b0,_),_=PARK_BRIDGE
        for side in (-1,1):
            for x in (b0+2.6,b0+7.1,b0+11.6):record(x,y+side*.98,north_height)
    if index==3:
        path=belmonte_path();d=np.gradient(path,axis=0);d/=np.linalg.norm(d,axis=1)[:,None];n=np.column_stack([-d[:,1],d[:,0]])
        for i in range(len(path)-1):
            for k,side in [(i,-1),(i+1,-1),(i+1,1),(i,1)]:record(*(path[k]+n[k]*1.3*side),reader)
    value=dict(schema=1,asset=asset,ground=values)
    if index==1:
        from hidamari import station_yard
        value['rail_clearance_min_y']=station_yard.Y1+2.
    atomic_json(destination,value)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--asset',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();project(args.asset,args.output)
