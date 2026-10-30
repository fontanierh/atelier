//! TU3 post-solver contact observations and their native record lifetimes.
pub(crate) mod board_reports;
mod collision_info;
mod compression;
mod reports;
mod spy;

pub use board_reports::BoardContactReport;
pub use collision_info::choose_surface;
pub use compression::average_wheel_compressions;

pub use spy::spy_contact_jacobians;

/// SkateboardBody+64..+876, retained as guest big-endian bytes.
pub type CollisionInfo = [u8; 812];
