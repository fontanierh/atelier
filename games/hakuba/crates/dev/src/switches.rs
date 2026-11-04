//! Desktop switches for playtests and measurements (see crates/screens): `HAKUBA_DEV=SECONDS` turns dev mode's free
//! camera on that long after the world has loaded, so a scripted pad can fly it to views the player only reaches
//! gliding; `HAKUBA_SHOT=PATH@SECONDS` saves the window's image; `HAKUBA_TRIS=1` logs the triangles drawn.

use std::time::{Duration, Instant};

use bevy::mesh::Indices;
use bevy::prelude::*;
use hakuba_screens::{DevMode, switch};

pub(crate) fn build(app: &mut App) {
    if switch("HAKUBA_TRIS").is_some() {
        app.add_systems(Last, count_triangles);
    }
    if let Some(shot) = switch("HAKUBA_SHOT").and_then(|v| Shot::parse(&v)) {
        app.insert_resource(shot).add_systems(Last, take_shot);
    }
    if let Some(after) = switch("HAKUBA_DEV").and_then(|v| v.parse::<f32>().ok()) {
        app.insert_resource(DevAfter { after, loaded: None }).add_systems(Last, dev_after);
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

/// `HAKUBA_SHOT=PATH@SECONDS` saves the window's own image to PATH that many seconds after the world has
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

/// `HAKUBA_DEV`: when to turn dev mode on, and when the world loaded.
#[derive(Resource)]
struct DevAfter {
    after: f32,
    loaded: Option<Instant>,
}

fn dev_after(
    mut commands: Commands,
    mut dev: ResMut<DevAfter>,
    mut next: ResMut<NextState<DevMode>>,
    loaded: Option<Res<hakuba_world::SceneryLoaded>>,
    unready: Query<(), With<hakuba_world::Unready>>,
) {
    if dev.loaded.is_none() && loaded.is_some() && unready.is_empty() {
        dev.loaded = Some(Instant::now());
    }
    if dev.loaded.is_some_and(|at| at.elapsed().as_secs_f32() >= dev.after) {
        info!("dev mode on, as HAKUBA_DEV asked");
        next.set(DevMode::On);
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
        info!("screenshot to {}", shot.path);
        commands
            .spawn(bevy::render::view::screenshot::Screenshot::primary_window())
            .observe(bevy::render::view::screenshot::save_to_disk(shot.path.clone()));
        commands.remove_resource::<Shot>();
    }
}
