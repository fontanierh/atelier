//! Imported collision metadata uses the same ordered faces as the world mesh.
use super::*;

#[test]
fn surfaces_keep_triangle_order_in_queries_and_solver_tags() {
    let points = |x| [[x, 0., -1.], [x, 0., 1.], [x + 1., 0., -1.]];
    let packed = vec![130, 647, 260, 129, 130];
    let map =
        collision_map((0..5).map(|x| points(x as f32 * 2.)).collect(), packed.clone(), vec![], [0.; 3], 0.).unwrap();
    let material = crate::core::physics::contact::RetailContactMaterial {
        static_friction: 0.8,
        dynamic_friction: 0.6,
        restitution: 0.,
    };
    let world = crate::skate_world::collision_world(&map, material).unwrap();
    assert_eq!(world.query_metadata().unwrap().packed_surfaces, packed);
    for (i, entry) in world.triangles().iter().enumerate() {
        assert_eq!(entry.tag, u32::from(packed[i]));
        assert_eq!(entry.triangle.vertices[0].x, i as f32 * 2.);
        let hit = world
            .query_thin_line(
                crate::core::math::Vector3::new(i as f32 * 2. + 0.1, 0.1, -0.8),
                crate::core::math::Vector3::new(i as f32 * 2. + 0.1, -0.1, -0.8),
            )
            .unwrap()
            .unwrap();
        assert_eq!(hit.tag, u32::from(packed[i]));
    }
}

#[test]
fn surface_count_and_profiles_are_required_not_synthesized() {
    let tri = [[-1., 0., -1.], [-1., 0., 1.], [1., 0., -1.]];
    assert!(collision_map(vec![tri], vec![], vec![], [0.; 3], 0.).is_err());
    assert!(collision_map(vec![tri], vec![0], vec![], [0.; 3], 0.).is_err());
    assert!(collision_map(vec![tri], vec![31 << 7], vec![], [0.; 3], 0.).is_err());
    assert!(collision_map(vec![], vec![], vec![], [0.; 3], 0.).is_ok());
}
