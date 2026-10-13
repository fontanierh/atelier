"""How Yorimichi is built from this repository: `atelier build yorimichi [step ...]`.

Order: world exports (Python and Blender) -> characters -> sounds and effect textures -> the Unreal module ->
the Unreal imports -> runtime data staged into unreal/Content/Data. The small factories below preserve that order;
optional character and region steps are appended when their source is available. Packaging is explicit, with a
certified cook and independently stamped download assembly. Generated outputs go to build/yorimichi (or
$ATELIER_BUILD_ROOT/yorimichi) and to the ignored unreal/Content. `atelier build yorimichi --list` prints the steps.

The Unreal imports run in the order the prototype established: `setup_project.py` rebuilds everything under
/Game/Japan (textures, props, terrain, foliage, the villager, Momiji Hamlet, Hidamari, the sailboat, the zeppelin and
the level), so every later import that writes under /Game/Japan, or uses its animation compression settings, reruns
after it. Cairo's base import supplies his body and the nine authored clips used by the merged move set.
"""
import importlib.util, json, os, tomllib
from dataclasses import dataclass
from pathlib import Path

from atelier.build import Step, Python, Blender, UnrealScript, UnrealCompile, UnrealPackage, Call
from atelier import paths, unreal_modules

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
ASSETS = GAME / 'assets'
CHARS = ASSETS / 'characters'
GRIPS = CHARS / 'grips'
AUDIO = ASSETS / 'audio'
SCRIPTS = GAME / 'unreal' / 'Scripts'
TOOLS = GAME / 'tools'
SKATE_RIDE = SCRIPTS / 'skate_ride'
SKATE_TOOLS = paths.ENGINE_PLUGINS / 'Activities/Skate/Tools'
SKATE_DATA = paths.ENGINE_PLUGINS / 'Activities/Skate/Data'
RIDE_IMPORT_BATCHES, RIDE_VERIFY_BATCHES = 4, 2   # editor runs of the clip import and its verification
TREEHOUSE = REGIONS / 'treehouse'
SOURCE = GAME / 'unreal' / 'Source'
# The compiled modules imports use (atelier.unreal_modules): the import tools (Source/YorimichiImport) and the types
# imports save in assets (Source/YorimichiAssets). Gameplay edits leave the imports current.
IMPORT_CODE = ('YorimichiImport',)
SAVED_TYPES = ('YorimichiAssets',)
# Nox captures USkinMorphContactData on its mesh; its helper and saved type live in this plugin.
CONTACT_TYPES = ('AtelierCore',)
NAMES = paths.STUDIO / 'atelier' / 'character'
# The shared rig and body export every humanoid character's steps run (assets/characters/pipeline).
PIPELINE = CHARS / 'pipeline'
FIT = CHARS / 'fit'   # the fit gate's reviewed baselines, one per character (pipeline/fit.py)
_definition = importlib.util.spec_from_file_location('character_definition', PIPELINE / 'definition.py')
definition = importlib.util.module_from_spec(_definition)
_definition.loader.exec_module(definition)
YORI = WORLD / 'yori.py'
SOUTHWEST_MODELS = ('stand,fisher_house_a,fisher_house_b,boat_shed,stairs,dock,boat,drying_rack,temple,island,'
                    'boulder_a,boulder_b,boulder_c,stone_wall,pine_lean_a,pine_lean_b')


# Keep the recipe's helpers available while the staging implementation has its own narrow input.
_spec = importlib.util.spec_from_file_location('yorimichi_runtime_data', GAME / 'runtime_data.py')
runtime_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime_data)
STAGED = runtime_data.STAGED
staged = runtime_data.staged
staged_source = runtime_data.staged_source
stage_data = runtime_data.stage_data


@dataclass
class PackageArchive(Python):
    """The download folder, zip, split and checksums: a guarded job of its own after UAT releases its turn, with its
    ditto and split children guarded too."""
    marker: str = 'PACKAGE ARCHIVE COMPLETE'
    timeout: float = 3 * 3600
    watch: tuple = ('ditto', 'split')
    progress: float = 25.


