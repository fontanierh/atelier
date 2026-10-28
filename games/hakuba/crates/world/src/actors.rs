//! Animated people described by the world's index.

mod attachment;

use bevy::asset::LoadState;
use bevy::gltf::Gltf;
use bevy::mesh::VertexAttributeValues;
use bevy::prelude::*;
use bevy::world_serialization::WorldInstanceReady;
use hakuba_characters::{
    Blend, Clips, DyeReady, DyeTint, MaterialFailed, MaterialReady, Model as CharacterModel, Play,
};
use serde::Deserialize;

use crate::{Ground, Unready};

pub struct ActorsPlugin;
impl Plugin for ActorsPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(attachment::AttachmentsPlugin)
            .add_observer(ready)
            .add_systems(Update, (prepare, start, move_actors));
    }
}

#[derive(Component, Deserialize)]
pub struct Actor {
    model: String,
    position: [f32; 3],
    yaw_deg: f32,
    scale: f32,
    clip: String,
    rate: f32,
    phase_s: f32,
    colour: [f32; 3],
    cloth: [f32; 4],
    route: Option<Route>,
    #[serde(default)]
    scan: Option<Scan>,
    #[serde(default)]
    practice: Option<Practice>,
    #[serde(default)]
    attachments: Vec<attachment::Spec>,
}

type Practice = hakuba_actor_schema::Practice<f32, String>;
type Scan = hakuba_actor_schema::Scan<f32>;

#[derive(Deserialize)]
struct Route {
    destination: [f32; 3],
    half_cycle_s: f32,
    delay_s: f32,
    travel_s: f32,
}

#[derive(Component)]
struct Model(Handle<Gltf>);
#[derive(Component, Default)]
struct Motion {
    elapsed: f32,
    practicing: bool,
    next_practice: f32,
    practice_until: f32,
}

fn game([x, y, z]: [f32; 3]) -> Vec3 {
    Vec3::new(x, z, -y)
}

pub fn spawn(commands: &mut Commands, assets: &AssetServer, spec: Actor) {
    let model = assets.load(spec.model.clone());
    let transform = Transform::from_translation(game(spec.position))
        .with_rotation(Quat::from_rotation_y(-spec.yaw_deg.to_radians()))
        .with_scale(Vec3::splat(spec.scale));
    let character_model = CharacterModel(spec.model.clone());
    let attachments = attachment::Requests::new(&spec.attachments, assets);
    let dye = DyeTint(Vec3::from_array(spec.colour));
    commands.spawn((
        spec,
        Model(model),
        character_model,
        dye,
        attachments,
        Motion::default(),
        transform,
        Visibility::default(),
        Unready,
        DespawnOnExit(hakuba_screens::Screen::World),
    ));
}

#[derive(Component)]
struct Started;

#[allow(clippy::type_complexity)]
fn start(
    mut commands: Commands,
    assets: Res<AssetServer>,
    actors: Query<(Entity, &Actor, &Model, Option<&Clips>), Without<Started>>,
) {
    for (entity, actor, Model(model), clips) in &actors {
        if assets.load_state(model).is_failed() {
            commands.entity(entity).remove::<Unready>().insert(Started);
        } else if let Some(clips) = clips.filter(|clips| clips.is_ready()) {
            if !ensure_practice_clip(entity, &actor.model, actor.practice.as_ref(), clips.names(), &mut commands) {
                continue;
            }
            if actor.route.is_none() {
                commands.trigger(Play::looping(entity, &actor.clip).at_speed(actor.rate).at_phase(actor.phase_s));
            }
            commands.entity(entity).insert(Started);
        }
    }
}

/// A declared visual action must exist on the loaded model before the actor starts.
fn ensure_practice_clip<'a>(
    entity: Entity,
    model: &str,
    practice: Option<&Practice>,
    mut clips: impl Iterator<Item = &'a str>,
    commands: &mut Commands,
) -> bool {
    if let Some(practice) = practice
        && !clips.any(|clip| clip == practice.clip)
    {
        let reason = format!("{model}: practice clip {:?} is missing", practice.clip);
        error!("{reason}");
        commands.insert_resource(crate::loading::Missing(reason));
        commands.entity(entity).despawn();
        return false;
    }
    true
}

