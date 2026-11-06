//! A plant's impostor: its full version drawn from many directions over the upper half of the sky, each view a
//! frame of one atlas, so the game can show a far tree as a quad that looks as the full tree does from where the
//! camera is, with no swap of shape between distances.
//!
//! The frames sit on a hemi-octahedral grid ([`direction`]): frame `(i, j)` of a `GRID` by `GRID` atlas looks at
//! the plant from the direction that grid point maps to, its centre at the plant's bounding sphere centre and its
//! sides the sphere's diameter ([`basis`]). Each frame is drawn by a small rasteriser at `SUPERSAMPLE` times its
//! size, testing each leaf texel against its material's cutoff as the game does, then averaged down: the albedo
//! atlas holds what the game's foliage shader colours a surface before lighting (its texture times its base colour
//! times its canopy shade) and, in its alpha, how much of the pixel is covered; the normal atlas holds the plant-space
//! normal and, in its alpha, how far in front of the frame's centre plane the surface is, a fraction of the radius.
//! Empty pixels take their nearest covered neighbour's colour, so filtering never brings in black.

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use glam::{Vec2, Vec3};
use serde_json::{Value, json};

use crate::glb::Mesh;
use crate::ktx2::{Level, MipColour, bc7_ktx2, bc7_linear_ktx2, linear, srgb};

/// Frames along each side of the atlas.
pub(super) const GRID: u32 = 8;
/// Pixels along each side of a frame.
pub(super) const FRAME: u32 = 256;
/// Samples along each side of a pixel.
const SUPERSAMPLE: u32 = 4;
/// Mipmap levels kept: down to frames 8 pixels across, past which a level would blend neighbouring frames.
const LEVELS: usize = 6;
/// A plant whose full version has fewer vertices than this has no impostor: its middle version is merged and cheap.
const AT_LEAST_VERTICES: usize = 1024;
/// The coverage the game's impostor shader keeps a pixel at.
const CUTOFF: f32 = 0.5;

/// Where a plant's impostor albedo atlas is written: beside its export.
pub(crate) fn albedo_path(output: &Path) -> PathBuf {
    output.with_extension("impostor.ktx2")
}

/// Where a plant's impostor normal and depth atlas is written: beside its export.
pub(crate) fn normal_path(output: &Path) -> PathBuf {
    output.with_extension("impostor-normal.ktx2")
}

/// Bakes the impostor of the plant exported at `output`, its textures' sources under `assets`, and writes its atlases
/// beside it, returning what its full node's extras say of it: `{ grid, frame, radius, centre }`. A plant with no
/// middle version or too few vertices to want one has none, and any atlases left from before are removed.
pub(super) fn write(output: &Path, assets: &Path) -> Result<Option<Value>> {
    let bytes = std::fs::read(output)?;
    let length = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
    let value: Value = serde_json::from_slice(&bytes[20..20 + length])?;
    let has_middle = value["nodes"].as_array().is_some_and(|nodes| nodes.iter().any(|n| n["name"] == "middle"));
    let parts = parts(&value, super::source::binary(&bytes), assets)?;
    let vertices: usize = parts.iter().map(|(mesh, _)| mesh.positions.len()).sum();
    if !has_middle || vertices < AT_LEAST_VERTICES {
        for path in [albedo_path(output), normal_path(output)] {
            if path.exists() {
                std::fs::remove_file(path)?;
            }
        }
        return Ok(None);
    }
    let impostor = bake(&parts);
    let size = impostor.albedo.width;
    let mut albedo = vec![impostor.albedo];
    let mut normal = vec![impostor.normal];
    while albedo.len() < LEVELS {
        let mut smaller = albedo.last().unwrap().halved(MipColour::OpacityWeighted).unwrap();
        keep_coverage(&albedo[0], &mut smaller);
        albedo.push(smaller);
        normal.push(halved_linear(normal.last().unwrap()));
    }
    std::fs::write(albedo_path(output), bc7_ktx2(size, size, &albedo)?)?;
    std::fs::write(normal_path(output), bc7_linear_ktx2(size, size, &normal)?)?;
    Ok(Some(json!({
        "grid": GRID,
        "frame": FRAME,
        "radius": impostor.radius,
        "centre": [impostor.centre.x, impostor.centre.y, impostor.centre.z],
    })))
}

