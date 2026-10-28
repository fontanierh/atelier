//! Source-authored woodland clearing, trails and lake surroundings.

use glam::DVec2;
use serde::Deserialize;

use super::Region;
use crate::world::levelling::Strip;
use crate::world::overlay::Overlay;
use crate::world::published;
use crate::world::scenery::{Land, Placement, Scenery};

#[derive(Deserialize)]
struct Layout<'a> {
    #[serde(borrow)]
    fixed_models: Vec<Fixed<'a>>,
    #[serde(borrow)]
    lake: Lake<'a>,
}

#[derive(Deserialize)]
struct Lake<'a> {
    #[serde(borrow)]
    water_models: Vec<Fixed<'a>>,
}

#[derive(Deserialize)]
struct Fixed<'a> {
    model: &'a str,
    origin_m: [f64; 3],
}

pub struct Woodland;

impl Region for Woodland {
    fn name(&self) -> &'static str {
        "woodland"
    }

    fn levelled(&self) -> Vec<Strip> {
        Vec::new()
    }

    fn overlays(&self) -> Vec<Overlay> {
        Vec::new()
    }

    fn water(&self) -> Vec<serde_json::Value> {
        let source: serde_json::Value = serde_json::from_str(include_str!("source-layout.json"))
            .expect("the committed woodland layout is valid JSON");
        let lake = &source["lake"];
        vec![serde_json::json!({
            "center_m": lake["center_m"], "radii_m": lake["radii_m"],
            "water_height_m": lake["water_height_m"], "shore_harmonics": lake["shore_harmonics"],
            "recovery_depth_m": lake["recovery_depth_m"], "safe_shore_m": lake["safe_shore_m"],
            "material": lake["material"], "water_models": lake["water_models"]
        })]
    }

    fn scenery(&self, land: &Land) -> Scenery {
        let source: Layout<'static> = serde_json::from_str(include_str!("source-layout.json"))
            .expect("the committed woodland layout is valid JSON");
        let mut placements = published::plants(include_str!("source-vegetation.json"), land);
        placements.extend(published::plants(include_str!("source-adjacent-canopy.json"), land));
        placements.extend(source.fixed_models.into_iter().chain(source.lake.water_models).map(|fixed| {
            let [x, y, height] = fixed.origin_m;
            Placement {
                model: fixed.model,
                at: DVec2::new(x, y),
                yaw: 0.0,
                scale: 1.0,
                origin_offset_m: 0.0,
                origin_height_m: Some(height),
                afar: true,
            }
        }));
        Scenery { placements, ..Scenery::default() }
    }
}
