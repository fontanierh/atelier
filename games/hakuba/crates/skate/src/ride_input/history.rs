//! Timestamped raw-stick observations. A tick never invents a reading between observations.
use crate::Controls;
use bevy::prelude::*;
use std::collections::VecDeque;

/// Optional high-frequency device reading in the `Time<Real>` elapsed-seconds clock.
/// Platform adapters publish the complete raw stick pairs at their actual capture time.
/// Bevy's ordinary raw axis events have no device timestamp and cannot provide hidden samples.
#[derive(Message, Clone, Copy, Debug)]
pub struct StickReading {
    pub gamepad: Entity,
    pub captured_at: f64,
    pub left: [i16; 2],
    pub right: [i16; 2],
}
#[derive(Clone, Copy, Debug)]
struct Sample {
    time: f64,
    left: [i16; 2],
    right: [i16; 2],
}
#[derive(Default)]
pub(super) struct StickHistory {
    samples: VecDeque<Sample>,
}
impl StickHistory {
    pub fn clear(&mut self) {
        self.samples.clear();
    }
    pub fn observe(&mut self, time: f64, now: f64, left: [i16; 2], right: [i16; 2]) {
        if !time.is_finite() || !now.is_finite() || time > now + 1.0e-6 || time < now - 0.5 {
            return;
        }
        while self.samples.front().is_some_and(|s| s.time < now - 0.5) {
            self.samples.pop_front();
        }
        let at = self.samples.partition_point(|s| s.time < time);
        let sample = Sample { time, left, right };
        if self.samples.get(at).is_some_and(|s| s.time == time) {
            self.samples[at] = sample;
        } else {
            self.samples.insert(at, sample);
        }
        while self.samples.len() > 256 {
            self.samples.pop_front();
        }
    }
    pub fn for_tick(&self, end: f64, period: f32, packet: Controls) -> Option<(Controls, Controls)> {
        if !end.is_finite() || !period.is_finite() || period <= 0.0 {
            return None;
        }
        let start = end - f64::from(period);
        let half = end - f64::from(period) * 0.5;
        let earlier = self.samples.iter().rev().find(|s| s.time <= half + 1.0e-7)?;
        let now = self.samples.iter().rev().find(|s| s.time <= end + 1.0e-7)?;
        // One ordinary frame's packet is not two samples. There must be real
        // observations in both halves of this tick, not repeated or stale data.
        if earlier.time <= start + 1.0e-7 || now.time <= half + 1.0e-7 {
            return None;
        }
        if now.left != packet.left || now.right != packet.right {
            return None;
        }
        Some((
            Controls { left: earlier.left, right: earlier.right, ..packet },
            Controls { left: now.left, right: now.right, ..packet },
        ))
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn packet(right: [i16; 2]) -> Controls {
        Controls { right, ..Default::default() }
    }
    #[test]
    fn actual_device_times_expose_a_between_frame_flick() {
        let mut h = StickHistory::default();
        let p = 1.0 / 60.0;
        h.observe(1.002, 1.017, [0; 2], [20000, -20000]);
        h.observe(1.012, 1.017, [0; 2], [20000, 20000]);
        let (half, end) = h.for_tick(1.0 + f64::from(p), p, packet([20000, 20000])).unwrap();
        assert_eq!(half.right, [20000, -20000]);
        assert_eq!(end.right, [20000, 20000]);
    }
    #[test]
    fn untimestamped_frame_events_never_invent_a_midpoint() {
        let mut h = StickHistory::default();
        let p = 1.0 / 60.0;
        h.observe(1.016, 1.016, [0; 2], [20000, -20000]);
        h.observe(1.016, 1.016, [0; 2], [20000, 20000]);
        assert!(h.for_tick(1.0 + f64::from(p), p, packet([20000, 20000])).is_none());
        assert_eq!(h.samples.len(), 1);
    }
    #[test]
    fn stale_future_and_injected_endpoint_mismatch_fall_back() {
        let mut h = StickHistory::default();
        let p = 1.0 / 60.0;
        h.observe(1.002, 1.017, [0; 2], [20000, -20000]);
        h.observe(1.012, 1.017, [0; 2], [20000, 20000]);
        assert!(h.for_tick(1.0 + f64::from(p), p, packet([0; 2])).is_none());
        assert!(h.for_tick(1.2, p, packet([20000, 20000])).is_none());
        h.observe(f64::NAN, 1.017, [0; 2], [0; 2]);
        h.observe(2.0, 1.017, [0; 2], [0; 2]);
        assert_eq!(h.samples.len(), 2);
        h.clear();
        assert!(h.samples.is_empty());
    }
}
