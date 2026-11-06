// The painterly filter (painterly.rs says what it does, and writes its taps where TAPS stands below). It works on
// gamma-encoded colours, as they show on screen.

struct Painterly {
    strength: f32,
    radius: f32,
    padding: vec2<f32>,
}

@group(0) @binding(0) var screen: texture_2d<f32>;
@group(0) @binding(1) var screen_sampler: sampler;
@group(0) @binding(2) var<uniform> settings: Painterly;

fn shown(uv: vec2<f32>) -> vec3<f32> {
    return pow(max(textureSampleLevel(screen, screen_sampler, uv, 0.0).rgb, vec3(0.0)), vec3(1.0 / 2.2));
}

// How much a wedge counts: smooth wedges count far more than busy ones.
fn weight(mean: vec3<f32>, square: vec3<f32>) -> f32 {
    let spread = square - mean * mean;
    let v = max(0.0, spread.r + spread.g + spread.b);
    return 1.0 / (1.0 + 65536.0 * v * v);
}

@fragment
fn fragment(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
    let original = textureSampleLevel(screen, screen_sampler, uv, 0.0);
    let step = settings.radius / vec2<f32>(textureDimensions(screen));
    // Per wedge k, the weighted mean (mk) and mean square (sk) of the colours, in plain variables rather than arrays so
    // they stay in registers.
    var c: vec3<f32>;
    // TAPS
    let painted = pow(sum / max(total, 1e-8), vec3(2.2));
    return vec4(mix(original.rgb, painted, settings.strength), original.a);
}
