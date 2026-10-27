//! Published source instances with asset-owned models and explicit placement heights.

use glam::DVec2;
use serde::Deserialize;

use crate::world::scenery::{Land, Placement, ScatterKind};

#[derive(Deserialize)]
struct Published<'a> {
    rectangle_m: [f64; 4],
    #[serde(borrow)]
    groups: Vec<Group<'a>>,
}

#[derive(Deserialize)]
struct Group<'a> {
    model: &'a str,
    kind: Option<&'a str>,
    afar: bool,
    instances: Vec<[f64; 5]>,
}

pub fn plants(source: &'static str, land: &Land) -> Vec<Placement> {
    let source: Published<'static> = serde_json::from_str(source).expect("published vegetation must be valid JSON");
    let [west, south, east, north] = source.rectangle_m;
    assert!(
        [west, south, east, north].iter().all(|v| v.is_finite()) && west < east && south < north,
        "invalid vegetation rectangle"
    );
    let mut placements = Vec::new();
    for group in source.groups {
        let kind = match group.kind {
            Some("tree") => Some(ScatterKind::Tree),
            Some("bush") => Some(ScatterKind::Bush),
            Some("grass") => Some(ScatterKind::Grass),
            None => None,
            _ => panic!("invalid source vegetation kind"),
        };
        for [x, y, z, yaw, scale] in group.instances {
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
            land.height(stored).expect("source vegetation stands on exported terrain");
            let placement = Placement {
                model: group.model,
                at,
                yaw: yaw.to_radians(),
                scale,
                origin_offset_m: 0.0,
                origin_height_m: Some(z),
                afar: group.afar,
            };
            if let Some(kind) = kind {
                assert!(land.allows_candidate(kind, &placement), "source vegetation contradicts a clearing at {at}");
            }
            placements.push(placement);
        }
    }
    placements
}
