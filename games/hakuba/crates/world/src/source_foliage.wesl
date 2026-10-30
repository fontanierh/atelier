// Source foliage vertex motion for the main and prepass. COLOR_0.r carries its motion weight;
// the asset profile provides wind and push parameters. Opaque parts use the same pipeline with motion disabled.

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

const TAU: f32 = 6.2831853;

// What pushes plants aside, as push.rs writes it: how many there are, then for each where its feet are and its radius,
// then its height.
@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<storage, read> pushers: array<vec4<f32>, 9>;
struct FoliageProfile { direction: vec4<f32>, slow: vec4<f32>, fast: vec4<f32>, global_slow: vec4<f32>, global_fast: vec4<f32>, global_tail: vec4<f32>, push_haze: vec4<f32>, haze_colour: vec4<f32> }
@group(constants::MATERIAL_BIND_GROUP) @binding(101) var<uniform> profile: FoliageProfile;

// How much nearer the main pass draws a vertex than the prepass, as a share of its depth (depth is reversed: nearer is
// larger): about 1 mm at 10 m, far above the rounding the two passes may differ by, far below the gap between leaves.
const DEPTH_MARGIN: f32 = 1.0001;

// Source weights are in COLOR_0.r; spatial coefficients are per metre and material sine uses a one-cycle period.
fn source_motion(at: vec3<f32>, time: f32, weight: f32, strength: f32) -> vec3<f32> {
    if profile.haze_colour.w == 0.0 {
        return vec3<f32>(0.0);
    }
    let x = at.x;
    let y = at.z;
    let z = at.y;
    let gust = profile.fast.w + profile.slow.w * sin(TAU * (profile.slow.x * time + profile.slow.y * x + profile.slow.z * y))
        + profile.fast.z * sin(TAU * (profile.fast.x * time + profile.fast.y * z));
    var push = vec2<f32>(0.0);
    var global_gust = 1.0;
    if u32(pushers[0].x) > 0u {
        let player = pushers[1].xz;
        global_gust = max(profile.global_fast.w, profile.global_slow.w + profile.global_slow.z * sin(profile.global_slow.x * time + player.x * profile.global_slow.y)
            + profile.global_fast.z * sin(profile.global_fast.x * time + player.y * profile.global_fast.y)
            + profile.global_tail.y * sin(profile.global_tail.x * time));
        let away = at.xz - player;
        let d = length(away);
        push = away / max(d, 0.000001) * (profile.push_haze.y * saturate(1.0 - d / profile.push_haze.x));
    }
    return profile.haze_colour.w * profile.global_tail.z * vec3<f32>((profile.direction.z * gust * strength * global_gust * normalize(profile.direction.xy) + push).x, 0.0,
        (profile.direction.z * gust * strength * global_gust * normalize(profile.direction.xy) + push).y) * weight;
}

// How strongly the wind blows on this mesh, its tag in thousandths: 1 is the usual wind.
fn blowing(instance_index: u32) -> f32 {
    return f32(mesh_functions::get_tag(instance_index)) / 1000.0;
}

@if(!PREPASS_PIPELINE)
@vertex
fn vertex(vertex_in: Vertex) -> VertexOutput {
    var out: VertexOutput;
    let vertex = decompress_vertex(vertex_in, vertex_in.instance_index);
    let world_from_local = mesh_functions::get_world_from_local(vertex_in.instance_index);
    let still = mesh_functions::mesh_position_local_to_world(world_from_local, vec4<f32>(vertex.position, 1.0));
    let motion = source_motion(still.xyz, globals.time, vertex.color.r, blowing(vertex_in.instance_index));
    out.world_position = vec4<f32>(still.xyz + motion, 1.0);
    out.position = position_world_to_clip(out.world_position.xyz);
    // A hair nearer than the prepass put it. The two passes are compiled apart, so a moving vertex may land a rounding
    // error further than the depth the prepass wrote, fail the depth test and leave a hole showing the clear colour for
    // a frame: black leaves flickering in the wind.
    out.position.z *= DEPTH_MARGIN;
    out.world_normal = select(mesh_functions::mesh_normal_local_to_world(vertex.normal, vertex_in.instance_index), vec3<f32>(0.0, 1.0, 0.0), profile.global_tail.w > 0.5);
    @if(VERTEX_UVS_A)
    out.uv = vertex.uv;
    @if(VERTEX_UVS_B)
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
    let motion = source_motion(still.xyz, globals.time, vertex.color.r, blowing(vertex_in.instance_index));
    out.world_position = vec4<f32>(still.xyz + motion, 1.0);
    out.position = position_world_to_clip(out.world_position.xyz);
    @if(UNCLIPPED_DEPTH_ORTHO_EMULATION) {
        out.unclipped_depth = out.position.z;
        out.position.z = min(out.position.z, 1.0);
    }
    @if(VERTEX_UVS_A)
    out.uv = vertex.uv;
    @if(VERTEX_UVS_B)
    out.uv_b = vertex.uv_b;
    @if(NORMAL_PREPASS_OR_DEFERRED_PREPASS)
    out.world_normal = select(mesh_functions::mesh_normal_local_to_world(vertex.normal, vertex_in.instance_index), vec3<f32>(0.0, 1.0, 0.0), profile.global_tail.w > 0.5);
    @if(NORMAL_PREPASS_OR_DEFERRED_PREPASS && VERTEX_TANGENTS)
    out.world_tangent =
        mesh_functions::mesh_tangent_local_to_world(world_from_local, vertex.tangent, vertex_in.instance_index);
    @if(VERTEX_COLORS)
    out.color = vertex.color;
    // Where the vertex was last frame, swayed and pushed as it is now: temporal anti-aliasing takes swaying leaves as
    // still. It keeps blending many frames over them, so their cut-out edges stay smooth; following their motion, it
    // would take a tenth of each new frame and their edges would flicker. A leaf's edge may soften a little in strong
    // wind, or as it is pushed aside.
    @if(MOTION_VECTOR_PREPASS) {
        let previous_from_local = mesh_functions::get_previous_world_from_local(vertex_in.instance_index);
        let before = mesh_functions::mesh_position_local_to_world(previous_from_local, vec4<f32>(vertex.position, 1.0));
        out.previous_world_position = vec4<f32>(before.xyz + motion, 1.0);
    }
    @if(VERTEX_OUTPUT_INSTANCE_INDEX)
    out.instance_index = vertex_in.instance_index;
    @if(VISIBILITY_RANGE_DITHER)
    out.visibility_range_dither =
        mesh_functions::get_visibility_range_dither_level(vertex_in.instance_index, world_from_local[3]);
    return out;
}
