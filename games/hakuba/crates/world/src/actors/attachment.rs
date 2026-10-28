//! Rigid painted attachments follow their character's current pose.

use bevy::app::AnimationSystems;
use bevy::asset::LoadState;
use bevy::camera::visibility::NoFrustumCulling;
use bevy::gltf::{Gltf, GltfMesh, GltfNode};
use bevy::prelude::*;
use hakuba_characters::AttachmentPose;

use super::{Model, SceneReady};
use crate::scenery::{PaintedPart, painted_part, standard_of};
use crate::vertex_paint::{MotionProfile, MovingPaintedMaterials, PaintedMaterials, Profile};

pub(super) type Spec = hakuba_actor_schema::Attachment<f32, String>;

#[derive(Component)]
pub(super) struct Requests(Vec<(Spec, Handle<Gltf>)>);
impl Requests {
    pub(super) fn new(specs: &[Spec], assets: &AssetServer) -> Self {
        Self(
            specs
                .iter()
                .cloned()
                .map(|s| {
                    let handle = assets.load(s.model.clone());
                    (s, handle)
                })
                .collect(),
        )
    }
}

#[derive(Component)]
pub(super) struct Ready;

#[derive(Component)]
pub(super) struct Mounted {
    pub(super) root: Entity,
    pub(super) position: Entity,
    pub(super) rotation: Entity,
    pub(super) reference: Quat,
    pub(super) offset: Vec3,
    pub(super) part_rotation: Quat,
}

pub(super) struct AttachmentsPlugin;
impl Plugin for AttachmentsPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, prepare.before(super::prepare))
            .add_systems(PostUpdate, follow.after(AnimationSystems).before(TransformSystems::Propagate));
    }
}

fn required_mesh(node: &GltfNode) -> Result<&Handle<GltfMesh>, &'static str> {
    node.mesh.as_ref().ok_or("full node has no mesh")
}

/// A bone's rest rotation from the loaded glTF, never from a possibly already animated scene entity.
fn rest_rotation(gltf: &Gltf, nodes: &Assets<GltfNode>, name: &str) -> Option<Quat> {
    let target = gltf
        .nodes
        .iter()
        .filter_map(|h| nodes.get(h).map(|n| (h, n)))
        .filter(|(_, n)| n.name == name)
        .map(|(h, _)| h.id())
        .collect::<Vec<_>>();
    if target.len() != 1 {
        return None;
    }
    let mut current = target[0];
    let mut rotation = Quat::IDENTITY;
    for _ in 0..=gltf.nodes.len() {
        let node = nodes.get(current)?;
        rotation = node.transform.rotation * rotation;
        let parents: Vec<_> = gltf
            .nodes
            .iter()
            .filter_map(|h| nodes.get(h).map(|n| (h, n)))
            .filter(|(_, n)| n.children.iter().any(|c| c.id() == current))
            .map(|(h, _)| h.id())
            .collect();
        if parents.is_empty() {
            return Some(rotation.normalize());
        }
        if parents.len() != 1 {
            return None;
        }
        current = parents[0];
    }
    None
}

