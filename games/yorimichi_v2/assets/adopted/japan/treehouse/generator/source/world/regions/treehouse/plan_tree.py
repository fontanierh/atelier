"""Construct one authored canopy tree and publish its dimensions before any mesh export."""
import argparse
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import asset_mesh as A  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from region_mesh_parts import plan  # noqa: E402
from treehouse.atomic_parameters import load  # noqa: E402
from treehouse.canopy import canopy_tree  # noqa: E402

OPTIONS=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
             mesh_smooth_type='FACE',path_mode='STRIP',embed_textures=False,use_tspace=False,colors_type='SRGB')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parameters',type=Path,required=True)
    parser.add_argument('--record',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    value=load(args.parameters);name=value['name']
    if not name.startswith('Tree_Canopy_'):raise ValueError('Selected source is not a canopy')
    bpy.ops.wm.read_factory_settings(use_empty=True);A.MATS.clear();A.LEAF_CROPS.clear()
    A.materials(['Bark','LeafMaple'])
    obj,info=canopy_tree(name,*value['args'])
    result=plan(obj,args.output,partition='whole', options=OPTIONS)
    if len(result['pieces'])!=1 or result['pieces'][0]['name']!=name:
        raise ValueError('Canopy requires a coordinated HISM membership change when oversized')
    atomic_json(args.record,dict(name=name,dimensions=info))
    print('TREEHOUSE CANOPY SOURCE COMPLETE',name,info['triangles'],flush=True)


if __name__=='__main__':main()
