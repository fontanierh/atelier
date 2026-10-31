//! Regression coverage for imported plank seams and transition landings.
use super::*;
use crate::core::physics::{
    board::BodyId, board_world::WorldTriangle, collision::Sphere, contact::RetailContactMaterial,
};

fn face(points: [[f32; 3]; 3]) -> Triangle {
    WorldTriangle::from_vertices(
        [points[0], points[2], points[1]].map(|p| Vector3::new(p[0], p[1], p[2])),
        RetailContactMaterial { static_friction: 0.8, dynamic_friction: 0.6, restitution: 0. },
        130,
        0xe0,
        [1.; 3],
        0.,
    )
    .unwrap()
    .triangle
}
fn wheel(speed: f32) -> BoardWorldVolume {
    BoardWorldVolume {
        body: CollisionBody::Board(BodyId::LeftFrontWheel),
        primitive: ContactPrimitive::Sphere(Sphere { center: Vector3::new(0., 0.03, 0.), radius: 0.03 }),
        linear_velocity: Vector3::new(0., 0., speed),
        material: RetailContactMaterial { static_friction: 0.8, dynamic_friction: 0.6, restitution: 0. },
        support: SmallEdgeSupport { up: UP, floor: 0., world_floor: 0., rider_floor: false },
    }
}
fn contact() -> ContactPair {
    ContactPair { a: Vector3::new(0., 0.005, 0.015), b: Vector3::new(0., 0.005, 0.015) }
}
fn bevel_normal() -> Vector3 {
    Vector3::new(0., 0.8, -0.6)
}

#[test]
fn wheels_step_over_plank_edges_only_when_approaching_and_within_twelve_mm() {
    let plank = face([[-1., 0., 0.015], [1., 0., 0.015], [0., 0.01, 0.015]]);
    for speed in [11., 12., 13.] {
        let volume = wheel(speed);
        let mut pair = contact();
        let mut normal = bevel_normal();
        assert_eq!(ride_over_small_edge(&volume, plank, &mut pair, &mut normal), SmallEdge::StepUp);
        assert_eq!(normal, UP);
        assert_eq!(pair.a, Vector3::ZERO);
        assert!((pair.b.y - 0.005).abs() < 1e-7);
        assert_eq!(pair.b.z, 0.);
    }
    let mut volume = wheel(-12.);
    assert_eq!(ride_over_small_edge(&volume, plank, &mut contact(), &mut bevel_normal()), SmallEdge::None);
    volume.linear_velocity.z = 12.;
    let mut pair = contact();
    pair.b.y = 0.0121;
    assert_eq!(ride_over_small_edge(&volume, plank, &mut pair, &mut bevel_normal()), SmallEdge::None);
    volume.support = SmallEdgeSupport::default();
    assert_eq!(ride_over_small_edge(&volume, plank, &mut contact(), &mut bevel_normal()), SmallEdge::None);
}

#[test]
fn quarter_pipe_faces_keep_wheel_and_truck_contacts_at_eleven_to_thirteen_ms() {
    // Rising quarter tangent: this face normal opposes incoming travel, just
    // like a tiny bevel, but its whole extent is metres, not millimetres.
    let ramp = face([[-2., 0., 0.], [2., 0., 0.], [0., 3., 4.]]);
    for speed in [11., 12., 13.] {
        let mut volume = wheel(speed);
        let mut pair = contact();
        let mut normal = ramp.feature.normal;
        assert_eq!(ride_over_small_edge(&volume, ramp, &mut pair, &mut normal), SmallEdge::None);
        volume.body = CollisionBody::Board(BodyId::FrontTruck);
        assert_eq!(ride_over_small_edge(&volume, ramp, &mut contact(), &mut bevel_normal()), SmallEdge::None);
        // A pitched landing has a small deck-up projection of the ramp, but
        // still may not erase the tall face in world-up.
        volume.support.up = Vector3::new(0., 0.8, -0.6);
        assert_eq!(ride_over_small_edge(&volume, ramp, &mut contact(), &mut bevel_normal()), SmallEdge::None);
    }
}

