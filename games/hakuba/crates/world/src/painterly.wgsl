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
    return pow(max(textureSample(screen, screen_sampler, uv).rgb, vec3(0.0)), vec3(1.0 / 2.2));
}

@fragment
fn fragment(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
    let original = textureSample(screen, screen_sampler, uv);
    let step = settings.radius / vec2<f32>(textureDimensions(screen));
    // Per wedge, the weighted mean and mean square of the colours.
    var means: array<vec3<f32>, 8>;
    var squares: array<vec3<f32>, 8>;
    var c: vec3<f32>;
    // TAPS
    // Smooth wedges count far more than busy ones.
    var sum = vec3(0.0);
    var total = 0.0;
    for (var k = 0u; k < 8u; k++) {
        let spread = squares[k] - means[k] * means[k];
        let v = max(0.0, spread.r + spread.g + spread.b);
        let w = 1.0 / (1.0 + 65536.0 * v * v);
        sum += means[k] * w;
        total += w;
    }
    let painted = pow(sum / max(total, 1e-8), vec3(2.2));
    return vec4(mix(original.rgb, painted, settings.strength), original.a);
}
