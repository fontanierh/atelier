//! Levelled strips: changes a region declares to the ground along a course, so that what it lays there, such as a
//! flat overlay, rests on ground that is level across the course and smooth along it.

use anyhow::{Result, bail};
use glam::DVec2;

use super::curve::curve;
use super::ground::Ground;

/// A strip of ground levelled along a smooth curve. Across the curve the strip is level; along it, its height is
/// the ground's along the curve, smoothed. Beyond its edges a shoulder eases from the strip's height back to the
/// ground's, starting and ending without a crease.
pub struct Strip {
    /// The points the strip's centre line passes through, on a Catmull-Rom curve, as for a ribbon.
    pub course: Vec<[f64; 2]>,
    /// How far the level part reaches either side of the centre line, in metres.
    pub half_width_m: f64,
    /// How wide the shoulder is, beyond each edge, in metres.
    pub shoulder_m: f64,
    /// How far along the centre line its heights are smoothed: the spread, in metres, of the bell curve each
    /// height is averaged over.
    pub smoothing_m: f64,
}

impl Strip {
    /// Levels `ground` along the strip. Fails if part of the centre line has no ground.
    pub fn level(&self, ground: &mut Ground) -> Result<()> {
        let line = curve(&self.course);
        let mut heights = Vec::with_capacity(line.len());
        for &(p, _) in &line {
            let Some(height) = ground.height(p) else { bail!("a levelled strip runs off the ground at {p}") };
            heights.push(height);
        }
        let heights = smooth(&heights, self.smoothing_m);
        let reach = self.half_width_m + self.shoulder_m;
        let (low, high) =
            line.iter().fold((DVec2::INFINITY, DVec2::NEG_INFINITY), |(low, high), &(p, _)| (low.min(p), high.max(p)));
        let (low, high) = (low - DVec2::splat(reach), high + DVec2::splat(reach));
        ground.reshape(|p, height| {
            if p.cmplt(low).any() || p.cmpgt(high).any() {
                return height;
            }
            let (distance, along) = project(&line, p);
            if distance >= reach {
                return height;
            }
            let k = (along.floor() as usize).min(heights.len() - 1);
            let t = along - k as f64;
            let level = heights[k] + (heights[(k + 1).min(heights.len() - 1)] - heights[k]) * t;
            if distance <= self.half_width_m {
                return level;
            }
            let u = (distance - self.half_width_m) / self.shoulder_m;
            let ease = u * u * (3.0 - 2.0 * u);
            level + (height - level) * ease
        });
        Ok(())
    }
}

/// A rectangular footprint levelled to a declared plane. Its margin extends by one coarse ground cell so both
/// full and middle tiles draw that plane over the complete footprint.
pub struct Pad {
    pub centre: [f64; 2],
    pub half_size_m: [f64; 2],
    /// Height at the centre and rise per metre east and north.
    pub height_m: f64,
    pub slope: [f64; 2],
    pub shoulder_m: f64,
}

impl Pad {
    fn bounds(&self, ground: &Ground) -> (DVec2, DVec2) {
        let centre = DVec2::from_array(self.centre);
        let reach = DVec2::from_array(self.half_size_m) + DVec2::splat(super::COARSE as f64 * ground.step);
        (centre, reach)
    }

    /// Levels the footprint and its margin, easing the shoulder back into the original ground.
    fn level(&self, ground: &mut Ground) -> Result<()> {
        let (centre, flat) = self.bounds(ground);
        if !centre.is_finite()
            || !flat.is_finite()
            || !self.height_m.is_finite()
            || !DVec2::from_array(self.slope).is_finite()
            || DVec2::from_array(self.half_size_m).min_element() <= 0.0
            || !self.shoulder_m.is_finite()
            || self.shoulder_m <= 0.0
        {
            bail!("invalid levelled pad");
        }
        let reach = flat + DVec2::splat(self.shoulder_m);
        for offset in [DVec2::ZERO, reach, -reach, DVec2::new(reach.x, -reach.y), DVec2::new(-reach.x, reach.y)] {
            if ground.height(centre + offset).is_none() {
                bail!("a levelled pad runs off the ground at {}", centre + offset);
            }
        }
        ground.reshape(|p, height| {
            let outside = ((p - centre).abs() - flat).max(DVec2::ZERO);
            let distance = outside.length();
            if distance >= self.shoulder_m {
                return height;
            }
            let u = distance / self.shoulder_m;
            let ease = u * u * (3.0 - 2.0 * u);
            let plane = self.height_m + (p - centre).dot(DVec2::from_array(self.slope));
            plane + (height - plane) * ease
        });
        Ok(())
    }
}

