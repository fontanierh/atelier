//! Full-rig bind data and exclusive, same-frame solved pose submission.
use bevy::app::AnimationSystems;
use bevy::math::Affine3A;
use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy::transform::TransformSystems;

/// A bound bone, with its authored local and body-frame bind transforms.
#[derive(Clone, Debug)]
pub struct Bone {
    pub name: String,
    pub entity: Entity,
    pub parent: Option<usize>,
    pub rest: Transform,
    pub body_rest: Affine3A,
    /// Non-bone ancestors between the body's origin and a skeleton root (for example an armature's scale).
    pub root_parent: Affine3A,
}

/// The whole authored character rig, ordered parent before child.
#[derive(Component, Debug)]
pub struct Rig {
    pub bones: Vec<Bone>,
}

impl Rig {
    pub fn index(&self, name: &str) -> Option<usize> {
        self.bones.iter().position(|bone| bone.name == name)
    }
}

/// Claims the rig's pose for a procedural controller. Clip requests are ignored until it is removed.
#[derive(Component)]
pub struct PoseOverride;

/// Bone locals in the order published by [`Rig`]. A missing or nonfinite bone is rejected, never partly applied.
#[derive(Component, Default)]
pub struct SolvedPose(pub Vec<Transform>);

#[derive(SystemSet, Debug, Clone, Copy, Hash, PartialEq, Eq)]
pub enum PoseSystems {
    Apply,
}

pub(crate) struct PosePlugin;
impl Plugin for PosePlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(
            PostUpdate,
            apply.in_set(PoseSystems::Apply).after(AnimationSystems).before(TransformSystems::Propagate),
        );
    }
}

pub(crate) fn bind(
    body: Entity,
    names: &HashMap<String, Entity>,
    transforms: &Query<(&Transform, Option<&ChildOf>)>,
) -> Rig {
    let mut selected: Vec<_> =
        names.iter().filter(|(name, _)| is_bone(name)).map(|(name, entity)| (name.clone(), *entity)).collect();
    let depth = |mut node| {
        let mut depth = 0;
        while node != body {
            let Ok((_, Some(parent))) = transforms.get(node) else { break };
            node = parent.parent();
            depth += 1;
        }
        depth
    };
    selected.sort_by_key(|(name, entity)| (depth(*entity), name.clone()));
    let mut bones: Vec<Bone> = Vec::with_capacity(selected.len());
    for (name, entity) in selected {
        let Ok((rest, parent)) = transforms.get(entity) else { continue };
        let parent = parent.and_then(|parent| bones.iter().position(|bone| bone.entity == parent.parent()));
        let mut chain = rest.compute_affine();
        let mut at = entity;
        while let Ok((_, Some(parent))) = transforms.get(at) {
            at = parent.parent();
            if at == body {
                break;
            }
            let Ok((local, _)) = transforms.get(at) else { break };
            chain = local.compute_affine() * chain;
        }
        let root_parent = if parent.is_none() { chain * rest.compute_affine().inverse() } else { Affine3A::IDENTITY };
        bones.push(Bone { name, entity, parent, rest: *rest, body_rest: chain, root_parent });
    }
    Rig { bones }
}

fn is_bone(name: &str) -> bool {
    matches!(name, "pelvis" | "spine" | "spine_mid" | "chest" | "neck" | "head")
        || [
            "thigh_",
            "shin_",
            "foot_",
            "toe_",
            "clavicle_",
            "upper_arm_",
            "forearm_",
            "hand_",
            "thumb_",
            "index_",
            "middle_",
            "ring_",
            "pinky_",
        ]
        .iter()
        .any(|prefix| name.starts_with(prefix))
}

fn apply(rigs: Query<(&Rig, &SolvedPose), With<PoseOverride>>, mut transforms: Query<&mut Transform>) {
    for (rig, pose) in &rigs {
        if pose.0.len() != rig.bones.len()
            || pose.0.iter().any(|p| !p.translation.is_finite() || !p.rotation.is_finite() || !p.scale.is_finite())
        {
            error!("Rejected incomplete or nonfinite solved character pose");
            continue;
        }
        for (bone, local) in rig.bones.iter().zip(&pose.0) {
            if let Ok(mut transform) = transforms.get_mut(bone.entity) {
                *transform = *local;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn binding_retains_armature_scale_and_parent_before_child_order() {
        let mut world = World::new();
        let body = world.spawn(Transform::IDENTITY).id();
        let armature = world.spawn((Transform::from_scale(Vec3::splat(1.6)), ChildOf(body))).id();
        let hip = world.spawn((Transform::from_xyz(0., 0.6, 0.), ChildOf(armature))).id();
        let leg = world.spawn((Transform::from_xyz(0.1, -0.1, 0.), ChildOf(hip))).id();
        let mut query = world.query::<(&Transform, Option<&ChildOf>)>();
        let query = query.query(&world);
        let names = HashMap::from_iter([("thigh_l".into(), leg), ("pelvis".into(), hip)]);
        let rig = bind(body, &names, &query);
        assert_eq!(rig.bones[0].entity, hip);
        assert_eq!(rig.bones[1].parent, Some(0));
        let root = rig.bones[0].body_rest;
        assert!((root.translation.y - 0.96).abs() < 1e-5);
        let local = rig.bones[0].root_parent.inverse() * root;
        assert!((local.translation.y - 0.6).abs() < 1e-5);
    }
}
