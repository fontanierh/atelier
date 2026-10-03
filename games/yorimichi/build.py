"""How Yorimichi is built from this repository: `atelier build yorimichi [step ...]`.

Order: world data and meshes (Python and Blender) -> characters -> sounds and effect textures -> the Unreal module ->
the Unreal imports -> runtime data staged into unreal/Content/Data. Every output goes to build/yorimichi (or
$ATELIER_BUILD_ROOT/yorimichi) and to the ignored unreal/Content. `atelier build yorimichi --list` prints the steps.

The Unreal imports run in the order the prototype established: `setup_project.py` rebuilds everything under
/Game/Japan (textures, props, terrain, foliage, the villager, Momiji Hamlet, Hidamari, the sailboat, the zeppelin and
the level), so every later import that writes under /Game/Japan, or uses its animation compression settings, reruns
after it. The player is installed in the prototype's three layers (full, sword, armed) from one source blend.
"""
import importlib.util, json, shutil, os
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
TOOLS = GAME / 'tools'
TREEHOUSE = REGIONS / 'treehouse'
SOURCE = GAME / 'unreal' / 'Source'
NAMES = paths.STUDIO / 'atelier' / 'character'
YORI = WORLD / 'yori.py'
SOUTHWEST_MODELS = ('stand,fisher_house_a,fisher_house_b,boat_shed,stairs,dock,boat,drying_rack,temple,island,'
                    'boulder_a,boulder_b,boulder_c,stone_wall,pine_lean_a,pine_lean_b')


def cairo_roles():
    """Clip role groups of the player, from its manifest (the export partitions the prototype used)."""
    manifest = json.loads((CHARS / 'cairo' / 'source-manifest.json').read_text())
    roles = [r['role'] for r in manifest['roles']]
    combat = ['SwordIdle', 'SwordDraw', 'SwordSheath', 'SwordAttack1', 'SwordAttack2', 'SwordAttack3',
              'SwordChargeUp', 'SwordChargeHold', 'SwordChargeRelease', 'SwordParry', 'SwordParryHit', 'SwordCombo']
    armed = [r for r in roles if r.startswith('Sword') and r not in combat and r != 'SwordRun']
    return combat, armed, roles


# Runtime files the game reads through AtelierDataPath, relative to unreal/Content/Data. Each is also an output of
# data.stage, so a file missing there (a renamed folder, a new entry) makes the step run.
STAGED = ('world.json', 'heightmap.bin', 'hidamari/city.json', 'skatepark/park.json', 'map/map.json', 'map/map_lines.json',
          'map/map.png', 'map/map.jpg', 'city_surface_tiles/v1_128m/manifest.json',
          'treehouse/runtime.json', 'megapark/park.json')


def staged_source(out, rel):
    """Where a staged file comes from: build output, except the committed park."""
    return {'skatepark/park.json': REGIONS / 'skatepark' / 'park.json'}.get(rel, out / rel)


def stage_data(ctx, log):
    """Copy the runtime files the game reads into unreal/Content/Data."""
    data = paths.content_data(ctx.game)
    for rel in STAGED:
        dst = data / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged_source(ctx.out, rel), dst)
        log.write(f'staged {rel}\n')


