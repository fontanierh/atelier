// Retired experiment: explicit Cargo test/doctest targets must stay empty.
#![cfg(not(any(test, doctest)))]

//! The forest lab: one dense forest of the game's own trees on a hill, seen along fixed camera paths at a fixed step
//! per frame, so two runs see the same frames. A run draws its trees one way (the knobs below), logs the GPU's time for
//! each frame, and may save every few frames to compare against another run (`lab-compare`): the reference run draws
//! every tree in full, so anything another way of drawing changes on screen, a tree changing shape, appearing late or
//! missing, shows as a difference from it.
//!
//! ```sh
//! LAB_PATH=fly LAB_OUT=target/lab/runs/reference LAB_CAPTURE=1 cargo run --release -p hakuba_forest_lab
//! ```
//!
//! `LAB_PATH` is `walk` (into the forest at head height), `fly` (over the canopy, looking ahead and down) or `glide`
//! (down from high above, looking at the forest below). `LAB_CAPTURE=N` saves every Nth frame; without it the run only
//! times. `LAB_SCREEN=other` opens on the screen that is not the main one.
//!
//! Knobs for trying a forest's cost: `LAB_SPACING` (metres between trees, default 7), `LAB_SCALE` (the trees' size,
//! default 1), `LAB_SHADOWS=off`, `LAB_VERSION` (the version seen: `full`, or `middle`) and `LAB_CASTER` (`middle`, as
//! the game: a shadow-only middle version casts each tree's shadow; `same`: the seen version casts it; `none`).
//! `LAB_SECONDS` shortens the path, `LAB_STILL=1` holds the camera at the path's start, and `LAB_AA=off` turns the
//! game's temporal anti-aliasing off. `LAB_OCCLUSION=1` culls the trees hidden behind others. `LAB_FAR_M` fades each
//! tree into its impostor around that distance, over `LAB_FADE_M` (default 20 m; 0 swaps at once), or with
//! `LAB_SWAP=middle` into its middle version, as the game did. `LAB_MIDDLE_M`, nearer than `LAB_FAR_M`, puts the
//! middle version between the full one and the impostor; `LAB_END_M` stops drawing impostors that far; `LAB_CASTER_M`
//! casts shadows only that near; `LAB_SHADOW_FILTER=gaussian` keeps the anti-aliasing but not its shadow filter, and
//! `LAB_PIXELS=M` draws M million pixels instead of the game's 3.

use std::fmt::Write as _;
use std::path::PathBuf;

use bevy::asset::io::AssetSourceBuilder;
use bevy::asset::{AssetMetaCheck, RenderAssetUsages};
use bevy::gltf::{Gltf, GltfMesh, GltfNode, GltfPlugin};
use bevy::image::{ImageFilterMode, ImageSamplerDescriptor};
use std::time::Duration;

use bevy::anti_alias::taa::TemporalAntiAliasing;
use bevy::camera::visibility::{RenderLayers, VisibilityRange};
use bevy::core_pipeline::prepass::DepthPrepass;
use bevy::light::{CascadeShadowConfigBuilder, NotShadowCaster, ShadowFilteringMethod};
use bevy::mesh::{Indices, MeshTag, PrimitiveTopology};
use bevy::prelude::*;
use bevy::render::occlusion_culling::OcclusionCulling;
use bevy::render::view::screenshot::{Screenshot, save_to_disk};
use bevy::time::TimeUpdateStrategy;
use bevy::window::{MonitorSelection, PresentMode, PrimaryWindow, WindowPosition, WindowResolution};
use hakuba_rendering::{ForwardMotionMode, RenderingPlugin};
use hakuba_world::lab;

/// The forest's side, in metres, centred on the origin.
const SIDE_M: f32 = 800.0;
/// The spacing of the jittered grid the trees stand on, in metres: about the game's forest.
const SPACING_M: f32 = 7.0;
/// Frames drawn before the path starts, for loading and the first pipelines.
const WARM_FRAMES: u32 = 180;
/// The path's time step per frame, in seconds: the frame index, not the clock, moves the camera.
const STEP_S: f32 = 1.0 / 60.0;
/// The wind's strength, as the game's default setting.
const WIND: f32 = 1.0;

