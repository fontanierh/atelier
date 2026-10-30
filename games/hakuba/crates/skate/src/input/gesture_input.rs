//! GameInputManager82696030/826962D8 -> listener8259B878/8259B9D0 ->
//! Fill8259B1F0..B7D8. Runs on the existing 60 Hz gameplay input boundary.
use crate::core::{
    graph::intents::IntentMap,
    input::gesture::{Recognizer, Settings},
};
use crate::data::collections::Collections;

pub(crate) struct GestureInput {
    recognizers: Vec<(usize, Recognizer)>,
    maximum_misses: [u8; 2],
    authored_misses: [u8; 2],
    pace: f32,
    tight_flicks: bool,
    held_pattern: Option<String>,
}
impl GestureInput {
    pub fn load(root: &crate::resources::Resources) -> Result<Self, String> {
        let data = Collections::load(root)?;
        let misses = |key| -> Result<u8, String> {
            let field = data.field("recognizer", key, "NumTicksPatternNotInRangeBeforeCulling")?;
            if field.type_name != "EA::Reflection::UInt8" {
                return Err("Recognizer culling field must be UInt8".into());
            }
            u8::from_str_radix(&field.data, 16).map_err(|e| e.to_string())
        };
        let mut recognizers = Vec::new();
        for (stick, patterns) in &root.gestures {
            recognizers.push((*stick, Recognizer::new(patterns.clone())?));
        }
        let authored_misses = [misses("left_stick")?, misses("right_stick")?];
        Ok(Self {
            recognizers,
            maximum_misses: authored_misses.map(|misses| (u16::from(misses) * 2).clamp(2, 120) as u8),
            authored_misses,
            pace: 1.0,
            tight_flicks: false,
            held_pattern: None,
        })
    }

    pub fn tune(&mut self, radius: f32, window: f32, pace: f32, tight: bool) {
        if tight != self.tight_flicks && !self.recognizers.is_empty() {
            let extra = if tight {
                vec![
                    crate::core::input::gesture::Pattern {
                        name: "Hardflip".into(),
                        points: vec![[0.34202, 0.93969], [-0.03490, 0.99939], [0.37461, -0.92718]],
                        tolerance_squared: 0.09,
                    },
                    crate::core::input::gesture::Pattern {
                        name: "InwardHeelflip".into(),
                        points: vec![[-0.34202, 0.93969], [0.03490, 0.99939], [-0.37461, -0.92718]],
                        tolerance_squared: 0.09,
                    },
                ]
            } else {
                vec![]
            };
            self.recognizers[0].1.set_extra_patterns(extra).expect("valid tight flick patterns");
            self.tight_flicks = tight;
        }
        for (_, recognizer) in &mut self.recognizers {
            recognizer.scale_radius(radius);
        }
        for i in 0..2 {
            self.maximum_misses[i] =
                (f32::from(self.authored_misses[i]) * window * 2.0).round().clamp(2.0, 120.0) as u8;
        }
        self.pace = pace;
    }

    pub fn publish(
        &mut self,
        axes: [[f32; 2]; 2],
        difficulty: u32,
        flags: u32,
        physical_state: u32,
        ag: &mut IntentMap,
    ) {
        self.publish_fine(None, axes, difficulty, flags, physical_state, ag);
    }

    pub fn publish_fine(
        &mut self,
        half: Option<[[f32; 2]; 2]>,
        axes: [[f32; 2]; 2],
        difficulty: u32,
        flags: u32,
        physical_state: u32,
        ag: &mut IntentMap,
    ) {
        // Native manager negates mapped Y. Component deadzone0.1 is initialized
        // by82F75F60 from820641A8, separately from cInputMap's own deadzones.
        let samples = axes.map(|[x, y]| [x, -y].map(|v| if v.abs() < 0.1 { 0.0 } else { v }));
        let earlier = half.map(|axes| axes.map(|[x, y]| [x, -y].map(|v| if v.abs() < 0.1 { 0.0 } else { v })));
        let mut events = Vec::new();
        let mut held = false;
        for stick in [1, 0] {
            // Held checks precede *all* matches on this stick.
            for (_, recognizer) in self.recognizers.iter_mut().filter(|r| r.0 == stick) {
                if let Some(index) = recognizer.held(samples[stick]) {
                    if self
                        .held_pattern
                        .as_deref()
                        .is_some_and(|name| name.eq_ignore_ascii_case(&recognizer.patterns()[index].name))
                    {
                        held = true;
                    }
                }
            }
            for (_, recognizer) in self.recognizers.iter_mut().filter(|r| r.0 == stick) {
                let settings = Settings { maximum_misses: self.maximum_misses[stick], difficulty, pace: self.pace };
                let matched = recognizer.sample_tick(earlier.map(|axes| axes[stick]), samples[stick], settings);
                if let Some(result) = matched {
                    let name = recognizer.patterns()[result.pattern].name.clone();
                    // Listener retains only these four hold-capable events.
                    if ["Kickflip", "Heelflip", "N_Kickflip", "N_Heelflip"].contains(&name.as_str()) {
                        self.held_pattern = Some(name.clone());
                    }
                    events.push((name, result.strength));
                }
            }
        }
        if held {
            ag.insert("HoldPattern", 1.0);
        }
        for (name, strength) in events {
            if permitted(&name, flags, physical_state, ag) {
                ag.insert("Trick", 1.0);
                ag.insert(&name, 1.0);
                ag.insert("GestureSpeed", strength);
            }
        }
    }
}

