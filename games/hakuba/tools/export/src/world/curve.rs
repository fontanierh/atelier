//! Smooth curves through a course of points, such as a road's centre line, for regions to lay ribbons and place
//! things along.

use glam::DVec2;

/// A point every metre along a Catmull-Rom curve through `course`, from its first point, each with the curve's
/// direction there.
pub fn curve(course: &[[f64; 2]]) -> Vec<(DVec2, DVec2)> {
    let control: Vec<DVec2> = course.iter().map(|&[x, y]| DVec2::new(x, y)).collect();
    let padded: Vec<DVec2> =
        [control[0]].into_iter().chain(control.iter().copied()).chain([control[control.len() - 1]]).collect();
    let mut fine = Vec::new();
    for k in 1..padded.len() - 2 {
        let (p0, p1, p2, p3) = (padded[k - 1], padded[k], padded[k + 1], padded[k + 2]);
        for step in 0..60 {
            let s = step as f64 / 60.0;
            fine.push(
                0.5 * (2.0 * p1
                    + (p2 - p0) * s
                    + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * s * s
                    + (3.0 * p1 - p0 - 3.0 * p2 + p3) * s * s * s),
            );
        }
    }
    let mut lengths = vec![0.0];
    for pair in fine.windows(2) {
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
        points.push(fine[segment].lerp(fine[segment + 1], t));
        along += 1.0;
    }
    let last = points.len() - 1;
    (0..points.len())
        .map(|i| (points[i], (points[(i + 1).min(last)] - points[i.saturating_sub(1)]).normalize()))
        .collect()
}

/// How far `p` is from the nearest point of `curve`, and the index of that point.
pub fn nearest(curve: &[(DVec2, DVec2)], p: DVec2) -> (f64, usize) {
    curve
        .iter()
        .enumerate()
        .map(|(k, (q, _))| (q.distance(p), k))
        .min_by(|a, b| a.0.total_cmp(&b.0))
        .expect("a curve has points")
}
