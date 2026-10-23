"""Only consumed island arrays and the approach-road anchor enter northern terrain."""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory,sha  # noqa: E402


def regular(path):
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():raise ValueError('Northern context input must be regular')


def project(world,heightmap,farhills):
    for path in (world,heightmap,farhills):regular(path)
    road=json.loads(world.read_text())['road']
    if (not isinstance(road,list) or not road or any(not isinstance(row,list) or len(row)<2
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in row[:2]) for row in road)):
        raise ValueError('Missing current island approach-road anchor')
    return dict(schema=1,heightmap_sha256=sha(heightmap),farhills_sha256=sha(farhills),
                street_start=[float(v) for v in max(road,key=lambda row:row[0])[:2]])


def apply(path,heightmap,farhills):
    """@cc [owner:fontanierh,label:correctness;performance] consumed-northern-world-context
    Northern construction MUST consume the exact heightmap/backdrop arrays and
    original road-end anchor. Unread world placements and unrelated metadata
    MUST stop at this projection. Before construction, bind the existing lazy
    terrain caches to the verified arrays and anchor, never an ambient world
    JSON or another checkout's file.
    """
    for item in (path,heightmap,farhills):regular(item)
    value=json.loads(path.read_text())
    if (set(value)!={'schema','heightmap_sha256','farhills_sha256','street_start'}
            or type(value['schema']) is not int or value['schema']!=1
            or not isinstance(value['street_start'],list) or len(value['street_start'])!=2
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in value['street_start'])
            or sha(heightmap)!=value['heightmap_sha256'] or sha(farhills)!=value['farhills_sha256']):
        raise ValueError('Stale or foreign northern terrain context')
    from hidamari import layout
    if (heightmap.absolute()!=layout.yori.OUT/'heightmap.npy' or farhills.absolute()!=layout.yori.OUT/'farhills.npy'):
        raise ValueError('Northern terrain arrays belong to another receiving output root')
    grid=np.load(heightmap,allow_pickle=False)
    backdrop=np.load(farhills,allow_pickle=False)
    if any(value.ndim!=2 or min(value.shape)<2 or not np.isfinite(value).all() for value in (grid,backdrop)):
        raise ValueError('Invalid current island terrain arrays')
    layout.H=grid;layout.BACKDROP=None;layout.street_height.start=list(value['street_start'])
    return value


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('world','heightmap','farhills','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args(argv);real_directory(args.output.parent)
    value=project(args.world,args.heightmap,args.farhills)
    if args.output.is_symlink() or args.output.exists() and not args.output.is_file():raise ValueError('Invalid context output')
    if not args.output.exists() or json.loads(args.output.read_text())!=value:atomic_json(args.output,value)
    print('BELMONTE NORTHERN CONTEXT COMPLETE',flush=True)


if __name__=='__main__':main()
