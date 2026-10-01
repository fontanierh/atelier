// [motion]
// Read-only observations appended after the complete pinned motion.rs prefix.
impl MotionHost {
    pub(crate) fn migration_complete_registration(&self) -> (Vec<bool>, usize) {
        (self.operations.iter().map(|op| !matches!(op, MotionOperation::Unsupported { .. })).collect(), self.instances.len())
    }
}
// [animation]
// Read-only observations appended after the complete pinned motion_animation.rs prefix.
impl MotionAnimation {
    pub(crate) fn migration_complete_pending(&self) -> &[SettableAttribute] {
        self.settable.entries()
    }
}
