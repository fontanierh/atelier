//! Ribbons: strips of even width along a smooth curve, for regions to lay as overlays.

use glam::DVec2;

use super::curve::curve;

/// The triangles of a strip `width` wide along a Catmull-Rom curve through `course`, one pair of triangles every
/// metre along it. The texture spans the strip's width and repeats every `texture_m` along it.
pub fn ribbon(course: &[[f64; 2]], width: f64, texture_m: f64) -> Vec<[(DVec2, DVec2); 3]> {
    let points = curve(course);
    let last = points.len() - 1;
    let half = width / 2.0;
    let corner = |i: usize, u: f64| {
        let (at, direction) = points[i];
        let p = at + direction.perp() * half * (2.0 * u - 1.0);
        (p, DVec2::new(u, i as f64 / texture_m))
    };
    let mut triangles = Vec::new();
    for k in 0..last {
        let [right, left, next_right, next_left] =
            [corner(k, 0.0), corner(k, 1.0), corner(k + 1, 0.0), corner(k + 1, 1.0)];
        triangles.extend([[next_right, next_left, left], [next_right, left, right]]);
    }
    triangles
}
