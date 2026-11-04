//! How many pixels the world draws. The camera draws into an image of as many pixels as the Resolution setting
//! chooses, by default as many as the window has up to 3 million, and a second camera stretches that image over the
//! window, with the interface on top. On a large or high-density screen the browser cannot shade every pixel of the
//! world at 60 frames a second; the image it draws instead is a little softer.

use bevy::camera::RenderTarget;
use bevy::camera::visibility::RenderLayers;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureFormat};
use bevy::window::PrimaryWindow;
use hakuba_screens::Screen;
use hakuba_settings::Settings;

pub struct PixelsPlugin;

impl Plugin for PixelsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Riding>()
            .init_resource::<Load>()
            .add_systems(Update, (follow_load, fit).chain().run_if(in_state(Screen::World)));
    }
}

/// Set while the player rides: the ride's camera sees far wider than the walker's, so it may draw fewer pixels.
#[derive(Resource, Default, PartialEq)]
pub struct Riding(pub bool);

/// The shares of the setting's pixels the world may draw, most first: each step is 7% fewer pixels, about 3.5% fewer
/// lines, small enough that temporal anti-aliasing hides the change.
const SHARES: [f32; 12] = [1.0, 0.93, 0.865, 0.805, 0.75, 0.7, 0.65, 0.6, 0.56, 0.52, 0.48, 0.44];
/// The fewest pixels walking draws, about 1200 lines of 1440, and riding, whose view is far wider.
const WALK_LEAST: usize = 5;
const RIDE_LEAST: usize = 11;
/// The GPU time a frame aims under, in milliseconds: the 16.7 ms of a 60 Hz frame, less room for a sudden heavier
/// view while the steps follow.
const TARGET_MS: f32 = 14.5;
/// Steps up only once the frame would stay under this with the next step's pixels.
const ROOM_MS: f32 = 13.5;
/// How long each measurement averages, and how long the GPU must have had room before stepping up.
const WINDOW_S: f32 = 0.25;
const CALM_S: f32 = 1.5;

/// The GPU's load follows what the camera sees, so the drawn pixels follow it, as Unreal's dynamic resolution does:
/// fewer as soon as a quarter second's frames take the GPU over [`TARGET_MS`], more once they have had room for a while.
/// Walking and riding keep separate steps.
#[derive(Resource, Default)]
struct Load {
    steps: [usize; 2],
    /// The GPU's busy milliseconds, frames and seconds of the current measurement.
    busy: f32,
    frames: u32,
    window: f32,
    calm: f32,
}

impl Load {
    fn share(&self, riding: bool) -> f32 {
        // Playtest: HAKUBA_ADAPT=0 always draws the setting's pixels.
        static ADAPT: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
        if !*ADAPT.get_or_init(|| !std::env::var("HAKUBA_ADAPT").is_ok_and(|v| v == "0")) {
            return 1.0;
        }
        SHARES[self.steps[riding as usize]]
    }
}

/// How many milliseconds the GPU was busy since the last call; zero where it is not measured.
fn gpu_busy_ms() -> f32 {
    #[cfg(target_os = "macos")]
    {
        unsafe extern "C" {
            fn hakuba_gpu_busy_ms() -> f64;
        }
        // SAFETY: the vendored Metal backend defines it.
        unsafe { hakuba_gpu_busy_ms() as f32 }
    }
    #[cfg(not(target_os = "macos"))]
    0.0
}

/// Playtest measurement: `HAKUBA_FIXED_PIXELS=1` keeps the setting's pixels, so GPU timings compare like with like.
fn fixed_pixels() -> bool {
    #[cfg(not(target_arch = "wasm32"))]
    return std::env::var("HAKUBA_FIXED_PIXELS").is_ok_and(|v| v == "1");
    #[cfg(target_arch = "wasm32")]
    false
}

