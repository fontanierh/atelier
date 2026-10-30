//! Curvature, physical flight and prediction consistency checks.
use super::*;
use crate::core::air::trajectory::{QueryRequest, Trajectory, query_trajectory};
const DT: f32 = 1.0 / 60.0;
fn ride(radius: f32, speed: f32, normal_y: f32, facet_degrees: f32, seconds: f32) -> CurvatureTracker {
    let mut t = CurvatureTracker::default();
    let horizontal = (1.0 - normal_y.powi(2)).sqrt() as f64;
    let facet = (facet_degrees as f64).to_radians();
    for tick in 0..=(seconds * 60.0) as u32 {
        let angle = speed as f64 * DT as f64 * tick as f64 / radius as f64;
        let face = if facet > 0.0 { ((angle / facet).floor() + 0.5) * facet } else { angle };
        t.observe(
            Vector3::new((-face.cos() * horizontal) as f32, normal_y, (-face.sin() * horizontal) as f32),
            Vector3::new(radius * angle.cos() as f32, 20.0, radius * angle.sin() as f32),
        );
    }
    t
}
fn latch(strength: f32, aligned: bool, assist: f32, limit: f32, transfer: f32, ticks: u32) -> f32 {
    let w = WallFollowAir {
        strength,
        tracker: ride(95.0, 40.0, 0.1, 0.74, 0.5),
        ticks_since_ground: ticks,
        ..Default::default()
    };
    w.launch_curvature(aligned, assist, limit, transfer, [0.0, 30.0, 40.0, 0.0], [-1.0, 0.0, 0.0, 0.0])
}
#[test]
fn curvature_reads_smooth_faceted_reverse_and_straight_walls() {
    for (radius, speed, ny, facet, tolerance) in [
        (95.0_f32, 40.0_f32, 0.1_f32, 0.0_f32, 0.01_f32),
        (95.0, -40.0, 0.1, 0.0, 0.01),
        (55.0, 40.0, 0.4, 0.0, 0.01),
        (95.0, 40.0, 0.1, 0.74, 0.05),
        (95.0, 40.0, 0.1, 3.0, 0.3),
    ] {
        let expected = -speed.signum() / radius;
        assert!((ride(radius, speed, ny, facet, 0.5).curvature() - expected).abs() < tolerance / radius);
    }
    let mut straight = CurvatureTracker::default();
    for i in 0..=30 {
        straight.observe(Vector3::new(-0.95, 0.3, 0.0), Vector3::new(95.0, 20.0, 40.0 * DT * i as f32));
    }
    assert_eq!(straight.curvature(), 0.0);
    for (r, s, ny, seconds) in
        [(95.0, 40.0, 0.8, 0.5), (95.0, 40.0, 0.1, 0.15), (6.0, 10.0, 0.1, 0.5), (600.0, 40.0, 0.1, 0.5)]
    {
        assert_eq!(ride(r, s, ny, 0.0, seconds).curvature(), 0.0);
    }
}
#[test]
fn only_recent_assisted_concave_vert_launch_latches() {
    let full = latch(1.0, true, 1.0, 1.0, 0.0, 1);
    assert!(full < -1.0 / 95.0 && full > -1.1 / 95.0);
    assert_eq!(latch(0.5, true, 1.0, 1.0, 0.0, 1), full * 0.5);
    for (strength, aligned, assist, limit, transfer, ticks) in [
        (0.0, true, 1.0, 1.0, 0.0, 1),
        (1.0, true, 0.0, 0.0, 0.0, 1),
        (1.0, true, 1.0, 0.0, 0.0, 1),
        (1.0, true, 0.0, 1.0, 0.0, 1),
        (1.0, false, 1.0, 1.0, 0.0, 1),
        (1.0, true, 1.0, 1.0, 1.0, 1),
        (1.0, true, 1.0, 1.0, 0.3, 1),
        (1.0, true, 1.0, 1.0, 0.0, 3),
    ] {
        assert_eq!(latch(strength, aligned, assist, limit, transfer, ticks), 0.0);
    }
    assert!(!concave(-1.0 / 95.0, [0.0, 0.0, 40.0, 0.0], [1.0, 0.0, 0.0, 0.0]));
    assert_eq!(inward([0.3, 17.0, 30.0, 0.0], -1.0, 0.0), [0.0, 17.0, 30.0, 0.0]);
    assert_eq!(inward([-0.3, 17.0, 30.0, 0.0], -1.0, 0.0), [-0.3, 17.0, 30.0, 0.0]);
}
#[test]
fn curved_bowl_flight_keeps_climb_speed_and_prediction() {
    let k = -LAUNCH_MARGIN / 95.0;
    let mut p = [95.0, 34.0, 0.0, 0.0];
    let mut v = [0.0, 10.0, 40.0, 0.0];
    let mut stock_y = p[1];
    let mut stock_vy = v[1];
    let mut outside = 0.0_f32;
    for _ in 0..120 {
        v[1] -= 9.8 * DT;
        stock_vy -= 9.8 * DT;
        for i in 0..3 {
            p[i] += v[i] * DT;
        }
        stock_y += stock_vy * DT;
        v = yaw(v, k * (v[0] * v[0] + v[2] * v[2]).sqrt() * DT);
        outside = outside.max((p[0] * p[0] + p[2] * p[2]).sqrt() - 95.0);
    }
    assert!(outside < 0.05);
    assert!(((p[0] * p[0] + p[2] * p[2]).sqrt() - 95.0).abs() < 1.0);
    assert!(((v[0] * v[0] + v[2] * v[2]).sqrt() - 40.0).abs() < 0.01);
    assert_eq!(p[1].to_bits(), stock_y.to_bits());
    let (dx, dz, _, _) = arc_at(0.0, 40.0, k, 6.0, 2.0);
    assert!(((95.0 + dx - p[0] as f64).powi(2) + (dz - p[2] as f64).powi(2)).sqrt() < 0.5);
    let (_, _, vx, vz) = arc_at(0.0, 40.0, -1.0 / 95.0, 1.0, 2.0);
    assert!(((-vx).atan2(vz) - 40.0 / 95.0).abs() < 1e-4);
}
fn trajectory(k: f32) -> Trajectory {
    Trajectory {
        position: [0.0; 4],
        velocity: [0.0, 10.0, 40.0, 0.0],
        acceleration: [0.0, -9.8, 0.0, 0.0],
        duration: 4.0,
        wall_curvature: k,
        wall_follow_time: if k == 0.0 { 0.0 } else { 4.0 },
    }
}
fn nearest(p: [f32; 4], segments: &[([f32; 4], [f32; 4])]) -> f64 {
    segments
        .iter()
        .map(|(a, b)| {
            let d: [f64; 3] = std::array::from_fn(|i| b[i] as f64 - a[i] as f64);
            let q: [f64; 3] = std::array::from_fn(|i| p[i] as f64 - a[i] as f64);
            let f = (q.iter().zip(d).map(|(q, d)| q * d).sum::<f64>() / d.iter().map(|d| d * d).sum::<f64>())
                .clamp(0.0, 1.0);
            (0..3).map(|i| (q[i] - f * d[i]).powi(2)).sum::<f64>().sqrt()
        })
        .fold(f64::INFINITY, f64::min)
}
#[test]
fn landing_query_chords_bound_tight_curvature_too() {
    for k in [0.0, -1.0 / 8.0, -LAUNCH_MARGIN / 95.0] {
        let t = trajectory(k);
        let mut segments = Vec::new();
        let result: Result<_, ()> = query_trajectory(
            QueryRequest { trajectory: t, radius: 0.2, start_error: 0.25, end_error: 1.2 },
            |a, b, _| {
                segments.push((a, b));
                Ok(None)
            },
            |_, _| Ok(Vec::new()),
        );
        assert!(!result.unwrap().valid());
        assert!(!segments.is_empty());
        let first_end = (0..40000)
            .map(|i| i as f32 * 0.0001)
            .min_by(|a, b| {
                let dist = |time| (0..3).map(|i| (t.position_at(time)[i] - segments[0].1[i]).powi(2)).sum::<f32>();
                dist(*a).total_cmp(&dist(*b))
            })
            .unwrap();
        assert!(nearest(t.position_at(first_end * 0.5), &segments) < 0.051);
        for i in 0..2394 {
            assert!(nearest(t.position_at(i as f32 / 600.0), &segments) < 0.241);
        }
    }
}
#[test]
fn stock_positions_and_velocities_keep_original_bits() {
    let t = trajectory(0.0);
    for time in [-1.0, 0.0, 0.016666668, 0.5, 2.0, 4.0] {
        let p: [f32; 4] = std::array::from_fn(|i| {
            (t.acceleration[i] * 0.5).mul_add(time * time, t.velocity[i].mul_add(time, t.position[i]))
        });
        let v: [f32; 4] = std::array::from_fn(|i| t.acceleration[i].mul_add(time, t.velocity[i]));
        assert_eq!(t.position_at(time).map(f32::to_bits), p.map(f32::to_bits));
        assert_eq!(t.velocity_at(time).map(f32::to_bits), v.map(f32::to_bits));
    }
}

#[test]
fn changing_or_stopping_air_clears_latched_state_not_strength() {
    let mut w = WallFollowAir {
        strength: 0.5,
        tracker: ride(95.0, 40.0, 0.1, 0.0, 0.5),
        ticks_since_ground: 0,
        pending: true,
        active: true,
        pending_ticks: 3,
        curvature: -1.0 / 95.0,
        elapsed: 5.5,
        inward_x: -1.0,
        inward_z: 0.0,
    };
    assert_eq!(w.remaining(), 0.5);
    w.stop();
    assert_eq!(w.strength, 0.5);
    assert!(!w.pending && !w.active);
    assert_eq!(w.curvature, 0.0);
    assert_ne!(w.tracker.curvature(), 0.0);
    w.reset();
    assert_eq!(w.tracker.curvature(), 0.0);
    assert_eq!(w.ticks_since_ground, 0xffff);
    assert_eq!(w.strength, 0.5);
}
