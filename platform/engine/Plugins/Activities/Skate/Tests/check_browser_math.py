#!/usr/bin/env python3
"""Compare current native FTZ and prepared Wasm math, including every NaN bit.

Invoke under the normal native compile guard, with the pinned SDK active:
  python3 check_browser_math.py --emsdk SDK --output build/GAME/browser-math

This is an explicit native check, outside ordinary Python unit discovery. It
does not acquire a second lock or claim whole-game/browser-render validation.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import random
import shlex
import struct
import subprocess
import sys

from check_math_parity import corpus

PLUGIN = Path(__file__).resolve().parents[1]
CORE = PLUGIN / "Source/AtelierSkate/Private/Simulation"
sys.path.insert(0, str(PLUGIN / "Tools"))
from prepare_wasm import prepare

EDGES = [
    0,
    0x80000000,
    1,
    0x80000001,
    0x7FFFFF,
    0x807FFFFF,
    0x800000,
    0x80800000,
    0x3F800000,
    0xBF800000,
    0x3F800001,
    0x3F7FFFFF,
    0x7F7FFFFF,
    0xFF7FFFFF,
    0x7F800000,
    0xFF800000,
    0x7FC00000,
    0xFFC00000,
    0x7FC12345,
    0xFFC12345,
    0x7F812345,
    0xFF812345,
]
EXTRA = """namespace atelier::skate {
__attribute__((noinline)) float BrowserMathFma(float a,float b,float c) { return std::fma(a,b,c); }
__attribute__((noinline)) float BrowserMathDemote(double value) { return static_cast<float>(value); }
__attribute__((noinline)) float BrowserMathMultiply(float a,float b) { return a*b; }
__attribute__((noinline)) float BrowserMathDivide(float a,float b) { return a/b; }
}
"""
CASES = """            case 10: {
                const float y=reader.Scalar(),x=reader.Scalar(); Scalar(Atan2(y,x)); break;
            }
            case 11: {
                const float a=reader.Scalar(),b=reader.Scalar(),c=reader.Scalar();
                Scalar(BrowserMathFma(a,b,c)); break;
            }
            case 12: {
                const auto low=reader.Word(),high=reader.Word();
                const std::uint64_t bits=std::uint64_t(low)|(std::uint64_t(high)<<32);
                double value; std::memcpy(&value,&bits,8); Scalar(BrowserMathDemote(value)); break;
            }
            case 13: {
                const float a=reader.Scalar(),b=reader.Scalar();
                Scalar(BrowserMathMultiply(a,b)); Scalar(BrowserMathDivide(a,b)); break;
            }
