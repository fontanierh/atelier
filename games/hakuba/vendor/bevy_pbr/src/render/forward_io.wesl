struct UncompressedVertex {
    @builtin(instance_index) instance_index: u32,
    @if(VERTEX_POSITIONS)
    @location(0) position: vec3<f32>,
    @if(VERTEX_NORMALS)
    @location(1) normal: vec3<f32>,
    @if(VERTEX_UVS_A)
    @location(2) uv: vec2<f32>,
    @if(VERTEX_UVS_B)
    @location(3) uv_b: vec2<f32>,
    @if(VERTEX_TANGENTS)
    @location(4) tangent: vec4<f32>,
    @if(VERTEX_COLORS)
    @location(5) color: vec4<f32>,
    @if(SKINNED)
    @location(6) joint_indices: vec4<u32>,
    @if(SKINNED)
    @location(7) joint_weights: vec4<f32>,
    @if(MORPH_TARGETS)
    @builtin(vertex_index) index: u32,
};

struct Vertex {
    @builtin(instance_index) instance_index: u32,
    @if(VERTEX_POSITIONS && VERTEX_POSITIONS_COMPRESSED)
    @location(0) compressed_position: vec4<f32>,
    @if(VERTEX_POSITIONS && !VERTEX_POSITIONS_COMPRESSED)
    @location(0) position: vec3<f32>,
    @if(VERTEX_NORMALS && VERTEX_NORMALS_COMPRESSED)
    @location(1) compressed_normal: vec2<f32>,
    @if(VERTEX_NORMALS && !VERTEX_NORMALS_COMPRESSED)
    @location(1) normal: vec3<f32>,
    @if(VERTEX_UVS_A && VERTEX_UVS_A_COMPRESSED)
    @location(2) compressed_uv: vec2<f32>,
    @if(VERTEX_UVS_A && !VERTEX_UVS_A_COMPRESSED)
    @location(2) uv: vec2<f32>,
    @if(VERTEX_UVS_B && VERTEX_UVS_B_COMPRESSED)
    @location(3) compressed_uv_b: vec2<f32>,
    @if(VERTEX_UVS_B && !VERTEX_UVS_B_COMPRESSED)
    @location(3) uv_b: vec2<f32>,
    @if(VERTEX_TANGENTS && VERTEX_TANGENTS_COMPRESSED)
    @location(4) compressed_tangent: vec2<f32>,
    @if(VERTEX_TANGENTS && !VERTEX_TANGENTS_COMPRESSED)
    @location(4) tangent: vec4<f32>,
    @if(VERTEX_COLORS)
    @location(5) color: vec4<f32>,
    @if(SKINNED)
    @location(6) joint_indices: vec4<u32>,
    @if(SKINNED)
    @location(7) joint_weights: vec4<f32>,
    @if(MORPH_TARGETS)
    @builtin(vertex_index) index: u32,
};

@if(!MESHLET_MESH_MATERIAL_PASS)

/// The instance_index parameter must match vertex_in.instance_index. This is a work around for a wgpu dx12 bug.
/// See https://github.com/gfx-rs/naga/issues/2416
fn decompress_vertex(vertex_in: Vertex, instance_index: u32) -> UncompressedVertex {
    let mesh_metadata = package::render::mesh_functions::get_metadata(instance_index);
    var uncompressed_vertex: UncompressedVertex;
    uncompressed_vertex.instance_index = instance_index;
@if(VERTEX_POSITIONS && VERTEX_POSITIONS_COMPRESSED)
    uncompressed_vertex.position = bevy_render::utils::decompress_vertex_position(vertex_in.compressed_position, mesh_metadata.aabb_center, mesh_metadata.aabb_half_extents);
@if(VERTEX_POSITIONS && !VERTEX_POSITIONS_COMPRESSED)
    uncompressed_vertex.position = vertex_in.position;
@if(VERTEX_NORMALS && VERTEX_NORMALS_COMPRESSED)
    uncompressed_vertex.normal = bevy_render::utils::decompress_vertex_normal(vertex_in.compressed_normal);
@if(VERTEX_NORMALS && !VERTEX_NORMALS_COMPRESSED)
    uncompressed_vertex.normal = vertex_in.normal;
@if(VERTEX_UVS_A && VERTEX_UVS_A_COMPRESSED) {
    let uv_min_and_extents_a = mesh_metadata.uv_channels_min_and_extents[0];
    uncompressed_vertex.uv = bevy_render::utils::decompress_vertex_uv(vertex_in.compressed_uv, uv_min_and_extents_a);
}
@if(VERTEX_UVS_A && !VERTEX_UVS_A_COMPRESSED)
    uncompressed_vertex.uv = vertex_in.uv;
@if(VERTEX_UVS_B && VERTEX_UVS_B_COMPRESSED) {
    let uv_min_and_extents_b = mesh_metadata.uv_channels_min_and_extents[1];
    uncompressed_vertex.uv_b = bevy_render::utils::decompress_vertex_uv(vertex_in.compressed_uv_b, uv_min_and_extents_b);
}
@if(VERTEX_UVS_B && !VERTEX_UVS_B_COMPRESSED)
    uncompressed_vertex.uv_b = vertex_in.uv_b;
@if(VERTEX_TANGENTS && VERTEX_TANGENTS_COMPRESSED)
    uncompressed_vertex.tangent = bevy_render::utils::decompress_vertex_tangent(vertex_in.compressed_tangent);
@if(VERTEX_TANGENTS && !VERTEX_TANGENTS_COMPRESSED)
    uncompressed_vertex.tangent = vertex_in.tangent;
@if(VERTEX_COLORS)
    uncompressed_vertex.color = vertex_in.color;
@if(SKINNED) {
    uncompressed_vertex.joint_indices = vertex_in.joint_indices;
    uncompressed_vertex.joint_weights = vertex_in.joint_weights;
}
@if(MORPH_TARGETS)
    uncompressed_vertex.index = vertex_in.index;
    return uncompressed_vertex;
}