/// Wait for all attachment products and prepare the same painted materials as scenery before showing the actor.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn prepare(
    mut commands: Commands,
    pending: Query<(Entity, &Requests, &Model), (With<SceneReady>, Without<Ready>)>,
    children: Query<&Children>,
    names: Query<(Entity, &Name), Without<Mesh3d>>,
    gltfs: Res<Assets<Gltf>>,
    nodes: Res<Assets<GltfNode>>,
    gltf_meshes: Res<Assets<GltfMesh>>,
    meshes: Res<Assets<Mesh>>,
    assets: Res<AssetServer>,
    mut painted: PaintedMaterials,
    mut moving: MovingPaintedMaterials,
) {
    for (root, requests, Model(body)) in &pending {
        if requests.0.is_empty() {
            commands.entity(root).insert(Ready);
            continue;
        }
        let Some(body) = gltfs.get(body) else { continue };
        let mut products = Vec::new();
        let mut failure = None;
        let mut waiting = false;
        for (spec, handle) in &requests.0 {
            if matches!(assets.load_state(handle), LoadState::Failed(_)) {
                failure = Some(format!("{} failed to load", spec.model));
                break;
            }
            let Some(gltf) = gltfs.get(handle) else {
                waiting = true;
                break;
            };
            let Some(node) = gltf.named_nodes.get("full").and_then(|h| nodes.get(h)) else {
                failure = Some(format!("{} has no full node", spec.model));
                break;
            };
            let Ok(mesh_handle) = required_mesh(node) else {
                failure = Some(format!("{} full node has no mesh", spec.model));
                break;
            };
            let Some(mesh) = gltf_meshes.get(mesh_handle) else {
                if matches!(assets.load_state(mesh_handle), LoadState::Failed(_)) {
                    failure = Some(format!("{} glTF mesh failed to load", spec.model));
                } else {
                    waiting = true;
                }
                break;
            };
            let value = node.extras.as_ref().and_then(|v| serde_json::from_str::<serde_json::Value>(&v.value).ok());
            let profile = value
                .as_ref()
                .and_then(|v| v.get("vertex_paint"))
                .and_then(|v| serde_json::from_value::<Profile>(v.clone()).ok());
            let motion = value
                .as_ref()
                .and_then(|v| v.get("vertex_motion"))
                .map(|v| serde_json::from_value::<MotionProfile>(v.clone()));
            let Some(profile) = profile.filter(Profile::valid) else {
                failure = Some(format!("{} has invalid paint profile", spec.model));
                break;
            };
            let motion = match motion {
                Some(Ok(m)) if m.valid() => Some(m),
                None => None,
                _ => {
                    failure = Some(format!("{} has invalid motion profile", spec.model));
                    break;
                }
            };
            let find = |name: &str| {
                let found: Vec<_> = children
                    .iter_descendants(root)
                    .filter_map(|e| names.get(e).ok())
                    .filter(|(_, n)| n.as_str() == name)
                    .map(|(e, _)| e)
                    .collect();
                (found.len() == 1).then(|| found[0])
            };
            let (Some(position), Some(rotation), Some(reference)) = (
                find(&spec.position_bone),
                find(&spec.rotation_bone),
                rest_rotation(body, &nodes, &spec.rotation_bone),
            ) else {
                failure = Some(format!("{} has missing or duplicate attachment bones", spec.model));
                break;
            };
            let offset = Vec3::from_array(spec.offset);
            let part_rotation = Quat::from_array(spec.rotation);
            if (AttachmentPose {
                position_bone: Vec3::ZERO,
                rotation_bone: reference,
                reference_rotation: reference,
                offset,
                part_rotation,
            })
            .transform()
            .is_none()
            {
                failure = Some(format!("{} has invalid attachment pose", spec.model));
                break;
            }
            let mut parts = Vec::new();
            for primitive in &mesh.primitives {
                let Some(source) = meshes.get(&primitive.mesh) else {
                    if matches!(assets.load_state(&primitive.mesh), LoadState::Failed(_)) {
                        failure = Some(format!("{} primitive mesh failed to load", spec.model));
                    } else {
                        waiting = true;
                    }
                    break;
                };
                let material = standard_of(&assets, primitive.material.as_ref());
                match painted_part(source, &material, &profile, motion.as_ref(), &mut painted, &mut moving) {
                    Ok(Some(p)) => parts.push((primitive.mesh.clone(), p)),
                    Ok(None) if matches!(assets.load_state(&material), LoadState::Failed(_)) => {
                        failure = Some(format!("{} material failed to load", spec.model));
                        break;
                    }
                    Ok(None) => {
                        waiting = true;
                        break;
                    }
                    Err(reason) => {
                        failure = Some(format!("{}: {reason}", spec.model));
                        break;
                    }
                }
            }
            if waiting || failure.is_some() {
                break;
            }
            if parts.is_empty() {
                failure = Some(format!("{} has no primitives", spec.model));
                break;
            }
            products.push((position, rotation, reference, offset, part_rotation, parts));
        }
        if let Some(reason) = failure {
            error!("{reason}");
            commands.insert_resource(crate::loading::Missing(reason));
            commands.entity(root).despawn();
        } else if !waiting {
            for (position, rotation, reference, offset, part_rotation, parts) in products {
                for (mesh, part) in parts {
                    let mut entity = commands.spawn((
                        Mesh3d(mesh),
                        Transform::default(),
                        ChildOf(root),
                        Mounted { root, position, rotation, reference, offset, part_rotation },
                    ));
                    match part {
                        PaintedPart::Static(material) => {
                            entity.insert(MeshMaterial3d(material));
                        }
                        PaintedPart::Moving(material, _) => {
                            entity.insert((MeshMaterial3d(material), NoFrustumCulling));
                        }
                    }
                }
            }
            commands.entity(root).insert(Ready);
        }
    }
}

