//! Momiji Hamlet: a woodland approach, the lanes around the well and a small settlement on a sloping terrace.

mod scenery;

use super::{REGIONS, Region};
use crate::world::curve::{curve, nearest};
use crate::world::levelling::{Pad, Profile, Strip};
use crate::world::overlay::Overlay;
use crate::world::ribbon::ribbon;
use crate::world::scenery::{Exclusion, Land, ScatterKind, Scenery};
use glam::DVec2;

/// The approach and the lane past the houses, from the coast toward the north of the hamlet.
const LANE: [[f64; 2]; 14] = [
    [81.0, -9.0],
    [83.0, 0.0],
    [85.0, 8.0],
    [88.0, 18.0],
    [92.0, 30.0],
    [97.0, 41.0],
    [103.0, 52.0],
    [108.0, 59.0],
    [98.0, 62.0],
    [88.0, 70.0],
    [87.0, 83.0],
    [90.0, 93.0],
    [102.0, 98.0],
    [112.0, 95.0],
];

/// The narrower approach meets the settlement's wider lane at the gate.
const APPROACH: [[f64; 2]; 9] = [
    [81.0, -9.0],
    [83.0, 0.0],
    [85.0, 8.0],
    [88.0, 18.0],
    [92.0, 30.0],
    [97.0, 41.0],
    [103.0, 52.0],
    [108.0, 59.0],
    [99.0, 61.7],
];
const INNER: [[f64; 2]; 6] = [[97.0, 62.8], [88.0, 70.0], [87.0, 83.0], [90.0, 93.0], [102.0, 98.0], [112.0, 95.0]];

/// The short lane on the other side of the well, joining the main lane at both ends.
const LOOP: [[f64; 2]; 7] =
    [[98.0, 62.0], [104.0, 66.0], [108.0, 72.0], [113.0, 78.0], [114.0, 84.0], [114.0, 89.0], [112.0, 95.0]];
const WELL_APRON: [[f64; 2]; 2] = [[99.0, 81.9], [114.0, 80.0]];

/// The road owns its centre and edge. Begin the dirt just beyond its edge, with a short ground verge.
fn entrance_geometry() -> (DVec2, DVec2) {
    let coast = REGIONS.iter().find(|region| region.name() == "momiji-coast").expect("the coast is listed");
    let strips = coast.levelled();
    let road = curve(&strips.first().expect("the coast has a road").course);
    // Select a clear stretch of the road, between its roadside poles.
    let toward = DVec2::new(80.0, -12.0);
    let (_, index) = nearest(&road, toward);
    let (centre, direction) = road[index];
    let side = if (toward - centre).dot(direction.perp()) >= 0.0 { 1.0 } else { -1.0 };
    let outward = direction.perp() * side;
    (centre + outward * 3.8, outward)
}

fn approach() -> Vec<[f64; 2]> {
    let (start, outward) = entrance_geometry();
    [start.to_array(), (start + outward * 8.0).to_array()]
        .into_iter()
        .chain(APPROACH)
        .chain([INNER[0], INNER[1]])
        .collect()
}

fn terrace() -> Pad {
    Pad { centre: [100.0, 85.0], half_size_m: [30.0, 25.0], height_m: 29.625, slope: [0.0, 0.055], shoulder_m: 45.0 }
}

/// A later ribbon meets the earlier ribbons' exact outlines; shared dirt never draws twice.
fn append_without_overlap(owned: &mut Vec<[(DVec2, DVec2); 3]>, incoming: Vec<[(DVec2, DVec2); 3]>) {
    let existing = owned.clone();
    for triangle in incoming {
        let mut pieces = vec![triangle.to_vec()];
        for owner in &existing {
            let corners = owner.map(|(p, _)| p);
            let turn = (corners[1] - corners[0]).perp_dot(corners[2] - corners[0]).signum();
            if turn == 0.0 {
                continue;
            }
            let low = corners[0].min(corners[1]).min(corners[2]);
            let high = corners[0].max(corners[1]).max(corners[2]);
            let mut remaining = Vec::new();
            for polygon in pieces {
                let (p_low, p_high) = polygon
                    .iter()
                    .fold((DVec2::INFINITY, DVec2::NEG_INFINITY), |(a, b), (p, _)| (a.min(*p), b.max(*p)));
                if p_low.cmpgt(high).any() || p_high.cmplt(low).any() {
                    remaining.push(polygon);
                    continue;
                }
                let mut inside = polygon;
                for edge in 0..3 {
                    let a = corners[edge];
                    let b = corners[(edge + 1) % 3];
                    let mut next = Vec::new();
                    let mut outside = Vec::new();
                    for n in 0..inside.len() {
                        let (p, uv) = inside[n];
                        let (q, vq) = inside[(n + 1) % inside.len()];
                        let sp = turn * (b - a).perp_dot(p - a);
                        let sq = turn * (b - a).perp_dot(q - a);
                        if sp >= 0.0 {
                            next.push((p, uv));
                        } else {
                            outside.push((p, uv));
                        }
                        if (sp >= 0.0) != (sq >= 0.0) {
                            let t = sp / (sp - sq);
                            let crossing = (p.lerp(q, t), uv.lerp(vq, t));
                            next.push(crossing);
                            outside.push(crossing);
                        }
                    }
                    if outside.len() >= 3 {
                        remaining.push(outside);
                    }
                    inside = next;
                    if inside.len() < 3 {
                        break;
                    }
                }
            }
            pieces = remaining;
            if pieces.is_empty() {
                break;
            }
        }
        for polygon in pieces {
            for n in 1..polygon.len().saturating_sub(1) {
                let result = [polygon[0], polygon[n], polygon[n + 1]];
                let [a, b, c] = result.map(|(p, _)| p);
                if (b - a).perp_dot(c - a).abs() > 1e-8 {
                    owned.push(result);
                }
            }
        }
    }
}

