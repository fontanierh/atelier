//! Host observations of native scoring, intentional ground pumps and rider-root spin; never score or move bodies.
use super::Session;
use crate::core::player::state::PhysicalStateId;
use bevy::prelude::*;

/// Retained fixed-tick observations. Display text uses authored scorer names, never input-based trick guesses.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct SkateTelemetry {
    pub display_trick: String,
    pub announcements: u32,
    pub start_switch: bool,
    pub start_fakie: bool,
    pub spin_degrees: f32,
    pub spin_half_turns: u32,
    pub spin_frontside: bool,
    pub pumps: u32,
    pub pump_gain: f32,
    pub pump_line: u32,
    pub pump_alone: bool,
    pub boost_total: f32,
}

#[derive(Default)]
pub(super) struct Observer {
    pub output: SkateTelemetry,
    pub goofy: bool,
    hidden_announcements: Option<u32>,
    pumps: Pumps,
    spin: f32,
    forward: Option<Vec3>,
    was_air: bool,
    spin_of: String,
    pumps_seen: u32,
    pump_of: String,
    fade: f32,
    previous_trick: String,
    previous_score: f32,
    marker_returns: u64,
}

pub(super) struct Observation<'a> {
    pub dt: f32,
    pub state: PhysicalStateId,
    pub root: Mat4,
    pub pumping_time: f32,
    pub intentional: bool,
    pub pump_acceleration: f32,
    pub announcements: u32,
    pub start_stance: [bool; 2],
    pub trick: &'a str,
    pub score: f32,
    pub manual: f32,
    pub boost_total: f32,
}

impl Observer {
    pub fn reset(&mut self, announcements: u32) {
        let goofy = self.goofy;
        *self = Self { goofy, hidden_announcements: Some(announcements), ..Default::default() };
    }
    fn returned_to_marker(&mut self, returns: u64, announcements: u32) {
        if self.marker_returns == returns {
            return;
        }
        self.marker_returns = returns;
        self.hidden_announcements = Some(announcements);
        self.output.display_trick.clear();
        self.output.spin_half_turns = 0;
        self.output.spin_degrees = 0.;
        self.output.pump_line = 0;
        self.pumps_seen = self.pumps.count;
        self.pump_of.clear();
        self.spin_of.clear();
        self.spin = 0.;
        self.was_air = false;
        self.forward = None;
        self.fade = 0.;
    }
    pub fn observe(&mut self, frame: Observation<'_>) {
        let ground = matches!(frame.state, PhysicalStateId::PhysicsGround | PhysicalStateId::RevertGround);
        let air = matches!(
            frame.state,
            PhysicalStateId::PhysicsAir
                | PhysicalStateId::KnownAir
                | PhysicalStateId::PhysicsAirSecondary
                | PhysicalStateId::BipedAir
        );
        let grind = frame.state.is_grind();
        self.pumps.observe(ground, frame.pumping_time, frame.intentional, frame.pump_acceleration, frame.dt);
        self.output.announcements = frame.announcements;
        [self.output.start_switch, self.output.start_fakie] = frame.start_stance;
        self.output.pumps = self.pumps.count;
        self.output.pump_gain = self.pumps.last_gain;
        self.output.boost_total = frame.boost_total;
        if self.hidden_announcements.is_some_and(|count| count != frame.announcements) {
            self.hidden_announcements = None;
        }
        let trick = if self.hidden_announcements.is_some() {
            String::new()
        } else {
            trick_label(frame.trick, frame.start_stance)
        };
        self.fade = (self.fade - frame.dt).max(0.);
        let up = frame.root.y_axis.truncate().normalize_or_zero();
        let raw_forward = frame.root.z_axis.truncate();
        let forward = (raw_forward - up * raw_forward.dot(up)).normalize_or_zero();
        if air {
            if !self.was_air {
                self.spin = 0.;
                self.output.spin_half_turns = 0;
                self.spin_of.clear();
            } else if let Some(previous) = self.forward {
                let previous = (previous - up * previous.dot(up)).normalize_or_zero();
                if previous != Vec3::ZERO && forward != Vec3::ZERO {
                    // The host world is a reflection of the simulation, so signed axial angles reverse.
                    self.spin -= up.dot(previous.cross(forward)).atan2(previous.dot(forward)).to_degrees();
                }
            }
            self.output.spin_degrees = self.spin;
        } else if self.was_air {
            let spun = self.spin.abs();
            if ground && spun >= 150. {
                self.output.spin_half_turns = (((spun - 30.) / 180. + 0.0001).round() as u32).max(1);
                let stance = if self.goofy != frame.start_stance[0] { -1. } else { 1. };
                let travel = if frame.start_stance[1] { -1. } else { 1. };
                self.output.spin_frontside = self.spin * stance * travel < 0.;
                self.spin_of = trick.clone();
            }
            self.spin = 0.;
        }
        self.forward = Some(forward);
        self.was_air = air;
        if trick != self.spin_of {
            self.output.spin_half_turns = 0;
        }
        let mut shown = trick.clone();
        if self.output.spin_half_turns != 0 {
            let label = format!(
                "{} {}",
                if self.output.spin_frontside { "FS" } else { "BS" },
                self.output.spin_half_turns * 180
            );
            shown = if shown.is_empty() { label } else { format!("{shown} / {label}") };
        }
        if self.pumps.count < self.pumps_seen {
            self.pumps_seen = self.pumps.count;
        }
        if self.pumps.count > self.pumps_seen {
            let faded = self.fade <= 0.;
            if faded || self.output.pump_line == 0 || trick != self.pump_of {
                self.output.pump_line = 0;
                self.pump_of = trick.clone();
                self.output.pump_alone = faded;
            }
            self.output.pump_line += self.pumps.count - self.pumps_seen;
            self.pumps_seen = self.pumps.count;
        }
        if trick != self.pump_of {
            self.output.pump_line = 0;
        }
        if self.output.pump_line != 0 {
            let label =
                if self.output.pump_line > 1 { format!("Pump x{}", self.output.pump_line) } else { "Pump".into() };
            shown = if self.output.pump_alone || shown.is_empty() { label } else { format!("{shown} + {label}") };
        }
        if shown != self.previous_trick
            || frame.score.round() != self.previous_score.round()
            || air
            || grind
            || (ground && frame.manual.abs() > 0.0001)
        {
            self.fade = 1.5;
        }
        self.previous_trick = shown.clone();
        self.previous_score = frame.score;
        self.output.display_trick = shown;
    }
}

