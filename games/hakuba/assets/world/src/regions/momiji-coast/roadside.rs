//! What stands along Momiji coast's road: utility poles on its rising side with cables from pole to pole, a street
//! lamp on every third pole, and a guardrail on its falling side wherever the ground drops away.

use std::f64::consts::FRAC_PI_2;

use glam::DVec2;

use super::{LEVEL_HALF_WIDTH_M, SHOULDER_M, uphill};
use crate::world::scenery::{Cable, Land, Placement, Rail, Scenery};

/// The named one-metre sample domain along the downhill rail.
pub const RAIL_PATH: &str = "coastal-downhill-rail";

pub const POLE: &str = "props/utility-pole";

const LAMP: &str = "props/street-lamp";

/// How far apart the poles stand along the road, and where along it the first stands, in metres.
const POLE_SPACING_M: usize = 30;
const FIRST_POLE_M: usize = 12;

/// How far the poles stand from the road's centre.
const POLE_OFFSET_M: f64 = 4.3;

/// How many anchors a pole has: each joins the same anchor of the next pole.
const POLE_ANCHORS: usize = 5;

/// How far the guardrail runs from the road's centre, how many metres apart its posts stand, and their radius.
const RAIL_OFFSET_M: f64 = 3.1;
const RAIL_POST_SPACING: usize = 2;
const RAIL_POST_RADIUS_M: f64 = 0.05;

/// The guardrail runs where the ground just past the levelled strip and its shoulder is this far below the road.
const RAIL_DROP_M: f64 = 1.2;

/// A guardrail is left out where it would run for fewer metres than this.
const SHORTEST_RAIL_M: usize = 6;

/// The guardrail's W-shaped beam: each point's offset toward the road from the posts' centres, and its height.
const RAIL_PROFILE: [[f64; 2]; 5] = [[0.05, 0.85], [0.11, 0.80], [0.05, 0.72], [0.11, 0.64], [0.05, 0.58]];

/// The guardrail's white paint, which tints its weathered painted metal, and the cables' dark metal.
const PAINT: [f64; 3] = [0.86, 0.86, 0.84];
const METAL: &str = "painted-metal";
const CABLE: [f64; 3] = [0.12, 0.12, 0.13];

/// Adds the poles, lamps, cables and guardrails along `road` to `scenery`.
pub fn add(scenery: &mut Scenery, land: &Land, road: &[(DVec2, DVec2)]) {
    let mut previous: Option<usize> = None;
    for (n, k) in (FIRST_POLE_M..road.len()).step_by(POLE_SPACING_M).enumerate() {
        let (centre, direction) = road[k];
        let side = uphill(land, centre, direction);
        let at = centre + direction.perp() * side * POLE_OFFSET_M;
        // A pole's y points to the road, so a lamp's arm reaches over it.
        let yaw = (-direction.perp() * side).to_angle() - FRAC_PI_2;
        let pole = scenery.placements.len();
        scenery.placements.push(Placement { model: POLE, at, yaw, scale: 1.0, origin_offset_m: 0.0, afar: true });
        if n % 3 == 1 {
            scenery.placements.push(Placement { model: LAMP, at, yaw, scale: 1.0, origin_offset_m: 0.0, afar: true });
        }
        if let Some(before) = previous {
            for anchor in 0..POLE_ANCHORS {
                let (from, to) = ((before, anchor), (pole, anchor));
                scenery.cables.push(Cable { from, to, sag: 0.035, radius_m: 0.015, colour: CABLE });
            }
        }
        previous = Some(pole);
    }

    // Each metre of road the guardrail runs along, with the side it runs on, in runs of neighbouring metres.
    let mut runs: Vec<Vec<(usize, f64)>> = vec![Vec::new()];
    for (k, &(centre, direction)) in road.iter().enumerate() {
        let side = -uphill(land, centre, direction);
        let drops = !land.is_open(RAIL_PATH, k as f64).expect("the rail samples its published domain")
            && match (
                land.height(centre),
                land.height(centre + direction.perp() * side * (LEVEL_HALF_WIDTH_M + SHOULDER_M)),
            ) {
                (Some(road_height), Some(out)) => out < road_height - RAIL_DROP_M,
                _ => false,
            };
        let run = runs.last_mut().unwrap();
        if drops && run.last().is_none_or(|&(last, last_side)| last + 1 == k && last_side == side) {
            run.push((k, side));
        } else if drops {
            runs.push(vec![(k, side)]);
        } else if !run.is_empty() {
            runs.push(Vec::new());
        }
    }
    for run in runs.into_iter().filter(|run| run.len() > SHORTEST_RAIL_M) {
        let side = run[0].1;
        let mut path: Vec<DVec2> =
            run.iter().map(|&(k, _)| road[k].0 + road[k].1.perp() * side * RAIL_OFFSET_M).collect();
        // The profile's offsets are to the path's left: run it so the road is on its left.
        if side > 0.0 {
            path.reverse();
        }
        scenery.rails.push(Rail {
            path,
            profile: RAIL_PROFILE.to_vec(),
            post_every: RAIL_POST_SPACING,
            post_radius_m: RAIL_POST_RADIUS_M,
            colour: PAINT,
            texture: METAL,
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::world::ground::Ground;
    use crate::world::openings::{Domain, Opening};

    #[test]
    fn declared_opening_splits_the_downhill_rail_without_changing_other_runs() {
        let ground = Ground::page(256, 1.0, |_, j| 10.0 + j as f32 * 0.2);
        let road: Vec<_> = (0..=120).map(|k| (DVec2::new(64.0 + k as f64, 128.0), DVec2::X)).collect();
        let domains = [Domain { id: RAIL_PATH, from: 0.0, to: 120.0, step: 1.0 }];
        let openings = [Opening { id: RAIL_PATH, from: 86.2, to: 105.9 }];
        let land = Land {
            ground: &ground,
            raised: &crate::world::raised::Prepared::new(&[], DVec2::ZERO, 1.0),
            low: DVec2::ZERO,
            high: DVec2::splat(256.0),
            exclusions: &[],
            regions: &[],
            domains: &domains,
            openings: &[],
        };
        let mut before = Scenery::default();
        add(&mut before, &land, &road);
        assert_eq!(before.rails.len(), 1);
        let opened = Land { openings: &openings, ..land };
        let mut after = Scenery::default();
        add(&mut after, &opened, &road);
        assert_eq!(after.rails.len(), 2);
        assert_eq!(after.rails[0].path, before.rails[0].path[..=86]);
        assert_eq!(after.rails[1].path, before.rails[0].path[106..]);
    }
}
