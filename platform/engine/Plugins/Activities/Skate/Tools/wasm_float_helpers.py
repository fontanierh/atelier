"""Instruction helpers for the skating simulation's binary32 FTZ policy.

These helpers flush arithmetic operands/results, preserving bitwise moves and
signed zero. FMA retains its IEEE software body and flushes at the call boundary;
its TwoSum test detects pre-rounding binary32 underflow. Never run this generator
through its own instruction transform.
"""


def generate(available: set[str]) -> tuple[dict[str, str], dict[str, str], list[str]]:
    helpers: list[str] = []
    operators: dict[str, str] = {}
    calls: dict[str, str] = {}
    for ty, width, exponent, sign in [
        ("f32", "i32", "0x7f800000", "0x80000000"),
        ("f64", "i64", "0x7ff0000000000000", "0x8000000000000000"),
    ]:
        helpers.append(f"""(func $atelier_ftz_{ty} (param $x {ty}) (result {ty})
      (local $bits {width})
      (local.set $bits ({width}.reinterpret_{ty} (local.get $x)))
      (if (result {ty}) ({width}.eqz ({width}.and (local.get $bits) ({width}.const {exponent})))
        (then ({ty}.reinterpret_{width} ({width}.and (local.get $bits) ({width}.const {sign}))))
        (else (local.get $x))))""")

        def clean(i):
            return f"(call $atelier_ftz_{ty} (local.get ${i}))"

        for op in [
            "add",
            "sub",
            "mul",
            "div",
            "min",
            "max",
            "eq",
            "ne",
            "lt",
            "gt",
            "le",
            "ge",
            "sqrt",
            "ceil",
            "floor",
            "trunc",
            "nearest",
        ]:
            arity = 1 if op in ["sqrt", "ceil", "floor", "trunc", "nearest"] else 2
            result = "i32" if op in ["eq", "ne", "lt", "gt", "le", "ge"] else ty
            name = f"{ty}_{op}"
            body = f"({ty}.{op} " + " ".join(clean(i) for i in range(arity)) + ")"
            if result == ty:
                body = f"(call $atelier_ftz_{ty} {body})"
            helpers.append(
                f"(func $atelier_ftz_{name} "
                + "".join(f"(param ${i} {ty}) " for i in range(arity))
                + f"(result {result}) {body})"
            )
            operators[f"{ty}.{op}"] = f"$atelier_ftz_{name}"
        # Conversion to integer observes flushed operands.
        for integer in ["i32", "i64"]:
            for mode in ["s", "u"]:
                for sat in ["", "sat_"]:
                    op = f"{integer}.trunc_{sat}{ty}_{mode}"
                    name = op.replace(".", "_")
                    helpers.append(
                        f"(func $atelier_ftz_{name} (param $0 {ty}) (result {integer}) ({op} {clean(0)}))"
                    )
                    operators[op] = "$atelier_ftz_" + name
    for op, source, target in [
        ("f32.demote_f64", "f64", "f32"),
        ("f64.promote_f32", "f32", "f64"),
    ]:
        name = op.replace(".", "_")
        if target == "f32":
            helpers.append(f"""(func $atelier_ftz_{name} (param $0 f64) (result f32)
            (local $clean f64)
            (local.set $clean (call $atelier_ftz_f64 (local.get $0)))
            (if (result f32) (f64.lt (f64.abs (local.get $clean)) (f64.const 0x1p-126))
              (then (f32.copysign (f32.const 0) (f32.demote_f64 (local.get $clean))))
              (else (call $atelier_ftz_f32 (f32.demote_f64 (local.get $clean))))))""")
        else:
            helpers.append(
                f"(func $atelier_ftz_{name} (param $0 {source}) (result {target}) (call $atelier_ftz_{target} ({op} (call $atelier_ftz_{source} (local.get $0)))))"
            )
        operators[op] = "$atelier_ftz_" + name
    calls["$fmaf"] = "$atelier_ftz_fmaf"
    if "$fma" in available:
        # Camera angle reduction's mixed int/float overload promotes binary32
        # operands to binary64. Keep software double FMA IEEE internally too.
        calls["$fma"] = "$atelier_ftz_fma"
        helpers.append("""(func $atelier_ftz_fma (param $a f64) (param $b f64) (param $c f64) (result f64)
        (call $atelier_ftz_f64 (call $fma
          (call $atelier_ftz_f64 (local.get $a))
          (call $atelier_ftz_f64 (local.get $b))
          (call $atelier_ftz_f64 (local.get $c)))))""")
    helpers.extend(
        [
            """(func $atelier_ftz_nan (param $x f32) (result i32)
        (i32.gt_u (i32.and (i32.reinterpret_f32 (local.get $x)) (i32.const 0x7fffffff)) (i32.const 0x7f800000)))""",
            """(func $atelier_ftz_signaling_nan (param $x f32) (result i32)
        (i32.and (call $atelier_ftz_nan (local.get $x))
          (i32.eqz (i32.and (i32.reinterpret_f32 (local.get $x)) (i32.const 0x400000)))))""",
            """(func $atelier_ftz_quiet_nan (param $x f32) (result f32)
        (f32.reinterpret_i32 (i32.or (i32.reinterpret_f32 (local.get $x)) (i32.const 0x400000))))""",
        ]
    )
    helpers.append("""(func $atelier_ftz_fmaf (param $a f32) (param $b f32) (param $c f32) (result f32)
    (local $A f32) (local $B f32) (local $C f32) (local $p f64) (local $s f64) (local $z f64) (local $e f64)
    (local.set $A (call $atelier_ftz_f32 (local.get $a)))
    (local.set $B (call $atelier_ftz_f32 (local.get $b)))
    (local.set $C (call $atelier_ftz_f32 (local.get $c)))
    (if (call $atelier_ftz_signaling_nan (local.get $C)) (then (return (call $atelier_ftz_quiet_nan (local.get $C)))))
    (if (call $atelier_ftz_signaling_nan (local.get $A)) (then (return (call $atelier_ftz_quiet_nan (local.get $A)))))
    (if (call $atelier_ftz_signaling_nan (local.get $B)) (then (return (call $atelier_ftz_quiet_nan (local.get $B)))))
    (if (i32.or
      (i32.and (f32.eq (f32.abs (local.get $A)) (f32.const inf)) (f32.eq (local.get $B) (f32.const 0)))
      (i32.and (f32.eq (f32.abs (local.get $B)) (f32.const inf)) (f32.eq (local.get $A) (f32.const 0))))
      (then (return (f32.const nan))))
    (if (call $atelier_ftz_nan (local.get $C)) (then (return (call $atelier_ftz_quiet_nan (local.get $C)))))
    (if (call $atelier_ftz_nan (local.get $A)) (then (return (call $atelier_ftz_quiet_nan (local.get $A)))))
    (if (call $atelier_ftz_nan (local.get $B)) (then (return (call $atelier_ftz_quiet_nan (local.get $B)))))
    (local.set $p (f64.mul (f64.promote_f32 (local.get $A)) (f64.promote_f32 (local.get $B))))
    (local.set $s (f64.add (local.get $p) (f64.promote_f32 (local.get $C))))
    (local.set $z (f64.sub (local.get $s) (local.get $p)))
    (local.set $e (f64.add (f64.sub (local.get $p) (f64.sub (local.get $s) (local.get $z))) (f64.sub (f64.promote_f32 (local.get $C)) (local.get $z))))
    (if (result f32)
     (i32.or (f64.lt (f64.abs (local.get $s)) (f64.const 0x1p-126))
      (i32.and (f64.eq (f64.abs (local.get $s)) (f64.const 0x1p-126)) (f64.lt (f64.mul (local.get $s) (local.get $e)) (f64.const 0))))
     (then (f32.copysign (f32.const 0) (f32.demote_f64 (local.get $s))))
     (else (call $atelier_ftz_f32 (call $fmaf (local.get $A) (local.get $B) (local.get $C))))))""")
    for op in ["mul", "div"]:
        name = "f32_" + op
        body = f"""(func $atelier_ftz_{name} (param $0 f32) (param $1 f32) (result f32)
     (local $a f32) (local $b f32) (local $wide f64)
     (local.set $a (call $atelier_ftz_f32 (local.get $0)))
     (local.set $b (call $atelier_ftz_f32 (local.get $1)))
     (local.set $wide (f64.{op} (f64.promote_f32 (local.get $a)) (f64.promote_f32 (local.get $b))))
     (if (result f32) (f64.lt (f64.abs (local.get $wide)) (f64.const 0x1p-126))
      (then (f32.copysign (f32.const 0) (f32.demote_f64 (local.get $wide))))
      (else (call $atelier_ftz_f32 (f32.{op} (local.get $a) (local.get $b))))))"""
        helpers = [
            body if h.startswith(f"(func $atelier_ftz_{name} ") else h for h in helpers
        ]
    for op in ["fminf", "fmaxf"]:
        if "$" + op in available:
            calls["$" + op] = "$atelier_ftz_" + op
            helpers.append(
                f"(func $atelier_ftz_{op} (param $a f32) (param $b f32) (result f32) (call $atelier_ftz_f32 (call ${op} (call $atelier_ftz_f32 (local.get $a)) (call $atelier_ftz_f32 (local.get $b)))))"
            )

    for vector, scalar, lanes, integer, exponent, sign in [
        ("f32x4", "f32", 4, "i32x4", "0x7f800000", "0x80000000"),
        ("f64x2", "f64", 2, "i64x2", "0x7ff0000000000000", "0x8000000000000000"),
    ]:
        mask = lambda value: (
            "(v128.const " + integer + " " + " ".join([value] * lanes) + ")"
        )
        helpers.append(
            f"(func $atelier_ftz_{vector} (param $v v128) (result v128) (v128.bitselect (v128.and (local.get $v) {mask(sign)}) (local.get $v) ({integer}.eq (v128.and (local.get $v) {mask(exponent)}) {mask('0')})))"
        )
        for op in [
            "add",
            "sub",
            "mul",
            "div",
            "min",
            "max",
            "pmin",
            "pmax",
            "eq",
            "ne",
            "lt",
            "gt",
            "le",
            "ge",
            "sqrt",
            "ceil",
            "floor",
            "trunc",
            "nearest",
        ]:
            arity = 1 if op in ["sqrt", "ceil", "floor", "trunc", "nearest"] else 2
            result = (
                "("
                + vector
                + "."
                + op
                + " "
                + " ".join(
                    f"(call $atelier_ftz_{vector} (local.get ${i}))"
                    for i in range(arity)
                )
                + ")"
            )
            if op not in ["eq", "ne", "lt", "gt", "le", "ge"]:
                result = f"(call $atelier_ftz_{vector} {result})"
            if scalar == "f32" and op in ["mul", "div"]:
                result = "(v128.const i32x4 0 0 0 0)"
                for lane in range(4):
                    result = f"(f32x4.replace_lane {lane} {result} (call $atelier_ftz_f32_{op} (f32x4.extract_lane {lane} (local.get $0)) (f32x4.extract_lane {lane} (local.get $1))))"
            name = vector + "_" + op
            helpers.append(
                f"(func $atelier_ftz_{name} "
                + "".join(f"(param ${i} v128) " for i in range(arity))
                + f"(result v128) {result})"
            )
            operators[vector + "." + op] = "$atelier_ftz_" + name
    for op, source, target in [
        ("f32x4.demote_f64x2_zero", "f64x2", "f32x4"),
        ("f64x2.promote_low_f32x4", "f32x4", "f64x2"),
    ]:
        name = op.replace(".", "_")
        body = f"(call $atelier_ftz_{target} ({op} (call $atelier_ftz_{source} (local.get $0))))"
        if target == "f32x4":
            body = "(v128.const i32x4 0 0 0 0)"
            for lane in range(2):
                body = f"(f32x4.replace_lane {lane} {body} (call $atelier_ftz_f32_demote_f64 (f64x2.extract_lane {lane} (local.get $0))))"
        helpers.append(
            f"(func $atelier_ftz_{name} (param $0 v128) (result v128) {body})"
        )
        operators[op] = "$atelier_ftz_" + name
    return operators, calls, helpers
