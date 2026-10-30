//! Imported-mesh wheel compliance. Tall transition faces retain their contacts.
use super::{BoardWorldVolume, CollisionBody, ContactPrimitive};
use crate::core::{
    math::Vector3,
    physics::{
        board_motion_output::{dot, scale, subtract},
        collision::{ContactPair, Triangle},
    },
};

pub const SMALL_EDGE_STEP: f32 = 0.012;
const RIDER_GAP_DEPTH: f32 = 0.05;
const UP: Vector3 = Vector3::new(0., 1., 0.);

/// Wheel-bottom reference; zero-up leaves ordinary volumes unchanged.
#[derive(Clone, Copy, Debug, Default)]
pub struct SmallEdgeSupport {
    pub up: Vector3,
    pub floor: f32,
    pub world_floor: f32,
    pub rider_floor: bool,
}

/// Bind all board children to the lowest enabled wheel in deck-up and world-up.
pub fn board_support(volumes: &mut [BoardWorldVolume], up: Vector3) {
    let mut floor: Option<f32> = None;
    let mut world_floor: Option<f32> = None;
    for volume in volumes.iter() {
        if !is_wheel(volume) {
            continue;
        }
        let ContactPrimitive::Sphere(wheel) = volume.primitive else {
            continue;
        };
        let bottom = dot(wheel.center, up) - wheel.radius;
        let world = wheel.center.y - wheel.radius;
        floor = Some(floor.map_or(bottom, |previous| previous.min(bottom)));
        world_floor = Some(world_floor.map_or(world, |previous| previous.min(world)));
    }
    if let (Some(floor), Some(world_floor)) = (floor, world_floor) {
        for volume in volumes {
            volume.support = SmallEdgeSupport { up, floor, world_floor, rider_floor: false };
        }
    }
}
fn is_wheel(volume: &BoardWorldVolume) -> bool {
    matches!(volume.body, CollisionBody::Board(id) if id.index() < 4)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum SmallEdge {
    None,
    StepUp,
    Drop,
}

pub(super) fn ride_over_small_edge(
    volume: &BoardWorldVolume,
    face: Triangle,
    pair: &mut ContactPair,
    normal: &mut Vector3,
) -> SmallEdge {
    let support = volume.support;
    if support.rider_floor {
        return ride_along(volume, face, UP, support.world_floor, -RIDER_GAP_DEPTH, pair, normal);
    }
    if dot(support.up, support.up) < 0.5 {
        return SmallEdge::None;
    }
    let deck = ride_along(volume, face, support.up, support.floor, f32::NEG_INFINITY, pair, normal);
    if deck != SmallEdge::None {
        deck
    } else {
        ride_along(volume, face, UP, support.world_floor, -SMALL_EDGE_STEP, pair, normal)
    }
}

fn ride_along(
    volume: &BoardWorldVolume,
    face: Triangle,
    up: Vector3,
    floor: f32,
    lowest: f32,
    pair: &mut ContactPair,
    normal: &mut Vector3,
) -> SmallEdge {
    let height = dot(pair.b, up) - floor;
    let along = dot(*normal, up);
    if height > SMALL_EDGE_STEP {
        return SmallEdge::None;
    }
    let wheel = match volume.primitive {
        ContactPrimitive::Sphere(wheel) if is_wheel(volume) => Some(wheel),
        _ => None,
    };
    let Some(wheel) = wheel else {
        if !(height >= lowest && along > -0.9 && along < 0.9) {
            return SmallEdge::None;
        }
        // The whole face, not just this contact, must lie under the world-up step.
        if face.vertices.iter().any(|corner| corner.y - volume.support.world_floor > SMALL_EDGE_STEP) {
            return SmallEdge::None;
        }
        return SmallEdge::Drop;
    };
    if height < -SMALL_EDGE_STEP || along >= 0.999 || along <= 0. {
        return SmallEdge::None;
    }
    if dot(*normal, face.feature.normal).abs() > 0.9999 {
        let low = face.vertices.iter().map(|corner| corner.y).fold(f32::INFINITY, f32::min);
        let high = face.vertices.iter().map(|corner| corner.y).fold(f32::NEG_INFINITY, f32::max);
        if high - low > SMALL_EDGE_STEP {
            return SmallEdge::None;
        }
    }
    let step = wheel.radius - dot(subtract(wheel.center, pair.b), up);
    if step > SMALL_EDGE_STEP {
        return SmallEdge::None;
    }
    let across = subtract(*normal, scale(up, along));
    if dot(across, volume.linear_velocity) >= 0. {
        return SmallEdge::None;
    }
    *normal = up;
    pair.a = subtract(wheel.center, scale(up, wheel.radius));
    pair.b = Vector3::new(up.x.mul_add(step, pair.a.x), up.y.mul_add(step, pair.a.y), up.z.mul_add(step, pair.a.z));
    SmallEdge::StepUp
}

#[cfg(test)]
mod tests;
