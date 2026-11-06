//! The renderer's settings the game always uses, rather than Bevy's defaults.

use bevy::pbr::ShadowCascadeReuse;
use bevy::prelude::*;
use bevy::render::RenderApp;
use bevy::render::mesh::allocator::MeshAllocatorSettings;

/// The largest a mesh slab grows, so growing one copies at most this much in a frame.
const MAX_SLAB_BYTES: u64 = 64 * 1024 * 1024;

pub(crate) fn build(app: &mut App) {
    // The far sun shadow cascade redraws every other frame and the frame between samples the map it kept (the vendored
    // PBR renderer, vendor/). The near one redraws every frame: it holds the player's shadow, which lags its body
    // visibly when kept.
    if let Some(render_app) = app.get_sub_app_mut(RenderApp) {
        render_app.insert_resource(ShadowCascadeReuse { periods: vec![1, 2] });
        // A mesh slab grows by half again into a new buffer and copies the old one across. Bevy lets one grow to
        // 512 MiB, and in flight the step from 300 to 450 MB held a frame for 61 ms; past 64 MiB a new slab starts.
        let world = render_app.world_mut();
        if !world.contains_resource::<MeshAllocatorSettings>() {
            world.insert_resource(MeshAllocatorSettings::default());
        }
        world.resource_mut::<MeshAllocatorSettings>().max_slab_size = MAX_SLAB_BYTES;
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        // The near shadows cover 40 m in one cascade: 1024 texels is ~4 cm each, and a quarter of the leaf cutouts.
        app.insert_resource(bevy::light::DirectionalLightShadowMap { size: 2048 });
        app.add_systems(Startup, no_gpu_clustering);
    }
}

/// The few lights here are clustered on the CPU: GPU clustering adds compute passes and a readback every frame on
/// Apple GPUs.
#[cfg(not(target_arch = "wasm32"))]
fn no_gpu_clustering(settings: Option<ResMut<bevy::light::cluster::GlobalClusterSettings>>) {
    if let Some(mut settings) = settings {
        settings.gpu_clustering = None;
    }
}
