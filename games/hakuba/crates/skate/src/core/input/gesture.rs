//! TU3 pattern recognition, 82697168/826972B8/826974A8.
//! Points are supplied in PAT authoring order. Native 82696B18 pushes them
//! to the front of a ring buffer, then the matcher walks that buffer backwards.

#[derive(Clone, Debug, PartialEq)]
pub struct Pattern {
    pub name: String,
    pub points: Vec<[f32; 2]>,
    pub tolerance_squared: f32,
}

#[derive(Clone, Copy, Debug)]
pub struct Settings {
    /// Recognizer config byte 33. Supplied by the owner, never inferred here.
    pub maximum_misses: u8,
    pub difficulty: u32,
    pub pace: f32,
}

#[derive(Clone, Copy, Debug, Default)]
struct Node {
    active: bool,
    complete: bool,
    next: usize,
    elapsed: u16,
    misses: u8,
    distance: f32,
}

impl Node {
    fn tick(&mut self, pattern: &Pattern, sample: [f32; 2], maximum_misses: u8, weight: u8) {
        if !self.active {
            let distance = distance_squared(pattern.points[0], sample);
            if distance <= pattern.tolerance_squared {
                *self = Self {
                    active: true,
                    next: 1,
                    elapsed: if weight == 2 { 0 } else { 1 },
                    distance,
                    ..Self::default()
                };
            }
        } else if !self.complete {
            let distance = distance_squared(pattern.points[self.next], sample);
            if distance <= pattern.tolerance_squared {
                self.distance += distance;
                self.elapsed = (self.elapsed + u16::from(weight)) & 0x3ff;
                if self.next + 1 == pattern.points.len() {
                    self.complete = true;
                } else {
                    self.next += 1;
                    self.misses = 0;
                }
            } else {
                // Holding the first point does not age a pending gesture.
                if self.next != 1 || distance_squared(pattern.points[0], sample) > pattern.tolerance_squared {
                    self.elapsed = (self.elapsed + u16::from(weight)) & 0x3ff;
                    self.misses = self.misses.wrapping_add(weight) & 0x7f;
                }
                if self.misses > maximum_misses {
                    *self = Self::default();
                }
            }
        }
    }

    fn score(self, count: usize, elapsed: f32) -> f32 {
        let count = count as f32;
        // The unusual two-sided 0.15 operation is present in 826972B8.
        let mean = (self.distance.max(0.15) / count).min(0.15);
        (count * count * count * count) / (mean * elapsed)
    }
}

fn distance_squared(a: [f32; 2], b: [f32; 2]) -> f32 {
    let x = a[0] - b[0];
    let y = a[1] - b[1];
    // VMX multiplies then adds; do not contract to FMA.
    x * x + y * y
}

#[derive(Clone, Debug, PartialEq)]
pub struct Recognition {
    pub pattern: usize,
    pub strength: f32,
    pub distance: f32,
    pub elapsed: f32,
}

#[derive(Clone, Debug)]
pub struct Recognizer {
    patterns: Vec<Pattern>,
    nodes: Vec<Node>,
    has_previous_sample: bool,
    refractory: u8,
    authored_tolerance: Vec<f32>,
    authored_count: usize,
    radius_scale: f32,
    held: Option<usize>,
}

impl Recognizer {
    pub fn new(patterns: Vec<Pattern>) -> Result<Self, String> {
        for pattern in &patterns {
            if !(2..=15).contains(&pattern.points.len())
                || !pattern.tolerance_squared.is_finite()
                || pattern.tolerance_squared < 0.0
                || pattern.points.iter().flatten().any(|v| !v.is_finite())
            {
                return Err(format!("invalid native gesture pattern {}", pattern.name));
            }
        }
        Ok(Self {
            nodes: vec![Node::default(); patterns.len()],
            authored_tolerance: patterns.iter().map(|p| p.tolerance_squared).collect(),
            authored_count: patterns.len(),
            radius_scale: 1.0,
            patterns,
            has_previous_sample: false,
            refractory: 0,
            held: None,
        })
    }

    pub fn patterns(&self) -> &[Pattern] {
        &self.patterns
    }

    /// Held messages are checked before recognition in 826962D8. Native point
    /// zero is the final authored coordinate (82699738 push-front).
    pub fn held(&mut self, sample: [f32; 2]) -> Option<usize> {
        if let Some(index) = self.held {
            let pattern = &self.patterns[index];
            if distance_squared(*pattern.points.last().unwrap(), sample) > pattern.tolerance_squared {
                self.held = None;
            }
        }
        self.held
    }

    /// Radius changes always start at the authored values, never at the last tuning.
    pub fn scale_radius(&mut self, scale: f32) {
        self.radius_scale = scale;
        for (pattern, authored) in self.patterns.iter_mut().zip(&self.authored_tolerance) {
            pattern.tolerance_squared = authored * (scale * scale);
        }
    }

