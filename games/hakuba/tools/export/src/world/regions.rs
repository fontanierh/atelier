//! Every region, each with its implementation of [`Region`] from its folder under the world's `src/regions/`.

use super::levelling::{Pad, Strip};
use super::overlay::Overlay;
use super::scenery::{Exclusion, Land, Scenery};

#[path = "../../../../assets/world/src/regions/momiji-coast/layout.rs"]
mod momiji_coast;

#[path = "../../../../assets/world/src/regions/momiji-hamlet/layout.rs"]
mod momiji_hamlet;

/// What a region adds to the world. Positions are in metres, in the map's frame: x east, y north, z up.
pub trait Region {
    /// The region's folder name.
    fn name(&self) -> &'static str;

    /// The strips of ground it levels, as declared changes to the ground. Everything else the world holds, its
    /// tiles, overlays and scenery, stands on the levelled ground.
    fn levelled(&self) -> Vec<Strip>;

    /// Planar ground footprints and shoulders, applied after strips and owning their final surface at crossings.
    fn pads(&self) -> Vec<Pad> {
        Vec::new()
    }

    /// Areas kept clear of scattered scenery. Explicit placements are unaffected.
    fn scatter_exclusions(&self) -> Vec<Exclusion> {
        Vec::new()
    }

    /// The flat shapes it lays over the ground.
    fn overlays(&self) -> Vec<Overlay>;

    /// What it stands on `land` and runs along it.
    fn scenery(&self, land: &Land) -> Scenery;

    /// The models whose anchors its cables fasten to, by folder under `assets/`. The world reads their exports.
    fn fastens_to(&self) -> Vec<&'static str>;
}

pub const REGIONS: [&dyn Region; 2] = [&momiji_coast::MomijiCoast, &momiji_hamlet::MomijiHamlet];
