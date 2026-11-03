//! Cutting a plant's leaf cards to what their texture shows, as SpeedTree's and Unreal's cutout cards do: a masked
//! card's see-through corners still cost the GPU a fragment each, in the main pass and in every shadow cascade, only
//! to be discarded. Each two-triangle card is shrunk to the rectangle, in texture space, round every texel that any
//! mip a full-detail card can sample keeps at the material's alpha cutoff, widened by the texel that bilinear
//! filtering reaches, so no fragment the cut removes could have been drawn. The card keeps its four corners: an
//! octagon removes more fragments, but on Mac its extra corners each run the wind and cost the main pass more than
//! the fragments save (1.4 ms more at the start point, against 0.4 ms saved in shadows).

use std::fs;
use std::io::Read;
use std::path::Path;

use anyhow::{Context, Result, ensure};
use glam::{Vec2, Vec3, Vec4};
use ktx2::Format;

use crate::glb::Mesh;

/// A card is shrunk only when that removes at least this share of its area.
const MIN_SAVING: f32 = 0.03;

/// The coarsest mip that counts holds at least this many texels across a card: coarser mips only show on cards too
/// small on screen for the full version to be drawn.
const MIN_TEXELS: f32 = 16.0;

/// A texture's alpha at each mip, from its exported linear R8 companion (`<name>.alpha.ktx2`).
pub(super) struct Alpha {
    mips: Vec<(usize, usize, Vec<u8>)>,
}

impl Alpha {
    pub(super) fn read(path: &Path) -> Result<Self> {
        let bytes = fs::read(path).with_context(|| format!("reading {}", path.display()))?;
        let reader = ktx2::Reader::new(bytes.as_slice()).context("invalid alpha KTX2")?;
        let header = reader.header();
        ensure!(header.format == Some(Format::R8_UNORM), "an alpha companion must be linear R8");
        let mut mips = Vec::new();
        for (mip, level) in reader.levels().enumerate() {
            let (w, h) = ((header.pixel_width >> mip).max(1) as usize, (header.pixel_height >> mip).max(1) as usize);
            let mut data = Vec::new();
            ruzstd::decoding::StreamingDecoder::new(level.data)?.take((w * h) as u64 + 1).read_to_end(&mut data)?;
            ensure!(data.len() == w * h, "wrong alpha mip length");
            mips.push((w, h, data));
        }
        Ok(Self { mips })
    }
}

/// The directions the cut's sides face, in texture coordinates: a card is cut to a rectangle.
const DIRECTIONS: [Vec2; 2] = [Vec2::new(1.0, 0.0), Vec2::new(0.0, 1.0)];

/// `part` with each two-triangle card cut to its rectangle (see the module), and cards that show nothing removed.
/// Returns the cut part and how many cards it cut and removed.
pub(super) fn cut(part: &Mesh, alpha: &Alpha, cutoff: f32) -> (Mesh, usize, usize) {
    let threshold = (cutoff * 255.0).ceil().clamp(1.0, 255.0) as u8;
    let mut out = Mesh { material: part.material, ..Mesh::default() };
    let (mut cut, mut removed) = (0, 0);
    for card in cards(part) {
        match shape(part, &card, alpha, threshold) {
            Shape::Keep => copy(part, &card, &mut out),
            Shape::Empty => removed += 1,
            Shape::Cut(outline) => {
                cut += 1;
                fan(part, &card, &outline, &mut out);
            }
        }
    }
    (out, cut, removed)
}

/// The triangles of each connected card, by their first index in `part.indices`.
fn cards(part: &Mesh) -> Vec<Vec<[u32; 3]>> {
    let mut parent: Vec<u32> = (0..part.positions.len() as u32).collect();
    fn root(parent: &mut [u32], mut i: u32) -> u32 {
        while parent[i as usize] != i {
            parent[i as usize] = parent[parent[i as usize] as usize];
            i = parent[i as usize];
        }
        i
    }
    for t in part.indices.chunks_exact(3) {
        let a = root(&mut parent, t[0]);
        for &v in &t[1..] {
            let b = root(&mut parent, v);
            parent[b as usize] = a;
        }
    }
    let mut order = Vec::new();
    let mut slot = std::collections::HashMap::new();
    for t in part.indices.chunks_exact(3) {
        let r = root(&mut parent, t[0]);
        let k = *slot.entry(r).or_insert_with(|| {
            order.push(Vec::new());
            order.len() - 1
        });
        order[k].push([t[0], t[1], t[2]]);
    }
    order
}