fn main() {
    let assets = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets");
    let experiments = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../target/lab");
    App::new()
        // The lab's experimental trees, written by its tools under the ignored target folder.
        .register_asset_source("lab", AssetSourceBuilder::platform_default(&experiments.to_string_lossy(), None))
        .add_plugins(
            DefaultPlugins
                .set(WindowPlugin {
                    primary_window: Some(Window {
                        title: "Forest lab".into(),
                        // About the 3 million pixels the game draws at most, one per screen pixel whatever the
                        // screen's density.
                        resolution: window_size().with_scale_factor_override(1.0),
                        present_mode: PresentMode::AutoNoVsync,
                        ..default()
                    }),
                    ..default()
                })
                .set(AssetPlugin {
                    file_path: assets.to_string_lossy().into_owned(),
                    meta_check: AssetMetaCheck::Never,
                    ..default()
                })
                // As the game: the glTF textures filtered across their mipmaps and along the view.
                .set(GltfPlugin {
                    default_sampler: ImageSamplerDescriptor {
                        mag_filter: ImageFilterMode::Linear,
                        min_filter: ImageFilterMode::Linear,
                        mipmap_filter: ImageFilterMode::Linear,
                        anisotropy_clamp: 16,
                        ..default()
                    },
                    ..default()
                }),
        )
        .add_plugins((lab::LabPlugin, RenderingPlugin))
        // The shaders' clock, and so the wind, steps as the camera does: two runs sway alike.
        .insert_resource(TimeUpdateStrategy::ManualDuration(Duration::from_secs_f32(STEP_S)))
        .insert_resource(Lab::from_env())
        .add_systems(Startup, (setup, load_species))
        .add_systems(Update, (choose_screen, cast_shadows, plant, (step, record).chain()))
        .run();
}

/// The run's settings and its progress.
#[derive(Resource)]
struct Lab {
    path: String,
    out: Option<PathBuf>,
    capture: Option<u32>,
    species: Vec<String>,
    spacing: f32,
    scale: f32,
    shadows: bool,
    version: String,
    caster: String,
    seconds: Option<f32>,
    still: bool,
    temporal: bool,
    occlusion: bool,
    prepass: bool,
    far_m: f32,
    fade_m: f32,
    swap: String,
    caster_m: f32,
    caster_far_m: f32,
    prune: Vec<f32>,
    offscreen: Option<Handle<Image>>,
    middle_m: f32,
    end_m: f32,
    temporal_shadows: bool,
    frame: u32,
    planted: bool,
    log: String,
}

impl Lab {
    fn from_env() -> Lab {
        let var = |name: &str| std::env::var(name).ok().filter(|v| !v.is_empty());
        Lab {
            path: var("LAB_PATH").unwrap_or("fly".into()),
            out: var("LAB_OUT").map(PathBuf::from),
            capture: var("LAB_CAPTURE").and_then(|v| v.parse().ok()).filter(|&n| n > 0),
            species: var("LAB_SPECIES")
                .unwrap_or("forest-maple,forest-oak,forest-pine,forest-ginkgo".into())
                .split(',')
                .map(str::to_owned)
                .collect(),
            spacing: var("LAB_SPACING").and_then(|v| v.parse().ok()).unwrap_or(SPACING_M),
            scale: var("LAB_SCALE").and_then(|v| v.parse().ok()).unwrap_or(1.0),
            shadows: var("LAB_SHADOWS").as_deref() != Some("off"),
            version: var("LAB_VERSION").unwrap_or("full".into()),
            caster: var("LAB_CASTER").unwrap_or("middle".into()),
            seconds: var("LAB_SECONDS").and_then(|v| v.parse().ok()),
            still: var("LAB_STILL").is_some(),
            temporal: var("LAB_AA").as_deref() != Some("off"),
            occlusion: var("LAB_OCCLUSION").is_some(),
            prepass: var("LAB_PREPASS").is_some(),
            far_m: var("LAB_FAR_M").and_then(|v| v.parse().ok()).unwrap_or(0.0),
            fade_m: var("LAB_FADE_M").and_then(|v| v.parse().ok()).unwrap_or(20.0),
            swap: var("LAB_SWAP").unwrap_or("impostor".into()),
            caster_m: var("LAB_CASTER_M").and_then(|v| v.parse().ok()).unwrap_or(0.0),
            caster_far_m: var("LAB_CASTER_FAR_M").and_then(|v| v.parse().ok()).unwrap_or(0.0),
            offscreen: None,
            prune: var("LAB_PRUNE").map(|v| v.split(',').filter_map(|d| d.parse().ok()).collect()).unwrap_or_default(),
            middle_m: var("LAB_MIDDLE_M").and_then(|v| v.parse().ok()).unwrap_or(0.0),
            end_m: var("LAB_END_M").and_then(|v| v.parse().ok()).unwrap_or(0.0),
            temporal_shadows: var("LAB_SHADOW_FILTER").as_deref() != Some("gaussian"),
            frame: 0,
            planted: false,
            log: String::from("frame,t,gpu_ms,cpu_ms\n"),
        }
    }
}

