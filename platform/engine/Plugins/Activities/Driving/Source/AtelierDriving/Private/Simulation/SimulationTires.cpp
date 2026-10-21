#include "SimulationTires.h"

#include <cmath>

namespace atelier::driving
{
namespace
{
constexpr float EPS = 1e-6f;
constexpr float SKID_FLOOR = 0.5f;
constexpr float ELLIPSE_RATIO = 1.5f;
constexpr float LOCK_RATIO = 1.2f;
constexpr float LOCK_AV_FACTOR = 100.0f;

constexpr float FAMILIES[7][6] = {
    {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {0.0f, 1.2f, 2.3f, 3.0f, 3.0f, 2.8f},
    {0.0f, 1.7f, 3.2f, 4.3f, 5.1f, 5.2f},
    {0.0f, 1.8f, 3.5f, 4.9f, 5.8f, 6.1f},
    {0.0f, 1.83f, 3.6f, 5.0f, 5.96f, 6.4f},
    {0.0f, 1.86f, 3.7f, 5.1f, 6.13f, 6.7f},
    {0.0f, 1.9f, 3.8f, 5.2f, 6.3f, 7.1f},
};

constexpr float TRACTION_TABLE[10] = {0.909f, 1.045f, 1.09f, 1.09f, 1.09f, 1.09f, 1.09f, 1.045f, 1.0f, 1.0f};
constexpr float GRIP_TABLE[10] = {0.833f, 0.958f, 1.008f, 1.0167f, 1.033f, 1.033f, 1.033f, 1.0167f, 1.0f, 1.0f};
} // namespace

inline float lateral_force(float load, float slip_angle, float grip_scale, float grip_boost)
{
    const float angle_deg = std::fabs(slip_angle) * 360.0f;
    const float seg = angle_deg * 0.5f;
    const float k = std::floor(seg);
    const float frac = seg - k;
    const float x = std::fmax(load, 0.0f) * 0.001f * 0.8f;
    const auto family = [&](int i) { return table(FAMILIES[i], 6, 0.0f, 10.0f, x); };
    const float value = k >= 6.0f ? family(6) : family(static_cast<int>(k)) +
                                                  frac * (family(static_cast<int>(k) + 1) - family(static_cast<int>(k)));
    return grip_scale * 1000.0f * grip_boost * 2.5f * value;
}

StepScales StepScales::make(float speed, bool reverse)
{
    const float r = ramp(speed, 0.0f, mph_to_ms(85.0f));
    StepScales out;
    out.max_slip = reverse ? 71.0f : 0.5f + ramp(speed, 10.0f, 71.0f);
    out.traction_scale = reverse ? 2.0f : table(TRACTION_TABLE, 10, 0.0f, 1.0f, r) * 1.1f;
    out.grip_scale = table(GRIP_TABLE, 10, 0.0f, 1.0f, r) * 1.2f;
    return out;
}

void Tire::begin_frame(float max_slip_, float grip_boost_, float traction_boost_)
{
    drive_torque = 0.0f;
    brake = 0.0f;
    ebrake = 0.0f;
    lateral_force = 0.0f;
    longitudinal_force = 0.0f;
    traction_circle_lateral = 1.0f;
    traction_circle_longitudinal = 1.0f;
    drift_friction = 1.0f;
    max_slip = max_slip_;
    grip_boost = grip_boost_;
    traction_boost = traction_boost_;
    drag_reduction = 0.15f;
}

void Tire::check_sign()
{
    constexpr float DEAD_BAND = 1e-6f;
    if ((last_sign > 0 && av < 0.0f) || (last_sign < 0 && av > 0.0f))
    {
        av = 0.0f;
    }
    last_sign = av > DEAD_BAND ? 1 : (av < -DEAD_BAND ? -1 : 0);
}

float Tire::display_av(float radius, bool compressed) const
{
    if (brake_locked)
    {
        return 0.0f;
    }
    const bool substitute = integration == TireIntegration::Reference ? (compressed && traction >= 1.0f)
                                                                      : (load > 0.0f && traction < 1.0f);
    return substitute ? road_speed / radius : av;
}

float Tire::pilot_factor(const TireParams& p, float body_speed) const
{
    if (p.front || brake_locked || av < 0.0f)
    {
        return 1.0f;
    }
    const float mph = ms_to_mph(body_speed);
    return 0.85f + 0.15f * clamp((mph - 30.0f) / 20.0f, 0.0f, 1.0f);
}

float Tire::update_loaded(const TireParams& p, const LoadedInput& i)
{
    const bool reference = integration == TireIntegration::Reference;
    const float r = p.radius;
    const float dt = i.dt;
    const float fwd = i.fwd_vel;
    const float lat = i.lat_vel;

    if (load <= 0.0f && !brake_locked)
    {
        av = fwd / r;
        if (!reference)
        {
            road_speed = fwd;
            angular_acc = 0.0f;
        }
    }
    const float fwd_acc = (fwd - road_speed) / dt;
    road_speed = fwd;
    load = std::fmax(i.load, 0.0f);
    lateral_speed = lat;
    const float body_mph = ms_to_mph(i.body_speed);

    const float bt = brake * p.brake_spec;
    const float ebt = ebrake * p.ebrake_spec;
    float brake_torque = 0.0f;
    if (reference && brake_locked)
    {
        drive_torque = 0.0f;
    }
    else if (std::fabs(fwd) < 1.0f)
    {
        const float viscous = -(brake + ebrake) * load * fwd / r;
        const float cap = i.quarter_mass * std::fabs(fwd) / dt * r;
        brake_torque = reference ? viscous : clamp(viscous, -cap, cap);
        drive_torque -= drive_torque * clamp(ebrake, 0.0f, 1.0f);
    }
    else if (!brake_locked)
    {
        brake_torque = av > 0.0f ? -(bt + ebt) : bt + ebt;
    }
    const float total_torque = drive_torque + brake_torque;

    slip_angle = std::atan2(lat, std::fabs(fwd)) / SIM_TAU;
    const float slip_value = av * r - fwd;
    slip = slip_value;
    const float pilot = pilot_factor(p, i.body_speed);
    const float skid = std::hypot(slip_value, lat);
    const float patch_speed = std::hypot(fwd, lat);
    float dyn_grip = 1.0f;
    float ground_friction = 0.0f;
    float ground_force = 0.0f;
    if (skid > EPS && patch_speed > EPS)
    {
        dyn_grip = p.dynamic_grip * traction_boost * pilot;
        const float divisor = reference ? skid : std::fmax(skid, SKID_FLOOR);
        ground_friction = load * dyn_grip / divisor;
        ground_force = std::fabs(fwd) * load * dyn_grip / patch_speed;
    }

    const float available = (brake * p.brake_lock_spec + ebrake * p.ebrake_spec) * LOCK_RATIO;
    const bool test_lock = !reference || (skid > EPS && patch_speed > EPS);
    bool locked;
    if (!test_lock)
    {
        locked = brake_locked;
    }
    else if (available > ground_force * r + std::fabs(av) * LOCK_AV_FACTOR)
    {
        av = 0.0f;
        locked = available > 1.0f;
    }
    else
    {
        locked = false;
    }
    brake_locked = locked;

    float slide_x = ground_friction * slip_value;
    float slide_y = -ground_friction * lat;
    if (body_mph < 1.0f && dyn_grip > 0.1f)
    {
        slide_x /= dyn_grip;
        slide_y /= dyn_grip;
    }
    const bool reference_limit = reference && slide_x * total_torque > 0.0f;
    if (reference_limit || (!reference && !locked))
    {
        const float limit = std::fabs(total_torque) / r;
        slide_x = clamp(slide_x, -limit, limit);
    }
    const float curve = atelier::driving::lateral_force(load, slip_angle, p.grip_scale, grip_boost);
    const float grip_y = lat > 0.0f ? -curve : (lat < 0.0f ? curve : 0.0f);
    const float grip_x = total_torque / r + (angular_acc * r - fwd_acc) * WHEEL_INERTIA / r;
    float w;
    if (locked || (reference && traction < 1.0f))
    {
        w = 0.0f;
    }
    else if (reference && traction >= 1.0f)
    {
        w = 1.0f;
    }
    else
    {
        w = clamp(traction, 0.0f, 1.0f);
    }
    float fx = w * grip_x + (1.0f - w) * slide_x;
    float fy = (w * grip_y + (1.0f - w) * slide_y) * lateral_boost;

    const bool stretched = total_torque * fwd > 0.0f && !locked;
    if (stretched)
    {
        fx *= ELLIPSE_RATIO;
    }
    fy *= traction_circle_lateral;
    fx *= traction_circle_longitudinal;

    const float len = std::hypot(fx, fy);
    const float max_f = load * p.static_grip * traction_boost * drift_friction * pilot;
    float max_slip_value = max_slip;
    if (len > max_f && len > 0.001f)
    {
        const float ratio = max_f / len;
        traction = ratio;
        fx *= ratio;
        fy *= ratio;
        max_slip_value *= ratio * ratio;
    }
    else
    {
        traction = 1.0f;
        if (stretched)
        {
            fx /= ELLIPSE_RATIO;
        }
    }
    if (std::fabs(slip_value) > max_slip_value)
    {
        traction *= max_slip_value / std::fabs(slip_value);
    }

    fy *= i.surface.lateral;
    fx *= i.surface.drive;

    if (fwd > 1.0f)
    {
        fx -= std::sin(slip_angle * SIM_TAU) * fy * drag_reduction / std::fmax(p.grip_scale, EPS);
    }
    else
    {
        fy *= std::fmin(std::fabs(lat), 1.0f);
    }

    if (locked)
    {
        angular_acc = 0.0f;
    }
    else
    {
        if (traction < 1.0f)
        {
            const float torque = (total_torque - fx * r + last_torque) * 0.5f;
            last_torque = torque;
            const float eff = torque - av * ROLLING_FRICTION * i.surface.rolling;
            angular_acc = eff / WHEEL_INERTIA - traction * slip_value / (r * dt);
        }
        if (!reference && traction >= 1.0f)
        {
            angular_acc = fwd_acc / r - slip_value / (r * dt);
        }
        else
        {
            angular_acc = lerp(angular_acc, fwd_acc / r, traction);
        }
        av += angular_acc * dt;
        check_sign();
    }
    longitudinal_force = fx;
    lateral_force = fy;
    return fy;
}

void Tire::update_free(const TireParams& p, float dt)
{
    load = 0.0f;
    slip = 0.0f;
    traction = 0.0f;
    slip_angle = 0.0f;
    lateral_force = 0.0f;
    longitudinal_force = 0.0f;
    lateral_speed = 0.0f;

    const float available = (brake * p.brake_lock_spec + ebrake * p.ebrake_spec) * LOCK_RATIO;
    if (available > std::fabs(av) * LOCK_AV_FACTOR)
    {
        av = 0.0f;
        brake_locked = available > 1.0f;
    }
    else
    {
        brake_locked = false;
    }
    if (brake_locked)
    {
        angular_acc = 0.0f;
        return;
    }
    const float bt = brake * p.brake_spec + ebrake * p.ebrake_spec;
    const float brake_torque = av > 0.0f ? -bt : bt;
    angular_acc = (drive_torque + brake_torque) / WHEEL_INERTIA;
    av += angular_acc * dt;
    check_sign();
}

bool TireDamage::puncture(int wheel)
{
    if (wheel < 0 || wheel >= 4)
    {
        return false;
    }
    const float delay = run_flat ? RUN_FLAT_BLOW_DELAY : BLOW_DELAY;
    if (states[wheel].kind != TireStateKind::None)
    {
        return false;
    }
    states[wheel] = TireState::punctured(delay);
    return true;
}

void TireDamage::advance(float dt)
{
    for (auto& s : states)
    {
        if (s.kind != TireStateKind::Punctured)
        {
            continue;
        }
        const float left = s.fuse - dt;
        s = left <= 0.0f ? TireState::blown() : TireState::punctured(left);
    }
}
} // namespace atelier::driving
