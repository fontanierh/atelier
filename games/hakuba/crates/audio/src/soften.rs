//! Board-only sample processing. Bevy exposes custom Decodable sources, not a live sink low-pass control.
//! A shared switch and gain reach existing decoders as well as the next voice before its first sample.
use bevy::audio::{ChannelCount, Decodable, SampleRate, Source};
use bevy::prelude::*;
use std::sync::{
    Arc,
    atomic::{AtomicBool, AtomicU32, Ordering},
};
use std::time::Duration;

#[derive(Resource, Clone)]
pub(super) struct VoicePreferences {
    soften: Arc<AtomicBool>,
    gain: Arc<AtomicU32>,
}
impl Default for VoicePreferences {
    fn default() -> Self {
        Self { soften: Arc::new(AtomicBool::new(false)), gain: Arc::new(AtomicU32::new(1.0f32.to_bits())) }
    }
}
impl VoicePreferences {
    pub fn set(&self, soften: bool, gain: f32) {
        if !gain.is_finite() {
            return;
        }
        self.soften.store(soften, Ordering::Relaxed);
        self.gain.store(gain.clamp(0., 1.).to_bits(), Ordering::Relaxed);
    }
}
#[derive(Asset, TypePath, Clone)]
pub(super) struct BoardSource {
    pub audio: AudioSource,
    pub preferences: VoicePreferences,
}
impl Decodable for BoardSource {
    type Decoder = Filtered<<AudioSource as Decodable>::Decoder>;
    fn decoder(&self) -> Self::Decoder {
        Filtered::new(self.audio.decoder(), self.preferences.clone())
    }
}
pub struct Filtered<S> {
    inner: S,
    preferences: VoicePreferences,
    memory: Vec<f32>,
    channel: usize,
    alpha: f32,
}
impl<S: Source<Item = f32>> Filtered<S> {
    fn new(inner: S, preferences: VoicePreferences) -> Self {
        let channels = inner.channels().get() as usize;
        // One-pole low-pass with a 3 kHz nominal cutoff, independently retained for each interleaved channel.
        let alpha = 1. - (-std::f32::consts::TAU * 3000. / inner.sample_rate().get() as f32).exp();
        Self { inner, preferences, memory: vec![0.; channels], channel: 0, alpha }
    }
}
impl<S: Source<Item = f32>> Iterator for Filtered<S> {
    type Item = f32;
    fn next(&mut self) -> Option<f32> {
        let raw = self.inner.next()?;
        let filtered = self.memory[self.channel] + self.alpha * (raw - self.memory[self.channel]);
        self.memory[self.channel] = filtered;
        self.channel = (self.channel + 1) % self.memory.len();
        let sample = if self.preferences.soften.load(Ordering::Relaxed) { filtered } else { raw };
        Some(sample * f32::from_bits(self.preferences.gain.load(Ordering::Relaxed)))
    }
    fn size_hint(&self) -> (usize, Option<usize>) {
        self.inner.size_hint()
    }
}
impl<S: Source<Item = f32>> Source for Filtered<S> {
    fn current_span_len(&self) -> Option<usize> {
        self.inner.current_span_len()
    }
    fn channels(&self) -> ChannelCount {
        self.inner.channels()
    }
    fn sample_rate(&self) -> SampleRate {
        self.inner.sample_rate()
    }
    fn total_duration(&self) -> Option<Duration> {
        self.inner.total_duration()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    struct Samples {
        samples: std::vec::IntoIter<f32>,
        channels: u16,
    }
    impl Iterator for Samples {
        type Item = f32;
        fn next(&mut self) -> Option<f32> {
            self.samples.next()
        }
    }
    impl Source for Samples {
        fn current_span_len(&self) -> Option<usize> {
            Some(self.samples.len())
        }
        fn channels(&self) -> ChannelCount {
            ChannelCount::new(self.channels).unwrap()
        }
        fn sample_rate(&self) -> SampleRate {
            SampleRate::new(48000).unwrap()
        }
        fn total_duration(&self) -> Option<Duration> {
            None
        }
    }
    fn samples(values: Vec<f32>, channels: u16) -> Samples {
        Samples { samples: values.into_iter(), channels }
    }
    #[test]
    fn live_and_future_voices_receive_gain_without_compounding() {
        let prefs = VoicePreferences::default();
        let mut current = Filtered::new(samples(vec![0.8; 8], 1), prefs.clone());
        assert_eq!(current.next(), Some(0.8));
        prefs.set(false, 0.5);
        assert_eq!(current.next(), Some(0.4));
        let mut future = Filtered::new(samples(vec![0.8; 8], 1), prefs.clone());
        assert_eq!(future.next(), Some(0.4));
        prefs.set(false, 1.0);
        assert_eq!(current.next(), Some(0.8));
        prefs.set(true, f32::NAN);
        assert_eq!(current.next(), Some(0.8));
    }
    #[test]
    fn softening_filters_real_samples_and_preserves_channel_separation() {
        let prefs = VoicePreferences::default();
        prefs.set(true, 1.);
        let mut stereo = Filtered::new(samples(vec![1., 0., 1., 0., 1., 0.], 2), prefs.clone());
        let left = stereo.next().unwrap();
        assert!(left > 0. && left < 1.);
        assert_eq!(stereo.next(), Some(0.));
        assert!(stereo.next().unwrap() > left);
        assert_eq!(stereo.next(), Some(0.));
        prefs.set(false, 1.);
        assert_eq!(stereo.next(), Some(1.));
        let alternating = (0..4800).map(|i| if i % 2 == 0 { 1. } else { -1. }).collect();
        prefs.set(true, 1.);
        let output: Vec<_> = Filtered::new(samples(alternating, 1), prefs).skip(100).collect();
        assert!(output.iter().all(|v| v.abs() < 0.25));
    }
}
