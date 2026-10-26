//! The rig: the humanoid skeleton every clip is stored on, and the [`Skeleton`] trait that maps a model's bones to it.
//! Its submodules are the two kinds made on it, `animation` and `character`, and what they share.
//!
//! A clip on the rig gives each rig bone's turn from the rig's rest pose, in the world's axes, and the pelvis's
//! position in hip heights. The rest pose is a T-pose facing +Z, with the character's left at +X, the pelvis one unit
//! above the floor and every bone's rest rotation the identity.

pub mod animation;
pub mod animations;
pub mod character;
pub mod characters;
pub mod equipment;
pub mod pose;
pub mod pose_edit;
pub mod retarget;

/// One rig bone: its name, its parent's name and its rest position, in hip heights.
pub struct RigBone {
    pub name: &'static str,
    pub parent: Option<&'static str>,
    pub rest: [f64; 3],
}

/// Every rig bone, each after its parent.
pub const RIG: [RigBone; 52] = [
    RigBone { name: "pelvis", parent: None, rest: [0.0000, 1.0000, 0.0000] },
    RigBone { name: "spine", parent: Some("pelvis"), rest: [0.0000, 1.0000, 0.0000] },
    RigBone { name: "spine_mid", parent: Some("spine"), rest: [0.0000, 1.0684, 0.0000] },
    RigBone { name: "chest", parent: Some("spine_mid"), rest: [0.0000, 1.1368, 0.0000] },
    RigBone { name: "neck", parent: Some("chest"), rest: [0.0000, 1.4016, 0.0000] },
    RigBone { name: "head", parent: Some("neck"), rest: [0.0000, 1.5267, 0.0000] },
    RigBone { name: "clavicle_l", parent: Some("chest"), rest: [0.0331, 1.3778, 0.0000] },
    RigBone { name: "upper_arm_l", parent: Some("clavicle_l"), rest: [0.1840, 1.3670, 0.0000] },
    RigBone { name: "forearm_l", parent: Some("upper_arm_l"), rest: [0.4253, 1.3670, 0.0000] },
    RigBone { name: "hand_l", parent: Some("forearm_l"), rest: [0.7041, 1.3670, 0.0000] },
    RigBone { name: "thumb_1_l", parent: Some("hand_l"), rest: [0.7283, 1.3465, 0.0252] },
    RigBone { name: "thumb_2_l", parent: Some("thumb_1_l"), rest: [0.7760, 1.3387, 0.0527] },
    RigBone { name: "thumb_3_l", parent: Some("thumb_2_l"), rest: [0.8014, 1.3346, 0.0674] },
    RigBone { name: "index_1_l", parent: Some("hand_l"), rest: [0.8071, 1.3667, 0.0279] },
    RigBone { name: "index_2_l", parent: Some("index_1_l"), rest: [0.8519, 1.3667, 0.0279] },
    RigBone { name: "index_3_l", parent: Some("index_2_l"), rest: [0.8802, 1.3667, 0.0279] },
    RigBone { name: "middle_1_l", parent: Some("hand_l"), rest: [0.8099, 1.3729, 0.0037] },
    RigBone { name: "middle_2_l", parent: Some("middle_1_l"), rest: [0.8620, 1.3729, 0.0037] },
    RigBone { name: "middle_3_l", parent: Some("middle_2_l"), rest: [0.8920, 1.3729, 0.0037] },
    RigBone { name: "ring_1_l", parent: Some("hand_l"), rest: [0.8091, 1.3725, -0.0228] },
    RigBone { name: "ring_2_l", parent: Some("ring_1_l"), rest: [0.8539, 1.3725, -0.0228] },
    RigBone { name: "ring_3_l", parent: Some("ring_2_l"), rest: [0.8804, 1.3725, -0.0228] },
    RigBone { name: "pinky_1_l", parent: Some("hand_l"), rest: [0.8052, 1.3659, -0.0465] },
    RigBone { name: "pinky_2_l", parent: Some("pinky_1_l"), rest: [0.8387, 1.3659, -0.0465] },
    RigBone { name: "pinky_3_l", parent: Some("pinky_2_l"), rest: [0.8593, 1.3659, -0.0465] },
    RigBone { name: "thigh_l", parent: Some("pelvis"), rest: [0.1127, 0.8908, 0.0166] },
    RigBone { name: "shin_l", parent: Some("thigh_l"), rest: [0.1127, 0.4684, 0.0166] },
    RigBone { name: "foot_l", parent: Some("shin_l"), rest: [0.1127, 0.1177, -0.0141] },
    RigBone { name: "toe_l", parent: Some("foot_l"), rest: [0.1127, 0.0420, 0.1346] },
    RigBone { name: "clavicle_r", parent: Some("chest"), rest: [-0.0331, 1.3778, 0.0000] },
    RigBone { name: "upper_arm_r", parent: Some("clavicle_r"), rest: [-0.1840, 1.3670, 0.0000] },
    RigBone { name: "forearm_r", parent: Some("upper_arm_r"), rest: [-0.4253, 1.3670, 0.0000] },
    RigBone { name: "hand_r", parent: Some("forearm_r"), rest: [-0.7041, 1.3670, 0.0000] },
    RigBone { name: "thumb_1_r", parent: Some("hand_r"), rest: [-0.7283, 1.3465, 0.0252] },
    RigBone { name: "thumb_2_r", parent: Some("thumb_1_r"), rest: [-0.7760, 1.3387, 0.0527] },
    RigBone { name: "thumb_3_r", parent: Some("thumb_2_r"), rest: [-0.8014, 1.3346, 0.0674] },
    RigBone { name: "index_1_r", parent: Some("hand_r"), rest: [-0.8071, 1.3667, 0.0279] },
    RigBone { name: "index_2_r", parent: Some("index_1_r"), rest: [-0.8519, 1.3667, 0.0279] },
    RigBone { name: "index_3_r", parent: Some("index_2_r"), rest: [-0.8802, 1.3667, 0.0279] },
    RigBone { name: "middle_1_r", parent: Some("hand_r"), rest: [-0.8099, 1.3729, 0.0037] },
    RigBone { name: "middle_2_r", parent: Some("middle_1_r"), rest: [-0.8620, 1.3729, 0.0037] },
    RigBone { name: "middle_3_r", parent: Some("middle_2_r"), rest: [-0.8920, 1.3729, 0.0037] },
    RigBone { name: "ring_1_r", parent: Some("hand_r"), rest: [-0.8091, 1.3725, -0.0228] },
    RigBone { name: "ring_2_r", parent: Some("ring_1_r"), rest: [-0.8539, 1.3725, -0.0228] },
    RigBone { name: "ring_3_r", parent: Some("ring_2_r"), rest: [-0.8804, 1.3725, -0.0228] },
    RigBone { name: "pinky_1_r", parent: Some("hand_r"), rest: [-0.8052, 1.3659, -0.0465] },
    RigBone { name: "pinky_2_r", parent: Some("pinky_1_r"), rest: [-0.8387, 1.3659, -0.0465] },
    RigBone { name: "pinky_3_r", parent: Some("pinky_2_r"), rest: [-0.8593, 1.3659, -0.0465] },
    RigBone { name: "thigh_r", parent: Some("pelvis"), rest: [-0.1127, 0.8908, 0.0166] },
    RigBone { name: "shin_r", parent: Some("thigh_r"), rest: [-0.1127, 0.4684, 0.0166] },
    RigBone { name: "foot_r", parent: Some("shin_r"), rest: [-0.1127, 0.1177, -0.0141] },
    RigBone { name: "toe_r", parent: Some("foot_r"), rest: [-0.1127, 0.0420, 0.1346] },
];

