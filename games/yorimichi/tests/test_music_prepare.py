"""The optional music selector fails on a cached file that no longer matches its release lock."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from atelier import build

HERE = Path(__file__).resolve().parents[1] / "assets/audio/music"


def load():
    spec = importlib.util.spec_from_file_location("music_prepare_test", HERE / "prepare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepare_rejects_mutated_audio(tmp_path, monkeypatch):
    module = load()
    cache = tmp_path / "cache/yorimichi/music"
    cache.mkdir(parents=True)
    audio = cache / "variety/lofi_rain/track.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"original audio")
    catalog = {"library": "test", "tracks": [{
        "path": "variety/lofi_rain/track.mp3", "category": "calm", "style_family": "lofi",
        "group": "lofi_rain", "zone": "variety",
    }]}
    (cache / "catalog.json").write_text(json.dumps(catalog))
    lock = tmp_path / "music.lock.json"
    lock.write_text(json.dumps({"files": [{
        "path": catalog["tracks"][0]["path"], "bytes": len(b"original audio"),
        "sha256": hashlib.sha256(b"original audio").hexdigest(),
    }]}))
    monkeypatch.setattr(module, "CACHE", cache)
    monkeypatch.setattr(module, "LOCK", lock)
    monkeypatch.setattr(module, "OUT", tmp_path / "build/manifest.json")
    monkeypatch.setattr(sys, "argv", ["prepare.py", "--categories", "calm"])
    module.main()
    assert (tmp_path / "build/manifest.json").exists()

    audio.write_bytes(b"original audiO")
    with pytest.raises(SystemExit, match="checksum"):
        module.main()


def test_recipe_collector_selects_cached_bytes(tmp_path):
    cache = tmp_path / "cache"
    (cache / "variety/calm").mkdir(parents=True)
    calm = cache / "variety/calm/calm.mp3"
    action = cache / "variety/action/action.mp3"
    action.parent.mkdir(parents=True)
    calm.write_bytes(b"calm")
    action.write_bytes(b"action")
    (cache / "catalog.json").write_text(json.dumps({"tracks": [
        {"path": "variety/calm/calm.mp3", "category": "calm", "style_family": "lofi",
         "group": "calm", "zone": "variety"},
        {"path": "variety/action/action.mp3", "category": "action", "style_family": "energy",
         "group": "action", "zone": "variety"},
    ]}))
    recipe = build.load_recipe("yorimichi")
    assert recipe.music_files(cache, "calm", "", "", 0) == (calm,)
    assert recipe.music_files(cache, "", "energy", "", 0) == (action,)


def test_full_import_followed_by_narrow_selection_removes_only_old_music():
    spec = importlib.util.spec_from_file_location(
        "music_inventory_test", HERE.parents[2] / "unreal/Scripts/music_inventory.py")
    inventory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inventory)
    music = "/Game/Audio/Music/variety/lofi_rain/MUS_variety_lofi_rain_1234"
    other = "/Game/Audio/Music/variety/energy_dnb/MUS_variety_energy_dnb_5678"
    combat = "/Game/Audio/Combat/hit_body/hit_body_01"
    assert inventory.stale_assets([music + "." + music.rsplit("/", 1)[-1], other, combat], {music}) == (other,)
