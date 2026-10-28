//! Optional character materials that emit a share of their vertex-tinted colour.

use bevy::asset::{LoadState, embedded_asset};
use bevy::gltf::GltfExtras;
use bevy::material::OpaqueRendererMethod;
use bevy::pbr::{ExtendedMaterial, MaterialExtension};
use bevy::prelude::*;
use bevy::render::render_resource::AsBindGroup;
use bevy::shader::ShaderRef;
use bevy::world_serialization::WorldInstanceReady;
use serde::Deserialize;

use crate::Clips;

#[derive(Asset, AsBindGroup, Reflect, Clone)]
struct VertexEmission {
    #[uniform(100)]
    factor: f32,
}

type Emissive = ExtendedMaterial<StandardMaterial, VertexEmission>;

impl MaterialExtension for VertexEmission {
    fn fragment_shader() -> ShaderRef {
        "embedded://hakuba_characters/emission.wesl".into()
    }
}

pub(super) struct EmissionPlugin;
impl Plugin for EmissionPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "emission.wesl");
        app.add_plugins(MaterialPlugin::<Emissive>::default()).add_observer(read_profile).add_systems(Update, apply);
    }
}

#[derive(Deserialize)]
struct Profile {
    factor: f32,
}

/// This character's materials are ready, including its optional vertex emission profile.
#[derive(Component)]
pub struct MaterialReady;

/// The profiled character could not prepare its material.
#[derive(Component)]
pub struct MaterialFailed;

#[derive(Component)]
struct Pending(f32);

/// A scene-ready event means entities exist, not that their mesh or material assets have finished loading.
fn read_profile(
    ready: On<WorldInstanceReady>,
    characters: Query<(), With<Clips>>,
    children: Query<&Children>,
    names: Query<(&Name, Option<&GltfExtras>)>,
    mut commands: Commands,
) {
    if !characters.contains(ready.entity) {
        return;
    }
    let mut profiles = children.iter_descendants(ready.entity).filter_map(|node| {
        let (name, extras) = names.get(node).ok()?;
        (name.as_str() == "vertex_emission").then_some(extras)
    });
    let Some(extras) = profiles.next() else {
        commands.entity(ready.entity).insert(MaterialReady);
        return;
    };
    let profile = extras.and_then(|extras| serde_json::from_str::<Profile>(&extras.value).ok());
    if profiles.next().is_some()
        || profile.as_ref().is_none_or(|profile| !profile.factor.is_finite() || profile.factor < 0.0)
    {
        error!("invalid character vertex emission profile");
        commands.entity(ready.entity).insert((MaterialFailed, Visibility::Hidden));
        return;
    }
    commands.entity(ready.entity).insert(Pending(profile.unwrap().factor));
}

