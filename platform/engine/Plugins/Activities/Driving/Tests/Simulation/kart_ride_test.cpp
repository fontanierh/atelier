// Uneven asphalt: the kart must stay composed over broken, rippled ground at a steady speed. Ride quality is the
// chassis' own vertical motion: too little damping or too little travel shows up here as a bouncy, scattered peak
// and wheels skipping off the surface, which the follow camera then passes straight to the player.

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

constexpr float PI = 3.14159265358979f;

/** Broken asphalt: a long undulation, a short ripple and a gentle crown across the lane. */
struct UnevenGround final : Ground
{
    float height(float x, float z) const
    {
        return 0.020f * std::sin(2.0f * PI * z / 3.1f) + 0.008f * std::sin(2.0f * PI * z / 0.95f + 1.1f) +
               0.006f * std::sin(2.0f * PI * x / 2.4f);
    }

    Vec3 normal(float x, float z) const
    {
        const float e = 0.01f;
        const float dx = (height(x + e, z) - height(x - e, z)) / (2.0f * e);
        const float dz = (height(x, z + e) - height(x, z - e)) / (2.0f * e);
        return normalize(Vec3{-dx, 1.0f, -dz});
    }

    bool hit(Vec3 origin, Vec3 dir, float max_distance, GroundHit& out) const override
    {
        if (dir.y >= -1e-6f)
        {
            return false;
        }
        // Vertical rays: march the ray and bisect the first crossing below the surface.
        float previous = 0.0f;
        float previous_gap = origin.y - height(origin.x, origin.z);
        for (int i = 1; i <= 16; ++i)
        {
            const float t = max_distance * float(i) / 16.0f;
            const Vec3 p = origin + dir * t;
            const float gap = p.y - height(p.x, p.z);
            if (gap <= 0.0f)
            {
                float low = previous, high = t;
                for (int k = 0; k < 12; ++k)
                {
                    const float mid = (low + high) * 0.5f;
                    const Vec3 q = origin + dir * mid;
                    if (q.y - height(q.x, q.z) <= 0.0f) high = mid;
                    else low = mid;
                }
                const Vec3 p_hit = origin + dir * high;
                out.distance = high;
                out.normal = normal(p_hit.x, p_hit.z);
                out.surface = SurfaceGrip{};
                return true;
            }
            previous = t;
            previous_gap = gap;
        }
        (void)previous_gap;
        return false;
    }
};

InputState cruise(float speed, float target)
{
    InputState in;
    const float error = target - speed;
    in.throttle = clamp(error * 0.6f, 0.0f, 1.0f);
    in.brake = clamp(-error * 0.5f, 0.0f, 1.0f);
    return in;
}
} // namespace

int main()
{
    UnevenGround ground;
    Vehicle car(kart_spec());
    if (!car.place_on_ground(ground, 0.0f, 0.0f, 1.0f, 0.0f))
    {
        std::printf("FAIL line %d: places on uneven ground\n", __LINE__);
        return 1;
    }
    for (int i = 0; i < 240; ++i)
    {
        car.step(FIXED_STEP, InputState{}, ground);
    }

    constexpr float TARGET = 8.0f;
    double sum_sq = 0.0, sum_jerk = 0.0;
    float peak = 0.0f;
    int samples = 0, contact_lost = 0, spikes = 0;
    float previous_vy = car.linear_velocity().y, previous_accel = 0.0f;
    for (int i = 0; i < 60 * 20; ++i)
    {
        car.step(FIXED_STEP, cruise(car.forward_speed(), TARGET), ground);
        const float vy = car.linear_velocity().y;
        const float accel = (vy - previous_vy) / FIXED_STEP;
        previous_vy = vy;
        if (i > 60)
        {
            sum_sq += double(accel) * accel;
            const float jerk = (accel - previous_accel) / FIXED_STEP;
            sum_jerk += double(jerk) * jerk;
            peak = std::fmax(peak, std::fabs(accel));
            if (std::fabs(accel) > 8.0f) ++spikes;
            ++samples;
            if (car.wheels_on_ground() < 4) ++contact_lost;
        }
        previous_accel = accel;
    }
    const float rms = float(std::sqrt(sum_sq / std::fmax(1, samples)));
    const float jerk = float(std::sqrt(sum_jerk / std::fmax(1, samples)));
    const float lost = samples ? 100.f * float(contact_lost) / float(samples) : 100.f;
    const float spike = samples ? 100.f * float(spikes) / float(samples) : 100.f;
    const float speed = car.forward_speed();
    std::printf("kart ride: %.1f m/s, vertical accel rms %.2f m/s2, peak %.2f m/s2, jerk %.1f, spikes %.1f%%, "
                "contact lost on %.1f%% of steps\n",
                speed, rms, peak, jerk, spike, lost);

    check(speed > 6.0f, "holds speed over broken asphalt", __LINE__);
    check(rms < 4.5f, "vertical motion stays smooth (rms)", __LINE__);
    check(peak < 12.0f, "no hard vertical spike", __LINE__);
    check(jerk < 280.0f, "no suspension chatter (jerk)", __LINE__);
    check(spike < 8.0f, "few hard vertical steps", __LINE__);
    check(lost < 2.0f, "wheels keep the surface", __LINE__);
    check(car.position().y > 0.10f, "does not sink into the road", __LINE__);
    if (failures == 0)
    {
        std::printf("kart ride test passed\n");
    }
    return failures == 0 ? 0 : 1;
}

