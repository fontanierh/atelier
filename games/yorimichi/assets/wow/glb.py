"""Portable preview export for decoded M2 skeletons and ordinary clip channels.

The neutral export/raw M2 remain authoritative: this GLB deliberately uses preview materials,
and rejects camera-dependent bones and special parent inheritance rather than baking them wrong.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import struct

YARD_METRES = 0.9144


def vector(v, *, scale=True):
    # Raw WoW RH Z-up -> glTF RH Y-up, one rotation with determinant +1.
    factor = YARD_METRES if scale else 1.0
    return [factor * v[0], factor * v[2], -factor * v[1]]


def rotation(q):
    norm = math.sqrt(sum(v * v for v in q))
    if norm == 0 or not math.isfinite(norm):
        raise ValueError("Invalid animation quaternion")
    return [q[0] / norm, q[2] / norm, -q[1] / norm, q[3] / norm]


def export_m2(model: dict, output: Path) -> dict:
    if model.get("kind") != "m2" or not model["skins"]:
        raise ValueError("An M2 with an embedded skin is required")
    bones = model["bones"]
    for index, bone in enumerate(bones):
        if bone["parent"] >= index or bone["parent"] < -1:
            raise ValueError("Bone hierarchy is cyclic or not parent-before-child")
        if bone["flags"] & 0x7F:
            raise ValueError("Special parent inheritance or billboard bone: use neutral channels")
        if any(mode not in (0, 1) for mode in bone["interpolation"].values()):
            raise ValueError("Nonlinear bone interpolation requires a dedicated bake")
    if model["global_sequence_bones"]:
        raise ValueError("Independent global-sequence bones require a dedicated bake")
    vertices = model["vertices"]
    if not vertices:
        raise ValueError("Model contains no mesh vertices")
    document = {
        "asset": {"version": "2.0", "generator": "Atelier offline M2 extraction"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "M2_root", "children": []}],
        "buffers": [], "bufferViews": [], "accessors": [], "meshes": [],
        "materials": [{"name": "preview", "pbrMetallicRoughness": {"baseColorFactor": [0.7, 0.7, 0.7, 1],
                         "metallicFactor": 0, "roughnessFactor": 1}, "doubleSided": True}],
        "extras": {"source_units": "yards", "export_units": "metres", "preview_materials": True,
                   "textures_and_material_flags": "See neutral M2 and extracted textures",
                   "geoset_selection": "All authored sections exported; appearance selection is separate",
                   "particles_and_ribbons": "See raw M2 and neutral metadata"},
    }
    binary = bytearray()

    def accessor(values, fmt, gl_type, dimensions, *, bounds=False, target=None):
        while len(binary) % 4:
            binary.append(0)
        start = len(binary)
        flattened = [list(v) if isinstance(v, (list, tuple)) else [v] for v in values]
        if not flattened:
            raise ValueError("Cannot create an empty accessor")
        if any(not math.isfinite(float(x)) for v in flattened for x in v):
            raise ValueError("Non-finite mesh/animation data")
        for value in flattened:
            binary.extend(struct.pack("<" + fmt * len(value), *value))
        view = {"buffer": 0, "byteOffset": start, "byteLength": len(binary) - start}
        if target is not None:
            view["target"] = target
        index = len(document["bufferViews"])
        document["bufferViews"].append(view)
        result = {"bufferView": index, "componentType": gl_type, "count": len(flattened), "type": dimensions}
        if bounds:
            result["min"] = [min(v[i] for v in flattened) for i in range(len(flattened[0]))]
            result["max"] = [max(v[i] for v in flattened) for i in range(len(flattened[0]))]
        document["accessors"].append(result)
        return len(document["accessors"]) - 1

    nodes = document["nodes"]
    for index, bone in enumerate(bones):
        pivot = vector(bone["pivot"])
        if bone["parent"] >= 0:
            parent = vector(bones[bone["parent"]]["pivot"])
            pivot = [a - b for a, b in zip(pivot, parent)]
        nodes.append({"name": f"bone_{index:03d}_key_{bone['key_bone']}", "translation": pivot,
                      "extras": {"source_bone": index, "key_bone": bone["key_bone"]}})
        parent_node = bone["parent"] + 1 if bone["parent"] >= 0 else 0
        nodes[parent_node].setdefault("children", []).append(index + 1)
    attributes = {
        "POSITION": accessor([vector(v["position"]) for v in vertices], "f", 5126, "VEC3", bounds=True, target=34962),
        "NORMAL": accessor([vector(v["normal"], scale=False) for v in vertices], "f", 5126, "VEC3", target=34962),
        "TEXCOORD_0": accessor([v["uv"] for v in vertices], "f", 5126, "VEC2", target=34962),
    }
    if bones:
        if any(j >= len(bones) for v in vertices for j, weight in zip(v["joints"], v["weights_u8"]) if weight):
            raise ValueError("Vertex references a nonexistent bone")
        weights, joints = [], []
        for vertex in vertices:
            total = sum(vertex["weights_u8"])
            weights.append([w / total for w in vertex["weights_u8"]] if total else [1, 0, 0, 0])
            joints.append([j if weight else 0 for j, weight in zip(vertex["joints"], vertex["weights_u8"])] if total else [0, 0, 0, 0])
        attributes["JOINTS_0"] = accessor(joints, "H", 5123, "VEC4", target=34962)
        attributes["WEIGHTS_0"] = accessor(weights, "f", 5126, "VEC4", target=34962)
        matrices = []
        for bone in bones:
            x, y, z = vector(bone["pivot"])
            matrices.append([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -x, -y, -z, 1])
        document["skins"] = [{"joints": list(range(1, len(bones) + 1)),
                               "inverseBindMatrices": accessor(matrices, "f", 5126, "MAT4")}]
    skin = model["skins"][0]
    triangles = skin["triangles"]
    if len(triangles) % 3 or any(i < 0 or i >= len(vertices) for i in triangles):
        raise ValueError("Invalid triangle indices")
    sections = skin["sections"] or [{"geoset_id": 0, "index_start": 0, "index_count": len(triangles)}]
    primitives = []
    for section in sections:
        start, count = section["index_start"], section["index_count"]
        if count == 0:
            continue
        if start < 0 or start + count > len(triangles) or count % 3:
            raise ValueError("Invalid geoset triangle range")
        primitives.append({"attributes": attributes, "indices": accessor(triangles[start:start + count], "I", 5125, "SCALAR", target=34963),
                           "material": 0, "extras": {"geoset_id": section["geoset_id"]}})
    if not primitives:
        raise ValueError("Model contains no triangles")
    document["meshes"].append({"primitives": primitives})
    mesh_node = {"name": "mesh", "mesh": 0}
    if bones:
        mesh_node["skin"] = 0
    nodes[0]["children"].append(len(nodes))
    nodes.append(mesh_node)
    animations = []
    for clip in model["animations"]:
        animation = {"name": f"anim_{clip['animation_id']:03d}_seq_{clip['source_sequence']:03d}",
                     "samplers": [], "channels": [], "extras": {"animation_id": clip["animation_id"],
                     "source_sequence": clip["source_sequence"], "looping": clip["looping"],
                     "duration_seconds": clip["duration_seconds"], "events": clip["events"]}}
        for track in clip["tracks"]:
            bone_index = track["bone"]
            if not 0 <= bone_index < len(bones):
                raise ValueError("Animation references a nonexistent bone")
            bone = bones[bone_index]
            for channel in ("translation", "rotation", "scale"):
                keys = track[channel]
                if not keys:
                    continue
                times = [t for t, _ in keys]
                if any(t < 0 or t > clip["duration_seconds"] + 1e-4 for t in times) or any(b <= a for a, b in zip(times, times[1:])):
                    raise ValueError("Animation keys must be ordered and inside the clip")
                rest = nodes[bone_index + 1]["translation"]
                if channel == "translation":
                    values = [[a + b for a, b in zip(rest, vector(v))] for _, v in keys]
                elif channel == "rotation":
                    values = [rotation(v) for _, v in keys]
                else:
                    values = [[v[0], v[2], v[1]] for _, v in keys]
                sampler = {"input": accessor(times, "f", 5126, "SCALAR", bounds=True),
                           "output": accessor(values, "f", 5126, "VEC4" if channel == "rotation" else "VEC3"),
                           "interpolation": "STEP" if bone["interpolation"][channel] == 0 else "LINEAR"}
                animation["channels"].append({"sampler": len(animation["samplers"]),
                                               "target": {"node": bone_index + 1, "path": channel}})
                animation["samplers"].append(sampler)
        if animation["channels"]:
            animations.append(animation)
    if animations:
        document["animations"] = animations
    document["buffers"].append({"byteLength": len(binary)})
    encoded = json.dumps(document, separators=(",", ":"), allow_nan=False).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\0" * (-len(binary) % 4)
    result = (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(encoded) + 8 + len(binary))
              + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
              + struct.pack("<II", len(binary), 0x004E4942) + binary)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".partial")
    temporary.write_bytes(result)
    temporary.replace(output)
    return document
