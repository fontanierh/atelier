#include "Manual.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) { float value; std::memcpy(&value, &word, 4); return value; }
float SymmetricClamp(float value, float bound)
{
    const float lower = -bound, clamped = lower - value >= 0.0f ? lower : value;
    return bound - clamped >= 0.0f ? clamped : bound;
}
void ApplyCorrection(ManualEffect& effect, const ManualInput& input, ManualMode mode, float target, float measured)
{
    const auto frame = input.velocity_frame_z, velocity = input.angular_velocity_world;
    const float local_z = std::fma(frame[2], velocity[2], std::fma(frame[1], velocity[1], frame[0] * velocity[0]));
    if (!input.braking || !(0.0f > local_z * input.balance)) return;
    if (!mode.corrective_force_enabled) { effect.opposing_motion_without_correction = true; return; }
    if (!(std::abs(local_z) > mode.correction_angular_speed_threshold)) return;
    const float conversion = Float(0x42652ee1), error = target * conversion - measured * conversion;
    if (!(std::abs(error) < 1.0f)) return;
    const bool alternate = input.reversed_point_selection ? input.balance < 0.0f : input.balance > 0.0f;
    effect.corrective_point_body = alternate ? input.correction_point_7888 : input.correction_point_7952;
    for (std::size_t i = 0; i < 4; ++i) effect.corrective_force_world[i] = (velocity[i] * -1.0f) * 400.0f;
    effect.correction_active = true;
}
}
bool NormalizeManualAngle(float angle, float& output)
{
    const float pi = Float(0x40490fdb);
    if (angle >= -pi && angle < pi) { output = angle; return true; }
    const float turns = angle * Float(0x3e22f983);
    if (!std::isfinite(turns) || turns < -2147483648.0f || double(turns) > 2147483647.0) return false;
    const auto whole = std::int32_t(turns); const float tau = Float(0x40c90fdb);
    // Keep the rounded FMA and its negation separate: folding this into a
    // negated fused instruction changes the sign of an exact-zero result.
    const volatile float fused = std::fma(float(whole), tau, -angle);
    const float reduced = -fused;
    output = reduced >= pi ? reduced - tau : reduced < -pi ? reduced + tau : reduced;
    return true;
}
void ManualState::Reset()
{
    filtered_angle_error = 0; target_angle = 0; measured_angle = 0; elapsed = 0; angular_correction = 0;
}
ManualEntryContinuation ManualState::EnterGround(std::uint32_t previous_category, float scale)
{
    if (previous_category == 100)
    {
        angular_correction *= scale; filtered_angle_error *= scale; return ManualEntryContinuation::Continue;
    }
    filtered_angle_error = 0; target_angle = 0; measured_angle = 0; angular_correction = 0; elapsed = 0;
    return ManualEntryContinuation::RemoveVelocityIntoGround;
}
std::optional<ManualEffect> CalculateManual(ManualState& state, const ManualSettings& settings,
    ManualMode mode, const ManualInput& input, ManualAngleMeasurement& geometry, ManualError& error)
{
    error = {}; ManualEffect effect; float output_scale = 1.0f;
    const auto norm = [&](float value, float& out) {
        if (NormalizeManualAngle(value, out)) return true;
        error.kind = ManualError::Kind::Angle; return false;
    };
    if (input.balance == 0.0f) state.Reset();
    else
    {
        const auto gains = input.powersliding ? settings.powerslide : settings.manual;
        const float balance = input.balance * input.flipped_controls, sign = balance > 0.0f ? 1.0f : -1.0f;
        const float signed_target = std::fma(std::abs(balance), .75f, .25f) * sign;
        const float started = state.elapsed == 0.0f ? 0.0f : 1.0f, radians = Float(0x3c8efa35);
        float base, target;
        if (!norm((settings.maximum_tilt_degrees * signed_target) * radians, base)) return std::nullopt;
        if (input.braking)
        {
            if (!norm((settings.brake_tilt_degrees * signed_target) * radians, target)) return std::nullopt;
        }
        else
        {
            const float phase = (input.procedural_noise_time * settings.procedural_noise_frequency) * Float(0x40c90fdb);
            const float noise = Sin(phase) * settings.procedural_noise_scale;
            const float speed_scale = settings.noise_vs_speed.Evaluate(input.absolute_speed);
            const float animated = input.animation_noise * settings.animation_noise_scale;
            const float disturbance = std::fma(animated, input.flipped_controls, noise);
            float noise_angle;
            if (!norm(speed_scale * disturbance, noise_angle) || !norm(noise_angle + base, target)) return std::nullopt;
        }
        if (state.elapsed == 0.0f)
        {
            if (!norm(settings.start_torque_scale * target, state.angular_correction)) return std::nullopt;
        }
        state.target_angle = target; float measured;
        if (!geometry.AngleBetween(input.deck_z, input.reference_z, input.reference_x, measured, error.measurement))
        { error.kind = ManualError::Kind::Measurement; return std::nullopt; }
        if (!norm(measured, measured)) return std::nullopt;
        const float change = measured - state.measured_angle; state.measured_angle = measured;
        float angle_error;
        if (!norm(target - measured, angle_error)) return std::nullopt;
        angle_error = SymmetricClamp(angle_error, settings.maximum_angle_error);
        const float weighted = angle_error * Float(0x3d4ccccd);
        state.filtered_angle_error = std::fma(state.filtered_angle_error, Float(0x3f733333), weighted);
        const float derivative = SymmetricClamp((change * started) * gains.derivative, settings.derivative_limit);
        const float wheel_scale = input.positive_balance_contact != input.negative_balance_contact ? .5f : 1.0f;
        const bool wrong = (!input.positive_balance_contact && input.balance > 0.0f)
            || (!input.negative_balance_contact && input.balance < 0.0f);
        if (wrong)
        {
            state.angular_correction = (settings.torque_bleed_without_contact * state.angular_correction) * wheel_scale;
            output_scale = settings.torque_scale_without_contact * wheel_scale;
        }
        else state.angular_correction = ((state.angular_correction + derivative) + state.filtered_angle_error * gains.integral) + angle_error * gains.proportional;
        ApplyCorrection(effect, input, mode, target, measured); state.elapsed = input.timestep + state.elapsed;
    }
    const float correction = state.angular_correction * output_scale;
    for (std::size_t i = 0; i < 4; ++i) effect.angular_displacement[i] = (-input.reference_x[i]) * correction;
    return effect;
}
}
