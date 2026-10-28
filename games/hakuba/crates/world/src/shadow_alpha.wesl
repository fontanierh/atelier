// Shadow-only foliage samples the original alpha from a single-channel texture at every mip.
import bevy_pbr::{
    prepass::io::{VertexOutput, FragmentOutput},
    render::{pbr_bindings, pbr_types, mesh_bindings::mesh, mesh_view_bindings::view},
};
import bevy_render::bindless::{bindless_samplers_filtering, bindless_textures_2d};
@if(BINDLESS)
import bevy_pbr::render::pbr_bindings::material_indices;

fn alpha_discard(in: VertexOutput) {
@if(MAY_DISCARD) {
@if(BINDLESS) {
    let slot = mesh[in.instance_index].material_and_lightmap_bind_group_slot & 0xffffu;
    let material = pbr_bindings::material_array[material_indices[slot].material];
}
@else
    let material = pbr_bindings::material;
    var alpha = material.base_color.a;
@if(VERTEX_UVS) {
@if(STANDARD_MATERIAL_BASE_COLOR_UV_B)
    var uv = in.uv_b;
@else
    var uv = in.uv;
    uv = (material.uv_transform * vec3(uv, 1.0)).xy;
    if (material.flags & pbr_types::STANDARD_MATERIAL_FLAGS_BASE_COLOR_TEXTURE_BIT) != 0u {
@if(BINDLESS)
        let texture = bindless_textures_2d[material_indices[slot].base_color_texture];
@else
        let texture = pbr_bindings::base_color_texture;
@if(BINDLESS)
        let sampler_ = bindless_samplers_filtering[material_indices[slot].base_color_sampler];
@else
        let sampler_ = pbr_bindings::base_color_sampler;
        alpha *= textureSampleBias(texture, sampler_, uv, view.mip_bias).r;
    }
}
    if alpha < material.alpha_cutoff { discard; }
}
}

@if(PREPASS_FRAGMENT)
@fragment
fn fragment(in: VertexOutput) -> FragmentOutput {
    alpha_discard(in);
    var out: FragmentOutput;
@if(UNCLIPPED_DEPTH_ORTHO_EMULATION)
    out.frag_depth = in.unclipped_depth;
    return out;
}
@else
@fragment
fn fragment(in: VertexOutput) { alpha_discard(in); }
