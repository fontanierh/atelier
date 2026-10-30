// Publish the exact RG16Float motion texel from the main pass to Bevy's existing TAA input.
import bevy_core_pipeline::fullscreen_vertex_shader::FullscreenVertexOutput;
@group(0) @binding(0) var motion: texture_2d<f32>;
@fragment
fn fragment(in: FullscreenVertexOutput) -> @location(0) vec2<f32> {
    return textureLoad(motion, vec2<i32>(in.position.xy), 0).rg;
}