/// Current local transforms are read after animation and before propagation, never one frame late.
fn component_transform(
    entity: Entity,
    root: Entity,
    nodes: &Query<(&Transform, Option<&ChildOf>), Without<Mounted>>,
) -> Option<Transform> {
    let mut current = entity;
    let mut parts = Vec::new();
    for _ in 0..256 {
        if current == root {
            let mut result = Transform::IDENTITY;
            for part in parts.into_iter().rev() {
                result = result.mul_transform(part);
            }
            return Some(result);
        }
        let (transform, parent) = nodes.get(current).ok()?;
        parts.push(*transform);
        current = parent?.parent();
    }
    None
}

fn follow(
    nodes: Query<(&Transform, Option<&ChildOf>), Without<Mounted>>,
    mut parts: Query<(&Mounted, &mut Transform)>,
) {
    for (mount, mut transform) in &mut parts {
        let Some(position) = component_transform(mount.position, mount.root, &nodes) else { continue };
        let Some(rotation) = component_transform(mount.rotation, mount.root, &nodes) else { continue };
        let pose = AttachmentPose {
            position_bone: position.translation,
            rotation_bone: rotation.rotation,
            reference_rotation: mount.reference,
            offset: mount.offset,
            part_rotation: mount.part_rotation,
        };
        if let Some(value) = pose.transform() {
            *transform = value;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn full_node_without_mesh_is_rejected() {
        let node = bevy::gltf::GltfNode {
            index: 0,
            name: "full".into(),
            children: Vec::new(),
            mesh: None,
            skin: None,
            transform: bevy::prelude::Transform::default(),
            is_animation_root: false,
            extras: None,
        };
        assert_eq!(super::required_mesh(&node).unwrap_err(), "full node has no mesh");
    }

    #[test]
    fn follows_position_bone_but_uses_reference_relative_rotation_bone() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins).add_systems(PostUpdate, follow);
        let root = app.world_mut().spawn(Transform::from_scale(Vec3::splat(1.12))).id();
        let position = app.world_mut().spawn((Transform::from_xyz(2.0, 3.0, 4.0), ChildOf(root))).id();
        let rest = Quat::from_rotation_y(0.4);
        let turn = Quat::from_rotation_z(std::f32::consts::FRAC_PI_2);
        let rotation = app.world_mut().spawn((Transform::from_rotation(turn * rest), ChildOf(root))).id();
        let part = app
            .world_mut()
            .spawn((
                Transform::default(),
                ChildOf(root),
                Mounted { root, position, rotation, reference: rest, offset: Vec3::X, part_rotation: Quat::IDENTITY },
            ))
            .id();
        app.update();
        let transform = app.world().get::<Transform>(part).unwrap();
        assert!(transform.translation.distance(Vec3::new(2.0, 4.0, 4.0)) < 1e-5);
        assert!((transform.rotation * Vec3::X).distance(Vec3::Y) < 1e-5);
        assert_eq!(transform.scale, Vec3::ONE);
    }
}
