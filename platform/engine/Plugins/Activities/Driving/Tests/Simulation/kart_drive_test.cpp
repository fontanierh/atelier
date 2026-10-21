// The go-kart the game drives: it must stand on its wheels, accelerate, brake, reverse and steer on flat ground.

#include "SimulationKart.h"
#include "SimulationVehicle.h"

#include <cmath>
#include <cstdio>

using namespace atelier::driving;

namespace
{
int failures = 0;

void check(bool ok, const char* what, int line)
{
    if (!ok)
    {
        std::printf("FAIL line %d: %s\n", line, what);
        ++failures;
    }
}

InputState drive(float throttle, float brake, float steer = 0.0f)
{
    InputState in;
    in.throttle = throttle;
    in.brake = brake;
    in.steer = steer;
    return in;
}

void steps(Vehicle& car, const Ground& ground, int count, const InputState& input)
{
    for (int i = 0; i < count; ++i)
    {
        car.step(FIXED_STEP, input, ground);
    }
}
} // namespace

int main()
{
    Vehicle car(kart_spec());
    FlatGround ground(0.0f);
    check(car.place_on_ground(ground, 0.0f, 0.0f, 1.0f, 0.0f), "places on flat ground", __LINE__);

    steps(car, ground, 120, drive(0.0f, 0.0f));
    check(car.wheels_on_ground() == 4, "four wheels carry it at rest", __LINE__);
    check(car.position().y > 0.20f && car.position().y < 0.40f, "rests near ride height", __LINE__);
    check((car.orientation() * Vec3{0.0f, 1.0f, 0.0f}).y > 0.9f, "stays upright", __LINE__);

    steps(car, ground, 240, drive(1.0f, 0.0f));
    const float speed = car.forward_speed();
    check(speed > 6.0f, "accelerates past 6 m/s in four seconds", __LINE__);
    check(car.gear() >= 2, "selects its forward gear", __LINE__);
    check(car.rpm() > 900.0f, "engine turns", __LINE__);

    const float before = car.forward_speed();
    steps(car, ground, 60, drive(0.0f, 1.0f));
    check(car.forward_speed() < before - 1.5f, "brakes", __LINE__);

    steps(car, ground, 240, drive(0.0f, 1.0f));
    check(car.forward_speed() < -1.0f, "reverses from rest when braking is held", __LINE__);

    Vehicle turning(kart_spec());
    check(turning.place_on_ground(ground, 0.0f, 0.0f, 1.0f, 0.0f), "places the second kart", __LINE__);
    steps(turning, ground, 120, drive(0.0f, 0.0f));
    steps(turning, ground, 120, drive(0.5f, 0.0f));
    steps(turning, ground, 60, drive(0.5f, 0.0f, 0.7f));
    const Vec3 forward = turning.orientation() * Vec3{0.0f, 0.0f, 1.0f};
    check(forward.x > 0.15f, "steering right turns the nose right", __LINE__);
    check(turning.wheels_on_ground() >= 2, "keeps its wheels down through the turn", __LINE__);

    if (failures == 0)
    {
        std::printf("kart drive test passed: %.1f m/s forward, %.1f m/s reverse\n", speed, car.forward_speed());
    }
    return failures == 0 ? 0 : 1;
}
