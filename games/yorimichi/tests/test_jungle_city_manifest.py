"""Refreshes to the Jungle City manifest must retain validated model provenance."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "tools"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_refresh_keeps_models_and_replaces_stale_hashes(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(TOOLS))
    spec = importlib.util.spec_from_file_location(
        "jungle_city_manifest_test", TOOLS / "jungle_city_manifest.py"
    )
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    monkeypatch.setattr(tool, "LIBRARY", tmp_path)

    models = tmp_path / "models"
    models.mkdir()
    model = models / "hero_prang.glb"
    validation = models / "hero_prang.validation.json"
    model.write_bytes(b"validated glb")
    validation.write_text('{"passed": true}\n')
    (tmp_path / "source-manifest.json").write_text(json.dumps({
        "models": {
            "hero_prang": {
                "model": model.name,
                "model_sha256": "stale",
                "validation": validation.name,
                "validation_sha256": "stale",
            },
            "missing": {"model": "missing.glb", "validation": "missing.validation.json"},
        },
    }))

    tool.main()
    manifest = json.loads((tmp_path / "source-manifest.json").read_text())
    assert manifest["models"] == {
        "hero_prang": {
            "model": model.name,
            "model_sha256": sha256(model),
            "validation": validation.name,
            "validation_sha256": sha256(validation),
        }
    }
