// A plant's fragment shader for the main pass (wind.rs uses it): Bevy's standard one, but lighting only what stays. A
// leaf card's see-through texels are discarded, yet in the browser a discarded fragment runs on to the end of the
// shader, so every card in front of what shows would pay the whole lighting and the shadow lookups for nothing.

import bevy_pbr::render::{
    forward_io::{FragmentOutput, VertexOutput, Varyings, vertex_output},
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{alpha_discard, apply_pbr_lighting, main_pass_post_lighting_processing},
    pbr_types,
};

@fragment
fn fragment(varyings: Varyings, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    let in = vertex_output(varyings);
    var out: FragmentOutput;
    var pbr_input = pbr_input_from_standard_material(in, is_front);
    let flags = pbr_input.material.flags;
    let masked = (flags & pbr_types::STANDARD_MATERIAL_FLAGS_ALPHA_MODE_RESERVED_BITS)
        == pbr_types::STANDARD_MATERIAL_FLAGS_ALPHA_MODE_MASK;
    if masked && pbr_input.material.base_color.a < pbr_input.material.alpha_cutoff {
        discard;
    } else {
        pbr_input.material.base_color =
            alpha_discard(flags, pbr_input.material.alpha_cutoff, pbr_input.material.base_color);
        out.color = main_pass_post_lighting_processing(pbr_input, apply_pbr_lighting(pbr_input));
    }
    @if(FORWARD_MOTION && VERTEX_PREVIOUS_POSITION)
    out.motion_vector = bevy_pbr::render::motion_vectors::calculate(in.world_position, in.previous_world_position);
    @if(FORWARD_MOTION && !VERTEX_PREVIOUS_POSITION)
    out.motion_vector = bevy_pbr::render::motion_vectors::calculate(
        in.world_position, bevy_pbr::render::mesh_functions::previous_world_position(in.world_position, in.motion_instance));
    return out;
}
