"""Close small holes in a derived Jungle City mesh without editing its source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def topology(mesh: trimesh.Trimesh) -> dict:
    uses = np.bincount(mesh.edges_unique_inverse)
    return {
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.faces),
        "components": mesh.body_count,
        "degenerate_triangles": int((~mesh.nondegenerate_faces()).sum()),
        "boundary_edges": int((uses == 1).sum()),
        "nonmanifold_edges": int((uses > 2).sum()),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "watertight": bool(mesh.is_watertight),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("output already exists")
    before_hash = sha256(source)
    with np.load(source, allow_pickle=False) as data:
        vertices = np.asarray(data["vertices"], dtype="float32")
        faces = np.asarray(data["faces"], dtype="uint32")
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    before = topology(mesh)
    nondegenerate = mesh.nondegenerate_faces()
    if not nondegenerate.all():
        mesh.update_faces(nondegenerate)
    filled = bool(mesh.fill_holes())
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(mesh, multibody=True)
    after = topology(mesh)
    accepted = all((
        after["degenerate_triangles"] == 0,
        after["boundary_edges"] == 0,
        after["nonmanifold_edges"] == 0,
        after["winding_consistent"],
        after["watertight"],
        after["components"] <= 4,
    ))
    if not accepted:
        raise ValueError(f"closed mesh does not meet acceptance topology: {after}")
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        vertices=np.asarray(mesh.vertices, dtype="<f4"),
        faces=np.asarray(mesh.faces, dtype="<u4"),
    )
    if sha256(source) != before_hash:
        raise ValueError("closing changed the retained source")
    report = {
        "method": "trimesh hole fill plus global winding repair on a derived copy",
        "source": source.name,
        "source_sha256": before_hash,
        "output": output.name,
        "output_sha256": sha256(output),
        "fill_holes_returned": filled,
        "before": before,
        "after": after,
        "accepted": accepted,
    }
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
