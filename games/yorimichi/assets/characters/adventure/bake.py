"""Bake an adventure library rig's BFRES curve clips into glTF animations.

The library's GLBs carry the rigged mesh only; each rig's clips live in a separate JSON curve library (the format of
the library's own `animation-player.js`: cubic BFRES polynomials per channel, Euler XYZ or quaternion rotations,
Maya segment scale compensation). This module evaluates those curves at every integer frame (30 fps), solves the
bone world matrices the same way the viewer does, and writes each clip as a glTF animation of local TRS channels,
so Blender and Unreal import the clips with the mesh.

Plain Python and numpy: it runs from the `atelier` venv and inside Blender.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

FPS = 30


# --- GLB ---------------------------------------------------------------------------------------------------------

def read_glb(path):
    data = Path(path).read_bytes()
    magic, _version, _length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError(f"{path} is not a GLB")
    offset, gltf, binary = 12, None, b""
    while offset < len(data):
        size, kind = struct.unpack_from("<I4s", data, offset)
        chunk = data[offset + 8:offset + 8 + size]
        if kind == b"JSON":
            gltf = json.loads(chunk)
        elif kind == b"BIN\x00":
            binary = bytes(chunk)
        offset += 8 + size
    return gltf, bytearray(binary)


def write_glb(path, gltf, binary):
    gltf["buffers"] = [{"byteLength": len(binary)}]
    text = json.dumps(gltf, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    binary = bytes(binary) + b"\x00" * (-len(binary) % 4)
    body = struct.pack("<I4s", len(text), b"JSON") + text + struct.pack("<I4s", len(binary), b"BIN\x00") + binary
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)


class Writer:
    """Appends float accessors to a GLB's binary chunk."""

    def __init__(self, gltf, binary):
        self.gltf, self.binary = gltf, binary
        gltf.setdefault("bufferViews", [])
        gltf.setdefault("accessors", [])

    def floats(self, array, kind, bounds=False):
        array = np.ascontiguousarray(array, dtype="<f4")
        self.binary += b"\x00" * (-len(self.binary) % 4)
        view = {"buffer": 0, "byteOffset": len(self.binary), "byteLength": array.nbytes}
        self.binary += array.tobytes()
        self.gltf["bufferViews"].append(view)
        accessor = {"bufferView": len(self.gltf["bufferViews"]) - 1, "componentType": 5126,
                    "count": int(array.shape[0]), "type": kind}
        if bounds:
            accessor["min"] = [float(v) for v in np.atleast_1d(array.min(axis=0))]
            accessor["max"] = [float(v) for v in np.atleast_1d(array.max(axis=0))]
        self.gltf["accessors"].append(accessor)
        return len(self.gltf["accessors"]) - 1


# --- Math --------------------------------------------------------------------------------------------------------

def quat_xyzw_from_euler_xyz(euler):
    """BFRES Euler XYZ (the viewer's three.js 'ZYX' order: R = Rz Ry Rx) to quaternions (x, y, z, w)."""
    half = np.asarray(euler, dtype=np.float64) * 0.5
    cx, cy, cz = np.cos(half[..., 0]), np.cos(half[..., 1]), np.cos(half[..., 2])
    sx, sy, sz = np.sin(half[..., 0]), np.sin(half[..., 1]), np.sin(half[..., 2])
    return np.stack([sx * cy * cz - cx * sy * sz,
                     cx * sy * cz + sx * cy * sz,
                     cx * cy * sz - sx * sy * cz,
                     cx * cy * cz + sx * sy * sz], axis=-1)


def matrices_from_quat(q):
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    m = np.empty(q.shape[:-1] + (3, 3))
    m[..., 0, 0] = 1 - 2 * (y * y + z * z); m[..., 0, 1] = 2 * (x * y - z * w); m[..., 0, 2] = 2 * (x * z + y * w)
    m[..., 1, 0] = 2 * (x * y + z * w); m[..., 1, 1] = 1 - 2 * (x * x + z * z); m[..., 1, 2] = 2 * (y * z - x * w)
    m[..., 2, 0] = 2 * (x * z - y * w); m[..., 2, 1] = 2 * (y * z + x * w); m[..., 2, 2] = 1 - 2 * (x * x + y * y)
    return m


