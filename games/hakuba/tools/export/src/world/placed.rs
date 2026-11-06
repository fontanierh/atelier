//! A region that is only data: models standing at exact map positions, read from its `placements.json`.
//!
//! The file holds `groups`, each a model by its folder under `assets/`, whether middle tiles show it too (`afar`),
//! and its `instances`, each `[x, y, z, yaw, scale]`: the foot on the map in metres, its height above the world's
//! zero, its turn counter-clockwise seen from above in degrees, and its scale. A group `on_ground` stands each model on
//! the ground under it instead, its height then an offset above that ground. Models past the ground stand in tiles
//! that hold only scenery.
//!
//! A group MAY name a `thinning`: the groups that name the same `set` are thinned together, keeping only instances at
//! least `apart_m` from every other kept one, in an order fixed by their positions, and growing each kept one by
//! `grow`. The source keeps every instance it was authored with, and the density is the region's own choice.

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
    #[serde(default, borrow)]
    thinning: Option<Thinning<'a>>,
}

/// Groups thinned together: no two kept instances nearer than `apart_m`, each kept one grown by `grow`.
#[derive(Deserialize, Clone, Copy, PartialEq)]
#[serde(deny_unknown_fields)]
struct Thinning<'a> {
    set: &'a str,
    apart_m: f64,
    grow: f64,
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
        let kept = thinned(name, &file.groups);
        file.groups.into_iter().enumerate().flat_map(move |(g, group)| {
            let (model, afar, on_ground) = (group.model, group.afar, group.on_ground);
            let grow = group.thinning.map_or(1.0, |t| t.grow);
            let kept = kept[g].clone();
            group.instances.into_iter().zip(kept).filter(|(_, keep)| *keep).map(move |([x, y, z, yaw, scale], _)| {
                assert!(
                    [x, y, z, yaw, scale].iter().all(|v| v.is_finite()) && scale > 0.0,
                    "{name}: invalid instance of {model}"
                );
                Placement {
                    model,
                    at: DVec2::new(x, y),
                    yaw: yaw.to_radians(),
                    scale: scale * grow,
                    origin_offset_m: if on_ground { z } else { 0.0 },
                    origin_height_m: (!on_ground).then_some(z),
                    afar,
                }
            })
        })
    }
}

/// Which instances of each group stay: every one of a group without thinning, and of each thinned set those at
/// least its `apart_m` from every one kept before them, taken in an order fixed by their positions alone.
fn thinned(name: &str, groups: &[Group]) -> Vec<Vec<bool>> {
    let mut kept: Vec<Vec<bool>> = groups.iter().map(|g| vec![true; g.instances.len()]).collect();
    let mut sets: Vec<Thinning> = Vec::new();
    for thinning in groups.iter().filter_map(|g| g.thinning) {
        match sets.iter().find(|s| s.set == thinning.set) {
            Some(other) => assert!(*other == thinning, "{name}: thinning set {} differs between groups", thinning.set),
            None => {
                assert!(thinning.apart_m > 0.0 && thinning.grow > 0.0, "{name}: invalid thinning {}", thinning.set);
                sets.push(thinning)
            }
        }
    }
    for set in sets {
        let mut order: Vec<(u64, usize, usize)> = Vec::new();
        for (g, group) in groups.iter().enumerate().filter(|(_, g)| g.thinning.is_some_and(|t| t.set == set.set)) {
            for (i, [x, y, ..]) in group.instances.iter().enumerate() {
                order.push((mix(x.to_bits() ^ mix(y.to_bits())), g, i));
            }
        }
        order.sort_unstable();
        let cell = set.apart_m;
        let mut grid: std::collections::HashMap<(i64, i64), Vec<DVec2>> = std::collections::HashMap::new();
        for (_, g, i) in order {
            let [x, y, ..] = groups[g].instances[i];
            let at = DVec2::new(x, y);
            let (cx, cy) = ((x / cell).floor() as i64, (y / cell).floor() as i64);
            let near = (-1..=1).any(|dx| {
                (-1..=1).any(|dy| {
                    grid.get(&(cx + dx, cy + dy)).is_some_and(|v| v.iter().any(|o| o.distance(at) < set.apart_m))
                })
            });
            if near {
                kept[g][i] = false;
            } else {
                grid.entry((cx, cy)).or_default().push(at);
            }
        }
    }
    kept
}

/// A 64-bit finaliser (SplitMix64's), to order positions without favouring any part of the map.
fn mix(mut z: u64) -> u64 {
    z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
    z ^ (z >> 31)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn thinning_keeps_kept_instances_apart_and_grows_them() {
        let source = r#"{"groups":[
            {"model":"a","afar":true,"instances":[[0,0,0,0,1],[3,0,0,0,1],[20,0,0,0,1]],"thinning":{"set":"t","apart_m":10,"grow":2}},
            {"model":"b","afar":true,"instances":[[0,4,0,0,1],[40,0,0,0,1]],"thinning":{"set":"t","apart_m":10,"grow":2}},
            {"model":"c","afar":true,"instances":[[1,0,0,0,1]]}]}"#;
        let placed = Placed { name: "test", placements: source };
        let all: Vec<Placement> = placed.placements().collect();
        let thinned: Vec<&Placement> = all.iter().filter(|p| p.model != "c").collect();
        assert_eq!(thinned.len(), 3, "one of the three near the origin, and the two far ones");
        for (i, a) in thinned.iter().enumerate() {
            assert_eq!(a.scale, 2.0);
            for b in &thinned[i + 1..] {
                assert!(a.at.distance(b.at) >= 10.0);
            }
        }
        assert_eq!(all.iter().filter(|p| p.model == "c").map(|p| p.scale).collect::<Vec<_>>(), [1.0]);
    }
    /// A tree with an impostor shows in middle tiles too: past its full version it is one quad, and a tree gone at a
    /// tile's edge is a tree that changed shape.
    #[test]
    fn every_region_shows_its_impostor_trees_afar() {
        let regions = std::path::Path::new(crate::ASSETS).join("world/src/regions");
        let mut hidden = Vec::new();
        for region in std::fs::read_dir(&regions).unwrap() {
            let path = region.unwrap().path().join("placements.json");
            let Ok(text) = std::fs::read_to_string(&path) else { continue };
            let file: Placements = serde_json::from_str(&text).unwrap();
            for group in file.groups.iter().filter(|group| !group.afar) {
                let name = group.model.rsplit('/').next().unwrap();
                let export = std::path::Path::new(crate::ASSETS).join(group.model).join(format!("{name}.glb"));
                let Ok(glb) = crate::glb::Glb::read(&export) else { continue };
                if glb.extras("full").is_ok_and(|extras| extras.get("impostor").is_some()) {
                    hidden.push(format!("{} in {}", group.model, path.display()));
                }
            }
        }
        assert!(hidden.is_empty(), "impostor trees shown only near: {hidden:?}");
    }
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
