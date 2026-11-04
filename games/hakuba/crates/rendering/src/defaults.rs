//! The renderer's settings the game always uses, rather than Bevy's defaults.

use bevy::pbr::ShadowCascadeReuse;
use bevy::prelude::*;
use bevy::render::RenderApp;

pub(crate) fn build(app: &mut App) {
    // Each of the two sun shadow cascades redraws every other frame, taking turns, and the frame between samples the
    // map it kept: half the shadow cost, with no lag visible on still scenery (the vendored PBR renderer, vendor/).
    if let Some(render_app) = app.get_sub_app_mut(RenderApp) {
        render_app.insert_resource(ShadowCascadeReuse { periods: vec![2, 2] });
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
