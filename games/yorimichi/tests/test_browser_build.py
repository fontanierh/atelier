"""The browser scene must bring its complete bounded dependencies, not the island."""

import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

from atelier import build

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browser_build", GAME / "browser_build.py"
)
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)


def test_browser_scene_keeps_riding_geometry_and_rails(tmp_path, monkeypatch):
    data = tmp_path / "Data"
    (data / "cairo").mkdir(parents=True)
    monkeypatch.setattr(browser.paths, "content_data", lambda game: data)
    browser.stage_scene(SimpleNamespace(game="yorimichi", out=tmp_path), io.StringIO())
    source = json.loads(browser.PARK.read_text())
    staged = json.loads((data / "Browser/park.json").read_text())
    assert staged == {k: v for k, v in source.items() if k != "trees"}
    assert staged["meshes"] and staged["rails"]
    assert json.loads((data / "Browser/scene-source.json").read_text()) == {
        "version": 1,
        "profile": "skate-pier",
        "required_assets": [],
    }
    assert (data / "cairo/portrait.png").read_bytes() == (
        GAME / "assets/characters/portraits/cairo.png"
    ).read_bytes()
    config = (tmp_path / 'browser/CookGame.ini').read_text()
    assert '[/Script/AtelierSkate.SkateSettings]' in config
    assert config.index('!DirectoriesToAlwaysCook=ClearArray') > config.index('/Game/Belmonte')
    assert '+DirectoriesToAlwaysCook=(Path="/Game/CairoAdventure")' in config


def test_browser_scene_graph_is_bounded_but_includes_production_preparation(tmp_path):
    ctx = SimpleNamespace(
        out=tmp_path, game="yorimichi", uproject=GAME / "unreal/Yorimichi.uproject"
    )
    recipe = build.load_recipe("yorimichi")
    ordered = build.order(recipe.steps(ctx), ["browser.scene"])
    selected = {step.name for step in ordered}
    assert all(
        command.threads <= 3
        for step in ordered
        for command in step.commands
        if isinstance(command, build.Blender)
    )
    assert {
        "unreal.cairo_pawn",
        "characters.cairo_fit",
        "world.skatepark",
        "unreal.skatepark",
        "unreal.skate_data",
        "unreal.skate_board",
        "unreal.materials",
        "audio.footsteps",
        "audio.skate",
        "audio.combat",
        "browser.data",
        "browser.audio",
    } <= selected
    assert selected.isdisjoint(
        {
            "unreal.world",
            "unreal.north",
            "data.stage",
            "unreal.horses",
            "world.hidamari.city",
            "unreal.modori_pawn",
            "unreal.skate_clips",
        }
    )


def test_preview_requires_the_complete_project_archive(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "browser_preview", GAME / "tools/browser_preview.py"
    )
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    import pytest

    with pytest.raises(RuntimeError, match="complete browser archive"):
        preview.package_page(tmp_path)
    page = tmp_path / "Yorimichi/Binaries/HTML5/Yorimichi.html"
    page.parent.mkdir(parents=True)
    page.write_text("<canvas></canvas>")
    (tmp_path / "HTML5Content.txt").write_text("# test\n")
    with pytest.raises(RuntimeError, match="Wasm module or loader"):
        preview.package_page(tmp_path)
    page.with_suffix(".wasm").write_bytes(b"\0asm\x01\0\0\0")
    page.with_suffix(".js").write_text("")
    assert preview.package_page(tmp_path) == "Yorimichi/Binaries/HTML5/Yorimichi.html"


def test_local_browser_stamp_rejects_changed_wasm_link_and_policy(
    tmp_path, monkeypatch
):
    import hashlib

    game = tmp_path / "game"
    tools = tmp_path / "plugins/Activities/Skate/Tools"
    tools.mkdir(parents=True)
    policy = hashlib.sha256()
    for name in ("prepare_wasm.py", "wasm_float.py", "wasm_float_helpers.py"):
        (tools / name).write_text(name + "\n")
        policy.update(name.encode() + b"\0" + (name + "\n").encode())
    monkeypatch.setattr(browser, "GAME", game)
    monkeypatch.setattr(browser.paths, "ENGINE_PLUGINS", tmp_path / "plugins")
    binary = game / "unreal/Binaries/HTML5/Yorimichi.wasm"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"\0asm\x01\0\0\0")
    manifest = binary.with_suffix(".html5link.json")
    manifest.write_bytes(b"link")
    ctx = SimpleNamespace(out=tmp_path / "build")
    report = ctx.out / "browser-float/Yorimichi/latest.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            dict(
                policy_sha256=policy.hexdigest(),
                output_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                link_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
            )
        )
    )
    assert browser.prepared_present(ctx)
    binary.write_bytes(b"corrupted")
    assert not browser.prepared_present(ctx)
    binary.write_bytes(b"\0asm\x01\0\0\0")
    manifest.write_bytes(b"changed link")
    assert not browser.prepared_present(ctx)
    manifest.write_bytes(b"link")
    (tools / "wasm_float.py").write_text("changed arithmetic policy")
    assert not browser.prepared_present(ctx)


def test_pier_helpers_invalidate_the_import(tmp_path, monkeypatch):
    from test_mega_ramp_layers import changed_by

    for name in ('import_village.py', 'mesh_import.py'):
        changed = changed_by(GAME / 'unreal/Scripts' / name, tmp_path, monkeypatch)
        assert 'unreal.skatepark' in changed