"""


def inputs():
    raw, original = corpus()
    records = [raw[4:]]
    count = len(original)

    def add(operation, values):
        nonlocal count
        records.append(struct.pack("<" + "I" * (len(values) + 1), operation, *values))
        count += 1

    rng = random.Random(0x4154414E)
    pairs = list(itertools.product(EDGES, repeat=2))
    pairs.extend((rng.getrandbits(32), rng.getrandbits(32)) for _ in range(32768))
    word = lambda value: struct.unpack("<I", struct.pack("<f", value))[0]
    pairs.extend(
        (word(rng.uniform(-1, 1)), word(rng.uniform(-1, 1))) for _ in range(32768)
    )
    for pair in pairs:
        add(10, pair)
    for triple in itertools.product(EDGES, repeat=3):
        add(11, triple)
    # Values immediately below the binary32 normal boundary that round up to
    # it under IEEE conversion. FTZ must decide tininess before that rounding.
    boundary = float.fromhex("0x1p-126")
    for sign in (-1, 1):
        for value in (
            boundary,
            boundary - float.fromhex("0x1p-151"),
            boundary - float.fromhex("0x1p-150"),
            float.fromhex("0x1p-149"),
        ):
            bits = struct.unpack("<Q", struct.pack("<d", sign * value))[0]
            add(12, (bits & 0xFFFFFFFF, bits >> 32))
    for pair in itertools.product(EDGES, repeat=2):
        add(13, pair)
    return struct.pack("<I", count) + b"".join(records), len(original), count


def check(output: Path, emsdk: Path):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw, original_count, count = inputs()
    (output / "input.bin").write_bytes(raw)
    source = (PLUGIN / "Tests/Simulation/math_probe.cpp").read_text()
    assert source.count("int main()\n{") == source.count("            default:") == 1
    source = source.replace(
        "int main()\n{",
        "int main()\n{\n    if (std::fesetenv(FE_DFL_ENV)!=0 || !FlushDenormalsToZero()) return 3;",
    )
    source = source.replace("            default:", CASES + "            default:")
    source = source.replace(
        "using namespace atelier::skate;", EXTRA + "\nusing namespace atelier::skate;"
    )
    probe = output / "probe.cpp"
    probe.write_text("#include <cfenv>\n" + source)
    flags = [
        "-std=c++20",
        "-O2",
        "-ffp-contract=off",
        "-fno-fast-math",
        "-I",
        str(CORE),
    ]
    sources = (CORE / "SimulationMath.cpp", CORE / "Geometry.cpp", probe)
    compiler = emsdk / "upstream/emscripten/em++"
    print(
        f"Compile {count} numeric cases ({original_count} unchanged math cases).",
        flush=True,
    )
    subprocess.run(
        ["clang++", *flags, *map(str, sources), "-o", str(output / "native")],
        check=True,
    )
    # Compile numerics normally, but preserve every namespace boundary at link
    # time. Even zero-sized inline thresholds permit some trivial forwarding.
    objects = []
    for source_file in sources:
        obj = output / (source_file.stem + ".o")
        subprocess.run(
            [
                str(compiler),
                *flags,
                "-msimd128",
                "-msse4.2",
                "-fno-math-errno",
                "-sMEMORY64=2",
                "-c",
                str(source_file),
                "-o",
                str(obj),
            ],
            check=True,
        )
        objects.append(str(obj))
    link = [
        str(compiler),
        *objects,
        "-O0",
        "-sMEMORY64=2",
        "-sMODULARIZE=1",
        "-sEXPORT_NAME=createSkateMath",
        "-sENVIRONMENT=web,node",
        "-sEXIT_RUNTIME=1",
        '-sEXPORTED_RUNTIME_METHODS=["callMain"]',
        "--profiling-funcs",
        "-Wl,--export=fma",
        "-Wl,--export=fmaf",
        "-sBINARYEN_EXTRA_PASSES=--always-inline-max-function-size=0,--flexible-inline-max-function-size=0,--one-caller-inline-max-function-size=0",
        "-o",
        str(output / "math.js"),
    ]
    subprocess.run(link, check=True)
    manifest = output / "link.json"
    manifest.write_text(
        json.dumps({"CommandArguments": shlex.join(link[1:]), "bAllowLTCG": False})
        + "\n"
    )
    runner = output / "runner.cjs"
    runner.write_text("""const fs=require('node:fs'),input=fs.readFileSync(0),output=[];let i=0;
require('./math.js')({noInitialRun:true,stdin:()=>i<input.length?input[i++]:null,stdout:b=>output.push(b)})
.then(m=>{m.callMain([]);fs.writeFileSync(1,Buffer.from(output));})
.catch(e=>{console.error(e);process.exitCode=1;});
""")
    # Use the active SDK's Node from PATH, as emsdk_env.sh configures it.
    negative = subprocess.run(["node", str(runner)], input=raw, capture_output=True)
    if negative.returncode != 3 or negative.stdout:
        raise ValueError("Unprepared Wasm did not refuse readiness")
    preparation = prepare(output / "math.wasm", output / "preparation", emsdk, manifest)
    native = subprocess.check_output([str(output / "native")], input=raw)
    wasm = subprocess.check_output(["node", str(runner)], input=raw)
    (output / "native.bin").write_bytes(native)
    (output / "wasm.bin").write_bytes(wasm)
    report = dict(
        preparation_policy_sha256=preparation["policy_sha256"],
        generated_probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
        cases=count,
        original_math_cases=original_count,
        bytes=[len(native), len(wasm)],
        input_sha256=hashlib.sha256(raw).hexdigest(),
        native_sha256=hashlib.sha256(native).hexdigest(),
        wasm_sha256=hashlib.sha256(wasm).hexdigest(),
        exact=native == wasm,
        comparison="Every output bit; no tolerance or NaN canonicalization",
        host=dict(system=platform.system(), machine=platform.machine()),
        compiler=subprocess.check_output([str(compiler), "--version"], text=True),
        sources_sha256={
            p.relative_to(PLUGIN).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                CORE / "SimulationMath.cpp",
                CORE / "SimulationMath.h",
                CORE / "SimulationWebMath.h",
                CORE / "Geometry.cpp",
                CORE / "Geometry.h",
                Path(__file__),
                PLUGIN / "Tests/Simulation/math_probe.cpp",
            ]
        },
    )
    if native != wasm:
        report["first_divergent_byte"] = next(
            (i for i, (a, b) in enumerate(zip(native, wasm)) if a != b),
            min(len(native), len(wasm)),
        )
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("compiler", "sources_sha256")}
        ),
        flush=True,
    )
    return report["exact"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--emsdk", type=Path, default=os.environ.get("EMSDK"))
    options = parser.parse_args()
    if options.emsdk is None:
        parser.error("Set EMSDK or pass --emsdk")
    raise SystemExit(0 if check(options.output, options.emsdk.resolve()) else 1)
