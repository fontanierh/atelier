//! Persisted skating choices, independent of the simulation. Presets keep custom edits for later.
use serde::{Deserialize, Serialize};

/// The three authored difficulties, used directly or as the base for Custom.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum SkateDifficulty {
    Easy,
    Normal,
    Hardcore,
}
impl SkateDifficulty {
    pub const ALL: [Self; 3] = [Self::Easy, Self::Normal, Self::Hardcore];
    pub fn name(self) -> &'static str {
        match self {
            Self::Easy => "easy",
            Self::Normal => "normal",
            Self::Hardcore => "hardcore",
        }
    }
}

/// A preset uses the authored feel; Custom applies the saved multipliers on its base difficulty.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum SkateMode {
    Easy,
    Normal,
    Hardcore,
    Custom,
}
impl SkateMode {
    pub const ALL: [Self; 4] = [Self::Easy, Self::Normal, Self::Hardcore, Self::Custom];
}

#[derive(Clone, Copy)]
pub(crate) struct SkateKnob {
    pub label: &'static str,
    pub low: f32,
    pub high: f32,
    pub step: f32,
    pub always: bool,
    pub authored: f32,
    pub group: &'static str,
    pub get: fn(&SkatePreferences) -> f32,
    pub set: fn(&mut SkatePreferences, f32),
}

// A preset uses the authored value when it differs from the saved release default.
macro_rules! authored_value {
    ($initial:expr) => {
        $initial
    };
    ($initial:expr, $authored:expr) => {
        $authored
    };
}

// Each numeric choice declares its storage, default, limits and UI row together.
macro_rules! skate_preferences {
    ($($field:ident: ($label:literal, $low:expr, $high:expr, $step:expr, $initial:expr $(=> $authored:expr)?, $always:literal, $group:literal)),* $(,)?) => {
        /// Saved skating preferences. Read `effective()` before applying them to a session.
        #[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
        #[serde(default)]
        pub struct SkatePreferences {
            pub mode: SkateMode,
            pub difficulty: SkateDifficulty,
            pub goofy: bool,
            pub auto_push: Option<bool>,
            pub assisted_air: Option<bool>,
            pub tight_flicks: bool,
            pub flick_120hz: bool,
            pub drift_powerslide: bool,
            pub soften: bool,
            $(pub $field: f32,)*
        }
        impl Default for SkatePreferences {
            fn default() -> Self {
                Self {
                    mode: SkateMode::Custom,
                    difficulty: SkateDifficulty::Easy,
                    goofy: true,
                    auto_push: None,
                    assisted_air: Some(false),
                    tight_flicks: false,
                    flick_120hz: true,
                    drift_powerslide: true,
                    soften: true,
                    $($field: $initial,)*
                }
            }
        }
        pub(crate) const SKATE_KNOBS: &[SkateKnob] = &[
            $(SkateKnob { label: $label, low: $low, high: $high, step: $step,
                always: $always, authored: authored_value!($initial $(, $authored)?), group: $group,
                get: |p| p.$field, set: |p, v| p.$field = v },)*
        ];
    };
}

