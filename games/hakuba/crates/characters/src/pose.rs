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

/// How long a rig takes to ease from the last pose shown to its new source's, in seconds.
const HANDOVER_S: f32 = 0.25;

/// A rig's last shown bone locals, whether a solved pose drove them, and the pose it eases from and for how long.
#[derive(Component, Default)]
pub struct PoseHandover {
    shown: Vec<Transform>,
    solved: bool,
    from: Option<(Vec<Transform>, f32)>,
    /// How far, in the world, the body's origin jumped at the change: the new source's root need not be where the old
    /// one stood, so the body is carried back by it and eased home with the pose.
    jump: Vec3,
}

/// Puts each rig's solved pose on its bones, or leaves its clips' pose. When a rig changes between the two, as on
/// stepping on or off the board, its bones ease from the last pose shown to the new source's over [`HANDOVER_S`], as
/// Unreal blends from a pose snapshot, instead of jumping.
#[allow(clippy::type_complexity)]
fn apply(
    mut commands: Commands,
    mut rigs: Query<(
        Entity,
        &Rig,
        Option<&SolvedPose>,
        Has<PoseOverride>,
        Option<&mut PoseHandover>,
        &GlobalTransform,
        Option<&ChildOf>,
    )>,
    mut transforms: Query<&mut Transform>,
    time: Res<Time>,
) {
    for (entity, rig, pose, solved, handover, shown_at, parent) in &mut rigs {
        let mut wanted: Vec<Transform> = match (solved, pose) {
            (true, Some(pose)) => {
                if pose.0.len() != rig.bones.len()
                    || pose
                        .0
                        .iter()
                        .any(|p| !p.translation.is_finite() || !p.rotation.is_finite() || !p.scale.is_finite())
                {
                    error!("Rejected incomplete or nonfinite solved character pose");
                    continue;
                }
                pose.0.clone()
            }
            (true, None) => continue,
            (false, _) => {
                let Ok(locals) = rig.bones.iter().map(|bone| transforms.get(bone.entity).copied()).collect() else {
                    continue;
                };
                locals
            }
        };
        let Some(mut handover) = handover else {
            commands.entity(entity).insert(PoseHandover {
                shown: wanted.clone(),
                solved,
                from: None,
                jump: Vec3::ZERO,
            });
            write(rig, &wanted, &mut transforms);
            continue;
        };
        // The body's parent, the player's root, is placed for this frame; the body's own place is still last frame's.
        let root = parent.and_then(|parent| transforms.get(parent.parent()).ok().copied());
        if handover.solved != solved && handover.shown.len() == wanted.len() {
            handover.from = Some((std::mem::take(&mut handover.shown), 0.0));
            handover.jump = root.map_or(Vec3::ZERO, |root| shown_at.translation() - root.translation);
        }
        handover.solved = solved;
        let (mut carried, jump) = (Vec3::ZERO, handover.jump);
        if let Some((from, elapsed)) = &mut handover.from {
            *elapsed += time.delta_secs();
            let t = (*elapsed / HANDOVER_S).min(1.0);
            let eased = t * t * (3.0 - 2.0 * t);
            carried = jump * (1.0 - eased);
            for (local, from) in wanted.iter_mut().zip(from.iter()) {
                local.translation = from.translation.lerp(local.translation, eased);
                local.rotation = from.rotation.slerp(local.rotation, eased);
                local.scale = from.scale.lerp(local.scale, eased);
            }
            if t >= 1.0 {
                handover.from = None;
            }
        }
        if let (Some(root), Ok(mut body)) = (root, transforms.get_mut(entity)) {
            body.translation = root.rotation.inverse() * carried / root.scale;
        }
        write(rig, &wanted, &mut transforms);
        handover.shown = wanted;
    }
}

fn write(rig: &Rig, locals: &[Transform], transforms: &mut Query<&mut Transform>) {
    for (bone, local) in rig.bones.iter().zip(locals) {
        if let Ok(mut transform) = transforms.get_mut(bone.entity) {
            transform.set_if_neq(*local);
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
