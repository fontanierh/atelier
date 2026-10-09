#pragma once
#include "NativeMath.h"
#include <optional>
#include <string>
namespace atelier::skate
{
struct ManualGains { float proportional, integral, derivative; };
struct ManualSettings
{
    PointGraph<8> noise_vs_speed;
    float torque_scale_without_contact, torque_bleed_without_contact, start_torque_scale;
    float procedural_noise_scale, procedural_noise_frequency;
    ManualGains powerslide, manual;
    float maximum_tilt_degrees, maximum_angle_error, derivative_limit, brake_tilt_degrees, animation_noise_scale;
};
struct ManualMode { float correction_angular_speed_threshold; bool corrective_force_enabled; };
enum class ManualEntryContinuation { Continue, RemoveVelocityIntoGround };
struct ManualState
{
    float filtered_angle_error = 0, target_angle = 0, measured_angle = 0, angular_correction = 0, elapsed = 0;
    void Reset();
    ManualEntryContinuation EnterGround(std::uint32_t previous_category, float powerslide_exit_scale);
};
struct ManualInput
{
    float balance, flipped_controls, procedural_noise_time, absolute_speed, animation_noise, timestep;
    bool powersliding, braking, positive_balance_contact, negative_balance_contact, reversed_point_selection;
    Vec4 reference_x, reference_z, deck_z, velocity_frame_z, angular_velocity_world;
    Vec4 correction_point_7888, correction_point_7952;
};
struct ManualEffect
{
    Vec4 angular_displacement{}, force_world{}, force_point_body{}, corrective_force_world{}, corrective_point_body{};
    bool correction_active = false, opposing_motion_without_correction = false;
};
struct ManualError
{
    enum class Kind { Angle, Measurement } kind = Kind::Angle;
    std::string measurement;
};
// The original mandatory physical measurement boundary. Failure retains any
// earlier controller writes but publishes no ManualEffect.
class ManualAngleMeasurement
{
public:
    virtual ~ManualAngleMeasurement() = default;
    virtual bool AngleBetween(Vec4 deck_z, Vec4 reference_z, Vec4 reference_x,
        float& output, std::string& error) = 0;
};
bool NormalizeManualAngle(float angle, float& output);
std::optional<ManualEffect> CalculateManual(ManualState&, const ManualSettings&, ManualMode,
    const ManualInput&, ManualAngleMeasurement&, ManualError&);
}