#[derive(Component)]
struct SceneReady;

fn ready(ready: On<WorldInstanceReady>, actors: Query<(), With<Actor>>, mut commands: Commands) {
    if actors.contains(ready.entity) {
        commands.entity(ready.entity).insert(SceneReady);
    }
}

/// The scene exists, but its mesh and material assets can arrive later. Keep the splash until both are ready.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn prepare(
    actors: Query<
        (Entity, &Actor, &Model, Has<MaterialReady>, Has<MaterialFailed>, Has<DyeReady>, Has<attachment::Ready>),
        (With<SceneReady>, With<Unready>),
    >,
    children: Query<&Children>,
    mounted: Query<(), With<attachment::Mounted>>,
    mut handles: Query<&mut Mesh3d>,
    mut meshes: ResMut<Assets<Mesh>>,
    assets: Res<AssetServer>,
    mut commands: Commands,
) {
    for (root, actor, Model(model), material_ready, material_failed, dye_ready, attachments_ready) in &actors {
        let mut nodes = Vec::new();
        let mut pending = vec![root];
        while let Some(parent) = pending.pop() {
            if let Ok(descendants) = children.get(parent) {
                for child in descendants.iter() {
                    if mounted.contains(child) {
                        continue;
                    }
                    if handles.contains(child) {
                        nodes.push(child);
                    }
                    pending.push(child);
                }
            }
        }
        let failed = material_failed
            || nodes.is_empty()
            || nodes.iter().any(|node| {
                handles.get(*node).is_ok_and(|mesh| matches!(assets.load_state(&mesh.0), LoadState::Failed(_)))
            });
        if failed {
            let name = assets.get_path(model.id()).map_or_else(|| actor.model.clone(), |path| path.to_string());
            error!("{name}: resident mesh or material failed to prepare");
            commands.insert_resource(crate::loading::Missing(name));
            commands.entity(root).despawn();
            continue;
        }
        if !attachments_ready
            || !material_ready
            || nodes.iter().any(|node| handles.get(*node).is_ok_and(|mesh| meshes.get(&mesh.0).is_none()))
        {
            continue;
        }
        if dye_ready {
            commands.entity(root).remove::<Unready>();
            continue;
        }
        let mut copies = Vec::new();
        for node in nodes {
            let mesh = handles.get(node).expect("the mesh was just checked");
            let mut copy = meshes.get(&mesh.0).expect("the mesh was just checked").clone();
            let Some(VertexAttributeValues::Float32x4(colours)) = copy.attribute_mut(Mesh::ATTRIBUTE_COLOR) else {
                error!("{}: resident mesh has no RGBA vertex colours", actor.model);
                commands.insert_resource(crate::loading::Missing(actor.model.clone()));
                commands.entity(root).despawn();
                copies.clear();
                break;
            };
            for c in colours {
                if c[1] >= c[0] * actor.cloth[0] && c[1] >= c[2] * actor.cloth[1] {
                    let light = (c[1] / actor.cloth[2]).max(actor.cloth[3]);
                    c[0] = actor.colour[0] * light;
                    c[1] = actor.colour[1] * light;
                    c[2] = actor.colour[2] * light;
                }
            }
            copies.push((node, copy));
        }
        if copies.is_empty() {
            continue;
        }
        for (node, copy) in copies {
            handles.get_mut(node).expect("the mesh was just checked").0 = meshes.add(copy);
        }
        commands.entity(root).remove::<Unready>();
    }
}

