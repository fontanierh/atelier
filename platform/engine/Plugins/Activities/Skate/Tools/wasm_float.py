"""Apply the skating core's FTZ arithmetic to named Binaryen WAT functions.

Only simulation functions and private copies of their libm helpers change.
Engine functions, data segments and the original libc/libm remain untouched.
The input must come from wasm-dis with function names retained and link-time
inlining disabled. The final Wasm must be assembled and validated before use.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Iterator, TextIO

from wasm_float_helpers import generate


# These are the arithmetic libm bodies used by the current core, not an engine
# call graph. Clone them so a simulation call cannot change engine arithmetic.
# Software FMA stays IEEE internally; its caller observes the FTZ boundary.
LIBM = frozenset(
    "$" + name
    for name in (
        "__rem_pio2",
        "__rem_pio2_large",
        "atanf",
        "__sin",
        "__cos",
        "__rem_pio2f",
        "__tandf",
        "expf",
        "__sindf",
        "__cosdf",
        "round",
        "hypotf",
        "sinf",
        "cosf",
        "tanf",
        "scalbn",
        "fmodf",
        "frexp",
        "sin",
        "cos",
        "__math_xflowf",
    )
)
TOKEN = re.compile(r'(?:\$)?"(?:\\.|[^"\\])*"|[^\s()]+|[()]')
MOVE_OPERATIONS = frozenset(
    (
        "abs",
        "neg",
        "copysign",
        "const",
        "load",
        "store",
        "reinterpret_i32",
        "reinterpret_i64",
        "convert_i32_s",
        "convert_i32_u",
        "convert_i64_s",
        "convert_i64_u",
        "splat",
        "extract_lane",
        "replace_lane",
        "convert_i32x4_s",
        "convert_i32x4_u",
        "convert_low_i32x4_s",
        "convert_low_i32x4_u",
    )
)


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int


def tokens(text: str) -> list[Token]:
    """Tokenize canonical wasm-dis output, keeping quoted symbols indivisible."""
    # wasm-dis does not emit comments. Reject them rather than interpret a new
    # producer's syntax incorrectly. Comment markers inside strings are data.
    result = [Token(m[0], m.start(), m.end()) for m in TOKEN.finditer(text)]
    if any(t.value.startswith((";;", ";)", ";")) for t in result):
        raise ValueError("Expected comment-free canonical wasm-dis output")
    return result


def function_name(text: str) -> str:
    # Inspect only the declaration, not an arbitrarily large body.
    header = tokens(text.splitlines()[0])
    if len(header) < 3 or [t.value for t in header[:2]] != ["(", "func"]:
        raise ValueError("Expected a named function declaration")
    name = header[2].value
    if not name.startswith("$"):
        raise ValueError("Function names were stripped; retain --profiling-funcs")
    return name


def declarations(source: TextIO) -> Iterator[tuple[str | None, str]]:
    """Stream canonical top-level declarations; never parse a data string as code."""
    pending: list[str] = []
    name: str | None = None
    for line in source:
        if line.startswith(" (") or line.rstrip() == ")":
            if pending:
                yield name, "".join(pending)
            pending = []
            name = function_name(line) if line.startswith(" (func ") else None
        pending.append(line)
    if pending:
        yield name, "".join(pending)


def private_name(name: str) -> str:
    return "$atelier_ftz_libm_" + name[1:]


def rewrite(
    text: str,
    operators: dict[str, str],
    calls: dict[str, str],
    counts: Counter,
    *,
    rename: str | None = None,
) -> str:
    parts = tokens(text)
    edits: list[tuple[int, int, str]] = []
    if rename:
        edits.append((parts[2].start, parts[2].end, rename))
    for i, token in enumerate(parts):
        if i == 0 or parts[i - 1].value != "(":
            continue
        op = token.value
        if op in operators:
            edits.append((token.start, token.end, "call " + operators[op]))
            counts[op] += 1
        elif op in ("call", "return_call"):
            target = parts[i + 1]
            if target.value == "$atan2f" or (target.value == "$fma" and target.value not in calls):
                raise ValueError(f"Unsupported simulation math call: {target.value}")
            if target.value in calls:
                edits.append((target.start, target.end, calls[target.value]))
                counts["call " + target.value] += 1
        elif op.startswith(("f32.", "f64.", "f32x4.", "f64x2.")):
            # A newly introduced FP instruction needs an explicit numeric policy.
            suffix = op.split(".", 1)[1]
            if suffix not in MOVE_OPERATIONS:
                raise ValueError(f"Unsupported simulation float instruction: {op}")
        elif "relaxed" in op:
            raise ValueError(f"Relaxed instructions cannot preserve parity: {op}")
    chunks = []
    at = 0
    for start, end, value in edits:
        chunks.extend((text[at:start], value))
        at = end
    chunks.append(text[at:])
    return "".join(chunks)


def transform(
    source: Path, destination: Path, progress: Callable[[str], None] | None = None
) -> dict:
    """@cc [owner:fontanierh,label:correctness] browser-simulation-arithmetic
    Only named skating functions and private copies of their arithmetic libm
    dependencies may be rewritten. Unrelated functions and data must remain
    byte-identical. Missing readiness/min-max boundaries and unsupported float
    instructions must fail the build, never silently publish an IEEE fallback.
    """
    if source.resolve() == destination.resolve():
        raise ValueError("Use a separate output so failures preserve the input")
    headers = {}
    with source.open() as stream:
        for line in stream:
            if line.startswith(" (func "):
                headers[function_name(line)] = line
    names = set(headers)
    if any("atelier_ftz_" in name for name in names):
        raise ValueError("Input already contains FTZ helpers")
    minimum = '$"atelier::skate::VectorMin(float, float)"'
    maximum = '$"atelier::skate::VectorMax(float, float)"'
    readiness = '$"atelier::skate::FlushDenormalsToZero()"'
    missing = {minimum, maximum, readiness, "$fmaf"} - names
    if missing:
        raise ValueError(f"Missing retained arithmetic boundaries: {sorted(missing)}")
    for name, expected in (("$fma", ["f64"] * 3), ("$fmaf", ["f32"] * 3)):
        if name in headers:
            parameters = [value for group in re.findall(r"\(param ([^)]+)\)", headers[name])
                          for value in group.split() if not value.startswith("$")]
            if parameters != expected:
                raise ValueError(f"Optimized ABI for {name}; retain -Wl,--export=fma and -Wl,--export=fmaf at link time")
    operators, calls, helpers = generate(names)
    clones = names & LIBM
    calls.update({name: private_name(name) for name in clones})
    wrappers = {
        minimum: "$atelier_ftz_original_min",
        maximum: "$atelier_ftz_original_max",
    }
    for name, original in wrappers.items():
        helpers.append(
            f"(func {name} (param $a f32) (param $b f32) (result f32) "
            f"(call $atelier_ftz_f32 (call {original} "
            "(call $atelier_ftz_f32 (local.get $a)) "
            "(call $atelier_ftz_f32 (local.get $b)))))"
        )
    counts: Counter = Counter()
    changed = []
    private = []
    closed = False
    visited = 0
    try:
        with source.open() as stream, destination.open("w") as output:
            for name, declaration in declarations(stream):
                if name:
                    visited += 1
                    if progress and visited % 500 == 0:
                        progress(
                            f"Read {visited}/{len(names)} functions; prepared {len(changed)} simulation functions."
                        )
                if name and "atelier::skate::" in name:
                    declaration = rewrite(
                        declaration, operators, calls, counts, rename=wrappers.get(name)
                    )
                    changed.append(name)
                elif name in clones:
                    private.append(
                        rewrite(
                            declaration,
                            operators,
                            calls,
                            counts,
                            rename=private_name(name),
                        )
                    )
                if declaration.strip() == ")":
                    output.write("\n" + "\n".join(private + helpers) + "\n")
                    closed = True
                output.write(declaration)
        if not closed or not counts:
            raise ValueError("Incomplete module or no simulation arithmetic")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return {
        "simulation_functions": changed,
        "private_libm_functions": sorted(clones),
        "instructions": dict(sorted(counts.items())),
    }
