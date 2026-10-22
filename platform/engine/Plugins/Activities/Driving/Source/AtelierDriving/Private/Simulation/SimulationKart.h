#pragma once

#include "SimulationSpec.h"

namespace atelier::driving
{
/** A single-seat go-kart: 2.16 m long, 1.24 m wide, 240 kg with its driver, a 125 cc engine and 130/60-5
 *  tyres. The host's kart mesh is built to the same frame, so the wheels and the seat line up without rescaling. */
inline VehicleSpec kart_spec()
{
    VehicleSpec s;
    s.mass = 240.0f;
    s.dimension = {0.62f, 0.25f, 1.08f};
    s.chassis.track_width[0] = 1.10f;
    s.chassis.track_width[1] = 1.24f;
    s.chassis.wheel_base = 1.50f;
    s.chassis.front_axle = 0.75f;
    s.chassis.front_weight_bias = 42.0f;
    s.chassis.roll_center = 3.0f;
    // Ride quality over broken ground: 4.5 in of travel on soft springs with light damping keeps all four tyres
    // down over ripples and facets without wallowing in a turn.
    s.chassis.spring_stiffness[0] = 90.0f;
    s.chassis.spring_stiffness[1] = 105.0f;
    s.chassis.spring_progression[0] = 0.5f;
    s.chassis.spring_progression[1] = 0.5f;
    s.chassis.shock_stiffness[0] = 12.0f;
    s.chassis.shock_stiffness[1] = 14.0f;
    s.chassis.shock_ext_stiffness[0] = 17.0f;
    s.chassis.shock_ext_stiffness[1] = 19.0f;
    s.chassis.swaybar_stiffness[0] = 80.0f;
    s.chassis.swaybar_stiffness[1] = 60.0f;
    s.chassis.travel[0] = 4.5f;
    s.chassis.travel[1] = 4.5f;
    s.chassis.ride_height[0] = 2.8f;
    s.chassis.ride_height[1] = 2.8f;

    s.tires.rim_size[0] = 5.0f;
    s.tires.rim_size[1] = 5.0f;
    s.tires.section_width[0] = 130.0f;
    s.tires.section_width[1] = 145.0f;
    s.tires.aspect_ratio[0] = 60.0f;
    s.tires.aspect_ratio[1] = 60.0f;
    s.tires.static_grip[0] = 1.3f;
    s.tires.static_grip[1] = 1.35f;
    s.tires.dynamic_grip[0] = 1.1f;
    s.tires.dynamic_grip[1] = 1.15f;
    s.tires.steering = 0.6f;   // fallback for the shared tables; the lock curve below is used instead
    s.tires.has_lock_curve = true;
    s.tires.lock_angle_low = 27.0f;    // tight at walking pace
    s.tires.lock_angle_high = 12.0f;   // calmer at the 24.6 m/s top speed
    s.tires.lock_speed_low = 3.0f;
    s.tires.lock_speed_high = 24.6f;
    s.tires.lock_ramp_time = 0.15f;
    s.tires.lock_center_rate = 1.5f;
    s.tires.yaw_control = {1.0f, 0.9f, 0.7f};
    s.body.collision_bottom_raise = 0.04f;
    s.drift_requires_request = true;
    s.drift_assist_min_speed = 3.0f;
    s.drift_assist_min_slip = 0.10471976f;   // 6 degrees
    s.stability_assist = true;
    s.wheel_ground_reference = true;

    s.brakes.brakes[0] = 60.0f;
    s.brakes.brakes[1] = 45.0f;
    s.brakes.brake_lock[0] = 0.9f;
    s.brakes.brake_lock[1] = 0.9f;
    s.brakes.ebrake = 30.0f;

    s.engine.torque = {70.0f, 75.0f, 78.0f, 78.0f, 74.0f, 66.0f, 56.0f, 40.0f};
    s.engine.idle = 1200.0f;
    s.engine.red_line = 5200.0f;
    s.engine.max_rpm = 5600.0f;
    s.engine.flywheel_mass = 3.0f;
    s.engine.engine_braking = {0.18f};
    s.engine.speed_limiter[0] = 55.0f;   // mph
    s.engine.speed_limiter[1] = 2.0f;

    s.transmission.gear_ratio = {1.8f, 0.0f, 4.2f};
    s.transmission.gear_efficiency.assign(3, 0.95f);
    s.transmission.final_gear = 1.0f;
    s.transmission.differential[1] = 0.0f;
    s.transmission.solid_axle[1] = true;
    s.transmission.clutch_slip = 0.4f;
    s.transmission.shift_speed = 0.1f;

    s.aero.drag_coefficient = 0.55f;
    s.aero.aero_coefficient = 0.004f;
    s.aero.aero_cg = 30.0f;
    return s;
}
} // namespace atelier::driving