#[allow(clippy::type_complexity)]
fn move_actors(
    time: Res<Time>,
    mut ground: Ground,
    mut commands: Commands,
    mut actors: Query<(Entity, &Actor, &mut Motion, &mut Transform, Option<&Clips>), With<Started>>,
) {
    for (entity, actor, mut motion, mut transform, clips) in &mut actors {
        motion.elapsed += time.delta_secs();
        if let Some(scan) = &actor.scan {
            transform.rotation =
                scan_rotation(actor.yaw_deg, scan, motion.elapsed, transform.rotation, time.delta_secs());
        }
        if let Some(practice) = &actor.practice {
            if motion.practicing && motion.elapsed >= motion.practice_until {
                commands.trigger(Play::looping(entity, &actor.clip).at_speed(actor.rate).fading(0.2));
                motion.practicing = false;
            } else if !motion.practicing && motion.elapsed >= practice.delay_s.max(motion.next_practice) {
                commands.trigger(Play::once(entity, &practice.clip).at_speed(practice.rate));
                motion.practicing = true;
                motion.practice_until = motion.elapsed + practice.duration_s;
                motion.next_practice = motion.elapsed + practice_interval(practice.interval_s, fastrand::f32());
            }
        }
        let Some(route) = &actor.route else { continue };
        let (alpha, outward, velocity) = progress(route, motion.elapsed);
        let a = game(actor.position);
        let b = game(route.destination);
        if let Some(clips) = clips {
            let speed = clips.speed(&actor.clip);
            if speed > 0.0 {
                commands.trigger(Blend {
                    entity,
                    first: "idle".into(),
                    second: actor.clip.clone(),
                    amount: a.distance(b) * velocity / speed,
                });
            }
        }
        let mut p = a.lerp(b, alpha);
        if let Some(hit) = ground.below(p, 1.0, 1.6) {
            p.y = hit.point.y + 0.015;
        }
        transform.translation = p;
        let direction = if outward { b - a } else { a - b };
        let target = Quat::from_rotation_y(direction.x.atan2(direction.z));
        transform.rotation = transform.rotation.slerp(target, (2.0 * time.delta_secs()).min(1.0));
    }
}

fn practice_interval(bounds: [f32; 2], sample: f32) -> f32 {
    bounds[0] + (bounds[1] - bounds[0]) * sample
}

/// Turn toward the oscillating home bearing at a bounded angular speed.
fn scan_rotation(home: f32, scan: &Scan, elapsed: f32, current: Quat, dt: f32) -> Quat {
    // The world index bearing has the opposite sign to the source Unreal yaw.
    let bearing = home - scan.amplitude_deg * (elapsed * scan.frequency).sin();
    let target = Quat::from_rotation_y(-bearing.to_radians());
    let angle = current.angle_between(target);
    let fraction = if angle > 0.0 { (scan.max_speed_deg.to_radians() * dt / angle).min(1.0) } else { 1.0 };
    current.slerp(target, fraction)
}

/// Smoothly walks out and back, pausing at each end.
fn progress(route: &Route, elapsed: f32) -> (f32, bool, f32) {
    let t = elapsed % (2.0 * route.half_cycle_s);
    let outward = t < route.half_cycle_s;
    let u = ((t - if outward { 0.0 } else { route.half_cycle_s } - route.delay_s) / route.travel_s).clamp(0.0, 1.0);
    let smooth = u * u * (3.0 - 2.0 * u);
    (if outward { smooth } else { 1.0 - smooth }, outward, 6.0 * u * (1.0 - u) / route.travel_s)
}

#[cfg(test)]
mod tests {
    use super::{Route, progress};

    #[test]
    fn source_actor_metadata_roundtrips_into_runtime_actor() {
        use hakuba_actor_schema::{Attachment, Practice, Scan};
        let attachment = Attachment {
            model: "props/sword/sword.glb",
            position_bone: "hand",
            rotation_bone: "chest",
            offset: [0.123456789_f64, -0.25, 0.5],
            rotation: [0.0, 0.0, 0.0, 1.0],
        };
        let practice =
            Practice { clip: "swing", rate: 1.15_f64, duration_s: 0.7, interval_s: [2.6, 4.2], delay_s: 2.0 };
        let scan = Scan { amplitude_deg: 28.0_f64, frequency: 0.85, max_speed_deg: 90.0 };
        let value = serde_json::json!({
            "model": "characters/example/example.glb", "position": [0.0, 0.0, 0.0],
            "yaw_deg": 0.0, "scale": 1.0, "clip": "idle", "rate": 1.0, "phase_s": 0.0,
            "colour": [1.0, 1.0, 1.0], "cloth": [1.0, 1.0, 1.0, 1.0], "route": null,
            "attachments": [attachment], "practice": practice, "scan": scan
        });
        let actor: super::Actor = serde_json::from_slice(&serde_json::to_vec(&value).unwrap()).unwrap();
        let part = &actor.attachments[0];
        assert_eq!(
            (&*part.model, &*part.position_bone, &*part.rotation_bone),
            ("props/sword/sword.glb", "hand", "chest")
        );
        assert_eq!(part.offset, [0.123456789_f64 as f32, -0.25, 0.5]);
        assert_eq!(part.rotation, [0.0, 0.0, 0.0, 1.0]);
        let practice = actor.practice.unwrap();
        assert_eq!(
            (practice.clip.as_str(), practice.rate, practice.duration_s, practice.interval_s, practice.delay_s),
            ("swing", 1.15, 0.7, [2.6, 4.2], 2.0)
        );
        let scan = actor.scan.unwrap();
        assert_eq!((scan.amplitude_deg, scan.frequency, scan.max_speed_deg), (28.0, 0.85, 90.0));
    }

