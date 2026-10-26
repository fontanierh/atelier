//! The painterly filter: an eight-sector Kuwahara over the finished image. Around each pixel it looks at eight
//! overlapping wedges, averages each, and keeps mostly the averages of the smoothest wedges, so flat areas turn into
//! soft brush strokes while edges stay sharp. It reads 21 pixels within `RADIUS_PX`, and blends the chosen share of
//! the result over the image (the Painterly setting).

use bevy::asset::embedded_asset;
use bevy::core_pipeline::Core3dSystems;
use bevy::core_pipeline::fullscreen_material::{FullscreenMaterial, FullscreenMaterialPlugin};
use bevy::core_pipeline::tonemapping::tonemapping;
use bevy::ecs::schedule::ScheduleConfigs;
use bevy::ecs::system::BoxedSystem;
use bevy::prelude::*;
use bevy::render::RenderApp;
use bevy::render::extract_component::ExtractComponent;
use bevy::render::render_resource::ShaderType;
use bevy::shader::ShaderRef;

/// How far, in pixels, the farthest pixels it reads are.
const RADIUS_PX: f32 = 2.0;

/// How many pixels it reads: those within √5 grid steps of the centre on a 5 × 5 grid.
const TAPS: usize = 21;

pub struct PainterlyPlugin;

impl Plugin for PainterlyPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "painterly.wgsl");
        app.add_plugins(FullscreenMaterialPlugin::<Painterly>::default());
    }
}

/// The filter on a camera, with its kernel: each tap's offset in grid steps, and its weight in each wedge (wedges
/// 0 to 3 in the first of its two vectors, 4 to 7 in the second).
#[derive(Component, ExtractComponent, Clone, Copy, ShaderType)]
#[extract_app(RenderApp)]
pub struct Painterly {
    /// How much of the filtered image shows over the original, from 0 to 1.
    pub strength: f32,
    radius: f32,
    _padding: Vec2,
    offsets: [Vec4; TAPS],
    weights: [Vec4; 2 * TAPS],
}

impl Default for Painterly {
    /// The kernel. A tap at `p` (in units of √5 grid steps) weighs, in the wedge turned by `a`,
    /// `max(0, x + 0.35 - 3.5 y²)² · exp(-2.5 |p|²)`, where (x, y) is `p` turned by `-a`; each wedge's weights then
    /// add up to one.
    fn default() -> Self {
        let mut offsets = [Vec4::ZERO; TAPS];
        let mut weights = [[0.0; 8]; TAPS];
        let mut n = 0;
        for y in -2..=2i32 {
            for x in -2..=2i32 {
                if x * x + y * y > 5 {
                    continue;
                }
                offsets[n] = Vec4::new(x as f32, y as f32, 0.0, 0.0);
                let p = Vec2::new(x as f32, y as f32) / 5f32.sqrt();
                for (k, weight) in weights[n].iter_mut().enumerate() {
                    let turned = Vec2::from_angle(-(k as f32) * std::f32::consts::FRAC_PI_4).rotate(p);
                    let w = (turned.x + 0.35 - 3.5 * turned.y * turned.y).max(0.0);
                    *weight = w * w * (-2.5 * p.length_squared()).exp();
                }
                n += 1;
            }
        }
        for k in 0..8 {
            let total: f32 = weights.iter().map(|tap| tap[k]).sum();
            weights.iter_mut().for_each(|tap| tap[k] /= total);
        }
        let mut packed = [Vec4::ZERO; 2 * TAPS];
        for (n, tap) in weights.iter().enumerate() {
            packed[2 * n] = Vec4::from_slice(&tap[..4]);
            packed[2 * n + 1] = Vec4::from_slice(&tap[4..]);
        }
        Self { strength: 0.0, radius: RADIUS_PX, _padding: Vec2::ZERO, offsets, weights: packed }
    }
}

impl FullscreenMaterial for Painterly {
    fn fragment_shader() -> ShaderRef {
        "embedded://hakuba_world/painterly.wgsl".into()
    }

    /// After the tone curve, on the colours as they show.
    fn schedule_configs(system: ScheduleConfigs<BoxedSystem>) -> ScheduleConfigs<BoxedSystem> {
        system.in_set(Core3dSystems::PostProcess).after(tonemapping)
    }
}
