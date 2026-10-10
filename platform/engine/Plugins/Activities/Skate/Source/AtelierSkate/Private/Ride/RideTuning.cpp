#include "RideTuning.h"
#include "HAL/IConsoleManager.h"

namespace
{
    TAutoConsoleVariable<FString> CVarRideTune(TEXT("skate.RideTune"), TEXT(""),
        TEXT("Ride tuning overrides: Name=Value words (names as in RideTuning.h)"));

#define RIDE_FIELD(Name) { TEXT(#Name), STRUCT_OFFSET(FRideTuning, Name) }
    struct FTuningField { const TCHAR* Name; SIZE_T Offset; };
    const FTuningField Fields[] = {
        RIDE_FIELD(WheelRadius), RIDE_FIELD(StepUp), RIDE_FIELD(StartRecover), RIDE_FIELD(WallSlope), RIDE_FIELD(BailSettle), RIDE_FIELD(GetUpBoardReach),
        RIDE_FIELD(MountBlend), RIDE_FIELD(DismountBlend), RIDE_FIELD(MeshSettle), RIDE_FIELD(BoardDissolveTime), RIDE_FIELD(BoardHoldTime), RIDE_FIELD(BoardLyingTime),
        RIDE_FIELD(BoardReach), RIDE_FIELD(MomentumDecay), RIDE_FIELD(MomentumBrake), RIDE_FIELD(ClipBlend), RIDE_FIELD(CarryBlend), RIDE_FIELD(RecoverBlend),
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