/// The next level of a linear atlas, each byte the average of the four it covers.
fn halved_linear(level: &Level) -> Level {
    let (width, height) = (level.width / 2, level.height / 2);
    let mut rgba = Vec::with_capacity((width * height * 4) as usize);
    for y in 0..height {
        for x in 0..width {
            for c in 0..4 {
                let at =
                    |dx: u32, dy: u32| level.rgba[(((y * 2 + dy) * level.width + x * 2 + dx) * 4 + c) as usize] as u32;
                rgba.push(((at(0, 0) + at(1, 0) + at(0, 1) + at(1, 1) + 2) / 4) as u8);
            }
        }
    }
    Level { width, height, rgba }
}

/// Scales each frame's coverage in `level` so as many of its pixels pass [`CUTOFF`] as of the first level's, so a
/// tree keeps its fullness at a distance instead of thinning to nothing as its leaves average away.
fn keep_coverage(first: &Level, level: &mut Level) {
    let passing = |level: &Level, i: u32, j: u32, scale: f32| {
        let side = level.width / GRID;
        let mut count = 0;
        for y in 0..side {
            for x in 0..side {
                let at = (((j * side + y) * level.width + i * side + x) * 4 + 3) as usize;
                count += u32::from(level.rgba[at] as f32 / 255.0 * scale >= CUTOFF);
            }
        }
        count as f32 / (side * side) as f32
    };
    for j in 0..GRID {
        for i in 0..GRID {
            let target = passing(first, i, j, 1.0);
            let (mut low, mut high) = (0.0f32, 8.0f32);
            for _ in 0..20 {
                let mid = (low + high) * 0.5;
                if passing(level, i, j, mid) < target { low = mid } else { high = mid }
            }
            let side = level.width / GRID;
            for y in 0..side {
                for x in 0..side {
                    let at = (((j * side + y) * level.width + i * side + x) * 4 + 3) as usize;
                    level.rgba[at] = (level.rgba[at] as f32 * high).round().min(255.0) as u8;
                }
            }
        }
    }
}

/// The direction from the plant towards the camera of grid point `cell` (0 to `GRID - 1` on each axis), y up: the
/// grid's corners and edges look level, its centre straight down.
pub(super) fn direction(cell: [u32; 2]) -> Vec3 {
    let o = Vec2::new(cell[0] as f32, cell[1] as f32) / (GRID - 1) as f32 * 2.0 - 1.0;
    let (a, b) = ((o.x + o.y) * 0.5, (o.x - o.y) * 0.5);
    Vec3::new(a, 1.0 - a.abs() - b.abs(), b).normalize()
}

/// The frame's right and up, for a view from `direction`: right is level, up is as near the sky as it can be.
pub(super) fn basis(direction: Vec3) -> (Vec3, Vec3) {
    let hint = if direction.y.abs() > 0.999 { Vec3::Z } else { Vec3::Y };
    let right = hint.cross(direction).normalize();
    (right, direction.cross(right))
}

/// How one part looks to the bake.
pub(super) struct Surface {
    pub texture: Option<Texture>,
    pub factor: [f32; 4],
    pub cutoff: Option<f32>,
    pub double_sided: bool,
    /// How much a vertex colour's green darkens it inside the canopy: the game's `moving * (1 - shade)`.
    pub shade: f32,
    pub up_normal: bool,
}

/// A base colour texture, linear.
pub(super) struct Texture {
    width: u32,
    height: u32,
    texels: Vec<[f32; 4]>,
}

impl Texture {
    /// Reads an sRGB image.
    pub fn read(path: &Path) -> Result<Self> {
        let image = image::open(path).with_context(|| format!("reading {}", path.display()))?.to_rgba8();
        let texels = image.pixels().map(|p| [linear(p[0]), linear(p[1]), linear(p[2]), p[3] as f32 / 255.0]).collect();
        Ok(Texture { width: image.width(), height: image.height(), texels })
    }

    fn sample(&self, uv: Vec2) -> [f32; 4] {
        let x = (uv.x.rem_euclid(1.0) * self.width as f32) as u32 % self.width;
        let y = (uv.y.rem_euclid(1.0) * self.height as f32) as u32 % self.height;
        self.texels[(y * self.width + x) as usize]
    }
}

/// The bake: the albedo and normal atlases, each `GRID * FRAME` square, and the bounding sphere the frames frame.
pub(super) struct Impostor {
    pub albedo: Level,
    pub normal: Level,
    pub centre: Vec3,
    pub radius: f32,
}

