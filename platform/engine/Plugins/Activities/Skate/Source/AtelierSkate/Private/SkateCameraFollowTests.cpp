// Camera follow (CameraFollow, GameplayRuntime::Feel): the camera's anchor chases the rider through a VectorTracker
// capped at the authored SubjectTrackerMaxSpeed, 40 m/s, times camera_follow. At the stock cap a rider at 45 m/s pulls
// away from the camera by 5 m every second; at twice the cap the anchor stays on the rider.
#include "Simulation/CameraTracking.h"
#include "Simulation/CameraEffects.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSkateCameraFollowTest, "AtelierSkate.Camera.Follow",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

// A named namespace, not an anonymous one or a using-directive: a unity build shares this file's scope with others.
namespace SkateCameraFollow
{
    using namespace atelier::skate;
    // The anchor's gap behind a rider riding straight at Speed m/s for Seconds, at 60 updates a second, with the
    // anchor's authored acceleration limit (10000) and no smoothing (AnchorRigTracking above 8 m/s).
    float Gap(float Speed, float Cap, float Seconds)
    {
        camera::ScalarTrackerParameters P{};
        P.speed_clamp = Cap;
        P.acceleration_clamp_min = P.acceleration_clamp_max = 10000.f;
        camera::VectorTracker T;
        const float Dt = 1.f / 60.f;
        T.velocity = {Speed, 0.f, 0.f, 0.f};
        Vec4 Rider{};
        for (int Update = 1; Update <= int(Seconds * 60.f); ++Update)
        {
            Rider[0] = Speed * Dt * Update;
            T.Update(Dt, Rider, P);
        }
        return Rider[0] - T.position[0];
    }
    // The speed shake's offset across (one constant sample, 1 cm a unit of amplitude) and its clock after Seconds at Speed
    // m/s with the camera on the rider, stock (Fade false) or eased from 30 to 40 m/s as GameplayRuntime::Tune sets it for
    // camera_follow above 1. Amplitude 6 and rate 0.5 are the stock shake's values at full speed.
    void Shake(float Speed, bool Fade, float& Offset, float& Clock)
    {
        camera::ShakeSettings S{};
        S.amplitude_minimum = S.amplitude_maximum = 6.f; S.frequency_minimum = S.frequency_maximum = .5f;
        S.data_frames_per_second = 90.f; S.translation_multiplier = 1.f;
        if (Fade) { S.high_speed_start = 30.f; S.high_speed_end = 40.f; S.high_speed_amplitude = .25f; S.high_speed_frequency = .5f; }
        camera::ShakeSamples Samples;
        Samples.rotations = {Vec4{}, Vec4{}}; Samples.translations = {Vec4{1.f, 0.f, 0.f, 0.f}, Vec4{1.f, 0.f, 0.f, 0.f}};
        Basis3 Basis; Basis.columns[0] = {1.f, 0.f, 0.f}; Basis.columns[1] = {0.f, 1.f, 0.f}; Basis.columns[2] = {0.f, 0.f, 1.f};
        camera::ShakeEffect Effect; Basis3 Result; std::string Error;
        for (int Update = 0; Update < 60; ++Update) Effect.Update(1.f / 60.f, Speed, 0.f, Basis, true, Samples, S, Result, Error);
        Offset = Effect.translation[0]; Clock = Effect.time;
    }
}

bool FSkateCameraFollowTest::RunTest(const FString&)
{
    using namespace SkateCameraFollow;
    TestTrue(TEXT("Stock cap: a rider at 30 m/s is followed"), Gap(30.f, 40.f, 3.f) < .01f);
    const float Stock = Gap(45.f, 40.f, 3.f), Doubled = Gap(45.f, 80.f, 3.f);
    TestTrue(TEXT("Stock cap: a rider at 45 m/s is 15 m ahead of the anchor after 3 s"), Stock > 14.9f && Stock < 15.1f);
    TestTrue(TEXT("Twice the cap: the anchor stays on the rider"), Doubled < .01f);
    TestTrue(TEXT("Twice the cap: a rider at 70 m/s is followed too"), Gap(70.f, 80.f, 3.f) < .01f);
    float StockSlow, StockClockSlow, StockFast, StockClockFast, Slow, ClockSlow, Fast, ClockFast, Mid, ClockMid;
    Shake(20.f, false, StockSlow, StockClockSlow); Shake(45.f, false, StockFast, StockClockFast);
    Shake(20.f, true, Slow, ClockSlow); Shake(45.f, true, Fast, ClockFast); Shake(35.f, true, Mid, ClockMid);
    TestTrue(TEXT("Stock shake: as big and as fast at 45 m/s as at 20 m/s"), StockFast == StockSlow && StockClockFast == StockClockSlow && StockSlow > 5.9f);
    TestTrue(TEXT("Eased shake: unchanged below 30 m/s"), Slow == StockSlow && ClockSlow == StockClockSlow);
    TestTrue(TEXT("Eased shake: a quarter of the size at half the rate above 40 m/s"),
        FMath::IsNearlyEqual(Fast, StockFast * .25f, 1e-4f) && FMath::IsNearlyEqual(ClockFast, StockClockFast * .5f, 1e-4f));
    TestTrue(TEXT("Eased shake: between the two at 35 m/s"), Mid < Slow && Mid > Fast && ClockMid < ClockSlow && ClockMid > ClockFast);
    return true;
}
#endif
