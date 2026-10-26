// The wind (wind.rs says what it does): Bevy's mesh vertex shaders for the main pass and the prepass, each moving a
// vertex in the wind by how far it bends and its leaf's phase, its second texture coordinates, scaled by how strongly
// the wind blows, its mesh's tag in thousandths, and leaning leaves and blades away from what pushes plants aside
// (push.rs). Plants have no morph targets or skins, so those are left out.

@if(PREPASS_PIPELINE)
import bevy_pbr::prepass::io::{Vertex, VertexOutput, decompress_vertex};
@if(PREPASS_PIPELINE)
import bevy_render::globals::Globals;
@if(!PREPASS_PIPELINE)
import bevy_pbr::render::forward_io::{Vertex, VertexOutput, decompress_vertex};
@if(!PREPASS_PIPELINE)
import bevy_pbr::render::mesh_view_bindings::globals;
import bevy_pbr::render::{mesh_functions, mesh_view_bindings::view, view_transformations::position_world_to_clip};

// The prepass binds the time at another place than the main pass.
@if(PREPASS_PIPELINE)
@group(0) @binding(1) var<uniform> globals: Globals;

// The way the wind blows, across the ground (x and z).
const WIND: vec2<f32> = vec2<f32>(0.3, -0.95);

const TAU: f32 = 6.2831853;

// What pushes plants aside, as push.rs writes it: how many there are, then for each where its feet are and its radius,
// then its height.
@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<storage, read> pushers: array<vec4<f32>, 9>;

// Where a plant swaps versions, as wind.rs sets it: from x metres from the camera, over y more.
@group(constants::MATERIAL_BIND_GROUP) @binding(101) var<uniform> swap: vec4<f32>;

// A mesh tag's bits, as wind.rs writes them: how strongly the wind blows, and whether the mesh is a plant's full
// version going with distance or its middle one coming.
const STRENGTH: u32 = 0x3fffffffu;
const GOING: u32 = 0x40000000u;
const COMING: u32 = 0x80000000u;

// Where a vertex goes so as not to be drawn: outside the view, where a card whose corners all go is never drawn.
const NOWHERE: vec4<f32> = vec4<f32>(2.0, 2.0, 2.0, 1.0);

// How much nearer the main pass draws a vertex than the prepass, as a share of its depth (depth is reversed: nearer is
// larger): about 1 mm at 10 m, far above the rounding the two passes may differ by, far below the gap between leaves.
const DEPTH_MARGIN: f32 = 1.0001;

// How far a leaf or blade right beside a pusher leans away, across the ground, for each metre it stands above the
// pusher's feet: about 24 degrees.
const LEAN: f32 = 0.45;

// How far above a pusher's height plants stop leaning, in metres.
const FADE_ABOVE_M: f32 = 0.5;

// How strongly the wind blows at `at` at `time`: about 1, rising and falling over several seconds in gusts that roll
// across the world, so plants a few tens of metres apart are pushed at different times. Never below 0.1: the wind
// pushes plants downwind and lets them spring back, rather than swinging them evenly both ways.
fn gust(at: vec3<f32>, time: f32) -> f32 {
    let slow = 0.45 * sin(0.31 * time + 0.031 * at.x + 0.017 * at.z);
    let middle = 0.3 * sin(0.73 * time - 0.05 * at.z + 1.3);
    let quick = 0.2 * sin(1.37 * time + 0.043 * at.x + 2.1);
    return max(0.1, 1.0 + slow + middle + quick);
}

// How far a vertex at `at` moves at `time`, for one that bends `bend` metres in a usual gust and belongs to a leaf or
// blade of phase `phase` (wood, below 0, does not flutter). Three motions add up, as in a real tree: the whole plant
// leans downwind as the gusts come and go; its branches sway around that, each part at its own point in the swing,
// along and across the wind; and each leaf flutters quickly on its own. All grow with the bend, so a plant's foot
// and the inside of its crown stay nearly still.
fn sway(at: vec3<f32>, time: f32, bend: f32, phase: f32) -> vec3<f32> {
    let strength = gust(at, time);
    let along = vec3<f32>(WIND.x, 0.0, WIND.y) / length(WIND);
    let across = vec3<f32>(-along.z, 0.0, along.x);
    let lean = along * strength;
    let branches = 0.3 * strength * (along * sin(2.1 * time + dot(at, vec3<f32>(0.8, 0.7, 0.5)))
        + across * 0.7 * sin(1.6 * time + dot(at, vec3<f32>(-0.4, 0.6, 0.9)) + 1.0));
    let angle = TAU * phase;
    let flutter = 0.12 * strength * step(0.0, phase) * vec3<f32>(
        sin(13.0 * time + 3.0 * angle),
        0.6 * sin(17.0 * time + 5.0 * angle),
        sin(11.0 * time + 7.0 * angle),
    );
    return (lean + branches + flutter) * bend;
}