fn permitted(name: &str, flags: u32, state: u32, ag: &IntentMap) -> bool {
    let bit = |n: u32| (flags & (1u32 << n)) != 0u32;
    let member = |names: &[&str]| names.iter().any(|n| n.eq_ignore_ascii_case(name));
    if bit(5) && member(&["FingerFlip", "FS_Varial", "BS_Varial"]) {
        return false;
    }
    if bit(4)
        && (matches!(state, 200 | 201)
            || member(&["L_F_Kickflip", "L_B_Kickflip", "L_F_Heelflip", "L_B_Heelflip", "L_FS_Shuvit", "L_BS_Shuvit"]))
    {
        return false;
    }
    if member(&["FrontFlip", "BackFlip"])
        && (!(ag.contains_key("RightAirGrab") || ag.contains_key("LeftAirGrab"))
            || ag.contains_key("LeftPush")
            || ag.contains_key("RightPush")
            || bit(3))
    {
        return false;
    }
    if bit(8) && member(&["SlideFs180", "SlideBs180"]) {
        return false;
    }
    if bit(12)
        && !member(&[
            "Ollie",
            "Kickflip",
            "Heelflip",
            "Hardflip",
            "InwardHeelflip",
            "VarialKickflip",
            "VarialHeelflip",
            "PopShuvit",
            "FSPopShuvit",
            "360PopShuvit",
            "FS360PopShuvit",
        ])
    {
        return false;
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stock_360_gesture_reaches_native_square_mapping() {
        let root = crate::test_support::resources();
        let mut input = GestureInput::load(&root).unwrap();
        let mut ag = IntentMap::new();
        let points = input.recognizers[0].1.patterns().iter().find(|p| p.name == "360Flip").unwrap().points.clone();
        input.publish([[0.0; 2]; 2], 0, 0, 100, &mut ag);
        for _ in 0..30 {
            ag.clear();
            input.publish([[0.0; 2], [points[0][0], -points[0][1]]], 0, 0, 100, &mut ag);
            assert!(!ag.contains_key("Trick"));
        }
        for point in &points[1..] {
            ag.clear();
            input.publish([[0.0; 2], [point[0], -point[1]]], 0, 0, 100, &mut ag);
        }
        assert!(ag.contains_key("360Flip"), "{ag:?}");
        assert_eq!(
            super::super::gesture_mapping::select(super::super::gesture_catalog::Group::Square, &ag, false),
            Some("360Flip")
        );
        assert_eq!(ag.get("GestureSpeed"), Some(&1.0));
        println!("Authored scoop through all seven PAT recognizers: {ag:?}");
    }
}

#[cfg(test)]
mod package_tests {
    use super::*;
    fn resources() -> crate::resources::Resources {
        let bytes = std::fs::read(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../assets/simulations/skate-simulation/skate-simulation.skatepack"
        ))
        .expect("export skating data before gesture package tests");
        crate::resources::Resources::from_bytes(bytes).unwrap()
    }
    #[test]
    fn every_authored_pattern_recognizes_ordinary_packets() {
        let source = resources();
        assert_eq!(source.gestures.len(), 7);
        let settings = Settings { maximum_misses: 6, difficulty: 0, pace: 1.0 };
        for (_, patterns) in &source.gestures {
            for pattern in patterns {
                let mut recognizer = Recognizer::new(vec![pattern.clone()]).unwrap();
                recognizer.sample_tick(None, [0.0; 2], settings);
                let mut result = None;
                for &point in &pattern.points {
                    if let Some(matched) = recognizer.sample_tick(None, point, settings) {
                        result = Some(matched);
                        break;
                    }
                }
                let result = result.unwrap_or_else(|| panic!("{} was not recognized", pattern.name));
                assert_eq!(result.pattern, 0);
                assert_eq!(result.elapsed, pattern.points.len() as f32, "{}", pattern.name);
                assert_eq!(result.strength, 1.0, "{}", pattern.name);
            }
        }
    }
    #[test]
    fn tight_patterns_are_additive_and_restore_real_package_patterns() {
        let source = resources();
        let mut input = GestureInput::load(&source).unwrap();
        let authored = input.recognizers[0].1.patterns().to_vec();
        assert_eq!(input.maximum_misses, input.authored_misses.map(|m| (u16::from(m) * 2).clamp(2, 120) as u8));
        input.tune(1.0, 1.0, 1.0, true);
        assert_eq!(&input.recognizers[0].1.patterns()[..authored.len()], authored.as_slice());
        assert_eq!(input.recognizers[0].1.patterns().len(), authored.len() + 2);
        input.tune(1.5, 2.0, 0.8, true);
        input.tune(1.0, 1.0, 1.0, false);
        assert_eq!(input.recognizers[0].1.patterns(), authored.as_slice());
        assert_eq!(input.maximum_misses, input.authored_misses.map(|m| (u16::from(m) * 2).clamp(2, 120) as u8));
        for (name, points) in [
            ("Hardflip", [[0.34202, 0.93969], [-0.03490, 0.99939], [0.37461, -0.92718]]),
            ("InwardHeelflip", [[-0.34202, 0.93969], [0.03490, 0.99939], [-0.37461, -0.92718]]),
        ] {
            let mut input = GestureInput::load(&source).unwrap();
            input.tune(1.0, 1.0, 1.0, true);
            let mut ag = IntentMap::new();
            input.publish([[0.0; 2]; 2], 0, 0, 100, &mut ag);
            let packet = |p: [f32; 2]| [[0.0; 2], [p[0], -p[1]]];
            input.publish_fine(None, packet(points[0]), 0, 0, 100, &mut ag);
            ag.clear();
            input.publish_fine(Some(packet(points[1])), packet(points[2]), 0, 0, 100, &mut ag);
            assert!(ag.contains_key(name), "{name}: {ag:?}");
        }
    }
}