def test_browser_package_forwards_tracked_cook_mode_and_log_root(tmp_path):
    from atelier.build_cook import CookMode

    engine = tmp_path / 'engine'
    version = engine / 'Engine/Build/Build.version'
    version.parent.mkdir(parents=True)
    version.write_text('{"MajorVersion":5,"MinorVersion":8}')
    ctx = SimpleNamespace(unreal_root=engine, unreal_cmd=engine / 'Editor',
                          uproject=tmp_path / 'Game.uproject', out=tmp_path / 'out')
    for mode, flag in ((CookMode.DEFAULT, None), (CookMode.FULL, '-fullcook'),
                       (CookMode.INCREMENTAL, '-cookincremental')):
        command = browser.BrowserPackage('Yorimichi', tmp_path / 'archive', cook_mode=mode)
        args = command.argv(ctx)
        options = [a for a in args if a.startswith('-AdditionalCookerOptions=')]
        assert len(options) == 1 and '-nullrhi' in options[0]
        assert str(ctx.out / 'browser/file-open') in options[0]
        assert '-DEFGameIni=' in options[0] and str(ctx.out / 'browser/CookGame.ini') in options[0]
        assert '-NoDefaultMaps' in options[0]
        if flag:
            assert flag in options[0] and '-Cook.DependencyTracking=1' in options[0]
        assert '-cookall' not in args


def test_browser_package_tracks_compiled_bytes_at_an_unchanged_source_key(tmp_path):
    ctx = SimpleNamespace(out=tmp_path, uproject=GAME / 'unreal/Yorimichi.uproject')
    commands = {s.name: s for s in browser.steps(ctx)}
    assert commands['browser.compile'].products[0].name == 'browser.binary'
    package = commands['browser.package']
    done = {'browser.compile': 'same-source', 'browser.scene': 'same-scene',
            'product:browser.binary': 'a' * 64, 'product:materials.shared': 'c' * 64}
    for product in ('browser.binary', 'materials.shared'):
        before = build.fingerprint(package, done)
        done['product:' + product] = 'b' * 64
        assert build.fingerprint(package, done) != before


def audio_fixture(tmp_path, monkeypatch):
    game, out = tmp_path / 'game', tmp_path / 'build'
    monkeypatch.setattr(browser, 'GAME', game)
    for bank in ('footsteps', 'combat', 'skate'):
        root = out / 'audio' / bank
        wave_files = []
        for index in range(3):
            wave = root / 'surface' / f'cue_{index}.wav'
            wave.parent.mkdir(parents=True, exist_ok=True)
            wave.write_bytes(b'prepared wave')
            wave_files.append(wave)
        rows = [{'file': p.relative_to(root if bank == 'combat' else out).as_posix()} for p in wave_files]
        (root / 'manifest.json').write_text(json.dumps({'loops': ['surface'], 'cues': {'surface': rows}} if bank == 'skate' else rows))
        dest = game / 'unreal/Content' / ('Japan/Audio/Footsteps/surface' if bank == 'footsteps' else 'Audio/' + bank.title())
        dest.mkdir(parents=True)
        for wave in wave_files:
            (dest / (wave.stem + '.uasset')).write_bytes(b'native imported wave')
    for name in ('DA_Footsteps', 'A_Footstep'):
        (game / 'unreal/Content/Japan/Audio' / (name + '.uasset')).write_bytes(b'native footstep asset')
    ctx = SimpleNamespace(out=out)
    browser.record_audio(ctx, io.StringIO())
    assert browser.audio_present(ctx)
    return ctx, game / 'unreal/Content'


def test_browser_audio_rejects_missing_middle_wave_in_every_bank(tmp_path, monkeypatch):
    ctx, content = audio_fixture(tmp_path, monkeypatch)
    for folder in ('Japan/Audio/Footsteps/surface', 'Audio/Combat', 'Audio/Skate'):
        wave = content / folder / 'cue_1.uasset'
        saved = wave.read_bytes()
        wave.unlink()
        assert not browser.audio_present(ctx)
        wave.write_bytes(saved)
        assert browser.audio_present(ctx)


def test_browser_audio_rejects_corruption_sidecar_changes_and_links(tmp_path, monkeypatch):
    ctx, content = audio_fixture(tmp_path, monkeypatch)
    wave = content / 'Audio/Skate/cue_1.uasset'
    wave.write_bytes(b'corrupt package')
    assert not browser.audio_present(ctx)
    wave.write_bytes(b'native imported wave')
    sidecar = wave.with_suffix('.ubulk')
    sidecar.write_bytes(b'bulk')
    assert not browser.audio_present(ctx)
    browser.record_audio(ctx, io.StringIO())
    sidecar.unlink()
    assert not browser.audio_present(ctx)
    sidecar.write_bytes(b'bulk')
    assert browser.audio_present(ctx)
    wave.unlink()
    wave.symlink_to(content / 'Audio/Skate/cue_0.uasset')
    assert not browser.audio_present(ctx)


def test_browser_audio_rejects_changed_or_incomplete_prepared_sources(tmp_path, monkeypatch):
    import pytest

    ctx, _ = audio_fixture(tmp_path, monkeypatch)
    wave = ctx.out / 'audio/footsteps/surface/cue_1.wav'
    wave.write_bytes(b'changed source')
    assert not browser.audio_present(ctx)
    wave.unlink()
    with pytest.raises(ValueError, match='differs from its manifest'):
        browser.record_audio(ctx, io.StringIO())
    assert not browser.audio_present(ctx)
