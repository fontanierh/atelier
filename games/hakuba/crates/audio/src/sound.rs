//! A sound from `assets/sounds`: its Ogg file and the list of its takes, and playing one take of it, never the same
//! one twice in a row.

use std::time::Duration;

use bevy::asset::io::Reader;
use bevy::asset::{AssetLoader, LoadContext};
use bevy::audio::Volume;
use bevy::prelude::*;
use hakuba_screens::Screen;
use serde::Deserialize;

pub struct TakesPlugin;

impl Plugin for TakesPlugin {
    fn build(&self, app: &mut App) {
        app.init_asset::<Takes>().init_asset_loader::<TakesLoader>().init_resource::<Dice>();
    }
}

/// Where each take of a sound starts in its file and how long it lasts, and whether the takes loop.
#[derive(Asset, TypePath, Deserialize)]
pub struct Takes {
    looped: bool,
    takes: Vec<Take>,
}

#[derive(Deserialize, Clone, Copy)]
struct Take {
    start: f32,
    seconds: f32,
}

/// Reads a sound's `.takes.json`.
#[derive(Default, TypePath)]
struct TakesLoader;

impl AssetLoader for TakesLoader {
    type Asset = Takes;
    type Settings = ();
    type Error = BevyError;

    async fn load(&self, reader: &mut dyn Reader, _: &(), _: &mut LoadContext<'_>) -> Result<Takes, BevyError> {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes).await?;
        Ok(serde_json::from_slice(&bytes)?)
    }

    fn extensions(&self) -> &[&str] {
        &["takes.json"]
    }
}

/// One sound: its file, its takes, and the take it played last.
#[derive(Clone)]
pub struct Sound {
    name: String,
    audio: Handle<AudioSource>,
    takes: Handle<Takes>,
    last: Option<usize>,
    board: Option<Handle<super::soften::BoardSource>>,
}

impl Sound {
    /// Starts loading the sound `assets/sounds/<name>/`.
    pub fn load(assets: &AssetServer, name: &str) -> Self {
        Self {
            name: name.to_owned(),
            audio: assets.load(format!("sounds/{name}/{name}.ogg")),
            takes: assets.load(format!("sounds/{name}/{name}.takes.json")),
            last: None,
            board: None,
        }
    }

    /// Plays one take, chosen at random but never the last one again, at `volume` (1 as recorded) and `speed` (which
    /// also sets the pitch), until it ends or the world closes. Nothing plays until the sound has loaded.
    pub fn play(&mut self, commands: &mut Commands, takes: &Assets<Takes>, dice: &mut Dice, volume: f32, speed: f32) {
        let Some(list) = takes.get(&self.takes) else { return };
        let count = list.takes.len();
        if count == 0 {
            return;
        }
        let mut index = dice.below(count);
        if count > 1 && Some(index) == self.last {
            index = (index + 1 + dice.below(count - 1)) % count;
        }
        self.last = Some(index);
        let take = list.takes[index];
        let settings = PlaybackSettings::DESPAWN
            .with_volume(Volume::Linear(volume))
            .with_speed(speed)
            .with_start_position(Duration::from_secs_f32(take.start))
            .with_duration(Duration::from_secs_f32(take.seconds));
        let entity =
            commands.spawn((Name::new(format!("Sound {}", self.name)), DespawnOnExit(Screen::World), settings)).id();
        if let Some(board) = &self.board {
            commands.entity(entity).insert(AudioPlayer::<super::soften::BoardSource>(board.clone()));
        } else {
            commands.entity(entity).insert(AudioPlayer::new(self.audio.clone()));
        }
    }

    pub fn board_source(
        &mut self,
        audio: &Assets<AudioSource>,
        sources: &mut Assets<super::soften::BoardSource>,
        preferences: &super::soften::VoicePreferences,
    ) -> bool {
        if self.board.is_some() {
            return true;
        }
        let Some(audio) = audio.get(&self.audio) else { return false };
        self.board =
            Some(sources.add(super::soften::BoardSource { audio: audio.clone(), preferences: preferences.clone() }));
        true
    }

    /// Whether the list of takes has loaded.
    pub fn loaded(&self, takes: &Assets<Takes>) -> bool {
        takes.contains(&self.takes)
    }

    pub fn failed(&self, assets: &AssetServer) -> bool {
        assets.load_state(&self.audio).is_failed() || assets.load_state(&self.takes).is_failed()
    }

    /// Both exported takes and decoded audio are ready before a required sound releases the splash.
    pub fn ready(&self, assets: &AssetServer, takes: &Assets<Takes>) -> bool {
        self.loaded(takes) && assets.is_loaded_with_dependencies(&self.audio)
    }

    /// Spawns every take looping, silent until its volume is set, until the world closes; each gets `marker` and its
    /// index among the takes. Spawns nothing while the sound loads.
    pub fn spawn_loops<M: Component>(
        &self,
        commands: &mut Commands,
        takes: &Assets<Takes>,
        marker: impl Fn(usize) -> M,
    ) {
        let Some(list) = takes.get(&self.takes) else { return };
        for (index, take) in list.takes.iter().enumerate() {
            let mut settings = PlaybackSettings::LOOP.with_volume(Volume::SILENT);
            if list.takes.len() > 1 {
                settings = settings
                    .with_start_position(Duration::from_secs_f32(take.start))
                    .with_duration(Duration::from_secs_f32(take.seconds));
            }
            if !list.looped {
                warn!("sounds/{}: its takes do not loop", self.name);
            }
            let entity = commands
                .spawn((
                    Name::new(format!("Sound {} {index}", self.name)),
                    DespawnOnExit(Screen::World),
                    settings,
                    marker(index),
                ))
                .id();
            if let Some(board) = &self.board {
                commands.entity(entity).insert(AudioPlayer::<super::soften::BoardSource>(board.clone()));
            } else {
                commands.entity(entity).insert(AudioPlayer::new(self.audio.clone()));
            }
        }
    }
}

/// Repeatable random numbers for choosing takes, volumes and pitches.
#[derive(Resource)]
pub struct Dice(u32);

impl Default for Dice {
    fn default() -> Self {
        Self(0x9E37_79B9)
    }
}

impl Dice {
    /// A number from 0 up to 1.
    pub fn roll(&mut self) -> f32 {
        // xorshift32
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 17;
        self.0 ^= self.0 << 5;
        (self.0 >> 8) as f32 / (1u32 << 24) as f32
    }

    /// A number from `low` up to `high`.
    pub fn between(&mut self, low: f32, high: f32) -> f32 {
        low + (high - low) * self.roll()
    }

    /// A whole number from 0 up to `count`.
    fn below(&mut self, count: usize) -> usize {
        ((self.roll() * count as f32) as usize).min(count - 1)
    }
}