/// The window: 2240 by 1400, or as many million pixels as `LAB_PIXELS` says, at the same shape.
fn window_size() -> WindowResolution {
    let pixels: f32 = std::env::var("LAB_PIXELS").ok().and_then(|v| v.parse().ok()).unwrap_or(2240.0 * 1400.0 / 1e6);
    let width = (pixels * 1e6 * 1.6).sqrt();
    WindowResolution::new(width.round() as u32, (width / 1.6).round() as u32)
}

/// The forest's ground height at `(x, z)`: flat, with one round hill to stand on and look over the trees from.
fn ground(x: f32, z: f32) -> f32 {
    let (dx, dz) = (x + 150.0, z - 120.0);
    45.0 * (-(dx * dx + dz * dz) / (2.0 * 110.0 * 110.0)).exp()
}

/// A hash of `(i, j, salt)` from 0 to 1, so the forest is the same in every run.
fn hash(i: i32, j: i32, salt: u32) -> f32 {
    let mut h =
        (i as u32).wrapping_mul(0x9E37_79B1) ^ (j as u32).wrapping_mul(0x85EB_CA77) ^ salt.wrapping_mul(0xC2B2_AE3D);
    h ^= h >> 15;
    h = h.wrapping_mul(0x2C1B_3C6D);
    h ^= h >> 12;
    h = h.wrapping_mul(0x297A_2D39);
    h ^= h >> 15;
    (h & 0x00FF_FFFF) as f32 / 0x0100_0000 as f32
}

/// Where the camera is and what it looks at, `t` seconds along the path.
fn camera_at(path: &str, t: f32) -> (Vec3, Vec3) {
    match path {
        // From the forest's edge, walking in at 1.5 m/s, looking ahead and a little around.
        "walk" => {
            let x = -390.0 + 1.5 * t;
            let eye = Vec3::new(x, ground(x, 0.0) + 1.7, 3.0);
            (eye, eye + Vec3::new(1.0, 0.0, 0.35 * (0.3 * t).sin()))
        }
        // From high above, gliding down and on at 14 m/s, looking at the forest ahead and below.
        "glide" => {
            let x = -380.0 + 14.0 * t;
            let eye = Vec3::new(x, 160.0 - 2.0 * t, -60.0);
            (eye, eye + Vec3::new(1.0, -0.6, 0.1))
        }
        // Low over the canopy at 15 m/s, looking ahead and down, as the glider does.
        _ => {
            let x = -380.0 + 15.0 * t;
            let eye = Vec3::new(x, ground(x, -40.0) + 40.0, -40.0);
            (eye, eye + Vec3::new(1.0, -0.45, 0.05))
        }
    }
}

/// How long the path runs, in seconds.
fn path_seconds(path: &str) -> f32 {
    match path {
        "walk" => 40.0,
        _ => 45.0,
    }
}