    pub fn set_extra_patterns(&mut self, extra: Vec<Pattern>) -> Result<(), String> {
        // Validate before replacing the live recognizer's extra patterns.
        Self::new(extra.clone())?;
        self.patterns.truncate(self.authored_count);
        self.authored_tolerance.truncate(self.authored_count);
        for pattern in extra {
            self.authored_tolerance.push(pattern.tolerance_squared);
            self.patterns.push(pattern);
        }
        self.scale_radius(self.radius_scale);
        self.nodes = vec![Node::default(); self.patterns.len()];
        if self.held.is_some_and(|i| i >= self.patterns.len()) {
            self.held = None;
        }
        Ok(())
    }

    fn advance(&mut self, sample: [f32; 2], settings: Settings, weight: u8) -> bool {
        if self.refractory != 0 {
            self.nodes.fill(Node::default());
            self.refractory = self.refractory.saturating_sub(weight);
            return false;
        }
        if !self.has_previous_sample {
            self.has_previous_sample = true;
            return false;
        }
        for (node, pattern) in self.nodes.iter_mut().zip(&self.patterns) {
            node.tick(pattern, sample, settings.maximum_misses, weight);
        }
        true
    }

    fn ticks(elapsed: u16) -> f32 {
        elapsed as f32 / 2.0 + 1.0
    }

    fn score(&self, index: usize) -> f32 {
        self.nodes[index].score(self.patterns[index].points.len(), Self::ticks(self.nodes[index].elapsed))
    }

    fn best(&self) -> Option<usize> {
        let mut best = None;
        for (index, node) in self.nodes.iter().enumerate() {
            if node.complete && best.is_none_or(|old| self.score(index) > self.score(old)) {
                best = Some(index);
            }
        }
        best
    }

    fn sample(&mut self, sample: [f32; 2], settings: Settings) -> Option<Recognition> {
        if !self.advance(sample, settings, 1) {
            return None;
        }
        self.best().map(|best| self.recognize(best, settings))
    }

    /// Two real readings compete within a physics tick. With no middle reading,
    /// the packet counts twice and preserves the original tick's score and pause.
    pub fn sample_tick(&mut self, half: Option<[f32; 2]>, now: [f32; 2], settings: Settings) -> Option<Recognition> {
        let Some(half) = half else {
            if !self.advance(now, settings, 2) {
                return None;
            }
            return self.best().map(|best| self.recognize(best, settings));
        };
        if !self.advance(half, settings, 1) {
            return self.sample(now, settings);
        }
        let Some(first) = self.best() else {
            return self.sample(now, settings);
        };
        let at_half = self.nodes.clone();
        self.advance(now, settings, 1);
        if let Some(second) = self.best() {
            if second != first && self.score(second) > self.score(first) {
                return Some(self.recognize(second, settings));
            }
        }
        self.nodes = at_half;
        let result = self.recognize(first, settings);
        self.advance(now, settings, 1);
        Some(result)
    }

