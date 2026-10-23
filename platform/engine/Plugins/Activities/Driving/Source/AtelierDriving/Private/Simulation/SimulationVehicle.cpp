#include "SimulationVehicle.h"

#include <cmath>

namespace atelier::driving
{
namespace
{
constexpr float DRIFT_SLIP = 0.04f;
constexpr float SKID_RANGE_LOW = 2.0f;
constexpr float SKID_RANGE_HIGH = 5.0f;
constexpr float SMOKE_RANGE_LOW = 3.5f;
constexpr float SMOKE_RANGE_HIGH = 9.0f;
} // namespace

Vehicle::Vehicle(const VehicleSpec& vehicle_spec) : spec(vehicle_spec)
{
    geometry = Geometry::make(spec.chassis, spec.tires, spec.dimension.y);
    for (int i = 0; i < 4; ++i)
    {
        const int axle = i / 2;
        params[i] = {
            geometry.radius[i],
            spec.tires.grip_scale[axle],
            spec.tires.static_grip[axle],
            spec.tires.dynamic_grip[axle],
            brake_torque(spec.brakes, axle),
            brake_lock_torque(spec.brakes, axle),
            ebrake_torque(spec.brakes),
            axle == 0,
        };
        tires[i].integration = tire_integration_;
    }
    body = RigidBody(spec.mass, spec.dimension, spec.tensor_scale, spec.body);
    powertrain = Powertrain(spec.engine, spec.transmission, spec.induction, spec.nos, spec.tires.average_radius());
}

void Vehicle::reset_dynamics()
{
    wall_steering_ = WallSteering{};
    jump_state_ = JumpState{};
    has_ground_reference = false;
    body_ground_contact_ = false;
    body_contacts_.clear();
    for (auto& tire : tires)
    {
        tire = Tire{};
        tire.integration = tire_integration_;
    }
    for (auto& corner : corners_)
    {
        corner = Corner{};
    }
    for (int i = 0; i < 4; ++i)
    {
        contact_valid_[i] = false;
        loaded_[i] = false;
    }
    wheels_on_ground_ = 0;
    wheels_on_ground_prev_ = 0;
    steering.reset();
    wheel_angles_ = WheelAngles{};
    controls_ = Controls{};
    yaw_control = 1.0f;
    burnout_ = Burnout{};
    drift_ = Drift{};
    body_slip = 0.0f;
    collided = false;
}

void Vehicle::place(Vec3 position, Quat orientation)
{
    reset_dynamics();
    body.place(position, orientation);
    powertrain.reset();
}

void Vehicle::place_moving(Vec3 position, Quat orientation, float speed)
{
    reset_dynamics();
    body.place(position, orientation);
    body.linear_velocity = orientation * Vec3{0.0f, 0.0f, speed};
    powertrain.match_speed(speed);
    for (int i = 0; i < 4; ++i)
    {
        tires[i].av = speed / params[i].radius;
        tires[i].road_speed = speed;
    }
}

bool Vehicle::place_on_ground(const Ground& ground, float x, float z, float top, float yaw)
{
    return place_on_ground_moving(ground, x, z, top, yaw, 0.0f);
}

bool Vehicle::place_on_ground_moving(const Ground& ground, float x, float z, float top, float yaw, float speed)
{
    GroundHit hit;
    if (!ground.hit(Vec3{x, top, z}, VEC3_NEG_Y, 100.0f, hit))
    {
        return false;
    }
    const float y = top - hit.distance;
    const float ride =
        std::fmax(chassis_axle(spec.chassis, 0, tunings.ride_height).ride,
                  chassis_axle(spec.chassis, 1, tunings.ride_height).ride);
    const Vec3 position{x, y + spec.dimension.y + ride, z};
    const Quat orientation = rotation_y(yaw);
    if (speed > 0.0f)
    {
        place_moving(position, orientation, speed);
    }
    else
    {
        place(position, orientation);
    }
    return true;
}

void Vehicle::set_tire_integration(TireIntegration integration)
{
    tire_integration_ = integration;
    burnout_ = Burnout{};
    for (auto& tire : tires)
    {
        tire.integration = integration;
    }
}

WheelState Vehicle::wheel(int i) const
{
    WheelState out;
    const float steer = i == 0 ? wheel_angles_.left : (i == 1 ? wheel_angles_.right : 0.0f);
    const Tire& tire = tires[i];
    const float radius = params[i].radius;
    const bool on_ground = loaded_[i];
    out.position = patch_positions_[i];
    out.radius = radius;
    out.steer_angle = steer;
    out.angular_velocity = tire.display_av(radius, corners_[i].compression > 0.0f);
    out.simulated_angular_velocity = tire.av;
    out.compression = corners_[i].compression;
    out.on_ground = on_ground;
    out.load = tire.load;
    out.slip = tire.slip;
    out.lateral_speed = tire.lateral_speed;
    out.slip_angle = tire.slip_angle * SIM_TAU;
    out.traction = tire.traction;
    out.locked = tire.brake_locked;
    out.lateral_force = tire.lateral_force;
    out.longitudinal_force = tire.longitudinal_force;
    out.slide_speed = on_ground ? std::hypot(tire.slip, tire.lateral_speed) : 0.0f;
    out.skid = on_ground ? ramp(out.slide_speed, SKID_RANGE_LOW, SKID_RANGE_HIGH) : 0.0f;
    out.smoke = on_ground ? ramp(out.slide_speed, SMOKE_RANGE_LOW, SMOKE_RANGE_HIGH) : 0.0f;
    return out;
}

bool Vehicle::wheel_surface_tag(int i, uint32_t& out) const
{
    if (i < 0 || i >= 4 || !contact_valid_[i])
    {
        return false;
    }
    out = contacts_[i].surface.tag;
    return true;
}

bool Vehicle::wheel_ground_hit(int i, Vec3& point, Vec3& normal) const
{
    if (i < 0 || i >= 4 || !contact_valid_[i])
    {
        return false;
    }
    point = contacts_[i].point;
    normal = contacts_[i].normal;
    return true;
}

void Vehicle::notify_collision(float impulse)
{
    steering.notify_collision(impulse);
    collided = true;
}

void Vehicle::step(float dt, const InputState& input, const Ground& ground)
{
    if (!(dt > 0.0f) || !std::isfinite(dt))
    {
        return;
    }
    tire_damage.advance(dt);
    body_contacts_.clear();
    body.begin_frame(dt);
    time_ += dt;
    if (body.state == BodyState::Frozen)
    {
        return;
    }
    if (body.state == BodyState::Asleep)
    {
        // Braking from rest selects reverse (auto-reverse), so it has to wake the body too.
        if (input.throttle > 0.0f || input.brake > 0.0f || input.handbrake > 0.0f)
        {
            body.wake();
        }
        else
        {
            return;
        }
    }
    const bool did_collide = collided;
    collided = false;
    wheels_on_ground_prev_ = wheels_on_ground_;

    const Mat3 rot = body.rotation();
    const Vec3 local_velocity = transpose(rot) * body.linear_velocity;
    const float speed = length(body.linear_velocity);
    const Vec3 angular_velocity = body.angular_velocity;
    body_slip = local_velocity.z < 1.0f ? 0.0f : std::atan2(local_velocity.x, local_velocity.z);

    update_controls(input, local_velocity.z);
    body.set_cog(center_of_gravity(spec.chassis, spec.dimension.y, tunings.ride_height,
                                   wheels_on_ground_prev_ > 0));
    update_steering(dt, local_velocity.z);
    apply_wall_steering();

    begin_tires(speed);
    run_powertrain(dt, speed);
    tune_tires(dt, speed, angular_velocity);
    apply_aero();

    const WheelOutput out = wheel_forces(dt, ground, angular_velocity);
    if (wheels_on_ground_ > 0)
    {
        const Vec3 up = body.rotation().y_axis;
        Vec3 torque = out.torque;
        const float yaw = dot(up, torque);
        torque += up * (yaw * spec.tires.yaw_speed - yaw);
        body.apply_force(out.force);
        body.apply_torque(torque);
        if (out.lift_need > 0.0f)
        {
            body.position.y += out.lift_need;
        }
    }
    const Vec3 angular_after = damp_landing(angular_velocity);
    apply_jump(dt, speed, angular_after);
    damp_creep(did_collide, angular_after);

    body.apply_drag();
    const int corner_contacts = collide_body_with_ground(ground);
    body_ground_contact_ = corner_contacts > 0;
    if (wheels_on_ground_ == 0)
    {
        body.update_sleep(corner_contacts);
    }
    sanitize();
}

void Vehicle::update_controls(const InputState& input, float forward_speed)
{
    InputContext ctx;
    ctx.forward_speed = forward_speed;
    ctx.gear = powertrain.gear_id();
    ctx.disabled = disabled;
    const Controls shaped = shape(input, config, ctx);
    if (shaped.gear_request.kind == GearRequestKind::Reverse)
    {
        powertrain.shift(GEAR_REVERSE);
    }
    else if (shaped.gear_request.kind == GearRequestKind::First)
    {
        powertrain.shift(GEAR_FIRST);
    }
    else if (shaped.gear_request.kind == GearRequestKind::Shift)
    {
        powertrain.request_shift(shaped.gear_request.value, config.automatic);
    }
    else if (shaped.gear_request.kind == GearRequestKind::Select)
    {
        powertrain.select_gear(shaped.gear_request.value, forward_speed);
    }
    controls_ = shaped;
}

void Vehicle::update_steering(float dt, float forward_speed)
{
    const Controls c = controls_;
    SteeringInput input;
    input.dt = dt;
    input.steer = c.steering;
    input.gas = c.gas;
    input.brake = c.brake;
    input.ebrake = c.handbrake;
    input.forward_speed = forward_speed;
    input.tire_steering = spec.tires.steering;
    input.tuning = tunings.steering;
    input.has_lock_curve = spec.tires.has_lock_curve;
    input.lock_angle_low = spec.tires.lock_angle_low;
    input.lock_angle_high = spec.tires.lock_angle_high;
    input.lock_speed_low = spec.tires.lock_speed_low;
    input.lock_speed_high = spec.tires.lock_speed_high;
    input.lock_ramp_time = spec.tires.lock_ramp_time;
    input.lock_center_rate = spec.tires.lock_center_rate;
    input.device = config.steering_device;
    input.rear_slip_deg[0] = tires[2].slip_angle * 360.0f;
    input.rear_slip_deg[1] = tires[3].slip_angle * 360.0f;
    const float normal_angle = steering.update(input);
    const float angle = maneuver.has_steering_degrees ? c.steering * maneuver.steering_degrees : normal_angle;
    wheel_angles_ = has_forced_wheel_angles
                       ? forced_wheel_angles
                       : ackermann(angle, spec.chassis.wheel_base, spec.chassis.track_width[0]);
}

void Vehicle::run_powertrain(float dt, float speed)
{
    const TransmissionSpec& trans = spec.transmission;
    const bool front = front_driven(trans);
    const bool rear = rear_driven(trans);
    const float dir = powertrain.gear_id() == GEAR_REVERSE ? -1.0f : 1.0f;
    const auto is_driven = [&](int i) { return i < 2 ? front : rear; };
    int count = 0;
    float slip_sum = 0.0f;
    for (int i = 0; i < 4; ++i)
    {
        if (is_driven(i))
        {
            ++count;
            slip_sum += tires[i].slip;
        }
    }
    const float drive_slip = count == 0 ? 0.0f : slip_sum / static_cast<float>(count) * dir;
    float max_wheel_slip = 0.0f;
    for (const auto& tire : tires)
    {
        max_wheel_slip = std::fmax(max_wheel_slip, std::fabs(tire.slip));
    }
    const bool reference = tire_integration_ == TireIntegration::Reference;
    std::array<float, 4> av{};
    for (int i = 0; i < 4; ++i)
    {
        av[i] = reference ? tires[i].display_av(params[i].radius, corners_[i].compression > 0.0f) : tires[i].av;
    }
    TickInput input;
    input.dt = dt;
    input.gas = controls_.gas;
    input.nos_held = controls_.nos;
    input.can_recharge_nos = can_recharge_nos;
    input.blown = disabled;
    input.automatic = config.automatic;
    input.speed = speed;
    input.wheel_av = &av;
    for (int i = 0; i < 4; ++i)
    {
        input.grounded[i] = loaded_[i];
    }
    input.drifting = is_drifting();
    input.drive_slip = drive_slip;
    input.max_wheel_slip = max_wheel_slip;
    input.induction_tuning = tunings.induction;
    input.nos_tuning = tunings.nos;
    input.has_clutch_pedal = controls_.has_clutch;
    input.clutch_pedal = controls_.clutch;
    const float drive_torque = powertrain.tick(input);
    const std::array<bool, 4> writes = powertrain.wheel_writes();
    for (int i = 0; i < 4; ++i)
    {
        if (!reference || writes[i])
        {
            tires[i].av = av[i];
        }
    }
    std::array<float, 4> wheel_av{};
    for (int i = 0; i < 4; ++i)
    {
        wheel_av[i] = tires[i].av;
    }
    std::array<bool, 4> grounded{};
    for (int i = 0; i < 4; ++i)
    {
        grounded[i] = loaded_[i];
    }
    distribute_drive(drive_torque, wheel_av, grounded);
}

bool Vehicle::is_drifting() const
{
    if (spec.drift_requires_request && controls_.handbrake <= 0.5f)
    {
        return false;
    }
    for (int i = 2; i < 4; ++i)
    {
        if (loaded_[i] && std::fabs(tires[i].slip_angle) > DRIFT_SLIP)
        {
            return true;
        }
    }
    return false;
}

void Vehicle::apply_aero()
{
    const Mat3 rot = body.rotation();
    body.apply_force((-rot.y_axis * spec.mass) * maneuver.extra_downward_acceleration);
    AeroSpec aero = spec.aero;
    aero.drag_coefficient = spec.aero.drag_coefficient * maneuver.drag_scale;
    aero::AeroInput input;
    input.linear_velocity = body.linear_velocity;
    input.rotation = rot;
    input.gas = controls_.gas;
    input.ground_effect = 0.25f * static_cast<float>(wheels_on_ground_prev_);
    input.any_wheel_on_ground = wheels_on_ground_prev_ > 0;
    input.tuning = tunings.aerodynamics;
    const aero::AeroForces f = aero::forces(aero, input, geometry.front_z(), geometry.rear_z());
    if (!(f.drag == VEC3_ZERO))
    {
        const Vec3 at = body.world_cog() - rot.y_axis * f.drag_drop;
        body.apply_force_at(f.drag, at);
    }
    if (!(f.downforce == VEC3_ZERO))
    {
        const Vec3 at = f.has_downforce_z ? body.position + rot * Vec3{0.0f, body.cog().y, f.downforce_z}
                                          : body.world_cog();
        body.apply_force_at(f.downforce, at);
    }
}

void Vehicle::sanitize()
{
    if (!(is_finite(body.position) && is_finite(body.linear_velocity) && is_finite(body.angular_velocity) &&
          is_finite(body.orientation)))
    {
        const Vec3 position = is_finite(body.position) ? body.position : VEC3_ZERO;
        const Quat yaw_only = is_finite(body.orientation) ? body.orientation : QUAT_IDENTITY;
        body.place(position, yaw_only);
    }
    for (auto& tire : tires)
    {
        tire.av = clamp_signed(tire.av, 5000.0f);
    }
}

void Vehicle::set_pending(Vec3 force, Vec3 torque)
{
    const Vec3 f0 = body.pending_force();
    const Vec3 t0 = body.pending_torque();
    body.apply_force(force - f0);
    body.apply_torque(torque - t0);
}

void Vehicle::set_spec(const VehicleSpec& new_spec)
{
    Vehicle prepared(new_spec);
    RigidBody new_body(new_spec.mass, new_spec.dimension, new_spec.tensor_scale, new_spec.body);
    new_body.place(body.position, body.orientation);
    new_body.linear_velocity = body.linear_velocity;
    new_body.angular_velocity = body.angular_velocity;
    new_body.state = body.state;
    new_body.set_cog(body.cog());
    new_body.apply_force(body.pending_force());
    new_body.apply_torque(body.pending_torque());
    body = new_body;
    powertrain.reconfigure(new_spec.engine, new_spec.transmission, new_spec.induction, new_spec.nos,
                           new_spec.tires.average_radius());
    geometry = prepared.geometry;
    for (int i = 0; i < 4; ++i)
    {
        params[i] = prepared.params[i];
    }
    spec = new_spec;
}

void Vehicle::modify_object_hit(BodyHit& hit) const
{
    if (!maneuver.has_collision_mass_scale)
    {
        return;
    }
    const float scale = maneuver.collision_mass_scale;
    if (hit.immobile || hit.mass_scale <= 0.0f || scale <= 0.0f)
    {
        return;
    }
    hit.inertia_scale = hit.inertia_scale * (scale / hit.mass_scale);
    hit.mass_scale = scale;
}
} // namespace atelier::driving
