//! Playtest helpers for the native build: a frame pacer that keeps to fixed deadlines, so every frame lands on the
//! same display refresh, and a once-a-second log of how far apart frames really were.
//!
//! `HAKUBA_PACE=N` paces at N frames a second (default 60, 0 for no pacing).

use std::time::{Duration, Instant};

use bevy::prelude::*;

pub struct PlaytestPlugin;
impl Plugin for PlaytestPlugin {
    fn build(&self, app: &mut App) {
        let pace = std::env::var("HAKUBA_PACE").ok().and_then(|v| v.parse::<f64>().ok()).unwrap_or(60.0);
        let relative = std::env::var("HAKUBA_PACE_MODE").is_ok_and(|mode| mode == "relative");
        let spin = std::env::var("HAKUBA_SPIN_MS").ok().and_then(|v| v.parse::<f64>().ok()).unwrap_or(4.0);
        #[cfg(target_os = "macos")]
        // SAFETY: sets this (the main) thread's own scheduling class; macOS coalesces timers less for it.
        unsafe {
            unsafe extern "C" {
                fn pthread_set_qos_class_self_np(class: u32, priority: i32) -> i32;
            }
            // QOS_CLASS_USER_INTERACTIVE
            pthread_set_qos_class_self_np(0x21, 0);
        }
        app.insert_resource(Pacer { period: (pace > 0.0).then(|| Duration::from_secs_f64(1.0 / pace)), next: None, relative, spin: Duration::from_secs_f64(spin / 1000.0) })
            .init_resource::<Intervals>()
            .add_systems(Last, (log_intervals, pace_frame).chain());
        if std::env::var("HAKUBA_GPU_CLUSTERING").is_err() {
            app.add_systems(Startup, no_gpu_clustering);
        }
    }
}

#[derive(Resource)]
struct Pacer {
    period: Option<Duration>,
    next: Option<Instant>,
    /// Each frame waits a period after the last one started, not on a fixed clock, so a pace a little faster than
    /// half the display's refresh leaves the display's own vsync wait to set the phase, and frames land two ticks
    /// apart every time instead of drifting across a tick.
    relative: bool,
    /// How long before a deadline to stop sleeping and spin: macOS may wake a sleeping thread a few ms late.
    spin: Duration,
}

/// Sleeps until this frame's deadline; deadlines step by a fixed period, so a slow frame does not shift the next.
fn pace_frame(mut pacer: ResMut<Pacer>) {
    let Some(period) = pacer.period else { return };
    let now = Instant::now();
    let next = match pacer.next {
        Some(last) if pacer.relative => (last + period).max(now),
        Some(next) if next + period > now => next + period,
        // Missed by more than a whole period: start again from now rather than rushing to catch up.
        _ => now,
    };
    pacer.next = Some(next);
    if next > now {
        let left = next - now;
        if left > pacer.spin {
            std::thread::sleep(left - pacer.spin);
        }
        while Instant::now() < next {
            std::hint::spin_loop();
        }
    }
    if pacer.relative {
        pacer.next = Some(Instant::now());
    }
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
fn log_intervals(mut intervals: ResMut<Intervals>, cameras: Query<&GlobalTransform, With<Camera3d>>) {
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
        intervals.worst = intervals.worst.max(ms);
    }
    intervals.last = Some(now);
    if now - intervals.started >= Duration::from_secs(1) {
        let camera = cameras.iter().next().map(|t| {
            let (_, rotation, translation) = t.to_scale_rotation_translation();
            let forward = rotation * Vec3::NEG_Z;
            format!("cam {:.1},{:.1},{:.1} yaw {:.0}", translation.x, translation.y, translation.z, forward.x.atan2(-forward.z).to_degrees())
        });
        let b = intervals.buckets;
        info!(
            "frames <12:{} ~17:{} ~25:{} ~33:{} >40:{} worst {:.1} ms {}",
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

/// The few lights here are clustered on the CPU: GPU clustering adds compute passes and a readback every frame on
/// Apple GPUs. `HAKUBA_GPU_CLUSTERING=1` keeps it.
fn no_gpu_clustering(settings: Option<ResMut<bevy::light::cluster::GlobalClusterSettings>>) {
    if let Some(mut settings) = settings {
        settings.gpu_clustering = None;
        info!("GPU light clustering off");
    }
}
