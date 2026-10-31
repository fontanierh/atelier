//! Board audio follows solved tick publications, not debug state names or render-frame edges.
use crate::soften::{BoardSource, VoicePreferences};
use crate::sound::{Dice, Sound, Takes};
use bevy::audio::{AddAudioSource, Volume};
use bevy::prelude::*;
use hakuba_screens::{Pause, Screen};
use hakuba_settings::Settings;
use hakuba_skate::{AudioEvent, AudioEventKind, AudioFrame, AudioMode, SkateStatus};

pub(super) struct SkateSoundsPlugin;
impl Plugin for SkateSoundsPlugin {
    fn build(&self, app: &mut App) {
        app.add_audio_source::<BoardSource>()
            .init_resource::<VoicePreferences>()
            .add_systems(Startup, load)
            .add_systems(OnEnter(Screen::World), begin)
            .add_systems(Update, preferences)
            .add_systems(PostUpdate, (loops, hear).chain().run_if(in_state(Screen::World)));
    }
}
const ROLL: [&str; 8] = [
    "skate-roll",
    "skate-roll-wood",
    "skate-roll-metal",
    "skate-roll-asphalt",
    "skate-roll-stone",
    "skate-roll-dirt",
    "skate-roll-grass",
    "skate-roll-sand",
];
const CONTACT: [&str; 4] = ["skate-grind", "skate-slide", "skate-skid", "skate-scrape"];
const POP: [&str; 8] = [
    "skate-pop",
    "skate-pop-wood",
    "skate-pop-metal",
    "skate-pop",
    "skate-pop",
    "skate-pop-dirt",
    "skate-pop-grass",
    "skate-pop-sand",
];
const LAND: [&str; 8] = [
    "skate-land",
    "skate-land-wood",
    "skate-land-metal",
    "skate-land",
    "skate-land",
    "skate-land-dirt",
    "skate-land-grass",
    "skate-land-sand",
];
#[derive(Resource)]
struct BoardSounds {
    roll: Vec<Sound>,
    contact: Vec<Sound>,
    pop: Vec<Sound>,
    land: Vec<Sound>,
    clatter: Sound,
}
impl BoardSounds {
    fn all(&self) -> impl Iterator<Item = &Sound> {
        self.roll.iter().chain(&self.contact).chain(&self.pop).chain(&self.land).chain([&self.clatter])
    }
}
#[derive(Component)]
struct BoardLoop {
    kind: usize,
    envelope: f32,
}
#[derive(Resource)]
struct Pending;
#[derive(Component)]
struct Preparing;
fn preferences(settings: Res<Settings>, preferences: Res<VoicePreferences>) {
    preferences.set(settings.skate.soften, settings.skate.volume);
}
fn load(mut commands: Commands, assets: Res<AssetServer>) {
    let family = |names: &[&str]| names.iter().map(|name| Sound::load(&assets, name)).collect();
    commands.insert_resource(BoardSounds {
        roll: family(&ROLL),
        contact: family(&CONTACT),
        pop: family(&POP),
        land: family(&LAND),
        clatter: Sound::load(&assets, "skate-clatter"),
    });
}
fn begin(mut commands: Commands, settings: Res<Settings>, preferences: Res<VoicePreferences>) {
    // Set the shared processor before any loop or one-shot decoder can start.
    preferences.set(settings.skate.soften, settings.skate.volume);
    commands.insert_resource(Pending);
    commands.spawn((Preparing, hakuba_world::Unready, DespawnOnExit(Screen::World)));
}
#[allow(clippy::too_many_arguments)]
fn loops(
    mut commands: Commands,
    pending: Option<Res<Pending>>,
    mut sounds: ResMut<BoardSounds>,
    takes: Res<Assets<Takes>>,
    assets: Res<AssetServer>,
    audio: Res<Assets<AudioSource>>,
    mut board_sources: ResMut<Assets<BoardSource>>,
    preferences: Res<VoicePreferences>,
    waiting: Query<Entity, With<Preparing>>,
) {
    if pending.is_none() {
        return;
    }
    if sounds.all().any(|s| s.failed(&assets)) {
        error!("A skating sound failed to load; board audio disabled (see named asset error)");
        commands.remove_resource::<Pending>();
        for entity in &waiting {
            commands.entity(entity).despawn();
        }
        return;
    }
    if !sounds.all().all(|s| s.ready(&assets, &takes)) {
        return;
    }
    let BoardSounds { roll, contact, pop, land, clatter } = &mut *sounds;
    for sound in roll.iter_mut().chain(contact.iter_mut()).chain(pop.iter_mut()).chain(land.iter_mut()).chain([clatter])
    {
        if !sound.board_source(&audio, &mut board_sources, &preferences) {
            return;
        }
    }
    for (kind, sound) in sounds.roll.iter().chain(&sounds.contact).enumerate() {
        sound.spawn_loops(&mut commands, &takes, move |_| BoardLoop { kind, envelope: 0. });
    }
    commands.remove_resource::<Pending>();
    for entity in &waiting {
        commands.entity(entity).despawn();
    }
}
#[allow(clippy::too_many_arguments)]
fn hear(
    mut commands: Commands,
    status: Res<SkateStatus>,
    settings: Res<Settings>,
    pause: Res<State<Pause>>,
    time: Res<Time>,
    mut sounds: ResMut<BoardSounds>,
    takes: Res<Assets<Takes>>,
    mut dice: ResMut<Dice>,
    mut sinks: Query<(&mut BoardLoop, &mut AudioSink)>,
    mut events: MessageReader<AudioEvent>,
) {
    let playing = *pause.get() == Pause::Playing && status.active && !status.waiting_for_collision;
    let frame = if playing { status.audio } else { AudioFrame::default() };
    let levels = loop_levels(frame);
    for (mut marker, mut sink) in &mut sinks {
        let (target, pitch) = levels[marker.kind];
        let rate = if target > marker.envelope { 30. } else { 10. };
        marker.envelope += (target - marker.envelope) * (time.delta_secs() * rate).min(1.);
        sink.set_volume(Volume::Linear(marker.envelope * settings.volume));
        sink.set_speed(pitch);
    }
    // Always drain messages while paused or unloaded, so an old attack cannot play on resume.
    for event in events.read() {
        if !playing {
            continue;
        }
        let surface = surface_index(event.surface);
        let (sound, gain) = match event.kind {
            AudioEventKind::Pop => (&mut sounds.pop[surface], 0.7),
            AudioEventKind::Land => (&mut sounds.land[surface], 0.8),
            AudioEventKind::Clatter => (&mut sounds.clatter, 0.9),
        };
        sound.play(&mut commands, &takes, &mut dice, gain * settings.volume, 1.);
    }
}
fn surface_index(surface: u16) -> usize {
    usize::from(surface.saturating_sub(1)).min(7)
}
/// Envelope targets remain independent from preferences, so gain changes never compound them.
fn loop_levels(frame: AudioFrame) -> [(f32, f32); 12] {
    let mut levels = [(0., 1.); 12];
    let speed = frame.speed_mps;
    let roll_pitch = 0.75 + 0.45 * (speed / 10.).clamp(0., 1.);
    for level in &mut levels[..8] {
        level.1 = roll_pitch;
    }
    match frame.mode {
        AudioMode::Roll => levels[surface_index(frame.surface)].0 = (speed / 4.5).clamp(0., 1.) * 0.85,
        AudioMode::Grind => levels[8] = (0.8 * (speed / 3.).clamp(0.45, 1.), 0.85 + 0.3 * (speed / 8.).clamp(0., 1.)),
        AudioMode::Slide => levels[9] = (0.85 * (speed / 3.).clamp(0.45, 1.), 0.9 + 0.2 * (speed / 8.).clamp(0., 1.)),
        AudioMode::Skid => {
            levels[10] = (
                0.9 * (speed / 4.).clamp(0., 1.) * frame.slide_angle_degrees / 82.,
                0.9 + 0.3 * (speed / 8.).clamp(0., 1.),
            )
        }
        AudioMode::Silent => {}
    }
    if frame.braking {
        levels[11].0 = 0.7 * (speed / 3.).clamp(0.3, 1.);
    }
    levels
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn surface_families_and_all_solved_modes_have_real_outputs() {
        for surface in 1..=8 {
            let levels =
                loop_levels(AudioFrame { mode: AudioMode::Roll, surface, speed_mps: 6., ..Default::default() });
            assert!(levels[surface_index(surface)].0 > 0.);
            assert_eq!(levels.iter().filter(|l| l.0 > 0.).count(), 1);
            assert_eq!(
                POP[surface_index(surface)],
                match surface {
                    2 => "skate-pop-wood",
                    3 => "skate-pop-metal",
                    6 => "skate-pop-dirt",
                    7 => "skate-pop-grass",
                    8 => "skate-pop-sand",
                    _ => "skate-pop",
                }
            );
        }
        for (mode, kind) in [(AudioMode::Grind, 8), (AudioMode::Slide, 9), (AudioMode::Skid, 10)] {
            assert!(
                loop_levels(AudioFrame { mode, speed_mps: 6., slide_angle_degrees: 45., ..Default::default() })[kind].0
                    > 0.
            );
        }
        assert!(
            loop_levels(AudioFrame { mode: AudioMode::Roll, braking: true, speed_mps: 3., ..Default::default() })[11].0
                > 0.
        );
        assert!(loop_levels(AudioFrame::default()).iter().all(|l| l.0 == 0.));
    }
}