skate_preferences! {
    trucks: ("Truck tightness", 0.0, 1.0, 0.05, 0.5, false, "Base"),
    flick_radius: ("Flick tolerance", 0.5, 2.0, 0.05, 1.0, false, "Flick-It"),
    flick_window: ("Flick time window", 0.5, 3.0, 0.05, 1.0, false, "Flick-It"),
    flick_pace: ("Flick speed for full pop", 0.5, 2.0, 0.05, 1.0, false, "Flick-It"),
    pop: ("Ollie pop", 0.5, 2.0, 0.05, 1.0 => 1.15, false, "Air"),
    boneless: ("Boneless height", 0.5, 3.0, 0.05, 1.0, false, "Air"),
    hippy: ("Hippy jump height", 0.5, 3.0, 0.05, 1.0, false, "Air"),
    gravity: ("Gravity", 0.5, 1.5, 0.05, 1.0, false, "Air"),
    spin: ("Spin speed", 0.5, 3.0, 0.05, 1.2 => 1.6, false, "Air"),
    vert_assist: ("Vert assist", 0.0, 1.0, 0.05, 0.9 => 1.0, false, "Air"),
    rail_magnetism: ("Rail magnetism", 0.25, 3.0, 0.05, 1.0, false, "Rails"),
    grind_pop: ("Grind pop", 0.5, 2.0, 0.05, 0.9 => 1.0, false, "Rails"),
    grind_friction: ("Grind friction", 0.0, 3.0, 0.05, 0.55 => 1.0, false, "Rails"),
    grind_tolerance: ("Grind balance", 0.5, 3.0, 0.05, 2.0, false, "Rails"),
    push_speed: ("Top push speed", 0.5, 2.0, 0.05, 1.0 => 1.15, false, "Rolling"),
    push_power: ("Push strength", 0.5, 3.0, 0.05, 1.0 => 1.45, false, "Rolling"),
    pump: ("Pumping", 0.0, 3.0, 0.05, 1.0, false, "Rolling"),
    bowl_boost: ("Bowl boost", 0.0, 2.0, 0.05, 1.2, true, "Rolling"),
    rolling_friction: ("Rolling resistance", 0.0, 3.0, 0.05, 1.0, false, "Rolling"),
    hill_speed: ("Hill speed", 0.0, 2.0, 0.05, 1.0, false, "Rolling"),
    braking: ("Braking", 0.25, 3.0, 0.05, 1.0, false, "Rolling"),
    steering: ("Steering", 0.5, 2.0, 0.05, 1.0, false, "Turning"),
    carve: ("Carve", 0.5, 2.0, 0.05, 1.0, false, "Turning"),
    grip: ("Wheel grip", 0.5, 2.0, 0.05, 1.0, false, "Turning"),
    powerslide: ("Powerslide bite", 0.25, 3.0, 0.05, 0.5 => 1.0, false, "Turning"),
    powerslide_turn: ("Powerslide turn", 0.25, 1.5, 0.05, 1.0, false, "Turning"),
    drift_grip: ("Drift half-tilt grip", 0.0, 1.5, 0.05, 0.3, true, "Turning"),
    drift_full_grip: ("Drift full-tilt grip", 0.0, 1.5, 0.05, 0.6, true, "Turning"),
    wobble: ("Speed wobble", 0.0, 3.0, 0.05, 1.0, false, "Balance"),
    wobble_onset: ("Wobble starts at", 0.5, 3.0, 0.05, 1.0, false, "Balance"),
    manual_drift: ("Manual drift", 0.0, 3.0, 0.05, 0.7 => 1.0, false, "Balance"),
    landing: ("Landing forgiveness", 0.5, 3.0, 0.05, 1.0, false, "Balance"),
    impact: ("Impact toughness", 0.5, 3.0, 0.05, 1.0, false, "Balance"),
    get_up_delay: ("Time down after bail", 0.25, 2.0, 0.05, 1.0, false, "Balance"),
    stick_dead_zone: ("Stick dead zone", 0.25, 0.6, 0.01, 0.25, true, "Controls"),
    stick_reach: ("Stick full tilt at", 0.6, 1.0, 0.01, 0.95, true, "Controls"),
    mouse_flick: ("Mouse flick strength", 0.25, 4.0, 0.05, 1.0, true, "Controls"),
    camera_follow: ("Camera follow speed", 1.0, 3.0, 0.05, 2.0, true, "Camera"),
    camera_distance: ("Camera distance", 0.6, 1.6, 0.05, 1.0, true, "Camera"),
    camera_fov: ("Camera FOV offset", -20.0, 20.0, 1.0, -1.0, true, "Camera"),
    camera_pullback: ("Pull-back at speed", 0.0, 1.5, 0.05, 0.8, true, "Camera"),
    wall_follow: ("Curved-wall airs", 0.0, 1.0, 0.05, 1.0, false, "Air"),
    volume: ("Skate volume", 0.0, 1.0, 0.05, 0.5, true, "Audio"),
}

impl SkatePreferences {
    /// Resolve the mode without changing the stored Custom values. Controls, camera, drift and bowl boost
    /// apply to every mode. Presets use the game's authored multipliers on their selected difficulty.
    pub fn effective(&self) -> Self {
        let mut effective = *self;
        if self.mode != SkateMode::Custom {
            for knob in SKATE_KNOBS.iter().filter(|k| !k.always) {
                (knob.set)(&mut effective, knob.authored);
            }
            effective.difficulty = match self.mode {
                SkateMode::Easy => SkateDifficulty::Easy,
                SkateMode::Normal => SkateDifficulty::Normal,
                SkateMode::Hardcore => SkateDifficulty::Hardcore,
                SkateMode::Custom => unreachable!(),
            };
            effective.auto_push = None;
            effective.assisted_air = None;
        }
        effective
    }

    /// Refuse invalid preferences before changing a live session.
    pub fn validate(&self) -> Result<(), String> {
        for knob in SKATE_KNOBS {
            let value = (knob.get)(self);
            if !value.is_finite() || !(knob.low..=knob.high).contains(&value) {
                return Err(format!("Invalid skating preference: {}", knob.label));
            }
        }
        if self.stick_reach < self.stick_dead_zone + 0.2 {
            return Err("Stick full tilt must exceed its dead zone by at least 0.2".into());
        }
        Ok(())
    }

