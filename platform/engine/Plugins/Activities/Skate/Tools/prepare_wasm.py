"""Required post-link preparation for an HTML5 target containing AtelierSkate.

Run under the enclosing build's normal admission and memory guard. The SDK must
match the engine pin; no tools are downloaded and no engine sources are edited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import time
import uuid

from wasm_float import tokens, transform

SDK_VERSION = "6.0.10"
POLICY_FILES = ("prepare_wasm.py", "wasm_float.py", "wasm_float_helpers.py")
# Explicit supported profile for the pinned fork's MEMORY64=2 output. Enabling
# every proposal can change binary encodings even when the module does not use
# them. An unsupported proposal must fail assembly instead of changing the ABI.
FEATURES = [
    "--enable-mutable-globals",
    "--enable-nontrapping-float-to-int",
    "--enable-sign-ext",
    "--enable-bulk-memory",
    "--enable-reference-types",
    "--enable-simd",
    "--enable-threads",
    "--enable-exception-handling",
    "--enable-multivalue",
]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def policy_digest() -> str:
    result = hashlib.sha256()
    for name in POLICY_FILES:
        result.update(name.encode() + b"\0")
        result.update(
            Path(__file__).with_name(name).read_bytes().replace(b"\r\n", b"\n")
        )
    return result.hexdigest()


def run(label: str, command: list[str]) -> None:
    print(label, flush=True)
    start = time.monotonic()
    child = subprocess.Popen(command)
    try:
        while child.poll() is None:
            try:
                child.wait(25)
            except subprocess.TimeoutExpired:
                print(
                    f"{label}: {time.monotonic() - start:.0f}s elapsed; no new tool progress reported.",
                    flush=True,
                )
        if child.returncode:
            raise subprocess.CalledProcessError(child.returncode, command)
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait()


def validate_link_manifest(path: Path) -> str:
    metadata = json.loads(path.read_text())
    command = shlex.split(metadata["CommandArguments"])
    optimization = [
        arg
        for arg in command
        if arg in ("-O0", "-O1", "-O2", "-O3", "-Os", "-Oz", "-Og")
    ]
    if (
        not optimization
        or optimization[-1] != "-O0"
        or metadata.get("bAllowLTCG") is not False
    ):
        raise ValueError(
            "Skating FTZ requires an unoptimized initial link without LTO; optimize after preparation"
        )
    return digest(path)


def explicit_lane_memory(source: Path, destination: Path) -> int:
    """Disambiguate canonical single-memory SIMD lane instructions.

    Binaryen's pinned parser mistakes an implicit lane number for a memory
    index, then scans the entire preceding text to construct a discarded error.
    Naming the existing memory avoids that quadratic path without changing any
    instruction, immediate or operand. Only canonical instruction lines change;
    quoted names and data remain untouched. Refuse multi-memory input.
    """
    if source.resolve() == destination.resolve():
        raise ValueError("Use a separate canonicalization output")
    memory = []
    with source.open() as stream:
        for line in stream:
            if line.startswith((" (memory ", " (import ")):
                header = [t.value for t in tokens(line)]
                index = 2 if header[1] == "memory" else 6
                if header[index - 1] != "memory":
                    continue
                if not header[index].startswith("$"):
                    raise ValueError("Expected a named canonical memory declaration")
                memory.append(header[index])
    if len(memory) != 1:
        raise ValueError("Lane canonicalization requires exactly one memory")
    lane = re.compile(r"^(\s*\(v128\.(?:load|store)(?:8|16|32|64)_lane)(\s+)(.*)$")
    changed = 0
    try:
        with source.open() as stream, destination.open("w") as output:
            for line in stream:
                match = lane.match(line)
                if match and not match[3].startswith("$"):
                    line = match[1] + " " + memory[0] + match[2] + match[3] + "\n"
                    changed += 1
                output.write(line)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return changed


def prepare(wasm: Path, work: Path, emsdk: Path, link_manifest: Path) -> dict:
    wasm, work, emsdk = wasm.resolve(), work.resolve(), emsdk.resolve()
    link_hash = validate_link_manifest(link_manifest)
    compiler = emsdk / "upstream/emscripten/emcc"
    version = subprocess.check_output(
        [str(compiler), "--version"], text=True
    ).splitlines()[0]
    if not version.startswith(
        f"emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) {SDK_VERSION} "
    ):
        raise ValueError(f"Expected Emscripten {SDK_VERSION}; received {version}")
    # Rewriting offsets invalidates DWARF/maps. The target disables debug info;
    # refuse an inconsistent invocation instead of silently dropping sidecars.
    if any(
        p.exists()
        for p in (wasm.with_suffix(".wasm.map"), wasm.with_suffix(".wasm.debug.wasm"))
    ):
        raise ValueError("FTZ preparation requires an HTML5 build with DebugInfo=None")
    with wasm.open("rb") as stream:
        if stream.read(8) != b"\0asm\x01\0\0\0":
            raise ValueError("Expected a linked Wasm module")
    policy, input_hash = policy_digest(), digest(wasm)
    latest = work / "latest.json"
    if latest.exists():
        previous = json.loads(latest.read_text())
        if (
            previous["output_sha256"] == input_hash
            and previous["policy_sha256"] == policy
            and previous["compiler"] == version
            and previous["link_manifest_sha256"] == link_hash
        ):
            print("Verified existing browser FTZ preparation.", flush=True)
            return previous

    stage = work / ("prepare-" + uuid.uuid4().hex)
    stage.mkdir(parents=True)
    original, wat, prepared, assembly_text, assembled, optimized = (
        stage / name
        for name in (
            "input.wasm",
            "input.wat",
            "prepared.wat",
            "assembly.wat",
            "assembled.wasm",
            "output.wasm",
        )
    )
    shutil.copyfile(wasm, original)
    bins = emsdk / "upstream/bin"
    suffix = ".exe" if os.name == "nt" else ""
    tool = lambda name: str(bins / (name + suffix))
    run("Read linked browser module", [tool("wasm-dis"), str(original), "-o", str(wat)])
    features = FEATURES
    print("Apply scoped skating arithmetic policy", flush=True)
    report = transform(
        wat, prepared, progress=lambda message: print(message, flush=True)
    )
    wat.unlink()
    report["explicit_lane_memories"] = explicit_lane_memory(prepared, assembly_text)
    prepared.unlink()
    run(
        "Assemble and validate prepared module",
        [tool("wasm-as"), str(assembly_text), *features, "-g", "-o", str(assembled)],
    )
    assembly_text.unlink()
    # The initial link retains named boundaries. Optimize only once their FTZ
    # semantics are explicit. Keep the default tiny-function threshold and no
    # single-caller expansion: whole-engine inlining exceeds bounded build RAM.
    optimization = [
        "-O2",
        "--always-inline-max-function-size=2",
        "--flexible-inline-max-function-size=0",
        "--one-caller-inline-max-function-size=0",
        "--inline-max-combined-binary-size=8192",
    ]
    run(
        "Optimize prepared browser module",
        [
            tool("wasm-opt"),
            str(assembled),
            *features,
            *optimization,
            "-g",
            "-o",
            str(optimized),
        ],
    )
    report.update(
        link_manifest_sha256=link_hash,
        input_sha256=input_hash,
        output_sha256=digest(optimized),
        policy_sha256=policy,
        compiler=version,
        features=features,
        optimization=optimization,
        input_bytes=wasm.stat().st_size,
        output_bytes=optimized.stat().st_size,
    )
    (stage / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    pending = work / "latest.pending.json"
    pending.write_text(json.dumps(report, indent=2) + "\n")
    # Until validation succeeds, the linked module remains intact. Publish the
    # module before its receipt: interruption then fails the next verification.
    optimized.replace(wasm)
    pending.replace(latest)
    assembled.unlink()
    print(
        f"Browser FTZ prepared: {len(report['simulation_functions'])} simulation functions, "
        f"{report['output_bytes']} bytes.",
        flush=True,
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wasm", type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--link-manifest", required=True, type=Path)
    parser.add_argument("--emsdk", type=Path, default=os.environ.get("EMSDK"))
    args = parser.parse_args()
    if args.emsdk is None:
        parser.error("Set EMSDK or pass --emsdk for the pinned SDK")
    prepare(args.wasm, args.work, args.emsdk, args.link_manifest)
