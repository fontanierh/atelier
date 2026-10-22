#pragma once

#include "SimulationMath.h"
#include "SimulationTypes.h"

#include <utility>
#include <array>
#include <vector>

namespace atelier::driving
{
struct ObjectMaterial
{
    float friction[2] = {0.5f, 0.3f};
    Vec3 elasticity = VEC3_ONE;
    Vec3 inertia_scale = VEC3_ONE;
    float mass_scale = 1.0f;

    std::array<float, 2> friction_with(const ObjectMaterial& other) const
    {
        const float sf = std::sqrt(std::fmax(this->friction[0] * other.friction[0], 0.0f));
        const float k = std::sqrt(std::fmax(this->friction[1] * other.friction[1], 0.0f));
        return {sf, std::fmin(k, sf)};
    }
    float restitution(Vec3 local_normal) const { return length(local_normal * elasticity); }
};

struct RigidBodySpec
{
    float gravity = -9.81f;
    Vec3 cg = VEC3_ZERO;
    Vec3 drag = VEC3_ZERO;
    Vec3 drag_angular = VEC3_ZERO;
    float sleep_velocity = 0.1f;
    Vec3 collision_box_pad = VEC3_ZERO;
    /** Raise the bottom collision corners off terrain facets (metres, 0 keeps every existing car unchanged). */
    float collision_bottom_raise = 0.0f;
    float ground_friction[2] = {0.8f, 0.6f};
    Vec3 ground_elasticity = Vec3::splat(0.2f);
    Vec3 ground_moment_scale = VEC3_ONE;
    bool no_ground_collisions = false;
    ObjectMaterial objects;
};

struct ChassisSpec
{
    float spring_stiffness[2] = {0.0f, 0.0f};
    float spring_progression[2] = {0.0f, 0.0f};
    float shock_stiffness[2] = {0.0f, 0.0f};
    float shock_ext_stiffness[2] = {0.0f, 0.0f};
    float shock_valving[2] = {0.0f, 0.0f};
    float shock_digression[2] = {0.0f, 0.0f};
    float shock_blowout = 0.0f;
    float swaybar_stiffness[2] = {0.0f, 0.0f};
    float travel[2] = {0.0f, 0.0f};
    float ride_height[2] = {0.0f, 0.0f};
    float track_width[2] = {0.0f, 0.0f};
    float wheel_base = 0.0f;
    float front_axle = 0.0f;
    float front_weight_bias = 0.0f;
    float roll_center = 0.0f;
};

struct AxleConstants
{
    float spring = 0.0f;
    float shock = 0.0f;
    float shock_ext = 0.0f;
    float sway = 0.0f;
    float travel = 0.0f;
    float ride = 0.0f;
    float progression = 0.0f;
    float valving = 0.0f;
    float digression = 0.0f;
};

inline AxleConstants chassis_axle(const ChassisSpec& c, int axle, float ride_extra)
{
    return {
        c.spring_stiffness[axle] * LB_IN_TO_N_M,
        c.shock_stiffness[axle] * LB_IN_TO_N_M,
        c.shock_ext_stiffness[axle] * LB_IN_TO_N_M,
        c.swaybar_stiffness[axle] * LB_IN_TO_N_M,
        inch_to_m(c.travel[axle]),
        inch_to_m(c.ride_height[axle] + ride_extra),
        c.spring_progression[axle],
        inch_to_m(c.shock_valving[axle]),
        1.0f - c.shock_digression[axle],
    };
}

struct TireSpec
{
    float rim_size[2] = {0.0f, 0.0f};
    float section_width[2] = {0.0f, 0.0f};
    float aspect_ratio[2] = {0.0f, 0.0f};
    float grip_scale[2] = {1.0f, 1.0f};
    float static_grip[2] = {1.0f, 1.0f};
    float dynamic_grip[2] = {1.0f, 1.0f};
    float steering = 1.0f;
    /** Optional absolute lock curve. Disabled by default; cars keep the shared steering tables. */
    bool has_lock_curve = false;
    float lock_angle_low = 0.0f;      // degrees at or below lock_speed_low
    float lock_angle_high = 0.0f;     // degrees at or above lock_speed_high
    float lock_speed_low = 0.0f;      // m/s
    float lock_speed_high = 0.0f;     // m/s
    float lock_ramp_time = 0.0f;      // seconds from centre to full lock
    float lock_center_rate = 1.5f;    // centring is this much faster than turning in
    std::vector<float> yaw_control;
    float yaw_speed = 1.0f;