def quat_from_matrices(m):
    """Rotation matrices (..., 3, 3) to quaternions (x, y, z, w), Shepperd's method."""
    m = np.asarray(m, dtype=np.float64)
    shape = m.shape[:-2]
    m = m.reshape(-1, 3, 3)
    q = np.empty((m.shape[0], 4))
    trace = m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2]
    for i in range(m.shape[0]):
        a, t = m[i], trace[i]
        if t > 0:
            s = 2.0 * np.sqrt(t + 1.0)
            q[i] = [(a[2, 1] - a[1, 2]) / s, (a[0, 2] - a[2, 0]) / s, (a[1, 0] - a[0, 1]) / s, 0.25 * s]
        elif a[0, 0] > a[1, 1] and a[0, 0] > a[2, 2]:
            s = 2.0 * np.sqrt(1.0 + a[0, 0] - a[1, 1] - a[2, 2])
            q[i] = [0.25 * s, (a[0, 1] + a[1, 0]) / s, (a[0, 2] + a[2, 0]) / s, (a[2, 1] - a[1, 2]) / s]
        elif a[1, 1] > a[2, 2]:
            s = 2.0 * np.sqrt(1.0 + a[1, 1] - a[0, 0] - a[2, 2])
            q[i] = [(a[0, 1] + a[1, 0]) / s, 0.25 * s, (a[1, 2] + a[2, 1]) / s, (a[0, 2] - a[2, 0]) / s]
        else:
            s = 2.0 * np.sqrt(1.0 + a[2, 2] - a[0, 0] - a[1, 1])
            q[i] = [(a[0, 2] + a[2, 0]) / s, (a[1, 2] + a[2, 1]) / s, 0.25 * s, (a[1, 0] - a[0, 1]) / s]
    q /= np.linalg.norm(q, axis=-1, keepdims=True)
    return q.reshape(shape + (4,))


def compose(position, quat, scale):
    m = np.zeros(position.shape[:-1] + (4, 4))
    m[..., :3, :3] = matrices_from_quat(quat) * scale[..., None, :]
    m[..., :3, 3] = position
    m[..., 3, 3] = 1.0
    return m


def decompose(m):
    """Affine matrices to translation, rotation (x, y, z, w) and scale. Shear, which only appears when segment scale
    compensation meets a non-uniform parent scale, is dropped by the polar decomposition."""
    position = m[..., :3, 3].copy()
    linear = m[..., :3, :3]
    u, _s, vt = np.linalg.svd(linear)
    rotation = u @ vt
    flip = np.linalg.det(rotation) < 0
    if np.any(flip):
        u[flip, :, -1] *= -1
        rotation = u @ vt
    stretch = np.swapaxes(rotation, -1, -2) @ linear
    scale = np.stack([stretch[..., 0, 0], stretch[..., 1, 1], stretch[..., 2, 2]], axis=-1)
    return position, quat_from_matrices(rotation), scale


def continuous(quats):
    """Flip quaternion signs along the frame axis (axis 0) so interpolation takes the short way."""
    out = quats.copy()
    for i in range(1, out.shape[0]):
        flip = np.sum(out[i] * out[i - 1], axis=-1) < 0
        out[i][flip] *= -1
    return out


# --- Curves ------------------------------------------------------------------------------------------------------

def curve_values(curve, frames):
    keys = np.asarray(curve["frames"], dtype=np.float64)
    coefficients = np.asarray(curve["keys"], dtype=np.float64)
    index = np.clip(np.searchsorted(keys, frames + 1e-9, side="right") - 1, 0, len(keys) - 1)
    last = index == len(keys) - 1
    span = np.where(last, 1.0, keys[np.minimum(index + 1, len(keys) - 1)] - keys[index])
    t = np.where(last, 0.0, np.maximum(0.0, (frames - keys[index]) / np.where(span == 0, 1.0, span)))
    c = coefficients[index]
    if curve["type"] == "Cubic":
        value = c[:, 0] + t * (c[:, 1] + t * (c[:, 2] + t * c[:, 3]))
    elif curve["type"] == "Linear":
        value = c[:, 0] + c[:, 1] * t
    else:
        value = c[:, 0]
    return value * (curve["scale"] or 1.0) + curve["offset"]


