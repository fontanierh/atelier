//! Opt-in build-v2 interfaces. No production v1 callers use this crate.
//! Deserialization checks wire shape; semantic declaration validation belongs to A2.
pub mod failure_policy;
pub mod fixture;
pub mod keys;
mod paths;
pub mod protocol;
pub mod schema;
pub mod source_hashes;
pub mod store;
pub mod validate;
