//! The `plant` kind: a tree, bush or tuft of grass. A tree or bush is wood, a tube of bark from below the ground up
//! with a branch to each clump of leaves, and leaves, square cards cut out of a leaf image and scattered through
//! those clumps. Grass is a tuft of curved blades coloured per vertex, casting no shadow. A plant whose leaves set `middle_cards` also
//! exports a `middle` version, its trunk and fewer, larger cards covering the same area, with no branches.

use std::f64::consts::{PI, TAU};
use std::path::Path;

use anyhow::{Result, bail};
use glam::{DMat3, DVec2, DVec3};
use serde::{Deserialize, Serialize};

use super::{Version, write};
use crate::glb::{Material, Mesh};
use crate::random::Random;
use crate::shapes::{card, tube, vertex};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// The seed of every random draw, so each export repeats exactly.
    seed: u64,
    wood: Option<Wood>,
    leaves: Option<Leaves>,
    tuft: Option<Tuft>,
}

/// A trunk and its branches.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Wood {
    /// The bark's texture, by its folder name under `assets/textures/`.
    texture: String,
    /// The trunk, from below the ground up, through each of these points.
    trunk: Vec<Point>,
    /// The radius where a branch leaves the trunk, in metres.
    branch_radius_m: f64,
}

/// A point of a tube: where it is in the plant's frame, and the tube's radius there, in metres.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Point {
    at: [f64; 3],
    radius: f64,
}

/// Cards of leaves, scattered through clumps.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Leaves {
    /// The leaves' texture, by its folder name under `assets/textures/`: four images in a two by two grid.
    texture: String,
    /// The linear colour that multiplies the texture.
    #[serde(default = "white")]
    tint: [f64; 3],
    /// How many cards the full version has, shared between the clumps by their volume.
    cards: usize,
    /// How many the middle version has, if there is one.
    middle_cards: Option<usize>,
    /// The width of a card in the full version, in metres.
    card_m: f64,
    /// The clumps: each an ellipsoid, its centre and its radii along x, y and z.
    lobes: Vec<Lobe>,
    /// The point the cards' normals point away from, so the crown is lit as one round mass.
    normals_from: [f64; 3],
    /// How far the normals lean up, so the crown is lit more from the sky.
    vertical_bias: f64,
    /// The share of cards pushed from a clump's inside out to its outer part, where they are seen.
    shell: f64,
}

/// One clump of leaves.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Lobe {
    at: [f64; 3],
    radii: [f64; 3],
}

/// A tuft of grass blades.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Tuft {
    blades: usize,
    /// How far from the tuft's centre a blade's root is, in metres.
    spread_m: [f64; 2],
    height_m: [f64; 2],
    /// The width of a blade at its root, in metres.
    width_m: [f64; 2],
    /// How far a blade's tip bends out, in metres.
    curl_m: [f64; 2],
    /// How far roots reach below the ground, in metres.
    depth_m: f64,
    /// The blades' linear colours, each picked in proportion to its weight.
    colours: Vec<Colour>,
    /// How much darker a blade is at its root than at its tip.
    root_shade: f64,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Colour {
    colour: [f64; 3],
    weight: f64,
}

fn white() -> [f64; 3] {
    [1.0; 3]
}

/// How far the texture of bark repeats along a trunk or branch, in metres.
const BARK_M: f64 = 1.5;

pub fn export(settings: &Settings, output: &Path) -> Result<()> {
    let mut random = Random::new(settings.seed);
    let (mut full, mut middle): (Version, Version) = (Vec::new(), Vec::new());
    let bark = settings.wood.as_ref().map(|wood| crate::uri_of_texture(&wood.texture)).transpose()?;
    let leaves = settings.leaves.as_ref().map(|leaves| crate::uri_of_texture(&leaves.texture)).transpose()?;
    if let (Some(wood), Some(uri)) = (&settings.wood, &bark) {
        let trunk = points(&wood.trunk);
        let mut mesh = Mesh::default();
        tube(&mut mesh, &trunk, 8, BARK_M);
        middle.push((mesh.clone(), Material::textured("bark", uri)));
        if let Some(leaves) = &settings.leaves {
            branches(&mut mesh, wood, &trunk, &leaves.lobes, &mut random);
        }
        full.push((mesh, Material::textured("bark", uri)));
    }
    if let (Some(leaves), Some(uri)) = (&settings.leaves, &leaves) {
        let material =
            || Material { colour: leaves.tint, cut_out: true, two_sided: true, ..Material::textured("leaves", uri) };
        full.push((cards(leaves, leaves.cards, leaves.card_m, &mut random), material()));
        if let Some(count) = leaves.middle_cards {
            // Fewer cards, each larger, so the crown covers the same area.
            let size = leaves.card_m * (leaves.cards as f64 / count as f64).sqrt();
            middle.push((cards(leaves, count, size, &mut random), material()));
        }
    }
    if let Some(tuft) = &settings.tuft {
        let material = Material { name: "grass", texture: None, colour: white(), cut_out: false, two_sided: true };
        full.push((blades(tuft, &mut random), material));
    }
    if full.is_empty() {
        bail!("a plant needs wood, leaves or a tuft");
    }
    let has_middle = settings.leaves.as_ref().is_some_and(|leaves| leaves.middle_cards.is_some());
    // So many tufts cast no shadow: the ground under them is shaded anyway.
    write(full, has_middle.then_some(middle), settings.tuft.is_none(), &[], output)
}

fn points(points: &[Point]) -> Vec<(DVec3, f64)> {
    points.iter().map(|p| (DVec3::from_array(p.at), p.radius)).collect()
}

