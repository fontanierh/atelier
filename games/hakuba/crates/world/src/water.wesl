// Source-authored opaque water: world-map wavelets remain continuous across tile boundaries.
import bevy_pbr::render::{
    forward_io::{VertexOutput, FragmentOutput}, mesh_view_bindings::globals,
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{apply_pbr_lighting, main_pass_post_lighting_processing},
};
struct WaterUniform {
    bounds: vec4<f32>, shore: vec4<f32>, waves: vec4<f32>, spectrum: vec4<f32>, warp: vec4<f32>, calm: vec4<f32>,
    deep: vec4<f32>, deep2: vec4<f32>, shallows: vec4<f32>, glint: vec4<f32>, drift_x: vec4<f32>, drift_y: vec4<f32>,
    crest: vec4<f32>, glint_range: vec4<f32>, drift_colour: vec4<f32>, fetch: vec4<f32>, roughness: vec4<f32>,
}
@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<uniform> water: WaterUniform;

fn harmonic(frequency: f32, amplitude: f32, angle: f32) -> f32 {
    if frequency < 0.0 { return amplitude * cos(-frequency * angle); }
    return amplitude * sin(frequency * angle);
}

@fragment
fn fragment(input: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    let p = vec2<f32>(input.world_position.x, -input.world_position.z);
    let relative = (p - water.bounds.xy) / water.bounds.zw;
    let angle = atan2(relative.y, relative.x);
    let shore = 1.0 + harmonic(water.shore.x, water.shore.y, angle) + harmonic(water.shore.z, water.shore.w, angle);
    let rim = length(relative) / shore;
    let shallows = smoothstep(water.calm.x, water.calm.y, rim);
    let calm = 1.0 - water.calm.z * shallows;
    let footprint = max(length(dpdx(p)), length(dpdy(p)));
    let time = globals.time;
    var slope = vec2<f32>(0.0);
    for (var i: u32 = 0u; i < u32(water.waves.x); i += 1u) {
        let n = f32(i);
        let a = water.waves.y + n * water.waves.z;
        let d = vec2<f32>(cos(a), sin(a));
        let k = water.waves.w * pow(water.spectrum.x, n);
        let foot = k * footprint;
        let amp = water.spectrum.y * pow(water.spectrum.z, n) * exp(-foot * foot * water.spectrum.w);
        let warp = sin(dot(p, vec2<f32>(-d.y, d.x)) * k * water.warp.x + time * water.warp.y + n) * water.warp.z;
        slope += d * cos(dot(p, d) * k + warp + time * sqrt(water.calm.w * k) + n * water.warp.w) * amp;
    }
    let drift = (sin(dot(p, water.drift_x.xy) + time * water.drift_x.z) + sin(dot(p, water.drift_y.xy) + time * water.drift_y.z)) * 0.5;
    var base = mix(mix(water.deep.xyz, water.deep2.xyz, drift * 0.5 + 0.5), water.shallows.xyz, shallows);
    let facing = dot(slope, water.crest.xy) / water.crest.z * calm;
    base *= 1.0 + facing * water.crest.w;
    let glint = smoothstep(water.glint_range.x, water.glint_range.y, facing) * calm;
    base += glint * water.glint.xyz + drift * water.glint_range.z * water.drift_colour.xyz;
    let fetch = sin(dot(p, water.fetch.xy) + time * water.fetch.z) * 0.5 + 0.5;
    let chop = clamp(length(slope) * water.fetch.w, 0.0, 1.0);
    var surface = pbr_input_from_standard_material(input, is_front);
    surface.material.base_color = vec4<f32>(base, 1.0);
    surface.material.perceptual_roughness = mix(water.roughness.x, water.roughness.y, clamp(fetch * water.roughness.z + chop * water.roughness.w, 0.0, 1.0));
    surface.N = normalize(vec3<f32>(-slope.x * calm, 1.0, slope.y * calm));
    var out: FragmentOutput;
    out.color = main_pass_post_lighting_processing(surface, apply_pbr_lighting(surface));
    return out;
}
