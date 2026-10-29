//! A region that is only data: models standing at exact map positions, read from its `placements.json`.
//!
//! The file holds `groups`, each a model by its folder under `assets/`, whether middle tiles show it too (`afar`),
//! and its `instances`, each `[x, y, z, yaw, scale]`: the foot on the map in metres, its height above the world's
//! zero, its turn counter-clockwise seen from above in degrees, and its scale. A group `on_ground` stands each model on
//! the ground under it instead, its height then an offset above that ground. Models past the ground stand in tiles
//! that hold only scenery.

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
    /// Whether each model stands on the ground under it, its height then an offset above the ground.
    #[serde(default)]
    on_ground: bool,
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
        let placements = self.placements().filter(|p| inside(land, p.at)).collect();
        Scenery { placements, ..Scenery::default() }
    }

    fn beyond(&self, land: &Land) -> Vec<Placement> {
        self.placements().filter(|p| !inside(land, p.at)).collect()
    }
}

fn inside(land: &Land, at: DVec2) -> bool {
    at.cmpge(land.low).all() && at.cmplt(land.high).all()
}

impl Placed {
    fn placements(&self) -> impl Iterator<Item = Placement> {
        let file: Placements<'static> = serde_json::from_str(self.placements)
            .unwrap_or_else(|error| panic!("{}: invalid placements.json: {error}", self.name));
        let name = self.name;
        file.groups.into_iter().flat_map(move |group| {
            let (model, afar, on_ground) = (group.model, group.afar, group.on_ground);
            group.instances.into_iter().map(move |[x, y, z, yaw, scale]| {
                assert!(
                    [x, y, z, yaw, scale].iter().all(|v| v.is_finite()) && scale > 0.0,
                    "{name}: invalid instance of {model}"
                );
                Placement {
                    model,
                    at: DVec2::new(x, y),
                    yaw: yaw.to_radians(),
                    scale,
                    origin_offset_m: if on_ground { z } else { 0.0 },
                    origin_height_m: (!on_ground).then_some(z),
                    afar,
                }
            })
        })
    }
}
