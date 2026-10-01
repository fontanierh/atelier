// Read-only migration observations appended after the complete original motion.rs.
impl MotionHost {
    pub(crate) fn migration_continuation_registration(&self) -> (Vec<bool>, usize) {
        (self.operations.iter().map(|op| !matches!(op, MotionOperation::Unsupported { .. })).collect(), self.instances.len())
    }
}
