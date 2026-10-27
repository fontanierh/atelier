//! Exact source witnesses for fixed world geometry, whose mesh origin is not a ground-contact point.
use super::scenery::{Land, Scenery, effective_pose};
use crate::glb::Glb;
use anyhow::{Context, Result, bail};
use glam::{DVec2, DVec3};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

#[derive(Deserialize)]
struct Witness {
    id: String,
    model: String,
    x: f64,
    y: f64,
    height: f64,
    yaw: f64,
    scale: f64,
    geometry_sha256: String,
    world_bounds_m: [[f64; 3]; 2],
}

fn geometry_hash(triangles: &[[DVec3; 3]]) -> String {
    let mut digest = Sha256::new();
    for vertex in triangles.iter().flatten() {
        for n in vertex.to_array() {
            digest.update((n as f32).to_bits().to_le_bytes());
        }
    }
    format!("{:x}", digest.finalize())
}

fn verify_geometry(expected: &str, triangles: &[[DVec3; 3]]) -> Result<()> {
    if geometry_hash(triangles) != expected {
        bail!("fixed source geometry changed");
    }
    Ok(())
}

pub struct FixedSources {
    entries: BTreeMap<String, Witness>,
    geometry: BTreeMap<String, Vec<[DVec3; 3]>>,
}

impl FixedSources {
    pub fn empty() -> Self {
        Self { entries: BTreeMap::new(), geometry: BTreeMap::new() }
    }
    pub fn read(path: &Path) -> Result<Self> {
        let witnesses: Vec<Witness> = serde_json::from_slice(&std::fs::read(path)?)?;
        let mut entries = BTreeMap::new();
        for witness in witnesses {
            if entries.insert(witness.id.clone(), witness).is_some() {
                bail!("duplicate fixed-source witness");
            }
        }
        let mut geometry = BTreeMap::new();
        for (id, witness) in &entries {
            if id.len() != 64
                || !id.bytes().all(|b| b.is_ascii_hexdigit())
                || ![witness.x, witness.y, witness.height, witness.yaw, witness.scale].iter().all(|v| v.is_finite())
                || witness.scale <= 0.0
                || witness.world_bounds_m.iter().flatten().any(|v| !v.is_finite())
                || (0..3).any(|i| witness.world_bounds_m[0][i] > witness.world_bounds_m[1][i])
            {
                bail!("invalid fixed-source witness");
            }
            if !geometry.contains_key(&witness.model) {
                crate::uri_of_asset(&witness.model, "glb")?;
                let path = Path::new(crate::ASSETS)
                    .join(&witness.model)
                    .join(format!("{}.glb", witness.model.rsplit('/').next().unwrap()));
                let triangles = Glb::read(&path)?.node_triangles("full")?;
                if triangles.is_empty() {
                    bail!("fixed source {} has no triangles", witness.model);
                }
                geometry.insert(witness.model.clone(), triangles);
            }
            verify_geometry(&witness.geometry_sha256, &geometry[&witness.model])
                .with_context(|| format!("fixed source {}", witness.model))?;
        }
        Ok(Self { entries, geometry })
    }

    pub fn models(&self) -> impl Iterator<Item = &str> {
        self.geometry.keys().map(String::as_str)
    }
    pub fn contains_model(&self, model: &str) -> bool {
        self.geometry.contains_key(model)
    }