/// The sphere around every vertex of `parts`, centred on their bounding box.
fn sphere(parts: &[(Mesh, Surface)]) -> (Vec3, f32) {
    let points = || parts.iter().flat_map(|(mesh, _)| mesh.positions.iter().map(|&p| Vec3::from(p)));
    let (low, high) = points().fold((Vec3::MAX, Vec3::MIN), |(l, h), p| (l.min(p), h.max(p)));
    let centre = (low + high) * 0.5;
    (centre, points().map(|p| p.distance(centre)).fold(0.0, f32::max))
}

/// What one sample of a frame saw, if anything: its albedo, normal and depth.
#[derive(Clone, Copy)]
struct Sample {
    albedo: Vec3,
    normal: Vec3,
    depth: f32,
}

pub(super) fn bake(parts: &[(Mesh, Surface)]) -> Impostor {
    let (centre, radius) = sphere(parts);
    let size = GRID * FRAME;
    let mut albedo = vec![0u8; (size * size * 4) as usize];
    let mut normal = vec![0u8; (size * size * 4) as usize];
    for j in 0..GRID {
        for i in 0..GRID {
            let frame = draw(parts, direction([i, j]), centre, radius);
            for y in 0..FRAME {
                for x in 0..FRAME {
                    let [a, n] = frame[(y * FRAME + x) as usize];
                    let at = (((j * FRAME + y) * size + i * FRAME + x) * 4) as usize;
                    albedo[at..at + 4].copy_from_slice(&a);
                    normal[at..at + 4].copy_from_slice(&n);
                }
            }
        }
    }
    Impostor {
        albedo: Level { width: size, height: size, rgba: albedo },
        normal: Level { width: size, height: size, rgba: normal },
        centre,
        radius,
    }
}

