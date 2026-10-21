"""How Yorimichi is built from this repository: `atelier build yorimichi [step ...]`.

Order: world exports (Python and Blender) -> characters -> sounds and effect textures -> the Unreal module ->
the Unreal imports -> runtime data staged into unreal/Content/Data. The small factories below preserve that order;
optional character and region steps are appended when their source is available. Packaging is explicit, with a
certified cook and independently stamped download assembly. Generated outputs go to build/yorimichi (or
$ATELIER_BUILD_ROOT/yorimichi) and to the ignored unreal/Content. `atelier build yorimichi --list` prints the steps.

Foliage and shared materials have independent owners. The legacy world importer preserves those packages,
binds them by stable path and rebuilds the remaining /Game/Japan content. The volcano follows it (unreal.north).
An import of a legacy region needs a digest step (`digest_step`) instead of an export it reads, so identical
re-exports leave the import current. Cairo's base import supplies his body and the nine authored clips used by
the merged move set.
"""
import importlib.util, json, os, tomllib
from dataclasses import dataclass
from pathlib import Path

from atelier.build import Product, Step, DeferredInputs, Python, Blender, UnrealScript, UnrealCompile, UnrealPackage, Call
from atelier.checkpoint_candidates import CandidateScope
from atelier import build_inputs, paths, unreal_modules

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
_kart_identity_spec = importlib.util.spec_from_file_location('kart_source_identity', TOOLS / 'kart_grip_editor/source_identity.py')
kart_source_identity = importlib.util.module_from_spec(_kart_identity_spec)
_kart_identity_spec.loader.exec_module(kart_source_identity)
_foliage_spec = importlib.util.spec_from_file_location('yorimichi_foliage_build', GAME / 'foliage_build.py')
foliage_build = importlib.util.module_from_spec(_foliage_spec)
_foliage_spec.loader.exec_module(foliage_build)

# Crater Park on the caldera floor: its block shapes the ground there (craterpark/placement.py terrain).
_v4_spec = importlib.util.spec_from_file_location('craterpark_v4_config', REGIONS / 'craterpark' / 'v2' / 'v4_config.py')
craterpark_v4 = importlib.util.module_from_spec(_v4_spec)
_v4_spec.loader.exec_module(craterpark_v4)
# The caldera's conifers (craterpark/v2/trees.py): world.hidamari_props fits their committed models.
_trees_spec = importlib.util.spec_from_file_location('craterpark_caldera_trees', REGIONS / 'craterpark' / 'v2' / 'trees.py')
caldera_trees = importlib.util.module_from_spec(_trees_spec)
_trees_spec.loader.exec_module(caldera_trees)
CRATERPARK = (REGIONS / 'craterpark' / 'placement.py', ASSETS / 'craterpark' / 'scene.json', ASSETS / 'craterpark' / 'geometry',
              REGIONS / 'craterpark' / 'v2' / 'v4_config.py',
              *(craterpark_v4.input_paths() if not craterpark_v4.selected() else ()))
# Crater Park v2 (regions/craterpark/v2): the park generated from a layout, clean by construction. False rolls back to
# the r4 build (craterpark/build.py); both write the same build.json, park.json and FBX names for unreal.craterpark.
CRATERPARK_V2 = True


def craterpark_v2_steps(out):
    """world.craterpark_geometry (numpy: compile, split, validate) then world.craterpark (Blender: FBX and the json)."""
    v2 = REGIONS / 'craterpark' / 'v2'
    common = [REGIONS / 'craterpark' / '__init__.py', REGIONS / 'craterpark' / 'placement.py', ASSETS / 'craterpark',
              REGIONS / 'megapark' / 'placement.py', YORI]
    geometry = out / 'craterpark' / 'v2'
    volcano = []
    if craterpark_v4.editor():      # the owner's editor park.json (ATELIER_CRATERPARK_EDITOR_PARK)
        runner, arguments = 'editor_generate.py', ('--park', str(craterpark_v4.editor_path()))
        # The floor samples natural terrain, not the railway-deformed/exported mountain surface.
        volcano = [REGIONS / 'hidamari' / '__init__.py', REGIONS / 'hidamari' / 'natural_terrain.py']
    else:
        runner = 'v4_generate.py' if craterpark_v4.selected() else 'generate.py'
        arguments = ('--design', str(craterpark_v4.design_path())) if craterpark_v4.selected() else ()
    return [
        Step('world.craterpark_geometry', [Python(v2 / runner, arguments)],
             inputs=[v2, *common, *volcano, *craterpark_v4.input_paths()],
             outputs=[geometry / 'geometry.npz', geometry / 'geometry-report.json'],
             about='Crater Park v2: layout -> conforming surfaces, solids, rails, render tiles and collision (numpy)',
             heavy=True),
        Step('world.craterpark', [Blender(v2 / 'export.py', threads=2)], inputs=[v2, *common, *craterpark_v4.input_paths()],
             needs=['world.craterpark_geometry'],
             outputs=[out / 'craterpark' / 'build.json', out / 'craterpark' / 'park.json', out / 'craterpark' / 'fbx' / 'SM_CP_ImportSeed.fbx'],
             about='Crater Park v2 export: FBX, build.json and park.json in the r4 contract', heavy=True),
        *([Step('world.craterpark_layout', [Python(WORLD / 'craterpark_layout.py')],
                inputs=[WORLD / 'craterpark_layout.py', *CRATERPARK, *craterpark_v4.input_paths()],
                needs=['world.craterpark_geometry'], outputs=[out / 'craterpark' / 'layout-identity.json'],
                cutoff=True, heavy=True,
                about='validated Crater Park landform, exclusion and spawn identity for island consumers')]
          if craterpark_v4.selected() else []),
    ]


# world.layout is a cutoff step: its dependents see its outputs, not its fingerprint, so each lists the layout sources
# its own scripts import. VILLAGE_LAYOUT: village/layout.py (sample, integrate), imported by every Blender region.
VILLAGE_LAYOUT = (REGIONS / 'village' / 'layout.py', YORI)
# What importing treehouse/layout.py reads (its sizes come from world.treehouse_trees' trees.json, which steps that
# import it also need), and the layout modules hidamari/layout.py brings in.
TREEHOUSE_LAYOUT = (TREEHOUSE / 'layout.py', TREEHOUSE / 'screen.py', REGIONS / 'zeppelin' / 'layout.py', REGIONS / 'megapark' / 'placement.py')
NORTH_LAYOUT = (REGIONS / 'hidamari' / 'forest_backdrop.py', REGIONS / 'megapark' / 'forest.py', REGIONS / 'megapark' / 'gate.py',
                REGIONS / 'megapark' / 'trail.py', *TREEHOUSE_LAYOUT, *VILLAGE_LAYOUT)
SOUTHWEST_MODELS = ('stand,fisher_house_a,fisher_house_b,boat_shed,stairs,dock,boat,drying_rack,temple,island,'
                    'boulder_a,boulder_b,boulder_c,stone_wall,pine_lean_a,pine_lean_b')
# The horse library (assets/horses/manifest.json) declares the breeds, tack sets and clips; the rider authors one clip
# per horse clip, and the mount and dismount. RIDE_COMMON is what the bike and horse riders share.
HORSES = ASSETS / 'horses'
HORSE_LIBRARY = json.loads((HORSES / 'manifest.json').read_text())
HORSE_VARIANTS = HORSES / 'coats' / 'variants'
HORSE_RIDER_CLIPS = (*(f'Horse{clip}' for clip in HORSE_LIBRARY['clips']), 'HorseMount', 'HorseDismount')
RIDE_COMMON = ASSETS / 'vehicles' / 'rider_common.py'
_horse_data = importlib.util.spec_from_file_location('horse_data', SCRIPTS / 'horse_data.py')
horse_data = importlib.util.module_from_spec(_horse_data)
_horse_data.loader.exec_module(horse_data)


def local_imports(script, roots=(WORLD, REGIONS)):
    """Hash the static local import closure; the platform memoizes parsing between steps."""
    return build_inputs.local_imports(script, roots)


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


def horse_import_inputs():
    """What Scripts/import_horses.py reads: its modules (horse_data.upright_glb packs with atelier.gltf), the library
    manifest, the coat masks and variants, and each breed's GLBs."""
    variants = json.loads((HORSE_VARIANTS / 'manifest.json').read_text())['variants']
    return [SCRIPTS / 'import_horses.py', SCRIPTS / 'horse_data.py', SCRIPTS / 'animation_compression.py', YORI,
            paths.STUDIO / 'atelier' / 'gltf.py',
            HORSES / 'manifest.json', HORSE_VARIANTS / 'manifest.json',
            *(HORSES / 'coats' / f'T_Coat_{mask}_Mask.png' for mask in HORSE_LIBRARY['coat_masks']),
            *(HORSE_VARIANTS / v['file'] for v in variants),
            *(HORSES / slug for slug in HORSE_LIBRARY['breeds'])]


def horses_imported_present(out):
    """The roster unreal.horses wrote matches its report and the contract (Scripts/horse_data.py), lists the library's
    breeds, clips, tack sets, coat masks and variants, and every asset it names is saved, as is each mesh's material
    instances and the textures they keep (the report's `materials`)."""
    try:
        roster = json.loads((GAME / 'unreal' / 'Content' / 'Data' / 'horses' / 'roster.json').read_text())
        report = json.loads((out / 'horses' / 'unreal_import.json').read_text())
        materials = report.pop('materials')
        if roster != report or horse_data.roster_problems(roster):
            return False
        if set(materials) != set(horse_data.meshes(roster)) or not all(materials.values()):
            return False
        library = json.loads((HORSES / 'manifest.json').read_text())
        variants = json.loads((HORSE_VARIANTS / 'manifest.json').read_text())['variants']
        if (roster['breed_order'] != list(library['breeds']) or roster['tack_sets'] != library['tack_sets']
                or list(roster['coat_masks']) != library['coat_masks']
                or [v['id'] for v in roster['coat_variants']] != [v['id'] for v in variants]
                or any(list(b['clips']) != [*library['clips'], *horse_data.TURN_CLIPS] for b in roster['breeds'].values())):
            return False
        content = GAME / 'unreal' / 'Content'
        dependencies = [path for used in materials.values() for pair in used.items() for path in pair]
        return all((content / f"{path.split('.')[0].removeprefix('/Game/')}.uasset").is_file()
                   for path in [*horse_data.asset_paths(roster), *dependencies])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
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


_digest_spec = importlib.util.spec_from_file_location('yorimichi_export_digest', GAME / 'export_digest.py')
export_digest = importlib.util.module_from_spec(_digest_spec)
_digest_spec.loader.exec_module(export_digest)
_city_spec = importlib.util.spec_from_file_location('yorimichi_city_inputs', GAME / 'city_inputs.py')
city_inputs = importlib.util.module_from_spec(_city_spec)
_city_spec.loader.exec_module(city_inputs)
_registry_spec = importlib.util.spec_from_file_location('yorimichi_source_registry', WORLD / 'source_registry.py')
source_registry = importlib.util.module_from_spec(_registry_spec)
_registry_spec.loader.exec_module(source_registry)


def city_input_step(out, part):
    """Fingerprint the selected generator's receipt fields and exact source FBXs after Hidamari."""
    names = {'tiles': city_inputs.TILES, 'trees': city_inputs.TREES}[part]
    output = out / 'digests' / f'world.hidamari.{part}.json'
    helper = GAME / 'city_inputs.py'
    return Step(f'world.hidamari.{part}',
                [Call(f'city {part} inputs', lambda ctx, log:
                      export_digest.record(output, city_inputs.snapshot(out, names), log))],
                inputs=[helper, GAME / 'export_digest.py'], needs=['world.hidamari'],
                deferred_inputs=[DeferredInputs('city-inputs', city_inputs.paths, (out, names), support=(helper,))],
                outputs=[output], cutoff=True, about=f'the three city {part} inputs, independent of other city exports')


def digest_step(out, export, part, about, root=None, names=(), north=None):
    """`<export>.<part>`: a cutoff step recording the digests of what an import reads from `export` (export_digest.py):
    files or folders under `root`, or the Hidamari meshes (`north`: the volcano's or the rest)."""
    name = f'{export}.{part}'
    output = out / 'digests' / f'{name}.json'
    if north is None:
        made, spec = (lambda: export_digest.files(root, names)), f'{root}: {", ".join(names)}'
    else:
        made, spec = (lambda: export_digest.hidamari(out, north)), f'hidamari north={north}'
    return Step(name, [Call(f'export digest {spec}', lambda ctx, log: export_digest.record(output, made(), log))],
                inputs=[GAME / 'export_digest.py'], needs=[export], outputs=[output], cutoff=True, about=about)


def hidamari_props_import_step(out):
    """The exact props manifest, meshes and textures import_hidamari and city_material consume."""
    name = 'world.hidamari_props.import'
    output = out / 'digests' / f'{name}.json'
    return Step(name, [Call('Hidamari props import digest', lambda ctx, log:
                           export_digest.record(output, export_digest.hidamari_props(out), log))],
                inputs=[GAME / 'export_digest.py'], needs=['world.hidamari_props'], outputs=[output], cutoff=True,
                verify=lambda: export_digest.hidamari_props_present(out),
                about='Hidamari prop exports the world import consumes, without review images')


def village_import_step(out, *, regions=REGIONS):
    """Validated files import_village.main(terrain=False) consumes, behind one semantic cutoff."""
    name = 'world.village.import'
    output = out / 'digests' / f'{name}.json'
    return Step(name, [Call('validated village import digest', lambda ctx, log:
                           export_digest.record(output, export_digest.village(out, regions), log))],
                inputs=[GAME / 'export_digest.py'],
                deferred_inputs=[DeferredInputs('village', export_digest.village_inputs, (out, regions),
                                                support=(GAME / 'export_digest.py',))],
                needs=['world.village'], outputs=[output], cutoff=True,
                verify=lambda: export_digest.village_present(out, regions),
                about='Village import files and validated layout/source identities, without FBX export-time churn')


