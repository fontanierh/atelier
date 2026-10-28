// Dye a sampled linear body colour; the profile and tint belong to the character instance.
import bevy_pbr::render::{
    forward_io::{FragmentOutput, VertexOutput},
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{alpha_discard, apply_pbr_lighting, main_pass_post_lighting_processing},
    pbr_types,
};

@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<uniform> tint: vec4<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(101) var<uniform> mask: vec4<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(102) var<uniform> luma: vec4<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(103) var<uniform> parameters: vec4<f32>;

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
        let c = surface.material.base_color.rgb;
        let coat = clamp((c.r - c.g * mask.x - mask.y) * mask.z, 0.0, 1.0)
            * clamp((mask.w - c.g) * luma.w, 0.0, 1.0);
        let dyed = clamp((dot(c, luma.xyz) / parameters.x)
            * pow(clamp(tint.xyz, vec3<f32>(0.0), vec3<f32>(1.0)), vec3<f32>(parameters.y)),
            vec3<f32>(0.0), vec3<f32>(1.0));
        surface.material.base_color = vec4<f32>(mix(c, dyed, coat), surface.material.base_color.a);
        surface.material.emissive = vec4<f32>(surface.material.base_color.rgb * parameters.z, 1.0);
        out.color = main_pass_post_lighting_processing(surface, apply_pbr_lighting(surface));
    }
    return out;
}
