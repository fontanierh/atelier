#pragma once

#include "SimulationSpec.h"

namespace atelier::driving
{
/** A Japanese kei car: 3.39 m long, 1.47 m wide, 1.40 m tall, 820 kg, a 660 cc engine, 155/65R13
 *  tyres and a five-speed automatic. A host's kei body built to the same class limits fits this
 *  chassis without rescaling. */
inline VehicleSpec kei_spec()
{
    VehicleSpec s;
    s.mass = 820.0f;
    s.dimension = {0.735f, 0.70f, 1.695f};
    // Track, wheelbase and axle are metres in this data (ride height and travel are inches).
    s.chassis.track_width[0] = 1.32f;
    s.chassis.track_width[1] = 1.30f;
    s.chassis.wheel_base = 2.40f;
    s.chassis.front_axle = 1.20f;
    s.chassis.front_weight_bias = 58.0f;
    s.chassis.roll_center = 10.0f;
    s.chassis.spring_stiffness[0] = 240.0f;
    s.chassis.spring_stiffness[1] = 200.0f;
    s.chassis.spring_progression[0] = 1.6f;
    s.chassis.spring_progression[1] = 1.6f;
    s.chassis.shock_stiffness[0] = 24.0f;
    s.chassis.shock_stiffness[1] = 22.0f;
    s.chassis.shock_ext_stiffness[0] = 30.0f;
    s.chassis.shock_ext_stiffness[1] = 28.0f;
    s.chassis.swaybar_stiffness[0] = 60.0f;
    s.chassis.swaybar_stiffness[1] = 40.0f;
    s.chassis.travel[0] = 3.2f;
    s.chassis.travel[1] = 3.2f;
    s.chassis.ride_height[0] = 4.0f;
    s.chassis.ride_height[1] = 4.0f;

    s.tires.rim_size[0] = 13.0f;
    s.tires.rim_size[1] = 13.0f;
    s.tires.section_width[0] = 155.0f;
    s.tires.section_width[1] = 155.0f;
    s.tires.aspect_ratio[0] = 65.0f;
    s.tires.aspect_ratio[1] = 65.0f;
    s.tires.static_grip[0] = 1.0f;
    s.tires.static_grip[1] = 1.0f;
    s.tires.dynamic_grip[0] = 0.9f;
    s.tires.dynamic_grip[1] = 0.9f;
    s.tires.yaw_control = {1.0f, 0.85f, 0.65f};

    s.brakes.brakes[0] = 120.0f;
    s.brakes.brakes[1] = 90.0f;
    s.brakes.brake_lock[0] = 0.85f;
    s.brakes.brake_lock[1] = 0.85f;
    s.brakes.ebrake = 60.0f;

    s.engine.torque = {55.0f, 72.0f, 82.0f, 86.0f, 84.0f, 78.0f, 68.0f, 52.0f, 34.0f};
    s.engine.idle = 850.0f;
    s.engine.red_line = 6200.0f;
    s.engine.max_rpm = 7000.0f;
    s.engine.flywheel_mass = 6.0f;
    s.engine.engine_braking = {0.12f};
    s.engine.speed_limiter[0] = 87.0f;   // mph: the kei class's 140 km/h
    s.engine.speed_limiter[1] = 2.0f;

    s.transmission.gear_ratio = {3.8f, 0.0f, 3.6f, 2.15f, 1.45f, 1.0f, 0.82f};
    s.transmission.gear_efficiency.assign(7, 0.92f);
    s.transmission.final_gear = 5.4f;
    s.transmission.differential[1] = 0.25f;
    s.transmission.clutch_slip = 0.35f;
    s.transmission.shift_speed = 0.15f;

    s.aero.drag_coefficient = 0.38f;
    s.aero.aero_coefficient = 0.0015f;
    s.aero.aero_cg = 45.0f;
    return s;
}
} // namespace atelier::driving
