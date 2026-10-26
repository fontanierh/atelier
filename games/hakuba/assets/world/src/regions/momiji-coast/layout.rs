//! Momiji coast: the coastal road, from west to east across the region.

use super::{Region, RoadPlan};

pub const REGION: Region = Region {
    name: "momiji-coast",
    roads: &[RoadPlan {
        course: &[
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
        ],
        width_m: 5.2,
        colour: [0.33, 0.33, 0.34],
    }],
};
