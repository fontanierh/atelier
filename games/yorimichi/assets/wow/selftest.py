"""Standalone integration smoke test; requires no pytest, game install or Atelier."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from fixtures import synthetic_m2
from glb import export_m2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="wow-extraction-fixture-") as folder:
        root = Path(folder)
        source = root / "fixture.m2"
        source.write_bytes(synthetic_m2())
        subprocess.run([str(args.binary.resolve()), "convert", str(source), str(root / "out")], check=True)
        model = json.loads((root / "out/decoded/fixture.m2.json").read_text())
        if model["skins"][0]["triangles"] != [0, 1, 2]:
            raise RuntimeError("Skin indices changed")
        if model["bones"][0]["pivot"] != [1, 2, 3]:
            raise RuntimeError("Bone pivot changed")
        if model["bones"][0]["interpolation"]["translation"] != 1:
            raise RuntimeError("Bone interpolation flag changed")
        clip = model["animations"][0]
        if clip["animation_id"] != 51 or clip["duration_seconds"] != 1:
            raise RuntimeError("Animation identity or time units changed")
        if clip["tracks"][0]["translation"] != [[0, [0, 0, 0]], [1, [0, 0, 1]]]:
            raise RuntimeError("Animation keys changed")
        export_m2(model, root / "out/fixture.glb")
        data = (root / "out/fixture.glb").read_bytes()
        magic, version, length = struct.unpack_from("<III", data)
        if (magic, version, length) != (0x46546C67, 2, len(data)):
            raise RuntimeError("Invalid GLB container")
        size = struct.unpack_from("<I", data, 12)[0]
        doc = json.loads(data[20:20 + size])
        if len(doc["animations"]) != 1 or len(doc["skins"][0]["joints"]) != 1:
            raise RuntimeError("Missing GLB skin or animation")
    print("PASS: synthetic M2 -> skeleton/clip/mesh JSON -> skinned animated GLB; no retail data used")


if __name__ == "__main__":
    main()