fn setup(
    mut commands: Commands,
    mut settings: ResMut<Lab>,
    assets: Res<AssetServer>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut images: ResMut<Assets<Image>>,
) {
    if std::env::var("LAB_OFFSCREEN").is_ok_and(|v| !v.is_empty()) {
        let size = window_size().physical_size();
        let format = bevy::render::render_resource::TextureFormat::Rgba8UnormSrgb;
        settings.offscreen = Some(images.add(Image::new_target_texture(size.x, size.y, format, None)));
    }
    // The ground: a grid of 4 m squares following the hill.
    let cells = (SIDE_M * 1.25 / 4.0) as u32;
    let half = SIDE_M * 0.625;
    let mut positions = Vec::new();
    let mut normals = Vec::new();
    for j in 0..=cells {
        for i in 0..=cells {
            let (x, z) = (-half + i as f32 * 4.0, -half + j as f32 * 4.0);
            positions.push([x, ground(x, z), z]);
            let n = Vec3::new(ground(x - 0.5, z) - ground(x + 0.5, z), 1.0, ground(x, z - 0.5) - ground(x, z + 0.5));
            normals.push(n.normalize().to_array());
        }
    }
    let mut indices = Vec::new();
    for j in 0..cells {
        for i in 0..cells {
            let a = j * (cells + 1) + i;
            let (b, c, d) = (a + 1, a + cells + 1, a + cells + 2);
            indices.extend([a, c, b, b, c, d]);
        }
    }
    let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD);
    mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, positions);
    mesh.insert_attribute(Mesh::ATTRIBUTE_NORMAL, normals);
    mesh.insert_indices(Indices::U32(indices));
    commands.spawn((
        Mesh3d(meshes.add(mesh)),
        MeshMaterial3d(materials.add(StandardMaterial {
            base_color: Color::srgb(0.16, 0.28, 0.1),
            perceptual_roughness: 1.0,
            reflectance: 0.0,
            ..default()
        })),
    ));
    // The game's sky, and its sun with the Near shadows: 300 m in four cascades, the first 20 m deep.
    commands.spawn((Sky, lab::sky(&assets, &mut meshes, &mut materials)));
    commands.spawn((
        lab::sun(),
        CascadeShadowConfigBuilder {
            num_cascades: 4,
            first_cascade_far_bound: 20.0,
            maximum_distance: 300.0,
            ..default()
        }
        .build(),
    ));
    let (eye, target) = camera_at("fly", 0.0);
    // The game's camera look, with its default temporal anti-aliasing and the shadows it filters.
    // The game's single forward pass, which writes the motion temporal anti-aliasing follows itself, with no camera
    // depth prepass.
    let mut camera = commands.spawn((
        Camera3d::default(),
        lab::camera(&mut images),
        Transform::from_translation(eye).looking_at(target, Vec3::Y),
    ));
    // `LAB_OFFSCREEN=1`: into an image of the window's size, as the game draws its world, so the frames are drawn and
    // timed even while the screen is locked and the window cannot be shown.
    if let Some(image) = &settings.offscreen {
        camera.insert(bevy::camera::RenderTarget::Image(image.clone().into()));
    }
    // Occlusion culling, Bevy's: each instance tested against the depth of the frame before, then of this frame's
    // first pass. It needs the camera's depth prepass, so the camera then keeps it, publishing the main pass's motion.
    if settings.occlusion {
        camera.insert((ForwardMotionMode::Publish, DepthPrepass, OcclusionCulling));
    } else if settings.prepass {
        // `LAB_PREPASS=1`: the depth prepass alone, so the main pass shades each pixel's nearest leaf only.
        camera.insert((ForwardMotionMode::Publish, DepthPrepass));
    } else {
        camera.insert(ForwardMotionMode::Single);
    }
    if settings.temporal {
        // `LAB_SHADOW_FILTER=gaussian` keeps the anti-aliasing but filters shadows without it.
        let filter =
            if settings.temporal_shadows { ShadowFilteringMethod::Temporal } else { ShadowFilteringMethod::Gaussian };
        camera.insert((TemporalAntiAliasing::default(), filter));
    } else {
        camera.insert(ShadowFilteringMethod::Gaussian);
    }
}

