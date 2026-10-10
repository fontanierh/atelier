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
    active = ['Adventure/Reference/A_Idle.uasset', 'CairoAdventure/DA_CairoAdventure.uasset',
              'Cairo/SK_Cairo.uasset', 'Cairo/DA_CairoBase.uasset', 'Cairo/A_DoubleJump.uasset', 'Cairo/A_Wave.uasset',
              'Cairo/A_SwordParry.uasset', 'Cairo/M_CairoOutfit.uasset', 'Cairo/Textures/T_M_Cairo.uasset',
              'Modori/Adventure/A_Run.uasset', 'Modori/Textures/coat.uasset', 'Modori/PA_Modori_Cloth.uasset',
              'SwordTrainer/Adventure/A_Run.uasset', 'SwordTrainer/A_Bow.uasset', 'SwordTrainer/Textures/body.uasset',
              'Data/SkateRide/clips.json', 'Data/cairo/adventure.json', 'Data/hippodrome/hippodrome.json',
              'Audio/Skate/roll.uasset', 'SkateMotion/MotionData.uasset', 'SkateMotion/Banks/Bank_000.uasset',
              'SkateRuntime/RuntimeData.uasset']
    old = ['RetiredCharacter/mesh.uasset', 'Data/retired-roster/roster.json',
           'Cairo/A_Roll.uasset', 'Cairo/A_DashGround.uasset', 'Cairo/A_SwordAttack1.uasset',
           'Cairo/BS_Locomotion.uasset', 'Cairo/DA_Cairo.uasset', 'Cairo/SM_Bokken.uasset',
           'Cairo/M_Bokken_Wood.uasset', 'Cairo/Textures/T_M_Bokken_Wood.uasset',
           'Modori/RetiredMoves/A_Run.uasset', 'SwordTrainer/RetiredMoves/A_Idle.uasset',
           'Data/cairo/old-moves.json', 'Data/hippodrome/charts.json', 'Audio/RetiredActivity/song.uasset']
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
