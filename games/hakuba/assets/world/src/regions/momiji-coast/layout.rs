//! Momiji coast: the coastal road, from west to east across the region, the plants on the slopes around it
//! (`planting.rs`) and what stands along it (`roadside.rs`).

mod planting;
mod roadside;

use super::Region;
use crate::world::authored::AuthoredSurface;
use crate::world::levelling::Strip;
use crate::world::overlay::Overlay;
use crate::world::raised::SurfacePaint;
use crate::world::scenery::{Land, Scenery};

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
        let mut scenery = Scenery { placements: planting::plants(land), ..Scenery::default() };
        roadside::add(&mut scenery, land);
        scenery
    }
}
