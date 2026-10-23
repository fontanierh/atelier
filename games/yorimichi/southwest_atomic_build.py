"""Independent Southwest logical source construction and bounded per-piece exports."""
import importlib.util
from pathlib import Path

from atelier.build import Product
from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGION = WORLD / 'regions/southwest'
# Preserve the production roster and logical world instance keys exactly.
MODELS = (
    ('stand', 'SW_CoconutStand'), ('fisher_house_a', 'SW_FisherHouseA'),
    ('fisher_house_b', 'SW_FisherHouseB'), ('boat_shed', 'SW_BoatShed'),
    ('stairs', 'SW_StoneStairs'), ('dock', 'SW_Dock'), ('boat', 'SW_Boat'),
    ('drying_rack', 'SW_DryingRack'), ('temple', 'SW_Temple'), ('island', 'SW_Island'),
    ('boulder_a', 'SW_Boulder_A'), ('boulder_b', 'SW_Boulder_B'), ('boulder_c', 'SW_Boulder_C'),
    ('stone_wall', 'SW_StoneWall'), ('pine_lean_a', 'Tree_PineLean_A'), ('pine_lean_b', 'Tree_PineLean_B'))


def steps(ctx):
    """@cc [owner:fontanierh,label:correctness;performance] independent-southwest-export-owners
    Each production logical model MUST have an independent factory-startup source planner
    and its explicitly measured original random context. No sibling constructor or export
    may recover that state. Every bounded leaf MUST own one independently cached export;
    assembly MUST only gather complete files. Final query surfaces precede all exports.
    The old render-only FBX collision policy MUST remain complex-as-simple, without turning
    diagnostic Mesh.colliders boxes into newly authored blocking UCX.
    """
    spec = importlib.util.spec_from_file_location('southwest_region_graph', GAME / 'region_exports.py')
    graph = importlib.util.module_from_spec(spec); spec.loader.exec_module(graph)
    assets = []
    for model, asset in MODELS:
        query = ctx.out / 'southwest/query' / (asset + '.npz')
        context = REGION / 'contexts' / (asset + '.json')
        module = ('stand' if model == 'stand' else 'temple' if model == 'temple' else
                  'island' if model in ('island','boulder_a','boulder_b','boulder_c','pine_lean_a','pine_lean_b') else 'fishing')
        code = local_imports(REGION / (module + '.py'), (WORLD, WORLD / 'regions'))
        assets.append(graph.LogicalAsset(asset, REGION / 'plan_asset.py',
            args=('--model', model, '--context', str(context), '--query-output', str(query)),
            inputs=(*code, context), products=(Product('southwest.query.' + asset, (query,)),)))
    return graph.steps(ctx, region='southwest', assets=assets)


def assembly_step(ctx):
    """Keep the existing public world owner as a file-only complete membership assembly."""
    from atelier.build import Call, Step
    from atelier.build_inputs import local_imports
    spec = importlib.util.spec_from_file_location('southwest_current_products', GAME / 'southwest_atomic_products.py')
    products = importlib.util.module_from_spec(spec); spec.loader.exec_module(products)
    def assemble(ctx, log):
        products.assemble(ctx.out, log)
    return Step('world.southwest', [Call('assemble Southwest logical runtime membership', assemble)],
        inputs=[*local_imports(GAME / 'southwest_atomic_products.py', (GAME, WORLD))],
        reads=['southwest.atomic'], products=[Product('southwest.meshes', (ctx.out / 'southwest/runtime.json',))],
        cache=True, about='file-only complete Southwest membership; preserves independent native children')