/// Where a species' model is: a game plant's export, or with `lab:NAME`, an experiment's in `target/lab/NAME/`.
fn model(name: &str) -> String {
    match name.strip_prefix("lab:") {
        Some(name) => format!("lab://{name}/{name}.glb"),
        None => format!("plants/{name}/{name}.glb"),
    }
}

/// The species' models, loading.
#[derive(Resource)]
struct Species(Vec<Handle<Gltf>>);

fn load_species(mut commands: Commands, lab: Res<Lab>, assets: Res<AssetServer>) {
    let handles = lab.species.iter().map(|name| assets.load(model(name))).collect();
    commands.insert_resource(Species(handles));
}

/// Once every species and its materials have loaded, plants the forest: each tree's full version in the game's own
/// leaf materials, its parts shared by every copy.
#[allow(clippy::too_many_arguments)]
fn plant(
    mut commands: Commands,
    mut lab: ResMut<Lab>,
    species: Option<Res<Species>>,
    assets: Res<AssetServer>,
    gltfs: Res<Assets<Gltf>>,
    nodes: Res<Assets<GltfNode>>,
    gltf_meshes: Res<Assets<GltfMesh>>,
    mut swaying: lab::SwayingMaterials,
    mut impostors: lab::Impostors,
    mut meshes: ResMut<Assets<Mesh>>,
) {
    if lab.planted {
        return;
    }
    let Some(species) = species else { return };
    // Each species' full and middle versions, and the middle version as the game casts its shadow: its cut-out
    // leaves in their shadow-only material.
    let mut trees: Vec<Vec<Vec<Part>>> = Vec::new();
    let mut pictures: Vec<Option<(Handle<lab::Impostor>, Handle<Mesh>)>> = Vec::new();
    for (handle, name) in species.0.iter().zip(&lab.species) {
        let Some(gltf) = gltfs.get(handle) else { return };
        // The full, middle, middle shadow and far versions, then a pruned export's `prune1`, `prune2`, ... (prune.py).
        let mut names: Vec<String> = ["full", "middle", "middle", "far"].map(String::from).to_vec();
        names.extend((1..).map(|k| format!("prune{k}")).take_while(|n| gltf.named_nodes.contains_key(n.as_str())));
        let mut versions: Vec<Vec<Part>> = names.iter().map(|_| Vec::new()).collect();
        for (index, name) in names.iter().enumerate() {
            let Some(node) = gltf.named_nodes.get(name.as_str()).and_then(|n| nodes.get(n)) else { return };
            let Some(mesh) = node.mesh.as_ref().and_then(|m| gltf_meshes.get(m)) else { return };
            let extras =
                node.extras.as_ref().and_then(|extras| serde_json::from_str::<serde_json::Value>(&extras.value).ok());
            let profile = extras.as_ref().and_then(|value| {
                serde_json::from_value::<lab::SourceProfile>(value.get("source_foliage")?.clone()).ok()
            });
            let alphas: Vec<Option<String>> = extras
                .as_ref()
                .and_then(|value| serde_json::from_value(value.get("shadow_alpha_textures")?.clone()).ok())
                .unwrap_or_default();
            for (k, primitive) in mesh.primitives.iter().enumerate() {
                let standard: Handle<StandardMaterial> = primitive
                    .material
                    .as_ref()
                    .and_then(|m| m.path())
                    .map(|path| {
                        let label = format!("{}/std", path.label().unwrap_or_default());
                        assets.load(path.clone().with_label(label))
                    })
                    .unwrap_or_default();
                let mesh = primitive.mesh.clone();
                versions[index].push(match &profile {
                    Some(profile) => {
                        let Some(source) = swaying.source_of(&standard, profile) else { return };
                        match alphas.get(k).cloned().flatten() {
                            Some(uri) if (index == 2 || index == 3) && swaying.is_masked(&source) => {
                                let Ok(Some(shadow)) = swaying.shadow_of(&source, &uri) else { return };
                                Part::Shadow(mesh, shadow)
                            }
                            _ => Part::Foliage(mesh, source),
                        }
                    }
                    None => Part::Still(mesh, standard),
                });
            }
        }
        trees.push(versions);
        // Its impostor, as the exporter baked it from the full version.
        let full = gltf.named_nodes.get("full").and_then(|n| nodes.get(n));
        let extras = full
            .and_then(|node| node.extras.as_ref())
            .and_then(|extras| serde_json::from_str::<serde_json::Value>(&extras.value).ok());
        let baked = extras.as_ref().and_then(lab::Baked::of);
        let profile = extras
            .as_ref()
            .and_then(|value| serde_json::from_value::<lab::SourceProfile>(value.get("source_foliage")?.clone()).ok());
        pictures.push(match (baked, profile) {
            (Some(baked), Some(profile)) => {
                let plant = name.strip_prefix("lab:").map_or(name.as_str(), |n| {
                    n.strip_suffix("-light")
                        .or_else(|| n.strip_suffix("-prune"))
                        .or_else(|| n.strip_suffix("-hull"))
                        .or_else(|| n.strip_suffix("-order"))
                        .unwrap_or(n)
                });
                Some(impostors.of(&format!("plants/{plant}/{plant}.glb"), &baked, &profile, &mut meshes))
            }
            _ => None,
        });
    }
    let seen = usize::from(lab.version == "middle");
    let spacing = lab.spacing;
    let cells = (SIDE_M / spacing) as i32;
    let mut count = 0;
    for j in -cells / 2..cells / 2 {
        for i in -cells / 2..cells / 2 {
            // A few clearings, so the forest has edges to see across.
            let clearing = |k: i32| (k as f32 * spacing / 63.0).floor() as i32;
            if hash(clearing(i), clearing(j), 7) < 0.12 {
                continue;
            }
            let x = (i as f32 + hash(i, j, 1)) * spacing;
            let z = (j as f32 + hash(i, j, 2)) * spacing;
            let kind = ((hash(i, j, 3) * trees.len() as f32) as usize).min(trees.len() - 1);
            let transform = Transform::from_xyz(x, ground(x, z), z)
                .with_rotation(Quat::from_rotation_y(hash(i, j, 4) * std::f32::consts::TAU))
                .with_scale(Vec3::splat(lab.scale * (0.8 + 0.4 * hash(i, j, 5))));
            let (caster, far_caster) = (&trees[kind][2], &trees[kind][3]);
            // With `LAB_FAR_M`, the seen version fades around that distance into the tree's impostor, or with
            // `LAB_SWAP=middle` into its middle version.
            let fade = lab.far_m - lab.fade_m / 2.0..lab.far_m + lab.fade_m / 2.0;
            // With `LAB_END_M`, impostors stop there, where the fog has hidden the forest.
            let end = if lab.end_m > 0.0 { lab.end_m..lab.end_m + lab.fade_m } else { f32::MAX / 2.0..f32::MAX / 2.0 };
            let farther = VisibilityRange { start_margin: fade.clone(), end_margin: end, use_aabb: false };
            // With `LAB_MIDDLE_M` under `LAB_FAR_M`, the full version fades into the middle one there, and the middle
            // one into the impostor at `LAB_FAR_M`.
            let middle_fade = lab.middle_m - lab.fade_m / 2.0..lab.middle_m + lab.fade_m / 2.0;
            let chained = lab.middle_m > 0.0 && lab.middle_m < lab.far_m && lab.swap != "middle";
            let swaps = lab.far_m > 0.0 && (lab.swap == "middle" || pictures[kind].is_some());
            // With `LAB_PRUNE=D1,D2,...`, a pruned export's `prune1` shows from D1, `prune2` from D2, ... up to
            // `LAB_FAR_M`, each fading into the next over `LAB_FADE_M`.
            let band = |d: f32| d - lab.fade_m / 2.0..d + lab.fade_m / 2.0;
            let prunes = (trees[kind].len() - 4).min(lab.prune.len());
            let first_end = if prunes > 0 {
                band(lab.prune[0])
            } else if chained {
                middle_fade.clone()
            } else {
                fade.clone()
            };
            let near = (swaps || prunes > 0).then(|| VisibilityRange {
                start_margin: 0.0..0.0,
                end_margin: first_end,
                use_aabb: false,
            });
            for k in 0..prunes {
                let end = if k + 1 < prunes {
                    band(lab.prune[k + 1])
                } else if swaps {
                    fade.clone()
                } else {
                    f32::MAX / 2.0..f32::MAX / 2.0
                };
                let range = VisibilityRange { start_margin: band(lab.prune[k]), end_margin: end, use_aabb: false };
                spawn(&mut commands, &trees[kind][4 + k], transform, false, false, Some(range));
            }
            if swaps && chained {
                let between =
                    VisibilityRange { start_margin: middle_fade.clone(), end_margin: fade.clone(), use_aabb: false };
                spawn(&mut commands, &trees[kind][1], transform, false, false, Some(between));
            }
            // With `LAB_CASTER_M`, shadows are cast only that near, fading out over `LAB_FADE_M`.
            let casting = (lab.caster_m > 0.0).then(|| VisibilityRange {
                start_margin: 0.0..0.0,
                end_margin: lab.caster_m - lab.fade_m / 2.0..lab.caster_m + lab.fade_m / 2.0,
                use_aabb: false,
            });
            // With `LAB_CASTER_FAR_M`, the far version casts the shadow from there instead of the middle one.
            let caster_far = lab.caster_far_m - lab.fade_m / 2.0..lab.caster_far_m + lab.fade_m / 2.0;
            let (casting, far_casting) = if lab.caster_far_m > 0.0 {
                let near = VisibilityRange { start_margin: 0.0..0.0, end_margin: caster_far.clone(), use_aabb: false };
                let far = VisibilityRange {
                    start_margin: caster_far,
                    end_margin: f32::MAX / 2.0..f32::MAX / 2.0,
                    use_aabb: false,
                };
                (Some(near), Some(far))
            } else {
                (casting, None)
            };
            if swaps && lab.swap == "middle" {
                spawn(&mut commands, &trees[kind][1], transform, false, false, Some(farther));
            } else if let (true, Some((material, quad))) = (swaps, &pictures[kind]) {
                commands.spawn((
                    Mesh3d(quad.clone()),
                    MeshMaterial3d(material.clone()),
                    transform,
                    NotShadowCaster,
                    farther,
                ));
            }
            match lab.caster.as_str() {
                // The seen version casts its own shadow, as the game never has it: for comparison only.
                "same" => spawn(&mut commands, &trees[kind][seen], transform, true, false, near),
                "none" => spawn(&mut commands, &trees[kind][seen], transform, false, false, near),
                // As the game: the seen version casts none, and a shadow-only middle version casts it.
                _ => {
                    spawn(&mut commands, &trees[kind][seen], transform, false, false, near);
                    spawn(&mut commands, caster, transform, true, true, casting);
                    if far_casting.is_some() {
                        spawn(&mut commands, far_caster, transform, true, true, far_casting);
                    }
                }
            }
            count += 1;
        }
    }
    info!("LAB planted {count} trees of {} species: {} seen, {} casting shadows", trees.len(), lab.version, lab.caster);
    lab.planted = true;
}

