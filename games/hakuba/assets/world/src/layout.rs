//! The world's layout: where the road runs, where the player starts, and the colours of the ground and the road.
//! Positions are in metres, in the map's frame: x east, y north, z up, the origin at the map's centre.

/// The points the road's centre line passes through, from its west end to its east end.
pub const ROAD: [[f64; 2]; 11] = [
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

/// The road's width.
pub const ROAD_WIDTH_M: f64 = 5.2;

/// How far along the road, from its west end, the player starts, facing east along it.
pub const SPAWN_ALONG_ROAD_M: usize = 40;

/// The ground's colour, in sRGB.
pub const GROUND: [f64; 3] = [0.40, 0.44, 0.20];

/// The road's colour, in sRGB.
pub const ROAD_COLOUR: [f64; 3] = [0.33, 0.33, 0.34];
