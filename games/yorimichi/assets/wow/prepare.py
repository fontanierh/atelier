"""Prepare portable views of a completed pack, run under Atelier's memory guard."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from catalogue import build_catalogues, verify_pack
from glb import export_m2, vector
from pipeline import write_json


def obj(value: dict, destination: Path) -> None:
    if value["kind"] == "wmo_group":
        meshes = [(value["positions"], value["indices"])]
    elif value["kind"] == "adt":
        meshes = [(c["positions"], c["indices"]) for c in value["chunks"]]
    else:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial")
    with temporary.open("w") as stream:
        stream.write("# Offline geometry view, metres, RH Y-up; materials/placements in neutral JSON\n")
        offset = 1
        for index, (positions, indices) in enumerate(meshes):
            if len(indices) % 3 or any(i < 0 or i >= len(positions) for i in indices):
                raise ValueError("Invalid world mesh indices")
            stream.write(f"o section_{index}\n")
            for position in positions:
                x, y, z = vector(position)
                stream.write(f"v {x:.9g} {y:.9g} {z:.9g}\n")
            for i in range(0, len(indices), 3):
                a, b, c = (v + offset for v in indices[i:i + 3])
                stream.write(f"f {a} {b} {c}\n")
            offset += len(positions)
    temporary.replace(destination)


def prepare(output: Path) -> None:
    pack = output / "pack"
    verify_pack(pack)
    profile = json.loads((output / "input-provenance.json").read_text())["profile"]
    build_catalogues(pack, profile)
    manifest = json.loads((pack / "manifest.json").read_text())
    exports, unsupported, geometry = [], [], []
    for asset in manifest["assets"]:
        decoded = asset.get("decoded")
        if not decoded or not decoded.endswith(".json"):
            continue
        value = json.loads((pack / decoded).read_text())
        if value["kind"] == "m2":
            destination = pack / "gltf" / (asset["path"] + ".glb")
            try:
                export_m2(value, destination)
                exports.append({"source": asset["path"], "glb": str(destination.relative_to(pack)),
                                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
            except ValueError as error:
                unsupported.append({"source": asset["path"], "reason": str(error), "neutral_export_retained": True})
        elif value["kind"] in {"adt", "wmo_group"}:
            destination = pack / "geometry" / (asset["path"] + ".obj")
            obj(value, destination)
            geometry.append({"source": asset["path"], "obj": str(destination.relative_to(pack)),
                             "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
    write_json(pack / "gltf-manifest.json", {"exports": exports, "unsupported": unsupported,
                                             "scope": "skinned geometry and ordinary bone animation; preview materials"})
    write_json(pack / "geometry-manifest.json", {"exports": geometry})
    write_json(output / "verification.json", verify_pack(pack))
    write_json(output / "status.json", {"status": "extracted", "retail_extracted": True,
                                        "playable": False, "unreal_used": False,
                                        "glb_count": len(exports), "glb_unsupported": len(unsupported)})


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))