/// Spawns a tree's version: casting a shadow or not, seen or only casting, and drawn only within `range`.
fn spawn(
    commands: &mut Commands,
    parts: &[Part],
    transform: Transform,
    casts: bool,
    only_casts: bool,
    range: Option<VisibilityRange>,
) {
    for part in parts {
        let mut entity = match part {
            Part::Foliage(mesh, material) => commands.spawn((
                Mesh3d(mesh.clone()),
                MeshMaterial3d(material.clone()),
                MeshTag::new(lab::tag(WIND)),
                transform,
            )),
            Part::Shadow(mesh, material) => commands.spawn((
                Mesh3d(mesh.clone()),
                MeshMaterial3d(material.clone()),
                MeshTag::new(lab::tag(WIND)),
                transform,
            )),
            Part::Still(mesh, material) => {
                commands.spawn((Mesh3d(mesh.clone()), MeshMaterial3d(material.clone()), transform))
            }
        };
        if !casts {
            entity.insert(NotShadowCaster);
        }
        if only_casts {
            entity.insert(RenderLayers::layer(lab::SHADOW_ONLY));
        }
        if let Some(range) = range.clone() {
            entity.insert(range);
        }
    }
}

/// One part of a tree: in the game's swaying leaf material, or, for a plant without one, its plain material.
enum Part {
    Foliage(Handle<Mesh>, Handle<lab::SourceFoliage>),
    Shadow(Handle<Mesh>, Handle<lab::ShadowFoliage>),
    Still(Handle<Mesh>, Handle<StandardMaterial>),
}

