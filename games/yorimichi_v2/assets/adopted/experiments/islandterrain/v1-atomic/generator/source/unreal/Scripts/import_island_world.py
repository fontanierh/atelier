"""One native owner for independent island pieces and their replacement Slice map."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'world'))
import yori  # noqa: E402
import json
import math
import unreal
from asset_catalog import material_bindings  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier import native_packages  # noqa: E402

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(yori.GAME))
from island_atomic_products import read  # noqa: E402
from island_native_policy import MATERIAL_PACKAGES  # noqa: E402
from import_island_atomic import receive,retire_after_map  # noqa: E402
from setup_project import build_level  # noqa: E402


def document(path):
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():raise ValueError('Island world data must be regular')
    return json.loads(path.read_text())


def main():
    """@cc [owner:fontanierh,label:correctness] single-island-native-and-map-owner
    Receive every independently cached island primary under current native
    validation, then save the original Slice lighting/map with all non-sea
    children at the original origin. Retire old parents/obsolete pieces only
    after that save and exact current runtime membership agree. Other world
    and region importers MUST NOT recreate those parents or mutate this map.
    Preserve final original sand/coast/forest/sea shaders, including M_Sea.
    """
    groups=read(yori.OUT)  # Complete source/link/hash preflight before material writes.
    runtime=document(yori.OUT/'terrain/island.json')
    members={parent:[row['asset'] for row in value['meshes']] for parent,value in runtime['parents'].items()}
    expected={parent:[row['asset'] for row in value['pieces']] for parent,value in groups.items()}
    if (runtime.get('schema')!=1 or runtime.get('complete') is not True or runtime.get('origin')!=[0.,0.,0.]
            or members!=expected):raise ValueError('Runtime island roster differs from validated source')
    world=document(yori.OUT/'world.json');start=world.get('player_start')
    if (not isinstance(start,list) or len(start)!=4
            or any(type(value) not in (int,float) or not math.isfinite(value) for value in start)):
        raise ValueError('Invalid island map player start')
    library=unreal.EditorAssetLibrary
    materials={name:library.load_asset(path) for name,path in material_bindings().items()}
    if not all(materials.values()):raise RuntimeError('Missing shared materials before island map save')
    from import_southwest import sand_material,sea_material
    from forest_ground import material,coast_instance,coast_rock_instance
    from material_assets import instance
    forest=material();instance('MI_FarForest',forest)
    coast_instance(forest);coast_rock_instance();sand_material();sea_material()
    for path in MATERIAL_PACKAGES:
        asset=library.load_asset(path)
        if asset is None:raise RuntimeError('Missing current island material product: '+path)
        native_packages.save(asset,library,yori.GAME/'unreal/Content')
    received=receive()
    meshes={parent:[] for parent in received['groups']}
    for parent,rows in received['groups'].items():
        for row in rows:
            mesh=library.load_asset(row['asset'])
            if mesh is None:raise RuntimeError('Current island child missing before map save: '+row['asset'])
            meshes[parent].append((row['name'],mesh))
    build_level(meshes,world,materials)
    if document(yori.OUT/'terrain/island.json')!=runtime:raise ValueError('Island runtime changed during native receiving')
    meshes=mesh=None
    unreal.SystemLibrary.collect_garbage()
    retire_after_map(received,runtime_members=members)


if __name__=='__main__':main()