fn follow_load(
    time: Res<Time<Real>>,
    riding: Res<Riding>,
    loaded: Option<Res<crate::loading::Loaded>>,
    mut load: ResMut<Load>,
) {
    let busy = gpu_busy_ms();
    // The splash hides loading's stalls, and they say nothing about the views to come.
    if loaded.is_none() || fixed_pixels() {
        return;
    }
    if riding.is_changed() {
        load.calm = 0.0;
    }
    load.busy += busy;
    load.frames += 1;
    load.window += time.delta_secs();
    if load.window < WINDOW_S {
        return;
    }
    let gpu_ms = load.busy / load.frames as f32;
    let window = std::mem::take(&mut load.window);
    load.busy = 0.0;
    load.frames = 0;
    let mode = riding.0 as usize;
    let least = if riding.0 { RIDE_LEAST } else { WALK_LEAST };
    let step = load.steps[mode];
    if gpu_ms > TARGET_MS {
        // As many steps fewer as the frame is over, as if all its time were per pixel, at most two at a time: the
        // next measurement takes another if that was not enough.
        let wanted = SHARES[step] * TARGET_MS / gpu_ms;
        let next = (step..=least).find(|&s| SHARES[s] <= wanted).unwrap_or(least).min(step + 2);
        load.calm = 0.0;
        if next != step {
            load.steps[mode] = next;
            info!("PIXELS fewer: GPU {gpu_ms:.1} ms, now {:.0}% of the setting", 100.0 * SHARES[next]);
        }
        return;
    }
    let roomy = step > 0 && gpu_ms * SHARES[step - 1] / SHARES[step] < ROOM_MS;
    load.calm = if roomy { load.calm + window } else { 0.0 };
    if load.calm >= CALM_S {
        load.calm = 0.0;
        load.steps[mode] = step - 1;
        info!("PIXELS more: GPU {gpu_ms:.1} ms, now {:.0}% of the setting", 100.0 * SHARES[step - 1]);
    }
}

/// The render layer only the window camera sees, holding the world image.
const WINDOW_LAYER: usize = 31;

/// The sprite showing the world image over the window.
#[derive(Component)]
struct WorldImage;

/// The image the world camera draws into.
#[derive(Component)]
pub struct Drawn(Handle<Image>);

/// What the world camera needs to draw into a new image, and the camera and node that show that image in the window.
pub fn spawn(commands: &mut Commands, images: &mut Assets<Image>) -> impl Bundle {
    let image = images.add(Image::new_target_texture(1, 1, TextureFormat::Rgba8UnormSrgb, None));
    commands.spawn((
        Name::new("Window camera"),
        DespawnOnExit(Screen::World),
        Camera2d,
        // The world image is already smoothed and the interface has no edges for multisampling to help: one sample a
        // pixel, not four, over every pixel of the window.
        Msaa::Off,
        IsDefaultUiCamera,
        RenderLayers::layer(WINDOW_LAYER),
    ));
    // A sprite rather than an interface node: the node's shader works out rounded corners and borders at each of the
    // window's pixels, the sprite's only samples the image.
    commands.spawn((
        Name::new("World image"),
        DespawnOnExit(Screen::World),
        Sprite::from_image(image.clone()),
        WorldImage,
        RenderLayers::layer(WINDOW_LAYER),
    ));
    (Camera { order: -1, ..default() }, RenderTarget::Image(image.clone().into()), Drawn(image))
}

/// Keeps the image the window's shape, with the share of the Resolution setting's pixels the load allows.
fn fit(
    window: Single<&Window, With<PrimaryWindow>>,
    drawn: Single<&Drawn>,
    settings: Res<Settings>,
    riding: Res<Riding>,
    load: Res<Load>,
    mut images: ResMut<Assets<Image>>,
    mut sprite: Single<&mut Sprite, With<WorldImage>>,
) {
    if sprite.custom_size != Some(window.size()) {
        sprite.custom_size = Some(window.size());
    }
    let size = settings.resolution.image_size(window.physical_size().as_vec2());
    let size = (size.as_vec2() * load.share(riding.0).sqrt()).round().as_uvec2().max(UVec2::ONE);
    if images.get(&drawn.0).is_some_and(|image| image.size() != size) {
        let mut image = images.get_mut(&drawn.0).expect("the drawn image exists");
        image.resize(Extent3d { width: size.x, height: size.y, depth_or_array_layers: 1 });
    }
}
