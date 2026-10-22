"""Character definitions (assets/characters/<id>/character.toml, read by assets/characters/pipeline/definition.py): the
shared body export's settings for every character that plays the merged move set, and the names its build and imports
use."""
import importlib.util
from pathlib import Path

import pytest

CHARS = Path(__file__).resolve().parents[1] / 'assets' / 'characters'
spec = importlib.util.spec_from_file_location('character_definition', CHARS / 'pipeline' / 'definition.py')
definition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(definition)

# The names each mover's build steps, output folder and Unreal folder already use.
IDENTITIES = {
    'cairo': ('Cairo', 'cairo', '/Game/Cairo'),
    'modori': ('Modori', 'modori', '/Game/Modori'),
    'nox': ('Nox', 'nox', '/Game/Nox'),
    'sword-trainer': ('SwordTrainer', 'sword-trainer', '/Game/SwordTrainer'),
}


def test_every_definition_loads():
    for character in definition.ids():
        definition.load(character)


def test_the_movers_and_the_donor():
    movers = definition.movers()
    assert {c.id for c in movers} >= set(IDENTITIES)
    assert movers[0].donor and not any(c.donor for c in movers[1:]), 'one donor, first'


@pytest.mark.parametrize('character', sorted(IDENTITIES))
def test_identity(character):
    c = definition.load(character)
    assert (c.name, c.output, c.unreal_path) == IDENTITIES[character]


@pytest.mark.parametrize('character', [c.id for c in definition.movers()])
def test_a_mover_uses_the_shared_export(character):
    c = definition.load(character)
    assert c.exporter is None and not (c.folder / 'export_unreal.py').exists()
    assert c.source.exists() and c.height
    assert c.export['meshes'] in ('skinned', 'armature', 'outfit')
    assert c.export['measure'] in ('raw', 'evaluated', 'evaluated-faces')
    assert c.export['actions'] in ('discard', 'authored')
    assert c.export['mesh_names'], 'a mesh naming rule'
    hooks = c.folder / 'export_hooks.py'
    assert not hooks.exists() or 'def body(' in hooks.read_text()


def test_unknown_keys_are_refused(tmp_path):
    folder = tmp_path / 'someone'
    folder.mkdir()
    (folder / 'character.toml').write_text('id = "someone"\nsource = "Someone.glb"\nheight_cm = 170\n[export]\nname = "x"\n')
    with pytest.raises(AssertionError, match='unknown'):
        definition.load('someone', tmp_path)


@pytest.mark.parametrize('source, meshes, measure', [('New.glb', 'armature', 'raw'), ('New.blend', 'skinned', 'evaluated')])
def test_a_new_character_needs_only_its_source_and_height(tmp_path, source, meshes, measure):
    folder = tmp_path / 'new-one'
    folder.mkdir()
    (folder / 'character.toml').write_text(f'id = "new-one"\nsource = "{source}"\nheight_cm = 170\n')
    c = definition.load('new-one', tmp_path)
    assert (c.name, c.output, c.unreal_path, c.fps) == ('NewOne', 'new-one', '/Game/NewOne', 30)
    assert (c.export['meshes'], c.export['measure'], c.export['actions']) == (meshes, measure, 'discard')


def test_a_new_player_imports_with_the_import_modules_and_rides(tmp_path):
    folder = tmp_path / 'new-one'
    folder.mkdir()
    (folder / 'character.toml').write_text('id = "new-one"\nrole = "player"\nsource = "New.glb"\nheight_cm = 170\n')
    c = definition.load('new-one', tmp_path)
    assert c.playable and c.unreal['modules'] == ['YorimichiImport', 'YorimichiAssets'] and c.blender == {'threads': 4}
    (folder / 'character.toml').write_text('id = "new-one"\nrole = "npc"\nsource = "New.glb"\nheight_cm = 170\n[blender]\nfast = 1\n')
    with pytest.raises(AssertionError, match='unknown'):
        definition.load('new-one', tmp_path)


# Each player's pawn as its own C++ class had it: capsule radius, half height and crouched half height, bike rig,
# skating clothing clearance and hull directions, a leg-scaled sailboat, cloth teleport, hair spring and seat correctives.
PAWNS = {
    'cairo': (22, 74, 65, 'Cairo', 0, 256, False, None, ['head_Hair_fore', 'head_Hair_side'], ''),
    'modori': (24, 88, 77, 'Modori', 14, 256, True, [150, 60], [], ''),
    'nox': (24, 89, 77, 'Nox', 3, 1024, True, None, [], 'NoxSeat'),
    'paul': (24, 83, 73, 'Paul', 0, 256, False, None, [], ''),
}


@pytest.mark.parametrize('character', sorted(PAWNS))
def test_a_players_pawn_keeps_its_values(character):
    g = definition.load(character).game
    keys = ('capsule_radius', 'half_height', 'crouched_half_height', 'bike_rig', 'skate_clothing_clearance',
            'skate_hull_directions', 'leg_scaled_sailboat', 'cloth_teleport', 'hair_spring_morphs', 'seat_correctives')
    assert tuple(g[k] for k in keys) == PAWNS[character]


def test_one_player_is_the_default_and_every_name_is_unique():
    players = [c for c in definition.movers() if c.playable]
    assert set(PAWNS) <= {c.id for c in players}   # a new player is data only: no test lists them all
    assert [c.id for c in players if c.game['default']] == ['cairo'] and definition.load('cairo').game['aliases'] == ['CairoAdventure']
    names = [n for c in players for n in (c.toml['display_name'], *c.game['aliases'])]
    assert len(names) == len(set(names)) and len({c.pawn for c in players}) == len(players)


def test_a_new_players_pawn_comes_from_its_height(tmp_path):
    folder = tmp_path / 'new-one'
    folder.mkdir()
    (folder / 'character.toml').write_text('id = "new-one"\nsource = "New.glb"\nheight_cm = 171\n')
    g = definition.load('new-one', tmp_path).game
    assert (g['capsule_radius'], g['half_height'], g['crouched_half_height'], g['bike_rig'], g['default']) == (24, 86, 75, 'NewOne', False)


def test_every_mover_has_its_steps():
    from atelier.build import Context
    spec = importlib.util.spec_from_file_location('yorimichi_build', CHARS.parents[1] / 'build.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    steps = build.steps(Context('yorimichi'))
    names = [s.name for s in steps]
    for c in definition.movers():
        k = c.id.replace('-', '_')
        wanted = [f'characters.{k}', f'unreal.{k}', f'characters.{k}_adventure', f'unreal.{k}_adventure', f'characters.{k}_fit']
        wanted += [f'characters.{k}_bike', f'unreal.{k}_bike', f'unreal.{k}_pawn'] if c.playable else []
        assert set(wanted) <= set(names), (c.id, sorted(set(wanted) - set(names)))
        if c.playable:   # published only once everything it plays with is built and its fit gate passed
            pawn = next(s for s in steps if s.name == f'unreal.{k}_pawn')
            ready = {f'unreal.{k}_adventure', f'unreal.{k}_bike', f'characters.{k}_fit'} | ({f'characters.{k}_grips'} & set(names))
            assert ready <= set(pawn.needs) and any(str(o).endswith(f'BP_{c.name}.uasset') for o in pawn.outputs), c.id
    # Production orders the dependency graph; projection providers may be declared later.
    from atelier.build import order
    scheduled = order(steps, names)
    positions = {step.name: i for i, step in enumerate(scheduled)}
    for i, step in enumerate(scheduled):
        assert all(positions[n] < i for n in step.needs if n in positions), step.name
