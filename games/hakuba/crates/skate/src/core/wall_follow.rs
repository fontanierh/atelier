//! Curved-wall measurement and the physical/predicted turn of assisted vert airs.
//! Zero strength leaves stock simulation untouched. All distances are metres.
use super::math::Vector3;

pub const STEEP_NORMAL_Y: f32 = 0.75;
pub const LAUNCH_MARGIN: f32 = 1.03;
pub const MAXIMUM_TIME: f32 = 6.0;
pub const PENDING_TICKS: u32 = 10;

/// Rotate about world +Y, preserving vertical speed and the fourth lane.
pub fn yaw(mut v: [f32; 4], angle: f32) -> [f32; 4] {
    let (s, c) = (angle as f64).sin_cos();
    let x = c * v[0] as f64 + s * v[2] as f64;
    let z = c * v[2] as f64 - s * v[0] as f64;
    v[0] = x as f32;
    v[2] = z as f32;
    v
}
pub fn yaw3(v: Vector3, angle: f32) -> Vector3 {
    let a = yaw([v.x, v.y, v.z, 0.0], angle);
    Vector3::new(a[0], a[1], a[2])
}
pub fn inward(mut v: [f32; 4], nx: f32, nz: f32) -> [f32; 4] {
    let into = v[0] * nx + v[2] * nz;
    if into < 0.0 {
        v[0] -= nx * into;
        v[2] -= nz * into;
    }
    v
}
pub fn inward3(v: Vector3, nx: f32, nz: f32) -> Vector3 {
    let a = inward([v.x, v.y, v.z, 0.0], nx, nz);
    Vector3::new(a[0], a[1], a[2])
}
/// Horizontal displacement and velocity; after `turning`, continue straight.
pub fn arc_at(vx: f32, vz: f32, curvature: f32, turning: f32, time: f32) -> (f64, f64, f32, f32) {
    let (vx, vz) = (vx as f64, vz as f64);
    let rate = curvature as f64 * (vx * vx + vz * vz).sqrt();
    let t = time as f64;
    let turned = t.clamp(0.0, (turning as f64).max(0.0));
    if rate == 0.0 || turned <= 0.0 {
        return (vx * t, vz * t, vx as f32, vz as f32);
    }
    let angle = rate * turned;
    let s = angle.sin();
    let half = (angle * 0.5).sin();
    let h = 2.0 * half * half;
    let c = 1.0 - h;
    let wx = c * vx + s * vz;
    let wz = c * vz - s * vx;
    ((s * vx + h * vz) / rate + wx * (t - turned), (s * vz - h * vx) / rate + wz * (t - turned), wx as f32, wz as f32)
}
/// A chord's sag is bounded by gravity and perpendicular centripetal acceleration.
pub fn chord_acceleration(gravity_y: f32, vx: f32, vz: f32, curvature: f32) -> f32 {
    let centripetal = (curvature as f64).abs() * ((vx as f64).powi(2) + (vz as f64).powi(2));
    -((gravity_y as f64).powi(2) + centripetal * centripetal).sqrt() as f32
}
pub fn concave(curvature: f32, v: [f32; 4], n: [f32; 4]) -> bool {
    let side = (v[2] * n[0] - v[0] * n[2]) * if curvature > 0.0 { 1.0 } else { -1.0 };
    curvature != 0.0 && side > 0.0
}
#[derive(Clone, Copy, Debug, Default)]
struct Sample {
    x: f32,
    z: f32,
    nx: f32,
    nz: f32,
}
/// Least-squares centre of recent horizontal ground-normal lines.
#[derive(Clone, Debug, Default)]
pub struct CurvatureTracker {
    samples: [Sample; 24],
    count: usize,
    next: usize,
}
impl CurvatureTracker {
    pub fn reset(&mut self) {
        self.count = 0;
        self.next = 0;
    }
    pub fn observe(&mut self, normal: Vector3, position: Vector3) {
        let horizontal = (normal.x * normal.x + normal.z * normal.z).sqrt();
        if !(normal.y < STEEP_NORMAL_Y) || !(horizontal > 0.3) || !position.x.is_finite() || !position.z.is_finite() {
            self.reset();
            return;
        }
        self.samples[self.next] =
            Sample { x: position.x, z: position.z, nx: normal.x / horizontal, nz: normal.z / horizontal };
        self.next = (self.next + 1) % 24;
        self.count = (self.count + 1).min(24);
    }
    pub fn curvature(&self) -> f32 {
        if self.count < 12 {
            return 0.0;
        }
        let first = self.samples[(self.next + 24 - self.count) % 24];
        let last = self.samples[(self.next + 23) % 24];
        let vx = last.x as f64 - first.x as f64;
        let vz = last.z as f64 - first.z as f64;
        if !((vx * last.nz as f64 - vz * last.nx as f64).abs() >= 4.0) {
            return 0.0;
        }
        let (mut a, mut b, mut d, mut e, mut f) = (0.0, 0.0, 0.0, 0.0, 0.0);
        for q in &self.samples[..self.count] {
            let (tx, tz) = (q.nz as f64, -q.nx as f64);
            let along = tx * (q.x as f64 - last.x as f64) + tz * (q.z as f64 - last.z as f64);
            a += tx * tx;
            b += tx * tz;
            d += tz * tz;
            e += tx * along;
            f += tz * along;
        }
        let det = a * d - b * b;
        if !(det / (self.count * self.count) as f64 > 1e-9) {
            return 0.0;
        }
        let cx = (d * e - b * f) / det;
        let cz = (a * f - b * e) / det;
        let radius = (cx * cx + cz * cz).sqrt();
        if !(8.0..=400.0).contains(&radius) {
            return 0.0;
        }
        let side = vz * cx - vx * cz;
        if side == 0.0 { 0.0 } else { (side.signum() / radius) as f32 }
    }
}
/// Launch-latched state, advanced only after the shared rigid-body solve.
#[derive(Clone, Debug)]
pub struct WallFollowAir {
    pub strength: f32,
    pub tracker: CurvatureTracker,
    pub ticks_since_ground: u32,
    pub pending: bool,
    pub active: bool,
    pub pending_ticks: u32,
    pub curvature: f32,
    pub elapsed: f32,
    pub inward_x: f32,
    pub inward_z: f32,
}
impl Default for WallFollowAir {
    fn default() -> Self {
        Self {
            strength: 0.0,
            tracker: CurvatureTracker::default(),
            ticks_since_ground: 0xffff,
            pending: false,
            active: false,
            pending_ticks: 0,
            curvature: 0.0,
            elapsed: 0.0,
            inward_x: 0.0,
            inward_z: 0.0,
        }
    }
}
impl WallFollowAir {
    pub fn stop(&mut self) {
        self.pending = false;
        self.active = false;
        self.pending_ticks = 0;
        self.curvature = 0.0;
        self.elapsed = 0.0;
        self.inward_x = 0.0;
        self.inward_z = 0.0;
    }
    pub fn reset(&mut self) {
        self.stop();
        self.tracker.reset();
        self.ticks_since_ground = 0xffff;
    }
    pub fn remaining(&self) -> f32 {
        (MAXIMUM_TIME - self.elapsed).max(0.0)
    }
    pub fn launch_curvature(
        &self,
        aligned: bool,
        assist: f32,
        limit: f32,
        directional: f32,
        velocity: [f32; 4],
        normal: [f32; 4],
    ) -> f32 {
        if !(self.strength > 0.0)
            || self.pending
            || self.active
            || !aligned
            || !(assist > 0.0)
            || !(limit > 0.0)
            || !(directional <= 0.25)
            || self.ticks_since_ground > 2
        {
            return 0.0;
        }
        let k = self.tracker.curvature();
        if concave(k, velocity, normal) { k * self.strength * LAUNCH_MARGIN } else { 0.0 }
    }
}
#[cfg(test)]
mod tests;
