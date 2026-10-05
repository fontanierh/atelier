#include "SkateSettings.h"
#include "SkateFeel.h"
#include "HAL/IConsoleManager.h"

namespace
{
    TAutoConsoleVariable<FString> CVarSkateBackend(TEXT("skate.Backend"), TEXT(""),
        TEXT("Skating backend for the next mount: Ride or Native (empty: USkateSettings::Backend)"));
}

USkateSettings::USkateSettings() = default;

ESkateBackend USkateSettings::ActiveBackend()
{
    const FString Name = CVarSkateBackend.GetValueOnGameThread().TrimStartAndEnd();
    if (Name.Equals(TEXT("Ride"), ESearchCase::IgnoreCase)) return ESkateBackend::Ride;
    if (Name.Equals(TEXT("Native"), ESearchCase::IgnoreCase)) return ESkateBackend::Native;
    return GetDefault<USkateSettings>()->Backend;
}

FSkateFeel FSkateFeel::Defaults()
{
    const USkateSettings* S = GetDefault<USkateSettings>();
    FSkateFeel F;
    F.Difficulty = S->Difficulty; F.TruckTightness = S->TruckTightness; F.Pop = S->PopHeightScale; F.Spin = S->AirSpinScale;
    F.PushSpeed = S->PushSpeedScale; F.PushPower = S->PushPowerScale; F.VertAssist = S->VertAssist;
    return F;
}

bool FSkateFeel::Validate(FString& Error) const
{
    if (Difficulty != TEXT("easy") && Difficulty != TEXT("normal") && Difficulty != TEXT("hardcore"))
    { Error = FString::Printf(TEXT("Difficulty %s is not easy, normal or hardcore"), *Difficulty); return false; }
    struct FRange { const TCHAR* Name; float Value, Low, High; };
    const FRange Ranges[] = {
        {TEXT("TruckTightness"), TruckTightness, 0, 1}, {TEXT("Pop"), Pop, .5f, 2}, {TEXT("Spin"), Spin, .5f, 3},
        {TEXT("PushSpeed"), PushSpeed, .5f, 2}, {TEXT("PushPower"), PushPower, .5f, 3}, {TEXT("VertAssist"), VertAssist, 0, 1},
        {TEXT("FlickRadius"), FlickRadius, .5f, 2}, {TEXT("FlickWindow"), FlickWindow, .5f, 3}, {TEXT("FlickPace"), FlickPace, .5f, 2},
        {TEXT("StickDeadZone"), StickDeadZone, .25f, .6f}, {TEXT("StickReach"), StickReach, .6f, 1}, {TEXT("MouseFlick"), MouseFlick, .25f, 4},
        {TEXT("Gravity"), Gravity, .5f, 1.5f}, {TEXT("Boneless"), Boneless, .5f, 3}, {TEXT("Hippy"), Hippy, .5f, 3},
        {TEXT("RailMagnetism"), RailMagnetism, .25f, 3}, {TEXT("GrindPop"), GrindPop, .5f, 2}, {TEXT("GrindFriction"), GrindFriction, 0, 3},
        {TEXT("Braking"), Braking, .25f, 3}, {TEXT("Steering"), Steering, .5f, 2}, {TEXT("Carve"), Carve, .5f, 2}, {TEXT("Grip"), Grip, .5f, 2},
        {TEXT("Powerslide"), Powerslide, .25f, 3}, {TEXT("RollingFriction"), RollingFriction, 0, 3}, {TEXT("HillSpeed"), HillSpeed, 0, 2},
        {TEXT("Pump"), Pump, 0, 3}, {TEXT("Wobble"), Wobble, 0, 3}, {TEXT("WobbleOnset"), WobbleOnset, .5f, 3}, {TEXT("ManualDrift"), ManualDrift, 0, 3},
        {TEXT("Landing"), Landing, .5f, 3}, {TEXT("Impact"), Impact, .5f, 3}, {TEXT("GetUpDelay"), GetUpDelay, .25f, 2},
        {TEXT("CameraDistance"), CameraDistance, .6f, 1.6f}, {TEXT("CameraFOV"), CameraFOV, -20, 20}};
    for (const FRange& R : Ranges)
        if (!FMath::IsFinite(R.Value) || R.Value < R.Low || R.Value > R.High)
        { Error = FString::Printf(TEXT("%s %g is outside %g..%g"), R.Name, R.Value, R.Low, R.High); return false; }
    if (StickReach < StickDeadZone + .2f) { Error = TEXT("StickReach must be at least 0.2 past StickDeadZone"); return false; }
    if (AutoPush < -1 || AutoPush > 1 || AssistedAir < -1 || AssistedAir > 1) { Error = TEXT("AutoPush and AssistedAir are -1, 0 or 1"); return false; }
    Error.Reset(); return true;
}
