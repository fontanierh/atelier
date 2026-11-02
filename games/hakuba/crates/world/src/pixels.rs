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

/// Set while the player rides: the ride's camera sees far wider than the walker's, so it starts with fewer pixels.
#[derive(Resource, Default, PartialEq)]
pub struct Riding(pub bool);

/// The shares of the setting's pixels the world may draw, most first: each step is about 15% fewer pixels.
const SHARES: [f32; 8] = [1.0, 0.85, 0.72, 0.61, 0.52, 0.44, 0.37, 0.31];
/// A ride starts at this step, since its view is far wider than the walker's.
const RIDE_STEP: usize = 4;
/// After a step, frames take this long to show its effect: misses before then do not step again.
const SETTLE_S: f32 = 0.3;
/// Seconds without a missed frame before trying one step more, at first; doubled each time the step above missed.
const CALM_S: f32 = 4.0;
const CALM_MAX_S: f32 = 64.0;
/// A miss this soon after stepping up blames the step.
const BLAME_S: f32 = 2.0;
/// The GPU is short of time when this many frames miss within [`BURST_S`]; a single hitch is not load.
const BURST: usize = 3;
const BURST_S: f32 = 0.5;

/// The GPU's load follows what the camera sees, so the drawn pixels follow it: one step fewer at each frame the
/// display had to show twice, and one more after seconds without one, waiting longer each time the step above failed.
/// Walking and riding keep separate steps.
#[derive(Resource)]
struct Load {
    steps: [usize; 2],
    since: f32,
    calm: f32,
    /// How long to stay calm before each step up, per step.
    wait: [f32; SHARES.len()],
    raised: bool,
    /// When recent frames missed, in seconds since the splash lifted.
    misses: std::collections::VecDeque<f32>,
    clock: f32,
}

impl Default for Load {
    fn default() -> Self {
        Load { steps: [0, RIDE_STEP], since: 0.0, calm: 0.0, wait: [CALM_S; SHARES.len()], raised: false, misses: default(), clock: 0.0 }
    }
}

impl Load {
    fn share(&self, riding: bool) -> f32 {
        SHARES[self.steps[riding as usize]]
    }
}

/// How many frames stayed on screen longer than one 60 Hz frame since the last call; zero where it is not measured.
fn missed_frames() -> u32 {
    #[cfg(target_os = "macos")]
    {
        unsafe extern "C" {
            fn hakuba_present_missed() -> u32;
        }
        // SAFETY: the vendored Metal backend defines it.
        unsafe { hakuba_present_missed() }
    }
    #[cfg(not(target_os = "macos"))]
    0
}

fn follow_load(
    time: Res<Time<Real>>,
    riding: Res<Riding>,
    loaded: Option<Res<crate::loading::Loaded>>,
    mut load: ResMut<Load>,
) {
    let fresh = missed_frames();
    // The splash hides loading's stalls, and they say nothing about the views to come.
    if loaded.is_none() {
        return;
    }
    let dt = time.delta_secs();
    load.since += dt;
    load.clock += dt;
    let clock = load.clock;
    for _ in 0..fresh {
        load.misses.push_back(clock);
    }
    while load.misses.front().is_some_and(|&t| clock - t > BURST_S) {
        load.misses.pop_front();
    }
    let short = load.misses.len() >= BURST;
    let mode = riding.0 as usize;
    if riding.is_changed() {
        load.since = 0.0;
        load.calm = 0.0;
        load.raised = false;
    }
    if fresh > 0 {
        load.calm = 0.0;
    }
    if short {
        if load.since >= SETTLE_S && load.steps[mode] + 1 < SHARES.len() {
            let step = load.steps[mode];
            if load.raised && load.since < BLAME_S {
                load.wait[step] = (load.wait[step] * 2.0).min(CALM_MAX_S);
            }
            load.steps[mode] += 1;
            load.since = 0.0;
            load.raised = false;
            info!("PIXELS fewer: now {:.0}% of the setting", 100.0 * SHARES[load.steps[mode]]);
        }
        return;
    }
    if fresh > 0 {
        return;
    }
    load.calm += dt;
    let step = load.steps[mode];
    if step > 0 && load.calm >= load.wait[step - 1] {
        load.steps[mode] -= 1;
        load.since = 0.0;
        load.calm = 0.0;
        load.raised = true;
        info!("PIXELS more: now {:.0}% of the setting", 100.0 * SHARES[load.steps[mode]]);
    }
}

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
        IsDefaultUiCamera,
        RenderLayers::none(),
    ));
    commands.spawn((
        Name::new("World image"),
        DespawnOnExit(Screen::World),
        ImageNode::new(image.clone()),
        Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
        GlobalZIndex(i32::MIN),
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
) {
    let size = settings.resolution.image_size(window.physical_size().as_vec2());
    let size = (size.as_vec2() * load.share(riding.0).sqrt()).round().as_uvec2().max(UVec2::ONE);
    if images.get(&drawn.0).is_some_and(|image| image.size() != size) {
        let mut image = images.get_mut(&drawn.0).expect("the drawn image exists");
        image.resize(Extent3d { width: size.x, height: size.y, depth_or_array_layers: 1 });
    }
}
