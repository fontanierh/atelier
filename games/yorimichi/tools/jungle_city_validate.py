"""Validate a Jungle City GLB before it is promoted to the committed asset library."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
import trimesh


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def glb_json(path: Path) -> dict:
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b"glTF":
            raise ValueError("not a binary glTF file")
        chunk_length, chunk_type = struct.unpack("<II", stream.read(8))
        if chunk_type != 0x4E4F534A:
            raise ValueError("GLB JSON chunk is not first")
        return json.loads(stream.read(chunk_length))


def scene_meshes(scene: trimesh.Scene) -> list[trimesh.Trimesh]:
    meshes = []
    for node in scene.graph.nodes_geometry:
        transform, geometry_name = scene.graph[node]
        geometry = scene.geometry[geometry_name]
        if not isinstance(geometry, trimesh.Trimesh):
            continue
        mesh = geometry.copy()
        mesh.apply_transform(transform)
        mesh.merge_vertices(merge_tex=True, merge_norm=True)
        meshes.append(mesh)
    return meshes


def inspect(path: Path) -> dict:
    loaded = trimesh.load(path, force="scene", process=False)
    if not isinstance(loaded, trimesh.Scene):
        loaded = trimesh.Scene(loaded)
    meshes = scene_meshes(loaded)
    if not meshes:
        raise ValueError("no triangle meshes in GLB")

    vertices = sum(len(mesh.vertices) for mesh in meshes)
    faces = sum(len(mesh.faces) for mesh in meshes)
    degenerate = sum(int((~mesh.nondegenerate_faces()).sum()) for mesh in meshes)
    boundary = 0
    nonmanifold = 0
    for mesh in meshes:
        uses = np.bincount(mesh.edges_unique_inverse)
        boundary += int((uses == 1).sum())
        nonmanifold += int((uses > 2).sum())

    components = sum(mesh.body_count for mesh in meshes)
    minimum = np.min(np.vstack([mesh.bounds[0] for mesh in meshes]), axis=0)
    maximum = np.max(np.vstack([mesh.bounds[1] for mesh in meshes]), axis=0)
    dimensions = (maximum - minimum).tolist()
    uv_meshes = [mesh for mesh in meshes if getattr(mesh.visual, "uv", None) is not None]
    uv_vertices = sum(len(mesh.visual.uv) for mesh in uv_meshes)
    document = glb_json(path)

    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "meshes": len(meshes),
        "components": components,
        "vertices": vertices,
        "triangles": faces,
        "degenerate_triangles": degenerate,
        "boundary_edges": boundary,
        "nonmanifold_edges": nonmanifold,
        "winding_consistent": all(mesh.is_winding_consistent for mesh in meshes),
        "watertight": all(mesh.is_watertight for mesh in meshes),
        "dimensions": [round(value, 4) for value in dimensions],
        "uv_meshes": len(uv_meshes),
        "uv_vertices": uv_vertices,
        "images": len(document.get("images", [])),
        "textures": len(document.get("textures", [])),
        "materials": len(document.get("materials", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-components", type=int, default=4)
    parser.add_argument("--max-triangles", type=int, default=120000)
    args = parser.parse_args()

    report = inspect(args.model.resolve())
    report["acceptance"] = {
        "bounded_triangles": report["triangles"] <= args.max_triangles,
        "bounded_components": report["components"] <= args.max_components,
        "no_degenerate_triangles": report["degenerate_triangles"] == 0,
        "no_nonmanifold_edges": report["nonmanifold_edges"] == 0,
        "no_boundary_edges": report["boundary_edges"] == 0,
        "consistent_winding": report["winding_consistent"],
        "watertight": report["watertight"],
        "has_uvs": report["uv_meshes"] > 0 and report["uv_vertices"] > 0,
        "has_texture": report["images"] > 0 and report["textures"] > 0,
        "finite_dimensions": all(np.isfinite(report["dimensions"])) and min(report["dimensions"]) > 0,
    }
    report["passed"] = all(report["acceptance"].values())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
