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
    browser.stage_scene(SimpleNamespace(game="yorimichi"), io.StringIO())
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