/// @cc [owner:fontanierh,label:correctness] pad-owns-final-ground
/// A pad MUST be applied after strips, so its complete footprint is the declared plane in both tile versions.
/// Pads MUST NOT overlap one another. Crossing strips use this final ground, not their superseded intermediate shape.
/// The resulting ground, including crossings, still goes through the overlay checks.
pub fn level_pads(ground: &mut Ground, pads: &[Pad]) -> Result<()> {
    for (index, pad) in pads.iter().enumerate() {
        let (centre, flat) = pad.bounds(ground);
        let reach = flat + DVec2::splat(pad.shoulder_m);
        for other in &pads[..index] {
            let (other_centre, other_flat) = other.bounds(ground);
            let other_reach = other_flat + DVec2::splat(other.shoulder_m);
            if (centre - other_centre).abs().cmple(reach + other_reach).all() {
                bail!("levelled pads overlap");
            }
        }
        pad.level(ground)?;
    }
    Ok(())
}

/// `heights`, one a metre, each averaged with its neighbours under a bell curve spreading `spread` metres. Near the
/// ends the bell is cut off, and the weights that remain still add up to one.
fn smooth(heights: &[f64], spread: f64) -> Vec<f64> {
    if spread <= 0.0 {
        return heights.to_vec();
    }
    let reach = (3.0 * spread).ceil() as usize;
    (0..heights.len())
        .map(|k| {
            let (mut sum, mut weights) = (0.0, 0.0);
            let first = k.saturating_sub(reach);
            for (n, height) in heights.iter().enumerate().take(k + reach + 1).skip(first) {
                let weight = (-0.5 * ((n as f64 - k as f64) / spread).powi(2)).exp();
                sum += weight * height;
                weights += weight;
            }
            sum / weights
        })
        .collect()
}

