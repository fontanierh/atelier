// Ski simulation: one rigid skier (rider and skis together) on a heightfield. Metres, seconds, kilograms; z up.
// Body axes: x forward along the skis, y left, z up. No Unreal types: the plugin's adapter maps this frame onto the
// world (README.md) and the standalone test compiles it with a plain C++ compiler. It is the port of the browser lab's
// sim.js (platform/web/ski-lab) and keeps its arithmetic step for step.
#pragma once

#include <string>
#include <vector>

namespace atelier::ski {

struct Vec3 {
    double x = 0, y = 0, z = 0;
};

inline Vec3 operator+(Vec3 a, Vec3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
inline Vec3 operator-(Vec3 a, Vec3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
inline Vec3 operator*(Vec3 a, double s) { return {a.x * s, a.y * s, a.z * s}; }
double Dot(Vec3 a, Vec3 b);
Vec3 Cross(Vec3 a, Vec3 b);
double Length(Vec3 a);
Vec3 Normalize(Vec3 a);

// Rotation as (w, x, y, z).
struct Quat {
    double w = 1, x = 0, y = 0, z = 0;
};

Vec3 Rotate(Quat q, Vec3 v);
Quat Multiply(Quat a, Quat b);
Quat Conjugate(Quat q);
// Rotation whose columns are the body axes in world space.
Quat FromBasis(Vec3 forward, Vec3 left, Vec3 up);

struct Settings {
    double dt = 1.0 / 600;
    double gravity = 9.81;
    double mass = 75;
    // Skis
    double skiLength = 1.75;
    double sidecutRadius = 17;
    int contactPoints = 7;
    // Snow: totals over the contact points
    double snowStiffness = 150000;
    double snowDamping = 4700;
    double glideFriction = 0.05;
    double slipSpeed = 0.15;
    double flatGrip = 0.35;
    double edgeGrip = 1.1;
    double edgeFullDeg = 20;
    double carveOnsetDeg = 15;
    // Air
    double airDensity = 1.1;
    double dragStand = 0.55;
    double dragTuck = 0.25;
    // Body
    Vec3 inertiaStand = {12, 12.5, 1.9};
    Vec3 inertiaTuck = {4.5, 5, 1.3};
    double standHeight = 0.92;
    double crouchDrop = 0.38;
    double rideCrouch = 0.25;
    double legRate = 4.2;
    double flexRate = 1.6;
    double recoverRate = 0.8;
    double legAccel = 45;
    double legForceMax = 3.6;
    double absorbStart = 2.0;
    double absorbSoftness = 9;
    double footShift = 0.12;
    double hipRadius = 0.18;
    double headRadius = 0.12;
    double headHeight = 0.62;
    // Rider skill
    double maxEdgeDeg = 58;
    double maxAngulationDeg = 28;
    double angulationRate = 5;
    double balanceReach = 0.18;
    double balanceGain = 5;
    double balanceDamping = 16;
    double maxRollRate = 1.6;
    double edgeHold = 0.25;
    double pivotRate = 1.6;
    double spinRate = 8.5;
    double pivotGrip = 0.25;
    double coilRate = 3;
    double brakeLeanDeg = 32;
    // Assists, 0 is honest physics
    double balanceAssist = 0.85;
    double airAssist = 0.35;
    double spinAssist = 0.2;
};

enum class Grab : int { None = 0, Mute = 1, Safety = 2 };
constexpr int GrabCount = 3;
const char* GrabName(Grab grab);

struct Input {
    double steer = 0;   // -1 left .. 1 right
    double lean = 0;    // -1 back .. 1 forward
    bool crouch = false;
    double spin = 0;    // wind-up: -1 .. 1
    Grab grab = Grab::None;
    bool brake = false;
};

// The snow under a point: its height and upward unit normal, and how well it grips (1 = groomed).
struct Ground {
    double height = 0;
    Vec3 normal = {0, 0, 1};
    double grip = 1;
};

class Terrain {
public:
    virtual ~Terrain() = default;
    virtual double Height(double x, double y) const = 0;
    virtual Vec3 Normal(double x, double y) const = 0;
    virtual double Grip(double, double) const { return 1; }
};

enum class Mode { Ride, Crash };

enum class EventType { Takeoff, Land, Trick, Crash, Bail };

struct Event {
    Event(EventType inType = EventType::Takeoff, double inTime = 0) : type(inType), time(inTime) {}
    EventType type = EventType::Takeoff;
    double time = 0;
    std::string trick;  // land, trick, bail
    std::string why;    // crash
    int points = 0;     // trick
    double air = 0;     // land
    double upright = 0; // land: cosine of the body from the snow normal
};

struct Air {
    double time = 0, yaw = 0, flip = 0, startZ = 0, peak = 0;
    double grabs[GrabCount] = {0, 0, 0};
    bool switchStance = false;
};

struct Landing {
    std::string name;
    int points = 0;
    double at = 0, air = 0, height = 0;
    bool landedSwitch = false;
};

struct State {
    Vec3 p, v;
    Quat q;
    Vec3 L;  // angular momentum, world
    double h = 0, hRate = 0, footX = 0, footXRate = 0;
    double angulation = 0, edge = 0, tuck = 0, coil = 0;
    bool switchStance = false, pivoting = false, crouchHeld = false;
    double popWindow = 0;
    Mode mode = Mode::Ride;
    double crashTime = 0, time = 0;
    bool grounded = true;
    double groundForce = 0;
    Vec3 contactForce;
    Vec3 normal = {0, 0, 1};
    double slip = 0, unloaded = 0;
    bool inAir = false;
    Air air;
    bool hasLanding = false;
    Landing landing;
    int score = 0;
    std::vector<Event> events;
};

double Radians(double degrees);
// Carving curvature of an edged ski: 1 / (sidecut radius x cos(edge)), toward the edged side (negative = right).
double Curvature(double edge, const Settings& s);
// The edge angle that carves curvature `kappa` (absolute value), within the rider's maximum edge.
double EdgeFor(double kappa, const Settings& s);
Vec3 AngularVelocity(const State& st, const Settings& s);

State CreateSkier(const Terrain& terrain, double x, double y, double heading, double speed, const Settings& s);
// Steps the skier through `seconds` at the fixed step s.dt (at least one step).
void Advance(State& st, const Input& input, const Terrain& terrain, double seconds, const Settings& s);
// One fixed step.
void Step(State& st, const Input& input, const Terrain& terrain, const Settings& s);

struct Report {
    double speed = 0, edgeDeg = 0, rollDeg = 0, yawRate = 0;
    bool grounded = false;
    Mode mode = Mode::Ride;
};
Report Summarize(const State& st, const Settings& s);

// Where the body puts its feet: the boot under the pelvis, in body axes (for the pose and the skis).
Vec3 BootLocal(const State& st);

}  // namespace atelier::ski