    fn recognize(&mut self, pattern: usize, settings: Settings) -> Recognition {
        let node = self.nodes[pattern];
        let elapsed = Self::ticks(node.elapsed);
        let ratio = elapsed / self.patterns[pattern].points.len() as f32;
        let (low, high) = if settings.difficulty == 2 { (1.5, 3.0) } else { (1.75, 4.4) };
        let (low, high) = (low / settings.pace, high / settings.pace);
        let strength = if ratio <= low {
            1.0
        } else if ratio >= high {
            0.0
        } else {
            let slope = 1.0 / (low - high);
            slope.mul_add(ratio, -(slope * high))
        };
        self.refractory = 2;
        self.held = Some(pattern);
        Recognition { pattern, strength, distance: node.distance, elapsed }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn recognizer() -> Recognizer {
        Recognizer::new(vec![Pattern {
            name: "360Flip".into(),
            points: vec![[-0.965714, 0.268571], [-0.497143, 0.84], [0.211429, 0.988571], [0.908571, -0.405714]],
            tolerance_squared: 0.4 * 0.4,
        }])
        .unwrap()
    }
    const SETTINGS: Settings = Settings { maximum_misses: 6, difficulty: 0, pace: 1.0 };

    #[test]
    fn anticipation_hold_does_not_weaken_authored_scoop() {
        let mut r = recognizer();
        let points = r.patterns[0].points.clone();
        r.sample_tick(None, [0.0; 2], SETTINGS);
        for _ in 0..120 {
            assert!(r.sample_tick(None, points[0], SETTINGS).is_none());
        }
        assert!(r.sample_tick(None, points[1], SETTINGS).is_none());
        assert!(r.sample_tick(None, points[2], SETTINGS).is_none());
        let result = r.sample_tick(None, points[3], SETTINGS).unwrap();
        assert_eq!((result.pattern, result.strength, result.elapsed), (0, 1.0, 4.0));
        assert_eq!(r.held(points[3]), Some(0));
        assert!(r.sample_tick(None, points[3], SETTINGS).is_none());
        assert_eq!(r.held([0.0; 2]), None);
    }

    #[test]
    fn packet_fallback_keeps_elapsed_strength_and_refractory_weight() {
        let mut r = recognizer();
        let points = r.patterns[0].points.clone();
        assert!(r.sample_tick(None, [0.0; 2], SETTINGS).is_none());
        assert!(r.sample_tick(None, points[0], SETTINGS).is_none());
        for &point in &points[1..3] {
            assert!(r.sample_tick(None, point, SETTINGS).is_none());
        }
        let result = r.sample_tick(None, points[3], SETTINGS).unwrap();
        assert_eq!((result.pattern, result.strength, result.elapsed), (0, 1.0, 4.0));
        assert!(r.sample_tick(None, points[0], SETTINGS).is_none());
        assert_eq!(r.refractory, 0);
    }
    #[test]
    fn packet_fallback_and_two_real_misses_have_equal_elapsed_weight() {
        let mut fallback = recognizer();
        let points = fallback.patterns[0].points.clone();
        fallback.sample_tick(None, [0.0; 2], SETTINGS);
        fallback.sample_tick(None, points[0], SETTINGS);
        let mut observed = fallback.clone();
        assert!(fallback.sample_tick(None, [0.0; 2], SETTINGS).is_none());
        assert!(observed.sample_tick(Some([0.0; 2]), [0.0; 2], SETTINGS).is_none());
        assert_eq!(fallback.nodes[0].elapsed, observed.nodes[0].elapsed);
        assert_eq!(fallback.nodes[0].misses, observed.nodes[0].misses);
        for &point in &points[1..3] {
            assert_eq!(fallback.sample_tick(None, point, SETTINGS), observed.sample_tick(None, point, SETTINGS));
        }
        let expected = fallback.sample_tick(None, points[3], SETTINGS).unwrap();
        assert_eq!(Some(expected), observed.sample_tick(None, points[3], SETTINGS));
    }

    #[test]
    fn midpoint_flick_is_seen_without_doubling_physics_ticks() {
        let mut r = Recognizer::new(vec![Pattern {
            name: "fast".into(),
            points: vec![[0.0, -1.0], [1.0, 0.0], [0.0, 1.0]],
            tolerance_squared: 0.01,
        }])
        .unwrap();
        r.sample_tick(None, [0.0; 2], SETTINGS);
        r.sample_tick(None, [0.0, -1.0], SETTINGS);
        let mut fallback = r.clone();
        assert!(fallback.sample_tick(None, [0.0, 1.0], SETTINGS).is_none());
        let result = r.sample_tick(Some([1.0, 0.0]), [0.0, 1.0], SETTINGS).unwrap();
        assert_eq!((result.pattern, result.elapsed, result.strength), (0, 2.0, 1.0));
    }
    #[test]
    fn complete_patterns_in_one_tick_compete_by_score() {
        let mut r = Recognizer::new(vec![
            Pattern { name: "short".into(), points: vec![[0.0, -1.0], [1.0, 0.0]], tolerance_squared: 0.01 },
            Pattern { name: "long".into(), points: vec![[0.0, -1.0], [1.0, 0.0], [0.0, 1.0]], tolerance_squared: 0.01 },
        ])
        .unwrap();
        r.sample_tick(None, [0.0; 2], SETTINGS);
        r.sample_tick(None, [0.0, -1.0], SETTINGS);
        assert_eq!(r.sample_tick(Some([1.0, 0.0]), [0.0, 1.0], SETTINGS).unwrap().pattern, 1);
    }

    #[test]
    fn radius_edits_restore_authored_values() {
        let mut r = recognizer();
        let stock = r.patterns[0].tolerance_squared;
        r.scale_radius(2.0);
        r.scale_radius(0.5);
        r.scale_radius(1.0);
        assert_eq!(r.patterns[0].tolerance_squared.to_bits(), stock.to_bits());
    }

    #[test]
    fn disconnected_scoop_and_reverse_path_do_not_trigger() {
        let mut r = recognizer();
        let points = r.patterns[0].points.clone();
        r.sample_tick(None, [0.0; 2], SETTINGS);
        r.sample_tick(None, points[0], SETTINGS);
        for _ in 0..4 {
            assert!(r.sample_tick(None, [0.0; 2], SETTINGS).is_none());
        }
        for &point in &points[1..] {
            assert!(r.sample_tick(None, point, SETTINGS).is_none());
        }
        let mut r = recognizer();
        r.sample_tick(None, [0.0; 2], SETTINGS);
        for &point in points.iter().rev() {
            assert!(r.sample_tick(None, point, SETTINGS).is_none());
        }
    }
}
