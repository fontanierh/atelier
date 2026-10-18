"""Promote one validated Jungle City hero GLB into the committed asset library."""

from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    parser.add_argument("model", type=Path)
    parser.add_argument("validation", type=Path)
    args = parser.parse_args()

    report = json.loads(args.validation.read_text())
    if not report.get("passed"):
        raise SystemExit("validation did not pass; refusing promotion")
    model = args.model.resolve()
    validation = args.validation.resolve()
    if model.suffix.lower() != ".glb":
        raise SystemExit("model must be a GLB")

    models = LIBRARY / "models"
    models.mkdir(parents=True, exist_ok=True)
    target_model = models / f"{args.slug}.glb"
    target_validation = models / f"{args.slug}.validation.json"
    target_model.write_bytes(model.read_bytes())
    target_validation.write_text(validation.read_text())

    manifest_path = LIBRARY / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.setdefault("models", {})[args.slug] = {
        "model": target_model.name,
        "model_sha256": sha256(target_model),
        "validation": target_validation.name,
        "validation_sha256": sha256(target_validation),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["models"][args.slug], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
