//! Applies the chosen settings to the world: the painterly filter, the wind, the sun's shadows and how edges are
//! smoothed. The image's size (`pixels.rs`) and the tiles' detail (`tiles.rs`) read the settings themselves.

use bevy::anti_alias::smaa::Smaa;
use bevy::anti_alias::taa::TemporalAntiAliasing;
use bevy::light::{CascadeShadowConfigBuilder, ShadowFilteringMethod};
use bevy::mesh::MeshTag;
use bevy::prelude::*;
use hakuba_screens::Screen;
use hakuba_settings::{AntiAliasing, Settings};

use crate::painterly::Painterly;
use crate::wind::{self, Swap, Swaying};

pub struct SettingsPlugin;

impl Plugin for SettingsPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, (look, blow).run_if(in_state(Screen::World)));
    }
}

/// The world's camera and sun, as the settings want them.
type Camera = (Entity, &'static mut Painterly);

/// Sets the painterly filter's strength, the anti-aliasing and the shadows, when they change and once the camera and
/// sun are spawned.
fn look(
    mut commands: Commands,
    settings: Res<Settings>,
    mut camera: Single<Camera, With<Camera3d>>,
    mut sun: Single<(Entity, &mut DirectionalLight)>,
) {
    let (camera, painterly) = &mut *camera;
    let (sun, light) = &mut *sun;
    if !settings.is_changed() && !painterly.is_added() && !light.is_added() {
        return;
    }
    painterly.strength = settings.painterly;
    let mut camera = commands.entity(*camera);
    match settings.anti_aliasing {
        AntiAliasing::Temporal => camera.remove::<Smaa>().insert(TemporalAntiAliasing::default()),
        AntiAliasing::Smaa => camera.remove::<TemporalAntiAliasing>().insert(Smaa::default()),
        AntiAliasing::Off => camera.remove::<(TemporalAntiAliasing, Smaa)>(),
    };
    // Under temporal anti-aliasing, shadows' edges are sampled a little differently each frame and blended: soft and
    // steady. Without it, that would shimmer, so they are blurred instead.
    camera.insert(match settings.anti_aliasing {
        AntiAliasing::Temporal => ShadowFilteringMethod::Temporal,
        _ => ShadowFilteringMethod::Gaussian,
    });
    light.shadow_maps_enabled = settings.shadows.reach().is_some();
    if let Some((reach, cascades)) = settings.shadows.reach() {
        let first = if cascades == 1 { reach } else { reach / 3.0 };
        commands.entity(*sun).insert(
            CascadeShadowConfigBuilder {
                num_cascades: cascades,
                maximum_distance: reach,
                first_cascade_far_bound: first,
                ..default()
            }
            .build(),
        );
    }
}

/// Tells every swaying plant how strongly the wind blows, and how it swaps with distance, through its mesh tag, when the
/// setting changes and as plants spawn.
fn blow(
    mut commands: Commands,
    settings: Res<Settings>,
    all: Query<(Entity, Option<&Swap>), With<MeshMaterial3d<Swaying>>>,
    added: Query<(Entity, Option<&Swap>), Added<MeshMaterial3d<Swaying>>>,
) {
    let plants: Vec<_> = if settings.is_changed() { all.iter().collect() } else { added.iter().collect() };
    for (plant, swap) in plants {
        commands.entity(plant).insert(MeshTag::new(wind::tag(settings.wind, swap.copied())));
    }
}
