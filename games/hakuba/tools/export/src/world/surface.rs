//! Finding what lies under a point of a mesh, and cutting shapes along its triangles.

use std::collections::HashMap;

use glam::{DVec2, DVec3};

use crate::glb::Mesh;

/// A mesh's triangles in the map's frame, to find what lies under a point.
#[derive(Clone)]
pub struct Surface {
    pub triangles: Vec<[DVec3; 3]>,
    /// The triangles that reach into each square of `SURFACE_CELL_M`, by square.
    cells: HashMap<(i64, i64), Vec<usize>>,
    crossings: Option<Box<Surface>>,
}

/// The side of the squares a [`Surface`] sorts its triangles into.
const SURFACE_CELL_M: f64 = 4.0;

/// How far outside a triangle a point may be, as a share of the triangle, and still count as on it. Meshes store
/// positions in 32-bit floats, so points on a shared edge can land a hair to either side.
const ON_TRIANGLE: f64 = 1e-4;

impl Surface {
    pub fn new(mesh: &Mesh) -> Self {
        let corner = |k: u32| {
            let [x, y, z] = mesh.positions[k as usize].map(f64::from);
            DVec3::new(x, -z, y)
        };
        let triangles: Vec<[DVec3; 3]> =
            mesh.indices.chunks(3).map(|t| [corner(t[0]), corner(t[1]), corner(t[2])]).collect();
        let mut cells: HashMap<(i64, i64), Vec<usize>> = HashMap::new();
        for (n, triangle) in triangles.iter().enumerate() {
            for square in squares(triangle.map(DVec3::truncate)) {
                cells.entry(square).or_default().push(n);
            }
        }
        Self { triangles, cells, crossings: None }
    }

    /// A terrain and explicit authored crossings: a vertical query returns the first rendered surface.
    pub fn with_crossings(ground: &Mesh, authored: &[Mesh]) -> Self {
        let mut surface = Self::new(ground);
        let mut combined = Mesh::default();
        for mesh in authored {
            let start = combined.positions.len() as u32;
            combined.positions.extend_from_slice(&mesh.positions);
            combined.indices.extend(mesh.indices.iter().map(|i| i + start));
        }
        if !combined.indices.is_empty() {
            surface.crossings = Some(Box::new(Self::new(&combined)));
        }
        surface
    }

    /// The triangles that may lie under any part of `outline`.
    pub fn under(&self, outline: [DVec2; 3]) -> Vec<[DVec3; 3]> {
        let mut found: Vec<usize> =
            squares(outline).filter_map(|square| self.cells.get(&square)).flatten().copied().collect();
        found.sort();
        found.dedup();
        found.into_iter().map(|n| self.triangles[n]).collect()
    }

    /// The height of the triangle under `p`, if any.
    pub fn ground_height(&self, p: DVec2) -> Option<f64> {
        let square = ((p.x / SURFACE_CELL_M).floor() as i64, (p.y / SURFACE_CELL_M).floor() as i64);
        self.cells.get(&square).and_then(|cells| {
            cells.iter().find_map(|&n| {
                let [a, b, c] = self.triangles[n];
                let w = weights([a, b, c].map(DVec3::truncate), p)?;
                (w.min_element() >= -ON_TRIANGLE).then_some(w.x * a.z + w.y * b.z + w.z * c.z)
            })
        })
    }

    /// Whether an exact stored point is inside an explicitly authored crossing.
    pub fn crossing_contains(&self, p: DVec2) -> bool {
        self.crossings.as_ref().is_some_and(|surface| surface.first_visible(p).is_some())
    }

    /// Apply only this surface's explicitly authored crossing to the retained terrain height.
    pub fn crossing_over(&self, p: DVec2, ground: Option<f64>) -> Option<f64> {
        let authored = self.crossings.as_ref().and_then(|surface| surface.first_visible(p));
        match (ground, authored) {
            (Some(g), Some(a)) if a > g => Some(a),
            (Some(g), _) => Some(g),
            (None, Some(a)) => Some(a),
            (None, None) => None,
        }
    }

    pub fn height(&self, p: DVec2) -> Option<f64> {
        self.crossing_over(p, self.ground_height(p))
    }

    /// Height reached first by a vertical ray over this explicitly crossing source surface.
    pub fn first_visible(&self, p: DVec2) -> Option<f64> {
        self.first_visible_face(p).map(|(height, _)| height)
    }

