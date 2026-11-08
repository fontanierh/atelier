"""The V2 package's cook configuration (tools/package/cook_config.py): coverage of string-loaded roots, excluded
content, maps, and the Mac identity. The real-tree test is the regression for the committed config; the rest run on
a synthetic game so they do not depend on hydrated content."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'package'))
import cook_config  # noqa: E402


def make_game(tmp: Path, *, ini_entries=(), content=(), literals=(), restricted=(), maps=(), bundle='com.atelier.v2'):
    (tmp / 'unreal/Config/Mac').mkdir(parents=True)
    (tmp / 'unreal/Source').mkdir(parents=True)
    (tmp / 'unreal/Content').mkdir(parents=True)
    for rel in content:
        path = tmp / 'unreal/Content' / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('')
    (tmp / 'unreal/Source/code.cpp').write_text('\n'.join(f'auto p = TEXT("{lit}");' for lit in literals))
    (tmp / 'unreal/Config/DefaultGame.ini').write_text(
        '[/Script/UnrealEd.ProjectPackagingSettings]\n'
        + ''.join(f'+DirectoriesToAlwaysCook=(Path="{e}")\n' for e in ini_entries) + '; a comment\n')
    (tmp / 'unreal/Config/DefaultEngine.ini').write_text(
        '[/Script/EngineSettings.GameMapsSettings]\n' + ''.join(f'GameDefaultMap={m}\n' for m in maps[:1]))
    (tmp / 'game.toml').write_text('[play.play]\nargs = [' + ', '.join(f'"{m}"' for m in maps) + ']\n')
    (tmp / 'restricted.toml').write_text('schema = 1\nroots = [' + ', '.join(f'"{r}"' for r in restricted) + ']\n')
    if bundle is not None:
        (tmp / 'unreal/Config/Mac/MacEngine.ini').write_text(
            f'[/Script/MacTargetPlatform.MacTargetSettings]\nBundleIdentifier={bundle}\n')
    return tmp


def codes(found):
    return {(p.level, p.code, p.subject) for p in found}


def test_root_of_names_the_top_level_folder():
    assert cook_config.root_of('/Game/Japan/Assets/X.X') == 'Japan'
    assert cook_config.root_of('/Game/Racing/M_RacingTv.M_RacingTv') == 'Racing'
    assert cook_config.root_of('/Game/BelmonteTrack.') == 'BelmonteTrack'
    assert cook_config.root_of('/Game/...') is None
    assert cook_config.root_of('/Game/__ExternalActors__/x') is None


def test_string_loaded_root_must_be_always_cook(tmp_path):
    game = make_game(tmp_path / 'g', content=['Japan/Assets/a.uasset', 'FX/b.uasset'],
                     literals=['/Game/FX/MI_FX_Glow.MI_FX_Glow', '/Game/Japan/Assets/a.a'],
                     ini_entries=['/Game/Japan/Assets'], maps=['/Game/V2/Maps/Slice'])
    (game / 'unreal/Content/V2/Maps').mkdir(parents=True)
    (game / 'unreal/Content/V2/Maps/Slice.umap').write_text('')
    found = cook_config.problems(game)
    assert ('FAIL', 'NOT_ALWAYS_COOK', '/Game/FX') in codes(found)
    # a nested entry covers only its own folder, so the top-level Japan is still not covered
    assert ('FAIL', 'NOT_ALWAYS_COOK', '/Game/Japan') in codes(found)
    # V2 is named by GameDefaultMap in the engine config, so it is a loaded root too
    assert cook_config.render_missing(game) == ['+DirectoriesToAlwaysCook=(Path="/Game/FX")',
                                                '+DirectoriesToAlwaysCook=(Path="/Game/Japan")',
                                                '+DirectoriesToAlwaysCook=(Path="/Game/V2")']


def test_restricted_root_counts_as_content_when_absent(tmp_path):
    game = make_game(tmp_path / 'g', literals=['/Game/Audio/Combat/x.x'], restricted=['/Game/Audio'],
                     ini_entries=['/Game/Audio'], maps=[])
    assert not [p for p in cook_config.problems(game) if p.level == 'FAIL']


def test_write_missing_appends_once_and_keeps_existing(tmp_path):
    game = make_game(tmp_path / 'g', content=['Gondola/a.uasset'], literals=['/Game/Gondola/a.a'],
                     ini_entries=['/Game/Racing'], maps=[])
    assert cook_config.write_missing(game) == ['+DirectoriesToAlwaysCook=(Path="/Game/Gondola")']
    text = (game / 'unreal/Config/DefaultGame.ini').read_text()
    assert text.count('(Path="/Game/Racing")') == 1 and text.count('(Path="/Game/Gondola")') == 1
    assert cook_config.write_missing(game) == []


def test_excluded_feature_content_fails_but_phone_booths_do_not(tmp_path):
    game = make_game(tmp_path / 'g', content=['Japan/Kart/Car.uasset', 'Japan/Hidamari/HD_P_phone_booth.uasset'],
                     ini_entries=['/Game/Japan'], maps=[])
    hits = cook_config.excluded_hits(game)
    assert hits == ['Japan/Kart/Car.uasset']
    assert ('FAIL', 'EXCLUDED_CONTENT', 'Content/Japan/Kart/Car.uasset') in codes(cook_config.problems(game))


def test_missing_map_and_template_bundle_fail(tmp_path):
    game = make_game(tmp_path / 'g', maps=['/Game/MegaPark/Maps/SuperUltraMegaPark'], ini_entries=[],
                     bundle='com.YourCompany.YorimichiV2')
    found = codes(cook_config.problems(game))
    assert ('FAIL', 'MAP_MISSING', '/Game/MegaPark/Maps/SuperUltraMegaPark') in found
    assert any(code == 'BUNDLE_ID' for _, code, _ in found)


def test_real_tree_has_no_failures():
    """The committed V2 configuration: every string-loaded root cooked, no excluded content, maps present, V2 identity."""
    found = cook_config.problems(ROOT)
    assert [str(p) for p in found if p.level == 'FAIL'] == []
    assert cook_config.bundle_identifier(ROOT) == 'com.atelier.yorimichiv2'
    assert cook_config.render_missing(ROOT) == []
    assert {p.subject for p in found if p.code == 'UNKNOWN_ROOT'} <= {'/Game/A', '/Game/HidamariStable'}
