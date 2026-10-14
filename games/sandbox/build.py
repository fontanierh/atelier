"""A portable block library and independent placements, then the compiled editor and test ground."""
from pathlib import Path

from atelier.build import Product, Python, Step, UnrealScript, UnrealCompile

GAME = Path(__file__).resolve().parent
SCRIPTS = GAME / 'unreal' / 'Scripts'


def steps(ctx):
    from atelier import paths
    return [
        Step('world.block', [Python(GAME / 'world/build_block.py',
                                   (GAME / 'world/block.json', ctx.out / 'block', GAME / 'world/block.override.json'))],
             inputs=[GAME / 'world/block.json'], optional_inputs=[GAME / 'world/block.override.json'], cache=True, audit=True,
             products=[Product('block.shape', (ctx.out / 'block/shape.json',)),
                       Product('block.bounds', (ctx.out / 'block/bounds.json',))],
             about='portable block dimensions and independently consumed bounds'),
        Step('world.placements', [Python(GAME / 'world/build_placements.py',
                                        (GAME / 'world/placements.json', ctx.out / 'placements.json'))],
             inputs=[GAME / 'world/placements.json'], references=['block.shape'], cache=True, audit=True,
             products=[Product('world.placements', (ctx.out / 'placements.json',))],
             about='positions reference asset IDs without deriving their geometry'),
        Step('unreal.compile', [UnrealCompile('SandboxEditor')],
             inputs=[GAME / 'unreal' / 'Source', ctx.uproject, paths.ENGINE_PLUGINS], heavy=True,
             about='the Sandbox C++ module (editor target) and the platform plugins it enables'),
        Step('unreal.level', [UnrealScript(SCRIPTS / 'make_level.py', 'SANDBOX LEVEL SAVED')],
             inputs=[SCRIPTS / 'make_level.py'], after=['unreal.compile'], heavy=True,
             reads=['block.shape', 'world.placements'],
             about='the prop material and the test ground (/Game/Sandbox)'),
    ]
