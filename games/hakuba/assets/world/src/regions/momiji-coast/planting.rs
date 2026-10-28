//! Published source vegetation and stones, after the original region and garden clearances.

use std::collections::BTreeMap;

use serde::Deserialize;

use crate::world::published::{self, Group};
use crate::world::scenery::{Land, Placement, ScatterKind};

#[derive(Deserialize)]
struct Published {
    rectangle_m: [f64; 4],
    groups: BTreeMap<String, Vec<[f64; 5]>>,
}

/// Reuses the published final instances, excluding the separately authored garden dressing.
pub fn plants(land: &Land) -> Vec<Placement> {
    let source: Published = serde_json::from_str(include_str!("source-vegetation.json"))
        .expect("the committed source vegetation is valid JSON");
    let groups = source.groups.into_iter().map(|(name, instances)| {
        let (model, kind, afar) = match name.as_str() {
            "Tree_Pine_A" => ("plants/garden-pine-a", Some(ScatterKind::Tree), true),
            "Tree_Pine_B" => ("plants/garden-pine-b", Some(ScatterKind::Tree), true),
            "Tree_Maple_A" => ("plants/garden-maple-a", Some(ScatterKind::Tree), true),
            "Tree_Maple_B" => ("plants/garden-maple-b", Some(ScatterKind::Tree), true),
            "Tree_Cedar_A" => ("plants/coast-cedar-a", Some(ScatterKind::Tree), true),
            "Tree_Cedar_B" => ("plants/garden-cedar-b", Some(ScatterKind::Tree), true),
            "Tree_Broad_A" => ("plants/coast-broad-a", Some(ScatterKind::Tree), true),
            "Tree_Broad_B" => ("plants/coast-broad-b", Some(ScatterKind::Tree), true),
            "Tree_Ginkgo" => ("plants/coast-ginkgo", Some(ScatterKind::Tree), true),
            "Bush_Flower_A" => ("plants/coast-flower-a", Some(ScatterKind::Bush), true),
            "Bush_Flower_B" => ("plants/garden-flower-b", Some(ScatterKind::Bush), true),
            "Bush_Green_A" => ("plants/coast-green-a", Some(ScatterKind::Bush), true),
            "Bush_Green_B" => ("plants/garden-green-b", Some(ScatterKind::Bush), true),
            "Bush_Ochre_A" => ("plants/coast-ochre-a", Some(ScatterKind::Bush), true),
            "Bush_Ochre_B" => ("plants/coast-ochre-b", Some(ScatterKind::Bush), true),
            "Grass_A" => ("plants/coast-grass-a", Some(ScatterKind::Grass), false),
            "Grass_B" => ("plants/coast-grass-b", Some(ScatterKind::Grass), false),
            "Litter" => ("plants/coast-litter", None, false),
            "Rock_A" => ("props/coast-rock-a", None, true),
            "Rock_B" => ("props/garden-rock", None, true),
            "Rock_C" => ("props/coast-rock-c", None, true),
            _ => panic!("unknown source vegetation model {name}"),
        };
        Group { model, kind, afar, instances }
    });
    published::placements(source.rectangle_m, groups, land)
}
