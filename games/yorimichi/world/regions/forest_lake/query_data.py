"""Canonical final-height trail/shore samples and shared seeded draws before lake mesh exports."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory
from atelier.model_files import regular_files  # noqa: E402
from village.layout import upper_surface  # noqa: E402
from forest_lake.scatter import shoreline  # noqa: E402


def publish(heightmap,world,output):
    """@cc [owner:fontanierh,label:correctness;performance] lake-canonical-query-before-export
    Final terrain samples and the original shared seeded draw sequence MUST be
    explicit pre-export data. Logical constructors MUST consume only their own
    source packets; no rendered export or hidden sibling construction may supply
    placement, shore, water or trail geometry. Unrelated world metadata MUST NOT
    enter the independently consumed geometric packets.
    """
    output=real_directory(output)
    expected={'Lake_Trail.json','Lake_Shore.json','Lake_Plants.json','queries.json'}
    if output.exists() and regular_files(output)-expected:raise ValueError('Foreign lake query members')
    output.mkdir(parents=True,exist_ok=True)
    h=np.load(heightmap,allow_pickle=False)
    if h.ndim!=2 or not np.isfinite(h).all():raise ValueError('Invalid final lake height query')
    document=json.loads(Path(world).read_text())
    path=np.array(document['forest_lake']['trail'])
    v=np.gradient(path[:,:2],axis=0);v/=np.linalg.norm(v,axis=1)[:,None]
    normal=np.column_stack([-v[:,1],v[:,0]])
    events=[]
    for i in range(len(path)-1):
        points=[]
        for k,side in [(i,-1),(i+1,-1),(i+1,1),(i,1)]:
            p=path[k,:2]+normal[k]*side*1.25
            points.append((*p,float(upper_surface(h,*p))+.045))
        events.append(['poly',[points,(.24,.15,.075)]])
    programs={'Lake_Trail':events,**shoreline(h)}
    for name,events in programs.items():
        atomic_json(output/(name+'.json'),dict(schema=1,name=name,events=events))
    source={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (heightmap,world)}
    atomic_json(output/'queries.json',dict(schema=1,complete=True,sources=source,assets=sorted(programs)))
    return programs


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--heightmap',type=Path,required=True)
    parser.add_argument('--world',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    result=publish(args.heightmap,args.world,args.output)
    print('LAKE QUERY DATA COMPLETE',{k:len(v) for k,v in result.items()},flush=True)


if __name__=='__main__':main()
