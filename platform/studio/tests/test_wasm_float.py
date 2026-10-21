"""The float pass must not rewrite engine arithmetic or quoted module data."""

from collections import Counter
from pathlib import Path
import json
import sys

import pytest

TOOLS = (
    Path(__file__).resolve().parents[3]
    / "platform/engine/Plugins/Activities/Skate/Tools"
)
sys.path.insert(0, str(TOOLS))
import wasm_float
import prepare_wasm


BOUNDARIES = """ (func $"atelier::skate::VectorMin(float, float)" (param f32 f32) (result f32)
  (f32.min (local.get 0) (local.get 1)))
 (func $"atelier::skate::VectorMax(float, float)" (param f32 f32) (result f32)
  (f32.max (local.get 0) (local.get 1)))
 (func $"atelier::skate::FlushDenormalsToZero()" (result i32) (i32.const 0))
 (func $fmaf (param $0 f32) (param $1 f32) (param $2 f32) (result f32)
  (f32.add (f32.mul (local.get 0) (local.get 1)) (local.get 2)))
"""


def prepare(tmp_path, body):
    source, destination = tmp_path / "input.wat", tmp_path / "output.wat"
    source.write_text("(module\n" + BOUNDARIES + body + ")\n")
    report = wasm_float.transform(source, destination)
    return source, destination, report


def test_engine_functions_libm_and_data_are_unchanged(tmp_path):
    untouched = """ (func $EngineMath (param f32) (result f32)
  (f32.add (call $sinf (local.get 0)) (f32.const 1)))
 (func $sinf (param f32) (result f32) (f32.add (local.get 0) (f32.const 1)))
 (data (i32.const 0) " (func $fake (f32.mul (call $fmaf)) ) \\" text")
"""
    body = """ (func $"atelier::skate::Example(float)" (param f32) (result f32)
  (f32.add (call $sinf (local.get 0)) (f32.const 1)))
"""
    source, destination, report = prepare(tmp_path, untouched + body)
    result = destination.read_text()
    assert untouched in result
    assert "(call $atelier_ftz_libm_sinf " in result
    assert "(func $atelier_ftz_libm_sinf " in result
    # The IEEE software FMA body is retained, never recursively flushed.
    assert BOUNDARIES[BOUNDARIES.index(" (func $fmaf") :].strip() in result
    assert report["private_libm_functions"] == ["$sinf"]
    assert untouched in source.read_text()


def test_quoted_function_name_is_not_instruction_text():
    name = '$"atelier::skate::name (f32.mul (call $fmaf))"'
    body = f" (func {name} (result f32) (f32.mul (f32.const 1) (f32.const 2)))"
    counts = Counter()
    result = wasm_float.rewrite(
        body, {"f32.mul": "$multiply"}, {"$fmaf": "$fused"}, counts
    )
    assert name in result
    assert result.endswith("(call $multiply (f32.const 1) (f32.const 2)))")
    assert counts == {"f32.mul": 1}


@pytest.mark.parametrize(
    "operation", ["f32.relaxed_new", "f32x4.relaxed_madd", "call $atan2f", "call $fma"]
)
def test_unsupported_arithmetic_preserves_input_and_removes_partial_output(
    tmp_path, operation
):
    source, destination = tmp_path / "input.wat", tmp_path / "output.wat"
    original = (
        "(module\n"
        + BOUNDARIES
        + f' (func $"atelier::skate::Bad()" ({operation}))\n)\n'
    )
    source.write_text(original)
    with pytest.raises(ValueError, match="Unsupported"):
        wasm_float.transform(source, destination)
    assert source.read_text() == original
    assert not destination.exists()


def test_missing_boundary_and_repeated_preparation_fail(tmp_path):
    source, destination, _ = prepare(tmp_path, "")
    with pytest.raises(ValueError, match="already contains"):
        wasm_float.transform(destination, tmp_path / "twice.wat")
    source.write_text(source.read_text().replace("VectorMin", "RemovedMin"))
    with pytest.raises(ValueError, match="Missing retained"):
        wasm_float.transform(source, tmp_path / "missing.wat")
    assert not (tmp_path / "missing.wat").exists()


@pytest.mark.parametrize(
    "command,lto",
    [("em++ -O0 -O2", False), ("em++ -O0", True), ("em++ objects.o", False)],
)
def test_early_optimization_or_lto_is_refused(tmp_path, command, lto):
    manifest = tmp_path / "link.json"
    manifest.write_text(json.dumps({"CommandArguments": command, "bAllowLTCG": lto}))
    with pytest.raises(ValueError, match="unoptimized initial link"):
        prepare_wasm.validate_link_manifest(manifest)


def test_final_link_option_wins_and_quoted_paths_are_not_options(tmp_path):
    manifest = tmp_path / "link.json"
    manifest.write_text(
        json.dumps(
            {"CommandArguments": 'em++ -O2 "some folder/-O3" -O0', "bAllowLTCG": False}
        )
    )
    assert len(prepare_wasm.validate_link_manifest(manifest)) == 64


def test_eliminated_fma_argument_is_refused_before_assembly(tmp_path):
    source, destination, _ = prepare(tmp_path, "")
    source.write_text(source.read_text().replace("(param $2 f32)", ""))
    with pytest.raises(ValueError, match="Optimized ABI"):
        wasm_float.transform(source, tmp_path / "bad-abi.wat")


def test_lane_memory_spelling_preserves_operands_and_quoted_data(tmp_path):
    source, destination = tmp_path / "lane.wat", tmp_path / "explicit.wat"
    original = '''(module
 (import "env" "memory" (memory $mimport$0 1 2))
 (func $"v128.store64_lane 1" (param v128)
  (v128.store64_lane align=1 1
   (i32.const 16) (local.get 0))
  (v128.store32_lane $mimport$0 2 (i32.const 0) (local.get 0)))
 (data (i32.const 0) "(v128.store64_lane 1)")
)
'''
    source.write_text(original)
    assert prepare_wasm.explicit_lane_memory(source, destination) == 1
    assert destination.read_text() == original.replace(
        "  (v128.store64_lane align=1 1", "  (v128.store64_lane $mimport$0 align=1 1"
    )
    source.write_text(original.replace(" (func", " (memory $second 1)\n (func", 1))
    with pytest.raises(ValueError, match="exactly one memory"):
        prepare_wasm.explicit_lane_memory(source, tmp_path / "invalid.wat")