pub struct MomijiHamlet;

impl Region for MomijiHamlet {
    fn name(&self) -> &'static str {
        "momiji-hamlet"
    }

    fn levelled(&self) -> Vec<Strip> {
        let (start, outward) = entrance_geometry();
        let course: Vec<_> = [start.to_array(), (start + outward * 8.0).to_array()]
            .into_iter()
            .chain(LANE[..7].iter().copied())
            .collect();
        let line = curve(&course);
        let (end, end_direction) = line[line.len() - 1];
        let terrace = terrace();
        let slope = DVec2::from_array(terrace.slope);
        // Height and outward grade sampled from the coast road at this entrance after its strip is levelled.
        let profile = Profile {
            heights: [16.8258951518, terrace.height_m + (end - DVec2::from_array(terrace.centre)).dot(slope)],
            grades: [0.0240236757, end_direction.dot(slope)],
        };
        vec![Strip { course, half_width_m: 4.0, shoulder_m: 10.0, smoothing_m: 8.0, profile: Some(profile) }]
    }

    fn pads(&self) -> Vec<Pad> {
        vec![terrace()]
    }

    fn scatter_exclusions(&self) -> Vec<Exclusion> {
        let mut exclusions = Vec::new();
        // Clear the settlement itself as well as its lanes and buildings, leaving the surrounding woodland.
        // This capsule approximates the original 62 by 66 m oval clearing.
        exclusions.push(Exclusion::corridor(
            &[[99.0, 83.0], [99.0, 87.0]],
            31.0,
            &[ScatterKind::Tree, ScatterKind::Bush, ScatterKind::Grass],
        ));
        let approach = approach();
        for path in [&approach[..], &LANE[..], &LOOP[..], &WELL_APRON[..]] {
            exclusions.push(Exclusion::corridor(path, 8.0, &[ScatterKind::Tree]));
            exclusions.push(Exclusion::corridor(path, 4.5, &[ScatterKind::Bush]));
            exclusions.push(Exclusion::corridor(path, 3.2, &[ScatterKind::Grass]));
        }
        for (_, x, y, _) in scenery::BUILT {
            let footprint = [[x - 1.0, y], [x + 1.0, y]];
            exclusions.push(Exclusion::corridor(&footprint, 8.0, &[ScatterKind::Tree]));
            exclusions.push(Exclusion::corridor(&footprint, 6.0, &[ScatterKind::Bush, ScatterKind::Grass]));
        }
        exclusions
    }

    fn overlays(&self) -> Vec<Overlay> {
        let mut triangles = ribbon(&approach(), 2.6, 8.0);
        for (course, width) in [(&INNER[..], 3.8), (&LOOP[..], 3.8), (&WELL_APRON[..], 1.5)] {
            let branch = ribbon(course, width, 8.0);
            append_without_overlap(&mut triangles, branch);
        }
        for triangle in &mut triangles {
            for (point, uv) in triangle {
                *uv = *point / 8.0;
            }
        }
        vec![Overlay { name: "lanes".into(), texture: "hamlet-path".into(), triangles }]
    }

    fn scenery(&self, _land: &Land) -> Scenery {
        scenery::make()
    }

    fn fastens_to(&self) -> Vec<&'static str> {
        Vec::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::world::ground::Ground;
    use crate::world::surface::{cut, weights};

    #[test]
    fn clearing_removes_native_vegetation_without_clearing_the_surrounding_forest() {
        let ground = Ground::page(64, 2.0, |_, _| 0.0);
        let exclusions = MomijiHamlet.scatter_exclusions();
        let land = Land { ground: &ground, low: DVec2::ZERO, high: DVec2::splat(200.0), exclusions: &exclusions };
        for kind in [ScatterKind::Tree, ScatterKind::Bush, ScatterKind::Grass] {
            for [x, y] in
                [[99.0, 85.0], [69.0, 85.0], [129.0, 85.0], [99.0, 53.0], [99.0, 117.0], [78.0, 65.0], [120.0, 105.0]]
            {
                assert!(!land.allows_scatter(DVec2::new(x, y), kind));
            }
            assert!(land.allows_scatter(DVec2::new(160.0, 145.0), kind));
        }
    }

    #[test]
    fn lanes_join_without_overlapping_and_cover_each_route() {
        let overlay = MomijiHamlet.overlays().pop().unwrap();
        let triangles: Vec<_> = overlay.triangles.iter().map(|triangle| triangle.map(|(p, _)| p)).collect();
        for (index, triangle) in triangles.iter().enumerate() {
            for other in &triangles[index + 1..] {
                assert!(cut(triangle.to_vec(), *other).is_empty(), "lane triangles overlap");
            }
        }
        let lies_on = |point: DVec2, course: &[[f64; 2]], width| {
            ribbon(course, width, 8.0)
                .iter()
                .any(|triangle| weights(triangle.map(|(p, _)| p), point).is_some_and(|w| w.min_element() >= -1e-7))
        };
        assert!(lies_on(DVec2::from_array(LOOP[0]), &approach(), 2.6));
        assert!(lies_on(DVec2::from_array(LOOP[LOOP.len() - 1]), &INNER, 3.8));
        assert!(lies_on(DVec2::from_array(WELL_APRON[1]), &LOOP, 3.8));
        for course in [approach(), INNER.to_vec(), LOOP.to_vec(), WELL_APRON.to_vec()] {
            for (point, _) in curve(&course) {
                assert!(
                    triangles
                        .iter()
                        .any(|triangle| { weights(*triangle, point).is_some_and(|w| w.min_element() >= -1e-7) }),
                    "lane has a gap at {point}"
                );
            }
        }
    }
}
