// Unjittered motion shared by the prepass and opt-in forward comparison output.
import package::render::mesh_view_bindings::view;
@if(!FORWARD_MOTION)
import package::prepass::bindings::previous_view_uniforms as previous_view;

struct PreviousView {
    view_from_world: mat4x4<f32>,
    clip_from_world: mat4x4<f32>,
    unjittered_clip_from_world: mat4x4<f32>,
    clip_from_view: mat4x4<f32>,
    world_from_clip: mat4x4<f32>,
    view_from_clip: mat4x4<f32>,
}

@if(FORWARD_MOTION)
@group(0) @binding(39) var<uniform> previous_view: PreviousView;
fn calculate(world_position: vec4<f32>, previous_world_position: vec4<f32>) -> vec2<f32> {
    let current_clip = view.unjittered_clip_from_world * world_position;
    let previous_clip = previous_view.unjittered_clip_from_world * previous_world_position;
    return (current_clip.xy / current_clip.w - previous_clip.xy / previous_clip.w) * vec2(0.5, -0.5);
}
