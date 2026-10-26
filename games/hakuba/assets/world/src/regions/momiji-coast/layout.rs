//! Momiji coast: the coastal road, from west to east across the region, the plants on the slopes around it
//! (`planting.rs`) and what stands along it (`roadside.rs`).

mod planting;
mod roadside;

use glam::DVec2;

use super::Region;
use crate::world::curve::curve;
use crate::world::levelling::Strip;
use crate::world::overlay::Overlay;
use crate::world::ribbon::ribbon;
use crate::world::scenery::{Exclusion, Land, ScatterKind, Scenery};

/// The points the road's centre line passes through, from its west end to its east end.
const ROAD: [[f64; 2]; 11] = [
    [-295.0, -95.0],
    [-230.0, -100.0],
    [-170.0, -85.0],
    [-110.0, -70.0],
    [-50.0, -70.0],
    [10.0, -45.0],
    [70.0, -30.0],
    [130.0, -25.0],
    [190.0, -5.0],
    [240.0, 25.0],
    [295.0, 60.0],
];

const ROAD_WIDTH_M: f64 = 5.2;

/// How far the ground is levelled either side of the road's centre: the road and a verge of 1.4 m, so the 2 m ground
/// triangles under the road's edges lie on level ground, or barely reach into the shoulder.
const LEVEL_HALF_WIDTH_M: f64 = 4.0;

/// How wide the ground eases from the levelled road back into the banks it is cut into. At this width the banks get no
/// steeper than they are.
const SHOULDER_M: f64 = 10.0;

/// How far along the road its height is smoothed, as the spread of the bell curve each height is averaged over.
const ROAD_SMOOTHING_M: f64 = 8.0;

/// How often the road's texture repeats along it.
const ROAD_TEXTURE_M: f64 = 8.0;

/// The road's texture: its width spans the road.
const ROAD_TEXTURE: &str = "road";

pub struct MomijiCoast;

impl Region for MomijiCoast {
    fn name(&self) -> &'static str {
        "momiji-coast"
    }

    /// The ground under the road and its verges, levelled across the road and smooth along it, so the road and the
    /// ground beside it run without a kink.
    fn levelled(&self) -> Vec<Strip> {
        vec![Strip {
            course: ROAD.to_vec(),
            half_width_m: LEVEL_HALF_WIDTH_M,
            shoulder_m: SHOULDER_M,
            smoothing_m: ROAD_SMOOTHING_M,
            profile: None,
        }]
    }

    fn scatter_exclusions(&self) -> Vec<Exclusion> {
        vec![
            Exclusion::corridor(&ROAD, 8.5, &[ScatterKind::Tree]),
            Exclusion::corridor(&ROAD, 4.3, &[ScatterKind::Bush]),
            Exclusion::corridor(&ROAD, 3.2, &[ScatterKind::Grass]),
        ]
    }

    /// The road, on its levelled strip.
    fn overlays(&self) -> Vec<Overlay> {
        vec![Overlay {
            name: "road".into(),
            texture: ROAD_TEXTURE.into(),
            triangles: ribbon(&ROAD, ROAD_WIDTH_M, ROAD_TEXTURE_M),
        }]
    }

    fn scenery(&self, land: &Land) -> Scenery {
        let road = curve(&ROAD);
        let mut scenery = Scenery { placements: planting::plants(land, &road), ..Scenery::default() };
        roadside::add(&mut scenery, land, &road);
        scenery
    }

    fn fastens_to(&self) -> Vec<&'static str> {
        vec![roadside::POLE]
    }
}

/// Which side of the road at `at`, going along `direction`, rises: 1 for its left, -1 for its right, judged from the
/// ground 12 m to each side.
fn uphill(land: &Land, at: DVec2, direction: DVec2) -> f64 {
    let side = |sign: f64| land.height(at + direction.perp() * 12.0 * sign).unwrap_or(f64::NEG_INFINITY);
    if side(1.0) >= side(-1.0) { 1.0 } else { -1.0 }
}
