//! Opt-in build-v2 interfaces. No production v1 callers use this crate.
//! Deserialization checks wire shape; semantic declaration validation belongs to A2.
#[cfg(all(test, target_os = "macos"))]
extern crate self as atelier_build_v2;
pub mod blender_ops;
pub mod checkout_locks;
pub mod cleanup;
#[cfg(any(target_os = "macos", target_os = "linux"))]
pub mod completion;
pub mod controller;
pub mod controller_transport;
#[cfg(any(target_os = "macos", target_os = "linux"))]
pub mod demand;
pub mod explain;
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
#[cfg(any(target_os = "macos", target_os = "linux"))]
mod legacy_epoch;
mod paths;
pub mod plans;
pub mod protocol;
pub mod py_data;
pub mod python_backend;
pub mod python_executor;
pub mod python_sources;
pub mod python_worker;
pub mod results;
pub mod roots;
pub mod scheduler;
pub mod schema;
pub mod session_lifecycle;
pub mod source_hashes;
pub mod staging;
pub mod store;
#[cfg(all(test, target_os = "macos"))]
#[path = "../tests/support/mod.rs"]
#[allow(dead_code)]
mod support;
pub mod unreal;
pub mod validate;
pub mod verify;
pub mod worker_lifecycle;
pub mod worker_session;

pub mod legacy_host;
pub(crate) mod legacy_host_launch;
