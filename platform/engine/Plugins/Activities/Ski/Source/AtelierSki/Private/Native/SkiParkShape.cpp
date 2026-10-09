#include "SkiParkShape.h"

#include <algorithm>
#include <cmath>

namespace atelier::ski {

namespace {

constexpr double Gravity = 9.81;
constexpr double SampleStep = 0.05;

double SmoothStep(double a, double b, double x) {
    const double t = std::min(1.0, std::max(0.0, (x - a) / (b - a)));
    return t * t * (3 - 2 * t);
}

double SoftPlus(double x, double width) { return x / width > 30 ? x : width * std::log1p(std::exp(x / width)); }

}  // namespace

ParkSpec DefaultPark() {
    ParkSpec park;
    park.jumps = {
        {"Small", 60, 0, 0.9, 22, 28, 7, 11, 8},
        {"Medium", 150, 0, 1.4, 25, 31, 9, 13, 9},
        {"Large", 260, 0, 1.9, 28, 34, 11, 15, 10},
    };
    return park;
}

double Touchdown(const JumpProfile& profile, double speed) {
    const double table = profile.tableEnd - profile.lipU, tl = std::tan(profile.landingRad);
    const double b = speed * (std::sin(profile.lipRad) + tl * std::cos(profile.lipRad));
    // Over the table (level with the lip) or onto the landing line, whichever it meets first.
    const double overTable = profile.lipU + speed * std::cos(profile.lipRad) * 2 * speed * std::sin(profile.lipRad) / Gravity;
    if (overTable <= profile.tableEnd) return overTable;
    const double t = (b + std::sqrt(b * b - 2 * Gravity * tl * table)) / Gravity;
    return profile.lipU + speed * std::cos(profile.lipRad) * t;
}

double JumpProfile::StepAt(double u) const { return step * SmoothStep(tableEnd, length, u); }

double JumpProfile::Sampled(double u) const {
    if (u <= 0 || u >= length - 0.1) return 0;
    const double i = u / SampleStep;
    const size_t j = size_t(std::floor(i));
    return samples[j] + (samples[j + 1] - samples[j]) * (i - double(j));
}

JumpProfile MakeJumpProfile(const JumpSpec& jump, double slopeDeg) {
    const double tb = std::tan(Radians(slopeDeg));
    JumpProfile p;
    p.lipRad = Radians(jump.lipDeg);
    p.landingRad = Radians(jump.landingDeg);
    p.lipU = 2 * jump.height / (std::tan(p.lipRad) + tb);
    p.tableEnd = p.lipU + std::max(2.0, jump.slowSpeed * jump.slowSpeed * std::sin(2 * p.lipRad) / Gravity);
    p.knuckle = jump.height + (p.tableEnd - p.lipU) * tb;
    const double drop = std::tan(p.landingRad) - tb;
    p.landingEnd = Touchdown(p, jump.fastSpeed) + 4;
    p.bottom = p.knuckle - (p.landingEnd - p.tableEnd) * drop;
    const double runout = 12;
    p.length = p.landingEnd + runout;
    const double knuckleRound = 1.2;
    const auto table = [&](double u) { return jump.height + (u - p.lipU) * tb; };
    const auto landing = [&](double u) { return p.knuckle - (u - p.tableEnd) * drop; };
    const auto at = [&](double u) {
        if (u <= 0 || u >= p.length) return 0.0;
        if (u <= p.lipU) return jump.height * (u / p.lipU) * (u / p.lipU);
        if (std::abs(u - p.tableEnd) < knuckleRound) {
            // Quadratic Bezier over the knuckle's corner; evenly spaced control points keep t linear in u.
            const double t = (u - (p.tableEnd - knuckleRound)) / (2 * knuckleRound);
            return (1 - t) * (1 - t) * table(p.tableEnd - knuckleRound) + 2 * (1 - t) * t * p.knuckle
                + t * t * landing(p.tableEnd + knuckleRound);
        }
        if (u <= p.tableEnd) return table(u);
        if (u <= p.landingEnd) return landing(u);
        // Run-out: the slope eases steadily from the landing's back to the base slope.
        const double d = u - p.landingEnd;
        return p.bottom - drop * d + drop * d * d / (2 * runout);
    };
    // The step the hill takes around the landing, at every y; the profile is drawn relative to it.
    p.step = std::min(0.0, p.bottom - drop * runout / 2);
    p.samples.resize(size_t(std::ceil(p.length / SampleStep)) + 2);
    for (size_t i = 0; i < p.samples.size(); i++) p.samples[i] = at(double(i) * SampleStep) - p.StepAt(double(i) * SampleStep);
    return p;
}

Park::Park(ParkSpec inSpec) : spec(std::move(inSpec)) {
    for (const JumpSpec& jump : spec.jumps) profiles.push_back(MakeJumpProfile(jump, spec.slopeDeg));
}

double Park::Base(double x) const {
    const double tb = std::tan(Radians(spec.slopeDeg));
    double z = -tb * (SoftPlus(x, 8) - SoftPlus(x - spec.finishX, 10));
    for (size_t i = 0; i < profiles.size(); i++)
        z += profiles[i].StepAt(std::min(x - spec.jumps[i].x, profiles[i].length));
    return z;
}

double Park::Height(double x, double y) const {
    double z = Base(x);
    for (size_t i = 0; i < profiles.size(); i++) {
        const JumpSpec& jump = spec.jumps[i];
        const double across = 1 - SmoothStep(jump.width / 2, jump.width / 2 + 3, std::abs(y - jump.y));
        if (across > 0) z += across * profiles[i].Sampled(x - jump.x);
    }
    const RollerSpec& r = spec.rollers;
    const double lane = 1 - SmoothStep(r.width / 2, r.width / 2 + 2, std::abs(y - r.y));
    if (lane > 0 && x > r.from && x < r.to)
        z += lane * r.height * 0.5 * (1 - std::cos(2 * 3.14159265358979323846 * (x - r.from) / r.spacing));
    // Banks at the edges keep riders in the park.
    const double edge = std::abs(y) - spec.halfWidth;
    if (edge > 0) z += 0.04 * edge * edge;
    if (x < spec.startX) z += 0.2 * (spec.startX - x) * (spec.startX - x);
    return z;
}

Vec3 Park::Normal(double x, double y) const {
    const double e = 0.03;
    const double dx = (Height(x + e, y) - Height(x - e, y)) / (2 * e);
    const double dy = (Height(x, y + e) - Height(x, y - e)) / (2 * e);
    const double l = std::sqrt(dx * dx + dy * dy + 1);
    return {-dx / l, -dy / l, 1 / l};
}

Slope::Slope(double slopeDeg) : t(std::tan(Radians(slopeDeg))), l(std::sqrt(t * t + 1)) {}
double Slope::Height(double x, double) const { return -t * x; }
Vec3 Slope::Normal(double, double) const { return {t / l, 0, 1 / l}; }

}  // namespace atelier::ski
