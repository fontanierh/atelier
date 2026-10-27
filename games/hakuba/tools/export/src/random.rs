//! Seeded random numbers, so every export repeats exactly. Each draw comes from a seed alone, never from the clock.

/// A stream of random numbers from one seed (splitmix64).
pub struct Random(u64);

impl Random {
    pub fn new(seed: u64) -> Self {
        Self(seed)
    }

    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// A number from 0 up to, but not including, 1.
    pub fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }

    /// A number from `low` up to `high`.
    pub fn range(&mut self, [low, high]: [f64; 2]) -> f64 {
        low + (high - low) * self.unit()
    }

    /// One of `items`, each picked in proportion to its `weight`.
    pub fn pick<'a, T>(&mut self, items: &'a [T], weight: impl Fn(&T) -> f64) -> &'a T {
        let mut left = self.unit() * items.iter().map(&weight).sum::<f64>();
        for item in items {
            if left < weight(item) {
                return item;
            }
            left -= weight(item);
        }
        &items[items.len() - 1]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Numbers fall in their range, and the same seed gives the same numbers.
    #[test]
    fn repeats_within_range() {
        let draw = |seed| {
            let mut random = Random::new(seed);
            (0..100).map(|_| random.range([2.0, 3.0])).collect::<Vec<_>>()
        };
        assert_eq!(draw(7), draw(7));
        assert_ne!(draw(7), draw(8));
        assert!(draw(7).iter().all(|x| (2.0..3.0).contains(x)));
    }

    /// Picks follow their weights: a weight three times another is picked about three times as often.
    #[test]
    fn picks_by_weight() {
        let mut random = Random::new(1);
        let picks: Vec<&str> = (0..4000).map(|_| random.pick(&[("a", 3.0), ("b", 1.0)], |(_, w)| *w).0).collect();
        let first = picks.iter().filter(|&&k| k == "a").count() as f64;
        assert!((first / 4000.0 - 0.75).abs() < 0.03);
    }
}
