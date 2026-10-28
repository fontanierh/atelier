//! The village's three residents and the household walk between its two endpoints.

use crate::world::actors::{Actor, Route};

pub fn residents() -> Vec<Actor> {
    vec![
        Actor {
            model: "characters/wanderer/wanderer.glb",
            position: [114.48589838486225, 69.91339745962155, 28.84],
            yaw_deg: -120.0,
            scale: 0.97,
            clip: "interact",
            rate: 0.35,
            phase_s: 0.0,
            colour: [0.055, 0.1, 0.18],
            cloth: [1.01, 1.25, 0.30, 0.4],
            attachments: Vec::new(),
            scan: None,
            practice: None,
            route: None,
        },
        Actor {
            model: "characters/wanderer/wanderer.glb",
            position: [83.5, 74.7, 29.3625],
            yaw_deg: -90.0,
            scale: 0.91,
            clip: "idle",
            rate: 0.75,
            phase_s: 0.4,
            colour: [0.34, 0.16, 0.045],
            cloth: [1.01, 1.25, 0.30, 0.4],
            attachments: Vec::new(),
            scan: None,
            practice: None,
            route: None,
        },
        Actor {
            model: "characters/wanderer/wanderer.glb",
            position: [82.75771644662753, 94.82806999099937, 30.545],
            yaw_deg: 135.0,
            scale: 0.93,
            clip: "walk",
            rate: 1.0,
            phase_s: 0.0,
            colour: [0.16, 0.075, 0.11],
            cloth: [1.01, 1.25, 0.30, 0.4],
            attachments: Vec::new(),
            scan: None,
            practice: None,
            route: Some(Route {
                destination: [84.59619407771255, 96.6665476220844, 30.545],
                half_cycle_s: 20.0,
                delay_s: 5.0,
                travel_s: 7.0,
            }),
        },
    ]
}