    pub fn validate(&self, scenery: &[Scenery], land: &Land<'_>, selection: (DVec2, DVec2)) -> Result<()> {
        let (low, high) = selection;
        let mut unseen: BTreeSet<&str> = self
            .entries
            .iter()
            .filter(|(_, w)| DVec2::new(w.x, w.y).cmpge(low).all() && DVec2::new(w.x, w.y).cmplt(high).all())
            .map(|(id, _)| id.as_str())
            .collect();
        for placement in scenery.iter().flat_map(|scene| &scene.placements) {
            if !self.contains_model(placement.model) {
                continue;
            }
            let (at, yaw, scale, _) = effective_pose(land.raised, land.rendered, placement);
            if at.cmplt(low).any() || at.cmpge(high).any() {
                continue;
            }
            let id = super::contact::key(placement);
            if !unseen.remove(id.as_str()) {
                bail!("missing, moved or duplicate fixed source {} at {at}", placement.model);
            }
            let w = &self.entries[&id];
            let height = placement.origin_height_m.context("fixed source needs an absolute height")?;
            if w.model != placement.model || [w.x, w.y, w.height, w.yaw, w.scale] != [at.x, at.y, height, yaw, scale] {
                bail!("fixed source pose changed for {}", placement.model);
            }
            let rotation = DVec2::from_angle(yaw);
            let mut minimum = DVec3::splat(f64::INFINITY);
            let mut maximum = DVec3::splat(f64::NEG_INFINITY);
            for point in self.geometry[placement.model].iter().flatten() {
                let xy = at + rotation.rotate(DVec2::new(point.x, -point.z) * scale);
                let p = xy.extend(height + point.y * scale);
                minimum = minimum.min(p);
                maximum = maximum.max(p);
            }
            let expected_min = DVec3::from_array(w.world_bounds_m[0]);
            let expected_max = DVec3::from_array(w.world_bounds_m[1]);
            if (minimum - expected_min).abs().max_element() > 1e-4
                || (maximum - expected_max).abs().max_element() > 1e-4
            {
                bail!("fixed source world bounds changed for {}", placement.model);
            }
            if minimum.truncate().cmplt(land.low).any() || maximum.truncate().cmpgt(land.high).any() {
                bail!("fixed source geometry exceeds validated source extent for {}", placement.model);
            }
        }
        if !unseen.is_empty() {
            bail!("{} fixed source placements are missing", unseen.len());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::world::ground::Ground;
    use crate::world::raised::Prepared;
    use crate::world::scenery::Placement;

    #[test]
    fn fixed_geometry_witness_rejects_moves_and_missing_but_respects_crop() {
        let ground = Ground::page(2, 1.0, |_, _| 0.0);
        let raised = Prepared::new(&[], DVec2::ZERO, 2.0);
        let land = Land {
            ground: &ground,
            rendered: None,
            raised: &raised,
            middle: false,
            low: DVec2::splat(-10.0),
            high: DVec2::splat(10.0),
            regions: &[],
        };
        let placement = Placement {
            model: "props/example",
            at: DVec2::ZERO,
            yaw: 0.0,
            scale: 1.0,
            origin_offset_m: 0.0,
            origin_height_m: Some(1.0),
            afar: false,
        };
        let triangle = [DVec3::ZERO, DVec3::X, DVec3::NEG_Z];
        let mut entries = BTreeMap::new();
        entries.insert(
            super::super::contact::key(&placement),
            Witness {
                id: super::super::contact::key(&placement),
                model: placement.model.into(),
                x: 0.0,
                y: 0.0,
                height: 1.0,
                yaw: 0.0,
                scale: 1.0,
                geometry_sha256: geometry_hash(&[triangle]),
                world_bounds_m: [[0.0, 0.0, 1.0], [1.0, 1.0, 1.0]],
            },
        );
        let fixed = FixedSources { entries, geometry: BTreeMap::from([("props/example".into(), vec![triangle])]) };
        let scene = Scenery { placements: vec![placement], ..Default::default() };
        assert!(fixed.validate(std::slice::from_ref(&scene), &land, (DVec2::splat(-2.0), DVec2::splat(2.0))).is_ok());
        assert!(fixed.validate(&[], &land, (DVec2::splat(-2.0), DVec2::splat(2.0))).is_err());
        assert!(fixed.validate(&[], &land, (DVec2::splat(2.0), DVec2::splat(3.0))).is_ok());
        let moved = Placement {
            model: "props/example",
            at: DVec2::X,
            yaw: 0.0,
            scale: 1.0,
            origin_offset_m: 0.0,
            origin_height_m: Some(1.0),
            afar: false,
        };
        let moved_scene = Scenery { placements: vec![moved], ..Default::default() };
        assert!(fixed.validate(&[moved_scene], &land, (DVec2::splat(-2.0), DVec2::splat(2.0))).is_err());
        let mut changed = triangle;
        changed[1].x += 0.01;
        assert!(verify_geometry(&geometry_hash(&[triangle]), &[triangle]).is_ok());
        assert!(verify_geometry(&geometry_hash(&[triangle]), &[changed]).is_err());
    }
}
