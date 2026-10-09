// Ski park terrain: a heightfield park in the simulation's frame (x down the fall line, y to the left, z up, metres).
// Jumps are designed from the speeds they must work for: the table is long enough that the slowest rider clears the
// knuckle, and the landing long enough that the fastest still lands on it. Where the landing ends below the slope,
// the whole hill steps down there, as parks do: gentle decks between features, the drop taken on the landings.
// Port of the browser lab's terrain.js.
#pragma once

#include <string>
#include <vector>

#include "SkiSim.h"

namespace atelier::ski {

struct JumpSpec {
    std::string name;
    double x = 0, y = 0, height = 0, lipDeg = 0, landingDeg = 0;
    double slowSpeed = 0, fastSpeed = 0, width = 0;
};

struct RollerSpec {
    double y = -16, from = 40, to = 300, spacing = 14, height = 0.9, width = 7;
};

struct ParkSpec {
    double slopeDeg = 9;
    double startX = -30;
    double finishX = 380;
    double halfWidth = 32;
    std::vector<JumpSpec> jumps;
    RollerSpec rollers;
};

// The lab's park: Small, Medium and Large jumps down the middle, rollers to the right.
ParkSpec DefaultPark();

struct JumpProfile {
    double lipU = 0, tableEnd = 0, knuckle = 0, lipRad = 0, landingRad = 0;
    double length = 0, landingEnd = 0, bottom = 0, step = 0;
    std::vector<double> samples;  // offsets above the base plane every 5 cm along u, relative to the step
    double StepAt(double u) const;
    double Sampled(double u) const;
};

// Where a rider leaving the lip at `speed` comes down, as u along the profile (point mass, no drag).
double Touchdown(const JumpProfile& profile, double speed);
JumpProfile MakeJumpProfile(const JumpSpec& jump, double slopeDeg);

class Park final : public Terrain {
public:
    explicit Park(ParkSpec spec = DefaultPark());
    double Height(double x, double y) const override;
    Vec3 Normal(double x, double y) const override;
    double Base(double x) const;
    const ParkSpec& Spec() const { return spec; }
    const std::vector<JumpProfile>& Profiles() const { return profiles; }
    double StartX() const { return spec.startX + 18; }
    double StartY() const { return 0; }

private:
    ParkSpec spec;
    std::vector<JumpProfile> profiles;
};

// A plain slope for tests: constant angle along x, flat across.
class Slope final : public Terrain {
public:
    explicit Slope(double slopeDeg);
    double Height(double x, double y) const override;
    Vec3 Normal(double x, double y) const override;

private:
    double t, l;
};

}  // namespace atelier::ski
