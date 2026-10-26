// The wind (wind.rs says what it does): Bevy's mesh vertex shaders for the main pass and the prepass, each moving a
// vertex along the wind by how far it sways, the first of its second texture coordinates. Plants have no morph
// targets or skins, so those are left out.

@if(PREPASS_PIPELINE)
import bevy_pbr::prepass::io::{Vertex, VertexOutput, decompress_vertex};
@if(PREPASS_PIPELINE)
import bevy_render::globals::Globals;
@if(!PREPASS_PIPELINE)
import bevy_pbr::render::forward_io::{Vertex, VertexOutput, decompress_vertex};
@if(!PREPASS_PIPELINE)
import bevy_pbr::render::mesh_view_bindings::globals;
import bevy_pbr::render::{mesh_functions, view_transformations::position_world_to_clip};

// The prepass binds the time at another place than the main pass.
@if(PREPASS_PIPELINE)
@group(0) @binding(1) var<uniform> globals: Globals;

// The way the wind blows, across the ground (x and z).
const WIND: vec2<f32> = vec2<f32>(0.3, -0.95);

// How far a vertex that sways `metres` at a full gust moves at `time`, at `at`: two slow waves rolling across the
// world, as in Yorimichi, so neighbouring plants lean together and far ones out of step.
fn sway(at: vec3<f32>, time: f32, metres: f32) -> vec3<f32> {
    let gust = 0.6 * sin(0.28 * time + 0.11 * at.x + 0.16 * at.z) + 0.3 * sin(0.7 * time + 0.2 * at.y) + 0.5;
    let along = normalize(WIND) * gust / 1.4 * metres;
    return vec3<f32>(along.x, 0.0, along.y);
}

@if(!PREPASS_PIPELINE)
@vertex
fn vertex(vertex_in: Vertex) -> VertexOutput {
    var out: VertexOutput;
    let vertex = decompress_vertex(vertex_in, vertex_in.instance_index);
    let world_from_local = mesh_functions::get_world_from_local(vertex_in.instance_index);
    let still = mesh_functions::mesh_position_local_to_world(world_from_local, vec4<f32>(vertex.position, 1.0));
    out.world_position = vec4<f32>(still.xyz + sway(still.xyz, globals.time, vertex.uv_b.x), 1.0);
    out.position = position_world_to_clip(out.world_position.xyz);
    out.world_normal = mesh_functions::mesh_normal_local_to_world(vertex.normal, vertex_in.instance_index);
    @if(VERTEX_UVS_A)
    out.uv = vertex.uv;
    out.uv_b = vertex.uv_b;
    @if(VERTEX_TANGENTS)
    out.world_tangent =
        mesh_functions::mesh_tangent_local_to_world(world_from_local, vertex.tangent, vertex_in.instance_index);
    @if(VERTEX_COLORS)
    out.color = vertex.color;
    @if(VERTEX_OUTPUT_INSTANCE_INDEX)
    out.instance_index = vertex_in.instance_index;
    @if(VISIBILITY_RANGE_DITHER)
    out.visibility_range_dither =
        mesh_functions::get_visibility_range_dither_level(vertex_in.instance_index, world_from_local[3]);
    return out;
}

@if(PREPASS_PIPELINE)
@vertex
fn vertex(vertex_in: Vertex) -> VertexOutput {
    var out: VertexOutput;
    let vertex = decompress_vertex(vertex_in, vertex_in.instance_index);
    let world_from_local = mesh_functions::get_world_from_local(vertex_in.instance_index);
    let still = mesh_functions::mesh_position_local_to_world(world_from_local, vec4<f32>(vertex.position, 1.0));
    out.world_position = vec4<f32>(still.xyz + sway(still.xyz, globals.time, vertex.uv_b.x), 1.0);
    out.position = position_world_to_clip(out.world_position.xyz);
    @if(UNCLIPPED_DEPTH_ORTHO_EMULATION) {
        out.unclipped_depth = out.position.z;
        out.position.z = min(out.position.z, 1.0);
    }
    @if(VERTEX_UVS_A)
    out.uv = vertex.uv;
    out.uv_b = vertex.uv_b;
    @if(NORMAL_PREPASS_OR_DEFERRED_PREPASS)
    out.world_normal = mesh_functions::mesh_normal_local_to_world(vertex.normal, vertex_in.instance_index);
    @if(NORMAL_PREPASS_OR_DEFERRED_PREPASS && VERTEX_TANGENTS)
    out.world_tangent =
        mesh_functions::mesh_tangent_local_to_world(world_from_local, vertex.tangent, vertex_in.instance_index);
    @if(VERTEX_COLORS)
    out.color = vertex.color;
    // Where the vertex was last frame, swayed as it was then, so temporal anti-aliasing follows the leaves.
    @if(MOTION_VECTOR_PREPASS) {
        let previous_from_local = mesh_functions::get_previous_world_from_local(vertex_in.instance_index);
        let before = mesh_functions::mesh_position_local_to_world(previous_from_local, vec4<f32>(vertex.position, 1.0));
        let then = globals.time - globals.delta_time;
        out.previous_world_position = vec4<f32>(before.xyz + sway(before.xyz, then, vertex.uv_b.x), 1.0);
    }
    @if(VERTEX_OUTPUT_INSTANCE_INDEX)
    out.instance_index = vertex_in.instance_index;
    @if(VISIBILITY_RANGE_DITHER)
    out.visibility_range_dither =
        mesh_functions::get_visibility_range_dither_level(vertex_in.instance_index, world_from_local[3]);
    return out;
}
