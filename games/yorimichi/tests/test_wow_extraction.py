"""Offline format fixtures: no retail content, Unreal, Blender or compatible server required."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

import pytest

WOW = Path(__file__).resolve().parents[1] / "assets/wow"
ROOT = WOW.parents[3]
spec = importlib.util.spec_from_file_location("wow_pipeline", WOW / "pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
spec = importlib.util.spec_from_file_location("wow_glb", WOW / "glb.py")
glb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(glb)
spec = importlib.util.spec_from_file_location("wow_catalogue", WOW / "catalogue.py")
catalogue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalogue)


def synthetic_m2() -> bytes:
    """A triangle, one pivot bone, a one-second translation clip and one skinned section."""
    data = bytearray(0x144)
    data[:4] = b"MD20"
    struct.pack_into("<I", data, 4, 256)

    def append(payload):
        offset = len(data)
        data.extend(payload)
        return offset

    def array(position, count, offset):
        struct.pack_into("<II", data, position, count, offset)

    seq = bytearray(68)
    struct.pack_into("<H", seq, 0, 51)
    struct.pack_into("<II", seq, 4, 0, 1000)
    array(0x1C, 1, append(seq))
    bone = bytearray(108)
    struct.pack_into("<i", bone, 0, -1)
    struct.pack_into("<h", bone, 8, -1)
    struct.pack_into("<3f", bone, 96, 1, 2, 3)
    for offset in (12, 40, 68):
        struct.pack_into("<HH", bone, offset, 1, 0xFFFF)
    bone_at = append(bone)
    array(0x34, 1, bone_at)
    times = append(struct.pack("<II", 0, 1000))
    values = append(struct.pack("<6f", 0, 0, 0, 0, 0, 1))
    ranges = append(struct.pack("<II", 0, 1))
    struct.pack_into("<6I", data, bone_at + 16, 1, ranges, 2, times, 2, values)
    vertices = bytearray()
    for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0)):
        vertex = bytearray(48)
        struct.pack_into("<3f", vertex, 0, *point)
        vertex[12] = 255
        struct.pack_into("<3f", vertex, 20, 0, 0, 1)
        vertices.extend(vertex)
    array(0x44, 3, append(vertices))
    skin = bytearray(44)
    skin_at = append(skin)
    array(0x4C, 1, skin_at)
    indices = append(struct.pack("<3H", 0, 1, 2))
    triangles = append(struct.pack("<3H", 0, 1, 2))
    section = bytearray(32)
    struct.pack_into("<H", section, 10, 3)
    section_at = append(section)
    array(skin_at, 3, indices)
    array(skin_at + 8, 3, triangles)
    array(skin_at + 24, 1, section_at)
    return bytes(data)


def preview_model():
    return {
        "kind": "m2", "bones": [{"parent": -1, "key_bone": 6, "pivot": [1, 2, 3], "flags": 0,
                                  "interpolation": {"translation": 1, "rotation": 1, "scale": 1}}],
        "vertices": [{"position": p, "normal": [0, 0, 1], "uv": [0, 0], "joints": [0, 0, 0, 0],
                      "weights_u8": [255, 0, 0, 0]} for p in ([0, 0, 0], [1, 0, 0], [0, 1, 0])],
        "skins": [{"triangles": [0, 1, 2], "sections": [{"geoset_id": 0, "index_start": 0, "index_count": 3}]}],
        "global_sequence_bones": [],
        "animations": [{"animation_id": 51, "source_sequence": 0, "looping": True,
                        "duration_seconds": 1, "events": [], "tracks": [{"bone": 0,
                        "translation": [[0, [0, 0, 0]], [1, [0, 0, 1]]], "rotation": [], "scale": []}]}],
    }


def unpack_glb(path):
    blob = path.read_bytes()
    magic, version, length = struct.unpack_from("<III", blob)
    assert (magic, version, length) == (0x46546C67, 2, len(blob))
    json_size, kind = struct.unpack_from("<II", blob, 12)
    assert kind == 0x4E4F534A
    document = json.loads(blob[20:20 + json_size])
    at = 20 + json_size
    size, kind = struct.unpack_from("<II", blob, at)
    assert kind == 0x004E4942 and at + 8 + size == len(blob)
    return document, blob[at + 8:]


def accessor(document, binary, index):
    value = document["accessors"][index]
    view = document["bufferViews"][value["bufferView"]]
    dimensions = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[value["type"]]
    formats = {5126: "f", 5125: "I", 5123: "H"}
    return struct.unpack_from("<" + formats[value["componentType"]] * dimensions * value["count"], binary, view["byteOffset"])


def test_profile_is_data_driven_and_no_unreal():
    profile = pipeline.profile(WOW / "profile.toml")
    plan = pipeline.plan(profile)
    assert (plan["class_id"], plan["spell_family"], plan["level"]) == (8, 3, 60)
    assert any("BootyBay.wmo" in p for p in plan["seeds"])
    changed = copy.deepcopy(profile)
    changed["character"].update(class_id=9, spell_family=5, level=40)
    assert pipeline.plan(changed)["spell_family"] == 5
    assert "server" not in plan and "unreal" not in plan


def test_missing_data_reports_blocked_instead_of_extracted(tmp_path):
    report = pipeline.doctor(None, tmp_path)
    assert report["status"] == "blocked_missing_client_data"
    assert not report["retail_extracted"]
    assert "model.mpq" in report["missing_archives"]


def test_generated_output_must_stay_ignored(tmp_path):
    with pytest.raises(ValueError, match="ignored build"):
        pipeline.output_path(tmp_path)


def test_glb_bind_pose_and_translation_are_converted_once(tmp_path):
    path = tmp_path / "triangle.glb"
    glb.export_m2(preview_model(), path)
    doc, binary = unpack_glb(path)
    assert doc["nodes"][1]["translation"] == pytest.approx([0.9144, 2.7432, -1.8288])
    inverse = accessor(doc, binary, doc["skins"][0]["inverseBindMatrices"])
    assert inverse[12:15] == pytest.approx([-0.9144, -2.7432, 1.8288])
    animation = doc["animations"][0]
    keys = accessor(doc, binary, animation["samplers"][0]["output"])
    assert keys[:3] == pytest.approx([0.9144, 2.7432, -1.8288])
    assert keys[3:] == pytest.approx([0.9144, 3.6576, -1.8288])
    positions = accessor(doc, binary, doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"])
    assert positions[3:6] == pytest.approx([0.9144, 0, 0])
    # Root bind translation plus inverse bind cancels; source vertex positions stay put.
    assert [doc["nodes"][1]["translation"][i] + inverse[12 + i] for i in range(3)] == pytest.approx([0, 0, 0], abs=1e-6)


@pytest.mark.parametrize("mutation", ["billboard", "global", "bad_joint", "bad_times", "cycle", "nonfinite"])
def test_glb_rejects_unsupported_or_invalid_data(tmp_path, mutation):
    model = preview_model()
    if mutation == "billboard": model["bones"][0]["flags"] = 8
    elif mutation == "global": model["global_sequence_bones"] = [{"bone": 0}]
    elif mutation == "bad_joint": model["vertices"][0]["joints"][0] = 99
    elif mutation == "bad_times": model["animations"][0]["tracks"][0]["translation"][1][0] = 0
    elif mutation == "cycle": model["bones"][0]["parent"] = 0
    elif mutation == "nonfinite": model["vertices"][0]["position"][0] = float("nan")
    with pytest.raises(ValueError):
        glb.export_m2(model, tmp_path / "bad.glb")
    assert not (tmp_path / "bad.glb").exists()


def test_dbc_checks_extent_and_string_offsets(tmp_path):
    path = tmp_path / "test.dbc"
    path.write_bytes(b"WDBC" + struct.pack("<4I", 1, 2, 8, 5) + struct.pack("<2I", 7, 1) + b"\0abc\0")
    table = catalogue.Dbc(path, 2)
    assert table.rows == [(7, 1)] and table.string(1) == "abc"
    with pytest.raises(ValueError): table.string(99)
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(ValueError): catalogue.Dbc(path, 2)


def test_manifest_detects_tampering_and_missing_dependencies(tmp_path):
    asset = tmp_path / "raw/model.m2"
    asset.parent.mkdir()
    asset.write_bytes(b"fixture")
    manifest = {"complete": True, "failures": [], "assets": [{"path": "model.m2", "raw": "raw/model.m2",
        "sha256": hashlib.sha256(b"fixture").hexdigest(), "decoded": None, "dependencies": []}]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert catalogue.verify_pack(tmp_path)["valid"]
    asset.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed output"):
        catalogue.verify_pack(tmp_path)
    asset.write_bytes(b"fixture")
    manifest["assets"][0]["dependencies"] = ["missing.blp"]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unresolved dependency"):
        catalogue.verify_pack(tmp_path)


def test_compiled_decoder_extracts_fixture_clip_and_mesh(tmp_path):
    binary = ROOT / "build/yorimichi/wow/tools/debug/yorimichi-wow-extract"
    if not binary.is_file():
        pytest.skip("Build the offline decoder to run the binary integration fixture")
    source = tmp_path / "fixture.m2"
    source.write_bytes(synthetic_m2())
    result = subprocess.run([str(binary), "convert", str(source), str(tmp_path / "out")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    model = json.loads((tmp_path / "out/decoded/fixture.m2.json").read_text())
    assert model["skins"][0]["triangles"] == [0, 1, 2]
    assert model["bones"][0]["pivot"] == [1, 2, 3]
    assert model["bones"][0]["interpolation"]["translation"] == 1
    clip = model["animations"][0]
    assert clip["animation_id"] == 51 and clip["duration_seconds"] == 1
    assert clip["tracks"][0]["translation"] == [[0, [0, 0, 0]], [1, [0, 0, 1]]]
    glb.export_m2(model, tmp_path / "out/fixture.glb")
    doc, _ = unpack_glb(tmp_path / "out/fixture.glb")
    assert len(doc["animations"]) == 1 and len(doc["skins"][0]["joints"]) == 1
