//! Published source vegetation and stones, after the original region and garden clearances.

use std::collections::BTreeMap;

use glam::DVec2;
use serde::Deserialize;

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
    let [west, south, east, north] = source.rectangle_m;
    assert!(
        [west, south, east, north].iter().all(|v| v.is_finite()) && west < east && south < north,
        "invalid source vegetation rectangle"
    );
    let mut placements = Vec::new();
    for (name, instances) in source.groups {
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
        for [x, y, z, yaw, scale] in instances {
            let at = DVec2::new(x, y);
            assert!(
                at.cmpge(DVec2::new(west, south)).all() && at.cmplt(DVec2::new(east, north)).all(),
                "source vegetation outside its declared region: {at}"
            );
            if at.cmplt(land.low).any() || at.cmpge(land.high).any() {
                continue;
            }
            let stored = land.placement_at(at).as_vec2().as_dvec2();
            assert!(land.slope(stored).is_finite(), "invalid source vegetation surface at {stored}");
            let _seat = land.height(stored).expect("published source vegetation stands on exported terrain");
            let placement = Placement {
                model,
                at,
                yaw: yaw.to_radians(),
                scale,
                origin_offset_m: 0.0,
                origin_height_m: Some(z),
                afar,
            };
            if let Some(kind) = kind {
                assert!(
                    land.allows_candidate(kind, &placement),
                    "published source {name} contradicts original clearing at {at}"
                );
            }
            placements.push(placement);
        }
    }
    placements
}
