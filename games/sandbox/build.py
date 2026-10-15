"""A portable block library and independent placements, then the compiled editor and test ground."""
from pathlib import Path

from atelier.build import BBoxQuery, Product, Python, Step, UnrealScript, UnrealCompile

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
    ] + spatial_steps(ctx)


def spatial_steps(ctx):
    """Fresh source declarations; actions receive only frozen matching results, never this catalogue."""
    import json
    from atelier.build_inputs import local_imports
    sources = []
    source_script = GAME / 'world/build_spatial_source.py'
    for path in sorted((GAME / 'world/spatial').glob('*.json')):
        bounds = json.loads(path.read_text())['bounds_cm']
        name = path.stem
        output = ctx.out / 'spatial/sources' / name
        sources.append(Step(f'spatial.source.{name}', [Python(source_script, (path, output))],
                            inputs=[path], cache=True, audit=True, explicit=True,
                            products=[Product(f'spatial.{name}', (output / 'geometry.json',),
                                              collection='blocks.cm', bounds=bounds),
                                      Product(f'spatial.{name}.preview', (output / 'preview.json',))]))
    tiles = []
    tile_script = GAME / 'world/build_spatial_tile.py'
    for name, start in (('west', 0), ('east', 100)):
        output = ctx.out / f'spatial/tiles/{name}.json'
        tiles.append(Step(f'spatial.tile.{name}', [Python(tile_script, (output,))],
                          inputs=local_imports(tile_script), cache=True, audit=True, explicit=True,
                          queries=[BBoxQuery('neighbours', 'blocks.cm', (start, -50, -50, start + 100, 50, 50))],
                          products=[Product(f'spatial.tile.{name}', (output,))]))
    return [*sources, *tiles, Step('spatial.demo', [], explicit=True,
                                  after=[s.name for s in (*sources, *tiles)],
                                  about='offline spatial dependency and cache example')]