enum Shape {
    Keep,
    Empty,
    Cut(Vec<Vec2>),
}

fn shape(part: &Mesh, card: &[[u32; 3]], alpha: &Alpha, threshold: u8) -> Shape {
    let Some(outline) = quad(part, card) else { return Shape::Keep };
    let (low, high) = outline.iter().fold((Vec2::MAX, Vec2::MIN), |(l, h), &p| (l.min(p), h.max(p)));
    // A card whose texture repeats across it is drawn as it is.
    if low.min_element() < 0.0 || high.max_element() > 1.0 {
        return Shape::Keep;
    }
    let mut slabs = [(f32::MAX, f32::MIN); DIRECTIONS.len()];
    let mut any = false;
    for (mip, (w, h, data)) in alpha.mips.iter().enumerate() {
        let (wf, hf) = (*w as f32, *h as f32);
        if mip > 0 && (high.x - low.x) * wf < MIN_TEXELS && (high.y - low.y) * hf < MIN_TEXELS {
            break;
        }
        // Bilinear filtering blends the four texel centres round a sample, so a sample passes the cutoff only within
        // one texel of a centre that does; a texel counts if that reach overlaps the card.
        let (x0, x1) = (((low.x * wf) - 1.5).floor().max(0.0) as usize, ((high.x * wf) + 1.5).ceil().min(wf) as usize);
        let (y0, y1) = (((low.y * hf) - 1.5).floor().max(0.0) as usize, ((high.y * hf) + 1.5).ceil().min(hf) as usize);
        for y in y0..y1 {
            for x in x0..x1 {
                if data[y * w + x] < threshold {
                    continue;
                }
                any = true;
                let centre = Vec2::new((x as f32 + 0.5) / wf, (y as f32 + 0.5) / hf);
                let reach = Vec2::new(1.0 / wf, 1.0 / hf);
                for corner in [Vec2::new(-1.0, -1.0), Vec2::new(1.0, -1.0), Vec2::new(-1.0, 1.0), Vec2::new(1.0, 1.0)] {
                    let p = centre + corner * reach;
                    for (slab, d) in slabs.iter_mut().zip(DIRECTIONS) {
                        let s = p.dot(d);
                        *slab = (slab.0.min(s), slab.1.max(s));
                    }
                }
            }
        }
    }
    if !any {
        return Shape::Empty;
    }
    let mut clipped = outline.clone();
    for (&(min, max), d) in slabs.iter().zip(DIRECTIONS) {
        clipped = clip(&clipped, d, max);
        clipped = clip(&clipped, -d, -min);
        if clipped.len() < 3 {
            return Shape::Empty;
        }
    }
    // A card not square to its texture would gain corners: it keeps its own.
    if clipped.len() > 4 || area(&clipped) > (1.0 - MIN_SAVING) * area(&outline) {
        return Shape::Keep;
    }
    Shape::Cut(clipped)
}

/// A two-triangle card's outline in texture coordinates, counter-clockwise, when it is a convex quad.
fn quad(part: &Mesh, card: &[[u32; 3]]) -> Option<Vec<Vec2>> {
    if card.len() != 2 || part.uvs.is_empty() {
        return None;
    }
    let [a, b] = [card[0], card[1]];
    let shared: Vec<u32> = a.iter().copied().filter(|v| b.contains(v)).collect();
    if shared.len() != 2 {
        return None;
    }
    let lone_a = *a.iter().find(|v| !shared.contains(v))?;
    let lone_b = *b.iter().find(|v| !shared.contains(v))?;
    let uv = |i: u32| Vec2::from(part.uvs[i as usize]);
    let mut outline = vec![uv(lone_a), uv(shared[0]), uv(lone_b), uv(shared[1])];
    if signed_area(&outline) < 0.0 {
        outline.reverse();
    }
    let convex = (0..4).all(|i| {
        let (p, q, r) = (outline[i], outline[(i + 1) % 4], outline[(i + 2) % 4]);
        (q - p).perp_dot(r - q) > 0.0
    });
    convex.then_some(outline)
}

