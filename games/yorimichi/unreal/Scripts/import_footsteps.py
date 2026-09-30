"""Import the sliced footstep one-shots and build the library the game reads.

    "$UE/Engine/Binaries/Mac/UnrealEditor-Cmd" "$PROJ/Yorimichi.uproject" \
        -run=pythonscript -script="$PROJ/Scripts/import_footsteps.py" -unattended -nop4 -nosplash

Source: build/yorimichi/audio/footsteps/<surface>/*.wav, produced by games/yorimichi/assets/audio/footsteps/slice.py from
the Sonniss GDC masters. Builds:

    /Game/Japan/Audio/Footsteps/<surface>/...   the SoundWaves
    /Game/Japan/Audio/A_Footstep                shared attenuation
    /Game/Japan/Audio/DA_Footsteps              UJapanFootstepSet, loaded by the character

Re-running is safe: existing waves are replaced in place and the data asset is rewritten.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
from pathlib import Path
import unreal as U

ROOT = yori.OUT
SOURCE = ROOT / 'audio' / 'footsteps'
DEST = '/Game/Japan/Audio'
E = U.EditorAssetLibrary
AT = U.AssetToolsHelpers.get_asset_tools()

# Painterly material name (MI_ stripped) -> surface pool. The slot names come from the Blender
# builders; anything unmapped falls back to the terrain default.
MATERIAL_SURFACES = {
    'Ground': 'grass', 'Hills': 'grass', 'Grass': 'grass', 'Moss': 'grass',
    'FarForest': 'grass', 'Flower': 'grass',
    'Road': 'dirt_gravel', 'Lane': 'dirt_gravel', 'Sand': 'dirt_gravel', 'Dirt': 'dirt_gravel',
    'Stone': 'stone', 'Rock': 'stone', 'Concrete': 'stone', 'Tile': 'stone',
    'Plaster': 'stone', 'Paint': 'stone', 'Metal': 'stone', 'RoofTile': 'stone',
    'Wood': 'wood', 'Lattice': 'wood', 'Bark': 'wood', 'Vermilion': 'wood',
    'Water': 'mud_water', 'Mud': 'mud_water',
    'Tatami': 'barefoot',
    # Foliage rarely has collision, but the litter and leaf cards read as forest floor if it does.
    'Litter': 'leaves', 'LeafBroad': 'leaves', 'LeafCedar': 'leaves', 'LeafPine': 'leaves',
    'LeafOchre': 'leaves', 'LeafMaple': 'leaves', 'LeafGinkgo': 'leaves', 'LeafSmall': 'leaves',
    # The tree house (import_treehouse.py): one MI_TH_<slot> per texture slug.
    'TH_wood_plank': 'wood', 'TH_wood_timber': 'wood', 'TH_wood_pale': 'wood', 'TH_bark': 'wood', 'TH_hull': 'wood',
    'TH_shingle': 'wood', 'TH_rope': 'wood', 'TH_stone': 'stone', 'TH_tile': 'stone', 'TH_plaster': 'stone',
    'TH_moss': 'grass', 'TH_straw': 'leaves', 'TH_rug': 'barefoot', 'TH_rug_blue': 'barefoot', 'TH_cushion': 'barefoot',
    'TH_quilt': 'barefoot',
}


def log(message):
    U.log(f'[footsteps] {message}')


def asset(name, cls, factory, path=DEST):
    full = f'{path}/{name}'
    return E.load_asset(full) if E.does_asset_exist(full) else AT.create_asset(name, path, cls, factory)


def import_surface(surface, files):
    """Import one surface's WAVs in a single batch and return the SoundWaves."""
    folder = f'{DEST}/Footsteps/{surface}'
    E.make_directory(folder)
    tasks = []
    for wav in files:
        task = U.AssetImportTask()
        for key, value in dict(filename=str(wav), destination_path=folder, destination_name=wav.stem,
                               automated=True, replace_existing=True, save=True).items():
            task.set_editor_property(key, value)
        task.set_editor_property('factory', U.SoundFactory())
        tasks.append(task)
    AT.import_asset_tasks(tasks)

    waves = []
    for task in tasks:
        for path in task.get_editor_property('imported_object_paths'):
            wave = E.load_asset(path)
            if not isinstance(wave, U.SoundWave):
                continue
            # One-shots: never loop, never stream, and cheap enough to stay resident.
            for key, value in dict(looping=False, streaming=False).items():
                try:
                    wave.set_editor_property(key, value)
                except Exception:
                    pass
            E.save_loaded_asset(wave, only_if_is_dirty=False)
            waves.append(wave)
    return waves


def build_attenuation():
    """Footsteps are small and close: audible across a courtyard, gone across a field."""
    attenuation = asset('A_Footstep', U.SoundAttenuation, U.SoundAttenuationFactory())
    settings = attenuation.get_editor_property('attenuation')
    for key, value in dict(attenuation_shape=U.AttenuationShape.SPHERE,
                           falloff_distance=2600.,
                           attenuation_shape_extents=U.Vector(350., 0., 0.),
                           distance_algorithm=U.AttenuationDistanceModel.NATURAL_SOUND,
                           db_attenuation_at_max=-60.,
                           enable_occlusion=False,
                           spatialization_algorithm=U.SoundSpatializationAlgorithm.SPATIALIZATION_DEFAULT).items():
        try:
            settings.set_editor_property(key, value)
        except Exception as error:
            log(f'  attenuation {key} skipped: {error}')
    attenuation.set_editor_property('attenuation', settings)
    E.save_loaded_asset(attenuation)
    return attenuation


def main():
    if not SOURCE.is_dir():
        raise SystemExit(f'no sliced footsteps at {SOURCE} - run `atelier build yorimichi audio` first')
    E.make_directory(DEST)

    surfaces, report = {}, {}
    for folder in sorted(p for p in SOURCE.iterdir() if p.is_dir() and p.name != 'preview'):
        files = sorted(folder.glob('*.wav'))
        if not files:
            continue
        waves = import_surface(folder.name, files)
        log(f'{folder.name}: {len(waves)}/{len(files)} one-shots')
        if len(waves) != len(files):
            raise SystemExit(f'{folder.name}: imported {len(waves)} of {len(files)} files')
        surfaces[folder.name] = U.JapanFootstepBank(steps=waves)
        report[folder.name] = len(waves)

    if not surfaces:
        raise SystemExit(f'{SOURCE} has no surface folders')

    factory = U.DataAssetFactory()
    factory.set_editor_property('data_asset_class', U.JapanFootstepSet)
    library = asset('DA_Footsteps', U.JapanFootstepSet, factory)
    for key, value in dict(surfaces=surfaces,
                           material_surfaces={k: U.Name(v) for k, v in MATERIAL_SURFACES.items()},
                           attenuation=build_attenuation(),
                           default_surface=U.Name('grass'),
                           canopy_surface=U.Name('leaves')).items():
        library.set_editor_property(key, value)
    E.save_loaded_asset(library)

    (ROOT / 'footsteps_import.json').write_text(
        json.dumps({'surfaces': report, 'total': sum(report.values()),
                    'library': library.get_path_name()}, indent=2) + '\n')
    log(f'{sum(report.values())} one-shots across {len(report)} surfaces -> {library.get_path_name()}')
    U.log('FOOTSTEP IMPORT COMPLETE')


main()
