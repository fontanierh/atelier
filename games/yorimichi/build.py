"""How Yorimichi is built from this repository: `atelier build yorimichi [step ...]`.

Order: world data and meshes (Python and Blender) -> characters -> sounds and effect textures -> the Unreal module ->
the Unreal imports -> runtime data staged into unreal/Content/Data. Every output goes to build/yorimichi (or
$ATELIER_BUILD_ROOT/yorimichi) and to the ignored unreal/Content. `atelier build yorimichi --list` prints the steps.

The Unreal imports run in the order the prototype established: `setup_project.py` rebuilds everything under
/Game/Japan (textures, props, terrain, foliage, the villager, Momiji Hamlet, Hidamari, the sailboat, the zeppelin and
the level), so every later import that writes under /Game/Japan, or uses its animation compression settings, reruns
after it. The player is installed in the prototype's four layers (full, sword, armed, skate) from one r17 source.
"""
import json, shutil
from pathlib import Path

from atelier.build import Step, Python, Blender, UnrealScript, UnrealCompile, Call
from atelier import paths

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
ASSETS = GAME / 'assets'
CHARS = ASSETS / 'characters'
AUDIO = ASSETS / 'audio'
SCRIPTS = GAME / 'unreal' / 'Scripts'
SOURCE = GAME / 'unreal' / 'Source'
NAMES = paths.STUDIO / 'atelier' / 'character'
YORI = WORLD / 'yori.py'
SOUTHWEST_MODELS = ('stand,fisher_house_a,fisher_house_b,boat_shed,stairs,dock,boat,drying_rack,temple,island,'
                    'boulder_a,boulder_b,boulder_c,stone_wall')


def warm_roles():
    """Clip role groups of the player, from its manifest (the export partitions the prototype used)."""
    manifest = json.loads((CHARS / 'warm-original' / 'source-manifest.json').read_text())
    roles = [r['role'] for r in manifest['roles']]
    combat = ['SwordIdle', 'SwordDraw', 'SwordSheath', 'SwordAttack1', 'SwordAttack2', 'SwordAttack3',
              'SwordChargeUp', 'SwordChargeHold', 'SwordChargeRelease', 'SwordParry', 'SwordParryHit', 'SwordCombo']
    armed = [r for r in roles if r.startswith('Sword') and r not in combat and r != 'SwordRun']
    skate = [r for r in roles if r.startswith('Skate')]
    return combat, armed, skate


def stage_data(ctx, log):
    """Copy the runtime files the game reads (YoriData.h) into unreal/Content/Data."""
    out, data = ctx.out, paths.content_data(ctx.game)
    files = {
        'world.json': out / 'world.json',
        'heightmap.bin': out / 'heightmap.bin',
        'hidamari/city.json': out / 'hidamari' / 'city.json',
        'skatepark/park.json': REGIONS / 'skatepark' / 'park.json',
        'map/map.json': out / 'map' / 'map.json',
        'map/map_lines.json': out / 'map' / 'map_lines.json',
        'map/map.png': out / 'map' / 'map.png',
        'map/map.jpg': out / 'map' / 'map.jpg',
        'city_surface_tiles/v1_128m/manifest.json': out / 'city_surface_tiles' / 'v1_128m' / 'manifest.json',
        'characters/warm-original/skate-build.json': CHARS / 'warm-original' / 'skate-build.json',
    }
    for rel, src in files.items():
        dst = data / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        log.write(f'staged {rel}\n')


