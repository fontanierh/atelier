//! A region that is only data: models standing at exact map positions, read from its `placements.json`.
//!
//! The file holds `groups`, each a model by its folder under `assets/`, whether middle tiles show it too (`afar`),
//! and its `instances`, each `[x, y, z, yaw, scale]`: the foot on the map in metres, its height above the world's
//! zero, its turn counter-clockwise seen from above in degrees, and its scale.

use glam::DVec2;
use serde::Deserialize;

use super::regions::Region;
use crate::world::levelling::Strip;
use crate::world::overlay::Overlay;
use crate::world::scenery::{Land, Placement, Scenery};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Placements<'a> {
    #[serde(borrow)]
    groups: Vec<Group<'a>>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Group<'a> {
    model: &'a str,
    afar: bool,
    instances: Vec<[f64; 5]>,
}

/// A data-only region: its folder name and its `placements.json`.
pub struct Placed {
    pub name: &'static str,
    pub placements: &'static str,
}

impl Region for Placed {
    fn name(&self) -> &'static str {
        self.name
    }

    fn levelled(&self) -> Vec<Strip> {
        Vec::new()
    }

    fn overlays(&self) -> Vec<Overlay> {
        Vec::new()
    }

    fn scenery(&self, land: &Land) -> Scenery {
        let file: Placements<'static> = serde_json::from_str(self.placements)
            .unwrap_or_else(|error| panic!("{}: invalid placements.json: {error}", self.name));
        let mut placements = Vec::new();
        for group in file.groups {
            for [x, y, z, yaw, scale] in group.instances {
                assert!(
                    [x, y, z, yaw, scale].iter().all(|v| v.is_finite()) && scale > 0.0,
                    "{}: invalid instance of {}",
                    self.name,
                    group.model
                );
                let at = DVec2::new(x, y);
                if at.cmplt(land.low).any() || at.cmpge(land.high).any() {
                    continue;
                }
                placements.push(Placement {
                    model: group.model,
                    at,
                    yaw: yaw.to_radians(),
                    scale,
                    origin_offset_m: 0.0,
                    origin_height_m: Some(z),
                    afar: group.afar,
                });
            }
        }
        Scenery { placements, ..Scenery::default() }
    }
}
