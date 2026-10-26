//! How many pixels the world draws. The camera draws into an image with as many pixels as the window has, up to
//! [`MAX_PIXELS`], and a second camera stretches that image over the window, with the interface on top. On a large or
//! high-density screen the browser cannot shade every pixel of the world at 60 frames a second; the image it draws
//! instead is a little softer.

use bevy::camera::RenderTarget;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureFormat};
use bevy::window::PrimaryWindow;
use hakuba_screens::Screen;

/// The most pixels the world draws: a 2300 × 1300 window's worth, which holds a frame under 14 ms in a 1728 × 913
/// retina window (6.3 million pixels), where drawing every pixel takes 24 ms.
const MAX_PIXELS: f32 = 3.0e6;

pub struct PixelsPlugin;

impl Plugin for PixelsPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, fit.run_if(in_state(Screen::World)));
    }
}

/// The image the world camera draws into.
#[derive(Component)]
pub struct Drawn(Handle<Image>);

/// What the world camera needs to draw into a new image, and the camera and node that show that image in the window.
pub fn spawn(commands: &mut Commands, images: &mut Assets<Image>) -> impl Bundle {
    let image = images.add(Image::new_target_texture(1, 1, TextureFormat::Rgba8UnormSrgb, None));
    commands.spawn((Name::new("Window camera"), DespawnOnExit(Screen::World), Camera2d, IsDefaultUiCamera));
    commands.spawn((
        Name::new("World image"),
        DespawnOnExit(Screen::World),
        ImageNode::new(image.clone()),
        Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
        GlobalZIndex(i32::MIN),
    ));
    (Camera { order: -1, ..default() }, RenderTarget::Image(image.clone().into()), Drawn(image))
}

/// Keeps the image the window's shape, with as many pixels as the window or [`MAX_PIXELS`], whichever is fewer.
fn fit(window: Single<&Window, With<PrimaryWindow>>, drawn: Single<&Drawn>, mut images: ResMut<Assets<Image>>) {
    let window = window.physical_size().as_vec2();
    let scale = (MAX_PIXELS / (window.x * window.y)).sqrt().min(1.0);
    let size = (window * scale).round().as_uvec2().max(UVec2::ONE);
    if images.get(&drawn.0).is_some_and(|image| image.size() != size) {
        let mut image = images.get_mut(&drawn.0).expect("the drawn image exists");
        image.resize(Extent3d { width: size.x, height: size.y, depth_or_array_layers: 1 });
    }
}
