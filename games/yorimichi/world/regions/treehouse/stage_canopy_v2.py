"""Original authored canopy construction inside a declared v2 planner job."""
from pathlib import Path
import sys

_root = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(_root / 'platform/studio'), str(_root / 'games/yorimichi/world'),
                str(_root / 'games/yorimichi/world/regions')]

import bpy
import asset_mesh as assets
from treehouse.atomic_parameters import load
from treehouse.canopy import canopy_tree
from region_mesh_parts import plan
from atelier.build_v2.blender_ops import run_plan

# D2 owns a single relative-media FBX, without embedding or copied resources.
# Geometry construction is the original helper; these are explicit new-op settings.
OPTIONS = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y',
               axis_up='Z', mesh_smooth_type='FACE', path_mode='RELATIVE',
               use_tspace=False, colors_type='SRGB')


def run(context):
    """Build the selected original canopy; the D2 producer verifies its whole plan."""
    if set(context.inputs) != {'parameters', 'bark', 'leaf_maple'}:
        raise ValueError('Canopy requires its exact parameter and atlas inputs')
    value = load(context.input('parameters'))
    if value['name'] != context.params['parent'] or not value['name'].startswith('Tree_Canopy_'):
        raise ValueError('Canopy parameters differ from the declared parent')
    textures = context.input('leaf_maple').parent
    if context.input('bark').parent != textures:
        raise ValueError('The declared canopy atlas files must share their staged directory')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assets.MATS.clear()
    assets.LEAF_CROPS.clear()
    assets.TEX = str(textures)
    assets.materials(['Bark', 'LeafMaple'])
    obj, _dimensions = canopy_tree(value['name'], *value['args'])
    def producer(root):
        result = plan(obj, root, partition='whole', options=OPTIONS)
        if len(result['pieces']) != 1 or result['pieces'][0]['name'] != value['name']:
            raise ValueError('Canopy requires its original whole membership')
    run_plan(context, producer)