/// How far `p` is from the line through `line`'s points, and where along it the nearest point is, in metres from
/// its start (the points are a metre apart). Beyond its ends the nearest point is the end.
fn project(line: &[(DVec2, DVec2)], p: DVec2) -> (f64, f64) {
    let nearest = line
        .iter()
        .enumerate()
        .min_by(|a, b| a.1.0.distance_squared(p).total_cmp(&b.1.0.distance_squared(p)))
        .map(|(k, _)| k)
        .expect("a curve has points");
    let mut best = (line[nearest].0.distance(p), nearest as f64);
    for k in nearest.saturating_sub(1)..=nearest {
        if k + 1 >= line.len() {
            continue;
        }
        let (a, b) = (line[k].0, line[k + 1].0);
        let t = ((p - a).dot(b - a) / (b - a).length_squared()).clamp(0.0, 1.0);
        let distance = (a + (b - a) * t).distance(p);
        if distance < best.0 {
            best = (distance, k as f64 + t);
        }
    }
    best
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::world::overlay::{Overlay, check_smooth, crease_deg};
    use crate::world::ribbon::ribbon;
    use crate::world::surface::Surface;
    use crate::world::{Detail, Tile};

    #[test]
    fn pads_level_the_drawn_full_and_middle_footprint_and_leave_distant_ground() {
        let original = Ground::page(64, 2.0, |i, j| (i as f32 * 0.13) + (j as f32 * 0.07));
        let mut ground = Ground::page(64, 2.0, |i, j| (i as f32 * 0.13) + (j as f32 * 0.07));
        let pad =
            Pad { centre: [64.0, 64.0], half_size_m: [7.0, 5.0], height_m: 4.0, slope: [0.0, 0.055], shoulder_m: 6.0 };
        level_pads(&mut ground, &[pad]).unwrap();
        let tile = Tile { columns: (0, 64), rows: (0, 64) };
        for detail in [Detail::Full, Detail::Middle] {
            let surface = Surface::new(&tile.ground(&ground, detail, 0, 1.0));
            for x in 57..=71 {
                for y in 59..=69 {
                    let height = surface.height(DVec2::new(x as f64, y as f64)).unwrap();
                    let expected = 4.0 + 0.055 * (y as f64 - 64.0);
                    assert!((height - expected).abs() < 1e-5, "footprint height {height} at {x}, {y}");
                }
            }
        }
        assert_eq!(ground.height(DVec2::new(4.0, 4.0)), original.height(DVec2::new(4.0, 4.0)));
    }

    #[test]
    fn pads_reject_other_pads() {
        let ground = || Ground::page(128, 2.0, |_, _| 0.0);
        let pad =
            || Pad { centre: [64.0, 64.0], half_size_m: [4.0, 4.0], height_m: 1.0, slope: [0.0, 0.0], shoulder_m: 4.0 };
        let other = Pad { centre: [84.0, 64.0], ..pad() };
        assert!(level_pads(&mut ground(), &[pad(), other]).is_err());
    }

    /// An approach crosses a sloping pad on one final surface. This is a geometry check, not a walk test.
    #[test]
    fn approach_crosses_a_shared_sloping_terrace() {
        let mut ground = Ground::page(128, 2.0, |i, j| {
            let (x, y) = (i as f32 * 2.0, j as f32 * 2.0);
            5.0 + 0.055 * (y - 85.0) + 0.015 * (x - 100.0)
        });
        let course = [[10.0, 36.0], [35.0, 48.0], [55.0, 64.0], [75.0, 68.0], [90.0, 72.0], [100.0, 82.0]];
        let strip = Strip { course: course.to_vec(), half_width_m: 4.0, shoulder_m: 10.0, smoothing_m: 8.0 };
        strip.level(&mut ground).unwrap();
        let pad = Pad {
            centre: [100.0, 85.0],
            half_size_m: [30.0, 25.0],
            height_m: 5.0,
            slope: [0.0, 0.055],
            shoulder_m: 20.0,
        };
        level_pads(&mut ground, &[pad]).unwrap();
        let tile = Tile { columns: (0, 128), rows: (0, 128) };
        let drawn = Surface::new(&tile.ground(&ground, Detail::Full, 0, 1.0));
        let overlay = Overlay { name: "approach".into(), texture: "t".into(), triangles: ribbon(&course, 2.6, 8.0) };
        let mesh = overlay.mesh(&ground, &drawn);
        // A narrow shoulder bends this approach too sharply: the ordinary export check must reject it.
        let mut narrow = Ground::page(128, 2.0, |i, j| {
            let (x, y) = (i as f32 * 2.0, j as f32 * 2.0);
            5.0 + 0.055 * (y - 85.0) + 0.015 * (x - 100.0)
        });
        strip.level(&mut narrow).unwrap();
        let narrow_pad = Pad {
            centre: [100.0, 85.0],
            half_size_m: [30.0, 25.0],
            height_m: 5.0,
            slope: [0.0, 0.055],
            shoulder_m: 6.0,
        };
        level_pads(&mut narrow, &[narrow_pad]).unwrap();
        let narrow_drawn = Surface::new(&tile.ground(&narrow, Detail::Full, 0, 1.0));
        assert!(check_smooth(&overlay.mesh(&narrow, &narrow_drawn)).is_err());
        let crease = crease_deg(&mesh);
        assert!(crease < 1.5, "approach creases by {crease:.3}° at its terrace join");
        let line = curve(&course);
        for pair in line.windows(2) {
            let h0 = drawn.height(pair[0].0).unwrap();
            let h1 = drawn.height(pair[1].0).unwrap();
            assert!((h1 - h0).abs() < 0.3, "approach changes height too sharply");
        }
    }

    /// A ground with a level cut 5 m wide running diagonally across it, its edges sharp and its banks rising 1 in 1,
    /// sampled on a 2 m grid: the cut's edges, and anything laid along them, staircase.
    fn cut_ground() -> Ground {
        Ground::page(64, 2.0, |i, j| {
            let p = DVec2::new(i as f64, j as f64) * 2.0;
            let across = (p.y - 0.4 * p.x - 20.0) / 1.16f64.sqrt();
            let along = (p.x + 0.4 * p.y) / 1.16f64.sqrt();
            (0.02 * along + (across.abs() - 2.5).max(0.0)) as f32
        })
    }

    const COURSE: [[f64; 2]; 3] = [[4.0, 21.6], [64.0, 45.6], [124.0, 69.6]];

    /// The road-like overlay along the cut, draped over the ground's full-detail triangles.
    fn draped(ground: &Ground) -> f64 {
        let tile = Tile { columns: (0, 64), rows: (0, 64) };
        let drawn = Surface::new(&tile.ground(ground, Detail::Full, 0, 1.0));
        let overlay = Overlay { name: "strip".into(), texture: "t".into(), triangles: ribbon(&COURSE, 5.2, 8.0) };
        crease_deg(&overlay.mesh(ground, &drawn))
    }

    /// An overlay laid along a sharp cut on the 2 m grid creases at the ground's triangle edges. Levelling a strip
    /// under it, with its shoulders, leaves it without a crease.
    #[test]
    fn an_overlay_on_a_levelled_strip_does_not_crease() {
        let mut ground = cut_ground();
        assert!(draped(&ground) > 5.0, "the cut ground creases the overlay");
        let strip = Strip { course: COURSE.to_vec(), half_width_m: 4.0, shoulder_m: 10.0, smoothing_m: 8.0 };
        strip.level(&mut ground).unwrap();
        let crease = draped(&ground);
        assert!(crease < 1.0, "the overlay creases by {crease:.2}° on the levelled strip");
    }

    /// The strip is level across its course (sampled 1 m either side, so the heights blended in come only from grid
    /// points on the level part), and past its shoulders the ground is as it was.
    #[test]
    fn a_strip_is_level_across_and_leaves_the_ground_beyond() {
        let before = cut_ground();
        let mut ground = cut_ground();
        let strip = Strip { course: COURSE.to_vec(), half_width_m: 4.0, shoulder_m: 6.0, smoothing_m: 8.0 };
        strip.level(&mut ground).unwrap();
        let line = curve(&COURSE);
        for &(at, direction) in &line[20..100] {
            let across: Vec<f64> =
                [-1.0, -0.5, 0.0, 0.5, 1.0].map(|d| ground.height(at + direction.perp() * d).unwrap()).to_vec();
            let spread = across.iter().fold(0.0f64, |m, h| m.max((h - across[2]).abs()));
            assert!(spread < 0.01, "the strip tilts by {spread:.3} m across at {at}");
            for side in [-1.0, 1.0] {
                let out = at + direction.perp() * side * 13.0;
                assert_eq!(ground.height(out), before.height(out), "the ground changes past the shoulder at {out}");
            }
        }
    }
}
