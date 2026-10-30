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
    #[serde(default)]
    skate: hakuba_world_skate_schema::Metadata,
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

    fn skate(&self) -> hakuba_world_skate_schema::Metadata {
        let file: Placements<'static> = serde_json::from_str(self.placements)
            .unwrap_or_else(|error| panic!("{}: invalid placements.json: {error}", self.name));
        file.skate
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn placed_skating_metadata_is_valid_and_keeps_whole_lines() {
        let source = r#"{"groups":[],"skate":{"rails":[{"id":"lip","points":[[0,1,0],[64,1,0],[128,1,0]],"closed":false,"kind":"coping","surface":"metal"}]}}"#;
        let placed = Placed { name: "test", placements: source };
        let metadata = placed.skate();
        metadata.validate().unwrap();
        assert_eq!(metadata.rails[0].points.len(), 3);
        assert_eq!(metadata.rails[0].points[2], [128., 1., 0.]);
    }
    #[test]
    fn every_region_exports_valid_nonconflicting_skating_metadata() {
        let mut materials = std::collections::BTreeMap::new();
        for region in crate::world::regions::REGIONS {
            let metadata = region.skate();
            metadata.validate().unwrap();
            for material in metadata.materials {
                if let Some(previous) = materials.insert(material.material, material.surface) {
                    assert_eq!(previous, material.surface)
                }
            }
        }
    }
}
