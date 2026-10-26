//! The idle: the skeleton its source clip is on, and how a character changes it: its stance, which a character sets
//! in its `asset.toml` under `[animations.idle]`.

use crate::animations::Animation;
use crate::pose::{Pose, UP};
use crate::pose_edit::{Foot, Leg, bend_forward, body_left, plant, repose};
use crate::rig::{self, Bones, Fingers, Limbs};
use anyhow::{Result, bail};
use serde::Deserialize;
use serde_json::Value;

/// The idle. Its source clip, in `source.glb`, is on a skeleton with no bone between its spine and chest.
pub struct Idle;

impl Animation for Idle {
    fn name(&self) -> &'static str {
        "idle"
    }

    fn source(&self) -> Bones {
        let limbs = |side: &str| {
            let name = |bone: &str| format!("{bone}_{side}");
            let digit = |letter: &str| [1, 2, 3].map(|k| name(&format!("Finger_{letter}_{k}")));
            Limbs {
                clavicle: name("Clavicle"),
                upper_arm: name("Arm_1"),
                forearm: name("Arm_2"),
                hand: name("Wrist"),
                fingers: Some(Fingers {
                    thumb: digit("A"),
                    index: digit("B"),
                    middle: digit("C"),
                    ring: digit("D"),
                    pinky: digit("E"),
                }),
                thigh: name("Leg_1"),
                shin: name("Leg_2"),
                foot: name("Ankle"),
                toe: name("Toe"),
            }
        };
        Bones {
            pelvis: "Waist".into(),
            spine: "Spine_1".into(),
            spine_mid: None,
            chest: "Spine_2".into(),
            neck: "Neck".into(),
            head: "Head".into(),
            left: limbs("L"),
            right: limbs("R"),
        }
    }

    fn change(&self, changes: Option<&Value>, rest: &Pose, frames: &mut [Pose]) -> Result<()> {
        apply(&crate::animations::changes(changes)?, rest, frames)
    }
}

/// A standing pose laid over the idle, which keeps its breathing. The feet stay where the idle plants them.
/// Distances are in centimetres, angles in degrees. A character leaves out what it does not change.
#[derive(PartialEq, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Stance {
    /// How far the hips move forward.
    pub hips_forward_cm: f64,
    /// How much wider the feet stand, in total.
    pub foot_spacing_cm: f64,
    /// How far the spine leans forward.
    pub lean_deg: f64,
    /// How far the upper back bends forward, on top of the lean.
    pub upper_back_deg: f64,
    /// How far each knee turns outward.
    pub knees_out_deg: f64,
    /// How far each upper arm swings back: left, then right.
    pub arm_swing_deg: [f64; 2],
}

impl Stance {
    /// No change.
    pub const NONE: Self = Self {
        hips_forward_cm: 0.0,
        foot_spacing_cm: 0.0,
        lean_deg: 0.0,
        upper_back_deg: 0.0,
        knees_out_deg: 0.0,
        arm_swing_deg: [0.0; 2],
    };
}

impl Default for Stance {
    fn default() -> Self {
        Self::NONE
    }
}

/// The frame the stance measures the body from: which way is left and forward, and which way each knee points.
const REFERENCE_FRAME: usize = 1;

/// The furthest a solved ankle may sit from its goal, in metres.
const ANKLE_TOLERANCE: f64 = 1e-5;

/// Changes the idle `frames` of a skeleton with the rest pose `rest` by `stance`.
///
/// The hips move forward, and the back and arms bend; the bones below follow. Then each foot is put back where the
/// idle has it, moved apart by the foot spacing, with its knee turned out.
pub fn apply(stance: &Stance, rest: &Pose, frames: &mut [Pose]) -> Result<()> {
    if *stance == Stance::NONE {
        return Ok(());
    }
    if frames.len() <= REFERENCE_FRAME {
        bail!("the idle is shorter than the stance's reference frame");
    }
    let reference = frames[REFERENCE_FRAME].clone();
    let left = body_left(&reference);
    let shift = left.cross(UP) * stance.hips_forward_cm / 100.0;
    let turns = [
        ("spine", stance.lean_deg),
        ("spine_mid", stance.upper_back_deg),
        ("upper_arm_l", stance.arm_swing_deg[0]),
        ("upper_arm_r", stance.arm_swing_deg[1]),
    ]
    .map(|(name, degrees)| bend_forward(&reference, rig::index(name), left, degrees));
    // Each leg, its side (1 on the left), and which way its knee points in the reference frame.
    let legs =
        [(Leg::on("l"), 1.0), (Leg::on("r"), -1.0)].map(|(leg, side)| (leg, side, leg.knee_direction(&reference)));
    let pelvis = rig::index("pelvis");
    let reference_pelvis = reference[pelvis].unwrap().rotation;

    let mut worst: f64 = 0.0;
    for frame in frames.iter_mut() {
        // The knees follow the pelvis's turn since the reference frame.
        let pelvis_turn = frame[pelvis].unwrap().rotation * reference_pelvis.transpose();
        let feet = legs.map(|(leg, side, knee)| Foot {
            leg,
            ankle: frame[leg.foot].unwrap().position + left * side * stance.foot_spacing_cm / 200.0,
            knee: pelvis_turn * knee,
            knee_turn_deg: -side * stance.knees_out_deg,
        });
        *frame = repose(frame, rest, shift, &turns);
        worst = worst.max(plant(frame, rest, &feet));
    }
    if worst > ANKLE_TOLERANCE {
        bail!("the stance misses an ankle by {:.3} mm", worst * 1000.0);
    }
    Ok(())
}
