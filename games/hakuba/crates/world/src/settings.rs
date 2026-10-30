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
use crate::scenery::Placing;
use crate::wind::{self, ShadowFoliage, SourceFoliage, Swaying};

pub struct SettingsPlugin;

impl Plugin for SettingsPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, (look, blow.after(Placing)).run_if(in_state(Screen::World)));
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

type SwayingPlants =
    Or<(With<MeshMaterial3d<Swaying>>, With<MeshMaterial3d<SourceFoliage>>, With<MeshMaterial3d<ShadowFoliage>>)>;
type AddedSwayingPlants =
    Or<(Added<MeshMaterial3d<Swaying>>, Added<MeshMaterial3d<SourceFoliage>>, Added<MeshMaterial3d<ShadowFoliage>>)>;

/// Tells every swaying plant how strongly the wind blows, through its mesh tag, when the setting changes and as plants
/// spawn.
fn blow(
    mut commands: Commands,
    settings: Res<Settings>,
    all: Query<Entity, SwayingPlants>,
    added: Query<Entity, AddedSwayingPlants>,
) {
    let plants: Vec<_> = if settings.is_changed() { all.iter().collect() } else { added.iter().collect() };
    for plant in plants {
        // A streamed tile may despawn this plant before the deferred wind update is applied.
        commands.entity(plant).try_insert(MeshTag::new(wind::tag(settings.wind)));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wind_update_ignores_a_plant_removed_before_deferred_commands_are_applied() {
        use bevy::ecs::system::IntoSystem;

        let mut world = World::new();
        world.init_resource::<Settings>();
        let plant = world.spawn(MeshMaterial3d::<SourceFoliage>(Handle::default())).id();
        let mut wind_update = IntoSystem::into_system(blow);
        wind_update.initialize(&mut world);
        wind_update.run_without_applying_deferred((), &mut world).unwrap();
        world.despawn(plant);
        wind_update.apply_deferred(&mut world);
        assert!(world.get_entity(plant).is_err());
    }

    #[test]
    fn source_foliage_and_its_shadow_receive_wind_setting_and_updates() {
        let mut app = App::new();
        app.init_resource::<Settings>().add_systems(Update, blow);
        let plant = app.world_mut().spawn(MeshMaterial3d::<SourceFoliage>(Handle::default())).id();
        let shadow = app.world_mut().spawn(MeshMaterial3d::<ShadowFoliage>(Handle::default())).id();
        app.update();
        assert_eq!(app.world().get::<MeshTag>(plant).unwrap().value, wind::tag(Settings::default().wind));
        assert_eq!(app.world().get::<MeshTag>(shadow).unwrap().value, wind::tag(Settings::default().wind));
        app.world_mut().resource_mut::<Settings>().wind = 0.25;
        app.update();
        assert_eq!(app.world().get::<MeshTag>(plant).unwrap().value, wind::tag(0.25));
        assert_eq!(app.world().get::<MeshTag>(shadow).unwrap().value, wind::tag(0.25));
        let added = app.world_mut().spawn(MeshMaterial3d::<ShadowFoliage>(Handle::default())).id();
        app.update();
        assert_eq!(app.world().get::<MeshTag>(added).unwrap().value, wind::tag(0.25));
    }
}