/// One frame: each pixel's albedo (sRGB, coverage in alpha) and normal (unsigned, depth in alpha), empty pixels
/// filled from their neighbours.
fn draw(parts: &[(Mesh, Surface)], direction: Vec3, centre: Vec3, radius: f32) -> Vec<[[u8; 4]; 2]> {
    let (right, up) = basis(direction);
    let side = FRAME * SUPERSAMPLE;
    let mut samples: Vec<Option<Sample>> = vec![None; (side * side) as usize];
    let scale = side as f32 / (2.0 * radius);
    for (mesh, surface) in parts {
        let projected: Vec<Vec3> = mesh
            .positions
            .iter()
            .map(|&p| {
                let p = Vec3::from(p) - centre;
                Vec3::new((p.dot(right) + radius) * scale, (radius - p.dot(up)) * scale, p.dot(direction))
            })
            .collect();
        for triangle in mesh.indices.chunks_exact(3) {
            let [a, b, c] = [triangle[0], triangle[1], triangle[2]].map(|k| k as usize);
            let [pa, pb, pc] = [projected[a], projected[b], projected[c]];
            // In pixels y runs down, so a triangle facing the camera winds clockwise here.
            let area = (pb.x - pa.x) * (pc.y - pa.y) - (pb.y - pa.y) * (pc.x - pa.x);
            if area.abs() < 1e-12 {
                continue;
            }
            let front = area < 0.0;
            if !front && !surface.double_sided {
                continue;
            }
            let x0 = pa.x.min(pb.x).min(pc.x).floor().max(0.0) as u32;
            let x1 = (pa.x.max(pb.x).max(pc.x).ceil() as u32).min(side);
            let y0 = pa.y.min(pb.y).min(pc.y).floor().max(0.0) as u32;
            let y1 = (pa.y.max(pb.y).max(pc.y).ceil() as u32).min(side);
            for y in y0..y1 {
                for x in x0..x1 {
                    let (px, py) = (x as f32 + 0.5, y as f32 + 0.5);
                    let wa = ((pb.x - px) * (pc.y - py) - (pb.y - py) * (pc.x - px)) / area;
                    let wb = ((pc.x - px) * (pa.y - py) - (pc.y - py) * (pa.x - px)) / area;
                    let wc = 1.0 - wa - wb;
                    if wa < 0.0 || wb < 0.0 || wc < 0.0 {
                        continue;
                    }
                    let depth = wa * pa.z + wb * pb.z + wc * pc.z;
                    let slot = &mut samples[(y * side + x) as usize];
                    if slot.is_some_and(|s| s.depth >= depth) {
                        continue;
                    }
                    let mix2 = |v: &[[f32; 2]]| Vec2::from(v[a]) * wa + Vec2::from(v[b]) * wb + Vec2::from(v[c]) * wc;
                    let mut colour = [1.0; 4];
                    if let Some(texture) = &surface.texture {
                        colour = texture.sample(mix2(&mesh.uvs));
                    }
                    let alpha = colour[3] * surface.factor[3];
                    if surface.cutoff.is_some_and(|cutoff| alpha < cutoff) {
                        continue;
                    }
                    let green = if mesh.colours.is_empty() {
                        1.0
                    } else {
                        wa * mesh.colours[a][1] + wb * mesh.colours[b][1] + wc * mesh.colours[c][1]
                    };
                    let shade = 1.0 - surface.shade * (1.0 - green);
                    let albedo =
                        Vec3::new(colour[0], colour[1], colour[2]) * Vec3::from_slice(&surface.factor[..3]) * shade;
                    let normal = if surface.up_normal {
                        Vec3::Y
                    } else {
                        let n = Vec3::from(mesh.normals[a]) * wa
                            + Vec3::from(mesh.normals[b]) * wb
                            + Vec3::from(mesh.normals[c]) * wc;
                        let n = n.normalize_or(Vec3::Y);
                        if front { n } else { -n }
                    };
                    *slot = Some(Sample { albedo, normal, depth });
                }
            }
        }
    }
    let mut pixels = vec![None::<(Vec3, Vec3, f32, f32)>; (FRAME * FRAME) as usize];
    for y in 0..FRAME {
        for x in 0..FRAME {
            let (mut albedo, mut normal, mut depth, mut count) = (Vec3::ZERO, Vec3::ZERO, 0.0, 0);
            for sy in 0..SUPERSAMPLE {
                for sx in 0..SUPERSAMPLE {
                    let at = (y * SUPERSAMPLE + sy) * side + x * SUPERSAMPLE + sx;
                    if let Some(s) = samples[at as usize] {
                        (albedo, normal, depth, count) =
                            (albedo + s.albedo, normal + s.normal, depth + s.depth, count + 1);
                    }
                }
            }
            if count > 0 {
                let n = count as f32;
                let coverage = n / (SUPERSAMPLE * SUPERSAMPLE) as f32;
                pixels[(y * FRAME + x) as usize] =
                    Some((albedo / n, normal.normalize_or(Vec3::Y), depth / n / radius, coverage));
            }
        }
    }
    let covered: Vec<bool> = pixels.iter().map(Option::is_some).collect();
    dilate(&mut pixels);
    pixels
        .iter()
        .zip(covered)
        .map(|(pixel, covered)| {
            let (albedo, normal, depth, coverage) = pixel.unwrap_or((Vec3::ZERO, Vec3::Y, 0.0, 0.0));
            let coverage = if covered { coverage } else { 0.0 };
            let unit = |v: f32| ((v * 0.5 + 0.5).clamp(0.0, 1.0) * 255.0).round() as u8;
            [
                [srgb(albedo.x), srgb(albedo.y), srgb(albedo.z), (coverage * 255.0).round() as u8],
                [unit(normal.x), unit(normal.y), unit(normal.z), unit(depth)],
            ]
        })
        .collect()
}

/// Fills each empty pixel of a frame with the average of its filled neighbours, ring by ring, until none is empty.
fn dilate(pixels: &mut [Option<(Vec3, Vec3, f32, f32)>]) {
    let side = FRAME as i32;
    if pixels.iter().all(Option::is_none) {
        return;
    }
    while pixels.iter().any(Option::is_none) {
        let before = pixels.to_vec();
        for y in 0..side {
            for x in 0..side {
                if before[(y * side + x) as usize].is_some() {
                    continue;
                }
                let (mut albedo, mut normal, mut depth, mut count) = (Vec3::ZERO, Vec3::ZERO, 0.0, 0);
                for (dx, dy) in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)] {
                    let (nx, ny) = (x + dx, y + dy);
                    if (0..side).contains(&nx)
                        && (0..side).contains(&ny)
                        && let Some((a, n, d, _)) = before[(ny * side + nx) as usize]
                    {
                        (albedo, normal, depth, count) = (albedo + a, normal + n, depth + d, count + 1);
                    }
                }
                if count > 0 {
                    let n = count as f32;
                    pixels[(y * side + x) as usize] = Some((albedo / n, normal.normalize_or(Vec3::Y), depth / n, 0.0));
                }
            }
        }
    }
}

