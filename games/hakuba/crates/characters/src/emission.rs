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
use hakuba_dye_schema::TextureDye as DyeProfile;

#[derive(Asset, AsBindGroup, Reflect, Clone)]
struct VertexEmission {
    #[uniform(100)]
    factor: f32,
}

type Emissive = ExtendedMaterial<StandardMaterial, VertexEmission>;

#[derive(Asset, AsBindGroup, Reflect, Clone)]
struct TextureDye {
    #[uniform(100)]
    tint: Vec4,
    #[uniform(101)]
    mask: Vec4,
    #[uniform(102)]
    luma: Vec4,
    #[uniform(103)]
    parameters: Vec4,
}
type Dyed = ExtendedMaterial<StandardMaterial, TextureDye>;
impl MaterialExtension for TextureDye {
    fn fragment_shader() -> ShaderRef {
        "embedded://hakuba_characters/dye.wesl".into()
    }
}

/// The linear tint selected for a character that declares a texture dye profile.
#[derive(Component)]
pub struct DyeTint(pub Vec3);

/// Its asset-owned dye material replaced the body material.
#[derive(Component)]
pub struct DyeReady;

#[derive(Component)]
struct PendingDye(DyeProfile, Vec3);

impl MaterialExtension for VertexEmission {
    fn fragment_shader() -> ShaderRef {
        "embedded://hakuba_characters/emission.wesl".into()
    }
}

