//! The ground's heights, read from square pages.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

use anyhow::{Context, Result, bail};
use glam::{DVec2, DVec3};

/// The ground: heights on one square grid across the world, stored as square pages.
pub struct Ground {
    /// Each page's heights by page column and row, row by row from its south-west corner. Neighbouring pages share
    /// their edge heights. A NaN marks a place with no ground.
    pages: HashMap<(usize, usize), Vec<f32>>,
    /// Each page's colour, laid out as its heights, if it has one: sRGB bytes and an alpha of 255 at a point with a
    /// colour, or 0 at one without.
    colours: HashMap<(usize, usize), Vec<[u8; 4]>>,
    /// The ground texture's mean linear colour, which a point's colour tints the texture towards.
    texture_mean: [f32; 3],
    /// The mean of the grain-only texture a wholly coloured tile shows instead, if there is one.
    coloured_mean: Option<f32>,
    /// How many steps each page spans.
    page_steps: usize,
    /// The distance between neighbouring heights.
    pub step: f64,
    /// Where the grid's first height is, on the map.
    south_west: DVec2,
    alternate_diagonals: HashSet<(usize, usize)>,
    diagonal_extent: Option<((usize, usize), (usize, usize))>,
    native_extent: Option<((usize, usize), (usize, usize))>,
}

impl Ground {
    /// Reads every `<column>_<row>.bin` page in `folder`: little-endian 32-bit floats in metres, and each page's colour
    /// from `colours/<column>_<row>.bin`, four bytes a point, if that folder holds it.
    pub fn read(folder: &Path, page_steps: usize, step: f64, south_west: DVec2) -> Result<Self> {
        let samples = page_steps + 1;
        let mut pages = HashMap::new();
        for entry in fs::read_dir(folder).with_context(|| format!("reading {}", folder.display()))? {
            let path = entry?.path();
            if path.is_dir() {
                continue;
            }
            let name = path.file_stem().unwrap_or_default().to_string_lossy();
            let page = name.split_once('_').and_then(|(c, r)| Some((c.parse().ok()?, r.parse().ok()?)));
            let Some(page) = page else { bail!("{}: expected a <column>_<row>.bin page", path.display()) };
            let bytes = fs::read(&path)?;
            if bytes.len() != samples * samples * 4 {
                bail!("{}: expected {samples} × {samples} heights", path.display());
            }
            pages.insert(page, bytes.chunks(4).map(|b| f32::from_le_bytes(b.try_into().unwrap())).collect());
        }
        let mut colours = HashMap::new();
        let folder = folder.join("colours");
        if folder.is_dir() {
            for page in pages.keys() {
                let path = folder.join(format!("{}_{}.bin", page.0, page.1));
                if !path.is_file() {
                    continue;
                }
                let bytes = fs::read(&path)?;
                if bytes.len() != samples * samples * 4 {
                    bail!("{}: expected {samples} × {samples} colours", path.display());
                }
                colours.insert(*page, bytes.chunks(4).map(|b| b.try_into().unwrap()).collect());
            }
        }
        Ok(Self {
            pages,
            colours,
            texture_mean: [1.0; 3],
            coloured_mean: None,
            page_steps,
            step,
            south_west,
            alternate_diagonals: HashSet::new(),
            diagonal_extent: None,
            native_extent: None,
        })
    }

    /// Load the explicitly authored alternate triangle diagonals, on the same ground grid.
    pub fn read_diagonals(&mut self, path: &Path) -> Result<()> {
        #[derive(serde::Deserialize)]
        #[serde(deny_unknown_fields)]
        struct Input {
            extent_m: [[f64; 2]; 2],
            native_extent_m: [[f64; 2]; 2],
            step_m: f64,
            alternate_cells_m: Vec<[f64; 2]>,
        }
        let input: Input =
            serde_json::from_slice(&fs::read(path).with_context(|| format!("reading {}", path.display()))?)?;
        if input.step_m != self.step {
            bail!("terrain diagonal grid step differs from ground");
        }
        let index = |p: [f64; 2]| -> Result<(usize, usize)> {
            let p = (DVec2::from_array(p) - self.south_west) / self.step;
            if !p.is_finite()
                || p.min_element() < 0.0
                || p.max_element() > usize::MAX as f64
                || (p - p.round()).abs().max_element() > 1e-8
            {
                bail!("terrain diagonal coordinates must align with the ground grid");
            }
            Ok((p.x.round() as usize, p.y.round() as usize))
        };
        let (first, last) = (index(input.extent_m[0])?, index(input.extent_m[1])?);
        let (native_first, native_last) = (index(input.native_extent_m[0])?, index(input.native_extent_m[1])?);
        if first.0 >= last.0 || first.1 >= last.1 {
            bail!("invalid terrain diagonal extent");
        }
        if native_first.0 > first.0 || native_first.1 > first.1 || native_last.0 < last.0 || native_last.1 < last.1 {
            bail!("terrain diagonal extent exceeds native source extent");
        }
        let mut cells = HashSet::new();
        for cell in input.alternate_cells_m {
            let cell = index(cell)?;
            if cell.0 < first.0 || cell.0 >= last.0 || cell.1 < first.1 || cell.1 >= last.1 || !cells.insert(cell) {
                bail!("invalid or repeated terrain diagonal cell");
            }
        }
        self.alternate_diagonals = cells;
        self.diagonal_extent = Some((first, last));
        self.native_extent = Some((native_first, native_last));
        Ok(())
    }