#[derive(Default)]
struct Pumps {
    count: u32,
    gain: f32,
    last_gain: f32,
    quiet: f32,
    counted: bool,
}
impl Pumps {
    fn observe(&mut self, ground: bool, pumping_time: f32, intentional: bool, acceleration: f32, dt: f32) {
        if !ground || pumping_time <= 0. {
            self.quiet += dt;
            if !ground || self.quiet >= 0.25 {
                self.gain = 0.;
                self.counted = false;
            }
            return;
        }
        self.quiet = 0.;
        if intentional {
            self.gain += acceleration;
        }
        if !self.counted && self.gain >= 0.5 {
            self.count = self.count.wrapping_add(1);
            self.last_gain = self.gain;
            self.counted = true;
        }
    }
}

fn trick_label(name: &str, stance: [bool; 2]) -> String {
    let mut name = name.strip_prefix("ID_TRICK_").unwrap_or(name);
    for prefix in ["GROUND_TRICK_", "FLIP_", "GRIND_", "GRAB_"] {
        name = name.strip_prefix(prefix).unwrap_or(name);
    }
    let mut label = name
        .split('_')
        .map(|word| {
            if matches!(word, "FS" | "BS") {
                word.into()
            } else {
                let mut chars = word.chars();
                match chars.next() {
                    Some(first) => first.to_uppercase().collect::<String>() + &chars.as_str().to_lowercase(),
                    None => String::new(),
                }
            }
        })
        .collect::<Vec<_>>()
        .join(" ");
    if !label.is_empty() && (stance[0] || stance[1]) {
        label = format!("{} {label}", if stance[1] { "Fakie" } else { "Switch" });
    }
    label
}

