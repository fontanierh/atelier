//! How many pixels the world draws. The camera draws into an image of as many pixels as the Resolution setting
//! chooses, by default as many as the window has up to 3 million, and a second camera stretches that image over the
//! window, with the interface on top. On a large or high-density screen the browser cannot shade every pixel of the
//! world at 60 frames a second; the image it draws instead is a little softer.
//!
//! The pixels stay as the setting asks. Following the GPU's measured time, as dynamic resolution does, made frames
//! later, not sooner: the Mac's frames are held by what they draw rather than by how many pixels, and each new size
//! is a new image, new textures and anti-aliasing started again.

use bevy::anti_alias::taa::TemporalAntiAliasing;
use bevy::camera::RenderTarget;
use bevy::camera::visibility::RenderLayers;
use bevy::prelude::*;
use bevy::render::render_resource::TextureFormat;
use bevy::window::PrimaryWindow;
use hakuba_screens::Screen;
use hakuba_settings::Settings;

pub struct PixelsPlugin;

impl Plugin for PixelsPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, fit.run_if(in_state(Screen::World)));
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

/// Keeps the image the window's shape, with the Resolution setting's pixels. A new size
/// draws into a new image, shown in the window in place of the old: an image resized in place could stay shown at its
/// old contents while the camera drew into the new, and the world froze on screen under a live interface. Temporal
/// anti-aliasing starts again at each new size: its history at the new size holds whatever an older frame left there,
/// and blended in, it flashes dark over the sky.
fn fit(
    window: Single<&Window, With<PrimaryWindow>>,
    drawn: Single<(&mut Drawn, &mut RenderTarget, Option<&mut TemporalAntiAliasing>)>,
    settings: Res<Settings>,
    mut images: ResMut<Assets<Image>>,
    mut sprite: Single<&mut Sprite, With<WorldImage>>,
) {
    if sprite.custom_size != Some(window.size()) {
        sprite.custom_size = Some(window.size());
    }
    let size = settings.resolution.image_size(window.physical_size().as_vec2());
    let size = size.max(UVec2::ONE);
    let (mut drawn, mut target, taa) = drawn.into_inner();
    if images.get(&drawn.0).is_some_and(|image| image.size() != size) {
        let image = images.add(Image::new_target_texture(size.x, size.y, TextureFormat::Rgba8UnormSrgb, None));
        *target = RenderTarget::Image(image.clone().into());
        sprite.image = image.clone();
        drawn.0 = image;
        if let Some(mut taa) = taa {
            taa.reset = true;
        }
    }
}