    fn first_visible_face(&self, p: DVec2) -> Option<(f64, [DVec3; 3])> {
        let square = ((p.x / SURFACE_CELL_M).floor() as i64, (p.y / SURFACE_CELL_M).floor() as i64);
        self.cells
            .get(&square)?
            .iter()
            .filter_map(|&n| {
                let triangle = self.triangles[n];
                let [a, b, c] = triangle;
                let w = weights([a, b, c].map(DVec3::truncate), p)?;
                (w.min_element() >= 0.0).then_some((w.x * a.z + w.y * b.z + w.z * c.z, triangle))
            })
            .max_by(|a, b| a.0.total_cmp(&b.0))
    }

    /// Slope of the source crossing only when that stored triangle is actually visible above retained terrain.
    pub fn crossing_slope_over(&self, p: DVec2, ground: Option<f64>) -> Option<f64> {
        let (height, [a, b, c]) = self.crossings.as_ref()?.first_visible_face(p)?;
        if ground.is_some_and(|g| g >= height) {
            return None;
        }
        let normal = (b - a).cross(c - a);
        (normal.z > 0.0).then_some(normal.truncate().length() / normal.z)
    }

    pub fn height_exact(&self, p: DVec2) -> Option<f64> {
        let square = ((p.x / SURFACE_CELL_M).floor() as i64, (p.y / SURFACE_CELL_M).floor() as i64);
        self.cells.get(&square)?.iter().find_map(|&n| {
            let [a, b, c] = self.triangles[n];
            let w = weights([a, b, c].map(DVec3::truncate), p)?;
            (w.min_element() >= 0.0).then_some(w.x * a.z + w.y * b.z + w.z * c.z)
        })
    }

    /// Whether a point lies on the actual stored triangles, without extending their boundaries.
    pub fn contains_exact(&self, p: DVec2) -> bool {
        let square = ((p.x / SURFACE_CELL_M).floor() as i64, (p.y / SURFACE_CELL_M).floor() as i64);
        self.cells.get(&square).is_some_and(|triangles| {
            triangles.iter().any(|&n| {
                let [a, b, c] = self.triangles[n].map(DVec3::truncate);
                let sides = [(a, b), (b, c), (c, a)].map(|(a, b)| (b - a).perp_dot(p - a));
                (b - a).perp_dot(c - a) != 0.0 && (sides.iter().all(|s| *s >= 0.0) || sides.iter().all(|s| *s <= 0.0))
            })
        })
    }
}

/// The squares of `SURFACE_CELL_M` that the box around `triangle` reaches into.
fn squares(triangle: [DVec2; 3]) -> impl Iterator<Item = (i64, i64)> {
    let [a, b, c] = triangle;
    let square = |x: f64| (x / SURFACE_CELL_M).floor() as i64;
    let (low, high) = (a.min(b).min(c), a.max(b).max(c));
    (square(low.x)..=square(high.x)).flat_map(move |i| (square(low.y)..=square(high.y)).map(move |j| (i, j)))
}

/// How much each corner of `triangle` weighs in `p`; the three weights add up to one. None if the triangle has no
/// area.
pub fn weights(triangle: [DVec2; 3], p: DVec2) -> Option<DVec3> {
    let [a, b, c] = triangle;
    let area = (b - a).perp_dot(c - a);
    if area.abs() < 1e-12 {
        return None;
    }
    let (s, t) = ((p - a).perp_dot(c - a) / area, (b - a).perp_dot(p - a) / area);
    Some(DVec3::new(1.0 - s - t, s, t))
}

/// The part of the convex `polygon` inside `triangle`, its corners in the polygon's order.
pub fn cut(mut polygon: Vec<DVec2>, triangle: [DVec2; 3]) -> Vec<DVec2> {
    let turn = (triangle[1] - triangle[0]).perp_dot(triangle[2] - triangle[0]).signum();
    for k in 0..3 {
        let (a, b) = (triangle[k], triangle[(k + 1) % 3]);
        let side = |p: DVec2| turn * (b - a).perp_dot(p - a);
        let mut kept = Vec::new();
        for n in 0..polygon.len() {
            let (p, q) = (polygon[n], polygon[(n + 1) % polygon.len()]);
            let (sp, sq) = (side(p), side(q));
            if sp >= 0.0 {
                kept.push(p);
            }
            if (sp >= 0.0) != (sq >= 0.0) {
                kept.push(p + (q - p) * (sp / (sp - sq)));
            }
        }
        polygon = kept;
        if polygon.is_empty() {
            break;
        }
    }
    let area: f64 = (1..polygon.len().saturating_sub(1))
        .map(|n| (polygon[n] - polygon[0]).perp_dot(polygon[n + 1] - polygon[0]))
        .sum();
    if area.abs() < 1e-8 { Vec::new() } else { polygon }
}