    #[test]
    fn missing_practice_clip_reports_error_and_despawns_only_invalid_actor() {
        use super::{Practice, ensure_practice_clip};
        use bevy::ecs::system::RunSystemOnce;
        use bevy::prelude::*;
        let mut app = App::new();
        app.add_plugins(MinimalPlugins);
        let missing = app.world_mut().spawn_empty().id();
        let valid = app.world_mut().spawn_empty().id();
        app.world_mut()
            .run_system_once(move |mut commands: Commands| {
                let practice = Practice {
                    clip: "practice".into(),
                    rate: 1.0,
                    duration_s: 1.0,
                    interval_s: [2.0, 3.0],
                    delay_s: 0.0,
                };
                assert!(!ensure_practice_clip(
                    missing,
                    "characters/example/example.glb",
                    Some(&practice),
                    ["idle"].into_iter(),
                    &mut commands
                ));
                assert!(ensure_practice_clip(
                    valid,
                    "characters/example/example.glb",
                    Some(&practice),
                    ["idle", "practice"].into_iter(),
                    &mut commands
                ));
            })
            .unwrap();
        assert!(app.world().get_entity(missing).is_err());
        assert!(app.world().get_entity(valid).is_ok());
        assert!(app.world().resource::<crate::loading::Missing>().0.contains("practice"));
    }

    #[test]
    fn stationary_scan_respects_home_bearing_and_turn_speed() {
        use super::{Scan, scan_rotation};
        use bevy::prelude::*;
        let scan = Scan { amplitude_deg: 28.0, frequency: 0.85, max_speed_deg: 90.0 };
        let home = Quat::from_rotation_y(-10_f32.to_radians());
        let quarter = std::f32::consts::FRAC_PI_2 / scan.frequency;
        let result = scan_rotation(10.0, &scan, quarter, home, 1.0);
        let expected = Quat::from_rotation_y(18_f32.to_radians());
        assert!(result.angle_between(expected) < 1e-4);
        let limited = scan_rotation(10.0, &scan, quarter, home, 0.1);
        assert!((home.angle_between(limited).to_degrees() - 9.0).abs() < 1e-3);
    }