/// The rig bone's index in [`RIG`].
pub fn index(name: &str) -> usize {
    RIG.iter().position(|bone| bone.name == name).unwrap_or_else(|| panic!("no rig bone is named {name}"))
}

/// The rig bone's parent's index in [`RIG`].
pub fn parent(bone: usize) -> Option<usize> {
    RIG[bone].parent.map(index)
}

/// A model whose skeleton plays rig clips.
pub trait Skeleton {
    /// Which of the model's bones plays each rig bone.
    fn bones(&self) -> Bones;
}

/// The model's bone for each rig bone, by node name.
pub struct Bones {
    pub pelvis: String,
    pub spine: String,
    /// The bone between the spine and the chest. Without one, the rig's `spine_mid` takes half their turn.
    pub spine_mid: Option<String>,
    pub chest: String,
    pub neck: String,
    pub head: String,
    pub left: Limbs,
    pub right: Limbs,
}

/// One side's arm and leg.
pub struct Limbs {
    pub clavicle: String,
    pub upper_arm: String,
    pub forearm: String,
    pub hand: String,
    /// Without fingers, the rig's fingers follow the hand.
    pub fingers: Option<Fingers>,
    pub thigh: String,
    pub shin: String,
    pub foot: String,
    pub toe: String,
}

/// One hand's fingers, each from the knuckle out.
pub struct Fingers {
    pub thumb: [String; 3],
    pub index: [String; 3],
    pub middle: [String; 3],
    pub ring: [String; 3],
    pub pinky: [String; 3],
}

