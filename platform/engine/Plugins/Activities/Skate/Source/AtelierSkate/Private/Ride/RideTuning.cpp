#include "RideTuning.h"
#include "HAL/IConsoleManager.h"

namespace
{
    TAutoConsoleVariable<FString> CVarRideTune(TEXT("skate.RideTune"), TEXT(""),
        TEXT("Ride backend tuning overrides: Name=Value words (names as in RideTuning.h)"));

#define RIDE_FIELD(Name) { TEXT(#Name), STRUCT_OFFSET(FRideTuning, Name) }
    struct FTuningField { const TCHAR* Name; SIZE_T Offset; };
    const FTuningField Fields[] = {
        RIDE_FIELD(DeckHeight), RIDE_FIELD(AxleX), RIDE_FIELD(WheelRadius), RIDE_FIELD(RollingResistance), RIDE_FIELD(GravityLimit), RIDE_FIELD(StickGap),
        RIDE_FIELD(StickPerSpeed), RIDE_FIELD(StepUp), RIDE_FIELD(WallSlope), RIDE_FIELD(LaunchFactor), RIDE_FIELD(CrestWindow), RIDE_FIELD(CrestReach), RIDE_FIELD(GroundStep), RIDE_FIELD(CurbBail), RIDE_FIELD(CurbImpact),
        RIDE_FIELD(FallLineSteer), RIDE_FIELD(PushCycle),
        RIDE_FIELD(PushContact), RIDE_FIELD(PushContactLength), RIDE_FIELD(PushTarget), RIDE_FIELD(PushTargetSlope), RIDE_FIELD(PushTapTarget), RIDE_FIELD(PushAccel),
        RIDE_FIELD(PushTopSpeed), RIDE_FIELD(BrakeDelay), RIDE_FIELD(BrakeDecel), RIDE_FIELD(SlideAngle), RIDE_FIELD(SlideTurnRate), RIDE_FIELD(SlideDecel),
        RIDE_FIELD(SlideMinSpeed), RIDE_FIELD(MaxYawRate), RIDE_FIELD(YawRatePerSpeed), RIDE_FIELD(PivotRate), RIDE_FIELD(PivotSpeed), RIDE_FIELD(SteerResponse), RIDE_FIELD(LeanAngle),
        RIDE_FIELD(PumpExtension), RIDE_FIELD(CrouchRate), RIDE_FIELD(PopHeight), RIDE_FIELD(PopHeightQuick), RIDE_FIELD(PopLoadTime), RIDE_FIELD(NollieScale), RIDE_FIELD(PopFromGrindScale), RIDE_FIELD(PopDelay),
        RIDE_FIELD(LateFlickWindow), RIDE_FIELD(AirGravity), RIDE_FIELD(SpinRate), RIDE_FIELD(FlatSpinRate), RIDE_FIELD(SpinResponse), RIDE_FIELD(SpinCarry), RIDE_FIELD(LevelLead), RIDE_FIELD(VertSteepness),
        RIDE_FIELD(VertReturn), RIDE_FIELD(TransferPush), RIDE_FIELD(FlipTime), RIDE_FIELD(CleanYaw), RIDE_FIELD(SketchyYaw), RIDE_FIELD(BailTilt),
        RIDE_FIELD(SidewaysSafeSpeed), RIDE_FIELD(BailYawFast), RIDE_FIELD(BailImpact), RIDE_FIELD(WallBailSpeed), RIDE_FIELD(WallRestitution), RIDE_FIELD(GrindCapture),
        RIDE_FIELD(GrindAbove), RIDE_FIELD(GrindBelow), RIDE_FIELD(GrindAlign), RIDE_FIELD(GrindFriction), RIDE_FIELD(SlideFriction), RIDE_FIELD(GrindStall),
        RIDE_FIELD(GrindExitPop), RIDE_FIELD(GrindRelock), RIDE_FIELD(GrindMinAhead), RIDE_FIELD(GrindCross), RIDE_FIELD(GrindCorner), RIDE_FIELD(GrindJoin), RIDE_FIELD(GrindLockSpeed),
        RIDE_FIELD(ManualInstability), RIDE_FIELD(ManualControl), RIDE_FIELD(ManualWobble), RIDE_FIELD(ManualPitch), RIDE_FIELD(ManualFriction),
        RIDE_FIELD(BailSettle), RIDE_FIELD(GetUpTime), RIDE_FIELD(GetUpBoardReach), RIDE_FIELD(BailSlideDecel), RIDE_FIELD(CameraDistance), RIDE_FIELD(CameraHeight), RIDE_FIELD(CameraLookHeight),
        RIDE_FIELD(CameraLookAhead), RIDE_FIELD(CameraFOV), RIDE_FIELD(CameraSpeedFOV), RIDE_FIELD(CameraFOVSpeed), RIDE_FIELD(CameraTurnRate), RIDE_FIELD(CameraFollow),
        RIDE_FIELD(CameraFollowZ), RIDE_FIELD(MountBlend), RIDE_FIELD(DismountBlend), RIDE_FIELD(MeshSettle), RIDE_FIELD(BoardDissolveTime),
        RIDE_FIELD(BoardHoldTime), RIDE_FIELD(BoardLyingTime), RIDE_FIELD(BoardReach), RIDE_FIELD(MomentumDecay), RIDE_FIELD(MomentumBrake), RIDE_FIELD(ClipBlend), RIDE_FIELD(CarryBlend), RIDE_FIELD(RecoverBlend),
    };
#undef RIDE_FIELD
}

bool FRideTuning::Apply(const FString& Words)
{
    TArray<FString> Items; Words.ParseIntoArrayWS(Items);
    bool bOkay = true;
    for (const FString& Item : Items)
    {
        FString Name, Value;
        if (!Item.Split(TEXT("="), &Name, &Value) || !Value.IsNumeric()) { bOkay = false; continue; }
        const FTuningField* Field = nullptr;
        for (const FTuningField& F : Fields) if (Name.Equals(F.Name, ESearchCase::IgnoreCase)) { Field = &F; break; }
        if (!Field) { UE_LOG(LogTemp, Warning, TEXT("SKATE ride: no tuning value named %s"), *Name); bOkay = false; continue; }
        *reinterpret_cast<float*>(reinterpret_cast<uint8*>(this) + Field->Offset) = FCString::Atof(*Value);
    }
    return bOkay;
}

const FRideTuning& FRideTuning::Get()
{
    static FRideTuning Current;
    static FString Applied;
    const FString Words = CVarRideTune.GetValueOnGameThread();
    if (Words != Applied)
    {
        Current = FRideTuning();
        Current.Apply(Words);
        Applied = Words;
    }
    return Current;
}
