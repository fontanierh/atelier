//! The Hidamari Hippodrome on the slope north of the city: its course, rails and buildings stand as placed models
//! (`placements.json`), and the lane from the city street up to its platform is ground, levelled to a ramp and laid with
//! the course's dirt.

use glam::DVec2;

use super::Region;
use crate::world::levelling::{Profile, Strip};
use crate::world::overlay::Overlay;
use crate::world::placed::Placed;
use crate::world::scenery::{Land, Placement, Scenery};

/// The platform's grass top, which owns the lane's north edge at `PLATFORM_EDGE_Y`.
const PLATFORM_TOP_M: f64 = 48.26;
const PLATFORM_EDGE_Y: f64 = 443.0;
/// The seam's declared clearance: the lane meets the platform's edge this far under its top, and the ground it levels
/// past the edge stays this far under the platform.
const PLATFORM_CLEARANCE_M: f64 = 0.01;
/// The lane's centre line, from the street's north end (x 560, y 343) to `LANDING_M` short of the platform's edge.
/// The levelled ground stays flat for the strip's half width past the line's end, so it is flat across the 2 m grid
/// cell the edge lies in, and meets the edge exactly.
const LANDING_M: f64 = 2.0;
const LANE: [[f64; 2]; 2] = [[560.0, 343.0], [560.0, PLATFORM_EDGE_Y - LANDING_M]];
/// Its heights at either end: the street's, and the seam's under the platform's top.
const LANE_HEIGHTS_M: [f64; 2] = [36.0, PLATFORM_TOP_M - PLATFORM_CLEARANCE_M];
const LANE_HALF_WIDTH_M: f64 = 3.0;
/// The ground levelled either side of the centre line: a grid step wider than the lane, so the dirt lies on level
/// ground to its edges, and then eased into the hillside over the shoulder.
const LEVEL_HALF_WIDTH_M: f64 = 5.0;
const LANE_SHOULDER_M: f64 = 6.0;
/// The dirt starts this far inside the strip's south end, where the ground on the 2 m grid bends into the street.
const DIRT_INSET_M: f64 = 2.0;
/// One repeat of the dirt texture every this many metres.
const UV_METRES: f64 = 4.0;

const PLACED: Placed = Placed { name: "hippodrome", placements: include_str!("placements.json") };

pub struct Hippodrome;

impl Region for Hippodrome {
    fn name(&self) -> &'static str {
        PLACED.name
    }

    /// The lane: a ramp level at either end, as the street and the platform it joins are, so the ground past its ends
    /// stays level too, under the platform by the seam's clearance.
    fn levelled(&self) -> Vec<Strip> {
        vec![Strip {
            course: LANE.to_vec(),
            half_width_m: LEVEL_HALF_WIDTH_M,
            shoulder_m: LANE_SHOULDER_M,
            smoothing_m: 0.0,
            profile: Some(Profile { heights: LANE_HEIGHTS_M, grades: [0.0; 2] }),
        }]
    }

    /// The lane's dirt, on its levelled ground.
    fn overlays(&self) -> Vec<Overlay> {
        let [[x, south], _] = LANE;
        let (south, north) = (south + DIRT_INSET_M, PLATFORM_EDGE_Y);
        let corner = |side: f64, y: f64| {
            let at = DVec2::new(x + side * LANE_HALF_WIDTH_M, y);
            (at, DVec2::new((side + 1.0) * LANE_HALF_WIDTH_M, y) / UV_METRES)
        };
        let [a, b, c, d] = [corner(-1.0, south), corner(1.0, south), corner(1.0, north), corner(-1.0, north)];
        vec![Overlay {
            name: "lane".into(),
            texture: "hippodrome-t-hd-dirt".into(),
            triangles: vec![[a, b, c], [a, c, d]],
        }]
    }

    fn scenery(&self, land: &Land) -> Scenery {
        PLACED.scenery(land)
    }

    fn beyond(&self, land: &Land) -> Vec<Placement> {
        PLACED.beyond(land)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::world::ground::Ground;

    /// The ground levelled for the lane over a hillside rising north with ridges across it, under the platform's top
    /// as the platform's source keeps it.
    fn levelled() -> Ground {
        let mut ground = Ground::page(300, 2.0, |i, j| 20.0 + j as f32 * 2.0 * 0.055 + (i as f32 * 0.7).sin());
        for strip in Hippodrome.levelled() {
            strip.level(&mut ground).unwrap();
        }
        ground
    }

    #[test]
    fn platform_top_is_where_its_grass_stands() {
        // The placed foot of `props/hippodrome-ground`, whose grass lies 1 cm under its origin.
        let placements: serde_json::Value = serde_json::from_str(PLACED.placements).unwrap();
        let groups = placements["groups"].as_array().unwrap();
        let ground = groups.iter().find(|group| group["model"] == "props/hippodrome-ground").unwrap();
        assert!((ground["instances"][0][2].as_f64().unwrap() - 0.01 - PLATFORM_TOP_M).abs() < 1e-9);
    }

    /// Along the whole entrance, the lane meets the platform's edge at its top less the declared clearance, and past
    /// the edge the levelled ground stays under the platform by at least that clearance.
    #[test]
    fn lane_meets_the_platform_edge_and_stays_under_it() {
        let ground = levelled();
        let at = |x: f64, y: f64| ground.height(DVec2::new(x, y)).unwrap();
        let x = LANE[0][0];
        let seam = PLATFORM_TOP_M - PLATFORM_CLEARANCE_M;
        for k in -40..=40 {
            let across = x + k as f64 * LEVEL_HALF_WIDTH_M / 40.0;
            let height = at(across, PLATFORM_EDGE_Y);
            if (across - x).abs() <= LANE_HALF_WIDTH_M {
                assert!((height - seam).abs() < 1e-9, "the lane meets the platform at {height} m at x {across}");
            }
            assert!(height <= seam + 1e-9, "the ground at the edge is {height} m at x {across}");
        }
        for dx in -15..=15 {
            for dy in 0..=40 {
                let (across, along) = (x + dx as f64, PLATFORM_EDGE_Y + dy as f64 * 0.5);
                let height = at(across, along);
                assert!(height <= seam + 1e-9, "the ground under the platform is {height} m at {across}, {along}");
            }
        }
    }

    /// The lane starts level with the street at its south end.
    #[test]
    fn lane_meets_the_street() {
        let ground = levelled();
        let [[x, south], _] = LANE;
        // Within a centimetre: the 2 m grid samples the eased end between its points.
        let height = ground.height(DVec2::new(x, south)).unwrap();
        assert!((height - LANE_HEIGHTS_M[0]).abs() < 0.01, "the lane is {height} m at the street");
    }
}
