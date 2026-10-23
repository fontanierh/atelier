//! Opt-in build-v2 interfaces. No production v1 callers use this crate.
//! Deserialization checks wire shape; semantic declaration validation belongs to A2.
pub mod checkout_locks;
#[cfg(any(target_os = "macos", target_os = "linux"))]
pub mod completion;
#[cfg(any(target_os = "macos", target_os = "linux"))]
pub mod demand;
pub mod failure_policy;
pub mod fixture;
pub mod graph;
pub mod groups;
pub mod guard_adapter;
#[cfg(any(target_os = "macos", target_os = "linux"))]
pub mod install;
#[cfg(any(target_os = "macos", target_os = "linux"))]
mod install_fs;
pub mod integrity;
pub mod keys;
pub mod launch;
pub mod leases;
mod paths;
pub mod plans;
pub mod protocol;
pub mod py_data;
pub mod results;
pub mod scheduler;
pub mod schema;
pub mod source_hashes;
pub mod staging;
pub mod store;
pub mod validate;
pub mod verify;
pub mod worker_lifecycle;
pub mod worker_session;