def botw_library():
    """assets/characters/botw/library.py: whether the local BOTW library is here, and the files the roster reads."""
    spec = importlib.util.spec_from_file_location('botw_library', CHARS / 'botw' / 'library.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def botw_steps(out):
    """The BOTW characters (assets/characters/botw/README.md), only where the library has been fetched."""
    library = botw_library()
    if not library.available():
        return []
    botw = CHARS / 'botw'
    return [
        Step('characters.botw', [Python(botw / 'export.py')], inputs=[botw, *library.sources()],
             outputs=[out / 'botw' / 'export.json'], about='BOTW characters: curve clips baked into rigged GLBs'),
        Step('unreal.botw', [UnrealScript(SCRIPTS / 'import_botw.py', 'BOTW IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / 'import_botw.py', SCRIPTS / 'animation_compression.py'], after=['unreal.world'],
             needs=['characters.botw'], outputs=[GAME / 'unreal' / 'Content' / 'Data' / 'botw' / 'roster.json'],
             heavy=True, about='/Game/Botw: meshes, materials and clips, and the roster the game reads'),
        Step('characters.cairo_botw', [Blender(CHARS / 'cairo' / 'botw.py', threads=4)], inputs=[CHARS / 'cairo', NAMES],
             needs=['characters.botw'], outputs=[out / 'cairo' / 'botw' / 'export.json'],
             about="Link's move set clips retargeted onto Cairo, to FBX"),
        Step('unreal.cairo_botw', [UnrealScript(SCRIPTS / 'import_cairo_botw.py', 'CAIRO BOTW IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / 'import_cairo_botw.py', SCRIPTS / 'animation_compression.py'],
             needs=['characters.cairo_botw', 'unreal.cairo', 'unreal.botw'],
             outputs=[GAME / 'unreal' / 'Content' / 'Data' / 'cairo' / 'botw.json'], heavy=True,
             about='/Game/CairoBotw: Cairo with the BOTW move set (-rider=CairoBotw): his clips, definition and move record'),
    ]


def steps(ctx):
    out = ctx.out
    combat, armed, locomotion = cairo_roles()
    cairo = CHARS / 'cairo' / 'export_unreal.py'
    return [
        # ------------------------------------------------------------ world
        Step('world.textures', [Python(WORLD / 'gen_textures.py')], inputs=[WORLD / 'gen_textures.py', YORI],
             outputs=[out / 'textures' / 'T_sky.png'], about='procedural textures (leaves, grass, bark, road, sky)'),
        # The tree house's tall canopy trees come first: its layout sizes them from trees.json.
        Step('world.treehouse_trees', [Blender(TREEHOUSE / 'trees.py', threads=4)], inputs=[TREEHOUSE / 'trees.py', WORLD / 'build_assets.py'],
             needs=['world.textures'], outputs=[out / 'treehouse' / 'trees' / 'trees.json'],
             about='tree house canopy trees (four autumn crowns) and their recoloured leaf atlases'),
        Step('world.layout', [Python(WORLD / 'gen_world.py')],
             inputs=[WORLD / 'gen_world.py', REGIONS / 'houses' / 'layout.py', WORLD / 'torii_clearance.py', YORI,
                     REGIONS / 'village' / 'layout.py', REGIONS / 'mega' / 'layout.py', REGIONS / 'southwest',
                     REGIONS / 'skatepark' / 'layout.py',
                     REGIONS / 'forest_lake' / 'layout.py', REGIONS / 'zeppelin' / 'layout.py', TREEHOUSE / 'layout.py',
                     TREEHOUSE / 'screen.py', REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'forest.py',
                     REGIONS / 'megapark' / 'trail.py', REGIONS / 'megapark' / 'gate.py', REGIONS / 'hidamari' / 'mountains.py'],
             needs=['world.treehouse_trees'],
             outputs=[out / 'world.json', out / 'heightmap.npy', out / 'heightmap.bin', out / 'treehouse' / 'layout.json',
                      out / 'megapark' / 'trail.json'],
             about='terrain heightfield, road, scatter and every region layout -> world.json'),
        Step('world.props', [Blender(WORLD / 'build_assets.py')], inputs=[WORLD / 'build_assets.py'], needs=['world.textures'],
             outputs=[out / 'assets' / 'Torii.fbx'], about='trees, bushes, grass, rocks, torii, lanterns, birds, sky dome'),
        Step('world.foliage_lods', [Blender(WORLD / 'build_foliage_lods.py')],
             inputs=[WORLD / 'build_foliage_lods.py', WORLD / 'build_assets.py'], needs=['world.textures'],
             outputs=[out / 'foliage_lods' / 'manifest.json'], about='seeded LOD chains for trees, bushes and grass'),
        Step('world.hidamari', [Blender(REGIONS / 'hidamari' / 'build.py')],
             inputs=[REGIONS / 'hidamari', REGIONS / 'village' / 'build.py', REGIONS / 'zeppelin' / 'layout.py',
                     REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'forest.py', REGIONS / 'megapark' / 'trail.py',
                     REGIONS / 'megapark' / 'gate.py'],
             needs=['world.layout'], outputs=[out / 'hidamari' / 'city.json', out / 'hidamari' / 'manifest.json'],
             about='the city: layout (city.json), building kit, harbor, plaza, arcade, mountains'),
        Step('world.zeppelin', [Blender(REGIONS / 'zeppelin' / 'build.py', threads=2)],
             inputs=[REGIONS / 'zeppelin', REGIONS / 'village' / 'build.py', REGIONS / 'hidamari' / 'mountains.py',
                     REGIONS / 'megapark' / 'gate.py'],
             needs=['world.layout', 'world.hidamari'],
             outputs=[out / 'zeppelin' / 'manifest.json'], about='airship and its three stations'),
        Step('world.treehouse_textures', [Python(TOOLS / 'treehouse_textures.py', ('finish',))],
             inputs=[TOOLS / 'treehouse_textures.py', ASSETS / 'treehouse' / 'textures'],
             outputs=[out / 'treehouse' / 'textures' / 'textures.json'],
             about='tree house textures: seamless detail maps and pictures from the Sunburst paintings'),
        Step('world.treehouse_props', [Blender(TREEHOUSE / 'props.py', threads=4)],
             inputs=[TREEHOUSE / 'props.py', TOOLS / 'treehouse_props.py', ASSETS / 'treehouse' / 'props'],
             outputs=[out / 'treehouse' / 'props' / 'props.json'], about='the 13 Tripo props fitted to their sizes'),
        Step('world.treehouse', [Blender(TREEHOUSE / 'build.py', threads=4)],
             inputs=[TREEHOUSE / 'build.py', TREEHOUSE / 'tmesh.py', TREEHOUSE / 'layout.py', REGIONS / 'village' / 'build.py'],
             needs=['world.layout'], outputs=[out / 'treehouse' / 'manifest.json', out / 'treehouse' / 'runtime.json'],
             about='the tree house: ten places, bridges, rooms and their dressing, lights, sunbeams'),
        Step('world.terrain', [Blender(WORLD / 'build_terrain.py')],
             inputs=[WORLD / 'build_terrain.py', REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py',
                     REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'trail.py', REGIONS / 'megapark' / 'gate.py'],
             needs=['world.layout', 'world.hidamari', 'world.textures'],
             outputs=[out / 'terrain.fbx', out / 'assets' / 'Sea.fbx'], about='terrain, road, wires, far hills, sea'),
        Step('world.village', [Blender(REGIONS / 'village' / 'build.py')], inputs=[REGIONS / 'village'], needs=['world.layout'],
             outputs=[out / 'village' / 'manifest.json'], about='Momiji Hamlet'),
        Step('world.houses', [Blender(REGIONS / 'houses' / 'build.py')], inputs=[REGIONS / 'houses', REGIONS / 'village' / 'build.py'],
             needs=['world.layout'], outputs=[out / 'houses' / 'manifest.json'],
             about='the five houses on the main road: three house models and their lots (terrace, hedge, gate, ishigaki)'),
        Step('world.southwest', [Blender(REGIONS / 'southwest' / 'build.py', ('--models', SOUTHWEST_MODELS, '--export', '--no-render'))],
             inputs=[REGIONS / 'southwest', REGIONS / 'village' / 'build.py'], needs=['world.layout'],
             outputs=[out / 'southwest' / 'fbx' / 'SW_Temple.fbx'], about='fishing village, cove, island temple'),
        Step('world.mega', [Blender(REGIONS / 'mega' / 'build.py')], inputs=[REGIONS / 'mega', REGIONS / 'village' / 'build.py'],
             needs=['world.layout'], outputs=[out / 'mega' / 'manifest.json'], about='the mini-mega ramp and its trail'),
        Step('world.megapark_restyle', [Python(TOOLS / 'megapark_textures.py', ('finish',))],
             inputs=[TOOLS / 'megapark_textures.py', ASSETS / 'megapark' / 'restyle', ASSETS / 'megapark' / 'map.json',
                     REGIONS / 'megapark' / 'sign.py', REGIONS / 'hidamari' / 'fonts' / 'NotoSansJP.ttf'],
             outputs=[out / 'megapark' / 'textures' / 'textures.json', out / 'megapark' / 'lettering' / 'NotoSansJP-Black.ttf'],
             about='Mega Park restyle: island-style rock, earth, paint and signs, lightmap levels, the 寄り道 font'),
        Step('world.megapark', [Blender(REGIONS / 'megapark' / 'build.py', threads=4)],
             inputs=[REGIONS / 'megapark' / 'build.py', REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'plants.py',
                     REGIONS / 'megapark' / 'sign.py', REGIONS / 'megapark' / 'cars.py', ASSETS / 'megapark', YORI], needs=['world.megapark_restyle'],
             outputs=[out / 'megapark' / 'build.json', out / 'megapark' / 'park.json', out / 'megapark' / 'fbx' / 'SM_MP_ImportSeed.fbx'],
             about='original Super Ultra Mega Park geometry, riding collision and grind curves -> FBX'),
        Step('world.lake', [Blender(REGIONS / 'forest_lake' / 'build.py')], inputs=[REGIONS / 'forest_lake', REGIONS / 'village' / 'build.py'],
             needs=['world.layout'], outputs=[out / 'forest_lake' / 'manifest.json'], about='the woodland lake and cabin'),
        Step('world.skatepark_textures', [Python(TOOLS / 'pier_textures.py', ('finish',))],
             inputs=[TOOLS / 'pier_textures.py', ASSETS / 'skatepark' / 'textures', ASSETS / 'megapark' / 'restyle' / 'stone_cut.jpg'],
             outputs=[out / 'skatepark' / 'textures' / 'textures.json'], about='Sunburst pier material maps (offline; no paid calls)'),
        Step('world.skatepark', [Blender(REGIONS / 'skatepark' / 'build.py')],
             inputs=[*sorted((REGIONS / 'skatepark').glob('*.py'))], needs=['world.layout', 'world.skatepark_textures'],
             outputs=[out / 'skatepark' / 'build-report.json'], heavy=True, about='the skate pier, its rails and the trick board (park.json)'),
        Step('world.sailboat', [Blender(ASSETS / 'vehicles' / 'sailboat' / 'build.py', threads=4)],
             inputs=[ASSETS / 'vehicles' / 'sailboat', REGIONS / 'village' / 'build.py'],
             outputs=[out / 'sailboat' / 'manifest.json'], about='the dinghy'),
        Step('world.kei', [Blender(ASSETS / 'vehicles' / 'kei' / 'build.py')],
             inputs=[ASSETS / 'vehicles' / 'kei', REGIONS / 'village' / 'build.py'],
             outputs=[out / 'kei' / 'manifest.json'], about='the four kei cars in the Mega Park car park'),
        Step('world.map', [Python(WORLD / 'map' / 'build_map.py')],
             inputs=[WORLD / 'map', REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'gate.py'],
             needs=['world.layout', 'world.hidamari', 'world.skatepark', 'world.zeppelin'],
             outputs=[out / 'map' / 'map.json', out / 'map' / 'map.png'], about='map zones and the painted sheet'),
        Step('world.city_tiles', [Blender(WORLD / 'city_surface_tiles.py', ('--tag', 'v1_128m'))],
             inputs=[WORLD / 'city_surface_tiles.py'], needs=['world.hidamari'],
             outputs=[out / 'city_surface_tiles' / 'v1_128m' / 'manifest.json'], about='desktop profile: city surfaces in 128 m tiles'),
        Step('world.city_trees', [Blender(WORLD / 'city_tree_lods.py', ('--tag', 'v4'))],
             inputs=[WORLD / 'city_tree_lods.py', REGIONS / 'hidamari' / 'arcade.py', REGIONS / 'hidamari' / 'plaza.py'],
             needs=['world.hidamari'], outputs=[out / 'city_tree_lods' / 'v4' / 'manifest.json'], about='desktop profile: city tree LODs'),
        # ------------------------------------------------------------ characters
        Step('characters.cairo', [
                Blender(cairo, ('--sword', '--clips', ','.join(locomotion)), threads=4),
                Blender(cairo, ('--clips', ','.join(combat), '--clips-only', '--sword', '--report', 'export-sword.json'), threads=4),
                Blender(cairo, ('--clips', ','.join(armed), '--clips-only', '--report', 'export-armed.json'), threads=4)],
             inputs=[CHARS / 'cairo', NAMES], outputs=[out / 'cairo' / 'export.json'],
             about='the player: mesh, locomotion/action clips and the bokken to FBX (full + sword and armed records)'),
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
        Step('skate.runtime', [Python(TOOLS / 'verify_skate_native.py',
                                     ('--output', out / 'skate-native/verification.json'))],
             inputs=[TOOLS / 'verify_skate_native.py', ASSETS / 'skate/runtime.json',
                     paths.content_data(ctx.game) / 'SkateNative'],
             outputs=[out / 'skate-native/verification.json'],
             about='verify committed native skating data for the in-process C++ backend'),
        Step('unreal.compile', [UnrealCompile('YorimichiEditor')], inputs=[SOURCE, ctx.uproject, paths.ENGINE_PLUGINS], needs=['skate.runtime'], heavy=True,
             about='the Yorimichi C++ module (editor target)'),
        Step('unreal.world', [UnrealScript(SCRIPTS / 'setup_project.py', 'level saved')],
             inputs=[SCRIPTS / n for n in ('setup_project.py', 'painterly_kernel.py', 'foliage_material.py', 'import_foliage_lods.py',
                                          'import_wanderer.py', 'cape_boy_material.py', 'animation_compression.py', 'import_village.py',
                                          'import_hidamari.py', 'import_southwest.py', 'arcade_material.py', 'plaza_material.py',
                                          'harbor_material.py', 'sea_look.py', 'mountain_material.py', 'import_sailboat.py', 'sailboat_material.py',
                                          'import_zeppelin.py')],
             after=['unreal.compile'], needs=['world.textures', 'world.layout', 'world.props', 'world.foliage_lods', 'world.hidamari',
                    'world.zeppelin', 'world.terrain', 'world.village', 'world.sailboat', 'characters.wanderer'],
             heavy=True, about='world assets, materials, the villager and the level (/Game/Japan)'),
        # The regions below layer onto the world (the south-west import replaces the terrain's and the sea's materials),
        # so they rerun when it is reimported.
        Step('unreal.southwest', [UnrealScript(SCRIPTS / 'import_southwest.py', 'SOUTHWEST IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_southwest.py', SCRIPTS / 'sea_look.py'], needs=['unreal.world', 'world.southwest', 'world.terrain'], heavy=True,
             about='south-west props, the terrain and the sea'),
        Step('unreal.mega', [UnrealScript(SCRIPTS / 'import_mega.py', 'MEGA IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_mega.py'], needs=['unreal.world', 'world.mega'], heavy=True, about='the mini-mega ramp'),
        Step('unreal.megapark', [UnrealScript(SCRIPTS / 'import_megapark.py', 'MEGAPARK IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / 'import_megapark.py'], needs=['unreal.compile', 'world.megapark', 'world.megapark_restyle'],
             outputs=[GAME / 'unreal' / 'Content' / 'MegaPark' / 'Maps' / 'SuperUltraMegaPark.umap'],
             heavy=True, about='editable standalone Super Ultra Mega Park level (/Game/MegaPark)'),
        Step('unreal.houses', [UnrealScript(SCRIPTS / 'import_houses.py', 'HOUSES IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_houses.py'], needs=['unreal.world', 'world.houses'], heavy=True,
             about='the houses on the main road and their lots'),
        Step('unreal.kei', [UnrealScript(SCRIPTS / 'import_kei.py', 'KEI IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_kei.py'], needs=['unreal.world', 'world.kei'], heavy=True,
             about='the kei cars the Mega Park parks in its car park (/Game/Japan/Assets)'),
        Step('unreal.lake', [UnrealScript(SCRIPTS / 'import_forest_lake.py', 'LAKE IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_forest_lake.py', SCRIPTS / 'forest_lake_material.py'], needs=['unreal.world', 'world.lake'],
             heavy=True, about='the woodland lake and cabin'),
        Step('unreal.treehouse', [UnrealScript(SCRIPTS / 'import_treehouse.py', 'TREEHOUSE IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_treehouse.py', SCRIPTS / 'see_through.py'],
             needs=['unreal.world', 'world.treehouse', 'world.treehouse_trees', 'world.treehouse_props', 'world.treehouse_textures'],
             heavy=True, about='the tree house meshes, textures, props and canopy trees'),
        Step('unreal.skatepark', [UnrealScript(SCRIPTS / 'import_skatepark.py', 'SKATEPARK IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_skatepark.py', REGIONS / 'skatepark' / 'park.json'], needs=['unreal.world', 'world.skatepark'],
             heavy=True, about='the skate pier and the board (/Game/SkatePark)'),
        Step('unreal.sounds', [
                UnrealScript(SCRIPTS / 'import_footsteps.py', 'FOOTSTEP IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_combat_audio.py', 'COMBAT AUDIO IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_skate_audio.py', 'SKATE AUDIO IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_footsteps.py', SCRIPTS / 'import_combat_audio.py', SCRIPTS / 'import_skate_audio.py'],
             # The footstep library lives in /Game/Japan, which the world import clears, so a world import reruns this.
             needs=['unreal.world', 'audio.footsteps', 'audio.combat', 'audio.skate'], heavy=True, about='footstep library, combat and skate sounds'),
        Step('unreal.fx', [UnrealScript(SCRIPTS / 'import_combat_fx.py', 'COMBAT FX IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_combat_fx.py'], after=['unreal.compile'], needs=['fx.textures'], heavy=True, about='/Game/FX materials'),
        Step('unreal.fox_hunter', [UnrealScript(SCRIPTS / 'import_fox_hunter.py', 'FOX HUNTER IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_fox_hunter.py', SCRIPTS / 'animation_compression.py'],
             after=['unreal.world'], needs=['characters.fox_hunter'], heavy=True, about='/Game/FoxHunter'),
        Step('unreal.cairo', [
                UnrealScript(SCRIPTS / 'import_cairo.py', 'CAIRO IMPORT COMPLETE', null_rhi=True),
                UnrealScript(SCRIPTS / 'import_cairo_sword.py', 'CAIRO SWORD IMPORT COMPLETE', null_rhi=True),
                UnrealScript(SCRIPTS / 'import_cairo_armed.py', 'CAIRO ARMED IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / n for n in ('import_cairo.py', 'verify_cairo.py', 'import_cairo_sword.py',
                                          'import_cairo_armed.py', 'animation_compression.py')],
             after=['unreal.world'], needs=['characters.cairo'], heavy=True, about='/Game/Cairo in three layers'),
        # The camera see-through (docs/CAMERA.md) patches materials the world and Cairo imports make, so it reruns after
        # either; the tree house builds its own with it (unreal.treehouse).
        Step('unreal.see_through', [UnrealScript(SCRIPTS / 'see_through.py', 'SEE-THROUGH COMPLETE')],
             inputs=[SCRIPTS / 'see_through.py'], needs=['unreal.world', 'unreal.cairo'], heavy=True,
             about='camera see-through on leaves, grass, trunks, the guardrail, poles, torii and Cairo (/Game/SeeThrough)'),
        Step('unreal.desktop', [
                UnrealScript(SCRIPTS / 'import_city_surface_tiles.py', 'CITY SURFACE TILE IMPORT COMPLETE', env=(('CITY_SURFACE_TILES_TAG', 'v1_128m'),)),
                UnrealScript(SCRIPTS / 'import_city_tree_lods.py', 'CITY TREE LODS IMPORT COMPLETE', env=(('CITY_TREE_LODS_TAG', 'v4'),))],
             inputs=[SCRIPTS / 'import_city_surface_tiles.py', SCRIPTS / 'import_city_tree_lods.py', SCRIPTS / 'experiment_mesh_import.py'],
             after=['unreal.world'], needs=['world.city_tiles', 'world.city_trees'], heavy=True,
             about='desktop profile: city tiles and tree LODs (/Game/Experiments)'),
        Step('data.stage', [Call('stage_data', stage_data)],
             inputs=[REGIONS / 'skatepark' / 'park.json'],
             needs=['world.layout', 'world.hidamari', 'world.map', 'world.city_tiles', 'world.treehouse', 'world.megapark'],
             outputs=[GAME / 'unreal' / 'Content' / 'Data' / rel for rel in STAGED], about='runtime files into unreal/Content/Data'),
    ] + botw_steps(out)
