//! Validation of source model contact against the rendered world surface.
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use super::scenery::{Land, Placement, Scenery, effective_pose};
use crate::glb::Glb;
use anyhow::{Context, Result, bail};
use glam::{DVec2, DVec3};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Policy {
    pub models: Vec<String>,
    pub band_m: f64,
}

pub struct Model {
    triangles: Vec<[DVec3; 3]>,
}

pub(super) fn key(placement: &Placement) -> String {
    let mut hash = Sha256::new();
    hash.update(placement.model.as_bytes());
    hash.update([0]);
    for number in [placement.at.x, placement.at.y, placement.yaw, placement.scale, placement.origin_offset_m] {
        hash.update((number as f32).to_bits().to_le_bytes());
    }
    hash.update([u8::from(placement.origin_height_m.is_some())]);
    if let Some(height) = placement.origin_height_m {
        hash.update((height as f32).to_bits().to_le_bytes());
    }
    format!("{:x}", hash.finalize())
}

pub fn read(policies: &[Policy], fixed: &super::fixed::FixedSources) -> Result<BTreeMap<String, Model>> {
    let mut models = BTreeMap::new();
    for policy in policies {
        if policy.models.is_empty() || !policy.band_m.is_finite() || policy.band_m < 0.0 {
            bail!("invalid ground contact policy");
        }
        for name in &policy.models {
            crate::uri_of_asset(name, "glb")?;
            let path = Path::new(crate::ASSETS).join(name).join(format!("{}.glb", name.rsplit('/').next().unwrap()));
            let triangles = Glb::read(&path)?.node_triangles("full")?;
            let lowest = triangles.iter().flatten().map(|p| p.y).fold(f64::INFINITY, f64::min);
            let triangles = triangles
                .into_iter()
                .filter(|t| fixed.contains_model(name) || t.iter().any(|p| p.y <= lowest + policy.band_m))
                .collect();
            if models.insert(name.clone(), Model { triangles }).is_some() {
                bail!("duplicate contact policy for {name}");
            }
        }
    }
    Ok(models)
}

/// Radius of the actual selected contact geometry, including instance scale.
pub fn footprint_radius(
    scenery: &[Scenery],
    selection: (DVec2, DVec2),
    models: &BTreeMap<String, Model>,
    fixed: &super::fixed::FixedSources,
) -> Result<f64> {
    let mut radius = 0.0_f64;
    for placement in scenery.iter().flat_map(|scene| &scene.placements) {
        if placement.at.cmplt(selection.0).any() || placement.at.cmpge(selection.1).any() {
            continue;
        }
        if fixed.contains_model(placement.model) {
            continue;
        }
        let model =
            models.get(placement.model).with_context(|| format!("no contact policy for {}", placement.model))?;
        if !placement.scale.is_finite() || placement.scale <= 0.0 {
            bail!("invalid placement scale");
        }
        for point in model.triangles.iter().flatten() {
            radius = radius.max(DVec2::new(point.x, point.z).length() * placement.scale);
        }
    }
    Ok(radius)
}

