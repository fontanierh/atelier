//! Solved board audio publication. Each tick owns its transients; the host forwards every tick before rendering.
use super::Session;
use crate::core::{physics::board::BodyId, player::state::PhysicalStateId as S};
use bevy::prelude::Message;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum AudioMode {
    #[default]
    Silent,
    Roll,
    Grind,
    Slide,
    Skid,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct AudioFrame {
    pub mode: AudioMode,
    pub surface: u16,
    pub speed_mps: f32,
    pub slide_angle_degrees: f32,
    pub braking: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AudioEventKind {
    Pop,
    Land,
    Clatter,
}

/// A one-shot from a completed simulation tick, never a rendered-frame state comparison.
#[derive(Message, Clone, Copy, Debug, PartialEq, Eq)]
pub struct AudioEvent {
    pub tick: u64,
    pub kind: AudioEventKind,
    pub surface: u16,
}

#[derive(Clone, Copy)]
struct Observation {
    state: S,
    wheels: u32,
    frame: AudioFrame,
}
#[derive(Default)]
pub(super) struct Publication {
    frame: AudioFrame,
    previous: Option<Observation>,
    airborne: bool,
    events: Vec<AudioEvent>,
}
impl Publication {
    fn publish(&mut self, tick: u64, observation: Observation) {
        self.events.clear();
        if let Some(previous) = self.previous {
            let air = |s| matches!(s, S::PhysicsAir | S::PhysicsAirSecondary | S::KnownAir);
            let ground = |s| matches!(s, S::PhysicsGround | S::SlideGround | S::RevertGround | S::GroundAnimation);
            if air(observation.state) && ground(previous.state) {
                self.events.push(AudioEvent { tick, kind: AudioEventKind::Pop, surface: previous.frame.surface });
            }
            if observation.wheels > 0 && ground(observation.state) && self.airborne {
                self.events.push(AudioEvent { tick, kind: AudioEventKind::Land, surface: observation.frame.surface });
                self.airborne = false;
            }
            if air(observation.state) {
                self.airborne = true;
            }
            if observation.state == S::WipeoutGround || observation.state == S::Teleporting {
                self.airborne = false;
            }
            if observation.state == S::WipeoutGround && previous.state != S::WipeoutGround {
                self.events.push(AudioEvent {
                    tick,
                    kind: AudioEventKind::Clatter,
                    surface: observation.frame.surface,
                });
            }
        }
        self.frame = observation.frame;
        self.previous = Some(observation);
    }
}

impl Session {
    pub fn audio(&self) -> AudioFrame {
        self.audio.frame
    }
    /// Valid until the next tick. Forward each tick to the presentation message stream.
    pub fn audio_events(&self) -> &[AudioEvent] {
        &self.audio.events
    }
    /// A placement or activation is not an audible takeoff or landing.
    pub fn reset_audio(&mut self) {
        self.audio = Publication::default();
        self.publish_audio();
        self.audio.events.clear();
    }
    pub(super) fn publish_audio(&mut self) {
        let state = self.skater.player_state.current();
        let surface = self.surface();
        let deck = self.physics.board.part_transforms()[BodyId::Deck.index()];
        let velocity = self.physics.board.bodies()[BodyId::Deck.index()].rates.linear_velocity;
        let speed = (velocity.x * velocity.x + velocity.y * velocity.y + velocity.z * velocity.z).sqrt();
        let forward = deck.basis.columns[2];
        let flat_speed = velocity.x.hypot(velocity.z);
        let flat_forward = forward[0].hypot(forward[2]);
        let angle = if flat_speed > 0. && flat_forward > 0. {
            ((velocity.x * forward[0] + velocity.z * forward[2]).abs() / (flat_speed * flat_forward))
                .clamp(0., 1.)
                .acos()
                .to_degrees()
        } else {
            0.
        };
        let mode = contact_mode(
            state,
            surface.wheels,
            self.skater.grind.active_family().is_some() && self.skater.player_input.physical.grinds.grinding_316 != 0,
        );
        let braking = mode == AudioMode::Roll && self.skater.player_input.processed.flags_2468 & 0x2000_0000 != 0;
        self.audio.publish(
            self.physics.ticks,
            Observation {
                state,
                wheels: surface.wheels,
                frame: AudioFrame {
                    mode,
                    surface: surface.sound as u16,
                    speed_mps: speed,
                    slide_angle_degrees: angle,
                    braking,
                },
            },
        );
    }
}
fn contact_mode(state: S, wheels: u32, grind_contact: bool) -> AudioMode {
    match state {
        S::GrindBoardslide | S::GrindTipslide | S::GrindDarkslide if grind_contact => AudioMode::Slide,
        s if s.is_grind() && grind_contact => AudioMode::Grind,
        S::SlideGround if wheels > 0 => AudioMode::Skid,
        S::PhysicsGround | S::RevertGround | S::GroundAnimation if wheels > 0 => AudioMode::Roll,
        _ => AudioMode::Silent,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn observation(state: S, wheels: u32, surface: u16) -> Observation {
        Observation {
            state,
            wheels,
            frame: AudioFrame { surface, mode: contact_mode(state, wheels, state.is_grind()), ..Default::default() },
        }
    }
    #[test]
    fn modes_require_solved_support_and_preserve_slide_families() {
        assert_eq!(contact_mode(S::SlideGround, 4, false), AudioMode::Skid);
        assert_eq!(contact_mode(S::SlideGround, 0, false), AudioMode::Silent);
        assert_eq!(contact_mode(S::PhysicsGround, 4, false), AudioMode::Roll);
        assert_eq!(contact_mode(S::GrindBoardslide, 0, true), AudioMode::Slide);
        assert_eq!(contact_mode(S::GrindFiftyFifty, 0, true), AudioMode::Grind);
        assert_eq!(contact_mode(S::GrindFiftyFifty, 0, false), AudioMode::Silent);
        assert_eq!(contact_mode(S::WipeoutGround, 4, false), AudioMode::Silent);
    }
    #[test]
    fn host_receives_pop_and_land_on_separate_ticks_in_one_render_frame() {
        let mut publication = Publication::default();
        let mut host = Vec::new();
        publication.publish(10, observation(S::GroundAnimation, 4, 2));
        assert!(publication.events.is_empty());
        publication.publish(11, observation(S::PhysicsAir, 0, 0));
        host.extend_from_slice(&publication.events);
        publication.publish(12, observation(S::PhysicsGround, 4, 3));
        host.extend_from_slice(&publication.events);
        assert_eq!(
            host,
            vec![
                AudioEvent { tick: 11, kind: AudioEventKind::Pop, surface: 2 },
                AudioEvent { tick: 12, kind: AudioEventKind::Land, surface: 3 }
            ]
        );
        publication.publish(13, observation(S::PhysicsGround, 4, 3));
        assert!(publication.events.is_empty());
    }
    #[test]
    fn no_fake_pop_from_offboard_or_cuts_and_clatter_fires_once() {
        let mut publication = Publication::default();
        publication.publish(0, observation(S::BipedGround, 0, 1));
        publication.publish(1, observation(S::BipedAir, 0, 1));
        assert!(publication.events.is_empty());
        publication.publish(2, observation(S::WipeoutGround, 0, 1));
        assert_eq!(publication.events[0].kind, AudioEventKind::Clatter);
        publication.publish(3, observation(S::WipeoutGround, 0, 1));
        assert!(publication.events.is_empty());
    }

    #[test]
    fn exported_session_publishes_takeoff_landing_and_surface_at_each_fixed_tick() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../assets/simulations/skate-simulation/skate-simulation.skatepack");
        let resources = crate::PreparedResources::from_bytes(std::fs::read(path).unwrap()).unwrap();
        let floor = vec![
            [[-500., 0., -500.], [-500., 0., 500.], [500., 0., 500.]],
            [[-500., 0., -500.], [500., 0., 500.], [500., 0., -500.]],
        ];
        let mut session = Session::from_resources(&resources, floor, vec![130; 2], vec![], [0.; 3], 0.).unwrap();
        session.configure("normal", false, 0.5).unwrap();
        session.activate([0.; 3], 0.).unwrap();
        assert!(session.audio_events().is_empty(), "activation is silent");
        let mut host = Vec::new();
        let mut rolling = false;
        // Two complete simulation ticks per host frame. Every event is copied before the next tick.
        for frame in 0..240 {
            for _ in 0..2 {
                let right = if (100..112).contains(&frame) {
                    [0, -32767]
                } else if frame == 112 {
                    [0, 32767]
                } else {
                    [0; 2]
                };
                session
                    .tick(super::super::Controls {
                        buttons: if (30..95).contains(&frame) { 0x1000 } else { 0 },
                        right,
                        ..Default::default()
                    })
                    .unwrap();
                rolling |= session.audio().mode == AudioMode::Roll;
                host.extend_from_slice(session.audio_events());
            }
        }
        assert!(rolling);
        for kind in [AudioEventKind::Pop, AudioEventKind::Land] {
            let events: Vec<_> = host.iter().filter(|event| event.kind == kind).collect();
            assert!(!events.is_empty(), "missing {kind:?}");
            assert!(
                events.iter().all(|event| event.surface == 2),
                "native wood vote must reach each attack: {events:?}"
            );
        }
    }
}
