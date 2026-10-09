#include "SkiSim.h"

#include <algorithm>
#include <cmath>

namespace atelier::ski {

namespace {

constexpr double Pi = 3.14159265358979323846;

double Clamp(double x, double lo, double hi) { return std::min(hi, std::max(lo, x)); }
double Lerp(double a, double b, double t) { return a + (b - a) * t; }
double SmoothStep(double a, double b, double x) {
    const double t = Clamp((x - a) / (b - a), 0, 1);
    return t * t * (3 - 2 * t);
}
double Approach(double x, double target, double rate) { return x + Clamp(target - x, -rate, rate); }
double Sign(double x) { return x > 0 ? 1 : x < 0 ? -1 : 0; }
Vec3 Lerp(Vec3 a, Vec3 b, double t) { return {Lerp(a.x, b.x, t), Lerp(a.y, b.y, t), Lerp(a.z, b.z, t)}; }

Quat NormalizeQ(Quat q) {
    const double l = std::sqrt(q.w * q.w + q.x * q.x + q.y * q.y + q.z * q.z);
    return {q.w / l, q.x / l, q.y / l, q.z / l};
}

// Signed angle of `v` from `n` about `axis`.
double AngleAbout(Vec3 n, Vec3 v, Vec3 axis) { return std::atan2(Dot(Cross(n, v), axis), Dot(n, v)); }

Vec3 Inertia(const State& st, const Settings& s) { return Lerp(s.inertiaStand, s.inertiaTuck, st.tuck); }

// The edge angle whose sideways grip is `grip` times the load.
double EdgeForGrip(double grip, const Settings& s) {
    const double t = Clamp((grip - s.flatGrip) / (s.edgeGrip - s.flatGrip), 0, 1);
    // Invert smoothstep: t = x^2 (3 - 2x).
    const double x = 0.5 - std::sin(std::asin(1 - 2 * t) / 3);
    return x * Radians(s.edgeFullDeg);
}

struct SnowContact {
    Vec3 force, torque;
    double total = 0, slip = 0, edge = 0;
    Vec3 normal;
};

SnowContact Contacts(const State& st, const Terrain& terrain, const Settings& s, Vec3 w) {
    const Vec3 fB = Rotate(st.q, {1, 0, 0});
    const Quat skiQ = Multiply(st.q, {std::cos(st.angulation / 2), std::sin(st.angulation / 2), 0, 0});
    const Vec3 skiUp = Rotate(skiQ, {0, 0, 1});
    const int count = s.contactPoints;
    const double k = s.snowStiffness / count, c = s.snowDamping / count;
    SnowContact out;
    double slip = 0, edgeSum = 0;
    Vec3 normalSum;
    for (int i = 0; i < count; i++) {
        const double along = (double(i) / (count - 1) - 0.5) * s.skiLength;
        const Vec3 r = Rotate(st.q, {st.footX + along, 0, -st.h});
        const Vec3 point = st.p + r;
        const double ground = terrain.Height(point.x, point.y);
        if (point.z >= ground) continue;
        const Vec3 n = terrain.Normal(point.x, point.y);
        const double depth = (ground - point.z) * n.z;
        const Vec3 pointV = st.v + Cross(w, r) + Rotate(st.q, {st.footXRate, 0, -st.hRate});
        const double into = -Dot(pointV, n);
        const double fn = std::max(0.0, k * depth + c * into);
        if (fn <= 0) continue;
        const Vec3 ft = Normalize(fB - n * Dot(fB, n));
        const double edge = AngleAbout(n, skiUp, ft);
        // The edged ski's contact line bends into an arc: its local tangent turns with the distance from the boot.
        const double yaw = -along * Curvature(edge, s);
        const Vec3 tangent = ft * std::cos(yaw) + Cross(n, ft) * std::sin(yaw);
        const Vec3 lateral = Cross(n, tangent);
        const double grip = Lerp(s.flatGrip, s.edgeGrip, SmoothStep(0, Radians(s.edgeFullDeg), std::abs(edge)))
            * terrain.Grip(point.x, point.y) * ((st.popWindow > 0 && st.coil != 0) || st.pivoting ? s.pivotGrip : 1);
        const double vl = Dot(pointV, lateral), vf = Dot(pointV, tangent);
        const Vec3 f = n * fn + lateral * (-grip * fn * Clamp(vl / s.slipSpeed, -1, 1))
            + tangent * (-s.glideFriction * fn * Clamp(vf / 0.1, -1, 1));
        out.force = out.force + f;
        out.torque = out.torque + Cross(r, f);
        out.total += fn;
        slip += std::abs(vl) * fn;
        normalSum = normalSum + n * fn;
        edgeSum += edge * fn;
    }
    out.slip = out.total > 0 ? slip / out.total : 0;
    out.normal = out.total > 0 ? Normalize(normalSum) : terrain.Normal(st.p.x, st.p.y);
    out.edge = out.total > 0 ? edgeSum / out.total : st.edge;
    return out;
}

struct BodyContact {
    Vec3 force, torque;
    bool hit = false;
};

// Hip and head spheres: touching the snow with either is a crash.
BodyContact BodyContacts(const State& st, const Terrain& terrain, const Settings& s, Vec3 w) {
    const struct { Vec3 local; double radius; } spheres[] = {
        {{0, 0, 0}, s.hipRadius},
        {{0, 0, s.headHeight * (1 - 0.4 * st.tuck)}, s.headRadius},
    };
    BodyContact out;
    for (const auto& sphere : spheres) {
        const Vec3 r = Rotate(st.q, sphere.local);
        const Vec3 centre = st.p + r;
        const double ground = terrain.Height(centre.x, centre.y);
        const Vec3 n = terrain.Normal(centre.x, centre.y);
        const double depth = (ground - centre.z) * n.z + sphere.radius;
        if (depth <= 0) continue;
        out.hit = true;
        const Vec3 pointV = st.v + Cross(w, r);
        const double fn = std::max(0.0, 40000 * depth - 1500 * Dot(pointV, n));
        const Vec3 tangentV = pointV - n * Dot(pointV, n);
        const double speed = Length(tangentV);
        const Vec3 friction = speed > 1e-6 ? tangentV * (-0.45 * fn * std::min(1.0, speed / 0.2) / speed) : Vec3{};
        const Vec3 f = n * fn + friction;
        out.force = out.force + f;
        out.torque = out.torque + Cross(r + n * -sphere.radius, f);
    }
    return out;
}

void Crash(State& st, const char* why) {
    if (st.mode == Mode::Crash) return;
    st.mode = Mode::Crash;
    st.crashTime = 0;
    Event crash{EventType::Crash, st.time};
    crash.why = why;
    st.events.push_back(crash);
    if (st.hasLanding) {
        Event bail{EventType::Bail, st.time};
        bail.trick = st.landing.name;
        st.events.push_back(bail);
        st.hasLanding = false;
    }
}

void Track(State& st, bool wasGrounded, const Input& input, const Settings& s, Vec3 w) {
    const Vec3 zB = Rotate(st.q, {0, 0, 1});
    if (st.mode == Mode::Ride && wasGrounded && !st.grounded) {
        st.inAir = true;
        st.air = Air{};
        st.air.startZ = st.air.peak = st.p.z;
        st.air.switchStance = st.switchStance;
        st.coil = 0;
        st.events.push_back({EventType::Takeoff, st.time});
    }
    if (st.inAir && !st.grounded) {
        Air& a = st.air;
        a.time += s.dt;
        a.yaw += w.z * s.dt;
        const Vec3 side = Normalize(Cross({0, 0, 1}, Rotate(st.q, {1, 0, 0})));
        a.flip += Dot(w, side) * s.dt;
        a.peak = std::max(a.peak, st.p.z);
        if (input.grab != Grab::None) a.grabs[int(input.grab)] += s.dt;
    }
    if (st.inAir && st.grounded) {
        const Air a = st.air;
        st.inAir = false;
        if (st.mode != Mode::Ride || a.time < 0.3) return;
        const int spin = int(std::floor(std::abs(a.yaw) / Pi + 0.5)) * 180;
        const int flips = int(std::floor(std::abs(a.flip) / (2 * Pi) + 0.5));
        int grab = 0;
        for (int i = 1; i < GrabCount; i++)
            if (a.grabs[i] > 0.15 && (grab == 0 || a.grabs[i] > a.grabs[grab])) grab = i;
        std::string name;
        const auto part = [&name](const std::string& word) { name += (name.empty() ? "" : " ") + word; };
        if (a.switchStance) part("Switch");
        if (flips) {
            const std::string dir = a.flip > 0 ? "Front" : "Back";
            part(flips > 1 ? "Double " + dir + "flip" : dir + "flip");
        }
        if (spin) part(std::to_string(spin));
        if (grab) part(GrabName(Grab(grab)));
        if (!spin && !flips && !grab) part("Straight Air");
        const double points = 100 * a.time + spin * 0.8 + flips * 400 + (grab ? a.grabs[grab] * 300 : 0);
        st.hasLanding = true;
        st.landing = {name, int(std::floor(points + 0.5)), st.time, a.time, a.peak - a.startZ, st.switchStance};
        Event land{EventType::Land, st.time};
        land.trick = name;
        land.air = a.time;
        land.upright = Dot(zB, st.normal);
        st.events.push_back(land);
    }
    if (st.hasLanding && st.mode == Mode::Ride && st.time - st.landing.at > 0.7) {
        st.score += st.landing.points;
        Event trick{EventType::Trick, st.time};
        trick.trick = st.landing.name;
        trick.points = st.landing.points;
        st.events.push_back(trick);
        st.hasLanding = false;
    }
}

}  // namespace

double Dot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
Vec3 Cross(Vec3 a, Vec3 b) { return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x}; }
double Length(Vec3 a) { return std::sqrt(a.x * a.x + a.y * a.y + a.z * a.z); }
Vec3 Normalize(Vec3 a) {
    const double l = Length(a);
    return l > 1e-12 ? a * (1 / l) : Vec3{};
}

