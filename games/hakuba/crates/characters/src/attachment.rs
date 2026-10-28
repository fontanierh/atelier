//! Reference-relative rigid attachment posing in the character's component frame.

use bevy::prelude::*;

/// Where a rigid part sits, relative to a position bone and a rotation bone.
/// All values are in the character's component frame, before the character's world scale.
pub struct AttachmentPose {
    pub position_bone: Vec3,
    pub rotation_bone: Quat,
    pub reference_rotation: Quat,
    pub offset: Vec3,
    pub part_rotation: Quat,
}

impl AttachmentPose {
    /// @cc [owner:fontanierh,label:correctness] attachments-follow-reference-relative-pose
    /// A rigid part MUST use the position bone and reference-relative rotation bone in the same component frame;
    /// its parent MUST apply world placement and scale exactly once.
    pub fn transform(&self) -> Option<Transform> {
        let rotation_ok = |q: Quat| q.is_finite() && (q.length_squared() - 1.0).abs() < 1e-4;
        if !self.position_bone.is_finite()
            || !self.offset.is_finite()
            || !rotation_ok(self.rotation_bone)
            || !rotation_ok(self.reference_rotation)
            || !rotation_ok(self.part_rotation)
        {
            return None;
        }
        let delta = (self.rotation_bone * self.reference_rotation.inverse()).normalize();
        Some(
            Transform::from_translation(self.position_bone + delta * self.offset)
                .with_rotation((delta * self.part_rotation).normalize()),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn uses_reference_relative_rotation_and_an_independent_position_bone() {
        let rest = Quat::from_rotation_y(0.6);
        let turn = Quat::from_rotation_z(std::f32::consts::FRAC_PI_2);
        let pose = AttachmentPose {
            position_bone: Vec3::new(2.0, 3.0, 4.0),
            rotation_bone: turn * rest,
            reference_rotation: rest,
            offset: Vec3::X,
            part_rotation: Quat::from_rotation_y(0.2),
        };
        let transform = pose.transform().unwrap();
        assert!(transform.translation.distance(Vec3::new(2.0, 4.0, 4.0)) < 1e-5);
        assert!((transform.rotation * Vec3::X).distance((turn * pose.part_rotation) * Vec3::X) < 1e-5);
        assert_eq!(transform.scale, Vec3::ONE);
    }

    #[test]
    fn rejects_invalid_bone_and_offset_data() {
        let mut pose = AttachmentPose {
            position_bone: Vec3::ZERO,
            rotation_bone: Quat::IDENTITY,
            reference_rotation: Quat::IDENTITY,
            offset: Vec3::ZERO,
            part_rotation: Quat::IDENTITY,
        };
        pose.offset.x = f32::NAN;
        assert!(pose.transform().is_none());
        pose.offset = Vec3::ZERO;
        pose.reference_rotation = Quat::from_xyzw(0.0, 0.0, 0.0, 0.0);
        assert!(pose.transform().is_none());
    }
}
