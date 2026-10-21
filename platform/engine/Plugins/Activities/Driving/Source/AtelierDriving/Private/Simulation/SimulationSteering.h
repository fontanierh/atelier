#pragma once

#include "SimulationSpec.h"

#include <array>

namespace atelier::driving
{
inline constexpr float ABSOLUTE_MAX_STEERING = 45.0f;
inline constexpr float MAX_SPEED_AXIS = 160.0f;
inline constexpr float RANGE_PAD[10] = {40.0f, 20.0f, 10.0f, 5.5f, 4.5f, 3.25f, 2.9f, 2.9f, 2.9f, 2.9f};
inline constexpr float RANGE_WHEEL[10] = {45.0f, 15.0f, 11.0f, 8.0f, 7.0f, 7.0f, 7.0f, 7.0f, 7.0f, 7.0f};
inline constexpr float STEER_SPEED[10] = {1.0f, 1.0f, 1.0f, 0.56f, 0.5f, 0.35f, 0.3f, 0.3f, 0.3f, 0.3f};
inline constexpr float RANGE_COEF[6] = {1.0f, 1.05f, 1.1f, 1.2f, 1.3f, 1.4f};
inline constexpr float INPUT_SPEED_COEF[6] = {1.0f, 1.05f, 1.1f, 1.5f, 2.2f, 3.1f};
inline constexpr float INPUT_COEF[6] = {1.0f, 1.05f, 1.1f, 1.2f, 1.3f, 1.4f};
inline constexpr float COLLISION_BLEND[4][2] = {{0.0f, 0.2f}, {0.2f, 0.5f}, {0.5f, 0.7f}, {0.7f, 1.0f}};

inline std::array<float, 21> input_remap()
{
    constexpr float half[11] = {-1.0f, -0.736f, -0.542f, -0.4f, -0.292f, -0.214f,
                                -0.16f, -0.123f, -0.078f, -0.036f, 0.0f};
    std::array<float, 21> t{};
    for (int i = 0; i < 11; ++i)
    {
        t[i] = half[i];
        t[20 - i] = -half[i];
    }
    return t;
}

template <int N>
struct Window
{
    float samples[N]{};
    int next = 0;
    int len = 0;
    void push(float v)
    {
        samples[next] = v;
        next = (next + 1) % N;
        len = std::min(len + 1, N);
    }
    float mean() const
    {
        if (len == 0)
        {
            return 0.0f;
        }
        float sum = 0.0f;
        for (int i = 0; i < len; ++i)
        {
            sum += samples[i];
        }
        return sum / static_cast<float>(len);
    }
};

inline WheelAngles ackermann(float target_deg, float wheel_base, float track_width)
{
    const float turns = target_deg / 360.0f;
    float inside = std::fabs(turns) * SIM_TAU;
    if (inside > SIM_PI)
    {
        inside -= SIM_TAU;
    }
    const float denom = track_width * inside + wheel_base;
    const float outside = std::fabs(denom) > 1e-6f ? wheel_base * inside / denom : inside;
    if (turns >= 0.0f)
    {
        return {outside, inside};
    }
    return {-inside, -outside};
}

struct SteeringInput
{
    float dt = 0.0f;
    float steer = 0.0f;
    float gas = 0.0f;
    float brake = 0.0f;
    float ebrake = 0.0f;
    float forward_speed = 0.0f;
    float tire_steering = 1.0f;
    float tuning = 0.0f;
    SteeringDevice device = SteeringDevice::Pad;
    float rear_slip_deg[2] = {0.0f, 0.0f};
};

struct Steering
{
    float prev_angle = 0.0f;
    float last_max = 0.0f;
    float last_input = 0.0f;
    Window<33> avg_input;
    Window<9> input_speed;
    float collision_timer = 0.0f;

    float angle() const { return prev_angle; }
    float average_input() const { return avg_input.mean(); }
    void notify_collision(float impulse)
    {
        if (impulse > 10.0f)
        {
            collision_timer = std::fmax(collision_timer, ramp(impulse, 10.0f, 40.0f));
        }
    }
    void reset() { *this = Steering{}; }
    float update(const SteeringInput& i);
};
} // namespace atelier::driving