def skate_data_present(out):
    """The runtime asset and every referenced generated bank must exist, not just the previous verification report."""
    try:
        report = json.loads((out / 'skate-data' / 'verify.json').read_text())
        content = GAME / 'unreal' / 'Content'
        return (report['exact'] and report['negative_control'] and report['runtime_exact']
                and report['runtime_negative_control'] and bool(report['banks']) and all(
                    (content / (path.removeprefix('/Game/').split('.')[0] + '.uasset')).is_file()
                    for path in [*report['banks'], report['runtime_asset']]))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def city_tree_cpu_access_present(ctx):
    """A same-input world reimport can overwrite these flags without changing its fingerprint: verify the overlay."""
    import hashlib
    try:
        report = json.loads((ctx.out / 'city_tree_lods' / 'production-cpu-access.json').read_text())
        root = ctx.uproject.parent / 'Content' / 'Japan' / 'Assets'
        names = ('HD_ArcadeTree', 'HD_PlazaTreeGold', 'HD_PlazaTreeOrange')
        return all(report[name]['allow_cpu_access'] is True and
                   hashlib.sha256((root / (name + '.uasset')).read_bytes()).hexdigest() == report[name]['sha256']
                   for name in names)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def package_present(out):
    """The zip or every part the manifest lists, at its recorded size: names vary with the revision and the split."""
    root = out / 'package'
    try:
        manifest = json.loads((root / 'manifest.json').read_text())
        return bool(manifest['files']) and all((root / e['file']).stat().st_size == e['bytes'] for e in manifest['files'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


# The cook and download have independent implementation inputs and success stamps.
_cook_spec = importlib.util.spec_from_file_location('yorimichi_package_cook', TOOLS / 'package_cook.py')
package_cook = importlib.util.module_from_spec(_cook_spec)
_cook_spec.loader.exec_module(package_cook)


def engine_version(ctx):
    """The installed engine's version files: saved packages and cooked output depend on the engine build."""
    engine = getattr(ctx, 'unreal_root', None)
    return [engine / 'Engine' / 'Build' / 'Build.version',
            engine / 'Engine' / 'Binaries' / 'Mac' / 'UnrealEditor.modules'] if engine else []


def cook_step(ctx, steps):
    out = ctx.out
    engine_inputs = engine_version(ctx)
    return Step('unreal.cook',
                [Call('prepare_cook', package_cook.prepare), UnrealPackage('Yorimichi', out / 'package' / 'archive'),
                 Call('certify_cook', package_cook.finish)],
                inputs=[SOURCE, ctx.uproject, paths.ENGINE_PLUGINS, GAME / 'unreal' / 'Config', TOOLS / 'package_cook.py', *engine_inputs],
                needs=[s.name for s in steps if s.name.startswith('unreal.')] + ['data.stage', 'data.network'], heavy=True, explicit=True,
                outputs=[out / 'package' / 'cook.json'], verify=lambda: package_cook.cook_present(out / 'package'),
                about='cook the macOS app once and certify its source and immutable archived files')


def package_step(ctx, steps):
    """The public entry point: independently guarded download assembly from a certified cook."""
    out = ctx.out
    return Step('unreal.package',
                [PackageArchive(TOOLS / 'package_archive.py', ('--out', out / 'package', '--cook-receipt'))],
                inputs=[TOOLS / 'package_archive.py', TOOLS / 'desktop_preview.py'],
                needs=['unreal.cook'], heavy=True, explicit=True,
                outputs=[out / 'package' / 'manifest.json', out / 'package' / 'SHA256SUMS'],
                verify=lambda: package_present(out),
                about='packaged macOS game (.app, Development): zipped, checksummed in build/<game>/package')


def adventure_library():
    """assets/characters/adventure/library.py: whether the local adventure library is here, and the files the roster reads."""
    spec = importlib.util.spec_from_file_location('adventure_library', CHARS / 'adventure' / 'library.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def moveset_import(character):
    """Scripts/import_adventure_moveset.py for one character (its adventure.toml), and its inputs: every character's adventure.toml, for
    its own layout and fit and the donor's clips."""
    done = f'{character.upper().replace("-", " ")} ADVENTURE IMPORT COMPLETE'
    script = UnrealScript(SCRIPTS / 'import_adventure_moveset.py', done, null_rhi=True, env=(('ADVENTURE_CHARACTER', character),))
    return script, [SCRIPTS / 'import_adventure_moveset.py', SCRIPTS / 'animation_compression.py', *sorted(CHARS.glob('*/adventure.toml'))]


def body_export(character, *args, threads=4):
    """assets/characters/pipeline/export.py for one character: its body, textures and own clips, to FBX."""
    return Blender(PIPELINE / 'export.py', ('--character', character, *args), threads=threads)


def body_import(character, modules=()):
    """unreal/Scripts/import_character.py for one character (its body, materials, own clips and base definition), and
    its inputs."""
    script = SCRIPTS / 'import_character.py'
    return (UnrealScript(script, f'CHARACTER IMPORT COMPLETE: {character}', null_rhi=True, env=(('CHARACTER', character),),
                         modules=modules),
            [script, SCRIPTS / 'animation_compression.py', SCRIPTS / 'skin_morph_contacts.py', PIPELINE / 'definition.py',
             CHARS / character / 'character.toml'])


def moveset_retarget(character, *args):
    """assets/characters/adventure/retarget.py onto one character, and its inputs."""
    retarget = CHARS / 'adventure' / 'retarget.py'
    return Blender(retarget, ('--character', character, *args), threads=3), [CHARS / character, retarget,
            retarget.parent / 'stance.py', *sorted(CHARS.glob('*/adventure.toml')), NAMES, PIPELINE]


def key(character):
    """A character's step names: characters.<key>, unreal.<key>_bike..."""
    return character.id.replace('-', '_')


def content(character):
    """Its Unreal folder on disk."""
    return GAME / 'unreal' / 'Content' / character.unreal_path.removeprefix('/Game/')


def mover_export_steps(character, out):
    """Its body (pipeline/export.py) and, if playable, its bike clips (vehicles/bike/rider.py), to FBX."""
    k, threads = key(character), character.blender['threads']
    steps = [Step(f'characters.{k}', [body_export(character.id, threads=threads)], inputs=[character.folder, NAMES, PIPELINE],
                  outputs=[out / character.output / 'export.json'], heavy=True,
                  about=f"{character.name}'s body, textures and own clips, to FBX")]
    if character.playable:
        steps.append(Step(f'characters.{k}_bike', [Blender(ASSETS / 'vehicles' / 'bike' / 'rider.py', ('--character', character.id), threads=threads)],
                          inputs=[character.folder, NAMES, PIPELINE, ASSETS / 'vehicles' / 'bike'], needs=['world.bike'],
                          outputs=[out / character.output / 'bike' / 'export.json'], heavy=True,
                          about=f"Every bike action authored on {character.name}'s rig, and the bike's channels"))
    return steps


def mover_grips_step(character):
    """Its posed grips (assets/characters/grips/<id>, docs/GRIPS.md) for the move set's grip node, when committed."""
    source = GRIPS / character.id
    return [Step(f'characters.{key(character)}_grips', [Python(GRIPS / 'game.py', ('--character', character.id, '--source', source))],
                 inputs=[GRIPS / 'game.py', GRIPS / 'moments.py', *(source / f for f in ('poses.json', 'moments.json', 'body.glb'))],
                 outputs=[GAME / 'unreal' / 'Content' / 'Data' / character.id / 'grips.json'],
                 about=f"{character.name}'s posed grips, for the move set's grip node")] if source.is_dir() else []


def mover_import_steps(character):
    """Its body (Scripts/import_character.py) and, if playable, its bike clips (Scripts/import_bike_clips.py)."""
    k, modules = key(character), tuple(character.unreal['modules'])
    body, inputs = body_import(character.id, modules)
    steps = [Step(f'unreal.{k}', [body], inputs=inputs, after=['unreal.world'], needs=[f'characters.{k}', *unreal_modules.needs(modules)],
                  outputs=[content(character) / f'SK_{character.name}.uasset'], heavy=True,
                  about=f'{character.unreal_path}: its mesh, materials, own clips and base definition')]
    if character.playable:
        steps.append(Step(f'unreal.{k}_bike', [UnrealScript(SCRIPTS / 'import_bike_clips.py', f'{character.id.upper()} BIKE IMPORT COMPLETE',
                                                            null_rhi=True, env=(('BIKE_CHARACTER', character.id),))],
                          inputs=[SCRIPTS / 'import_bike_clips.py', SCRIPTS / 'animation_compression.py', PIPELINE / 'definition.py', character.folder / 'character.toml'],
                          needs=[f'characters.{k}_bike', f'unreal.{k}'], heavy=True,
                          about=f'{character.unreal_path}Bike: its bike clips on SK_{character.name}'))
    return steps


def mover_adventure_steps(character, out):
    """The merged move set retargeted onto it (adventure/retarget.py; the donor also samples its own clips for the
    others) and imported (Scripts/import_adventure_moveset.py)."""
    k = key(character)
    (retarget, retarget_inputs), (importer, import_inputs) = moveset_retarget(character.id), moveset_import(character.id)
    donor = definition.movers()[0]
    if character.donor:
        commands, needs = [retarget, moveset_retarget(character.id, '--dump-own')[0]], ['characters.adventure']
        outputs = [out / character.output / 'adventure' / 'export.json', out / character.output / 'adventure' / 'own.npz']
    else:
        commands, needs = [retarget], ['characters.adventure', f'characters.{key(donor)}_adventure']
        outputs = [out / character.output / 'adventure' / 'export.json']
    return [
        Step(f'characters.{k}_adventure', commands, inputs=retarget_inputs, needs=needs, outputs=outputs, heavy=True,
             about=f'The merged move set retargeted onto {character.name}, to FBX'),
        Step(f'unreal.{k}_adventure', [importer], inputs=import_inputs, needs=[f'characters.{k}_adventure', f'unreal.{k}', 'unreal.adventure'],
             outputs=[GAME / 'unreal' / 'Content' / 'Data' / character.id / 'adventure.json'], heavy=True,
             about=f"{character.adventure['dest']} and {character.adventure['definition']}: {character.name}'s merged move set, definition and move record"),
    ]


def pawn_steps(steps):
    """Each player's pawn, BP_<Name>, and the readiness record that registers it (Scripts/character_pawn.py), in the
    full editor (the Blueprint's parent is the game's AMoverCharacter). Last of its steps: a character is published
    only once its move set, bike clips, grips and fit gate are all built."""
    names = {s.name for s in steps}
    result = []
    for character in definition.movers():
        if not character.playable:
            continue
        k, script = key(character), SCRIPTS / 'character_pawn.py'
        ready = [n for n in (f'unreal.{k}_adventure', f'unreal.{k}_bike', f'characters.{k}_grips', f'characters.{k}_fit') if n in names]
        result.append(Step(
            f'unreal.{k}_pawn', [UnrealScript(script, f'CHARACTER PAWN COMPLETE: {character.id}', null_rhi=True, env=(('CHARACTER', character.id),))],
            inputs=[script, PIPELINE / 'definition.py', character.folder / 'character.toml'],
            needs=[*ready, 'unreal.compile'],
            outputs=[content(character) / f'BP_{character.name}.uasset', GAME / 'unreal' / 'Content' / 'Data' / character.id / 'character.json'],
            heavy=True,
            about=f'{character.unreal_path}/BP_{character.name}: {character.name} as a playable pawn, registered with the game'))
    return result


def fit_steps(out, steps):
    """Each mover's fit gate (pipeline/fit.py), after the exports that write its reports: adventure and bike."""
    names = {s.name for s in steps}
    result = []
    for character in definition.movers():
        k = key(character)
        exports = [n for n in (f'characters.{k}_adventure', f'characters.{k}_bike') if n in names]
        if exports:
            result.append(Step(f'characters.{k}_fit', [Python(PIPELINE / 'fit.py', ('--character', character.id))],
                               inputs=[PIPELINE / 'fit.py', PIPELINE / 'definition.py', character.folder / 'character.toml',
                                       *FIT.glob(f'{character.id}.json')],
                               needs=exports, outputs=[out / character.output / 'fit.json'],
                               about=f"{character.name}'s exported clips against its fit baseline and bounds"))
    return result


def adventure_steps(out):
    """The committed merged motion reference and every mover's retarget (characters with an adventure.toml): the donor's
    first, which the others take its own clips from."""
    library = adventure_library()
    if not library.available():
        return []
    adventure = CHARS / 'adventure'
    return [
        Step('characters.adventure', [Python(adventure / 'export.py')], inputs=[adventure, *library.sources()],
             outputs=[out / 'adventure' / 'export.json'], about='Merged motion reference and two props'),
        Step('unreal.adventure', [UnrealScript(SCRIPTS / 'import_adventure.py', 'ADVENTURE IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / 'import_adventure.py', SCRIPTS / 'animation_compression.py'], after=['unreal.world'],
             needs=['characters.adventure'], outputs=[GAME / 'unreal' / 'Content' / 'Data' / 'adventure' / 'reference.json'],
             heavy=True, about='/Game/Adventure: motion reference, sword and paraglider'),
        *[step for character in definition.movers() for step in mover_adventure_steps(character, out)],
    ]


def hippodrome_steps(out):
    """The Hidamari Hippodrome (docs/HIPPODROME.md): the racecourse north of the city, built without Blender."""
    region = REGIONS / 'hippodrome'
    return [
        Step('world.hippodrome', [Python(region / 'build.py')],
             inputs=[region, ASSETS / 'hippodrome' / 'props', REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py', REGIONS / 'forest/ecotone.py', REGIONS / 'forest/specs.py'],
             needs=['world.layout'], outputs=[out / 'hippodrome' / 'region' / 'hippodrome.json'],
             about='hippodrome course meshes (platform, skirt, track, rails, lane), its Tripo structures and venue data'),
        Step('unreal.hippodrome', [UnrealScript(SCRIPTS / 'import_hippodrome.py', 'HIPPODROME IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / 'import_hippodrome.py'], needs=['world.hippodrome', 'unreal.world'], heavy=True,
             outputs=[GAME / 'unreal' / 'Content' / 'Data' / 'hippodrome' / 'hippodrome.json'],
             about='/Game/Hippodrome: the course meshes with collision, and the data AHippodrome places them from'),

    ]


def belmonte_steps(out):
    """The current town and countryside library, with island planting and a northern apron."""
    region = REGIONS / 'belmonte'
    return [
        Step('world.belmonte', [Python(region / 'build.py')],
             inputs=[region, WORLD / 'surface_textures.py', ASSETS / 'belmonte', ASSETS / 'environment/textures/tuscan-ground.jpg',
                     ASSETS / 'environment/textures/tuscan-ground.provenance.json', REGIONS / 'megapark/forest.py', REGIONS / 'hippodrome' / 'build.py',
                     REGIONS / 'forest/ecotone.py', REGIONS / 'forest/specs.py',
                     REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py', YORI],
             needs=['world.layout'], outputs=[out / 'belmonte' / 'runtime.json', out / 'belmonte' / 'build-report.json'],
             about='Belmonte environment: committed models, northern terrain join and island flora'),
        # Keep derived-mesh workers out of material sections while the importer edits them.
        Step('unreal.belmonte', [UnrealScript(SCRIPTS / 'import_belmonte.py', 'BELMONTE IMPORT COMPLETE',
                                             null_rhi=True, modules=IMPORT_CODE,
                                             args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',))],
             inputs=[SCRIPTS / 'import_belmonte.py', SCRIPTS / 'atmosphere.py', SCRIPTS / 'ground_grain.py', ASSETS / 'environment/textures/tuscan-ground.jpg'],
             needs=['world.belmonte', 'unreal.forest', 'unreal.world', *unreal_modules.needs(IMPORT_CODE)], heavy=True,
             outputs=[out / 'belmonte' / 'import-report.json', GAME / 'unreal' / 'Content' / 'Belmonte' / 'Meshes' / 'SM_BM_NorthApron.uasset'],
             about='/Game/Belmonte: environment meshes, collision and painterly surfaces'),
    ]


def world_steps(ctx):
    """World exports."""
    out = ctx.out
    return [
        # ------------------------------------------------------------ world
        Step('world.textures', [Python(WORLD / 'gen_textures.py')], inputs=[WORLD / 'gen_textures.py', WORLD / 'surface_textures.py', YORI,
             ASSETS / 'environment/textures/tree-bark.jpg', ASSETS / 'environment/textures/tuscan-ground.jpg',
             ASSETS / 'environment/textures/tuscan-ground.provenance.json'],
             outputs=[out / 'textures' / 'T_sky.png', out / 'textures' / 'T_ground_detail.png'], about='procedural textures (leaves, grass, bark, road, sky)'),
        # The tree house's tall canopy trees come first: its layout sizes them from trees.json.
        Step('world.treehouse_trees', [Blender(TREEHOUSE / 'trees.py', threads=4)], inputs=[TREEHOUSE / 'trees.py', WORLD / 'build_assets.py', WORLD / 'forest_trees.py', REGIONS / 'forest/specs.py'],
             needs=['world.textures'], outputs=[out / 'treehouse' / 'trees' / 'trees.json'],
             about='tree house canopy trees (four autumn crowns) and their recoloured leaf atlases', heavy=True),
        Step('world.layout', [Python(WORLD / 'gen_world.py')],
             inputs=[WORLD / 'gen_world.py', REGIONS / 'forest/ecotone.py', REGIONS / 'forest/specs.py', REGIONS / 'houses' / 'layout.py', WORLD / 'torii_clearance.py', YORI,
                     REGIONS / 'village' / 'layout.py', REGIONS / 'mega' / 'layout.py', REGIONS / 'southwest',
                     REGIONS / 'skatepark' / 'pier_site.py',
                     REGIONS / 'forest_lake' / 'layout.py', REGIONS / 'zeppelin' / 'layout.py', TREEHOUSE / 'layout.py',
                     TREEHOUSE / 'screen.py', REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'forest.py',
                     REGIONS / 'megapark' / 'trail.py', REGIONS / 'megapark' / 'gate.py', REGIONS / 'hidamari' / 'mountains.py',
                     REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari' / 'forest_backdrop.py'],
             needs=['world.treehouse_trees'],
             outputs=[out / 'world.json', out / 'heightmap.npy', out / 'heightmap.bin', out / 'farhills.npy', out / 'treehouse' / 'layout.json',
                      out / 'megapark' / 'trail.json'],
             about='terrain heightfield, road, scatter and every region layout -> world.json'),
        Step('world.forest_textures', [Python(TOOLS / 'forest_textures.py')],
             inputs=[TOOLS / 'forest_textures.py', ASSETS / 'environment/textures'],
             outputs=[out / 'forest/textures/textures.json'], about='Sunburst Mediterranean twig atlases with coverage masks'),
        Step('world.forest', [Blender(WORLD / 'build_forest.py')],
             inputs=[WORLD / 'build_forest.py', WORLD / 'forest_impostors.py', WORLD / 'forest_trees.py', REGIONS / 'forest/specs.py', WORLD / 'build_assets.py'],
             needs=['world.textures', 'world.forest_textures'], heavy=True,
             outputs=[out / 'forest/trees.json'], about='Tuscan branching crowns and authored HISM detail levels'),
        Step('world.props', [Blender(WORLD / 'build_assets.py')], inputs=[WORLD / 'build_assets.py', WORLD / 'forest_trees.py', REGIONS / 'forest/specs.py'], needs=['world.textures'],
             outputs=[out / 'assets' / 'Torii.fbx'], about='trees, bushes, grass, rocks, torii, lanterns, birds, sky dome', heavy=True),
        Step('world.foliage_lods', [Blender(WORLD / 'build_foliage_lods.py')],
             inputs=[WORLD / 'build_foliage_lods.py', WORLD / 'build_assets.py', WORLD / 'forest_trees.py', REGIONS / 'forest/specs.py'], needs=['world.textures'],
             outputs=[out / 'foliage_lods' / 'manifest.json'], about='seeded LOD chains for trees, bushes and grass', heavy=True),
        Step('world.hidamari', [Blender(REGIONS / 'hidamari' / 'build.py')],
             inputs=[REGIONS / 'hidamari', REGIONS / 'village' / 'build.py', REGIONS / 'zeppelin' / 'layout.py',
                     REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'forest.py', REGIONS / 'megapark' / 'trail.py',
                     REGIONS / 'megapark' / 'gate.py', REGIONS / 'forest/ecotone.py', REGIONS / 'forest/specs.py', ASSETS / 'hidamari' / 'props'],
             needs=['world.layout'], outputs=[out / 'hidamari' / 'city.json', out / 'hidamari' / 'manifest.json',
                                             out / 'hidamari' / 'north_snow.png', out / 'hidamari' / 'north_snow.json'],
             about='the city: layout (city.json), building kit, harbor, plaza, arcade, mountains', heavy=True),
        *belmonte_steps(out)[:1],
        Step('world.zeppelin', [Blender(REGIONS / 'zeppelin' / 'build.py', threads=2)],
             inputs=[REGIONS / 'zeppelin', REGIONS / 'village' / 'build.py', REGIONS / 'hidamari' / 'mountains.py',
                     REGIONS / 'megapark' / 'gate.py'],
             needs=['world.layout', 'world.hidamari'],
             outputs=[out / 'zeppelin' / 'manifest.json'], about='airship and its three stations', heavy=True),
        Step('world.hidamari_textures', [Python(TOOLS / 'hidamari_textures.py', ('finish',))],
             inputs=[TOOLS / 'hidamari_textures.py', TOOLS / 'treehouse_textures.py', ASSETS / 'hidamari' / 'textures'],
             outputs=[out / 'hidamari' / 'textures' / 'textures.json'], pool_roots=[out / 'hidamari' / 'textures'],
             about='Hidamari city surfaces: seamless detail maps from the Sunburst paintings'),
        Step('world.hidamari_props', [Blender(REGIONS / 'hidamari' / 'props.py', threads=4)],
             inputs=[REGIONS / 'hidamari' / 'props.py', TREEHOUSE / 'props.py', TOOLS / 'hidamari_props.py',
                     ASSETS / 'hidamari' / 'props'],
             outputs=[out / 'hidamari' / 'props' / 'props.json'], about='the Hidamari Tripo street props fitted to their sizes', heavy=True),
        Step('world.treehouse_textures', [Python(TOOLS / 'treehouse_textures.py', ('finish',))],
             inputs=[TOOLS / 'treehouse_textures.py', ASSETS / 'treehouse' / 'textures'],
             outputs=[out / 'treehouse' / 'textures' / 'textures.json'], pool_roots=[out / 'treehouse' / 'textures'],
             about='tree house textures: seamless detail maps and pictures from the Sunburst paintings'),
        Step('world.treehouse_props', [Blender(TREEHOUSE / 'props.py', threads=4)],
             inputs=[TREEHOUSE / 'props.py', TOOLS / 'treehouse_props.py', ASSETS / 'treehouse' / 'props'],
             outputs=[out / 'treehouse' / 'props' / 'props.json'], about='the 13 Tripo props fitted to their sizes', heavy=True),
        Step('world.treehouse', [Blender(TREEHOUSE / 'build.py', threads=4)],
             inputs=[TREEHOUSE / 'build.py', TREEHOUSE / 'tmesh.py', TREEHOUSE / 'layout.py', REGIONS / 'village' / 'build.py'],
             needs=['world.layout'], outputs=[out / 'treehouse' / 'manifest.json', out / 'treehouse' / 'runtime.json'],
             about='the tree house: ten places, bridges, rooms and their dressing, lights, sunbeams', heavy=True),
        Step('world.terrain', [Blender(WORLD / 'build_terrain.py')],
             inputs=[WORLD / 'build_terrain.py', REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py',
                     *(REGIONS / 'belmonte' / name for name in ('terrain.py', 'source.py', 'layout.py')),
                     *(ASSETS / 'belmonte' / entry['path'] for entry in json.loads((ASSETS / 'belmonte/source.json').read_text())['meshes']
                       if entry['name'].startswith('SM_BM_BT_Terrain_')),
                     REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'trail.py', REGIONS / 'megapark' / 'gate.py'],
             needs=['world.layout', 'world.hidamari', 'world.textures'],
             outputs=[out / 'terrain.fbx', out / 'assets' / 'Sea.fbx'], about='terrain, road, wires, far hills, sea', heavy=True),
        Step('world.village', [Blender(REGIONS / 'village' / 'build.py')], inputs=[REGIONS / 'village'], needs=['world.layout'],
             outputs=[out / 'village' / 'manifest.json'], about='Momiji Hamlet', heavy=True),
        Step('world.houses', [Blender(REGIONS / 'houses' / 'build.py')], inputs=[REGIONS / 'houses', REGIONS / 'village' / 'build.py'],
             needs=['world.layout'], outputs=[out / 'houses' / 'manifest.json'],
             about='the five houses on the main road: three house models and their lots (terrace, hedge, gate, ishigaki)', heavy=True),
        Step('world.southwest', [Blender(REGIONS / 'southwest' / 'build.py', ('--models', SOUTHWEST_MODELS, '--export', '--no-render'))],
             inputs=[REGIONS / 'southwest', REGIONS / 'village' / 'build.py'], needs=['world.layout'],
             outputs=[out / 'southwest' / 'fbx' / 'SW_Temple.fbx'], about='fishing village, cove, island temple', heavy=True),
        Step('world.mega', [Blender(REGIONS / 'mega' / 'build.py')], inputs=[REGIONS / 'mega', REGIONS / 'village' / 'build.py'],
             needs=['world.layout'], outputs=[out / 'mega' / 'manifest.json'], about='the mini-mega ramp and its trail', heavy=True),
        Step('world.megapark_restyle', [Python(TOOLS / 'megapark_textures.py', ('finish',))],
             inputs=[TOOLS / 'megapark_textures.py', ASSETS / 'megapark' / 'restyle', ASSETS / 'megapark' / 'map.json',
                     REGIONS / 'megapark' / 'sign.py', REGIONS / 'hidamari' / 'fonts' / 'NotoSansJP.ttf'],
             outputs=[out / 'megapark' / 'textures' / 'textures.json', out / 'megapark' / 'lettering' / 'NotoSansJP-Black.ttf'],
             about='Mega Park restyle: island-style rock, earth, paint and signs, lightmap levels, the 寄り道 font'),
        Step('world.megapark', [Blender(REGIONS / 'megapark' / 'build.py', threads=4)],
             inputs=[REGIONS / 'megapark' / 'build.py', REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'plants.py',
                     REGIONS / 'megapark' / 'sign.py', REGIONS / 'megapark' / 'cars.py', ASSETS / 'megapark', YORI], needs=['world.megapark_restyle'],
             outputs=[out / 'megapark' / 'build.json', out / 'megapark' / 'park.json', out / 'megapark' / 'fbx' / 'SM_MP_ImportSeed.fbx'],
             about='original Super Ultra Mega Park geometry, riding collision and grind curves -> FBX', heavy=True),
        Step('world.lake', [Blender(REGIONS / 'forest_lake' / 'build.py')], inputs=[REGIONS / 'forest_lake', REGIONS / 'village' / 'build.py'],
             needs=['world.layout'], outputs=[out / 'forest_lake' / 'manifest.json'], about='the woodland lake and cabin', heavy=True),
        Step('world.skatepark_textures', [Python(TOOLS / 'pier_textures.py', ('finish',))],
             inputs=[TOOLS / 'pier_textures.py', ASSETS / 'skatepark' / 'textures', ASSETS / 'megapark' / 'restyle' / 'stone_cut.jpg'],
             outputs=[out / 'skatepark' / 'textures' / 'textures.json'], about='Sunburst pier material maps (offline; no paid calls)'),
        Step('world.skatepark', [Blender(REGIONS / 'skatepark' / 'build.py')],
             inputs=[*sorted((REGIONS / 'skatepark').glob('*.py')), ASSETS / 'skatepark' / 'modules.json',
                     ASSETS / 'skatepark' / 'modules'],
             needs=['world.layout', 'world.skatepark_textures'],
             outputs=[out / 'skatepark' / 'build-report.json'], heavy=True, about='the skate pier, its rails and the trick board (park.json)'),
        Step('world.sailboat', [Blender(ASSETS / 'vehicles' / 'sailboat' / 'build.py', threads=4)],
             inputs=[ASSETS / 'vehicles' / 'sailboat', REGIONS / 'village' / 'build.py'],
             outputs=[out / 'sailboat' / 'manifest.json'], about='the dinghy', heavy=True),
        Step('world.bike', [Blender(ASSETS / 'vehicles' / 'bike' / 'build.py')],
             inputs=[ASSETS / 'vehicles' / 'bike' / 'build.py', YORI],
             outputs=[out / 'bike' / 'manifest.json'], about="Cairo's bike: frame, steering, wheels, crank, pedals, kickstand, rack board", heavy=True),
        Step('world.kei', [Blender(ASSETS / 'vehicles' / 'kei' / 'build.py')],
             inputs=[ASSETS / 'vehicles' / 'kei', REGIONS / 'village' / 'build.py'],
             outputs=[out / 'kei' / 'manifest.json'], about='the four kei cars in the Mega Park car park', heavy=True),
        Step('world.map', [Python(WORLD / 'map' / 'build_map.py')],
             inputs=[WORLD / 'map', REGIONS / 'mega' / 'ramp.py', REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'gate.py',
                     *[REGIONS / 'belmonte' / (name + '.py') for name in ('plan', 'planting', 'source', 'layout')],
                     ASSETS / 'belmonte' / 'source.json',
                     *(ASSETS / 'belmonte' / entry['path']
                       for entry in json.loads((ASSETS / 'belmonte' / 'source.json').read_text())['meshes']
                       if entry['name'].startswith(('SM_BM_BT_blk_', 'SM_BM_BH_', 'SM_BM_BE_', 'SM_BM_BHip_',
                                                    'SM_BM_BVV_Farm_', 'SM_BM_BC_Water_', 'SM_BM_BC_Pave', 'SM_BM_BC_Ponte')))],
             needs=['world.layout', 'world.hidamari', 'world.skatepark', 'world.zeppelin', 'world.belmonte'],
             outputs=[out / 'map' / 'map.json', out / 'map' / 'map.png'], about='map zones and the painted sheet'),
        Step('world.city_tiles', [Blender(WORLD / 'city_surface_tiles.py', ('--tag', 'v1_128m'))],
             inputs=[WORLD / 'city_surface_tiles.py'], needs=['world.hidamari'],
             outputs=[out / 'city_surface_tiles' / 'v1_128m' / 'manifest.json'], about='desktop profile: city surfaces in 128 m tiles', heavy=True),
        Step('world.city_trees', [Blender(WORLD / 'city_tree_lods.py', ('--tag', 'v4'))],
             inputs=[WORLD / 'city_tree_lods.py', REGIONS / 'hidamari' / 'arcade.py', REGIONS / 'hidamari' / 'plaza.py'],
             needs=['world.hidamari'], outputs=[out / 'city_tree_lods' / 'v4' / 'manifest.json'], about='desktop profile: city tree LODs', heavy=True),
    ]


def character_steps(ctx):
    """Character bodies, merged-set donor clips and villagers."""
    out = ctx.out
    return [
        # ------------------------------------------------------------ characters
        # Every mover's body and bike clips, then its committed grips: before data.stage, which stages the bike reports
        # and grips so the cook carries them. They need its rig and the bike, not the adventure library.
        *[step for character in definition.movers() for step in mover_export_steps(character, out)],
        *[step for character in definition.movers() for step in mover_grips_step(character)],
        Step('characters.fox_hunter', [Blender(CHARS / 'fox-hunter' / 'export_unreal.py', threads=4)],
             inputs=[CHARS / 'fox-hunter', NAMES], outputs=[out / 'fox_hunter' / 'export.json'], about='the fox hunter: mesh and 15 clips', heavy=True),
        Step('characters.wanderer', [Blender(CHARS / 'wanderer' / 'build.py', ('--animations', '--export', '--no-render'), threads=4)],
             inputs=[CHARS / 'wanderer'], outputs=[out / 'wanderer' / 'build.json'], about='the villagers (procedural model and clips)', heavy=True),
    ]


def sound_effect_steps(ctx):
    """Offline sound slices and procedural effect textures."""
    out = ctx.out
    return [
        # ------------------------------------------------------------ sounds and effects
        Step('audio.footsteps', [Python(AUDIO / 'footsteps' / 'slice.py')], inputs=[AUDIO / 'footsteps', paths.cache_dir('sonniss', 'footsteps')],
             outputs=[out / 'audio' / 'footsteps' / 'manifest.json'], about='531 footstep one-shots (needs `atelier fetch`)'),
        Step('audio.combat', [Python(AUDIO / 'combat' / 'slice.py')], inputs=[AUDIO / 'combat', paths.cache_dir('sonniss', 'combat')],
             outputs=[out / 'audio' / 'combat' / 'manifest.json'], about='combat cues and the countryside ambience'),
        Step('audio.skate', [Python(AUDIO / 'skate' / 'make.py')], inputs=[AUDIO / 'skate', paths.cache_dir('sonniss', 'combat')],
             outputs=[out / 'audio' / 'skate' / 'manifest.json'], about='board loops and cues'),
        Step('audio.bike', [Python(AUDIO / 'bike' / 'make.py')], inputs=[AUDIO / 'bike', AUDIO / 'skate' / 'make.py', paths.cache_dir('sonniss', 'combat')],
             outputs=[out / 'audio' / 'bike' / 'manifest.json'], about="the bike's tyres, freewheel, chain, wind, bell and knocks"),
        Step('fx.textures', [Python(ASSETS / 'fx' / 'gen_textures.py')], inputs=[ASSETS / 'fx'],
             outputs=[out / 'combat_fx' / 'T_FX_Glow.png'], about='glow, spark, ring, dust and trail sprites'),
    ]


def unreal_steps(ctx):
    """Native checks, editor compilation and ordered content imports."""
    out = ctx.out
    return [
        # ------------------------------------------------------------ Unreal
        # Imports run `after` the compile (the editor must load the module) but do not rerun when C++ changes, except
        # those that declare the modules they use (IMPORT_CODE, SAVED_TYPES); the later imports run after the world
        # (materials and folders it creates) without rerunning when it is reimported.
        # The Skate plugin's simulation package: the runtime payloads, rig, clips and metadata banks built from its runtime
        # and motion text, every payload checked against its manifest. The game reads them from typed assets
        # (unreal.skate_data); tools read the package.
        Step('skate.runtime', [Python(SKATE_TOOLS / 'simulation_package.py',
                                     ('--assemble', out / 'skate-simulation/package',
                                      '--output', out / 'skate-simulation/verification.json'))],
             inputs=[SKATE_TOOLS / 'simulation_package.py', SKATE_TOOLS / 'motion_text.py', SKATE_TOOLS / 'runtime_text.py',
                     SKATE_DATA],
             outputs=[out / 'skate-simulation/verification.json', out / 'skate-simulation/package' / 'package-manifest.json'],
             about="assemble the Skate plugin's simulation package and verify every payload"),
        Step('unreal.compile', [UnrealCompile('YorimichiEditor')], inputs=[SOURCE, ctx.uproject, GAME / 'unreal/Config', paths.ENGINE_PLUGINS], needs=['skate.runtime'], heavy=True,
             about='the Yorimichi C++ modules (editor target)'),
        *unreal_modules.steps(ctx, IMPORT_CODE + SAVED_TYPES + CONTACT_TYPES),
        Step('unreal.world', [UnrealScript(SCRIPTS / 'setup_project.py', 'level saved')],
             inputs=[ASSETS / 'environment/textures/volcanic-rock.jpg', out / 'hidamari' / 'north_snow.png', out / 'hidamari' / 'north_snow.json',
                     *[SCRIPTS / n for n in ('setup_project.py', 'painterly_kernel.py', 'foliage_material.py', 'import_foliage_lods.py',
                                          'import_wanderer.py', 'cape_boy_material.py', 'animation_compression.py', 'import_village.py',
                                          'import_hidamari.py', 'import_southwest.py', 'arcade_material.py', 'plaza_material.py',
                                          'harbor_material.py', 'sea_look.py', 'mountain_material.py', 'import_sailboat.py', 'sailboat_material.py',
                                          'import_zeppelin.py', 'forest_ground.py', 'ground_grain.py', 'atmosphere.py', 'city_material.py', 'mesh_materials.py')]],
             after=['unreal.compile'], needs=['world.textures', 'world.layout', 'world.props', 'world.foliage_lods', 'world.hidamari', 'world.hidamari_textures', 'world.hidamari_props',
                    'world.zeppelin', 'world.terrain', 'world.village', 'world.sailboat', 'characters.wanderer'],
             heavy=True, about='world assets, materials, the villager and the level (/Game/Japan)'),
        # The regions below layer onto the world (the south-west import replaces the terrain's and the sea's materials),
        # so they rerun when it is reimported.
        Step('unreal.southwest', [UnrealScript(SCRIPTS / 'import_southwest.py', 'SOUTHWEST IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_southwest.py', SCRIPTS / 'sea_look.py'], needs=['unreal.world', 'world.southwest', 'world.terrain'], heavy=True,
             about='south-west props, the terrain and the sea'),
        Step('unreal.mega', [UnrealScript(SCRIPTS / 'import_mega.py', 'MEGA IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_mega.py'], needs=['unreal.world', 'world.mega'], heavy=True, about='the mini-mega ramp'),
        # Do not build distance fields or cards while replacing the seed mesh's material sections: UE 5.8 can read
        # that map concurrently. The final meshes already disable distance fields; normal runtime settings build
        # their cards once the imported meshes and material slots are stable.
        # Audits its meshes with the import tools and places the park's actors, game classes.
        Step('unreal.megapark', [UnrealScript(SCRIPTS / 'import_megapark.py', 'MEGAPARK IMPORT COMPLETE', null_rhi=True,
                                            args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',),
                                            modules=IMPORT_CODE + SAVED_TYPES)],
             inputs=[SCRIPTS / 'import_megapark.py'],
             needs=['world.megapark', 'world.megapark_restyle', *unreal_modules.needs(IMPORT_CODE + SAVED_TYPES)],
             outputs=[GAME / 'unreal' / 'Content' / 'MegaPark' / 'Maps' / 'SuperUltraMegaPark.umap'],
             heavy=True, about='editable standalone Super Ultra Mega Park level (/Game/MegaPark)'),
        Step('unreal.houses', [UnrealScript(SCRIPTS / 'import_houses.py', 'HOUSES IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_houses.py'], needs=['unreal.world', 'world.houses'], heavy=True,
             about='the houses on the main road and their lots'),
        Step('unreal.kei', [UnrealScript(SCRIPTS / 'import_kei.py', 'KEI IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_kei.py'], needs=['unreal.world', 'world.kei'], heavy=True,
             about='the kei cars the Mega Park parks in its car park (/Game/Japan/Assets)'),
        Step('unreal.bike', [UnrealScript(SCRIPTS / 'import_bike.py', 'BIKE IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_bike.py', SCRIPTS / 'bike_material.py'], needs=['unreal.world', 'world.bike'], heavy=True,
             about="Cairo's bike parts and M_Bike (/Game/Japan/Assets)"),
        Step('unreal.lake', [UnrealScript(SCRIPTS / 'import_forest_lake.py', 'LAKE IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_forest_lake.py', SCRIPTS / 'forest_lake_material.py'], needs=['unreal.world', 'world.lake'],
             heavy=True, about='the woodland lake and cabin'),
        Step('unreal.forest', [UnrealScript(SCRIPTS / 'import_forest.py', 'FOREST IMPORT COMPLETE', null_rhi=True,
                                           modules=IMPORT_CODE)],
             inputs=[SCRIPTS / 'import_forest.py', SCRIPTS / 'forest_impostor_material.py', SCRIPTS / 'import_foliage_lods.py', SCRIPTS / 'foliage_material.py', SCRIPTS / 'import_village.py', SCRIPTS / 'atmosphere.py'],
             needs=['unreal.world', 'world.forest', *unreal_modules.needs(IMPORT_CODE)], heavy=True,
             outputs=[out / 'forest/import-report.json'], about='current detailed Mediterranean trees with matching HISM LODs'),
        Step('unreal.treehouse', [UnrealScript(SCRIPTS / 'import_treehouse.py', 'TREEHOUSE IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_treehouse.py', SCRIPTS / 'see_through.py'],
             needs=['unreal.world', 'world.treehouse', 'world.treehouse_trees', 'world.treehouse_props', 'world.treehouse_textures'],
             heavy=True, about='the tree house meshes, textures, props and canopy trees'),
        Step('unreal.skatepark', [UnrealScript(SCRIPTS / 'import_skatepark.py', 'SKATEPARK IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_skatepark.py', REGIONS / 'skatepark' / 'park.json'], needs=['unreal.world', 'world.skatepark'],
             heavy=True, about='the skate pier and the board (/Game/SkatePark)'),
        Step('unreal.skate_board', [UnrealScript(SCRIPTS / 'board_dissolve_material.py', 'BOARD DISSOLVE MATERIAL COMPLETE')],
             inputs=[SCRIPTS / 'board_dissolve_material.py'], after=['unreal.compile'],
             outputs=[GAME / 'unreal' / 'Content' / 'SkatePark' / 'Board' / 'M_BoardDissolve.uasset'],
             heavy=True, about="the board's dissolve material for the Ride transitions (/Game/SkatePark/Board)"),
        Step('unreal.sounds', [
                UnrealScript(SCRIPTS / 'import_footsteps.py', 'FOOTSTEP IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_combat_audio.py', 'COMBAT AUDIO IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_skate_audio.py', 'SKATE AUDIO IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_bike_audio.py', 'BIKE AUDIO IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_footsteps.py', SCRIPTS / 'import_combat_audio.py', SCRIPTS / 'import_skate_audio.py', SCRIPTS / 'import_bike_audio.py'],
             # The footstep library lives in /Game/Japan, which the world import clears, so a world import reruns this.
             needs=['unreal.world', 'audio.footsteps', 'audio.combat', 'audio.skate', 'audio.bike'], heavy=True, about='footstep library, combat, skate and bike sounds'),
        Step('unreal.fx', [UnrealScript(SCRIPTS / 'import_combat_fx.py', 'COMBAT FX IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_combat_fx.py'], after=['unreal.compile'], needs=['fx.textures'], heavy=True, about='/Game/FX materials'),
        Step('unreal.fox_hunter', [UnrealScript(SCRIPTS / 'import_fox_hunter.py', 'FOX HUNTER IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_fox_hunter.py', SCRIPTS / 'animation_compression.py'],
             after=['unreal.world'], needs=['characters.fox_hunter'], heavy=True, about='/Game/FoxHunter'),
        *[step for character in definition.movers() for step in mover_import_steps(character)],
        # The camera see-through (docs/CAMERA.md) patches materials the world and the see-through characters' imports make, so it reruns after
        # either; the tree house builds its own with it (unreal.treehouse).
        Step('unreal.see_through', [UnrealScript(SCRIPTS / 'see_through.py', 'SEE-THROUGH COMPLETE')],
             inputs=[SCRIPTS / 'see_through.py', PIPELINE / 'definition.py', *sorted(CHARS.glob('*/character.toml'))],
             needs=['unreal.world', *[f'unreal.{key(c)}' for c in definition.movers() if 'see_through' in c.toml]], heavy=True,
             about='camera see-through on leaves, grass, trunks, the guardrail, poles, torii and Cairo (/Game/SeeThrough)'),
        # Runtime metadata is a separate overlay: changing it must not clear/reimport /Game/Japan.
        Step('unreal.city_tree_cpu_access', [UnrealScript(SCRIPTS / 'city_tree_cpu_access.py', 'CITY TREE CPU ACCESS COMPLETE')],
             inputs=[SCRIPTS / 'city_tree_cpu_access.py'], needs=['unreal.world'], heavy=True,
             outputs=[out / 'city_tree_lods' / 'production-cpu-access.json'],
             verify=lambda: city_tree_cpu_access_present(ctx),
             about='retain cooked CPU buffers for the three production trees used by runtime LOD validation'),
        Step('unreal.desktop', [
                UnrealScript(SCRIPTS / 'import_city_surface_tiles.py', 'CITY SURFACE TILE IMPORT COMPLETE', env=(('CITY_SURFACE_TILES_TAG', 'v1_128m'),)),
                UnrealScript(SCRIPTS / 'import_city_tree_lods.py', 'CITY TREE LODS IMPORT COMPLETE', env=(('CITY_TREE_LODS_TAG', 'v4'),))],
             inputs=[SCRIPTS / 'import_city_surface_tiles.py', SCRIPTS / 'import_city_tree_lods.py', SCRIPTS / 'experiment_mesh_import.py'],
             needs=['unreal.city_tree_cpu_access', 'world.city_tiles', 'world.city_trees'], heavy=True,
             about='desktop profile: city tiles and tree LODs (/Game/Experiments)'),
        # The Ride skating clips: the simulation rig and every simulation clip as Unreal assets (/Game/SkateRide), the manifest
        # the Ride runtime reads, and the measurement of the compressed poses against the simulation data. Both scripts
        # run in batches that resume where a failed run stopped (unreal/Scripts/skate_ride/README.md).
        Step('unreal.skate_clips', [
                *[UnrealScript(SKATE_RIDE / 'import_clips.py', 'SKATE RIDE CLIPS BATCH COMPLETE', null_rhi=True,
                               env=(('SKATE_RIDE_BATCH', f'{i}/{RIDE_IMPORT_BATCHES}'),)) for i in range(1, RIDE_IMPORT_BATCHES + 1)],
                *[UnrealScript(SKATE_RIDE / 'verify_clips.py', 'SKATE RIDE CLIPS VERIFY COMPLETE', null_rhi=True,
                               env=(('SKATE_RIDE_VERIFY_BATCH', f'{i}/{RIDE_VERIFY_BATCHES}'),)) for i in range(1, RIDE_VERIFY_BATCHES + 1)]],
             inputs=[SKATE_RIDE / n for n in ('import_clips.py', 'verify_clips.py', 'simulation.py', 'rider_mesh.py')] +
                    [SKATE_DATA / 'motion'],
             needs=['skate.runtime'], after=['unreal.compile'], heavy=True,
             outputs=[GAME / 'unreal' / 'Content' / 'Data' / 'SkateRide' / 'clips.json', out / 'skate-ride' / 'clips-verify.json'],
             about='skating rig and clips as Unreal assets (/Game/SkateRide), their manifest and verification'),
        # Independent NullRHI processes: write typed packages, then reload and verify production resource decoding.
        Step('unreal.skate_data', [
                UnrealScript(SKATE_RIDE / 'import_runtime.py', 'SKATE RUNTIME IMPORT COMPLETE', null_rhi=True),
                UnrealScript(SKATE_RIDE / 'import_motion.py', 'SKATE MOTION IMPORT COMPLETE', null_rhi=True),
                UnrealScript(SKATE_RIDE / 'verify_data.py', 'SKATE DATA VERIFY COMPLETE', null_rhi=True)],
             inputs=[SKATE_RIDE / 'import_runtime.py', SKATE_RIDE / 'import_motion.py', SKATE_RIDE / 'verify_data.py',
                     paths.ENGINE_PLUGINS / 'Activities/Skate/Source/AtelierSkate',
                     SKATE_DATA, GAME / 'unreal/Config/DefaultGame.ini',
                     *engine_version(ctx)],
             needs=['skate.runtime'], after=['unreal.compile'], heavy=True,
             outputs=[GAME / 'unreal/Content/SkateRuntime/RuntimeData.uasset',
                      GAME / 'unreal/Content/SkateMotion/MotionData.uasset', out / 'skate-data/verify.json'],
             verify=lambda: skate_data_present(out),
             about='typed simulation runtime and motion records; exact serialized reload and offline gameplay replays'),
        Step('skate.ride_stills', [Python(SKATE_RIDE / 'render_stills.py')],
             inputs=[SKATE_RIDE / n for n in ('render_stills.py', 'simulation.py', 'rider_mesh.py')], needs=['unreal.skate_clips'],
             outputs=[out / 'skate-ride' / 'clip-stills' / 'index.json'], about='stills of a few Ride clips sampled in Unreal'),
    ]


def staging_steps(ctx):
    """Runtime data copied into Content/Data after its producers complete."""
    out = ctx.out
    return [
        Step('data.stage', [Call('stage_data', stage_data)],
             inputs=[GAME / 'runtime_data.py', REGIONS / 'skatepark' / 'park.json'],
             needs=['world.layout', 'world.hidamari', 'world.map', 'world.city_tiles', 'world.treehouse', 'world.megapark', 'world.belmonte', 'world.bike',
                    *[f'characters.{key(c)}_{kind}' for c in definition.movers() for kind, wanted in
                      (('bike', c.playable), ('grips', (GRIPS / c.id).is_dir())) if wanted]],
             outputs=[GAME / 'unreal' / 'Content' / 'Data' / rel for rel in staged(out)], about='runtime files into unreal/Content/Data'),
    ]


def steps(ctx):
    """Compose the recipe in its established order; packaging is explicit and optional sources remain optional."""
    result = (world_steps(ctx) + character_steps(ctx) + sound_effect_steps(ctx)
              + unreal_steps(ctx) + staging_steps(ctx) + adventure_steps(ctx.out) + hippodrome_steps(ctx.out) + belmonte_steps(ctx.out)[1:])
    result += fit_steps(ctx.out, result)
    result += pawn_steps(result)
    identity_spec = importlib.util.spec_from_file_location('yorimichi_network_identity', GAME / 'network_identity.py')
    identity = importlib.util.module_from_spec(identity_spec)
    identity_spec.loader.exec_module(identity)
    content = GAME / 'unreal' / 'Content'
    policy_spec = importlib.util.spec_from_file_location('yorimichi_content_policy', GAME / 'content_policy.py')
    policy = importlib.util.module_from_spec(policy_spec)
    policy_spec.loader.exec_module(policy)
    result.append(Step('data.content', [Call('archive_retired_content', policy.archive)],
                       inputs=[GAME / 'content_policy.py'],
                       needs=[s.name for s in result if s.name.startswith('unreal.')] + ['data.stage'],
                       outputs=[ctx.out / 'runtime-content.json'],
                       verify=lambda: not any(policy.retired(content)),
                       about='archive retired generated imports before multiplayer identity and cooking'))
    result.append(Step('data.network', [Call('network_identity', identity.stage)],
                       inputs=[GAME / 'network_identity.py', SOURCE, ctx.uproject, GAME / 'unreal/Config',
                               paths.ENGINE_PLUGINS, *identity.content_files(content)],
                       needs=[s.name for s in result if s.name.startswith('unreal.')] + ['data.stage', 'data.content'],
                       outputs=[content / 'Data/Network/session.json'],
                       about='matching multiplayer code, imported assets and staged gameplay data'))
    return result + [cook_step(ctx, result), package_step(ctx, result)]