pub fn check(model: &Model, name: &str, at: DVec2, yaw: f64, scale: f64, origin: f64, land: &Land<'_>) -> Result<f64> {
    let mut min = f64::INFINITY;
    let rotate = DVec2::from_angle(yaw);
    for triangle in &model.triangles {
        let vertices = triangle.map(|p| {
            let xy = at + rotate.rotate(DVec2::new(p.x, -p.z) * scale);
            xy.extend(origin + p.y * scale)
        });
        let outline = vertices.map(DVec3::truncate);
        let mut sample = |xy: DVec2, model_height: f64| {
            if xy.cmplt(land.low).any() || xy.cmpge(land.high).any() {
                return;
            }
            let xy = xy.as_vec2().as_dvec2();
            if let Some(height) = land.height(xy) {
                min = min.min(model_height - height);
            }
        };
        for vertex in vertices {
            sample(vertex.truncate(), vertex.z);
        }
        let Some(surface) = land.rendered else { continue };
        let mut under = surface.all_under(outline);
        under.extend(land.raised.under(outline, land.middle));
        if super::surface::weights(outline, outline[0]).is_none() {
            // A vertical face projects to segments, whose interior can meet a peak missed by its vertices.
            for i in 0..3 {
                let a = vertices[i];
                let b = vertices[(i + 1) % 3];
                let direction = b.truncate() - a.truncate();
                let length2 = direction.length_squared();
                if length2 == 0.0 {
                    continue;
                }
                for triangle in &under {
                    for edge in 0..3 {
                        let c = triangle[edge].truncate();
                        let d = triangle[(edge + 1) % 3].truncate();
                        let along = d - c;
                        let denominator = direction.perp_dot(along);
                        if denominator.abs() < 1e-12 {
                            if (c - a.truncate()).perp_dot(direction).abs() < 1e-12 {
                                for point in [c, d] {
                                    let t = (point - a.truncate()).dot(direction) / length2;
                                    if (0.0..=1.0).contains(&t) {
                                        sample(a.truncate() + direction * t, a.z + (b.z - a.z) * t);
                                    }
                                }
                            }
                        } else {
                            let t = (c - a.truncate()).perp_dot(along) / denominator;
                            let u = (c - a.truncate()).perp_dot(direction) / denominator;
                            if (0.0..=1.0).contains(&t) && (0.0..=1.0).contains(&u) {
                                sample(a.truncate() + direction * t, a.z + (b.z - a.z) * t);
                            }
                        }
                    }
                }
            }
            continue;
        }
        for ground in under {
            for xy in super::surface::cut(outline.to_vec(), ground.map(DVec3::truncate)) {
                if let Some(weights) = super::surface::weights(outline, xy) {
                    sample(xy, weights.x * vertices[0].z + weights.y * vertices[1].z + weights.z * vertices[2].z);
                }
            }
        }
    }
    if !min.is_finite() {
        bail!("{name} at {at} has no contact surface in the exported extent");
    }
    Ok(min)
}

/// A source measurement is keyed by the model and its exact authored placement, and carries its source XY.
struct Entry {
    at: DVec2,
    gap: f64,
}

fn verify_gap(name: &str, at: DVec2, gap: f64, expected: f64) -> Result<()> {
    const SOURCE_TOLERANCE_M: f64 = 0.01;
    if (gap - expected).abs() > SOURCE_TOLERANCE_M {
        bail!("{name} at {at} contact differs from source: {gap:.4} m vs {expected:.4} m");
    }
    Ok(())
}

/// @cc [owner:fontanierh,label:correctness] source-contact-reference
/// Every selected placement MUST agree with its independently measured minimum gap on the logical visible owner
/// surface. Fixed source geometry MUST also match its exact source pose and geometry and be selected by its bounds.
/// Validation MUST run on every export, including tile checksum hits, and MUST fail on missing or changed rows.
/// Cropping tiles MUST NOT replace an owner with hidden terrain or change the reference surface.
pub struct Reference {
    low: DVec2,
    high: DVec2,
    entries: BTreeMap<String, Entry>,
}

impl Reference {
    pub fn read(path: &Path) -> Result<Self> {
        let data = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;
        if data.len() < 44 || &data[..8] != b"HCNT0001" {
            bail!("invalid source contact reference header");
        }
        let number = |bytes: &[u8]| f64::from_le_bytes(bytes.try_into().unwrap());
        let low = DVec2::new(number(&data[8..16]), number(&data[16..24]));
        let high = DVec2::new(number(&data[24..32]), number(&data[32..40]));
        let count = u32::from_le_bytes(data[40..44].try_into().unwrap()) as usize;
        if !low.is_finite()
            || !high.is_finite()
            || !low.cmplt(high).all()
            || count.checked_mul(56).and_then(|n| n.checked_add(44)) != Some(data.len())
        {
            bail!("invalid source contact reference extent or size");
        }
        let mut entries = BTreeMap::new();
        for row in data[44..].chunks_exact(56) {
            let id: String = row[..32].iter().map(|b| format!("{b:02x}")).collect();
            let entry = Entry { at: DVec2::new(number(&row[32..40]), number(&row[40..48])), gap: number(&row[48..56]) };
            if !entry.at.is_finite()
                || !entry.gap.is_finite()
                || entry.at.cmplt(low).any()
                || entry.at.cmpge(high).any()
                || entries.insert(id, entry).is_some()
            {
                bail!("invalid or duplicate source contact reference row");
            }
        }
        Ok(Self { low, high, entries })
    }
}

