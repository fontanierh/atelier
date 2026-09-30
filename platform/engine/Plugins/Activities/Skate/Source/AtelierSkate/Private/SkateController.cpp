#include "SkateComponent.h"
#include "SkateSettings.h"
#include "SkateRails.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"

void USkateComponent::ResetControllers()
{
    const FString Difficulty = GetDefault<USkateSettings>()->Difficulty;
    Native = SkateNative::RetailSettings(Difficulty == TEXT("hardcore") ? SkateNative::Difficulty::Hardcore :
        Difficulty == TEXT("easy") ? SkateNative::Difficulty::Easy : SkateNative::Difficulty::Normal);
    NativePushAcceleration = NativePumpAcceleration = 0.f;
    NativeSteering = {}; NativePump = {}; NativeManual = {}; NativeLanding = {};
    NativeGestures.Patterns = SkateNative::RetailPatterns(); NativeGestures.Reset();
    SimulationClock = {}; RideClock = RideCrouch = NoInputTime = 0;
    PushHeld = PushTarget = LandingRecovery = ManualPitch = RailOffset = RailSideSpeed = 0;
    Flick.Reset(); Previous = In;
    Combo.Reset(); ComboPoints = 0; ComboIdle = ComboFade = 0.f; ShownCombo.Reset();
    bManual = bPushing = bPowerslide = false; ManualHold = 0; bManualLock = false;
}

FSkateTrick USkateComponent::ReadNativeFlick(float Dt)
{
    // Keep the existing load/crouch and mouse diagnostics. Recognition comes exclusively
    // from the authored point patterns, including their duplicate-name alternatives.
    Flick.UpdateLoad(In.Right, Dt);
    // The native graph mirrors the PAT trick names for regular stance (kickflip is down then up-left).
    const SkateNative::Point Sample{float(In.Right.X) * (bGoofy ? 1.f : -1.f), -float(In.Right.Y)};
    const auto Result = NativeGestures.Update(Sample, GetDefault<USkateSettings>()->Difficulty == TEXT("hardcore"));
    if (Result.Index < 0) return {};
    FString Name = UTF8_TO_TCHAR(NativeGestures.Patterns[Result.Index].Name.c_str());
    const bool Nollie = Name.RemoveFromStart(TEXT("N_")) || Name == TEXT("Nollie");
    struct Definition { const TCHAR* Key; const TCHAR* Label; float Flip, Shove; int32 Points; };
    static const Definition Tricks[] = {
        {TEXT("Ollie"), TEXT("Ollie"), 0, 0, 50}, {TEXT("Nollie"), TEXT("Ollie"), 0, 0, 50},
        {TEXT("Kickflip"), TEXT("Kickflip"), 1, 0, 150}, {TEXT("Heelflip"), TEXT("Heelflip"), -1, 0, 150},
        {TEXT("PopShuvit"), TEXT("Pop Shove-it"), 0, 180, 120}, {TEXT("FSPopShuvit"), TEXT("Frontside Pop Shove-it"), 0, -180, 120},
        {TEXT("VarialKickflip"), TEXT("Varial Kickflip"), 1, 180, 250}, {TEXT("VarialHeelflip"), TEXT("Varial Heelflip"), -1, -180, 250},
        {TEXT("Hardflip"), TEXT("Hardflip"), 1, -180, 350}, {TEXT("InwardHeelflip"), TEXT("Inward Heelflip"), -1, 180, 350},
        {TEXT("360PopShuvit"), TEXT("360 Shove-it"), 0, 360, 250}, {TEXT("FS360PopShuvit"), TEXT("Frontside 360 Shove-it"), 0, -360, 250},
        {TEXT("360Flip"), TEXT("360 Flip"), 1, 360, 450}, {TEXT("Laserflip"), TEXT("Laser Flip"), -1, -360, 450},
        {TEXT("360Hardflip"), TEXT("360 Hardflip"), 1, -360, 500}, {TEXT("360InwardHeelflip"), TEXT("360 Inward Heelflip"), -1, 360, 500}
    };
    for (const auto& D : Tricks) if (Name == D.Key)
    {
        FSkateTrick T;
        T.Name = Nollie ? (FString(D.Label) == TEXT("Ollie") ? FName(TEXT("Nollie")) : FName(*(FString(TEXT("Nollie ")) + D.Label))) : FName(D.Label);
        T.Flips = D.Flip; T.Shove = D.Shove; T.Points = D.Points + (Nollie ? 30 : 0);
        T.bNollie = Nollie; T.Strength = Flick.Power >= 0.f ? FMath::Lerp(Result.Strength, Flick.Power, .5f) : Result.Strength;
        Flick.LastDebug = FString::Printf(TEXT("PAT %d: %s (%.2f)"), Result.Index, *T.Name.ToString(), T.Strength);
        return T;
    }
    return {};
}

