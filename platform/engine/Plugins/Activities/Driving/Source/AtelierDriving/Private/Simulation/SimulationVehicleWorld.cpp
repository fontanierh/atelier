#include "SimulationVehicle.h"

#include <cmath>

namespace atelier::driving
{
namespace
{
constexpr Vec3 BOX_CORNERS[8] = {
    {-1.0f, -1.0f, 1.0f}, {1.0f, -1.0f, 1.0f}, {1.0f, -1.0f, -1.0f}, {-1.0f, -1.0f, -1.0f},
    {-1.0f, 1.0f, 1.0f},  {1.0f, 1.0f, 1.0f},  {1.0f, 1.0f, -1.0f},  {-1.0f, 1.0f, -1.0f},
};
} // namespace

Vehicle::WheelOutput Vehicle::wheel_forces(float dt, const Ground& ground, Vec3 angular_velocity)
{
    const Mat3 rot = body.rotation();
    const Vec3 up = rot.y_axis;
    const Vec3 pos = body.position;
    const Vec3 cog_world = rot * body.cog();
    const Vec3 cog_point = pos + cog_world;
    const Vec3 velocity = body.linear_velocity;
    const float body_speed = length(velocity);
    const float mass = body.mass();
    const float ride_extra = tunings.ride_height;
    AxleConstants axles[2] = {chassis_axle(spec.chassis, 0, ride_extra), chassis_axle(spec.chassis, 1, ride_extra)};
    float old_compression[4];
    for (int i = 0; i < 4; ++i)
    {
        old_compression[i] = corners_[i].compression;
    }
    const auto steer_dir = [&](float angle) { return rot * Vec3{std::sin(angle), 0.0f, std::cos(angle)}; };
    const Vec3 dirs[4] = {steer_dir(wheel_angles_.left), steer_dir(wheel_angles_.right), rot.z_axis, rot.z_axis};

    WheelOutput out;
    for (int i = 0; i < 4; ++i)
    {
        const int axle = i / 2;
        const AxleConstants& a = axles[axle];
        const Vec3 arm_world = rot * geometry.arms[i];
        const Vec3 point = pos + arm_world;
        const Vec3 point_vel = velocity + cross(angular_velocity, arm_world - cog_world);
        const float tolerance =
            std::fmin(std::fmax(-point_vel.y * dt, 0.0f) + geometry.radius[i] +
                          length(Vec3{point_vel.x, 0.0f, point_vel.z}) * dt,
                      spec.dimension.y);

        WheelContact contact;
        bool has_contact = false;
        WheelPlane plane;
        if (ground.wheel_plane(i, point, tolerance, old_compression[i] > 0.0f, plane))
        {
            contact.point = point + plane.normal * plane.separation;
            contact.normal = plane.normal;
            contact.penetration = plane.separation;
            contact.surface = plane.surface;
            has_contact = true;
        }
        else
        {
            has_contact = probe(ground, point, tolerance, contact);
        }
        contacts_[i] = contact;
        contact_valid_[i] = has_contact;
        const float c_old = old_compression[i];
        Compression comp;
        bool has_comp = false;
        if (has_contact)
        {
            comp = compression(a.ride, a.travel, clamp(dot(contact.normal, up), 0.0f, 1.0f), contact.penetration);
            has_comp = true;
        }
        const float c_new = has_comp ? comp.value : 0.0f;
        corners_[i].compression = c_new;
        corners_[i].air_time = c_new == 0.0f ? corners_[i].air_time + dt : 0.0f;

        Vec3 force = VEC3_ZERO;
        const bool loaded = has_comp && comp.loaded;
        loaded_[i] = loaded;
        if (loaded && has_contact && has_comp)
        {
            out.lift_need = std::fmax(out.lift_need, comp.lift_need);
            SpringInput spring_input;
            spring_input.c_old = c_old;
            spring_input.c_new = c_new;
            spring_input.c_left_old = old_compression[axle * 2];
            spring_input.c_right_old = old_compression[axle * 2 + 1];
            spring_input.side = i % 2 == 0 ? Side::Left : Side::Right;
            spring_input.dt = dt;
            spring_input.mass = mass;
            spring_input.blowout = spec.chassis.shock_blowout;
            const float f_spring = spring_force(a, spring_input);
            const Vec3 n = contact.normal;
            const Vec3 f = dirs[i];
            const Vec3 flat = cross(cross(f, n), f);
            const float load = std::fmax(4.0f * dot(flat, n) - 3.0f, 0.3f) * f_spring;
            const Vec3 cross_lat = cross(n, f);
            const Vec3 lat_dir = length_squared(cross_lat) > 1e-8f ? normalize(cross_lat) : rot.x_axis;
            const float fwd_speed = dot(point_vel, f);
            const float lat_speed = dot(point_vel, lat_dir);
            LoadedInput input;
            input.lat_vel = lat_speed;
            input.fwd_vel = fwd_speed;
            input.body_speed = body_speed;
            input.load = load;
            input.dt = dt;
            input.quarter_mass = 0.25f * mass;
            input.surface = contact.surface;
            const float fy = tires[i].update_loaded(params[i], input);
            const float fy_limit = std::fabs(lat_speed / dt) * 0.25f * mass;
            const Vec3 lateral = lat_dir * clamp(fy, -fy_limit, fy_limit);
            const Vec3 cross_drive = cross(lat_dir, n);
            const Vec3 drive_dir = length_squared(cross_drive) > 1e-8f ? normalize(cross_drive) : rot.z_axis;
            force = lateral + drive_dir * tires[i].longitudinal_force + up * f_spring;
        }
        else
        {
            tires[i].update_free(params[i], dt);
        }

        Vec3 arm = geometry.arms[i];
        arm.y += c_new - a.ride;
        const Vec3 patch = pos + rot * arm;
        patch_positions_[i] = patch;
        if (is_finite(force))
        {
            out.force += force;
            out.torque += cross(patch - cog_point, force);
        }
    }
    wheels_on_ground_ = 0;
    for (bool l : loaded_)
    {
        wheels_on_ground_ += l ? 1 : 0;
    }
    if (spec.wheel_ground_reference && wheels_on_ground_ > 0)
    {
        // Keep the last contact plane for the airborne alignment assist. It stays valid after the wheels unload
        // until the vehicle is reset or lands again.
        Vec3 normal = VEC3_ZERO;
        float contacts_y = 0.0f;
        for (int i = 0; i < 4; ++i)
        {
            if (!loaded_[i])
            {
                continue;
            }
            normal += contacts_[i].normal;
            contacts_y += contacts_[i].point.y;
        }
        ground_reference.normal = length_squared(normal) > 1e-8f ? normalize(normal) : VEC3_Y;
        ground_reference.separation = contacts_y / float(wheels_on_ground_) - body.position.y;
        has_ground_reference = true;
    }
    return out;
}

int Vehicle::collide_body_with_ground(const Ground& ground)
{
    const Vec3 half = body.dimension() + body.spec().collision_box_pad;
    std::vector<GroundContact> found;
    const float raise = body.spec().collision_bottom_raise;
    for (const Vec3& corner : BOX_CORNERS)
    {
        Vec3 local = half * corner;
        if (corner.y < 0.0f && raise > 0.0f)
        {
            local.y += raise;
        }
        const Vec3 point = body.position + body.rotation() * local;
        GroundContact c;
        if (body.ground_contact(point, ground, FIXED_STEP, c))
        {
            found.push_back(c);
        }
    }
    body.resolve_ground(found);
    body_contacts_ = found;
    return static_cast<int>(found.size());
}

Vec3 Vehicle::damp_landing(Vec3 angular_velocity)
{
    if (wheels_on_ground_prev_ == 0 && wheels_on_ground_ > 0)
    {
        const Mat3 rot = body.rotation();
        Vec3 w = transpose(rot) * angular_velocity;
        w.y *= 0.5f;
        w.z *= 0.5f;
        body.angular_velocity = rot * w;
        return body.angular_velocity;
    }
    return angular_velocity;
}

void Vehicle::damp_creep(bool did_collide, Vec3 angular_velocity)
{
    const Controls c = controls_;
    const float speed = length(body.linear_velocity);
    const float spin = length(angular_velocity);
    if (spin >= 0.25f || c.gas > 0.0f)
    {
        return;
    }
    const Mat3 rot = body.rotation();
    if (speed < 0.5f && wheels_on_ground_ == 4 && (c.brake > 0.0f || c.handbrake > 0.0f) && !did_collide)
    {
        body.linear_velocity *= speed;
        body.angular_velocity *= speed;
        if (tire_integration_ == TireIntegration::Reference)
        {
            set_pending(body.pending_force() * speed, body.pending_torque() * speed);
        }
        for (auto& tire : tires)
        {
            tire.av = 0.0f;
        }
    }
    else if (speed < 1.0f)
    {
        Vec3 v = transpose(rot) * body.linear_velocity;
        v.x *= speed;
        body.linear_velocity = rot * v;
        Vec3 w = transpose(rot) * angular_velocity;
        w.y *= speed;
        body.angular_velocity = rot * w;
        const float keep = tire_integration_ == TireIntegration::Reference ? speed : 1.0f - speed;
        Vec3 f = transpose(rot) * body.pending_force();
        Vec3 t = transpose(rot) * body.pending_torque();
        f.x *= keep;
        t.y *= keep;
        set_pending(rot * f, rot * t);
    }
}

namespace
{
float graph_pairs(const std::vector<std::pair<float, float>>& points, float x)
{
    if (points.empty())
    {
        return 0.0f;
    }
    if (x <= points.front().first)
    {
        return points.front().second;
    }
    if (x >= points.back().first)
    {
        return points.back().second;
    }
    for (size_t i = 0; i + 1 < points.size(); ++i)
    {
        const float x0 = points[i].first;
        const float y0 = points[i].second;
        const float x1 = points[i + 1].first;
        const float y1 = points[i + 1].second;
        if (x <= x1)
        {
            return x1 > x0 ? lerp(y0, y1, (x - x0) / (x1 - x0)) : y1;
        }
    }
    return points.back().second;
}

Vec3 correction(Vec3 flat, Vec3 direction, float weight, float threshold)
{
    const float d = dot(flat, direction);
    if (d >= threshold)
    {
        return VEC3_ZERO;
    }
    return normalize_or_zero(cross(flat, direction)) * (weight * (d - 1.0f));
}

Vec3 passive(const PassiveConfig& config, const JumpInput& input)
{
    if (input.grounded_wheels >= config.maximum_grounded_wheels || input.rotation.y_axis.y <= config.minimum_up ||
        input.body_contact || input.grounded_wheels > 0)
    {
        return VEC3_ZERO;
    }
    const Vec3 angular = transpose(input.rotation) * input.angular_velocity;
    const float damping = ramp(input.speed, 0.0f, config.maximum_speed) *
                          graph_pairs(config.damping, length(angular));
    const Vec3 moment = -angular * input.inertia * damping;
    return input.rotation * Vec3{moment.x, 0.0f, moment.z};
}

Vec3 alignment(const AlignmentConfig& config, const JumpInput& input)
{
    if (!input.has_ground)
    {
        return VEC3_ZERO;
    }
    const Vec3 up = input.rotation.y_axis;
    const float altitude = -input.ground.separation;
    if (input.grounded_wheels != 0 || input.ground.normal.y <= config.minimum_ground_up ||
        up.y <= config.minimum_body_up || dot(up, input.ground.normal) <= config.minimum_alignment ||
        altitude <= config.minimum_altitude)
    {
        return VEC3_ZERO;
    }
    const Vec3 right = input.rotation.x_axis;
    const Vec3 forward = input.rotation.z_axis;
    const float weight = input.mass * ramp(input.speed, 0.0f, config.maximum_speed) *
                         (1.0f - ramp(altitude, 0.0f, config.maximum_altitude));
    const Vec3 flat_forward = normalize_or_zero(cross(right, input.ground.normal));
    const Vec3 flat_right = normalize_or_zero(cross(input.ground.normal, forward));
    return correction(flat_forward, forward, weight * config.pitch, config.correction_threshold) +
           correction(flat_right, right, weight * config.roll, config.correction_threshold);
}
} // namespace

float JumpState::landing(const JumpConfig& config, const JumpInput& input) const
{
    if (!input.has_ground)
    {
        return 0.0f;
    }
    const LandingConfig& c = config.landing;
    const float altitude = -input.ground.separation;
    if (airborne_time <= c.minimum_time || peak_altitude <= c.minimum_peak_altitude ||
        dot(input.rotation.y_axis, input.ground.normal) <= c.minimum_alignment ||
        input.linear_velocity.y >= 0.0f || altitude >= c.maximum_altitude)
    {
        return 0.0f;
    }
    return c.acceleration * (1.0f - ramp(altitude, 0.0f, c.maximum_altitude)) *
           ramp(input.speed, 0.0f, c.maximum_speed);
}

JumpForces JumpState::update(const JumpConfig& config, const JumpInput& input)
{
    if (!std::isfinite(input.dt) || input.dt <= 0.0f)
    {
        return JumpForces{};
    }
    JumpForces result;
    if (input.grounded_wheels == 0)
    {
        airborne_time += input.dt;
        if (input.has_ground)
        {
            peak_altitude = std::fmax(peak_altitude, -input.ground.separation);
        }
        const float acceleration = config.extra_airborne_acceleration + landing(config, input);
        result.force = VEC3_NEG_Y * (input.mass * acceleration);
    }
    if (input.grounded_wheels > 0)
    {
        *this = JumpState{};
    }
    result.torque += passive(config.passive, input);
    result.torque += alignment(config.alignment, input);
    return result;
}

void Vehicle::apply_jump(float dt, float speed, Vec3 angular_velocity)
{
    JumpInput input;
    input.dt = dt;
    input.mass = body.mass();
    input.inertia = body.inertia();
    input.rotation = body.rotation();
    input.linear_velocity = body.linear_velocity;
    input.angular_velocity = angular_velocity;
    input.speed = speed;
    input.grounded_wheels = wheels_on_ground_;
    input.body_contact = body_ground_contact_ || wheels_on_ground_ > 0;
    input.has_ground = has_ground_reference;
    input.ground = ground_reference;
    const JumpForces output = jump_state_.update(jump_config, input);
    body.apply_force(output.force);
    body.apply_torque(output.torque);
}
} // namespace atelier::driving