    pub fn alternate_diagonal(&self, i: usize, j: usize) -> bool {
        self.alternate_diagonals.contains(&(i, j))
    }

    pub fn covers_diagonals(&self, columns: (usize, usize), rows: (usize, usize)) -> bool {
        self.diagonal_extent.is_none_or(|(first, last)| {
            columns.0 >= first.0 && columns.1 <= last.0 && rows.0 >= first.1 && rows.1 <= last.1
        })
    }

    /// Upper grid bounds of the loaded pages, with overflow rejected.
    pub fn max_steps(&self) -> Option<(usize, usize)> {
        let x = self.pages.keys().map(|(x, _)| *x).max()?.checked_add(1)?.checked_mul(self.page_steps)?;
        let y = self.pages.keys().map(|(_, y)| *y).max()?.checked_add(1)?.checked_mul(self.page_steps)?;
        Some((x, y))
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

    /// Sets the ground texture's mean linear colour and, if wholly coloured tiles show a grain-only texture
    /// instead, that texture's mean, for [`Ground::tint`].
    pub fn set_texture_means(&mut self, mean: [f64; 3], coloured: Option<f64>) {
        self.texture_mean = mean.map(|c| c as f32);
        self.coloured_mean = coloured.map(|c| c as f32);
    }

    /// Whether every grid point with ground from (`i0`, `j0`) to (`i1`, `j1`) has a colour, so the tile there can
    /// show the grain-only texture.
    pub fn wholly_coloured(&self, (i0, i1): (usize, usize), (j0, j1): (usize, usize)) -> bool {
        self.coloured_mean.is_some()
            && (j0..=j1).all(|j| (i0..=i1).all(|i| self.sample(i, j).is_none() || self.colour(i, j).is_some()))
    }

    /// The vertex colour the ground texture is multiplied by at grid point (`i`, `j`): its colour over the mean of
    /// the texture shown (the grain-only one if `grain`), or white where it has none.
    pub fn tint(&self, i: usize, j: usize, grain: bool) -> [f32; 4] {
        let mean = match (grain, self.coloured_mean) {
            (true, Some(mean)) => [mean; 3],
            _ => self.texture_mean,
        };
        let [r, g, b] = self.colour(i, j).map_or([1.0; 3], |c| [0, 1, 2].map(|k| c[k] / mean[k]));
        [r, g, b, 1.0]
    }

    /// Whether any page has a colour.
    pub fn has_colours(&self) -> bool {
        !self.colours.is_empty()
    }

    /// The linear colour at grid point (`i`, `j`), if its page gives it one.
    pub fn colour(&self, i: usize, j: usize) -> Option<[f32; 3]> {
        let pages = |k: usize| [k / self.page_steps, k.saturating_sub(1) / self.page_steps];
        pages(i).into_iter().flat_map(|pi| pages(j).map(|pj| (pi, pj))).find_map(|(pi, pj)| {
            let colours = self.colours.get(&(pi, pj))?;
            let [r, g, b, a] = colours[(j - pj * self.page_steps) * (self.page_steps + 1) + i - pi * self.page_steps];
            let linear = |c: u8| {
                let c = c as f32 / 255.0;
                if c <= 0.04045 { c / 12.92 } else { ((c + 0.055) / 1.055).powf(2.4) }
            };
            (a == 255).then(|| [linear(r), linear(g), linear(b)])
        })
    }

    /// Whether there is ground at any grid point from (`i0`, `j0`) to (`i1`, `j1`).
    pub fn touches(&self, (i0, i1): (usize, usize), (j0, j1): (usize, usize)) -> bool {
        (j0..=j1).any(|j| (i0..=i1).any(|i| self.sample(i, j).is_some()))
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
        if self.diagonal_extent.is_some() {
            let (a, b, c, d) = if self.alternate_diagonal(i, j) {
                if u + v <= 1.0 { (1.0 - u - v, u, 0.0, v) } else { (0.0, 1.0 - v, u + v - 1.0, 1.0 - u) }
            } else if u >= v {
                (1.0 - u, u - v, v, 0.0)
            } else {
                (1.0 - v, 0.0, u, v - u)
            };
            return Some(h(i, j, a)? + h(i + 1, j, b)? + h(i + 1, j + 1, c)? + h(i, j + 1, d)?);
        }
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
        Self {
            pages: HashMap::from([((0, 0), heights)]),
            colours: HashMap::new(),
            texture_mean: [1.0; 3],
            coloured_mean: None,
            page_steps,
            step,
            south_west: DVec2::ZERO,
            alternate_diagonals: HashSet::new(),
            diagonal_extent: None,
            native_extent: None,
        }
    }
}
