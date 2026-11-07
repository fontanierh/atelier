// Retired experiment: explicit Cargo test/doctest targets must stay empty.
#![cfg(not(any(test, doctest)))]

//! `lab-compare REFERENCE CANDIDATE`: compares two forest lab runs' saved frames, frame by frame, to find what a
//! player would see change: a tree changing shape, appearing late or vanishing.
//!
//! Both runs move the camera and blow the wind alike, so the only difference between their frames is how they draw
//! the trees. For each 8-pixel square it takes how far the candidate is from the reference, and reports two things:
//!
//! - *wrong*: squares further from the reference than [`WRONG`], how different the candidate looks;
//! - *shifts*: squares whose distance from the reference jumps by more than [`SHIFT`] from one frame to the next. A
//!   version swapping in, a tree changing shape or popping in or out, jumps; the camera's motion and the wind move
//!   both runs alike and do not. Only consecutive saved frames are compared, so capture every frame (`LAB_CAPTURE=1`).
//!   *Patches* count only the shifting squares that touch at least [`PATCH`] - 1 others: a tree changing shape moves a
//!   patch of squares, while a lone square on a leaf's edge can shift from the anti-aliasing's history alone;
//! - *coarse*: the share of 32-pixel squares further from the reference than [`WRONG`], a difference in light or shade
//!   rather than in which leaf lands on which pixel.
//!
//! It writes `compare.csv` beside the candidate's frames, and for the frames that shift most, `shift-NNNNN.png`: the
//! candidate's frame with each shifting square marked in red, to look at. Run a reference against a second reference
//! run first: what that reports is the renderer's own noise, which a candidate must not exceed.
//!
//! `lab-compare RUN` alone, for a run with the camera held still (`LAB_STILL=1`), counts the squares that change from
//! one frame to the next by more than [`SHIFT`]: flicker, as nothing on screen should move but the leaves in the wind.

use std::path::{Path, PathBuf};

use image::{Rgb, RgbImage};

/// A square's side, in pixels.
const SQUARE: u32 = 8;
/// The mean difference, from 0 to 1, over which a square differs from the reference.
const WRONG: f32 = 0.06;
/// How far a square's difference from the reference must jump in one frame to be a visible change.
const SHIFT: f32 = 0.05;
/// How many touching shifting squares make a patch.
const PATCH: usize = 4;
/// How many of the worst frames get a marked picture.
const MARKED: usize = 4;

fn main() {
    let args: Vec<PathBuf> = std::env::args().skip(1).map(PathBuf::from).collect();
    if let [run] = args.as_slice() {
        flicker(run);
        return;
    }
    let [reference, candidate] = args.as_slice() else {
        eprintln!("usage: lab-compare REFERENCE CANDIDATE, or lab-compare RUN for a still camera's flicker");
        std::process::exit(2);
    };
    let mut rows = String::from("frame,wrong,coarse,shifts,patches,largest_shift\n");
    let mut results: Vec<(u64, String, Vec<bool>)> = Vec::new();
    let (mut total_wrong, mut total_coarse, mut total_shifts, mut total_patches, mut count, mut steps) =
        (0.0, 0.0, 0u64, 0u64, 0u32, 0u32);
    let mut before: Option<(u32, Vec<f32>)> = None;
    let mut size = (0, 0);
    for name in frames(reference) {
        let (Some(r), Some(c)) = (open(&reference.join(&name)), open(&candidate.join(&name))) else { continue };
        if r.dimensions() != c.dimensions() {
            eprintln!("{name}: the runs' frames differ in size");
            std::process::exit(1);
        }
        size = r.dimensions();
        let index: u32 = name.trim_end_matches(".png").parse().unwrap_or(0);
        let distance = squares(&r, &c);
        let wrong = distance.iter().filter(|&&d| d > WRONG).count() as f32 / distance.len() as f32;
        let coarse = coarse(&distance, r.width() / SQUARE);
        let (shifts, largest, marks) = match &before {
            Some((previous, last)) if *previous + 1 == index => {
                let jumps: Vec<f32> = distance.iter().zip(last).map(|(d, e)| (d - e).abs()).collect();
                let marks: Vec<bool> = jumps.iter().map(|&j| j > SHIFT).collect();
                steps += 1;
                (marks.iter().filter(|&&m| m).count() as u64, jumps.iter().copied().fold(0.0, f32::max), marks)
            }
            _ => (0, 0.0, Vec::new()),
        };
        let patches = patched(&marks, r.width() / SQUARE);
        rows.push_str(&format!("{index},{wrong:.4},{coarse:.4},{shifts},{patches},{largest:.3}\n"));
        total_wrong += wrong;
        total_coarse += coarse;
        total_shifts += shifts;
        total_patches += patches;
        count += 1;
        results.push((patches, name.clone(), marks));
        before = Some((index, distance));
    }
    std::fs::write(candidate.join("compare.csv"), rows).ok();
    results.sort_by(|a, b| b.0.cmp(&a.0));
    for (shifts, name, marks) in results.iter().take(MARKED).filter(|(shifts, ..)| *shifts > 0) {
        if let Some(mut frame) = open(&candidate.join(name)) {
            mark(&mut frame, marks, size.0 / SQUARE);
            frame.save(candidate.join(format!("shift-{name}"))).ok();
        }
        let _ = shifts;
    }
    println!(
        "{count} frames, {steps} steps: {:.2}% of the screen differs on average ({:.2}% coarse); {total_shifts} \
         squares shifted in all, {total_patches} of them in patches, {} frames with a patch",
        100.0 * total_wrong / count.max(1) as f32,
        100.0 * total_coarse / count.max(1) as f32,
        results.iter().filter(|(patches, ..)| *patches > 0).count()
    );
    let worst: Vec<String> =
        results.iter().take(6).map(|(s, n, _)| format!("{} {s}", n.trim_end_matches(".png"))).collect();
    println!("most squares in patches: {}", worst.join(", "));
}

