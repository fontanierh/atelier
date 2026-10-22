#include "SimulationVehicle.h"

#include <cmath>

namespace atelier::driving
{
namespace
{
constexpr float BURNOUT_GRIP[6][2] = {
    {0.0f, 1.0f}, {5.0f, 0.8f}, {9.0f, 0.9f}, {12.6f, 0.833f}, {17.1f, 0.72f}, {25.0f, 0.65f}};
constexpr float REAR_GRIP[10] = {1.1f, 0.95f, 0.87f, 0.77f, 0.67f, 0.6f, 0.51f, 0.43f, 0.37f, 0.34f};
constexpr float STABILIZER[7][2] = {
    {0.0f, 0.0f}, {15.0f, 0.1f}, {30.0f, 0.45f}, {45.0f, 0.85f}, {60.0f, 0.95f}, {89.0f, 1.15f}, {90.0f, 0.0f}};

std::pair<std::array<float, 2>, std::array<float, 2>> traction_control(float torque, float slip, float lateral,
                                                                     Vec3 velocity, float steer)
{
    const float delta_lat = lateral - velocity.x;
    if (delta_lat * steer <= 0.0f || torque * slip <= 0.0f)
    {
        return {{1.0f, 1.0f}, {1.0f, 1.0f}};
    }
    const float delta_fwd = slip - velocity.z;
    const float angle =
        std::fabs(steer * (std::atan2(delta_lat, std::fabs(delta_fwd)) * RAD_TO_DEG));
    const float limit = ramp(delta_fwd, 1.0f, 20.0f) * ramp(angle, 1.0f, 16.0f);
    std::array<float, 2> control{1.0f - limit * 0.5f, 1.0f - limit * 0.5f};
    std::array<float, 2> grip{1.0f, 1.0f};
    const int slipping_side = delta_lat > 0.0f ? 1 : 0;
    control[slipping_side] = 1.0f - limit;
    grip[1 - slipping_side] = 1.0f + limit;
    return {control, grip};
}
} // namespace

void Vehicle::begin_tires(float speed)
{
    StepScales scales = StepScales::make(speed, powertrain.gear_id() == GEAR_REVERSE);
    if (tire_integration_ == TireIntegration::Regularized)
    {
        scales.max_slip = StepScales::make(speed, false).max_slip;
    }
    for (auto& tire : tires)
    {
        tire.begin_frame(scales.max_slip, scales.grip_scale, scales.traction_scale);
        if (maneuver.has_tire_steering_drag)
        {
            tire.drag_reduction = maneuver.tire_steering_drag;
        }
    }
}

void Vehicle::tune_tires(float dt, float speed, Vec3 angular_velocity)
{
    const Controls c = controls_;
    if (c.handbrake >= 0.5f)
    {
        yaw_control = std::fmax(yaw_control - 20.0f * dt, 0.5f);
    }
    else
    {
        yaw_control = std::fmin(yaw_control + dt, 1.0f);
    }
    const float max_speed = std::fmax(powertrain.max_speed(), 1.0f);
    const float yaw_limit = table(spec.tires.yaw_control.data(), static_cast<int>(spec.tires.yaw_control.size()),
                                  0.0f, 1.0f, speed / max_speed);
    const float grade = std::fabs(body.rotation().z_axis.y);
    const float speed_factor = speed / 30.0f;
    const bool driven_front = front_driven(spec.transmission);
    const bool driven_rear = rear_driven(spec.transmission);
    BrakeContext brake_ctx;
    brake_ctx.brake = c.brake;
    brake_ctx.ebrake = c.handbrake;
    brake_ctx.gas = c.gas;
    brake_ctx.speed = forward_speed();
    brake_ctx.slip_angle = body_slip;
    brake_ctx.tuning = tunings.brakes;
    const float nos_boost = powertrain.nos.boost;
    const float h = tunings.handling;
    for (int i = 0; i < 4; ++i)
    {
        const bool driven = i < 2 ? driven_front : driven_rear;
        const bool blown = tire_damage.is_blown(i);
        const BrakeCommand cmd = wheel_command(brake_ctx, i, driven, blown);
        Tire& t = tires[i];
        t.lateral_boost = 1.0f;
        if (i < 2)
        {
            t.lateral_boost += maneuver.front_grip_gain * std::fabs(c.steering);
            t.traction_boost *= t.lateral_boost;
        }
        t.brake = cmd.brake;
        t.ebrake = cmd.ebrake;
        if (i >= 2)
        {
            float boost = 1.0f + grade;
            if (!(c.handbrake > 0.5f && std::fabs(body_slip) * RAD_TO_DEG < 20.0f))
            {
                boost += std::fmin(std::fabs(body_slip) * yaw_limit * speed_factor, 0.35f);
            }
            t.traction_boost *= yaw_control * (1.0f - drift_.value) * (boost - 1.0f) + 1.0f;
        }
        t.traction_boost *= nos_boost;
        if (blown)
        {
            t.traction_boost *= BLOWN_TRACTION;
        }
        t.traction_circle_lateral = 1.0f + 0.2f * h;
        t.traction_circle_longitudinal = 1.0f - 0.2f * h;
    }
    if (tire_integration_ == TireIntegration::Reference)
    {
        int wheel = 0;
        float slip = 0.0f;
        for (int i = 0; i < 4; ++i)
        {
            if (tires[i].slip > slip)
            {
                wheel = i;
                slip = tires[i].slip;
            }
        }
        burnout_.update(dt, powertrain.gear_id() == GEAR_FIRST && c.gas >= 1.0f, forward_speed(), body_slip, slip,
                        wheel);
    }
    update_drift(dt, speed, angular_velocity);
}

void Vehicle::update_drift(float dt, float speed, Vec3 angular_velocity)
{
    Drift& d = drift_;
    d.speed = speed;
    const float change = (d.phase == Drift::Phase::In || d.phase == Drift::Phase::Enter) ? 8.0f : -2.0f;
    d.value = clamp(d.value + change * dt, 0.0f, 1.0f);
    if (d.value <= 0.0f)
    {
        d.phase = Drift::Phase::Out;
    }
    if (d.value >= 1.0f)
    {
        d.phase = Drift::Phase::In;
    }
    const float slip = body_slip;
    const float yaw = dot(body.rotation().y_axis, angular_velocity);
    const Controls c = controls_;
    const float threshold = spec.drift_assist_min_slip;
    const bool fast = speed > spec.drift_assist_min_speed;
    const bool requested = c.handbrake > 0.5f;
    const bool may_drift = !spec.drift_requires_request || requested;
    if (spec.drift_requires_request && !requested)
    {
        d.phase = Drift::Phase::Out;
    }
    if (d.phase == Drift::Phase::In || d.phase == Drift::Phase::Exit)
    {
        const bool sustaining = may_drift && yaw * slip < 0.0f && std::fabs(slip) <= SIM_PI * 0.5f && fast &&
                                steering.average_input() * slip <= 0.0f && std::fabs(slip) > threshold;
        const bool sustaining_or_power = sustaining || (may_drift && c.gas * c.steering * slip > threshold && fast);
        const bool power = may_drift && c.gas * std::fabs(slip) > threshold;
        d.phase = sustaining_or_power ? Drift::Phase::In : (power ? Drift::Phase::Enter : Drift::Phase::Exit);
    }
    else if (fast && may_drift && (requested || std::fabs(slip) > threshold))
    {
        d.phase = Drift::Phase::Enter;
    }
    if (spec.stability_assist && fast && std::fabs(slip) > threshold && yaw * slip < 0.0f &&
        wheels_on_ground_prev_ >= 2)
    {
        // A kart keeps its rear under control from walking pace. This torque is independent of the drift state:
        // steering alone never lowers rear grip, but it does get the early stabilizer.
        const float gain = graph(STABILIZER, 7, std::fabs(slip) * RAD_TO_DEG);
        const float torque = -yaw * gain * 4.0f * body.inertia().y * spec.stability_gain;
        body.apply_torque(body.rotation().y_axis * torque);
    }
    if (d.value <= 0.0f)
    {
        return;
    }
    if (!spec.stability_assist && yaw * slip < 0.0f && wheels_on_ground_prev_ >= 2)
    {
        const float gain = graph(STABILIZER, 7, std::fabs(slip) * RAD_TO_DEG);
        const float torque = d.value * -yaw * gain * 4.0f * body.inertia().y;
        body.apply_torque(body.rotation().y_axis * torque);
    }
    const float counter = c.steering * slip > 0.0f ? std::fabs(c.steering) : 0.0f;
    const float coefficient = 0.5f * std::fabs(slip) + 4.0f * counter + 0.5f * std::fabs(yaw);
    const float grip = table(REAR_GRIP, 10, 0.0f, 1.0f, coefficient * d.value);
    for (int i = 2; i < 4; ++i)
    {
        tires[i].drift_friction = grip;
    }
}

void Vehicle::distribute_drive(float torque, const std::array<float, 4>& av, const std::array<bool, 4>& grounded)
{
    if (std::fabs(torque) <= 1.19209290e-7f)
    {
        return;
    }
    const TransmissionSpec& trans = spec.transmission;
    bool axle_traction[2] = {grounded[0] || grounded[1], grounded[2] || grounded[3]};
    float axle_omega[2] = {av[0] + av[1], av[2] + av[3]};
    const std::array<float, 2> share =
        calc_split(trans.torque_split, trans.differential[2], false, axle_traction, axle_omega);
    const Vec3 velocity = transpose(body.rotation()) * body.linear_velocity;
    for (int axle = 0; axle < 2; ++axle)
    {
        const float axle_torque = torque * share[axle];
        if (std::fabs(axle_torque) <= 1.19209290e-7f)
        {
            continue;
        }
        const int a = axle * 2;
        const Tire pair[2] = {tires[a], tires[a + 1]};
        const float slip = (pair[0].slip + pair[1].slip) * share[axle] * 0.5f;
        const float lateral = (pair[0].lateral_speed + pair[1].lateral_speed) * share[axle] * 0.5f;
        auto control_grip = traction_control(axle_torque, slip, lateral, velocity, controls_.steering);
        if (axle == 1)
        {
        }
        float bias = 0.5f;
        const bool locked = (burnout_.state & 3) != 0;
        switch (burnout_.state & 3)
        {
        case 1:
        case 3:
            control_grip.first = {1.0f, 1.0f};
            control_grip.second = {1.0f, burnout_.traction};
            bias = burnout_.traction * 0.5f;
            break;
        case 2:
            control_grip.first = {1.0f, 1.0f};
            control_grip.second = {burnout_.traction, 1.0f};
            bias = 1.0f - burnout_.traction * 0.5f;
            break;
        default:
            break;
        }
        bool wheel_traction[2] = {grounded[a], grounded[a + 1]};
        float wheel_omega[2] = {av[a], av[a + 1]};
        std::array<float, 2> split =
            calc_split(bias, trans.differential[axle], locked, wheel_traction, wheel_omega);
        if (trans.solid_axle[axle])
        {
            // A locked axle still turns both wheels together; when one is in the air the other takes the axle torque.
            const int loaded = (wheel_traction[0] ? 1 : 0) + (wheel_traction[1] ? 1 : 0);
            split = {loaded && wheel_traction[0] ? 1.0f / float(loaded) : 0.0f,
                     loaded && wheel_traction[1] ? 1.0f / float(loaded) : 0.0f};
        }
        for (int i = 0; i < 2; ++i)
        {
            if (!grounded[a + i])
            {
                continue;
            }
            tires[a + i].traction_boost *= control_grip.second[i];
            if (tire_integration_ == TireIntegration::Reference && tires[a + i].brake_locked)
            {
                continue;
            }
            tires[a + i].drive_torque = axle_torque * split[i] * control_grip.first[i];
        }
    }
}

void Burnout::update(float dt, bool active, float speed, float body_slip_value, float slip, int wheel)
{
    if (!active)
    {
        *this = Burnout{};
        return;
    }
    if (state > 0)
    {
        if (speed > mph_to_ms(5.0f) && std::fabs(body_slip_value) > 0.5f)
        {
            *this = Burnout{};
            return;
        }
        if (slip < 0.5f)
        {
            release_time += dt;
            if (release_time > 1.0f)
            {
                *this = Burnout{};
            }
            return;
        }
        release_time = 0.0f;
        time -= dt;
        if (time < 0.0f)
        {
            --state;
            time = 2.0f;
        }
        return;
    }
    if (speed >= mph_to_ms(20.0f) || slip <= 0.5f)
    {
        return;
    }
    const float grip = graph(BURNOUT_GRIP, 6, slip);
    traction = grip / 1.4f;
    state = static_cast<int>(6.0f * (1.5f - grip) + static_cast<float>(wheel & 1));
    time = 2.0f;
    release_time = 0.0f;
}
} // namespace atelier::driving
