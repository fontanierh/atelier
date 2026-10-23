"""Declared city placement products and independent logical mesh construction inputs."""
import importlib.util
from pathlib import Path

from atelier.build import Blender, Product, Python, Step
from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
REGION = REGIONS / 'hidamari'
DATA_ASSETS = ('HD_CivicGardens', 'HD_Streets', 'HD_PlazaShopApproaches', 'HD_Wires', 'HD_LaneEdges')


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def layout_steps(ctx, *, terrain_inputs=(), terrain_needs=()):
    """@cc [owner:fontanierh,label:correctness;performance] independent-city-layout-products
    City placement MUST be constructed without building or exporting any mesh. Declare
    its complete code, terrain, source-presence and canopy-dimension inputs. Selected
    constructor projections MUST consume only their declared city fields and stop
    unchanged values before any geometry task. Mesh definitions and sibling export
    identities MUST NOT enter a selected city's placement projection or export key.
    """
    out = ctx.out
    script = REGION / 'layout_data.py'
    city = out / 'hidamari/layout-data.json'
    assets = GAME / 'assets'
    result = [Step('world.hidamari.layout_data', [Blender(script, ('--output', str(city)),
        threads=3, factory_startup=True, env=(('PYTHONHASHSEED', '0'),))],
        inputs=[*local_imports(script, (WORLD, REGIONS)), *terrain_inputs,
                REGION / 'location.json', assets / 'hidamari/props',
                assets / 'megapark/map.json', assets / 'megapark/geometry', assets / 'megapark/collision',
                out / 'world.json', out / 'heightmap.npy', out / 'farhills.npy',
                out / 'megapark/trail.json', out / 'treehouse/trees/trees.json'],
        needs=['world.layout', 'world.treehouse_trees', *terrain_needs],
        reads=['terrain.FarHills.final'], products=[Product('hidamari.city_data', (city,))],
        cache=True, toolchain=True, heavy=True,
        about='city placement and final-surface queries without constructing meshes')]
    projection_script = REGION / 'city_data.py'
    for key in DATA_ASSETS:
        path = out / 'hidamari/constructor-data' / (key + '.json')
        result.append(Step('world.hidamari.data.' + key, [Python(projection_script, (
            '--source', str(city), '--asset', key, '--output', str(path)))],
            inputs=local_imports(projection_script, (WORLD, REGIONS)),
            reads=['hidamari.city_data'], products=[Product('hidamari.data.' + key, (path,))],
            cache=True, about='only the city fields consumed by ' + key))
    return result
