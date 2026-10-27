//! Animated people described by the world's index.

use bevy::asset::LoadState;
use bevy::gltf::Gltf;
use bevy::mesh::VertexAttributeValues;
use bevy::prelude::*;
use bevy::world_serialization::WorldInstanceReady;
use hakuba_characters::{Blend, Clips, MaterialFailed, MaterialReady, Model as CharacterModel, Play, Playing};
use serde::Deserialize;

use crate::{Ground, Unready};

pub struct ActorsPlugin;
impl Plugin for ActorsPlugin {
    fn build(&self, app: &mut App) {
        app.add_observer(ready).add_systems(Update, (prepare, start, move_actors));
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
}

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
    commands.spawn((
        spec,
        Model(model),
        character_model,
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
    actors: Query<(Entity, &Actor, &Model, Option<&Playing>, Option<&Clips>), Without<Started>>,
) {
    for (entity, actor, Model(model), playing, clips) in &actors {
        if assets.load_state(model).is_failed() {
            commands.entity(entity).remove::<Unready>().insert(Started);
        } else if clips.is_some() && playing.is_some_and(|p| !p.clip.is_empty()) {
            if actor.route.is_none() {
                commands.trigger(Play::looping(entity, &actor.clip).at_speed(actor.rate).at_phase(actor.phase_s));
            }
            commands.entity(entity).insert(Started);
        }
    }
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
    actors: Query<(Entity, &Actor, &Model, Has<MaterialReady>, Has<MaterialFailed>), (With<SceneReady>, With<Unready>)>,
    children: Query<&Children>,
    mut handles: Query<&mut Mesh3d>,
    mut meshes: ResMut<Assets<Mesh>>,
    assets: Res<AssetServer>,
    mut commands: Commands,
) {
    for (root, actor, Model(model), material_ready, material_failed) in &actors {
        let nodes: Vec<_> = children.iter_descendants(root).filter(|node| handles.contains(*node)).collect();
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
        if !material_ready
            || nodes.iter().any(|node| handles.get(*node).is_ok_and(|mesh| meshes.get(&mesh.0).is_none()))
        {
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
        let Some(route) = &actor.route else { continue };
        motion.elapsed += time.delta_secs();
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
    fn actor_waits_for_material_and_mesh_before_tinting() {
        use super::{Actor, Model, SceneReady, Unready, prepare};
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
                },
                Model(Handle::default()),
                SceneReady,
                Unready,
            ))
            .id();
        let child = app.world_mut().spawn((Mesh3d(handle.clone()), ChildOf(actor))).id();
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
