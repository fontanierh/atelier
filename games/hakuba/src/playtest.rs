//! Playtest helpers for the native build: a frame pacer that keeps to fixed deadlines, so every frame lands on the
//! same display refresh, and a once-a-second log of how far apart frames really were.
//!
//! `HAKUBA_PACE=N` paces at N frames a second (default 62, 0 for no pacing). A little faster than 60 leaves the 120 Hz
//! display's own vsync wait to set each frame's phase: paced at exactly 60, the deadlines drift against the display's
//! ticks and a frame landing a hair late waits a whole extra tick, 25 ms. Over 25 s of the walk, 62 halved those frames
//! (115 and 107 at 60, 58 and 43 at 62, 69 at 61).

use std::time::{Duration, Instant};

use bevy::mesh::Indices;
use bevy::prelude::*;

pub struct PlaytestPlugin;
impl Plugin for PlaytestPlugin {
    fn build(&self, app: &mut App) {
        let pace = std::env::var("HAKUBA_PACE").ok().and_then(|v| v.parse::<f64>().ok()).unwrap_or(62.0);
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
        app.insert_resource(Pacer {
            period: (pace > 0.0).then(|| Duration::from_secs_f64(1.0 / pace)),
            next: None,
            relative,
            spin: Duration::from_secs_f64(spin / 1000.0),
        })
        .init_resource::<Intervals>()
        .init_resource::<Phases>()
        .add_systems(First, start_frame)
        .add_systems(Last, (log_intervals, pace_frame).chain());
        if std::env::var("HAKUBA_TRIS").is_ok() {
            app.add_systems(Last, count_triangles);
        }
        // The near shadows cover 40 m in one cascade: 1024 texels is ~4 cm each, and a quarter of the leaf cutouts.
        let shadow_map = std::env::var("HAKUBA_SHADOW_MAP").ok().and_then(|v| v.parse().ok()).unwrap_or(2048);
        app.insert_resource(bevy::light::DirectionalLightShadowMap { size: shadow_map });
        if std::env::var("HAKUBA_GPU_CLUSTERING").is_err() {
            app.add_systems(Startup, no_gpu_clustering);
        }
        if let Some(shot) = std::env::var("HAKUBA_SHOT").ok().and_then(|v| Shot::parse(&v)) {
            app.insert_resource(shot).add_systems(Last, take_shot);
        }
        // Playtest: HAKUBA_DEV=SECONDS turns dev mode's free camera on that long after the world loads, so a pad script
        // can fly it (r2 rises) to views the player only reaches gliding.
        // Playtest: HAKUBA_NO_ENVIRONMENT=1 takes the sky's fill light off the camera, to measure what sampling it costs.
        if std::env::var_os("HAKUBA_NO_ENVIRONMENT").is_some() {
            app.add_systems(Last, no_environment);
        }
        // Playtest: HAKUBA_HEMISPHERE=0 samples the sky's fill light from its cubemap again, to compare.
        if std::env::var("HAKUBA_HEMISPHERE").is_ok_and(|v| v == "0") {
            app.add_systems(Last, sampled_fill);
        }
        if let Some(after) = std::env::var("HAKUBA_DEV").ok().and_then(|v| v.parse::<f32>().ok()) {
            app.insert_resource(DevAfter { after, loaded: None }).add_systems(Last, dev_after);
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
fn pace_frame(mut pacer: ResMut<Pacer>, mut phases: ResMut<Phases>) {
    let started = Instant::now();
    let Some(period) = pacer.period else {
        phases.paced = Duration::ZERO;
        phases.paced_end = Some(started);
        return;
    };
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

/// `HAKUBA_TRIS=1`: every two seconds, logs the triangles of the meshes visible in some view, by distance from the
/// camera to each mesh's bounds' centre, and how many of them cast shadows.
fn count_triangles(
    time: Res<Time>,
    mut last: Local<f32>,
    meshes: Res<Assets<Mesh>>,
    mut added: MessageReader<AssetEvent<Mesh>>,
    mut counts: Local<std::collections::HashMap<AssetId<Mesh>, u64>>,
    camera: Single<(&GlobalTransform, &Camera), With<Camera3d>>,
    window: Single<&Window, With<bevy::window::PrimaryWindow>>,
    shown: Query<(
        &Mesh3d,
        &ViewVisibility,
        &GlobalTransform,
        Option<&bevy::camera::primitives::Aabb>,
        Has<bevy::light::NotShadowCaster>,
        Option<&Name>,
        Option<&ChildOf>,
    )>,
    names: Query<&Name>,
) {
    // A mesh's data leaves for the GPU once drawn, so each is counted as it arrives.
    for event in added.read() {
        if let AssetEvent::Added { id } | AssetEvent::Modified { id } = event
            && let Some(mesh) = meshes.get(*id)
            && let Ok(indices) = mesh.try_indices_option()
        {
            let corners = indices.map_or_else(|| mesh.count_vertices(), Indices::len);
            counts.insert(*id, corners as u64 / 3);
        }
    }
    if time.elapsed_secs() - *last < 2.0 {
        return;
    }
    *last = time.elapsed_secs();
    const BANDS: [f32; 7] = [40.0, 80.0, 135.0, 260.0, 400.0, 1000.0, f32::MAX];
    let mut drawn = [(0usize, 0u64, 0u64); 7];
    // Copies of one mesh draw together, so the distinct meshes in each band are about how many draws it costs.
    let mut distinct = [(); 7].map(|_| std::collections::HashSet::new());
    let (camera, view) = *camera;
    let eye = camera.translation();
    let mut kinds = std::collections::HashMap::<String, (usize, u64)>::new();
    for (mesh, visibility, transform, aabb, no_shadow, name, parent) in &shown {
        if !visibility.get() {
            continue;
        }
        let Some(&triangles) = counts.get(&mesh.0.id()) else { continue };
        let centre = transform.transform_point(aabb.map_or(Vec3::ZERO, |aabb| Vec3::from(aabb.center)));
        let band = BANDS.iter().position(|&end| eye.distance(centre) < end).unwrap_or(6);
        if band >= 4 {
            let own = name.map(|n| n.as_str().to_string()).unwrap_or_default();
            let up =
                parent.and_then(|p| names.get(p.parent()).ok()).map(|n| n.as_str().to_string()).unwrap_or_default();
            let key: String = format!("{own}<{up}").chars().filter(|c| !c.is_ascii_digit()).collect();
            let kind = kinds.entry(key).or_default();
            kind.0 += 1;
            kind.1 += triangles;
        }
        drawn[band].0 += 1;
        distinct[band].insert(mesh.0.id());
        drawn[band].1 += triangles;
        if !no_shadow {
            drawn[band].2 += triangles;
        }
    }
    let line: Vec<String> = BANDS
        .iter()
        .zip(drawn)
        .zip(&distinct)
        .map(|((end, (n, t, s)), d)| {
            format!("<{end:.0}: {n} meshes ({} distinct) {}k tris ({}k cast)", d.len(), t / 1000, s / 1000)
        })
        .collect();
    let mut kinds: Vec<_> = kinds.into_iter().collect();
    kinds.sort_by_key(|(_, (n, _))| std::cmp::Reverse(*n));
    for (kind, (n, t)) in kinds.iter().take(12) {
        info!("TRIS far kind {kind}: {n} meshes {}k tris", t / 1000);
    }
    info!(
        "TRIS drawn {:?} window {}x{} | {}",
        view.physical_viewport_size(),
        window.physical_width(),
        window.physical_height(),
        line.join(" | ")
    );
}

/// Playtest: `HAKUBA_SHOT=PATH@SECONDS` saves the window's own image to PATH that many seconds after the world has
/// loaded, whatever covers the window on the desktop.
#[derive(Resource)]
struct Shot {
    path: String,
    after: Duration,
    loaded: Option<Instant>,
}

impl Shot {
    fn parse(value: &str) -> Option<Self> {
        let (path, seconds) = value.rsplit_once('@')?;
        Some(Self { path: path.to_owned(), after: Duration::from_secs_f64(seconds.parse().ok()?), loaded: None })
    }
}

fn no_environment(mut commands: Commands, cameras: Query<Entity, Added<bevy::light::EnvironmentMapLight>>) {
    for camera in &cameras {
        commands.entity(camera).remove::<bevy::light::EnvironmentMapLight>();
    }
}

fn sampled_fill(mut commands: Commands, cameras: Query<Entity, Added<bevy::pbr::HemisphereLight>>) {
    for camera in &cameras {
        commands.entity(camera).remove::<bevy::pbr::HemisphereLight>();
    }
}

#[derive(Resource)]
struct DevAfter {
    after: f32,
    loaded: Option<Instant>,
}

fn dev_after(
    mut commands: Commands,
    mut dev: ResMut<DevAfter>,
    mut next: ResMut<NextState<hakuba_screens::DevMode>>,
    loaded: Option<Res<hakuba_world::SceneryLoaded>>,
    unready: Query<(), With<hakuba_world::Unready>>,
) {
    if dev.loaded.is_none() && loaded.is_some() && unready.is_empty() {
        dev.loaded = Some(Instant::now());
    }
    if dev.loaded.is_some_and(|at| at.elapsed().as_secs_f32() >= dev.after) {
        info!("playtest: dev mode on");
        next.set(hakuba_screens::DevMode::On);
        commands.remove_resource::<DevAfter>();
    }
}

fn take_shot(
    mut commands: Commands,
    shot: Option<ResMut<Shot>>,
    loaded: Option<Res<hakuba_world::SceneryLoaded>>,
    unready: Query<(), With<hakuba_world::Unready>>,
) {
    let Some(mut shot) = shot else { return };
    if shot.loaded.is_none() && loaded.is_some() && unready.is_empty() {
        shot.loaded = Some(Instant::now());
    }
    if shot.loaded.is_some_and(|at| at.elapsed() >= shot.after) {
        info!("playtest: screenshot to {}", shot.path);
        commands
            .spawn(bevy::render::view::screenshot::Screenshot::primary_window())
            .observe(bevy::render::view::screenshot::save_to_disk(shot.path.clone()));
        commands.remove_resource::<Shot>();
    }
}