// How far a vertex at `at`, of a leaf or blade of phase `phase`, moves to lean away from the pushers: as if bent over
// at the pusher's feet, so the higher it stands the further it goes, and it drops a little, keeping its length. A
// plant leans most at a pusher's middle and not at all from its radius out, nor above its height; wood, of phase
// below 0, stands still.
fn push(at: vec3<f32>, phase: f32) -> vec3<f32> {
    var moved = vec3<f32>(0.0);
    if phase < 0.0 {
        return moved;
    }
    let count = u32(pushers[0].x);
    for (var i = 0u; i < count; i++) {
        let feet = pushers[1u + 2u * i];
        let height = pushers[2u + 2u * i].x;
        let away = at.xz - feet.xz;
        let far = length(away);
        let up = at.y - feet.y;
        let lean = LEAN * saturate(1.0 - far / feet.w) * saturate((height + FADE_ABOVE_M - up) / FADE_ABOVE_M);
        let high = max(up, 0.0);
        moved += vec3<f32>(away.x, 0.0, away.y) * (lean * high / max(far, 0.001))
            - vec3<f32>(0.0, 0.5 * lean * lean * high, 0.0);
    }
    return moved;
}

// How strongly the wind blows on this mesh, its tag in thousandths: 1 is the usual wind.
fn blowing(instance_index: u32) -> f32 {
    return f32(mesh_functions::get_tag(instance_index) & STRENGTH) / 1000.0;
}

// Whether a card or blade of phase `phase`, of a mesh standing at `origin`, shows. A plant's full version gives way to
// its middle one between swap's distances from the camera that picks detail: a whole card or blade at a time, each at
// its own distance, set by its phase, so every frame shows whole cards and nothing shimmers under temporal
// anti-aliasing. Wood, of phase below 0, swaps halfway. Shadows come from the middle version alone.
fn shows(instance_index: u32, origin: vec3<f32>, phase: f32) -> bool {
    let tag = mesh_functions::get_tag(instance_index);
    if (tag & (GOING | COMING)) == 0u {
        return true;
    }
    // The sun's shadow views are the only orthographic ones: they always draw the middle version, wherever the camera
    // is, so a plant's shadows hold still as the camera moves, the sun's light falling on it as it would.
    if view.clip_from_view[3][3] == 1.0 {
        return (tag & COMING) != 0u;
    }
    let along = saturate((distance(origin, view.lod_view_world_position) - swap.x) / swap.y);
    let at = select(phase, 0.5, phase < 0.0);
    return select(along > at, along <= at, (tag & GOING) != 0u);
}

@if(!PREPASS_PIPELINE)
@vertex
fn vertex(vertex_in: Vertex) -> VertexOutput {
    var out: VertexOutput;
    let vertex = decompress_vertex(vertex_in, vertex_in.instance_index);
    let world_from_local = mesh_functions::get_world_from_local(vertex_in.instance_index);
    let still = mesh_functions::mesh_position_local_to_world(world_from_local, vec4<f32>(vertex.position, 1.0));
    let bend = vertex.uv_b.x * blowing(vertex_in.instance_index);
    let pushed = push(still.xyz, vertex.uv_b.y);
    out.world_position = vec4<f32>(still.xyz + pushed + sway(still.xyz, globals.time, bend, vertex.uv_b.y), 1.0);
    out.position = position_world_to_clip(out.world_position.xyz);
    // A hair nearer than the prepass put it. The two passes are compiled apart, so a moving vertex may land a rounding
    // error further than the depth the prepass wrote, fail the depth test and leave a hole showing the clear colour for
    // a frame: black leaves flickering in the wind.
    out.position.z *= DEPTH_MARGIN;
    if !shows(vertex_in.instance_index, world_from_local[3].xyz, vertex.uv_b.y) {
        out.position = NOWHERE;
    }
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
    let bend = vertex.uv_b.x * blowing(vertex_in.instance_index);
    let pushed = push(still.xyz, vertex.uv_b.y);
    out.world_position = vec4<f32>(still.xyz + pushed + sway(still.xyz, globals.time, bend, vertex.uv_b.y), 1.0);
    out.position = position_world_to_clip(out.world_position.xyz);
    if !shows(vertex_in.instance_index, world_from_local[3].xyz, vertex.uv_b.y) {
        out.position = NOWHERE;
    }
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
    // Where the vertex was last frame, swayed and pushed as it is now: temporal anti-aliasing takes swaying leaves as
    // still. It keeps blending many frames over them, so their cut-out edges stay smooth; following their motion, it
    // would take a tenth of each new frame and their edges would flicker. A leaf's edge may soften a little in strong
    // wind, or as it is pushed aside.
    @if(MOTION_VECTOR_PREPASS) {
        let previous_from_local = mesh_functions::get_previous_world_from_local(vertex_in.instance_index);
        let before = mesh_functions::mesh_position_local_to_world(previous_from_local, vec4<f32>(vertex.position, 1.0));
        let swayed = sway(still.xyz, globals.time, bend, vertex.uv_b.y);
        out.previous_world_position = vec4<f32>(before.xyz + pushed + swayed, 1.0);
    }
    @if(VERTEX_OUTPUT_INSTANCE_INDEX)
    out.instance_index = vertex_in.instance_index;
    @if(VISIBILITY_RANGE_DITHER)
    out.visibility_range_dither =
        mesh_functions::get_visibility_range_dither_level(vertex_in.instance_index, world_from_local[3]);
    return out;
}