    /// Keep edited files within the same bounds as the menu, without discarding unrelated settings.
    pub(crate) fn sanitize(&mut self) {
        let defaults = Self::default();
        for knob in SKATE_KNOBS {
            let value = (knob.get)(self);
            (knob.set)(self, if value.is_finite() { value.clamp(knob.low, knob.high) } else { (knob.get)(&defaults) });
        }
        self.stick_reach = self.stick_reach.max(self.stick_dead_zone + 0.2).min(1.0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Settings;

    #[test]
    fn old_and_partial_settings_keep_new_defaults_and_round_trip() {
        let old: Settings = serde_json::from_str(r#"{"volume":0.4}"#).unwrap();
        assert_eq!(old.volume, 0.4);
        assert_eq!(old.skate, SkatePreferences::default());
        let partial: Settings = serde_json::from_str(r#"{"skate":{"gravity":0.8,"goofy":false}}"#).unwrap();
        assert_eq!(partial.skate.gravity, 0.8);
        assert!(!partial.skate.goofy);
        assert_eq!(partial.skate.pop, 1.0);
        let json = serde_json::to_string(&partial).unwrap();
        assert_eq!(serde_json::from_str::<Settings>(&json).unwrap(), partial);
        assert!(partial.skate.validate().is_ok());
    }

    #[test]
    fn release_defaults_have_typed_skating_values() {
        let prefs = SkatePreferences::default();
        assert_eq!(prefs.mode, SkateMode::Custom);
        assert_eq!(prefs.difficulty, SkateDifficulty::Easy);
        assert!(prefs.goofy && prefs.flick_120hz && prefs.soften);
        assert!(!prefs.tight_flicks);
        assert_eq!(prefs.auto_push, None);
        assert_eq!(prefs.assisted_air, Some(false));
        assert_eq!(prefs.pop, 1.0);
        assert_eq!(prefs.spin, 1.2);
        assert_eq!(prefs.vert_assist, 0.9);
        assert_eq!(prefs.grind_pop, 0.9);
        assert_eq!(prefs.grind_friction, 0.55);
        assert_eq!(prefs.push_speed, 1.0);
        assert_eq!(prefs.push_power, 1.0);
        assert_eq!(prefs.bowl_boost, 1.2);
        assert_eq!(prefs.powerslide, 0.5);
        assert_eq!(prefs.manual_drift, 0.7);
        assert_eq!(prefs.camera_fov, -1.0);
        assert_eq!(prefs.volume, 0.5);
        assert!(prefs.validate().is_ok());
    }

    #[test]
    fn presets_preserve_custom_values_and_every_mode_choices() {
        let mut prefs = SkatePreferences {
            pop: 1.75,
            gravity: 0.8,
            camera_distance: 1.4,
            bowl_boost: 1.8,
            auto_push: Some(false),
            assisted_air: Some(true),
            ..Default::default()
        };
        for (mode, difficulty) in [
            (SkateMode::Easy, SkateDifficulty::Easy),
            (SkateMode::Normal, SkateDifficulty::Normal),
            (SkateMode::Hardcore, SkateDifficulty::Hardcore),
        ] {
            prefs.mode = mode;
            let effective = prefs.effective();
            assert_eq!(effective.difficulty, difficulty);
            assert_eq!(effective.pop, 1.15);
            assert_eq!(effective.spin, 1.6);
            assert_eq!(effective.push_speed, 1.15);
            assert_eq!(effective.push_power, 1.45);
            assert_eq!(effective.vert_assist, 1.0);
            assert_eq!(effective.grind_pop, 1.0);
            assert_eq!(effective.grind_friction, 1.0);
            assert_eq!(effective.powerslide, 1.0);
            assert_eq!(effective.manual_drift, 1.0);
            assert_eq!(effective.gravity, 1.0);
            assert_eq!(effective.camera_distance, 1.4);
            assert_eq!(effective.camera_fov, -1.0);
            assert_eq!(effective.bowl_boost, 1.8);
            assert_eq!(effective.volume, 0.5);
            assert!(effective.goofy && effective.flick_120hz && effective.soften);
            assert!(!effective.tight_flicks);
            assert_eq!(effective.auto_push, None);
            assert_eq!(effective.assisted_air, None);
            assert_eq!(prefs.pop, 1.75);
        }
        prefs.mode = SkateMode::Custom;
        assert_eq!(prefs.effective(), prefs);
    }

    #[test]
    fn saved_values_cannot_break_stick_conditioning_or_session_ranges() {
        let mut prefs = SkatePreferences { gravity: 9.0, stick_dead_zone: 0.6, stick_reach: 0.6, ..Default::default() };
        assert!(prefs.validate().is_err());
        prefs.sanitize();
        assert_eq!(prefs.gravity, 1.5);
        assert_eq!(prefs.stick_reach, 0.8);
        assert!(prefs.validate().is_ok());
        assert!(SkatePreferences::default().flick_120hz);
    }
}