    float wheel_diameter(int axle) const
    {
        return inch_to_m(rim_size[axle]) +
               2.0f * section_width[axle] * 0.001f * aspect_ratio[axle] * 0.01f;
    }
    float radius(int axle) const { return std::fmax(wheel_diameter(axle) * 0.5f, 0.1f); }
    float average_radius() const { return 0.5f * (radius(0) + radius(1)); }
};

struct BrakeSpec
{
    float brakes[2] = {0.0f, 0.0f};
    float brake_lock[2] = {0.0f, 0.0f};
    float ebrake = 0.0f;
};

struct EngineSpec
{
    std::vector<float> torque;
    float idle = 0.0f;
    float red_line = 0.0f;
    float max_rpm = 0.0f;
    float flywheel_mass = 0.0f;
    std::vector<float> engine_braking;
    float speed_limiter[2] = {0.0f, 0.0f};
    bool no_rev_limiter = false;
};

struct TransmissionSpec
{
    std::vector<float> gear_ratio;
    std::vector<float> gear_efficiency;
    float final_gear = 0.0f;
    float torque_split = 0.0f;
    float differential[3] = {0.0f, 0.0f, 0.0f};
    /** A locked axle gives all of its torque to the grounded wheel(s); false keeps the open differential. */
    bool solid_axle[2] = {false, false};
    float torque_converter = 0.0f;
    float clutch_slip = 0.0f;
    float shift_speed = 0.0f;
    float optimal_shift = 0.0f;
};

struct InductionSpec
{
    float low_boost = 0.0f;
    float high_boost = 0.0f;
    float spool = 0.0f;
    float spool_time_up = 0.0f;
    float spool_time_down = 0.0f;
    float vacuum = 0.0f;
    float psi = 0.0f;
    InductionKind kind() const
    {
        if (high_boost > 0.0f || low_boost > 0.0f)
        {
            return spool > 0.0f ? InductionKind::Turbo : InductionKind::Supercharger;
        }
        return InductionKind::None;
    }
    float full_boost(float rpm, float idle, float red_line) const;
    bool operator==(const InductionSpec& o) const
    {
        return low_boost == o.low_boost && high_boost == o.high_boost && spool == o.spool &&
               spool_time_up == o.spool_time_up && spool_time_down == o.spool_time_down &&
               vacuum == o.vacuum && psi == o.psi;
    }
};

struct NosSpec
{
    float nos_capacity = 0.0f;
    float torque_boost = 0.0f;
    float nos_disengage = 0.0f;
    float recharge_min = 0.0f;
    float recharge_max = 0.0f;
    float recharge_min_speed = 0.0f;
    float recharge_max_speed = 0.0f;
    bool present() const { return nos_capacity > 0.0f && torque_boost > 0.0f; }
    bool operator==(const NosSpec& o) const
    {
        return nos_capacity == o.nos_capacity && torque_boost == o.torque_boost &&
               nos_disengage == o.nos_disengage && recharge_min == o.recharge_min &&
               recharge_max == o.recharge_max && recharge_min_speed == o.recharge_min_speed &&
               recharge_max_speed == o.recharge_max_speed;
    }
};

struct AeroSpec
{
    float drag_coefficient = 0.0f;
    float aero_coefficient = 0.0f;
    float aero_cg = 0.0f;
    float airborne_scale = 0.1f;
};

struct VehicleSpec
{
    float mass = 0.0f;
    Vec3 dimension = VEC3_ZERO;
    Vec3 tensor_scale = VEC3_ONE;
    RigidBodySpec body;
    ChassisSpec chassis;
    TireSpec tires;
    BrakeSpec brakes;
    EngineSpec engine;
    TransmissionSpec transmission;
    InductionSpec induction;
    NosSpec nos;
    AeroSpec aero;
    /** True only for the kart: the drift state waits for the handbrake, and a low-speed stabilizer runs. */
    bool drift_requires_request = false;
    float drift_assist_min_speed = 13.4112f;   // 30 mph
    float drift_assist_min_slip = 0.2094395f;  // 12 degrees
    bool stability_assist = false;
    float stability_gain = 1.0f;
    /** Feed the last wheel-contact plane into the jump/alignment assist (off keeps existing cars unchanged). */
    bool wheel_ground_reference = false;
};

struct Tunings
{
    float steering = 0.0f;
    float handling = 0.0f;
    float brakes = 0.0f;
    float ride_height = 0.0f;
    float aerodynamics = 0.0f;
    float nos = 0.0f;
    float induction = 0.0f;
};

struct ControlConfig
{
    float dead_zone = 0.05f;
    bool auto_reverse = true;
    bool auto_brake = true;
    bool automatic = true;
    SteeringDevice steering_device = SteeringDevice::Pad;
    bool manual_clutch = false;
    bool h_shifter = false;
};

struct InputState
{
    float throttle = 0.0f;
    float brake = 0.0f;
    float steer = 0.0f;
    float handbrake = 0.0f;
    bool nos = false;
    bool shift_up = false;
    bool shift_down = false;
    bool has_gear_select = false;
    int gear_select = 0;
    float clutch = 0.0f;
};

struct WheelAngles
{
    float left = 0.0f;
    float right = 0.0f;
    bool operator==(const WheelAngles& o) const { return left == o.left && right == o.right; }
};

struct WheelState
{
    Vec3 position = VEC3_ZERO;
    float radius = 0.0f;
    float steer_angle = 0.0f;
    float angular_velocity = 0.0f;
    float simulated_angular_velocity = 0.0f;
    float compression = 0.0f;
    bool on_ground = false;
    float load = 0.0f;
    float slip = 0.0f;
    float lateral_speed = 0.0f;
    float slip_angle = 0.0f;
    float traction = 0.0f;
    bool locked = false;
    float lateral_force = 0.0f;
    float longitudinal_force = 0.0f;
    float slide_speed = 0.0f;
    float skid = 0.0f;
    float smoke = 0.0f;
};

struct GroundReference
{
    Vec3 normal = VEC3_Y;
    float separation = 0.0f;
    bool operator==(const GroundReference& o) const
    {
        return normal == o.normal && separation == o.separation;
    }
};

struct LandingConfig
{
    float acceleration = 0.0f;
    float minimum_time = 0.0f;
    float minimum_peak_altitude = 0.0f;
    float maximum_altitude = 0.0f;
    float minimum_alignment = 0.0f;
    float maximum_speed = 0.0f;
};

struct PassiveConfig
{
    float minimum_up = 0.0f;
    int maximum_grounded_wheels = 0;
    float maximum_speed = 0.0f;
    std::vector<std::pair<float, float>> damping;
};

struct AlignmentConfig
{
    float minimum_ground_up = 0.0f;
    float minimum_body_up = 0.0f;
    float minimum_alignment = 0.0f;
    float minimum_altitude = 0.0f;
    float maximum_altitude = 0.0f;
    float maximum_speed = 0.0f;
    float correction_threshold = 0.0f;
    float pitch = 0.0f;
    float roll = 0.0f;
};

struct JumpConfig
{
    float extra_airborne_acceleration = 0.0f;
    LandingConfig landing;
    PassiveConfig passive;
    AlignmentConfig alignment;
};

struct ManeuverAssist
{
    float extra_downward_acceleration = 0.0f;
    bool has_tire_steering_drag = false;
    float tire_steering_drag = 0.0f;
    bool has_collision_mass_scale = false;
    float collision_mass_scale = 0.0f;
    float drag_scale = 1.0f;
    float front_grip_gain = 0.0f;
    bool has_steering_degrees = false;
    float steering_degrees = 0.0f;
};

struct WallSteeringConfig
{
    float maximum_normal_y = 0.0f;
    float maximum_closing_speed_squared = 0.0f;
    float maximum_nose_speed_squared = 0.0f;
    float end_fraction = 0.0f;
    float side_epsilon = 0.0f;
    float yaw_gain = 0.0f;
};

// Unit factors used by the data layer are in SimulationMath.h.

inline float InductionSpec::full_boost(float rpm, float idle, float red_line) const
{
    if (kind() == InductionKind::None)
    {
        return 0.0f;
    }
    const float spool_rpm = spool * (red_line - idle) + idle;
    if (rpm >= spool_rpm)
    {
        const float r = ramp(rpm, spool_rpm, red_line);
        return r * high_boost + (1.0f - r) * low_boost;
    }
    if (vacuum < 0.0f)
    {
        return ramp(rpm, idle, spool_rpm) * vacuum;
    }
    return 0.0f;
}

} // namespace atelier::driving
