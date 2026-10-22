#include "SimulationSteering.h"

namespace atelier::driving
{
float Steering::update(const SteeringInput& i)
{
    const float u = clamp(i.steer, -1.0f, 1.0f);
    if (i.device == SteeringDevice::Ai)
    {
        prev_angle = ABSOLUTE_MAX_STEERING * i.tire_steering * u;
        return prev_angle;
    }
    const float v = i.forward_speed;
    if (i.has_lock_curve)
    {
        // Kart-style absolute lock curve: tight at walking pace, calmer at speed, with a finite ramp in and a
        // faster return to centre. Cars without the curve keep the shared tables below unchanged.
        const float span = std::fmax(i.lock_speed_high - i.lock_speed_low, 1e-3f);
        const float t = clamp((v - i.lock_speed_low) / span, 0.0f, 1.0f);
        const float smooth = t * t * (3.0f - 2.0f * t);
        const float angle = i.lock_angle_low + (i.lock_angle_high - i.lock_angle_low) * smooth;
        const float target = clamp(u, -1.0f, 1.0f) * angle;
        const float rate_angle = std::fmax(std::fabs(angle), std::fmax(std::fabs(i.lock_angle_low),
                                                                      std::fabs(i.lock_angle_high)));
        const float rate = rate_angle / std::fmax(i.lock_ramp_time, 1e-3f);
        const bool centering = std::fabs(target) < std::fabs(prev_angle);
        const float step = rate * (centering ? std::fmax(i.lock_center_rate, 1.0f) : 1.0f) * i.dt;
        prev_angle = clamp(target, prev_angle - step, prev_angle + step);
        last_max = angle;
        last_input = u;
        avg_input.push(u);
        return prev_angle;
    }
    collision_timer = std::fmax(collision_timer - i.dt, 0.0f);
    const float avg = std::fabs(avg_input.mean());

    float range;
    switch (i.device)
    {
    case SteeringDevice::Pad:
        range = table(RANGE_PAD, 10, 0.0f, MAX_SPEED_AXIS, v);
        break;
    case SteeringDevice::WheelSpeedSensitive:
        range = table(RANGE_WHEEL, 10, 0.0f, MAX_SPEED_AXIS, v);
        break;
    default:
        range = ABSOLUTE_MAX_STEERING;
        break;
    }
    const float speed_coef = table(STEER_SPEED, 10, 0.0f, MAX_SPEED_AXIS, v);
    const float tb = 1.0f - (i.gas + 1.0f - (i.brake + i.ebrake) * 0.5f) * 0.5f;
    float max = range * (1.45f * tb * speed_coef + 1.0f);
    max *= table(RANGE_COEF, 6, 0.0f, 1.0f, avg);
    max *= 1.0f + 0.2f * i.tuning;

    if (collision_timer > 0.0f)
    {
        const float secs = 1.0f - collision_timer;
        const float speed_term = 1.0f - clamp(v / (mph_to_ms(170.0f) * 0.7f), 0.0f, 1.0f);
        const float blend = graph(COLLISION_BLEND, 4, secs);
        max *= speed_term * (1.0f - blend) + blend;
    }

    if (u > 0.0f && i.rear_slip_deg[1] > 0.0f)
    {
        max = std::fmin(std::fmax(max, i.rear_slip_deg[1]), ABSOLUTE_MAX_STEERING);
    }
    else if (u < 0.0f && i.rear_slip_deg[0] < 0.0f)
    {
        max = std::fmin(std::fmax(max, -i.rear_slip_deg[0]), ABSOLUTE_MAX_STEERING);
    }
    else if (avg >= 0.5f)
    {
        max = std::fmax(max, last_max);
    }
    max = std::fmin(max, ABSOLUTE_MAX_STEERING);
    if (i.device == SteeringDevice::WheelFixed)
    {
        max = ABSOLUTE_MAX_STEERING;
    }
    last_max = max;

    const float target = clamp(u * max * i.tire_steering, -ABSOLUTE_MAX_STEERING, ABSOLUTE_MAX_STEERING);
    if (i.device == SteeringDevice::Pad)
    {
        const float input_speed = std::fabs((u - last_input) / i.dt);
        this->input_speed.push(table(INPUT_SPEED_COEF, 6, 0.0f, 10.0f, input_speed));
        const float rate = 180.0f * i.tire_steering * speed_coef * this->input_speed.mean() *
                           table(INPUT_COEF, 6, 0.0f, 1.0f, avg);
        prev_angle = clamp(target, prev_angle - rate * i.dt, prev_angle + rate * i.dt);
    }
    else
    {
        prev_angle = target;
    }
    float recorded;
    if (i.device == SteeringDevice::Pad)
    {
        const std::array<float, 21> remap = input_remap();
        recorded = table(remap.data(), 21, -1.0f, 1.0f, u);
    }
    else
    {
        recorded = u;
    }
    last_input = recorded;
    avg_input.push(recorded);
    return prev_angle;
}
} // namespace atelier::driving