/// `polygon`'s part where `p · d <= limit`.
fn clip(polygon: &[Vec2], d: Vec2, limit: f32) -> Vec<Vec2> {
    let mut out = Vec::with_capacity(polygon.len() + 1);
    for i in 0..polygon.len() {
        let (p, q) = (polygon[i], polygon[(i + 1) % polygon.len()]);
        let (sp, sq) = (p.dot(d) - limit, q.dot(d) - limit);
        if sp <= 0.0 {
            out.push(p);
        }
        if (sp < 0.0) != (sq < 0.0) && sp != sq && sp != 0.0 && sq != 0.0 {
            out.push(p + (q - p) * (sp / (sp - sq)));
        }
    }
    out
}

fn signed_area(polygon: &[Vec2]) -> f32 {
    (0..polygon.len()).map(|i| polygon[i].perp_dot(polygon[(i + 1) % polygon.len()])).sum::<f32>() / 2.0
}

fn area(polygon: &[Vec2]) -> f32 {
    signed_area(polygon).abs()
}

fn copy(part: &Mesh, card: &[[u32; 3]], out: &mut Mesh) {
    let mut remap = std::collections::HashMap::new();
    for &i in card.iter().flatten() {
        let k = match remap.get(&i) {
            Some(&k) => k,
            None => *remap.entry(i).or_insert(push(out, part, &[(i, 1.0)])),
        };
        out.indices.push(k);
    }
}

/// Adds one vertex to `out`, the `weights` blend of `part`'s vertices, and returns its index.
fn push(out: &mut Mesh, part: &Mesh, weights: &[(u32, f32)]) -> u32 {
    let blend3 = |values: &[[f32; 3]]| weights.iter().map(|&(i, w)| Vec3::from(values[i as usize]) * w).sum::<Vec3>();
    out.positions.push(blend3(&part.positions).to_array());
    out.normals.push(blend3(&part.normals).normalize_or_zero().to_array());
    if !part.uvs.is_empty() {
        out.uvs.push(weights.iter().map(|&(i, w)| Vec2::from(part.uvs[i as usize]) * w).sum::<Vec2>().to_array());
    }
    if !part.colours.is_empty() {
        out.colours.push(weights.iter().map(|&(i, w)| Vec4::from(part.colours[i as usize]) * w).sum::<Vec4>().to_array());
    }
    (out.positions.len() - 1) as u32
}

/// Adds the card cut to `outline` as a fan, each vertex blended from the card triangle it lies in, facing as the card
/// did.
fn fan(part: &Mesh, card: &[[u32; 3]], outline: &[Vec2], out: &mut Mesh) {
    let uv = |i: u32| Vec2::from(part.uvs[i as usize]);
    let facing = (uv(card[0][1]) - uv(card[0][0])).perp_dot(uv(card[0][2]) - uv(card[0][0])) > 0.0;
    let first = out.positions.len() as u32;
    for &p in outline {
        let (t, bary) = card
            .iter()
            .map(|t| (t, barycentric(p, uv(t[0]), uv(t[1]), uv(t[2]))))
            .max_by(|a, b| a.1.min_element().total_cmp(&b.1.min_element()))
            .unwrap();
        push(out, part, &[(t[0], bary.x), (t[1], bary.y), (t[2], bary.z)]);
    }
    for k in 1..outline.len() as u32 - 1 {
        let (b, c) = (first + k, first + k + 1);
        out.indices.extend(if facing { [first, b, c] } else { [first, c, b] });
    }
}

