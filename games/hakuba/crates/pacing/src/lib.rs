// Retired experiment: explicit Cargo test/doctest targets must stay empty.
#![cfg(not(any(test, doctest)))]

//! The frame pacer of the desktop game, at the Frame rate setting's 60: each frame starts on a fixed deadline, so every
//! frame lands on the same display refresh, and on the Mac each stays on screen at least a 60th of a second, so a
//! 120 Hz display shows a steady 60 timed by the window server rather than a timer on the CPU. A screen that shows at
//! most 60 is paced by its own vsync instead. The browser paces its own frames (crates/CONTRACTS,
//! `the-browser-paces-sixty`), so in the browser this plugin does nothing.
//!
//! Once a second it logs how far apart the frames really were (`frames <12:… ~17:… ~25:… ~33:… >40:…`), and each frame
//! over 17.5 ms as a `SLOW` line naming where the main thread's time went and where the camera was.

use std::time::{Duration, Instant};

use bevy::prelude::*;
use bevy::window::Monitor;
use hakuba_settings::{FrameRate, Settings};

/// The frames a second the deadlines step by. A little faster than 60 leaves the 120 Hz display's own vsync wait to
/// set each frame's phase: paced at exactly 60, the deadlines drift against the display's ticks and a frame landing a
/// hair late waits a whole extra tick, 25 ms. Over 25 s of the walk, 62 halved those frames (115 and 107 at 60, 58 and
/// 43 at 62, 69 at 61).
const PACE: f64 = 62.0;
/// How long before a deadline to stop sleeping and spin: macOS may wake a sleeping thread a few ms late.
const SPIN: Duration = Duration::from_millis(4);

/// A screen refreshing at most this many times a second keeps 60 by its own vsync.
const SELF_PACED_HZ: u32 = 61;

pub struct PacingPlugin;

impl Plugin for PacingPlugin {
    fn build(&self, app: &mut App) {
        if cfg!(target_arch = "wasm32") {
            return;
        }
        // macOS coalesces timers less for an interactive thread, so the pacer wakes on time.
        hakuba_screens::run_this_thread_as(hakuba_screens::ThreadClass::Interactive);
        app.init_resource::<Pacer>()
            .init_resource::<Intervals>()
            .init_resource::<Phases>()
            .add_systems(First, start_frame)
            .add_systems(Last, (log_intervals, pace_frame).chain());
    }
}

/// The next frame's deadline.
#[derive(Resource, Default)]
struct Pacer {
    next: Option<Instant>,
}

/// Sleeps until this frame's deadline; deadlines step by a fixed period, so a slow frame does not shift the next.
fn pace_frame(
    mut pacer: ResMut<Pacer>,
    mut phases: ResMut<Phases>,
    settings: Res<Settings>,
    screens: Query<&Monitor>,
    screen: Option<Res<hakuba_screens::GameScreen>>,
    mut applied: Local<Option<bool>>,
) {
    let started = Instant::now();
    // Only a cap of 60 is paced: a lower one is kept by the settings crate's reactive updates, and none draws as fast
    // as it can. A screen that shows at most 60 paces itself through its vsync: deadlines a little faster than it
    // would queue frames behind it until no drawable is left, and the next frame waits up to a second for one.
    // A screen that does not say its rate, or not yet known, is paced.
    let screen_hz = screen
        .and_then(|screen| screens.get(screen.0).ok())
        .and_then(|screen| screen.refresh_rate_millihertz)
        .map(|mhz| mhz / 1000);
    let sixty = settings.frame_rate == FrameRate::Sixty && screen_hz.is_none_or(|hz| hz > SELF_PACED_HZ);
    if *applied != Some(sixty) {
        *applied = Some(sixty);
        #[cfg(target_os = "macos")]
        wgpu_hal::metal::frames::set_minimum_on_screen(if sixty { 1.0 / 60.0 } else { 0.0 });
    }
    if !sixty {
        pacer.next = None;
        phases.paced = Duration::ZERO;
        phases.paced_end = Some(started);
        return;
    }
    let period = Duration::from_secs_f64(1.0 / PACE);
    let now = Instant::now();
    let next = match pacer.next {
        Some(next) if next + period > now => next + period,
        // Missed by more than a whole period: start again from now rather than rushing to catch up.
        _ => now,
    };
    pacer.next = Some(next);
    if next > now {
        let left = next - now;
        if left > SPIN {
            std::thread::sleep(left - SPIN);
        }
        while Instant::now() < next {
            std::hint::spin_loop();
        }
    }
    let ended = Instant::now();
    phases.paced = ended - started;
    phases.paced_end = Some(ended);
}

