// Previous animation position shared by forward motion and the existing prepass.
import package::render::{mesh_bindings::mesh, mesh_functions, morph, skinning};

@if(MORPH_TARGETS)
fn morph_position(position: vec3<f32>, vertex_index: u32, instance_index: u32) -> vec3<f32> {
    var previous = position;
    let vertex = vertex_index - mesh[instance_index].first_vertex_index;
    let descriptor = mesh[instance_index].morph_descriptor_index;
    let count = morph::layer_count(descriptor);
    for (var i: u32 = 0u; i < count; i ++) {
        let weight = morph::prev_weight_at(i, descriptor);
        if weight == 0.0 { continue; }
        previous += weight * morph::morph_position(vertex, i, descriptor);
    }
    return previous;
}

@if(SKINNED)
fn skin_model(indices: vec4<u32>, weights: vec4<f32>, instance_index: u32) -> mat4x4<f32> {
    @if(HAS_PREVIOUS_SKIN)
    return skinning::skin_prev_model(indices, weights, instance_index);
    @else
    return mesh_functions::get_previous_world_from_local(instance_index);
}