#[test]
fn flat_bevel_faces_are_small_in_world_up_not_deck_up() {
    let bevel = face([[-1., 0., 0.], [1., 0., 0.], [0., 0.01, 0.02]]);
    let mut volume = wheel(12.);
    let mut pair = contact();
    pair.b = Vector3::new(0., 0.005, 0.01);
    let mut normal = bevel.feature.normal;
    assert_eq!(ride_over_small_edge(&volume, bevel, &mut pair, &mut normal), SmallEdge::StepUp);
    let tall = face([[-1., 0., 0.], [1., 0., 0.], [0., 0.013, 0.026]]);
    volume.support.up = Vector3::new(0., std::f32::consts::FRAC_1_SQRT_2, -std::f32::consts::FRAC_1_SQRT_2);
    let projected: Vec<_> = tall.vertices.iter().map(|p| dot(*p, volume.support.up)).collect();
    assert!(
        projected.iter().copied().fold(f32::NEG_INFINITY, f32::max)
            - projected.iter().copied().fold(f32::INFINITY, f32::min)
            < SMALL_EDGE_STEP
    );
    let mut normal = tall.feature.normal;
    assert_eq!(ride_over_small_edge(&volume, tall, &mut contact(), &mut normal), SmallEdge::None);
}

#[test]
fn pushing_foot_passes_plank_gap_but_not_tall_wall_or_deep_floor() {
    let plank = face([[-1., -0.1, 0.015], [1., -0.1, 0.015], [0., 0.01, 0.015]]);
    let mut volume = wheel(5.);
    volume.body = CollisionBody::Attached(11);
    volume.support = SmallEdgeSupport { rider_floor: true, ..Default::default() };
    let mut pair = contact();
    pair.b.y = -0.049;
    let mut normal = Vector3::new(0., 0., -1.);
    assert_eq!(ride_over_small_edge(&volume, plank, &mut pair, &mut normal), SmallEdge::Drop);
    pair.b.y = -0.051;
    assert_eq!(ride_over_small_edge(&volume, plank, &mut pair, &mut normal), SmallEdge::None);
    let wall = face([[-1., -0.1, 0.015], [1., -0.1, 0.015], [0., 1., 0.015]]);
    assert_eq!(ride_over_small_edge(&volume, wall, &mut contact(), &mut normal), SmallEdge::None);
}

#[test]
fn ordinary_world_keeps_the_same_primitive_contact_imported_wheels_step_over() {
    use crate::core::physics::board_world::{BoardWorld, ContactRetentionSettings};
    use crate::core::physics::collision::WorldContactSettings;
    // A single unshared plank top has a rounded wheel contact on its exposed edge.
    let top = WorldTriangle::from_vertices(
        [Vector3::new(-1., 0.005, 0.015), Vector3::new(-1., 0.005, 1.), Vector3::new(1., 0.005, 0.015)],
        wheel(5.).material,
        130,
        0xe0,
        [1.; 3],
        0.,
    )
    .unwrap();
    let mut stock = BoardWorld::new(vec![top]);
    let mut imported = BoardWorld::new(vec![top]);
    imported.enable_imported_floor_seams();
    let query = WorldContactSettings {
        volume_padding: 0.001,
        maximum_separating_distance: 0.05,
        edge_cos_bend_normal_threshold: -1.,
        convexity_epsilon: 0.,
        is_object: false,
    };
    let retention =
        ContactRetentionSettings { capacity: 50, duplicate_distance_squared: 1e-8, deferred_reduction: false };
    let volume = wheel(5.);
    let original = stock.query_primitives(&[volume], query, retention).to_vec();
    let corrected = imported.query_primitives(&[volume], query, retention);
    assert!(!original.is_empty());
    assert_eq!(original.len(), corrected.len());
    assert!(original[0].contact.normal.z < -0.1);
    assert_eq!(corrected[0].contact.normal, UP);
    assert_eq!(corrected[0].contact.tag, original[0].contact.tag);
}
