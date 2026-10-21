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
    selected = {step.name for step in build.order(recipe.steps(ctx), ["browser.scene"])}
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
