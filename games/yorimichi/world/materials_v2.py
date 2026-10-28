"""Author one shared native material package from explicit frozen inputs."""
from pathlib import Path
import sys


def _helpers():
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    sys.path.insert(0, str(scripts))
    import shared_materials
    import material_assets
    import foliage_material
    import see_through
    return shared_materials, material_assets, foliage_material, see_through


def run(context):
    """@cc [owner:fontanierh,label:correctness] one-authored-material-package
    A job MUST create/save only its one declared package, using the original narrow
    factories and shader/instance overlays. Every loaded game package MUST be an
    explicit input; native parent dependencies MUST already be staged. The old main,
    build_materials and world_materials monoliths MUST NOT execute. Failed compilation,
    unexpected output identity or a failed final save MUST prevent completion.
    """
    import unreal
    if set(context.params) != {'args', 'settings'} or context.params['settings'] != []:
        raise ValueError('unsupported authored material parameters/settings')
    args = context.params['args']
    name, package, factory = args['asset'], args['package'], args['factory']
    fields = {'wind': set(), 'collection': set(), 'master': {'masked', 'unlit', 'fixed_texture', 'wind', 'overlay'},
              'grass': {'overlay'}, 'cloud': {'texture'}, 'painterly': set(),
              'instance': {'parent', 'texture', 'tint', 'bark_lod', 'mask_instance', 'cut_scale'}}
    if factory not in fields or set(args) - {'asset', 'package', 'factory', 'inputs'} - fields[factory]:
        raise ValueError('unsupported authored material factory arguments')
    expected = '/Game/SeeThrough/MPC_SeeThrough' if name == 'MPC_SeeThrough' else '/Game/Japan/Materials/' + name
    if package != expected or list(context.outputs) != [package]:
        raise ValueError('authored material must own exactly its declared package')
    declared = args['inputs']
    if set(context.inputs) != set(declared) or set(context.packages) != set(declared):
        raise ValueError('authored material input slots differ from its explicit package dependencies')
    for slot, path in declared.items():
        actual = context.packages[slot]
        if actual != path and actual != [path]:
            raise ValueError('authored material input package differs: ' + slot)
        if not path.startswith('/Game/') or path == package:
            raise ValueError('unsupported or overlapping authored material input')
    loaded = {}
    for slot, path in declared.items():
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if asset is None:
            raise ValueError('missing declared material dependency: ' + path)
        loaded[slot] = asset
    shared, assets, foliage, see = _helpers()
    if factory == 'wind' and name == 'MPC_Wind':
        result = shared.make_mpc()
    elif factory == 'collection' and name == 'MPC_SeeThrough':
        result = see.collection(create=True)
    elif factory == 'master':
        result = shared.master(name, masked=args.get('masked', False), unlit=args.get('unlit', False),
            white=loaded.get('T_white'), fixed_tex=loaded.get(args.get('fixed_texture')),
            mpc=loaded.get('MPC_Wind') if args.get('wind') else None)
    elif factory == 'grass' and name == 'M_Grass':
        result = shared.grass_material(loaded['T_white'], loaded['MPC_Wind'])
    elif factory == 'cloud' and name == 'M_CloudShadow':
        result = shared.cloud_shadow_material(loaded[args['texture']])
    elif factory == 'painterly' and name == 'M_Painterly':
        result = shared.painterly_material()
    elif factory == 'instance':
        result = assets.instance(name, loaded[args['parent']], loaded.get(args.get('texture')),
                                 tuple(args['tint']) if 'tint' in args else None)
        if args.get('bark_lod'):
            foliage.enable_bark_lod_blend(result)
        if args.get('mask_instance'):
            see.mask_instance(result)
        if 'cut_scale' in args:
            if not see.cut_scale(result, tuple(args['cut_scale'])):
                raise ValueError('could not set authored material CutScale')
    else:
        raise ValueError('unsupported authored material factory')
    if args.get('overlay') is not None:
        if not see.add_mask(result, **args['overlay']) or not see.save(result):
            raise ValueError('could not compile/save authored see-through overlay')
    if result is None or result.get_path_name().split('.')[0] != package:
        raise ValueError('authored factory returned another package')
    if not unreal.EditorAssetLibrary.save_loaded_asset(result, False):
        raise ValueError('could not save the authored material package')
