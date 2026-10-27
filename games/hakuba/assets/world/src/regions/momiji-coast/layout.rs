//! Momiji coast: the coastal road, from west to east across the region, the plants on the slopes around it
//! (`planting.rs`) and what stands along it (`roadside.rs`).

mod planting;
mod roadside;

use glam::DVec2;

use super::Region;
use crate::world::authored::AuthoredSurface;
use crate::world::curve::curve;
use crate::world::levelling::Strip;
use crate::world::openings::Domain;
use crate::world::overlay::Overlay;
use crate::world::raised::SurfacePaint;
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

pub struct MomijiCoast;

impl Region for MomijiCoast {
    fn name(&self) -> &'static str {
        "momiji-coast"
    }

    /// The ground under the road and its verges, levelled across the road and smooth along it, so the road and the
    /// ground beside it run without a kink.
    fn levelled(&self) -> Vec<Strip> {
        Vec::new()
    }

    fn scatter_exclusions(&self) -> Vec<Exclusion> {
        vec![
            Exclusion::corridor(&ROAD, 8.5, &[ScatterKind::Tree]),
            Exclusion::corridor(&ROAD, 4.3, &[ScatterKind::Bush]),
            Exclusion::corridor(&ROAD, 3.2, &[ScatterKind::Grass]),
        ]
    }

    fn path_domains(&self) -> Vec<Domain> {
        vec![Domain { id: roadside::RAIL_PATH, from: 0.0, to: (curve(&ROAD).len() - 1) as f64, step: 1.0 }]
    }

    /// This region's road retains its source-authored three-dimensional triangles.
    fn overlays(&self) -> Vec<Overlay> {
        Vec::new()
    }

    fn authored_surfaces(&self) -> Vec<AuthoredSurface> {
        #[derive(serde::Deserialize)]
        struct RoadSource {
            triangles: Vec<crate::world::authored::Triangle>,
        }
        let mut source: RoadSource =
            serde_json::from_str(include_str!("road-source.json")).expect("the committed source road is valid JSON");
        // The FBX source UV convention is the inverse of glTF's vertical axis.
        for triangle in &mut source.triangles {
            for uv in &mut triangle.uv {
                uv[1] = 1.0 - uv[1];
            }
        }
        vec![AuthoredSurface {
            name: "road",
            texture: "road",
            tint: [0.34, 0.33, 0.33],
            paint: Some(SurfacePaint {
                haze_start_m: 30.0,
                haze_length_m: 9000.0,
                haze_colour: [0.0932, 0.2301, 0.5328],
            }),
            triangles: source.triangles,
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