/// The sky dome, kept centred on the camera.
#[derive(Component)]
struct Sky;

/// Turns the sun's shadows on, unless `LAB_SHADOWS=off`, once it is spawned.
fn cast_shadows(lab: Res<Lab>, mut suns: Query<&mut DirectionalLight, Added<DirectionalLight>>) {
    for mut sun in &mut suns {
        sun.shadow_maps_enabled = lab.shadows;
        info!("LAB sun shadows {}", sun.shadow_maps_enabled);
    }
}

/// Moves the camera one step along its path, saving the frame when it is one to capture, and quits at the path's end.
fn step(
    mut commands: Commands,
    mut lab: ResMut<Lab>,
    mut camera: Query<&mut Transform, (With<Camera3d>, Without<Sky>)>,
    mut sky: Query<&mut Transform, With<Sky>>,
    mut exit: MessageWriter<AppExit>,
) {
    if !lab.planted {
        return;
    }
    lab.frame += 1;
    let Some(along) = lab.frame.checked_sub(WARM_FRAMES) else { return };
    let t = along as f32 * STEP_S;
    if t > lab.seconds.unwrap_or(path_seconds(&lab.path)) {
        if let Some(out) = &lab.out {
            std::fs::create_dir_all(out).ok();
            std::fs::write(out.join("frames.csv"), &lab.log).ok();
        }
        exit.write(AppExit::Success);
        return;
    }
    let (eye, target) = camera_at(&lab.path, if lab.still { 0.0 } else { t });
    if let Ok(mut transform) = camera.single_mut() {
        *transform = Transform::from_translation(eye).looking_at(target, Vec3::Y);
    }
    for mut sky in &mut sky {
        sky.translation = eye;
    }
    if let (Some(every), Some(out)) = (lab.capture, &lab.out)
        && along % every == 0
    {
        std::fs::create_dir_all(out).ok();
        let path = out.join(format!("{along:05}.png"));
        let screenshot = match &lab.offscreen {
            Some(image) => Screenshot::image(image.clone()),
            None => Screenshot::primary_window(),
        };
        commands.spawn(screenshot).observe(save_to_disk(path));
    }
}

