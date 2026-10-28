//! Authored structure origins in map metres and turns in degrees.

/// Asset folder, map x/y/z, yaw and scale. These origins are independent of sampled terrain.
pub const STRUCTURES: [(&str, [f64; 3], f64, f64); 9] = [
    ("props/village-cottage-a", [80.0, 99.0, 30.395], 45.0, 1.0),
    ("props/village-cottage-b", [104.5, 105.0, 30.725], -20.0, 1.0),
    ("props/village-workshop", [118.0, 68.0, 28.69], -120.0, 1.0),
    ("props/village-storehouse", [122.0, 89.5, 29.872500000000002], -90.0, 1.0),
    ("props/village-garden", [99.0, 85.0, 29.625], 0.0, 1.0),
    ("props/village-sign", [90.1, -22.4, 17.275307391620597], 57.08788176478339, 0.78),
    ("props/village-sign", [118.0, 106.0, 31.01500735218522], -125.0, 0.78),
    ("props/village-threshold", [125.80262901384049, 107.86342718806809, 31.5987373308337], -54.97661733564209, 1.0),
    ("props/village-tea-house", [77.5, 77.5, 29.212500000000002], 90.0, 1.0),
];
