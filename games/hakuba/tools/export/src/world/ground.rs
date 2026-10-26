//! The ground's heights, read from square pages.

use std::collections::HashMap;
use std::fs;
use std::path::Path;

use anyhow::{Context, Result, bail};
use glam::{DVec2, DVec3};

/// The ground: heights on one square grid across the world, stored as square pages.
pub struct Ground {
    /// Each page's heights by page column and row, row by row from its south-west corner. Neighbouring pages share
    /// their edge heights. A NaN marks a place with no ground.
    pages: HashMap<(usize, usize), Vec<f32>>,
    /// How many steps each page spans.
    page_steps: usize,
    /// The distance between neighbouring heights.
    pub step: f64,
    /// Where the grid's first height is, on the map.
    south_west: DVec2,
}

impl Ground {
    /// Reads every `<column>_<row>.bin` page in `folder`: little-endian 32-bit floats in metres.
    pub fn read(folder: &Path, page_steps: usize, step: f64, south_west: DVec2) -> Result<Self> {
        let samples = page_steps + 1;
        let mut pages = HashMap::new();
        for entry in fs::read_dir(folder).with_context(|| format!("reading {}", folder.display()))? {
            let path = entry?.path();
            let name = path.file_stem().unwrap_or_default().to_string_lossy();
            let page = name.split_once('_').and_then(|(c, r)| Some((c.parse().ok()?, r.parse().ok()?)));
            let Some(page) = page else { bail!("{}: expected a <column>_<row>.bin page", path.display()) };
            let bytes = fs::read(&path)?;
            if bytes.len() != samples * samples * 4 {
                bail!("{}: expected {samples} × {samples} heights", path.display());
            }
            pages.insert(page, bytes.chunks(4).map(|b| f32::from_le_bytes(b.try_into().unwrap())).collect());
        }
        Ok(Self { pages, page_steps, step, south_west })
    }

    /// Gives every grid point with ground the height `change` returns for its map position and its height. A point
    /// on a page's edge gets the same new height on every page that holds it.
    pub fn reshape(&mut self, change: impl Fn(DVec2, f64) -> f64) {
        let (samples, page_steps, step, south_west) =
            (self.page_steps + 1, self.page_steps, self.step, self.south_west);
        for (&(pi, pj), heights) in &mut self.pages {
            for (k, height) in heights.iter_mut().enumerate() {
                if height.is_nan() {
                    continue;
                }
                let (i, j) = (pi * page_steps + k % samples, pj * page_steps + k / samples);
                let p = south_west + DVec2::new(i as f64, j as f64) * step;
                *height = change(p, *height as f64) as f32;
            }
        }
    }

    /// The height at grid point (`i`, `j`), counted from the world's south-west corner, if there is ground there.
    pub fn sample(&self, i: usize, j: usize) -> Option<f64> {
        // A point on a page's edge is on both pages beside it.
        let pages = |k: usize| [k / self.page_steps, k.saturating_sub(1) / self.page_steps];
        pages(i).into_iter().flat_map(|pi| pages(j).map(|pj| (pi, pj))).find_map(|(pi, pj)| {
            let heights = self.pages.get(&(pi, pj))?;
            let h = heights[(j - pj * self.page_steps) * (self.page_steps + 1) + i - pi * self.page_steps];
            (!h.is_nan()).then_some(h as f64)
        })
    }

    /// Whether there is ground at every grid point from (`i0`, `j0`) to (`i1`, `j1`).
    pub fn covers(&self, (i0, i1): (usize, usize), (j0, j1): (usize, usize)) -> bool {
        (j0..=j1).all(|j| (i0..=i1).all(|i| self.sample(i, j).is_some()))
    }

    /// The map position of grid point (`i`, `j`), which may fall between points.
    pub fn position(&self, i: f64, j: f64) -> DVec2 {
        self.south_west + DVec2::new(i, j) * self.step
    }

    /// The point on the ground at grid position (`i`, `j`).
    pub fn at(&self, i: f64, j: f64) -> DVec3 {
        let p = self.position(i, j);
        p.extend(self.height(p).expect("the tiles lie on the ground"))
    }

    /// The ground's height at `p`, blended between the four nearest heights, if there is ground there.
    pub fn height(&self, p: DVec2) -> Option<f64> {
        let f = (p - self.south_west) / self.step;
        if f.min_element() < 0.0 {
            return None;
        }
        let (i, j) = (f.x as usize, f.y as usize);
        let (u, v) = (f.x - i as f64, f.y - j as f64);
        // A corner that weighs nothing need not be on the ground, so the ground's last points have heights too.
        let h =
            |i: usize, j: usize, weight: f64| if weight == 0.0 { Some(0.0) } else { Some(self.sample(i, j)? * weight) };
        Some(
            h(i, j, (1.0 - u) * (1.0 - v))?
                + h(i + 1, j, u * (1.0 - v))?
                + h(i, j + 1, (1.0 - u) * v)?
                + h(i + 1, j + 1, u * v)?,
        )
    }

    /// The ground's up direction at `p`. Where the ground stops on one side, the slope comes from the other.
    pub fn normal(&self, p: DVec2) -> DVec3 {
        let slope = |d: DVec2| {
            let here = self.height(p).expect("the tiles lie on the ground");
            match (self.height(p + d), self.height(p - d)) {
                (Some(ahead), Some(behind)) => (ahead - behind) / (2.0 * self.step),
                (Some(ahead), None) => (ahead - here) / self.step,
                (None, Some(behind)) => (here - behind) / self.step,
                (None, None) => 0.0,
            }
        };
        DVec3::new(-slope(DVec2::X * self.step), -slope(DVec2::Y * self.step), 1.0).normalize()
    }
}

#[cfg(test)]
impl Ground {
    /// A ground of one page, its height at each grid point given by `height`.
    pub fn page(page_steps: usize, step: f64, height: impl Fn(usize, usize) -> f32) -> Self {
        let samples = page_steps + 1;
        let heights = (0..samples * samples).map(|k| height(k % samples, k / samples)).collect();
        Self { pages: HashMap::from([((0, 0), heights)]), page_steps, step, south_west: DVec2::ZERO }
    }
}