    #[test]
    fn actor_waits_for_material_and_mesh_before_tinting() {
        use super::{Actor, Model, SceneReady, Unready, attachment, prepare};
        use bevy::asset::{AssetPlugin, RenderAssetUsages};
        use bevy::mesh::{PrimitiveTopology, VertexAttributeValues};
        use bevy::prelude::*;
        use hakuba_characters::MaterialReady;

        let mut app = App::new();
        app.add_plugins((MinimalPlugins, AssetPlugin::default()))
            .init_resource::<Assets<Mesh>>()
            .add_systems(Update, prepare);
        let handle = app.world_mut().resource_mut::<Assets<Mesh>>().reserve_handle();
        let actor = app
            .world_mut()
            .spawn((
                Actor {
                    model: "characters/example/example.glb".into(),
                    position: [0.0; 3],
                    yaw_deg: 0.0,
                    scale: 1.0,
                    clip: "idle".into(),
                    rate: 1.0,
                    phase_s: 0.0,
                    colour: [0.2, 0.1, 0.05],
                    cloth: [1.01, 1.25, 0.3, 0.4],
                    route: None,
                    scan: None,
                    practice: None,
                    attachments: Vec::new(),
                },
                Model(Handle::default()),
                SceneReady,
                attachment::Ready,
                Unready,
            ))
            .id();
        let child = app.world_mut().spawn((Mesh3d(handle.clone()), ChildOf(actor))).id();
        let equipment = app
            .world_mut()
            .spawn((
                attachment::Mounted {
                    root: actor,
                    position: child,
                    rotation: child,
                    reference: Quat::IDENTITY,
                    offset: Vec3::ZERO,
                    part_rotation: Quat::IDENTITY,
                },
                ChildOf(actor),
            ))
            .id();
        let equipment_mesh = app.world_mut().resource_mut::<Assets<Mesh>>().reserve_handle();
        let equipment_child = app.world_mut().spawn((Mesh3d(equipment_mesh.clone()), ChildOf(equipment))).id();
        app.update();
        assert!(app.world().get::<Unready>(actor).is_some());
        app.world_mut().entity_mut(actor).insert(MaterialReady);
        app.update();
        assert!(app.world().get::<Unready>(actor).is_some());
        let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default());
        mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, vec![[0.05, 0.3, 0.1, 1.0]]);
        app.world_mut().resource_mut::<Assets<Mesh>>().insert(handle.id(), mesh).unwrap();
        app.update();
        assert!(app.world().get::<Unready>(actor).is_none());
        let new_handle = &app.world().get::<Mesh3d>(child).unwrap().0;
        let mesh = app.world().resource::<Assets<Mesh>>().get(new_handle).unwrap();
        let Some(VertexAttributeValues::Float32x4(colours)) = mesh.attribute(Mesh::ATTRIBUTE_COLOR) else {
            panic!("missing colours")
        };
        assert_eq!(colours[0], [0.2, 0.1, 0.05, 1.0]);
        assert_eq!(app.world().get::<Mesh3d>(equipment_child).unwrap().0, equipment_mesh);
    }

    #[test]
    fn actor_with_texture_dye_preserves_mesh_without_vertex_colours() {
        use super::{Actor, Model, SceneReady, Unready, attachment, prepare};
        use bevy::asset::{AssetPlugin, RenderAssetUsages};
        use bevy::mesh::PrimitiveTopology;
        use bevy::prelude::*;
        use hakuba_characters::{DyeReady, MaterialReady};

        let mut app = App::new();
        app.add_plugins((MinimalPlugins, AssetPlugin::default()))
            .init_resource::<Assets<Mesh>>()
            .add_systems(Update, prepare);
        let mesh = app
            .world_mut()
            .resource_mut::<Assets<Mesh>>()
            .add(Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default()));
        let actor = app
            .world_mut()
            .spawn((
                Actor {
                    model: "characters/example/example.glb".into(),
                    position: [0.0; 3],
                    yaw_deg: 0.0,
                    scale: 1.0,
                    clip: "idle".into(),
                    rate: 1.0,
                    phase_s: 0.0,
                    colour: [0.2, 0.1, 0.05],
                    cloth: [1.01, 1.25, 0.3, 0.4],
                    route: None,
                    scan: None,
                    practice: None,
                    attachments: Vec::new(),
                },
                Model(Handle::default()),
                SceneReady,
                attachment::Ready,
                Unready,
                MaterialReady,
                DyeReady,
            ))
            .id();
        let body = app.world_mut().spawn((Mesh3d(mesh.clone()), ChildOf(actor))).id();
        app.update();
        assert!(app.world().get::<Unready>(actor).is_none());
        assert_eq!(app.world().get::<Mesh3d>(body).unwrap().0, mesh);
    }

    #[test]
    fn stroll_rests_at_each_end_and_returns_after_forty_seconds() {
        let route = Route { destination: [0.0; 3], half_cycle_s: 20.0, delay_s: 5.0, travel_s: 7.0 };
        assert_eq!(progress(&route, 0.0), (0.0, true, 0.0));
        assert_eq!(progress(&route, 5.0), (0.0, true, 0.0));
        assert_eq!(progress(&route, 8.5), (0.5, true, 1.5 / 7.0));
        assert_eq!(progress(&route, 12.0), (1.0, true, 0.0));
        assert_eq!(progress(&route, 25.0), (1.0, false, 0.0));
        assert_eq!(progress(&route, 28.5), (0.5, false, 1.5 / 7.0));
        assert_eq!(progress(&route, 32.0), (0.0, false, 0.0));
        assert_eq!(progress(&route, 40.0), (0.0, true, 0.0));
    }
}