/// The share of 4x4 blocks of squares whose mean distance from the reference is over [`WRONG`].
fn coarse(distance: &[f32], across: u32) -> f32 {
    let down = distance.len() as u32 / across;
    let (cols, rows) = (across / 4, down / 4);
    let mut over = 0;
    for by in 0..rows {
        for bx in 0..cols {
            let mut sum = 0.0;
            for y in by * 4..by * 4 + 4 {
                for x in bx * 4..bx * 4 + 4 {
                    sum += distance[(y * across + x) as usize];
                }
            }
            if sum / 16.0 > WRONG {
                over += 1;
            }
        }
    }
    over as f32 / (cols * rows).max(1) as f32
}

/// How many marked squares are in groups of at least [`PATCH`] touching, sides or corners.
fn patched(marks: &[bool], across: u32) -> u64 {
    let across = across as i64;
    let mut seen = vec![false; marks.len()];
    let mut total = 0;
    for start in 0..marks.len() {
        if !marks[start] || seen[start] {
            continue;
        }
        let (mut group, mut stack) = (0, vec![start]);
        seen[start] = true;
        while let Some(k) = stack.pop() {
            group += 1;
            let (x, y) = (k as i64 % across, k as i64 / across);
            for (dx, dy) in [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)] {
                let (nx, ny) = (x + dx, y + dy);
                let n = ny * across + nx;
                if nx >= 0
                    && nx < across
                    && n >= 0
                    && (n as usize) < marks.len()
                    && marks[n as usize]
                    && !seen[n as usize]
                {
                    seen[n as usize] = true;
                    stack.push(n as usize);
                }
            }
        }
        if group >= PATCH {
            total += group as u64;
        }
    }
    total
}

/// Tints red each marked square of `frame`, `across` squares a row.
fn mark(frame: &mut RgbImage, marks: &[bool], across: u32) {
    for (k, _) in marks.iter().enumerate().filter(|(_, m)| **m) {
        let (x0, y0) = ((k as u32 % across) * SQUARE, (k as u32 / across) * SQUARE);
        for y in y0..y0 + SQUARE {
            for x in x0..x0 + SQUARE {
                let p = frame.get_pixel(x, y);
                frame.put_pixel(x, y, Rgb([255, p[1] / 3, p[2] / 3]));
            }
        }
    }
}

/// Counts, for a still camera's run, the squares each frame changes from the one before.
fn flicker(run: &Path) {
    let mut before: Option<RgbImage> = None;
    let (mut total, mut count, mut worst) = (0u64, 0u32, 0u64);
    for name in frames(run) {
        let Some(frame) = open(&run.join(&name)) else { continue };
        if let Some(before) = &before {
            let changed = squares(before, &frame).iter().filter(|&&d| d > SHIFT).count() as u64;
            total += changed;
            worst = worst.max(changed);
            count += 1;
        }
        before = Some(frame);
    }
    println!(
        "{count} steps: {:.1} squares flicker a step on average, {worst} at most",
        total as f32 / count.max(1) as f32
    );
}

/// The saved frames' names in `dir`, in order.
fn frames(dir: &Path) -> Vec<String> {
    let mut names: Vec<String> = std::fs::read_dir(dir)
        .map(|entries| {
            entries
                .filter_map(|e| e.ok()?.file_name().into_string().ok())
                .filter(|n| n.ends_with(".png") && n.trim_end_matches(".png").chars().all(|c| c.is_ascii_digit()))
                .collect()
        })
        .unwrap_or_default();
    names.sort();
    names
}

fn open(path: &Path) -> Option<RgbImage> {
    Some(image::open(path).ok()?.to_rgb8())
}

/// Each square's mean absolute difference between `a` and `b`, from 0 to 1.
fn squares(a: &RgbImage, b: &RgbImage) -> Vec<f32> {
    let (w, h) = a.dimensions();
    let (sx, sy) = (w / SQUARE, h / SQUARE);
    let mut out = vec![0.0; (sx * sy) as usize];
    for y in 0..sy * SQUARE {
        for x in 0..sx * SQUARE {
            let (p, q) = (a.get_pixel(x, y), b.get_pixel(x, y));
            let d = (0..3).map(|k| (p[k] as f32 - q[k] as f32).abs()).sum::<f32>() / (3.0 * 255.0);
            out[((y / SQUARE) * sx + x / SQUARE) as usize] += d;
        }
    }
    let n = (SQUARE * SQUARE) as f32;
    out.iter_mut().for_each(|v| *v /= n);
    out
}
