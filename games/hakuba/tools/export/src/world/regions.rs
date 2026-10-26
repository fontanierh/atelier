//! Every region, each with its layout from its folder under the world's `src/regions/`.

#[path = "../../../../assets/world/src/regions/momiji-coast/layout.rs"]
mod momiji_coast;

/// What a region adds to the world. Positions are in metres, in the map's frame: x east, y north, z up.
pub struct Region {
    /// The region's folder name.
    pub name: &'static str,
    pub roads: &'static [RoadPlan],
}

/// A road a region lays on the ground.
pub struct RoadPlan {
    /// The points its centre line passes through, in order.
    pub course: &'static [[f64; 2]],
    pub width_m: f64,
    /// Its colour, in sRGB.
    pub colour: [f64; 3],
}

pub const REGIONS: [Region; 1] = [momiji_coast::REGION];