pub(super) struct EmissionPlugin;
impl Plugin for EmissionPlugin {
    fn build(&self, app: &mut App) {
        embedded_asset!(app, "emission.wesl");
        embedded_asset!(app, "dye.wesl");
        app.add_plugins((MaterialPlugin::<Emissive>::default(), MaterialPlugin::<Dyed>::default()))
            .add_observer(read_profile)
            .add_systems(Update, (apply, apply_dye));
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
    characters: Query<Option<&DyeTint>, With<Clips>>,
    children: Query<&Children>,
    names: Query<(&Name, Option<&GltfExtras>)>,
    mut commands: Commands,
) {
    let Ok(tint) = characters.get(ready.entity) else { return };
    let mut dyes = children.iter_descendants(ready.entity).filter_map(|node| {
        let (name, extras) = names.get(node).ok()?;
        (name.as_str() == "texture_dye").then_some(extras)
    });
    if let Some(extras) = dyes.next() {
        let profile = extras.and_then(|extras| serde_json::from_str::<DyeProfile>(&extras.value).ok());
        let tint = tint.map(|t| t.0);
        if dyes.next().is_some() || profile.as_ref().is_none_or(|p| !p.valid()) || tint.is_none_or(|v| !v.is_finite()) {
            error!("invalid character texture dye profile or tint");
            commands.entity(ready.entity).insert((MaterialFailed, Visibility::Hidden));
        } else {
            commands.entity(ready.entity).insert(PendingDye(profile.unwrap(), tint.unwrap()));
        }
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

/// @cc [owner:fontanierh,label:correctness] character-texture-dye-is-mesh-owned
/// An authored dye profile MUST replace only its named mesh material, wait for that material, and leave other meshes unchanged.
#[allow(clippy::too_many_arguments)]
fn apply_dye(
    pending: Query<(Entity, &PendingDye)>,
    children: Query<&Children>,
    names: Query<&Name, Without<Mesh3d>>,
    materials: Query<&MeshMaterial3d<StandardMaterial>>,
    standard: Res<Assets<StandardMaterial>>,
    assets: Res<AssetServer>,
    mut dyed: ResMut<Assets<Dyed>>,
    mut commands: Commands,
) {
    for (root, PendingDye(profile, tint)) in &pending {
        let targets: Vec<_> = children
            .iter_descendants(root)
            .filter(|node| names.get(*node).is_ok_and(|name| name.as_str() == profile.mesh))
            .collect();
        if targets.len() != 1 {
            error!("texture dye needs exactly one named mesh node");
            commands.entity(root).remove::<PendingDye>().insert((MaterialFailed, Visibility::Hidden));
            continue;
        }
        // Bevy places each glTF mesh primitive on a direct child of its authored node.
        let primitives: Vec<_> = children
            .get(targets[0])
            .into_iter()
            .flat_map(|c| c.iter())
            .filter_map(|node| materials.get(node).ok().map(|m| (node, m.0.clone())))
            .collect();
        if primitives.is_empty() {
            error!("texture dye mesh has no standard material primitives");
            commands.entity(root).remove::<PendingDye>().insert((MaterialFailed, Visibility::Hidden));
            continue;
        }
        if primitives.iter().any(|(_, handle)| matches!(assets.load_state(handle), LoadState::Failed(_))) {
            error!("texture dye material failed to load");
            commands.entity(root).remove::<PendingDye>().insert((MaterialFailed, Visibility::Hidden));
            continue;
        }
        if primitives.iter().any(|(_, handle)| standard.get(handle).is_none()) {
            continue;
        }
        for (node, handle) in primitives {
            let mut base = standard.get(&handle).expect("all materials were checked").clone();
            base.opaque_render_method = OpaqueRendererMethod::Forward;
            base.perceptual_roughness = profile.roughness;
            base.reflectance = profile.reflectance;
            base.metallic = 0.0;
            let extension = TextureDye {
                tint: tint.extend(1.0),
                mask: Vec4::from_array(profile.mask),
                luma: Vec3::from_array(profile.luma).extend(profile.green_scale),
                parameters: Vec4::new(profile.reference, profile.exponent, profile.emission, 0.0),
            };
            commands
                .entity(node)
                .remove::<MeshMaterial3d<StandardMaterial>>()
                .insert(MeshMaterial3d(dyed.add(Dyed { base, extension })));
        }
        commands.entity(root).remove::<PendingDye>().insert((DyeReady, MaterialReady));
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
    fn texture_dye_targets_only_named_mesh_after_material_loads() {
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, AssetPlugin::default()))
            .init_resource::<Assets<StandardMaterial>>()
            .init_resource::<Assets<Dyed>>()
            .add_observer(read_profile)
            .add_systems(Update, apply_dye);
        let handle = app.world_mut().resource_mut::<Assets<StandardMaterial>>().reserve_handle();
        let character = app.world_mut().spawn((clips(), DyeTint(Vec3::new(0.14, 0.28, 0.62)))).id();
        let profile = r#"{"mesh":"body","mask":[2.15,0.02,18.0,0.18],"luma":[0.299,0.587,0.114],"green_scale":16.0,"reference":0.11,"exponent":1.35,"emission":0.3,"roughness":0.7,"reflectance":0.38729835}"#;
        app.world_mut().spawn((Name::new("texture_dye"), GltfExtras { value: profile.into() }, ChildOf(character)));
        let body_node = app.world_mut().spawn((Name::new("body"), ChildOf(character))).id();
        let body = app
            .world_mut()
            .spawn((Name::new("body"), Mesh3d(Handle::default()), MeshMaterial3d(handle.clone()), ChildOf(body_node)))
            .id();
        let equipment =
            app.world_mut().spawn((Name::new("hat"), MeshMaterial3d(handle.clone()), ChildOf(character))).id();
        let id = WorldInstanceSpawner::default().spawn(Handle::<WorldAsset>::default());
        app.world_mut().trigger(WorldInstanceReady { entity: character, instance_id: id });
        app.world_mut().flush();
        app.update();
        assert!(app.world().get::<PendingDye>(character).is_some());
        assert!(app.world().get::<MaterialReady>(character).is_none());
        app.world_mut()
            .resource_mut::<Assets<StandardMaterial>>()
            .insert(handle.id(), StandardMaterial::default())
            .unwrap();
        app.update();
        let dyed = app.world().get::<MeshMaterial3d<Dyed>>(body).unwrap();
        let material = app.world().resource::<Assets<Dyed>>().get(&dyed.0).unwrap();
        assert_eq!(material.base.perceptual_roughness, 0.7);
        assert_eq!(material.base.reflectance, 0.38729835);
        let extension = &material.extension;
        assert_eq!(extension.tint, Vec4::new(0.14, 0.28, 0.62, 1.0));
        assert!(app.world().get::<MeshMaterial3d<StandardMaterial>>(equipment).is_some());
        assert!(app.world().get::<DyeReady>(character).is_some());
        assert!(app.world().get::<MaterialReady>(character).is_some());
    }

    #[test]
    fn texture_dye_requires_a_valid_tint_and_profile() {
        let mut app = App::new();
        app.add_observer(read_profile);
        let character = app.world_mut().spawn(clips()).id();
        app.world_mut().spawn((Name::new("texture_dye"), GltfExtras { value: "{}".into() }, ChildOf(character)));
        let id = WorldInstanceSpawner::default().spawn(Handle::<WorldAsset>::default());
        app.world_mut().trigger(WorldInstanceReady { entity: character, instance_id: id });
        app.world_mut().flush();
        assert!(app.world().get::<MaterialFailed>(character).is_some());
        assert_eq!(app.world().get::<Visibility>(character), Some(&Visibility::Hidden));
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
