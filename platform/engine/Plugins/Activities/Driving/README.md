# Atelier driving

A self-contained C++17 driving simulation for a four-wheel car, and the Unreal component that
drives one from a character. The simulation is engine-free: it has no engine, renderer, asset or
platform dependency. `UDrivingComponent` is the Unreal host: it reads the world with a ray per
wheel, steps the simulation, and moves the character it is attached to.

## What it does

One fixed 60 Hz step drives a four-wheel car:

- rigid body with box inertia, drag, sleep and ordered ground contacts;
- spring and damper corners with progressive springs, digressive dampers, blow-off and anti-roll;
- load-sensitive lateral tire curve, friction ellipse, brake lock, wheel spin and damage;
- engine torque curve, clutch, automatic and manual gearbox, differentials and torque converter;
- speed-sensitive steering, range and rate shaping, counter-steer, Ackermann and wall-steering escape;
- drag and downforce with a caller-supplied maneuver assist;
- forced induction, nitrous, drift state, burnout and launch traction control;
- jump stabilizers, landing assist, terrain alignment and low-speed sleep damping;
- rigid-body pair contacts, ball joints, angular limits, OBB and sphere contacts for props and trailers.

The entry point is atelier::driving::Vehicle. A ground is the only world interface the car needs: a
ray hit per wheel plus optional prepared planes and surface grip. Vehicle keeps its own body; a host
receives position(), orientation() and wheel(i) and can drive its own presentation from them.

## Layout

| Path | Contents |
|---|---|
| Source/AtelierDriving/Private/Simulation/SimulationMath.h | Vec3, Quat, Mat3, tables and units |
| SimulationSpec.h | plain car, chassis, tire, engine, transmission and tuning data |
| SimulationRigidBody.* | rigid body, ground response, pair contacts, OBB/sphere contacts, joints and limits |
| SimulationDrivetrain.* | engine coupling, clutch, gearbox, differentials and torque loop |
| SimulationTires.* | tire force, slip, load, damage and surface grip |
| SimulationSuspension.* | corner geometry, probes, compression, springs and dampers |
| SimulationSteering.* | steering tables, input history, speed-sensitive range and Ackermann |
| SimulationVehicle.* | the car step, wheel loop, aero, wall response and hardware replacement |
| SimulationPerformance.* | measured top speed and acceleration table |
| Tests/Simulation/self_test.cpp | standalone C++ checks for driving, shifting, contacts and performance |
| Private/DrivingComponent.cpp | the Unreal host: summon, mount, ground traces, fixed-step tick, dismount |

## Unreal host

`UDrivingComponent` is a component on the playable character. `Initialize` creates its scene root,
body mesh, seat, four wheel meshes and steering wheel on that character. `SetMeshes` supplies the four
required assets, and `Configure` takes the host's cockpit frame in centimetres (+X nose, +Y right).
The body origin is the ground under its middle, the wheel origin is its axle (+Y), and the steering
wheel origin is its hub (axis +X). Missing assets or an unsupported rider fit prevent mounting.
The component fits the entire cockpit and simulation to the rider's reference leg length before mounting.

`Toggle` finds ground beside the rider, places the chassis with `Vehicle::place_on_ground`, keeps the
character visible for the seated stance, stops CharacterMovement and takes the actor transform each tick. The step is
the simulation's fixed 1/60 s, fed the character's stick intent: `Move.Y` accelerates or brakes,
`Move.X` steers right. Each wheel's world contact comes from one downward line trace through
`Ground::hit`; a box sweep of the chassis stops it at walls. Wheels spin and steer and the steering
wheel turns from the simulation's own angles. `Toggle` again (stopped) puts the rider on the ground
beside the car.

## Units and conventions

- Physics space is metres, kilograms, seconds and radians: x right, y up, z forward.
- Wheel order is front left, front right, rear left, rear right.
- Gear ids are 0 reverse, 1 neutral, 2 first, and so on.
- Parameter structs keep the units of the production car data (inches, ft*lb, lb/in, mph, rpm); the
  simulation converts at construction.
- The step is FIXED_STEP = 1/60. The tuning assumes 60 Hz.

## Build and test

    clang++ -std=c++17 -O2 -ffp-contract=off -fno-fast-math -Wall -Wextra -Werror \
      -ISource/AtelierDriving/Private/Simulation \
      Source/AtelierDriving/Private/Simulation/*.cpp \
      Tests/Simulation/self_test.cpp -o /tmp/driving-self-test
    /tmp/driving-self-test

Keep the floating-point flags. The simulation relies on precise IEEE arithmetic and avoids FMA
contraction; do not add -ffast-math or architecture-specific reassociation. A host that compiles
these translation units should also keep them out of unity builds and use precise floating point.

## Out of scope

Car data import, car meshes, materials, animations, audio, streaming, traffic, pursuit, networking
and host integration are separate concerns. This module provides the simulation state and step only.
