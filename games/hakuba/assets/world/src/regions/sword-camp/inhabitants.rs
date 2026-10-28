//! Provisional visual inhabitants: source role colours, placement and rigid equipment.
//! Source import settings, displayed poses, ground owners and idle blade pose still need visual verification.

use crate::world::actors::{Actor, Attachment, Practice, Scan};
use glam::{DMat3, DQuat, DVec3};

/// Convert the authored pitch/yaw/roll rotation to the world's component frame.
fn turn(pitch: f64, yaw: f64, roll: f64) -> DQuat {
    let [p, y, r] = [pitch, yaw, roll].map(|v| v.to_radians() * 0.5);
    let (sp, cp) = p.sin_cos();
    let (sy, cy) = y.sin_cos();
    let (sr, cr) = r.sin_cos();
    let x = cr * sp * sy - sr * cp * cy;
    let y = -cr * sp * cy - sr * cp * sy;
    let z = cr * cp * sy - sr * sp * cy;
    let w = cr * cp * cy + sr * sp * sy;
    DQuat::from_xyzw(-x, -z, -y, w)
}

fn part(
    model: &'static str,
    position: &'static str,
    rotation: &'static str,
    offset: [f64; 3],
    turn: DQuat,
) -> Attachment {
    Attachment { model, position_bone: position, rotation_bone: rotation, offset, rotation: turn.to_array() }
}

fn role(role: usize) -> Vec<Attachment> {
    let mut parts = vec![part(
        [
            "props/visitor-kasa/visitor-kasa.glb",
            "props/visitor-jingasa/visitor-jingasa.glb",
            "props/visitor-kabuto/visitor-kabuto.glb",
        ][role],
        "head",
        "head",
        [-0.04, 0.248, 0.0],
        DQuat::IDENTITY,
    )];
    if role == 0 {
        parts.push(part(
            "props/visitor-wakizashi/visitor-wakizashi.glb",
            "chest",
            "chest",
            [-0.04, -0.22, -0.20],
            turn(-65.0, -12.0, 0.0),
        ));
    } else {
        parts.push(part("props/visitor-menpo/visitor-menpo.glb", "head", "head", [0.065, 0.095, 0.0], DQuat::IDENTITY));
        parts.push(part("props/visitor-do/visitor-do.glb", "chest", "chest", [-0.004, -0.05, 0.0], DQuat::IDENTITY));
        for (bone, side, yaw) in [("upperarm_L", -0.095, -90.0), ("upperarm_R", 0.095, 90.0)] {
            parts.push(part(
                "props/visitor-sode/visitor-sode.glb",
                bone,
                "chest",
                [0.0, -0.055, side],
                turn(0.0, yaw, 0.0) * turn(16.0, 0.0, 0.0),
            ));
        }
    }
    if role == 2 {
        parts.push(part(
            "props/visitor-sashimono/visitor-sashimono.glb",
            "chest",
            "chest",
            [-0.175, -0.10, 0.0],
            DQuat::IDENTITY,
        ));
    }
    // Unarmed idle: the hidden reference sword is carried on the chest. Its original
    // import report records the pivot and axes in component space. GetBladePose starts
    // at 18% of the reference blade's far bound; custom role lengths affect the tip,
    // not this base or direction. Convert UE (x,y,z) cm to world (x,z,y) metres.
    // The original importer frame and the posed result still need visual confirmation.
    let (edge, blade, base, bone) = if role == 1 {
        // Imported sword-trainer held transform in the exported hand reference frame.
        // UE bone-local to glTF bone-local uses H=(x,-y,z); equipment uses E=(x,z,y).
        // The source import record rounds the held transform; posed fit needs review.
        (
            DVec3::new(0.23553218, -0.23492799, -0.94304477).normalize(),
            DVec3::new(-0.97038979, -0.11032052, -0.21487914).normalize(),
            DVec3::new(-0.11325734, 0.02333232, 0.11308673),
            "hand_R",
        )
    } else {
        let edge = DVec3::new(-0.02761, -0.5, 0.86559).normalize();
        let blade = DVec3::new(-0.99949, 0.0, -0.03188).normalize();
        let pivot = DVec3::new(-0.1082, 0.2934, 0.1455);
        (edge, blade, pivot + blade * (0.783203125 * (0.005 * 167.99966444290786) * 0.18), "chest")
    };
    let side = edge.cross(blade).normalize();
    let edge = blade.cross(side).normalize();
    parts.push(part(
        if role == 2 { "props/visitor-nodachi/visitor-nodachi.glb" } else { "props/visitor-katana/visitor-katana.glb" },
        bone,
        bone,
        base.to_array(),
        DQuat::from_mat3(&DMat3::from_cols(edge, blade, side)),
    ));
    parts
}

pub fn residents() -> Vec<Actor> {
    let poses = [
        ([-55.8504257542, -88.2749738404, 8.5748556543], 92.489552922, 0.94, [0.14, 0.28, 0.62], "Nml_Wait"),
        ([-57.1448550376, -95.3378665077, 7.9558396300], 37.489552922, 1.03, [0.16, 0.42, 0.24], "A_Pose_Sword_Wait"),
        ([-52.6795083820, -96.7452325743, 7.9411933659], 107.489552922, 1.12, [0.68, 0.10, 0.13], "Nml_Wait"),
    ];
    poses
        .into_iter()
        .enumerate()
        .map(|(i, (position, yaw_deg, scale, colour, clip))| Actor {
            model: "characters/camp-visitor/camp-visitor.glb",
            position,
            yaw_deg,
            scale,
            clip,
            rate: 1.0,
            phase_s: 0.0,
            colour,
            cloth: [1.01, 1.25, 0.3, 0.4],
            route: None,
            scan: (i == 0).then_some(Scan { amplitude_deg: 28.0, frequency: 0.85, max_speed_deg: 90.0 }),
            // The source chooses a fresh delay from 2.6–4.2 seconds after each cut.
            practice: (i == 1).then_some(Practice {
                clip: "Sword_Attack_S1",
                rate: 1.15,
                duration_s: 0.7 / 1.15,
                interval_s: [2.6, 4.2],
                delay_s: 2.0,
            }),
            attachments: role(i),
        })
        .collect()
}