/// Adds to `mesh` a branch from the trunk to each lobe, ending inside it, and a twig off each branch.
fn branches(mesh: &mut Mesh, wood: &Wood, trunk: &[(DVec3, f64)], lobes: &[Lobe], random: &mut Random) {
    for lobe in lobes {
        let centre = DVec3::from_array(lobe.at);
        let radii = DVec3::from_array(lobe.radii);
        let start = nearest_on(trunk, centre);
        let end = start.lerp(centre, 0.78);
        if start.distance(end) < 0.3 {
            continue;
        }
        tube(mesh, &[(start, wood.branch_radius_m), (end, 0.045)], 6, BARK_M);
        let side = |random: &mut Random| if random.unit() < 0.5 { -0.7 } else { 0.7 };
        let towards = centre + DVec3::new(side(random), side(random), 0.5) * radii;
        let fork = start.lerp(end, 0.55);
        tube(mesh, &[(fork, 0.035), (fork.lerp(towards, 0.8), 0.009)], 5, BARK_M);
    }
}

/// The point of the line through `points` nearest to `target`.
fn nearest_on(points: &[(DVec3, f64)], target: DVec3) -> DVec3 {
    points
        .windows(2)
        .map(|pair| {
            let (a, b) = (pair[0].0, pair[1].0);
            a + (b - a) * ((target - a).dot(b - a) / (b - a).length_squared()).clamp(0.0, 1.0)
        })
        .min_by(|p, q| p.distance(target).total_cmp(&q.distance(target)))
        .expect("a trunk has at least two points")
}

/// `count` cards about `size` wide, shared between the lobes by their volume.
fn cards(leaves: &Leaves, count: usize, size: f64, random: &mut Random) -> Mesh {
    let mut mesh = Mesh::default();
    let volumes: Vec<f64> = leaves.lobes.iter().map(|lobe| lobe.radii.iter().product()).collect();
    let total: f64 = volumes.iter().sum();
    let normals_from = DVec3::from_array(leaves.normals_from);
    let normal = |at: DVec3| (at - normals_from).normalize_or(DVec3::Z) + DVec3::Z * leaves.vertical_bias;
    for (lobe, volume) in leaves.lobes.iter().zip(volumes) {
        let (centre, radii) = (DVec3::from_array(lobe.at), DVec3::from_array(lobe.radii));
        for _ in 0..(count as f64 * volume / total).round() as usize {
            let mut p = in_ball(random);
            if random.unit() < leaves.shell && p.length() < 0.5 {
                p = p.normalize_or(DVec3::Z) * random.range([0.6, 1.0]);
            }
            let width = size * random.range([0.8, 1.2]);
            let turn = DMat3::from_rotation_z(random.range([0.0, TAU]))
                * DMat3::from_rotation_x(random.range([-70.0, 70.0]).to_radians())
                * DMat3::from_rotation_y(random.range([-40.0, 40.0]).to_radians());
            let cell = (random.unit() * 4.0) as usize;
            let low = DVec2::new((cell % 2) as f64 * 0.5, (cell / 2) as f64 * 0.5);
            // Cards deep inside the crown are darker, as the leaves around them shade them.
            let shade = 0.22 + 0.78 * p.length().min(1.0);
            card(&mut mesh, centre + p * radii, width, turn, normal, (low, 0.5), shade);
        }
    }
    mesh
}

/// A point evenly drawn from the ball of radius one.
fn in_ball(random: &mut Random) -> DVec3 {
    loop {
        let p = DVec3::new(random.range([-1.0, 1.0]), random.range([-1.0, 1.0]), random.range([-1.0, 1.0]));
        if p.length_squared() <= 1.0 {
            return p;
        }
    }
}

/// The blades of a tuft: each a strip from its root below the ground, narrowing to a point at its tip, bent out from
/// the tuft's centre. Its normals lean up, so the tuft is lit as soft grass rather than as flat strips.
fn blades(tuft: &Tuft, random: &mut Random) -> Mesh {
    const SEGMENTS: usize = 4;
    let mut mesh = Mesh::default();
    for _ in 0..tuft.blades {
        let bearing = random.range([0.0, TAU]);
        let out = DVec2::from_angle(bearing).extend(0.0);
        // A blade faces mostly out from the centre, turned a little either way.
        let across = DVec2::from_angle(bearing + PI / 2.0 + random.range([-0.4, 0.4])).extend(0.0);
        let root = out * random.range(tuft.spread_m) - DVec3::Z * tuft.depth_m;
        let (height, width, curl) =
            (random.range(tuft.height_m), random.range(tuft.width_m), random.range(tuft.curl_m));
        let colour = DVec3::from_array(random.pick(&tuft.colours, |c| c.weight).colour);
        let normal = out * 0.3 + DVec3::Z;
        let mut rows = Vec::new();
        for k in 0..=SEGMENTS {
            let t = k as f64 / SEGMENTS as f64;
            let at = root + DVec3::Z * (height + tuft.depth_m) * t + out * curl * t * t;
            let half = width / 2.0 * (1.0 - t);
            let shade = colour * (tuft.root_shade + (1.0 - tuft.root_shade) * t);
            let rgba = Some([shade.x, shade.y, shade.z, 1.0]);
            let left = vertex(&mut mesh, at - across * half, normal, DVec2::new(0.0, t), rgba);
            let right = vertex(&mut mesh, at + across * half, normal, DVec2::new(1.0, t), rgba);
            rows.push((left, right));
        }
        for pair in rows.windows(2) {
            let ((a, b), (c, d)) = (pair[0], pair[1]);
            mesh.indices.extend([a, b, d, a, d, c]);
        }
    }
    mesh
}
