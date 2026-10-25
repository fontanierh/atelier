"""Finish one Kei car: its raw import duplicated to /Game/Japan/Assets/<car> on M_Village, checked as import_kei.py does.

import_kei.py binds M_Village to slot 0, requires the bounding box max X to match the source within 0.3 cm and the
convex collision element count to equal the source's collision boxes, then saves. The source values here are the
car's own export child receipt (export.json: bounds and metadata.collision_hulls), not the combined manifest.
"""
import json
from pathlib import Path
import re

DEST = '/Game/Japan/Assets/'
MATERIAL = '/Game/Japan/Materials/M_Village'
CAR = re.compile(r'SM_Kei_[A-Za-z0-9]+\Z')
MAX_RECEIPT = 1024 * 1024


def _one(context, slot):
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if slot not in context.inputs or not isinstance(packages, (list, tuple)) or len(packages) != 1:
        raise ValueError('Kei input must be exactly one declared package: ' + slot)
    return packages[0]


def _receipt(context, slot, car):
    root = context.inputs.get(slot)
    if root is None or context.packages.get(slot) not in ([], (), None):
        raise ValueError('Kei export child must be a declared data input')
    root = Path(root)
    path = root / 'export.json'
    if (not root.is_absolute() or root.is_symlink() or not root.is_dir() or path.is_symlink() or not path.is_file()
            or path.stat().st_size > MAX_RECEIPT):
        raise ValueError('Kei export child has no regular export receipt')
    receipt = json.loads(path.read_bytes())
    bounds, metadata = receipt.get('bounds'), receipt.get('metadata')
    if (receipt.get('asset') != car or receipt.get('primary') != car + '.fbx'
            or not isinstance(bounds, list) or len(bounds) != 2 or any(not isinstance(v, list) or len(v) != 3 for v in bounds)
            or not isinstance(metadata, dict) or type(metadata.get('collision_hulls')) is not int
            or type(receipt.get('triangles')) is not int):
        raise ValueError('Kei export receipt is not this car\'s FBX child')
    return receipt


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-kei-finish
    The finish MUST own exactly /Game/Japan/Assets/<car> for the one exported child
    named <car>, as a fresh duplicate of its declared raw import, bind the declared
    M_Village to slot 0 and keep import_kei.py's scale and collision checks against
    that child's receipt before and after its save. Raw and material inputs are read-only.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if (set(params) != {'op', 'kind', 'source', 'destination', 'args'} or params['op'] != 'finish'
            or params['kind'] != 'static_mesh' or params['source'] != 'raw' or not isinstance(args, dict)
            or set(args) != {'car', 'piece', 'export', 'material'} or not CAR.fullmatch(str(args['car']))):
        raise ValueError('Unexpected Kei finish parameters')
    car = args['car']
    if args['piece'] != car:
        raise ValueError('Kei export child is not its car: ' + str(args['piece']))
    destination = DEST + car
    if params['destination'] != destination or list(context.outputs) != [destination]:
        raise ValueError('Kei finish must own exactly ' + destination)
    if set(context.inputs) != {'raw', args['export'], args['material']}:
        raise ValueError('Kei finish inputs differ from its declaration')
    receipt = _receipt(context, args['export'], car)
    library = unreal.EditorAssetLibrary
    material_path = _one(context, args['material'])
    material = library.load_asset(material_path)
    if material_path != MATERIAL or not isinstance(material, unreal.MaterialInterface):
        raise ValueError('Kei finish needs the declared M_Village')
    raw_path = _one(context, 'raw')
    if not raw_path.startswith('/Game/_Raw/') or not isinstance(library.load_asset(raw_path), unreal.StaticMesh):
        raise ValueError('Kei raw input is not a raw StaticMesh')
    if library.does_asset_exist(destination):
        raise ValueError('Kei finish destination must be fresh: ' + destination)
    mesh = library.duplicate_asset(raw_path, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh.get_path_name().split('.', 1)[0] != destination:
        raise ValueError('Kei raw duplicate failed: ' + destination)
    mesh.set_material(0, material)
    def validate():
        box = mesh.get_bounding_box()
        if abs(box.max.x - receipt['bounds'][1][0] * 100) >= .3:
            raise ValueError(f'{car}: axis/scale differs from its export ({box.max.x})')
        boxes = len(mesh.get_editor_property('body_setup').get_editor_property('agg_geom').get_editor_property('convex_elems'))
        if boxes != receipt['metadata']['collision_hulls']:
            raise ValueError(f'{car}: collision {boxes} differs from its export')
        if mesh.get_material(0) != material:
            raise ValueError(f'{car}: lost M_Village')
    validate()
    if not library.save_loaded_asset(mesh, False):
        raise ValueError('Kei package save failed: ' + destination)
    validate()
    return mesh
