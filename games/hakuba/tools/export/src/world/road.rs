//! A road: a smooth curve through its course, laid on the ground.

use anyhow::{Result, bail};
use glam::{DVec2, DVec3};

use super::ground::Ground;
use super::regions::RoadPlan;
use super::surface::{Surface, cut, weights};
use super::{game, game_direction};
use crate::glb::Mesh;

/// How far the road sits above the ground under it.
const ROAD_LIFT_M: f64 = 0.06;

/// How close the road may come to the ground under it before the export fails.
const ROAD_CLEARANCE_M: f64 = 0.01;

/// How often the road's texture repeats along it.
const ROAD_TEXTURE_M: f64 = 8.0;

/// A road laid on the ground: its centre line, one point a metre, with the direction it runs at each.
pub struct Road {
    pub name: String,
    pub colour: [f64; 3],
    points: Vec<DVec3>,
    tangents: Vec<DVec2>,
    width: f64,
}

impl Road {
    /// The road `plan` on `ground`: a Catmull-Rom curve through the points of its course, one point every metre
    /// along it. The ground already holds the road's cut, so the road takes its heights from the ground.
    pub fn new(name: &str, plan: &RoadPlan, ground: &Ground) -> Result<Self> {
        let control: Vec<DVec2> = plan.course.iter().map(|&[x, y]| DVec2::new(x, y)).collect();
        let padded: Vec<DVec2> = [control[0]].into_iter().chain(control.iter().copied()).chain([control[control.len() - 1]]).collect();
        let mut curve = Vec::new();
        for k in 1..padded.len() - 2 {
            let (p0, p1, p2, p3) = (padded[k - 1], padded[k], padded[k + 1], padded[k + 2]);
            for step in 0..60 {
                let s = step as f64 / 60.0;
                curve.push(0.5 * (2.0 * p1 + (p2 - p0) * s + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * s * s + (3.0 * p1 - p0 - 3.0 * p2 + p3) * s * s * s));
            }
        }
        let mut lengths = vec![0.0];
        for pair in curve.windows(2) {
            lengths.push(lengths.last().unwrap() + pair[0].distance(pair[1]));
        }
        let mut flat = Vec::new();
        let mut segment = 0;
        let mut along = 0.0;
        while along < *lengths.last().unwrap() {
            while lengths[segment + 1] < along {
                segment += 1;
            }
            let t = (along - lengths[segment]) / (lengths[segment + 1] - lengths[segment]);
            flat.push(curve[segment].lerp(curve[segment + 1], t));
            along += 1.0;
        }
        let last = flat.len() - 1;
        let tangents = (0..flat.len()).map(|i| (flat[(i + 1).min(last)] - flat[i.saturating_sub(1)]).normalize()).collect();
        let mut points = Vec::new();
        for p in flat {
            let Some(height) = ground.height(p) else { bail!("the road leaves the ground at ({:.1}, {:.1})", p.x, p.y) };
            points.push(p.extend(height));
        }
        Ok(Self { name: name.into(), colour: plan.colour, points, tangents, width: plan.width_m })
    }

    /// The road over the ground `drawn` in one tile. Each metre of road is two triangles, cut along the edges of the
    /// ground triangles under them. Each cut piece lies `ROAD_LIFT_M` above its ground triangle, so the road follows
    /// the ground exactly and stops at the tile's edge. The texture spans the road's width and repeats every
    /// `ROAD_TEXTURE_M` along it.
    pub fn mesh(&self, ground: &Ground, drawn: &Surface) -> Mesh {
        let mut mesh = Mesh::default();
        let half = self.width / 2.0;
        let corner = |i: usize, u: f64| {
            let p = self.points[i].truncate() + self.tangents[i].perp() * half * (2.0 * u - 1.0);
            (p, DVec2::new(u, i as f64 / ROAD_TEXTURE_M))
        };
        for k in 0..self.points.len() - 1 {
            let [right, left, next_right, next_left] = [corner(k, 0.0), corner(k, 1.0), corner(k + 1, 0.0), corner(k + 1, 1.0)];
            for piece in [[next_right, next_left, left], [next_right, left, right]] {
                let outline = piece.map(|(p, _)| p);
                for under in drawn.under(outline) {
                    let flat = under.map(DVec3::truncate);
                    let cut = cut(outline.to_vec(), flat);
                    if cut.len() < 3 {
                        continue;
                    }
                    let first = mesh.positions.len() as u32;
                    for &p in &cut {
                        let on_ground = weights(flat, p).expect("a ground triangle has area");
                        let on_road = weights(outline, p).expect("a road triangle has area");
                        let height = on_ground.x * under[0].z + on_ground.y * under[1].z + on_ground.z * under[2].z;
                        let uv = on_road.x * piece[0].1 + on_road.y * piece[1].1 + on_road.z * piece[2].1;
                        mesh.positions.push(game(p.extend(height + ROAD_LIFT_M)).as_vec3().to_array());
                        mesh.normals.push(game_direction(ground.normal(p)).as_vec3().to_array());
                        mesh.uvs.push(uv.as_vec2().to_array());
                    }
                    for n in 1..cut.len() as u32 - 1 {
                        mesh.indices.extend([first, first + n, first + n + 1]);
                    }
                }
            }
        }
        mesh
    }
}

/// Fails if the road comes closer than `ROAD_CLEARANCE_M` to the ground drawn under it anywhere, checking points
/// spread over each of its triangles.
pub fn check_above(drawn: &Surface, road: &Mesh) -> Result<()> {
    const SPLITS: u32 = 4;
    for [a, b, c] in Surface::new(road).triangles {
        for s in 0..=SPLITS {
            for t in 0..=SPLITS - s {
                let p = a + (b - a) * (s as f64 / SPLITS as f64) + (c - a) * (t as f64 / SPLITS as f64);
                let Some(under) = drawn.height(p.truncate()) else {
                    bail!("the road runs off the tile's ground at ({:.1}, {:.1})", p.x, p.y);
                };
                if p.z - under < ROAD_CLEARANCE_M {
                    bail!("the road comes within {:.3} m of the ground at ({:.1}, {:.1})", p.z - under, p.x, p.y);
                }
            }
        }
    }
    Ok(())
}
