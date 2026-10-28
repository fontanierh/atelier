//! The roadside camp's positions and scenery.

mod inhabitants;

use glam::DVec2;

use super::Region;
use crate::world::actors::Actor;
use crate::world::levelling::Strip;
use crate::world::overlay::Overlay;
use crate::world::scenery::{Land, Placement, Scenery};

const CENTRE: DVec2 = DVec2::new(-54.0, -94.0);
const ROAD: DVec2 = DVec2::new(-55.0, -71.0);

pub struct SwordCamp;

impl Region for SwordCamp {
    fn name(&self) -> &'static str {
        "sword-camp"
    }

    fn actors(&self) -> Vec<Actor> {
        inhabitants::residents()
    }

    fn levelled(&self) -> Vec<Strip> {
        Vec::new()
    }

    fn overlays(&self) -> Vec<Overlay> {
        Vec::new()
    }

    fn scenery(&self, _land: &Land) -> Scenery {
        let forward = (ROAD - CENTRE).normalize();
        let left = DVec2::new(-forward.y, forward.x);
        let yaw = forward.y.atan2(forward.x);
        let placements = [
            ("props/camp-firepit", 0.0, 0.0, 0.0_f64),
            ("props/camp-jinmaku", -6.2, 0.0, 90.0),
            ("props/camp-weapon-rack", -2.4, 4.4, -35.0),
            ("props/camp-bales", -2.6, -4.4, 30.0),
        ]
        .into_iter()
        .map(|(model, along, across, turn)| Placement {
            model,
            at: CENTRE + forward * along + left * across,
            yaw: yaw + turn.to_radians(),
            scale: 1.0,
            origin_offset_m: 0.0,
            origin_height_m: None,
            afar: true,
        })
        .collect();
        Scenery { placements, ..Scenery::default() }
    }
}

#[cfg(test)]
mod tests {
    use super::CENTRE;
    use glam::DVec2;

    #[test]
    fn camp_clearing_has_no_published_scenery() {
        let source: serde_json::Value = serde_json::from_str(include_str!("../momiji-coast/source-vegetation.json"))
            .expect("coast scenery is valid JSON");
        for (group, poses) in source["groups"].as_object().expect("coast scenery groups") {
            for pose in poses.as_array().expect("group poses") {
                let x = pose[0].as_f64().expect("pose east");
                let y = pose[1].as_f64().expect("pose north");
                assert!(
                    DVec2::new(x, y).distance_squared(CENTRE) >= 15.5_f64.powi(2),
                    "{group} stands inside the camp clearing at ({x}, {y})"
                );
            }
        }
    }
}