struct VertexOutput {
    /// This is `clip position` when the struct is used as a vertex stage output
    /// and `frag coord` when used as a fragment stage input
    @builtin(position) @invariant position: vec4<f32>,
    @location(0) world_position: vec4<f32>,
    @location(1) world_normal: vec3<f32>,
    @if(FORWARD_MOTION && VERTEX_PREVIOUS_POSITION)
    @location(8) previous_world_position: vec4<f32>,
    // A rigid mesh's instance, with the top bit set when its transform changed since the last frame.
    @if(FORWARD_MOTION && !VERTEX_PREVIOUS_POSITION)
    @location(8) @interpolate(flat) motion_instance: u32,
    @if(VERTEX_UVS_A)
    @location(2) uv: vec2<f32>,
    @if(VERTEX_UVS_B)
    @location(3) uv_b: vec2<f32>,
    @if(VERTEX_TANGENTS)
    @location(4) world_tangent: vec4<f32>,
    @if(VERTEX_COLORS)
    @location(5) color: vec4<f32>,
    @if(VERTEX_OUTPUT_INSTANCE_INDEX)
    @location(6) @interpolate(flat) instance_index: u32,
    @if(VISIBILITY_RANGE_DITHER)
    @location(7) @interpolate(flat) visibility_range_dither: i32,
}

// What the main pass's vertex stage passes on: `VertexOutput` less the world position under WORLD_FROM_DEPTH, which the
// fragment finds again from its own depth. A tiled GPU writes every vertex's outputs to memory and reads them back for
// every fragment, so each one left out is bandwidth saved on every vertex of every leaf card.
struct Varyings {
    @builtin(position) @invariant position: vec4<f32>,
    @if(!WORLD_FROM_DEPTH)
    @location(0) world_position: vec4<f32>,
    @location(1) world_normal: vec3<f32>,
    @if(FORWARD_MOTION && VERTEX_PREVIOUS_POSITION)
    @location(8) previous_world_position: vec4<f32>,
    @if(FORWARD_MOTION && !VERTEX_PREVIOUS_POSITION)
    @location(8) @interpolate(flat) motion_instance: u32,
    @if(VERTEX_UVS_A)
    @location(2) uv: vec2<f32>,
    @if(VERTEX_UVS_B)
    @location(3) uv_b: vec2<f32>,
    @if(VERTEX_TANGENTS)
    @location(4) world_tangent: vec4<f32>,
    @if(VERTEX_COLORS)
    @location(5) color: vec4<f32>,
    @if(VERTEX_OUTPUT_INSTANCE_INDEX)
    @location(6) @interpolate(flat) instance_index: u32,
    @if(VISIBILITY_RANGE_DITHER)
    @location(7) @interpolate(flat) visibility_range_dither: i32,
}

fn varyings(out: VertexOutput) -> Varyings {
    var v: Varyings;
    v.position = out.position;
    @if(!WORLD_FROM_DEPTH)
    v.world_position = out.world_position;
    v.world_normal = out.world_normal;
    @if(FORWARD_MOTION && VERTEX_PREVIOUS_POSITION)
    v.previous_world_position = out.previous_world_position;
    @if(FORWARD_MOTION && !VERTEX_PREVIOUS_POSITION)
    v.motion_instance = out.motion_instance;
    @if(VERTEX_UVS_A)
    v.uv = out.uv;
    @if(VERTEX_UVS_B)
    v.uv_b = out.uv_b;
    @if(VERTEX_TANGENTS)
    v.world_tangent = out.world_tangent;
    @if(VERTEX_COLORS)
    v.color = out.color;
    @if(VERTEX_OUTPUT_INSTANCE_INDEX)
    v.instance_index = out.instance_index;
    @if(VISIBILITY_RANGE_DITHER)
    v.visibility_range_dither = out.visibility_range_dither;
    return v;
}

// The fragment's `VertexOutput`, its world position found from its window position and depth where it was left out.
fn vertex_output(v: Varyings) -> VertexOutput {
    var out: VertexOutput;
    out.position = v.position;
    @if(WORLD_FROM_DEPTH)
    out.world_position = vec4<f32>(package::render::view_transformations::position_ndc_to_world(
        package::render::view_transformations::frag_coord_to_ndc(v.position)), 1.0);
    @if(!WORLD_FROM_DEPTH)
    out.world_position = v.world_position;
    out.world_normal = v.world_normal;
    @if(FORWARD_MOTION && VERTEX_PREVIOUS_POSITION)
    out.previous_world_position = v.previous_world_position;
    @if(FORWARD_MOTION && !VERTEX_PREVIOUS_POSITION)
    out.motion_instance = v.motion_instance;
    @if(VERTEX_UVS_A)
    out.uv = v.uv;
    @if(VERTEX_UVS_B)
    out.uv_b = v.uv_b;
    @if(VERTEX_TANGENTS)
    out.world_tangent = v.world_tangent;
    @if(VERTEX_COLORS)
    out.color = v.color;
    @if(VERTEX_OUTPUT_INSTANCE_INDEX)
    out.instance_index = v.instance_index;
    @if(VISIBILITY_RANGE_DITHER)
    out.visibility_range_dither = v.visibility_range_dither;
    return out;
}

struct FragmentOutput {
    @location(0) color: vec4<f32>,
    @if(FORWARD_MOTION)
    @location(1) motion_vector: vec2<f32>,
}