def rest_pose(skeleton):
    """Local rest matrices of the curve library's skeleton."""
    out = []
    for bone in skeleton:
        rotation = np.asarray(bone["rotation"], dtype=np.float64)
        if bone["rotation_mode"] == "EulerXYZ":
            quat = quat_xyzw_from_euler_xyz(rotation[:3])
        else:
            quat = rotation / np.linalg.norm(rotation)
        out.append(compose(np.asarray(bone["position"])[None], quat[None], np.asarray(bone["scale"])[None])[0])
    return out


def sample_clip(skeleton, clip, frames):
    """World matrices (bones, frames, 4, 4) of one clip, exactly as the library viewer poses the rig."""
    tracks = {track["name"]: track for track in clip["bones"]}
    count = len(frames)
    worlds = np.zeros((len(skeleton), count, 4, 4))
    scales = np.zeros((len(skeleton), count, 3))
    for i, bone in enumerate(skeleton):
        position = np.tile(np.asarray(bone["position"], dtype=np.float64), (count, 1))
        rotate = np.tile(np.asarray(bone["rotation"], dtype=np.float64), (count, 1))
        scale = np.tile(np.asarray(bone["scale"], dtype=np.float64), (count, 1))
        mode = bone["rotation_mode"]
        track = tracks.get(bone["name"])
        if track:
            flags = track["base_flags"]
            if "Translate" in flags:
                position[:] = track["position"]
            if "Rotate" in flags:
                rotate[:] = track["rotation"]
            if "Scale" in flags:
                scale[:] = track["scale"]
            mode = clip["rotation"]
            for curve in track["curves"]:
                target = curve["target"]
                if 4 <= target <= 12:
                    scale[:, (target - 4) // 4] = curve_values(curve, frames)
                elif 16 <= target <= 24:
                    position[:, (target - 16) // 4] = curve_values(curve, frames)
                elif 32 <= target <= 44:
                    rotate[:, (target - 32) // 4] = curve_values(curve, frames)
                else:
                    raise ValueError(f"unsupported animation channel {target} on {bone['name']}")
        quat = quat_xyzw_from_euler_xyz(rotate[:, :3]) if mode == "EulerXYZ" else rotate
        local = compose(position, quat, scale)
        scales[i] = scale
        parent = bone["parent"]
        if parent < 0:
            worlds[i] = local
            continue
        if track and track.get("segment_scale_compensate"):
            inverse = np.where(np.abs(scales[parent]) > 1e-9, 1.0 / np.where(scales[parent] == 0, 1, scales[parent]), 0.0)
            local = local.copy()
            local[:, :3, :] *= inverse[:, :, None]
        worlds[i] = worlds[parent] @ local
    return worlds


def local_tracks(skeleton, worlds):
    """Plain TRS locals (no compensation) that reproduce the given world matrices under ordinary inheritance.

    Each local is solved against its parent's reconstructed world, so the shear TRS cannot hold (a non-uniform scale
    under compensation, such as a compressed auxiliary bone) stays on that bone instead of drifting its children."""
    out, rebuilt = [], []
    for i, bone in enumerate(skeleton):
        parent = bone["parent"]
        local = worlds[i] if parent < 0 else np.linalg.inv(rebuilt[parent]) @ worlds[i]
        position, quat, scale = decompose(local)
        quat = continuous(quat)
        trs = compose(position, quat, scale)
        rebuilt.append(trs if parent < 0 else rebuilt[parent] @ trs)
        out.append((position, quat, scale))
    return out


# --- Baking ------------------------------------------------------------------------------------------------------

def ground_travel(skeleton, worlds):
    """The skeleton root's ground-plane (x, z) offset from its first frame, per frame: the clip's root motion."""
    root = next(i for i, bone in enumerate(skeleton) if bone["parent"] < 0)
    travel = worlds[root, :, :3, 3] - worlds[root, :1, :3, 3]
    travel[:, 1] = 0.0
    return travel


def heading(matrices):
    """Yaw (radians, about +y) of each matrix's forward (+z) axis."""
    forward = matrices[..., :3, 2]
    return np.arctan2(forward[..., 0], forward[..., 2])


def root_path(skeleton, worlds):
    """The skeleton root's position (metres) and heading change since the first frame (radians), per frame."""
    root = next(i for i, bone in enumerate(skeleton) if bone["parent"] < 0)
    yaw = np.unwrap(heading(worlds[root]))
    return worlds[root, :, :3, 3].copy(), yaw - yaw[0]


def yaw_matrices(yaw):
    m = np.zeros(yaw.shape + (4, 4))
    m[..., 0, 0] = m[..., 2, 2] = np.cos(yaw)
    m[..., 0, 2] = np.sin(yaw)
    m[..., 2, 0] = -np.sin(yaw)
    m[..., 1, 1] = m[..., 3, 3] = 1.0
    return m


def bake(rig_glb, curve_json, out_glb, clips=None, fps=FPS, rename=None, in_place=False, strip=(), drive=(), progress=None):
    """Write `out_glb`: the rig with one glTF animation per selected clip (all clips when `clips` is None, none when
    it is empty), named `rename(clip)` when given. `in_place` removes the root's ground travel (the summary keeps it
    as each clip's `travel`, in metres), for a game that moves the character itself.

    Clips named in `strip` lose all their root translation instead: the root stays at the origin and the game moves
    the character (a jump's height is the game's). Clips named in `drive` lose their root translation and heading
    change both, and the summary keeps them as the clip's `path`: per frame the root's position (metres, the clip's
    space) and heading change (radians), for the game to move the character along.

    Returns a summary dict (bones, clips with frame counts and loop flags) for the import manifest."""
    gltf, binary = read_glb(rig_glb)
    library = json.loads(Path(curve_json).read_text())
    skeleton = library["skeleton"]
    nodes = {node.get("name"): index for index, node in enumerate(gltf["nodes"])}
    missing = [bone["name"] for bone in skeleton if bone["name"] not in nodes]
    if missing:
        raise ValueError(f"{rig_glb} lacks bones {missing[:5]}")

    # Animated nodes must use TRS, not matrices: give every bone node its library rest pose.
    for bone, matrix in zip(skeleton, rest_pose(skeleton)):
        node = gltf["nodes"][nodes[bone["name"]]]
        node.pop("matrix", None)
        position, quat, scale = decompose(matrix[None])
        node["translation"] = [float(v) for v in position[0]]
        node["rotation"] = [float(v) for v in quat[0]]
        node["scale"] = [float(v) for v in scale[0]]

    writer = Writer(gltf, binary)
    wanted = None if clips is None else set(clips)
    animations, summary = [], []
    for clip in library["animations"]:
        if wanted is not None and clip["name"] not in wanted:
            continue
        frame_count = max(1, int(clip["frames"]))
        frames = np.arange(frame_count + 1, dtype=np.float64)
        worlds = sample_clip(skeleton, clip, frames)
        travel = ground_travel(skeleton, worlds)
        driven = None
        if clip["name"] in drive:
            position, yaw = root_path(skeleton, worlds)
            undo = yaw_matrices(-yaw)
            undo[:, :3, 3] = -(undo[:, :3, :3] @ position[:, :, None])[:, :, 0]
            worlds = undo[None] @ worlds
            driven = np.concatenate([position, yaw[:, None]], axis=1)
        elif clip["name"] in strip:
            worlds[:, :, :3, 3] -= root_path(skeleton, worlds)[0][None]
        elif in_place:
            worlds[:, :, :3, 3] -= travel[None]
        tracks = local_tracks(skeleton, worlds)
        times = writer.floats(frames / fps, "SCALAR", bounds=True)
        samplers, channels = [], []
        for bone, (position, quat, scale) in zip(skeleton, tracks):
            node = nodes[bone["name"]]
            for path, values, kind in (("translation", position, "VEC3"), ("rotation", quat, "VEC4"),
                                       ("scale", scale, "VEC3")):
                if path == "scale" and np.allclose(scale, 1.0, atol=1e-5):
                    continue
                samplers.append({"input": times, "output": writer.floats(values, kind), "interpolation": "LINEAR"})
                channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": path}})
        name = rename(clip["name"]) if rename else clip["name"]
        animations.append({"name": name, "samplers": samplers, "channels": channels})
        summary.append({"name": name, "source": clip["name"], "frames": frame_count, "loop": bool(clip.get("loop")),
                        "partial": bool(clip.get("partial")), "travel": [round(float(v), 4) for v in travel[-1]]})
        if driven is not None:
            summary[-1]["path"] = [[round(float(v), 4) for v in row] for row in driven]
        if progress:
            progress(name, len(summary), frame_count)
    if wanted is not None:
        absent = wanted - {item["source"] for item in summary}
        if absent:
            raise ValueError(f"{curve_json} has no clips {sorted(absent)}")
    if animations:
        gltf["animations"] = animations
    write_glb(out_glb, gltf, writer.binary)
    return {"bones": [bone["name"] for bone in skeleton], "clips": summary, "fps": fps}


def static(glb, out_glb):
    """Write `out_glb`: a one-bone rigged prop (a weapon, a shield) as a plain mesh, its skin and joints dropped, so it
    imports as a static mesh in the rig's bind space."""
    gltf, binary = read_glb(glb)
    for node in gltf["nodes"]:
        node.pop("skin", None)
    gltf.pop("skins", None)
    gltf.pop("animations", None)
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            for attribute in ("JOINTS_0", "WEIGHTS_0"):
                primitive["attributes"].pop(attribute, None)
    write_glb(out_glb, gltf, binary)


def check(rig_glb, curve_json, baked_glb, clip_name, frame):
    """Largest joint position difference (metres) between the viewer's pose and the baked TRS chain for one frame."""
    library = json.loads(Path(curve_json).read_text())
    skeleton = library["skeleton"]
    clip = next(item for item in library["animations"] if item["name"] == clip_name)
    expected = sample_clip(skeleton, clip, np.array([float(frame)]))[:, 0]
    gltf, binary = read_glb(baked_glb)
    animation = next(item for item in gltf["animations"] if item["name"] == clip_name)
    nodes = {node.get("name"): index for index, node in enumerate(gltf["nodes"])}

    def read(accessor_index):
        accessor = gltf["accessors"][accessor_index]
        view = gltf["bufferViews"][accessor["bufferView"]]
        width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[accessor["type"]]
        return np.frombuffer(binary, "<f4", accessor["count"] * width, view.get("byteOffset", 0)).reshape(-1, width)

    pose = {}
    for channel in animation["channels"]:
        sampler = animation["samplers"][channel["sampler"]]
        pose[(channel["target"]["node"], channel["target"]["path"])] = read(sampler["output"])[frame]
    worlds = []
    for i, bone in enumerate(skeleton):
        node = gltf["nodes"][nodes[bone["name"]]]
        t = pose.get((nodes[bone["name"]], "translation"), node["translation"])
        r = pose.get((nodes[bone["name"]], "rotation"), node["rotation"])
        s = pose.get((nodes[bone["name"]], "scale"), node.get("scale", [1, 1, 1]))
        local = compose(np.asarray(t, float)[None], np.asarray(r, float)[None], np.asarray(s, float)[None])[0]
        worlds.append(local if bone["parent"] < 0 else worlds[bone["parent"]] @ local)
    return float(max(np.abs(w[:3, 3] - e[:3, 3]).max() for w, e in zip(worlds, expected)))
