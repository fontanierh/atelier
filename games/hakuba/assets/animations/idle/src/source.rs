//! The skeleton of `source.glb`: which of its bones plays each rig bone. It has no bone between its spine and chest.

use crate::rig::{Bones, Fingers, Limbs, Skeleton};

pub struct Source;

impl Skeleton for Source {
    fn bones(&self) -> Bones {
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
}
