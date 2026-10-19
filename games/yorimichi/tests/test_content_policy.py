"""Incremental checkouts archive retired imports before cooking and keep current source data intact."""
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('content_policy', Path(__file__).resolve().parents[1] / 'content_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def test_archive_moves_old_imports_and_preserves_current_data(tmp_path):
    ctx = SimpleNamespace(game_dir=tmp_path / 'game', out=tmp_path / 'build')
    content = ctx.game_dir / 'unreal/Content'
    active = ['Adventure/Reference/A_Idle.uasset', 'Belmonte/Meshes/SM_BM_NorthApron.uasset',
              'Data/belmonte/runtime.json', 'CairoAdventure/DA_CairoAdventure.uasset',
              'Cairo/SK_Cairo.uasset', 'Cairo/DA_CairoBase.uasset', 'Cairo/A_DoubleJump.uasset', 'Cairo/A_Wave.uasset',
              'Cairo/A_SwordParry.uasset', 'Cairo/M_CairoOutfit.uasset', 'Cairo/Textures/T_M_Cairo.uasset',
              'Modori/Adventure/A_Run.uasset', 'Modori/Textures/coat.uasset', 'Modori/PA_Modori_Cloth.uasset',
              'SwordTrainer/Adventure/A_Run.uasset', 'SwordTrainer/A_Bow.uasset', 'SwordTrainer/Textures/body.uasset',
              'Data/SkateRide/clips.json', 'Data/cairo/adventure.json', 'Data/cairo/portrait.png',
              'Data/hippodrome/hippodrome.json',
              'Audio/Skate/roll.uasset', 'SkateMotion/MotionData.uasset', 'SkateMotion/Banks/Bank_000.uasset',
              'SkateRuntime/RuntimeData.uasset', 'Nox/SK_Nox.uasset', 'Nox/Adventure/A_Run.uasset',
              'Nox/Textures/T_Nox_Head.uasset', 'NoxBike/A_Ride.uasset',
              'Data/nox/adventure.json', 'Data/nox/bike/export.json',
              'Paul/SK_Paul.uasset', 'Paul/Adventure/A_Run.uasset',
              'Paul/Textures/T_M_Paul_0.uasset', 'PaulBike/A_Ride.uasset',
              'Data/paul/adventure.json', 'Data/paul/portrait.png', 'Data/paul/bike/export.json',
              'Horses/M_HorseCoat.uasset', 'Horses/Arabian/SK_Horse_Arabian.uasset', 'Horses/Coats/Masks/T_Coat_Solid_Mask.uasset',
              'CairoHorse/A_HorseIdle.uasset', 'NoxHorse/A_HorseWalk.uasset', 'PaulHorse/A_HorseMount.uasset',
              'Data/horses/roster.json',
              'SwordCamp/Assets/SM_RoninKatana.uasset']
    old = ['RetiredCharacter/mesh.uasset', 'Data/retired-roster/roster.json',
           'Cairo/A_Roll.uasset', 'Cairo/A_DashGround.uasset', 'Cairo/A_SwordAttack1.uasset',
           'Cairo/BS_Locomotion.uasset', 'Cairo/DA_Cairo.uasset', 'Cairo/SM_Bokken.uasset',
           'Cairo/M_Bokken_Wood.uasset', 'Cairo/Textures/T_M_Bokken_Wood.uasset',
           'Modori/RetiredMoves/A_Run.uasset', 'SwordTrainer/RetiredMoves/A_Idle.uasset',
           'Data/cairo/old-moves.json', 'Data/hippodrome/charts.json', 'Audio/RetiredActivity/song.uasset',
           # world.horses' build manifest is no longer staged: the roster carries the contacts.
           'Data/horses/manifest.json', 'Data/horses/old-roster.json',
           # nor are the riders' horse reports: the game reads none of them.
           'Data/cairo/horse/export.json', 'Data/nox/horse/export.json']
    for relative in active + old:
        path = content / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    ctx.out.mkdir()
    policy.archive(ctx, io.StringIO())
    assert not list(policy.retired(content))
    for relative in active:
        assert (content / relative).read_bytes() == relative.encode()
    for relative in old:
        assert not (content / relative).exists()
        copies = list((ctx.out / 'retired-content').glob('*/' + relative))
        assert len(copies) == 1 and copies[0].read_bytes() == relative.encode()


def test_optional_music_survives_only_when_a_selector_enables_it(tmp_path, monkeypatch):
    content = tmp_path / 'game' / 'unreal/Content'
    track = content / 'Audio/Music/lofi_rain/Rainy Window.uasset'
    metadata = content / 'Data/Music/library.json'
    for path in (track, metadata):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'music')
    for name in ('YORIMICHI_MUSIC', 'YORIMICHI_MUSIC_CATEGORIES', 'YORIMICHI_MUSIC_STYLES',
                 'YORIMICHI_MUSIC_GROUPS', 'YORIMICHI_MUSIC_LIMIT'):
        monkeypatch.delenv(name, raising=False)
    assert set(policy.retired(content)) == {content / 'Audio/Music', content / 'Data/Music'}
    monkeypatch.setenv('YORIMICHI_MUSIC_CATEGORIES', 'calm')
    assert not list(policy.retired(content))
