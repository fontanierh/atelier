// The colour attribute is linear in the asset. Encode at the vertices so interpolation follows the source's packed
// colour channel, then decode in the fragment before applying its painted material response.
import bevy_pbr::render::{
    forward_io::{Vertex, VertexOutput, FragmentOutput, decompress_vertex},
    mesh_functions,
    mesh_view_bindings::view,
    view_transformations::position_world_to_clip,
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{apply_pbr_lighting, main_pass_post_lighting_processing},
};

struct PaintUniform { lower: vec4<f32>, upper: vec4<f32>, haze: vec4<f32>, colour: vec4<f32> }
@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<uniform> paint: PaintUniform;

fn encode(c: vec3<f32>) -> vec3<f32> {
    return select(12.92 * c, 1.055 * pow(c, vec3<f32>(1.0 / 2.4)) - 0.055, c > vec3<f32>(0.0031308));
}
fn decode(c: vec3<f32>) -> vec3<f32> {
    return select(c / 12.92, pow((c + 0.055) / 1.055, vec3<f32>(2.4)), c >= vec3<f32>(0.04045));
}

@vertex
fn vertex(input: Vertex) -> VertexOutput {
    let v = decompress_vertex(input, input.instance_index);
    let transform = mesh_functions::get_world_from_local(input.instance_index);
    var out: VertexOutput;
    out.world_position = mesh_functions::mesh_position_local_to_world(transform, vec4<f32>(v.position, 1.0));
    out.position = position_world_to_clip(out.world_position.xyz);
    @if(FORWARD_MOTION)
    out.previous_world_position = mesh_functions::mesh_position_local_to_world(
        mesh_functions::get_previous_world_from_local(input.instance_index), vec4<f32>(v.position, 1.0));
    @if(VERTEX_NORMALS)
    out.world_normal = mesh_functions::mesh_normal_local_to_world(v.normal, input.instance_index);
    @if(VERTEX_UVS_A)
    out.uv = v.uv;
    @if(VERTEX_UVS_B)
    out.uv_b = v.uv_b;
    @if(VERTEX_TANGENTS)
    out.world_tangent = mesh_functions::mesh_tangent_local_to_world(transform, v.tangent, input.instance_index);
    @if(VERTEX_COLORS)
    out.color = vec4<f32>(encode(v.color.rgb), 1.0);
    @if(VERTEX_OUTPUT_INSTANCE_INDEX)
    out.instance_index = input.instance_index;
    @if(VISIBILITY_RANGE_DITHER)
    out.visibility_range_dither = mesh_functions::get_visibility_range_dither_level(input.instance_index, transform[3]);
    return out;
}

@fragment
fn fragment(input: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var decoded = input;
    @if(VERTEX_COLORS)
    decoded.color = vec4<f32>(decode(input.color.rgb), 1.0);
    var surface = pbr_input_from_standard_material(decoded, is_front);
    let color = surface.material.base_color.rgb;
    let within = step(paint.lower.xyz, color) * step(color, paint.upper.xyz);
    let glow = within.x * within.y * within.z;
    let depth = max(-(view.view_from_world * input.world_position).z, 0.0);
    let haze = 1.0 - exp(-max(depth - paint.haze.x, 0.0) / paint.haze.y);
    surface.material.base_color = vec4<f32>(color * (1.0 - haze), 1.0);
    surface.material.emissive = vec4<f32>(color * (paint.lower.w + glow * paint.upper.w) * (1.0 - haze) + paint.colour.xyz * haze, 1.0);
    var out: FragmentOutput;
    out.color = main_pass_post_lighting_processing(surface, apply_pbr_lighting(surface));
    @if(FORWARD_MOTION)
    out.motion_vector = bevy_pbr::render::motion_vectors::calculate(input.world_position, input.previous_world_position);
    return out;
}
