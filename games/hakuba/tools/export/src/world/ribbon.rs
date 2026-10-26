//! Ribbons: strips of even width along a smooth curve, for regions to lay as overlays.

use glam::DVec2;

/// The triangles of a strip `width` wide along a Catmull-Rom curve through `course`, one pair of triangles every
/// metre along it. The texture spans the strip's width and repeats every `texture_m` along it.
pub fn ribbon(course: &[[f64; 2]], width: f64, texture_m: f64) -> Vec<[(DVec2, DVec2); 3]> {
    let control: Vec<DVec2> = course.iter().map(|&[x, y]| DVec2::new(x, y)).collect();
    let padded: Vec<DVec2> =
        [control[0]].into_iter().chain(control.iter().copied()).chain([control[control.len() - 1]]).collect();
    let mut curve = Vec::new();
    for k in 1..padded.len() - 2 {
        let (p0, p1, p2, p3) = (padded[k - 1], padded[k], padded[k + 1], padded[k + 2]);
        for step in 0..60 {
            let s = step as f64 / 60.0;
            curve.push(
                0.5 * (2.0 * p1
                    + (p2 - p0) * s
                    + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * s * s
                    + (3.0 * p1 - p0 - 3.0 * p2 + p3) * s * s * s),
            );
        }
    }
    let mut lengths = vec![0.0];
    for pair in curve.windows(2) {
        lengths.push(lengths.last().unwrap() + pair[0].distance(pair[1]));
    }
    let mut points = Vec::new();
    let mut segment = 0;
    let mut along = 0.0;
    while along < *lengths.last().unwrap() {
        while lengths[segment + 1] < along {
            segment += 1;
        }
        let t = (along - lengths[segment]) / (lengths[segment + 1] - lengths[segment]);
        points.push(curve[segment].lerp(curve[segment + 1], t));
        along += 1.0;
    }
    let last = points.len() - 1;
    let tangents: Vec<DVec2> =
        (0..points.len()).map(|i| (points[(i + 1).min(last)] - points[i.saturating_sub(1)]).normalize()).collect();
    let half = width / 2.0;
    let corner = |i: usize, u: f64| {
        let p = points[i] + tangents[i].perp() * half * (2.0 * u - 1.0);
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
