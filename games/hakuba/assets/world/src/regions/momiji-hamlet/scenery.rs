//! The houses, covered well, waymark and maple around the hamlet's lanes.

use super::{APPROACH, INNER, entrance_geometry};
use crate::world::scenery::{Placement, Scenery};
use glam::DVec2;

/// Each house is turned from its model's local front toward its lane.
pub const BUILT: [(&str, f64, f64, f64); 6] = [
    ("props/hamlet-tea-house", 77.5, 77.5, 0.0),
    ("props/hamlet-cottage-a", 80.0, 99.0, -45.0),
    ("props/hamlet-cottage-b", 104.5, 105.0, -110.0),
    ("props/hamlet-workshop", 118.0, 68.0, -210.0),
    ("props/hamlet-storehouse", 122.0, 89.5, -90.0),
    ("props/hamlet-well", 99.0, 83.35, 0.0),
];

pub fn make() -> Scenery {
    let mut scenery = Scenery::default();
    for (model, x, y, yaw) in BUILT {
        scenery.placements.push(Placement {
            model,
            at: DVec2::new(x, y),
            yaw: yaw.to_radians(),
            scale: 1.0,
            afar: true,
        });
        // Furniture offsets are in the building's original front-facing frame. The four rotated models map
        // source (x, y) to local (-y, x); the placement's yaw then carries that frame into the world.
        let furniture: &[(&str, [f64; 2], f64)] = match model {
            "props/hamlet-cottage-a" => &[
                ("props/hamlet-bench", [-1.3, -3.16], 1.0),
                ("props/hamlet-clay-pot", [-2.85, -3.03], 0.75),
                ("props/hamlet-blue-pot", [2.85, -3.03], 0.75),
            ],
            "props/hamlet-cottage-b" => &[
                ("props/hamlet-bench", [0.85, -3.31], 1.0),
                ("props/hamlet-clay-pot", [-2.6, -3.18], 0.75),
                ("props/hamlet-blue-pot", [2.6, -3.18], 0.75),
            ],
            "props/hamlet-tea-house" => &[
                ("props/hamlet-bench", [1.55, -4.14], 2.4 / 1.7),
                ("props/hamlet-blue-pot", [-3.6, -4.8], 1.1),
                ("props/hamlet-blue-pot", [3.6, -4.8], 1.05),
            ],
            "props/hamlet-workshop" => &[("props/hamlet-clay-pot", [3.4, -3.04], 1.2)],
            _ => &[],
        };
        let angle = yaw.to_radians();
        let (sin, cos) = angle.sin_cos();
        for &(piece, [source_x, source_y], scale) in furniture {
            let local = DVec2::new(-source_y, source_x);
            let at = DVec2::new(x, y) + DVec2::new(cos * local.x - sin * local.y, sin * local.x + cos * local.y);
            scenery.placements.push(Placement {
                model: piece,
                at,
                yaw: angle + std::f64::consts::FRAC_PI_2,
                scale,
                afar: true,
            });
        }
    }
    // The waymark stands beside the trail just beyond the road's edge.
    let (start, along) = entrance_geometry();
    scenery.placements.push(Placement {
        model: "props/hamlet-waymark",
        at: start + along * 4.0 + along.perp() * 3.0,
        yaw: along.to_angle(),
        scale: 1.0,
        afar: true,
    });
    // The gate straddles the joined lanes; its origin is the left support foot.
    let from = DVec2::from_array(APPROACH[APPROACH.len() - 1]);
    let to = DVec2::from_array(INNER[0]);
    let gate_yaw = (to - from).to_angle() - std::f64::consts::FRAC_PI_2;
    let support = DVec2::new(gate_yaw.cos(), gate_yaw.sin()) * 3.15;
    scenery.placements.push(Placement {
        model: "props/hamlet-gate",
        at: (from + to) / 2.0 - support,
        yaw: gate_yaw,
        scale: 1.0,
        afar: true,
    });
    scenery.placements.push(Placement {
        model: "plants/maple-a",
        at: DVec2::new(100.0, 86.0),
        yaw: 0.0,
        scale: 1.0,
        afar: true,
    });
    // The original clearing's hand-placed edge trees; its eighth candidate is excluded by the workshop clearance.
    for (model, x, y, yaw, scale) in [
        ("plants/maple-a", 68.0, 75.0, 87.44757538_f64, 0.87919702),
        ("plants/maple-a", 70.0, 95.0, 17.47955613, 1.01990732),
        ("plants/pine-a", 77.0, 115.0, 112.25721183, 1.03206234),
        ("plants/pine-a", 93.0, 119.0, 240.99400646, 0.96034478),
        ("plants/pine-a", 115.0, 116.0, 66.17115333, 0.95816282),
        ("plants/maple-a", 133.0, 98.0, 160.1036988, 0.91127997),
        ("plants/maple-a", 127.0, 73.0, 245.32795517, 0.98160027),
    ] {
        scenery.placements.push(Placement { model, at: DVec2::new(x, y), yaw: yaw.to_radians(), scale, afar: true });
    }
    scenery
}