/// The parts of an exported plant's `full` node with how each looks, its textures read from their sources under
/// `assets`.
pub(super) fn parts(value: &Value, binary: &[u8], assets: &Path) -> Result<Vec<(Mesh, Surface)>> {
    let node = value["nodes"]
        .as_array()
        .and_then(|nodes| nodes.iter().find(|n| n["name"] == "full"))
        .context("a plant has no full version")?;
    let profile = &node["extras"]["source_foliage"];
    let shade_strength = 1.0 - profile["direction_amplitude_shade"][3].as_f64().unwrap_or(1.0) as f32;
    let up_normal = profile["up_normal"].as_bool().unwrap_or(false);
    let mesh = node["mesh"].as_u64().context("the full version has no mesh")? as usize;
    let primitives = value["meshes"][mesh]["primitives"].as_array().context("the full version has no parts")?;
    primitives
        .iter()
        .map(|primitive| {
            let mesh = super::source::part(value, binary, primitive)?;
            let material = &value["materials"][mesh.material];
            let pbr = &material["pbrMetallicRoughness"];
            let mut factor = [1.0; 4];
            if let Some(values) = pbr["baseColorFactor"].as_array() {
                for (slot, v) in factor.iter_mut().zip(values) {
                    *slot = v.as_f64().unwrap_or(1.0) as f32;
                }
            }
            let texture = match pbr["baseColorTexture"]["index"].as_u64() {
                Some(index) => {
                    let image =
                        value["textures"][index as usize]["source"].as_u64().context("texture needs an image")?;
                    let uri = value["images"][image as usize]["uri"].as_str().context("texture needs a URI")?;
                    let name = uri
                        .strip_prefix("../../textures/")
                        .and_then(|s| s.split('/').next())
                        .context("an impostor reads only exported textures")?;
                    Some(Texture::read(&texture_source(&assets.join("textures").join(name))?)?)
                }
                None => None,
            };
            let masked = material["alphaMode"] == "MASK";
            let surface = Surface {
                texture,
                factor,
                cutoff: masked.then(|| material["alphaCutoff"].as_f64().unwrap_or(0.5) as f32),
                double_sided: material["doubleSided"].as_bool().unwrap_or(false),
                shade: if masked { shade_strength } else { 0.0 },
                up_normal,
            };
            Ok((mesh, surface))
        })
        .collect()
}

/// A texture asset's source image.
fn texture_source(folder: &Path) -> Result<std::path::PathBuf> {
    let text = std::fs::read_to_string(folder.join("asset.toml"))
        .with_context(|| format!("reading {}", folder.join("asset.toml").display()))?;
    let document: toml_edit::DocumentMut = text.parse()?;
    let source = document["source"].as_str().context("a texture asset names its source")?;
    Ok(folder.join(source))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn directions_cover_the_upper_hemisphere() {
        assert!(direction([0, 0]).y.abs() < 1e-6 && direction([GRID - 1, GRID - 1]).y.abs() < 1e-6);
        for j in 0..GRID {
            for i in 0..GRID {
                let d = direction([i, j]);
                assert!(d.y >= -1e-6 && (d.length() - 1.0).abs() < 1e-5);
                let (right, up) = basis(d);
                assert!(right.cross(up).distance(d) < 1e-4 && right.y.abs() < 1e-5);
            }
        }
    }

    /// Writes forest-maple's atlases to `HAKUBA_IMPOSTOR_PREVIEW` as PNGs, to look at.
    #[test]
    #[ignore]
    fn preview() {
        let out = std::path::PathBuf::from(std::env::var("HAKUBA_IMPOSTOR_PREVIEW").unwrap());
        let plant = std::env::var("HAKUBA_IMPOSTOR_PLANT").unwrap_or("forest-maple".into());
        let assets = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets");
        let bytes = std::fs::read(assets.join(format!("plants/{plant}/{plant}.glb"))).unwrap();
        let length = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let value: Value = serde_json::from_slice(&bytes[20..20 + length]).unwrap();
        let start = std::time::Instant::now();
        let impostor = bake(&parts(&value, super::super::source::binary(&bytes), &assets).unwrap());
        eprintln!("baked in {:?}, radius {}", start.elapsed(), impostor.radius);
        for (name, level) in [("albedo", &impostor.albedo), ("normal", &impostor.normal)] {
            image::save_buffer(
                out.join(format!("{plant}.{name}.png")),
                &level.rgba,
                level.width,
                level.height,
                image::ColorType::Rgba8,
            )
            .unwrap();
        }
    }
}