Vec3 Rotate(Quat q, Vec3 v) {
    const Vec3 u = {q.x, q.y, q.z};
    const Vec3 t = Cross(u, v) * 2;
    return v + t * q.w + Cross(u, t);
}

Quat Multiply(Quat a, Quat b) {
    return {
        a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
        a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
        a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
        a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
    };
}

Quat Conjugate(Quat q) { return {q.w, -q.x, -q.y, -q.z}; }

Quat FromBasis(Vec3 f, Vec3 l, Vec3 u) {
    const double m00 = f.x, m10 = f.y, m20 = f.z, m01 = l.x, m11 = l.y, m21 = l.z, m02 = u.x, m12 = u.y, m22 = u.z;
    const double trace = m00 + m11 + m22;
    Quat q;
    if (trace > 0) {
        const double s = 0.5 / std::sqrt(trace + 1);
        q = {0.25 / s, (m21 - m12) * s, (m02 - m20) * s, (m10 - m01) * s};
    } else if (m00 > m11 && m00 > m22) {
        const double s = 2 * std::sqrt(1 + m00 - m11 - m22);
        q = {(m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s};
    } else if (m11 > m22) {
        const double s = 2 * std::sqrt(1 + m11 - m00 - m22);
        q = {(m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s};
    } else {
        const double s = 2 * std::sqrt(1 + m22 - m00 - m11);
        q = {(m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s};
    }
    return NormalizeQ(q);
}

const char* GrabName(Grab grab) {
    switch (grab) {
        case Grab::Mute: return "Mute";
        case Grab::Safety: return "Safety";
        default: return "";
    }
}

double Radians(double degrees) { return degrees * Pi / 180; }

double Curvature(double edge, const Settings& s) {
    const double onset = SmoothStep(0, Radians(s.carveOnsetDeg), std::abs(edge));
    return Sign(edge) * onset / (s.sidecutRadius * std::cos(std::min(std::abs(edge), Radians(75))));
}

double EdgeFor(double kappa, const Settings& s) {
    double lo = 0, hi = Radians(s.maxEdgeDeg);
    if (std::abs(Curvature(hi, s)) <= kappa) return hi;
    for (int i = 0; i < 14; i++) {
        const double mid = (lo + hi) / 2;
        if (std::abs(Curvature(mid, s)) < kappa) lo = mid; else hi = mid;
    }
    return (lo + hi) / 2;
}

Vec3 AngularVelocity(const State& st, const Settings& s) {
    const Vec3 I = Inertia(st, s);
    const Vec3 local = Rotate(Conjugate(st.q), st.L);
    return Rotate(st.q, {local.x / I.x, local.y / I.y, local.z / I.z});
}

Vec3 BootLocal(const State& st) { return {st.footX, 0, -st.h}; }

State CreateSkier(const Terrain& terrain, double x, double y, double heading, double speed, const Settings& s) {
    const Vec3 n = terrain.Normal(x, y);
    const Vec3 along = {std::cos(heading), std::sin(heading), 0};
    const Vec3 f = Normalize(along - n * Dot(along, n));
    const Vec3 l = Cross(n, f);
    State st;
    st.h = s.standHeight - s.crouchDrop * s.rideCrouch;
    const double sink = s.mass * s.gravity / s.snowStiffness;
    st.p = Vec3{x, y, terrain.Height(x, y)} + n * (st.h - sink);
    st.v = f * speed;
    st.q = FromBasis(f, l, n);
    st.groundForce = s.mass * s.gravity;
    st.contactForce = n * (s.mass * s.gravity);
    st.normal = n;
    return st;
}

void Step(State& st, const Input& input, const Terrain& terrain, const Settings& s) {
    const double dt = s.dt, m = s.mass, g = s.gravity;
    const bool riding = st.mode == Mode::Ride;
    const Vec3 n = st.normal;
    const Vec3 fB = Rotate(st.q, {1, 0, 0}), zB = Rotate(st.q, {0, 0, 1});
    const Vec3 ft = Normalize(fB - n * Dot(fB, n));
    const Vec3 lt = Cross(n, ft);
    const Vec3 I = Inertia(st, s);
    Vec3 w = AngularVelocity(st, s);
    const double vf = Dot(st.v, ft), vl = Dot(st.v, lt);
    if (std::abs(vf) > 0.8) st.switchStance = vf < 0;
    const double travel = st.switchStance ? -1 : 1;
    const bool grounded = st.grounded;
    const double steer = Clamp(input.steer, -1, 1) * travel;
    Vec3 torque;

    if (riding && st.crouchHeld && !input.crouch && grounded) st.popWindow = 0.25;
    st.crouchHeld = input.crouch;
    st.popWindow = std::max(0.0, st.popWindow - dt);

    // Legs: crouch to load, extend to pop. Extension only pushes while the skis are on the snow.
    const bool grabbing = input.grab != Grab::None;
    const double crouch = !riding ? 0.3 : input.crouch ? 1 : !grounded && grabbing ? 1 : s.rideCrouch;
    const double target = s.standHeight - s.crouchDrop * crouch;
    // The legs are a servo with limited speed and acceleration: flexing is slower than extending, and extension
    // stops pushing once the snow pushes back harder than the legs can. Only a pop extends at full speed; after
    // soaking up a landing the legs stand back up slowly.
    const double extend = !grounded || st.popWindow > 0 ? s.legRate : s.recoverRate;
    double hRate = Approach(st.hRate, Clamp((target - st.h) * 30, -s.flexRate, extend), s.legAccel * dt);
    if (grounded && hRate > 0 && st.groundForce > s.legForceMax * m * g) hRate = Approach(hRate, 0, 2 * s.legAccel * dt);
    // Flexing lets the body sink onto bent knees; on the snow it never pulls the skis up off it.
    if (grounded && riding && hRate < 0 && st.groundForce < 0.45 * m * g) hRate = Approach(hRate, 0, 2 * s.legAccel * dt);
    st.hRate = hRate;
    if (grounded && st.groundForce > s.absorbStart * m * g) hRate -= (st.groundForce - s.absorbStart * m * g) / (m * s.absorbSoftness);
    const double h = Clamp(st.h + hRate * dt, s.standHeight - s.crouchDrop - 0.08, s.standHeight);
    if (h != st.h + hRate * dt) st.hRate = 0;
    st.h = h;
    const double footTarget = riding ? -Clamp(input.lean, -1, 1) * s.footShift * travel : 0;
    st.footXRate = Clamp((footTarget - st.footX) * 10, -1, 1);
    st.footX += st.footXRate * dt;

    const double tuckTarget = !riding ? 0.2 : grounded ? 0 : grabbing ? 1 : input.crouch ? 0.5 : 0.15;
    st.tuck = Approach(st.tuck, tuckTarget, 6 * dt);

    if (riding && grounded) {
        // Edge: steering, braking or holding the line against a sideslip. The stick asks for a turn and the rider
        // leans into it. The edge follows the lean: the rider tips the skis to carve the turn their inclination
        // (from plumb) can stand on, never more.
        const double roll = AngleAbout(n, zB, ft);
        const double lean = AngleAbout({0, 0, 1}, zB, ft);
        const double speed2 = vf * vf + vl * vl;
        const double wanted = std::abs(steer) * std::abs(Curvature(Radians(s.maxEdgeDeg), s));
        const double standable = g * std::tan(std::min(std::abs(lean), Radians(80))) / std::max(speed2, 0.5);
        // Sideslip of the boots, not the body: rolling over the edges swings the body sideways above held feet.
        const Vec3 feet = st.v + Cross(w, Rotate(st.q, BootLocal(st)));
        const double slide = Dot(feet, lt);
        double edgeTarget = Sign(lean) * EdgeFor(standable, s) + Clamp(slide * s.edgeHold, -Radians(15), Radians(15));
        // Hockey stop: flatten and pivot the skis across the travel, lean back against the slide, then set the
        // edges as hard as that lean can stand on.
        const double swing = std::abs(std::atan2(std::abs(slide), std::abs(Dot(feet, ft))));
        const double against = Sign(slide) * lean;
        st.pivoting = input.brake && speed2 > 1 && (swing < Radians(55) || against < Radians(s.brakeLeanDeg) * 0.6);
        if (input.brake)
            edgeTarget = st.pivoting || std::abs(slide) < 0.3 ? 0 : Sign(slide) * EdgeForGrip(std::tan(std::max(0.0, against)), s);
        // Balance: lean along the felt force of the turn the stick asks for.
        const Vec3 felt = lt * (-speed2 * Sign(steer) * wanted) + Vec3{0, 0, g};
        const double balanced = AngleAbout(n, Normalize(felt), ft);
        // The steepest lean the skis can hold at this speed: the full-edge carve. The assist keeps the lean inside it.
        const Vec3 fullCarve = lt * (-speed2 * Sign(steer) * std::abs(Curvature(Radians(s.maxEdgeDeg), s))) + Vec3{0, 0, g};
        const double limit = std::abs(AngleAbout(n, Normalize(fullCarve), ft));
        double rollTarget = Lerp(steer * Radians(s.maxEdgeDeg) * 0.75, balanced, s.balanceAssist);
        // Lean back against the slide once the skis are across, standing up again as the slide dies away.
        if (input.brake && speed2 > 0.04)
            rollTarget = Sign(slide) * Radians(s.brakeLeanDeg) * SmoothStep(Radians(20), Radians(50), swing)
                * SmoothStep(0.5, 5, std::sqrt(speed2));
        const double most = input.brake ? Radians(60)
            : Lerp(Radians(80), std::max(0.0, limit - Radians(5)), SmoothStep(0, 0.5, s.balanceAssist));
        rollTarget = Clamp(rollTarget, -most, most);
        const double reach = st.groundForce * s.balanceReach;
        // Roll at a rate that can still be stopped: the centre of pressure only reaches so far across the skis.
        const double error = rollTarget - roll;
        const double stoppable = std::sqrt(2 * 0.3 * reach / I.x * std::abs(error));
        const double rollRate = Sign(error) * std::min({s.maxRollRate, s.balanceGain * std::abs(error), stoppable});
        const double rollTorque = Clamp(I.x * s.balanceDamping * (rollRate - Dot(w, ft)), -reach, reach);
        torque = torque + ft * rollTorque;
        const double angulationTarget = Clamp(edgeTarget - roll, -Radians(s.maxAngulationDeg), Radians(s.maxAngulationDeg));
        st.angulation = Approach(st.angulation, angulationTarget, s.angulationRate * dt);

        // Yaw: unwind the coil at the pop, pivot slow turns, or swing across the fall line to brake.
        const double yawRate = Dot(w, n);
        const double edgeFrac = SmoothStep(0, Radians(s.edgeFullDeg), std::abs(st.edge));
        double yawTarget = yawRate, yawLimit = 0;
        if (st.popWindow > 0 && st.coil != 0) {
            yawTarget = st.coil * s.spinRate;
            yawLimit = s.edgeGrip * st.groundForce * 0.45;
        } else if (input.brake && speed2 > 1) {
            const Vec3 velocity = Normalize(ft * vf + lt * vl);
            const Vec3 across = Cross(n, velocity);
            const Vec3 side = Dot(ft, across) >= 0 ? across : across * -1;
            yawTarget = Clamp(6 * AngleAbout(ft, side, n), -5, 5);
            yawLimit = s.flatGrip * st.groundForce * 0.6;
        } else {
            const double slow = 1 - SmoothStep(2, 6, std::sqrt(speed2));
            yawTarget = Lerp(yawRate, -steer * s.pivotRate, slow * (1 - edgeFrac * 0.8));
            yawLimit = s.flatGrip * st.groundForce * 0.4;
        }
        torque = torque + n * Clamp(I.z * 30 * (yawTarget - yawRate), -yawLimit, yawLimit);

        st.coil = input.spin != 0 && st.popWindow == 0 ? Approach(st.coil, Clamp(input.spin, -1, 1), s.coilRate * dt)
            : st.popWindow > 0 ? st.coil : Approach(st.coil, 0, 2 * dt);
    } else if (riding) {
        // Air: no external torque except the optional assists.
        const Vec3 below = terrain.Normal(st.p.x, st.p.y);
        const Vec3 axis = Cross(zB, below);
        const Vec3 level = axis * 25 + (w - zB * Dot(w, zB)) * -6;
        torque = torque + level * (s.airAssist * I.x);
        torque = torque + zB * (s.spinAssist * I.z * 10 * Clamp(input.spin, -1, 1));
        st.angulation = Approach(st.angulation, 0, s.angulationRate * dt);
    } else {
        st.angulation = Approach(st.angulation, 0, s.angulationRate * dt);
    }

    const SnowContact contact = Contacts(st, terrain, s, w);
    const BodyContact body = BodyContacts(st, terrain, s, w);
    const Vec3 drag = st.v * (-0.5 * s.airDensity * Lerp(s.dragStand, s.dragTuck, std::max(st.tuck, crouch > 0.5 ? 0.6 : 0.0)) * Length(st.v));
    const Vec3 force = contact.force + body.force + drag + Vec3{0, 0, -m * g};
    torque = torque + contact.torque + body.torque;

    st.v = st.v + force * (dt / m);
    st.p = st.p + st.v * dt;
    st.L = st.L + torque * dt;
    w = AngularVelocity(st, s);
    const double angle = Length(w) * dt;
    if (angle > 1e-12) {
        const Vec3 axis = w * (1 / Length(w));
        const double half = std::sin(angle / 2);
        st.q = NormalizeQ(Multiply({std::cos(angle / 2), axis.x * half, axis.y * half, axis.z * half}, st.q));
    }

    st.groundForce = contact.total;
    st.contactForce = contact.force;
    st.normal = contact.normal;
    st.edge = contact.edge;
    st.slip = contact.slip;
    st.unloaded = contact.total > 0.05 * m * g ? 0 : st.unloaded + dt;
    const bool wasGrounded = st.grounded;
    st.grounded = st.unloaded < 0.08;
    st.time += dt;

    if (riding && body.hit) Crash(st, "body hit the snow");
    if (riding && st.grounded && std::abs(AngleAbout(st.normal, zB, ft)) > Radians(78)) Crash(st, "fell over");
    if (!riding) st.crashTime += dt;
    Track(st, wasGrounded, input, s, w);
}

void Advance(State& st, const Input& input, const Terrain& terrain, double seconds, const Settings& s) {
    const int steps = std::max(1, int(std::floor(seconds / s.dt + 0.5)));
    for (int i = 0; i < steps; i++) Step(st, input, terrain, s);
}

Report Summarize(const State& st, const Settings& s) {
    const Vec3 fB = Rotate(st.q, {1, 0, 0});
    const Vec3 ft = Normalize(fB - st.normal * Dot(fB, st.normal));
    Report r;
    r.speed = Length(st.v);
    r.edgeDeg = st.edge * 180 / Pi;
    r.rollDeg = AngleAbout(st.normal, Rotate(st.q, {0, 0, 1}), ft) * 180 / Pi;
    r.yawRate = Dot(AngularVelocity(st, s), st.normal);
    r.grounded = st.grounded;
    r.mode = st.mode;
    return r;
}

}  // namespace atelier::ski