impl Bones {
    /// The rig's own bones, for a clip stored on the rig.
    pub fn rig() -> Self {
        let limbs = |side: &str| Limbs {
            clavicle: format!("clavicle_{side}"),
            upper_arm: format!("upper_arm_{side}"),
            forearm: format!("forearm_{side}"),
            hand: format!("hand_{side}"),
            fingers: Some(Fingers {
                thumb: [1, 2, 3].map(|k| format!("thumb_{k}_{side}")),
                index: [1, 2, 3].map(|k| format!("index_{k}_{side}")),
                middle: [1, 2, 3].map(|k| format!("middle_{k}_{side}")),
                ring: [1, 2, 3].map(|k| format!("ring_{k}_{side}")),
                pinky: [1, 2, 3].map(|k| format!("pinky_{k}_{side}")),
            }),
            thigh: format!("thigh_{side}"),
            shin: format!("shin_{side}"),
            foot: format!("foot_{side}"),
            toe: format!("toe_{side}"),
        };
        Self {
            pelvis: "pelvis".into(),
            spine: "spine".into(),
            spine_mid: Some("spine_mid".into()),
            chest: "chest".into(),
            neck: "neck".into(),
            head: "head".into(),
            left: limbs("l"),
            right: limbs("r"),
        }
    }

    /// The skeleton of the motion library every animation's clip comes from, Yorimichi's: it has no bone between its
    /// spine and chest.
    pub fn library() -> Self {
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
        Self {
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

    /// A Mixamo skeleton's bones, named `mixamorig:<bone>`.
    pub fn mixamo() -> Self {
        let name = |bone: &str| format!("mixamorig:{bone}");
        let limbs = |side: &str| Limbs {
            clavicle: name(&format!("{side}Shoulder")),
            upper_arm: name(&format!("{side}Arm")),
            forearm: name(&format!("{side}ForeArm")),
            hand: name(&format!("{side}Hand")),
            fingers: Some(Fingers {
                thumb: [1, 2, 3].map(|k| name(&format!("{side}HandThumb{k}"))),
                index: [1, 2, 3].map(|k| name(&format!("{side}HandIndex{k}"))),
                middle: [1, 2, 3].map(|k| name(&format!("{side}HandMiddle{k}"))),
                ring: [1, 2, 3].map(|k| name(&format!("{side}HandRing{k}"))),
                pinky: [1, 2, 3].map(|k| name(&format!("{side}HandPinky{k}"))),
            }),
            thigh: name(&format!("{side}UpLeg")),
            shin: name(&format!("{side}Leg")),
            foot: name(&format!("{side}Foot")),
            toe: name(&format!("{side}ToeBase")),
        };
        Self {
            pelvis: name("Hips"),
            spine: name("Spine"),
            spine_mid: Some(name("Spine1")),
            chest: name("Spine2"),
            neck: name("Neck"),
            head: name("Head"),
            left: limbs("Left"),
            right: limbs("Right"),
        }
    }

    /// Each mapped rig bone's index in [`RIG`] with the model's bone for it.
    pub fn pairs(&self) -> Vec<(usize, &str)> {
        let mut pairs = vec![("pelvis", &self.pelvis), ("spine", &self.spine)];
        pairs.extend(self.spine_mid.iter().map(|bone| ("spine_mid", bone)));
        pairs.extend([("chest", &self.chest), ("neck", &self.neck), ("head", &self.head)]);
        let mut named: Vec<(String, &str)> =
            pairs.into_iter().map(|(rig, bone)| (rig.to_string(), bone.as_str())).collect();
        for (side, limbs) in [("l", &self.left), ("r", &self.right)] {
            let parts = [
                ("clavicle", &limbs.clavicle),
                ("upper_arm", &limbs.upper_arm),
                ("forearm", &limbs.forearm),
                ("hand", &limbs.hand),
                ("thigh", &limbs.thigh),
                ("shin", &limbs.shin),
                ("foot", &limbs.foot),
                ("toe", &limbs.toe),
            ];
            named.extend(parts.map(|(rig, bone)| (format!("{rig}_{side}"), bone.as_str())));
            if let Some(fingers) = &limbs.fingers {
                let digits = [
                    ("thumb", &fingers.thumb),
                    ("index", &fingers.index),
                    ("middle", &fingers.middle),
                    ("ring", &fingers.ring),
                    ("pinky", &fingers.pinky),
                ];
                for (digit, bones) in digits {
                    for (k, bone) in bones.iter().enumerate() {
                        named.push((format!("{digit}_{}_{side}", k + 1), bone.as_str()));
                    }
                }
            }
        }
        named.into_iter().map(|(rig, bone)| (index(&rig), bone)).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_parent_comes_first() {
        for (i, bone) in RIG.iter().enumerate() {
            assert!(bone.parent.is_none_or(|parent| index(parent) < i), "{} comes before its parent", bone.name);
        }
    }

    #[test]
    fn the_rig_maps_every_rig_bone_once() {
        let mut found: Vec<usize> = Bones::rig().pairs().into_iter().map(|(rig, _)| rig).collect();
        found.sort();
        assert_eq!(found, (0..RIG.len()).collect::<Vec<_>>());
    }
}
