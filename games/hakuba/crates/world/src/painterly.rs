//! The painterly filter: an eight-sector Kuwahara over the finished image. Around each pixel it looks at eight
//! overlapping wedges, averages each, and keeps mostly the averages of the smoothest wedges, so flat areas turn into
//! soft brush strokes while edges stay sharp. It reads 21 pixels within `RADIUS_PX`, and blends the chosen share of
//! the result over the image (the Painterly setting). The kernel is written into the shader as constants, leaving out
//! the wedges a tap has no weight in: two thirds of them.

use bevy::asset::uuid_handle;
use bevy::core_pipeline::Core3dSystems;
use bevy::core_pipeline::fullscreen_material::{FullscreenMaterial, FullscreenMaterialPlugin};
use bevy::core_pipeline::tonemapping::tonemapping;
use bevy::ecs::schedule::ScheduleConfigs;
use bevy::ecs::system::BoxedSystem;
use bevy::prelude::*;
use bevy::render::RenderApp;
use bevy::render::extract_component::ExtractComponent;
use bevy::render::render_resource::ShaderType;
use bevy::shader::{Shader, ShaderRef};

/// How far, in pixels, the farthest pixels it reads are.
const RADIUS_PX: f32 = 2.0;

/// How many pixels it reads: those within √5 grid steps of the centre on a 5 × 5 grid.
const TAPS: usize = 21;

pub struct PainterlyPlugin;

/// The filter's shader, with its kernel written in.
const SHADER: Handle<Shader> = uuid_handle!("5c0e6c43-2f0b-4b5e-9d3a-7a1f4f8f2a61");

impl Plugin for PainterlyPlugin {
    fn build(&self, app: &mut App) {
        app.world_mut().resource_mut::<Assets<Shader>>().insert(&SHADER, Shader::from_wgsl(source(), file!())).ok();
        app.add_plugins(FullscreenMaterialPlugin::<Painterly>::default());
    }
}

/// The filter on a camera.
#[derive(Component, ExtractComponent, Clone, Copy, ShaderType)]
#[extract_app(RenderApp)]
pub struct Painterly {
    /// How much of the filtered image shows over the original, from 0 to 1.
    pub strength: f32,
    radius: f32,
    _padding: Vec2,
}

impl Default for Painterly {
    fn default() -> Self {
        Self { strength: 0.0, radius: RADIUS_PX, _padding: Vec2::ZERO }
    }
}

/// The kernel: each tap's offset in grid steps, and its weight in each of the eight wedges. A tap at `p` (in units of
/// √5 grid steps) weighs, in the wedge turned by `a`, `max(0, x + 0.35 - 3.5 y²)² · exp(-2.5 |p|²)`, where (x, y) is
/// `p` turned by `-a`; each wedge's weights then add up to one.
fn kernel() -> Vec<(IVec2, [f32; 8])> {
    let mut taps = Vec::with_capacity(TAPS);
    for y in -2..=2i32 {
        for x in -2..=2i32 {
            if x * x + y * y > 5 {
                continue;
            }
            let p = Vec2::new(x as f32, y as f32) / 5f32.sqrt();
            let mut weights = [0.0; 8];
            for (k, weight) in weights.iter_mut().enumerate() {
                let turned = Vec2::from_angle(-(k as f32) * std::f32::consts::FRAC_PI_4).rotate(p);
                let w = (turned.x + 0.35 - 3.5 * turned.y * turned.y).max(0.0);
                *weight = w * w * (-2.5 * p.length_squared()).exp();
            }
            taps.push((IVec2::new(x, y), weights));
        }
    }
    for k in 0..8 {
        let total: f32 = taps.iter().map(|(_, weights)| weights[k]).sum();
        taps.iter_mut().for_each(|(_, weights)| weights[k] /= total);
    }
    taps
}

/// Where the shader's source takes the taps.
const TAPS_AT: &str = "    // TAPS\n";

/// The shader's source, with its taps written where it says.
fn source() -> String {
    let source = include_str!("painterly.wgsl");
    assert_eq!(source.matches(TAPS_AT).count(), 1, "painterly.wgsl marks where its taps go once, as `{TAPS_AT}`");
    source.replace(TAPS_AT, &taps())
}

/// The shader's lines that read each tap and add it to the wedges it weighs in.
fn taps() -> String {
    let mut lines = String::new();
    for (offset, weights) in kernel() {
        let (x, y) = (offset.x as f32, offset.y as f32);
        lines += &format!("    c = shown(clamp(uv + vec2({x:?}, {y:?}) * step, vec2(0.0), vec2(1.0)));\n");
        for (k, weight) in weights.iter().enumerate().filter(|(_, weight)| **weight > 0.0) {
            lines += &format!("    means[{k}] += c * {weight:?};\n    squares[{k}] += c * c * {weight:?};\n");
        }
    }
    lines
}

impl FullscreenMaterial for Painterly {
    fn fragment_shader() -> ShaderRef {
        SHADER.into()
    }

    /// After the tone curve, on the colours as they show.
    fn schedule_configs(system: ScheduleConfigs<BoxedSystem>) -> ScheduleConfigs<BoxedSystem> {
        system.in_set(Core3dSystems::PostProcess).after(tonemapping)
    }
}
