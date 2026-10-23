"""One-owner terrain stages with explicit neighbour boundary inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from belmonte import mesh_data,seam_data,query_arrays,source,surface_data  # noqa: E402
from belmonte import layout as L  # noqa: E402

OWNERS=('SM_BM_NorthApron','SM_BM_NorthCountry')


def joins():
    from belmonte import terrain
    return [(0,terrain.OUTER[0]),(0,terrain.OUTER[2]),(1,terrain.OUTER[3])]


def raw(owner,factory,argv=None,*,valley=False):
    parser=argparse.ArgumentParser(description='Construct only '+owner)
    parser.add_argument('--output',type=Path,required=True)
    for key in ('context','heightmap','farhills'):parser.add_argument('--'+key,type=Path,required=True)
    if valley:
        parser.add_argument('--valley',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(argv)
    from belmonte.north_context import apply
    apply(args.context,args.heightmap,args.farhills)
    if valley:
        value=query_arrays.read(args.valley,owner='BelmonteValley',stage='natural')
        surface=source.Surface(value['faces'])
        mesh,report=factory(surface=surface)
        real_directory(args.report.parent)
        if args.report.is_symlink() or args.report.exists() and not args.report.is_file():raise ValueError('Invalid apron seam report')
    else:mesh=factory()
    mesh_data.write(args.output,mesh,owner=owner)
    if valley and (not args.report.exists() or json.loads(args.report.read_text())!=report):atomic_json(args.report,report)
    print('BELMONTE RAW TERRAIN COMPLETE',owner,len(mesh.i)//3,flush=True)


def boundary(args):
    if len(args.input)!=2 or args.owner is not None:raise ValueError('Boundary requires both independent construction sources')
    meshes={owner:mesh_data.read(path,owner=owner) for owner,path in zip(OWNERS,args.input)}
    values=seam_data.capture(meshes,L.ORIGIN,joins())
    real_directory(args.output)
    # Complete target/path validation precedes either boundary output write.
    for owner in OWNERS:
        path=args.output/(owner+'.json')
        if path.is_symlink() or path.exists() and not path.is_file():raise ValueError('Invalid boundary projection target')
    for owner in OWNERS:seam_data.write(args.output/(owner+'.json'),values[owner],owner=owner)
    print('BELMONTE CONSUMED BOUNDARIES COMPLETE',sum(len(v['seams']) for v in values.values()),flush=True)


def one(args):
    if args.owner not in OWNERS or len(args.input)!=1:raise ValueError('Terrain stage requires one explicit owner')
    for path in (args.output,*([args.query] if args.query is not None else [])):
        real_directory(path.parent)
        if path.is_symlink() or path.exists() and not path.is_file():raise ValueError('Terrain stage outputs must be regular')
    owner=args.owner;mesh=mesh_data.read(args.input[0],owner=owner)
    if args.mode in ('natural','final'):
        if args.seam is None:raise ValueError('Terrain finishing requires its consumed seam projection')
        mesh=seam_data.apply(mesh,seam_data.read(args.seam,owner=owner),owner=owner)
    if args.mode=='carve':
        if args.seam or args.palette or args.query:raise ValueError('Carving may not consume a rendered or sibling mesh')
        from hidamari import mountains
        from train import earthworks
        earthworks.quads(mesh,L.ORIGIN,2.5 if owner==OWNERS[0] else 4.,
            hidden=lambda x,y:(x>mountains.BOUNDS[0])&(x<mountains.BOUNDS[2])&(y>mountains.BOUNDS[1])&(y<L.SOUTH_JOIN),
            weight=lambda x,y:earthworks.seam_weight(x,y,L.BOUNDS))
        mesh_data.write(args.output,mesh,owner=owner)
        print('BELMONTE CARVED TERRAIN COMPLETE',owner,len(mesh.i)//3,flush=True);return
    from hippodrome.build import encoded_glb
    data,info=encoded_glb(owner,mesh.p,mesh.n,mesh.t,mesh.i,'BM_000_Ground')
    if args.mode=='final':
        if args.palette is None or args.query:raise ValueError('Final terrain requires the explicit natural colour surface')
        from belmonte.appearance import paint_join_data
        value=query_arrays.read(args.palette,owner='BelmonteValleyColours',stage='natural')
        data=paint_join_data(data,owner,mesh,palette=source.Surface(value['faces'],value['values']))
    elif args.mode=='natural':
        if args.query is None or args.palette:raise ValueError('Natural terrain requires its explicit query-source output')
        mesh_data.write(args.output,mesh,owner=owner)
    entry=dict(name=owner,path='glb/'+owner+'.glb',sha256=hashlib.sha256(data).hexdigest(),
               triangles=info['triangles'],bounds_m=[info['min'],info['max']],slots=['Ground'])
    surface_data.write(args.query if args.mode=='natural' else args.output,entry,data,stage=args.mode)
    print('BELMONTE TERRAIN SOURCE COMPLETE',args.mode,owner,entry['triangles'],flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',required=True,choices=('boundary','natural','carve','final'))
    parser.add_argument('--owner',choices=OWNERS)
    parser.add_argument('--input',type=Path,action='append',required=True)
    parser.add_argument('--seam',type=Path);parser.add_argument('--palette',type=Path);parser.add_argument('--query',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.mode=='boundary':boundary(args)
    else:one(args)


if __name__=='__main__':main()