impl Session {
    pub fn telemetry(&self) -> SkateTelemetry {
        self.observer.output.clone()
    }
    pub(super) fn observe_telemetry(&mut self) {
        let (announcements, start_stance) = self.skater.scoring.announcement();
        self.observer.returned_to_marker(self.markers.status().returns, announcements);
        let (score, _, _) = self.score();
        let pump = &self.skater.ground.pumping;
        let observation = Observation {
            dt: self.period(),
            state: self.skater.player_state.current(),
            root: crate::animation::native_matrix(self.skater.animated_skeleton.roots.animation_to_world),
            pumping_time: pump.pumping_time,
            intentional: pump.intentional_pumping != 0,
            pump_acceleration: pump.pump_acceleration,
            announcements,
            start_stance,
            trick: self.skater.scoring.current_trick(),
            score,
            manual: self.manual_balance(),
            boost_total: self.boost.total,
        };
        self.observer.observe(observation);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn intentional_pumps_count_once_and_join_only_short_ground_pauses() {
        let mut p = Pumps::default();
        for _ in 0..60 {
            p.observe(true, 1., false, 1., 1. / 60.);
        }
        assert_eq!(p.count, 0, "coasting or slope acceleration must not be called pumping");
        p.observe(true, 1., true, 0.3, 1. / 60.);
        p.observe(true, 0., false, 0., 0.2);
        p.observe(true, 1., true, 0.2, 1. / 60.);
        assert_eq!(p.count, 1);
        for _ in 0..60 {
            p.observe(true, 1., true, 0.1, 1. / 60.);
        }
        assert_eq!(p.count, 1, "one continuing rise counts only once");
        p.observe(true, 0., false, 0., 0.25);
        p.observe(true, 1., true, 0.5, 1. / 60.);
        assert_eq!(p.count, 2);
        p.observe(false, 1., true, 5., 1. / 60.);
        p.observe(true, 1., true, 0.5, 1. / 60.);
        assert_eq!(p.count, 3, "air ends a rise, even if brief");
    }
    fn frame() -> Observation<'static> {
        Observation {
            dt: 1. / 60.,
            state: PhysicalStateId::PhysicsGround,
            root: Mat4::IDENTITY,
            pumping_time: 0.,
            intentional: false,
            pump_acceleration: 0.,
            announcements: 1,
            start_stance: [false; 2],
            trick: "ID_TRICK_FLIP_KICKFLIP",
            score: 100.,
            manual: 0.,
            boost_total: 0.,
        }
    }
    #[test]
    fn root_spin_not_board_spin_labels_with_carrier_start_stance_and_retains_landing() {
        for (stance, goofy, expected_fs) in [
            ([false, false], false, true),
            ([true, false], false, false),
            ([false, true], false, false),
            ([false, false], true, false),
        ] {
            let mut o = Observer { goofy, ..Default::default() };
            for tick in 0..=12 {
                o.observe(Observation {
                    state: PhysicalStateId::PhysicsAir,
                    root: Mat4::from_rotation_y(tick as f32 * std::f32::consts::PI / 12.),
                    start_stance: stance,
                    ..frame()
                });
            }
            o.observe(Observation { start_stance: stance, ..frame() });
            assert_eq!(o.output.spin_half_turns, 1);
            assert_eq!(o.output.spin_frontside, expected_fs);
            assert!(o.output.display_trick.contains(if expected_fs { "FS 180" } else { "BS 180" }));
            o.observe(Observation { start_stance: stance, ..frame() });
            assert_eq!(o.output.spin_half_turns, 1);
            o.observe(Observation { trick: "ID_TRICK_FLIP_HEELFLIP", start_stance: stance, ..frame() });
            assert_eq!(o.output.spin_half_turns, 0);
        }
    }
    #[test]
    fn pumps_join_the_current_line_then_start_alone_after_fade_and_reset_hides_stale_names() {
        let mut o = Observer::default();
        o.observe(frame());
        o.observe(Observation { pumping_time: 1., intentional: true, pump_acceleration: 0.5, ..frame() });
        assert_eq!(o.output.display_trick, "Kickflip + Pump");
        o.observe(Observation { dt: 0.25, ..frame() });
        o.observe(Observation { pumping_time: 1., intentional: true, pump_acceleration: 0.5, ..frame() });
        assert_eq!(o.output.display_trick, "Kickflip + Pump x2");
        o.observe(Observation { dt: 2., ..frame() });
        o.observe(Observation {
            pumping_time: 1.,
            intentional: true,
            pump_acceleration: 0.5,
            boost_total: 8.,
            ..frame()
        });
        assert_eq!(o.output.display_trick, "Pump");
        assert_eq!(o.output.pumps, 3);
        assert_eq!(o.output.boost_total, 8.);
        o.returned_to_marker(1, 1);
        o.observe(frame());
        assert_eq!(o.output.pumps, 3, "marker return hides the line without erasing the session observer count");
        assert!(o.output.display_trick.is_empty());
        o.observe(Observation { announcements: 2, start_stance: [true, true], ..frame() });
        assert_eq!(o.output.display_trick, "Fakie Kickflip");
        o.reset(1);
        o.observe(frame());
        assert!(o.output.display_trick.is_empty());
        o.observe(Observation { announcements: 2, start_stance: [true, true], ..frame() });
        assert_eq!(o.output.display_trick, "Fakie Kickflip");
    }
}
