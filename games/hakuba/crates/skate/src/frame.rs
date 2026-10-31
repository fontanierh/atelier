//! The sole simulation-world boundary. Rig-local axes are deliberately not converted here.
use bevy::prelude::*;

pub fn world_point(point: Vec3) -> Vec3 {
    Vec3::new(point.z, point.y, point.x)
}
pub fn simulation_point(point: Vec3) -> Vec3 {
    world_point(point)
}

/// Conjugating by the reflection preserves rotations and does not introduce a negative scale.
pub fn world_transform(matrix: Mat4) -> Transform {
    let swap = Mat4::from_cols(Vec4::Z, Vec4::Y, Vec4::X, Vec4::W);
    Transform::from_matrix(swap * matrix * swap)
}

pub fn interpolate(a: &Transform, b: &Transform, alpha: f32) -> Transform {
    Transform {
        translation: a.translation.lerp(b.translation, alpha),
        rotation: a.rotation.slerp(b.rotation, alpha),
        scale: a.scale.lerp(b.scale, alpha),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn asymmetric_world_fixture_preserves_points_turns_and_winding() {
        let source = Mat4::from_rotation_translation(Quat::from_rotation_y(0.7), Vec3::new(2., 3., 5.));
        let local = Vec3::new(0.1, 0.2, 0.9);
        let shown = world_transform(source);
        assert!(
            (shown.transform_point(world_point(local)) - world_point(source.transform_point3(local))).length() < 1e-5
        );
        assert!((shown.rotation.length() - 1.).abs() < 1e-5);
        let triangle = [Vec3::new(1., 0., 2.), Vec3::new(1., 0., 5.), Vec3::new(4., 0., 2.)];
        let a = world_point(triangle[0]);
        let b = world_point(triangle[2]);
        let c = world_point(triangle[1]);
        assert!((b - a).cross(c - a).normalize().dot(Vec3::Y) > 0.99);
    }
}
