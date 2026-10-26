//! Every region, each with its implementation of [`Region`] from its folder under the world's `src/regions/`.

use super::overlay::Overlay;
use super::scenery::{Land, Scenery};

#[path = "../../../../assets/world/src/regions/momiji-coast/layout.rs"]
mod momiji_coast;

/// What a region adds to the world. Positions are in metres, in the map's frame: x east, y north, z up.
pub trait Region {
    /// The region's folder name.
    fn name(&self) -> &'static str;

    /// The flat shapes it lays over the ground.
    fn overlays(&self) -> Vec<Overlay>;

    /// What it stands on `land` and runs along it.
    fn scenery(&self, land: &Land) -> Scenery;

    /// The models whose anchors its cables fasten to, by folder under `assets/`. The world reads their exports.
    fn fastens_to(&self) -> Vec<&'static str>;
}

pub const REGIONS: [&dyn Region; 1] = [&momiji_coast::MomijiCoast];
