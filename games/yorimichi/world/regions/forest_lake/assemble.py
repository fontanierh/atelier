"""Gather exact independently cached lake files and complete logical membership metadata."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier import export_assembly  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from region_mesh_parts import validate  # noqa: E402
OWNERS=('Lake_Cabin','Lake_Water','Lake_Trail','Lake_Shore','Lake_Plants')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    items=[];logical={};entries={}
    for parent in OWNERS:
        source=validate(args.out/'planned_exports/lake'/parent)
        record=json.loads((args.out/'lake-data/records'/(parent+'.json')).read_text())
        if record['name']!=parent or record['triangles']!=source['source_triangles']:
            raise ValueError('Lake source record differs from complete logical membership')
        logical[parent]=[row['name'] for row in source['pieces']]
        for row in source['pieces']:
            key=row['name'];items.append(export_assembly.Item(key,args.out/'exports/world.lake.export'/key))
            entries[key]=dict(parent=parent,triangles=row['triangles'],collision_boxes=row['collision_hulls'],
                              min=row['min'],max=row['max'],fbx='assets/'+key+'.fbx')
    destination=args.out/'forest_lake'
    manifest=export_assembly.assemble(items,destination/'assets')
    for row in manifest['exports']:
        entries[row['asset']]['sha256']=row['sha256']
    atomic_json(destination/'manifest.json',dict(schema=2,complete=True,parents=logical,assets=entries))
    print('LAKE ASSEMBLY COMPLETE',len(entries),flush=True)


if __name__=='__main__':main()
