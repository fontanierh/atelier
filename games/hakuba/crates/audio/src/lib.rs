//! The sounds: the player's footsteps on what each foot lands on, the landings, the bursts
//! of air of the double jump, the dodges and the paraglider opening, the wind while gliding, and the countryside
//! around the world. Every sound is from `assets/sounds`, at the volume the settings choose.
//!
//! Nothing plays before the world opens, which takes a click or a key on the menu: browsers keep a page silent until
//! then.

mod moves;
mod skate;
mod soften;
mod sound;

use bevy::audio::Volume;
use bevy::prelude::*;
use bevy::transform::TransformSystems;
use hakuba_screens::Screen;
use hakuba_settings::Settings;

use sound::{Sound, Takes};

pub struct SoundsPlugin;

impl Plugin for SoundsPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((sound::TakesPlugin, skate::SkateSoundsPlugin))
            .add_systems(Startup, load)
            .add_systems(OnEnter(Screen::World), |mut commands: Commands| commands.insert_resource(Pending))
            .add_systems(
                PostUpdate,
                (spawn_loops, moves::hear, moves::wind, play_countryside)
                    .chain()
                    .after(TransformSystems::Propagate)
                    .run_if(in_state(Screen::World)),
            );
    }
}

/// The countryside around the player: birdsong, a breeze and a faint distant sea, at half its recorded loudness.
const COUNTRYSIDE_VOLUME: f32 = 0.5;

/// Every sound the game plays.
#[derive(Resource)]
struct Sounds {
    grass: Sound,
    gravel: Sound,
    stone: Sound,
    dash: Sound,
    countryside: Sound,
    wind: Sound,
}

fn load(mut commands: Commands, assets: Res<AssetServer>) {
    commands.insert_resource(Sounds {
        grass: Sound::load(&assets, "footstep-grass"),
        gravel: Sound::load(&assets, "footstep-gravel"),
        stone: Sound::load(&assets, "footstep-stone"),
        dash: Sound::load(&assets, "dash"),
        countryside: Sound::load(&assets, "countryside"),
        wind: Sound::load(&assets, "glide-wind"),
    });
}

/// The world has opened and its loops have not started yet.
#[derive(Resource)]
struct Pending;

/// The countryside loop.
#[derive(Component)]
struct Countryside;

/// Starts the world's loops, silent, once their sounds have loaded: the countryside and the paraglider's wind.
fn spawn_loops(mut commands: Commands, pending: Option<Res<Pending>>, sounds: Res<Sounds>, takes: Res<Assets<Takes>>) {
    if pending.is_none() || !(sounds.countryside.loaded(&takes) && sounds.wind.loaded(&takes)) {
        return;
    }
    sounds.countryside.spawn_loops(&mut commands, &takes, |_| Countryside);
    sounds.wind.spawn_loops(&mut commands, &takes, moves::Wind);
    commands.remove_resource::<Pending>();
}

/// Keeps the countryside at its volume, times the settings' volume.
fn play_countryside(settings: Res<Settings>, mut sinks: Query<&mut AudioSink, With<Countryside>>) {
    for mut sink in &mut sinks {
        sink.set_volume(Volume::Linear(COUNTRYSIDE_VOLUME * settings.volume));
    }
}
