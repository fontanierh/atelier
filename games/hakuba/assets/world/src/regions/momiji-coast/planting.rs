//! Momiji coast's plants: a mixed wood of maples, broadleaves, ginkgos and pines on the slopes, cedars high up, a
//! thinner wood far from the road, bushes thick by the road and sparse beyond, grass everywhere, and grass and bushes
//! along the bank the road is cut into.

use std::f64::consts::TAU;

use glam::DVec2;

use super::uphill;
use crate::random::Random;
use crate::world::curve::nearest;
use crate::world::scenery::{Land, Placement, ScatterKind};

/// Models, each with its weight in the mix.
type Mix = [(&'static str, f64)];

/// Trees within 26 m of the road.
const ROADSIDE_TREES: &Mix = &[
    ("plants/pine-a", 0.12),
    ("plants/pine-b", 0.05),
    ("plants/maple-a", 0.16),
    ("plants/maple-b", 0.08),
    ("plants/broad-a", 0.38),
    ("plants/ginkgo-a", 0.12),
    ("plants/ginkgo-b", 0.09),
];

/// Trees on ground more than 22 m above the sea.
const HIGH_TREES: &Mix = &[
    ("plants/cedar-a", 0.04),
    ("plants/cedar-b", 0.02),
    ("plants/pine-a", 0.06),
    ("plants/maple-a", 0.36),
    ("plants/maple-b", 0.14),
    ("plants/broad-b", 0.2),
    ("plants/ginkgo-a", 0.1),
    ("plants/ginkgo-b", 0.08),
];

/// Trees elsewhere.
const TREES: &Mix = &[
    ("plants/broad-a", 0.12),
    ("plants/broad-b", 0.08),
    ("plants/maple-a", 0.28),
    ("plants/maple-b", 0.14),
    ("plants/ginkgo-a", 0.08),
    ("plants/ginkgo-b", 0.06),
    ("plants/pine-a", 0.2),
    ("plants/cedar-b", 0.04),
];

/// The thinner wood more than 95 m from the road.
const FAR_TREES: &Mix = &[
    ("plants/maple-a", 0.48),
    ("plants/broad-a", 0.18),
    ("plants/ginkgo-a", 0.12),
    ("plants/cedar-b", 0.08),
    ("plants/pine-b", 0.14),
];

const BUSHES: &Mix = &[
    ("plants/green-bush-a", 0.36),
    ("plants/green-bush-b", 0.24),
    ("plants/ochre-bush-a", 0.13),
    ("plants/ochre-bush-b", 0.09),
    ("plants/flower-bush-a", 0.11),
    ("plants/flower-bush-b", 0.07),
];

/// The smaller bushes, for the bank.
const SMALL_BUSHES: &Mix =
    &[("plants/green-bush-b", 0.24), ("plants/ochre-bush-b", 0.09), ("plants/flower-bush-b", 0.07)];

const GRASS: &Mix = &[("plants/grass-a", 0.5), ("plants/grass-b", 0.5)];

/// How high above the sea the ground must be for anything to grow.
const SHORE_M: f64 = 1.2;

/// Every plant in the region, on the exported part of `land`, kept clear of the road along `road`.
pub fn plants(land: &Land, road: &[(DVec2, DVec2)]) -> Vec<Placement> {
    let mut plants = Vec::new();
    // Each candidate, with its distance to the road.
    let ground = |seed, side, jitter, kind| {
        land.scatter(seed, side, jitter, kind).filter_map(|(at, random)| {
            let height = land.height(land.placement_at(at))?;
            (height >= SHORE_M).then(|| (at, height, nearest(road, at).0, random))
        })
    };
    let mut place = |kind, model: &'static str, at, random: &mut Random, scale, afar| {
        let placement = Placement { model, at, yaw: random.range([0.0, TAU]), scale, afar };
        if land.allows_candidate(kind, &placement) {
            plants.push(placement);
        }
    };

    for (at, height, road_m, mut random) in ground(1, 5.0, 0.45, ScatterKind::Tree) {
        if land.slope(land.placement_at(at)) > 1.6 {
            continue;
        }
        let (skip, mix) = match () {
            _ if road_m < 26.0 => (0.2, ROADSIDE_TREES),
            _ if height > 22.0 => (0.05, HIGH_TREES),
            _ => (0.15, TREES),
        };
        if random.unit() < skip {
            continue;
        }
        let model = random.pick(mix, |(_, w)| *w).0;
        let scale = random.range([0.85, 1.25]) * if road_m > 26.0 { 1.25 } else { 1.0 };
        place(ScatterKind::Tree, model, at, &mut random, scale, true);
    }

    for (at, _, road_m, mut random) in ground(2, 3.2, 0.5, ScatterKind::Tree) {
        if road_m < 95.0 || land.slope(land.placement_at(at)) > 1.6 || random.unit() > 0.6 {
            continue;
        }
        let model = random.pick(FAR_TREES, |(_, w)| *w).0;
        let scale = random.range([0.9, 1.3]);
        place(ScatterKind::Tree, model, at, &mut random, scale, true);
    }

    for (at, _, road_m, mut random) in ground(3, 2.4, 0.45, ScatterKind::Bush) {
        if land.slope(land.placement_at(at)) > 1.8 {
            continue;
        }
        let keep = match () {
            _ if road_m < 9.0 => 0.9,
            _ if road_m < 40.0 => 0.35,
            _ => 0.08,
        };
        if random.unit() > keep {
            continue;
        }
        let model = random.pick(BUSHES, |(_, w)| *w).0;
        let scale = random.range(if road_m < 6.5 { [0.6, 0.95] } else { [0.8, 1.3] });
        place(ScatterKind::Bush, model, at, &mut random, scale, true);
    }

    for (at, _, road_m, mut random) in ground(4, 0.85, 0.5, ScatterKind::Grass) {
        let keep = match () {
            _ if road_m < 40.0 => 1.0,
            _ if road_m < 90.0 => 0.4,
            _ => 0.08,
        };
        if random.unit() > keep {
            continue;
        }
        let model = random.pick(GRASS, |(_, w)| *w).0;
        let scale = random.range([0.7, 1.25]) * if road_m < 6.0 { 1.25 } else { 1.0 };
        place(ScatterKind::Grass, model, at, &mut random, scale, false);
    }

    // The bank: thick grass, and now and then a small bush, on the rising side of the road, every metre along it.
    for (k, &(centre, direction)) in road.iter().enumerate() {
        let (Some(road_height), side) = (land.height(centre), uphill(land, centre, direction)) else { continue };
        for (n, offset) in [3.5, 4.8, 6.3, 8.0].into_iter().enumerate() {
            let mut random = Random::at(5, k as i64, n as i64);
            let at = centre + direction.perp() * side * (offset + random.range([-0.3, 0.3]));
            if !land.allows_scatter(at, ScatterKind::Grass) {
                continue;
            }
            let Some(height) = land.height(land.placement_at(at)) else { continue };
            if offset > 5.0 && height < road_height + 0.3 {
                continue;
            }
            let model = random.pick(GRASS, |(_, w)| *w).0;
            let scale = random.range([1.0, 1.4]);
            place(ScatterKind::Grass, model, at, &mut random, scale, false);
        }
        let mut random = Random::at(6, k as i64, 0);
        if random.unit() < 0.25 {
            let at = centre + direction.perp() * side * random.range([4.5, 8.5]);
            if !land.allows_scatter(at, ScatterKind::Bush) {
                continue;
            }
            let model = random.pick(SMALL_BUSHES, |(_, w)| *w).0;
            let scale = random.range([0.6, 1.0]);
            place(ScatterKind::Bush, model, at, &mut random, scale, true);
        }
    }
    plants
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::world::ground::Ground;
    use crate::world::levelling::Strip;
    use crate::world::overlay::Overlay;
    use crate::world::regions::Region;
    use crate::world::scenery::Scenery;

    struct Mask;
    impl Region for Mask {
        fn name(&self) -> &'static str {
            "test"
        }
        fn levelled(&self) -> Vec<Strip> {
            vec![]
        }
        fn overlays(&self) -> Vec<Overlay> {
            vec![]
        }
        fn scenery(&self, _: &Land) -> Scenery {
            Scenery::default()
        }
        fn fastens_to(&self) -> Vec<&'static str> {
            vec![]
        }
        fn allows_scatter_candidate(&self, kind: ScatterKind, p: &Placement) -> bool {
            !(kind == ScatterKind::Grass && p.model == "plants/grass-a" && p.scale > 1.0 && p.at.x < 32.0)
        }
    }

    #[test]
    fn selected_candidate_mask_keeps_other_placements_and_random_choices() {
        let ground = Ground::page(64, 1.0, |_, _| 10.0);
        let empty = Land {
            ground: &ground,
            raised: &crate::world::raised::Prepared::new(&[], DVec2::ZERO, 8.0),
            low: DVec2::splat(8.0),
            high: DVec2::splat(56.0),
            exclusions: &[],
            regions: &[],
            domains: &[],
            openings: &[],
        };
        let mask = Mask;
        let regions: [&dyn Region; 1] = [&mask];
        let filtered = Land { regions: &regions, ..empty };
        let road = crate::world::curve::curve(&[[0.0, 32.0], [64.0, 32.0]]);
        let values = |plants: Vec<Placement>| {
            plants.into_iter().map(|p| (p.model, p.at.to_array(), p.yaw, p.scale, p.afar)).collect::<Vec<_>>()
        };
        let all = plants(&empty, &road);
        let expected = values(
            plants(&empty, &road)
                .into_iter()
                .filter(|p| {
                    mask.allows_scatter_candidate(
                        if p.model.starts_with("plants/grass-") { ScatterKind::Grass } else { ScatterKind::Tree },
                        p,
                    )
                })
                .collect(),
        );
        let actual = values(plants(&filtered, &road));
        assert!(actual.len() < all.len());
        assert_eq!(actual, expected);
    }
}
