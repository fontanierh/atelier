//! What stands along Momiji coast's road: utility poles on its rising side with cables from pole to pole, a street
//! lamp on every third pole, and a guardrail on its falling side wherever the ground drops away.

use glam::{DVec2, DVec3};

use crate::world::raised::SurfacePaint;
use crate::world::scenery::{Cable, Land, Placement, Scenery};

#[derive(serde::Deserialize)]
struct Source {
    poles: std::collections::BTreeMap<String, Vec<[f64; 5]>>,
    anchors: Vec<Vec<[f64; 3]>>,
    rails: Vec<Vec<[f64; 5]>>,
}

/// The guardrail's white paint, which tints its weathered painted metal, and the cables' dark metal.
const PAINT: [f64; 3] = [0.85, 0.85, 0.82];
const CABLE: [f64; 3] = [0.08, 0.08, 0.09];

fn source_paint() -> Option<SurfacePaint> {
    Some(SurfacePaint { haze_start_m: 30.0, haze_length_m: 9000.0, haze_colour: [0.0932, 0.2301, 0.5328] })
}

/// Adds the source poles, wires and guardrails to the scenery.
pub fn add(scenery: &mut Scenery, land: &Land) {
    let source: Source = serde_json::from_str(include_str!("source-roadside.json")).expect("valid source roadside");
    for (name, rows) in &source.poles {
        let model = match name.as_str() {
            "Pole" => "props/coast-pole",
            "Pole_Lamp" => "props/coast-pole-lamp",
            _ => panic!("unknown source pole {name}"),
        };
        for &[x, y, z, yaw, scale] in rows {
            let at = DVec2::new(x, y);
            if at.cmplt(land.low).any() || at.cmpge(land.high).any() {
                continue;
            }
            let _seat = land.height(land.placement_at(at)).expect("source pole stands on exported ground");
            scenery.placements.push(Placement {
                model,
                at,
                yaw: yaw.to_radians(),
                scale,
                origin_offset_m: 0.0,
                origin_height_m: Some(z),
                afar: true,
            });
        }
    }
    assert!(source.anchors.iter().all(|anchors| anchors.len() == 5));
    for pair in source.anchors.windows(2) {
        for (&from, &to) in pair[0].iter().zip(&pair[1]) {
            scenery.cables.push(Cable {
                from: DVec3::from_array(from),
                to: DVec3::from_array(to),
                sag: 0.035,
                radius_m: 0.03,
                colour: CABLE,
                paint: source_paint(),
            });
        }
    }

    for run in source.rails {
        scenery.rails.push(crate::world::scenery::Rail {
            points: run.into_iter().map(|[x, y, z, nx, ny]| (DVec3::new(x, y, z), DVec2::new(nx, ny))).collect(),
            profile: vec![[0.0, 0.85], [0.06, 0.80], [0.0, 0.72], [0.06, 0.64], [0.0, 0.58]],
            post_every: 2,
            post_half_width: 0.05,
            post_bottom: -0.3,
            post_top: 0.72,
            colour: PAINT,
            paint: source_paint(),
        });
    }
}