void USkateComponent::AssistGrind(float H)
{
    if (!RailSystem || LeaveRailCooldown > 0.f || AirTime < .08f || Vel.Z > 200.f ||
        (Trick.MovesBoard() && TrickProgress() < .78f)) return;
    // World adapter: predict descending rail-height crossings on the host game's polylines.
    // Native admission limits and displacement budgets apply before any correction.
    FVector BestCorrection = FVector::ZeroVector;
    float BestTime = 0.f, BestDistance = TNumericLimits<float>::Max();
    FCollisionQueryParams Query(SCENE_QUERY_STAT(SkateAssist), false, Rider);
    for (float Time = H; Time <= .35f; Time += H)
    {
        FVector Predicted = Pos + Vel * Time - FVector(0, 0, .5f * Native.Gravity * 100.f * Time * Time);
        float S; FVector Point, Tangent;
        const int32 Candidate = RailSystem->FindNear(Predicted, Native.GrindLockDistance * 100.f, -5.f, 8.f, S, Point, Tangent);
        if (Candidate == INDEX_NONE || FMath::Abs(Tangent.Z) > .9f) continue;
        FVector Perpendicular = Vel - Tangent * FVector::DotProduct(Vel, Tangent);
        const bool Ledge = RailSystem->Rails[Candidate].IsSlideSurface();
        if (FMath::Abs(Perpendicular.Z) * (1.f - FMath::Abs(Tangent.Z)) > Native.GrindMaxDown * 100.f ||
            Perpendicular.SizeSquared2D() > (Ledge ? Native.GrindMaxLedge : Native.GrindMaxRail) * 10000.f) continue;
        FVector Correction = FVector::VectorPlaneProject(Point - Predicted, Tangent); Correction.Z = 0.f;
        const FVector Adjusted = Vel + Correction / Time;
        const float Angle = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(FVector::DotProduct(Vel.GetSafeNormal(), Adjusted.GetSafeNormal())), -1.f, 1.f)));
        if (Angle > Native.GrindAdjustAngle || Correction.Size() >= BestDistance) continue;
        FHitResult Obstacle;
        if (GetWorld()->SweepSingleByChannel(Obstacle, Pos + FVector(0,0,12), Predicted + Correction + FVector(0,0,12), FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(8.f), Query)) continue;
        BestCorrection = Correction; BestTime = Time; BestDistance = Correction.Size();
    }
    if (BestTime > 0.f)
    {
        // The original stores per-frame and total offsets separately. Here the offset is
        // applied to our board root; both limits stay in metres in the native settings.
        const FVector Delta = (BestCorrection * (H / BestTime)).GetClampedToMaxSize(Native.GrindMaxDelta * 100.f * (H / SkateNative::Step));
        const FVector NewOffset = (AirAssistOffset + Delta).GetClampedToMaxSize(Native.GrindMaxOffset * 100.f);
        Pos += NewOffset - AirAssistOffset;
        AirAssistOffset = NewOffset;
    }
}
