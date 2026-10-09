// Standalone checks of the native ski simulation (no Unreal): the same claims as the browser lab's test_ski.mjs,
// plus `trace`, which prints a scripted run for the parity check against sim.js (test_ski_native.py).
#include <cmath>
#include <cstdio>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

#include "SkiParkShape.h"
#include "SkiSim.h"

using namespace atelier::ski;

namespace {

int failures = 0;

void Check(bool ok, const std::string& what) {
    if (!ok) {
        std::printf("FAIL %s\n", what.c_str());
        failures++;
    }
}

bool Crashed(const State& st) {
    for (const Event& e : st.events)
        if (e.type == EventType::Crash) return true;
    return false;
}

void Ride(State& st, const Terrain& terrain, double seconds, Input input = {}, const Settings& s = Settings{}) {
    Advance(st, input, terrain, seconds, s);
}

void StraightRun() {
    const Settings s;
    const Slope slope(15);
    State st = CreateSkier(slope, 0, 0, 0, 5, s);
    Ride(st, slope, 4);
    Check(st.mode == Mode::Ride, "straight: still riding");
    Check(Summarize(st, s).speed > 10, "straight: accelerates");
    Check(std::abs(st.groundForce / (s.mass * s.gravity) - std::cos(Radians(15))) < 0.05, "straight: load is the slope normal");
    Check(std::abs(st.p.y) < 0.05, "straight: runs straight");
}

void Carving() {
    const Settings s;
    const Slope flat(0.0001);
    for (double steer : {0.5, 1.0}) {
        State st = CreateSkier(flat, 0, 0, 0, 6, s);
        Input in;
        in.steer = steer;
        Ride(st, flat, 1.2, in);
        const Report r = Summarize(st, s);
        const double path = std::abs(r.yawRate) / r.speed;
        Check(std::abs(path / std::abs(Curvature(st.edge, s)) - 1) < 0.2, "carve: path follows the sidecut at steer " + std::to_string(steer));
        Check(r.yawRate < 0, "carve: turns right");
    }
}

void LeansIntoTurns() {
    const Settings s;
    const Slope flat(0.0001);
    for (double steer : {0.25, 0.5, 1.0, -1.0}) {
        State st = CreateSkier(flat, 0, 0, 0, 12, s);
        Input in;
        in.steer = steer;
        Ride(st, flat, 1.5, in);
        const double roll = Summarize(st, s).rollDeg;
        Check(!Crashed(st), "lean: stays up at steer " + std::to_string(steer));
        Check((roll > 0) == (steer > 0) && std::abs(roll) > 10, "lean: leans into the turn at steer " + std::to_string(steer));
    }
}

void ToppleWithoutAssist() {
    Settings s;
    s.balanceAssist = 0;
    const Slope flat(0.0001);
    State st = CreateSkier(flat, 0, 0, 0, 1, s);
    Input in;
    in.steer = 1;
    Advance(st, in, flat, 3, s);
    Check(Crashed(st), "topple: leaning hard at a standstill without assist falls over");
}

void HockeyStop() {
    const Settings s;
    const Slope flat(0.0001);
    State st = CreateSkier(flat, 0, 0, 0, 12, s);
    Input in;
    in.brake = true;
    Ride(st, flat, 4, in);
    Check(!Crashed(st), "stop: no crash");
    Check(Summarize(st, s).speed < 1, "stop: stops");
}

void Pop() {
    const Settings s;
    const Slope flat(0.0001);
    State st = CreateSkier(flat, 0, 0, 0, 8, s);
    Input crouch;
    crouch.crouch = true;
    Ride(st, flat, 0.6, crouch);
    double air = 0;
    for (int i = 0; i < 100; i++) {
        Ride(st, flat, 0.01);
        if (!st.grounded) air += 0.01;
    }
    Check(air > 0.3, "pop: airborne for " + std::to_string(air) + " s");
    Check(!Crashed(st), "pop: no crash");
}

void Spin() {
    Settings s;
    s.airAssist = 0;
    s.spinAssist = 0;
    const Slope flat(0.0001);
    State st = CreateSkier(flat, 0, 0, 0, 8, s);
    Input in;
    in.crouch = true;
    in.spin = 1;
    Advance(st, in, flat, 0.6, s);
    in.crouch = false;
    Advance(st, in, flat, 0.3, s);
    Check(!st.grounded, "spin: in the air");
    const double open = std::abs(AngularVelocity(st, s).z);
    Check(open > 2, "spin: spins at " + std::to_string(open) + " rad/s");
    const Vec3 momentum = st.L;
    Input grab;
    grab.grab = Grab::Mute;
    Advance(st, grab, flat, 0.15, s);
    Check(!st.grounded, "spin: still in the air");
    Check(std::abs(AngularVelocity(st, s).z) > open * 1.2, "spin: tucking spins faster");
    Check(Length(st.L - momentum) < 1e-9, "spin: no torque in the air");
}

void JumpWindows() {
    const Park park;
    for (size_t i = 0; i < park.Profiles().size(); i++) {
        const JumpProfile& p = park.Profiles()[i];
        const JumpSpec& jump = park.Spec().jumps[i];
        Check(Touchdown(p, jump.slowSpeed) >= p.tableEnd - 0.01, "jumps: slowest clears the knuckle of " + jump.name);
        Check(Touchdown(p, jump.fastSpeed) <= p.landingEnd - 3, "jumps: fastest lands on the landing of " + jump.name);
    }
}

void ParkRun() {
    const Settings s;
    const Park park;
    State st = CreateSkier(park, park.StartX(), park.StartY(), 0, 3, s);
    std::vector<double> landings;
    bool wasGrounded = true;
    while (st.p.x < park.Spec().finishX - 20 && st.time < 60) {
        Ride(st, park, 0.01);
        if (!wasGrounded && st.grounded && !st.events.empty() && st.events.back().type == EventType::Land)
            landings.push_back(st.p.x);
        wasGrounded = st.grounded;
    }
    Check(!Crashed(st), "park: no crash");
    Check(landings.size() == park.Spec().jumps.size(), "park: lands every jump");
    for (size_t i = 0; i < landings.size() && i < park.Profiles().size(); i++) {
        const double u = landings[i] - park.Spec().jumps[i].x;
        const JumpProfile& p = park.Profiles()[i];
        Check(u > p.tableEnd && u < p.landingEnd, park.Spec().jumps[i].name + " landed at " + std::to_string(u));
    }
}

// A scripted run through the park printed every 0.1 s: the parity check runs the same script through sim.js.
void Trace() {
    const Settings s;
    const Park park;
    State st = CreateSkier(park, park.StartX(), park.StartY(), 0, 3, s);
    for (int tick = 0; tick < 60; tick++) {
        const double t = tick * 0.1;
        Input in;
        in.steer = t < 2 ? 0.4 : t < 3 ? -0.6 : 0;
        in.lean = t < 1 ? 0.3 : 0;
        in.crouch = t >= 3.5 && t < 4.2;
        in.spin = t >= 3.5 && t < 4.3 ? 1 : 0;
        in.grab = t >= 4.5 && t < 5 ? Grab::Safety : Grab::None;
        Ride(st, park, 0.1, in);
        std::printf("%.1f %.9f %.9f %.9f %.9f %.9f %.9f %.9f %.9f %.9f %.9f %d\n", t + 0.1, st.p.x, st.p.y, st.p.z,
            st.v.x, st.v.y, st.v.z, st.q.w, st.q.x, st.q.y, st.q.z, st.grounded ? 1 : 0);
    }
}

}  // namespace

int main(int argc, char** argv) {
    if (argc > 1 && std::strcmp(argv[1], "trace") == 0) {
        Trace();
        return 0;
    }
    const std::vector<std::pair<const char*, std::function<void()>>> tests = {
        {"straight run", StraightRun}, {"carving", Carving}, {"leans into turns", LeansIntoTurns},
        {"topples without assist", ToppleWithoutAssist}, {"hockey stop", HockeyStop}, {"pop", Pop},
        {"spin", Spin}, {"jump windows", JumpWindows}, {"park run", ParkRun},
    };
    for (const auto& [name, test] : tests) {
        const int before = failures;
        test();
        std::printf("%s %s\n", failures == before ? "ok" : "FAILED", name);
    }
    return failures ? 1 : 0;
}
