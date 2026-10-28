//! The village's source-authored structures and landscape.

mod landscape;
mod placements;
mod residents;

use glam::DVec2;

use super::Region;
use crate::world::actors::Actor;
use crate::world::authored::{AuthoredSurface, VertexPaint};
use crate::world::levelling::Strip;
use crate::world::overlay::Overlay;
use crate::world::published;
use crate::world::scenery::{Land, Placement, Scenery};

pub struct MomijiVillage;

impl Region for MomijiVillage {
    fn name(&self) -> &'static str {
        "momiji-village"
    }

    fn levelled(&self) -> Vec<Strip> {
        Vec::new()
    }

    fn overlays(&self) -> Vec<Overlay> {
        Vec::new()
    }

    fn authored_surfaces(&self) -> Vec<AuthoredSurface> {
        vec![AuthoredSurface {
            name: "ground",
            texture: None,
            tint: [1.0; 3],
            paint: None,
            vertex_paint: Some(VertexPaint {
                fill: 0.06,
                glow: 0.8,
                glow_min: [0.8, 0.35, 0.0],
                glow_max: [1.0, 0.72, 0.30],
                haze_start_m: 30.0,
                haze_length_m: 9000.0,
                haze_colour: [0.0932, 0.2301, 0.5328],
            }),
            triangles: serde_json::from_str(include_str!("ground-triangles.json"))
                .expect("village ground triangles are valid JSON"),
        }]
    }

    fn actors(&self) -> Vec<Actor> {
        residents::residents()
    }

    fn scenery(&self, land: &Land) -> Scenery {
        let placements = placements::STRUCTURES
            .into_iter()
            .map(|(model, [x, y, z], yaw, scale)| Placement {
                model,
                at: DVec2::new(x, y),
                yaw: yaw.to_radians(),
                scale,
                origin_offset_m: 0.0,
                origin_height_m: Some(z),
                afar: true,
            })
            .chain(landscape::LANDSCAPE.into_iter().map(|(model, [x, y, z])| Placement {
                model,
                at: DVec2::new(x, y),
                yaw: 0.0,
                scale: 1.0,
                origin_offset_m: 0.0,
                origin_height_m: Some(z),
                afar: true,
            }))
            .chain(published::plants(include_str!("source-vegetation.json"), land))
            .collect();
        Scenery { placements, ..Default::default() }
    }
}
