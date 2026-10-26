//! Momiji coast: the coastal road, from west to east across the region.

use super::Region;
use crate::world::overlay::Overlay;
use crate::world::ribbon::ribbon;

/// The points the road's centre line passes through, from its west end to its east end.
const ROAD: [[f64; 2]; 11] = [
    [-295.0, -95.0],
    [-230.0, -100.0],
    [-170.0, -85.0],
    [-110.0, -70.0],
    [-50.0, -70.0],
    [10.0, -45.0],
    [70.0, -30.0],
    [130.0, -25.0],
    [190.0, -5.0],
    [240.0, 25.0],
    [295.0, 60.0],
];

const ROAD_WIDTH_M: f64 = 5.2;

/// How often the road's texture repeats along it.
const ROAD_TEXTURE_M: f64 = 8.0;

/// The road's colour, in sRGB.
const ROAD_COLOUR: [f64; 3] = [0.33, 0.33, 0.34];

pub struct MomijiCoast;

impl Region for MomijiCoast {
    fn name(&self) -> &'static str {
        "momiji-coast"
    }

    /// The road. The ground already holds its cut.
    fn overlays(&self) -> Vec<Overlay> {
        vec![Overlay {
            name: "road".into(),
            colour: ROAD_COLOUR,
            triangles: ribbon(&ROAD, ROAD_WIDTH_M, ROAD_TEXTURE_M),
        }]
    }
}
