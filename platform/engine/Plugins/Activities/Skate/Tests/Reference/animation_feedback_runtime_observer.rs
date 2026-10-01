// Appended after the complete immutable animation_feedback.rs implementation.
impl AnimationFeedback {
    pub(crate) fn migration_observe(&self, out: &mut crate::Output) {
        let s = &self.settings;
        for c in s.filter_coefficients { out.floats(c); }
        for p in [&s.input_curve, &s.quickness_curve, &s.speed_curve] {
            out.floats(p.x); out.floats(p.y);
        }
        out.floats(s.smoothing_curve.x); out.floats(s.smoothing_curve.y);
        out.floats(s.parameters);
        out.floats([self.bump_settings.scale_x_acc, self.bump_settings.min_bump_mag]);
        out.floats(self.state.history);
        for f in self.state.filters { out.floats(f); }
        out.floats(self.previous_lateral_tilt);
        out.floats(self.published_previous_lateral_tilt);
    }
}