/// Reject changed authored placements or changed contact with the source-recorded owning surface.
pub fn validate(
    scenery: &[Scenery],
    land: &Land<'_>,
    selection: (DVec2, DVec2),
    models: &BTreeMap<String, Model>,
    reference: &Reference,
    fixed: &super::fixed::FixedSources,
) -> Result<()> {
    let (low, high) = selection;
    if low.cmplt(reference.low).any() || high.cmpgt(reference.high).any() {
        bail!("world extent exceeds source contact reference coverage; extend the source reference first");
    }
    let mut unseen: BTreeSet<_> = reference
        .entries
        .iter()
        .filter(|(id, entry)| {
            fixed.selects_id(id, selection).unwrap_or_else(|| entry.at.cmpge(low).all() && entry.at.cmplt(high).all())
        })
        .map(|(id, _)| id.as_str())
        .collect();
    let started = std::time::Instant::now();
    let mut last_report = started;
    let mut completed = 0usize;
    for scene in scenery {
        for placement in &scene.placements {
            let (at, yaw, scale, _) = effective_pose(land.raised, land.rendered, placement);
            if fixed.contains_model(placement.model) {
                if !fixed.selects_placement(placement, at, yaw, scale, selection)? {
                    continue;
                }
            } else if at.cmplt(low).any() || at.cmpge(high).any() {
                continue;
            }
            let id = key(placement);
            if !unseen.remove(id.as_str()) {
                bail!("missing or duplicate source contact placement {} at {at}", placement.model);
            }
            let model =
                models.get(placement.model).with_context(|| format!("no contact policy for {}", placement.model))?;
            let origin = if fixed.contains_model(placement.model) {
                placement.origin_height_m.context("fixed source needs an absolute height")?
            } else {
                let seat =
                    land.height(at).with_context(|| format!("{} has no drawn ground at {at}", placement.model))?;
                placement.origin_height_m.unwrap_or(seat + placement.origin_offset_m)
            };
            let gap = check(model, placement.model, at, yaw, scale, origin, land)?;
            verify_gap(placement.model, at, gap, reference.entries[&id].gap)?;
            completed += 1;
            if last_report.elapsed().as_secs() >= 20 {
                println!("ground contacts: {completed} checked in {}s", started.elapsed().as_secs());
                last_report = std::time::Instant::now();
            }
        }
    }
    if !unseen.is_empty() {
        bail!("{} source contact placements are missing from the exported extent", unseen.len());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::glb::Mesh;
    use crate::world::ground::Ground;
    use crate::world::raised::{Prepared, Raised};
    use crate::world::surface::Surface;

    fn peak(height: f32) -> Surface {
        let mesh = Mesh {
            positions: vec![[0., 0., 0.], [2., 0., 0.], [2., 0., -2.], [0., 0., -2.], [1., height, -1.]],
            indices: vec![0, 1, 4, 1, 2, 4, 2, 3, 4, 3, 0, 4],
            ..Default::default()
        };
        Surface::new(&mesh)
    }

    #[test]
    fn interior_surface_contact_and_later_edits_are_checked() {
        let ground = Ground::page(2, 1.0, |_, _| 0.0);
        let raised = Prepared::new(&[], DVec2::ZERO, 2.0);
        let surface = peak(0.2);
        let land = Land {
            ground: &ground,
            rendered: Some(&surface),
            raised: &raised,
            middle: false,
            low: DVec2::ZERO,
            high: DVec2::splat(2.0),
            regions: &[],
        };
        let model = Model {
            triangles: vec![[DVec3::new(0.1, 0.0, -0.1), DVec3::new(1.9, 0.0, -0.1), DVec3::new(0.1, 0.0, -1.9)]],
        };
        let expected = check(&model, "test", DVec2::ZERO, 0.0, 1.0, 0.1, &land).unwrap();
        assert!(expected < 0.0, "the terrain peak intersects the triangle interior");
        let shifted = check(&model, "test", DVec2::ZERO, 0.0, 1.0, 0.5, &land).unwrap();
        assert!(verify_gap("test", DVec2::ZERO, shifted, expected).is_err());
        let flat = peak(0.0);
        let flattened = Land { rendered: Some(&flat), ..land };
        let changed_ground = check(&model, "test", DVec2::ZERO, 0.0, 1.0, 0.1, &flattened).unwrap();
        assert!(verify_gap("test", DVec2::ZERO, changed_ground, expected).is_err());
        let moved = Model { triangles: model.triangles.iter().map(|t| t.map(|p| p + DVec3::Y * 0.4)).collect() };
        let changed_model = check(&moved, "test", DVec2::ZERO, 0.0, 1.0, 0.1, &land).unwrap();
        assert!(verify_gap("test", DVec2::ZERO, changed_model, expected).is_err());
    }

    #[test]
    fn vertical_face_detects_a_peak_between_its_vertices() {
        let ground = Ground::page(2, 1.0, |_, _| 0.0);
        let raised = Prepared::new(&[], DVec2::ZERO, 2.0);
        let surface = peak(0.2);
        let land = Land {
            ground: &ground,
            rendered: Some(&surface),
            raised: &raised,
            middle: false,
            low: DVec2::ZERO,
            high: DVec2::splat(2.0),
            regions: &[],
        };
        let model = Model {
            triangles: vec![[DVec3::new(0.1, 0.0, -1.0), DVec3::new(1.9, 0.0, -1.0), DVec3::new(0.1, 1.0, -1.0)]],
        };
        let gap = check(&model, "wall", DVec2::ZERO, 0.0, 1.0, 0.1, &land).unwrap();
        assert!((gap + 0.1).abs() < 1e-6, "peak must be sampled: {gap}");
        let flat = peak(0.0);
        let changed = Land { rendered: Some(&flat), ..land };
        let flat_gap = check(&model, "wall", DVec2::ZERO, 0.0, 1.0, 0.1, &changed).unwrap();
        assert!(verify_gap("wall", DVec2::ZERO, flat_gap, gap).is_err());
    }

    #[test]
    fn vertical_face_detects_peak_on_collinear_surface_edges() {
        let ground = Ground::page(2, 1.0, |_, _| 0.0);
        let raised = Prepared::new(&[], DVec2::ZERO, 2.0);
        let surface = Surface::new(&Mesh {
            positions: vec![
                [0., 0., 0.],
                [2., 0., 0.],
                [0., 0., -1.],
                [1., 0.2, -1.],
                [2., 0., -1.],
                [0., 0., -2.],
                [2., 0., -2.],
            ],
            indices: vec![0, 1, 3, 0, 3, 2, 1, 4, 3, 2, 3, 5, 3, 6, 5, 3, 4, 6],
            ..Default::default()
        });
        let land = Land {
            ground: &ground,
            rendered: Some(&surface),
            raised: &raised,
            middle: false,
            low: DVec2::ZERO,
            high: DVec2::splat(2.0),
            regions: &[],
        };
        let model =
            Model { triangles: vec![[DVec3::new(0.1, 0., -1.), DVec3::new(1.9, 0., -1.), DVec3::new(0.1, 1., -1.)]] };
        let gap = check(&model, "wall", DVec2::ZERO, 0.0, 1.0, 0.1, &land).unwrap();
        assert!((gap + 0.1).abs() < 1e-6, "collinear peak must be sampled: {gap}");
    }

    #[test]
    fn contact_uses_raised_owner_not_hidden_ground() {
        let ground = Ground::page(2, 1.0, |_, _| 0.0);
        let surface = peak(0.0);
        let point = |x, y| (DVec2::new(x, y), DVec2::ZERO);
        let raised = [Raised {
            name: "top".into(),
            texture: "ground".into(),
            ground: true,
            paint: None,
            height: 0.4,
            clearance: 0.0,
            cut_ground: false,
            triangles: vec![
                [point(0., 0.), point(2., 0.), point(2., 2.)],
                [point(0., 0.), point(2., 2.), point(0., 2.)],
            ],
        }];
        let mut prepared = Prepared::new(&raised, DVec2::ZERO, 2.0);
        prepared.add_tile((0, 0), &surface, false).unwrap();
        let land = Land {
            ground: &ground,
            rendered: Some(&surface),
            raised: &prepared,
            middle: false,
            low: DVec2::ZERO,
            high: DVec2::splat(2.0),
            regions: &[],
        };
        let model = Model {
            triangles: vec![[DVec3::new(0.5, 0., -0.5), DVec3::new(1.5, 0., -0.5), DVec3::new(0.5, 0., -1.5)]],
        };
        let on_owner = check(&model, "test", DVec2::ZERO, 0.0, 1.0, 0.4, &land).unwrap();
        assert!(on_owner.abs() < 0.001);
        let hidden_ground = check(&model, "test", DVec2::ZERO, 0.0, 1.0, 0.0, &land).unwrap();
        assert!(verify_gap("test", DVec2::ZERO, hidden_ground, on_owner).is_err());
    }

    #[test]
    fn grounded_absolute_height_still_requires_origin_owner() {
        let placement = Placement {
            model: "grounded",
            at: DVec2::splat(-0.5),
            yaw: 0.0,
            scale: 1.0,
            origin_offset_m: 0.0,
            origin_height_m: Some(1.0),
            afar: false,
        };
        let triangle = [DVec3::new(1.0, 0.0, -1.0), DVec3::new(1.5, 0.0, -1.0), DVec3::new(1.0, 0.0, -1.5)];
        let models = BTreeMap::from([("grounded".to_string(), Model { triangles: vec![triangle] })]);
        let reference = Reference {
            low: DVec2::splat(-1.0),
            high: DVec2::splat(3.0),
            entries: BTreeMap::from([(key(&placement), Entry { at: placement.at, gap: 1.0 })]),
        };
        let scene = Scenery { placements: vec![placement], ..Default::default() };
        let ground = Ground::page(3, 1.0, |_, _| 0.0);
        let raised = Prepared::new(&[], DVec2::ZERO, 3.0);
        let land = Land {
            ground: &ground,
            rendered: None,
            raised: &raised,
            middle: false,
            low: DVec2::splat(-1.0),
            high: DVec2::splat(3.0),
            regions: &[],
        };
        assert!(
            validate(
                &[scene],
                &land,
                (DVec2::splat(-1.0), DVec2::splat(3.0)),
                &models,
                &reference,
                &super::super::fixed::FixedSources::empty()
            )
            .is_err()
        );
    }

    #[test]
    fn fixed_crop_checks_source_minimum_even_when_origin_is_outside() {
        let placement = || Placement {
            model: "fixed",
            at: DVec2::ZERO,
            yaw: 0.0,
            scale: 1.0,
            origin_offset_m: 0.0,
            origin_height_m: Some(1.0),
            afar: false,
        };
        let triangle = [DVec3::new(1.0, 0.0, -1.0), DVec3::new(1.8, 0.0, -1.0), DVec3::new(1.0, 0.0, -1.8)];
        let fixed = super::super::fixed::FixedSources::test_instance(
            &placement(),
            vec![triangle],
            [[1.0, 1.0, 1.0], [1.8, 1.8, 1.0]],
        );
        let model = Model { triangles: vec![triangle] };
        let models = BTreeMap::from([("fixed".to_string(), model)]);
        let reference = Reference {
            low: DVec2::ZERO,
            high: DVec2::splat(3.0),
            entries: BTreeMap::from([(key(&placement()), Entry { at: placement().at, gap: 1.0 })]),
        };
        let scene = Scenery { placements: vec![placement()], ..Default::default() };
        let crop = (DVec2::splat(1.1), DVec2::splat(1.7));
        let ground = Ground::page(3, 1.0, |_, _| 0.0);
        let raised = Prepared::new(&[], DVec2::ZERO, 3.0);
        let land = Land {
            ground: &ground,
            rendered: None,
            raised: &raised,
            middle: false,
            low: DVec2::ZERO,
            high: DVec2::splat(3.0),
            regions: &[],
        };
        assert!(validate(std::slice::from_ref(&scene), &land, crop, &models, &reference, &fixed).is_ok());
        assert!(validate(&[Scenery::default()], &land, crop, &models, &reference, &fixed).is_err());
        let duplicate = Scenery { placements: vec![placement(), placement()], ..Default::default() };
        assert!(validate(&[duplicate], &land, crop, &models, &reference, &fixed).is_err());
        let changed_ground = Ground::page(3, 1.0, |_, _| 0.2);
        let changed = Land { ground: &changed_ground, ..land };
        assert!(validate(&[scene], &changed, crop, &models, &reference, &fixed).is_err());
    }

    #[test]
    fn crop_uses_the_same_logical_surface_and_checks_selected_rows() {
        let ground = Ground::page(2, 1.0, |_, _| 0.0);
        let surface = peak(0.2);
        let prepared = Prepared::new(&[], DVec2::ZERO, 2.0);
        let land = Land {
            ground: &ground,
            rendered: Some(&surface),
            raised: &prepared,
            middle: false,
            low: DVec2::ZERO,
            high: DVec2::splat(2.0),
            regions: &[],
        };
        let model = Model {
            triangles: vec![[DVec3::new(0.0, 0.0, 0.0), DVec3::new(0.6, 0.0, 0.0), DVec3::new(0.0, 0.0, -0.6)]],
        };
        let placement = |at| Placement {
            model: "test",
            at,
            yaw: 0.0,
            scale: 1.0,
            origin_offset_m: 0.0,
            origin_height_m: Some(0.1),
            afar: true,
        };
        let a = placement(DVec2::new(0.5, 0.5));
        let b = placement(DVec2::new(1.2, 1.2));
        let entries = [&a, &b]
            .into_iter()
            .map(|p| {
                let gap = check(&model, "test", p.at, p.yaw, p.scale, 0.1, &land).unwrap();
                (key(p), Entry { at: p.at, gap })
            })
            .collect();
        let reference = Reference { low: DVec2::ZERO, high: DVec2::splat(2.0), entries };
        let models = BTreeMap::from([("test".to_string(), model)]);
        let scene = Scenery { placements: vec![a, b], ..Default::default() };
        assert!(
            validate(
                std::slice::from_ref(&scene),
                &land,
                (DVec2::ZERO, DVec2::splat(2.0)),
                &models,
                &reference,
                &super::super::fixed::FixedSources::empty()
            )
            .is_ok()
        );
        // The first triangle extends past the crop; it must still use the same owner surface.
        assert!(
            validate(
                std::slice::from_ref(&scene),
                &land,
                (DVec2::ZERO, DVec2::splat(1.0)),
                &models,
                &reference,
                &super::super::fixed::FixedSources::empty()
            )
            .is_ok()
        );
        let missing = Scenery::default();
        assert!(
            validate(
                &[missing],
                &land,
                (DVec2::ZERO, DVec2::splat(1.0)),
                &models,
                &reference,
                &super::super::fixed::FixedSources::empty()
            )
            .is_err()
        );
        let mut altered = scene;
        altered.placements[0].yaw = 0.1;
        assert!(
            validate(
                &[altered],
                &land,
                (DVec2::ZERO, DVec2::splat(1.0)),
                &models,
                &reference,
                &super::super::fixed::FixedSources::empty()
            )
            .is_err()
        );
    }
}