/// @cc [owner:fontanierh,label:correctness] character-emission-is-asset-owned
/// A character export's vertex-emission factor MUST affect only its own spawned materials, and MUST emit the same
/// tinted base colour drawn by its skinned mesh; models without a profile MUST retain their original materials.
#[allow(clippy::too_many_arguments)]
fn apply(
    pending: Query<(Entity, &Pending)>,
    children: Query<&Children>,
    materials: Query<&MeshMaterial3d<StandardMaterial>>,
    standard: Res<Assets<StandardMaterial>>,
    assets: Res<AssetServer>,
    mut emissive: ResMut<Assets<Emissive>>,
    mut commands: Commands,
) {
    for (root, Pending(factor)) in &pending {
        let targets: Vec<_> = children
            .iter_descendants(root)
            .filter_map(|node| materials.get(node).ok().map(|material| (node, material.0.clone())))
            .collect();
        if targets.is_empty() {
            error!("profiled character has no standard material");
            commands.entity(root).remove::<Pending>().insert((MaterialFailed, Visibility::Hidden));
            continue;
        }
        if targets.iter().any(|(_, handle)| matches!(assets.load_state(handle), LoadState::Failed(_))) {
            error!("profiled character material failed to load");
            commands.entity(root).remove::<Pending>().insert((MaterialFailed, Visibility::Hidden));
            continue;
        }
        if targets.iter().any(|(_, handle)| standard.get(handle).is_none()) {
            continue;
        }
        for (node, handle) in targets {
            let mut base = standard.get(&handle).expect("all materials were checked").clone();
            base.opaque_render_method = OpaqueRendererMethod::Forward;
            let material = emissive.add(Emissive { base, extension: VertexEmission { factor: *factor } });
            commands.entity(node).remove::<MeshMaterial3d<StandardMaterial>>().insert(MeshMaterial3d(material));
        }
        commands.entity(root).remove::<Pending>().insert(MaterialReady);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use bevy::asset::AssetPlugin;
    use bevy::platform::collections::HashMap;
    use bevy::world_serialization::{WorldAsset, WorldInstanceSpawner};

    fn clips() -> Clips {
        Clips { graph: Handle::default(), clips: Vec::new(), speeds: HashMap::default(), hips_m: 1.0, player: None }
    }

    #[test]
    fn profiled_material_waits_for_late_asset_and_leaves_plain_character_untouched() {
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, AssetPlugin::default()))
            .init_resource::<Assets<StandardMaterial>>()
            .init_resource::<Assets<Emissive>>()
            .add_observer(read_profile)
            .add_systems(Update, apply);
        let standard = app.world_mut().resource_mut::<Assets<StandardMaterial>>().reserve_handle();
        let profiled = app.world_mut().spawn(clips()).id();
        let plain = app.world_mut().spawn(clips()).id();
        app.world_mut().spawn((
            Name::new("vertex_emission"),
            GltfExtras { value: r#"{"factor":0.25}"#.into() },
            ChildOf(profiled),
        ));
        let painted = app.world_mut().spawn((MeshMaterial3d(standard.clone()), ChildOf(profiled))).id();
        let untouched = app.world_mut().spawn((MeshMaterial3d(standard.clone()), ChildOf(plain))).id();
        let id = WorldInstanceSpawner::default().spawn(Handle::<WorldAsset>::default());
        app.world_mut().trigger(WorldInstanceReady { entity: profiled, instance_id: id });
        app.world_mut().trigger(WorldInstanceReady { entity: plain, instance_id: id });
        app.world_mut().flush();
        app.update();
        assert!(app.world().get::<Pending>(profiled).is_some());
        assert!(app.world().get::<MaterialReady>(profiled).is_none());
        assert!(app.world().get::<MaterialReady>(plain).is_some());
        app.world_mut()
            .resource_mut::<Assets<StandardMaterial>>()
            .insert(standard.id(), StandardMaterial::default())
            .unwrap();
        app.update();
        let material = app.world().get::<MeshMaterial3d<Emissive>>(painted).unwrap();
        let extension = &app.world().resource::<Assets<Emissive>>().get(&material.0).unwrap().extension;
        assert_eq!(extension.factor, 0.25);
        assert!(app.world().get::<MaterialReady>(profiled).is_some());
        assert!(app.world().get::<MeshMaterial3d<StandardMaterial>>(painted).is_none());
        assert!(app.world().get::<MeshMaterial3d<StandardMaterial>>(untouched).is_some());
        assert!(app.world().get::<MeshMaterial3d<Emissive>>(untouched).is_none());
    }

    #[test]
    fn invalid_profile_hides_character_and_reports_failure() {
        let mut app = App::new();
        app.add_observer(read_profile);
        let character = app.world_mut().spawn(clips()).id();
        app.world_mut().spawn((Name::new("vertex_emission"), GltfExtras { value: "{}".into() }, ChildOf(character)));
        let id = WorldInstanceSpawner::default().spawn(Handle::<WorldAsset>::default());
        app.world_mut().trigger(WorldInstanceReady { entity: character, instance_id: id });
        app.world_mut().flush();
        assert!(app.world().get::<MaterialFailed>(character).is_some());
        assert_eq!(app.world().get::<Visibility>(character), Some(&Visibility::Hidden));
    }
}