def package_present(out):
    """The zip or every part the manifest lists, at its recorded size: names vary with the revision and the split."""
    root = out / 'package'
    try:
        manifest = json.loads((root / 'manifest.json').read_text())
        return bool(manifest['files']) and all((root / e['file']).stat().st_size == e['bytes'] for e in manifest['files'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def belmonte_train_route_present(out):
    """route.json, line.json and terrain_mask.json exist and line.json matches the committed line.json."""
    root = out / 'belmonte-train' / 'route'
    try:
        generated = json.loads((root / 'line.json').read_text())
        committed = json.loads((ASSETS / 'vehicles' / 'belmonte-train' / 'line.json').read_text())
        return ((root / 'route.json').is_file() and (root / 'terrain_mask.json').is_file()
                and generated == committed)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def belmonte_train_assembly_present(out):
    """consist.json, index.html and every vehicle and furniture GLB/gltf.json copy in assembly/."""
    root = out / 'belmonte-train' / 'assembly'
    try:
        doc = json.loads((root / 'consist.json').read_text())
        vehicles = doc['vehicles']
        furniture = doc['furniture']
        baked = train_bake.read(root.parent / 'furniture')
        return (bool(vehicles) and (root / 'index.html').is_file()
                and doc['furniture_bake_sha256'] == train_bake.sha(root.parent / 'furniture' / 'lod' / 'summary.json')
                and set(furniture) == set(TRAIN_FURNITURE)
                and all((root / v['glb']).is_file() and (root / v['web']).is_file()
                        for v in vehicles if v.get('status') == 'built')
                and all(f['glb'] == baked[aid]['levels'][0]['glb']
                        and train_bake.sha(root / f['glb']) == baked[aid]['levels'][0]['sha256']
                        and f['lods'] == [dict(r, glb='lod/' + r['glb']) for r in baked[aid]['levels']]
                        and (root / f['web']).is_file()
                        for aid, f in furniture.items()))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def belmonte_train_present(out):
    """Every coach GLB/blend/placement and furniture GLB/report recorded by world.belmonte_train."""
    root = out / 'belmonte-train'
    try:
        manifest = json.loads((root / 'manifest.json').read_text())
        coaches = manifest['coaches']
        return (bool(coaches)
                and all((root / v / name).stat().st_size == meta['bytes']
                        for v, info in coaches.items() for name, meta in info['files'].items())
                and all((root / 'furniture' / f'{a}.glb').is_file() and (root / 'furniture' / f'{a}.json').is_file()
                        for a in TRAIN_FURNITURE))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def belmonte_track_present(out):
    """Every track LOD GLB recorded in manifest.json and track.json, at its recorded size."""
    root = out / 'belmonte-track'
    try:
        manifest = json.loads((root / 'manifest.json').read_text())
        track = json.loads((root / 'track.json').read_text())
        files = manifest['files']
        return (bool(files)
                and all((root / 'meshes' / name).stat().st_size == meta['bytes'] for name, meta in files.items())
                and all((root / rel).is_file() for info in track['meshes'].values() for rel in info['lods']))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def belmonte_train_furniture_lods_present(out):
    """A complete, source-bound and budgeted furniture bake, independently owned by its step."""
    try:
        return set(train_bake.read(out / 'belmonte-train' / 'furniture')) == set(TRAIN_FURNITURE)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
        return False


def belmonte_train_service_present(out):
    """Every split vehicle body LOD and door leaf GLB referenced by service.json."""
    root = out / 'belmonte-train'
    try:
        data = json.loads((root / 'service' / 'service.json').read_text())
        train_bake.preflight_service(root, data)
        vehicles = data['consist']['vehicles']
        return (bool(vehicles)
                and all((root / rel).is_file() for v in vehicles for rel in v['levels'])
                and all((root / leaf['glb']).is_file()
                        for v in vehicles for d in v.get('doors', []) for leaf in d.get('leaves', [])
                        if leaf.get('glb')))
    except (OSError, ValueError, KeyError, TypeError):
        return False


# The cook and download have independent implementation inputs and success stamps.
_racing_assets_spec = importlib.util.spec_from_file_location('yorimichi_racing_assets', TOOLS / 'racing_assets.py')
racing_assets = importlib.util.module_from_spec(_racing_assets_spec)
_racing_assets_spec.loader.exec_module(racing_assets)
_cook_spec = importlib.util.spec_from_file_location('yorimichi_package_cook', TOOLS / 'package_cook.py')
package_cook = importlib.util.module_from_spec(_cook_spec)
_cook_spec.loader.exec_module(package_cook)


def engine_version(ctx):
    """The installed engine's version files: saved packages and cooked output depend on the engine build."""
    engine = getattr(ctx, 'unreal_root', None)
    return [engine / 'Engine' / 'Build' / 'Build.version',
            engine / 'Engine' / 'Binaries' / 'Mac' / 'UnrealEditor.modules'] if engine else []


def cook_step(ctx, steps):
    from atelier.build_cook_recovery import CookRecovery
    out = ctx.out
    engine_inputs = engine_version(ctx)
    return Step('unreal.cook',
                [Call('prepare_cook', package_cook.prepare), UnrealPackage('Yorimichi', out / 'package' / 'archive'),
                 Call('certify_cook', package_cook.finish)],
                inputs=[SOURCE, ctx.uproject, GAME / 'unreal/Plugins', paths.ENGINE_PLUGINS, GAME / 'unreal' / 'Config', TOOLS / 'package_cook.py', *engine_inputs],
                needs=[s.name for s in steps if s.name.startswith('unreal.') and not s.explicit] + ['data.stage', 'data.racing_assets', 'data.network'], heavy=True, explicit=True,
                outputs=[out / 'package' / 'cook.json'], verify=lambda: package_cook.cook_present(out / 'package'),
                checkpoint_restore=package_cook.certify_restored,
                cook_recovery=CookRecovery(package_cook.source_snapshot, package_cook.finish, package_cook.recovery_inputs),
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


def character_export_members(root, names):
    """Every exported body/clip/texture member, including missing required roots."""
    result = []
    for name in names:
        path = root / name
        result.extend(sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path])
    return tuple(result)


def mover_export_steps(character, out):
    """@cc [owner:fontanierh,label:performance] unchanged-character-content-skips-import
    Character import dependencies MUST identify every consumed mesh, skin/clip record and texture.
    Exporter code changes that reproduce the same content MUST NOT invalidate the import. FBX
    timestamp/ID normalization MUST retain geometry, skinning, animation and connection changes.
    """
    k, threads = key(character), character.blender['threads']
    steps = [Step(f'characters.{k}', [body_export(character.id, threads=threads)], inputs=[character.folder, NAMES, PIPELINE],
                  outputs=[out / character.output / 'export.json'], heavy=True,
                  checkpoint_outputs=(out / character.output / 'fbx', out / character.output / 'textures', out / character.output / 'export.json'),
                  about=f"{character.name}'s body, textures and own clips, to FBX")]
    if character.playable:
        steps.append(Step(f'characters.{k}_bike', [Blender(ASSETS / 'vehicles' / 'bike' / 'rider.py', ('--character', character.id), threads=threads)],
                          inputs=[character.folder, NAMES, PIPELINE, ASSETS / 'vehicles' / 'bike', RIDE_COMMON], needs=['world.bike'],
                          outputs=[out / character.output / 'bike' / 'export.json'], heavy=True,
                          about=f"Every bike action authored on {character.name}'s rig, and the bike's channels"))
        steps.append(Step(f'characters.{k}_horse', [Blender(ASSETS / 'horses' / 'rider.py', ('--character', character.id), threads=threads)],
                          inputs=[character.folder, NAMES, PIPELINE, HORSES / 'rider.py', RIDE_COMMON, YORI], needs=['world.horses'],
                          outputs=[out / character.output / 'horse' / 'export.json',
                                   *(out / character.output / 'horse' / 'fbx' / f'A_{c}.fbx' for c in HORSE_RIDER_CLIPS)], heavy=True,
                          about=f"Every horseback riding action authored on {character.name}'s rig, with its reach errors"))
    # Imports consume exported character content, not the generator implementation identity.
    # FBX timestamps/IDs are normalized by the shared export digest; geometry, skinning,
    # clips, textures and the report remain inputs. Each lane excludes its import reports.
    for lane in ('body', 'bike', 'horse') if character.playable else ('body',):
        producer = f'characters.{k}' + ('' if lane == 'body' else '_' + lane)
        root = out / character.output if lane == 'body' else out / character.output / lane
        names = ('export.json', 'fbx', 'textures') if lane == 'body' else ('export.json', 'fbx')
        digest = digest_step(out, producer, 'import', f'{character.name} {lane} content consumed by Unreal', root, names)
        output, body = digest.outputs[0], character.name if lane == 'body' else None
        digest.commands = [Call('character consumed export digest',
                               lambda ctx, log, root=root, names=names, body=body, output=output:
                               export_digest.record(output, export_digest.character(root, names, body), log))]
        digest.deferred_inputs = [DeferredInputs('character-exports', character_export_members, (root, names),
                                                 support=(GAME / 'build.py', GAME / 'export_digest.py'))]
        steps.append(digest)
    return steps


def mover_grips_step(character):
    """Its posed grips (assets/characters/grips/<id>, docs/GRIPS.md) for the move set's grip node, when committed."""
    source = GRIPS / character.id
    return [Step(f'characters.{key(character)}_grips', [Python(GRIPS / 'game.py', ('--character', character.id, '--source', source))],
                 inputs=[GRIPS / 'game.py', GRIPS / 'moments.py', *(source / f for f in ('poses.json', 'moments.json', 'body.glb'))],
                 outputs=[GAME / 'unreal' / 'Content' / 'Data' / character.id / 'grips.json'],
                 about=f"{character.name}'s posed grips, for the move set's grip node")] if source.is_dir() else []


def mover_import_steps(character, out):
    """Its body (Scripts/import_character.py) and, if playable, its bike and horse clips (Scripts/import_ride_clips.py)."""
    k, modules = key(character), tuple(character.unreal['modules'])
    body, inputs = body_import(character.id, modules)
    steps = [Step(f'unreal.{k}', [body], inputs=inputs, after=['unreal.world'], needs=[f'characters.{k}.import', *unreal_modules.needs(modules)],
                  outputs=[content(character) / f'SK_{character.name}.uasset'], heavy=True,
                  about=f'{character.unreal_path}: its mesh, materials, own clips and base definition')]
    if character.playable:
        rides = SCRIPTS / 'import_ride_clips.py'
        ride = lambda kind: UnrealScript(rides, f'{character.id.upper()} {kind.upper()} IMPORT COMPLETE', null_rhi=True,
                                         env=(('RIDE', kind), ('RIDE_CHARACTER', character.id)))
        inputs = [rides, SCRIPTS / 'animation_compression.py', YORI, PIPELINE / 'definition.py', character.folder / 'character.toml']
        steps.append(Step(f'unreal.{k}_bike', [ride('bike')], inputs=inputs, needs=[f'characters.{k}_bike.import', f'unreal.{k}'], heavy=True,
                          about=f'{character.unreal_path}Bike: its bike clips on SK_{character.name}'))
        steps.append(Step(f'unreal.{k}_horse', [ride('horse')], inputs=inputs, needs=[f'characters.{k}_horse.import', f'unreal.{k}'],
                          outputs=[out / character.output / 'horse' / 'unreal_import.json',
                                   *(GAME / 'unreal' / 'Content' / f"{character.game['bike_rig']}Horse" / f'A_{c}.uasset' for c in HORSE_RIDER_CLIPS)],
                          heavy=True, about=f'{character.unreal_path}Horse: its horseback riding clips on SK_{character.name}'))
    for step in steps:
        step.checkpoint_previous_needs = tuple(n.removesuffix('.import') if n.startswith('characters.') else n for n in step.needs)
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
    only once its move set, bike clips, grips and fit gate are all built, and after its horse clips: the pawn reads
    none of them, so horse changes leave it current."""
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
            needs=[*ready, 'unreal.compile'], after=[n for n in (f'unreal.{k}_horse',) if n in names],
            outputs=[content(character) / f'BP_{character.name}.uasset', GAME / 'unreal' / 'Content' / 'Data' / character.id / 'character.json'],
            heavy=True,
            about=f'{character.unreal_path}/BP_{character.name}: {character.name} as a playable pawn, registered with the game'))
    return result


def fit_steps(out, steps):
    """Each mover's fit gate (pipeline/fit.py), after the exports that write its reports: adventure, bike and horse."""
    names = {s.name for s in steps}
    result = []
    for character in definition.movers():
        k = key(character)
        exports = [n for n in (f'characters.{k}_adventure', f'characters.{k}_bike', f'characters.{k}_horse') if n in names]
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
             inputs=[region, ASSETS / 'hippodrome' / 'props', REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari_stable' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py', *CRATERPARK, REGIONS / 'forest/ecotone.py', REGIONS / 'forest/specs.py',
                     *NORTH_LAYOUT],
             needs=['world.layout', 'world.treehouse_trees'], outputs=[out / 'hippodrome' / 'region' / 'hippodrome.json'],
             about='hippodrome course meshes (platform, skirt, track, rails, lane), its Tripo structures and venue data'),
        digest_step(out, 'world.hippodrome', 'meshes', 'what unreal.hippodrome reads of the course', out / 'hippodrome', ['region']),
        Step('unreal.hippodrome', [UnrealScript(SCRIPTS / 'import_hippodrome.py', 'HIPPODROME IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / 'import_hippodrome.py'], needs=['world.hippodrome.meshes', 'unreal.world'], heavy=True,
             outputs=[GAME / 'unreal' / 'Content' / 'Data' / 'hippodrome' / 'hippodrome.json'],
             about='/Game/Hippodrome: the course meshes with collision, and the data AHippodrome places them from'),
        *hidamari_stable_steps(out),
    ]


def hidamari_stable_steps(out):
    """Henry's racing stable east of the hippodrome (world/regions/hidamari_stable/README.md): the Blender model, its
    control renders and the Unreal import. All three steps are explicit, so plain builds skip them."""
    region = REGIONS / 'hidamari_stable'
    root = out / 'hidamari-stable'
    kit = [REGIONS / 'village' / 'build.py', REGIONS / 'village' / 'layout.py', REGIONS / 'hidamari' / 'arcade.py',
           REGIONS / 'hidamari' / 'kit' / 'kawara.py', REGIONS / 'hidamari' / 'kit' / '_lettering.py',
           REGIONS / 'hidamari' / 'fonts' / 'NotoSansJP.ttf']
    return [
        Step('world.hidamari_stable', [Blender(region / 'build.py', threads=3)],
             inputs=[region / 'build.py', region / 'layout.py', *kit, REGIONS / 'hippodrome' / 'layout.py',
                     REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py', *CRATERPARK,
                     REGIONS / 'forest/ecotone.py', REGIONS / 'forest/specs.py', *NORTH_LAYOUT, YORI],
             needs=['world.layout', 'world.treehouse_trees'], heavy=True, explicit=True,
             outputs=[root / 'hidamari-stable.blend', root / 'placements.json', root / 'manifest.json',
                      *(root / 'glb' / f'SM_HS_{m}_LOD{k}.glb' for m in ('Stable', 'StallDoor', 'RoomDoor') for k in (0, 1, 2)),
                      *(root / 'glb' / f'SM_HS_{m}.glb' for m in ('Ground', 'Road', 'RoadSign')), root / 'glb' / 'SM_HS_Stable_Collision.glb'],
             about='Hidamari stable: barn (10 stalls, tack room, office), gate, yard, paddock; LOD0-2, collision, placements'),
        Step('world.hidamari_stable_review', [Blender(region / 'render.py', threads=3)],
             inputs=[region / 'render.py', region / 'layout.py', REGIONS / 'hippodrome' / 'layout.py'],
             needs=['world.hidamari_stable', 'world.hippodrome'], heavy=True, explicit=True,
             outputs=[root / 'review' / f'{v}.png' for v in ('road', 'gate', 'front', 'three_quarter', 'aerial', 'aisle', 'plan', 'lod1', 'lod2')],
             about='Hidamari stable control renders: road from the street, front, three-quarter, aerial, interior aisle'),
        Step('unreal.hidamari_stable', [UnrealScript(SCRIPTS / 'import_hidamari_stable.py', 'HIDAMARI STABLE IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / 'import_hidamari_stable.py'], needs=['world.hidamari_stable', 'unreal.world'],
             after=['unreal.compile'], heavy=True, explicit=True,
             outputs=[GAME / 'unreal' / 'Content' / 'Data' / 'hidamari_stable' / 'stable.json', root / 'import-report.json'],
             about='/Game/HidamariStable: the stable (3 LODs, box collision), door leaves, pad, road and sign, AHidamariStable data'),
    ]


_train_bake_spec = importlib.util.spec_from_file_location('train_furniture_bake', WORLD / 'train' / 'bake_manifest.py')
train_bake = importlib.util.module_from_spec(_train_bake_spec)
_train_bake_spec.loader.exec_module(train_bake)

TRAIN_VEHICLES = ('locomotive', 'tender', 'baggage-van', 'restaurant', 'first-class', 'second-class', 'brake-van')
TRAIN_FURNITURE = tuple(a['id'] for a in json.loads((ASSETS / 'vehicles/belmonte-train/planning/furniture-dimensions.json').read_text())['assets'])
def belmonte_train_corridor(out):
    """The railway corridor and earthworks (world/train/corridor.py and earthworks.py read the committed line.json):
    unconditional inputs of the terrain and planting steps."""
    return [WORLD / 'train' / 'corridor.py', WORLD / 'train' / 'earthworks.py', WORLD / 'train' / 'station_site.py',
            ASSETS / 'vehicles' / 'belmonte-train' / 'line.json']


def brinecove_source_step(out):
    """A small cutoff owns the exact library entries the region verifier consumes."""
    output = out / 'digests' / 'brinecove-source-library.json'
    return Step('world.brinecove.sources',
                [Call('Brinecove source-library selection', lambda ctx, log:
                      source_registry.publish(ASSETS / 'source-library.json', output, 'brinecove/models/'))],
                inputs=[WORLD / 'source_registry.py', ASSETS / 'source-library.json'],
                outputs=[output], cutoff=True,
                about='Brinecove model membership/checksums, independent of unrelated source-library entries')


def brinecove_steps(out):
    """Brinecove (world/regions/brinecove): the export closes its ground onto the FarHills hole, so it reads the
    final FarHills product; the import builds /Game/Brinecove, which ABelmonteRegion places from runtime.json."""
    region = REGIONS / 'brinecove'
    library = out / 'digests' / 'brinecove-source-library.json'
    return [
        Step('world.brinecove', [Blender(region / 'build.py', ('--source-library', str(library)), threads=3)],
             inputs=[*(p for p in region.iterdir() if p.name not in ('ferry_terminal.py', '__pycache__')), ASSETS / 'brinecove', library, WORLD / 'source_registry.py', WORLD / 'terrain_product.py', YORI],
             needs=['world.brinecove.sources'],
             reads=['terrain.FarHills.final'], heavy=True,
             outputs=[out / 'brinecove' / 'runtime.json', out / 'brinecove' / 'build-report.json'],
             about='Brinecove: pirate port ground joined to the far hills, town, waterfall, ships and flora'),
        digest_step(out, 'world.brinecove', 'meshes', 'what unreal.brinecove reads of the export', out, ['brinecove']),
        Step('unreal.brinecove', [UnrealScript(SCRIPTS / 'import_brinecove.py', 'BRINECOVE IMPORT COMPLETE',
                                              null_rhi=True, modules=IMPORT_CODE,
                                              args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',))],
             inputs=[SCRIPTS / 'import_brinecove.py', SCRIPTS / 'atmosphere.py', SCRIPTS / 'sea_look.py'],
             needs=['world.brinecove.meshes', 'unreal.world', *unreal_modules.needs(IMPORT_CODE)],
             after=['unreal.belmonte'], heavy=True,
             outputs=[out / 'brinecove' / 'import-report.json',
                      GAME / 'unreal' / 'Content' / 'Brinecove' / 'Meshes' / 'SM_BC_Ground_0_0.uasset'],
             about='/Game/Brinecove: meshes, collision and painterly surfaces'),
    ]


def belmonte_steps(out):
    """@cc [owner:fontanierh,label:safety] country-generation-admission
    The world.belmonte terrain export MUST use normal heavy-job admission and
    actual-child and aggregate memory guards, preserving their failure status.
    """
    region = REGIONS / 'belmonte'
    return [
        Step('world.belmonte', [Python(region / 'build.py')],
             inputs=[*(p for p in region.iterdir() if p.name not in ('gondola.py', '__pycache__')), WORLD / 'surface_textures.py', ASSETS / 'belmonte', ASSETS / 'environment/textures/tuscan-ground.jpg',
                     ASSETS / 'environment/textures/tuscan-ground.provenance.json', REGIONS / 'megapark/forest.py', REGIONS / 'hippodrome' / 'build.py',
                     REGIONS / 'forest/ecotone.py', REGIONS / 'forest/specs.py',
                     REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari_stable' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py', *CRATERPARK, YORI, *NORTH_LAYOUT, *belmonte_train_corridor(out)],
             needs=['world.layout', 'world.treehouse_trees'], heavy=True,
             outputs=[out / 'belmonte' / 'runtime.json', out / 'belmonte' / 'build-report.json',
                      out / 'belmonte' / 'natural' / 'SM_BM_NorthApron.glb', out / 'belmonte' / 'natural' / 'SM_BM_NorthCountry.glb'],
             about='Belmonte environment: committed models, northern terrain join and island flora'),
        digest_step(out, 'world.belmonte', 'meshes', 'what unreal.belmonte reads of the environment', out, ['belmonte']),
        # Keep derived-mesh workers out of material sections while the importer edits them.
        Step('unreal.belmonte', [UnrealScript(SCRIPTS / 'import_belmonte.py', 'BELMONTE IMPORT COMPLETE',
                                             null_rhi=True, modules=IMPORT_CODE,
                                             args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',))],
             inputs=[SCRIPTS / 'import_belmonte.py', SCRIPTS / 'racing_tv_material.py', SCRIPTS / 'atmosphere.py', SCRIPTS / 'ground_grain.py', ASSETS / 'environment/textures/tuscan-ground.jpg'],
             # Reused plants are runtime references, not reads by this library importer.
             needs=['world.belmonte.meshes', 'unreal.world', *unreal_modules.needs(IMPORT_CODE)],
             after=['unreal.forest'], heavy=True,
             outputs=[out / 'belmonte' / 'import-report.json', GAME / 'unreal' / 'Content' / 'Belmonte' / 'Meshes' / 'SM_BM_NorthApron.uasset',
                      GAME / 'unreal' / 'Content' / 'Racing' / 'M_RacingTv.uasset'],
             about='/Game/Belmonte: environment meshes, collision and painterly surfaces'),
        Step('unreal.belmonte_train', [UnrealScript(SCRIPTS / 'import_belmonte_train.py', 'BELMONTE TRAIN IMPORT COMPLETE', null_rhi=True,
                                                       args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',))],
                inputs=[SCRIPTS / 'import_belmonte_train.py', WORLD / 'train' / 'bake_manifest.py', WORLD / 'train' / 'budgets.py',
                        SOURCE / 'Yorimichi' / 'BelmonteTrainService.h', SOURCE / 'Yorimichi' / 'BelmonteTrainService.cpp',
                        out / 'belmonte-train' / 'manifest.json', out / 'belmonte-train' / 'service' / 'service.json',
                        out / 'belmonte-train' / 'service' / 'glb', out / 'belmonte-train' / 'furniture',
                        *(out / 'belmonte-train' / v for v in TRAIN_VEHICLES)],
                needs=['world.belmonte_train', 'world.belmonte_train_service'],
                after=['unreal.compile'], heavy=True,
                outputs=[GAME / 'unreal' / 'Content' / 'Data' / 'belmonte_train' / 'service.json', out / 'belmonte-train' / 'service' / 'import-report.json'],
                about='/Game/BelmonteTrain: the train vehicles (3 LODs, box collision) and furniture, and the service data'),
        Step('unreal.belmonte_track', [UnrealScript(SCRIPTS / 'import_belmonte_track.py', 'BELMONTE TRACK IMPORT COMPLETE', null_rhi=True,
                                                       args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',))],
                inputs=[SCRIPTS / 'import_belmonte_track.py'],
                needs=['world.belmonte_track.meshes', 'world.belmonte.meshes', 'unreal.belmonte'],
                after=['unreal.compile'], heavy=True,
                outputs=[GAME / 'unreal' / 'Content' / 'Data' / 'belmonte_track' / 'track.json', out / 'belmonte-track' / 'runtime' / 'import-report.json'],
                about='/Game/BelmonteTrack: track chunks, loop, turnouts, buffers, tunnel linings and portals, viaduct, banks, lamps'),
    ]


def texture_steps(ctx):
    """One exact PNG/JPEG owner per spec; the familiar aggregate consumes their byte identities."""
    from atelier.build_inputs import local_imports as action_imports
    definition = importlib.util.spec_from_file_location('yorimichi_texture_catalog', WORLD / 'texture_catalog.py')
    catalogue = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(catalogue)
    script = WORLD / 'gen_textures.py'
    support = [path for path in action_imports(script) if path != script]
    steps, products = [], []
    for key, (filename, _, assets) in catalogue.TEXTURES.items():
        spec = WORLD / 'textures' / f'{key}.json'
        output = ctx.out / 'textures' / filename
        product = f'texture.{key}'
        products.append(product)
        steps.append(Step(f'world.textures.{key}',
                          [Python(script, ('--texture', key, '--spec', spec, '--output', output,
                                           *(('--assets', ASSETS) if assets else ())))],
                          inputs=[spec, *support, *(ASSETS / 'environment/textures' / name for name in assets)],
                          outputs=[output], products=[Product(product, (output,))], cache=True, audit=True,
                          about=f'independent {filename} source texture'))
    return [*steps, Step('world.textures', [], reads=products,
                        about='all island source textures, retaining the legacy consumer boundary')]


SWORDCAMP_MESHES = (
    'SM_RoninKasa', 'SM_GuardJingasa', 'SM_CaptainKabuto',
    'SM_RoninMenpo', 'SM_RoninDo', 'SM_RoninSode', 'SM_RoninSashimono',
    'SM_RoninKatana', 'SM_RoninNodachi', 'SM_RoninWakizashi',
    'SM_CampJinmaku', 'SM_CampFirePit', 'SM_CampWeaponRack', 'SM_CampBales',
)


def world_steps(ctx):
    """@cc [owner:fontanierh,label:safety] map-generation-admission
    The world.map build command MUST use normal heavy-job admission and the
    actual-child and aggregate memory guards, preserving their failure status.
    """
    out = ctx.out
    # The volcano terrain, the world layout and the map all sample the editor park's cut ground grid. A bowl seal
    # changes that grid, so they must wait for (and be invalidated by) the geometry step in editor mode. The v4
    # design path keeps its cutoff layout dependency instead.
    crater_geometry = (['world.craterpark_layout', 'world.craterpark_geometry'] if craterpark_v4.editor()
                       else ['world.craterpark_layout'] if craterpark_v4.selected() else [])
    return [*texture_steps(ctx),
        # ------------------------------------------------------------ world
        # The tree house's tall canopy trees come first: its layout sizes them from trees.json.
        Step('world.treehouse_trees', [Blender(TREEHOUSE / 'trees.py', threads=4)], inputs=[TREEHOUSE / 'trees.py', WORLD / 'asset_mesh.py'],
             needs=['world.textures'], outputs=[out / 'treehouse' / 'trees' / 'trees.json'],
             about='tree house canopy trees (four autumn crowns) and their recoloured leaf atlases', heavy=True),
        Step('world.layout', [Python(WORLD / 'gen_world.py')],
             inputs=[WORLD / 'gen_world.py', REGIONS / 'forest/ecotone.py', REGIONS / 'forest/specs.py', REGIONS / 'houses' / 'layout.py', WORLD / 'torii_clearance.py', YORI,
                     REGIONS / 'village' / 'layout.py', REGIONS / 'mega' / 'layout.py', REGIONS / 'southwest',
                     REGIONS / 'skatepark' / 'pier_site.py',
                     REGIONS / 'forest_lake' / 'layout.py', REGIONS / 'zeppelin' / 'layout.py', TREEHOUSE / 'layout.py',
                     TREEHOUSE / 'screen.py', REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'forest.py',
                     REGIONS / 'megapark' / 'trail.py', REGIONS / 'megapark' / 'gate.py', REGIONS / 'hidamari' / 'mountains.py', *CRATERPARK,
                     REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari_stable' / 'layout.py', REGIONS / 'hidamari' / 'forest_backdrop.py', WORLD / 'farhills_grid.py',
                     *belmonte_train_corridor(out)],
             needs=['world.treehouse_trees', *crater_geometry], cutoff=True,
             outputs=[out / 'world.json', out / 'heightmap.npy', out / 'heightmap.bin', out / 'farhills.npy', out / 'treehouse' / 'layout.json',
                      out / 'megapark' / 'trail.json'],
             about='terrain heightfield, road, scatter and every region layout -> world.json (dependents see these files)'),
        Step('world.forest_textures', [Python(TOOLS / 'forest_textures.py')],
             # Only the twig atlases it reads: a new rock or ground painting leaves the forest current.
             inputs=[TOOLS / 'forest_textures.py', *sorted((ASSETS / 'environment/textures').glob('leaf-*'))],
             outputs=[out / 'forest/textures/textures.json'], about='Sunburst Mediterranean twig atlases with coverage masks'),
        Step('world.forest', [Blender(WORLD / 'build_forest.py')],
             inputs=[WORLD / 'build_forest.py', WORLD / 'forest_impostors.py', WORLD / 'forest_trees.py', REGIONS / 'forest/specs.py', WORLD / 'asset_mesh.py'],
             needs=['world.textures', 'world.forest_textures'], heavy=True,
             outputs=[out / 'forest/trees.json'], about='Tuscan branching crowns and authored HISM detail levels'),
        Step('world.props', [Blender(WORLD / 'build_assets.py')], inputs=local_imports(WORLD / 'build_assets.py'), needs=['world.textures'],
             outputs=[out / 'assets' / 'Torii.fbx'], about='rocks, torii, lanterns, poles, birds and sky dome', heavy=True),
        *foliage_build.world_steps(ctx),
        Step('world.farhills', [Blender(WORLD / 'farhills_surface.py', threads=3)],
             inputs=[WORLD / 'farhills_surface.py', WORLD / 'farhills_grid.py', WORLD / 'terrain_product.py',
                     WORLD / 'shorelines.py', YORI, *belmonte_train_corridor(out), REGIONS / 'brinecove' / 'region.py',
                     REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari_stable' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py', *CRATERPARK,
                     *(REGIONS / 'belmonte' / name for name in ('terrain.py', 'source.py', 'layout.py')),
                     *(ASSETS / 'belmonte' / entry['path'] for entry in json.loads((ASSETS / 'belmonte/source.json').read_text())['meshes']
                       if entry['name'].startswith('SM_BM_BT_Terrain_')),
                     REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'trail.py', REGIONS / 'megapark' / 'gate.py',
                     out / 'world.json', out / 'heightmap.npy', out / 'farhills.npy', out / 'megapark' / 'trail.json',
                     *([out / 'craterpark/v2/geometry.npz'] if craterpark_v4.selected() else [])],
             needs=['world.layout', *crater_geometry],
             products=[Product('terrain.FarHills.natural', (out / 'terrain/FarHills/natural.npz',)),
                       Product('terrain.FarHills.final', (out / 'terrain/FarHills/final.npz',)),
                       Product('terrain.FarHills.provenance', (out / 'terrain/FarHills/manifest.json',))],
             heavy=True, about='authoritative FarHills natural and final ordered geometry before city scenery'),
        Step('world.hidamari', [Blender(REGIONS / 'hidamari' / 'build.py')],
             inputs=[*(p for p in (REGIONS / 'hidamari').iterdir() if p.name not in ('ferry_terminal.py', 'ferry_cut.py', 'ferry_source.py', 'gondola.py', '__pycache__')), *CRATERPARK, REGIONS / 'village' / 'build.py', REGIONS / 'zeppelin' / 'layout.py',
                     REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'forest.py', REGIONS / 'megapark' / 'trail.py',
                     REGIONS / 'megapark' / 'gate.py', REGIONS / 'forest/ecotone.py', REGIONS / 'forest/specs.py', ASSETS / 'hidamari' / 'props',
                     *TREEHOUSE_LAYOUT, *VILLAGE_LAYOUT, WORLD / 'farhills_grid.py', WORLD / 'north_mountain_surface.py',
                     WORLD / 'terrain_product.py', WORLD / 'city_terrain_surface.py', *belmonte_train_corridor(out)],
             needs=['world.layout', 'world.treehouse_trees', *crater_geometry], reads=['terrain.FarHills.final'],
             outputs=[out / 'hidamari' / 'city.json', out / 'hidamari' / 'manifest.json',
                                             out / 'hidamari' / 'north_snow.png', out / 'hidamari' / 'north_snow.json',
                                             out / 'hidamari' / 'north_crater.png', out / 'hidamari' / 'north_crater.json'],
             products=[Product('terrain.HD_NorthMountains.natural', (out / 'terrain/HD_NorthMountains/natural.npz',)),
                       Product('terrain.HD_NorthMountains.final', (out / 'terrain/HD_NorthMountains/final.npz',)),
                       Product('terrain.HD_NorthMountains.provenance', (out / 'terrain/HD_NorthMountains/manifest.json',)),
                       Product('terrain.HD_Terrain.natural', (out / 'terrain/HD_Terrain/natural.npz',)),
                       Product('terrain.HD_Terrain.final', (out / 'terrain/HD_Terrain/final.npz',)),
                       Product('terrain.HD_Terrain.provenance', (out / 'terrain/HD_Terrain/manifest.json',))],
             about='the city: layout (city.json), building kit, harbor, plaza, arcade, mountains', heavy=True),
        digest_step(out, 'world.hidamari', 'city', 'the Hidamari meshes unreal.world reads (all but the volcano)', north=False),
        digest_step(out, 'world.hidamari', 'north', "the volcano's meshes unreal.north reads (HD_North*)", north=True),
        *belmonte_steps(out)[:2],
        brinecove_source_step(out),
        *brinecove_steps(out)[:2],
        # Zeppelin samples layout products and shared terrain code, not Hidamari's exported city/assets.
        # Keep the old build order; track tree metadata read by the imported treehouse layout directly.
        Step('world.zeppelin', [Blender(REGIONS / 'zeppelin' / 'build.py', threads=2)],
             # The Hidamari path follows HD_Terrain as built (layout height, railway earthworks, apron pad).
            inputs=[REGIONS / 'zeppelin', REGIONS / 'village' / 'build.py', REGIONS / 'hidamari' / 'mountains.py', *CRATERPARK,
                     REGIONS / 'hidamari' / 'layout.py', *belmonte_train_corridor(out),
                     REGIONS / 'belmonte' / 'layout.py', REGIONS / 'belmonte' / 'source.py', REGIONS / 'belmonte' / 'terrain.py',
                     ASSETS / 'belmonte' / 'source.json',
                     *(ASSETS / 'belmonte' / entry['path'] for entry in json.loads((ASSETS / 'belmonte/source.json').read_text())['meshes']
                       if entry['name'].startswith('SM_BM_BT_Terrain_')),
                     REGIONS / 'megapark' / 'gate.py', ASSETS / 'megapark' / 'map.json',
                     ASSETS / 'megapark' / 'geometry', ASSETS / 'megapark' / 'collision'],
             needs=['world.layout', 'world.treehouse_trees'], after=['world.hidamari'],
             outputs=[out / 'zeppelin' / 'manifest.json'], about='airship and its four stations', heavy=True),
        digest_step(out, 'world.zeppelin', 'meshes', 'the zeppelin meshes unreal.world reads', out / 'zeppelin', ['manifest.json', 'assets']),
        Step('world.hidamari_textures', [Python(TOOLS / 'hidamari_textures.py', ('finish',))],
             inputs=[TOOLS / 'hidamari_textures.py', TOOLS / 'treehouse_textures.py', ASSETS / 'hidamari' / 'textures'],
             outputs=[out / 'hidamari' / 'textures' / 'textures.json'], pool_roots=[out / 'hidamari' / 'textures'],
             about='Hidamari city surfaces: seamless detail maps from the Sunburst paintings'),
        Step('world.hidamari_props', [Blender(REGIONS / 'hidamari' / 'props.py', threads=4)],
             inputs=[REGIONS / 'hidamari' / 'props.py', TREEHOUSE / 'props.py', TOOLS / 'hidamari_props.py',
                     ASSETS / 'hidamari' / 'props', REGIONS / 'craterpark' / '__init__.py', REGIONS / 'craterpark' / 'v2' / '__init__.py',
                     REGIONS / 'craterpark' / 'v2' / 'trees.py',
                     *map(caldera_trees.source, caldera_trees.TREES)],
             outputs=[out / 'hidamari' / 'props' / 'props.json'],
             about="the Hidamari Tripo street props and the caldera's conifers fitted to their sizes, the conifers' LODs", heavy=True),
        hidamari_props_import_step(out),
        Step('world.treehouse_textures', [Python(TOOLS / 'treehouse_textures.py', ('finish',))],
             inputs=[TOOLS / 'treehouse_textures.py', ASSETS / 'treehouse' / 'textures'],
             outputs=[out / 'treehouse' / 'textures' / 'textures.json'], pool_roots=[out / 'treehouse' / 'textures'],
             about='tree house textures: seamless detail maps and pictures from the Sunburst paintings'),
        Step('world.treehouse_props', [Blender(TREEHOUSE / 'props.py', threads=4)],
             inputs=[TREEHOUSE / 'props.py', TOOLS / 'treehouse_props.py', ASSETS / 'treehouse' / 'props'],
             outputs=[out / 'treehouse' / 'props' / 'props.json'], about='the 13 Tripo props fitted to their sizes', heavy=True),
        Step('world.treehouse', [Blender(TREEHOUSE / 'build.py', threads=4)],
             inputs=[TREEHOUSE / 'build.py', TREEHOUSE / 'tmesh.py', REGIONS / 'village' / 'build.py', *TREEHOUSE_LAYOUT, *VILLAGE_LAYOUT],
             needs=['world.layout', 'world.treehouse_trees'], outputs=[out / 'treehouse' / 'manifest.json', out / 'treehouse' / 'runtime.json'],
             about='the tree house: ten places, bridges, rooms and their dressing, lights, sunbeams', heavy=True),
        Step('world.terrain', [Blender(WORLD / 'build_terrain.py')],
             inputs=[WORLD / 'build_terrain.py', WORLD / 'farhills_surface.py', WORLD / 'terrain_product.py',
                     WORLD / 'shorelines.py', WORLD / 'coastal_surface.py', YORI, *belmonte_train_corridor(out),
                     REGIONS / 'brinecove' / 'region.py'],
             needs=['world.layout', 'world.hidamari', 'world.textures'],
             outputs=[out / 'terrain.fbx', out / 'assets' / 'Sea.fbx'],
             reads=['terrain.FarHills.final'],
             about='terrain, road, wires, far hills, sea', heavy=True),
        digest_step(out, 'world.terrain', 'meshes', 'the terrain and sea meshes the imports read', out, ['terrain.fbx', 'assets/Sea.fbx']),
        Step('world.village', [Blender(REGIONS / 'village' / 'build.py')], inputs=[REGIONS / 'village', YORI], needs=['world.layout'],
             outputs=[out / 'village' / 'manifest.json'], about='Momiji Hamlet', heavy=True),
        village_import_step(out),
        Step('world.houses', [Blender(REGIONS / 'houses' / 'build.py')],
             inputs=[REGIONS / 'houses', REGIONS / 'village' / 'build.py', WORLD / 'torii_clearance.py', *VILLAGE_LAYOUT],
             needs=['world.layout', 'world.textures'], outputs=[out / 'houses' / 'manifest.json'],
             about='the five houses on the main road: three house models and their lots (terrace, hedge, gate, ishigaki)', heavy=True),
        Step('world.southwest', [Blender(REGIONS / 'southwest' / 'build.py', ('--models', SOUTHWEST_MODELS, '--export', '--no-render'))],
             inputs=[REGIONS / 'southwest', REGIONS / 'village' / 'build.py', *VILLAGE_LAYOUT], needs=['world.layout'],
             outputs=[out / 'southwest' / 'fbx' / 'SW_Temple.fbx'], about='fishing village, cove, island temple', heavy=True),
        Step('world.mega', [Blender(REGIONS / 'mega' / 'build.py')], inputs=[REGIONS / 'mega', REGIONS / 'village' / 'build.py', *VILLAGE_LAYOUT],
             needs=['world.layout'], outputs=[out / 'mega' / 'manifest.json'], about='the mini-mega ramp and its trail', heavy=True),
        Step('world.swordcamp_atlas', [Python(REGIONS / 'swordcamp' / 'make_atlas.py')],
             inputs=[REGIONS / 'swordcamp' / 'make_atlas.py', ASSETS / 'swordcamp', ASSETS / 'treehouse' / 'textures', YORI],
             outputs=[out / 'swordcamp' / 'swordcamp_atlas.jpg'],
             about='2048x2048 Sunburst UV texture atlas for the Kasa Ronin and roadside mini-camp'),
        Step('world.swordcamp', [Blender(REGIONS / 'swordcamp' / 'build.py', threads=3)],
             inputs=[REGIONS / 'swordcamp' / 'build.py', YORI],
             needs=['world.swordcamp_atlas'],
             outputs=[out / 'swordcamp' / 'manifest.json',
                      *(out / 'swordcamp' / 'fbx' / f'{n}.fbx' for n in SWORDCAMP_MESHES)],
             about='Kasa Ronin equipment and roadside mini-camp procedural meshes', heavy=True),
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
        Step('world.craterpark_restyle', [Python(TOOLS / 'craterpark_textures.py', ('finish',))],
             inputs=[TOOLS / 'craterpark_textures.py', ASSETS / 'craterpark' / 'restyle', ASSETS / 'craterpark' / 'textures',
                     ASSETS / 'craterpark' / 'materials.json', ASSETS / 'craterpark' / 'shrine',
                     REGIONS / 'craterpark' / 'v2' / 'shrine.py', REGIONS / 'craterpark' / 'v2' / 'dsl.py'],
             outputs=[out / 'craterpark' / 'textures' / 'textures.json'],
             about="Crater Park restyle: painted textures in the island's style, world-aligned ground and concrete"),
        *(craterpark_v2_steps(out) if CRATERPARK_V2 else [
        Step('world.craterpark', [Blender(REGIONS / 'craterpark' / 'build.py', threads=4)],
             inputs=[REGIONS / 'craterpark', ASSETS / 'craterpark', REGIONS / 'megapark' / 'placement.py', YORI],
             outputs=[out / 'craterpark' / 'build.json', out / 'craterpark' / 'park.json', out / 'craterpark' / 'fbx' / 'SM_CP_ImportSeed.fbx'],
             about='Crater Park geometry and riding collision on the caldera floor -> FBX', heavy=True)]),
        Step('world.crater_cloud', [Python(REGIONS / 'craterpark' / 'cloud_build.py')],
             inputs=[REGIONS / 'craterpark' / 'cloud.py', REGIONS / 'craterpark' / 'cloud_build.py', YORI],
             outputs=[out / 'craterpark' / 'cloud.json'],
             about="Crater Park's lenticular cap cloud: its nested lens shells and their look (numpy)"),
        Step('world.lake', [Blender(REGIONS / 'forest_lake' / 'build.py')], inputs=[REGIONS / 'forest_lake', REGIONS / 'village' / 'build.py', *VILLAGE_LAYOUT],
             needs=['world.layout'], outputs=[out / 'forest_lake' / 'manifest.json'], about='the woodland lake and cabin', heavy=True),
        Step('world.skatepark_textures', [Python(TOOLS / 'pier_textures.py', ('finish',))],
             inputs=[TOOLS / 'pier_textures.py', ASSETS / 'skatepark' / 'textures', ASSETS / 'megapark' / 'restyle' / 'stone_cut.jpg'],
             outputs=[out / 'skatepark' / 'textures' / 'textures.json'], about='Sunburst pier material maps (offline; no paid calls)'),
        Step('world.skatepark', [Blender(REGIONS / 'skatepark' / 'build.py')],
             inputs=[*sorted((REGIONS / 'skatepark').glob('*.py')), ASSETS / 'skatepark' / 'modules.json',
                     ASSETS / 'skatepark' / 'modules', *VILLAGE_LAYOUT],
             needs=['world.layout', 'world.skatepark_textures'],
             outputs=[out / 'skatepark' / 'build-report.json'], heavy=True, about='the skate pier, its rails and the trick board (park.json)'),
        Step('world.sailboat', [Blender(ASSETS / 'vehicles' / 'sailboat' / 'build.py', threads=4)],
             inputs=[ASSETS / 'vehicles' / 'sailboat', REGIONS / 'village' / 'build.py'],
             outputs=[out / 'sailboat' / 'manifest.json'], about='the dinghy', heavy=True),
        Step('world.bike', [Blender(ASSETS / 'vehicles' / 'bike' / 'build.py')],
             inputs=[ASSETS / 'vehicles' / 'bike' / 'build.py', YORI],
             outputs=[out / 'bike' / 'manifest.json'], about="Cairo's bike: frame, steering, wheels, crank, pedals, kickstand, rack board", heavy=True),
        # Verifies every library GLB, measures each breed's contacts and samples the reference breed's clips. A cutoff:
        # its dependents (the riders, unreal.horses) list what else they read, so a palette edit reruns only the import.
        Step('world.horses', [Blender(HORSES / 'build.py', threads=3)],
             inputs=[HORSES / 'build.py', HORSES / 'turn.py', HORSES / 'manifest.json', YORI,
                     paths.STUDIO / 'atelier' / 'gltf.py', *(HORSES / slug for slug in HORSE_LIBRARY['breeds'])],
             outputs=[out / 'horses' / 'manifest.json', *(out / 'horses' / 'turns' / f'{slug}.glb' for slug in HORSE_LIBRARY['breeds'])], cutoff=True,
             about="the horses' rider contacts and 60 Hz clip trajectories", heavy=True),
        Step('world.kei', [Blender(ASSETS / 'vehicles' / 'kei' / 'build.py')],
             inputs=[ASSETS / 'vehicles' / 'kei', REGIONS / 'village' / 'build.py'],
             outputs=[out / 'kei' / 'manifest.json'], about='the four kei cars in the Mega Park car park', heavy=True),
        Step('world.kart', [Blender(ASSETS / 'vehicles' / 'kart' / 'build.py', threads=3)],
             inputs=[ASSETS / 'vehicles' / 'kart' / 'build.py', ASSETS / 'vehicles' / 'kart' / 'cockpit.py',
                     ASSETS / 'vehicles' / 'kart' / 'cockpit.json', REGIONS / 'village' / 'build.py', REGIONS / 'village' / 'layout.py', YORI],
             outputs=[out / 'kart' / 'manifest.json', out / 'kart' / 'cockpit.json',
                      *(out / 'kart' / 'assets' / f'{name}.fbx' for name in
                        ('SM_Kart_Body', 'SM_Kart_Seat', 'SM_Kart_Wheel', 'SM_Kart_SteeringWheel'))],
             about='the go-kart, its seat, its wheels and its steering wheel', heavy=True),
        Step('world.belmonte_train', [Blender(WORLD / 'train' / 'build.py', threads=3)],
             inputs=[*build_inputs.local_imports(WORLD / 'train' / 'build.py', (WORLD,)),
                     ASSETS / 'vehicles' / 'belmonte-train' / 'planning',
                     ASSETS / 'vehicles' / 'belmonte-train' / 'textures',
                     ASSETS / 'vehicles' / 'belmonte-train' / 'furniture',
                     ASSETS / 'vehicles' / 'belmonte-train' / 'source.toml', YORI],
             outputs=[out / 'belmonte-train' / 'manifest.json',
                      *(out / 'belmonte-train' / v / f'{v}-placements.json' for v in TRAIN_VEHICLES),
                      *(out / 'belmonte-train' / 'furniture' / f'{a}.glb' for a in TRAIN_FURNITURE),
                      *(out / 'belmonte-train' / 'furniture' / f'{a}.json' for a in TRAIN_FURNITURE)],
             verify=lambda: belmonte_train_present(out),
             heavy=True,
             about='Belmonte train: restaurant and first-class coach shells, collision, reservations, placements'),
        Step('world.belmonte_train_plan', [Python(WORLD / 'train' / 'plan.py')],
             inputs=[WORLD / 'train' / 'plan.py', WORLD / 'train' / 'layout.py', ASSETS / 'vehicles' / 'belmonte-train' / 'planning'],
             outputs=[out / 'belmonte-train' / 'plan' / 'section.svg'], explicit=True, about='Belmonte train dimensioned plans (SVG)'),
        Step('world.belmonte_train_furniture_lods', [Blender(WORLD / 'train' / 'lod_furniture.py', threads=3)],
             inputs=[WORLD / 'train' / 'lod_furniture.py', WORLD / 'train' / 'budgets.py',
                     WORLD / 'train' / 'bake_manifest.py',
                     ASSETS / 'vehicles' / 'belmonte-train' / 'planning',
                     *(out / 'belmonte-train' / 'furniture' / f'{a}.glb' for a in TRAIN_FURNITURE)],
             needs=['world.belmonte_train'], heavy=True,
             outputs=[out / 'belmonte-train' / 'furniture' / 'lod' / 'summary.json',
                      *(out / 'belmonte-train' / 'furniture' / 'lod' / f'{a}_LOD{k}.glb'
                        for a in TRAIN_FURNITURE for k in ([0, 1] if train_bake.B.FURNITURE[a][1] else [0]))],
             verify=lambda: belmonte_train_furniture_lods_present(out),
             about='Belmonte train furniture: LOD0/LOD1 decimated from the fitted Tripo meshes, maps baked (Cycles)'),
        Step('world.belmonte_train_assembly', [Python(WORLD / 'train' / 'consist.py')],
             inputs=[WORLD / 'train' / 'consist.py', WORLD / 'train' / 'layout.py', WORLD / 'train' / 'viewer.html',
                     WORLD / 'train' / 'bake_manifest.py', WORLD / 'train' / 'budgets.py',
                     ASSETS / 'vehicles' / 'belmonte-train' / 'planning', out / 'belmonte-train' / 'furniture',
                     *(out / 'belmonte-train' / v for v in TRAIN_VEHICLES)],
             needs=['world.belmonte_train', 'world.belmonte_train_furniture_lods'],
             outputs=[out / 'belmonte-train' / 'assembly' / 'consist.json', out / 'belmonte-train' / 'assembly' / 'index.html'],
             verify=lambda: belmonte_train_assembly_present(out),
             about='Belmonte train assembly: consist.json, GLBs and the viewer page'),
        Step('world.belmonte_train_review', [Blender(WORLD / 'train' / 'render.py', threads=3)],
             inputs=[WORLD / 'train' / 'render.py', WORLD / 'train' / 'layout.py',
                     ASSETS / 'vehicles' / 'belmonte-train' / 'planning',
                     *(out / 'belmonte-train' / v for v in TRAIN_VEHICLES)],
             needs=['world.belmonte_train'], heavy=True, explicit=True,
             outputs=[out / 'belmonte-train' / 'review' / 'consist-profile.png'],
             about='Belmonte train control renders (white background)'),
        Step('world.belmonte_train_route', [Python(WORLD / 'train' / 'route.py')],
             inputs=[WORLD / 'train' / 'route.py', WORLD / 'train' / 'corridor.py', WORLD / 'train' / 'station_site.py',
                     ASSETS / 'vehicles' / 'belmonte-train' / 'line.json', *CRATERPARK, *NORTH_LAYOUT,
                     REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari_stable' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py',
                     REGIONS / 'belmonte' / 'layout.py', REGIONS / 'belmonte' / 'source.py', REGIONS / 'belmonte' / 'terrain.py',
                     ASSETS / 'belmonte', out / 'belmonte' / 'natural' / 'SM_BM_NorthApron.glb',
                     out / 'belmonte' / 'natural' / 'SM_BM_NorthCountry.glb'],
             needs=['world.layout', 'world.hidamari', 'world.belmonte'], cutoff=True,
             outputs=[out / 'belmonte-train' / 'route' / 'route.json', out / 'belmonte-train' / 'route' / 'line.json',
                      out / 'belmonte-train' / 'route' / 'terrain_mask.json'],
             verify=lambda: belmonte_train_route_present(out),
             about='Belmonte railway route study: alignment, profile, structures, timetable (route.json, plan and profile)'),
        Step('world.belmonte_track', [Blender(WORLD / 'train' / 'track_build.py', threads=3)],
             inputs=[WORLD / 'train' / 'track.py', WORLD / 'train' / 'track_build.py', WORLD / 'train' / 'earthworks.py',
                     WORLD / 'train' / 'corridor.py', WORLD / 'train' / 'station_site.py', WORLD / 'train' / 'overbridge.py',
                     WORLD / 'train' / 'station.py',
                     *CRATERPARK, *NORTH_LAYOUT,
                     REGIONS / 'hidamari' / 'layout.py', REGIONS / 'hidamari_stable' / 'layout.py', REGIONS / 'hidamari' / 'mountains.py',
                     REGIONS / 'belmonte' / 'layout.py', REGIONS / 'belmonte' / 'source.py', REGIONS / 'belmonte' / 'terrain.py',
                     ASSETS / 'belmonte' / 'source.json',
                     *(ASSETS / 'belmonte' / entry['path'] for entry in json.loads((ASSETS / 'belmonte/source.json').read_text())['meshes']
                       if entry['name'].startswith('SM_BM_BT_Terrain_')),
                     out / 'belmonte-train' / 'route' / 'route.json', out / 'belmonte-train' / 'route' / 'line.json'],
             needs=['world.belmonte_train_route'],
             heavy=True, outputs=[out / 'belmonte-track' / 'track.json', out / 'belmonte-track' / 'manifest.json'],
             verify=lambda: belmonte_track_present(out),
             about='Belmonte railway track: ballast and rail chunks, sleepers, loop, turnouts, buffer stops, tunnels, viaduct (GLBs + track.json)'),
        Step('world.belmonte_track_review', [Blender(WORLD / 'train' / 'track_render.py', threads=3)],
             inputs=[WORLD / 'train' / 'track_render.py', WORLD / 'train' / 'track.py', WORLD / 'train' / 'track_build.py',
                     out / 'belmonte-track' / 'track.json', out / 'belmonte-track' / 'meshes'],
             needs=['world.belmonte_track'], heavy=True, explicit=True,
             outputs=[out / 'belmonte-track' / 'review' / 'viaduct.png'], about='Belmonte railway track control renders'),
        Step('world.belmonte_station_review', [Blender(WORLD / 'train' / 'station_render.py', threads=3)],
             inputs=[WORLD / 'train' / 'station_render.py', WORLD / 'train' / 'station.py', WORLD / 'train' / 'station_site.py',
                     WORLD / 'train' / 'track_render.py', out / 'belmonte-track' / 'track.json', out / 'belmonte-track' / 'meshes'],
             needs=['world.belmonte_track'], heavy=True, explicit=True,
             outputs=[out / 'belmonte-track' / 'review' / 'station-front.png'],
             about='Belmonte station control renders: the elevations of Paul\'s references, platforms, stair hall, overbridge'),
        Step('world.belmonte_train_furniture_review', [Blender(WORLD / 'train' / 'review_lods.py', threads=3),
                                                       Python(WORLD / 'train' / 'review_sheets.py')],
             inputs=[WORLD / 'train' / 'review_lods.py', WORLD / 'train' / 'review_sheets.py', WORLD / 'train' / 'render.py',
                     WORLD / 'train' / 'budgets.py', WORLD / 'train' / 'layout.py',
                     ASSETS / 'vehicles' / 'belmonte-train' / 'planning', out / 'belmonte-train' / 'furniture',
                     *(out / 'belmonte-train' / v for v in TRAIN_VEHICLES)],
             needs=['world.belmonte_train', 'world.belmonte_train_furniture_lods'], heavy=True, explicit=True,
             outputs=[out / 'belmonte-train' / 'review-perf' / 'second-class-saloon.png'],
             about='Belmonte train furniture LODs: before/after renders, assets and furnished interiors'),
        Step('world.belmonte_train_service', [Python(TOOLS / 'belmonte_train_service.py')],
             inputs=[TOOLS / 'belmonte_train_service.py', TOOLS / 'gltf_subset.py',
                     WORLD / 'train' / 'bake_manifest.py', WORLD / 'train' / 'budgets.py',
                     WORLD / 'train' / 'station_site.py', WORLD / 'regions' / 'hidamari' / 'station_yard.py',
                     out / 'belmonte-train' / 'route' / 'route.json', out / 'belmonte-train' / 'assembly' / 'consist.json',
                     out / 'belmonte-train' / 'furniture', *(out / 'belmonte-train' / v for v in TRAIN_VEHICLES)],
             needs=['world.belmonte_train_route', 'world.belmonte_train', 'world.belmonte_train_assembly'],
             outputs=[out / 'belmonte-train' / 'service' / 'service.json'],
             verify=lambda: belmonte_train_service_present(out),
             about='Belmonte train service: line, loop, consist, collision boxes and timetable for Unreal'),
        Step('world.belmonte_track_data', [Python(TOOLS / 'belmonte_track_data.py')],
             inputs=[TOOLS / 'belmonte_track_data.py', out / 'belmonte-track' / 'track.json', out / 'belmonte-track' / 'meshes'],
             needs=['world.belmonte_track'],
             outputs=[out / 'belmonte-track' / 'runtime' / 'track.json'],
             about='Belmonte track runtime data: pieces, instances, tunnel lights and exposure boxes in Unreal units'),
        Step('world.belmonte_track.meshes',
             [Call('export digest belmonte-track', lambda ctx, log:
                   export_digest.record(out / 'digests' / 'world.belmonte_track.meshes.json',
                                        export_digest.files(out / 'belmonte-track', ['runtime/track.json', 'meshes']), log))],
             inputs=[GAME / 'export_digest.py'], needs=['world.belmonte_track', 'world.belmonte_track_data'],
             outputs=[out / 'digests' / 'world.belmonte_track.meshes.json'], cutoff=True,
             about='the track meshes and runtime data unreal.belmonte_track reads'),
        Step('world.map', [Python(WORLD / 'map' / 'build_map.py')],
             inputs=[WORLD / 'map', WORLD / 'north_mountain_surface.py', WORLD / 'city_terrain_surface.py',
                     REGIONS / 'hidamari' / 'build.py', REGIONS / 'hidamari_stable' / 'layout.py', WORLD / 'build_terrain.py', WORLD / 'farhills_surface.py', WORLD / 'farhills_grid.py', WORLD / 'terrain_product.py',
                     *CRATERPARK, REGIONS / 'southwest', REGIONS / 'mega' / 'ramp.py', REGIONS / 'megapark' / 'placement.py', REGIONS / 'megapark' / 'gate.py',
                     *[REGIONS / 'belmonte' / (name + '.py') for name in ('plan', 'planting', 'source', 'layout', 'terrain')],
                     *belmonte_train_corridor(out),
                     ASSETS / 'belmonte' / 'source.json',
                     *(ASSETS / 'belmonte' / entry['path']
                       for entry in json.loads((ASSETS / 'belmonte' / 'source.json').read_text())['meshes']
                       if entry['name'].startswith(('SM_BM_BT_Terrain_', 'SM_BM_BT_blk_', 'SM_BM_BH_', 'SM_BM_BE_', 'SM_BM_BHip_',
                                                    'SM_BM_BVV_Farm_', 'SM_BM_BC_Water_', 'SM_BM_BC_Pave', 'SM_BM_BC_Ponte')))],
             needs=['world.layout', 'world.hidamari', 'world.skatepark', 'world.zeppelin', 'world.belmonte', 'world.brinecove',
                    *crater_geometry],
             outputs=[out / 'map' / 'map.json', out / 'map' / 'map.png',
                      *(out / 'map' / 'atlas' / f'{key}.png' for key in ('world', 'momiji_coast', 'momiji_woods', 'hidamari', 'temple_island',
                                                                     'northern_foothills', 'volcanic_highlands', 'haras_valley',
                                                                     'brinecove'))],
             heavy=True, about='map zones and label-free regional atlas'),
        city_input_step(out, 'tiles'),
        Step('world.city_tiles', [Blender(WORLD / 'city_surface_tiles.py', ('--tag', 'v1_128m'), threads=3)],
             inputs=[WORLD / 'city_surface_tiles.py'], needs=['world.hidamari.tiles'],
             outputs=[out / 'city_surface_tiles' / 'v1_128m' / 'manifest.json'], about='desktop profile: city surfaces in 128 m tiles', heavy=True),
        digest_step(out, 'world.city_tiles', 'meshes', 'the city tiles unreal.desktop reads', out / 'city_surface_tiles', ['v1_128m']),
        city_input_step(out, 'trees'),
        Step('world.city_trees', [Blender(WORLD / 'city_tree_lods.py', ('--tag', 'v4'), threads=3)],
             inputs=[WORLD / 'city_tree_lods.py', REGIONS / 'hidamari' / 'arcade.py', REGIONS / 'hidamari' / 'plaza.py'],
             needs=['world.hidamari.trees'], outputs=[out / 'city_tree_lods' / 'v4' / 'manifest.json'], about='desktop profile: city tree LODs', heavy=True),
        digest_step(out, 'world.city_trees', 'meshes', 'the city tree LODs unreal.desktop reads', out / 'city_tree_lods', ['v4']),
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


def music_files(cache, categories, styles, groups, limit):
    """Selected cached tracks; their bytes and declared selectors enter the audio step key."""
    catalog_path = Path(cache) / 'catalog.json'
    if not catalog_path.is_file():
        return ()
    catalog = json.loads(catalog_path.read_text())
    categories = {part.strip() for part in categories.split(',') if part.strip()}
    styles = {part.strip() for part in styles.split(',') if part.strip()}
    groups = {part.strip() for part in groups.split(',') if part.strip()}
    chosen = []
    for track in catalog.get('tracks', []):
        if categories and track.get('category') not in categories:
            continue
        if styles and track.get('style_family') not in styles:
            continue
        if groups and track.get('group') not in groups and track.get('zone') not in groups:
            continue
        chosen.append(Path(cache) / track['path'])
        if limit and len(chosen) >= limit:
            break
    return tuple(chosen)


def music_selector_members(categories, styles, groups, limit, enabled):
    """Retain the optional-music settings in data.content's build key."""
    return ()


def music_import_present(out):
    """Every selected SoundWave package exists and no stale owned package remains."""
    try:
        data = json.loads((out / 'music_import.json').read_text())
        imported = data['imported']
        expected = set()
        for item in imported.values():
            path = item.get('path')
            if not path or not path.startswith('/Game/'):
                return False
            package = path.rsplit('.', 1)[0] if '.' in path.rsplit('/', 1)[-1] else path
            asset = GAME / 'unreal/Content' / (package.removeprefix('/Game/') + '.uasset')
            if not asset.is_file() or asset.stat().st_size == 0:
                return False
            expected.add(asset.resolve())
    except (OSError, KeyError, TypeError, ValueError):
        return False
    root = GAME / 'unreal/Content/Audio/Music'
    actual = {path.resolve() for path in root.rglob('*.uasset')} if root.is_dir() else set()
    return bool(expected) and actual == expected


# The Sonniss combat masters assets/audio/transport/make.py layers (its METAL, THUMP, DRUM and STICK).
TRANSPORT_MASTERS = ('smartsound_sword_hit_metal_02.wav', 'gamemaster_body_thump_02.wav', 'baxter_hit_big_drum_03.wav',
                     'audioville_stick_hit_13_wild.wav')


def sound_effect_steps(ctx):
    """Offline sound slices and procedural effect textures."""
    out = ctx.out
    music_cache = paths.cache_dir('yorimichi', 'music', create=False)
    music_categories = os.environ.get('YORIMICHI_MUSIC_CATEGORIES', '')
    music_styles = os.environ.get('YORIMICHI_MUSIC_STYLES', '')
    music_groups = os.environ.get('YORIMICHI_MUSIC_GROUPS', '')
    music_limit = os.environ.get('YORIMICHI_MUSIC_LIMIT', '0')
    music_args = (
        '--categories', music_categories, '--styles', music_styles,
        '--groups', music_groups, '--limit', music_limit,
    )
    return [
        # ------------------------------------------------------------ sounds and effects
        Step('audio.footsteps', [Python(AUDIO / 'footsteps' / 'slice.py')], inputs=[AUDIO / 'footsteps', paths.cache_dir('sonniss', 'footsteps', create=False)],
             outputs=[out / 'audio' / 'footsteps' / 'manifest.json'],
             products=[Product('audio.footsteps', (out / 'audio' / 'footsteps',))],
             about='531 footstep one-shots (needs `atelier fetch`)'),
        Step('audio.combat', [Python(AUDIO / 'combat' / 'slice.py')], inputs=[AUDIO / 'combat', paths.cache_dir('sonniss', 'combat', create=False)],
             outputs=[out / 'audio' / 'combat' / 'manifest.json'], about='combat cues and the countryside ambience'),
        Step('audio.skate', [Python(AUDIO / 'skate' / 'make.py')], inputs=[AUDIO / 'skate', paths.cache_dir('sonniss', 'combat', create=False)],
             outputs=[out / 'audio' / 'skate' / 'manifest.json'],
             products=[Product('audio.skate', (out / 'audio' / 'skate',))], about='board loops and cues'),
        Step('audio.bike', [Python(AUDIO / 'bike' / 'make.py')], inputs=[AUDIO / 'bike', AUDIO / 'skate' / 'make.py', paths.cache_dir('sonniss', 'combat', create=False)],
             outputs=[out / 'audio' / 'bike' / 'manifest.json'], about="the bike's tyres, freewheel, chain, wind, bell and knocks"),
        # Only what make.py reads: itself, the skate and bike DSP helpers, the combat fetch list (for the manifest's
        # md5s) and the four combat masters it layers (TRANSPORT_MASTERS).
        Step('audio.transport', [Python(AUDIO / 'transport' / 'make.py')],
             inputs=[AUDIO / 'transport' / 'make.py', AUDIO / 'skate' / 'make.py', AUDIO / 'bike' / 'make.py', AUDIO / 'combat' / 'fetch.py',
                     *(paths.cache_dir('sonniss', 'combat', create=False) / name for name in TRANSPORT_MASTERS)],
             outputs=[out / 'audio' / 'transport' / 'manifest.json'],
             about="the ferry's, gondolas' and zeppelin's engines, wash, wind, horns, bells, gates and doors"),
        Step('audio.kart', [Python(AUDIO / 'kart' / 'make.py')], inputs=[AUDIO / 'kart', AUDIO / 'skate' / 'make.py'],
             outputs=[out / 'audio' / 'kart' / 'manifest.json'], about="the kart's engine, tyres, skid, wind, impacts and suspension knocks"),
        # The Suno library is optional: naming `audio.music` or `unreal.music` selects
        # only the tracks requested by YORIMICHI_MUSIC_* selectors. A plain build
        # never downloads or imports the large release.
        Step('audio.music', [Python(AUDIO / 'music' / 'prepare.py', music_args)],
             inputs=[AUDIO / 'music' / 'prepare.py', music_cache / 'catalog.json',
                     AUDIO / 'music' / 'music.lock.json'],
             deferred_inputs=[DeferredInputs(
                 'music', music_files,
                 (music_cache, music_categories, music_styles, music_groups,
                  int(music_limit or 0)), support=(GAME / 'build.py',))],
             outputs=[out / 'audio' / 'music' / 'manifest.json'], explicit=True,
             about='select fetched Suno tracks for the optional music import'),
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
        Step('unreal.compile', [UnrealCompile('YorimichiEditor')], inputs=[SOURCE, ctx.uproject, GAME / 'unreal/Config', GAME / 'unreal/Plugins', paths.ENGINE_PLUGINS], needs=['skate.runtime'], heavy=True,
             about='the Yorimichi C++ modules (editor target)'),
        *unreal_modules.steps(ctx, IMPORT_CODE + SAVED_TYPES + CONTACT_TYPES),
        *foliage_build.unreal_steps(ctx, IMPORT_CODE, engine_version(ctx)),
        Step('unreal.world', [UnrealScript(SCRIPTS / 'setup_project.py', 'level saved')],
             # The city's arcade and harbor materials read the region's committed paintings.
             inputs=[WORLD / 'asset_catalog.py', WORLD / 'coast_water.py', REGIONS / 'hidamari' / 'textures',
                     REGIONS / 'hidamari/ferry_source.py',
                     ASSETS / 'environment/textures/volcanic-rock.jpg', SCRIPTS / 'coast_rock_look.py',
                     *[SCRIPTS / n for n in ('setup_project.py', 'material_assets.py', 'mesh_import.py',
                                          'import_wanderer.py', 'cape_boy_material.py', 'animation_compression.py', 'import_village.py',
                                          'import_hidamari.py', 'import_southwest.py', 'arcade_material.py', 'plaza_material.py',
                                          'harbor_material.py', 'sea_look.py', 'import_sailboat.py', 'sailboat_material.py',
                                          'import_zeppelin.py', 'forest_ground.py', 'ground_grain.py', 'atmosphere.py', 'city_material.py', 'mesh_materials.py')]],
             after=['unreal.compile', 'unreal.materials'],
             references=['materials.shared', *['foliage.' + name + '.native' for name in foliage_build.catalog.FOLIAGE]],
             needs=['world.hidamari_ferry_cut', 'world.textures', 'world.layout', 'world.props', 'world.hidamari.city', 'world.hidamari_textures', 'world.hidamari_props.import',
                    'world.zeppelin.meshes', 'world.terrain.meshes', 'world.village.import', 'world.sailboat', 'characters.wanderer'],
             heavy=True, about='legacy world assets and level; preserves independent materials and foliage'),
        # The volcano: its meshes, M_NorthMountains with the rock and snow mask textures, M_NorthGate. The world import
        # purges /Game/Japan and makes the textures and MPC these materials use, so this reruns after it.
        Step('unreal.north', [UnrealScript(SCRIPTS / 'import_hidamari.py', 'HIDAMARI IMPORT COMPLETE', env=(('HIDAMARI_ASSETS', 'HD_North*'),))],
             inputs=[WORLD / 'coast_water.py', SCRIPTS / 'forest_ground.py', ASSETS / 'environment/textures/volcanic-rock.jpg', out / 'hidamari' / 'north_snow.png', out / 'hidamari' / 'north_snow.json',
                     out / 'hidamari' / 'north_crater.png', out / 'hidamari' / 'north_crater.json',
                     out / 'craterpark' / 'textures' / 'crater_floor.png', TOOLS / 'craterpark_textures.py',
                     *[SCRIPTS / n for n in ('import_hidamari.py', 'mountain_material.py', 'import_village.py', 'atmosphere.py', 'ground_grain.py', 'sea_look.py')]],
             needs=['unreal.world', 'world.hidamari.north', 'world.craterpark_restyle'], heavy=True,
             about='/Game/Japan: the volcano (HD_North*), M_NorthMountains and its rock, snow and crater floor textures'),
        # The regions below layer onto the world (the south-west import replaces the terrain's and the sea's materials),
        # so they rerun when it is reimported.
        Step('unreal.southwest', [UnrealScript(SCRIPTS / 'import_southwest.py', 'SOUTHWEST IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_southwest.py', SCRIPTS / 'sea_look.py', SCRIPTS / 'forest_ground.py',
                     SCRIPTS / 'ground_grain.py', SCRIPTS / 'material_assets.py'], needs=['unreal.world', 'world.southwest', 'world.terrain.meshes'], heavy=True,
             about='south-west props, the terrain and the sea'),
        Step('unreal.mega', [UnrealScript(SCRIPTS / 'import_mega.py', 'MEGA IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_mega.py'], needs=['unreal.world', 'world.mega'], heavy=True, about='the mini-mega ramp'),
        Step('unreal.swordcamp', [UnrealScript(SCRIPTS / 'import_swordcamp.py', 'SWORDCAMP IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / 'import_swordcamp.py', SCRIPTS / 'mesh_import.py', SCRIPTS / 'atmosphere.py', SCRIPTS / 'sea_look.py'],
             after=['unreal.compile'], needs=['world.swordcamp'],
             outputs=[out / 'swordcamp' / 'import-report.json',
                      GAME / 'unreal' / 'Content' / 'SwordCamp' / 'Textures' / 'T_SwordCampAtlas.uasset',
                      GAME / 'unreal' / 'Content' / 'SwordCamp' / 'Materials' / 'M_SwordCamp.uasset',
                      GAME / 'unreal' / 'Content' / 'SwordCamp' / 'Materials' / 'M_RoninBody.uasset',
                      *(GAME / 'unreal' / 'Content' / 'SwordCamp' / 'Assets' / f'{n}.uasset' for n in SWORDCAMP_MESHES)],
             heavy=True, about='/Game/SwordCamp: Kasa Ronin equipment and roadside mini-camp props'),
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
        Step('unreal.craterpark', [UnrealScript(SCRIPTS / 'import_craterpark.py', 'CRATERPARK IMPORT COMPLETE', null_rhi=True,
                                              args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',),
                                              modules=IMPORT_CODE + SAVED_TYPES)],
             inputs=[SCRIPTS / 'import_craterpark.py', SCRIPTS / 'import_megapark.py'],
             needs=['world.craterpark', 'world.craterpark_restyle', *unreal_modules.needs(IMPORT_CODE + SAVED_TYPES)],
             outputs=[out / 'craterpark' / 'import-report.json'],
             heavy=True, about='Crater Park meshes, textures and materials (/Game/CraterPark)'),
        Step('unreal.houses', [UnrealScript(SCRIPTS / 'import_houses.py', 'HOUSES IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_houses.py'], needs=['unreal.world', 'world.houses'], heavy=True,
             about='the houses on the main road and their lots'),
        Step('unreal.kei', [UnrealScript(SCRIPTS / 'import_kei.py', 'KEI IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_kei.py'], needs=['unreal.world', 'world.kei'], heavy=True,
             about='the kei cars the Mega Park parks in its car park (/Game/Japan/Assets)'),
        Step('unreal.kart', [Python(TOOLS / 'kart_grip_editor/validate_profiles.py', ('--layout', out / 'kart/cockpit.json')),
                             UnrealScript(SCRIPTS / 'import_kart.py', 'KART IMPORT COMPLETE', modules=IMPORT_CODE)],
             inputs=[SCRIPTS / 'import_kart.py', SCRIPTS / 'kart_material.py', SCRIPTS / 'mesh_import.py', YORI,
                     *(kart_source_identity.profile_path(name) for name in kart_source_identity.playable_ids()),
                     *(kart_source_identity.model_path(name) for name in kart_source_identity.playable_ids()),
                     TOOLS / 'kart_grip_editor/validate_profiles.py',
                     TOOLS / 'kart_grip_editor/server.py', TOOLS / 'kart_grip_editor/grip_data.py',
                     TOOLS / 'kart_grip_editor/source_identity.py',
                     *(p for name in kart_source_identity.playable_ids() for p in kart_source_identity.source_paths(name))],
             needs=['world.kart', *unreal_modules.needs(IMPORT_CODE)], heavy=True,
             outputs=[GAME / 'unreal' / 'Content' / 'Japan' / 'Kart' / f'{name}.uasset' for name in
                      ('M_Kart', 'SM_Kart_Body', 'SM_Kart_Seat', 'SM_Kart_Wheel', 'SM_Kart_SteeringWheel')]
                     + [GAME / 'unreal/Content/Data/kart/cockpit.json',
                        GAME / 'unreal/Content/Data/kart/prepared-models.json',
                        *(GAME / f'unreal/Content/Data/kart/grips/{name}.json' for name in kart_source_identity.playable_ids())],
             about='the go-kart body, wheels and steering wheel (/Game/Japan/Kart)'),
        Step('unreal.bike', [UnrealScript(SCRIPTS / 'import_bike.py', 'BIKE IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_bike.py', SCRIPTS / 'bike_material.py'], needs=['unreal.world', 'world.bike'], heavy=True,
             about="Cairo's bike parts and M_Bike (/Game/Japan/Assets)"),
        Step('unreal.horses', [UnrealScript(SCRIPTS / 'import_horses.py', 'HORSES IMPORT COMPLETE')],
             inputs=horse_import_inputs(), after=['unreal.compile'], needs=['world.horses'],
             outputs=[out / 'horses' / 'unreal_import.json', GAME / 'unreal' / 'Content' / 'Data' / 'horses' / 'roster.json'],
             verify=lambda: horses_imported_present(out),
             heavy=True, about='the horse breeds, coats, tack sets and materials (/Game/Horses) and their roster'),
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
        Step('unreal.crater_cloud', [UnrealScript(SCRIPTS / 'crater_cloud_material.py', 'CRATER CLOUD MATERIAL COMPLETE')],
             inputs=[SCRIPTS / 'crater_cloud_material.py', SCRIPTS / 'atmosphere.py', SCRIPTS / 'sea_look.py'], after=['unreal.compile'],
             outputs=[GAME / 'unreal' / 'Content' / 'CraterPark' / 'Cloud' / f'{name}.uasset' for name in ('M_CraterCloud', 'M_CraterCloudVeil')],
             heavy=True, about="the cap cloud's translucent materials, plain and blurring veil (/Game/CraterPark/Cloud)"),
        Step('unreal.sounds', [
                UnrealScript(SCRIPTS / 'import_footsteps.py', 'FOOTSTEP IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_combat_audio.py', 'COMBAT AUDIO IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_skate_audio.py', 'SKATE AUDIO IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_bike_audio.py', 'BIKE AUDIO IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_transport_audio.py', 'TRANSPORT AUDIO IMPORT COMPLETE'),
                UnrealScript(SCRIPTS / 'import_driving_audio.py', 'DRIVING AUDIO IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_footsteps.py', SCRIPTS / 'import_combat_audio.py', SCRIPTS / 'import_skate_audio.py', SCRIPTS / 'import_bike_audio.py',
                     SCRIPTS / 'import_transport_audio.py', SCRIPTS / 'import_driving_audio.py'],
             # The footstep library lives in /Game/Japan, which the world import clears, so a world import reruns this.
             needs=['unreal.world', 'audio.footsteps', 'audio.combat', 'audio.skate', 'audio.kart', 'audio.bike', 'audio.transport'], heavy=True,
             about='footstep library, combat, skate, bike, transport and driving sounds'),
        Step('unreal.music', [UnrealScript(SCRIPTS / 'import_music.py', 'MUSIC IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / 'import_music.py', SCRIPTS / 'music_inventory.py', AUDIO / 'music' / 'prepare.py'],
             needs=['audio.music'], after=['unreal.compile'], explicit=True, heavy=True,
             outputs=[out / 'music_import.json', GAME / 'unreal/Content/Data/Music/library.json'],
             verify=lambda: music_import_present(out),
             about='/Game/Audio/Music from the optional fetched Suno library'),
        Step('unreal.fx', [UnrealScript(SCRIPTS / 'import_combat_fx.py', 'COMBAT FX IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_combat_fx.py'], after=['unreal.compile'], needs=['fx.textures'], heavy=True, about='/Game/FX materials'),
        Step('unreal.fox_hunter', [UnrealScript(SCRIPTS / 'import_fox_hunter.py', 'FOX HUNTER IMPORT COMPLETE')],
             inputs=[SCRIPTS / 'import_fox_hunter.py', SCRIPTS / 'animation_compression.py'],
             after=['unreal.world'], needs=['characters.fox_hunter'], heavy=True, about='/Game/FoxHunter'),
        *[step for character in definition.movers() for step in mover_import_steps(character, out)],
        # Character material overlays; shared world graphs belong to unreal.materials and the treehouse owns its graph.
        Step('unreal.see_through', [UnrealScript(SCRIPTS / 'import_see_through.py', 'SEE-THROUGH COMPLETE')],
             inputs=[SCRIPTS / 'import_see_through.py', SCRIPTS / 'see_through.py', PIPELINE / 'definition.py', *sorted(CHARS.glob('*/character.toml'))],
             needs=['unreal.world', *[f'unreal.{key(c)}' for c in definition.movers() if 'see_through' in c.toml]], heavy=True,
             about='camera see-through on playable character materials'),
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
             needs=['unreal.city_tree_cpu_access', 'world.city_tiles.meshes', 'world.city_trees.meshes'], heavy=True,
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
             inputs=[GAME / 'runtime_data.py', REGIONS / 'skatepark' / 'park.json', ASSETS / 'ui/fonts/atlas-serif.ttf',
                     runtime_data.RACING_COURSES, runtime_data.RACING_VALIDATOR, ASSETS / 'belmonte/source.json',
                     *runtime_data.courses.surface_inputs(),
                     *build_inputs.local_imports(runtime_data.courses.SOURCE_READER),
                     *(CHARS / 'portraits' / f'{c.id}.png' for c in definition.movers() if c.playable)],
             needs=['world.ferry_service', 'world.gondola_service', 'world.layout', 'world.hidamari', 'world.map', 'world.city_tiles', 'world.treehouse', 'world.megapark', 'world.craterpark', 'world.crater_cloud', 'world.belmonte', 'world.bike',
                    *[f'characters.{key(c)}_{kind}' for c in definition.movers() for kind, wanted in
                      (('bike', c.playable), ('grips', (GRIPS / c.id).is_dir())) if wanted]],
             outputs=[GAME / 'unreal' / 'Content' / 'Data' / rel for rel in staged(out)], about='runtime files into unreal/Content/Data'),
        racing_assets_step(out),
    ]


def racing_assets_step(out):
    """The racing service loads its runners by path (docs/RACING.md, "Horses"): fail before cooking when one is missing."""
    jockey = next(c for c in definition.movers() if c.game.get('default'))
    rig = racing_assets.default_rig(definition)
    return Step('data.racing_assets', [Call('racing_assets', lambda ctx, log: racing_assets.check(ctx.out, rig, log))],
                inputs=[TOOLS / 'racing_assets.py', GAME / 'unreal' / 'Config' / 'DefaultGame.ini', jockey.folder / 'character.toml'],
                needs=['unreal.horses', f'unreal.{key(jockey)}_horse'],
                outputs=[out / 'racing' / 'assets.json'],
                about='the racing breeds, coats, saddles and jockey clips: present and always cooked')


def gondola_steps(ctx):
    """@cc [owner:fontanierh,label:correctness] production-gondola-preparation
    Normal preparation MUST build every kit piece using canonical parameters,
    with soft failure disabled, and preserve closure, seating, rope-contact,
    level-floor, collision, walking and triangle-budget failures. Verified reuse
    MUST include every runtime mesh, collision mesh, texture and walking layout.
    """
    kit = ASSETS / 'vehicles/gondola'
    spec = importlib.util.spec_from_file_location('gondola_parameters', kit / 'params.py')
    parameters = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parameters)
    folder = ctx.out / 'gondola'
    files = [folder / name for name in parameters.product_files()]
    result = [Step('world.gondola_kit', [Blender(kit / 'build.py', threads=3, factory_startup=True,
                    env=(('GONDOLA_PIECES', 'cabin,towers,valley,rim,crater'),
                         ('GONDOLA_PARAMS', ''), ('GONDOLA_SOFT_FAIL', '')))],
                 inputs=sorted(set(local_imports(kit / 'build.py') + [kit / name for name in parameters.BUILD_SOURCES] + [WORLD/'walk_raster.py'])),
                 products=[Product('gondola.kit', tuple(files))], heavy=True, cache=True,
                 about='ropeway cabin, all tower heights and stations: closure, contact, level-floor and walk gates')]

    query = WORLD / 'gondola/inputs.py'
    query_spec = importlib.util.spec_from_file_location('gondola_world_inputs', query)
    queries = importlib.util.module_from_spec(query_spec)
    query_spec.loader.exec_module(queries)
    digest = ctx.out / 'digests/world.gondola.ground.json'
    result += [Step('world.gondola_ground_inputs',
                    [Call('ropeway final ground inputs', lambda ctx, log:
                          export_digest.record(digest, queries.snapshot(ctx.out), log))],
                    inputs=[*queries.CODE.values(), ASSETS / 'belmonte/source.json'],
                    needs=['world.hidamari', 'world.terrain.meshes', 'world.belmonte'],
                    deferred_inputs=[DeferredInputs('gondola-ground', queries.paths, (ctx.out,), support=(query,))],
                    outputs=[digest], cutoff=True,
                    about='only final terrain, North Trail and corridor-selected Belmonte ground'),
               Step('world.gondola_ground', [Blender(WORLD / 'gondola/probe.py', threads=3, factory_startup=True)],
                    inputs=[WORLD / 'gondola/probe.py', query, GAME / 'export_digest.py', REGIONS / 'belmonte/source.py',
                            paths.STUDIO / 'atelier/gltf.py', YORI],
                    needs=['world.gondola_ground_inputs'],
                    outputs=[folder / 'world/ground.npz', folder / 'world/ground.json'], heavy=True,
                    about='final exported trail contact and owned Belmonte terrain queries')]
    site_code = WORLD / 'gondola/validation.py'
    site_spec = importlib.util.spec_from_file_location('gondola_site_validation', site_code)
    validation = importlib.util.module_from_spec(site_spec)
    site_spec.loader.exec_module(validation)
    structure_code = WORLD / 'gondola/structures.py'
    structure_spec = importlib.util.spec_from_file_location('gondola_structure_inputs', structure_code)
    structures = importlib.util.module_from_spec(structure_spec)
    structure_spec.loader.exec_module(structures)
    structure_digest = ctx.out / 'digests/world.gondola.structures.json'
    result += [Step('world.gondola_structure_inputs',
                    [Call('ropeway final structure inputs', lambda ctx, log:
                          export_digest.record(structure_digest, structures.inputs(ctx.out), log))],
                    inputs=[*(paths.REPO / name for name in structures.CODE),
                            ctx.out / 'belmonte/runtime.json', ctx.out / 'belmonte/build-report.json'],
                    needs=['world.belmonte'],
                    deferred_inputs=[DeferredInputs('gondola-structures', structures.paths, (ctx.out,), support=(structure_code,))],
                    outputs=[structure_digest], cutoff=True,
                    about='collision-enabled Belmonte structures intersecting the ropeway footprint'),
               Step('world.gondola_structures', [Python(WORLD / 'gondola/structure_probe.py')],
                    inputs=[*(paths.REPO / name for name in structures.CODE), YORI],
                    needs=['world.gondola_structure_inputs'],
                    outputs=[folder / 'world/structures.npz', folder / 'world/structures.json'],
                    about='final instanced visual and actual complex collision geometry for ropeway clearance')]
    names = validation.network_layout().mesh_names()
    result.append(Step('world.gondola_site',
                       [Blender(REGIONS / 'gondola/site.py',threads=3,factory_startup=True)],
                       inputs=[*validation.SITE_CODE, *[kit/name for name in parameters.BUILD_SOURCES],
                               WORLD / 'solid_mesh.py', query, *craterpark_v4.input_paths(), YORI],
                       needs=['world.gondola_kit','world.gondola_ground','world.gondola_structures','world.craterpark_geometry','world.zeppelin'],
                       outputs=[folder/'world/site.json',*(folder/'world/assets'/f'{name}.fbx' for name in names)],
                       heavy=True,about='final station supports/access, exact rope paths and actual fitted-span contact gates'))
    service=WORLD/'gondola/service.py'
    result += [Step('world.gondola_service',[Python(service)],
                    inputs=[service,WORLD/'gondola/clock.py',WORLD/'gondola/inputs.py',*validation.SITE_CODE,YORI,kit/'params.py',kit/'rope.py'],
                    needs=['world.gondola_site'],outputs=[folder/'runtime.json'],
                    about='source-bound detachable cabin clocks and station boarding data'),
               Step('unreal.gondola',[UnrealScript(SCRIPTS/'import_gondola.py','GONDOLA IMPORT COMPLETE',null_rhi=True)],
                    inputs=[SCRIPTS/'import_gondola.py',SCRIPTS/'mesh_import.py',SCRIPTS/'mesh_materials.py',SCRIPTS/'material_assets.py',
                            service,WORLD/'gondola/clock.py',WORLD/'gondola/inputs.py',*validation.SITE_CODE,YORI,kit/'params.py',kit/'rope.py'],
                    needs=['world.gondola_service','unreal.world'],after=['unreal.compile'],heavy=True,
                    outputs=[folder/'import-report.json',
                             *(GAME/'unreal/Content/Gondola/Kit'/f'{name}.uasset' for name in parameters.asset_names()),
                             *(GAME/'unreal/Content/Gondola/World'/f'{name}.uasset' for name in names if not name.endswith(('_LOD1','_LOD2'))),
                             *(GAME/'unreal/Content/Gondola/Materials'/f'{name}.uasset' for name in parameters.MATERIALS),
                             *(GAME/'unreal/Content/Gondola/Textures'/f'{Path(name).stem}.uasset'
                               for name in parameters.product_files() if name.startswith('textures/'))],
                    about='complete ropeway kit, fitted supports/access and authored rope detail levels')]
    return result


def ferry_steps(ctx):
    """Approved ship and region-owned terminals through audited preparation, import and runtime data."""
    out = ctx.out
    kit = ASSETS / 'vehicles/ferry'
    terminal = kit / 'terminals'
    region = REGIONS / 'ferry'
    shared = [WORLD / 'solid_mesh.py', YORI]
    harbor_source = REGIONS / 'hidamari/ferry_source.py'
    layouts = [REGIONS / name / 'ferry_terminal.py' for name in ('hidamari', 'brinecove')]
    site_code = [terminal / 'site.py', terminal / 'world_probe.py', kit / 'build.py', region / 'route.py', *layouts, *shared]
    ship_names = ['FY_' + name for name in ('Hull', 'Superstructure', 'Funnel', 'Lifeboats', 'Rails', 'Masts', 'Fittings', 'BoardingGate', 'Collision')]
    terminal_names = ['FT_HD_' + name for name in ('Jetty', 'Stage', 'Brow', 'WaitingHouse', 'Timetable', 'Collision')]
    terminal_names += ['FT_BC_' + name for name in ('Landing', 'Brow', 'Pavilion', 'TicketHut', 'Fenders', 'Props', 'Collision')]
    return [
        Step('world.ferry_ship', [Blender(kit / 'build.py', threads=3), Python(kit / 'walk.py')],
             inputs=[kit / 'build.py', kit / 'walk.py', WORLD/'walk_raster.py', *shared],
             outputs=[out / 'ferry/manifest.json', out / 'ferry/deck_layout.json', out / 'ferry/review/walk_report.json',
                      out / 'ferry/assets/FY_ImportSeed.fbx',
                      *(out / 'ferry/assets' / f'{name}.fbx' for name in ship_names)], heavy=True,
             about='approved passenger ferry: closed meshes, seated fittings, collision and deck walk audits'),
        Step('world.ferry_probes', [Blender(terminal / 'world_probe.py', (str(out),), threads=3)],
             inputs=site_code,
             needs=['world.hidamari.city', 'world.brinecove.meshes', 'world.terrain.meshes', 'world.southwest', 'world.layout'],
             outputs=[out / 'ferry/terminals' / f'world_{name}.npz' for name in ('hidamari', 'brinecove', 'crossing')],
             heavy=True, about='final exported harbour and open-water geometry for the ferry sweeps'),
        Step('world.ferry_site', [Python(terminal / 'site.py')], inputs=site_code,
             needs=['world.ferry_probes'], outputs=[out / 'ferry/terminals/site.json'], heavy=True,
             about='the full hull and underwater envelope swept through both harbours and sea crossings'),
        Step('world.ferry_terminals', [Blender(terminal / 'build.py', threads=3)],
             inputs=[terminal / 'build.py', terminal / 'walkcheck.py', *site_code],
             needs=['world.ferry_ship', 'world.ferry_site'],
             outputs=[out / 'ferry/terminals/manifest.json', out / 'ferry/terminals/walk.json',
                      *(out / 'ferry/terminals/assets' / f'{name}.fbx' for name in terminal_names)],
             heavy=True, about='region-owned ferry terminals: grounded, carried, walkable, with moving brow collision'),
        Step('world.hidamari_ferry_cut', [Blender(REGIONS / 'hidamari/ferry_cut.py', threads=3)],
             inputs=[REGIONS / 'hidamari/ferry_cut.py', *site_code],
             needs=['world.ferry_site'],
             outputs=[out / 'hidamari/ferry/HD_Harbor.fbx', out / 'hidamari/ferry/cut.json'],
             heavy=True, about='Hidamari opens its quay rail and posts at the audited jetty root'),
        Step('world.ferry_service', [Python(region / 'service.py')],
             inputs=[region / 'service.py', region / 'timetable.py', harbor_source, terminal / 'walkcheck.py', kit / 'walk.py', WORLD/'walk_raster.py', *site_code],
             needs=['world.ferry_terminals', 'world.hidamari_ferry_cut'],
             outputs=[out / 'ferry/service/service.json'],
             about='one passenger ferry, a shared-clock two-way timetable, audited boarding walks and sounds'),
        Step('unreal.ferry', [UnrealScript(SCRIPTS / 'import_ferry.py', 'FERRY IMPORT COMPLETE', null_rhi=True)],
             inputs=[SCRIPTS / 'import_ferry.py', SCRIPTS / 'mesh_import.py',
                     region / 'service.py', region / 'timetable.py', harbor_source, terminal / 'walkcheck.py', kit / 'walk.py', WORLD/'walk_raster.py', *site_code],
             needs=['world.ferry_service', 'unreal.world'], after=['unreal.compile'],
             outputs=[out / 'ferry/import-report.json',
                      *(GAME / 'unreal/Content/Ferry/Ship' / f'{name}.uasset' for name in ship_names),
                      *(GAME / 'unreal/Content/Ferry/Terminals' / f'{name}.uasset' for name in terminal_names)],
             heavy=True, about='the audited ferry, fixed terminals, moving gangways and Hidamari harbour access'),
    ]


def steps(ctx):
    """Compose the recipe in its established order; packaging is explicit and optional sources remain optional."""
    ferry = ferry_steps(ctx)
    gondola = gondola_steps(ctx)
    result = (world_steps(ctx) + character_steps(ctx) + sound_effect_steps(ctx)
              + [step for step in ferry if not step.name.startswith('unreal.')]
              + [step for step in gondola if not step.name.startswith('unreal.')]
              + unreal_steps(ctx) + staging_steps(ctx) + adventure_steps(ctx.out) + hippodrome_steps(ctx.out) + belmonte_steps(ctx.out)[2:]
              + brinecove_steps(ctx.out)[2:] + [step for step in ferry if step.name.startswith('unreal.')]
              + [step for step in gondola if step.name.startswith('unreal.')])
    result += fit_steps(ctx.out, result)
    result += pawn_steps(result)
    # A step layered on the world brings the volcano with it: a targeted build that reimports the world reimports it too.
    for step in result:
        if 'unreal.world' in step.needs + step.after and step.name != 'unreal.north':
            step.after.append('unreal.north')
    # world.layout is a cutoff step, and the scripts behind it and its dependents import across regions (the volcano
    # reads Belmonte's terrain): each such step also hashes every module its scripts import.
    scanner = build_inputs.ImportScanner()
    for step in result:
        for command in step.commands:
            if isinstance(command, (Python, Blender)) and WORLD in Path(command.script).parents:
                step.inputs += [f for f in scanner.local_imports(command.script, (WORLD, REGIONS)) if f not in step.inputs]
        # Native geometry reuse hashes its complete native-only source closure.
        for command in step.commands:
            if not isinstance(command, UnrealScript):
                continue
            code = scanner.local_imports(command.script, (SCRIPTS, WORLD, REGIONS))
            if any('import_village.py' in file.read_text() for file in code):
                code = sorted(set(code + scanner.local_imports(SCRIPTS / 'import_village.py', (SCRIPTS, WORLD))))
            common_mesh = SCRIPTS / 'mesh_import.py' in code
            native_reuse = paths.STUDIO / 'atelier' / 'unreal_mesh_reuse.py' in code
            if common_mesh or native_reuse:
                step.inputs += [file for file in code if file not in step.inputs]
            if common_mesh:
                # Candidate staging is read-only metadata. Package adoption remains
                # per mesh, with current source/options/native validation.
                content_root = GAME / 'unreal' / 'Content'
                roots = {Path(output).parent for output in step.outputs
                         if Path(output).suffix == '.uasset' and Path(output).is_relative_to(content_root)}
                if step.name in {'unreal.world', 'unreal.north', 'unreal.southwest', 'unreal.kei', 'unreal.bike', 'unreal.forest'}:
                    roots.add(content_root / 'Japan' / 'Assets')
                roots = {root for root in roots if not any(other != root and other in root.parents for other in roots)}
                if roots:
                    step.candidate_scope = CandidateScope(directories=tuple(sorted(roots)))
        if step.name in ('unreal.belmonte', 'unreal.brinecove'):
            region = step.name.removeprefix('unreal.')
            namespace = {'belmonte': 'Belmonte', 'brinecove': 'Brinecove'}[region]
            step.candidate_scope = CandidateScope(
                files=(ctx.out / region / 'build-report.json', ctx.out / region / 'runtime.json'),
                directories=(GAME / 'unreal' / 'Content' / namespace / 'Meshes',))
        # Shorelines preserve natural cover from the committed railway geometry.
        rail_line = ASSETS / 'vehicles' / 'belmonte-train' / 'line.json'
        if WORLD / 'shorelines.py' in step.inputs and rail_line not in step.inputs:
            step.inputs.append(rail_line)
        # Scripts that import placement validate the raw geometry themselves. Its cutoff
        # covers their complete consumed landform, site and spawn values, after validating
        # current source provenance; render-only changes can therefore leave them current.
        if (craterpark_v4.selected() and REGIONS / 'craterpark' / 'placement.py' in step.inputs
                and step.name not in ('world.craterpark_geometry', 'world.craterpark', 'world.craterpark_layout')
                and 'world.craterpark_layout' not in step.needs):
            step.needs.append('world.craterpark_layout')
        if SCRIPTS / 'import_village.py' in step.inputs and SCRIPTS / 'mesh_import.py' not in step.inputs:
            step.inputs.append(SCRIPTS / 'mesh_import.py')
        if step.name in ('unreal.forest', 'unreal.treehouse', 'unreal.see_through'):
            step.reads.append('materials.shared')
    identity_spec = importlib.util.spec_from_file_location('yorimichi_network_identity', GAME / 'network_identity.py')
    identity = importlib.util.module_from_spec(identity_spec)
    identity_spec.loader.exec_module(identity)
    content = GAME / 'unreal' / 'Content'
    policy_spec = importlib.util.spec_from_file_location('yorimichi_content_policy', GAME / 'content_policy.py')
    policy = importlib.util.module_from_spec(policy_spec)
    policy_spec.loader.exec_module(policy)
    result.append(Step('data.content', [Call('archive_retired_content', policy.archive)],
                       inputs=[GAME / 'content_policy.py'],
                       deferred_inputs=[DeferredInputs(
                           'music-selectors', music_selector_members,
                           (os.environ.get('YORIMICHI_MUSIC_CATEGORIES', ''),
                            os.environ.get('YORIMICHI_MUSIC_STYLES', ''),
                            os.environ.get('YORIMICHI_MUSIC_GROUPS', ''),
                            os.environ.get('YORIMICHI_MUSIC_LIMIT', '0'),
                            policy.music_enabled()),
                           support=(GAME / 'build.py',))],
                       needs=[s.name for s in result if s.name.startswith('unreal.') and not s.explicit] + ['data.stage'],
                       outputs=[ctx.out / 'runtime-content.json'],
                       verify=lambda: not any(policy.retired(content)),
                       about='archive retired generated imports before multiplayer identity and cooking'))
    result.append(Step('data.network', [Call('network_identity', identity.stage)],
                       inputs=[GAME / 'network_identity.py', SOURCE, ctx.uproject, GAME / 'unreal/Config', GAME / 'unreal/Plugins',
                               paths.ENGINE_PLUGINS],
                       deferred_inputs=[DeferredInputs('content', identity.content_files, (content,),
                                                       support=(GAME / 'network_identity.py',))],
                       needs=[s.name for s in result if s.name.startswith('unreal.') and not s.explicit] + ['data.stage', 'data.content'],
                       outputs=[content / 'Data/Network/session.json'],
                       about='matching multiplayer code, imported assets and staged gameplay data'))
    return result + [cook_step(ctx, result), package_step(ctx, result)]
