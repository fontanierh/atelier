"""Sparse eight-sector Kuwahara kernel, compiled to straight-line HLSL at setup.

The brush footprint scales with Radius and depth; work stays at 21 taps.
Sector weights are normalized offline, removing per-pixel trig, exp and divisions.
"""
import math


def kernel():
    taps = []
    for y in range(-2, 3):
        for x in range(-2, 3):
            if x * x + y * y > 5:
                continue
            u, v = x / math.sqrt(5), y / math.sqrt(5)
            weights = []
            for k in range(8):
                a = k * math.pi / 4
                px = u * math.cos(a) + v * math.sin(a)
                py = -u * math.sin(a) + v * math.cos(a)
                w = max(0.0, px + 0.35 - 3.5 * py * py)
                weights.append(w * w * math.exp(-2.5 * (u * u + v * v)))
            taps.append((u, v, weights))
    totals = [sum(t[2][k] for t in taps) for k in range(8)]
    return [(x, y, tuple(w / totals[k] for k, w in enumerate(ws))) for x, y, ws in taps]


def shader():
    lines = [
        "float3 outc = Scene;",
        "if (Strength > 0.001) {",
        # Simplify far woodland into painted masses while keeping nearby grass
        # and character silhouettes readable. SceneZ is linear depth in cm.
        "float distancePaint = smoothstep(1800.0, 14000.0, SceneZ.r);",
        "float radius = clamp(Radius * (1.0 + distancePaint), 1.0, 8.0);",
        "float strength = lerp(Strength, Strength + (1.0 - Strength) * 0.25, distancePaint);",
    ]
    for k in range(8):
        lines.append(f"float3 m{k} = 0, s{k} = 0;")
    for i, (x, y, weights) in enumerate(kernel()):
        sample = "Scene" if x == 0 and y == 0 else f"SceneTextureLookup(clamp(uv + float2({x:.9f}, {y:.9f}) * radius * d, uvMin, uvMax), 14, true).rgb"
        lines.append(f"float3 c{i} = {sample};")
        lines.append(f"float3 c2_{i} = c{i} * c{i};")
        for k, weight in enumerate(weights):
            if weight > 0:
                lines.append(f"m{k} += c{i} * {weight:.10f}; s{k} += c2_{i} * {weight:.10f};")
    lines.append("float3 acc = 0; float wt = 0;")
    for k in range(8):
        lines.extend([
            f"float3 var{k} = s{k} - m{k} * m{k};",
            f"float v{k} = max(0.0, var{k}.r + var{k}.g + var{k}.b);",
            # (sqrt(v) * 16)^4 == 65536 * v^2; no sqrt/pow required.
            f"float w{k} = rcp(1.0 + 65536.0 * v{k} * v{k});",
            f"acc += m{k} * w{k}; wt += w{k};",
        ])
    lines.extend(["outc = lerp(Scene, acc / max(wt, 1e-8), strength);", "}"])
    return "\n".join(lines)
