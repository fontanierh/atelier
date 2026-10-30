// Source foliage colors encode wind and canopy depth, not an albedo tint.
import bevy_pbr::render::{
    forward_io::{FragmentOutput, VertexOutput},
    mesh_view_bindings::view,
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{alpha_discard, apply_pbr_lighting, main_pass_post_lighting_processing},
    pbr_types,
};

struct FoliageProfile { direction: vec4<f32>, slow: vec4<f32>, fast: vec4<f32>, global_slow: vec4<f32>, global_fast: vec4<f32>, global_tail: vec4<f32>, push_haze: vec4<f32>, haze_colour: vec4<f32> }
@group(constants::MATERIAL_BIND_GROUP) @binding(101) var<uniform> profile: FoliageProfile;

@fragment
fn fragment(input: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var neutral = input;
    @if(VERTEX_COLORS)
    neutral.color = vec4<f32>(1.0);
    var surface = pbr_input_from_standard_material(neutral, is_front);
    if profile.global_tail.w > 0.5 {
        surface.world_normal = vec3<f32>(0.0, 1.0, 0.0);
        surface.N = surface.world_normal;
    }
    let flags = surface.material.flags;
    let masked = (flags & pbr_types::STANDARD_MATERIAL_FLAGS_ALPHA_MODE_RESERVED_BITS)
        == pbr_types::STANDARD_MATERIAL_FLAGS_ALPHA_MODE_MASK;
    var out: FragmentOutput;
    if masked && surface.material.base_color.a < surface.material.alpha_cutoff {
        discard;
    } else {
        surface.material.base_color = alpha_discard(flags, surface.material.alpha_cutoff, surface.material.base_color);
        let depth = max(-(view.view_from_world * input.world_position).z, 0.0);
        let haze = 1.0 - exp(-max(depth - profile.push_haze.z, 0.0) / profile.push_haze.w);
        var shade = 1.0;
        @if(VERTEX_COLORS)
        shade = 1.0 - profile.haze_colour.w * (1.0 - profile.direction.w) * (1.0 - input.color.g);
        surface.material.base_color = vec4<f32>(surface.material.base_color.rgb * (1.0 - haze) * shade, surface.material.base_color.a);
        surface.material.emissive = vec4<f32>(profile.haze_colour.xyz * haze, 1.0);
        out.color = main_pass_post_lighting_processing(surface, apply_pbr_lighting(surface));
    }
    @if(FORWARD_MOTION)
    out.motion_vector = bevy_pbr::render::motion_vectors::calculate(input.world_position, input.previous_world_position);
    return out;
}
