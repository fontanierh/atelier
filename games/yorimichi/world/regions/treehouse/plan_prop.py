"""Fit only one committed prop model and plan its independently exported bounded mesh."""
import argparse
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402
from region_mesh_parts import plan,capture_collision  # noqa: E402
from treehouse.atomic_parameters import load  # noqa: E402
from treehouse.prop_geometry import fit  # noqa: E402

OPTIONS=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
             mesh_smooth_type='FACE',use_custom_props=False,path_mode='STRIP',colors_type='SRGB')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parameters',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    value=load(args.parameters);name=value['name']
    if not name.startswith('TH_P_'):raise ValueError('Selected source is not a prop')
    real_directory(args.source.parent)
    if args.source.is_symlink() or not args.source.is_file():raise ValueError('Prop source must be a regular committed model')
    root=real_directory(args.data)
    if root.exists() and regular_files(root)-{name+'.png','record.json'}:raise ValueError('Foreign selected prop data')
    captured={}
    def publish(obj,hulls):
        collisions=[capture_collision(hull) for hull in hulls]
        result=plan(obj,args.output,collisions=collisions,partition='whole', options=OPTIONS)
        if len(result['pieces'])!=1 or result['pieces'][0]['name']!=name:
            raise ValueError('Prop requires coordinated instancing membership when oversized')
        captured.update(hulls=collisions)
    key,info=fit(value['slug'],args.source,name,value['size'],value['turn'],value['target'],value['solid'],root,
                 publisher=publish,diagnostic_views=False)
    atomic_json(root/'record.json',dict(name=key,info=info,**captured))
    print('TREEHOUSE PROP SOURCE COMPLETE',name,info['triangles'],flush=True)


if __name__=='__main__':main()