def steps(ctx):
    out = ctx.out
    combat, armed, skate = warm_roles()
    warm = CHARS / 'warm-original' / 'export_unreal.py'
    return [
        # ------------------------------------------------------------ world
        Step('world.textures', [Python(WORLD / 'gen_textures.py')], inputs=[WORLD / 'gen_textures.py', YORI],
             outputs=[out / 'textures' / 'T_sky.png'], about='procedural textures (leaves, grass, bark, road, sky)'),
        Step('world.layout', [Python(WORLD / 'gen_world.py')],
             inputs=[WORLD / 'gen_world.py', WORLD / 'house_clearance.py', WORLD / 'torii_clearance.py', YORI,
                     REGIONS / 'village' / 'layout.py', REGIONS / 'mega' / 'layout.py', REGIONS / 'southwest',
                     REGIONS / 'forest_lake' / 'layout.py', REGIONS / 'zeppelin' / 'layout.py'],
             outputs=[out / 'world.json', out / 'heightmap.npy', out / 'heightmap.bin'],
             about='terrain heightfield, road, scatter and every region layout -> world.json'),
        Step('world.props', [Blender(WORLD / 'build_assets.py')], inputs=[WORLD / 'build_assets.py'], needs=['world.textures'],
             outputs=[out / 'assets' / 'House.fbx'], about='trees, bushes, grass, rocks, house, torii, lanterns, birds, sky dome'),
        Step('world.foliage_lods', [Blender(WORLD / 'build_foliage_lods.py')],
             inputs=[WORLD / 'build_foliage_lods.py', WORLD / 'build_assets.py'], needs=['world.textures'],
             outputs=[out / 'foliage_lods' / 'manifest.json'], about='seeded LOD chains for trees, bushes and grass'),
        Step('world.hidamari', [Blender(REGIONS / 'hidamari' / 'build.py')],
             inputs=[REGIONS / 'hidamari', REGIONS / 'village' / 'build.py', REGIONS / 'zeppelin' / 'layout.py'],
             needs=['world.layout'], outputs=[out / 'hidamari' / 'city.json', out / 'hidamari' / 'manifest.json'],
             about='the city: layout (city.json), building kit, harbor, plaza, arcade, mountains'),
        Step('world.zeppelin', [Blender(REGIONS / 'zeppelin' / 'build.py', threads=2)],
             inputs=[REGIONS / 'zeppelin', REGIONS / 'village' / 'build.py'], needs=['world.layout', 'world.hidamari'],
             outputs=[out / 'zeppelin' / 'manifest.json'], about='airship and its two stations'),
        Step('world.terrain', [Blender(WORLD / 'build_terrain.py')],
             inputs=[WORLD / 'build_terrain.py', REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py'],
             needs=['world.layout', 'world.hidamari', 'world.textures'],
             outputs=[out / 'terrain.fbx', out / 'assets' / 'Sea.fbx'], about='terrain, road, wires, far hills, sea'),
        Step('world.village', [Blender(REGIONS / 'village' / 'build.py')], inputs=[REGIONS / 'village'], needs=['world.layout'],
             outputs=[out / 'village' / 'manifest.json'], about='Momiji Hamlet'),
        Step('world.southwest', [Blender(REGIONS / 'southwest' / 'build.py', ('--models', SOUTHWEST_MODELS, '--export', '--no-render'))],
             inputs=[REGIONS / 'southwest', REGIONS / 'village' / 'build.py'], needs=['world.layout'],
             outputs=[out / 'southwest' / 'fbx' / 'SW_Temple.fbx'], about='fishing village, cove, island temple'),
        Step('world.mega', [Blender(REGIONS / 'mega' / 'build.py')], inputs=[REGIONS / 'mega', REGIONS / 'village' / 'build.py'],
             needs=['world.layout'], outputs=[out / 'mega' / 'manifest.json'], about='the mini-mega ramp and its trail'),
        Step('world.lake', [Blender(REGIONS / 'forest_lake' / 'build.py')], inputs=[REGIONS / 'forest_lake', REGIONS / 'village' / 'build.py'],
             needs=['world.layout'], outputs=[out / 'forest_lake' / 'manifest.json'], about='the woodland lake and cabin'),
        Step('world.skatepark', [Blender(REGIONS / 'skatepark' / 'build.py')],
             inputs=[*sorted((REGIONS / 'skatepark').glob('*.py'))], needs=['world.layout'],
             outputs=[out / 'skatepark' / 'build-report.json'], about='the skate pier, its rails and the trick board (park.json)'),
        Step('world.sailboat', [Blender(ASSETS / 'vehicles' / 'sailboat' / 'build.py', threads=4)],
             inputs=[ASSETS / 'vehicles' / 'sailboat', REGIONS / 'village' / 'build.py'],
             outputs=[out / 'sailboat' / 'manifest.json'], about='the dinghy'),
        Step('world.map', [Python(WORLD / 'map' / 'build_map.py')], inputs=[WORLD / 'map'],
             needs=['world.layout', 'world.hidamari', 'world.skatepark', 'world.zeppelin'],
             outputs=[out / 'map' / 'map.json', out / 'map' / 'map.png'], about='map zones and the painted sheet'),
        Step('world.city_tiles', [Blender(WORLD / 'city_surface_tiles.py', ('--tag', 'v1_128m'))],
             inputs=[WORLD / 'city_surface_tiles.py'], needs=['world.hidamari'],
             outputs=[out / 'city_surface_tiles' / 'v1_128m' / 'manifest.json'], about='desktop profile: city surfaces in 128 m tiles'),
        Step('world.city_trees', [Blender(WORLD / 'city_tree_lods.py', ('--tag', 'v4'))],
             inputs=[WORLD / 'city_tree_lods.py', REGIONS / 'hidamari' / 'arcade.py', REGIONS / 'hidamari' / 'plaza.py'],
             needs=['world.hidamari'], outputs=[out / 'city_tree_lods' / 'v4' / 'manifest.json'], about='desktop profile: city tree LODs'),
        # ------------------------------------------------------------ characters
        Step('characters.warm_original', [
                Blender(warm, ('--sword',), threads=4),
                Blender(warm, ('--clips', ','.join(combat), '--clips-only', '--sword', '--report', 'export-sword.json'), threads=4),
                Blender(warm, ('--clips', ','.join(armed), '--clips-only', '--report', 'export-armed.json'), threads=4),
                Blender(warm, ('--clips', ','.join(skate), '--clips-only', '--report', 'export-skate.json'), threads=4)],
             inputs=[CHARS / 'warm-original', NAMES], outputs=[out / 'warm_original' / 'export.json'],
             about='the player: mesh, 110 clips and the bokken to FBX (full + sword, armed, skate records)'),
        Step('characters.fox_hunter', [Blender(CHARS / 'fox-hunter' / 'export_unreal.py', threads=4)],
             inputs=[CHARS / 'fox-hunter', NAMES], outputs=[out / 'fox_hunter' / 'export.json'], about='the fox hunter: mesh and 15 clips'),
        Step('characters.wanderer', [Blender(CHARS / 'wanderer' / 'build.py', ('--animations', '--export', '--no-render'), threads=4)],
             inputs=[CHARS / 'wanderer'], outputs=[out / 'wanderer' / 'build.json'], about='the villagers (procedural model and clips)'),
        # ------------------------------------------------------------ sounds and effects
        Step('audio.footsteps', [Python(AUDIO / 'footsteps' / 'slice.py')], inputs=[AUDIO / 'footsteps', paths.cache_dir('sonniss', 'footsteps')],
             outputs=[out / 'audio' / 'footsteps' / 'manifest.json'], about='531 footstep one-shots (needs `atelier fetch`)'),
        Step('audio.combat', [Python(AUDIO / 'combat' / 'slice.py')], inputs=[AUDIO / 'combat', paths.cache_dir('sonniss', 'combat')],
             outputs=[out / 'audio' / 'combat' / 'manifest.json'], about='combat cues and the countryside ambience'),
        Step('audio.skate', [Python(AUDIO / 'skate' / 'make.py')], inputs=[AUDIO / 'skate', paths.cache_dir('sonniss', 'combat')],
             outputs=[out / 'audio' / 'skate' / 'manifest.json'], about='board loops and cues'),
        Step('fx.textures', [Python(ASSETS / 'fx' / 'gen_textures.py')], inputs=[ASSETS / 'fx'],
             outputs=[out / 'combat_fx' / 'T_FX_Glow.png'], about='glow, spark, ring, dust and trail sprites'),
        # ------------------------------------------------------------ Unreal
        # Imports run `after` the compile (the editor must load the module) but do not rerun when C++ changes; the later
        # imports run after the world (materials and folders it creates) without rerunning when it is reimported.
        Step('unreal.compile', [UnrealCompile('YorimichiEditor')], inputs=[SOURCE, ctx.uproject, paths.ENGINE_PLUGINS], heavy=True,
             about='the Yorimichi C++ module (editor target)'),
        Step('unreal.world', [UnrealScript(SCRIPTS / 'setup_project.py', 'level saved')],
             inputs=[SCRIPTS / n for n in ('setup_project.py', 'painterly_kernel.py', 'foliage_material.py', 'import_foliage_lods.py',
                                          'import_wanderer.py', 'cape_boy_material.py', 'animation_compression.py', 'import_village.py',
                                          'import_hidamari.py', 'import_southwest.py', 'arcade_material.py', 'plaza_material.py',
                                          'harbor_material.py', 'mountain_material.py', 'import_sailboat.py', 'sailboat_material.py',
                                          'import_zeppelin.py')],
             after=['unreal.compile'], needs=['world.textures', 'world.layout', 'world.props', 'world.foliage_lods', 'world.hidamari',
                    'world.zeppelin', 'world.terrain', 'world.village', 'world.sailboat', 'characters.wanderer'],
             heavy=True, about='world assets, materials, the villager and the level (/Game/Japan)'),
        # The regions below layer onto the world (the south-west import replaces the terrain's and the sea's materials),
        # so they rerun when it is reimported.
        Step('unreal.southwest', [UnrealScript(SCRIPTS / 'import_southwest.py', 'SOUTHWEST IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_southwest.py'], needs=['unreal.world', 'world.southwest', 'world.terrain'], heavy=True,
             about='south-west props, the terrain and the sea'),
        Step('unreal.mega', [UnrealScript(SCRIPTS / 'import_mega.py', 'MEGA IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_mega.py'], needs=['unreal.world', 'world.mega'], heavy=True, about='the mini-mega ramp'),
        Step('unreal.lake', [UnrealScript(SCRIPTS / 'import_forest_lake.py', 'LAKE IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_forest_lake.py', SCRIPTS / 'forest_lake_material.py'], needs=['unreal.world', 'world.lake'],
             heavy=True, about='the woodland lake and cabin'),
        Step('unreal.skatepark', [UnrealScript(SCRIPTS / 'import_skatepark.py', 'SKATEPARK IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_skatepark.py', REGIONS / 'skatepark' / 'park.json'], needs=['unreal.world', 'world.skatepark'],
             heavy=True, about='the skate pier and the board (/Game/SkatePark)'),
        Step('unreal.sounds', [
                UnrealScript(SCRIPTS / 'import_footsteps.py', 'FOOTSTEP IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_combat_audio.py', 'COMBAT AUDIO IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_skate_audio.py', 'SKATE AUDIO IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_footsteps.py', SCRIPTS / 'import_combat_audio.py', SCRIPTS / 'import_skate_audio.py'],
             after=['unreal.world'], needs=['audio.footsteps', 'audio.combat', 'audio.skate'], heavy=True, about='footstep library, combat and skate sounds'),
        Step('unreal.fx', [UnrealScript(SCRIPTS / 'import_combat_fx.py', 'COMBAT FX IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_combat_fx.py'], after=['unreal.compile'], needs=['fx.textures'], heavy=True, about='/Game/FX materials'),
        Step('unreal.fox_hunter', [UnrealScript(SCRIPTS / 'import_fox_hunter.py', 'FOX HUNTER IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_fox_hunter.py', SCRIPTS / 'animation_compression.py'],
             after=['unreal.world'], needs=['characters.fox_hunter'], heavy=True, about='/Game/FoxHunter'),
        Step('unreal.warm_original', [
                UnrealScript(SCRIPTS / 'import_warm_original.py', 'WARM ORIGINAL IMPORT COMPLETE', null_rhi=True),
                UnrealScript(SCRIPTS / 'import_warm_sword.py', 'WARM SWORD IMPORT COMPLETE', null_rhi=True),
                UnrealScript(SCRIPTS / 'import_warm_armed.py', 'WARM ARMED IMPORT COMPLETE', null_rhi=True),
                UnrealScript(SCRIPTS / 'import_warm_skate.py', 'WARM SKATE IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / n for n in ('import_warm_original.py', 'verify_warm_original.py', 'import_warm_sword.py',
                                          'import_warm_armed.py', 'import_warm_skate.py', 'animation_compression.py')],
             after=['unreal.world'], needs=['characters.warm_original'], heavy=True, about='/Game/WarmOriginal in four layers'),
        Step('unreal.desktop', [
                UnrealScript(SCRIPTS / 'import_city_surface_tiles.py', 'CITY SURFACE TILE IMPORT COMPLETE', env=(('CITY_SURFACE_TILES_TAG', 'v1_128m'),)),
                UnrealScript(SCRIPTS / 'import_city_tree_lods.py', 'CITY TREE LODS IMPORT COMPLETE', env=(('CITY_TREE_LODS_TAG', 'v4'),))],
             inputs=[SCRIPTS / 'import_city_surface_tiles.py', SCRIPTS / 'import_city_tree_lods.py', SCRIPTS / 'experiment_mesh_import.py'],
             after=['unreal.world'], needs=['world.city_tiles', 'world.city_trees'], heavy=True,
             about='desktop profile: city tiles and tree LODs (/Game/Experiments)'),
        Step('data.stage', [Call('stage_data', stage_data)],
             inputs=[REGIONS / 'skatepark' / 'park.json', CHARS / 'warm-original' / 'skate-build.json'],
             needs=['world.layout', 'world.hidamari', 'world.map', 'world.city_tiles'],
             outputs=[GAME / 'unreal' / 'Content' / 'Data' / 'world.json'], about='runtime files into unreal/Content/Data'),
    ]