/// Where the main thread's time went in the last frame: its own schedules, the pacer's sleep before them, and the wait
/// in between, mostly for the render thread to take the frame, so a slow frame's log names its owner.
#[derive(Resource, Default)]
struct Phases {
    first: Option<Instant>,
    paced: Duration,
    paced_end: Option<Instant>,
}

fn start_frame(mut phases: ResMut<Phases>) {
    phases.first = Some(Instant::now());
}

#[derive(Resource)]
struct Intervals {
    started: Instant,
    last: Option<Instant>,
    buckets: [u32; 5],
    worst: f32,
}

impl Default for Intervals {
    fn default() -> Self {
        Self { started: Instant::now(), last: None, buckets: [0; 5], worst: 0.0 }
    }
}

/// Once a second: how many frames were under 12 ms, about one 60 Hz frame (12–20 ms), 20–29, 29–40 and over 40 ms,
/// the worst, and where the camera is and which way it looks.
fn log_intervals(
    mut intervals: ResMut<Intervals>,
    cameras: Query<(&GlobalTransform, &Projection), With<Camera3d>>,
    phases: Res<Phases>,
) {
    let now = Instant::now();
    if let Some(last) = intervals.last {
        let ms = (now - last).as_secs_f32() * 1000.0;
        let bucket = match ms {
            m if m < 12.0 => 0,
            m if m < 20.0 => 1,
            m if m < 29.0 => 2,
            m if m < 40.0 => 3,
            _ => 4,
        };
        intervals.buckets[bucket] += 1;
        if ms > 17.5 {
            if let Some((t, _)) = cameras.iter().next() {
                let (_, rotation, translation) = t.to_scale_rotation_translation();
                let forward = rotation * Vec3::NEG_Z;
                let ms_of = |d: Duration| d.as_secs_f32() * 1000.0;
                let work = phases.first.map_or(0.0, |first| ms_of(now - first));
                let waited = match (phases.first, phases.paced_end) {
                    (Some(first), Some(end)) if first > end => ms_of(first - end),
                    _ => 0.0,
                };
                info!(
                    "SLOW {ms:.1} ms (paced {:.1}, waited {waited:.1}, worked {work:.1}) cam {:.1},{:.1},{:.1} yaw {:.0} pitch {:.0}",
                    ms_of(phases.paced),
                    translation.x,
                    translation.y,
                    translation.z,
                    forward.x.atan2(-forward.z).to_degrees(),
                    forward.y.asin().to_degrees()
                );
            }
        }
        intervals.worst = intervals.worst.max(ms);
    }
    intervals.last = Some(now);
    if now - intervals.started >= Duration::from_secs(1) {
        let camera = cameras.iter().next().map(|(t, projection)| {
            let (_, rotation, translation) = t.to_scale_rotation_translation();
            let forward = rotation * Vec3::NEG_Z;
            let fov = match projection {
                Projection::Perspective(p) => p.fov.to_degrees(),
                _ => 0.0,
            };
            format!(
                "cam {:.1},{:.1},{:.1} yaw {:.0} fov {fov:.0}",
                translation.x,
                translation.y,
                translation.z,
                forward.x.atan2(-forward.z).to_degrees()
            )
        });
        let b = intervals.buckets;
        // The GPU's work per frame, as Unreal's `stat unit` reads it: a frame late with little of it was held elsewhere.
        #[cfg(target_os = "macos")]
        let gpu =
            format!(" gpu {:.1} ms", wgpu_hal::metal::frames::gpu_busy_ms() / b.iter().sum::<u32>().max(1) as f64);
        #[cfg(not(target_os = "macos"))]
        let gpu = "";
        info!(
            "frames <12:{} ~17:{} ~25:{} ~33:{} >40:{} worst {:.1} ms{gpu} {}",
            b[0],
            b[1],
            b[2],
            b[3],
            b[4],
            intervals.worst,
            camera.unwrap_or_default()
        );
        intervals.started = now;
        intervals.buckets = [0; 5];
        intervals.worst = 0.0;
    }
}
