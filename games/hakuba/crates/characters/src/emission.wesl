// The default skinned vertex path supplies the tinted base colour; emit its authored share after alpha rejection.
import bevy_pbr::render::{
    forward_io::{FragmentOutput, VertexOutput},
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{alpha_discard, apply_pbr_lighting, main_pass_post_lighting_processing},
    pbr_types,
};

@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<uniform> emission_factor: f32;

@fragment
fn fragment(input: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var surface = pbr_input_from_standard_material(input, is_front);
    let flags = surface.material.flags;
    let masked = (flags & pbr_types::STANDARD_MATERIAL_FLAGS_ALPHA_MODE_RESERVED_BITS)
        == pbr_types::STANDARD_MATERIAL_FLAGS_ALPHA_MODE_MASK;
    var out: FragmentOutput;
    if masked && surface.material.base_color.a < surface.material.alpha_cutoff {
        discard;
    } else {
        surface.material.base_color = alpha_discard(flags, surface.material.alpha_cutoff, surface.material.base_color);
        surface.material.emissive = vec4<f32>(surface.material.base_color.rgb * emission_factor, 1.0);
        out.color = main_pass_post_lighting_processing(surface, apply_pbr_lighting(surface));
    }
    return out;
}
