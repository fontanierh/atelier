//! Sunset Pier: its pieces, standing from `placements.json` as a data-only region's do, and the walking surface of
//! the path in from the coast road, which runs over the ground: the source's own triangles (`path-source.json`), the
//! paving and its joints, each drawing the pier's concrete map tinted as its source face is.

use super::Region;
use crate::world::authored::{AuthoredSurface, Triangle};
use crate::world::levelling::Strip;
use crate::world::overlay::Overlay;
use crate::world::placed::Placed;
use crate::world::raised::SurfacePaint;
use crate::world::scenery::{Land, Placement, Scenery};

/// The pier's pieces: the deck, pilings, features and furniture, and the path's skirts, edges and railings.
const PIECES: Placed = Placed { name: "skatepark", placements: include_str!("placements.json") };

/// The path's walking surfaces by their name in `path-source.json`.
const SURFACES: [&str; 2] = ["path", "path-joint"];

pub struct SkatePark;

impl Region for SkatePark {
    fn name(&self) -> &'static str {
        "skatepark"
    }

    /// The path keeps its source surface over the ground rather than levelling it.
    fn levelled(&self) -> Vec<Strip> {
        Vec::new()
    }

    fn overlays(&self) -> Vec<Overlay> {
        Vec::new()
    }

    fn authored_surfaces(&self) -> Vec<AuthoredSurface> {
        #[derive(serde::Deserialize)]
        struct Source {
            surfaces: Vec<Surface>,
        }
        #[derive(serde::Deserialize)]
        struct Surface {
            name: String,
            tint: [f64; 3],
            triangles: Vec<Triangle>,
        }
        let source: Source =
            serde_json::from_str(include_str!("path-source.json")).expect("the committed pier path is valid JSON");
        source
            .surfaces
            .into_iter()
            .map(|surface| AuthoredSurface {
                name: SURFACES
                    .into_iter()
                    .find(|name| *name == surface.name)
                    .unwrap_or_else(|| panic!("unknown pier path surface {}", surface.name)),
                texture: Some("skatepark-concrete-albedo"),
                tint: surface.tint,
                paint: Some(SurfacePaint {
                    haze_start_m: 30.0,
                    haze_length_m: 9000.0,
                    haze_colour: [0.0932, 0.2301, 0.5328],
                }),
                vertex_paint: None,
                triangles: surface.triangles,
            })
            .collect()
    }

    fn skate(&self) -> hakuba_world_skate_schema::Metadata {
        PIECES.skate()
    }

    fn scenery(&self, land: &Land) -> Scenery {
        PIECES.scenery(land)
    }

    fn beyond(&self, land: &Land) -> Vec<Placement> {
        PIECES.beyond(land)
    }
}