fn barycentric(p: Vec2, a: Vec2, b: Vec2, c: Vec2) -> Vec3 {
    let (v0, v1, v2) = (b - a, c - a, p - a);
    let d = v0.perp_dot(v1);
    if d == 0.0 {
        return Vec3::new(1.0, 0.0, 0.0);
    }
    let v = v2.perp_dot(v1) / d;
    let w = v0.perp_dot(v2) / d;
    Vec3::new(1.0 - v - w, v, w)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn card(uv_low: Vec2, uv_high: Vec2) -> Mesh {
        let uvs = [uv_low, Vec2::new(uv_high.x, uv_low.y), uv_high, Vec2::new(uv_low.x, uv_high.y)];
        Mesh {
            positions: uvs.iter().map(|uv| [uv.x, 0.0, uv.y]).collect(),
            normals: vec![[0.0, 1.0, 0.0]; 4],
            uvs: uvs.iter().map(|uv| uv.to_array()).collect(),
            colours: vec![[1.0, 0.5, 0.25, 1.0]; 4],
            indices: vec![0, 1, 2, 0, 2, 3],
            ..Mesh::default()
        }
    }

    /// A 64-texel square texture opaque only in a disc of `radius` texels round its centre.
    fn disc(radius: f32) -> Alpha {
        let mut mips = Vec::new();
        let mut size = 64;
        while size >= 1 {
            let scale = size as f32 / 64.0;
            let data = (0..size * size)
                .map(|k| {
                    let p = Vec2::new((k % size) as f32 + 0.5, (k / size) as f32 + 0.5) / scale;
                    if p.distance(Vec2::splat(32.0)) <= radius { 255 } else { 0 }
                })
                .collect();
            mips.push((size, size, data));
            size /= 2;
        }
        Alpha { mips }
    }

    #[test]
    fn a_card_is_cut_round_what_it_shows_and_keeps_its_look() {
        let (out, cut_cards, removed) = cut(&card(Vec2::ZERO, Vec2::ONE), &disc(12.0), 0.5);
        assert_eq!((cut_cards, removed), (1, 0));
        assert_eq!(cards(&out).len(), 1, "the cut card stays one connected card");
        // Every opaque texel the card shows stays inside the cut card.
        let alpha = disc(12.0);
        let tris: Vec<[Vec2; 3]> = out
            .indices
            .chunks_exact(3)
            .map(|t| [0, 1, 2].map(|k| Vec2::from(out.uvs[t[k] as usize])))
            .collect();
        let (w, h, data) = &alpha.mips[0];
        for y in 0..*h {
            for x in 0..*w {
                if data[y * w + x] == 255 {
                    let p = Vec2::new((x as f32 + 0.5) / 64.0, (y as f32 + 0.5) / 64.0);
                    assert!(tris.iter().any(|t| barycentric(p, t[0], t[1], t[2]).min_element() >= -1e-4));
                }
            }
        }
        let kept: f32 = tris.iter().map(|t| area(&[t[0], t[1], t[2]])).sum();
        assert!(kept < 0.4, "the cut card keeps {kept} of its area");
        // Positions and colours follow the texture coordinates as on the card, and the card faces as it did.
        for k in 0..out.positions.len() {
            assert!((out.positions[k][0] - out.uvs[k][0]).abs() < 1e-5 && (out.positions[k][2] - out.uvs[k][1]).abs() < 1e-5);
            assert_eq!(out.colours[k], [1.0, 0.5, 0.25, 1.0]);
        }
        for t in tris {
            assert!((t[1] - t[0]).perp_dot(t[2] - t[0]) > 0.0);
        }
    }

    #[test]
    fn a_card_that_shows_nothing_is_removed_and_a_full_one_kept() {
        let (out, _, removed) = cut(&card(Vec2::ZERO, Vec2::splat(0.1)), &disc(12.0), 0.5);
        assert_eq!((removed, out.indices.len()), (1, 0));
        let (out, cut_cards, _) = cut(&card(Vec2::splat(0.4), Vec2::splat(0.6)), &disc(30.0), 0.5);
        assert_eq!((cut_cards, out.indices, out.positions.len()), (0, vec![0, 1, 2, 0, 2, 3], 4));
    }
}
