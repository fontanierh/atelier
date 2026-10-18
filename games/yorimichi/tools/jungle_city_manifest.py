"""Write the committed Jungle City source manifest for reviewed images and models."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
LIBRARY = REPO / "games/yorimichi/assets/jungle_city"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def records(folder: Path) -> dict[str, dict[str, str]]:
    result = {}
    for image in sorted(folder.glob("*.jpg")):
        provenance = image.with_suffix(".provenance.json")
        result[image.name] = {
            "sha256": sha256(image),
            "provenance": provenance.name if provenance.is_file() else "",
        }
    return result


def main() -> int:
    manifest = {
        "schema": 1,
        "name": "Jungle City unplaced proposal asset sources",
        "status": "review-only; no Unreal placement",
        "references": records(LIBRARY / "references"),
        "textures": records(LIBRARY / "textures"),
        "models": {},
        "generator": "games/yorimichi/tools/jungle_city_manifest.py",
    }
    (LIBRARY / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"references": len(manifest["references"]), "textures": len(manifest["textures"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
