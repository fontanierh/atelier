"""Repair a derived Jungle City mesh into a watertight manifold with MeshFix."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pymeshfix
import trimesh


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def topology(vertices: np.ndarray, faces: np.ndarray) -> dict:
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    cross = np.cross(vertices[faces[:, 1]]-vertices[faces[:, 0]],
                     vertices[faces[:, 2]]-vertices[faces[:, 0]])
    return {
        "vertices": len(vertices),
        "triangles": len(faces),
        "degenerate_triangles": int((np.linalg.norm(cross, axis=1) <= 1e-14).sum()),
        "boundary_edges": int((counts == 1).sum()),
        "nonmanifold_edges": int((counts > 2).sum()),
        "winding_consistent": bool(np.all(counts == 2)),
        "watertight": bool(np.all(counts == 2)),
    }


def cap_boundary_loops(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    boundary = [tuple(map(int, edge)) for edge in unique[counts == 1]]
    if not boundary:
        return vertices, faces
    adjacency: dict[int, list[int]] = {}
    for left, right in boundary:
        adjacency.setdefault(left, []).append(right)
        adjacency.setdefault(right, []).append(left)
    if any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise ValueError("boundary contains a junction rather than simple loops")
    unused = {tuple(sorted(edge)) for edge in boundary}
    output_vertices = list(vertices)
    output_faces = list(faces)
    while unused:
        left, right = next(iter(unused))
        unused.remove((left, right))
        loop = [left, right]
        while loop[-1] != loop[0]:
            current = loop[-1]
            candidates = [neighbor for neighbor in adjacency[current]
                          if tuple(sorted((current, neighbor))) in unused]
            if len(candidates) != 1:
                raise ValueError("boundary loop traversal is ambiguous")
            neighbor = candidates[0]
            unused.remove(tuple(sorted((current, neighbor))))
            loop.append(neighbor)
            if neighbor == loop[0]:
                break
        loop.pop()
        centre_index = len(output_vertices)
        output_vertices.append(vertices[loop].mean(axis=0))
        for index, vertex in enumerate(loop):
            output_faces.append((centre_index, vertex, loop[(index + 1) % len(loop)]))
    return np.asarray(output_vertices, dtype=vertices.dtype), np.asarray(output_faces, dtype=faces.dtype)


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
        vertices = np.asarray(data["vertices"], dtype="float64")
        faces = np.asarray(data["faces"], dtype="int64")
    before = topology(vertices.astype("float32"), faces.astype("uint32"))
    repair = pymeshfix.MeshFix(vertices, faces)
    repair.repair(verbose=False, joincomp=True, remove_smallest_components=False)
    mesh = trimesh.Trimesh(vertices=np.asarray(repair.v), faces=np.asarray(repair.f), process=False)
    mesh.fill_holes()
    mesh.remove_unreferenced_vertices()
    capped_vertices, capped_faces = cap_boundary_loops(
        np.asarray(mesh.vertices), np.asarray(mesh.faces))
    mesh = trimesh.Trimesh(vertices=capped_vertices, faces=capped_faces, process=False)
    trimesh.repair.fix_normals(mesh, multibody=True)
    out_vertices = np.asarray(mesh.vertices, dtype="<f4")
    out_faces = np.asarray(mesh.faces, dtype="<u4")
    after = topology(out_vertices, out_faces)
    accepted = all((
        after["degenerate_triangles"] == 0,
        after["boundary_edges"] == 0,
        after["nonmanifold_edges"] == 0,
        after["winding_consistent"],
        after["watertight"],
        after["triangles"] <= 120000,
    ))
    if not accepted:
        raise ValueError(f"MeshFix output does not meet acceptance topology: {after}")
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, vertices=out_vertices, faces=out_faces)
    if sha256(source) != before_hash:
        raise ValueError("MeshFix changed the retained source")
    report = {
        "method": "pymeshfix 0.17.1 plus trimesh hole fill/winding repair on a derived copy",
        "source": source.name,
        "source_sha256": before_hash,
        "output": output.name,
        "output_sha256": sha256(output),
        "before": before,
        "after": after,
        "accepted": accepted,
    }
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
