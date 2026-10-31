// Asset-owned painted motion, using the colour alpha as a weight in both main and prepass vertices.
@if(PREPASS_PIPELINE)
import bevy_pbr::prepass::io::{Vertex, VertexOutput, decompress_vertex};
@if(PREPASS_PIPELINE)
import bevy_render::globals::Globals;
@if(!PREPASS_PIPELINE)
import bevy_pbr::render::forward_io::{Vertex, VertexOutput, decompress_vertex};
@if(!PREPASS_PIPELINE)
import bevy_pbr::render::mesh_view_bindings::globals;
import bevy_pbr::render::{mesh_functions, view_transformations::position_world_to_clip};

@if(PREPASS_PIPELINE)
@group(0) @binding(1) var<uniform> globals: Globals;

struct MovingPaintUniform {
    lower: vec4<f32>, upper: vec4<f32>, haze: vec4<f32>, colour: vec4<f32>,
    phase: vec4<f32>, amplitude: vec4<f32>, harmonic: vec4<f32>,
}
@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<uniform> paint: MovingPaintUniform;

fn encode(c: vec3<f32>) -> vec3<f32> {
    return select(12.92 * c, 1.055 * pow(c, vec3<f32>(1.0 / 2.4)) - 0.055, c > vec3<f32>(0.0031308));
}

fn motion(at: vec3<f32>, time: f32, weight: f32) -> vec3<f32> {
    if weight == 0.0 { return vec3<f32>(0.0); }
    let phase = paint.phase.z * time + dot(paint.phase.xy, at.xz);
    return paint.amplitude.xyz * vec3<f32>(sin(phase * paint.harmonic.x), sin(phase * paint.harmonic.y), cos(phase * paint.harmonic.z)) * weight * weight;
}

@if(!PREPASS_PIPELINE)
@vertex
fn vertex(input: Vertex) -> VertexOutput {
    let v = decompress_vertex(input, input.instance_index);
    let transform = mesh_functions::get_world_from_local(input.instance_index);
    let still = mesh_functions::mesh_position_local_to_world(transform, vec4<f32>(v.position, 1.0));
    var out: VertexOutput;
    out.world_position = vec4<f32>(still.xyz + motion(still.xyz, globals.time, v.color.a), 1.0);
    out.position = position_world_to_clip(out.world_position.xyz);
    out.position.z *= 1.0001;
    @if(FORWARD_MOTION) {
        let previous = mesh_functions::get_previous_world_from_local(input.instance_index);
        let before = mesh_functions::mesh_position_local_to_world(previous, vec4<f32>(v.position, 1.0));
        out.previous_world_position = vec4<f32>(before.xyz + motion(before.xyz, max(globals.time - globals.delta_time, 0.0), v.color.a), 1.0);
    }
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

@if(PREPASS_PIPELINE)
@vertex
fn vertex(input: Vertex) -> VertexOutput {
    let v = decompress_vertex(input, input.instance_index);
    let transform = mesh_functions::get_world_from_local(input.instance_index);
    let still = mesh_functions::mesh_position_local_to_world(transform, vec4<f32>(v.position, 1.0));
    let moved = motion(still.xyz, globals.time, v.color.a);
    var out: VertexOutput;
    out.world_position = vec4<f32>(still.xyz + moved, 1.0);
    out.position = position_world_to_clip(out.world_position.xyz);
    @if(UNCLIPPED_DEPTH_ORTHO_EMULATION) {
        out.unclipped_depth = out.position.z;
        out.position.z = min(out.position.z, 1.0);
    }
    @if(VERTEX_UVS_A)
    out.uv = v.uv;
    @if(VERTEX_UVS_B)
    out.uv_b = v.uv_b;
    @if(NORMAL_PREPASS_OR_DEFERRED_PREPASS)
    out.world_normal = mesh_functions::mesh_normal_local_to_world(v.normal, input.instance_index);
    @if(NORMAL_PREPASS_OR_DEFERRED_PREPASS && VERTEX_TANGENTS)
    out.world_tangent = mesh_functions::mesh_tangent_local_to_world(transform, v.tangent, input.instance_index);
    @if(VERTEX_COLORS)
    out.color = vec4<f32>(encode(v.color.rgb), 1.0);
    @if(MOTION_VECTOR_PREPASS) {
        let previous = mesh_functions::get_previous_world_from_local(input.instance_index);
        let before = mesh_functions::mesh_position_local_to_world(previous, vec4<f32>(v.position, 1.0));
        out.previous_world_position = vec4<f32>(before.xyz + motion(before.xyz, max(globals.time - globals.delta_time, 0.0), v.color.a), 1.0);
    }
    @if(VERTEX_OUTPUT_INSTANCE_INDEX)
    out.instance_index = input.instance_index;
    @if(VISIBILITY_RANGE_DITHER)
    out.visibility_range_dither = mesh_functions::get_visibility_range_dither_level(input.instance_index, transform[3]);
    return out;
}