/// Logs each frame's GPU and CPU time, and once a second a summary.
fn record(mut lab: ResMut<Lab>, time: Res<Time<Real>>) {
    if !lab.planted {
        return;
    }
    #[cfg(target_os = "macos")]
    let gpu = wgpu_hal::metal::frames::gpu_busy_ms();
    #[cfg(not(target_os = "macos"))]
    let gpu = 0.0;
    let Some(along) = lab.frame.checked_sub(WARM_FRAMES) else { return };
    let t = along as f32 * STEP_S;
    let cpu = time.delta_secs() * 1000.0;
    let _ = writeln!(lab.log, "{along},{t:.3},{gpu:.2},{cpu:.2}");
    if along % 60 == 0 {
        info!("LAB t {t:.1} s gpu {gpu:.1} ms cpu {cpu:.1} ms");
    }
}

/// Opens on the screen that is not the main one, with `LAB_SCREEN=other`: the screens are only known once the window
/// is open.
fn choose_screen(
    mut done: Local<bool>,
    screens: Query<(Entity, &bevy::window::Monitor, Has<bevy::window::PrimaryMonitor>)>,
    mut window: Query<&mut Window, With<PrimaryWindow>>,
) {
    if *done || std::env::var("LAB_SCREEN").as_deref() != Ok("other") {
        return;
    }
    let Some((entity, ..)) = screens.iter().find(|(_, _, primary)| !*primary) else { return };
    if let Ok(mut window) = window.single_mut() {
        window.position = WindowPosition::Centered(MonitorSelection::Entity(entity));
        *done = true;
    }
}
